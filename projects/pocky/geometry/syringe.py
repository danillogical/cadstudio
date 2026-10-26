"""Syringe dispenser: housing on four pop-in legs, slider with two arms, clip-on PULL handle, printed spring.

The slider is a frame around the housing. Its pusher plate sits behind the
bottom packet, enters the bore through a slot at the foot of the rear wall,
and is carried by a yoke behind the rear wall. Two arms run forward outside
the side walls on V rails and end in two legs beside the shelf. The handle is
a separate flat U: a bar hanging low in front of the shelf, two runners, and
a T-slide tail at each runner's back end that clips into a socket in each
leg. Pulling the bar toward you (+X) pushes the bottom packet out of the exit.
The housing's floor is a slab; four separate legs (parts ``leg_1`` .. ``leg_4``)
snap into sockets in its underside and stand it on the table. "Legs" alone
below means the slider's legs; the housing's are "housing legs".

Assembly coordinates as the prototype: X is the packet long axis with the exit
at +X, Z is up, the bottom packet's underside is z=0, and the packet is centred
at x=y=0.

Z layout, bottom to top:

* z = -52: the table (``TABLE_Z``). The housing legs' foot pads stand on it,
  so the packet plane stands 52 mm above the table.
* z = -49.6 .. -13.05: housing leg columns, under the slab's four corners.
* z = -37 .. -27: handle bar and runners, 15 mm above the table so fingers can
  curl under the bar, and 2 mm under the hand keep-out zone.
* z = -13 .. 0: the floor slab (``slab_z0``): the spring channel with a 2.4 mm
  wall under it, as deep as the yoke so the yoke's whole front face stops on it.
* z = -13 .. 4.3: arms and yoke, on the V rails at z = -4.5 .. 1.5.
* z = -10.3 .. -5.3: return spring, in a channel in the floor under the stack.
* z = -2.4 .. 0: the two channel lips' tips, flush with the floor top.
* z = 0: floor top. z = 0.3 .. 4.3: pusher plate, in a 4.6 mm rear slot.
* z = 5.75: separator blade underside (``separator.gap``); with the wedge
  separator, the exit wall's lower edge (the window top) instead.
* z = 0 .. 4.8: wedge separator only, the two side funnel wedges.

Separator variants (``separator=`` on ``syringe_layout`` and ``syringe_solids``):

* ``"blade"``: a 2.4 mm blade under the exit wall reaches 2 mm back
  over the bottom packet's front edge, so packets 2..N rest tilted on its rear
  edge.
* ``"wedge"`` (default): no blade. The window is a plain 5.75 mm opening in the 3 mm exit
  wall, which already passes only one 5.2 mm packet, and nothing overhangs the
  stack behind the wall's inner face (x=85), so the packets stack flat and
  packet 2's front face meets the wall above the window. A funnel wedge on the
  inside of each side wall narrows the bore from 60 mm to 55.6 mm (0.3 mm a
  side for the 55 mm packet) over the 18 mm before the exit wall, 7 deg to X,
  and runs on through the window. The wedges stop at z=4.8, under packet 1's
  top, so they never touch packet 2 while packet 1 is there. Their inner top
  edge is a 45 deg chamfer, so a packet that drops onto a wedge slides inward.

Hand keep-out (``hand_keepout``): with the slider home and a packet presented
(leading edge at x=128), the box x 106..148, |y| <= 47.5, z -25..30.2 around
the packet's exposed part holds only the packet. The housing and its legs end
at the shelf (x=106), the legs end at x=100, and the bar and runners stay
under z=-27 at every stroke fraction. The arms, legs and the handle's tails inside the legs do
cross the zone while the slider is pulled, when the hand is on the bar and no
packet is presented yet.

Why raise the dispenser rather than move the bar elsewhere: a bar in front of
the zone (x > 148) needs arms through the zone or wider than |y| = 47.5, and a
bar over the housing blocks loading the magazine. Moving the table down keeps
z=0 at the packet plane, so the exit plane and the presentation criteria stand.

Housing legs: a 16 mm column on a 20 mm x 2.4 mm foot pad, 39 mm from the
table to the slab, under each corner of the slab (axes at x = -77.4 and 96,
y = +-22.4), each pad's edge flush with the slab's end and side. The housing
is 233.3 cm^3 (296 g) and the four legs 32.6 cm^3 (41 g); a solid base filling
the table-to-slab space instead would make the housing 723.7 cm^3 (919 g).
Nothing else is under the slab: the slider's
arms and yoke stay at z >= -13 and its legs, the handle's runners and tails at
|y| >= 32.75, outside the housing legs (|y| <= 30.4 for the columns, the pads
under z=-49.6 below everything that moves), and the yoke at full stroke stops
at x = -87.45, behind the rear columns (x >= -85.4). The spring and keel run in
the channel at |y| <= 7.5, clear of the sockets (|y| >= 18.7).

Leg joint: a split snap pin on each column top pops into a blind socket in the
slab underside. The pin is 6.5 mm square, split by a 1.2 mm slot into two flat
prongs 2.65 mm thick; a 0.25 mm ridge across each prong's outer face clicks
into a groove in the socket wall. Square, so each prong section is a rectangle
with no edge thinner than the 2.4 mm wall (a split round pin has knife edges
where the slot meets the circle). The socket is the pin offset by 0.05 mm
everywhere (bore, groove and the vault over the tops), so seated the leg
touches nothing, and the column top stops 0.05 mm under the slab
(``STOP_EPS``, as the other stops); the housing's weight closes that gap and
bears on the column top. The groove runs round all four walls, so the leg goes
in at any quarter turn. Pushing in, each ridge meets the bore with 0.2 mm of
interference: the prongs flex inward into the slot, which is the press. The
prongs root 3 mm down a round well about the pin, so they are 8.5 mm long to
the ridge and the 0.2 mm deflection strains them 1.1% (eps = 1.5 t y / L^2).
With PETG at E = 2 GPa and friction 0.3 that is about 42 N to push a leg in
over the 60 deg lead-in flank and 60 N to pull it out over the 50 deg
retaining flank, against a 10 g leg: the legs stay when the dispenser is
lifted, and a firm pull takes one off. No screws or glue.

Tipping, unheld: the pull acts at the bar's mid-height, 20 mm over the table,
so 30 N overturns about the front feet's edge (x=106) with 0.60 N*m. The whole
dispenser (housing 296 g, slider and handle 123 g, spring 3 g, legs 41 g,
464 g; centre of mass at x=8.9) restores 4.55 N x 97 mm = 0.44 N*m empty and
0.51 N*m with 10 packets (534 g): a margin of 0.74 to 0.86, so it tips at
22 to 26 N if the feet do not slide. They do slide first: table friction
(0.5 x W = 2.3 to 2.6 N) is under a tenth of the pull. Weight would not fix
that: with a solid base under the slab (1.05 to 1.12 kg in all) it would slide
at 5.1 to 5.5 N and tip at 50 to 53 N. So the dispenser is held or clamped
while pulled, as the passing case assumes.

Printability:

* Housing: stands on the slab underside (z=-13 on the bed). The floor top
  needs no bridge, as the slab is solid under it (print with sparse infill).
  The four leg sockets are blind holes opening on the bed face, printed
  upright: their ceilings are vaults of 50 deg faces (no bridge), the
  groove's upper flank is 60 deg from horizontal and its lower flank faces up,
  and the mouth has a 0.4 mm lead-in chamfer at 60 deg that also takes up
  elephant's foot.
  The rails' lower flanks are 50 deg from horizontal and the
  shelf nose is a radius. The spring channel's two lips have undersides 50 deg
  from horizontal, rising from the channel wall to the tip, so they grow out of
  the wall without support, and the slot between them stays open (no bridge).
  The one bridge is the exit wall and blade
  over the 60 mm exit window (the exit wall alone with the wedge separator).
  The wedges have vertical faces and an upward-facing chamfer, so they print
  upright without support.
* Housing legs: standing, foot pad on the bed, pin up, as assembled. Every
  face rises straight up or faces up (pad top, column top, well floor, slot
  floor, prong tops) except the ridge's retaining flank, 50 deg from
  horizontal. No support, no bridge. The four legs are identical; the model
  exports each (``leg_1`` .. ``leg_4``) so a slicer plate can take all four, or
  any one with four copies.
* Slider: upside down on the plane z=4.3 that the plate, yoke, arms and legs
  share. Every face rises straight from the bed except the rail grooves (50 deg
  flanks) and the detent groove in each socket (50 and 60 deg flanks). The
  sockets open upward in this pose, so there is no bridge at all.
* Handle: flat, as assembled, bottom face on the bed and the PULL face up. The
  text is debossed 0.8 mm into the bar's top face: an upward-facing recess
  prints crisp walls with no overhang, and it can be painted. Embossed text on
  top would print as well but snags fingers and is harder to paint cleanly.
  The bar's top edges are 2 mm radii (upward-facing); its bottom edges are
  chamfers 50 deg from horizontal; the detent ridge's lower flank is 50 deg.
  Nothing on the handle needs support and nothing is bridged.
* Splitting the handle off is what makes the low bar printable: in the
  slider's upside-down pose a one-piece U hanging 40 mm under the arms would
  be a cantilevered overhang, and right side up the rail grooves and the plate
  would need support.
* Spring: lies flat, as in the prototype.

Handle joint: a vertical T-slide at each leg, 0.25 mm clearance all round. A
4 mm neck passes through a slot in the leg's front face and a 9 mm head sits
in a socket behind it, so the pull is carried by the head's square shoulders
in bearing against the leg's 3 mm jaws: pulling cannot open the joint, it can
only come apart by sliding straight down. The two joints are mirror images, so
the pull splits evenly between the arms. The handle goes on from below until
the tail tops hit the socket ceilings (the positive stop), and a ridge on a
flexing leaf at the back of each head clicks into a groove in the socket back
wall to hold it there (0.55 mm interference while sliding; the 50 deg lower
flank lets a firm pull down take the handle off). No screws, inserts or glue.
A square T-slide rather than a dovetail: the shoulders take the pull with no
wedge play, and a dovetail's acute corners are thinner than the 2.4 mm wall.
Fit the slider on the housing first, then push the handle up onto the legs
with the housing lifted off the table (on its housing legs the bar is 15 mm
over the table, too little to slide the tails in). The bar sits about 30 mm under the
rails, so the pull also pitches the slider; the V rails take that couple.

Spring channel: the 14 mm spring lies in a 15 mm channel in the floor, from
the rear face to the seat. Two lips flush with the floor top run its whole
length and overhang each long edge of the spring by 2 mm, so nothing above
(an empty magazine, the spring bowing under compression) lets it lift out:
the spring top sits 0.5 mm under the lip underside at its edge. The keel, the
slider web that pushes the spring's rear pad, is 9.3 mm wide, centred on the
pad over its full 5 mm height, and runs in the 10 mm slot between the lip tips
with 0.35 mm a side.

Assembly order:

1. With the housing upside down, push a leg's pin into each socket until it
   clicks. The legs sit wholly under the slab, inside the slider's frame, so
   they never get in the way of the steps below.
2. Slide the spring into the channel from the open rear end, seat pad first,
   until the seat pad stops on the seat. It cannot drop in from the top any
   more. Its free rear pad stands about 3 mm proud of the rear face.
3. Hold that pad 3 mm in (the preload) and fit the slider at rest. At rest the
   keel lies wholly behind the rear face, so it never has to pass through the
   lips: it sits behind the pad and enters the slot from the rear as the slider
   moves forward. The yoke then closes the channel's rear end. At full stroke
   the yoke's front face stops on the slab's rear face and the rear wall
   (0.05 mm of air at the CAD stroke, ``STOP_EPS``).
4. Push the handle onto the legs, as above.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from build123d import (
    Align,
    Axis,
    Cylinder,
    FontStyle,
    Location,
    Plane,
    Polygon,
    Pos,
    RectangleRounded,
    Rot,
    Text,
    extrude,
    fillet,
)

from projects.pocky.geometry.linkage import EXIT_WALL, FACE_W, STOP_EPS, _box, on_bed
from projects.pocky.geometry.prototype import (
    BLADE_BITE,
    BLADE_T,
    CHEEK_TOP,
    EDGE_R,
    LIP_LEN,
    PRELOAD,
    PROTOTYPE_SPRING,
    SpringSpec,
    _cut,
    _fuse,
    _round_lower_edge,
    spring_solid,
)
from projects.pocky.params import Params

# Presentation, from the frozen acceptance: leading edge 30 mm past the exit
# face is the minimum, 40 mm is the target, and 10 mm must clear the shelf end.
MIN_PROTRUSION = 30.0
TARGET_PROTRUSION = 40.0
MIN_PAST_SHELF = 10.0

# Sliding clearance per side between the slider and the housing.
SLIDE_CLEAR = 0.35
# Pusher plate band and the rear slot it runs in (0.3 mm above and below).
PLATE_Z0 = 0.3
PLATE_H = 4.0
SLOT_H = 4.6
PLATE_W = FACE_W  # 40, as the prototype bullnose
# At rest the plate face is this far behind the rear wall's outer face, so the
# bore and the slot are empty and the slider can be lowered on from above.
PARK = 0.1

# The table sits 52 mm under the packet plane so the bar can hang below the hand zone.
# The housing stands on four legs; its floor is a slab (``SyringeLayout.slab_z0``).
TABLE_Z = -52.0
SLIDER_TOP = PLATE_Z0 + PLATE_H  # 4.3, the slider's print face
ARM_Z0 = -13.0
ARM_T = 4.65  # in Y; leaves 2.65 mm behind the rail groove
YOKE_T = 8.0

# Hand keep-out around the presented packet's exposed part (see ``hand_keepout``).
KEEPOUT_MARGIN = 20.0  # past the packet tip and beside its long edges
KEEPOUT_Z_MARGIN = 25.0  # under and over the packet

# Handle bar, at rest. Its top is 2 mm under the keep-out floor (z=-25) and its
# underside 15 mm over the table, so fingers can curl under and behind it. The
# back face is 24 mm in front of the shelf end, the finger room behind the bar.
BAR_Z1 = -27.0
BAR_Z0 = BAR_Z1 - 10.0
BAR_X0 = 130.0
BAR_D = 14.0  # in X; the top face carries the PULL text
BAR_TOP_R = 2.0  # top edge radius
BAR_CHAMFER = 1.0  # bottom edge chamfer, horizontal leg; 50 deg from horizontal
BAR_END_R = 4.0  # plan-view radius at the bar's ends

# Debossed PULL on the bar's top face: Arial Bold, 7 mm caps, 0.8 mm deep.
PULL_TEXT = "PULL"
PULL_CAP_H = 7.0
PULL_CAP_PER_SIZE = 0.728  # Arial Bold cap height per unit font size
PULL_DEPTH = 0.8

# Legs: the arms' front ends, widened outward and dropped to the bar level.
# Their front face stays 6 mm behind the shelf end, outside the keep-out zone.
LEG_X0 = 84.0
LEG_X1 = 100.0
LEG_W = 14.8  # in Y, from the arm's inner face outward

# Vertical T-slide between each leg (socket) and the handle (tail): a neck
# through the leg's front face and a wider head behind it. Square shoulders
# carry the pull in bearing and keep every corner at 90 deg.
JOINT_CLEAR = 0.25
NECK_L = 3.0  # in X; also the leg's jaws in front of the head
NECK_HW = 2.0
HEAD_L = 6.0  # in X: leaf, leaf slot and a 2.4 mm front block
HEAD_HW = 4.5
TAIL_TOP = -19.0  # 18 mm of engagement above the handle's underside
# Detent: a leaf at the head's back, free above LEAF_ROOT_Z, with a ridge on its back face.
LEAF_T = 2.4
LEAF_SLOT = 1.2
LEAF_ROOT_Z = BAR_Z0 + 4.0
RIDGE_H = 0.8  # proud of the leaf; 0.55 mm interference with the socket wall
RIDGE_Z = -22.0  # ridge tip height
RIDGE_LOW_DEG = 50.0  # retaining flank, faces down in the handle's print pose
RIDGE_UP_DEG = 60.0  # lead-in flank
RIDGE_INSET = 0.3  # ridge ends short of the head's sides

# V rail on each side wall. Flanks are 50 deg from horizontal, so the lower
# flank on the housing and the matching groove face on the upside-down slider
# both stay under the 45 deg overhang limit.
RAIL_ZC = -1.5
RAIL_HALF = 3.0  # root half-height
RAIL_D = 2.0  # depth out of the wall
RAIL_DEG = 50.0
RAIL_X = (-75.0, 75.0)

# Spring channel in the floor, under the stack. Spring folds stay 0.5 mm off
# the channel walls and 0.2 mm off its floor, as the prototype spring pocket.
SPRING_WALL_CLEAR = 0.5
CHANNEL_HALF_W = PROTOTYPE_SPRING.amplitude / 2.0 + SPRING_WALL_CLEAR  # 7.5
# Two lips, flush with the floor top, close the channel over the spring's long
# edges so it cannot lift out; the keel runs in the slot between their tips.
LIP_OVER = 2.0  # overhang across each long edge of the spring
LIP_T = 2.4  # thickness at the tip, the structure min_wall
LIP_DEG = 50.0  # underside from horizontal, so the upright housing prints it without support
LIP_CLEAR = 0.5  # spring top to lip underside, vertically, at the spring's long edge
LIP_SLOT_HALF_W = PROTOTYPE_SPRING.amplitude / 2.0 - LIP_OVER  # 5.0
_LIP_TAN = math.tan(math.radians(LIP_DEG))
# Lip underside where it meets the channel wall (-5.38); it rises 50 deg to the tip at -LIP_T.
LIP_ROOT_Z = -(LIP_T + (CHANNEL_HALF_W - LIP_SLOT_HALF_W) * _LIP_TAN)
SPRING_Z0 = -(LIP_T + LIP_OVER * _LIP_TAN + LIP_CLEAR) - PROTOTYPE_SPRING.height  # -10.28
CHANNEL_Z0 = SPRING_Z0 - 0.2
# The keel is narrower than the spring: it clears each lip tip by SLIDE_CLEAR.
KEEL_HALF_W = LIP_SLOT_HALF_W - SLIDE_CLEAR  # 4.65
# Variant B closes 79% of each gap at full press; the long spring is held to the same.
MAX_GAP_CLOSURE = 0.79
SHELF_NOSE_R = 1.2

# Wedge separator: the funnel narrows to the packet width plus this per side at the exit.
SEPARATORS = ("wedge", "blade")
WEDGE_CLEAR = 0.3
WEDGE_LEAD = 18.0  # the ramp starts this far behind the exit wall's inner face
# Top under packet 1's top (5.2), so packet 2 resting on packet 1 never touches a wedge.
WEDGE_TOP = CHEEK_TOP  # 4.8
WEDGE_CHAMFER_DEG = 45.0  # inner top edge, so a packet dropping onto a wedge slides inward

# Housing legs (parts leg_1..leg_4): a round column on a foot pad, one under each corner of
# the slab, carrying the housing from the table to the slab underside.
HLEG_D = 16.0  # column diameter
FOOT_D = 20.0  # foot pad diameter; the pad's edge is flush with the slab's corner edges
FOOT_T = 2.4  # the structure min_wall
# Split snap pin on each column top: a square pin split by a slot into two flat prongs, with a
# ridge across each prong's outer face that clicks into a groove in the slab's blind socket.
# Square, so every prong section is a rectangle with no thin edge. Heights are above the
# column top.
PIN_HALF = 3.25  # 6.5 mm square
PIN_SLOT = 1.2  # prong thickness PIN_HALF - PIN_SLOT/2 = 2.65, above the 2.4 mm wall
PIN_CLEAR = 0.05  # socket over the pin and ridge, normal to every face
PIN_RIDGE_H = 0.25  # proud of the prong: 0.2 mm interference with the socket while pushing in
PIN_RIDGE_Z = 5.5  # ridge peak
PIN_RIDGE_LOW_DEG = 50.0  # retaining flank, faces down in the leg's print pose
PIN_RIDGE_UP_DEG = 60.0  # lead-in flank
PIN_RIDGE_INSET = 0.3  # ridge ends short of the prong's sides
PIN_TOP = 6.3  # flat prong tops
CEILING_DEG = 50.0  # the socket's vaulted ceiling, from horizontal
# The prongs root this far under the column top, in a round well about the pin, so they are
# 8.5 mm long to the ridge (1.1% strain at 0.2 mm) inside the slab's depth.
PIN_WELL = 3.0
PIN_WELL_R = 5.4  # 0.8 mm clear of the pin's corners, 2.6 mm of column wall outside
SOCKET_CHAMFER = 0.4  # mouth lead-in; 60 deg from horizontal, so it is no overhang
SOCKET_CHAMFER_DEG = 60.0


@dataclass(frozen=True)
class LongSpring(SpringSpec):
    """Variant-B section and pitch with more beams, for the 50 mm stroke."""

    n_beams: int = 24

    @property
    def beams(self) -> int:
        return self.n_beams


@dataclass(frozen=True)
class SyringeLayout:
    """Derived dimensions (mm). ``*_rest`` values are at stroke fraction 0."""

    gap: float
    wall: float
    bore_x0: float
    bore_x1: float
    bore_y: float
    rear_x: float  # rear wall outer face
    exit_x: float  # exit wall outer face
    shelf_x: float  # shelf end
    side_y: float  # side wall outer face
    top: float
    blade_x0: float
    blade_top: float
    slot_w: float
    slot_h: float
    plate_z0: float
    plate_z1: float
    plate_w: float
    plate_rest_x: float
    contact_travel: float  # plate travel before it meets a centred packet
    stroke: float
    stroke_min: float
    lead_full: float  # packet 1 leading edge at full stroke
    yoke_rest_x: float  # yoke front face at rest
    cross_rest_x: float  # handle bar back face at rest
    table_z: float  # the table, under the legs' foot pads
    slab_z0: float  # housing floor slab underside, where the legs' columns stop
    leg_xy: tuple[tuple[float, float], ...]  # leg axes: rear +Y, rear -Y, front +Y, front -Y
    bar_z0: float
    bar_z1: float
    leg_x1: float  # leg front face at rest
    keepout: tuple[float, float, float, float, float, float]  # x0, x1, y0, y1, z0, z1
    spring: LongSpring
    spring_installed: float
    spring_full: float
    seat_x: float  # spring seat face on the housing (channel front end)
    separator: str  # "blade" or "wedge"
    wedge_x0: float  # funnel ramp start, on the side wall's inner face
    wedge_y: float  # funnel inner half-width from the ramp end (bore_x1) to the exit face
    wedge_top: float

    def wedge_line_y(self, x: float) -> float:
        """Funnel inner half-width at ``x``: the bore half-width before the ramp, ``wedge_y`` after it."""
        if x <= self.wedge_x0:
            return self.bore_y
        if x >= self.bore_x1:
            return self.wedge_y
        return self.bore_y + (self.wedge_y - self.bore_y) * (x - self.wedge_x0) / (self.bore_x1 - self.wedge_x0)

    def wedge_line_x(self, y: float) -> float:
        """Where the funnel ramp reaches half-width ``y`` (the inverse of ``wedge_line_y`` on the ramp)."""
        return self.wedge_x0 + (self.bore_y - y) / (self.bore_y - self.wedge_y) * (self.bore_x1 - self.wedge_x0)

    @property
    def wedge_deg(self) -> float:
        """Funnel ramp angle to the X axis."""
        return math.degrees(math.atan2(self.bore_y - self.wedge_y, self.bore_x1 - self.wedge_x0))

    def wedge_chamfer_z(self, y: float) -> float:
        """Height of the wedge's chamfered top at half-width ``|y|``."""
        return self.wedge_top - (self.bore_y - abs(y)) * math.tan(math.radians(WEDGE_CHAMFER_DEG))

    @property
    def protrusion_full(self) -> float:
        return self.lead_full - self.exit_x

    @property
    def past_shelf_full(self) -> float:
        return self.lead_full - self.shelf_x

    @property
    def stroke_margin(self) -> float:
        return self.stroke - self.stroke_min

    @property
    def shoulder_z(self) -> float:
        """Leg column top, seated: ``STOP_EPS`` of air under the slab, as the other stops."""
        return self.slab_z0 - STOP_EPS

    @property
    def socket_roof(self) -> float:
        """Slab material over the apex of the socket's vaulted ceiling, up to the floor top (z=0)."""
        return -(self.shoulder_z + _socket_apex_u())

    @property
    def spring_margin(self) -> float:
        """Spring length left before the beams touch, at full stroke."""
        return self.spring_full - self.spring.solid_length

    def travel(self, fraction: float) -> float:
        if fraction < 0.0 or fraction > 1.0:
            raise ValueError(f"stroke fraction must be in [0, 1], got {fraction}")
        return fraction * self.stroke

    def packet_shift(self, fraction: float) -> float:
        """How far the plate has pushed a centred bottom packet."""
        return max(0.0, self.travel(fraction) - self.contact_travel)

    def bar_x(self, fraction: float) -> tuple[float, float]:
        """Handle bar back and front faces at this stroke fraction."""
        x0 = self.cross_rest_x + self.travel(fraction)
        return x0, x0 + BAR_D


def syringe_layout(p: Params, separator: str = "wedge") -> SyringeLayout:
    """All derived dimensions. The stroke comes from the packet and bore, not a constant.

    ``separator`` picks the exit: ``"wedge"`` (default) or ``"blade"`` (see the module notes).
    """
    if separator not in SEPARATORS:
        raise ValueError(f"separator must be one of {SEPARATORS}, got {separator!r}")
    wall = p.structure.min_wall
    k = p.packet
    bore_x1 = p.magazine.length_i / 2.0
    bore_y = p.magazine.width_i / 2.0
    rear_x = -bore_x1 - wall
    exit_x = bore_x1 + EXIT_WALL
    shelf_x = exit_x + LIP_LEN
    plate_rest_x = rear_x - PARK
    # The final plate face is the trailing edge, whatever the packet's start in the bore.
    lead_min = max(exit_x + MIN_PROTRUSION, shelf_x + MIN_PAST_SHELF)
    lead_target = max(exit_x + TARGET_PROTRUSION, lead_min)
    stroke_min = lead_min - k.length - plate_rest_x
    stroke = lead_target - k.length - plate_rest_x
    gaps = math.ceil((stroke + PRELOAD) / (PROTOTYPE_SPRING.gap * MAX_GAP_CLOSURE))
    spring = LongSpring("S", PROTOTYPE_SPRING.thickness, n_beams=gaps + 1)
    installed = spring.installed()
    lead_full = plate_rest_x + stroke + k.length
    keepout = (shelf_x, lead_full + KEEPOUT_MARGIN,
               -(k.width / 2.0 + KEEPOUT_MARGIN), k.width / 2.0 + KEEPOUT_MARGIN,
               -KEEPOUT_Z_MARGIN, k.height + KEEPOUT_Z_MARGIN)
    # The slab holds the spring channel with a wall under it, and reaches the yoke's underside
    # so the whole yoke front face stops on the slab's rear face at full stroke.
    slab_z0 = min(CHANNEL_Z0 - wall, ARM_Z0)
    # One leg under each corner, the foot pad's edge flush with the slab's rear or front end
    # and its side, so the support footprint is as wide as the housing.
    side_y = bore_y + wall
    inset = FOOT_D / 2.0
    leg_xy = tuple((x, s * (side_y - inset))
                   for x in (rear_x + inset, shelf_x - inset) for s in (1.0, -1.0))
    lay = SyringeLayout(
        gap=p.separator.gap,
        wall=wall,
        bore_x0=-bore_x1,
        bore_x1=bore_x1,
        bore_y=bore_y,
        rear_x=rear_x,
        exit_x=exit_x,
        shelf_x=shelf_x,
        side_y=side_y,
        top=p.stack_nominal_height + p.magazine.headroom,
        blade_x0=k.length / 2.0 - BLADE_BITE,
        blade_top=p.separator.gap + BLADE_T,
        slot_w=PLATE_W + 2.0 * SLIDE_CLEAR,
        slot_h=SLOT_H,
        plate_z0=PLATE_Z0,
        plate_z1=SLIDER_TOP,
        plate_w=PLATE_W,
        plate_rest_x=plate_rest_x,
        contact_travel=-k.length / 2.0 - plate_rest_x,
        stroke=stroke,
        stroke_min=stroke_min,
        lead_full=lead_full,
        yoke_rest_x=rear_x - STOP_EPS - stroke,
        cross_rest_x=BAR_X0,
        table_z=TABLE_Z,
        slab_z0=slab_z0,
        leg_xy=leg_xy,
        bar_z0=BAR_Z0,
        bar_z1=BAR_Z1,
        leg_x1=LEG_X1,
        keepout=keepout,
        spring=spring,
        spring_installed=installed,
        spring_full=installed - stroke,
        seat_x=plate_rest_x + installed,
        separator=separator,
        wedge_x0=bore_x1 - WEDGE_LEAD,
        wedge_y=k.width / 2.0 + WEDGE_CLEAR,
        wedge_top=WEDGE_TOP,
    )
    if lay.socket_roof < wall:
        raise ValueError(f"leg socket leaves {lay.socket_roof:.2f} mm under the floor top, "
                         f"under the {wall} mm wall")
    return lay

def _prism_yz(points, x0: float, x1: float):
    """Polygon in the (Y, Z) plane extruded along X from ``x0`` to ``x1``."""
    face = Plane.YZ * Polygon(*points, align=None)
    return (Pos(x0, 0.0, 0.0) * extrude(face, amount=x1 - x0, dir=(1.0, 0.0, 0.0))).solid()


def _rail_profile(sign: float, root_y: float, extra: float = 0.0, inset: float = 0.2):
    """V rail section, root on the wall at ``root_y``; ``extra`` offsets every face outward."""
    t = math.tan(math.radians(RAIL_DEG))
    tip_y = root_y + RAIL_D + extra
    # Each flank line moves down (up) by extra/cos so its normal offset is ``extra``.
    shift = extra / math.cos(math.radians(RAIL_DEG))
    y_in = root_y - inset

    def z_low(y):
        return RAIL_ZC - RAIL_HALF - shift + (y - root_y) * t

    pts = [
        (y_in, z_low(y_in)),
        (tip_y, z_low(tip_y)),
        (tip_y, 2 * RAIL_ZC - z_low(tip_y)),
        (y_in, 2 * RAIL_ZC - z_low(y_in)),
    ]
    return [(sign * y, z) for y, z in pts]


def _wedge_solid(lay: SyringeLayout, sign: float):
    """Side funnel wedge on the ``sign`` side wall: plan-view ramp, vertical faces, chamfered top."""
    by = lay.bore_y
    plan = [(lay.wedge_x0, by), (lay.bore_x1, lay.wedge_y), (lay.exit_x, lay.wedge_y),
            (lay.exit_x, by + 0.5), (lay.wedge_x0, by + 0.5)]
    body = _prism_xy([(x, sign * y) for x, y in plan], -0.2, lay.wedge_top)
    # Keep only what is under the chamfer plane through the top's outer edge (y = bore_y).
    reach = 5.0
    drop = reach * math.tan(math.radians(WEDGE_CHAMFER_DEG))
    section = [(by - reach, -1.0), (by + 1.0, -1.0), (by + 1.0, lay.wedge_top),
               (by, lay.wedge_top), (by - reach, lay.wedge_top - drop)]
    keep = _prism_yz([(sign * y, z) for y, z in section], lay.wedge_x0 - 1.0, lay.exit_x + 1.0)
    return (body & keep).solid()


def housing_solid(lay: SyringeLayout):
    """Floor slab, tube, exit wall, blade or wedges, shelf, cheeks, rails; slot, channel, sockets cut."""
    w = lay.wall
    sy = lay.side_y
    slab = _box(lay.rear_x, lay.shelf_x, -sy, sy, lay.slab_z0, 0.0)
    sides = [
        _box(lay.rear_x, lay.exit_x, lay.bore_y, sy, -0.2, lay.top),
        _box(lay.rear_x, lay.exit_x, -sy, -lay.bore_y, -0.2, lay.top),
    ]
    rear = _box(lay.rear_x, lay.bore_x0, -lay.bore_y - 0.2, lay.bore_y + 0.2, -0.2, lay.top)
    front = _box(lay.bore_x1, lay.exit_x, -lay.bore_y - 0.2, lay.bore_y + 0.2, lay.gap, lay.top)
    if lay.separator == "blade":
        # Blade bites back over the packet's front edge; its underside sets the gap.
        blade = _box(lay.blade_x0, lay.bore_x1 + 0.2, -lay.bore_y - 0.2, lay.bore_y + 0.2,
                     lay.gap, lay.blade_top)
        blade = _round_lower_edge(blade, lay.blade_x0, -lay.bore_y - 0.2, lay.bore_y + 0.2,
                                  lay.gap, EDGE_R)
        separator = [blade]
    else:
        # No bite: the exit wall's sharp lower edge sets the gap, and the wedges centre the packet.
        separator = [_wedge_solid(lay, sign) for sign in (1.0, -1.0)]
    # Cheeks keep the presented packet on the shelf, with a lead-in from the
    # bore width. Their top stays under the gap.
    cheeks = []
    half = lay.bore_y - 2.0  # 28: 0.5 mm outside a 55 mm packet
    for sign in (1.0, -1.0):
        pts = [(lay.exit_x - 0.2, lay.bore_y), (lay.exit_x + 6.0, half),
               (lay.shelf_x - 2.0, half), (lay.shelf_x - 2.0, sy), (lay.exit_x - 0.2, sy)]
        face = Polygon(*[(x, sign * y) for x, y in pts], align=None)
        cheeks.append((Pos(0.0, 0.0, -0.2) * extrude(face, amount=CHEEK_TOP + 0.2, dir=(0.0, 0.0, 1.0))).solid())
    rails = [
        _prism_yz(_rail_profile(sign, sy), RAIL_X[0], RAIL_X[1]) for sign in (1.0, -1.0)
    ]
    body = _fuse([slab, *sides, rear, front, *separator, *cheeks, *rails])
    slot = _box(lay.rear_x - 1.0, lay.bore_x0 + 0.5, -lay.slot_w / 2.0, lay.slot_w / 2.0,
                0.0, lay.slot_h)
    # Channel section: the spring pocket under the two lips, and the keel slot between them.
    # It is open at the rear face, which is how the spring goes in.
    cy, sw = CHANNEL_HALF_W, LIP_SLOT_HALF_W
    section = [(-cy, CHANNEL_Z0), (cy, CHANNEL_Z0), (cy, LIP_ROOT_Z), (sw, -LIP_T), (sw, 1.0),
               (-sw, 1.0), (-sw, -LIP_T), (-cy, LIP_ROOT_Z)]
    channel = _prism_yz(section, lay.rear_x - 1.0, lay.seat_x)
    nose = _box(lay.shelf_x - SHELF_NOSE_R, lay.shelf_x + 0.5, -sy - 1.0, sy + 1.0,
                -SHELF_NOSE_R, 0.5)
    disc = (Pos(lay.shelf_x - SHELF_NOSE_R, 0.0, -SHELF_NOSE_R) * Rot(90.0, 0.0, 0.0)
            * Cylinder(SHELF_NOSE_R, 2.0 * sy + 4.0))
    sockets = [Pos(x, y, 0.0) * _socket_cutter(lay) for x, y in lay.leg_xy]
    return _cut(body, [slot, channel, (nose - disc).solid(), *sockets])


def _prism_xz(points, y0: float, y1: float):
    """Polygon in the (X, Z) plane extruded along Y from ``y0`` to ``y1``."""
    face = Plane.XZ * Polygon(*points, align=None)
    return (Pos(0.0, y0, 0.0) * extrude(face, amount=y1 - y0, dir=(0.0, 1.0, 0.0))).solid()


def _prism_xy(points, z0: float, z1: float):
    """Polygon in the (X, Y) plane extruded along Z from ``z0`` to ``z1``."""
    face = Polygon(*points, align=None)
    return (Pos(0.0, 0.0, z0) * extrude(face, amount=z1 - z0, dir=(0.0, 0.0, 1.0))).solid()


def _offset_convex(points, d: float):
    """Counter-clockwise convex polygon with every edge moved ``d`` outward (sharp corners)."""
    n = len(points)
    lines = []
    for i in range(n):
        (x0, y0), (x1, y1) = points[i], points[(i + 1) % n]
        length = math.hypot(x1 - x0, y1 - y0)
        nx, ny = (y1 - y0) / length, -(x1 - x0) / length
        lines.append(((x0 + d * nx, y0 + d * ny), (x1 - x0, y1 - y0)))
    out = []
    for i in range(n):
        (px, py), (dx, dy) = lines[i - 1]
        (qx, qy), (ex, ey) = lines[i]
        t = ((qx - px) * ey - (qy - py) * ex) / (dx * ey - dy * ex)
        out.append((px + t * dx, py + t * dy))
    return out


def _tan(deg: float) -> float:
    return math.tan(math.radians(deg))


def _socket_apex_u() -> float:
    """Socket ceiling apex above the leg column top: the vault over the pin, offset by the clearance."""
    return PIN_TOP + PIN_HALF * _tan(CEILING_DEG) + PIN_CLEAR / math.cos(math.radians(CEILING_DEG))


def _ridge_u() -> tuple[float, float]:
    """Ridge foot heights on the prong face: below (retaining flank) and above (lead-in flank)."""
    return (PIN_RIDGE_Z - PIN_RIDGE_H * _tan(PIN_RIDGE_LOW_DEG),
            PIN_RIDGE_Z + PIN_RIDGE_H * _tan(PIN_RIDGE_UP_DEG))


def _socket_section():
    """Socket section in (w, u) across one pair of walls, counter-clockwise.

    It is the pin's section with both ridges and a 50 deg gable over the tops, offset by
    ``PIN_CLEAR``, so a seated leg touches nothing; the mouth has a lead-in chamfer.
    """
    mouth = STOP_EPS  # the slab underside, above the column top
    lo, hi = _ridge_u()
    h = PIN_HALF
    half = [(0.0, mouth + 1.0), (h, mouth + 1.0), (h, lo), (h + PIN_RIDGE_H, PIN_RIDGE_Z), (h, hi),
            (h, PIN_TOP), (0.0, PIN_TOP + h * _tan(CEILING_DEG))]
    # Keep the offset wall, groove and gable; the mouth and the apex are set below.
    wall = _offset_convex(half, PIN_CLEAR)[2:-1]
    bore = h + PIN_CLEAR
    right = [(bore + SOCKET_CHAMFER, mouth - 1.0), (bore + SOCKET_CHAMFER, mouth),
             (bore, mouth + SOCKET_CHAMFER * _tan(SOCKET_CHAMFER_DEG)), *wall]
    left = [(-w, u) for w, u in reversed(right)]
    return right + [(0.0, _socket_apex_u())] + left


def _socket_cutter(lay: SyringeLayout):
    """Blind square socket at the origin in XY, grooved on all four walls, vaulted on top.

    Two crossed prisms of ``_socket_section``: each is as wide as the bore, so the bore stays
    6.6 mm square and the groove runs along each wall. Their gables cross into a vault of
    50 deg faces, so the upright housing prints the ceiling with no bridge, and the groove
    on every wall lets the leg go in at any of the four quarter turns.
    """
    sec = [(w, lay.shoulder_z + u) for w, u in _socket_section()]
    b = PIN_HALF + PIN_CLEAR
    return _fuse([_prism_yz(sec, -b, b), _prism_xz(sec, -b, b)])


def leg_solid(lay: SyringeLayout, index: int):
    """Housing leg ``index`` (0..3) seated in its socket: foot pad, column, well and split snap pin."""
    x, y = lay.leg_xy[index]
    zs = lay.shoulder_z
    h = PIN_HALF
    pad = Pos(0.0, 0.0, TABLE_Z + FOOT_T / 2.0) * Cylinder(FOOT_D / 2.0, FOOT_T)
    col_z0 = TABLE_Z + FOOT_T - 0.2
    column = Pos(0.0, 0.0, (col_z0 + zs) / 2.0) * Cylinder(HLEG_D / 2.0, zs - col_z0)
    well = Pos(0.0, 0.0, zs - PIN_WELL / 2.0 + 0.5) * Cylinder(PIN_WELL_R, PIN_WELL + 1.0)
    pin = _box(-h, h, -h, h, zs - PIN_WELL - 0.5, zs + PIN_TOP)
    # Ridges across the two outer prong faces (normal Y); each overlaps its prong by 0.5 mm.
    lo, hi = _ridge_u()
    ridge = [(h - 0.5, zs + lo), (h, zs + lo), (h + PIN_RIDGE_H, zs + PIN_RIDGE_Z), (h, zs + hi),
             (h - 0.5, zs + hi)]
    xr = h - PIN_RIDGE_INSET
    ridges = [_prism_yz([(s * w, z) for w, z in ridge], -xr, xr) for s in (1.0, -1.0)]
    body = _fuse([_cut(_fuse([pad, column]), [well]), pin, *ridges])
    # The slot splits the pin into two prongs down to the well floor and stays inside the well.
    slot = _box(-h - 1.0, h + 1.0, -PIN_SLOT / 2.0, PIN_SLOT / 2.0, zs - PIN_WELL, zs + PIN_TOP + 1.0)
    leg = _cut(body, [slot])
    return (Pos(x, y, 0.0) * leg).solid()


def leg_solids(lay: SyringeLayout) -> dict:
    """The four identical legs, ``leg_1`` .. ``leg_4`` in ``lay.leg_xy`` order."""
    return {f"leg_{i + 1}": leg_solid(lay, i) for i in range(len(lay.leg_xy))}


def _leg_yc(lay: SyringeLayout, sign: float) -> float:
    """Leg (and runner) centre line in Y."""
    return sign * (lay.side_y + SLIDE_CLEAR + LEG_W / 2.0)


def _head_x() -> tuple[float, float]:
    """T-slide head back and front faces in X, seated."""
    x1 = LEG_X1 - NECK_L
    return x1 - HEAD_L, x1


def _ridge_profile():
    """Detent ridge section in (X, Z) on the head's back face, counter-clockwise."""
    xb = _head_x()[0]
    z_lo = RIDGE_Z - RIDGE_H * math.tan(math.radians(RIDGE_LOW_DEG))
    z_hi = RIDGE_Z + RIDGE_H * math.tan(math.radians(RIDGE_UP_DEG))
    return [(xb, z_lo), (xb, z_hi), (xb - RIDGE_H, RIDGE_Z)]


def _ridge_half() -> float:
    """Ridge half-length in Y, short of the head's sides."""
    return HEAD_HW - RIDGE_INSET


def slider_solid(lay: SyringeLayout, travel: float = 0.0):
    """Yoke, plate stem and keel, two grooved arms ending in socketed legs, moved ``travel`` in +X."""
    yf = lay.yoke_rest_x
    arm_in = lay.side_y + SLIDE_CLEAR
    arm_out = arm_in + ARM_T
    x_back = yf - YOKE_T
    yoke = _box(x_back, yf, -arm_out, arm_out, ARM_Z0, SLIDER_TOP)
    # The plate face is the stem's front; the keel under it is the spring pad.
    # The keel is narrower than the spring, so it runs in the slot between the channel lips.
    stem = _box(yf - 0.2, lay.plate_rest_x, -lay.plate_w / 2.0, lay.plate_w / 2.0,
                PLATE_Z0, SLIDER_TOP)
    keel = _box(yf - 0.2, lay.plate_rest_x, -KEEL_HALF_W, KEEL_HALF_W, SPRING_Z0, PLATE_Z0 + 0.2)
    arms = [
        _box(x_back, LEG_X0 + 1.0, arm_in, arm_out, ARM_Z0, SLIDER_TOP),
        _box(x_back, LEG_X0 + 1.0, -arm_out, -arm_in, ARM_Z0, SLIDER_TOP),
    ]
    # Each leg is full height, so it rises straight off the bed in the print pose.
    legs = [
        _box(LEG_X0, LEG_X1, arm_in, arm_in + LEG_W, BAR_Z0, SLIDER_TOP),
        _box(LEG_X0, LEG_X1, -arm_in - LEG_W, -arm_in, BAR_Z0, SLIDER_TOP),
    ]
    frame = _fuse([yoke, stem, keel, *arms, *legs])
    # Each groove covers every rail position over the stroke. Its closed front
    # end rests on the rail's front end: that is the home stop.
    stop_x = RAIL_X[1] + STOP_EPS
    cutters = [
        _prism_yz(_rail_profile(sign, lay.side_y, extra=SLIDE_CLEAR, inset=0.6), yf, stop_x)
        for sign in (1.0, -1.0)
    ]
    # T-slide sockets, open at the bottom; the ceiling is the handle's positive stop.
    hx0, hx1 = _head_x()
    c = JOINT_CLEAR
    for sign in (1.0, -1.0):
        yc = _leg_yc(lay, sign)
        cutters.append(_box(hx0 - c, hx1 + c, yc - HEAD_HW - c, yc + HEAD_HW + c,
                            BAR_Z0 - 1.0, TAIL_TOP + STOP_EPS))
        cutters.append(_box(hx1, LEG_X1 + 1.0, yc - NECK_HW - c, yc + NECK_HW + c,
                            BAR_Z0 - 1.0, TAIL_TOP + STOP_EPS))
        half = _ridge_half() + JOINT_CLEAR
        cutters.append(_prism_xz(_offset_convex(_ridge_profile(), JOINT_CLEAR),
                                 yc - half, yc + half))
    slider = _cut(frame, cutters)
    return (Pos(travel, 0.0, 0.0) * slider).solid()


def _bar(lay: SyringeLayout):
    """Pull bar: 2 mm radii on the top edges, 50 deg chamfers on the bottom edges."""
    x0, x1 = lay.cross_rest_x, lay.cross_rest_x + BAR_D
    cz = BAR_CHAMFER * math.tan(math.radians(50.0))
    pts = [(x0 + BAR_CHAMFER, BAR_Z0), (x1 - BAR_CHAMFER, BAR_Z0), (x1, BAR_Z0 + cz),
           (x1, BAR_Z1), (x0, BAR_Z1), (x0, BAR_Z0 + cz)]
    section = Polygon(*pts, align=None)
    section = fillet(section.vertices().group_by(Axis.Y)[-1], BAR_TOP_R)
    half = lay.side_y + SLIDE_CLEAR + LEG_W
    face = Plane.XZ * section
    return (Pos(0.0, -half, 0.0) * extrude(face, amount=2.0 * half, dir=(0.0, 1.0, 0.0))).solid()


def _pull_text(lay: SyringeLayout):
    """PULL as a cutter, 0.8 mm into the bar top, reading left to right from the user's side (+X)."""
    size = PULL_CAP_H / PULL_CAP_PER_SIZE
    text = Text(PULL_TEXT, font_size=size, font="Arial", font_style=FontStyle.BOLD,
                align=(Align.CENTER, Align.CENTER))
    # Baseline along +Y (the user's right) and letter tops toward -X, away from the user.
    plane = Plane(origin=(lay.cross_rest_x + BAR_D / 2.0, 0.0, BAR_Z1),
                  x_dir=(0.0, 1.0, 0.0), z_dir=(0.0, 0.0, 1.0))
    cutter = extrude(plane * text, amount=PULL_DEPTH + 1.0, dir=(0.0, 0.0, -1.0))
    return Pos(0.0, 0.0, 1.0) * cutter


def handle_solid(lay: SyringeLayout, travel: float = 0.0, text: bool = True):
    """Bar, two runners and two T-slide tails with detent leaves, moved ``travel`` in +X.

    ``text=False`` gives the plain handle, the undecorated base for ``min_wall``.
    """
    run_x0 = LEG_X1 + JOINT_CLEAR
    arm_in = lay.side_y + SLIDE_CLEAR
    parts = [_bar(lay)]
    cutters = []
    for sign in (1.0, -1.0):
        yc = _leg_yc(lay, sign)
        parts.append(_box(run_x0, lay.cross_rest_x + 1.0, yc - LEG_W / 2.0, yc + LEG_W / 2.0,
                          BAR_Z0, BAR_Z1))
        xb, hx1 = _head_x()
        parts.append(_box(xb, hx1, yc - HEAD_HW, yc + HEAD_HW, BAR_Z0, TAIL_TOP))
        parts.append(_box(hx1 - 0.1, run_x0, yc - NECK_HW, yc + NECK_HW, BAR_Z0, TAIL_TOP))
        half = _ridge_half()
        ridge = _ridge_profile()
        # Overlap the leaf by 0.5 mm so the ridge fuses into it.
        ridge = [(xb + 0.5, ridge[0][1]), (xb + 0.5, ridge[1][1]), ridge[1], ridge[2], ridge[0]]
        parts.append(_prism_xz(ridge, yc - half, yc + half))
        # Slot behind the leaf, open at the top, so the leaf flexes forward to click in.
        cutters.append(_box(xb + LEAF_T, xb + LEAF_T + LEAF_SLOT, yc - HEAD_HW - 1.0,
                            yc + HEAD_HW + 1.0,
                            LEAF_ROOT_Z, TAIL_TOP + 1.0))
    body = _fuse(parts)
    # Round the bar's two front corners in plan.
    x_hi = lay.cross_rest_x + BAR_D
    half = arm_in + LEG_W
    plan = Pos((LEG_X0 + x_hi) / 2.0, 0.0, BAR_Z0 - 1.0) * extrude(
        RectangleRounded(x_hi - LEG_X0, 2.0 * half, BAR_END_R), amount=TAIL_TOP - BAR_Z0 + 2.0)
    body = (body & plan).solid()
    if text:
        cutters.append(_pull_text(lay))
    handle = _cut(body, cutters)
    return (Pos(travel, 0.0, 0.0) * handle).solid()


def hand_keepout(p: Params):
    """Box that must hold only the presented packet with the slider home (see the module notes)."""
    return _box(*syringe_layout(p).keepout)


def spring_at(lay: SyringeLayout, travel: float, length: float | None = None):
    """Spring with its rear pad on the keel at this travel. Default length fills the gap to the seat."""
    x0 = lay.plate_rest_x + travel
    if length is None:
        length = lay.seat_x - x0
    return spring_solid(lay.spring, length, x0, 0.0, SPRING_Z0)


def syringe_solids(p: Params, stroke_fraction: float = 0.0, free_spring: bool = False,
                   separator: str = "wedge") -> dict:
    """Housing, slider, handle, spring and the four legs at one stroke fraction (0 rest, 1 forward stop).

    The handle is clipped onto the slider and the legs are seated in the housing's sockets.
    The spring is at its compressed
    length for that stroke, so it touches the keel and the seat.
    ``free_spring`` gives the printed (free) spring instead, which runs
    ``PRELOAD`` mm into the seat in this pose. ``separator`` picks the
    housing's exit, ``"blade"`` or ``"wedge"``; the other parts do not change.
    """
    lay = syringe_layout(p, separator)
    travel = lay.travel(stroke_fraction)
    length = lay.spring.free_length if free_spring else None
    return {
        "housing": housing_solid(lay),
        "slider": slider_solid(lay, travel),
        "handle": handle_solid(lay, travel),
        "spring": spring_at(lay, travel, length),
        **leg_solids(lay),
    }


def wall_shape_for(name: str, p: Params, stroke_fraction: float = 0.0):
    """The handle's undecorated base (no PULL deboss); other parts have no decoration."""
    if name == "handle":
        lay = syringe_layout(p)
        return handle_solid(lay, lay.travel(stroke_fraction), text=False)
    return None


def print_location_for(name: str, shape) -> Location:
    """Housing on its slab, slider upside down on its z=4.3 face, legs on their feet, handle and spring as is."""
    if name == "slider":
        flip = Rot(180.0, 0.0, 0.0)
        return Pos(0.0, 0.0, -(flip * shape).bounding_box().min.Z) * flip
    return on_bed(shape)


def min_wall_override(name: str, p: Params) -> float | None:
    """Only the spring beams are thinner than ``structure.min_wall`` on purpose."""
    if name == "spring":
        return syringe_layout(p).spring.thickness
    return None
