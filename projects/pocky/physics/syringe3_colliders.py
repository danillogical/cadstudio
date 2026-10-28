"""Explicit box colliders and fidelity contracts for the syringe dispenser.

Every collider is a box in **body-local** millimetres, written feature by feature from
``geometry/syringe3.py``; nothing is hulled. Both bodies use identity frames, so local
coordinates are the stroke-fraction-0 assembly coordinates.

The handle is a separate CAD part but is welded to the slider: one rigid body, with its own
part (mass from its CAD volume x PETG density) and its own colliders for the bar, the two runners
and the two T-slide tails. The tails fill the leg sockets (0.25 mm clearance, so the leg boxes are
solid there and the tails overlap them, which is harmless inside one body). The debossed PULL
text, the detent leaf slot and ridge, the 2 mm top-edge radii, the 1 mm bottom chamfers and the
plan-view corner radii are ignored: every collider is the outer box of its feature.

The housing is concave, so it is decomposed: floor slab (split around the spring channel), the two
channel lips as stacked boxes, side walls, the rear wall split around the slot, the rear ramp (toe land,
side blocks, a core box behind its face, and its face as a box rotated about Y), the exit wall above the window, the blade,
the cheeks with their lead-in, and the two V rails as stacked boxes. With the wedge separator the blade is
gone and each side funnel wedge is a box rotated about Z for the ramp face below the lead-in and a
straight box after it, plus one rotated box under each of the two flat lead-in faces (over the ramp
and after it), so a packet landing on a lead-in rests on its true slope and slides in, rather than
perching on the flat top of a stacked strip. The four legs are separate CAD parts welded to the housing
body, like the handle on the slider: each is a column box and a foot pad box, the outer boxes of
its cylinders, and the pads' undersides are the housing's only floor contacts. The two backstop
clips are welded to the housing the same way: each is a base box under the slab and a plate box
outside the arm, ``SLIDE_CLEAR`` off it. At home their front faces stand ``STOP_EPS`` behind the
slider legs' boxes, so the legs stop on them if the slider is pushed back (with the housing
clamped; a free housing's contacts with its child slider are filtered). The snap pins
of the legs and clips sit in the slab's sockets, inside the slab boxes, which are solid there.
Nothing else fills the space under the slab between the legs. The slider's two arms are
solid boxes, so the rail grooves are filled. That is deliberate: the slide joint is the guide,
the arms touch nothing else, and the rail boxes are collision-masked (contype/conaffinity 0).
The mask is needed because MuJoCo filters parent/child contacts only while the parent is a
free body; with the housing clamped to the world the filter is off and the filled grooves would
jam on the rails. Pusher plate vs packet, packet vs housing and packet vs packet contacts are
real.

Friction conventions are those of ``colliders.py``: PETG 0.40 priority 0, packet 0.30 priority
1, analytic floor 0.50.

Every dimension comes from ``geometry/syringe3.py`` (constants and ``SyringeLayout``), so the colliders
follow a CAD change; only the box decomposition below is written by hand.
"""
from __future__ import annotations

import math
from dataclasses import replace

from cadkit.physics.collision import VOID_TOL_MM, FidelitySpec, ProbeSpec, TransitSpec, contains
from cadkit.physics.schema import ColliderSpec

from projects.pocky.geometry.prototype import CHEEK_TOP, PROTOTYPE_SPRING
from projects.pocky.geometry.syringe3 import (
    ARM_T,
    ARM_Z0,
    BAR_D,
    BAR_Z0,
    BAR_Z1,
    CHANNEL_Z0,
    CLIP_X,
    FOOT_D,
    FOOT_T,
    HEAD_HW,
    HLEG_D,
    JOINT_CLEAR,
    KEEL_HALF_W,
    LEG_W,
    LEG_X0,
    LEG_X1,
    LIP_DEG,
    LIP_SLOT_HALF_W,
    LIP_T,
    NECK_HW,
    RAIL_D,
    RAIL_DEG,
    RAIL_HALF,
    RAIL_X,
    RAIL_ZC,
    PLATE_LIP_LAND,
    PLATE_UNDERCUT,
    PLATE_UNDERCUT_DEG,
    RAMP_DEG,
    WEDGE_LEAD_IN_DEG,
    SLIDE_CLEAR,
    SPRING_H,
    SPRING_WALL_CLEAR,
    SPRING_Z0,
    TABLE_Z,
    TAIL_TOP,
    YOKE_T,
    SyringeLayout,
    _head_x,
    _leg_yc,
)
from projects.pocky.params import Params
from projects.pocky.physics.colliders import (
    COVERAGE_GAP_MM,
    CRITICAL_TOL_MM,
    FLOOR_FRICTION,
    PETG_FRICTION,
    PETG_PRIORITY,
    _b,
    _src,
)

#: Analytic floor: top at the table, where the four legs' foot pads stand.
FLOOR_TOP_Z = TABLE_Z
#: Plate stem is split here so the plate face is its own box.
PLATE_BOX_LEN = 5.0
#: Rail V approximated by this many stacked boxes per side.
RAIL_STEPS = 4
#: Cheek lead-in wedge approximated by this many stacked boxes per side.
LEAD_IN_STEPS = 3
#: Spring channel lip (50 degree underside) approximated by this many stacked boxes per side.
LIP_STEPS = 4
#: Wedge lead-in box thickness, normal to the lead-in face, into the wedge.
WEDGE_LEAD_T = 1.0
#: The lead-in over the funnel ramp is split along the funnel line into this many boxes, each
#: reaching just past the bore wall, so none reaches through the side wall into the slider's arms.
WEDGE_LEAD_SEGMENTS = 5
#: How far each lead-in box reaches past the bore wall, and the least wall it must leave outside.
WEDGE_LEAD_WALL_REACH = 0.1
WEDGE_LEAD_WALL_KEEP = 0.2
#: Wedge ramp box thickness, outward from the ramp face into the wedge and side wall.
WEDGE_RAMP_T = 2.0
#: Rear ramp face box thickness, from the sloped face into the ramp and the rear wall.
REAR_RAMP_T = 2.0


def _rot_deg(x_axis, y_axis, z_axis) -> tuple[float, float, float]:
    """``rot_deg`` whose ``Rot(a, b, c) = Rx(a) Ry(b) Rz(c)`` takes the local axes to these unit vectors."""
    m = [[x_axis[i], y_axis[i], z_axis[i]] for i in range(3)]
    b = math.asin(max(-1.0, min(1.0, m[0][2])))
    a = math.atan2(-m[1][2], m[2][2])
    c = math.atan2(-m[0][1], m[0][0])
    return math.degrees(a), math.degrees(b), math.degrees(c)


def _cross(u, v):
    return (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])


def _channel_y() -> float:
    return PROTOTYPE_SPRING.amplitude / 2.0 + SPRING_WALL_CLEAR


def floor_collider() -> ColliderSpec:
    """The analytic floor: fixed to the world, top at the table, z = TABLE_Z (the legs' foot pads)."""
    return _b("floor_box", (-200.0, 200.0, -200.0, 200.0, FLOOR_TOP_Z - 1.0, FLOOR_TOP_Z),
              "analytic floor fixture, top at the legs' foot pads", role="mount",
              friction=FLOOR_FRICTION)


def spring_mask_collider(spring_shape) -> ColliderSpec:
    """One non-colliding box so the spring visual participates in the schema."""
    bb = spring_shape.bounding_box()
    return ColliderSpec(
        collider_id="spring_mask", kind="box",
        size_mm=((bb.max.X - bb.min.X) / 2.0, (bb.max.Y - bb.min.Y) / 2.0,
                 (bb.max.Z - bb.min.Z) / 2.0),
        pos_mm=((bb.min.X + bb.max.X) / 2.0, (bb.min.Y + bb.max.Y) / 2.0,
                (bb.min.Z + bb.max.Z) / 2.0),
        contype=0, conaffinity=0, role="mechanism",
        source=_src("spring visual/mass; collision masked, the joint spring is the elasticity"),
    )


# --------------------------------------------------------------------------- housing
def housing_colliders(lay: SyringeLayout) -> tuple[ColliderSpec, ...]:
    """Housing at its only pose: slab, walls, slot, window, blade, shelf, cheeks, rails (legs apart)."""
    sy, by, top, ch = lay.side_y, lay.bore_y, lay.top, _channel_y()
    slot = lay.slot_w / 2.0
    out = [
        _b("slab_base", (lay.rear_x, lay.shelf_x, -sy, sy, lay.slab_z0, CHANNEL_Z0),
           "floor slab under the spring channel; solid over the leg sockets"),
        _b("floor_front", (lay.seat_x, lay.shelf_x, -sy, sy, CHANNEL_Z0, 0.0),
           "floor and shelf in front of the spring seat"),
        _b("floor_strip_n", (lay.rear_x, lay.seat_x, ch, sy, CHANNEL_Z0, 0.0),
           "floor beside the spring channel, +Y"),
        _b("floor_strip_s", (lay.rear_x, lay.seat_x, -sy, -ch, CHANNEL_Z0, 0.0),
           "floor beside the spring channel, -Y"),
        _b("wall_n", (lay.rear_x, lay.exit_x, by, sy, 0.0, top), "side wall +Y"),
        _b("wall_s", (lay.rear_x, lay.exit_x, -sy, -by, 0.0, top), "side wall -Y"),
        _b("rear_top", (lay.rear_x, lay.bore_x0, -by, by, lay.slot_h, top),
           "rear wall above the slot"),
        _b("rear_side_n", (lay.rear_x, lay.bore_x0, slot, by, 0.0, lay.slot_h),
           "rear wall beside the slot, +Y"),
        _b("rear_side_s", (lay.rear_x, lay.bore_x0, -by, -slot, 0.0, lay.slot_h),
           "rear wall beside the slot, -Y"),
        _b("exit_wall", (lay.bore_x1, lay.exit_x, -by, by, lay.gap, top),
           "exit wall above the window"),
        *_rear_ramp_colliders(lay),
    ]
    if lay.separator == "blade":
        out.append(_b("blade", (lay.blade_x0, lay.bore_x1, -by, by, lay.gap, lay.blade_top),
                      "molded separator blade; underside sets the gap"))
    else:
        out.extend(_wedge_colliders(lay))
    # Cheeks: straight part, then a lead-in wedge from the bore width down to the cheek line.
    half = by - 2.0
    x_in, x_end = lay.exit_x - 0.2, lay.shelf_x - 2.0
    x_lead = lay.exit_x + 6.0
    for sign, tag in ((1.0, "n"), (-1.0, "s")):
        def yb(a, b):
            return (a, b) if sign > 0 else (-b, -a)
        y0, y1 = yb(half, sy)
        out.append(_b(f"cheek_{tag}", (x_lead, x_end, y0, y1, 0.0, CHEEK_TOP),
                      f"presentation cheek, {tag}"))
        for i in range(LEAD_IN_STEPS):
            xa = x_in + (x_lead - x_in) * i / LEAD_IN_STEPS
            xb = x_in + (x_lead - x_in) * (i + 1) / LEAD_IN_STEPS
            xm = 0.5 * (xa + xb)
            line = by + (half - by) * (xm - x_in) / (x_lead - x_in)
            y0, y1 = yb(line, sy)
            out.append(_b(f"cheek_lead_{tag}{i}", (xa, xb, y0, y1, 0.0, CHEEK_TOP),
                          f"cheek lead-in wedge step {i}, {tag}"))
    # Rails: the 50 degree V as stacked boxes, each at the V height at its mid depth.
    t = math.tan(math.radians(RAIL_DEG))
    for sign, tag in ((1.0, "n"), (-1.0, "s")):
        for i in range(RAIL_STEPS):
            da = RAIL_D * i / RAIL_STEPS
            db = RAIL_D * (i + 1) / RAIL_STEPS
            z_low = RAIL_ZC - RAIL_HALF + 0.5 * (da + db) * t
            z_high = 2.0 * RAIL_ZC - z_low
            ya, yb_ = sy + da, sy + db
            y0, y1 = (ya, yb_) if sign > 0 else (-yb_, -ya)
            rail = _b(f"rail_{tag}{i}", (RAIL_X[0], RAIL_X[1], y0, y1, z_low, z_high),
                      f"V rail {tag}, step {i}; collision masked, the slide joint is the guide")
            out.append(replace(rail, contype=0, conaffinity=0))
    # Channel lips: the 50 degree underside as stacked boxes, each at the underside height at its
    # mid width, so the keel slot between the tips stays open.
    lt = math.tan(math.radians(LIP_DEG))
    for sign, tag in ((1.0, "n"), (-1.0, "s")):
        for i in range(LIP_STEPS):
            ya = LIP_SLOT_HALF_W + (ch - LIP_SLOT_HALF_W) * i / LIP_STEPS
            yb_ = LIP_SLOT_HALF_W + (ch - LIP_SLOT_HALF_W) * (i + 1) / LIP_STEPS
            z_low = -LIP_T - (0.5 * (ya + yb_) - LIP_SLOT_HALF_W) * lt
            y0, y1 = (ya, yb_) if sign > 0 else (-yb_, -ya)
            out.append(_b(f"lip_{tag}{i}", (lay.rear_x, lay.seat_x, y0, y1, z_low, 0.0),
                          f"spring channel lip {tag}, step {i}"))
    return tuple(out)


def _rear_ramp_face(lay: SyringeLayout):
    """Rear ramp's sloped face in (X, Z): toe-end point, wall-end point, outward unit normal."""
    x0, z0 = lay.ramp_toe_x, lay.ramp_land_top
    x1, z1 = lay.bore_x0, lay.ramp_top
    length = math.hypot(x0 - x1, z1 - z0)
    return (x0, z0), (x1, z1), ((z1 - z0) / length, (x0 - x1) / length)


def _rear_ramp_colliders(lay: SyringeLayout) -> list[ColliderSpec]:
    """Rear ramp: the toe land across the bore, the two blocks beside the slot down to the floor,
    a core box filling the ramp behind its face, and the sloped face as one box rotated about Y,
    so a packet end slides on a flat face."""
    by, slot = lay.bore_y, lay.slot_w / 2.0
    out = [
        _b("ramp_land", (lay.bore_x0, lay.ramp_toe_x, -by, by, lay.slot_h, lay.ramp_land_top),
           "rear ramp's toe land, over the slot; its underside continues the slot roof"),
        _b("ramp_side_n", (lay.bore_x0, lay.ramp_toe_x, slot, by, 0.0, lay.slot_h),
           "rear ramp beside the slot, +Y, down to the floor"),
        _b("ramp_side_s", (lay.bore_x0, lay.ramp_toe_x, -by, -slot, 0.0, lay.slot_h),
           "rear ramp beside the slot, -Y, down to the floor"),
    ]
    (x0, z0), (x1, z1), (nx, nz) = _rear_ramp_face(lay)
    # The core box's front top corner sits mid-face, half the face box's thickness behind the face,
    # so it fills the ramp's body behind the thin face box and never stands proud of the face.
    xc = 0.5 * (x0 + x1) - 0.5 * REAR_RAMP_T * nx
    zc = 0.5 * (z0 + z1) - 0.5 * REAR_RAMP_T * nz
    out.append(_b("ramp_core", (lay.bore_x0, xc, -by, by, lay.slot_h, zc),
                  "rear ramp's body behind its sloped face, over the slot"))
    length = math.hypot(x0 - x1, z1 - z0)
    # Rot(0, b, 0) takes local +X to (cos b, 0, -sin b): along the face, from the wall down to the toe.
    deg = math.degrees(math.atan2(z1 - z0, x0 - x1))
    cx = 0.5 * (x0 + x1) - 0.5 * REAR_RAMP_T * nx
    cz = 0.5 * (z0 + z1) - 0.5 * REAR_RAMP_T * nz
    out.append(ColliderSpec(
        collider_id="ramp_face", kind="box",
        size_mm=(length / 2.0, by, REAR_RAMP_T / 2.0), pos_mm=(cx, 0.0, cz),
        rot_deg=(0.0, deg, 0.0), friction=PETG_FRICTION, priority=PETG_PRIORITY,
        role="structure",
        source=_src(f"rear ramp face, {RAMP_DEG:g} deg from vertical (box rotated about Y)")))
    return out


def leg_colliders(lay: SyringeLayout, index: int) -> tuple[ColliderSpec, ...]:
    """Leg ``index`` (0..3), welded to the housing: column and foot pad as their outer boxes.

    The pad's underside, at the table, is a floor contact; the snap pin is inside the slab boxes.
    """
    x, y = lay.leg_xy[index]
    n = index + 1
    r, rf = HLEG_D / 2.0, FOOT_D / 2.0
    return (
        _b(f"leg_{n}_column", (x - r, x + r, y - r, y + r, TABLE_Z + FOOT_T, lay.shoulder_z),
           f"housing leg {n} column, up to the slab underside (0.05 mm stop gap)"),
        _b(f"leg_{n}_foot", (x - rf, x + rf, y - rf, y + rf, TABLE_Z, TABLE_Z + FOOT_T),
           f"housing leg {n} foot pad; its underside stands on the table"),
    )


def clip_colliders(lay: SyringeLayout, index: int) -> tuple[ColliderSpec, ...]:
    """Backstop clip ``index`` (0 +Y, 1 -Y), welded to the housing: its base and plate as boxes.

    The base box also fills the pry notch; its snap pin is inside the slab boxes.
    """
    tag = ("n", "s")[index]
    x0, x1 = CLIP_X

    def yb(a, b):
        return (a, b) if index == 0 else (-b, -a)

    return (
        _b(f"clip_{tag}_base", (x0, x1, *yb(lay.clip_base_in_y, lay.clip_in_y), lay.clip_z0,
                                lay.shoulder_z),
           f"backstop clip {tag} base under the slab (0.05 mm stop gap), pry notch filled"),
        _b(f"clip_{tag}_plate", (x0, x1, *yb(lay.clip_in_y, lay.clip_out_y), lay.clip_z0,
                                 lay.plate_z1),
           f"backstop clip {tag} plate outside the arm, {SLIDE_CLEAR:g} mm off its outer face; "
           f"its front face is the slider legs' home stop"),
    )


def _clip_face_points(lay: SyringeLayout, offset: float):
    """Points on both clips' plate inner faces over the arm's height, ``offset`` mm toward the arm."""
    x0, x1 = CLIP_X
    return tuple((x, s * (lay.clip_in_y - offset), z)
                 for s in (1.0, -1.0) for x in (x0 + 1.0, 0.5 * (x0 + x1), x1 - 1.0)
                 for z in (ARM_Z0 + 0.5, 0.5 * (ARM_Z0 + lay.plate_z1), lay.plate_z1 - 0.5))


def _clip_stop_points(lay: SyringeLayout, offset: float):
    """Points on both clips' front faces where the slider legs bear, ``offset`` mm toward the legs."""
    x1 = CLIP_X[1] + offset
    return tuple((x1, s * y, z) for s in (1.0, -1.0)
                 for y in (lay.clip_in_y + 0.3, 0.5 * (lay.clip_in_y + lay.clip_out_y), lay.clip_out_y - 0.3)
                 for z in (lay.clip_z0 + 0.5, ARM_Z0, lay.plate_z1 - 0.5))


def _lead_in_faces(lay: SyringeLayout, sign: float):
    """The ``sign`` wedge's two lead-in faces: (edge start, edge end, up-slope unit, outward normal).

    Each face rises from the inner face's top edge (z = ``wedge_foot_z``), perpendicular to that
    edge, at ``WEDGE_LEAD_IN_DEG``; over the ramp the edge follows the funnel line.
    """
    foot, a = lay.wedge_foot_z, math.radians(WEDGE_LEAD_IN_DEG)
    th = math.radians(lay.wedge_deg)
    faces = []
    for (x0, y0), (x1, y1), h in (
            ((lay.wedge_x0, lay.bore_y), (lay.bore_x1, lay.wedge_y), (math.sin(th), math.cos(th))),
            ((lay.bore_x1, lay.wedge_y), (lay.exit_x, lay.wedge_y), (0.0, 1.0))):
        hx, hy = h[0], sign * h[1]
        up = (math.cos(a) * hx, math.cos(a) * hy, math.sin(a))
        normal = (-math.sin(a) * hx, -math.sin(a) * hy, math.cos(a))
        faces.append(((x0, sign * y0, foot), (x1, sign * y1, foot), up, normal))
    return faces


def _wedge_colliders(lay: SyringeLayout) -> list[ColliderSpec]:
    """Side funnel wedges: the ramp face below the lead-in as a box rotated about Z, the straight
    face after it, and a rotated box under each lead-in face, its top face on that face."""
    by, wy, foot = lay.bore_y, lay.wedge_y, lay.wedge_foot_z
    run, drop = lay.bore_x1 - lay.wedge_x0, by - wy
    length = math.hypot(run, drop)
    deg = math.degrees(math.atan2(drop, run))
    # Outward unit normal of the +Y ramp face (into the wedge and the wall).
    nx, ny = drop / length, run / length
    slope = (lay.wedge_top - foot) / math.sin(math.radians(WEDGE_LEAD_IN_DEG))
    out = []
    for sign, tag in ((1.0, "n"), (-1.0, "s")):
        cx = 0.5 * (lay.wedge_x0 + lay.bore_x1) + 0.5 * WEDGE_RAMP_T * nx
        cy = sign * (0.5 * (by + wy) + 0.5 * WEDGE_RAMP_T * ny)
        out.append(ColliderSpec(
            collider_id=f"wedge_ramp_{tag}", kind="box",
            size_mm=(length / 2.0, WEDGE_RAMP_T / 2.0, foot / 2.0),
            pos_mm=(cx, cy, foot / 2.0), rot_deg=(0.0, 0.0, -sign * deg),
            friction=PETG_FRICTION, priority=PETG_PRIORITY, role="structure",
            source=_src(f"funnel wedge {tag}: ramp face up to the lead-in, "
                        f"{deg:.2f} deg to X (box rotated about Z)")))
        y0, y1 = (wy, by) if sign > 0 else (-by, -wy)
        out.append(_b(f"wedge_{tag}0", (lay.bore_x1, lay.exit_x, y0, y1, 0.0, foot),
                      f"funnel wedge {tag}: straight face after the ramp, up to the lead-in"))
        for (p0, p1, up, normal), part in zip(_lead_in_faces(lay, sign), ("ramp", "straight")):
            n_seg = WEDGE_LEAD_SEGMENTS if part == "ramp" else 1
            for j in range(n_seg):
                qa = tuple(p0[i] + (p1[i] - p0[i]) * j / n_seg for i in range(3))
                qb = tuple(p0[i] + (p1[i] - p0[i]) * (j + 1) / n_seg for i in range(3))
                out.append(_lead_in_box(lay, f"wedge_lead_{part}_{tag}" + (f"{j}" if n_seg > 1 else ""),
                                        qa, qb, up, normal, slope,
                                        f"funnel wedge {tag}: lead-in over the {part} part"
                                        + (f", segment {j}" if n_seg > 1 else "")))
    return out


def _lead_in_box(lay: SyringeLayout, cid: str, qa, qb, up, normal, slope: float, note: str):
    """Rotated box under one stretch ``qa``..``qb`` of a lead-in edge, its top face on the lead-in.

    Up the slope it reaches just past the bore wall at the stretch's narrower end (``qb``), and
    never so far that any corner leaves the side wall: the slider's arms run just outside it.
    """
    out_y = abs(up[1])  # |y| gained per mm up the slope
    reach = (lay.bore_y + WEDGE_LEAD_WALL_REACH - abs(qb[1])) / out_y
    reach = max(reach, 1e-3)
    far = abs(qa[1]) + reach * out_y + WEDGE_LEAD_T * abs(normal[1])
    if far > lay.side_y - WEDGE_LEAD_WALL_KEEP:
        raise ValueError(f"{cid} reaches |y| {far:.2f}, past the side wall's outer face "
                         f"({lay.side_y:g}) less {WEDGE_LEAD_WALL_KEEP} mm")
    if reach > slope + 0.5:
        raise ValueError(f"{cid} reaches {reach:.2f} mm up a {slope:.2f} mm lead-in")
    edge = math.dist(qa, qb)
    centre = tuple(0.5 * (qa[i] + qb[i]) + 0.5 * reach * up[i] - 0.5 * WEDGE_LEAD_T * normal[i]
                   for i in range(3))
    return ColliderSpec(
        collider_id=cid, kind="box",
        size_mm=(edge / 2.0, reach / 2.0, WEDGE_LEAD_T / 2.0), pos_mm=centre,
        rot_deg=_rot_deg(_cross(up, normal), up, normal),
        friction=PETG_FRICTION, priority=PETG_PRIORITY, role="structure",
        source=_src(f"{note}, {WEDGE_LEAD_IN_DEG:g} deg from horizontal (rotated box)"))


def _lead_in_points(lay: SyringeLayout, offset: float):
    """Points on both wedges' lead-in faces, moved ``offset`` mm along the face normal."""
    slope = (lay.wedge_top - lay.wedge_foot_z) / math.sin(math.radians(WEDGE_LEAD_IN_DEG))
    pts = []
    for sign in (1.0, -1.0):
        for p0, p1, up, normal in _lead_in_faces(lay, sign):
            for f in (0.35, 0.65, 0.95):
                for g in (0.15, 0.5, 0.85):
                    p = tuple(p0[i] + (p1[i] - p0[i]) * f + g * slope * up[i] for i in range(3))
                    # Only where the face is the CAD surface: inside the bore wall, under the top.
                    if abs(p[1]) < lay.bore_y - 0.3 and p[2] < lay.wedge_top - 0.2:
                        pts.append(tuple(p[i] + offset * normal[i] for i in range(3)))
    return tuple(pts)


def _pts(xs, ys, zs):
    return tuple((x, y, z) for x in xs for y in ys for z in zs)


def _keepout_points(lay: SyringeLayout, beyond_x: float):
    """Grid inside ``lay.keepout``, 0.25 mm in from its faces, starting at ``beyond_x`` in X."""
    x0, x1, y0, y1, z0, z1 = lay.keepout
    e = 0.25

    def span(a, b, n):
        return tuple(a + (b - a) * i / (n - 1) for i in range(n))

    return _pts(span(max(x0, beyond_x) + e, x1 - e, 8), span(y0 + e, y1 - e, 7),
                span(z0 + e, z1 - e, 8))


def _ramp_surface_points(lay: SyringeLayout) -> tuple[tuple[float, float, float], ...]:
    """Critical points on the rear ramp: its sloped face, toe land and the blocks beside the slot."""
    (x0, z0), (x1, z1), _ = _rear_ramp_face(lay)
    face = tuple((x0 + (x1 - x0) * f, y, z0 + (z1 - z0) * f)
                 for f in (0.25, 0.5, 0.75) for y in (-20.0, 0.0, 20.0))
    land_z = 0.5 * (lay.slot_h + lay.ramp_land_top)
    side_y = 0.5 * (lay.slot_w / 2.0 + lay.bore_y)
    return face + ((lay.ramp_toe_x, 0.0, land_z), (lay.ramp_toe_x, 25.0, land_z),
                   (lay.ramp_toe_x, side_y, 2.3), (lay.ramp_toe_x, -side_y, 2.3))


def _ramp_front_points(lay: SyringeLayout) -> tuple[tuple[float, float, float], ...]:
    """Points 0.2 mm off the rear ramp, in the bore: no collider may stand proud of it."""
    (x0, z0), (x1, z1), (nx, nz) = _rear_ramp_face(lay)
    off = 0.2
    face = tuple((x0 + (x1 - x0) * f + off * nx, y, z0 + (z1 - z0) * f + off * nz)
                 for f in (0.1, 0.5, 0.9) for y in (-27.0, 0.0, 27.0))
    land = _pts((lay.ramp_toe_x + off,), (-27.0, 0.0, 27.0),
                (0.1, lay.slot_h + 0.3, lay.ramp_land_top - 0.3))
    return face + land


def housing_fidelity(lay: SyringeLayout) -> FidelitySpec:
    by, ch = lay.bore_y, _channel_y()
    clips = clip_colliders(lay, 0) + clip_colliders(lay, 1)
    bore_xs = tuple(float(x) for x in range(-80, 81, 20))
    # Along the whole channel, from the rear face to just short of the spring seat.
    channel_xs = tuple(float(x) for x in range(math.ceil(lay.rear_x + 1.0),
                                               math.floor(lay.seat_x - 1.0) + 1, 15))
    probes = (
        ProbeSpec("bore", _pts(bore_xs, (-27.0, 0.0, 27.0), (0.1, 2.6, 5.1, 8.5, 30.0, 70.0)),
                  f"open tube bore, {lay.bore_x1 - lay.bore_x0:g} x {2.0 * by:g}, in front of the ramp"),
        ProbeSpec("exit_window", _pts((86.0, 87.0), (-27.0, 0.0, 27.0), (0.1, lay.gap / 2.0, lay.gap - 0.15)),
                  f"exit window below the exit wall, 0..{lay.gap:g}"),
        ProbeSpec("separator_gap",
                  _pts((70.0, 81.0, 83.0, 86.0, 87.5, 90.0, 100.0), (-27.0, 0.0, 27.0),
                       (lay.packet_h + 0.1, 0.5 * (lay.packet_h + lay.gap), lay.gap - 0.1)),
                  f"separator gap z {lay.packet_h:g}..{lay.gap:g} above the bottom packet path"),
        ProbeSpec("above_blade",
                  _pts((81.0, 83.0, 84.5), (-27.0, 0.0, 27.0), (lay.blade_top + 0.1, lay.blade_top + 0.35)),
                  f"bore above the blade top ({lay.blade_top:g}): the blade must not be taller"),
        ProbeSpec("rear_slot",
                  _pts((lay.rear_x + 0.5, lay.rear_x + 1.2, lay.bore_x0 - 0.5,
                        lay.bore_x0 + 0.5, lay.ramp_toe_x - 0.3),
                       (-19.0, 0.0, 19.0), (0.1, 2.3, lay.slot_h - 0.1)),
                  f"rear slot {lay.slot_w:g} x {lay.slot_h:g} the pusher stem passes through, "
                  f"on under the ramp"),
        ProbeSpec("outside_side_walls",
                  _pts(tuple(float(x) for x in range(math.ceil(lay.rear_x + 1.0),
                                                     math.floor(lay.exit_x - 1.0) + 1, 5)),
                       (-(lay.side_y + 0.15), lay.side_y + 0.15), (-12.0, -8.0, 2.5, lay.plate_z1 - 0.2)),
                  "0.15 mm outside the side walls, where the slider's arms run (clear of the "
                  "rails' z band): no housing collider may reach through a wall"),
        ProbeSpec("ramp_front", _ramp_front_points(lay),
                  "0.2 mm in front of the rear ramp's toe land and sloped face"),
        ProbeSpec("hand_keepout", _keepout_points(lay, beyond_x=lay.shelf_x),
                  "hand keep-out zone past the shelf end: no housing collider in it"),
        ProbeSpec("spring_channel",
                  _pts(channel_xs, (-ch + 0.2, ch - 0.2), (SPRING_Z0 + SPRING_H / 2.0,)),
                  "spring channel beside the spring, under the lips"),
        ProbeSpec("keel_slot",
                  _pts(channel_xs,
                       (-LIP_SLOT_HALF_W + 0.2, 0.0, LIP_SLOT_HALF_W - 0.2), (-LIP_T / 2.0,)),
                  "keel slot between the lip tips"),
        ProbeSpec("under_slab",
                  tuple(pt for pt in _pts((-60.0, -30.0, 0.0, 30.0, 60.0, 80.0),
                                          (-30.0, -15.0, 0.0, 15.0, 30.0),
                                          (lay.slab_z0 - 0.3, -20.0, -30.0, -40.0, TABLE_Z + 0.5))
                        if not any(contains(c, pt, margin_mm=VOID_TOL_MM) for c in clips)),
                  "the space under the slab between the legs is empty down to the table, "
                  "but for the two backstop clips"),
        ProbeSpec("clip_inner_face", _clip_face_points(lay, 0.2),
                  f"0.2 mm inside each backstop clip's plate (|y| {lay.clip_in_y:g}), toward the arm"),
        ProbeSpec("clip_stop_face", _clip_stop_points(lay, 0.2),
                  f"0.2 mm ahead of each backstop clip's front face (x {CLIP_X[1]:g}), toward the leg"),
    )
    transits = tuple(
        TransitSpec(f"packet_exit_y{int(y * 10)}_z{int(z * 10)}",
                    (lay.bore_x1 - 20.0, y, z), (lay.shelf_x + 5.0, y, z), 0.05)
        for z in (0.1, lay.packet_h / 2.0, lay.packet_h - 0.1) for y in (-27.5, 0.0, 27.5)
    ) + (
        TransitSpec("under_slab_x", (lay.rear_x - 5.0, 0.0, -30.0),
                    (lay.shelf_x + 5.0, 0.0, -30.0), 5.0),
    )
    # The four foot pad centres, on the table: the housing's floor contacts.
    feet = tuple((x, y, TABLE_Z) for x, y in lay.leg_xy)
    ramp = _ramp_surface_points(lay)
    clip_face = _clip_face_points(lay, 0.0) + _clip_stop_points(lay, 0.0)
    critical = (
        (0.0, 15.0, 0.0), (40.0, -20.0, 0.0), (95.0, 0.0, 0.0),
        (82.0, 0.0, lay.gap), (84.0, 20.0, lay.gap), (83.0, -20.0, lay.gap),
    ) + feet + ramp + clip_face
    if lay.separator == "wedge":
        probes, critical = _wedge_fidelity(lay, probes)
        critical += feet + ramp + clip_face
    return FidelitySpec(probes=probes, transits=transits, critical_surfaces_mm=critical,
                        max_surface_deviation_mm=CRITICAL_TOL_MM,
                        max_coverage_gap_mm=COVERAGE_GAP_MM)


def _wedge_fidelity(lay: SyringeLayout, probes):
    """Wedge separator: add the funnel and no-bite voids; critical surfaces on the exit wall and wedges."""
    foot = lay.wedge_foot_z
    xs = (lay.wedge_x0 + 1.0, 72.0, 76.0, 80.0, 82.5, 84.5, 86.0, 87.5)
    funnel = tuple((x, s * (lay.wedge_line_y(x) - 0.2), z)
                   for x in xs for s in (1.0, -1.0) for z in (0.1, foot / 2.0, foot + 0.3, 3.0))
    extra = (
        ProbeSpec("funnel", funnel, "0.2 mm inside the funnel line, below and above the lead-in foot"),
        ProbeSpec("lead_in", _lead_in_points(lay, 0.2),
                  f"0.2 mm off the wedges' {WEDGE_LEAD_IN_DEG:g} deg lead-in faces, in the bore"),
        ProbeSpec("no_bite",
                  _pts((70.0, 80.5, 83.0, lay.bore_x1 - 0.2), (-27.0, 0.0, 27.0),
                       (lay.gap + 0.05, lay.gap + 0.85, lay.gap + 1.75, lay.gap + 3.25)),
                  "nothing over the stack behind the exit wall's inner face"),
        ProbeSpec("over_wedges",
                  _pts((75.0, 80.0, 84.0, 86.5), (-29.5, 29.5),
                       (lay.wedge_top + 0.2, lay.packet_h - 0.05)),
                  f"under packet 2's underside ({lay.packet_h:g}) the wedges stop at {lay.wedge_top:g}"),
    )
    xr = 0.5 * (lay.wedge_x0 + lay.bore_x1)
    critical = (
        (0.0, 15.0, 0.0), (40.0, -20.0, 0.0), (95.0, 0.0, 0.0),
        (86.5, 0.0, lay.gap), (86.0, 20.0, lay.gap), (87.0, -20.0, lay.gap),
        (xr, lay.wedge_line_y(xr), foot / 2.0), (xr, -lay.wedge_line_y(xr), foot / 2.0),
        (86.5, lay.wedge_y, foot / 2.0), (86.5, -lay.wedge_y, foot / 2.0),
    ) + _lead_in_points(lay, 0.0)
    return probes + extra, critical


# --------------------------------------------------------------------------- slider
def slider_colliders(lay: SyringeLayout) -> tuple[ColliderSpec, ...]:
    """Slider at stroke 0: yoke, stem and plate, keel, two arms, two socketed legs."""
    yf = lay.yoke_rest_x
    arm_in = lay.side_y + SLIDE_CLEAR
    arm_out = arm_in + ARM_T
    x_back = yf - YOKE_T
    pw = lay.plate_w / 2.0
    xp = lay.plate_rest_x
    slider_top, plate_z0 = lay.plate_z1, lay.plate_z0
    out = [
        _b("yoke", (x_back, yf, -arm_out, arm_out, ARM_Z0, slider_top), "yoke behind the rear wall",
           role="mechanism"),
        _b("stem", (yf - 0.2, xp - PLATE_BOX_LEN, -pw, pw, plate_z0, slider_top),
           "pusher stem through the rear slot", role="mechanism"),
        _b("plate", (xp - PLATE_BOX_LEN, lay.keel_rest_x, -pw, pw, plate_z0, slider_top),
           "pusher plate up to its face under the undercut", role="mechanism"),
        *_plate_lip_colliders(lay),
        _b("keel", (yf - 0.2, lay.keel_rest_x, -KEEL_HALF_W, KEEL_HALF_W, SPRING_Z0,
                    plate_z0 + 0.2),
           "keel in the spring channel, the spring pad", role="mechanism"),
        _b("arm_n", (x_back, LEG_X0 + 1.0, arm_in, arm_out, ARM_Z0, slider_top),
           "arm +Y (rail groove filled; the joint is the guide)", role="mechanism"),
        _b("arm_s", (x_back, LEG_X0 + 1.0, -arm_out, -arm_in, ARM_Z0, slider_top),
           "arm -Y (rail groove filled; the joint is the guide)", role="mechanism"),
    ]
    for sign, tag in ((1.0, "n"), (-1.0, "s")):
        ya, yb_ = arm_in, arm_in + LEG_W
        y0, y1 = (ya, yb_) if sign > 0 else (-yb_, -ya)
        out.append(_b(f"leg_{tag}", (LEG_X0, LEG_X1, y0, y1, BAR_Z0, slider_top),
                      f"leg {tag}, full height; T-slide socket filled, the handle tail sits in it",
                      role="mechanism"))
    return tuple(out)


def _plate_undercut(lay: SyringeLayout):
    """The plate's undercut face in (X, Z): its foot, its top (the lip land's foot), outward unit normal."""
    b = math.radians(PLATE_UNDERCUT_DEG)
    top = (lay.plate_rest_x, lay.plate_z1 - PLATE_LIP_LAND)
    foot = (lay.keel_rest_x, top[1] - lay.plate_undercut_h)
    return foot, top, (math.cos(b), -math.sin(b))


def _plate_lip_colliders(lay: SyringeLayout) -> tuple[ColliderSpec, ...]:
    """The lip's land as a box, and under it the undercut as a box rotated about Y, its front face
    on the undercut face, ``PLATE_UNDERCUT x cos`` deep so it reaches the plate box behind; its
    back top corner stays inside the land box."""
    (xf, zf), (xt, zt), (nx, nz) = _plate_undercut(lay)
    depth = PLATE_UNDERCUT * nx
    span = math.hypot(xt - xf, zt - zf)
    pw = lay.plate_w / 2.0
    land = _b("plate_lip_land", (xf, xt, -pw, pw, zt, lay.plate_z1),
              "pusher plate's lip land; its front face and top edge are the push edge",
              role="mechanism")
    return land, ColliderSpec(
        collider_id="plate_undercut", kind="box",
        size_mm=(depth / 2.0, lay.plate_w / 2.0, span / 2.0),
        pos_mm=(0.5 * (xf + xt) - 0.5 * depth * nx, 0.0, 0.5 * (zf + zt) - 0.5 * depth * nz),
        rot_deg=(0.0, PLATE_UNDERCUT_DEG, 0.0), role="mechanism", friction=PETG_FRICTION,
        priority=PETG_PRIORITY,
        source=_src(f"pusher plate's undercut lip, {PLATE_UNDERCUT:g} mm at "
                    f"{PLATE_UNDERCUT_DEG:g} deg under the land (box rotated about Y)"))


def handle_colliders(lay: SyringeLayout) -> tuple[ColliderSpec, ...]:
    """Handle at stroke 0, welded to the slider: bar, two runners, two T-slide tails.

    The PULL deboss, detent leaf and ridge, and the edge radii and chamfers are ignored.
    """
    arm_in = lay.side_y + SLIDE_CLEAR
    half = arm_in + LEG_W
    run_x0 = LEG_X1 + JOINT_CLEAR
    xb, hx1 = _head_x()
    out = [
        _b("handle_bar", (lay.cross_rest_x, lay.cross_rest_x + BAR_D, -half, half, BAR_Z0, BAR_Z1),
           "pull bar, 15 mm over the table; PULL deboss ignored", role="mechanism"),
    ]
    for sign, tag in ((1.0, "n"), (-1.0, "s")):
        yc = _leg_yc(lay, sign)
        out.append(_b(f"handle_runner_{tag}",
                      (run_x0, lay.cross_rest_x + 1.0, yc - LEG_W / 2.0, yc + LEG_W / 2.0,
                       BAR_Z0, BAR_Z1),
                      f"handle runner {tag}, in front of the leg", role="mechanism"))
        out.append(_b(f"handle_tail_head_{tag}",
                      (xb, hx1, yc - HEAD_HW, yc + HEAD_HW, BAR_Z0, TAIL_TOP),
                      f"T-slide head {tag}, in the leg socket; detent leaf ignored",
                      role="mechanism"))
        out.append(_b(f"handle_tail_neck_{tag}",
                      (hx1 - 0.1, run_x0, yc - NECK_HW, yc + NECK_HW, BAR_Z0, TAIL_TOP),
                      f"T-slide neck {tag}, through the leg's front face", role="mechanism"))
    return tuple(out)


def _undercut_points(lay: SyringeLayout, offset: float):
    """Points on the plate face below the lip and on the undercut face, ``offset`` mm out of them."""
    (xf, zf), (xt, zt), (nx, nz) = _plate_undercut(lay)
    ys = (-15.0, 0.0, 15.0)
    low = tuple((xf + offset, y, z) for y in ys
                for z in (lay.plate_z0 + 0.3, 0.5 * (lay.plate_z0 + zf), zf - 0.3))
    lip = tuple((xf + (xt - xf) * f + offset * nx, y, zf + (zt - zf) * f + offset * nz)
                for y in ys for f in (0.15, 0.5, 0.85))
    land = tuple((xt + offset, y, z) for y in ys
                 for z in (zt + 0.3, lay.plate_z1 - 0.3))
    return low + lip + land


def slider_fidelity(lay: SyringeLayout) -> FidelitySpec:
    yf = lay.yoke_rest_x
    xp = lay.plate_rest_x
    arm_in = lay.side_y + SLIDE_CLEAR
    xs = tuple(float(x) for x in range(-130, 131, 20))
    # Under the keel, which reaches down to the spring's underside.
    z_open = SPRING_Z0 - 3.0
    probes = (
        ProbeSpec("housing_clearance",
                  _pts(xs, (-(lay.side_y + 0.15), lay.side_y + 0.15), (-10.0, 0.0, 3.0)),
                  f"0.35 mm slide clearance between arm and side wall (arm face at {arm_in:.2f})"),
        ProbeSpec("above_print_face",
                  _pts((yf + 5.0, yf + 20.0, xp - 10.0), (-15.0, 0.0, 15.0), (lay.plate_z1 + 0.2,)),
                  f"nothing above the z={lay.plate_z1:g} print face"),
        ProbeSpec("undercut", _undercut_points(lay, 0.2),
                  "0.2 mm in front of the plate face under the lip and of the undercut face"),
        ProbeSpec("frame_interior",
                  _pts((yf + 10.0, -60.0, 0.0, 60.0, LEG_X0 - 2.0), (-20.0, 0.0, 20.0),
                       (z_open, -30.0, -45.0)),
                  "open frame round the housing slab, below the keel, down to the table"),
        ProbeSpec("hand_keepout", _keepout_points(lay, beyond_x=lay.shelf_x),
                  "hand keep-out zone, slider home: no slider or handle collider in it"),
    )
    transits = (
        TransitSpec("housing_passage", (yf + 2.0, 0.0, z_open), (LEG_X0 - 2.0, 0.0, z_open), 2.0),
        TransitSpec("under_slab_passage", (yf + 2.0, 0.0, -40.0), (LEG_X0 - 2.0, 0.0, -40.0), 2.0),
    )
    critical = _undercut_points(lay, 0.0) + ((lay.cross_rest_x + BAR_D / 2.0, 0.0, BAR_Z1),)
    return FidelitySpec(probes=probes, transits=transits, critical_surfaces_mm=critical,
                        max_surface_deviation_mm=CRITICAL_TOL_MM,
                        max_coverage_gap_mm=COVERAGE_GAP_MM)
