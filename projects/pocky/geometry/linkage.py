"""Straight-line pusher linkage for the M1 motion proof.

Constants are the M0 proposal plus the three corrections from the M1 review
(hub OD 11 mm, slot stadia measured center-to-center, crank and neck in
different Z bands). They are not in ``params.toml``. Stroke and crank radius
are derived from the packet and magazine lengths so a ``--set`` cannot leave
the crank short of the stroke.

Assembly frame matches ``geometry/packet.py``: origin at the packet centre,
+X toward the exit, Z up, packet underside at z = 0.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass

from build123d import Box, Cylinder, Location, Plane, Polygon, Pos, Rot, extrude

from projects.pocky.geometry.packet import packet
from projects.pocky.params import Params

# Proposed linkage. Not accepted into params.toml.
PRESENTATION = 40.0
EXIT_WALL = 3.0
POCKET_SETBACK = 2.0
HALF_DEG = 30.0
BUTTON_OFFSET = -20.0  # button line y minus pivot y
BUTTON_Y = -28.0
FACE_LEAD = 16.0
FACE_W = 40.0
FACE_H = 4.2
NOSE_R = FACE_H / 2.0  # full bullnose, 2.1
PIN_D = 4.0
PIN_HOLE = 4.1
SLOT_W = 4.30
SLOT_END_MARGIN = 1.0
PIVOT_PIN_D = 5.0
PIVOT_BORE = 5.2
HUB_OD = 11.0  # (11 - 5.2) / 2 = 2.9 mm wall, above structure.min_wall
ARM_W = 10.0  # (10 - 4.30) / 2 = 2.85 mm beside the button slot
CRANK_T = 4.0
CARRIAGE_T = 4.0
ROD_W = 10.0
ROD_T = 4.0
Z_GAP = 0.4
NECK_X = 4.0  # a 6 mm neck centered on the bullnose would pass the contact face
NECK_Y = 6.0
NECK_Z_TOP = 2.0
NECK_EMBED = 0.2  # into the carriage so the fuse is one solid
CHAMFER_LEG = 1.2
CHAMFER_DEG = 30.0
HEAD_LEN = 14.0
HEAD_GAP = 3.0  # full-stroke gap from the outer face to the head's inner face
HEAD_TOP = 12.0
HEAD_SIDE_GAP = 0.2
FLOOR_X = (-115.0, 90.0)
FLOOR_Y = (-46.0, 52.0)
SLOT_X_MARGIN = 2.0
SLOT_Y_CLEAR = 0.5  # per side: 6 mm neck in a 7 mm slot
CARRIAGE_X = (-8.0, 20.0)  # relative to the pusher pin
CARRIAGE_Y = (-8.0, 50.0)
STOP_EPS = 0.05  # air so a nominal zero gap does not fuse the stop solids
SHOULDER_X = 40.0  # nominal shoulder face at button travel 0
FLANGE_T = 4.0
LUG_T = 4.0
LUG_Y = (-42.0, -36.0)
HOME_BLOCK_Z = (-18.0, -9.0)
FORWARD_LUG_Z = (-18.0, -12.0)
CUT_EPS = 0.5

POSE_FRACTIONS = {"0": 0.0, "25": 0.25, "50": 0.5, "75": 0.75, "100": 1.0}
CHAMFER_NOTE = "applied"


@dataclass(frozen=True)
class Linkage:
    """Sizes derived from params. Angles are radians."""

    stroke: float
    radius: float
    pivot_x: float
    pivot_y: float
    phi0: float
    phi1: float
    button_stroke: float
    face0: float
    e_abs: float
    outer_x: float
    home_x: float
    packet_length: float
    packet_width: float
    packet_height: float
    min_wall: float
    floor_z0: float
    floor_z1: float
    carriage_z0: float
    carriage_z1: float
    crank_z0: float
    crank_z1: float
    rod_z0: float
    rod_z1: float


@dataclass(frozen=True)
class Pose:
    """One crank angle. ``phi`` is radians, CCW from +X."""

    phi: float
    face_x: float
    button_travel: float
    button_x: float
    button_y: float
    slot_radius: float
    pusher_pin_x: float
    pusher_pin_y: float
    speed_ratio: float
    packet_shift: float
    protrusion: float


def linkage_from(p: Params) -> Linkage:
    """Derive the crank from the packet and magazine. Radius equals the stroke at the defaults."""
    phi0 = math.radians(90.0 + HALF_DEG)
    phi1 = math.radians(90.0 - HALF_DEG)
    stroke = PRESENTATION + EXIT_WALL + (p.magazine.length_i - p.packet.length) + POCKET_SETBACK
    delta_cos = math.cos(phi1) - math.cos(phi0)
    radius = stroke / delta_cos
    face0 = -p.magazine.length_i / 2.0 - POCKET_SETBACK
    e_abs = abs(BUTTON_OFFSET)
    floor_z1 = 0.0
    floor_z0 = -p.structure.min_wall
    carriage_z1 = floor_z0 - Z_GAP
    carriage_z0 = carriage_z1 - CARRIAGE_T
    crank_z1 = carriage_z0 - Z_GAP
    crank_z0 = crank_z1 - CRANK_T
    rod_z1 = crank_z0 - Z_GAP
    rod_z0 = rod_z1 - ROD_T
    return Linkage(
        stroke=stroke,
        radius=radius,
        pivot_x=face0 - FACE_LEAD - radius * math.cos(phi0),
        pivot_y=BUTTON_Y - BUTTON_OFFSET,
        phi0=phi0,
        phi1=phi1,
        button_stroke=2.0 * e_abs * math.tan(math.radians(HALF_DEG)),
        face0=face0,
        e_abs=e_abs,
        outer_x=p.magazine.length_i / 2.0 + EXIT_WALL,
        home_x=p.magazine.length_i / 2.0,
        packet_length=p.packet.length,
        packet_width=p.packet.width,
        packet_height=p.packet.height,
        min_wall=p.structure.min_wall,
        floor_z0=floor_z0,
        floor_z1=floor_z1,
        carriage_z0=carriage_z0,
        carriage_z1=carriage_z1,
        crank_z0=crank_z0,
        crank_z1=crank_z1,
        rod_z0=rod_z0,
        rod_z1=rod_z1,
    )


def button_fraction_from_env() -> float:
    """``POCKY_POSE`` is a percent of button travel: 0, 25, 50, 75, or 100."""
    raw = os.environ.get("POCKY_POSE", "0")
    if raw not in POSE_FRACTIONS:
        allowed = ", ".join(sorted(POSE_FRACTIONS, key=int))
        raise ValueError(f"POCKY_POSE must be one of {allowed}, got {raw!r}")
    return POSE_FRACTIONS[raw]


def phi_for_button_fraction(link: Linkage, fraction: float) -> float:
    """Crank angle whose button travel is ``fraction`` of the stroke. ``fraction`` is 0..1."""
    if fraction < 0.0 or fraction > 1.0:
        raise ValueError(f"button fraction must be in [0, 1], got {fraction}")
    travel = fraction * link.button_stroke
    cot_phi = travel / link.e_abs + _cot(link.phi0)
    return math.atan2(1.0, cot_phi)


def pose_at_phi(link: Linkage, phi: float) -> Pose:
    """Closed form. Button travel is zero at ``phi0`` and increases as ``phi`` falls."""
    face_x = link.pivot_x + link.radius * math.cos(phi) + FACE_LEAD
    slot_radius = link.e_abs / math.sin(phi)
    button_x = link.pivot_x + slot_radius * math.cos(phi + math.pi)
    travel = link.e_abs * (_cot(phi) - _cot(link.phi0))
    pin_x = link.pivot_x + link.radius * math.cos(phi)
    pin_y = link.pivot_y + link.radius * math.sin(phi)
    back = -link.packet_length / 2.0
    shift = max(0.0, face_x - back)
    return Pose(
        phi=phi,
        face_x=face_x,
        button_travel=travel,
        button_x=button_x,
        button_y=BUTTON_Y,
        slot_radius=slot_radius,
        pusher_pin_x=pin_x,
        pusher_pin_y=pin_y,
        speed_ratio=(link.radius / link.e_abs) * math.sin(phi) ** 3,
        packet_shift=shift,
        protrusion=back + shift + link.packet_length - link.outer_x,
    )


def parked_shift(link: Linkage) -> float:
    """Packet shift at the forward stop. The return branch leaves the packet here."""
    return pose_at_phi(link, link.phi1).packet_shift


def button_slot_radii(link: Linkage) -> tuple[float, float]:
    """End-arc radii of the crank slot, inner then outer. The pin center stays 1 mm inside."""
    r_min = link.e_abs  # sin(phi) = 1 at mid-stroke
    r_max = link.e_abs / math.sin(link.phi1)
    return r_min - SLOT_END_MARGIN, r_max + SLOT_END_MARGIN


def pusher_slot_ends(link: Linkage) -> tuple[float, float]:
    """Y of the carriage-slot end arcs. The pin center stays 1 mm inside."""
    y_min = link.pivot_y + link.radius * math.sin(link.phi1)
    y_max = link.pivot_y + link.radius
    return y_min - SLOT_END_MARGIN, y_max + SLOT_END_MARGIN


def floor_slot_bounds(link: Linkage) -> tuple[float, float, float, float]:
    """Through-slot ``(x0, x1, y0, y1)``: neck envelope over the stroke, plus the margins."""
    nose = NOSE_R
    x_lo = (link.face0 - nose) - NECK_X / 2.0 - SLOT_X_MARGIN
    x_hi = (link.face0 + link.stroke - nose) + NECK_X / 2.0 + SLOT_X_MARGIN
    y_lo = -(NECK_Y / 2.0 + SLOT_Y_CLEAR)
    y_hi = NECK_Y / 2.0 + SLOT_Y_CLEAR
    return x_lo, x_hi, y_lo, y_hi


def slot_end_clearance(link: Linkage, pose: Pose) -> tuple[float, float]:
    """How far each pin center sits from the nearer end-arc center, button slot then pusher slot."""
    inner, outer = button_slot_radii(link)
    button_clear = min(abs(pose.slot_radius - inner), abs(pose.slot_radius - outer))
    y0, y1 = pusher_slot_ends(link)
    pusher_clear = min(abs(pose.pusher_pin_y - y0), abs(pose.pusher_pin_y - y1))
    return button_clear, pusher_clear


def mechanism_solids(p: Params, phi: float) -> dict:
    """Printable solids at one crank angle. Pins are not included."""
    link = linkage_from(p)
    pose = pose_at_phi(link, phi)
    return {
        "floor": floor_solid(link),
        "crank": crank_solid(link, phi),
        "rod": rod_solid(link, pose),
        "pusher": pusher_solid(link, pose),
        "home_stop": home_stop_solid(link),
        "forward_stop": forward_stop_solid(link),
    }


def pin_solids(p: Params, phi: float) -> dict:
    """Steel pins for the sweep only. ``build`` exports the holes, not these."""
    link = linkage_from(p)
    pose = pose_at_phi(link, phi)
    return {
        "button_pin": _cyl(pose.button_x, pose.button_y, link.rod_z0, link.crank_z1, PIN_D / 2.0),
        "pusher_pin": _cyl(
            pose.pusher_pin_x, pose.pusher_pin_y, link.crank_z0, link.carriage_z1, PIN_D / 2.0,
        ),
        "pivot_pin": _cyl(link.pivot_x, link.pivot_y, link.crank_z0, link.crank_z1, PIVOT_PIN_D / 2.0),
    }


def packet_solids(p: Params, shift: float) -> dict:
    """Bottom packet moved by ``shift``, and the next packet sitting on it, unshifted."""
    bottom = Pos(shift, 0, 0) * packet(p)
    second = Pos(0, 0, p.packet.height) * packet(p)
    return {"packet": bottom, "packet2": second}


def ghost_packet_shapes(p: Params):
    """Bottom packet at the ``POCKY_POSE`` contact shift, and the next packet unshifted."""
    link = linkage_from(p)
    pose = pose_at_phi(link, phi_for_button_fraction(link, button_fraction_from_env()))
    solids = packet_solids(p, pose.packet_shift)
    return solids["packet"], solids["packet2"]


def on_bed(shape) -> Location:
    """Pure Z translation that puts the part's lowest point on z = 0."""
    return Location((0.0, 0.0, -shape.bounding_box().min.Z))


def floor_solid(link: Linkage):
    sx0, sx1, sy0, sy1 = floor_slot_bounds(link)
    x0 = min(FLOOR_X[0], sx0 - 2.0)
    x1 = max(FLOOR_X[1], sx1 + 2.0)
    y0 = min(FLOOR_Y[0], sy0 - 2.0)
    y1 = max(FLOOR_Y[1], sy1 + 2.0)
    plate = _box(x0, x1, y0, y1, link.floor_z0, link.floor_z1)
    slot = _box(sx0, sx1, sy0, sy1, link.floor_z0 - CUT_EPS, link.floor_z1 + CUT_EPS)
    return (plate - slot).solid()


def crank_solid(link: Linkage, phi: float):
    """Straight 180° bar. Local +X is the pusher; the button slot is on local −X."""
    z0, z1 = link.crank_z0, link.crank_z1
    inner, outer = button_slot_radii(link)
    reach_button = outer + SLOT_W / 2.0 + link.min_wall
    reach_pusher = link.radius + PIN_HOLE / 2.0 + link.min_wall
    bar = _box(-reach_button, reach_pusher, -ARM_W / 2.0, ARM_W / 2.0, z0, z1)
    hub = _cyl(0.0, 0.0, z0, z1, HUB_OD / 2.0)
    cz0, cz1 = z0 - CUT_EPS, z1 + CUT_EPS
    bore = _cyl(0.0, 0.0, cz0, cz1, PIVOT_BORE / 2.0)
    slot = _stadium(-outer, 0.0, -inner, 0.0, SLOT_W, cz0, cz1)
    hole = _cyl(link.radius, 0.0, cz0, cz1, PIN_HOLE / 2.0)
    local = (bar + hub) - bore - slot - hole
    world = Pos(link.pivot_x, link.pivot_y, 0.0) * Rot(0.0, 0.0, math.degrees(phi)) * local
    return world.solid()


def rod_solid(link: Linkage, pose: Pose):
    """Button rod at this travel. Built at travel 0, then shifted by ``−travel`` along X."""
    rest = pose_at_phi(link, link.phi0)
    pin_x = rest.button_x
    y0 = BUTTON_Y - ROD_W / 2.0
    y1 = BUTTON_Y + ROD_W / 2.0
    z0, z1 = link.rod_z0, link.rod_z1
    x_start = pin_x - (PIN_HOLE / 2.0 + link.min_wall)
    head_inner = link.outer_x + HEAD_GAP + link.button_stroke
    head_outer = head_inner + HEAD_LEN
    shaft = _box(x_start, head_outer, y0, y1, z0, z1)
    # The head stands above the floor. Keep it off the packet's −Y face.
    head_y1 = min(-link.packet_width / 2.0 - HEAD_SIDE_GAP, BUTTON_Y)
    head = _box(head_inner, head_outer, LUG_Y[0], head_y1, z0, HEAD_TOP)
    flange_x1 = link.home_x - STOP_EPS
    flange = _box(flange_x1 - FLANGE_T, flange_x1, LUG_Y[0], y0, HOME_BLOCK_Z[0], z1)
    shoulder_x0 = SHOULDER_X + STOP_EPS
    shoulder = _box(
        shoulder_x0, shoulder_x0 + FLANGE_T, LUG_Y[0], y0, z0, FORWARD_LUG_Z[1],
    )
    hole = _cyl(pin_x, BUTTON_Y, z0 - CUT_EPS, z1 + CUT_EPS, PIN_HOLE / 2.0)
    rod = (shaft + head + flange + shoulder) - hole
    return (Pos(-pose.button_travel, 0.0, 0.0) * rod).solid()


def pusher_solid(link: Linkage, pose: Pose):
    """Carriage, neck, and bullnose. The carriage translates in X and does not move in Y."""
    global CHAMFER_NOTE
    pin_x = pose.pusher_pin_x
    z0, z1 = link.carriage_z0, link.carriage_z1
    y_lo, y_hi = pusher_slot_ends(link)
    side = SLOT_W / 2.0
    car_y0 = min(CARRIAGE_Y[0], y_lo - side - link.min_wall)
    car_y1 = max(CARRIAGE_Y[1], y_hi + side + link.min_wall)
    carriage = _box(pin_x + CARRIAGE_X[0], pin_x + CARRIAGE_X[1], car_y0, car_y1, z0, z1)
    slot = _stadium(pin_x, y_lo, pin_x, y_hi, SLOT_W, z0 - CUT_EPS, z1 + CUT_EPS)
    body = carriage - slot
    cx = pose.face_x - NOSE_R
    neck = _box(cx - NECK_X / 2.0, cx + NECK_X / 2.0, -NECK_Y / 2.0, NECK_Y / 2.0, z1 - NECK_EMBED, NECK_Z_TOP)
    bullnose = Pos(cx, 0.0, NOSE_R) * Rot(90.0, 0.0, 0.0) * Cylinder(NOSE_R, FACE_W)
    fused = body + neck + bullnose
    try:
        solid = (fused - _return_chamfer_cut(pose.face_x)).solid()
        if not solid.is_valid:
            raise ValueError("chamfer solid is invalid")
        CHAMFER_NOTE = "applied"
        return solid
    except ValueError:
        CHAMFER_NOTE = "dropped: boolean did not yield one valid solid"
        return fused.solid()


def home_stop_solid(link: Linkage):
    """Fixed block. The flange's nominal face is ``home_x``; both faces are pulled back by ``STOP_EPS``."""
    x0 = link.home_x + STOP_EPS
    return _box(x0, link.home_x + EXIT_WALL, LUG_Y[0], LUG_Y[1], HOME_BLOCK_Z[0], HOME_BLOCK_Z[1]).solid()


def forward_stop_solid(link: Linkage):
    """Fixed lug. After ``button_stroke`` the shoulder's nominal face lands on this face."""
    nominal = SHOULDER_X - link.button_stroke
    x1 = nominal - STOP_EPS
    return _box(x1 - LUG_T, x1, LUG_Y[0], LUG_Y[1], FORWARD_LUG_Z[0], FORWARD_LUG_Z[1]).solid()


def _cot(angle: float) -> float:
    return math.cos(angle) / math.sin(angle)


def _box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float):
    if x1 <= x0 or y1 <= y0 or z1 <= z0:
        raise ValueError(f"empty box {(x0, x1, y0, y1, z0, z1)}")
    return Pos((x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0) * Box(x1 - x0, y1 - y0, z1 - z0)


def _cyl(x: float, y: float, z0: float, z1: float, radius: float):
    return Pos(x, y, (z0 + z1) / 2.0) * Cylinder(radius, z1 - z0)


def _stadium(x0: float, y0: float, x1: float, y1: float, width: float, z0: float, z1: float):
    """Slot void from center ``(x0, y0)`` to ``(x1, y1)``. ``width`` is the full width."""
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    angle = math.degrees(math.atan2(dy, dx))
    zc = (z0 + z1) / 2.0
    height = z1 - z0
    ends = _cyl(x0, y0, z0, z1, width / 2.0) + _cyl(x1, y1, z0, z1, width / 2.0)
    if length < 1e-9:
        return ends
    bar = Pos((x0 + x1) / 2.0, (y0 + y1) / 2.0, zc) * Rot(0.0, 0.0, angle) * Box(length, width, height)
    return bar + ends


def _return_chamfer_cut(face_x: float):
    """30° wedge, 1.2 mm along the bottom, on the lower rear of the bullnose."""
    rear = face_x - 2.0 * NOSE_R
    x0 = rear - 0.4
    x1 = rear + CHAMFER_LEG
    z_hi = (x1 - x0) * math.tan(math.radians(CHAMFER_DEG))
    poly = Plane.XZ * Polygon((x0, -0.4), (x1, -0.4), (x0, z_hi))
    return extrude(poly, amount=FACE_W / 2.0 + 1.0, both=True)
