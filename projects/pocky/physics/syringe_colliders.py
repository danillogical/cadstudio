"""Explicit box colliders and fidelity contracts for the syringe dispenser.

Every collider is a box in **body-local** millimetres, written feature by feature from
``geometry/syringe.py``; nothing is hulled. Both bodies use identity frames, so local
coordinates are the stroke-fraction-0 assembly coordinates.

The handle is a separate CAD part but is welded to the slider: one rigid body, with its own
part (mass from its CAD volume x PETG density) and its own colliders for the bar, the two runners
and the two T-slide tails. The tails fill the leg sockets (0.25 mm clearance, so the leg boxes are
solid there and the tails overlap them, which is harmless inside one body). The debossed PULL
text, the detent leaf slot and ridge, the 2 mm top-edge radii, the 1 mm bottom chamfers and the
plan-view corner radii are ignored: every collider is the outer box of its feature.

The housing is concave, so it is decomposed: floor slab (split around the spring channel), the two
channel lips as stacked boxes, side walls, the rear wall split around the 4.6 mm slot, the exit wall above the window, the blade,
the cheeks with their lead-in, and the two V rails as stacked boxes. With the wedge separator the blade is
gone and each side funnel wedge is one box rotated about Z for the ramp face below the chamfer, plus
stacked strips for the 45 degree chamfered top (each strip starts where the ramp reaches its inner edge,
so no strip stands proud of the ramp). The four legs are separate CAD parts welded to the housing
body, like the handle on the slider: each is a column box and a foot pad box, the outer boxes of
its cylinders, and the pads' undersides are the housing's only floor contacts. The snap pins sit in
the slab's sockets, inside the slab boxes, which are solid there. Nothing fills the space under
the slab between the legs. The slider's two arms are
solid boxes, so the rail grooves are filled. That is deliberate: the slide joint is the guide,
the arms touch nothing else, and the rail boxes are collision-masked (contype/conaffinity 0).
The mask is needed because MuJoCo filters parent/child contacts only while the parent is a
free body; with the housing clamped to the world the filter is off and the filled grooves would
jam on the rails. Pusher plate vs packet, packet vs housing and packet vs packet contacts are
real.

Friction conventions are those of ``colliders.py``: PETG 0.40 priority 0, packet 0.30 priority
1, analytic floor 0.50.

Every dimension comes from ``geometry/syringe.py`` (constants and ``SyringeLayout``), so the colliders
follow a CAD change; only the box decomposition below is written by hand.
"""
from __future__ import annotations

import math
from dataclasses import replace

from cadkit.physics.collision import FidelitySpec, ProbeSpec, TransitSpec
from cadkit.physics.schema import ColliderSpec

from projects.pocky.geometry.prototype import CHEEK_TOP, PROTOTYPE_SPRING
from projects.pocky.geometry.syringe import (
    ARM_T,
    ARM_Z0,
    BAR_D,
    BAR_Z0,
    BAR_Z1,
    CHANNEL_Z0,
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
    PLATE_Z0,
    RAIL_D,
    RAIL_DEG,
    RAIL_HALF,
    RAIL_X,
    RAIL_ZC,
    SLIDE_CLEAR,
    SLIDER_TOP,
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
#: Wedge separator: chamfered top approximated by this many strips per side.
WEDGE_STEPS = 4
#: Wedge ramp box thickness, outward from the ramp face into the wedge and side wall.
WEDGE_RAMP_T = 2.0


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


def _wedge_colliders(lay: SyringeLayout) -> list[ColliderSpec]:
    """Side funnel wedges: the ramp face as a box rotated about Z, the chamfered top as strips."""
    by, wy = lay.bore_y, lay.wedge_y
    face_top = lay.wedge_chamfer_z(wy)  # the chamfer's foot on the inner face (2.6)
    run, drop = lay.bore_x1 - lay.wedge_x0, by - wy
    length = math.hypot(run, drop)
    deg = math.degrees(math.atan2(drop, run))
    # Outward unit normal of the +Y ramp face (into the wedge and the wall).
    nx, ny = drop / length, run / length
    out = []
    for sign, tag in ((1.0, "n"), (-1.0, "s")):
        cx = 0.5 * (lay.wedge_x0 + lay.bore_x1) + 0.5 * WEDGE_RAMP_T * nx
        cy = sign * (0.5 * (by + wy) + 0.5 * WEDGE_RAMP_T * ny)
        out.append(ColliderSpec(
            collider_id=f"wedge_ramp_{tag}", kind="box",
            size_mm=(length / 2.0, WEDGE_RAMP_T / 2.0, face_top / 2.0),
            pos_mm=(cx, cy, face_top / 2.0), rot_deg=(0.0, 0.0, -sign * deg),
            friction=PETG_FRICTION, priority=PETG_PRIORITY, role="structure",
            source=_src(f"funnel wedge {tag}: ramp face up to the chamfer foot, "
                        f"{deg:.2f} deg to X (box rotated about Z)")))
        for i in range(WEDGE_STEPS):
            ya = wy + drop * i / WEDGE_STEPS
            yb_ = wy + drop * (i + 1) / WEDGE_STEPS
            z1 = lay.wedge_chamfer_z(0.5 * (ya + yb_))
            y0, y1 = (ya, yb_) if sign > 0 else (-yb_, -ya)
            out.append(_b(f"wedge_{tag}{i}", (lay.wedge_line_x(ya), lay.exit_x, y0, y1, 0.0, z1),
                          f"funnel wedge {tag}, chamfer strip {i}"))
    return out


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


def housing_fidelity(lay: SyringeLayout) -> FidelitySpec:
    by, ch = lay.bore_y, _channel_y()
    bore_xs = tuple(float(x) for x in range(-80, 81, 20))
    probes = (
        ProbeSpec("bore", _pts(bore_xs, (-27.0, 0.0, 27.0), (0.1, 2.6, 5.1, 8.5, 30.0, 70.0)),
                  "open tube bore, 170 x 60"),
        ProbeSpec("exit_window", _pts((86.0, 87.0), (-27.0, 0.0, 27.0), (0.1, 2.6, 5.6)),
                  "exit window below the exit wall, 0..5.75"),
        ProbeSpec("separator_gap",
                  _pts((70.0, 81.0, 83.0, 86.0, 87.5, 90.0, 100.0), (-27.0, 0.0, 27.0),
                       (5.3, 5.5, 5.65)),
                  "separator gap z 5.2..5.75 above the bottom packet path"),
        ProbeSpec("above_blade", _pts((81.0, 83.0, 84.5), (-27.0, 0.0, 27.0), (8.25, 8.5)),
                  "bore above the blade top (8.15): the blade must not be taller"),
        ProbeSpec("rear_slot",
                  _pts((lay.rear_x + 0.5, lay.rear_x + 1.2, lay.bore_x0 - 0.5),
                       (-19.0, 0.0, 19.0), (0.1, 2.3, 4.5)),
                  "rear slot 40.7 x 4.6 the pusher stem passes through"),
        ProbeSpec("hand_keepout", _keepout_points(lay, beyond_x=lay.shelf_x),
                  "hand keep-out zone past the shelf end: no housing collider in it"),
        ProbeSpec("spring_channel",
                  _pts(tuple(float(x) for x in range(-80, 11, 15)), (-ch + 0.2, ch - 0.2),
                       (SPRING_Z0 + PROTOTYPE_SPRING.height / 2.0,)),
                  "spring channel beside the spring, under the lips"),
        ProbeSpec("keel_slot",
                  _pts(tuple(float(x) for x in range(-80, 11, 15)),
                       (-LIP_SLOT_HALF_W + 0.2, 0.0, LIP_SLOT_HALF_W - 0.2), (-LIP_T / 2.0,)),
                  "keel slot between the lip tips"),
        ProbeSpec("under_slab",
                  _pts((-60.0, -30.0, 0.0, 30.0, 60.0, 80.0), (-30.0, -15.0, 0.0, 15.0, 30.0),
                       (lay.slab_z0 - 0.3, -20.0, -30.0, -40.0, TABLE_Z + 0.5)),
                  "the space under the slab between the legs is empty down to the table"),
    )
    transits = tuple(
        TransitSpec(f"packet_exit_y{int(y * 10)}_z{int(z * 10)}",
                    (lay.bore_x1 - 20.0, y, z), (lay.shelf_x + 5.0, y, z), 0.05)
        for z in (0.1, 2.6, 5.1) for y in (-27.5, 0.0, 27.5)
    ) + (
        TransitSpec("under_slab_x", (lay.rear_x - 5.0, 0.0, -30.0),
                    (lay.shelf_x + 5.0, 0.0, -30.0), 5.0),
    )
    # The four foot pad centres, on the table: the housing's floor contacts.
    feet = tuple((x, y, TABLE_Z) for x, y in lay.leg_xy)
    critical = (
        (0.0, 15.0, 0.0), (40.0, -20.0, 0.0), (95.0, 0.0, 0.0),
        (82.0, 0.0, lay.gap), (84.0, 20.0, lay.gap), (83.0, -20.0, lay.gap),
    ) + feet
    if lay.separator == "wedge":
        probes, critical = _wedge_fidelity(lay, probes)
        critical += feet
    return FidelitySpec(probes=probes, transits=transits, critical_surfaces_mm=critical,
                        max_surface_deviation_mm=CRITICAL_TOL_MM,
                        max_coverage_gap_mm=COVERAGE_GAP_MM)


def _wedge_fidelity(lay: SyringeLayout, probes):
    """Wedge separator: add the funnel and no-bite voids; critical surfaces on the exit wall and wedges."""
    face_top = lay.wedge_chamfer_z(lay.wedge_y)
    xs = (lay.wedge_x0 + 1.0, 72.0, 76.0, 80.0, 82.5, 84.5, 86.0, 87.5)
    funnel = tuple((x, s * (lay.wedge_line_y(x) - 0.2), z)
                   for x in xs for s in (1.0, -1.0) for z in (0.1, 1.3, face_top - 0.2))
    extra = (
        ProbeSpec("funnel", funnel, "0.2 mm inside the funnel line, below the chamfer foot"),
        ProbeSpec("no_bite",
                  _pts((70.0, 80.5, 83.0, lay.bore_x1 - 0.2), (-27.0, 0.0, 27.0),
                       (lay.gap + 0.05, 6.6, 7.5, 9.0)),
                  "nothing over the stack behind the exit wall's inner face"),
        ProbeSpec("over_wedges",
                  _pts((75.0, 80.0, 84.0, 86.5), (-29.5, 29.5), (lay.wedge_top + 0.2, 5.15)),
                  "under packet 2's underside (5.2) the wedges stop at 4.8"),
    )
    xr = 0.5 * (lay.wedge_x0 + lay.bore_x1)
    critical = (
        (0.0, 15.0, 0.0), (40.0, -20.0, 0.0), (95.0, 0.0, 0.0),
        (86.5, 0.0, lay.gap), (86.0, 20.0, lay.gap), (87.0, -20.0, lay.gap),
        (xr, lay.wedge_line_y(xr), 1.3), (xr, -lay.wedge_line_y(xr), 1.3),
        (86.5, lay.wedge_y, 1.3), (86.5, -lay.wedge_y, 1.3),
    )
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
    out = [
        _b("yoke", (x_back, yf, -arm_out, arm_out, ARM_Z0, SLIDER_TOP), "yoke behind the rear wall",
           role="mechanism"),
        _b("stem", (yf - 0.2, xp - PLATE_BOX_LEN, -pw, pw, PLATE_Z0, SLIDER_TOP),
           "pusher stem through the rear slot", role="mechanism"),
        _b("plate", (xp - PLATE_BOX_LEN, xp, -pw, pw, PLATE_Z0, SLIDER_TOP),
           "pusher plate; its front face is the push face", role="mechanism"),
        _b("keel", (yf - 0.2, xp, -KEEL_HALF_W, KEEL_HALF_W, SPRING_Z0, 0.5),
           "keel in the spring channel, the spring pad", role="mechanism"),
        _b("arm_n", (x_back, LEG_X0 + 1.0, arm_in, arm_out, ARM_Z0, SLIDER_TOP),
           "arm +Y (rail groove filled; the joint is the guide)", role="mechanism"),
        _b("arm_s", (x_back, LEG_X0 + 1.0, -arm_out, -arm_in, ARM_Z0, SLIDER_TOP),
           "arm -Y (rail groove filled; the joint is the guide)", role="mechanism"),
    ]
    for sign, tag in ((1.0, "n"), (-1.0, "s")):
        ya, yb_ = arm_in, arm_in + LEG_W
        y0, y1 = (ya, yb_) if sign > 0 else (-yb_, -ya)
        out.append(_b(f"leg_{tag}", (LEG_X0, LEG_X1, y0, y1, BAR_Z0, SLIDER_TOP),
                      f"leg {tag}, full height; T-slide socket filled, the handle tail sits in it",
                      role="mechanism"))
    return tuple(out)


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
                  _pts((yf + 5.0, yf + 20.0, xp - 10.0), (-15.0, 0.0, 15.0), (4.5,)),
                  "nothing above the z=4.3 print face"),
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
    critical = ((xp, 0.0, 2.3), (xp, 15.0, 1.0), (xp, -15.0, 3.5),
                (lay.cross_rest_x + BAR_D / 2.0, 0.0, BAR_Z1))
    return FidelitySpec(probes=probes, transits=transits, critical_surfaces_mm=critical,
                        max_surface_deviation_mm=CRITICAL_TOL_MM,
                        max_coverage_gap_mm=COVERAGE_GAP_MM)
