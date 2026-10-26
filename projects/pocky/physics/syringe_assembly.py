"""The syringe dispenser assembly for the generic MuJoCo runner.

Bodies: ``housing`` (free on the analytic floor on its four welded legs, or clamped to the table
on request), ``slider`` (child of the housing on the ``slider_x`` slide joint along +X, with the
clip-on handle welded to it), free ``packet`` bodies and the fixed analytic ``floor_world``. The scene is always built at stroke fraction 0.

Legs: the four pop-in legs are separate CAD parts welded to the housing, one rigid body, each with
its own part (mass from its CAD volume x PETG density) and its column and foot pad colliders; the
four pads are the housing's floor contacts.

Spring: the printed spring is represented only by the joint's equivalent ``SpringSpec``. Its
solid is welded to the housing as the seat side (mass and visual, collision masked); it is not
a separate body and does not move with the slider.

Separator: ``"blade"`` seats packets 2..N tilted on the blade's rear edge, as the
prototype (``assembly.tilted_packet_frames``); ``"wedge"`` (default) has no blade over the stack, so packets
2..N are stacked flat (``flat_packet_frames``) and the housing carries the funnel wedge colliders.

Housing and slider are parent and child, so MuJoCo filters their contacts while the housing is
free; the clamped housing is welded to the world, which switches that filter off, so the rail
colliders are also collision-masked (see ``syringe_colliders``). The slide joint is the guide;
the rails and grooves are not simulated. Plate vs packet, packet vs
housing and packet vs packet contacts are real.
"""
from __future__ import annotations

import math
from dataclasses import replace

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

from projects.pocky.geometry.packet import packet as packet_solid
from projects.pocky.geometry.prototype import PRELOAD
from projects.pocky.geometry.syringe import syringe_layout, syringe_solids
from projects.pocky.params import Params
from projects.pocky.physics import colliders, syringe_colliders as sc
from projects.pocky.physics.assembly import (
    CONTACT_TIMECONST_S,
    DEFAULT_SPRING_STIFFNESS_N_M,
    STOP_TIMECONST_S,
    TILT_SEAT_CLEARANCE_MM,
    VALID_CONTACT_TIMECONST_S,
    VALID_TIMESTEP_S,
    tilted_packet_frames,
)

__all__ = ["syringe_assembly", "flat_packet_frames", "VALID_CONTACT_TIMECONST_S",
           "VALID_TIMESTEP_S", "PULL_MAX_EFFORT_N"]

#: Slide guard of 0.5 mm beyond each end of the CAD stroke.
SLIDER_GUARD_M = 0.0005
SLIDER_DAMPING = 0.5
#: Pull force bound. The spring at full stroke is k x (stroke + preload) = 500 x 0.0535 = 26.8 N,
#: above 25 N, so the prototype's 25 N cannot reach the stroke; 40 N leaves ~1.5x for friction.
PULL_MAX_EFFORT_N = 40.0
#: Wedge separator: numerical seating clearance between flat-stacked packets, as the tilted seat's.
FLAT_SEAT_CLEARANCE_MM = TILT_SEAT_CLEARANCE_MM


def flat_packet_frames(p: Params, count: int) -> list[Frame]:
    """Body frames for packets 1..``count`` stacked flat; the bottom packet is identity.

    Packet i (1-based) sits at z = (i - 1) x (packet height + ``FLAT_SEAT_CLEARANCE_MM``), untilted.
    """
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError(f"packet count must be a non-negative int, got {count!r}")
    pitch = p.packet.height + FLAT_SEAT_CLEARANCE_MM
    return [Frame() if i == 0 else Frame(pos_mm=(0.0, 0.0, i * pitch)) for i in range(count)]


def _source(note: str) -> Source:
    return Source("derived", note)


def syringe_assembly(
    p: Params,
    *,
    packets: int = 0,
    packet_mass_kg: float = 0.007,
    timestep_s: float = 1.0e-3,
    contact_timeconst_s: float = CONTACT_TIMECONST_S,
    stop_timeconst_s: float = STOP_TIMECONST_S,
    spring_stiffness_n_m: float = DEFAULT_SPRING_STIFFNESS_N_M,
    pull_actuator: bool = False,
    housing_clamped: bool = False,
    separator: str = "wedge",
) -> AssemblySpec:
    """Build the syringe scene at stroke fraction 0.

    ``packets=1`` adds the bottom packet flat on the floor; ``packets=2..N`` add ``packet_02``,
    ... on the tilted seat shared with the prototype (``assembly.tilted_packet_frames``) for the
    ``"blade"`` separator, or stacked flat (``flat_packet_frames``) for ``"wedge"`` (the default).
    """
    max_packets = int(p.magazine.capacity_test)
    if isinstance(packets, bool) or not isinstance(packets, int) or not 0 <= packets <= max_packets:
        raise ValueError(
            f"packets must be an integer in 0..{max_packets} (the tube capacity), got {packets!r}"
        )
    if not (math.isfinite(packet_mass_kg) and 0.004 <= packet_mass_kg <= 0.010):
        raise ValueError(f"packet_mass_kg must be in [0.004, 0.010] kg, got {packet_mass_kg!r}")
    if not (0.0 < timestep_s <= 0.01):
        raise ValueError(f"timestep_s must be in (0, 0.01], got {timestep_s!r}")
    if not (math.isfinite(spring_stiffness_n_m) and spring_stiffness_n_m > 0.0):
        raise ValueError(f"spring stiffness must be positive, got {spring_stiffness_n_m!r}")
    for name, value in (("contact_timeconst_s", contact_timeconst_s),
                        ("stop_timeconst_s", stop_timeconst_s)):
        if not (math.isfinite(value) and value > 0.0):
            raise ValueError(f"{name} must be positive, got {value!r}")

    lay = syringe_layout(p, separator)
    solids = syringe_solids(p, 0.0, separator=separator)
    tilted = separator == "blade"
    density = p.material.density_g_cm3

    def petg(part_id, shape, cols, role, note="CAD solid x PETG density"):
        return PartSpec(part_id=part_id, shape=shape, colliders=tuple(cols), role=role,
                        density_g_cm3=density, source=_source(note))

    housing_parts = (
        petg("housing", solids["housing"], sc.housing_colliders(lay), "structure"),
        petg("spring", solids["spring"], (sc.spring_mask_collider(solids["spring"]),),
             "mechanism", "spring CAD solid x PETG density (welded to the housing seat; "
             "collision masked)"),
        *(petg(f"leg_{i + 1}", solids[f"leg_{i + 1}"], sc.leg_colliders(lay, i), "structure",
               "leg CAD solid x PETG density (snapped into the slab; welded to the housing)")
          for i in range(len(lay.leg_xy))),
    )
    # The handle is welded to the slider: same body, mass from its CAD volume x density.
    slider_parts = (
        petg("slider", solids["slider"], sc.slider_colliders(lay), "mechanism"),
        petg("handle", solids["handle"], sc.handle_colliders(lay), "mechanism",
             "handle CAD solid x PETG density (welded to the slider; PULL deboss kept in the mass)"),
    )
    floor_parts = (
        PartSpec(part_id="floor", shape=_floor_shape(), colliders=(sc.floor_collider(),),
                 role="mount", density_g_cm3=density,
                 source=_source("analytic floor fixture, not a product body")),
    )

    packet_bodies: list[BodySpec] = []
    frames = tilted_packet_frames(p, packets) if tilted else flat_packet_frames(p, packets)
    for index, frame in enumerate(frames, start=1):
        name = "packet" if index == 1 else f"packet_{index:02d}"
        box = colliders.packet_collider(p, 0.0)
        if index > 1:
            box = replace(box, collider_id=f"{name}_box")
        part = PartSpec(
            part_id=name, shape=frame.location() * packet_solid(p), colliders=(box,),
            role="packet", mass_kg=float(packet_mass_kg),
            source=Source("assumed", "rigid wrapped-packet proxy; 4-10 g range, no measurement"))
        if not tilted and index > 1:
            note = f"packet stacked flat on packet {index - 1}, free body"
        else:
            note = ("bottom packet flat on the housing floor, free body" if index == 1
                    else "packet on the tilted seat: rear on packet 1's top edge, front on the blade"
                    if index == 2 else "packet stacked on packet 2 along its tilted normal, free body")
        packet_bodies.append(BodySpec(body_id=name, parts=(part,), frame=frame,
                                      source=_source(note)))

    # Spring force is -k (q - reference). A reference of -PRELOAD gives -k x 3 mm = -1.5 N (500 N/m)
    # at q = 0, i.e. toward -X (home), and -k (stroke + preload) at full stroke.
    slider_joint = JointSpec(
        joint_id="slider_x", body_id="slider", kind="slide", axis=(1.0, 0.0, 0.0),
        anchor_mm=(0.0, 0.0, 0.0),
        limits=(-SLIDER_GUARD_M, lay.stroke / 1000.0 + SLIDER_GUARD_M),
        damping=SLIDER_DAMPING,
        spring=SpringSpec(spring_stiffness_n_m, -PRELOAD / 1000.0,
                          _source("assumed equivalent spring, installed 3 mm preload toward home")),
        stop_timeconst_s=stop_timeconst_s, stop_dampratio=1.0,
        source=_source(f"+X slide, {lay.stroke:.1f} mm CAD stroke with a 0.5 mm guard"),
    )

    bodies = (
        BodySpec(
            body_id="housing", parts=housing_parts, fixed_to_world=housing_clamped,
            fixture="diagnostic_fixture" if housing_clamped else "none",
            source=_source("housing clamped to the table (user-declared boundary condition)"
                           if housing_clamped
                           else "printed housing on its four legs, plus the welded spring seat"),
            fidelity=sc.housing_fidelity(lay)),
        BodySpec(body_id="slider", parts=slider_parts, parent="housing", joint=slider_joint,
                 source=_source("slider: yoke, stem and plate, keel, arms, legs, welded handle"),
                 fidelity=sc.slider_fidelity(lay)),
        *packet_bodies,
        BodySpec(body_id="floor_world", parts=floor_parts, fixed_to_world=True,
                 fixture="analytic_fixture",
                 source=_source("legitimate analytic floor; top z = TABLE_Z")),
    )

    return AssemblySpec(
        name="pocky_syringe",
        bodies=bodies,
        gravity_m_s2=(0.0, 0.0, -9.80665),
        timestep_s=float(timestep_s),
        actuators=((ActuatorSpec("pull", "slider_x", "force", PULL_MAX_EFFORT_N,
                                 source=_source("opt-in bounded pull on the slider, +X")),)
                   if pull_actuator else ()),
        integrator="RK4", cone="elliptic", solver="Newton", iterations=100,
        friction=colliders.PETG_FRICTION,
        contact_timeconst_s=contact_timeconst_s,
        contact_dampratio=1.0,
        source=_source("syringe CAD assembly at stroke fraction 0; "
                       + ("" if tilted else "wedge separator; ")
                       + ("no packets" if packets == 0 else "one bottom packet" if packets == 1
                          else f"{packets} packets on the tilted seat" if tilted
                          else f"{packets} packets stacked flat")),
    )


def _floor_shape():
    from build123d import Box, Pos

    return (Pos(0.0, 0.0, sc.FLOOR_TOP_Z - 0.5) * Box(400.0, 400.0, 1.0)).solid()
