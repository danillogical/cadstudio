"""The original Pocky assembly for the generic MuJoCo runner.

The runtime scene is always built at CAD button fraction 0. The five S0 fractions are
initial joint coordinates derived from the actual CAD helpers, never a rebuilt scene:

    link = linkage_from(p)
    pose = pose_at_phi(link, phi_for_button_fraction(link, f))
    crank_phi = pose.phi - link.phi0
    rod_x     = -pose.button_travel / 1000
    pusher_x  = (pose.face_x - rest.face_x) / 1000

Static preflight uses the exact CAD solids at every fraction (``support.py``); the
collider/CAD audit uses the compiled transforms after each reset (``clearance_audit.py``).

Only the analytic floor is fixed to the world. It has no product role: its top is at
z = -19.2 mm, the chassis bed. Every other body is free or jointed, with the declared
idealizations listed in ``docs/mujoco-m5a-1-adapter-static-report.md``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from build123d import Box, Pos

from cadkit.physics.schema import (
    AssemblySpec,
    BodySpec,
    Frame,
    JointSpec,
    PartSpec,
    Source,
    SpringSpec,
)

from projects.pocky.geometry.linkage import (
    linkage_from,
    phi_for_button_fraction,
    pose_at_phi,
)
from projects.pocky.geometry.prototype import (
    CHASSIS_Z0,
    DEFAULT_GAP,
    PROTOTYPE_SPRING,
    compressed_length,
    moving_solids,
    static_solids,
)
from projects.pocky.params import Params
from projects.pocky.physics import colliders

#: The five static/compiled button fractions. Quarter stroke is not quarter pusher travel.
RESET_FRACTIONS = (0.0, 0.25, 0.5, 0.75, 1.0)

#: CAD joint-angle guard, just outside the 0..-1.0472 rad CAD swing.
CRANK_LIMITS = (-1.06, 0.01)
#: CAD-derived stop coordinates, metres. Home/forward gaps are 0.1 mm.
ROD_LIMITS = (-0.023194, 0.0001)
#: 50 mm pusher stroke plus a 0.5 mm guard at each declared end.
PUSHER_LIMITS = (-0.0005, 0.0505)

DEFAULT_SPRING_STIFFNESS_N_M = 500.0
SPRING_REFERENCE_M = 0.003
ROD_DAMPING = 0.5
CRANK_DAMPING = 0.005
PUSHER_DAMPING = 0.5
STOP_TIMECONST_S = 2.0e-3
CONTACT_TIMECONST_S = 2.0e-3


def _source(note: str) -> Source:
    return Source("derived", note)


@dataclass(frozen=True)
class ResetState:
    """One CAD-derived reset state, plus the helper pose it came from."""

    fraction: float
    crank_phi_rad: float
    rod_x_m: float
    pusher_x_m: float
    phi_rad: float
    face_x_mm: float
    button_travel_mm: float
    pusher_pin_x_mm: float
    pusher_pin_y_mm: float
    button_x_mm: float
    button_y_mm: float

    def joint_coordinates(self) -> dict[str, float]:
        """The only three joint coordinates a scenario may write at reset."""
        return {
            "crank_phi": self.crank_phi_rad,
            "rod_x": self.rod_x_m,
            "pusher_x": self.pusher_x_m,
        }


def reset_state(p: Params, fraction: float) -> ResetState:
    """Derive one reset from the actual CAD helpers. No interpolation, no second formula."""
    link = linkage_from(p)
    rest = pose_at_phi(link, link.phi0)
    pose = pose_at_phi(link, phi_for_button_fraction(link, fraction))
    return ResetState(
        fraction=float(fraction),
        crank_phi_rad=pose.phi - link.phi0,
        rod_x_m=-pose.button_travel / 1000.0,
        pusher_x_m=(pose.face_x - rest.face_x) / 1000.0,
        phi_rad=pose.phi,
        face_x_mm=pose.face_x,
        button_travel_mm=pose.button_travel,
        pusher_pin_x_mm=pose.pusher_pin_x,
        pusher_pin_y_mm=pose.pusher_pin_y,
        button_x_mm=pose.button_x,
        button_y_mm=pose.button_y,
    )


def reset_states(p: Params) -> tuple[ResetState, ...]:
    return tuple(reset_state(p, f) for f in RESET_FRACTIONS)


def expected_quarter_stroke_mm(p: Params) -> tuple[float, float]:
    """Pusher displacement at f=0.25 and f=0.75, from the CAD helpers."""
    return (reset_state(p, 0.25).pusher_x_m * 1000.0,
            reset_state(p, 0.75).pusher_x_m * 1000.0)


def _petg_part(part_id: str, shape, p: Params, *, role: str = "structure",
               colliders_=(), note: str = "CAD solid x PETG density") -> PartSpec:
    return PartSpec(
        part_id=part_id, shape=shape, colliders=tuple(colliders_), role=role,
        density_g_cm3=p.material.density_g_cm3, source=_source(note),
    )


def prototype_assembly(
    p: Params,
    *,
    button_fraction: float = 0.0,
    packets: int = 0,
    packet_mass_kg: float = 0.007,
    timestep_s: float = 1.0e-3,
    capacity: int | None = None,
    spring_stiffness_n_m: float = DEFAULT_SPRING_STIFFNESS_N_M,
) -> AssemblySpec:
    """Build the assembled prototype scene at CAD button fraction 0.

    Loaded packets and the 25-capacity variant are deliberately rejected: the baseline has
    zero packets and those variants need a later bounded planning approval. Static
    preflight uses :func:`projects.pocky.physics.support.assembly_solids`.
    """
    if button_fraction != 0.0:
        raise ValueError(
            "the runtime scene is built at CAD button fraction 0; the reset coordinates "
            "carry the other fractions (see reset_state)"
        )
    if packets != 0:
        raise ValueError(
            "loaded packets are not supported in the M5a-1 adapter/static increment; "
            "packet seating and stacks need a later bounded planning approval"
        )
    if capacity is not None:
        raise ValueError(
            "the 25-capacity tube is not supported in the M5a-1 adapter/static increment; "
            "it needs a later bounded planning approval"
        )
    if not (0.0 < timestep_s <= 0.01):
        raise ValueError(f"timestep_s must be in (0, 0.01], got {timestep_s!r}")
    if not (math.isfinite(spring_stiffness_n_m) and spring_stiffness_n_m > 0.0):
        raise ValueError(f"spring stiffness must be positive, got {spring_stiffness_n_m!r}")

    link = linkage_from(p)
    rest = pose_at_phi(link, link.phi0)
    static = static_solids(p, link, DEFAULT_GAP)
    moving = moving_solids(p, link, rest, compressed_length(0.0))

    body_colliders = colliders.body_colliders(p, link)
    chassis_colliders = colliders.chassis_colliders(p, link)
    lip_colliders = colliders.lip_colliders(p, link)
    crank_colliders = colliders.crank_colliders(p, link)
    rod_colliders = colliders.rod_colliders(p, link, rest)
    pusher_colliders = colliders.pusher_colliders(p, link, rest)

    # Body: housing plus the two installed shims. The shims are separate CAD parts and
    # separate boxes; no double count in mass (each part contributes once).
    body_parts = [
        _petg_part("body", static["body"], p,
                   colliders_=[c for c in body_colliders if not c.collider_id.startswith("shim_")]),
        _petg_part("shim_04_a", static["shim_04_a"], p,
                   colliders_=[c for c in body_colliders if c.collider_id == "shim_04_a"],
                   note="installed 0.4 mm shim CAD solid x PETG density"),
        _petg_part("shim_04_b", static["shim_04_b"], p,
                   colliders_=[c for c in body_colliders if c.collider_id == "shim_04_b"],
                   note="installed 0.4 mm shim CAD solid x PETG density"),
    ]

    chassis_parts = [
        _petg_part("chassis", static["chassis"], p,
                   colliders_=[c for c in chassis_colliders if c.collider_id != "spring_seat"]),
        _petg_part("spring_seat", static["spring_seat"], p,
                   colliders_=[c for c in chassis_colliders if c.collider_id == "spring_seat"],
                   note="chassis B spring insert CAD solid x PETG density"),
        _petg_part("peg_pivot", moving["peg_pivot"], p,
                   colliders_=colliders.peg_pivot_colliders(link), role="mechanism",
                   note="pivot peg CAD solid x PETG density (welded to the chassis)"),
    ]

    crank_parts = [
        _petg_part("crank", moving["crank"], p, colliders_=crank_colliders, role="mechanism"),
        _petg_part("peg_pusher", moving["peg_pusher"], p,
                   colliders_=colliders.peg_pusher_colliders(link, rest), role="mechanism",
                   note="pusher peg CAD solid x PETG density (welded to the crank)"),
    ]

    spring_mask = colliders.spring_mask_collider(link, rest, moving["spring"])
    rod_parts = [
        _petg_part("rod", moving["rod"], p, colliders_=rod_colliders, role="mechanism"),
        _petg_part("peg_button", moving["peg_button"], p,
                   colliders_=colliders.peg_button_colliders(link, rest), role="mechanism",
                   note="button peg CAD solid x PETG density (welded to the rod)"),
        _petg_part("spring", moving["spring"], p, colliders_=(spring_mask,), role="mechanism",
                   note="spring visual/mass, welded to the rod; collision masked"),
    ]

    pusher_parts = [
        _petg_part("pusher", moving["pusher"], p, colliders_=pusher_colliders, role="mechanism"),
    ]

    lip_parts = [
        _petg_part("lip", static["lip"], p, colliders_=lip_colliders),
    ]

    floor_shape = (Pos(0.0, 0.0, CHASSIS_Z0 - 0.5) * Box(400.0, 400.0, 1.0)).solid()
    floor_parts = [
        PartSpec(
            part_id="floor", shape=floor_shape,
            colliders=(colliders.floor_collider(p),), role="mount",
            density_g_cm3=p.material.density_g_cm3,
            source=_source("analytic floor fixture, not a product body"),
        ),
    ]

    crank_joint = JointSpec(
        joint_id="crank_phi", body_id="crank", kind="hinge",
        axis=(0.0, 0.0, 1.0),
        anchor_mm=(link.pivot_x, link.pivot_y, 0.5 * (link.crank_z0 + link.crank_z1)),
        limits=CRANK_LIMITS, damping=CRANK_DAMPING,
        stop_timeconst_s=STOP_TIMECONST_S, stop_dampratio=1.0,
        source=_source("CAD pivot (-78, -8), 60 deg swing with a guard"),
    )
    rod_joint = JointSpec(
        joint_id="rod_x", body_id="rod", kind="slide", axis=(1.0, 0.0, 0.0),
        anchor_mm=(0.0, 0.0, 0.0), limits=ROD_LIMITS, damping=ROD_DAMPING,
        spring=SpringSpec(spring_stiffness_n_m, SPRING_REFERENCE_M,
                          _source("assumed equivalent spring, installed 3 mm preload")),
        stop_timeconst_s=STOP_TIMECONST_S, stop_dampratio=1.0,
        source=_source("+X slide, 23.094 mm button stroke, CAD home/forward stops"),
    )
    pusher_joint = JointSpec(
        joint_id="pusher_x", body_id="pusher", kind="slide", axis=(1.0, 0.0, 0.0),
        anchor_mm=(0.0, 0.0, 0.0), limits=PUSHER_LIMITS, damping=PUSHER_DAMPING,
        stop_timeconst_s=STOP_TIMECONST_S, stop_dampratio=1.0,
        source=_source("+X slide, 50 mm CAD stroke with a 0.5 mm guard"),
    )

    bodies = (
        BodySpec(body_id="body", parts=tuple(body_parts),
                 source=_source("housing plus the two installed 0.4 mm shims; welded group"),
                 fidelity=colliders.body_fidelity(p, link)),
        BodySpec(body_id="lip", parts=tuple(lip_parts),
                 source=_source("independent lip; hook rails 0.15 mm behind the body bars"),
                 fidelity=colliders.lip_fidelity(p, link)),
        BodySpec(body_id="chassis", parts=tuple(chassis_parts),
                 source=_source("base frame; pivot peg and B insert welded to it"),
                 fidelity=colliders.chassis_fidelity(p, link)),
        BodySpec(body_id="crank", parts=tuple(crank_parts), parent="chassis",
                 joint=crank_joint,
                 source=_source("crank plus its welded pusher peg"),
                 fidelity=colliders.crank_fidelity(p, link)),
        BodySpec(body_id="rod", parts=tuple(rod_parts), parent="chassis", joint=rod_joint,
                 source=_source("rod plus button peg and masked spring visual/mass"),
                 fidelity=colliders.rod_fidelity(p, link)),
        BodySpec(body_id="pusher", parts=tuple(pusher_parts), parent="chassis",
                 joint=pusher_joint,
                 source=_source("pusher carriage, neck and bullnose"),
                 fidelity=colliders.pusher_fidelity(p, link, rest)),
        BodySpec(body_id="floor_world", parts=tuple(floor_parts), fixed_to_world=True,
                 fixture="analytic_fixture",
                 source=_source("legitimate analytic floor; top z = -19.2 mm")),
    )

    return AssemblySpec(
        name="pocky_prototype",
        bodies=bodies,
        gravity_m_s2=(0.0, 0.0, -9.80665),
        timestep_s=float(timestep_s),
        integrator="RK4", cone="elliptic", solver="Newton", iterations=100,
        friction=colliders.PETG_FRICTION,
        contact_timeconst_s=CONTACT_TIMECONST_S,
        contact_dampratio=1.0,
        source=_source("original CAD assembly at button fraction 0; no packets"),
    )


def export_assembly(p: Params, outdir: str | Path, **kwargs):
    """Export and compile the scene through the accepted generic exporter."""
    from cadkit.physics.scene import export_scene

    return export_scene(prototype_assembly(p, **kwargs), Path(outdir))
