"""Printed 10-packet prototype. Kinematics come from ``linkage.py`` unchanged.

Steel dowels, the Ø4.1 holes and the 4.30 mm slots stay in the M1 model.
This module is the PETG parts: wider sliding slots, printed pegs, the
variant-B serpentine, and the body / chassis / lip.

The head on each peg is 2.4 mm thick. The plan's 2.0 mm head fails
``min_wall`` (the 1st percentile would sit on that face, under 95% of
2.4 mm), and the plan forbids a ``min_wall`` override on anything except
the spring beams and, by the wall rule, the shims.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from build123d import Cylinder, Pos, Rot

from projects.pocky.geometry.linkage import (
    ARM_W,
    BUTTON_Y,
    CARRIAGE_T,
    CRANK_T,
    CUT_EPS,
    EXIT_WALL,
    FACE_W,
    FLANGE_T,
    FORWARD_LUG_Z,
    HEAD_GAP,
    HEAD_LEN,
    HEAD_SIDE_GAP,
    HEAD_TOP,
    HOME_BLOCK_Z,
    HUB_OD,
    LUG_T,
    LUG_Y,
    ROD_T,
    ROD_W,
    SHOULDER_X,
    STOP_EPS,
    Z_GAP,
    Linkage,
    Pose,
    button_slot_radii,
    floor_slot_bounds,
    forward_stop_solid,
    home_stop_solid,
    linkage_from,
    on_bed,
    phi_for_button_fraction,
    pose_at_phi,
    pusher_slot_ends,
    pusher_solid,
    _box,
    _cyl,
    _stadium,
)
from projects.pocky.models.packet_dummy import build as dummy_build
from projects.pocky.params import Params

# Printed joints. Sliding slots are wider than the M1 steel slots.
# Grip holes stay at the peg diameter.
PROTO_SLOT_W = 4.6
PIVOT_BORE = 5.4
PEG_D = 4.0
PIVOT_PEG_D = 5.0
GRIP = 4.0
HEAD_T = 2.4
HEAD_EXTRA = 3.0  # head diameter = shaft diameter + 3 mm
TIP_CHAMFER = 0.5
END_ALLOW = 0.2

# Variant B is the only spring in this print. A and C are seat-offset contingencies.
PRELOAD = 3.0
SPRING_BEAMS = 12
SPRING_PAD = 3.0
SPRING_GAP = 3.0
SPRING_HEIGHT = 5.0
SPRING_AMPLITUDE = 14.0
# Centre of the spring, on the −Y side of the rod. The near edge is about
# 4.5 mm outside the crank's 54.5 mm swept disc.
SPRING_Y = -74.0
SPRING_Z0 = -16.6
# Rod-pad contact face at button travel 0. The seat is ``installed`` mm toward −X.
ROD_PAD_X = 20.0
ROD_PAD_T = 4.0
INSERT_T = 4.0
POCKET_RECESS = 4.8  # empty behind the B insert, for a C insert
WALL_CLEAR = 0.5  # per side, folds to a pocket wall
GUIDE_CLEAR = 0.3  # per side, rod shaft to a guide
LIP_LEN = 18.0
LEDGE_Z = 5.35
MAX_GAP = 6.55
DEFAULT_GAP = 5.75  # one 0.4 mm shim
SHIM_THIN = 0.4
SHIM_THICK = 0.8
EDGE_R = 0.8
BLADE_T = 2.4  # separator plate; the R0.8 edge is a corner round on this plate
CHEEK_TOP = 4.8  # below the 5.35 mm ledge, so a cheek cannot close the gap
# The tallest shim lifts a 2.4 mm blade to 8.95. The front wall starts above that.
FRONT_WALL_Z = MAX_GAP + BLADE_T + 0.25  # 9.20
# Chassis bed. The spring pocket floor ends 0.2 mm under the spring, and the
# plate below that face is 2.4 mm, so the bed sits 1.2 mm under the M1 z=−18.
CHASSIS_Z0 = -19.2
# Button head. Full width (up to y=−28) only below the shelf. Above that line
# the head stops at HEAD_UPPER_Y, 0.8 mm outside the −Y lip bar, so the ledge,
# the shim, and the shelf stay clear of the thumb pad for the whole stroke.
HEAD_SPLIT_Z = -2.6
HEAD_UPPER_Y = -36.8
BAR_Z0 = 11.0
BAR_Z1 = 16.0
HOOK_Z0 = 12.3  # above the head top (12), so a rail here misses the button
HOOK_Z1 = 14.7
BLADE_BITE = 2.0  # separator reaches this far back over the packet's front edge
BULLNOSE_Z = 4.4  # face height 4.2, plus a little, for the back-wall notch
TUBE_OUTER_Y_EXTRA = 0.0

PART_ROLES = (
    "body",
    "chassis",
    "lip",
    "shim",
    "spring_seat",
    "crank",
    "pusher",
    "rod",
    "spring",
    "peg",
    "dummy",
)


@dataclass(frozen=True)
class SpringSpec:
    """One serpentine. Only B is turned into a solid for this print."""

    letter: str
    thickness: float

    @property
    def beams(self) -> int:
        return SPRING_BEAMS

    @property
    def gap(self) -> float:
        return SPRING_GAP

    @property
    def pad(self) -> float:
        return SPRING_PAD

    @property
    def height(self) -> float:
        return SPRING_HEIGHT

    @property
    def amplitude(self) -> float:
        return SPRING_AMPLITUDE

    @property
    def pitch(self) -> float:
        return self.thickness + self.gap

    @property
    def solid_length(self) -> float:
        """Beams and pads stacked, gaps closed."""
        return self.beams * self.thickness + 2 * self.pad

    @property
    def free_length(self) -> float:
        """12 beams, 11 gaps, two pads."""
        return self.solid_length + (self.beams - 1) * self.gap

    def installed(self, preload: float = PRELOAD) -> float:
        return self.free_length - preload

    def full_press(self, button_stroke: float, preload: float = PRELOAD) -> float:
        return self.installed(preload) - button_stroke


VARIANTS = {
    "A": SpringSpec("A", 1.0),
    "B": SpringSpec("B", 1.2),
    "C": SpringSpec("C", 1.6),
}
PROTOTYPE_SPRING = VARIANTS["B"]


def seat_face_offset(letter: str) -> float:
    """How far that variant's seat face sits from B's, +X toward the rod."""
    return PROTOTYPE_SPRING.installed() - VARIANTS[letter].installed()


def compressed_length(travel: float) -> float:
    """Variant B at this button travel. Rest is the installed length."""
    return PROTOTYPE_SPRING.installed() - travel


def gap_for_shims(thickness: float) -> float:
    """Ledge at 5.35 mm plus the shim stack."""
    return LEDGE_Z + thickness


def _fuse(shapes):
    acc = shapes[0]
    for shape in shapes[1:]:
        acc = acc + shape
    return acc.solid()


def _cut(shape, cutters):
    acc = shape
    for cutter in cutters:
        acc = acc - cutter
    return acc.solid()


def _peg(x: float, y: float, z_tip: float, z_head0: float, z_head1: float, radius: float):
    """Shaft from the tip to the head, head included, 0.5 mm chamfer on the tip only.

    The chamfer is cut on the tip edge. A fused cone leaves an internal face
    that the wall check reads as a paper-thin cap.
    """
    head_r = radius + HEAD_EXTRA / 2.0
    z_lo = min(z_tip, z_head0)
    z_hi = max(z_tip, z_head1)
    shaft = _cyl(x, y, z_lo, z_hi, radius)
    head = _cyl(x, y, z_head0, z_head1, head_r)
    body = _fuse([shaft, head])
    tip_edges = [
        edge for edge in body.edges()
        if abs(edge.center().Z - z_tip) < 1e-4 and abs(edge.radius - radius) < 0.05
    ]
    if len(tip_edges) != 1:
        raise ValueError(f"expected one tip edge, found {len(tip_edges)}")
    return body.chamfer(TIP_CHAMFER, None, tip_edges)


def _half_ring(cx: float, cy: float, z0: float, z1: float, ri: float, ro: float, positive_y: bool):
    ring = _cyl(cx, cy, z0, z1, ro) - _cyl(cx, cy, z0 - 0.4, z1 + 0.4, ri)
    extra = ro + 1.0
    if positive_y:
        cutter = _box(cx - extra, cx + extra, cy - extra, cy, z0 - 1.0, z1 + 1.0)
    else:
        cutter = _box(cx - extra, cx + extra, cy, cy + extra, z0 - 1.0, z1 + 1.0)
    return (ring - cutter).solid()


def spring_solid(spec: SpringSpec, length: float, x0: float, y_center: float, z0: float):
    """Serpentine of ``length`` mm along X, seat end at ``x0``.

    Folds are semicircles that span the gap, so the inner radius is half the
    gap. For variant B that is 1.5 mm, above the 1.2 mm minimum. The outside
    across the folds is the amplitude (14 mm). Pads do not fold.
    """
    if length <= spec.solid_length + 1e-6:
        raise ValueError(f"spring length {length} is at or under the solid length")
    gaps = spec.beams - 1
    gap = (length - spec.solid_length) / gaps
    pitch = spec.thickness + gap
    t = spec.thickness
    rc = pitch / 2.0
    ri = rc - t / 2.0
    ro = rc + t / 2.0
    if ri <= 0.2:
        raise ValueError(f"fold inner radius {ri} is too small to cut")
    y_out = spec.amplitude / 2.0
    fold_y = y_out - ro
    z1 = z0 + spec.height
    shapes = []
    # Pads. Local X starts at the seat face.
    shapes.append(_box(x0, x0 + spec.pad + 0.2, y_center - y_out, y_center + y_out, z0, z1))
    rod_pad_x = x0 + length - spec.pad
    shapes.append(_box(rod_pad_x - 0.2, x0 + length, y_center - y_out, y_center + y_out, z0, z1))
    first_beam_x = x0 + spec.pad
    for i in range(spec.beams):
        bx = first_beam_x + i * pitch
        y0 = -y_out
        y1 = y_out
        # Fold i (between beam i and i+1) is on +Y when i is even.
        has_pos = (i % 2 == 0 and i < gaps) or (i % 2 == 1 and i > 0)
        has_neg = (i % 2 == 1 and i < gaps) or (i % 2 == 0 and i > 0)
        if has_pos:
            y1 = fold_y + 0.2
        if has_neg:
            y0 = -fold_y - 0.2
        shapes.append(_box(bx, bx + t, y_center + y0, y_center + y1, z0, z1))
    for i in range(gaps):
        cx = x0 + spec.pad + t / 2.0 + i * pitch + rc
        positive = i % 2 == 0
        cy = y_center + (fold_y if positive else -fold_y)
        shapes.append(_half_ring(cx, cy, z0, z1, ri, ro, positive))
    return _fuse(shapes)


def _crank(link: Linkage, phi: float):
    """M1 crank with a Ø5.4 bore, a 4.6 mm button slot, and a Ø4 grip for the pusher peg."""
    z0, z1 = link.crank_z0, link.crank_z1
    inner, outer = button_slot_radii(link)
    reach_button = outer + PROTO_SLOT_W / 2.0 + link.min_wall
    reach_pusher = link.radius + PEG_D / 2.0 + link.min_wall
    bar = _box(-reach_button, reach_pusher, -ARM_W / 2.0, ARM_W / 2.0, z0, z1)
    hub = _cyl(0.0, 0.0, z0, z1, HUB_OD / 2.0)
    cz0, cz1 = z0 - CUT_EPS, z1 + CUT_EPS
    bore = _cyl(0.0, 0.0, cz0, cz1, PIVOT_BORE / 2.0)
    slot = _stadium(-outer, 0.0, -inner, 0.0, PROTO_SLOT_W, cz0, cz1)
    hole = _cyl(link.radius, 0.0, cz0, cz1, PEG_D / 2.0)
    local = (bar + hub) - bore - slot - hole
    world = Pos(link.pivot_x, link.pivot_y, 0.0) * Rot(0.0, 0.0, math.degrees(phi)) * local
    return world.solid()


def _rod_features(link: Linkage):
    """Rest-pose X stations of the rod, before the travel shift."""
    rest = pose_at_phi(link, link.phi0)
    pin_x = rest.button_x
    x_start = pin_x - (PEG_D / 2.0 + link.min_wall)
    head_inner = link.outer_x + HEAD_GAP + link.button_stroke
    head_outer = head_inner + HEAD_LEN
    flange_x1 = link.home_x - STOP_EPS
    shoulder_x0 = SHOULDER_X + STOP_EPS
    return {
        "pin_x": pin_x,
        "x_start": x_start,
        "head_inner": head_inner,
        "head_outer": head_outer,
        "flange": (flange_x1 - FLANGE_T, flange_x1),
        "shoulder": (shoulder_x0, shoulder_x0 + FLANGE_T),
        "pad": (ROD_PAD_X, ROD_PAD_X + ROD_PAD_T),
    }


def _swept(span: tuple[float, float], stroke: float) -> tuple[float, float]:
    """X range of a rod feature as the button goes from rest to full stroke."""
    return span[0] - stroke, span[1]


def _spring_web(link: Linkage) -> tuple[float, float, float]:
    """Rest-pose X of the pad's north web, and the Y the pad stays south of.

    The forward lug sits on the pad's travel. The web is 0.4 mm clear of the
    lug's −X face, so the whole stroke stays on that side of the lug. The pad
    itself stays south of the lug.
    """
    lug_x0 = SHOULDER_X - link.button_stroke - STOP_EPS - LUG_T
    web_x1 = lug_x0 - 0.4
    web_x0 = web_x1 - 4.0
    south_y = LUG_Y[0] - 0.4
    return web_x0, web_x1, south_y


def _rod(link: Linkage, pose: Pose):
    feat = _rod_features(link)
    y0 = BUTTON_Y - ROD_W / 2.0
    y1 = BUTTON_Y + ROD_W / 2.0
    z0, z1 = link.rod_z0, link.rod_z1
    shaft = _box(feat["x_start"], feat["head_outer"], y0, y1, z0, z1)
    head_y1 = min(-link.packet_width / 2.0 - HEAD_SIDE_GAP, BUTTON_Y)
    # Lower head joins the shaft. Upper head is the thumb pad and stops south
    # of the exit ledge (see HEAD_UPPER_Y).
    head_lower = _box(feat["head_inner"], feat["head_outer"], LUG_Y[0], head_y1, z0, HEAD_SPLIT_Z)
    head_upper = _box(
        feat["head_inner"], feat["head_outer"], LUG_Y[0], HEAD_UPPER_Y,
        HEAD_SPLIT_Z - 0.2, HEAD_TOP,
    )
    fx0, fx1 = feat["flange"]
    flange = _box(fx0, fx1, LUG_Y[0], y0, HOME_BLOCK_Z[0], z1)
    sx0, sx1 = feat["shoulder"]
    shoulder = _box(sx0, sx1, LUG_Y[0], y0, z0, FORWARD_LUG_Z[1])
    web_x0, web_x1, south_y = _spring_web(link)
    # The pad face covers the spring. It stays south of the forward lug. A web
    # on the lug's −X side joins the pad to the shaft.
    pad = _box(ROD_PAD_X, ROD_PAD_X + ROD_PAD_T, SPRING_Y - SPRING_AMPLITUDE / 2.0, south_y,
               SPRING_Z0, z1)
    beam = _box(web_x0, ROD_PAD_X + ROD_PAD_T, south_y - 3.4, south_y, SPRING_Z0, z1)
    web = _box(web_x0, web_x1, south_y - 0.2, y0 + 0.2, z0, z1)
    hole = _cyl(feat["pin_x"], BUTTON_Y, z0 - CUT_EPS, z1 + CUT_EPS, PEG_D / 2.0)
    rod = _cut(_fuse([shaft, head_lower, head_upper, flange, shoulder, pad, beam, web]), [hole])
    return (Pos(-pose.button_travel, 0.0, 0.0) * rod).solid()


def _pusher(link: Linkage, pose: Pose):
    """M1 pusher with the carriage slot opened to 4.6 mm."""
    base = pusher_solid(link, pose)
    y0, y1 = pusher_slot_ends(link)
    wider = _stadium(
        pose.pusher_pin_x, y0, pose.pusher_pin_x, y1, PROTO_SLOT_W,
        link.carriage_z0 - CUT_EPS, link.carriage_z1 + CUT_EPS,
    )
    return (base - wider).solid()


def _pivot_peg(link: Linkage):
    """Head under the boss, tip 0.2 mm above the crank."""
    boss_bot = link.crank_z0 - Z_GAP - GRIP
    z_tip = link.crank_z1 + END_ALLOW
    z_head1 = boss_bot - STOP_EPS
    z_head0 = z_head1 - HEAD_T
    return _peg(link.pivot_x, link.pivot_y, z_tip, z_head0, z_head1, PIVOT_PEG_D / 2.0)


def _pusher_peg(link: Linkage, pose: Pose):
    """Grip in the crank, head above the carriage."""
    z_tip = link.crank_z0
    z_head0 = link.carriage_z1 + END_ALLOW
    z_head1 = z_head0 + HEAD_T
    return _peg(pose.pusher_pin_x, pose.pusher_pin_y, z_tip, z_head0, z_head1, PEG_D / 2.0)


def _button_peg(link: Linkage, pose: Pose):
    """Grip in the rod, head above the crank."""
    z_tip = link.rod_z0
    z_head0 = link.crank_z1 + END_ALLOW
    z_head1 = z_head0 + HEAD_T
    return _peg(pose.button_x, pose.button_y, z_tip, z_head0, z_head1, PEG_D / 2.0)


def _tube(p: Params, link: Linkage):
    """Bore, outer faces, and the floor plate limits."""
    hx = p.magazine.length_i / 2.0
    hy = p.magazine.width_i / 2.0
    wall = link.min_wall
    sx0, _, _, _ = floor_slot_bounds(link)
    return {
        "x0": -hx,
        "x1": hx,
        "y0": -hy,
        "y1": hy,
        "ox0": -hx - wall,
        "ox1": hx + EXIT_WALL,
        "oy": hy + wall,
        "floor_x0": min(-hx - wall, sx0) - wall,
        "top": p.stack_nominal_height + p.magazine.headroom,
        "wall": wall,
    }


def _body(p: Params, link: Linkage):
    t = _tube(p, link)
    wall = t["wall"]
    top = t["top"]
    floor = _box(t["floor_x0"], t["ox1"], -t["oy"], t["oy"], link.floor_z0, link.floor_z1)
    sx0, sx1, sy0, sy1 = floor_slot_bounds(link)
    floor = _cut(floor, [_box(sx0, sx1, sy0, sy1, link.floor_z0 - CUT_EPS, link.floor_z1)])
    # Back wall bridges the floor slot. The middle bay starts at z=0 so it does not fill the slot.
    back_side = []
    for y0, y1 in ((-t["oy"], sy0), (sy1, t["oy"])):
        back_side.append(_box(t["ox0"], t["x0"], y0, y1, link.floor_z1 - 0.2, top))
    back_mid = _box(t["ox0"], t["x0"], sy0 - 0.2, sy1 + 0.2, link.floor_z1, top)
    sides = [
        _box(t["ox0"], t["ox1"], t["y1"], t["oy"], link.floor_z1 - 0.2, top),
        _box(t["ox0"], t["ox1"], -t["oy"], t["y0"], link.floor_z1 - 0.2, top),
    ]
    front = _box(t["x1"], t["ox1"], t["y0"] - 0.2, t["y1"] + 0.2, FRONT_WALL_Z, top)
    # Shim ledges on the exit, outside the bore. Top face is the 5.35 mm ledge.
    ledge_y = 6.0
    ledges = []
    for sign in (1.0, -1.0):
        y_in = sign * t["y1"]
        y_out = sign * (t["y1"] + ledge_y)
        lo, hi = (y_in, y_out) if y_out > y_in else (y_out, y_in)
        ledges.append(_box(t["ox1"] - 1.0, t["ox1"] + 8.0, lo - 0.2 * sign, hi, LEDGE_Z - wall, LEDGE_Z))
    # Chassis-hook ribs, outside the crank disc (x well in front of the pivot).
    rib_z0 = link.floor_z0
    ribs = [
        _box(60.0, 74.0, t["oy"] - 0.2, t["oy"] + 2.6, rib_z0, link.floor_z1),
        _box(-40.0, -26.0, -t["oy"] - 2.6, -t["oy"] + 0.2, rib_z0, link.floor_z1),
    ]
    # Lip-hook bars. The tooth bears on the −X face. The −Y bar stays clear of
    # the button head (see ``_bar_span``).
    bars = []
    ties = []
    for sign in (1.0, -1.0):
        by0, by1 = _bar_span(t, sign)
        bars.append(_box(t["ox1"] - 1.0, t["ox1"] + 4.0, by0, by1, BAR_Z0, BAR_Z1))
        inner = by0 if abs(by0) <= abs(by1) else by1
        ty0, ty1 = _span(inner - sign * 0.8, inner + sign * 1.6)
        ties.append(_box(t["ox1"] - 4.0, t["ox1"] + 0.2, ty0, ty1, BAR_Z0, BAR_Z1))
    body = _fuse([floor, back_mid, front, *back_side, *sides, *ledges, *ribs, *bars, *ties])
    # Relief so the pusher-peg head can travel beside the floor.
    relief = []
    for i in range(21):
        pose = pose_at_phi(link, phi_for_button_fraction(link, i / 20.0))
        relief.append(_cyl(
            pose.pusher_pin_x, pose.pusher_pin_y, link.floor_z0 - 0.2, -0.01,
            PEG_D / 2.0 + HEAD_EXTRA / 2.0 + 0.4,
        ))
    # The bullnose at rest sits in the back wall. The window is the face envelope.
    # A 5.2 mm packet is taller than this notch, so the wall still holds the stack.
    notch = _box(
        t["ox0"] - 0.2, t["x0"] + 0.05,
        -FACE_W / 2.0 - 0.2, FACE_W / 2.0 + 0.2,
        -0.02, BULLNOSE_Z,
    )
    cut = _cut(body, [*relief, notch])
    # The notch ceiling and the exit-wall underside face down into the packet
    # path. A 45° chamfer leaves them printable without support in the bore.
    return _bore_chamfers(cut, t)


def _bore_chamfers(body, t):
    """Slope the back-notch ceiling and the exit underside."""
    back = [
        edge for edge in body.edges()
        if abs(edge.center().Z - BULLNOSE_Z) < 0.08
        and abs(edge.center().X - (t["x0"] + 0.05)) < 0.2
        and edge.length > 1.0
    ]
    front = [
        edge for edge in body.edges()
        if abs(edge.center().Z - FRONT_WALL_Z) < 0.08
        and abs(edge.center().X - t["x1"]) < 0.2
        and edge.length > 1.0
    ]
    if not back or not front:
        raise ValueError(f"bore chamfer edges back={len(back)} front={len(front)}")
    sloped = body.chamfer(2.0, None, back)
    return sloped.chamfer(2.6, None, _refind_front(sloped, t))


def _refind_front(body, t):
    """The exit edge moves when the back chamfer rebuilds the solid."""
    front = [
        edge for edge in body.edges()
        if abs(edge.center().Z - FRONT_WALL_Z) < 0.08
        and abs(edge.center().X - t["x1"]) < 0.2
        and edge.length > 1.0
    ]
    if not front:
        raise ValueError("exit chamfer edge disappeared")
    return front


def _chassis(p: Params, link: Linkage):
    """Basement frame: boss, stops, guides, spring pocket, two hooks."""
    t = _tube(p, link)
    feat = _rod_features(link)
    stroke = link.button_stroke
    base = _box(-115.0, 110.0, -20.2, 55.0, CHASSIS_Z0, -15.6)
    boss = _cyl(link.pivot_x, link.pivot_y, -15.8, link.crank_z0 - Z_GAP, 7.0)
    stops = [home_stop_solid(link), forward_stop_solid(link)]
    # Bridges from each stop up to the base, under the rod shaft.
    home_x0 = link.home_x + STOP_EPS
    home_bridge = _box(home_x0, link.home_x + EXIT_WALL, LUG_Y[0], -19.8, CHASSIS_Z0, -15.75)
    fwd_x1 = SHOULDER_X - stroke - STOP_EPS
    fwd_bridge = _box(fwd_x1 - LUG_T, fwd_x1, LUG_Y[0], -19.8, CHASSIS_Z0, -15.75)
    # Spring pocket. Walls stay 0.5 mm off the folds and outside the swept disc.
    seat = ROD_PAD_X - PROTOTYPE_SPRING.installed()
    back_x = seat - INSERT_T - POCKET_RECESS
    y_near = SPRING_Y + SPRING_AMPLITUDE / 2.0 + WALL_CLEAR  # −66.5
    y_far = SPRING_Y - SPRING_AMPLITUDE / 2.0 - WALL_CLEAR  # −81.5
    z_floor = SPRING_Z0 - 0.2
    spine = _box(back_x - t["wall"], 20.0, y_far - t["wall"], -16.0, CHASSIS_Z0, z_floor)
    pocket_floor = _box(back_x - t["wall"], seat + 1.0, y_far - t["wall"], y_near + t["wall"], CHASSIS_Z0, z_floor)
    side_near = _box(back_x, seat + 1.0, y_near, y_near + t["wall"], z_floor - 0.2, -2.5)
    side_far = _box(back_x, seat + 1.0, y_far - t["wall"], y_far, z_floor - 0.2, -2.5)
    back_wall = _box(back_x - t["wall"], back_x, y_far - t["wall"], y_near + t["wall"], z_floor - 0.2, -2.5)
    # Steps the B insert sits against. The 4.8 mm behind them is the C recess.
    step_x1 = seat - INSERT_T
    steps = [
        _box(step_x1 - t["wall"], step_x1, y_near - 1.2, y_near + 0.2, z_floor, SPRING_Z0 + SPRING_HEIGHT),
        _box(step_x1 - t["wall"], step_x1, y_far - 0.2, y_far + 1.2, z_floor, SPRING_Z0 + SPRING_HEIGHT),
    ]
    # Rod guides. North rail is clear of the flange. South rail is split around the flange,
    # the shoulder, the head, and the spring pad.
    shaft_y1 = BUTTON_Y + ROD_W / 2.0
    shaft_y0 = BUTTON_Y - ROD_W / 2.0
    north = _box(
        feat["x_start"] - stroke - 1.0, feat["head_outer"],
        shaft_y1 + GUIDE_CLEAR, shaft_y1 + GUIDE_CLEAR + t["wall"],
        link.rod_z0, link.rod_z1, 
    )
    north_leg = _box(-20.0, -14.0, shaft_y1 + GUIDE_CLEAR, -15.0, CHASSIS_Z0, link.rod_z1)
    south_y0 = shaft_y0 - GUIDE_CLEAR - t["wall"]
    south_y1 = shaft_y0 - GUIDE_CLEAR
    pad_lo, _pad_hi = _swept(feat["pad"], stroke)
    sh_lo, sh_hi = _swept(feat["shoulder"], stroke)
    fl_lo, fl_hi = _swept(feat["flange"], stroke)
    hd_lo, _hd_hi = _swept((feat["head_inner"], feat["head_outer"]), stroke)
    web_x0, _web_x1, _south_y = _spring_web(link)
    web_swept = web_x0 - stroke
    # The pad's north web travels through x left of the forward lug. Keep the
    # south guide off that interval as well as off the flange, shoulder, and head.
    south_spans = (
        (feat["x_start"] - stroke - 1.0, min(pad_lo, web_swept) - 0.4),
        (sh_hi + 0.4, fl_lo - 0.4),
        (fl_hi + 0.4, hd_lo - 0.4),
    )
    south = [_box(a, b, south_y0, south_y1, link.rod_z0, link.rod_z1) for a, b in south_spans]
    # The guide rail sits above the bed. A plinth under each span keeps that
    # underside off the support list. The spans already miss the rod's features.
    south_plinths = [
        _box(a, b, south_y0, south_y1, CHASSIS_Z0, link.rod_z0 + 0.2) for a, b in south_spans
    ]
    north_plinth = _box(
        feat["x_start"] - stroke - 1.0, feat["head_outer"],
        shaft_y1 + GUIDE_CLEAR, shaft_y1 + GUIDE_CLEAR + t["wall"],
        CHASSIS_Z0, link.rod_z0 + 0.2,
    )
    # Ties from the artery up to the guide, in the same X spans.
    south_drops = []
    for a, b in south_spans:
        mid = (a + b) / 2.0
        south_drops.append(_box(mid - 1.2, mid + 1.2, LUG_Y[0] - 6.0, south_y1, CHASSIS_Z0, link.rod_z0 + 0.2))
    artery = _box(south_spans[0][0], south_spans[-1][1], LUG_Y[0] - 6.0, LUG_Y[0] - 0.4, CHASSIS_Z0, z_floor)
    # Hooks. Tooth overlaps the rib by 1 mm and sits 0.05 mm above it, so the
    # chassis cannot drop in −Z without the tooth meeting the rib.
    hook_pos = _chassis_hook(62.0, 72.0, t["oy"] + 2.6, 1.0, CHASSIS_Z0, link.floor_z1)
    hook_neg = _chassis_hook(-38.0, -28.0, -(t["oy"] + 2.6), -1.0, CHASSIS_Z0, link.floor_z1)
    bed_stops = [_on_chassis_bed(stop) for stop in stops]
    parts = [base, boss, home_bridge, fwd_bridge, spine, pocket_floor, side_near, side_far,
             back_wall, north, north_leg, north_plinth, artery, *bed_stops, *steps, *south,
             *south_plinths, *south_drops, hook_pos, hook_neg]
    fused = _fuse(parts)
    head_r = PIVOT_PEG_D / 2.0 + HEAD_EXTRA / 2.0 + 0.4
    # Open through the bed so the pivot head still seats against the boss.
    head_void = _cyl(link.pivot_x, link.pivot_y, CHASSIS_Z0 - 0.2, -15.55, head_r)
    grip_void = _cyl(link.pivot_x, link.pivot_y, -15.55, link.crank_z0 - Z_GAP + 0.2, PIVOT_PEG_D / 2.0)
    return _cut(fused, [head_void, grip_void])


def _on_chassis_bed(shape):
    """Pad a linkage stop down to the chassis bed. The stop face stays where it is."""
    bb = shape.bounding_box()
    if bb.min.Z <= CHASSIS_Z0 + 1e-6:
        return shape
    pad = _box(bb.min.X, bb.max.X, bb.min.Y, bb.max.Y, CHASSIS_Z0, bb.min.Z + 0.2)
    return _fuse([shape, pad])


def _chassis_hook(x0, x1, rib_outer_y, sign, z0, rib_top):
    """Post 0.3 mm outboard of a body rib. The tooth reaches 1 mm back over it.

    The catching face is the tooth's underside, square to −Z, 0.05 mm above
    the rib. Releasing the clip deflects the tooth outward by that 1 mm.
    """
    wall = 2.4
    post_in = rib_outer_y + sign * 0.3
    post_out = rib_outer_y + sign * (0.3 + wall)
    tooth_in = rib_outer_y - sign * 1.0
    py0, py1 = _span(post_in, post_out)
    ty0, ty1 = _span(tooth_in, post_in)
    z_catch = rib_top + STOP_EPS
    z_top = z_catch + wall
    mid = (x0 + x1) / 2.0
    post = _box(x0, x1, py0, py1, z0, z_top)
    tooth = _box(mid - 3.0, mid + 3.0, ty0, ty1, z_catch, z_top)
    return _fuse([post, tooth])


def _shim_plate(x0, x1, y0, y1, z0, thickness):
    return _box(x0, x1, y0, y1, z0, z0 + thickness).solid()


def _shims(p: Params, link: Linkage, thickness: float):
    """One plate on each ledge. ``thickness`` 0 returns no plates."""
    if thickness <= 0:
        return []
    t = _tube(p, link)
    plates = []
    for sign in (1.0, -1.0):
        y_in = sign * (t["y1"] + 0.4)
        y_out = sign * (t["y1"] + 5.4)
        lo, hi = (y_in, y_out) if y_out > y_in else (y_out, y_in)
        plates.append(_shim_plate(t["ox1"] + 0.4, t["ox1"] + 6.6, lo, hi, LEDGE_Z, thickness))
    return plates


def _lip(p: Params, link: Linkage, gap: float):
    """Shelf, cheeks, separator blade, feet, and two hooks. ``gap`` is the separator edge."""
    t = _tube(p, link)
    # The shelf stays at z=0 for every shim. Only the blade and the feet follow
    # ``gap``, so a thicker shim does not lift the shelf into the packet.
    shelf_x0 = t["ox1"] + 0.3
    shelf_x1 = t["ox1"] + LIP_LEN
    # Bullnose of the full shelf thickness. R0.8 would leave a 1.6 mm tip.
    nose_r = t["wall"] / 2.0
    shelf = _box(shelf_x0, shelf_x1 - nose_r + 0.2, -t["y1"] - 2.0, t["y1"] + 2.0, -t["wall"], 0.0)
    nose = (
        Pos(shelf_x1 - nose_r, 0.0, -nose_r)
        * Rot(90.0, 0.0, 0.0)
        * Cylinder(nose_r, (t["y1"] + 2.0) * 2.0)
    )
    # Cheeks sit just outside the packet and past the ledge, so they miss the
    # shim seat. Their top stays at CHEEK_TOP, under the separator edge.
    half = p.packet.width / 2.0
    cheeks = []
    for sign in (1.0, -1.0):
        # Just outside the packet, and inboard of the hook riser, past the ledge.
        cy0, cy1 = _span(sign * (half + 0.2), sign * (half + 3.3))
        cheeks.append(_box(t["ox1"] + 8.3, shelf_x1 - 2.0, cy0, cy1, -0.2, CHEEK_TOP))
    # Blade reaches back over the packet. The underside is the gap. The
    # packet-facing lower corner is an R0.8 round on the 2.4 mm plate.
    blade_x0 = p.packet.length / 2.0 - BLADE_BITE
    blade_x1 = t["ox1"] + 3.0
    blade_y0 = -t["y1"] + 0.3
    blade_y1 = t["y1"] - 0.3
    blade_top = gap + BLADE_T
    blade = _box(blade_x0, blade_x1, blade_y0, blade_y1, gap, blade_top)
    blade = _round_lower_edge(blade, blade_x0, blade_y0, blade_y1, gap, EDGE_R)
    feet = []
    for sign in (1.0, -1.0):
        # Inner edge overlaps the blade. Outer end reaches the hook riser.
        # The sole stays STOP_EPS above the shim so the two do not fuse.
        fy0, fy1 = _span(sign * (t["y1"] - 0.5), sign * (t["y1"] + 5.6))
        feet.append(_box(
            t["ox1"] + 0.4, t["ox1"] + 11.0, fy0, fy1,
            gap + STOP_EPS, gap + STOP_EPS + t["wall"],
        ))
    hooks = []
    for sign in (1.0, -1.0):
        hooks.append(_lip_hook(t, sign))
    return _fuse([shelf, nose, blade, *cheeks, *feet, *hooks])


def _round_lower_edge(blade, x0: float, y0: float, y1: float, z0: float, radius: float):
    """Replace the packet-facing lower corner with a radius. The underside stays at ``z0``."""
    corner = _box(x0 - 0.2, x0 + radius, y0 - 0.2, y1 + 0.2, z0 - 0.2, z0 + radius)
    disc = Pos(x0 + radius, 0.0, z0 + radius) * Rot(90.0, 0.0, 0.0) * Cylinder(radius, y1 - y0 + 2.0)
    scrap = (corner - disc).solid()
    return (blade - scrap).solid()


def _span(a: float, b: float) -> tuple[float, float]:
    return (a, b) if b > a else (b, a)


def _bar_span(t, sign: float) -> tuple[float, float]:
    """Y of the lip bar. The inner face bites 0.4 mm into the side wall.

    On −Y the outer face stops 0.8 mm short of the button head.
    """
    inner = sign * (t["oy"] - 0.4)
    outer = sign * (t["oy"] + 3.6)
    if sign < 0:
        outer = max(outer, HEAD_UPPER_Y + 0.8)
    return _span(inner, outer)


def _lip_hook(t, sign: float):
    """Tooth 0.15 mm behind the bar. A +X pull of 1 mm drives the tooth into it.

    The rail is outboard of the bar and above the button head. The riser stands
    on the shelf, past the shim. Overlap with the bar in Y is 1 mm. Hook height
    does not follow the shim: the bars are tall enough for every separator gap.
    """
    z0 = HOOK_Z0
    z1 = HOOK_Z1
    by0, by1 = _bar_span(t, sign)
    outer = by0 if abs(by0) >= abs(by1) else by1
    # Tooth takes the outer 1 mm of the bar and 0.4 mm past it, for the rail.
    ty0, ty1 = _span(outer - sign * 1.0, outer + sign * 0.4)
    tooth_x0 = t["ox1"] - 3.4
    tooth_x1 = t["ox1"] - 1.15  # bar starts at ox1 − 1.0, so 0.15 mm of air
    # Rail just outboard of the bar, clear of it by 0.2 mm, overlapping the tooth.
    rail_in = outer + sign * 0.2
    rail_out = outer + sign * 2.6
    ry0, ry1 = _span(rail_in, rail_out)
    riser_x0 = t["ox1"] + 8.4
    riser_x1 = t["ox1"] + 11.0
    # Riser on the shelf, 2.4 mm in Y. The shelf outer face is at y = ±(y1+2).
    outer = sign * (t["y1"] + 2.0)
    sy0, sy1 = _span(outer, outer - sign * t["wall"])
    shelf_y = sy0 if abs(sy0) <= abs(sy1) else sy1
    riser = _box(riser_x0, riser_x1, sy0, sy1, -0.2, z1)
    # High plate at the riser, from the shelf Y out to the rail. Above the head.
    py0, py1 = _span(shelf_y, rail_out)
    plate = _box(riser_x0, riser_x1, py0, py1, z0, z1)
    rail = _box(tooth_x0, riser_x1, ry0, ry1, z0, z1)
    tooth = _box(tooth_x0, tooth_x1, ty0, ty1, z0, z1)
    return _fuse([riser, plate, rail, tooth])


def _spring_seat(link: Linkage):
    """B insert. Its +X face is the seat. A and C are not solids."""
    spec = PROTOTYPE_SPRING
    seat = ROD_PAD_X - spec.installed()
    y0 = SPRING_Y - SPRING_AMPLITUDE / 2.0
    y1 = SPRING_Y + SPRING_AMPLITUDE / 2.0
    return _box(seat - INSERT_T, seat, y0, y1, SPRING_Z0, SPRING_Z0 + spec.height).solid()


def _spring_at(link: Linkage, travel: float, length: float):
    """Spring of ``length`` with its rod-end pad face on the rod pad at this travel."""
    pad_face = ROD_PAD_X - travel
    x0 = pad_face - length
    return spring_solid(PROTOTYPE_SPRING, length, x0, SPRING_Y, SPRING_Z0)


def button_keepout(link: Linkage):
    """Ø6 cylinder swept along the button peg from rest to full stroke, over the peg's Z."""
    rest = pose_at_phi(link, link.phi0)
    full = pose_at_phi(link, link.phi1)
    z0 = link.rod_z0
    z1 = link.crank_z1 + END_ALLOW + HEAD_T
    return _stadium(full.button_x, BUTTON_Y, rest.button_x, BUTTON_Y, 6.0, z0, z1)


def moving_solids(p: Params, link: Linkage, pose: Pose, spring_length: float) -> dict:
    return {
        "crank": _crank(link, pose.phi),
        "rod": _rod(link, pose),
        "pusher": _pusher(link, pose),
        "spring": _spring_at(link, pose.button_travel, spring_length),
        "peg_pivot": _pivot_peg(link),
        "peg_pusher": _pusher_peg(link, pose),
        "peg_button": _button_peg(link, pose),
    }


def static_solids(p: Params, link: Linkage, gap: float) -> dict:
    shim_t = gap - LEDGE_Z
    plates = _shims(p, link, shim_t)
    parts = {
        "body": _body(p, link),
        "chassis": _chassis(p, link),
        "lip": _lip(p, link, gap),
        "spring_seat": _spring_seat(link),
        "dummy": Pos(0.0, 105.0, 0.0) * dummy_build(p)["dummy"].shape,
    }
    if len(plates) == 2:
        parts["shim_04_a"] = plates[0]
        parts["shim_04_b"] = plates[1]
    elif len(plates) == 1:
        parts["shim"] = plates[0]
    return parts


def spare_shim(p: Params, link: Linkage):
    """The 0.8 mm plate, parked clear of the assembly so it can be sliced with the rest."""
    t = _tube(p, link)
    return _shim_plate(t["ox1"] + 24.0, t["ox1"] + 36.0, -8.0, 8.0, 0.0, SHIM_THICK)


def prototype_solids(p: Params, fraction: float = 0.0, gap: float = DEFAULT_GAP) -> dict:
    """Assembly at one button fraction. The exported spring is the free spring.

    The free spring is 3 mm longer than the installed gap, so in this pose it
    runs 3 mm into the seat insert. That is the preload, shown on the free
    part. The sweep uses ``moving_solids`` with the compressed length instead.
    """
    link = linkage_from(p)
    pose = pose_at_phi(link, phi_for_button_fraction(link, fraction))
    parts = static_solids(p, link, gap)
    parts.update(moving_solids(p, link, pose, PROTOTYPE_SPRING.free_length))
    if gap == DEFAULT_GAP:
        parts["shim_08"] = spare_shim(p, link)
    return parts


def print_location_for(name: str, shape):
    """Bed pose. Most parts only drop onto z=0. A few are turned first.

    The rod lies on the shaft's +Y face, so the long axis is on the bed and the
    spring pad stands up off that face. The lip lies on the separator edge.
    """
    if name == "rod":
        return _turned(shape, Rot(-90.0, 0.0, 0.0))
    if name == "lip":
        return _turned(shape, Rot(0.0, -90.0, 0.0))
    if name in ("peg_pusher", "peg_button"):
        return _turned(shape, Rot(180.0, 0.0, 0.0))
    if name.startswith("dummy"):
        return None
    return on_bed(shape)


def _turned(shape, rotation):
    spun = rotation * shape
    zmin = spun.bounding_box().min.Z
    return Pos(0.0, 0.0, -zmin) * rotation


def min_wall_override(name: str) -> float | None:
    """Spring beams and shim plates are the only parts thinner than 2.4 mm on purpose."""
    if name == "spring":
        return PROTOTYPE_SPRING.thickness
    if name.startswith("shim_04"):
        return SHIM_THIN
    if name == "shim_08":
        return SHIM_THICK
    return None
