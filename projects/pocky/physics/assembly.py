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
from dataclasses import dataclass, replace
from pathlib import Path

from build123d import Box, Pos, Rot

from cadkit.physics.schema import (
    ActuatorSpec,
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
    packet_solids,
    phi_for_button_fraction,
    pose_at_phi,
)
from projects.pocky.geometry.packet import packet as packet_solid
from projects.pocky.geometry.prototype import (
    BLADE_BITE,
    BLADE_T,
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
#: Validated contact/stop time constant and timestep (tc/4); see out/mujoco-sim-valid/sweep/results.md.
VALID_CONTACT_TIMECONST_S = 2.5e-4
VALID_TIMESTEP_S = 6.25e-5
#: Button force bound: spring at full press is 500 N/m x 26.094 mm = 13.05 N; 25 N adds ~2x margin for friction and contacts.
BUTTON_MAX_EFFORT_N = 25.0
#: Seating lift under the packet: 0, as the exact-solid overlap with every part is 0 at the CAD seat.
PACKET_SEAT_LIFT_MM = 0.0
#: Numerical seating clearance for the tilted packet 2, along its normal (0.001 mm; plan 5.1).
TILT_SEAT_CLEARANCE_MM = 0.001


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


def tilted_packet_frames(p: Params, count: int) -> list[Frame]:
    """Body frames (assembly mm / deg) for packets 1..``count``; the bottom packet is identity.

    Packet 2 rests on packet 1's rear top edge and the lip blade's rear edge, so its underside
    is tilted about Y. Packets 3..N are translated along that tilted normal from the already
    seated packet 2 (its origin is counted once). ``count=0`` returns no frames.
    """
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError(f"packet count must be a non-negative int, got {count!r}")
    if count == 0:
        return []
    k = p.packet
    blade_rear_x = k.length / 2.0 - BLADE_BITE
    blade_top_z = p.separator.gap + BLADE_T
    rear_x, rear_z = -k.length / 2.0, k.height
    angle = math.atan2(blade_top_z - rear_z, blade_rear_x - rear_x)
    deg = math.degrees(angle)
    normal = (-math.sin(angle), 0.0, math.cos(angle))
    seat = (Pos(rear_x, 0.0, rear_z) * Rot(0.0, -deg, 0.0) * Pos(-rear_x, 0.0, 0.0)).position
    base = (seat.X + normal[0] * TILT_SEAT_CLEARANCE_MM,
            seat.Y,
            seat.Z + normal[2] * TILT_SEAT_CLEARANCE_MM)
    frames = [Frame()]
    for i in range(1, count):
        step = (i - 1) * k.height
        frames.append(Frame(
            pos_mm=(base[0] + step * normal[0], base[1], base[2] + step * normal[2]),
            rot_deg=(0.0, -deg, 0.0)))
    return frames


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
    contact_timeconst_s: float = CONTACT_TIMECONST_S,
    stop_timeconst_s: float = STOP_TIMECONST_S,
    button_actuator: bool = False,
    chassis_clamped: bool = False,
) -> AssemblySpec:
    """Build the assembled prototype scene at CAD button fraction 0.

    The baseline has zero packets; ``packets=1`` adds the bottom packet as one free rigid box
    resting on the housing floor. ``packets=2..capacity_test`` add ``packet_02``, ``packet_03``,
    ... as free boxes on the tilted seat of plan 5.1 (see :func:`tilted_packet_frames`). The
    25-capacity variant is rejected: it needs a later bounded planning approval. Static
    preflight uses :func:`projects.pocky.physics.support.assembly_solids`.
    """
    if button_fraction != 0.0:
        raise ValueError(
            "the runtime scene is built at CAD button fraction 0; the reset coordinates "
            "carry the other fractions (see reset_state)"
        )
    max_packets = int(p.magazine.capacity_test)
    if isinstance(packets, bool) or not isinstance(packets, int) or not 0 <= packets <= max_packets:
        raise ValueError(
            f"packets must be an integer in 0..{max_packets} (the tube capacity), got {packets!r}"
        )
    if not (math.isfinite(packet_mass_kg) and 0.004 <= packet_mass_kg <= 0.010):
        raise ValueError(f"packet_mass_kg must be in [0.004, 0.010] kg, got {packet_mass_kg!r}")
    if capacity is not None:
        raise ValueError(
            "the 25-capacity tube is not supported in the M5a-1 adapter/static increment; "
            "it needs a later bounded planning approval"
        )
    if not (0.0 < timestep_s <= 0.01):
        raise ValueError(f"timestep_s must be in (0, 0.01], got {timestep_s!r}")
    if not (math.isfinite(spring_stiffness_n_m) and spring_stiffness_n_m > 0.0):
        raise ValueError(f"spring stiffness must be positive, got {spring_stiffness_n_m!r}")

    for name, value in (("contact_timeconst_s", contact_timeconst_s),
                        ("stop_timeconst_s", stop_timeconst_s)):
        if not (math.isfinite(value) and value > 0.0):
            raise ValueError(f"{name} must be positive, got {value!r}")

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

    packet_bodies: tuple[BodySpec, ...] = ()
    if packets >= 1:
        frames = tilted_packet_frames(p, packets)
        built = []
        for index, frame in enumerate(frames, start=1):
            name = "packet" if index == 1 else f"packet_{index:02d}"
            if index == 1:
                # The CAD bottom packet (shift 0) plus the seating lift, which is 0 (exact overlap is 0).
                shape = Pos(0.0, 0.0, PACKET_SEAT_LIFT_MM) * packet_solids(p, 0.0)["packet"]
                note = "bottom packet at its CAD seat in the magazine, free body"
            else:
                shape = frame.location() * packet_solid(p)
                note = ("packet on the tilted seat of plan 5.1: rear on packet 1's top edge, front "
                        "on the lip blade's rear edge" if index == 2
                        else "packet stacked on packet 2 along its tilted normal, free body")
            box = colliders.packet_collider(p, PACKET_SEAT_LIFT_MM)
            if index > 1:
                # Collider ids are scene-global geom names; packet 1 keeps "packet_box".
                box = replace(box, collider_id=f"{name}_box")
            part = PartSpec(
                part_id=name, shape=shape, colliders=(box,), role="packet",
                mass_kg=float(packet_mass_kg),
                source=Source("assumed", "rigid wrapped-packet proxy; 4-10 g range, no measurement"),
            )
            built.append(BodySpec(body_id=name, parts=(part,), frame=frame,
                                  source=_source(note)))
        packet_bodies = tuple(built)

    crank_joint = JointSpec(
        joint_id="crank_phi", body_id="crank", kind="hinge",
        axis=(0.0, 0.0, 1.0),
        anchor_mm=(link.pivot_x, link.pivot_y, 0.5 * (link.crank_z0 + link.crank_z1)),
        limits=CRANK_LIMITS, damping=CRANK_DAMPING,
        stop_timeconst_s=stop_timeconst_s, stop_dampratio=1.0,
        source=_source("CAD pivot (-78, -8), 60 deg swing with a guard"),
    )
    rod_joint = JointSpec(
        joint_id="rod_x", body_id="rod", kind="slide", axis=(1.0, 0.0, 0.0),
        anchor_mm=(0.0, 0.0, 0.0), limits=ROD_LIMITS, damping=ROD_DAMPING,
        spring=SpringSpec(spring_stiffness_n_m, SPRING_REFERENCE_M,
                          _source("assumed equivalent spring, installed 3 mm preload")),
        stop_timeconst_s=stop_timeconst_s, stop_dampratio=1.0,
        source=_source("+X slide, 23.094 mm button stroke, CAD home/forward stops"),
    )
    pusher_joint = JointSpec(
        joint_id="pusher_x", body_id="pusher", kind="slide", axis=(1.0, 0.0, 0.0),
        anchor_mm=(0.0, 0.0, 0.0), limits=PUSHER_LIMITS, damping=PUSHER_DAMPING,
        stop_timeconst_s=stop_timeconst_s, stop_dampratio=1.0,
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
                 # Opt-in restraint; the default free chassis leaves the scene unchanged.
                 fixed_to_world=chassis_clamped,
                 fixture="diagnostic_fixture" if chassis_clamped else "none",
                 source=_source(
                     "base frame; pivot peg and B insert welded to it; chassis clamped to the "
                     "table (user-declared boundary condition)" if chassis_clamped
                     else "base frame; pivot peg and B insert welded to it"),
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
        *packet_bodies,
        BodySpec(body_id="floor_world", parts=tuple(floor_parts), fixed_to_world=True,
                 fixture="analytic_fixture",
                 source=_source("legitimate analytic floor; top z = -19.2 mm")),
    )

    return AssemblySpec(
        name="pocky_prototype",
        bodies=bodies,
        gravity_m_s2=(0.0, 0.0, -9.80665),
        timestep_s=float(timestep_s),
        actuators=((ActuatorSpec("button", "rod_x", "force", BUTTON_MAX_EFFORT_N,
                                 source=_source("opt-in bounded button press on the rod slide"),),)
                   if button_actuator else ()),
        integrator="RK4", cone="elliptic", solver="Newton", iterations=100,
        friction=colliders.PETG_FRICTION,
        contact_timeconst_s=contact_timeconst_s,
        contact_dampratio=1.0,
        source=_source("original CAD assembly at button fraction 0; "
                       + ("no packets" if packets == 0 else "one bottom packet" if packets == 1
                          else f"{packets} packets on the tilted seat")),
    )


def export_assembly(p: Params, outdir: str | Path, **kwargs):
    """Export and compile the scene through the accepted generic exporter."""
    from cadkit.physics.scene import export_scene

    return export_scene(prototype_assembly(p, **kwargs), Path(outdir))
