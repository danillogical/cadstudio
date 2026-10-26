"""Mockup sketches of candidate Pocky prototypes. UNTESTED CONCEPTS, not CAD.

Run: ``uv run --frozen python projects/pocky/docs/mockups/sketch.py``

Writes one ``NN-<slug>.png`` per concept (side section X-Z over a top view X-Y)
and ``overview.png`` (every side section as a thumbnail) next to this file.

Coordinates follow ``projects/pocky/README.md``: X is the packet long axis
(+X is the exit), Y the short axis, Z up with the bottom packet's underside at
z = 0. Dimensions are mm and come from ``geometry/linkage.py`` and
``geometry/prototype.py`` where a concept reuses a part; new features are
first guesses drawn roughly to scale.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Circle, Patch, Polygon, Rectangle  # noqa: E402

OUT = Path(__file__).resolve().parent

# One colour per role, the same in every concept.
COLORS = {
    "housing": "#a6cee3",  # body / magazine
    "lip": "#fdae61",      # lip, shelf, separator blade, shims
    "chassis": "#9e9e9e",  # chassis, base, cover, cassette, fixed mechanism plate
    "crank": "#ffd92f",    # crank or any rotating link (lever, gear)
    "rod": "#e8615a",      # button input (rod, plunger)
    "pusher": "#66bd63",   # pusher, ram, slider
    "packet": "#a0522d",   # packets
    "spring": "#1b9e9e",   # springs and flexures
    "peg": "#303030",      # separate headed pegs (baseline only)
}
LOAD_FIXED = "#00682c"
LOAD_MOVING = "#b2182b"
MOTION = "#6a3d9a"
LABEL_FS = 6.5

# Shared dimensions (mm).
PACKET_L, PACKET_W, PACKET_H, N_PACKETS = 165.0, 55.0, 5.2, 10
BORE_X, BORE_Y = 85.0, 30.0
WALL = 2.4
OY = BORE_Y + WALL  # 32.4, outer face of the side walls
TOP = 72.0  # top of the magazine walls
FLOOR = (-2.4, 0.0)
CARRIAGE = (-6.8, -2.8)
CRANK = (-11.2, -7.2)
ROD = (-15.6, -11.6)
BASE = (-19.2, -15.6)
PIVOT = (-78.0, -8.0)
GAP = 5.75  # separator gap
EJECT_SHIFT = 45.5  # packet travel at full stroke, 40 mm past the 88 mm exit face


@dataclass
class Shape:
    role: str
    kind: str  # "rect", "poly", "circle"
    geom: tuple
    label: str | None = None
    at: tuple | None = None  # label position; a leader line is drawn to the shape
    alpha: float = 1.0
    dashed: bool = False
    hatch: str | None = None


def R(role, x0, x1, a0, a1, label=None, at=None, alpha=1.0, dashed=False, hatch=None):
    return Shape(role, "rect", (x0, x1, a0, a1), label, at, alpha, dashed, hatch)


def P(role, pts, label=None, at=None, alpha=1.0, dashed=False):
    return Shape(role, "poly", tuple(pts), label, at, alpha, dashed)


def C(role, cx, cy, r, label=None, at=None, alpha=1.0, dashed=False):
    return Shape(role, "circle", (cx, cy, r), label, at, alpha, dashed)


@dataclass
class Concept:
    num: str
    slug: str
    title: str
    tagline: str
    side: list
    top: list
    table_z: float
    loads: list  # (x, z_from, z_to, "fixed" | "moving")
    motions: list  # ((x0, z0), (x1, z1), text, text_xy)
    top_motions: list = field(default_factory=list)
    notes: list = field(default_factory=list)  # (x, z, text) free text on the side panel
    com: tuple = (0.0, 0.0)
    support: list = field(default_factory=list)  # top-view green patches
    xlim: tuple = (-165.0, 155.0)


# ---------------------------------------------------------------- shared parts

def packets_side():
    shapes = []
    for i in range(N_PACKETS):
        z0 = i * PACKET_H
        shapes.append(R("packet", -PACKET_L / 2, PACKET_L / 2, z0 + 0.15, z0 + PACKET_H - 0.15,
                        alpha=1.0 if i == 0 else 0.55))
    shapes[-1].label = "10 packets 165×55×5.2"
    shapes[-1].at = (-60, 62)
    # Bottom packet at full stroke: 40 mm past the exit face.
    shapes.append(R("packet", -PACKET_L / 2 + EJECT_SHIFT, PACKET_L / 2 + EJECT_SHIFT, 0.15, 5.05,
                    "ejected packet, 40 mm out", at=(118, -30), alpha=0.15, dashed=True))
    return shapes


def body_side(x0=-95.5, x1=88.0, notch=True, label="body / magazine"):
    """Floor, back wall (notched for the pusher), exit wall above the gap, side wall behind."""
    back_z0 = 4.4 if notch else 0.0
    return [
        R("housing", -87.4, x1, 0.0, TOP, alpha=0.18),  # side wall behind the section
        R("housing", x0, x1, *FLOOR, label, at=(-20, 78)),
        R("housing", -87.4, -85.0, back_z0, TOP),
        R("housing", 85.0, 88.0, 9.2, TOP),
    ]


def lip_side():
    return [
        R("lip", 88.3, 106.0, -2.4, 0.0, "18 mm shelf", at=(140, -14)),
        R("lip", 80.5, 91.0, GAP, GAP + 2.4, "separator blade, 5.75 gap", at=(112, 34)),
    ]


def packets_top():
    return [R("packet", -PACKET_L / 2, PACKET_L / 2, -PACKET_W / 2, PACKET_W / 2, alpha=0.25, dashed=True)]


def body_top(x0=-95.5, x1=88.0, y0=-OY, y1=OY, label="body floor"):
    return [
        R("housing", x0, x1, y0, y1, label, at=(-40, 66), alpha=0.45),
        R("housing", -BORE_X, BORE_X, -BORE_Y, BORE_Y, alpha=0.0, dashed=True),
    ]


def lip_top():
    return [R("lip", 88.3, 106.0, -OY, OY, "lip", at=(122, 52), alpha=0.8)]


def crank_poly(phi_deg=120.0, a=32.4, b=54.4, w=10.0, px=PIVOT[0], py=PIVOT[1]):
    """Top-view outline of the straight crank bar, pusher end at +b along ``phi``."""
    ux, uy = math.cos(math.radians(phi_deg)), math.sin(math.radians(phi_deg))
    nx, ny = -uy, ux
    h = w / 2
    return [
        (px - a * ux + h * nx, py - a * uy + h * ny),
        (px + b * ux + h * nx, py + b * uy + h * ny),
        (px + b * ux - h * nx, py + b * uy - h * ny),
        (px - a * ux - h * nx, py - a * uy - h * ny),
    ]


def crank_mech_side(pegs="molded", spring="inline"):
    """The M1 linkage in section. ``pegs`` is "headed" (today) or "molded" (pins grown on the lower part)."""
    s = [
        R("rod", -71.0, 128.0, *ROD, "button rod", at=(20, -30)),
        R("rod", 114.0, 128.0, ROD[1], 12.0, "button", at=(140, 4)),
        R("rod", 81.0, 85.0, -18.0, ROD[1]),
        R("crank", -105.0, -62.0, *CRANK, "crank", at=(-135, -26)),
        R("pusher", -111.0, -83.0, *CARRIAGE, "pusher", at=(-140, 10)),
        R("pusher", -91.1, -87.0, CARRIAGE[1], 4.2),
        R("chassis", 85.05, 88.0, -18.0, -9.0),
        R("chassis", 12.9, 16.9, -18.0, -12.0),
    ]
    if pegs == "headed":
        s += [
            R("peg", -80.5, -75.5, BASE[0], CRANK[1], "3 separate headed pegs", at=(-60, -34)),
            R("peg", -83.0, -73.0, BASE[0], BASE[0] + 2.4),
            R("peg", -105.0, -101.0, CRANK[0], CARRIAGE[1]),
            R("peg", -107.5, -98.5, CRANK[0] - 2.4, CRANK[0]),
            R("peg", -68.5, -64.5, ROD[0], CRANK[1]),
            R("peg", -71.0, -62.0, ROD[0] - 2.4, ROD[0]),
        ]
    elif pegs == "molded":
        s += [
            R("chassis", -85.0, -71.0, ROD[0], ROD[1]),
            R("chassis", -81.0, -75.0, ROD[1], CRANK[1], "pins molded, no heads", at=(-60, -34)),
            R("crank", -106.0, -100.0, CRANK[1], CARRIAGE[1]),
            R("rod", -69.5, -63.5, ROD[1], CRANK[1]),
        ]
    if spring == "beside":
        s.append(R("spring", -30.4, 20.0, -16.6, -11.6, "spring (y = −74, behind)", at=(-10, -38), alpha=0.6))
    elif spring == "inline":
        s.append(R("spring", -122.0, -71.5, -15.4, -11.8, "spring in line behind rod", at=(-150, -36), alpha=0.8))
    return s


def crank_mech_top(spring="inline", pegs="molded"):
    s = [
        R("rod", -71.0, 128.0, -33.0, -23.0, "rod", at=(40, -62)),
        R("rod", 114.0, 128.0, -42.0, -28.0, "button", at=(140, -60)),
        P("crank", crank_poly(), "crank R50, ±30°", at=(-150, 40)),
        C("crank", PIVOT[0], PIVOT[1], 5.5),
        R("pusher", -111.0, -83.0, -8.0, 50.0, "carriage (y to +50)", at=(-150, 64), alpha=0.85),
        R("pusher", -91.1, -87.0, -20.0, 20.0),
    ]
    if spring == "beside":
        s.append(R("spring", -30.4, 20.0, -81.0, -67.0, "spring y=−74", at=(40, -92)))
    elif spring == "inline":
        s.append(R("spring", -122.0, -71.5, -35.0, -21.0, "spring in line (rod layer, under crank)", at=(-130, -70)))
    return s


# ------------------------------------------------------------------- concepts

def baseline():
    side = [
        R("chassis", -115.0, 110.0, *BASE, "chassis base 225×75", at=(60, -34)),
        R("chassis", 62.0, 72.0, BASE[0], 2.45, "clip hook, 2.4 mm post", at=(40, 26), alpha=0.6),
        *crank_mech_side(pegs="headed", spring="beside"),
        *body_side(), *lip_side(), *packets_side(),
    ]
    top = [
        R("chassis", -115.0, 110.0, -20.2, 55.0, "chassis 225×75", at=(60, 66), alpha=0.35),
        R("chassis", -42.0, 21.0, -84.0, -64.0, alpha=0.35),
        R("chassis", 62.0, 72.0, 35.0, 37.4, "hooks", at=(85, 60)),
        R("chassis", -38.0, -28.0, -37.4, -35.0),
        *body_top(), *lip_top(), *packets_top(), *crank_mech_top(spring="beside"),
    ]
    loads = [
        (-100.0, -2.4, -6.8, "moving"), (-88.0, -2.4, -6.8, "moving"), (55.0, -2.4, -11.6, "moving"),
        (-100.0, -15.6, -19.2, "fixed"), (55.0, -15.6, -19.2, "fixed"),
    ]
    motions = [((121.0, 15.0), (98.0, 15.0), "press 23 mm", (104, 19)),
               ((-87.0, 7.0), (-37.0, 7.0), "pusher 50 mm", (-75, 10))]
    notes = [(-150.0, 40.0, "no downward seat:\nbody tips 4.5-4.7 mm / ~3°\nonto pusher + rod (sim)")]
    return Concept("00", "current-baseline", "Current prototype (baseline, for comparison)",
                   "Body rests on the moving pusher and rod; hooks only stop it lifting.",
                   side, top, BASE[0], loads, motions, notes=notes)


def seated_rails():
    side = [
        R("chassis", -125.0, 92.0, *BASE, "chassis 217 long, y −50…+53", at=(60, -34)),
        R("chassis", -25.0, 88.0, BASE[1], FLOOR[0], "dovetail rails (y≈±40, behind)", at=(40, 26), alpha=0.35),
        R("chassis", 78.0, 82.0, FLOOR[0] - 0.8, FLOOR[0], "detent", at=(70, -44)),
        *crank_mech_side(pegs="molded", spring="inline"),
        *body_side(), *lip_side(), *packets_side(),
    ]
    top = [
        R("chassis", -125.0, 92.0, -50.0, 53.0, "trimmed chassis", at=(60, 70), alpha=0.25),
        R("housing", -45.0, 88.0, -48.0, -OY, alpha=0.45),
        R("housing", -25.0, 88.0, OY, 38.0, alpha=0.45),
        R("chassis", -45.0, 88.0, -48.0, -44.0, "−Y dovetail rail", at=(20, -94)),
        R("chassis", -25.0, 88.0, 34.0, 38.0, "+Y dovetail rail", at=(30, 52)),
        R("chassis", 78.0, 82.0, 34.0, 38.0),
        *body_top(label="body floor + side flanges"), *lip_top(), *packets_top(), *crank_mech_top(),
    ]
    support = [(-45.0, 88.0, -48.0, -44.0), (-25.0, 88.0, 34.0, 38.0)]
    loads = [(x, FLOOR[0], BASE[1], "fixed") for x in (-15.0, 30.0, 75.0)] + \
            [(x, BASE[0] + 3.4, BASE[0], "fixed") for x in (-100.0, 90.0)]
    motions = [((-150.0, 80.0), (-110.0, 80.0), "body slides on +X", (-158, 83)),
               ((121.0, 15.0), (98.0, 15.0), "press 23 mm", (104, 19))]
    return Concept("01", "seated-rails-dovetail", "Seated linkage: rails, dovetail, detent",
                   "Today's linkage, but the body slides onto two fixed dovetail rails and clicks home.",
                   side, top, BASE[0], loads, motions, support=support)


def standoffs_latches():
    side = [
        R("chassis", -125.0, 92.0, *BASE, "chassis (as 01)", at=(60, -34)),
        R("chassis", -29.0, -19.0, BASE[1], FLOOR[0], "standoff", at=(-40, 26), alpha=0.75),
        R("chassis", 74.0, 84.0, BASE[1], FLOOR[0], "standoff", at=(60, 26), alpha=0.75),
        R("chassis", -5.0, 7.0, BASE[1], 9.0, "snap latch 12×3 arm", at=(10, 40), alpha=0.75),
        R("chassis", -5.0, 7.0, 6.0, 9.0),
        *crank_mech_side(pegs="molded", spring="inline"),
        *body_side(), *lip_side(), *packets_side(),
    ]
    cols = [(-29.0, -19.0, -18.0, -8.0), (-29.0, -19.0, 22.0, 32.0), (74.0, 84.0, -18.0, -8.0), (74.0, 84.0, 22.0, 32.0)]
    top = [
        R("chassis", -125.0, 92.0, -50.0, 53.0, alpha=0.25),
        *body_top(), *lip_top(), *packets_top(), *crank_mech_top(),
        *[R("chassis", *c) for c in cols],
        R("chassis", -5.0, 7.0, OY, OY + 3.0, "latch", at=(10, 60)),
        R("chassis", -5.0, 7.0, -40.0, -37.0, "latch", at=(10, -92)),
        P("chassis", [(-24, -13), (79, -13), (79, 27), (-24, 27)], "support polygon", at=(40, -80), alpha=0.0, dashed=True),
    ]
    loads = [(x, FLOOR[0], BASE[1], "fixed") for x in (-24.0, 79.0)] + \
            [(x, BASE[0] + 3.4, BASE[0], "fixed") for x in (-100.0, 90.0)]
    motions = [((-130.0, 84.0), (-130.0, 74.0), "drop straight down", (-158, 86)),
               ((121.0, 15.0), (98.0, 15.0), "press 23 mm", (104, 19))]
    return Concept("02", "standoffs-snap-latches", "Four standoffs and two chunky snap latches",
                   "Columns carry the weight; two thick latches only stop lift-off. Vertical drop-in assembly.",
                   side, top, BASE[0], loads, motions, support=cols)


def body_is_base():
    side = [
        R("housing", -125.0, 92.0, BASE[0], FLOOR[0], "side skirts to table (behind)", at=(40, 26), alpha=0.3),
        R("housing", -125.0, 92.0, *FLOOR),
        R("chassis", -123.0, 90.0, BASE[0] + 1.0, BASE[1], "cassette tray, hangs on skirt ledges", at=(40, -34)),
        R("chassis", -125.0, -121.0, BASE[0] + 1.0, -10.0, "detent tab", at=(-150, -12)),
        *crank_mech_side(pegs="molded", spring="inline"),
        *body_side(x0=-125.0, x1=92.0), *lip_side(), *packets_side(),
    ]
    top = [
        R("housing", -125.0, 92.0, -48.4, 56.4, "body plinth", at=(-40, 70), alpha=0.35),
        R("housing", -125.0, 92.0, -48.4, -46.0),
        R("housing", -125.0, 92.0, 54.0, 56.4, "skirts", at=(110, 64)),
        R("chassis", -123.0, 90.0, -46.0, 54.0, "cassette", at=(60, -90), alpha=0.25),
        *body_top(), *lip_top(), *packets_top(), *crank_mech_top(),
    ]
    support = [(-125.0, 92.0, -48.4, -46.0), (-125.0, 92.0, 54.0, 56.4)]
    loads = [(x, FLOOR[0], BASE[0], "fixed") for x in (-112.0, -10.0, 70.0)]
    motions = [((-155.0, -17.0), (-128.0, -17.0), "cassette slides in +X", (-158, -26)),
               ((121.0, 15.0), (98.0, 15.0), "press 23 mm", (104, 19))]
    return Concept("03", "body-is-base-cassette", "The body is the base; mechanism is a drawer",
                   "Skirts take the body straight to the table; the mechanism is a cassette that slides in underneath.",
                   side, top, BASE[0], loads, motions, support=support)


def one_piece_tub():
    side = [
        R("housing", -125.0, 92.0, BASE[0], FLOOR[0], "tub skirt (same print as magazine)", at=(40, 26), alpha=0.3),
        R("housing", -125.0, 92.0, *FLOOR),
        R("housing", -45.0, 84.0, ROD[0], FLOOR[0], "guides + stops hang from floor", at=(40, -34), alpha=0.45),
        R("chassis", -122.0, 89.0, BASE[0] + 0.5, -16.3, "snap-on cover, carries pivot pin", at=(-60, -44)),
        R("chassis", -85.0, -71.0, -16.3, ROD[1]),
        R("chassis", -81.0, -75.0, ROD[1], CRANK[1]),
        R("rod", -71.0, 128.0, *ROD, "button rod", at=(60, -46)),
        R("rod", 114.0, 128.0, ROD[1], 12.0, "button", at=(140, 4)),
        R("crank", -105.0, -62.0, *CRANK, "crank", at=(-135, -26)),
        R("crank", -106.0, -100.0, CRANK[1], CARRIAGE[1]),
        R("rod", -69.5, -63.5, ROD[1], CRANK[1]),
        R("pusher", -111.0, -83.0, *CARRIAGE, "pusher", at=(-140, 10)),
        R("pusher", -91.1, -87.0, CARRIAGE[1], 4.2),
        R("spring", -122.0, -71.5, -15.4, -11.8, "spring", at=(-150, -36), alpha=0.8),
        *body_side(x0=-125.0, x1=92.0), *lip_side(), *packets_side(),
    ]
    top = [
        R("housing", -125.0, 92.0, -48.4, 56.4, "tub outline", at=(-40, 70), alpha=0.35),
        R("chassis", -122.0, 89.0, -46.0, 54.0, alpha=0.0, dashed=True),
        *[R("chassis", x, x + 10.0, y0, y1) for x in (-80.0, 40.0) for (y0, y1) in ((-48.4, -45.0), (53.0, 56.4))],
        *body_top(label=None), *lip_top(), *packets_top(), *crank_mech_top(),
    ]
    support = [(-125.0, 92.0, -48.4, -46.0), (-125.0, 92.0, 54.0, 56.4), (-125.0, -122.6, -46.0, 54.0), (89.6, 92.0, -46.0, 54.0)]
    loads = [(x, FLOOR[0], BASE[0], "fixed") for x in (-115.0, -20.0, 75.0)]
    motions = [((-150.0, -40.0), (-150.0, -21.0), "cover snaps on from below", (-158, -48)),
               ((121.0, 15.0), (98.0, 15.0), "press 23 mm", (104, 19))]
    notes = [(-158.0, 50.0, "print standing on\nthe −X end")]
    return Concept("04", "one-piece-tub", "One-piece tub with a snap-on bottom cover",
                   "Magazine, floor, guides and stops are one print; nothing structural can shift between them.",
                   side, top, BASE[0], loads, motions, notes=notes, support=support)


def syringe_slider():
    tz = -8.4
    side = [
        R("housing", -100.0, 88.0, tz, FLOOR[0], "side skirts (behind)", at=(40, 26), alpha=0.3),
        R("housing", -100.0, -92.0, 0.0, 24.0, "finger wings (±Y)", at=(-130, 50)),
        R("pusher", -150.0, -83.0, *CARRIAGE, "slider = button + pusher, one part", at=(-60, -26)),
        R("pusher", -91.1, -87.0, CARRIAGE[1], 4.2),
        R("pusher", -158.0, -150.0, tz + 0.4, 22.0, "thumb plate", at=(-140, 34)),
        R("spring", -82.0, 30.0, -6.4, -3.2, "2 serpentines (y=±20), compressed 50 mm", at=(40, -20), alpha=0.7),
        R("housing", 30.0, 34.0, -6.8, FLOOR[0], "spring stops", at=(60, -30)),
        *body_side(x0=-100.0), *lip_side(), *packets_side(),
    ]
    top = [
        R("housing", -100.0, -92.0, -60.0, -OY, "wings", at=(-120, -80)),
        R("housing", -100.0, -92.0, OY, 60.0),
        *body_top(x0=-100.0), *lip_top(), *packets_top(),
        R("pusher", -150.0, -83.0, -25.0, 25.0, "slider", at=(-150, 50), alpha=0.85),
        R("pusher", -91.1, -87.0, -20.0, 20.0),
        R("pusher", -158.0, -150.0, -30.0, 30.0),
        R("spring", -82.0, 30.0, 15.0, 25.0, "springs", at=(10, 52)),
        R("spring", -82.0, 30.0, -25.0, -15.0),
        R("housing", 30.0, 34.0, 15.0, 25.0),
        R("housing", 30.0, 34.0, -25.0, -15.0),
    ]
    support = [(-100.0, 88.0, -OY, -30.0), (-100.0, 88.0, 30.0, OY)]
    loads = [(x, FLOOR[0], tz, "fixed") for x in (-95.0, -10.0, 80.0)]
    motions = [((-154.0, 26.0), (-104.0, 26.0), "thumb squeezes 50 mm", (-150, 29)),
               ((-87.0, 7.0), (-37.0, 7.0), "pusher 50 mm", (-75, 10))]
    top_motions = [((-154.0, 0.0), (-104.0, 0.0), "squeeze")]
    notes = [(-158.0, 70.0, "hand reacts the force\n(syringe grip): nothing\npushes the unit along the table")]
    return Concept("05", "syringe-direct-slider", "Syringe grip: the button is the pusher",
                   "One sliding part, no crank, no rod. Thumb on the plate, fingers on the wings.",
                   side, top, tz, loads, motions, top_motions=top_motions, notes=notes, support=support)


LEVER_PIVOT = (-150.0, 64.0)
LEVER_IN = 30.0  # pivot to paddle centre
LEVER_SWING = 55.0  # degrees for 50 mm at the 61 mm output arm


def _lever_pts(theta_deg):
    """Bell crank about the pivot: input arm to -X, output arm down to z = 3. CCW positive."""
    px, pz = LEVER_PIVOT
    h = 4.0
    xin = px - LEVER_IN - 6.0
    base = [(xin, pz + h), (px + h, pz + h), (px + h, 3.0), (px - h, 3.0), (px - h, pz - h), (xin, pz - h)]
    t = math.radians(theta_deg)
    return [(px + (x - px) * math.cos(t) - (z - pz) * math.sin(t),
             pz + (x - px) * math.sin(t) + (z - pz) * math.cos(t)) for x, z in base]


def rear_bell_crank():
    """The ram fin starts 50 mm + clearance behind the back wall so it never reaches it."""
    tz = FLOOR[0]
    px, pz = LEVER_PIVOT
    paddle = (px - LEVER_IN - 6.0, px - LEVER_IN + 6.0)
    drop = LEVER_IN * math.sin(math.radians(LEVER_SWING))
    side = [
        R("housing", -192.0, 88.0, *FLOOR),
        R("housing", px - 7.0, px + 7.0, 0.0, 70.0, "tower cheeks (y=±20)", at=(-120, 40), alpha=0.45),
        P("crank", _lever_pts(0.0), "bell-crank lever, 2:1", at=(-110, 84)),
        P("crank", _lever_pts(LEVER_SWING), alpha=0.0, dashed=True),
        C("crank", px, pz, 3.0),
        R("crank", paddle[0], paddle[1], pz, pz + 6.0, "press paddle", at=(-188, 86)),
        R("pusher", px - 5.0, -87.0, 0.2, 4.2, "ram on the floor, enters back notch", at=(-60, -20)),
        R("pusher", px - 5.0, px + 5.0, 0.2, 32.0, "fin with slot for lever pin", at=(-120, -12)),
        R("spring", px + 4.0, px + 8.0, pz + 2.0, pz + 12.0, "leaf spring on lever", at=(-110, 70)),
        *body_side(x0=-192.0), *lip_side(), *packets_side(),
    ]
    top = [
        *body_top(x0=-192.0, label="flat floor on the table"), *lip_top(), *packets_top(),
        R("housing", px - 7.0, px + 7.0, 18.0, 22.0, "cheeks", at=(-170, 50)),
        R("housing", px - 7.0, px + 7.0, -22.0, -18.0),
        R("pusher", px - 5.0, -91.0, -15.0, 15.0, "ram (fits between cheeks)", at=(-60, -55), alpha=0.85),
        R("pusher", -91.0, -87.0, -20.0, 20.0),
        R("crank", paddle[0], px + 4.0, -4.0, 4.0, "lever", at=(-170, -55)),
        R("crank", paddle[0], paddle[1], -15.0, 15.0),
    ]
    support = [(-192.0, 88.0, -OY, OY)]
    loads = [(x, FLOOR[1], tz, "fixed") for x in (-170.0, -60.0, 20.0, 80.0)]
    motions = [((px - LEVER_IN, 80.0), (px - LEVER_IN, 80.0 - drop), f"press {drop:.0f} mm down", (-198, 50)),
               ((-87.0, 9.0), (-37.0, 9.0), "ram 50 mm", (-70, 12))]
    notes = [(-40.0, -12.0, "no basement: the floor is on the table")]
    return Concept("06", "rear-bell-crank", "Rear tower bell crank, flat-bottom body",
                   "No basement at all. The floor sits on the table; a lever on a rear tower drives a ram through the back notch.",
                   side, top, tz, loads, motions, notes=notes, support=support, xlim=(-200.0, 155.0))


def gear_reverser():
    side = [
        R("housing", -100.0, 92.0, BASE[0], FLOOR[0], "side skirts (behind)", at=(40, 26), alpha=0.3),
        R("housing", -100.0, 92.0, *FLOOR),
        R("chassis", -98.0, 90.0, BASE[0] + 1.0, BASE[1], "mechanism plate", at=(60, -34)),
        R("chassis", -53.0, -47.0, BASE[1], CRANK[1]),
        R("rod", -75.0, 128.0, *ROD, "rod with rack", at=(20, -42)),
        R("rod", 114.0, 128.0, ROD[1], 12.0, "button", at=(140, 4)),
        R("crank", -60.0, -40.0, *ROD, "pinion r10", at=(-140, -36), alpha=0.95),
        R("crank", -71.7, -28.3, *CRANK, "gear r21.7 (same part)", at=(-150, -20), alpha=0.95),
        R("pusher", -108.0, -44.0, *CARRIAGE, "pusher + rack", at=(-140, 10)),
        R("pusher", -108.0, -44.0, CRANK[0] + 0.4, CRANK[1], alpha=0.5),
        R("pusher", -91.1, -87.0, CARRIAGE[1], 4.2),
        R("spring", -30.4, 20.0, -16.6, -11.6, "spring beside rod", at=(-10, -46), alpha=0.6),
        R("chassis", 12.9, 16.9, -18.0, -12.0),
        R("chassis", 85.05, 88.0, -18.0, -9.0),
        *body_side(x0=-100.0, x1=92.0), *lip_side(), *packets_side(),
    ]
    top = [
        R("housing", -100.0, 92.0, -51.0, 34.8, "body plinth", at=(-40, 66), alpha=0.35),
        *body_top(x0=-100.0, x1=92.0, label=None), *lip_top(), *packets_top(),
        R("rod", -75.0, 128.0, -33.0, -23.0, "rod rack", at=(40, -70)),
        R("rod", 114.0, 128.0, -42.0, -28.0),
        C("crank", -50.0, -13.0, 21.7, "compound gear", at=(-150, 40), alpha=0.8),
        C("crank", -50.0, -13.0, 10.0),
        R("pusher", -108.0, -44.0, -4.0, 14.0, "pusher rack", at=(-150, -60), alpha=0.85),
        R("pusher", -91.1, -87.0, -20.0, 20.0),
        R("spring", -30.4, 20.0, -47.0, -34.0, "spring", at=(40, -92)),
    ]
    support = [(-100.0, 92.0, -51.0, -48.6), (-100.0, 92.0, 32.4, 34.8)]
    loads = [(x, FLOOR[0], BASE[0], "fixed") for x in (-90.0, 0.0, 80.0)]
    motions = [((121.0, 15.0), (98.0, 15.0), "press 23 mm", (104, 19)),
               ((-87.0, 7.0), (-37.0, 7.0), "pusher 50 mm", (-75, 10))]
    return Concept("07", "rack-pinion-reverser", "Rack, compound gear, rack",
                   "Replaces the crank with a stacked gear: constant 2.17:1 ratio and natural direction reversal.",
                   side, top, BASE[0], loads, motions, support=support)


def compliant_crank():
    side = [
        R("chassis", -125.0, 92.0, *BASE, "chassis + rails as 01", at=(60, -34)),
        R("chassis", -25.0, 88.0, BASE[1], FLOOR[0], "rails (behind)", at=(40, 26), alpha=0.35),
        R("chassis", -90.0, -66.0, ROD[0], ROD[1], "anchor (printed with crank)", at=(-150, -44)),
        R("rod", -71.0, 128.0, *ROD, "button rod", at=(20, -30)),
        R("rod", 114.0, 128.0, ROD[1], 12.0, "button", at=(140, 4)),
        R("rod", 81.0, 85.0, -18.0, ROD[1]),
        R("crank", -105.0, -86.0, *CRANK, "crank", at=(-135, -26)),
        R("crank", -70.0, -62.0, *CRANK),
        R("spring", -86.0, -70.0, *CRANK, "cross-leaf flexure = pivot + spring", at=(-40, -24)),
        R("crank", -106.0, -100.0, CRANK[1], CARRIAGE[1]),
        R("rod", -69.5, -63.5, ROD[1], CRANK[1]),
        R("pusher", -111.0, -83.0, *CARRIAGE, "pusher", at=(-140, 10)),
        R("pusher", -91.1, -87.0, CARRIAGE[1], 4.2),
        R("chassis", 85.05, 88.0, -18.0, -9.0),
        R("chassis", 12.9, 16.9, -18.0, -12.0),
        *body_side(), *lip_side(), *packets_side(),
    ]
    leaves = []
    for ang in (35.0, -35.0):
        ux, uy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        nx, ny = -uy * 0.6, ux * 0.6
        a = (PIVOT[0] - 12.5 * ux, PIVOT[1] - 12.5 * uy)
        b = (PIVOT[0] + 12.5 * ux, PIVOT[1] + 12.5 * uy)
        leaves.append(P("spring", [(a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny), (b[0] - nx, b[1] - ny), (a[0] - nx, a[1] - ny)]))
    leaves[0].label, leaves[0].at = "crossed leaves 25×1.0", (-150, -40)
    top = [
        R("chassis", -125.0, 92.0, -50.0, 53.0, alpha=0.25),
        R("chassis", -45.0, 88.0, -48.0, -44.0, "rails", at=(20, -94)),
        R("chassis", -25.0, 88.0, 34.0, 38.0),
        *body_top(), *lip_top(), *packets_top(),
        R("rod", -71.0, 128.0, -33.0, -23.0, "rod", at=(40, -62)),
        R("rod", 114.0, 128.0, -42.0, -28.0),
        P("crank", crank_poly(a=32.4, b=54.4), "crank, no bore", at=(-150, 40)),
        R("chassis", -96.0, -84.0, -20.0, -14.0, "anchor", at=(-150, -70)),
        *leaves,
        R("pusher", -111.0, -83.0, -8.0, 50.0, "carriage", at=(-150, 64), alpha=0.85),
        R("pusher", -91.1, -87.0, -20.0, 20.0),
    ]
    support = [(-45.0, 88.0, -48.0, -44.0), (-25.0, 88.0, 34.0, 38.0)]
    loads = [(x, FLOOR[0], BASE[1], "fixed") for x in (-15.0, 30.0, 75.0)] + \
            [(x, BASE[0] + 3.4, BASE[0], "fixed") for x in (-100.0, 90.0)]
    motions = [((121.0, 15.0), (98.0, 15.0), "press 23 mm", (104, 19)),
               ((-87.0, 7.0), (-37.0, 7.0), "pusher 50 mm", (-75, 10))]
    return Concept("08", "compliant-crank", "Compliant crank: the flexure is the pivot and the spring",
                   "No pivot pin and no separate spring; the crank twists on crossed PETG leaves that pull it home.",
                   side, top, BASE[0], loads, motions, support=support)


CONCEPTS = [baseline, seated_rails, standoffs_latches, body_is_base, one_piece_tub,
            syringe_slider, rear_bell_crank, gear_reverser, compliant_crank]


# -------------------------------------------------------------------- drawing

def _patch(s: Shape):
    color = COLORS[s.role]
    kw = dict(facecolor=color, alpha=None, edgecolor="#222222", linewidth=0.6)
    if s.dashed:
        kw.update(linestyle="--", linewidth=0.9, edgecolor=COLORS["packet"] if s.role == "packet" else "#444444")
    if s.alpha < 1.0:
        kw["facecolor"] = matplotlib.colors.to_rgba(color, s.alpha)
    if s.kind == "rect":
        x0, x1, a0, a1 = s.geom
        return Rectangle((x0, a0), x1 - x0, a1 - a0, **kw), ((x0 + x1) / 2, (a0 + a1) / 2), (x1 - x0, a1 - a0)
    if s.kind == "poly":
        xs = [p[0] for p in s.geom]
        ys = [p[1] for p in s.geom]
        return Polygon(s.geom, closed=True, **kw), (sum(xs) / len(xs), sum(ys) / len(ys)), (max(xs) - min(xs), max(ys) - min(ys))
    cx, cy, r = s.geom
    return Circle((cx, cy), r, **kw), (cx, cy), (2 * r, 2 * r)


def draw_shapes(ax, shapes, labels=True):
    for s in shapes:
        patch, center, (w, h) = _patch(s)
        ax.add_patch(patch)
        if not labels or not s.label:
            continue
        if s.at is None:
            ax.text(*center, s.label, fontsize=LABEL_FS, ha="center", va="center")
        else:
            ax.annotate(s.label, xy=center, xytext=s.at, fontsize=LABEL_FS, ha="center", va="center",
                        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8),
                        arrowprops=dict(arrowstyle="-", color="#555555", lw=0.5))


def draw_table(ax, z, x0, x1):
    ax.add_patch(Rectangle((x0, z - 5.0), x1 - x0, 5.0, facecolor="white", edgecolor="#444444", hatch="////", lw=0.8))
    ax.text(x1 - 2, z - 2.5, "table", fontsize=LABEL_FS, ha="right", va="center",
            bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none"))


def draw_side(ax, c: Concept, labels=True):
    draw_table(ax, c.table_z, *c.xlim)
    draw_shapes(ax, c.side, labels)
    for x, z0, z1, kind in c.loads:
        color = LOAD_FIXED if kind == "fixed" else LOAD_MOVING
        ax.annotate("", xy=(x, z1), xytext=(x, z0 + 5.0),
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=2.2, mutation_scale=10))
    for (x0, z0), (x1, z1), text, txy in c.motions:
        ax.annotate("", xy=(x1, z1), xytext=(x0, z0),
                    arrowprops=dict(arrowstyle="-|>", color=MOTION, lw=1.8, mutation_scale=11))
        if labels:
            ax.text(*txy, text, fontsize=LABEL_FS, color=MOTION, ha="left", va="bottom", fontweight="bold")
    if labels:
        for x, z, text in c.notes:
            ax.text(x, z, text, fontsize=LABEL_FS, ha="left", va="top", style="italic",
                    bbox=dict(boxstyle="round,pad=0.25", fc="#fff8dc", ec="#bbbbbb", lw=0.5))
    ax.set_xlim(*c.xlim)
    ax.set_ylim(min(-50, c.table_z - 8), 92)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=6)
    ax.grid(True, lw=0.3, alpha=0.4)


def draw_top(ax, c: Concept):
    for x0, x1, y0, y1 in c.support:
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor=matplotlib.colors.to_rgba(LOAD_FIXED, 0.10),
                               edgecolor=LOAD_FIXED, hatch="//", lw=1.0, zorder=5))
    draw_shapes(ax, c.top)
    for (x0, y0), (x1, y1), text in c.top_motions:
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                    arrowprops=dict(arrowstyle="-|>", color=MOTION, lw=1.8, mutation_scale=11), zorder=6)
    ax.plot(*c.com, marker="x", color="black", ms=8, mew=2, zorder=7)
    ax.text(c.com[0] + 3, c.com[1] + 3, "body COM (est.)", fontsize=LABEL_FS, zorder=7)
    ax.set_xlim(*c.xlim)
    ax.set_ylim(-100, 78)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=6)
    ax.grid(True, lw=0.3, alpha=0.4)


def legend_handles():
    names = {
        "housing": "body / magazine", "lip": "lip, shelf, separator", "chassis": "chassis / base / fixed plate",
        "crank": "crank / rotating link", "rod": "button input", "pusher": "pusher / ram / slider",
        "packet": "packets", "spring": "spring / flexure", "peg": "separate headed peg",
    }
    h = [Patch(facecolor=COLORS[k], edgecolor="#222222", label=v) for k, v in names.items()]
    h += [
        Line2D([], [], color=LOAD_FIXED, lw=2.2, marker=">", label="weight via fixed structure"),
        Line2D([], [], color=LOAD_MOVING, lw=2.2, marker=">", label="weight via a MOVING part"),
        Line2D([], [], color=MOTION, lw=1.8, marker=">", label="button / pusher motion"),
        Patch(facecolor=matplotlib.colors.to_rgba(LOAD_FIXED, 0.10), edgecolor=LOAD_FIXED, hatch="//",
              label="fixed support contact (top view)"),
    ]
    return h


def render(c: Concept):
    fig = plt.figure(figsize=(12, 12.5))
    gs = fig.add_gridspec(2, 1, height_ratios=[150, 178], hspace=0.12, left=0.05, right=0.98, top=0.92, bottom=0.11)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1])
    draw_side(ax1, c)
    draw_top(ax2, c)
    ax1.set_title("Side section X-Z at y = 0 (mm)  — parts behind the section drawn faint", fontsize=8, loc="left")
    ax2.set_title("Top view X-Y (mm)", fontsize=8, loc="left")
    fig.suptitle(f"{c.num}  {c.title}", fontsize=13, fontweight="bold", x=0.05, ha="left", y=0.975)
    fig.text(0.05, 0.945, c.tagline, fontsize=9, ha="left")
    fig.text(0.98, 0.975, "UNTESTED CONCEPT — mockup, not CAD", fontsize=9, color="#b2182b", ha="right", fontweight="bold")
    fig.legend(handles=legend_handles(), loc="lower center", ncol=5, fontsize=7, frameon=False, bbox_to_anchor=(0.5, 0.01))
    path = OUT / f"{c.num}-{c.slug}.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def render_overview(concepts):
    fig, axes = plt.subplots(3, 3, figsize=(16, 9.5))
    for ax, c in zip(axes.flat, concepts):
        draw_side(ax, c, labels=False)
        ax.set_title(f"{c.num}  {c.title}", fontsize=8.5, fontweight="bold")
        ax.tick_params(labelsize=5)
    fig.suptitle("Pocky prototype mockups — side sections (UNTESTED CONCEPTS)", fontsize=13, fontweight="bold")
    fig.legend(handles=legend_handles(), loc="lower center", ncol=7, fontsize=7, frameon=False)
    fig.subplots_adjust(left=0.03, right=0.99, top=0.92, bottom=0.08, wspace=0.08, hspace=0.25)
    path = OUT / "overview.png"
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def main():
    concepts = [make() for make in CONCEPTS]
    for c in concepts:
        print(render(c))
    print(render_overview(concepts))


if __name__ == "__main__":
    main()
