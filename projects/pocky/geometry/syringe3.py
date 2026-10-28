"""Syringe3 dispenser, the next prototype, a copy of ``syringe.py`` whose exit gap, presentation and
pusher plate band come from ``p.syringe3``. The numbers in the notes below are the baseline values:
75 mm presentation past the exit (85 mm stroke), a 176 mm bore with an 8 mm rear ramp over the
slot and the plate resting mid-way between its toe and the rear wall, a 4.7 mm plate with an
undercut lip, 60 deg lead-ins on the wedges, and a 7.5 mm tall spring with 10 mm preload.

Syringe dispenser: housing on four pop-in legs, slider with two arms, clip-on PULL handle, printed spring,
two backstop clips.

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
* z = -49.6 .. -15.43: housing leg columns, under the slab's four corners.
* z = -37 .. -27: handle bar and runners, 15 mm above the table so fingers can
  curl under the bar, and 2 mm under the hand keep-out zone.
* z = -20.83 .. 4.9: backstop clips, a base under the slab (to -15.43) and a
  plate outside each arm up to the arm's top, behind the slider's legs.
* z = -15.38 .. 0: the floor slab (``slab_z0``): the spring channel with a 2.4 mm
  wall under it, deeper than the yoke so the yoke's whole front face stops on it.
* z = -13 .. 4.9: arms and yoke, on the V rails at z = -4.5 .. 1.5.
* z = -12.78 .. -5.28: return spring, in a channel in the floor under the stack.
* z = -2.4 .. 0: the two channel lips' tips, flush with the floor top.
* z = 0: floor top. z = 0.2 .. 4.9: pusher plate, in a 5.2 mm rear slot; its top
  stays 0.3 mm under packet 2's underside (5.2), which it slides under.
* z = 5.2 .. 19.03: rear ramp on the rear wall's inner face, over the slot.
* z = 7.8: separator blade underside (``syringe3.exit_gap``); with the wedge
  separator, the exit wall's lower edge (the window top) instead.
* z = 0 .. 4.8: wedge separator only, the two side funnel wedges.

Separator variants (``separator=`` on ``syringe_layout`` and ``syringe_solids``):

* ``"blade"``: a 2.4 mm blade under the exit wall reaches 2 mm back
  over the bottom packet's front edge, so packets 2..N rest tilted on its rear
  edge.
* ``"wedge"`` (default): no blade. The window is a plain 7.8 mm opening in the 3 mm exit
  wall: it passes one 5.2 mm packet (with 2.6 mm of vertical play) but not two (10.4 mm), and
  nothing overhangs the stack behind the wall's inner face (x=85), so the packets stack flat and
  packet 2 (z 5.2..10.4) meets the wall's lower edge, which covers 2.6 mm of its front face. A funnel wedge on the
  inside of each side wall narrows the bore from 60 mm to 55.6 mm (0.3 mm a
  side for the 55 mm packet) over the 18 mm before the exit wall, 7 deg to X,
  and runs on through the window. The wedges only centre packet 1 sideways; the exit wall alone
  separates the packets vertically, so the window height does not move the wedges. They stop at
  z=4.8, under packet 1's top, so they never touch packet 2 while packet 1 is there. Each has a
  vertical inner face 0.99 mm tall (``wedge_foot_z``), which centres packet 1's lower edge, and
  above it a lead-in at 60 deg from horizontal (``WEDGE_LEAD_IN_DEG``) along the funnel line,
  reaching the bore wall at or under the wedge top, so no flat top is left inside the bore.
  A packet that drops up to 2.5 mm off-centre (all the bore allows) lands with its edge on a
  lead-in, not on a ledge. If a quarter of its weight rests on that corner, the lead-in's push
  beats floor friction while tan 60 = 1.73 > mu / 0.25, i.e. for mu under 0.43; a 45 deg
  chamfer (the earlier one) needed mu under 0.25.

Rear ramp: a packet end that falls against the rear wall must land in front of
the plate face, not on the stem or plate. A ramp across the bore on the rear
wall's inner face does that. The bore is 176 mm long (``syringe3.bore_length``),
6 mm over ``magazine.length_i``, and grows at the back so the exit and the
protrusion stay put: x = -91 .. 85, the rear wall's outer face at -93.4. The
ramp's toe, 8 mm into the bore at x=-83, stands 0.5 mm behind a centred packet's
rear end (``RAMP_PACKET_CLEAR``), so the stack loads centred as before. The toe
is a 2.4 mm vertical land from the slot roof (z=5.2, 0.3 mm over the plate top)
to z=7.6, so it is no thinner than the wall; the face then rises 35 deg from
vertical (``RAMP_DEG``) to the wall at z=19.03. At 55 deg from horizontal a
packet end slides off it for any friction under tan 55 = 1.4.

The face reaches packets 2 to 4 of a flat stack, and every packet's rear end is
clear of it. A packet's end play, between the ramp under its rear end and the
exit wall's inner face (x=85), grows with its height: packet 2 (z 5.2 .. 10.4)
3.0 mm, its rear end 0.5 mm ahead of the toe land; packet 3 (z 10.4) 5.0 mm;
packet 4 (z 15.6) 8.6 mm; packets 5 and up, above the ramp, 11 mm. Packets 2 and
up sit above the 7.8 mm window, so the exit wall stops their fronts; a centred
stack's fronts are at x=82.5, 2.5 mm short of it, so none is wedged between the
ramp and the wall. Packet 1 is stopped behind by the ramp's blocks beside the
slot, at the toe, and is free in front through the window.

The plate face rests at the centre of the window between the toe and the rear
wall's inner face (x=-87, 4 mm from each; ``PLATE_WINDOW_MARGIN`` requires 3),
under the ramp. Print and assembly tolerance can then neither bring the plate
top out past the toe, where a falling packet could land on it, nor put the face
back at the wall. A packet end leaving the toe falls in front of the plate face,
and the 0.3 mm between the plate top and the ramp's underside is too thin for a
packet. The plate meets a centred packet after 4.5 mm. The ramp's heights follow
the plate top: the slot roof is ``slot_h``, at least ``PLATE_HEADROOM`` over it.
Beside the slot (|y| > 20.35) the ramp stands down to the floor, so over the
slot its underside is a 40.7 mm bridge, the slot roof carried on to the toe, and
packet 1, 55 mm wide, cannot back into the slot under it.

Pusher plate: z 0.2 .. 4.9, so a wrapped packet's end meets 4.7 mm of face
and the plate leaves only 0.2 mm under it to slide in. The top edge is an
undercut lip: a 1.3 mm vertical land (``PLATE_LIP_LAND``) at the plate face,
and under it the face leans back 15 deg (``PLATE_UNDERCUT_DEG``) to stand
0.6 mm behind (``PLATE_UNDERCUT``), so a soft wrapper end is caught under the
lip rather than ridden over. The land keeps every min_wall ray through the top
edge over 1.2 mm. The keel's front is flush with the face under the undercut
(``keel_rest_x``, x=-87.6), and the spring's rear pad sits on it.

Hand keep-out (``hand_keepout``): with the slider home and a packet presented
(leading edge at x=163), the box x 106..183, |y| <= 47.5, z -25..30.2 around
the packet's exposed part holds only the packet. The housing and its legs end
at the shelf (x=106), the legs end at x=100, and the bar and runners stay
under z=-27 at every stroke fraction. The arms, legs and the handle's tails inside the legs do
cross the zone while the slider is pulled, when the hand is on the bar and no
packet is presented yet.

Why raise the dispenser rather than move the bar elsewhere: a bar in front of
the zone (x > 183) needs arms through the zone or wider than |y| = 47.5, and a
bar over the housing blocks loading the magazine. Moving the table down keeps
z=0 at the packet plane, so the exit plane and the presentation criteria stand.

Housing legs: a 16 mm column on a 20 mm x 2.4 mm foot pad, 39 mm from the
table to the slab, under each corner of the slab (axes at x = -83.4 and 96,
y = +-22.4), each pad's edge flush with the slab's end and side. The housing
is 257.4 cm^3 (327 g) and the four legs 30.7 cm^3 (39 g); a solid base filling
the table-to-slab space instead would make the housing about 731 cm^3 (928 g).
Under the slab there is otherwise only the two backstop clips' bases (x 63.95 ..
83.95, |y| 16 .. 40.75, z >= -20.83, 4 mm behind the front columns), and the slider's
arms, yoke and keel stay at z >= -13 and its legs, the handle's runners and tails at
|y| >= 32.75, outside the housing legs (|y| <= 30.4 for the columns, the pads
under z=-49.6 below everything that moves), and the yoke at full stroke stops
at x = -93.45, behind the rear columns (x >= -91.4). The spring and keel run in
the channel at |y| <= 7.5, clear of the sockets (|y| >= 18.7 for the legs', 22.6 for the clips').

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
dispenser (housing 327 g, slider and handle 152 g, spring 8 g, legs 39 g,
clips 10 g, 536 g; centre of mass at x=-3.5) restores 5.25 N x 109.5 mm = 0.58 N*m
empty and 0.65 N*m with 10 packets of 7 g (606 g): a margin of 0.96 to 1.08, so it
tips at 29 to 32 N if the feet do not slide. They do slide first: table friction
(0.5 x W = 2.6 to 3.0 N) is under a tenth of the pull. Weight would not fix
that: with a solid base under the slab (1.10 to 1.17 kg in all) it would slide
at 5.4 to 5.7 N and tip at 56 to 60 N. So the dispenser is held or clamped
while pulled, as the passing case assumes.

Printability:

* Housing: stands on the slab underside (z=-15.38 on the bed). The floor top
  needs no bridge, as the slab is solid under it (print with sparse infill).
  The six sockets (four legs, two clips) are blind holes opening on the bed face, printed
  upright: their ceilings are vaults of 50 deg faces (no bridge), the
  groove's upper flank is 60 deg from horizontal and its lower flank faces up,
  and the mouth has a 0.4 mm lead-in chamfer at 60 deg that also takes up
  elephant's foot.
  The rails' lower flanks are 50 deg from horizontal and the
  shelf nose is a radius. The spring channel's two lips have undersides 50 deg
  from horizontal, rising from the channel wall to the tip, so they grow out of
  the wall without support, and the slot between them stays open (no bridge).
  The bridges are the exit wall and blade over the 60 mm exit window (the
  exit wall alone with the wedge separator) and the rear slot's 40.7 mm roof,
  which runs on under the rear ramp to its toe. The ramp's face faces up and
  its toe land is vertical.
  The wedges have vertical faces and an upward-facing chamfer, so they print
  upright without support.
* Housing legs: standing, foot pad on the bed, pin up, as assembled. Every
  face rises straight up or faces up (pad top, column top, well floor, slot
  floor, prong tops) except the ridge's retaining flank, 50 deg from
  horizontal. No support, no bridge. The four legs are identical; the model
  exports each (``leg_1`` .. ``leg_4``) so a slicer plate can take all four, or
  any one with four copies.
* Slider: upside down on the plane z=4.9 that the plate, yoke, arms and legs
  share. Every face rises straight from the bed except the rail grooves (50 deg
  flanks), the detent groove in each socket (50 and 60 deg flanks) and the
  plate's undercut, which faces up in this pose (15 deg from vertical). The
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
* Backstop clips: standing on the base underside, pin and plate up, as assembled.
  The base, plate and pin rise straight up, the well floor and the pry notch's
  step face up, and the pin's ridges are the legs' (retaining flank 50 deg from
  horizontal). No support, no bridge. The two are mirror images.

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

Backstop clips (``clip_n``, ``clip_s``): pushing the handle back past home
drives the slider backwards, and with nothing behind it the plate would leave
the rear slot after 6.4 mm. A clip under each side of the slab stops it. Its
plate stands right behind the slider leg (x 63.95 .. 83.95, the front face
``STOP_EPS`` behind the leg's rear face at x=84), outside the arm, so at home
the leg's rear face bears on the clip's front face: the plate's front end
(3 mm x 25.7 mm) and the base's under the arm, 104 mm^2 in all. Pulling moves
the legs away, so the stroke is unchanged. The grooves' closed front ends are
the backup: they stand ``GROOVE_BACKUP`` (0.5 mm) further from the rails' front
ends than the clips from the legs, so they stop the slider only if a clip gives
way. At 40 N (``PULL_MAX_EFFORT_N``) all on one clip, the plate, loaded in its
own plane over its 20 mm depth, bends 2.0 MPa at its root and moves 0.01 mm;
the leg face bears at 0.4 MPa; the pin's two prongs bear on the socket's X
walls at 1.2 MPa, 3.1 MPa at the edge with the moment, and the base's front end
bears up on the slab underside. All of it is in bearing; the snap ridge only
holds the clip up.

The clips still limit arm spread. Outward motion is free in the V (that is how
the arms spring on), and an arm unhooks once its inner face (|y| = 32.75) clears
the rail tip (34.4): 1.65 mm (``rail_engagement``, the rail depth less the slide
clearance). Each plate's inner face is ``SLIDE_CLEAR`` (0.35 mm) off the arm's
outer face (|y| = 37.75), over the arm's whole height (-13 .. 4.9; the plate
runs from -20.83), and the arm runs beside it at every stroke (the arm covers x
-101.45 .. 85 throughout), so an arm spreads 0.35 mm before it bears on the
plate, a fifth of what unhooks it. In normal sliding a clip touches nothing.

The base carries the housing legs' split snap pin, in a slab socket made as
theirs, its mouth chamfer one wall in from the slab's side face (pin axis
x=73.95, |y| = 26.3), so the socket's outer wall is 2.4 mm at the mouth; it is
14.6 mm from the front leg's socket. The pin, 6.3 mm deep in a socket 0.05 mm
over it, takes a push in X or Y in bearing; the ridge only holds the clip up,
as it holds a leg in, and the base's top stops 0.05 mm (``STOP_EPS``) under the
slab. The base's inner end steps down 1.5 mm (``CLIP_PRY_D``) for 2.5 mm under
the slab: the pry notch.

Spring channel: the 14 mm spring lies in a 15 mm channel in the floor, from
the rear face to the seat (x=81.8, under the funnel). Two lips flush with the floor top run its whole
length and overhang each long edge of the spring by 2 mm, so nothing above
(an empty magazine, the spring bowing under compression) lets it lift out:
the spring top sits 0.5 mm under the lip underside at its edge. The keel, the
slider web that pushes the spring's rear pad, is 9.3 mm wide, centred on the
pad over its full 7.5 mm height, and runs in the 10 mm slot between the lip tips
with 0.35 mm a side.

Return spring: variant B's section (1.2 mm beams, 3 mm gaps, 14 mm across) made
7.5 mm tall, with 42 beams so the 95 mm from free to full stroke (85 mm
stroke and 10 mm preload) closes 77% of each gap, under variant B's 79%. Its
rate from beam bending (``serpentine_rate``, PETG at 2 GPa, +-25%) is 199 N/m;
the physics joint spring uses 200 N/m (the nearest approved option), which
holds the slider home with 2.0 N and returns it from full stroke with
19.0 N. The beam strain at full stroke
(``serpentine_strain``, 3.4%) depends on the section and the gap closure, not
the height, so it stays variant B's. The same estimate gives variant B in the
prototype (12 beams, 5 mm tall) 500 N/m, the prototype's physics rate.

Assembly order:

1. With the housing upside down, push a leg's pin into each socket until it
   clicks. The legs sit wholly under the slab, inside the slider's frame, so
   they never get in the way of the steps below.
2. Slide the spring into the channel from the open rear end, seat pad first,
   until the seat pad stops on the seat. It cannot drop in from the top any
   more. Its free rear pad stands about 4.2 mm proud of the rear face.
3. Fit the slider from behind, the plate in line with the rear slot. At rest
   the plate and stem reach 6.4 mm through the slot, 4 mm of it into the bore,
   under the rear wall and the ramp, so the slider cannot be lowered on from above. Push
   it forward, before the clips are fitted, with the arms sprung out over the
   rails (2 mm, as when snapping on from above) until the grooves click onto the rails at home, where each
   groove's front end is 0.55 mm short of its rail's front end. The keel, narrower than the
   slot between the channel lips, enters the channel from its open rear end and
   pushes the spring's pad 10 mm in (the preload, about 2 N); at rest it reaches
   5.8 mm into the channel. The yoke then closes the channel's rear end. At full stroke
   the yoke's front face stops on the slab's rear face and the rear wall
   (0.05 mm of air at the CAD stroke, ``STOP_EPS``).
4. Push the handle onto the legs, as above.
5. Fit the backstop clips last, with the dispenser on its legs or lifted. Pull
   the handle a few mm forward so the slider legs stand clear, hold each clip
   under the slab, its plate outside the arm and behind the leg, and push it
   straight up until its pin clicks into the socket (about 42 N, as a leg); the
   plate rises 0.35 mm off the arm's outer face and the base passes under the
   arm. Let the handle go: the spring brings the legs back onto the clips. To
   take the slider off, remove both clips first: slide a flat screwdriver into
   the pry notch at the base's inner end, between the base and the slab
   underside, and twist to lever the clip down off its pin (about 60 N, as
   pulling a leg).
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
    PROTOTYPE_SPRING,
    SpringSpec,
    _cut,
    _fuse,
    _round_lower_edge,
    spring_solid,
)
from projects.pocky.params import Params

# Presentation distances (min/target protrusion, min past the shelf) come from
# ``p.syringe3``, as do the exit gap and the pusher plate band (see ``syringe_layout``).

# Sliding clearance per side between the slider and the housing.
SLIDE_CLEAR = 0.35
# The pusher plate band and the rear slot it runs in come from ``p.syringe3``.
PLATE_W = FACE_W  # 40, as the prototype bullnose
# Rear ramp on the rear wall's inner face, over the slot (see the module notes). Its face is this
# far from vertical: 55 deg from horizontal sheds a packet end for any friction under tan 55 = 1.4.
RAMP_DEG = 35.0
# The ramp's toe stops this far behind a centred packet's rear end, so the stack loads as before.
RAMP_PACKET_CLEAR = 0.5
# At rest the plate face sits mid-way between the toe and the rear wall's inner face, under the
# ramp, and at least this far from each, so print and assembly tolerance can neither push it past
# the toe (its top exposed to a falling packet) nor back to the wall (room behind the ramp).
PLATE_WINDOW_MARGIN = 3.0
# Undercut lip on the plate face: the top edge stands this far ahead of the face below it, the
# face leaning back this far from vertical under it, so a soft wrapper end is caught, not ridden.
PLATE_UNDERCUT = 0.6
PLATE_UNDERCUT_DEG = 15.0
# The lip's vertical front land, over the undercut: taller than half the 2.4 mm wall, so no
# min_wall ray through the top edge is thinner than the check's warn line.
PLATE_LIP_LAND = 1.3
# The slot and the ramp's underside stand at least this far over the plate top.
PLATE_HEADROOM = 0.25

# The table sits 52 mm under the packet plane so the bar can hang below the hand zone.
# The housing stands on four legs; its floor is a slab (``SyringeLayout.slab_z0``).
TABLE_Z = -52.0
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
# At home each groove's closed front end stands this much further ahead of its rail's front end
# than the backstop clips stand behind the legs, so it only stops the slider if a clip gives way.
GROOVE_BACKUP = 0.5

# Return spring: variant B's 1.2 mm beams, 3 mm gaps and 14 mm amplitude, made 7.5 mm tall
# (B is 5) so the long spring's rate is 200 N/m, and installed with 10 mm of preload (B has 3).
# Height raises the rate without raising the beam strain, which only the section and the gap
# closure set (see ``serpentine_rate``).
SPRING_H = 7.5
SPRING_PRELOAD = 10.0
# Printed PETG modulus for the rate estimate, as in the leg-joint notes.
PETG_E_MPA = 2000.0

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
SPRING_Z0 = -(LIP_T + LIP_OVER * _LIP_TAN + LIP_CLEAR) - SPRING_H  # -12.78
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
# Independent of the exit gap: the wedges centre packet 1, the exit wall separates the packets.
WEDGE_TOP = CHEEK_TOP  # 4.8
# Lead-in on each wedge's inner top edge, from the inner face's foot up to the wedge top at the
# bore wall, following the funnel. 60 deg from horizontal so a packet that lands with one corner
# on it slides in: with a quarter of its weight on the corner it slides while tan 60 > mu / 0.25.
WEDGE_LEAD_IN_DEG = 60.0
# The vertical face below the lead-in, which centres packet 1, is at least this tall.
WEDGE_GUIDE_MIN = 0.8

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

# Backstop clips (parts clip_n, clip_s), fitted last: on each side a plate outside the arm on a
# base under the slab, held by the housing legs' split snap pin in a slab socket (see the notes).
# The slider legs' rear faces stop on the clips' front faces at home, STOP_EPS of air in the CAD.
CLIP_L = 20.0  # along X
CLIP_X = (LEG_X0 - STOP_EPS - CLIP_L, LEG_X0 - STOP_EPS)
CLIP_PLATE_T = 3.0  # thicker than the wall for stiffness: 5 N at mid-arm bends it 0.03 mm (top 0.16)
# Pry notch: the base's inner end steps down under the slab, room for a flat screwdriver's tip.
CLIP_PRY_L = 2.5
CLIP_PRY_D = 1.5


@dataclass(frozen=True)
class LongSpring(SpringSpec):
    """Variant-B section and pitch, ``SPRING_H`` tall, with more beams, for the 85 mm stroke."""

    n_beams: int = 42
    z_height: float = SPRING_H

    @property
    def beams(self) -> int:
        return self.n_beams

    @property
    def height(self) -> float:
        return self.z_height


def serpentine_rate(spec: SpringSpec, e_mpa: float = PETG_E_MPA) -> float:
    """Estimated axial rate (N/mm) of a printed serpentine, from beam bending alone.

    The axial load runs along the centre line (y=0) and the pads apply no moment, so the
    bending moment at any point of the chain is F times its distance |y| from that line.
    Castigliano then gives a compliance of the integral of y^2 ds / EI: 2a^3/3 per free
    beam (a is the fold centre's |y|) and rc (pi a^2 + 4 a rc + pi rc^2 / 2) per
    semicircular fold of centre-line radius rc. The two end beams are fused to the pads and
    do not bend. Shear and axial strain are ignored, and E is a datasheet value, so treat
    the result as +-25%. For prototype variant B (12 beams, 5 mm tall) it gives 0.50 N/mm.
    """
    t, gaps = spec.thickness, spec.beams - 1
    rc = spec.pitch / 2.0
    a = spec.amplitude / 2.0 - rc - t / 2.0
    ei = e_mpa * spec.height * t ** 3 / 12.0
    beam = 2.0 * a ** 3 / 3.0
    fold = rc * (math.pi * a * a + 4.0 * a * rc + math.pi * rc * rc / 2.0)
    return ei / ((spec.beams - 2) * beam + gaps * fold)


def serpentine_strain(spec: SpringSpec, compression: float, e_mpa: float = PETG_E_MPA) -> float:
    """Peak bending strain at this compression (mm): at the fold crowns, |y| = a + rc."""
    t = spec.thickness
    rc = spec.pitch / 2.0
    a = spec.amplitude / 2.0 - rc - t / 2.0
    force = serpentine_rate(spec, e_mpa) * compression
    return 6.0 * force * (a + rc) / (spec.height * t * t) / e_mpa


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
    packet_h: float  # packet thickness, the bottom packet's top
    slot_w: float
    slot_h: float
    ramp_toe_x: float  # rear ramp's toe face, ahead of the rear wall's inner face
    ramp_land_top: float  # top of the toe's vertical land, where the sloped face starts
    ramp_top: float  # where the sloped face meets the rear wall's inner face
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
    clip_xy: tuple[tuple[float, float], ...]  # backstop clip pin axes: +Y, -Y
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

    @property
    def wedge_foot_z(self) -> float:
        """Top of the wedges' vertical inner face, where the lead-in starts (0.99)."""
        return self.wedge_top - (self.bore_y - self.wedge_y) * math.tan(math.radians(WEDGE_LEAD_IN_DEG))

    def wedge_lead_z(self, x: float, y: float) -> float:
        """Height of a wedge's lead-in at ``(x, |y|)``, outward of the funnel line, capped at the top.

        Over the ramp it rises perpendicular to the funnel line, after it straight across Y.
        """
        out = abs(y) - self.wedge_line_y(x)
        if x < self.bore_x1:
            out *= math.cos(math.radians(self.wedge_deg))
        return min(self.wedge_top, self.wedge_foot_z + out * math.tan(math.radians(WEDGE_LEAD_IN_DEG)))

    @property
    def plate_undercut_h(self) -> float:
        """Height of the plate's undercut face, under the lip's land (2.24)."""
        return PLATE_UNDERCUT / math.tan(math.radians(PLATE_UNDERCUT_DEG))

    @property
    def keel_rest_x(self) -> float:
        """Keel front at rest, flush with the plate face under the undercut; the spring pad's face."""
        return self.plate_rest_x - PLATE_UNDERCUT

    @property
    def wall_cover(self) -> float:
        """How much of packet 2's front face the exit wall covers above the window (it stops packet 2)."""
        return 2.0 * self.packet_h - self.gap

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
    def rail_engagement(self) -> float:
        """How far an arm must spread before its groove's closed end clears the rail tip (1.65)."""
        return RAIL_D - SLIDE_CLEAR

    @property
    def clip_in_y(self) -> float:
        """Backstop clip plate's inner face |y|, ``SLIDE_CLEAR`` outside the arm's outer face."""
        return self.side_y + SLIDE_CLEAR + ARM_T + SLIDE_CLEAR

    @property
    def clip_out_y(self) -> float:
        """Backstop clip plate's outer face |y|."""
        return self.clip_in_y + CLIP_PLATE_T

    @property
    def clip_base_in_y(self) -> float:
        """Backstop clip base's inner end |y|: a wall round the pin's well, then the pry notch."""
        return abs(self.clip_xy[0][1]) - PIN_WELL_R - self.wall - CLIP_PRY_L

    @property
    def clip_z0(self) -> float:
        """Backstop clip underside: a wall under the pin's well, as the leg columns."""
        return self.shoulder_z - PIN_WELL - self.wall

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
    sp = p.syringe3
    wall = p.structure.min_wall
    k = p.packet
    # The exit end stays where syringe has it, so the protrusion holds; the bore grows at the back.
    bore_x1 = p.magazine.length_i / 2.0
    bore_x0 = bore_x1 - sp.bore_length
    bore_y = p.magazine.width_i / 2.0
    rear_x = bore_x0 - wall
    exit_x = bore_x1 + EXIT_WALL
    shelf_x = exit_x + LIP_LEN
    # The ramp's toe stands just behind a centred packet's rear end; the plate face rests behind it.
    ramp_toe_x = -k.length / 2.0 - RAMP_PACKET_CLEAR
    ramp_land_top = sp.slot_h + wall
    ramp_top = ramp_land_top + (ramp_toe_x - bore_x0) / math.tan(math.radians(RAMP_DEG))
    plate_rest_x = 0.5 * (ramp_toe_x + bore_x0)
    for what, margin in (("the ramp's toe", ramp_toe_x - plate_rest_x),
                         ("the rear wall's inner face", plate_rest_x - bore_x0)):
        if margin < PLATE_WINDOW_MARGIN:
            raise ValueError(f"plate face at rest ({plate_rest_x:.2f}) is {margin:.2f} mm from {what}, "
                             f"under {PLATE_WINDOW_MARGIN} mm: lengthen syringe3.bore_length")
    # The final plate face is the trailing edge, whatever the packet's start in the bore.
    lead_min = max(exit_x + sp.min_protrusion, shelf_x + sp.min_past_shelf)
    lead_target = max(exit_x + sp.target_protrusion, lead_min)
    stroke_min = lead_min - k.length - plate_rest_x
    stroke = lead_target - k.length - plate_rest_x
    gaps = math.ceil((stroke + SPRING_PRELOAD) / (PROTOTYPE_SPRING.gap * MAX_GAP_CLOSURE))
    spring = LongSpring("S", PROTOTYPE_SPRING.thickness, n_beams=gaps + 1)
    installed = spring.installed(SPRING_PRELOAD)
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
    # Each clip's socket is a leg socket with its mouth chamfer one wall in from the slab's side.
    clip_y = side_y - wall - SOCKET_CHAMFER - PIN_HALF - PIN_CLEAR
    clip_xy = tuple((0.5 * (CLIP_X[0] + CLIP_X[1]), s * clip_y) for s in (1.0, -1.0))
    # The window must pass one packet but reject two: packet 2 rests on packet 1 at
    # z = packet.height .. 2*packet.height, so a gap in between leaves the wall covering its front face.
    if not k.height < sp.exit_gap < 2.0 * k.height:
        raise ValueError(f"syringe3.exit_gap {sp.exit_gap} must be between one packet ({k.height}) "
                         f"and two ({2.0 * k.height}) to pass one packet and reject two")
    lay = SyringeLayout(
        gap=sp.exit_gap,
        wall=wall,
        bore_x0=bore_x0,
        bore_x1=bore_x1,
        bore_y=bore_y,
        rear_x=rear_x,
        exit_x=exit_x,
        shelf_x=shelf_x,
        side_y=side_y,
        top=p.stack_nominal_height + p.magazine.headroom,
        blade_x0=k.length / 2.0 - BLADE_BITE,
        blade_top=sp.exit_gap + BLADE_T,
        packet_h=k.height,
        slot_w=PLATE_W + 2.0 * SLIDE_CLEAR,
        slot_h=sp.slot_h,
        ramp_toe_x=ramp_toe_x,
        ramp_land_top=ramp_land_top,
        ramp_top=ramp_top,
        plate_z0=sp.plate_z0,
        plate_z1=sp.plate_z0 + sp.plate_h,  # the slider's print face (4.9)
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
        clip_xy=clip_xy,
        bar_z0=BAR_Z0,
        bar_z1=BAR_Z1,
        leg_x1=LEG_X1,
        keepout=keepout,
        spring=spring,
        spring_installed=installed,
        spring_full=installed - stroke,
        seat_x=plate_rest_x - PLATE_UNDERCUT + installed,
        separator=separator,
        wedge_x0=bore_x1 - WEDGE_LEAD,
        wedge_y=k.width / 2.0 + WEDGE_CLEAR,
        wedge_top=WEDGE_TOP,
    )
    if lay.slot_h - lay.plate_z1 < PLATE_HEADROOM:
        raise ValueError(f"syringe3.slot_h {lay.slot_h} leaves under {PLATE_HEADROOM} mm over the "
                         f"plate top ({lay.plate_z1}); the slot and the rear ramp must clear it")
    if lay.plate_z1 >= k.height:
        raise ValueError(f"plate top {lay.plate_z1} must stay under packet 2's underside ({k.height}), "
                         f"which it slides under during the stroke")
    if lay.wedge_foot_z < WEDGE_GUIDE_MIN:
        raise ValueError(f"wedge lead-in leaves a {lay.wedge_foot_z:.2f} mm guide face, under "
                         f"{WEDGE_GUIDE_MIN} mm")
    if lay.plate_undercut_h + PLATE_LIP_LAND > lay.plate_z1 - lay.plate_z0:
        raise ValueError("the plate undercut is taller than the plate")
    if SLIDE_CLEAR >= lay.rail_engagement:
        raise ValueError(f"the backstop clips let an arm spread {SLIDE_CLEAR} mm, not less than the "
                         f"{lay.rail_engagement:.2f} mm that unhooks it from its rail")
    # The arm runs beside each clip at every stroke, so the clip limits its spread throughout.
    if not (lay.yoke_rest_x - YOKE_T + lay.stroke <= CLIP_X[0] and CLIP_X[1] <= LEG_X0 + 1.0):
        raise ValueError(f"the arm does not cover the backstop clips (x {CLIP_X}) at every stroke")
    # Each clip's socket keeps a wall to the front housing leg's socket, and its base clears the column.
    sock = 2.0 * (PIN_HALF + PIN_CLEAR + SOCKET_CHAMFER)
    for cx, cy in lay.clip_xy:
        for lx, ly in lay.leg_xy:
            if abs(cx - lx) < sock + wall and abs(cy - ly) < sock + wall:
                raise ValueError(f"backstop clip socket at x {cx:.2f} meets the leg socket at x {lx:.2f}")
            if abs(cy - ly) < HLEG_D and abs(cx - lx) < HLEG_D / 2.0 + (CLIP_X[1] - CLIP_X[0]) / 2.0:
                raise ValueError(f"backstop clip base (x {CLIP_X}) meets the housing leg column at x {lx:.2f}")
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
    """Side funnel wedge on the ``sign`` side wall: plan-view ramp, a vertical inner face up to
    ``wedge_foot_z`` and the lead-in above it (see ``wedge_lead_z``)."""
    by, wy = lay.bore_y, lay.wedge_y
    plan = [(lay.wedge_x0, by), (lay.bore_x1, wy), (lay.exit_x, wy),
            (lay.exit_x, by + 0.5), (lay.wedge_x0, by + 0.5)]
    body = _prism_xy([(x, sign * y) for x, y in plan], -0.2, lay.wedge_top)
    # Keep what is under the lead-in plane through the inner face's top edge, in (Y, Z) across
    # that edge: straight across Y after the ramp, and turned by the funnel angle over the ramp.
    foot, t, reach = lay.wedge_foot_z, math.tan(math.radians(WEDGE_LEAD_IN_DEG)), 5.0
    section = [(wy - reach, -1.0), (by + reach, -1.0), (by + reach, foot + (by + reach - wy) * t),
               (wy, foot), (wy - reach, foot)]
    section = [(sign * y, z) for y, z in section]
    straight = _prism_yz(section, lay.bore_x1, lay.exit_x + 1.0)
    along = _prism_yz(section, lay.wedge_x0 - 10.0, lay.bore_x1 + 10.0)
    along = (Pos(lay.bore_x1, sign * wy, 0.0) * Rot(0.0, 0.0, -sign * lay.wedge_deg)
             * Pos(-lay.bore_x1, -sign * wy, 0.0) * along)
    along = along & _box(lay.wedge_x0 - 1.0, lay.bore_x1, -by - reach, by + reach, -2.0,
                         lay.wedge_top + 2.0)
    return (body & (straight + along)).solid()


def _ramp_solid(lay: SyringeLayout):
    """Rear ramp across the bore, down to the floor; the slot cut later frees the plate under it.

    Section in (X, Z): a vertical land at the toe up to ``ramp_land_top``, then the face rising
    ``RAMP_DEG`` from vertical back to the rear wall's inner face at ``ramp_top``.
    """
    back = lay.bore_x0 - 0.2
    rise = 0.2 / math.tan(math.radians(RAMP_DEG))
    section = [(back, -0.2), (lay.ramp_toe_x, -0.2), (lay.ramp_toe_x, lay.ramp_land_top),
               (back, lay.ramp_top + rise)]
    return _prism_xz(section, -lay.bore_y - 0.2, lay.bore_y + 0.2)


def housing_solid(lay: SyringeLayout):
    """Floor slab, tube, rear ramp, exit wall, blade or wedges, shelf, cheeks, rails; slot, channel, sockets cut."""
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
        # No bite: the exit wall's sharp lower edge sets the gap (it covers ``wall_cover`` of packet 2's
        # front face), and the wedges centre the packet.
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
    body = _fuse([slab, *sides, rear, _ramp_solid(lay), front, *separator, *cheeks, *rails])
    # The slot runs on under the ramp to its toe, so the ramp's underside continues the slot's roof.
    slot = _box(lay.rear_x - 1.0, lay.ramp_toe_x + 0.5, -lay.slot_w / 2.0, lay.slot_w / 2.0,
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
    sockets = [Pos(x, y, 0.0) * _socket_cutter(lay) for x, y in (*lay.leg_xy, *lay.clip_xy)]
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


def _snap_pin(zs: float):
    """Split snap pin at the XY origin, seated with its shoulder at ``zs``: (pin and ridges, well, slot).

    Fuse the pin and ridges into a body with the well cut from it, then cut the slot.
    """
    h = PIN_HALF
    well = Pos(0.0, 0.0, zs - PIN_WELL / 2.0 + 0.5) * Cylinder(PIN_WELL_R, PIN_WELL + 1.0)
    pin = _box(-h, h, -h, h, zs - PIN_WELL - 0.5, zs + PIN_TOP)
    # Ridges across the two outer prong faces (normal Y); each overlaps its prong by 0.5 mm.
    lo, hi = _ridge_u()
    ridge = [(h - 0.5, zs + lo), (h, zs + lo), (h + PIN_RIDGE_H, zs + PIN_RIDGE_Z), (h, zs + hi),
             (h - 0.5, zs + hi)]
    xr = h - PIN_RIDGE_INSET
    ridges = [_prism_yz([(s * w, z) for w, z in ridge], -xr, xr) for s in (1.0, -1.0)]
    # The slot splits the pin into two prongs down to the well floor and stays inside the well.
    slot = _box(-h - 1.0, h + 1.0, -PIN_SLOT / 2.0, PIN_SLOT / 2.0, zs - PIN_WELL, zs + PIN_TOP + 1.0)
    return [pin, *ridges], well, slot


def leg_solid(lay: SyringeLayout, index: int):
    """Housing leg ``index`` (0..3) seated in its socket: foot pad, column, well and split snap pin."""
    x, y = lay.leg_xy[index]
    zs = lay.shoulder_z
    pad = Pos(0.0, 0.0, TABLE_Z + FOOT_T / 2.0) * Cylinder(FOOT_D / 2.0, FOOT_T)
    col_z0 = TABLE_Z + FOOT_T - 0.2
    column = Pos(0.0, 0.0, (col_z0 + zs) / 2.0) * Cylinder(HLEG_D / 2.0, zs - col_z0)
    pin, well, slot = _snap_pin(zs)
    body = _fuse([_cut(_fuse([pad, column]), [well]), *pin])
    leg = _cut(body, [slot])
    return (Pos(x, y, 0.0) * leg).solid()


def leg_solids(lay: SyringeLayout) -> dict:
    """The four identical legs, ``leg_1`` .. ``leg_4`` in ``lay.leg_xy`` order."""
    return {f"leg_{i + 1}": leg_solid(lay, i) for i in range(len(lay.leg_xy))}


def clip_solid(lay: SyringeLayout, index: int):
    """Backstop clip ``index`` (0 on +Y, 1 on -Y), seated: a base under the slab carrying the legs'
    split snap pin in its socket, and a plate rising outside the arm, ``SLIDE_CLEAR`` off it, its
    front face ``STOP_EPS`` behind the slider leg's rear face at home."""
    x, y = lay.clip_xy[index]
    zs = lay.shoulder_z
    yp = abs(y)
    x0, x1 = CLIP_X
    # Built on +Y, then mirrored for -Y; the pin is symmetric in Y.
    base = _box(x0, x1, lay.clip_base_in_y, lay.clip_out_y, lay.clip_z0, zs)
    plate = _box(x0, x1, lay.clip_in_y, lay.clip_out_y, zs - 0.2, lay.plate_z1)
    notch = _box(x0 - 1.0, x1 + 1.0, lay.clip_base_in_y - 1.0, lay.clip_base_in_y + CLIP_PRY_L,
                 zs - CLIP_PRY_D, zs + 1.0)
    at = Pos(x, yp, 0.0)
    pin, well, slot = _snap_pin(zs)
    body = _fuse([_cut(_fuse([base, plate]), [at * well, notch]), *[at * s for s in pin]])
    clip = _cut(body, [at * slot]).solid()
    return clip if y > 0.0 else clip.mirror(Plane.XZ).solid()


def clip_solids(lay: SyringeLayout) -> dict:
    """The two backstop clips, ``clip_n`` (+Y) and ``clip_s`` (-Y), mirror images."""
    return {f"clip_{tag}": clip_solid(lay, i) for i, tag in enumerate(("n", "s"))}


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
    slider_top = lay.plate_z1
    arm_in = lay.side_y + SLIDE_CLEAR
    arm_out = arm_in + ARM_T
    x_back = yf - YOKE_T
    yoke = _box(x_back, yf, -arm_out, arm_out, ARM_Z0, slider_top)
    # The plate face is the stem's front; the keel under it is the spring pad.
    # The keel is narrower than the spring, so it runs in the slot between the channel lips.
    stem = _box(yf - 0.2, lay.plate_rest_x, -lay.plate_w / 2.0, lay.plate_w / 2.0,
                lay.plate_z0, slider_top)
    keel = _box(yf - 0.2, lay.keel_rest_x, -KEEL_HALF_W, KEEL_HALF_W, SPRING_Z0, lay.plate_z0 + 0.2)
    arms = [
        _box(x_back, LEG_X0 + 1.0, arm_in, arm_out, ARM_Z0, slider_top),
        _box(x_back, LEG_X0 + 1.0, -arm_out, -arm_in, ARM_Z0, slider_top),
    ]
    # Each leg is full height, so it rises straight off the bed in the print pose.
    legs = [
        _box(LEG_X0, LEG_X1, arm_in, arm_in + LEG_W, BAR_Z0, slider_top),
        _box(LEG_X0, LEG_X1, -arm_in - LEG_W, -arm_in, BAR_Z0, slider_top),
    ]
    frame = _fuse([yoke, stem, keel, *arms, *legs])
    # Each groove covers every rail position over the stroke. Its closed front end on the rail's
    # front end is the backup home stop, GROOVE_BACKUP behind the clips' (the legs on the clips).
    stop_x = RAIL_X[1] + STOP_EPS + GROOVE_BACKUP
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
    cutters.append(_undercut_cutter(lay))
    slider = _cut(frame, cutters)
    return (Pos(travel, 0.0, 0.0) * slider).solid()


def _undercut_cutter(lay: SyringeLayout):
    """What the undercut removes ahead of the plate face: the lip's land is vertical at the plate
    face, under it the face leans back ``PLATE_UNDERCUT_DEG`` to ``PLATE_UNDERCUT`` behind it."""
    xp, z0, z1 = lay.plate_rest_x, lay.plate_z0, lay.plate_z1
    xb = xp - PLATE_UNDERCUT
    zt = z1 - PLATE_LIP_LAND
    section = [(xb, z0 - 1.0), (xp + 2.0, z0 - 1.0), (xp + 2.0, z1 + 1.0), (xp, z1 + 1.0),
               (xp, zt), (xb, zt - lay.plate_undercut_h)]
    half = lay.plate_w / 2.0 + 1.0
    return _prism_xz(section, -half, half)


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
    x0 = lay.keel_rest_x + travel
    if length is None:
        length = lay.seat_x - x0
    return spring_solid(lay.spring, length, x0, 0.0, SPRING_Z0)


def syringe_solids(p: Params, stroke_fraction: float = 0.0, free_spring: bool = False,
                   separator: str = "wedge") -> dict:
    """Housing, slider, handle, spring, the four legs and the two backstop clips at one stroke
    fraction (0 rest, 1 forward stop).

    The handle is clipped onto the slider; the legs and clips are seated in the housing's sockets.
    The spring is at its compressed
    length for that stroke, so it touches the keel and the seat.
    ``free_spring`` gives the printed (free) spring instead, which runs
    ``SPRING_PRELOAD`` mm into the seat in this pose. ``separator`` picks the
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
        **clip_solids(lay),
    }


def wall_shape_for(name: str, p: Params, stroke_fraction: float = 0.0):
    """The handle's undecorated base (no PULL deboss); other parts have no decoration."""
    if name == "handle":
        lay = syringe_layout(p)
        return handle_solid(lay, lay.travel(stroke_fraction), text=False)
    return None


def print_location_for(name: str, shape) -> Location:
    """Housing on its slab, slider upside down on its z=4.9 face, legs on their feet, handle and spring as is."""
    if name == "slider":
        flip = Rot(180.0, 0.0, 0.0)
        return Pos(0.0, 0.0, -(flip * shape).bounding_box().min.Z) * flip
    return on_bed(shape)


def min_wall_override(name: str, p: Params) -> float | None:
    """Only the spring beams are thinner than ``structure.min_wall`` on purpose."""
    if name == "spring":
        return syringe_layout(p).spring.thickness
    return None
