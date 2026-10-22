"""Neon-cyberpunk armor: raised LED-strip rails + angular plates on the bezel, glow slots on the back.

Front bezel: all decoration is raised on the visible face (z >= total_t) inside the base decor face.
Rear shell: a thin skin below the back plate (z < 0) carries recessed glow-fill slots.

Tunables (module constants; env vars override for experiments):
  LED_STRIP_W (NEON_LED_STRIP_W)  adhesive LED strip width, default 5.0 mm.
  NEON_DIFFUSER=0                 skip the press-fit diffuser strips (see DIFFUSER_T); emitted by default.
"""
from __future__ import annotations

import math
import os

from build123d import (
    Align, Box, BuildSketch, Face, Location, Locations, Part, Pos, Solid, Text, Vector, Wire,
)
from shapely.geometry import LineString, MultiPolygon, Polygon, box as sbox
from shapely.ops import unary_union

from projects.armor.params import Params
from projects.armor.part import ArmorPart

from projects.armor.models._armor_base import (
    DECOR_EDGE_INSET, DECOR_KEEPOUT, frame, front_bezel, print_location_front,
    print_location_rear, rear_shell, screw_positions,
)

# ----------------------------------------------------------------------------- tunables
LED_STRIP_W = float(os.environ.get("NEON_LED_STRIP_W", 5.0))
LED_CHANNEL_CLEARANCE = 0.4
LED_CHANNEL_DEPTH = 2.5
RAIL_WALL = 2.4          # preferred rail wall; clipped to the decor face but never below RAIL_WALL_MIN
RAIL_WALL_MIN = 1.6
WIRE_SLOT_W = 3.0
WIRE_SLOT_H = 2.0
PLATE_H = 1.2            # angular plates, raised above the bezel face
TAG_H = 1.6              # barcode tag plates
DIFFUSER_T = 1.2
DIFFUSER_MIN_WALL = 1.0  # clear diffuser strips are intentionally thin; relaxed from structure.min_wall
DIFFUSER_ENABLED = os.environ.get("NEON_DIFFUSER", "1") != "0"
SKIN_T = 1.6
GLOW_DEPTH = 1.0         # <= 1.2
GLOW_W = 4.5             # <= 6 so it bridges
GLOW_RIM = 6.0           # solid margin between glow slots and skin edge

TRACE_W = 1.0            # secondary circuit traces (raised)
TRACE_H = 0.8
VIA_D = 2.4              # round via pad at the end of each trace
TEXT_H = 0.6             # raised text above its plate
TEXT_FONT = "Arial Black"
TEXT_MIN_STROKE = 0.8
RING_H = 1.2             # counterbore guard ring height above the bezel face
RING_IN_D = 8.4          # >= counterbore_d + 2
RING_HEX_R = 6.6         # hexagon circumradius of the guard ring
GLOW_TRACE_W = 1.2       # rear linking trace recesses
GLOW_TRACE_DEPTH = 0.8

# Reference layout: the original design was authored for a 336x221 lid; plate/rear coordinates below are
# written in that frame and mapped onto the current frame (see _layout / _rear).
REF_X_END = 150.0        # outer x of the front plates in the reference layout
REF_PLATE_H = 9.0        # top plate height in the reference layout
REF_BOT_H = 4.4          # bottom plate height in the reference layout
REF_REAR_HW = 176.1      # rear decor half width (x) in the reference layout
REF_REAR_HH = 103.5      # rear decor half height (y) in the reference layout
REF_REAR_YC = 120.5      # rear decor centre y in the reference layout
JOG = 5.0                # 45-degree jog amplitude of the LED channel
PLATEAU_DY = 11.5        # rise of the 45-degree diagonal up to the camera plateau

_MITRE = dict(join_style="mitre", mitre_limit=5.0)
_RES = 16


# ----------------------------------------------------------------------------- shapely <-> build123d
def _rrect(w: float, h: float, r: float, cx: float, cy: float) -> Polygon:
    return sbox(cx - w / 2 + r, cy - h / 2 + r, cx + w / 2 - r, cy + h / 2 - r).buffer(r, _RES)


def _polys(g) -> list[Polygon]:
    if g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g]
    return [q for part in getattr(g, "geoms", []) for q in _polys(part)]


def _wire(coords) -> Wire:
    pts = [Vector(x, y, 0) for x, y in list(coords)[:-1]]
    return Wire.make_polygon(pts)


def _solid(g, z0: float, z1: float) -> Part | None:
    """Extrude a shapely (multi)polygon from z0 to z1 as one fused shape (None if empty)."""
    out = None
    for poly in _polys(g.buffer(0).simplify(0.01)):
        if poly.area < 0.05:
            continue
        face = Face(_wire(poly.exterior.coords), [_wire(r.coords) for r in poly.interiors])
        s = Pos(0, 0, z0) * Solid.extrude(face, Vector(0, 0, z1 - z0))
        out = s if out is None else out + s
    return out


def _frange(a, b, step):
    n = int((b - a) // step) + 1
    return [a + i * step for i in range(n)]


def _mirror_x(g):
    from shapely import affinity
    return affinity.scale(g, xfact=-1, yfact=1, origin=(0, 0))


def _text_solid(txt: str, size: float, x: float, y: float, right: bool, plate: Polygon, z0: float):
    """Raised text anchored at (x, y); shrinks until it fits inside ``plate`` (eroded 0.6 mm), else (None, None)."""
    room = plate.buffer(-0.6)
    while size > 2.5:
        with BuildSketch() as sk:
            with Locations((x, y)):
                Text(txt, size, align=(Align.MAX if right else Align.MIN, Align.CENTER), font=TEXT_FONT)
        bb = sk.sketch.bounding_box()
        if room.contains(sbox(bb.min.X, bb.min.Y, bb.max.X, bb.max.Y)):
            out = None
            for fc in sk.sketch.faces():
                so = Pos(0, 0, z0 - 0.1) * Solid.extrude(fc, Vector(0, 0, TEXT_H + 0.1))
                out = so if out is None else out + so
            return out, size
        size -= 0.2
    return None, None


def _outward_x(chan: Polygon, y: float, side: int) -> float | None:
    """x of the outer rail edge at height y on the given side (-1 left, +1 right)."""
    hit = LineString([(side * 100, y), (side * 400, y)]).intersection(chan.buffer(RAIL_WALL, **_MITRE))
    if hit.is_empty:
        return None
    xs = [c[0] for g in getattr(hit, "geoms", [hit]) for c in g.coords]
    return max(xs, key=abs)


def _trace_shapes(chan: Polygon, allowed: Polygon, blocked: Polygon, lay: dict):
    """Secondary circuit traces: 45-degree branches off the channel rails ending in via pads, plus a bottom bus."""
    ok_zone = allowed.buffer(-0.4)
    traces, n_branch = [], 0

    def add(pts, pad=True):
        g = LineString(pts).buffer(TRACE_W / 2, cap_style="flat", **_MITRE)
        if pad:
            g = g.union(sbox(*pts[-1], *pts[-1]).buffer(VIA_D / 2, _RES))
        return g

    # side branches: (fraction of the channel's vertical run, +-1 = up/down, dx outward, straight stub)
    left = [(0.056, 1, 4.0, 3), (0.226, -1, 4.0, 0), (0.416, 1, 3.5, 4), (0.692, -1, 4.0, 3),
            (0.830, 1, 4.0, 0), (0.936, -1, 3.5, 3)]
    right = [(0.088, 1, 4.0, 0), (0.268, 1, 4.0, 4), (0.523, -1, 4.0, 0), (0.640, 1, 3.5, 3),
             (0.778, -1, 4.0, 4), (0.900, 1, 3.5, 0)]
    ya, yb = lay["run_y"]
    for side, lst in ((-1, left), (1, right)):
        for frac, v, dx, stub in lst:
            y = ya + frac * (yb - ya)
            x0 = _outward_x(chan, y, side)
            if x0 is None:
                continue
            out = side  # outward direction in x
            for d in (dx, dx - 1.0, dx - 2.0):
                a = (x0 - out * 0.5, y)  # start inside the rail so it fuses
                b = (x0 + out * d, y + v * (d + 0.5))
                pts = [a, b] + ([(b[0], b[1] + v * stub)] if stub else [])
                g = add(pts)
                if g.difference(ok_zone).area < 1e-3 and g.distance(blocked) > 0.8 and \
                        g.difference(chan.buffer(RAIL_WALL + 0.0)).area > 0.5 * g.area:
                    traces.append(g)
                    n_branch += 1
                    break
    # bottom bus: parallel traces between the plates, 45-degree kinks, staggered via pads
    bot = lay.get("bot")
    bus = []
    if bot is not None:
        lo, hi, kx, cap = bot
        # offsets in the reference band; the top trace is capped below the screen keep-out and the others
        # kept >= 1.8 mm apart
        y3 = min(lo + 4.6 * (hi - lo) / REF_BOT_H, cap)
        y2 = min(lo + 3.2 * (hi - lo) / REF_BOT_H, y3 - 1.8)
        y1 = min(lo + 1.2 * (hi - lo) / REF_BOT_H, y2 - 1.8)
        bus = [(y1, -80 * kx, 14 * kx, True), (y2, -74 * kx, 22 * kx, True), (y3, -68 * kx, 8 * kx, False)]
    for y, xa, xb, pad in bus:
        g = add([(xa, y), (xb, y)], pad=pad)
        if pad:
            g = g.union(sbox(xa, y, xa, y).buffer(VIA_D / 2, _RES))
        if g.difference(ok_zone).area < 1e-3 and g.distance(blocked) > 0.8:
            traces.append(g)
    return unary_union(traces), n_branch


def _ring_shapes(p: Params, allowed_ring: Polygon, rail: Polygon):
    """Raised hexagonal guard rings (notched on the outboard side) around each counterbore."""
    out = []
    for x, y in screw_positions(p):
        hexa = Polygon([(x + RING_HEX_R * math.cos(math.radians(a)), y + RING_HEX_R * math.sin(math.radians(a)))
                        for a in range(30, 390, 60)])
        notch = Polygon([(x + (-1 if x < 0 else 1) * 5.5, y + 1.8), (x + (-1 if x < 0 else 1) * 9.0, y),
                         (x + (-1 if x < 0 else 1) * 5.5, y - 1.8)])
        ring = hexa.difference(sbox(x, y, x, y).buffer(RING_IN_D / 2, 32)).difference(notch)
        out.append(ring)
    ring = unary_union(out).intersection(allowed_ring).difference(rail.buffer(0.8))
    keep = [q for q in _polys(ring) if q.area > 4.0]
    return unary_union(keep) if keep else Polygon()


# ----------------------------------------------------------------------------- front geometry
def _allowed(p: Params) -> Polygon:
    """Shapely mirror of ``front_decor_face`` (same constants), used to place decoration."""
    fr, sc, cam, s = frame(p), p.screen, p.camera, p.fasteners
    k, e = DECOR_KEEPOUT, DECOR_EDGE_INSET
    a = _rrect(fr.outer_w - 2 * e, fr.outer_h - 2 * e, max(p.structure.outer_corner_r - e, 0.5), 0, fr.yc)
    a = a.difference(_rrect(sc.w + 2 * k, sc.h + 2 * k, sc.corner_r + k, 0, sc.bottom + sc.h / 2))
    cy = p.lid.h - cam.top_offset - cam.h / 2
    a = a.difference(sbox(-(cam.w / 2 + k), cy - (cam.h / 2 + k), cam.w / 2 + k, cy + cam.h / 2 + k))
    for x, y in screw_positions(p):
        a = a.difference(sbox(x, y, x, y).buffer(s.counterbore_d / 2 + k, _RES))
    return a.buffer(-0.02, _RES)  # tiny erosion so shared boundaries never poke out


def _allowed_no_screws(p: Params) -> Polygon:
    """``_allowed`` without the counterbore keep-outs (the guard rings sit around the counterbores)."""
    fr, sc, cam = frame(p), p.screen, p.camera
    k, e = DECOR_KEEPOUT, DECOR_EDGE_INSET
    a = _rrect(fr.outer_w - 2 * e, fr.outer_h - 2 * e, max(p.structure.outer_corner_r - e, 0.5), 0, fr.yc)
    a = a.difference(_rrect(sc.w + 2 * k, sc.h + 2 * k, sc.corner_r + k, 0, sc.bottom + sc.h / 2))
    cy = p.lid.h - cam.top_offset - cam.h / 2
    a = a.difference(sbox(-(cam.w / 2 + k), cy - (cam.h / 2 + k), cam.w / 2 + k, cy + cam.h / 2 + k))
    return a.buffer(-0.02, _RES)


def _layout(p: Params, ch_w: float) -> dict:
    """Anchor values for the front decoration, all derived from the frame, screen, camera and screws."""
    fr, sc, cam = frame(p), p.screen, p.camera
    k, e = DECOR_KEEPOUT, DECOR_EDGE_INSET
    half = ch_w / 2
    need = half + RAIL_WALL_MIN              # channel centre to decor-face edge/keep-out
    dec_top, dec_bot = fr.y1 - e, fr.y0 + e
    c0 = sc.w / 2 + k + RAIL_WALL + half + 0.5  # inner wall clears the screen keep-out
    cam_top = p.lid.h - cam.top_offset
    py = min(cam_top + 6.5, dec_top - need - 0.05)                      # plateau above the camera region
    ty = max(py - PLATEAU_DY, sc.bottom + sc.h + k + need + 0.3)        # top run, clear of the screen keep-out
    ty = min(ty, py - 3.0)
    y_start = dec_bot + RAIL_WALL            # channel starts one end-wall above the decor edge
    x_end = c0 - 13.0                        # outer x of the plates
    tb, tt = ty + 6.8, dec_top - 0.2         # top plate band
    bot_lo = dec_bot + 0.8
    bot_hi = min(bot_lo + REF_BOT_H, sc.bottom - k - 0.8)
    return dict(c0=c0, py=py, ty=ty, xp=cam.w / 2 + 5.0, y_start=y_start, x_end=x_end, kx=x_end / REF_X_END,
                tb=tb, tt=tt, bot_lo=bot_lo, bot_hi=bot_hi, run_y=(y_start, ty),
                bot_cap=sc.bottom - k - 0.4 - TRACE_W / 2 - 0.05)


def _led_path(p: Params, lay: dict) -> list[tuple[float, float]]:
    """Centerline of the LED channel, left side bottom -> top plateau -> right side bottom.

    Straight where it passes screws (hugging the screen keep-out), 45-degree jogs outward between screws.
    """
    c0, ty, py, j = lay["c0"], lay["ty"], lay["py"], JOG
    sy = frame(p).screw_ys
    pts = [(c0, lay["y_start"])]
    y = sy[0] + 8
    pts.append((c0, y))
    # screws the side run passes before the top run (each gets a straight window of -21..+17 around it)
    mids = [v for v in sy[1:] if v + 17 < ty - 3]
    for i, v in enumerate(mids):
        lo, hi = v - 21, v + 17
        jj = j if i == 0 else j - 1
        if lo - y - 2 * jj >= 6:
            pts += [(c0 + jj, y + jj), (c0 + jj, lo - jj), (c0, lo)]
        pts.append((c0, hi))
        y = hi
    jj = j - 1
    y_in = ty - 20
    if y_in - jj - (y + jj) >= 6:
        pts += [(c0 + jj, y + jj), (c0 + jj, y_in - jj), (c0, y_in)]
    pts += [(c0, ty - 3), (c0 - 3, ty)]
    xd = lay["xp"] + (py - ty)
    pts += [(xd, ty), (lay["xp"], py), (0.0, py)]
    left = pts
    right = list(reversed(left[:-1]))
    left = [(-x, y) for x, y in left]
    return left + right


def _split_valid(pts, ch_w: float, allowed: Polygon) -> list[list[tuple[float, float]]]:
    """Group consecutive path segments whose channel + RAIL_WALL_MIN stays inside ``allowed``."""
    runs, cur = [], []
    for a, b in zip(pts[:-1], pts[1:]):
        seg = LineString([a, b]).buffer(ch_w / 2 + RAIL_WALL_MIN, cap_style="flat", **_MITRE)
        ok = seg.difference(allowed).area < 0.02
        if ok:
            cur = cur if cur else [a]
            cur.append(b)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return runs


def _front_deco(p: Params):
    """Return (raised_shape, info) for the bezel decoration, all clipped to the decor face."""
    ch_w = LED_STRIP_W + LED_CHANNEL_CLEARANCE
    allowed = _allowed(p)
    lay = _layout(p, ch_w)
    path = _led_path(p, lay)
    runs = _split_valid(path, ch_w, allowed)
    chan = unary_union([LineString(r).buffer(ch_w / 2, cap_style="flat", **_MITRE) for r in runs])
    rail = chan.buffer(RAIL_WALL, **_MITRE).intersection(allowed).difference(chan)
    n_seg = len(path) - 1
    kept = sum(len(r) - 1 for r in runs)
    info = {"runs": len(runs), "segments_kept": kept, "segments_total": n_seg, "chan": chan, "ch_w": ch_w, "notes": []}
    notes = info["notes"]

    fr = frame(p)
    # --- plates (angular, asymmetric) and chevron cut-outs, outside the rails by >= 1.4 mm
    keep_off = rail.buffer(1.4)
    kx = lay["kx"]
    X = lambda v: v * kx                       # reference x -> current x
    tb, th = lay["tb"], lay["tt"] - lay["tb"]
    fh = th / REF_PLATE_H
    Yt = lambda o: tb + o * fh                 # reference offset in the top band -> y
    bl, bh = lay["bot_lo"], lay["bot_hi"] - lay["bot_lo"]
    fb = bh / REF_BOT_H
    Yb = lambda o: bl + o * fb
    top_ok, bot_ok = th >= 3.5, bh >= 2.5
    if not top_ok:
        notes.append(f"top plates and NEON//DECK/VLT-03 text dropped (band {th:.1f} mm < 3.5 mm)")
    if not bot_ok:
        notes.append(f"bottom plates and bus traces dropped (band {bh:.1f} mm < 2.5 mm)")
    parts_pl, parts_tag = [], []
    if top_ok:
        wedge = Polygon([(X(-150), Yt(0)), (X(-64), Yt(0)), (X(-96), Yt(9)), (X(-150), Yt(9))])
        chevs = []
        for i in range(2):
            cx, cy = X(-143) + i * 10, Yt(4.5)
            chevs.append(Polygon([(cx - 3, cy + 2.0 * fh), (cx + 1.5, cy), (cx - 3, cy - 2.0 * fh),
                                  (cx - 5.2, cy - 2.0 * fh), (cx - 0.7, cy), (cx - 5.2, cy + 2.0 * fh)]))
        parts_pl += [wedge.difference(unary_union(chevs))]
        parts_pl += [Polygon([(X(x), Yt(0.6)), (X(x) + 4.8, Yt(0.6)), (X(x) + 8.8, Yt(8.4)), (X(x) + 4.0, Yt(8.4))])
                     for x in (-58.0, -51.0, -44.0)]
        parts_tag.append(Polygon([(X(72), Yt(0)), (X(150), Yt(0)), (X(150), Yt(9)), (X(78), Yt(9))]))
    if bot_ok:
        notched = Polygon([(X(40), Yb(0)), (X(150), Yb(0)), (X(150), Yb(4.4)), (X(68), Yb(4.4))])
        notched = notched.difference(Polygon([(X(108), Yb(4.6)), (X(118), Yb(4.6)), (X(113), Yb(1.6))]))
        notched = notched.difference(Polygon([(X(126), Yb(-0.2)), (X(132), Yb(-0.2)), (X(132), Yb(2.4))]))
        parts_pl.append(notched)
        # angular tag plate: chamfered end and a notch
        parts_tag.append(Polygon([(X(-146), Yb(0)), (X(-92), Yb(0)), (X(-88), Yb(4.4)), (X(-146), Yb(4.4))])
                         .difference(Polygon([(X(-126), Yb(4.6)), (X(-116), Yb(4.6)), (X(-121), Yb(1.6))])))
    plates = unary_union(parts_pl).difference(keep_off).intersection(allowed) if parts_pl else Polygon()
    tag_polys = unary_union(parts_tag).difference(keep_off).intersection(allowed) if parts_tag else Polygon()

    z = fr.total_t
    shape = _solid(rail, z, z + LED_CHANNEL_DEPTH)
    for g, h in ((plates, PLATE_H), (tag_polys, TAG_H)):
        s = _solid(g, z, z + h)
        if s is not None:
            shape = s if shape is None else shape + s

    # --- raised text (0.6 mm above its plate); shrinks to a floor, then is dropped with a note
    info["text_sizes"] = (None, None)
    if top_ok and _polys(plates) and _polys(tag_polys):
        top_pl = [q for q in _polys(plates) if q.bounds[1] > tb - 1.0]
        wedge_poly = max(top_pl, key=lambda q: q.bounds[2] - q.bounds[0] if q.centroid.x < 0 else 0)
        tag_r = max([q for q in _polys(tag_polys) if q.bounds[1] > tb - 1.0], key=lambda q: q.centroid.x)
        t1, sz1 = _text_solid("NEON//DECK", 5.0 * fh, X(-126), Yt(4.5), False, wedge_poly, z + PLATE_H)
        t2, sz2 = _text_solid("VLT-03", 5.6 * fh, X(146), Yt(4.5), True, tag_r, z + TAG_H)
        for name, t in (("NEON//DECK", t1), ("VLT-03", t2)):
            if t is None:
                notes.append(f"text {name!r} dropped (does not fit its plate)")
            else:
                shape = shape + t
        info["text_sizes"] = (sz1, sz2)

    # --- secondary circuit traces
    blocked = unary_union([plates, tag_polys]).buffer(0)
    traces, n_br = _trace_shapes(
        chan, allowed, blocked, dict(run_y=lay["run_y"], bot=(bl, bl + bh, kx, lay["bot_cap"]) if bot_ok else None))
    traces = traces.difference(chan.buffer(RAIL_WALL - 0.4)).intersection(allowed)
    ts = _solid(traces, z, z + TRACE_H)
    if ts is not None:
        shape = shape + ts
    info["branches"] = n_br
    info["layout"] = lay

    # --- counterbore guard rings (clipped to the decor face outline, counterbore keep-out lifted)
    rings = _ring_shapes(p, _allowed_no_screws(p), rail)
    rs = _solid(rings, z, z + RING_H)
    if rs is not None:
        shape = shape + rs
    # --- wire exit: slot through the bottom end wall of the rail at the left start of the path
    x0, y0 = path[0]
    slot = Pos(x0, (fr.y0 - 1 + path[0][1] + 0.05) / 2, z) * Box(
        WIRE_SLOT_W, path[0][1] + 0.05 - (fr.y0 - 1), WIRE_SLOT_H, align=(Align.CENTER, Align.CENTER, Align.MIN))
    shape = shape - slot
    for n in notes:
        print(f"armor_neon: note: {n}")
    return shape, info


def _front(p: Params):
    deco, info = _front_deco(p)
    return front_bezel(p) + deco, info


# ----------------------------------------------------------------------------- diffuser
def _diffusers(p: Params, info) -> dict[str, ArmorPart]:
    fr = frame(p)
    zt = fr.total_t + LED_CHANNEL_DEPTH
    out: dict[str, ArmorPart] = {}
    chan = info["chan"]
    for side, half in (("left", sbox(-400, -400, 0, 400)), ("right", sbox(0, -400, 400, 400))):
        region = chan.intersection(half)
        for i, poly in enumerate(sorted(_polys(region), key=lambda q: q.centroid.x)):
            if poly.area < 5:
                continue
            name = f"diffuser_{side}" + ("" if i == 0 else f"_{i + 1}")
            shape = _solid(poly, zt - DIFFUSER_T, zt)
            c = poly.centroid
            loc = Location((-c.x, -c.y, -(zt - DIFFUSER_T)))
            out[name] = ArmorPart(shape, loc, check_lid=False, check_screen=False, min_wall=DIFFUSER_MIN_WALL)
    return out


# ----------------------------------------------------------------------------- rear
def _rear(p: Params):
    fr = frame(p)
    e = DECOR_EDGE_INSET
    skin_poly = _rrect(fr.outer_w - 2 * e, fr.outer_h - 2 * e, max(p.structure.outer_corner_r - e, 0.5), 0, fr.yc)
    skin = _solid(skin_poly, -SKIN_T, 0.0)
    region = skin_poly.buffer(-GLOW_RIM)
    w = GLOW_W

    def trace(pts):
        return LineString(pts).buffer(w / 2, cap_style="flat", **_MITRE)

    # slot layout is authored in the reference frame and scaled uniformly (keeps the 45-degree jogs) about
    # the rear decor centre so it fills the current decor face
    sc = min((fr.outer_w / 2 - e) / REF_REAR_HW, (fr.outer_h / 2 - e) / REF_REAR_HH)

    def T(pts):
        return [(x * sc, fr.yc + (y - REF_REAR_YC) * sc) for x, y in pts]

    cy = REF_REAR_YC
    cuts = []
    for i in range(5):  # ">>>>>" chevron train, centre
        x = -44 + i * 17
        cuts.append(trace(T([(x, cy + 34), (x + 30, cy), (x, cy - 34)])))
    # circuit-style traces with 45-degree jogs, asymmetric
    cuts.append(trace(T([(-160, 205), (-120, 205), (-100, 185), (-70, 185)])))
    cuts.append(trace(T([(-160, 188), (-136, 188), (-118, 170), (-118, 150)])))
    cuts.append(trace(T([(160, 40), (120, 40), (100, 60), (70, 60)])))
    cuts.append(trace(T([(160, 58), (138, 58), (122, 74), (122, 96)])))
    cuts.append(trace(T([(160, 205), (140, 205), (125, 190)])))
    # slash bars bottom-left and top-right
    for i in range(4):
        x = -150 + i * 13
        cuts.append(trace(T([(x, 28), (x + 28, 56)])))
    for i in range(3):
        x = 90 + i * 14
        cuts.append(trace(T([(x, 150), (x + 26, 176)])))
    glow = unary_union(cuts).intersection(region)
    cutter = _solid(glow, -SKIN_T - 0.5, -SKIN_T + GLOW_DEPTH)
    # linking circuit traces: 45-degree jogs between the slot groups, shallower than the slots
    def link(pts):
        return LineString(T(pts)).buffer(GLOW_TRACE_W / 2, cap_style="flat", **_MITRE)

    links = [
        [(-70, 185), (-62, 177), (-62, 162.5), (-54, 154.5), (-44, 154.5)],
        [(-118, 150), (-118, 110), (-96, 88), (-96, 56)],
        [(70, 60), (55, 60), (40, 75), (28.5, 86.5), (24, 86.5)],
        [(125, 190), (125, 181), (130, 176)],
        [(56, 120.5), (90, 120.5), (114.5, 96), (122, 96)],
        [(-44, 86.5), (-74.5, 56), (-83, 56)],
    ]
    link_cut = unary_union([link(q) for q in links]).intersection(region)
    link_cutter = _solid(link_cut, -SKIN_T - 0.5, -SKIN_T + GLOW_TRACE_DEPTH)
    cutter = cutter + link_cutter
    # the cutter spans z=-SKIN_T-0.5..-SKIN_T+GLOW_DEPTH: open to the bed face, stops inside the skin
    return (rear_shell(p) + skin) - cutter


# ----------------------------------------------------------------------------- build
def build(p: Params) -> dict[str, ArmorPart]:
    front, info = _front(p)
    parts = {
        "rear": ArmorPart(_rear(p), Location((0, 0, SKIN_T)) * print_location_rear(p), wall_shape=rear_shell(p)),
        "front": ArmorPart(front, print_location_front(p), wall_shape=front_bezel(p)),
    }
    if DIFFUSER_ENABLED:
        parts.update(_diffusers(p, info))
    build.last_info = info  # for scripts/debugging
    return parts
