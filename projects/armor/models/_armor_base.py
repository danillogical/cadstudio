"""Shared parametric geometry for the two-piece slide-on lid armor (rear shell + front bezel).

Assembly coordinates follow ``projects.armor.params``: X centered, Y from hinge edge up, Z from the
rear shell back face toward the viewer. Variants import the functions below.
"""
from __future__ import annotations

from dataclasses import dataclass

from build123d import (
    Align, Box, BuildPart, BuildSketch, Circle, Cylinder, Location, Locations, Mode, Part, Plane,
    Pos, Rectangle, RectangleRounded, Sketch, extrude,
)

from projects.armor.params import Params

# Keep-out margin (mm) around openings and counterbores in the decoration faces.
DECOR_KEEPOUT = 2.0
# Inset (mm) of the decoration faces from the outer outline.
DECOR_EDGE_INSET = 3.0
# Overshoot (mm) so cutters pass cleanly through faces.
_EPS = 0.5


@dataclass(frozen=True)
class Frame:
    """Dimensions derived from Params (assembly coordinates, mm)."""
    outer_w: float
    outer_h: float
    y0: float
    y1: float
    yc: float
    cavity_w: float
    side_wall_w: float
    screw_x: float
    screw_ys: tuple[float, ...]
    back_th: float
    front_z: float
    total_t: float
    cap_y0: float  # bottom edge of the rear shell top cap


def frame(p: Params) -> Frame:
    """Derive the shell frame; bosses live entirely inside the side walls."""
    f, s = p.fit, p.fasteners
    side_wall_w = s.boss_d + 2 * s.boss_margin
    cavity_w = p.cavity_w
    y0 = f.bottom_hinge_relief
    y1 = p.lid.h + f.top_extension
    outer_h = y1 - y0
    return Frame(
        outer_w=cavity_w + 2 * side_wall_w,
        outer_h=outer_h,
        y0=y0, y1=y1, yc=(y0 + y1) / 2,
        cavity_w=cavity_w,
        side_wall_w=side_wall_w,
        screw_x=cavity_w / 2 + s.boss_margin + s.boss_d / 2,
        screw_ys=(y0 + 32, y0 + 0.55 * outer_h, y1 - 12),
        back_th=p.structure.back_th,
        front_z=p.front_z,
        total_t=p.total_t,
        cap_y0=p.lid.h + f.slide_clearance,
    )


def screw_positions(p: Params) -> list[tuple[float, float]]:
    """(x, y) of all six screw axes, left side first."""
    fr = frame(p)
    return [(sx * fr.screw_x, y) for sx in (-1, 1) for y in fr.screw_ys]


def _slab(w: float, h: float, r: float, cx: float, cy: float, z0: float, z1: float) -> Part:
    """Rounded-rect prism spanning z0..z1."""
    with BuildPart() as bp:
        with BuildSketch(Plane.XY.offset(z0)):
            with Locations((cx, cy)):
                RectangleRounded(w, h, r)
        extrude(amount=z1 - z0)
    return bp.part


def _outline(p: Params, z0: float, z1: float) -> Part:
    fr = frame(p)
    return _slab(fr.outer_w, fr.outer_h, p.structure.outer_corner_r, 0, fr.yc, z0, z1)


def _cyl(x: float, y: float, d: float, z0: float, z1: float) -> Part:
    return Pos(x, y, z0) * Cylinder(d / 2, z1 - z0, align=(Align.CENTER, Align.CENTER, Align.MIN))


def rear_shell(p: Params) -> Part:
    """Back plate, side walls with insert bores, closed top cap; bottom (hinge) edge open."""
    fr, s = frame(p), p.fasteners
    shell = _outline(p, 0, fr.front_z)
    # Hollow out everything above the back plate that is inside the cavity and below the cap.
    cavity = Pos(0, (fr.y0 - 1 + fr.cap_y0) / 2, (fr.back_th + fr.front_z + _EPS) / 2) * Box(
        fr.cavity_w, fr.cap_y0 - (fr.y0 - 1), fr.front_z + _EPS - fr.back_th)
    shell = shell - cavity
    for x, y in screw_positions(p):
        shell = shell - _cyl(x, y, s.insert_d, fr.front_z - s.insert_depth, fr.front_z + _EPS)
    return shell


def front_bezel(p: Params) -> Part:
    """Front plate with screen opening, optional camera notch and counterbored M3 through holes."""
    fr, s, sc, cam = frame(p), p.fasteners, p.screen, p.camera
    z0, z1 = fr.front_z, fr.total_t
    plate = _outline(p, z0, z1)
    plate = plate - _slab(sc.w, sc.h, sc.corner_r, 0, sc.bottom + sc.h / 2, z0 - _EPS, z1 + _EPS)
    if cam.notch:
        cam_top = p.lid.h - cam.top_offset
        plate = plate - Pos(0, cam_top - cam.h / 2, (z0 + z1) / 2) * Box(cam.w, cam.h, z1 - z0 + 2 * _EPS)
    for x, y in screw_positions(p):
        plate = plate - _cyl(x, y, s.screw_d, z0 - _EPS, z1 + _EPS)
        plate = plate - _cyl(x, y, s.counterbore_d, z1 - s.counterbore_depth, z1 + _EPS)
    return plate


def front_decor_face(p: Params) -> Sketch:
    """Bezel border area free for decoration, as a Sketch on the plane z=total_t."""
    fr, sc, cam, s = frame(p), p.screen, p.camera, p.fasteners
    k, e = DECOR_KEEPOUT, DECOR_EDGE_INSET
    with BuildSketch() as sk:
        with Locations((0, fr.yc)):
            RectangleRounded(fr.outer_w - 2 * e, fr.outer_h - 2 * e,
                             max(p.structure.outer_corner_r - e, 0.5))
        with Locations((0, sc.bottom + sc.h / 2)):
            RectangleRounded(sc.w + 2 * k, sc.h + 2 * k, sc.corner_r + k, mode=Mode.SUBTRACT)
        with Locations((0, p.lid.h - cam.top_offset - cam.h / 2)):
            Rectangle(cam.w + 2 * k, cam.h + 2 * k, mode=Mode.SUBTRACT)
        with Locations(*screw_positions(p)):
            Circle(s.counterbore_d / 2 + k, mode=Mode.SUBTRACT)
    return Pos(0, 0, fr.total_t) * sk.sketch


def rear_decor_face(p: Params) -> Sketch:
    """Back plate area free for decoration, as a Sketch on the plane z=0."""
    fr, e = frame(p), DECOR_EDGE_INSET
    with BuildSketch() as sk:
        with Locations((0, fr.yc)):
            RectangleRounded(fr.outer_w - 2 * e, fr.outer_h - 2 * e,
                             max(p.structure.outer_corner_r - e, 0.5))
    return sk.sketch


def print_location_front(p: Params) -> Location:
    """Inner face (z=front_z) on the bed, visible face up, centered in XY."""
    fr = frame(p)
    return Location((0, -fr.yc, -fr.front_z))


def print_location_rear(p: Params) -> Location:
    """Back face (z=0) on the bed, centered in XY."""
    return Location((0, -frame(p).yc, 0))
