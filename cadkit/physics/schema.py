"""Typed, immutable scene description: bodies, parts, frames and primitive colliders.

Units are explicit in every field name. Authoring is in **mm, degrees, g/cm3** — the units the
CAD already uses — and conversion to SI happens exactly once, in :mod:`cadkit.physics.scene`.

Two coordinate systems, deliberately distinct:

* **assembly** — the CAD's own coordinates, which is what ``ModelPart.shape`` is authored in.
* **body-local** — the frame a MuJoCo body is defined in.

The single mapping is::

    assembly_point = frame.pos_mm + R(frame.rot_deg) @ local_point

so a mesh or collider written in body-local coordinates and placed at ``frame`` lands back on
its CAD position. Nothing is transformed twice.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

Provenance = Literal["measured", "derived", "assumed", "calibrated"]
ColliderKind = Literal["box", "cylinder", "capsule", "sphere", "convex"]
PartRole = Literal["structure", "mechanism", "packet", "spare", "mount"]


@dataclass(frozen=True)
class Source:
    """Where a physical quantity came from. Mandatory on every physical input."""

    kind: Provenance
    note: str
    date: str | None = None


@dataclass(frozen=True)
class Frame:
    """A rigid pose in assembly coordinates: mm and degrees.

    ``rot_deg`` is XYZ Euler in build123d's ``Rot(X, Y, Z)`` order, i.e. the same convention
    the CAD uses, so a frame can be copied straight from a model's ``Pos``/``Rot``.
    """

    pos_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rot_deg: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def validate(self) -> None:
        for value in (*self.pos_mm, *self.rot_deg):
            if not math.isfinite(value):
                raise ValueError(f"Frame has a non-finite component: {self!r}")
        if len(self.pos_mm) != 3 or len(self.rot_deg) != 3:
            raise ValueError(f"Frame needs three position and three rotation values: {self!r}")

    @property
    def is_identity(self) -> bool:
        return self.pos_mm == (0.0, 0.0, 0.0) and self.rot_deg == (0.0, 0.0, 0.0)

    def location(self):
        """The equivalent build123d ``Location`` (assembly coordinates)."""
        from build123d import Pos, Rot

        return Pos(*self.pos_mm) * Rot(*self.rot_deg)

    def rotation_matrix(self) -> tuple[tuple[float, float, float], ...]:
        """3x3 rotation taken from build123d's own transform, so the convention cannot drift."""
        trsf = self.location().wrapped.Transformation()
        return tuple(
            tuple(float(trsf.Value(row, col)) for col in range(1, 4)) for row in range(1, 4)
        )

    def apply(self, point_mm: tuple[float, float, float]) -> tuple[float, float, float]:
        """Assembly point for a body-local point."""
        m = self.rotation_matrix()
        x, y, z = point_mm
        return tuple(  # type: ignore[return-value]
            self.pos_mm[i] + sum(m[i][j] * (x, y, z)[j] for j in range(3)) for i in range(3)
        )

    def to_local(self, point_mm: tuple[float, float, float]) -> tuple[float, float, float]:
        """Body-local point for an assembly point (inverse of :meth:`apply`)."""
        m = self.rotation_matrix()
        d = tuple(point_mm[i] - self.pos_mm[i] for i in range(3))
        # rotation matrices are orthonormal, so the inverse is the transpose
        return tuple(  # type: ignore[return-value]
            sum(m[j][i] * d[j] for j in range(3)) for i in range(3)
        )


@dataclass(frozen=True)
class ColliderSpec:
    """One convex primitive in **body-local** mm.

    ``box`` size is **half-extents**. ``cylinder``/``capsule`` size is ``(radius, half_length)``.
    ``sphere`` size is ``(radius,)``. ``convex`` needs ``vertices_mm``.
    """

    collider_id: str
    kind: ColliderKind
    size_mm: tuple[float, ...]
    pos_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rot_deg: tuple[float, float, float] = (0.0, 0.0, 0.0)
    role: PartRole = "structure"
    contype: int = 1
    conaffinity: int = 1
    vertices_mm: tuple[tuple[float, float, float], ...] | None = None  # reserved for convex
    source: Source = Source("derived", "declared primitive")

    def validate(self) -> None:
        _validate_id(self.collider_id, "collider_id")
        if self.kind == "convex":
            # Advertised in the type, not yet implemented: emitting type="mesh" without a
            # mesh asset makes MuJoCo reject the whole scene. Reject it here, at the point the
            # author can still act on it, until M2b adds the convex-mesh asset path with a
            # real convexity proof.
            raise ValueError(
                f"convex collider {self.collider_id!r} is not implemented yet; use box, "
                f"cylinder, capsule or sphere (convex meshes arrive with the M2b "
                f"collider-fidelity work)"
            )
        elif len(self.size_mm) < 1 or not all(math.isfinite(s) and s > 0.0 for s in self.size_mm):
            raise ValueError(
                f"collider {self.collider_id!r} needs positive finite size, got {self.size_mm!r}"
            )
        if self.kind == "box" and len(self.size_mm) != 3:
            raise ValueError(f"box collider {self.collider_id!r} needs 3 half-extents")
        if self.kind in ("cylinder", "capsule") and len(self.size_mm) != 2:
            raise ValueError(f"{self.kind} collider {self.collider_id!r} needs (radius, half_length)")
        if self.kind == "sphere" and len(self.size_mm) != 1:
            raise ValueError(f"sphere collider {self.collider_id!r} needs (radius,)")
        for v in (*self.pos_mm, *self.rot_deg):
            if not math.isfinite(v):
                raise ValueError(f"collider {self.collider_id!r} has a non-finite pose")
        for bits in (self.contype, self.conaffinity):
            if not 0 <= bits <= 0xFFFF:
                raise ValueError(f"collider {self.collider_id!r} has an out-of-range bitmask")


@dataclass(frozen=True)
class PartSpec:
    """One CAD solid taking part in the scene.

    ``shape`` is the build123d solid in **assembly** coordinates, or ``None`` when the part is
    a pure collider body with no CAD source. ``frame`` places the owning body; the part itself
    needs no frame because its shape is already in assembly coordinates.
    """

    part_id: str
    shape: object | None
    colliders: tuple[ColliderSpec, ...] = ()
    role: PartRole = "structure"
    density_g_cm3: float | None = None
    mass_kg: float | None = None
    source: Source = Source("derived", "CAD volume x density")

    def validate(self) -> None:
        _validate_id(self.part_id, "part_id")
        if self.shape is None and not self.colliders:
            raise ValueError(f"part {self.part_id!r} has neither a shape nor a collider")
        if self.shape is not None:
            if not bool(getattr(self.shape, "is_valid", False)):
                raise ValueError(f"part {self.part_id!r} shape is not a valid solid")
            if len(self.shape.solids()) != 1:
                raise ValueError(f"part {self.part_id!r} must be exactly one solid")
            volume = float(self.shape.volume)
            if not math.isfinite(volume) or volume <= 0.0:
                raise ValueError(f"part {self.part_id!r} has non-positive volume {volume!r}")
            if self.mass_kg is None and self.density_g_cm3 is None:
                raise ValueError(
                    f"part {self.part_id!r} has a shape but no density and no measured mass"
                )
        if self.mass_kg is not None:
            if not math.isfinite(self.mass_kg) or self.mass_kg <= 0.0:
                raise ValueError(f"part {self.part_id!r} measured mass must be positive, "
                                 f"got {self.mass_kg!r}")
        if self.density_g_cm3 is not None:
            if not math.isfinite(self.density_g_cm3) or self.density_g_cm3 <= 0.0:
                raise ValueError(f"part {self.part_id!r} density must be positive, "
                                 f"got {self.density_g_cm3!r}")
        seen: set[str] = set()
        for c in self.colliders:
            c.validate()
            if c.collider_id in seen:
                raise ValueError(f"part {self.part_id!r} has duplicate collider "
                                 f"{c.collider_id!r}")
            seen.add(c.collider_id)


@dataclass(frozen=True)
class SpringSpec:
    """An equivalent joint spring, in explicit SI units.

    ``stiffness`` is N/m for a slide joint and N m/rad for a hinge. ``reference`` is the
    joint coordinate at which the spring force is zero (m or rad). The force at any other
    coordinate is ``-stiffness * (q - reference)``, so a nonzero reference is a preload.
    Collision geometry never supplies elasticity; this is the only source of spring force.
    """

    stiffness: float
    reference: float = 0.0
    source: Source = Source("assumed", "declared equivalent spring")

    def __post_init__(self) -> None:
        # Fail at construction: a spec that cannot be valid must not be buildable, so no
        # caller can hold one and only discover the problem at export time.
        if not (math.isfinite(self.stiffness) and self.stiffness > 0.0):
            raise ValueError(f"spring stiffness must be finite and positive, got "
                             f"{self.stiffness!r}")
        if not math.isfinite(self.reference):
            raise ValueError(f"spring reference must be finite, got {self.reference!r}")

    def force_at(self, coordinate: float) -> float:
        """Signed spring force at a joint coordinate, in N (slide) or N m (hinge).

        ``F = -k (q - reference)``: zero at the reference, and **positive** below it (the
        spring pushes the coordinate back up toward the reference). A declared preload is a
        nonzero ``reference``, so ``SpringSpec(50.0, 0.02).force_at(0.0)`` is ``+1.0`` N.
        """
        return -self.stiffness * (coordinate - self.reference)

    def validate(self, kind: str) -> None:
        """Kind-specific check. Units are the caller's contract: N/m or N m/rad."""
        if kind not in ("hinge", "slide"):
            raise ValueError(f"spring kind must be hinge or slide, got {kind!r}")


@dataclass(frozen=True)
class JointSpec:
    """One joint connecting a body to its parent.

    Units are explicit: a ``slide`` joint's limits and spring reference are **metres**; a
    ``hinge`` joint's are **radians**. The emitted MJCF declares ``angle="radian"``, so every
    angle in the XML is the same number the caller wrote — nothing is converted and nothing
    is ambiguous.

    ``anchor_mm`` is the joint position in the **owning body's local frame**, in millimetres
    (the frame MuJoCo calls the body frame). ``axis`` is a direction in that same frame.

    ``stop_timeconst_s`` / ``stop_dampratio`` are the **physical compliance of the joint
    stop**, emitted as MJCF ``solreflimit``. They are absolute SI seconds and a dimensionless
    damping ratio, not timestep multiples, so refining ``dt`` changes integration resolution
    only and never the stop's stiffness. MuJoCo's default is 0.02 s, which is soft enough for a
    bounded input to drive a light body far past a short range; a fixture that tests a stop
    must declare its compliance instead of inheriting that default. ``None`` leaves the
    compiler default and must not be used by a stop test.
    """

    joint_id: str
    body_id: str
    kind: Literal["hinge", "slide"]
    axis: tuple[float, float, float] = (0.0, 0.0, 1.0)
    anchor_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    limits: tuple[float, float] | None = None
    damping: float = 0.0
    frictionloss: float = 0.0
    spring: SpringSpec | None = None
    armature: float = 0.0
    stop_timeconst_s: float | None = None
    stop_dampratio: float = 1.0
    source: Source = Source("derived", "declared joint")

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        _validate_id(self.joint_id, "joint_id")
        _validate_id(self.body_id, "joint body_id")
        if self.kind not in ("hinge", "slide"):
            raise ValueError(f"joint {self.joint_id!r} kind must be hinge or slide, "
                             f"got {self.kind!r}")
        n = math.sqrt(sum(a * a for a in self.axis))
        if not math.isfinite(n) or n <= 1e-12:
            raise ValueError(f"joint {self.joint_id!r} axis must be nonzero, got {self.axis!r}")
        for value in (*self.axis, *self.anchor_mm):
            if not math.isfinite(value):
                raise ValueError(f"joint {self.joint_id!r} has a non-finite geometry value")
        for name in ("damping", "frictionloss", "armature"):
            value = getattr(self, name)
            if not (math.isfinite(value) and value >= 0.0):
                raise ValueError(f"joint {self.joint_id!r} {name} must be finite and "
                                 f"non-negative, got {value!r}")
        if self.limits is not None:
            lo, hi = self.limits
            if not (math.isfinite(lo) and math.isfinite(hi)):
                raise ValueError(f"joint {self.joint_id!r} limits must be finite")
            if lo >= hi:
                raise ValueError(f"joint {self.joint_id!r} limit ordering is illegal: "
                                 f"{lo!r} >= {hi!r}")
            # Unit guardrails: a hinge written in degrees, or a slide written in mm, is the
            # most likely authoring error and would silently be off by 57x or 1000x.
            if self.kind == "hinge" and max(abs(lo), abs(hi)) > 2.0 * math.pi:
                raise ValueError(
                    f"hinge {self.joint_id!r} limits {self.limits!r} exceed one full turn "
                    f"in rad; degrees were probably intended (rad = deg * pi / 180)")
            if self.kind == "slide" and max(abs(lo), abs(hi)) > 1.0:
                raise ValueError(
                    f"slide {self.joint_id!r} limits {self.limits!r} exceed 1 m in m; "
                    f"millimetres were probably intended (m = mm / 1000)")
        if self.spring is not None:
            self.spring.validate(self.kind)
        if self.stop_timeconst_s is not None:
            if not (math.isfinite(self.stop_timeconst_s) and self.stop_timeconst_s > 0.0):
                raise ValueError(f"joint {self.joint_id!r} stop_timeconst_s must be finite "
                                 f"and positive, got {self.stop_timeconst_s!r}")
        if not (math.isfinite(self.stop_dampratio) and self.stop_dampratio > 0.0):
            raise ValueError(f"joint {self.joint_id!r} stop_dampratio must be finite and "
                             f"positive, got {self.stop_dampratio!r}")


@dataclass(frozen=True)
class ActuatorSpec:
    """A bounded force or torque input on one joint.

    ``max_effort`` is the **generalized joint effort** the actuator may transmit: N for a
    slide joint, N m for a hinge. It is a bound on ``gear * actuator_force``, i.e. on the
    force that actually enters the joint, not on the raw control signal — so it holds for any
    gear, including a negative one. The emitter sets both ``ctrlrange`` and ``forcerange`` to
    ``max_effort / |gear|``, which makes the transmitted effort exactly bounded in both
    directions.

    ``gear`` is the transmission ratio; 1.0 is a direct drive. Its sign selects the direction
    in which a positive control value drives the joint, and does not change the bound.
    """

    actuator_id: str
    joint_id: str
    kind: Literal["force", "torque"]
    max_effort: float
    gear: float = 1.0
    source: Source = Source("assumed", "declared bounded input")

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        _validate_id(self.actuator_id, "actuator_id")
        _validate_id(self.joint_id, "actuator joint_id")
        if self.kind not in ("force", "torque"):
            raise ValueError(f"actuator {self.actuator_id!r} kind must be force or torque")
        if not (math.isfinite(self.max_effort) and self.max_effort > 0.0):
            raise ValueError(f"actuator {self.actuator_id!r} max_effort must be finite and "
                             f"positive, got {self.max_effort!r}")
        if not (math.isfinite(self.gear) and self.gear != 0.0):
            raise ValueError(f"actuator {self.actuator_id!r} gear must be finite and nonzero")


@dataclass(frozen=True)
class BodySpec:
    """A rigid body: one or more parts welded together, at one pose in assembly coordinates."""

    body_id: str
    parts: tuple[PartSpec, ...]
    frame: Frame = Frame()
    fixed_to_world: bool = False
    fixture: Literal["none", "diagnostic_fixture", "analytic_fixture"] = "none"
    source: Source = Source("derived", "declared body")
    #: Optional collider-fidelity contract. When present, export rejects a recipe that fills a
    #: declared void or blocks a declared transit, so a wrong recipe cannot compile and PASS.
    fidelity: object | None = None
    #: Parent body id for a jointed body. ``None`` means a direct child of the world.
    parent: str | None = None
    #: The joint attaching this body to its parent. A jointed body never gets a freejoint.
    joint: JointSpec | None = None

    def validate(self) -> None:
        _validate_id(self.body_id, "body_id")
        if not self.parts:
            raise ValueError(f"body {self.body_id!r} has no parts")
        self.frame.validate()
        seen: set[str] = set()
        for part in self.parts:
            part.validate()
            if part.part_id in seen:
                raise ValueError(f"body {self.body_id!r} has duplicate part {part.part_id!r}")
            seen.add(part.part_id)
        if self.parent is not None:
            _validate_id(self.parent, "parent body_id")
            if self.parent == self.body_id:
                raise ValueError(f"body {self.body_id!r} cannot be its own parent")
        if self.joint is not None:
            self.joint.validate()
            # Report the most fundamental conflict first: a body welded to the world cannot
            # be jointed at all, so "needs a parent" would be a misleading next error.
            if self.fixed_to_world:
                raise ValueError(f"jointed body {self.body_id!r} cannot be fixed to the world")
            if self.joint.body_id != self.body_id:
                raise ValueError(
                    f"joint {self.joint.joint_id!r} body_id {self.joint.body_id!r} does not "
                    f"match the body that declares it ({self.body_id!r})")
            if self.parent is None:
                raise ValueError(f"jointed body {self.body_id!r} needs a parent body")
        elif self.parent is not None:
            raise ValueError(f"body {self.body_id!r} declares a parent but no joint")
        if self.fixed_to_world and self.fixture == "none":
            # A world-fixed body is a restraint. It must say why, so a product restraint can
            # never hide as an ordinary body.
            raise ValueError(
                f"body {self.body_id!r} is fixed to the world but declares no fixture; "
                f"state 'analytic_fixture' or 'diagnostic_fixture'"
            )


@dataclass(frozen=True)
class AssemblySpec:
    """A complete scene: bodies, gravity, and the solver settings that must be explicit."""

    name: str
    bodies: tuple[BodySpec, ...]
    gravity_m_s2: tuple[float, float, float] = (0.0, 0.0, -9.80665)
    timestep_s: float = 1.0e-3
    integrator: Literal["Euler", "RK4", "implicit", "implicitfast"] = "RK4"
    cone: Literal["pyramidal", "elliptic"] = "elliptic"
    solver: Literal["PGS", "CG", "Newton"] = "Newton"
    iterations: int = 100
    #: Sliding/torsional/rolling friction for structure contacts, declared not implied.
    friction: tuple[float, float, float] = (0.4, 0.005, 0.0001)
    #: Contact stiffness as an **absolute SI time constant** plus the damping ratio. MuJoCo's
    #: default is 0.02 s, soft enough to allow ~1 mm of penetration for a small probe. Absolute
    #: seconds, not timestep multiples: a timestep-refinement study must change integration
    #: resolution only, never contact compliance, or the two effects are confounded.
    contact_timeconst_s: float = 2.0e-3
    contact_dampratio: float = 1.0
    actuators: tuple[ActuatorSpec, ...] = ()
    source: Source = Source("derived", "declared assembly")

    def validate(self) -> None:
        _validate_id(self.name, "assembly name")
        if not self.bodies:
            raise ValueError("assembly has no bodies")
        if len({b.body_id for b in self.bodies}) != len(self.bodies):
            raise ValueError("assembly has duplicate body ids")
        for b in self.bodies:
            b.validate()
        if not all(math.isfinite(g) for g in self.gravity_m_s2):
            raise ValueError(f"gravity must be finite, got {self.gravity_m_s2!r}")
        gravity_magnitude = math.sqrt(sum(g * g for g in self.gravity_m_s2))
        # Zero gravity is an explicit diagnostic scene (no-gravity negative). Any other
        # magnitude outside 1..100 m/s2 is almost certainly a unit-scale error: 9.8 mm/s2
        # reads as 0.0098 m/s2 and would silently make a gravity test nearly motionless.
        if gravity_magnitude != 0.0 and not 1.0 <= gravity_magnitude <= 100.0:
            raise ValueError(
                f"gravity magnitude {gravity_magnitude!r} m/s2 is outside the plausible "
                f"1..100 m/s2 range; check for a unit-scale error (mm/s2 vs m/s2)")
        if not (math.isfinite(self.timestep_s) and 0.0 < self.timestep_s <= 1.0e-2):
            raise ValueError(f"timestep_s must be in (0, 0.01], got {self.timestep_s!r}")
        if not 1 <= self.iterations <= 10_000:
            raise ValueError(f"iterations out of range: {self.iterations!r}")
        if len(self.friction) != 3 or not all(
                math.isfinite(f) and f >= 0.0 for f in self.friction):
            raise ValueError(f"friction must be 3 finite non-negative values, "
                             f"got {self.friction!r}")
        if not (math.isfinite(self.contact_timeconst_s) and self.contact_timeconst_s > 0.0):
            raise ValueError("contact_timeconst_s must be finite and positive, got "
                             f"{self.contact_timeconst_s!r}")
        if self.contact_timeconst_s < 2.0 * self.timestep_s:
            # MuJoCo's refsafe safety floor makes the *effective* contact time constant
            # max(solref[0], 2*dt). Requiring only one timestep let a scene declare a contact
            # stiffer than the solver would actually use: at dt = 1 ms and tc = 1 ms the stored
            # value reads 1 ms while the solver silently uses 2 ms, so the declared compliance
            # was not the compliance being simulated.
            raise ValueError(
                f"contact_timeconst_s ({self.contact_timeconst_s!r}) must be at least two "
                f"timesteps ({2.0 * self.timestep_s!r}) at timestep {self.timestep_s!r}: "
                f"MuJoCo's refsafe floor is 2*dt, so a shorter time constant would be silently "
                f"softened and the declared compliance would not be the one simulated")
        if not (math.isfinite(self.contact_dampratio) and self.contact_dampratio > 0.0):
            raise ValueError("contact_dampratio must be positive, got "
                             f"{self.contact_dampratio!r}")
        for body in self.bodies:
            joint = body.joint
            if (joint is not None and joint.limits is not None
                    and joint.stop_timeconst_s is not None
                    and joint.stop_timeconst_s < 2.0 * self.timestep_s):
                raise ValueError(
                    f"joint stop {joint.joint_id!r}: stop_timeconst_s "
                    f"({joint.stop_timeconst_s!r}) must clear the refsafe floor "
                    f"2*dt ({2.0 * self.timestep_s!r}); effective compliance would change")
        self._validate_topology()
        joints = {b.joint.joint_id: b.joint for b in self.bodies if b.joint is not None}
        seen_actuators: set[str] = set()
        for actuator in self.actuators:
            actuator.validate()
            if actuator.actuator_id in seen_actuators:
                raise ValueError(f"duplicate actuator {actuator.actuator_id!r}")
            seen_actuators.add(actuator.actuator_id)
            if actuator.joint_id not in joints:
                raise ValueError(
                    f"actuator {actuator.actuator_id!r} references unknown joint "
                    f"{actuator.joint_id!r}")
            joint = joints[actuator.joint_id]
            expected = "torque" if joint.kind == "hinge" else "force"
            if actuator.kind != expected:
                raise ValueError(
                    f"actuator {actuator.actuator_id!r} is {actuator.kind!r} but drives a "
                    f"{joint.kind!r} joint, which needs {expected!r}")

    def _validate_topology(self) -> None:
        """Parent references must exist, be unique, and form a forest (no cycles)."""
        by_id = {b.body_id: b for b in self.bodies}
        joint_ids: set[str] = set()
        for body in self.bodies:
            if body.parent is not None and body.parent not in by_id:
                raise ValueError(f"body {body.body_id!r} has unknown parent {body.parent!r}")
            if body.joint is not None:
                jid = body.joint.joint_id
                if jid in joint_ids:
                    raise ValueError(f"duplicate joint id {jid!r}")
                joint_ids.add(jid)
        for body in self.bodies:
            seen: set[str] = set()
            cursor = body.body_id
            while cursor is not None:
                if cursor in seen:
                    raise ValueError(f"joint topology has a cycle through {body.body_id!r}")
                seen.add(cursor)
                cursor = by_id[cursor].parent

    def part_ids(self) -> list[str]:
        return [p.part_id for b in self.bodies for p in b.parts]

    def body_for_part(self, part_id: str) -> BodySpec:
        for body in self.bodies:
            if any(p.part_id == part_id for p in body.parts):
                return body
        raise KeyError(part_id)


_ID_ALLOWED = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")


def _validate_id(value: str, what: str) -> None:
    """IDs become MJCF names and asset filenames, so they must be safe and unique."""
    if not value or not isinstance(value, str):
        raise ValueError(f"{what} must be a non-empty string, got {value!r}")
    bad = set(value) - _ID_ALLOWED
    if bad:
        raise ValueError(f"{what} {value!r} contains unsafe characters {sorted(bad)}")
    if value in (".", "..") or value.startswith("."):
        raise ValueError(f"{what} {value!r} must not start with '.'")
    if len(value) > 64:
        raise ValueError(f"{what} {value!r} is longer than 64 characters")
    if "__" in value:
        # "__" separates body and part in asset filenames, so allowing it inside an id would
        # make (body "a__b", part "c") and (body "a", part "b__c") produce the same asset.
        raise ValueError(f"{what} {value!r} must not contain '__' (reserved as the "
                         f"body/part separator in asset names)")


def safe_filename(value: str) -> str:
    """A filename that cannot escape its directory, whatever the ID looked like."""
    _validate_id(value, "id")
    return value
