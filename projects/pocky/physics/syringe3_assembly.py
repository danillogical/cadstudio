"""The syringe dispenser assembly for the generic MuJoCo runner.

Bodies: ``housing`` (free on the analytic floor on its four welded legs, or clamped to the table
on request), ``slider`` (child of the housing on the ``slider_x`` slide joint along +X, with the
clip-on handle welded to it), free ``packet`` bodies and the fixed analytic ``floor_world``. The scene is always built at stroke fraction 0.

Legs: the four pop-in legs are separate CAD parts welded to the housing, one rigid body, each with
its own part (mass from its CAD volume x PETG density) and its column and foot pad colliders; the
four pads are the housing's floor contacts. The two backstop clips are welded to the housing
the same way, with base and plate colliders clear of the slider's arms.

Home stop: pushed back, the slider's leg colliders stop on the clips' front faces, ``STOP_EPS``
behind them at home. That is a housing-slider contact, which MuJoCo only makes when the housing is
clamped: a free housing is the slider's parent body, and parent-child contacts are filtered. So
with the housing clamped the slide joint's lower limit is set back to just short of the plate
leaving the rear slot, and the clips are the stop; with a free housing the 0.5 mm guard stays the
home stop, as before. The six stop geoms (the clips' plate and base boxes, the slider legs) carry
their own, stiffer stop numerics (``CLIP_STOP_TIMECONST_S``), with priority so they win in the pair.

Spring: the printed spring is represented only by the joint's equivalent ``SpringSpec``. Its
solid is welded to the housing as the seat side (mass and visual, collision masked); it is not
a separate body and does not move with the slider.

Separator: ``"blade"`` seats packets 2..N tilted on the blade's rear edge, as the
prototype (``assembly.tilted_packet_frames``); ``"wedge"`` (default) has no blade over the stack, so packets
2..N are stacked flat (``flat_packet_frames``) and the housing carries the funnel wedge colliders.

Housing and slider are parent and child, so MuJoCo filters their contacts while the housing is
free; the clamped housing is welded to the world, which switches that filter off, so the rail
colliders are also collision-masked (see ``syringe3_colliders``). The slide joint is the guide;
the rails and grooves are not simulated. Plate vs packet, packet vs
housing and packet vs packet contacts are real.
"""
from __future__ import annotations

import math
import sys
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
from projects.pocky.geometry.linkage import STOP_EPS
from projects.pocky.geometry.syringe3 import SPRING_PRELOAD, syringe_layout, syringe_solids
from projects.pocky.params import Params
from projects.pocky.physics import colliders, syringe3_colliders as sc
from projects.pocky.physics.assembly import (
    CONTACT_TIMECONST_S,
    STOP_TIMECONST_S,
    TILT_SEAT_CLEARANCE_MM,
    VALID_CONTACT_TIMECONST_S,
    VALID_TIMESTEP_S,
    tilted_packet_frames,
)

__all__ = ["syringe_assembly", "flat_packet_frames", "VALID_CONTACT_TIMECONST_S",
           "VALID_TIMESTEP_S", "PULL_MAX_EFFORT_N", "SPRING_STIFFNESS_N_M", "pose_contacts"]

#: Slide guard of 0.5 mm beyond each end of the CAD stroke (and at home with a free housing).
SLIDER_GUARD_M = 0.0005
SLIDER_DAMPING = 0.5
#: Time constant of the leg-clip stop pair, stiffer than ``stop_timeconst_s``: let go from full
#: stroke, the slider hits the backstop clips at about 3.2 m/s, and a critically damped stop at
#: the 0.25 mm stop time constant would overshoot the 0.2 mm penetration bound (0.28 mm). It must
#: stay at least 2x the timestep; at a coarser step ``syringe_assembly`` falls back to
#: ``stop_timeconst_s`` for the stop pair and warns.
CLIP_STOP_TIMECONST_S = 1.5e-4
#: The stop pair's impedance: MuJoCo's default solimplimit, which the slide joint's limit uses.
CLIP_STOP_SOLIMP = (0.9, 0.95, 0.001, 0.5, 2.0)
#: Above every other geom's priority (PETG 0, packets 1), so the stop pair's settings win.
CLIP_STOP_PRIORITY = 2
#: The six stop geoms: the clips' plate and base boxes, and the slider legs that bear on them.
CLIP_STOP_IDS = frozenset({"clip_n_plate", "clip_n_base", "clip_s_plate", "clip_s_base",
                           "leg_n", "leg_s"})
#: Equivalent rate of the printed spring: ``geometry.syringe3.serpentine_rate`` estimates 199 N/m
#: (+-25%) for its 42 beams, 7.5 mm tall, and 200 N/m is in the approved option set (``options.py``).
SPRING_STIFFNESS_N_M = 200.0
#: Pull force bound. The spring at full stroke is k x (stroke + preload) = 200 x 0.095 = 19.0 N,
#: so the scenario's 30 N reaches the stroke with ~11 N for friction; 40 N leaves ~2x.
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


def _stop(cols, timeconst_s: float):
    """``cols`` with the leg-clip stop geoms given the stop pair's solref, solimp and priority."""
    return tuple(replace(c, solref=(timeconst_s, 1.0), solimp=CLIP_STOP_SOLIMP,
                         priority=CLIP_STOP_PRIORITY) if c.collider_id in CLIP_STOP_IDS else c
                 for c in cols)


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
    spring_stiffness_n_m: float = SPRING_STIFFNESS_N_M,
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

    clip_stop_s = CLIP_STOP_TIMECONST_S
    if clip_stop_s < 2.0 * timestep_s:
        clip_stop_s = stop_timeconst_s
        print(f"warning: backstop clip stop softened to stop_timeconst_s ({stop_timeconst_s:g} s) at "
              f"timestep {timestep_s:g} s, as CLIP_STOP_TIMECONST_S ({CLIP_STOP_TIMECONST_S:g} s) is "
              f"under 2x the timestep; impacts may exceed the penetration bound", file=sys.stderr)

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
        *(petg(f"clip_{tag}", solids[f"clip_{tag}"], _stop(sc.clip_colliders(lay, i), clip_stop_s), "structure",
               "retainer clip CAD solid x PETG density (snapped into the slab; welded to the housing)")
          for i, tag in enumerate(("n", "s"))),
    )
    # The handle is welded to the slider: same body, mass from its CAD volume x density.
    slider_parts = (
        petg("slider", solids["slider"], _stop(sc.slider_colliders(lay), clip_stop_s), "mechanism"),
        petg("handle", solids["handle"], sc.handle_colliders(lay), "mechanism",
             "handle CAD solid x PETG density (welded to the slider; PULL deboss kept in the mass)"),
    )
    found = {c.collider_id for part in housing_parts + slider_parts for c in part.colliders}
    if not CLIP_STOP_IDS <= found:
        raise ValueError(f"backstop stop geoms missing from the colliders: "
                         f"{sorted(CLIP_STOP_IDS - found)}")
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

    # Spring force is -k (q - reference). A reference of -SPRING_PRELOAD gives -k x 10 mm = -2.0 N
    # (200 N/m) at q = 0, i.e. toward -X (home), and -k (stroke + preload) at full stroke.
    # Clamped, the clips stop the slider (see the module notes), so the lower limit only keeps the
    # plate face SLIDER_GUARD_M inside the rear wall's outer face (5.9 mm back).
    back_m = ((lay.plate_rest_x - lay.rear_x) / 1000.0 - SLIDER_GUARD_M if housing_clamped
              else SLIDER_GUARD_M)
    slider_joint = JointSpec(
        joint_id="slider_x", body_id="slider", kind="slide", axis=(1.0, 0.0, 0.0),
        anchor_mm=(0.0, 0.0, 0.0),
        limits=(-back_m, lay.stroke / 1000.0 + SLIDER_GUARD_M),
        damping=SLIDER_DAMPING,
        spring=SpringSpec(spring_stiffness_n_m, -SPRING_PRELOAD / 1000.0,
                          _source(f"equivalent spring (beam-bending estimate, not measured), "
                                  f"installed {SPRING_PRELOAD:g} mm preload toward home")),
        stop_timeconst_s=stop_timeconst_s, stop_dampratio=1.0,
        source=_source(f"+X slide, {lay.stroke:.1f} mm CAD stroke with a 0.5 mm guard; "
                       + (f"{back_m * 1000.0:.1f} mm back, the backstop clips stop it at home"
                          if housing_clamped else "0.5 mm back, the home stop")),
    )

    bodies = (
        BodySpec(
            body_id="housing", parts=housing_parts, fixed_to_world=housing_clamped,
            fixture="diagnostic_fixture" if housing_clamped else "none",
            source=_source("housing clamped to the table (user-declared boundary condition)"
                           if housing_clamped
                           else "printed housing on its four legs, plus the welded spring seat "
                                "and retainer clips"),
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
        name="pocky_syringe3",
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


#: Deepest contact allowed when the slider is set to a pose, as the acceptance's penetration bound.
POSE_PENETRATION_MAX_M = 2.0e-4
#: A stop contact this deep or less is touching, not a defect: the CAD's stop gap.
POSE_TOUCH_M = STOP_EPS / 1000.0


def pose_contacts(spec: AssemblySpec, outdir, fractions=(0.0, 0.5, 1.0),
                  ignore_bodies=()) -> dict[float, list[tuple[str, str, float]]]:
    """Contacts deeper than ``POSE_PENETRATION_MAX_M`` with the slider set to each stroke fraction.

    Exports and compiles ``spec`` into ``outdir``, sets ``slider_x`` (everything else at its
    initial pose), runs ``mj_forward`` and returns ``(geom, geom, dist_m)`` for each such contact.
    A contact no deeper than ``POSE_TOUCH_M`` (the legs resting on the backstop clips) is touching
    and is never reported; only real penetration is.
    Contacts of ``ignore_bodies`` are skipped: packets stay where they were loaded, so a plate
    moved into them is not a collider defect. An empty list at every pose means no collider of
    the housing, legs, slider or handle overlaps another anywhere along the stroke.
    """
    from pathlib import Path

    from cadkit.physics import require_mujoco
    from cadkit.physics.scene import export_scene

    mujoco = require_mujoco()
    export = export_scene(spec, Path(outdir))
    model = mujoco.MjModel.from_xml_path(str(export.scene_xml))
    data = mujoco.MjData(model)
    joint = [b.joint for b in spec.bodies if b.joint is not None and b.joint.joint_id == "slider_x"][0]
    adr = model.joint("slider_x").qposadr[0]
    stroke_m = joint.limits[1] - SLIDER_GUARD_M  # fractions may be negative: behind home
    out = {}
    for fraction in fractions:
        mujoco.mj_resetData(model, data)
        data.qpos[adr] = fraction * stroke_m
        mujoco.mj_forward(model, data)
        deep = []
        for c in data.contact[:data.ncon]:
            bodies = {model.body(model.geom_bodyid[g]).name for g in (c.geom1, c.geom2)}
            if c.dist < -max(POSE_PENETRATION_MAX_M, POSE_TOUCH_M) and not bodies & set(ignore_bodies):
                deep.append((model.geom(c.geom1).name, model.geom(c.geom2).name, float(c.dist)))
        out[fraction] = deep
    return out


def _floor_shape():
    from build123d import Box, Pos

    return (Pos(0.0, 0.0, sc.FLOOR_TOP_Z - 0.5) * Box(400.0, 400.0, 1.0)).solid()
