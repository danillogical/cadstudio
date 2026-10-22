"""Fit-test coupons: the real top-left corner geometry cut out for a clearance x thickness sweep."""
from build123d import Align, Box, Cylinder, Location, Part, Plane, Pos, Rot, Text, extrude, BuildPart, BuildSketch

from projects.armor.params import Params, lid_envelope
from projects.armor.part import ArmorPart

from projects.armor.models._armor_base import frame, front_bezel, rear_shell

CLEARANCES = (0.4, 0.7, 1.0)
THICKNESSES = (6.5, 7.0, 7.5)
CORNER_SPAN_Y = 40.0   # coupon height below the lid top edge
INBOARD = 40.0         # coupon extent inboard of the lid's left edge
LABEL_DEPTH = 0.6
LABEL_SIZE = 4.0


def _deboss(shape: Part, text: str, plane: Plane, depth: float, size: float) -> Part:
    """Cut ``text`` into ``shape`` ``depth`` mm below ``plane`` (its normal points out of the part)."""
    with BuildPart() as bp:
        with BuildSketch(plane):
            Text(text, font_size=size)
        extrude(amount=-depth)
    return shape - bp.part


def _label(shape: Part, text: str, plane: Plane, depth: float, size: float, warnings: list) -> Part:
    try:
        return _deboss(shape, text, plane, depth, size)
    except Exception as exc:  # fonts may be unavailable; skip the label rather than crash
        warnings.append(f"label {text!r} skipped: {exc}")
        return shape


def coupon(p: Params, label: str) -> Part:
    """Top-left corner of the fused shell, cut by a box, with a label debossed on the side wall."""
    fr = frame(p)
    x0, x1 = -fr.outer_w / 2 - 1, -p.lid.w / 2 + INBOARD
    y0, y1 = p.lid.h - CORNER_SPAN_Y, fr.y1 + 1
    z1 = fr.total_t + 1
    box = Pos((x0 + x1) / 2, (y0 + y1) / 2, z1 / 2 - 0.5) * Box(x1 - x0, y1 - y0, z1 + 1)
    shape = (rear_shell(p) + front_bezel(p)) & box
    # Text runs along +Y with up = +Z, viewed from outside (-X); centered on the wall face.
    plane = Plane(origin=(-fr.outer_w / 2, (p.lid.h - CORNER_SPAN_Y + fr.y1) / 2 - 3,
                          (fr.back_th + fr.front_z) / 2),
                  x_dir=(0, -1, 0), z_dir=(-1, 0, 0))
    return _label(shape, label, plane, LABEL_DEPTH, LABEL_SIZE, _WARNINGS)


def _stand_on_y_cut(shape: Part) -> Location:
    """Pose with the lower Y-cut face on the bed (+Y up), centered in XY."""
    rot = Rot(X=90)
    bb = shape.moved(rot).bounding_box()
    return Pos(-(bb.min.X + bb.max.X) / 2, -(bb.min.Y + bb.max.Y) / 2, -bb.min.Z) * rot


def insert_test(p: Params) -> Part:
    """Block with three heat-set insert bores (insert_d -0.3, 0, +0.3), labeled."""
    fr, s = frame(p), p.fasteners
    h = fr.front_z - fr.back_th
    block = Box(30, 12, h, align=(Align.CENTER, Align.CENTER, Align.MIN))
    for dx, dd in ((-9, -0.3), (0, 0.0), (9, 0.3)):
        d = s.insert_d + dd
        block = block - Pos(dx, 0, h - s.insert_depth) * Cylinder(
            d / 2, s.insert_depth + 1, align=(Align.CENTER, Align.CENTER, Align.MIN))
    # Short one-glyph labels (-, 0, +  = insert_d offset sign) under each bore, on the -Y side
    # face, so the label never thins the walls around the bores.
    for dx, glyph in ((-9, "-"), (0, "0"), (9, "+")):
        plane = Plane(origin=(dx, -6, h / 2), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
        block = _label(block, glyph, plane, LABEL_DEPTH, 4.0, _WARNINGS)
    return block


_WARNINGS: list[str] = []


def build(p: Params) -> dict[str, ArmorPart]:
    _WARNINGS.clear()
    parts: dict[str, ArmorPart] = {}
    for c in CLEARANCES:
        for t in THICKNESSES:
            pp = p.override({"fit.slide_clearance": c, "lid.t": t})
            shape = coupon(pp, f"C{c:g} T{t:g}")
            name = f"c{round(c * 100):03d}_t{round(t * 10):02d}"
            parts[name] = ArmorPart(shape, _stand_on_y_cut(shape), lid_envelope=lid_envelope(pp))
    blk = insert_test(p)
    parts["insert_test"] = ArmorPart(blk, check_lid=False, check_screen=False)
    for w in _WARNINGS:
        print("WARNING:", w)
    return parts
