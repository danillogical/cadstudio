"""Industrial / military cyberdeck armor: segmented bezel plates, corner guards, hex nut guards, stencil text, knurled skin.

Front decoration is raised on the visible face (z >= total_t); the rear gets a full-coverage skin below the back plate
(z in [-SKIN_T, 0]) with shallow recesses cut from the bed side, so the original shell is never modified.
The skin stays full coverage so the whole rear back face is flat on the bed (no bridged back plate).

Every position is derived from ``frame(p)`` / ``p`` (outer extents, screen rect, decor face, screw positions), so the
same design adapts to any lid size. A feature that does not fit is shrunk to a floor, then dropped with a printed note.
The finished parts are checked with the 3MF mesher; a feature that makes the mesh invalid is reported and dropped.
"""
from __future__ import annotations

import math
import warnings
from dataclasses import dataclass

import numpy as np
from build123d import (
    Align, Axis, BuildSketch, Circle, FontStyle, Location, Locations, Mesher, Mode, Part, Polygon, Pos,
    Rectangle, RegularPolygon, Sketch, Text, chamfer, extrude,
)

from projects.armor.params import Params
from projects.armor.part import ArmorPart

from projects.armor.models._armor_base import (
    DECOR_EDGE_INSET, DECOR_KEEPOUT, _slab, frame, front_bezel, front_decor_face, print_location_front, rear_shell,
    screw_positions,
)

# ---------------------------------------------------------------- decoration constants (mm)
# Front plates
PLATE_H = 1.2             # raised armor plate layer on the bezel border
GROOVE_W = 1.0            # panel-line groove width, cut through the plate layer
MIN_SEG = 10.0            # a panel-line groove is dropped if it would leave a plate shorter than this
SIDE_GROOVE_FRACS = (0.352, 0.751)  # horizontal panel lines across the side borders, fraction of the shell height
TOP_GROOVE_FRACS = (0.145, 0.692)   # vertical panel lines across the top border, fraction of the half shell width
BOTTOM_GROOVE_FRAC = 0.335        # vertical panel lines across the bottom border, fraction of the half shell width
CORNER_SPLIT_GAP = 0.8            # side panel line sits this far above the bottom corner guard
CAM_PLATE_PAD = 4.0               # center top plate extends this far past the camera keepout (sensor cover plate)
# Corner guards (extra layer on top of the plates). Outlines are (u, v): inward from the shell side edge and from the
# top/bottom edge, drawn for the reference border sizes below and scaled to the actual border.
GUARD_H = 1.4
GUARD_TAPER = 40.0
GUARD_MIN_SCALE = 0.4             # guards are dropped when the border is thinner than this fraction of the reference
GUARD_REF_SIDE = 21.85            # reference side border width (shell edge to screen keepout)
GUARD_REF_TOP = 25.2              # reference top border height
GUARD_REF_BOT = 9.0               # reference bottom border height
GUARD_TOP_UV = ((0, 0), (71.1, 0), (61.1, 8), (41.1, 8), (33.1, 17), (16.1, 17), (13.1, 22), (13.1, 27), (0, 27))
GUARD_BOT_UV = ((0, 0), (29.1, 0), (21.1, 7), (13.1, 12), (13.1, 20), (18.1, 24), (0, 24))
GUARD_TOP_RUN_MAX = 0.45          # top guard runs at most this fraction of the shell width along the top edge
# Hex bolt guards around the counterbores (open toward the shell edge to keep every wall thick)
BOLT_RING_H = 2.8                 # total ring height above the bezel face
RING_IN_CLEAR = 2.4               # ring inner diameter is counterbore_d + this
BOLT_RING_R = 8.6                 # hexagon circumradius (vertices point along +/-X)
BOLT_RING_SHIFT = 2.4             # hexagon center offset inboard of the screw axis
BOLT_RING_OUT_REACH = 2.5         # arms are cut off this far outboard of the screw axis (blunt ends)
NUT_RING_H = 3.6                  # hex nut ring height above the bezel face (taller than the guard)
NUT_RING_WALL = 1.2               # hex ring wall (apothem minus inner radius)
NUT_EDGE_CLIP = 0.1               # ring is clipped this far inside the shell edge
# Raised block text on the plates (heavy font and low height keep the thin-wall share under the min_wall limit)
TEXT_H = 0.8
TEXT_FONT = "Arial Black"
TEXT_STYLE_BOLD = False
TEXT_PAD = 1.0                    # clear space between a label and the plate's studs / raised inner border
LABEL_TL = "VLT-03"
LABEL_TL_SIZE = 13.0
LABEL_TL_FLOOR = 7.0
LABEL_BR = "MOBILE TERMINAL"
LABEL_BR_SIZE = 4.2
LABEL_BR_FLOOR = 3.0
LABEL_BR_GAP = 8.0                # label stays this far from the rib strip
STENCIL_GAP = 1.0                 # stencil bridge gap cut through the VLT-03 glyphs at mid-height
# Hazard stripes and rib grooves (bottom bezel)
BOTTOM_MIN_H = 3.5                # bottom border strip features are dropped when the strip is thinner than this
HAZARD_INSET = (0.6, 0.4)         # hazard band inset from the bottom border strip edges (lower, upper)
HAZARD_X_FRACS = (1.0, 1.25)      # hazard band from the bottom guard edge to this multiple of the bottom groove x
HAZARD_PITCH = 10.0
HAZARD_BAR_W = 5.0
HAZARD_H = 0.8
HAZARD_MIN_AREA = 4.0             # clipped stripe fragments smaller than this (mm^2) are dropped
TICK_FRAC = 0.75                  # rib strip half length as a fraction of the bottom groove x
TICK_PITCH = 3.6                  # rib pitch; ribs are grooves so the plates between stay 2.8 mm wide
TICK_W = 0.8                      # rib groove width
# Plate studs and inner borders (large plates only)
STUD_R = 1.6                      # hex stud circumradius (3.2 mm across corners)
STUD_H = 0.8
STUD_INSET = 5.5                  # stud center distance from the plate edges
BORDER_INSET = 1.5                # raised inner border distance from the plate edge
BORDER_W = 1.2
BORDER_H = 0.8
BIG_PLATE_MIN = 40.0              # a plate counts as large if its long side is at least this
# Status LED window (raised bezel with three recessed windows), centered in the rib strip
LED_WIN = (4.0, 2.0)              # window size
LED_PITCH = 5.0                   # window center spacing
LED_BEZEL = 1.0                   # bezel border around the windows
LED_BEZEL_MIN = 0.8
LED_H = 0.8
LED_CLEAR_X = 10.0                # rib grooves are dropped inside |x| < this
# Rear skin
SKIN_T = 1.0
SKIN_CHAMFER = 0.6                # bed-side outer edge chamfer
REAR_RECESS_D = 0.6               # recess depth into the skin (leaves 0.4 mm floor)
REAR_LINE_W = 1.2                 # panel-line groove width (<= 6)
REAR_FRAME_INSET = 13.0           # panel-line frame inset from the shell outline
REAR_BRACKET_LEN = 26.0           # corner bracket arm length
REAR_BRACKET_INSET = 6.0
VENT_W = 5.0                      # vent slot width (<= 6, bridges cleanly)
VENT_LEN = 30.0
VENT_LEN_MIN = 14.0
VENT_PITCH = 11.0
VENT_COUNT = 5
VENT_LINE_GAP = 25.1              # vent bank outer edge sits this far inside the panel-line frame
VENT_TOP_CLEAR = 18.0             # vent frame top edge sits this far below the shell top
VENT_END_CUT = 1.5                # 45 deg chamfer on slot ends
VENT_X_MIN = 20.0                 # vent banks must stay at least this far from the center line
ID_PLATE_W = 70.0
ID_PLATE_H = 28.0
ID_PLATE_W_MIN = 40.0
ID_PLATE_H_MIN = 18.0
ID_PLATE_Y_FRAC = 0.2254          # plate center height as a fraction of the shell height above the bottom edge
ID_LINE_W = 4.0                   # recessed "text line" slot width
ID_LINE_LENS = (50.0, 38.0, 44.0)
ID_LINE_PITCH = 7.0
ID_CLEAR = 12.0                   # clear space between the ID plate and neighbouring panels / frame
KNURL_X_IN_FRAC = 0.614           # inner |x| of each knurl panel, fraction of the half shell width
KNURL_LINE_GAP = 14.1             # knurl panel outer edge sits this far inside the panel-line frame
KNURL_Y_FRACS = (0.178, 0.676)    # knurl panel y extent as fractions of the shell height above the bottom edge
KNURL_VENT_GAP = 11.0             # gap between the knurl panel and the vent frame above it
KNURL_MIN_W = 16.0                # knurl panels narrower or shorter than this are dropped
KNURL_MIN_H = 30.0
KNURL_PITCH = 4.3                 # nominal groove spacing along the diagonal intercept; tuned per panel by _knurl_params
KNURL_W = 1.0                     # diagonal groove width
KNURL_CORNER_MARGIN = 0.6         # target clearance (intercept units) between a panel corner and any groove edge
KNURL_MARGIN_OK = 0.25            # below this the panel falls back to an inset clip
KNURL_FALLBACK_INSET = 2.0        # fallback: grooves are clipped to the panel inset by this (> groove width)
VENT_FRAME_MARGIN = 5.0           # outline frame distance from the vent bank
VENT_FRAME_W = 1.6
VENT_FRAME_CHAMFER = 6.0
VENT_NOTCH = 3.0                  # square corner notch size
MESH_GUARD_TOL = 0.001            # linear deflection of the mesh validity guard (the exporter default)


def _note(msg: str) -> None:
    print(f"armor_industrial: note: {msg}")


# ---------------------------------------------------------------- 2D helpers (all at z=0, extruded then moved)

def _rect(cx: float, cy: float, w: float, h: float) -> Sketch:
    with BuildSketch() as s:
        with Locations((cx, cy)):
            Rectangle(w, h)
    return s.sketch


def _poly(pts) -> Sketch:
    pts = list(pts)
    area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))
    if area < 0:  # mirrored polygons wind clockwise; normalize to CCW
        pts.reverse()
    with BuildSketch() as s:
        Polygon(*pts, align=None)
    return s.sketch


def _bar(x0: float, y0: float, x1: float, y1: float, w: float) -> Sketch:
    """Rectangle of width ``w`` along the segment (x0,y0)-(x1,y1)."""
    dx, dy = x1 - x0, y1 - y0
    n = math.hypot(dx, dy)
    nx, ny = -dy / n * w / 2, dx / n * w / 2
    return _poly([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)])


def _union(shapes) -> Sketch | None:
    out = None
    for s in shapes:
        if s is None:
            continue
        out = s if out is None else out + s
    return out


def _and(a: Sketch | None, b: Sketch | None) -> Sketch | None:
    """Intersection of two sketches; None when either is None or the overlap is empty."""
    if a is None or b is None:
        return None
    hit = a & b
    return hit if hit is not None and hit.area > 1e-6 else None


def _lift(sk: Sketch, z0: float, h: float, taper: float = 0.0) -> Part:
    return Pos(0, 0, z0) * extrude(sk, amount=h, taper=taper)


def _prism(sk: Sketch, z0: float, z1: float) -> Part:
    return _lift(sk, z0, z1 - z0)


def _oct(x0: float, x1: float, y0: float, y1: float, c: float) -> Sketch:
    """Rectangle with 45 degree chamfered corners (leg ``c``)."""
    return _poly([(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c), (x1 - c, y1), (x0 + c, y1), (x0, y1 - c),
                  (x0, y0 + c)])


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ---------------------------------------------------------------- mesh validity guard

def _mesh_ok(shape) -> bool:
    """True if the 3MF mesher accepts the shape (the exporter raises 'mesh is invalid' otherwise)."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            Mesher().add_shape(shape, linear_deflection=MESH_GUARD_TOL)
    except RuntimeError:
        return False
    return True


def _fuse_features(part: str, base: Part, features, apply) -> Part:
    """Apply every feature to ``base`` and validate the mesh; on failure name and drop the feature that breaks it.

    ``features`` is a list of (name, payload) and ``apply(shape, payload)`` adds or cuts one feature. A payload that
    is a list holds alternatives tried in order (e.g. knurl variants).
    """
    features = [(n, [a for a in (pl if isinstance(pl, list) else [pl]) if a is not None]) for n, pl in features]
    features = [(n, pl) for n, pl in features if pl]
    shape = base
    for _, alts in features:
        shape = apply(shape, alts[0])
    if _mesh_ok(shape):
        return shape
    shape = base
    for name, alts in features:
        for i, alt in enumerate(alts):
            cand = apply(shape, alt)
            if _mesh_ok(cand):
                shape = cand
                if i:
                    _note(f"{part}: '{name}' mesh invalid, used fallback variant {i}")
                break
            _note(f"{part}: '{name}' made the 3MF mesh invalid"
                  + ("; trying fallback" if i + 1 < len(alts) else "; dropped"))
    if not _mesh_ok(shape):
        raise RuntimeError(f"armor_industrial {part}: 3MF mesh invalid although every feature validates alone")
    return shape


# ---------------------------------------------------------------- front layout

@dataclass(frozen=True)
class _FL:
    """Front border regions derived from the frame, the screen keepout and the decor face."""
    hx: float          # half outer width
    y0: float
    y1: float
    yc: float
    ow: float          # outer width
    oh: float          # outer height
    face_x: float      # decor face half width
    face_y0: float
    face_y1: float
    sc_hw: float       # screen keepout half width
    sc_y0: float       # screen keepout bottom
    sc_y1: float       # screen keepout top
    cam_hw: float      # camera keepout half width
    su: float          # corner guard scale across the side border
    svt: float         # corner guard scale across the top border
    svb: float         # corner guard scale across the bottom border

    @property
    def bot_h(self) -> float:
        return self.sc_y0 - self.face_y0

    @property
    def top_h(self) -> float:
        return self.face_y1 - self.sc_y1


def _front_layout(p: Params) -> _FL:
    fr, sc, cam = frame(p), p.screen, p.camera
    k, e = DECOR_KEEPOUT, DECOR_EDGE_INSET
    hx = fr.outer_w / 2
    sc_hw, sc_y0, sc_y1 = sc.w / 2 + k, sc.bottom - k, sc.bottom + sc.h + k
    return _FL(
        hx=hx, y0=fr.y0, y1=fr.y1, yc=fr.yc, ow=fr.outer_w, oh=fr.outer_h,
        face_x=hx - e, face_y0=fr.y0 + e, face_y1=fr.y1 - e,
        sc_hw=sc_hw, sc_y0=sc_y0, sc_y1=sc_y1, cam_hw=cam.w / 2 + k,
        su=(hx - sc_hw) / GUARD_REF_SIDE, svt=(fr.y1 - sc_y1) / GUARD_REF_TOP, svb=(sc_y0 - fr.y0) / GUARD_REF_BOT,
    )


def _text_size_fit(txt: str, size: float, floor: float, avail_w: float, avail_h: float):
    """Largest font size in [floor, size] whose label fits the box, or None."""
    with BuildSketch() as s:
        Text(txt, 10.0, align=(Align.MIN, Align.CENTER), font=TEXT_FONT)
    bb = s.sketch.bounding_box()
    w10, h10 = bb.size.X, bb.size.Y
    sz = size
    while sz >= floor - 1e-9:
        if w10 * sz / 10 <= avail_w and h10 * sz / 10 <= avail_h:
            return sz
        sz -= 0.5
    return None


def _text2d(txt: str, size: float, x: float, y: float, right: bool, stencil: bool) -> Sketch:
    kw = {"font": TEXT_FONT}
    if TEXT_STYLE_BOLD:
        kw["font_style"] = FontStyle.BOLD
    with BuildSketch() as s:
        with Locations((x, y)):
            Text(txt, size, align=(Align.MAX if right else Align.MIN, Align.CENTER), **kw)
    sk = s.sketch
    if not stencil or STENCIL_GAP <= 0:
        return sk
    bb = sk.bounding_box()
    # Stencil bridge: a thin horizontal gap through the middle of the glyphs.
    gap = _rect((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, bb.size.X + 2, STENCIL_GAP)
    return sk - gap


def _place_text(txt, size, floor, stencil, xs, y, avail_w, avail_h, avoid, right=False):
    """Fit a label into the box (shrinking to ``floor``) and keep it off ``avoid``; None if it cannot be placed.

    ``xs`` is the x anchor: the centre of the box when ``right`` is False, the right end when True.
    """
    sz = _text_size_fit(txt, size, floor, avail_w, avail_h)
    while sz is not None:
        if right:
            sk = _text2d(txt, sz, xs, y, True, stencil)
        else:
            with BuildSketch() as s:
                Text(txt, sz, align=(Align.MIN, Align.CENTER), font=TEXT_FONT)
            w = s.sketch.bounding_box().size.X
            sk = _text2d(txt, sz, xs - w / 2, y, False, stencil)
        if avoid is None or _and(sk, avoid) is None:
            return sk
        sz -= 0.5
        if sz < floor - 1e-9:
            return None
    return None


# ---------------------------------------------------------------- front bezel

def _hazard_stripes(x0: float, x1: float, y0: float, y1: float) -> Sketch | None:
    clip = _rect((x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0)
    h = y1 - y0
    bars, x = [], x0 - h
    while x < x1:
        bars.append(_bar(x, y0 - 1, x + h + 2, y1 + 1, HAZARD_BAR_W))
        x += HAZARD_PITCH
    # Fragments of a bar clipped to a sliver at the band ends are dropped.
    return _union([f for f in (_union(bars) & clip).faces() if f.area >= HAZARD_MIN_AREA])


def _ticks(half: float, yc: float, h: float) -> Sketch | None:
    """Full-height rib grooves across the bottom bezel, centered on x=0 (plates between ribs stay >= 2.3 mm wide)."""
    n = int(2 * half / TICK_PITCH + 1e-6)
    xs = [(i - n / 2) * TICK_PITCH for i in range(n + 1)]
    return _union([_rect(x, yc, TICK_W, h) for x in xs if abs(x) >= LED_CLEAR_X])


def _corner_guards(L: _FL) -> Sketch | None:
    """Angular brackets wrapping the four corners, scaled to the actual border sizes."""
    if min(L.su, L.svt, L.svb) < GUARD_MIN_SCALE:
        _note("corner guards dropped: bezel border too thin")
        return None
    su_top = min(L.su, GUARD_TOP_RUN_MAX * L.ow / GUARD_TOP_UV[1][0])
    polys = []
    for sx in (-1, 1):
        polys.append(_poly([(sx * (L.hx - u * su_top), L.y1 - v * L.svt) for u, v in GUARD_TOP_UV]))
        polys.append(_poly([(sx * (L.hx - u * L.su), L.y0 + v * L.svb) for u, v in GUARD_BOT_UV]))
    return _union(polys)


def _hex_ring2d(p: Params, x: float, y: float) -> Sketch:
    """Hex bolt guard: a hexagon shifted inboard of the screw axis, clipped at the shell edge, with the
    counterbore clearance hole and a slot opening toward the edge so every wall stays thick."""
    out = 1 if x > 0 else -1
    in_d = p.fasteners.counterbore_d + RING_IN_CLEAR
    with BuildSketch() as s:
        with Locations((x - out * BOLT_RING_SHIFT, y)):
            RegularPolygon(BOLT_RING_R, 6, rotation=0)
        with Locations((x + out * (BOLT_RING_OUT_REACH + 10.0), y)):
            Rectangle(20.0, 40.0, mode=Mode.SUBTRACT)  # clip beyond the edge reach
        with Locations((x, y)):
            Circle(in_d / 2, mode=Mode.SUBTRACT)
        with Locations((x + out * 4.0, y)):
            Rectangle(8.0, in_d, mode=Mode.SUBTRACT)
    return s.sketch


def _nut_ring2d(p: Params, x: float, y: float) -> Sketch:
    """Hex nut ring centered on the screw axis (flats facing +/-X), clipped just inside the shell edge."""
    fr = frame(p)
    in_d = p.fasteners.counterbore_d + RING_IN_CLEAR
    r_out = (in_d / 2 + NUT_RING_WALL) / math.cos(math.radians(30))
    with BuildSketch() as s:
        with Locations((x, y)):
            RegularPolygon(r_out, 6, rotation=30)
            Circle(in_d / 2, mode=Mode.SUBTRACT)
    edge = fr.outer_w / 2 - NUT_EDGE_CLIP
    return s.sketch & _rect(0, fr.yc, 2 * edge, fr.outer_h)


def _trim_rect(r, obstacles, margin: float):
    """Shrink rect (x0, x1, y0, y1) so it clears every obstacle rect, keeping the largest remaining area."""
    for ox0, ox1, oy0, oy1 in obstacles:
        x0, x1, y0, y1 = r
        ox0, ox1, oy0, oy1 = ox0 - margin, ox1 + margin, oy0 - margin, oy1 + margin
        if x0 >= ox1 or x1 <= ox0 or y0 >= oy1 or y1 <= oy0:
            continue
        opts = [(x0, min(x1, ox0), y0, y1), (max(x0, ox1), x1, y0, y1), (x0, x1, y0, min(y1, oy0)), (x0, x1, max(y0, oy1), y1)]
        r = max(opts, key=lambda o: max(o[1] - o[0], 0) * max(o[3] - o[2], 0))
    return r


def _plate_studs_borders(p: Params, plate2d: Sketch, guards2d: Sketch | None) -> tuple[Sketch | None, Sketch | None]:
    """Hex studs at the corners and a raised inner border on every large rectangular plate.

    A plate's decorated rectangle is trimmed to clear the corner guards it overlaps; the border may run under
    a bolt guard (the guard is taller), but studs that would touch a bolt guard are dropped.
    """
    rg = BOLT_RING_R + BOLT_RING_SHIFT
    studs, borders = [], []
    for f in plate2d.faces():
        bb = f.bounding_box()
        if max(bb.size.X, bb.size.Y) < BIG_PLATE_MIN or f.area < 0.9 * bb.size.X * bb.size.Y:
            continue
        hit = None if guards2d is None else _and(
            guards2d, _rect((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, bb.size.X + 2, bb.size.Y + 2))
        obstacles = []
        if hit is not None:
            obstacles = [(g.bounding_box().min.X, g.bounding_box().max.X, g.bounding_box().min.Y, g.bounding_box().max.Y)
                         for g in hit.faces()]
        x0, x1, y0, y1 = _trim_rect((bb.min.X, bb.max.X, bb.min.Y, bb.max.Y), obstacles, 1.0)
        w, h = x1 - x0, y1 - y0
        if max(w, h) < BIG_PLATE_MIN or min(w, h) < 2 * STUD_INSET:
            continue
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        a, b = BORDER_INSET, BORDER_INSET + BORDER_W
        borders.append(_rect(cx, cy, w - 2 * a, h - 2 * a) - _rect(cx, cy, w - 2 * b, h - 2 * b))
        for sx in (-1, 1):
            for sy in (-1, 1):
                px, py = cx + sx * (w / 2 - STUD_INSET), cy + sy * (h / 2 - STUD_INSET)
                if any(abs(px - bx) < rg + STUD_R and abs(py - by) < rg + STUD_R for bx, by in screw_positions(p)):
                    continue
                with BuildSketch() as st:
                    with Locations((px, py)):
                        RegularPolygon(STUD_R, 6)
                studs.append(st.sketch)
    return _union(studs), _union(borders)


def _led_window2d(cy: float, bezel: float) -> Sketch:
    n = 3
    w, h = LED_WIN
    fw, fh = (n - 1) * LED_PITCH + w + 2 * bezel, h + 2 * bezel
    frame2d = _rect(0.0, cy, fw, fh)
    wins = [_rect((i - (n - 1) / 2) * LED_PITCH, cy, w, h) for i in range(n)]
    return frame2d - _union(wins)


def _groove_xs(fracs, hx, first_min: float, limit: float) -> list[float]:
    """Positive panel-line x positions: ``fracs`` of the half width, spaced >= MIN_SEG apart and inside ``limit``."""
    xs, prev = [], 0.0
    for i, f in enumerate(fracs):
        x = f * hx
        if i == 0:
            x = max(x, first_min)
        if x - prev < MIN_SEG or x > limit - MIN_SEG:
            _note(f"top/bottom panel line at x={x:.1f} dropped: plate would be under {MIN_SEG:.0f} mm")
            continue
        xs.append(x)
        prev = x
    return xs


def _front_features(p: Params):
    """Return (plate base part, [(name, sketch, z0, height, taper)]) for the front decoration."""
    fr, L = frame(p), _front_layout(p)
    zt = fr.total_t
    cam, k = p.camera, DECOR_KEEPOUT
    face = Pos(0, 0, -zt) * front_decor_face(p)
    hx = L.hx

    # The camera is covered (no notch): the top plates run across it as a sensor cover plate.
    if not cam.notch:
        cy = p.lid.h - cam.top_offset - cam.h / 2
        cover = _and(_rect(0, cy, cam.w + 2 * k, cam.h + 2 * k),
                     _rect(0, (L.face_y0 + L.face_y1) / 2, 2 * L.face_x, L.face_y1 - L.face_y0))
        if cover is not None:
            screen_keepout = _rect(0, (L.sc_y0 + L.sc_y1) / 2, 2 * L.sc_hw, L.sc_y1 - L.sc_y0)
            cover = cover - screen_keepout
            face = face + cover

    # ---- panel-line grooves split the plate layer into segments
    cuts = []
    corner_split = L.y0 + 24.0 * L.svb + CORNER_SPLIT_GAP
    side_ys, prev = [], L.face_y0
    for y in (corner_split, *(L.y0 + f * L.oh for f in SIDE_GROOVE_FRACS)):
        if y - prev < MIN_SEG or L.face_y1 - y < MIN_SEG:
            _note(f"side panel line at y={y:.1f} dropped: plate would be under {MIN_SEG:.0f} mm")
            continue
        side_ys.append(y)
        prev = y
    gx0, gx1 = L.sc_hw - 0.5, hx + 1.0
    for y in side_ys:
        cuts += [_rect(sx * (gx0 + gx1) / 2, y, gx1 - gx0, GROOVE_W) for sx in (-1, 1)]
    # Top: the first line clears the camera keepout so the sensor cover plate is a plate of its own.
    first_min = (L.cam_hw + CAM_PLATE_PAD) if not cam.notch else 0.0
    top_xs = _groove_xs(TOP_GROOVE_FRACS, hx, first_min, L.face_x)
    for x in top_xs:
        for sx in (-1, 1):
            cuts.append(_rect(sx * x, (L.sc_y1 - 0.5 + L.y1 + 1) / 2, GROOVE_W, L.y1 + 1 - L.sc_y1 + 0.5))
    bot_gx = BOTTOM_GROOVE_FRAC * hx
    bot_ok = L.bot_h >= BOTTOM_MIN_H
    if bot_ok:
        for sx in (-1, 1):
            cuts.append(_rect(sx * bot_gx, (L.y0 - 1 + L.sc_y0 + 0.5) / 2, GROOVE_W, L.sc_y0 + 1.5 - L.y0))
    else:
        _note("bottom border too thin: bottom panel lines, rib strip, hazard stripes, LED and label dropped")
    hz_y0, hz_y1 = L.face_y0 + HAZARD_INSET[0], L.sc_y0 - HAZARD_INSET[1]
    hz_yc = (hz_y0 + hz_y1) / 2
    tick_half = TICK_FRAC * bot_gx
    if bot_ok:
        cuts.append(_ticks(tick_half, hz_yc, hz_y1 - hz_y0 + 2.0))
    # Remove the plate sliver between the screen keepout and the camera keepout when there is a camera notch.
    if cam.notch:
        gap_lo, gap_hi = L.sc_y1, p.lid.h - cam.top_offset - cam.h - k
        if gap_hi - gap_lo > 0:
            cuts.append(_rect(0, (gap_lo + gap_hi) / 2, cam.w + 2 * k, gap_hi - gap_lo + 0.4))
    plate2d = face - _union(cuts)
    base = _lift(plate2d, zt, PLATE_H)
    feats: list = []

    # ---- corner guards on top of the plates (0.05 mm overlap keeps the tapered fuse watertight)
    guards2d = _and(_corner_guards(L), face)
    if guards2d is not None:
        feats.append(("corner guards", guards2d, zt + PLATE_H - 0.05, GUARD_H + 0.05, GUARD_TAPER))

    # ---- studs and a raised inner border on the large plates (kept off the corner guards)
    studs2d, borders2d = _plate_studs_borders(p, plate2d, guards2d)
    if studs2d is not None:
        feats.append(("plate studs", studs2d, zt + PLATE_H - 0.05, STUD_H + 0.05, 0.0))
    if borders2d is not None:
        feats.append(("plate borders", borders2d, zt + PLATE_H - 0.05, BORDER_H + 0.05, 0.0))

    if bot_ok:
        # ---- status LED window: raised bezel whose windows are open down to the plate top
        w_led = (3 - 1) * LED_PITCH + LED_WIN[0]
        bezel = min(LED_BEZEL, (hz_y1 - hz_y0 - LED_WIN[1]) / 2)
        if bezel >= LED_BEZEL_MIN and w_led + 2 * bezel < 2 * LED_CLEAR_X:
            feats.append(("LED window", _and(_led_window2d(hz_yc, bezel), face), zt + PLATE_H - 0.05, LED_H + 0.05, 0.0))
        else:
            _note("LED window dropped: rib strip too thin")
        # ---- hazard stripes (raised on the bottom plate), from the bottom guard edge toward the center
        guard_x = hx - GUARD_BOT_UV[1][0] * L.su
        hx0, hx1 = -guard_x, -HAZARD_X_FRACS[1] * bot_gx
        if hx1 - hx0 >= HAZARD_PITCH and hz_y1 - hz_y0 >= 2.0:
            feats.append(("hazard stripes", _and(_hazard_stripes(hx0, hx1, hz_y0, hz_y1), face), zt + PLATE_H, HAZARD_H, 0.0))
        else:
            _note("hazard stripes dropped: bottom strip too small")
        # ---- bottom-right label between the rib strip and the guard
        avail_w = guard_x - (tick_half + LABEL_BR_GAP)
        br = _place_text(LABEL_BR, LABEL_BR_SIZE, LABEL_BR_FLOOR, False, guard_x, (L.face_y0 + L.sc_y0) / 2,
                         avail_w, L.bot_h - 2.0, guards2d, right=True)
        if br is None:
            _note(f"'{LABEL_BR}' label dropped: no room")
        else:
            feats.append(("MOBILE TERMINAL label", _and(br, face), zt + PLATE_H - 0.1, TEXT_H + 0.1, 0.0))

    # ---- top-left stencil label centered on the plate between the top panel lines, inside its raised border
    if top_xs:
        xa = top_xs[0] + GROOVE_W / 2
        xb = (top_xs[1] if len(top_xs) > 1 else L.face_x) - GROOVE_W / 2
        if guards2d is not None:  # the plate's decorated rectangle is trimmed 1 mm short of the top guard
            xb = min(xb, L.hx - GUARD_TOP_UV[1][0] * min(L.su, GUARD_TOP_RUN_MAX * L.ow / GUARD_TOP_UV[1][0]) - 1.0)
        pad_w = 2 * (STUD_INSET + STUD_R + TEXT_PAD)  # between the corner studs of the plate
        pad_h = 2 * (BORDER_INSET + BORDER_W + TEXT_PAD)  # inside the raised border
        tl = _place_text(LABEL_TL, LABEL_TL_SIZE, LABEL_TL_FLOOR, True, -(xa + xb) / 2, (L.sc_y1 + L.face_y1) / 2,
                         xb - xa - pad_w, L.top_h - pad_h, guards2d)
    else:
        tl = None
    if tl is None:
        _note(f"'{LABEL_TL}' label dropped: no room")
    else:
        feats.append(("VLT-03 label", _and(tl, face), zt + PLATE_H - 0.1, TEXT_H + 0.1, 0.0))

    # ---- hex bolt-head rings (nut rings are taller than the bolt guards)
    sp = screw_positions(p)
    feats.append(("bolt guards", _union([_hex_ring2d(p, x, y) for x, y in sp]), zt, BOLT_RING_H, 0.0))
    feats.append(("nut rings", _union([_nut_ring2d(p, x, y) for x, y in sp]), zt, NUT_RING_H, 0.0))
    return base, [f for f in feats if f[1] is not None]


def _front(p: Params) -> Part:
    base, feats = _front_features(p)
    bezel = front_bezel(p)

    def apply(shape, f):
        _, sk, z0, h, taper = f
        return shape + _lift(sk, z0, h, taper)

    return _fuse_features("front", bezel + base, [(f[0], f) for f in feats], apply)


# ---------------------------------------------------------------- rear layout

@dataclass(frozen=True)
class _RL:
    """Rear panel layout derived from the frame."""
    hx: float
    y0: float
    y1: float
    yc: float
    line_lines: bool                                    # panel-line frame between the corner brackets
    vents: tuple | None                                 # (x0, y_bottom, count, length)
    knurl: tuple | None                                 # (xa, xb, ya, yb), positive-x panel (mirrored)
    idp: tuple | None                                   # (cy, w, h)


def _rear_layout(p: Params) -> _RL:
    fr = frame(p)
    hx, y0, y1, H = fr.outer_w / 2, fr.y0, fr.y1, fr.outer_h
    line_x = hx - REAR_FRAME_INSET
    m = VENT_FRAME_MARGIN
    lines = (fr.outer_w - 2 * REAR_FRAME_INSET - 2 * (REAR_BRACKET_LEN + 14) > 4.0
             and H - 2 * REAR_FRAME_INSET - 2 * (REAR_BRACKET_LEN + 14) > 4.0)
    if not lines:
        _note("rear panel-line frame dropped: shell too small between the corner brackets")

    # knurl panels: x from the inner fraction to the frame, y from fractions of the height
    kx0, kx1 = KNURL_X_IN_FRAC * hx, line_x - KNURL_LINE_GAP
    ky0 = max(y0 + KNURL_Y_FRACS[0] * H, y0 + REAR_FRAME_INSET + 12.0)
    ky1 = y0 + KNURL_Y_FRACS[1] * H

    # vent banks: columns shrink until the bank clears the center; slot length shrinks until the knurl fits
    bank_w = lambda n: (n - 1) * VENT_PITCH + VENT_W
    vx_out = line_x - VENT_LINE_GAP
    n = VENT_COUNT
    while n >= 2 and vx_out - bank_w(n) < VENT_X_MIN + m:
        n -= 1
    vents, length = None, VENT_LEN
    if n >= 2:
        top = y1 - VENT_TOP_CLEAR - m
        while True:
            fb = top - length - m  # vent frame bottom edge
            knurl_h = min(ky1, fb - KNURL_VENT_GAP) - ky0
            if knurl_h >= KNURL_MIN_H or length - 2.0 < VENT_LEN_MIN:
                break
            length -= 2.0
        if fb > y0 + REAR_FRAME_INSET + 10.0:
            vents = (vx_out - bank_w(n), top - length, n, length)
            ky1 = min(ky1, fb - KNURL_VENT_GAP)
            if n < VENT_COUNT or length < VENT_LEN:
                _note(f"vent banks shrunk to {n} slots of {length:.0f} mm")
    if vents is None:
        _note("vent banks dropped: no room")
    knurl = (kx0, kx1, ky0, ky1) if (kx1 - kx0 >= KNURL_MIN_W and ky1 - ky0 >= KNURL_MIN_H) else None
    if knurl is None:
        _note("knurl panels dropped: no room")

    # ID plate: centered, shrinks to a floor, dropped if it cannot clear the panels and the frame
    ow = ID_PLATE_W
    clear_x = (kx0 - REAR_LINE_W - 1.5 - ID_CLEAR) if knurl else line_x - ID_CLEAR
    ow = min(ow, 2 * clear_x)
    cy = y0 + ID_PLATE_Y_FRAC * H
    avail_h = (y1 - REAR_FRAME_INSET - ID_CLEAR) - (y0 + REAR_FRAME_INSET + ID_CLEAR)
    oh = min(ID_PLATE_H, avail_h, ow * ID_PLATE_H / ID_PLATE_W)
    idp = None
    if ow >= ID_PLATE_W_MIN and oh >= ID_PLATE_H_MIN:
        cy = max(cy, y0 + REAR_FRAME_INSET + ID_CLEAR + oh / 2)
        idp = (cy, ow, oh)
        if ow < ID_PLATE_W:
            _note(f"ID plate shrunk to {ow:.0f} x {oh:.0f} mm")
    else:
        _note("ID plate dropped: no room")
    return _RL(hx=hx, y0=y0, y1=y1, yc=fr.yc, line_lines=lines, vents=vents, knurl=knurl, idp=idp)


# ---------------------------------------------------------------- knurl

def _knurl_params(xa: float, xb: float, ya: float, yb: float, pitch0: float = KNURL_PITCH, w: float = KNURL_W):
    """Pick (pitch, phase+, phase-, margin) so no groove touches a panel corner.

    Grooves are diagonal bands y = +/-x + c with centres c = phase + i * pitch and width ``g`` in intercept units.
    A corner's intercept must stay at least ``margin`` outside every band; pitch and the two phases are searched.
    """
    g = w * math.sqrt(2)
    cp = np.array([ya - xa, ya - xb, yb - xa, yb - xb])  # y = x + c through each corner
    cm = np.array([ya + xa, ya + xb, yb + xa, yb + xb])  # y = -x + c through each corner

    def best_phase(c, pitch):
        ph = np.linspace(0.0, pitch, 64, endpoint=False)
        r = np.mod(c[None, :] - ph[:, None], pitch)
        dist = np.minimum(r, pitch - r) - g / 2  # clearance outside the nearest band (negative = inside)
        m = dist.min(axis=1)
        i = int(np.argmax(m))
        return float(m[i]), float(ph[i])

    best = None
    for pitch in np.linspace(0.8 * pitch0, 1.25 * pitch0, 91):
        mp, php = best_phase(cp, pitch)
        mm, phm = best_phase(cm, pitch)
        margin = min(mp, mm)
        score = (min(margin, KNURL_CORNER_MARGIN), -abs(pitch - pitch0))
        if best is None or score > best[0]:
            best = (score, (float(pitch), php, phm, margin))
    return best[1]


def _clip_convex(poly, xa, xb, ya, yb):
    """Sutherland-Hodgman clip of a polygon against the axis-aligned rectangle."""
    def clip(pts, inside, cut):
        out = []
        for i, cur in enumerate(pts):
            prev = pts[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(cut(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cut(prev, cur))
        return out

    def at_x(x):
        return lambda a, b: (x, a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]))

    def at_y(y):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]), y)

    pts = list(poly)
    for inside, cut in ((lambda q: q[0] >= xa, at_x(xa)), (lambda q: q[0] <= xb, at_x(xb)),
                        (lambda q: q[1] >= ya, at_y(ya)), (lambda q: q[1] <= yb, at_y(yb))):
        if not pts:
            break
        pts = clip(pts, inside, cut)
    return pts


def _knurl_polys(xa, xb, ya, yb, inset: float = 0.0):
    """Clipped groove polygons for the panel (xa..xb, ya..yb); grooves stay inside the panel inset by ``inset``."""
    xa, xb, ya, yb = xa + inset, xb - inset, ya + inset, yb - inset
    pitch, ph_p, ph_m, margin = _knurl_params(xa, xb, ya, yb)
    if inset == 0.0 and margin < KNURL_MARGIN_OK:
        _note(f"knurl panel {xb - xa:.1f} x {yb - ya:.1f}: best corner clearance {margin:.2f} is small")
    g = KNURL_W * math.sqrt(2)
    X0, X1 = xa - 1.0, xb + 1.0
    by_dir = []
    for d, ph in ((1, ph_p), (-1, ph_m)):
        polys = []
        lo = (ya - xb if d > 0 else ya + xa) - g
        hi = (yb - xa if d > 0 else yb + xb) + g
        for i in range(math.ceil((lo - ph) / pitch), math.floor((hi - ph) / pitch) + 1):
            c = ph + i * pitch
            f0, f1 = (lambda x: x + c), (lambda x: -x + c)
            f = f0 if d > 0 else f1
            quad = [(X0, f(X0) - g / 2), (X1, f(X1) - g / 2), (X1, f(X1) + g / 2), (X0, f(X0) + g / 2)]
            pts = _clip_convex(quad, xa, xb, ya, yb)
            if len(pts) >= 3 and abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))) > 0.1:
                polys.append(pts)
        by_dir.append(polys)
    return by_dir


def _knurl_sketches(rect, inset: float = 0.0) -> tuple[Sketch, ...]:
    """Groove sketches for both (mirrored) knurl panels: one per diagonal direction, each a disjoint bar set.

    The directions are cut one after the other; fusing both into one sketch gives one huge groove-floor face that
    the mesher can leave with a hole, so the floor is kept as many small faces instead.
    """
    xa, xb, ya, yb = rect
    out = []
    for polys in _knurl_polys(xa, xb, ya, yb, inset):
        sk = _union([_poly([(sx * x, y) for x, y in pts]) for sx in (-1, 1) for pts in polys])
        if sk is not None:
            out.append(sk)
    return tuple(out) or None


# ---------------------------------------------------------------- rear shell

def _skin_features(p: Params):
    """List of (name, payload) rear recess features; a payload is a 2D sketch or a list of alternatives."""
    fr, R = frame(p), _rear_layout(p)
    hw, hh = fr.outer_w / 2, fr.outer_h / 2
    feats = []

    # Panel-line frame, broken at the corners where the corner brackets sit.
    fw, fh = fr.outer_w - 2 * REAR_FRAME_INSET, fr.outer_h - 2 * REAR_FRAME_INSET
    gap = REAR_BRACKET_LEN + 14
    cuts = []
    if R.line_lines:
        for sy in (-1, 1):  # horizontal lines
            cuts.append(_rect(0, fr.yc + sy * fh / 2, fw - 2 * gap, REAR_LINE_W))
        for sx in (-1, 1):  # vertical lines
            cuts.append(_rect(sx * fw / 2, fr.yc, REAR_LINE_W, fh - 2 * gap))
    feats.append(("panel-line frame", _union(cuts)))
    # Corner brackets (L-shaped grooves) with a diagonal link toward the frame.
    cuts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = sx * (hw - REAR_BRACKET_INSET), fr.yc + sy * (hh - REAR_BRACKET_INSET)
            cuts.append(_rect(cx - sx * REAR_BRACKET_LEN / 2, cy, REAR_BRACKET_LEN, REAR_LINE_W))
            cuts.append(_rect(cx, cy - sy * REAR_BRACKET_LEN / 2, REAR_LINE_W, REAR_BRACKET_LEN))
            dx, dy = sx * (hw - REAR_FRAME_INSET), fr.yc + sy * (hh - REAR_FRAME_INSET)
            cuts.append(_bar(cx, cy, dx, dy, REAR_LINE_W))
    feats.append(("corner brackets", _union(cuts)))

    if R.vents is not None:
        vx0, vy0, n, vlen = R.vents
        c = VENT_END_CUT
        cuts = []
        for sx in (-1, 1):
            for i in range(n):
                xa, xb = vx0 + i * VENT_PITCH, vx0 + i * VENT_PITCH + VENT_W
                pts = [(xa, vy0 + c), (xa + c, vy0), (xb - c, vy0), (xb, vy0 + c),
                       (xb, vy0 + vlen - c), (xb - c, vy0 + vlen), (xa + c, vy0 + vlen), (xa, vy0 + vlen - c)]
                cuts.append(_poly([(sx * x, y) for x, y in pts]))
        feats.append(("vent slots", _union(cuts)))
        # Outline frame around each vent bank: chamfered ring plus square corner notches.
        m, c, w = VENT_FRAME_MARGIN, VENT_FRAME_CHAMFER, VENT_FRAME_W
        bx0, bx1 = vx0 - m, vx0 + (n - 1) * VENT_PITCH + VENT_W + m
        by0, by1 = vy0 - m, vy0 + vlen + m
        ci = c - w * (2 - math.sqrt(2))
        cuts = []
        for sx in (-1, 1):
            xa, xb = sorted((sx * bx0, sx * bx1))
            cuts.append(_oct(xa, xb, by0, by1, c) - _oct(xa + w, xb - w, by0 + w, by1 - w, ci))
            for cx in (xa, xb):
                for cy in (by0, by1):
                    cuts.append(_rect(cx, cy, VENT_NOTCH, VENT_NOTCH))
        feats.append(("vent frames", _union(cuts)))

    if R.idp is not None:
        # ID plate: outline groove plus recessed text-line slots.
        py, w, h = R.idp
        s = w / ID_PLATE_W
        cuts = [_rect(0, py + h / 2, w, REAR_LINE_W), _rect(0, py - h / 2, w, REAR_LINE_W),
                _rect(-w / 2, py, REAR_LINE_W, h + REAR_LINE_W), _rect(w / 2, py, REAR_LINE_W, h + REAR_LINE_W)]
        pitch = ID_LINE_PITCH * min(1.0, h / ID_PLATE_H)
        for i, ln in enumerate(ID_LINE_LENS):
            ln *= s
            cuts.append(_rect(-w / 2 + 6 * s + ln / 2, py + (1 - i) * pitch, ln, ID_LINE_W))
        feats.append(("ID plate", _union(cuts)))

    if R.knurl is not None:
        xa, xb, ya, yb = R.knurl
        # Bordered zones; the grooves are separate alternatives (tuned clip first, inset clip as the fallback).
        cuts = []
        for sx in (-1, 1):
            lx0, lx1 = sorted((sx * xa, sx * xb))
            cx, cy = (lx0 + lx1) / 2, (ya + yb) / 2
            pw, ph = lx1 - lx0 + 2 * (REAR_LINE_W + 1.5), yb - ya + 2 * (REAR_LINE_W + 1.5)
            cuts.append(_rect(cx, cy, pw, ph) - _rect(cx, cy, pw - 2 * REAR_LINE_W, ph - 2 * REAR_LINE_W))
        feats.append(("knurl borders", _union(cuts)))
        feats.append(("knurl grooves", [_knurl_sketches(R.knurl), _knurl_sketches(R.knurl, KNURL_FALLBACK_INSET)]))
    return [f for f in feats if f[1] is not None]


def _rear(p: Params) -> Part:
    fr = frame(p)
    shell = rear_shell(p)
    skin = _slab(fr.outer_w, fr.outer_h, p.structure.outer_corner_r, 0, fr.yc, -SKIN_T, 0)
    skin = chamfer(skin.edges().filter_by_position(Axis.Z, -SKIN_T - 0.01, -SKIN_T + 0.01), SKIN_CHAMFER)

    def apply(shape, sketches):
        for sk in sketches if isinstance(sketches, tuple) else (sketches,):
            shape = shape - _prism(sk, -SKIN_T - 0.5, -SKIN_T + REAR_RECESS_D)
        return shape

    skin = _fuse_features("rear", skin, _skin_features(p), apply)
    return shell + skin


def build(p: Params) -> dict[str, ArmorPart]:
    fr = frame(p)
    front = _front(p)
    rear = _rear(p)
    rear_loc = Location((0, -fr.yc, SKIN_T))
    return {
        "rear": ArmorPart(rear, rear_loc, wall_shape=rear_shell(p)),
        "front": ArmorPart(front, print_location_front(p), wall_shape=front_bezel(p)),
    }
