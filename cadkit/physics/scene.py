"""Assembly -> visual assets -> deterministic MJCF -> compiled model.

Conversion happens exactly once, here. Everything upstream is mm / degrees / g·cm⁻³.

Two coordinate systems are bridged by one rule:

* a part's ``shape`` is authored in **assembly** coordinates;
* its mesh is written **body-local**, by moving the shape with the inverse of the body frame;
* the MJCF body is placed at ``frame`` in metres.

So ``body_pose * mesh_vertices == cad_assembly_point``. Nothing is transformed twice.

Collision geometry is never derived from the visual mesh. A participating solid without an
explicit collider recipe is ``SCENE_INVALID``; the silent convex hull that MuJoCo would
otherwise apply is exactly the failure mode M0 identified.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import require_mujoco
from .inertia import body_inertial
from .schema import (COUPLING_SOLIMP, AssemblySpec, BodySpec, ColliderSpec, Frame,
                     JointCouplingSpec, safe_filename)
from .units import mm_to_m


class SceneInvalid(RuntimeError):
    """The assembly cannot be expressed as a valid physics scene."""


@dataclass(frozen=True)
class BodyReport:
    """Per-body facts, useful headlessly and asserted by the tests."""

    body_id: str
    mass_kg: float
    com_m: tuple[float, float, float]
    com_world_m: tuple[float, float, float]
    inertia_kg_m2: tuple[tuple[float, float, float], ...]
    n_colliders: int
    n_visual_meshes: int
    fixed: bool


@dataclass
class SceneExport:
    outdir: Path
    scene_xml: Path
    scene_hash: str
    asset_hashes: dict[str, str]
    bodies: list[BodyReport]
    fidelity: dict = field(default_factory=dict)
    model: object = None
    n_bodies: int = 0
    n_free_joints: int = 0
    n_geoms: int = 0
    report_json: Path | None = None

    def report(self) -> dict:
        return {
            "assembly": self.scene_xml.parent.name,
            "scene_hash": self.scene_hash,
            "n_bodies": self.n_bodies,
            "n_free_joints": self.n_free_joints,
            "n_geoms": self.n_geoms,
            "assets": self.asset_hashes,
            "fidelity": self.fidelity,
            "bodies": [
                {
                    "body_id": b.body_id,
                    "mass_kg": b.mass_kg,
                    "com_body_m": list(b.com_m),
                    "com_world_m": list(b.com_world_m),
                    "inertia_kg_m2": [list(r) for r in b.inertia_kg_m2],
                    "n_colliders": b.n_colliders,
                    "n_visual_meshes": b.n_visual_meshes,
                    "fixed": b.fixed,
                }
                for b in self.bodies
            ],
        }


def _f(value: float) -> str:
    """Stable float formatting: shortest round-trip text, no '-0'.

    ``repr`` gives the shortest decimal that parses back to the same double, so a pose
    written into the XML is the pose the compiler reads. A fixed ``%.9g`` would instead cap
    every transform at ~1e-9 relative error, which is text precision masquerading as a
    transform bug. Deterministic: CPython's shortest round-trip repr is platform-independent.
    """
    value = float(value)
    if value == 0.0:
        return "0"  # collapses -0.0 too
    return repr(value)


def _vec(values) -> str:
    return " ".join(_f(float(v)) for v in values)


def body_local_mesh(shape, frame: Frame):
    """The part's solid expressed in body-local coordinates."""
    return shape.moved(frame.location().inverse())


def _write_stl(shape, path: Path) -> None:
    """Write a binary STL in **millimetres**, using the repo's own mesher settings.

    The mm -> m conversion is applied by ``<mesh scale="0.001 0.001 0.001">`` in the XML, not
    here: build123d exports native millimetre vertices and ``scale()`` scales about the
    centroid, which would move the part. MuJoCo's mesh scale is a pure vertex multiply, so it
    is exact and happens exactly once, alongside the collider and body-pose conversions.
    """
    from build123d import export_stl

    export_stl(shape, str(path), tolerance=0.02, angular_tolerance=0.1, ascii_format=False)


def export_scene(spec: AssemblySpec, outdir: Path, *, compile_model: bool = True) -> SceneExport:
    """Write ``scene.xml`` plus assets, optionally compiling with the installed MuJoCo."""
    spec.validate()
    outdir = Path(outdir)
    assets = outdir / "assets"

    # Validate before touching the filesystem: an invalid spec must create nothing at all.
    _validate_geometry_participation(spec)
    fidelity = _validate_fidelity(spec)

    try:
        assets.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SceneInvalid(f"cannot create asset directory {assets}: {exc}") from exc

    asset_hashes: dict[str, str] = {}
    mesh_decls: list[str] = []
    body_reports: list[BodyReport] = []
    prepared: dict[str, tuple] = {}
    children_of: dict[str, list[str]] = {}
    roots: list[str] = []

    by_id = {b.body_id: b for b in spec.bodies}
    for body in spec.bodies:
        inertial = body_inertial(body)
        mesh_names: list[str] = []
        collider_xml: list[str] = []

        for part in body.parts:
            if part.role == "spare":
                # A spare is parked outside the unit: it is not part of the simulated scene,
                # so it contributes neither geometry nor mass. A declared collider, though, is
                # an explicit intent to collide; dropping it silently would make a restraint
                # the author wired up simply not exist.
                if part.colliders:
                    raise SceneInvalid(
                        f"spare part {part.part_id!r} in body {body.body_id!r} declares "
                        f"{len(part.colliders)} collider(s) that would never be simulated; "
                        f"remove them or use another role"
                    )
                continue
            if part.shape is not None:
                # "__" is reserved as the body/part separator, so ids cannot contain it and
                # this name is unambiguous (enforced in schema._validate_id).
                name = f"{body.body_id}__{part.part_id}"
                path = assets / f"{name}.stl"
                _write_stl(body_local_mesh(part.shape, body.frame), path)
                asset_hashes[f"assets/{name}.stl"] = _sha256(path)
                mesh_names.append(name)
                # Meshes are written in millimetres and scaled to metres by this attribute:
                # the conversion happens exactly once, here.
                mesh_decls.append(
                    f'    <mesh name="{name}" file="assets/{name}.stl" '
                    f'scale="{_f(mm_to_m(1.0))} {_f(mm_to_m(1.0))} {_f(mm_to_m(1.0))}"/>'
                )

            for collider in part.colliders:
                collider_xml.append(_collider_xml(collider))

        # World COM is pos + R @ com_local. Adding pos componentwise would ignore the body
        # rotation and disagree with MuJoCo's data.xipos for any rotated body.
        com_world = _apply_frame_m(body.frame, inertial.com_m)

        body_reports.append(BodyReport(
            body_id=body.body_id,
            mass_kg=inertial.mass_kg,
            com_m=inertial.com_m,
            com_world_m=com_world,  # type: ignore[arg-type]
            inertia_kg_m2=inertial.inertia_kg_m2,
            n_colliders=len(collider_xml),
            n_visual_meshes=len(mesh_names),
            fixed=body.fixed_to_world,
        ))
        prepared[body.body_id] = (body, inertial, mesh_names, collider_xml)
        if body.parent is None:
            roots.append(body.body_id)
        else:
            children_of.setdefault(body.parent, []).append(body.body_id)

    def render(body_id: str, depth: int) -> str:
        body, inertial, mesh_names, collider_xml = prepared[body_id]
        parent = by_id[body.parent] if body.parent else None
        nested = [render(child, depth + 1) for child in children_of.get(body_id, ())]
        return _body_xml(body, inertial, mesh_names, collider_xml, parent,
                         depth=depth, children=nested)

    xml_bodies = [render(body_id, 2) for body_id in roots]

    actuator_xml = [_actuator_xml(a) for a in spec.actuators]
    equality_xml = [_coupling_xml(c) for c in spec.couplings]
    xml = _assemble_xml(spec, mesh_decls, xml_bodies, actuator_xml, equality_xml)
    scene_path = outdir / "scene.xml"
    try:
        scene_path.write_text(xml, encoding="utf-8")
    except OSError as exc:
        raise SceneInvalid(f"cannot write {scene_path}: {exc}") from exc

    digest = _scene_hash(xml, asset_hashes, spec)

    model = None
    mujoco_version = None
    n_bodies = n_free = n_geoms = 0
    if compile_model:
        mujoco = require_mujoco()
        try:
            model = mujoco.MjModel.from_xml_path(str(scene_path))
        except Exception as exc:  # mujoco raises its own error type
            raise SceneInvalid(f"MuJoCo rejected the scene: {exc}") from exc
        n_bodies = int(model.nbody)
        # Count actual free joints, not model.njnt: hinges and slides are joints too, and
        # reporting them as "free" would misdescribe the assembly.
        n_free = sum(1 for j in range(model.njnt)
                     if model.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE)
        n_geoms = int(model.ngeom)
        mujoco_version = mujoco.__version__

    export = SceneExport(
        outdir=outdir,
        scene_xml=scene_path,
        scene_hash=digest,
        asset_hashes=asset_hashes,
        bodies=body_reports,
        fidelity=fidelity,
        model=model,
        n_bodies=n_bodies,
        n_free_joints=n_free,
        n_geoms=n_geoms,
    )

    # Provenance artifact: what was built, from which spec, with which assets and solver.
    # allow_nan=False so a non-finite value fails here rather than producing invalid JSON.
    report = export.report()
    report["assembly"] = spec.name
    report["mujoco_version"] = mujoco_version
    report["source"] = {"kind": spec.source.kind, "note": spec.source.note}
    report["fidelity"] = fidelity
    report["solver"] = {
        "timestep_s": spec.timestep_s, "integrator": spec.integrator,
        "cone": spec.cone, "solver": spec.solver, "iterations": spec.iterations,
        "gravity_m_s2": list(spec.gravity_m_s2),
    }
    # Canonical identity payload: replay recomputes the scene hash from the saved XML and
    # asset hashes with this exact payload, without touching CAD.
    if spec.couplings:
        report["couplings"] = [_coupling_record(c) for c in spec.couplings]
    report["scene_identity"] = scene_identity(xml, asset_hashes, spec)
    report_path = outdir / "report.json"
    try:
        report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n",
                               encoding="utf-8")
    except (OSError, ValueError) as exc:
        raise SceneInvalid(f"cannot write {report_path}: {exc}") from exc
    export.report_json = report_path
    return export


def _validate_fidelity(spec: AssemblySpec) -> dict[str, dict]:
    """Run each body's declared fidelity contract; a violation is SCENE_INVALID.

    This is what makes a wrong recipe fail *production export* rather than only a test: a
    collider that fills a declared void, blocks a declared transit, or omits real geometry
    cannot reach a compiled scene at all.
    """
    from .collision import validate_fidelity

    results: dict[str, dict] = {}
    for body in spec.bodies:
        contract = getattr(body, "fidelity", None)
        if contract is None:
            continue
        result = validate_fidelity(body, contract)
        results[body.body_id] = result.to_dict()
        if not result.ok:
            raise SceneInvalid(
                f"body {body.body_id!r} fails its declared collision-fidelity contract: "
                + "; ".join(result.violations)
            )
    return results


def _validate_geometry_participation(spec: AssemblySpec) -> None:
    """Every participating solid needs an explicit collider; nothing gets a silent hull."""
    for body in spec.bodies:
        for part in body.parts:
            if part.shape is not None and not part.colliders and part.role != "spare":
                raise SceneInvalid(
                    f"part {part.part_id!r} in body {body.body_id!r} has a CAD shape but no "
                    f"collider recipe; MuJoCo would silently collide with its convex hull. "
                    f"Declare primitive colliders, or set role='spare' to exclude it."
                )


def _apply_frame_m(frame: Frame, point_m: tuple[float, float, float]) -> tuple[float, ...]:
    """Apply a millimetre frame to a point already in metres."""
    local_mm = tuple(c * 1e3 for c in point_m)
    return tuple(mm_to_m(v) for v in frame.apply(local_mm))


def _collider_xml(collider: ColliderSpec) -> str:
    geom_type = {
        "box": "box", "cylinder": "cylinder", "capsule": "capsule",
        "sphere": "sphere", "convex": "mesh",
    }[collider.kind]
    size = " ".join(_f(mm_to_m(s)) for s in collider.size_mm)
    pos = _vec(mm_to_m(v) for v in collider.pos_mm)
    # Declared in XYZ Euler degrees; emitted as a quaternion so the compiler's angle
    # convention cannot reinterpret it, and so a rotated collider cannot drift from the
    # build123d rotation it was copied from.
    rot = _quat_from_rot_deg(collider.rot_deg)
    # Optional attributes are emitted only when set, so existing specs keep identical XML.
    extra = ""
    if collider.friction is not None:
        extra += f' friction="{_vec(collider.friction)}"'
    if collider.priority != 0:
        extra += f' priority="{collider.priority}"'
    if collider.solimp is not None:
        extra += f' solimp="{_vec(collider.solimp)}"'
    if collider.solref is not None:
        extra += f' solref="{_vec(collider.solref)}"'
    if collider.margin is not None:
        extra += f' margin="{_f(collider.margin)}"'
    return (
        f'<geom name="{safe_filename(collider.collider_id)}" type="{geom_type}" '
        f'size="{size}" pos="{pos}" quat="{rot}" '
        f'contype="{collider.contype}" conaffinity="{collider.conaffinity}"{extra} '
        f'condim="3" material="mat_structure"/>'
    )


def _quat_text(q, what: str) -> str:
    """Unit ``w x y z`` quaternion text from an OCP quaternion, sign-normalised.

    Normalising guards against a transform that is not exactly orthonormal; fixing the sign
    (``q`` and ``-q`` are the same rotation) keeps the emitted XML byte-stable.
    """
    w, x, y, z = float(q.W()), float(q.X()), float(q.Y()), float(q.Z())
    norm = math.hypot(math.hypot(w, x), math.hypot(y, z))
    if not (math.isfinite(norm) and norm > 0.0):
        raise SceneInvalid(f"{what} rotation cannot be normalised")
    values = (w / norm, x / norm, y / norm, z / norm)
    if values[0] < 0.0:
        values = tuple(-v for v in values)
    return _vec(values)


def _quat_from_rot_deg(rot_deg: tuple[float, float, float]) -> str:
    """``w x y z`` text for build123d's ``Rot(X, Y, Z)``."""
    from build123d import Rot

    return _quat_text(Rot(*rot_deg).wrapped.Transformation().GetRotation(),
                      f"collider rotation {rot_deg!r}")


def _relative_pose(body: BodySpec, parent: BodySpec | None) -> tuple[str, str]:
    """The body's pose **relative to its parent**, in metres and a unit quaternion.

    A jointed body is authored in assembly coordinates like every other body, so nesting it
    under a parent requires expressing its frame in the parent's frame. Doing this once, here,
    keeps local meshes, COM/inertia and joint anchors in their accepted conventions.

    The relative rotation is emitted as ``quat``, not ``euler``: a quaternion carries the
    rotation unambiguously, whereas extracting XYZ Euler angles and re-decomposing them in
    the compiler is an unverified convention round-trip that silently reorders rotations.
    MuJoCo's quaternion order is ``w x y z``.
    """
    if parent is None:
        rel = body.frame.location()
    else:
        # parent^-1 * child, using build123d's own location algebra
        rel = parent.frame.location().inverse() * body.frame.location()
    pos = rel.position
    quat = _quat_text(rel.wrapped.Transformation().GetRotation(),
                      f"body {body.body_id!r}")
    return (_vec((mm_to_m(pos.X), mm_to_m(pos.Y), mm_to_m(pos.Z))), quat)


def _joint_xml(body: BodySpec, indent: str = "      ") -> list[str]:
    """The joint element plus any spring reference it needs.

    Every angle here is already SI: ``JointSpec`` documents hinge limits and spring
    references in **radians**, and the compiler is told ``angle="radian"``, so nothing is
    converted in this function. That is the point: one convention, stated once, so a
    nonzero hinge preload cannot be off by 57x.
    """
    joint = body.joint
    if joint is None:
        return []
    axis = _vec(joint.axis)
    anchor = _vec(mm_to_m(v) for v in joint.anchor_mm)
    attrs = [f'name="{safe_filename(joint.joint_id)}"', f'type="{joint.kind}"',
             f'axis="{axis}"', f'pos="{anchor}"']
    if joint.limits is not None:
        lo, hi = joint.limits
        attrs.append(f'range="{_f(lo)} {_f(hi)}"')
        attrs.append('limited="true"')
        if joint.stop_timeconst_s is not None:
            # Absolute SI seconds, so refining the timestep changes resolution only and never
            # the stop's physical compliance.
            attrs.append(f'solreflimit="{_f(joint.stop_timeconst_s)} '
                         f'{_f(joint.stop_dampratio)}"')
    if joint.spring is not None:
        # MuJoCo's joint spring uses stiffness (N/m or N m/rad) and springref (m or rad).
        attrs.append(f'stiffness="{_f(joint.spring.stiffness)}"')
        attrs.append(f'springref="{_f(joint.spring.reference)}"')
    for name in ("damping", "frictionloss", "armature"):
        value = getattr(joint, name)
        if value:
            attrs.append(f'{name}="{_f(value)}"')
    return [f'{indent}<joint {" ".join(attrs)}/>']


def _body_xml(body: BodySpec, inertial, mesh_names: list[str], collider_xml: list[str],
              parent: BodySpec | None = None, depth: int = 2,
              children: list[str] | None = None) -> str:
    """One body element, with its children nested inside it (``children`` pre-rendered).

    Nesting is what makes the parent graph real: a child rendered as a sibling would compile
    with ``body_parentid == 0`` and its parent-relative pose would be interpreted in world
    coordinates, so every jointed assembly would move wrongly even though its numbers looked
    right in the XML.
    """
    pos, quat = _relative_pose(body, parent)
    i = np.array(inertial.inertia_kg_m2, dtype=float)
    diag = np.diag(i)
    offdiag = max(abs(i[0][1]), abs(i[0][2]), abs(i[1][2]))
    # MuJoCo accepts a full inertia tensor via fullinertia; use it whenever the body is not
    # axis-aligned in its own frame, so an off-diagonal term is never silently dropped.
    if offdiag > 1e-15 * max(1.0, float(np.max(np.abs(i)))):
        inertia_attr = (
            f'fullinertia="{_f(i[0][0])} {_f(i[1][1])} {_f(i[2][2])} '
            f'{_f(i[0][1])} {_f(i[0][2])} {_f(i[1][2])}"'
        )
    else:
        inertia_attr = f'diaginertia="{_vec(diag)}"'

    pad = "  " * depth
    inner = "  " * (depth + 1)
    lines = [f'{pad}<body name="{safe_filename(body.body_id)}" pos="{pos}" quat="{quat}">']
    if body.joint is not None:
        # A jointed body must never also get a freejoint: that would make it unconstrained.
        lines.extend(_joint_xml(body, inner))
    elif not body.fixed_to_world:
        lines.append(f'{inner}<freejoint name="{safe_filename(body.body_id)}_free"/>')
    lines.append(
        # inertial.com_m is already in metres; converting again would put the COM at the
        # body origin and silently discard an offset COM.
        f'{inner}<inertial pos="{_vec(inertial.com_m)}" '
        f'mass="{_f(inertial.mass_kg)}" {inertia_attr}/>'
    )
    for name in mesh_names:
        # Visual only: contype/conaffinity 0 means this geom never collides.
        lines.append(
            f'{inner}<geom name="{name}_visual" type="mesh" mesh="{name}" '
            f'contype="0" conaffinity="0" group="1" material="mat_visual"/>'
        )
    lines.extend(f"{inner}{line}" for line in collider_xml)
    lines.extend(children or [])
    lines.append(f'{pad}</body>')
    return "\n".join(lines)


def _actuator_xml(actuator) -> str:
    """One ``motor`` whose **transmitted** generalized effort is bounded.

    MuJoCo's ``ctrlrange`` limits the control signal; the generalized force actually applied
    is ``gear * actuator_force``. With ``gear != 1`` a ctrlrange alone therefore does not bound
    the joint force — a gear of 4 and a ctrlrange of +-2 N would transmit +-8 N. ``forcerange``
    bounds ``actuator_force`` (the motor's own force), so ``|gear| * forcerange`` is the
    transmitted bound. Setting both to ``max_effort / |gear|`` makes the transmitted force
    exactly ``max_effort`` in either direction, for either sign of gear.

    ``max_effort`` is therefore the **generalized joint effort**: N for a slide joint, N m for
    a hinge, after the gear ratio. A negative gear reverses direction without changing the
    bound.
    """
    gear = float(actuator.gear)
    motor_limit = actuator.max_effort / abs(gear)
    return (
        f'    <motor name="{safe_filename(actuator.actuator_id)}" '
        f'joint="{safe_filename(actuator.joint_id)}" gear="{_f(gear)}" '
        f'ctrllimited="true" ctrlrange="{_f(-motor_limit)} {_f(motor_limit)}" '
        f'forcelimited="true" forcerange="{_f(-motor_limit)} {_f(motor_limit)}"/>'
    )


def _coupling_xml(coupling: JointCouplingSpec) -> str:
    """One joint equality: ``q_joint1 = polycoef[0] + polycoef[1] * q_joint2 + ...``.

    MuJoCo constrains ``joint1`` as a polynomial of ``joint2``, so the follower is ``joint1``
    and the driver ``joint2``. Only the linear term is set; both joints have a zero reference
    position, so the relation holds from the joints' zero with no offset. ``solref`` is the
    coupling's declared absolute time constant and ``solimp`` is fixed, so the compliance is
    stated in the XML instead of inherited from MuJoCo's softer equality default.
    """
    return (
        f'    <joint name="{safe_filename(coupling.name)}" '
        f'joint1="{safe_filename(coupling.follower)}" '
        f'joint2="{safe_filename(coupling.driver)}" '
        f'polycoef="0 {_f(coupling.ratio)} 0 0 0" '
        f'solref="{_f(coupling.timeconst_s)} {_f(coupling.dampratio)}" '
        f'solimp="{_vec(COUPLING_SOLIMP)}"/>'
    )


def _assemble_xml(spec: AssemblySpec, meshes: list[str], bodies: list[str],
                  actuators: list[str] | None = None,
                  equalities: list[str] | None = None) -> str:
    g = _vec(spec.gravity_m_s2)
    mesh_xml = "\n".join(meshes)
    body_xml = "\n".join(bodies)
    # Optional contact numerics are emitted only when set, so existing specs keep identical XML.
    solimp = _vec(spec.contact_solimp) if spec.contact_solimp is not None else "0.95 0.99 0.001"
    geom_extra = ""
    if spec.contact_margin_m is not None:
        geom_extra += f' margin="{_f(spec.contact_margin_m)}"'
    if spec.contact_gap_m is not None:
        geom_extra += f' gap="{_f(spec.contact_gap_m)}"'
    option_extra = ""
    if spec.noslip_iterations > 0:
        option_extra += f' noslip_iterations="{spec.noslip_iterations}"'
    if spec.impratio is not None:
        option_extra += f' impratio="{_f(spec.impratio)}"'
    return f"""<mujoco model="{safe_filename(spec.name)}">
  <!-- Generated by cadkit.physics.scene. Regenerate; do not edit. -->
  <compiler angle="radian" coordinate="local"/>
  <option timestep="{_f(spec.timestep_s)}" integrator="{spec.integrator}" cone="{spec.cone}"
          solver="{spec.solver}" iterations="{spec.iterations}" gravity="{g}"{option_extra}/>
  <visual><global offwidth="1280" offheight="960"/></visual>
  <default>
    <geom condim="3" friction="{_vec(spec.friction)}"
          solref="{_f(spec.contact_timeconst_s)} {_f(spec.contact_dampratio)}"
          solimp="{solimp}"{geom_extra}/>
  </default>
  <asset>
{mesh_xml}
    <material name="mat_visual" rgba="0.72 0.74 0.78 1"/>
    <material name="mat_structure" rgba="0.45 0.50 0.58 1"/>
  </asset>
  <worldbody>
    <body name="world_frame"/>
{body_xml}
  </worldbody>
{_actuator_block(actuators or [])}{_equality_block(equalities or [])}</mujoco>
"""


def _actuator_block(actuators: list[str]) -> str:
    if not actuators:
        return ""
    return "  <actuator>\n" + "\n".join(actuators) + "\n  </actuator>\n"


def _equality_block(equalities: list[str]) -> str:
    if not equalities:
        return ""
    return "  <equality>\n" + "\n".join(equalities) + "\n  </equality>\n"


def scene_identity(xml: str, asset_hashes: dict[str, str], spec: AssemblySpec) -> dict:
    """The canonical semantic scene identity payload.

    It is written into ``report.json`` so replay can recompute the scene hash from the saved
    XML and asset hashes without regenerating CAD.
    """
    identity = {
        "xml": xml,
        "assets": asset_hashes,
        "assembly": spec.name,
        "bodies": [
            {"id": b.body_id, "fixed": b.fixed_to_world, "fixture": b.fixture,
             "parts": [p.part_id for p in b.parts]}
            for b in spec.bodies
        ],
    }
    # Added only when present, so an uncoupled scene keeps the hash it always had.
    if spec.couplings:
        identity["couplings"] = [_coupling_record(c) for c in spec.couplings]
    return identity


def _coupling_record(coupling: JointCouplingSpec) -> dict:
    return {"name": coupling.name, "driver": coupling.driver, "follower": coupling.follower,
            "ratio": coupling.ratio, "timeconst_s": coupling.timeconst_s,
            "dampratio": coupling.dampratio}


def compute_scene_hash(identity: dict) -> str:
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def _scene_hash(xml: str, asset_hashes: dict[str, str], spec: AssemblySpec) -> str:
    return compute_scene_hash(scene_identity(xml, asset_hashes, spec))


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
