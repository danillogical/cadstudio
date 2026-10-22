# Plan: first prototype

Progress against this plan is in `report-current-progress.md`.

Status at the last progress report (2026-10-18): M0 and M1 are done, Gate A passed, and nothing has been printed. No spring, body, chassis, lip, or shim solid exists yet.

Decision after that report: skip the spring coupons and the linkage fixture. Go straight to the prototype. This supersedes the "Next step" in `report-current-progress.md` and steps 1–2 of the earlier draft of this plan. The first print is the assembled 10-packet unit, with the Coupon B spring (1.2 mm beams) built in. The risk is accepted in the open: the spring rate and the printed-peg fit are first seen on the full print, not on a coupon or a fixture. A failure there costs a reprint of the spring, a peg, the crank, or the rod. It does not cost the body, unless the CAD checks below were skipped.

This is the plan from the current M1 linkage to the first thing we print and judge. It covers one 10-packet dispenser made entirely of PETG. A metal spring, steel pins, heat-set inserts, and the 50- and 100-cycle tests stay on the durability path in `plan-pockey-dispenser.md`. They are not part of this prototype.

The root plan still holds for licensing, the packet frame, and the decision not to build a second magazine or a 100-packet machine. Where it asks for a metal spring or for Gate D cycle counts, this file wins until the printed prototype has been accepted or rejected.

M1 is already done. `projects/pocky/models/linkage_motion.py` passed Gate A: straight pusher, 180° reversing crank, 50 mm face travel, 23.09 mm button travel, pivot (−78, −8). Those kinematic numbers stay. This plan changes what the parts are made of, how they assemble, and what "good" means on the bench.

## What we are printing

One module a person can load from the top and operate with one hand.

- Magazine for 10 packets. The tube height follows `magazine.capacity_test`. A 25-packet tube is a later print of the same mechanism.
- The M1 linkage, with printed pegs in place of steel dowels.
- An original printed return spring. `Resorte.stl` is the reference dispenser's printed serpentine. It is evidence that a printed spring can return a short slider. It is not our part. Its beam count, 1.50 mm beams, 2.30 mm gaps, 62.5 mm free length, and 9.7 × 6 mm section are not copied.
- A separator whose gap is set with printed shims, and an 18 mm presentation lip.
- No metal, no inserts, no purchased spring.

The prototype is the assembled 10-packet unit. There are no earlier prints. No spring coupon and no linkage fixture are modelled, printed, or gated on. The checks that would have run on them move into CAD (below) and into a dry cycle of the assembled unit before any real packet is loaded.

## Decisions locked for this print

These avoid a second crank design before any plastic exists.

| Choice | Value | Why it is locked now |
|---|---|---|
| Dispense axis | +X, push the 55 mm end | Already the M1 recommendation. Stick direction is still unmeasured. The print is how we learn it. If sticks crack, the next iteration is +Y, not a quiet change inside this one. |
| Presentation | 40 mm past the outer face | Middle of the 30–50 mm range. 22 mm of that hangs past the 18 mm lip. |
| Button | y = −28, about 40 mm stick-out at rest | Off the packet edge. A centred button needs another link. |
| Crank | R = 50, ±30°, included angle 180°, pivot (−78, −8) | Gate A. Do not move it to make the housing easier. |
| Packet | 165 × 55 × 5.2, bore 170 × 60 | Already in `projects/pocky/params.toml`. |
| Separator target | 5.75 mm (`separator.gap`) | One printed shim on a 5.35 mm ledge. |
| Material | PETG, Prusa XL, 0.4 mm nozzle | Walls stay at `structure.min_wall` (2.4 mm) unless a feature is a spring beam or a shim. |
| Linkage constants | In `projects/pocky/geometry/linkage.py`, not in `params.toml` | The progress report confirms they were never moved. Do not add linkage keys to `params.toml` for this prototype. Derive stroke and radius from the packet and magazine as `linkage_from` already does, so a `--set packet.length=…` cannot leave the crank short of the stroke. |
| Shim stock | Printed PETG, 0.4 mm and 0.8 mm | This supersedes the 0.20 mm stainless scheme in `projects/pocky/docs/mechanism-proposal.md`. No stainless is bought or fitted for this print. |
| Pins | Printed PETG pegs | This supersedes the Ø4 / Ø5 steel dowels in the proposal and in M1. Steel is a durability-path repair only, under the waiver in "After the run". |
| Spring | Coupon B geometry only: 12 beams, 1.2 mm thick, 3.0 mm gap, 53.4 mm free | No coupon selection. B was the starting coupon and the housing was already drawn around it. A and C are contingency reprints only if B fails on the bench (see "After the run"); they are not printed first. |
| Pre-prototype prints | None | Coupons and the linkage fixture are skipped by decision. Do not model them. |

## Left to the bench

CAD will not close these. The prototype is built so each one is a small part swap, not a new housing.

- Real packet thickness at the centre, at both end seals, and under a stack of 10. If an end seal is taller than the chosen gap, that shim setting fails and the next thicker shim is tried.
- Which edge is the fin, and how far it sticks out in X.
- Whether an axial push cracks sticks. That is the +X risk accepted above.
- Whether the 1.2 mm spring returns the rod under one thumb, and whether it cracks or whitens at a fold. There is no coupon to answer this first. It is answered on the assembled unit, in the dry cycle and the bench run.
- Peg clearance after printing. The drawing starts at the values below. The prototype may open a slot by 0.2 mm, as a documented reprint of the crank or the rod. It may not move the crank.

## Parts

All of these are printed. Assembly is by hand. No tong, no screw, no insert.

| Part | Role | Print note |
|---|---|---|
| `body` | 10-packet tube, floor, exit wall, separator ledge, lip cheeks | Floor on the bed. The tube grows upward. The floor is a solid face so the part sits flat. |
| `chassis` | Basement: crank pivot boss, rod guides, both stops, spring-seat pocket, open top | Clips up against the underside of the floor. Printed as its own part because a basement cannot hang below a floor that is on the bed. |
| `lip` | 18 mm presentation shelf and the moving half of the separator | Separate so the shim stack can be changed without reprinting the body. |
| `shim` | 0.4 mm and 0.8 mm plates | Two 0.2 mm layers for 0.4 mm. A single 0.2 mm layer is not used. |
| `crank` | Straight reverser, hub, radial slot, pusher peg | Flat, bores and peg vertical. |
| `pusher` | Carriage, neck, 40 × 4.2 bullnose | Neck through the floor slot. |
| `rod` | Button, head, home flange, forward shoulder, button peg, spring pad | Long axis on the bed. |
| `spring` | Serpentine, original, Coupon B geometry (1.2 mm beams) | Flat. Bends in the plane of the bed. The only spring in the first print. Print one spare in the same job. |
| `spring_seat` | Removable seat insert in the chassis pocket; sets the installed spring length | The B insert is printed with the prototype. It exists so a contingency A or C spring can be fitted later with a new insert, without reprinting the chassis. See "Printed spring". |
| `peg` | Pivot, pusher, button. Three short spares of each | Sacrificial. A sheared peg is a reprint of the peg, not of the crank. |
| `dummy` | Two or three rigid packets from `packet_dummy` | Separator and fit only. Acceptance uses real packets. |

The M1 model stays the kinematic reference. The printable assembly is a new model, `projects/pocky/models/prototype.py`, so the Gate A files are not retuned in place. Do not edit `projects/pocky/models/linkage_motion.py`, `projects/pocky/geometry/linkage.py`, or `projects/pocky/docs/m1_sweep.py` to make the prototype fit. When the prototype model exists, the sweep is re-run with the printed clearances by a new script (see "What CAD must show before slicing the body").

### Print orientation and slicing

M1 left two overhang warnings open (rod 2138.8 mm², pusher 118.5 mm² in the assembly pose). The print poses below close that question. `overhangs` is WARN only, but a part whose warning is larger in its print pose than in the M1 assembly pose is printed the wrong way up.

| Part | Print pose | Slicing note |
|---|---|---|
| `body` | Floor on the bed, tube up | No support inside the bore. |
| `chassis` | Open top up, pivot boss up | Hooks must not need support on their catching faces. If they do, move the hook, not the pivot. |
| `lip` | Separator face down on the bed | That face stays flat and unfiled. |
| `shim` | Flat | 0.4 mm is two 0.2 mm layers; 0.8 mm is four. No brim that has to be trimmed off the gap face. |
| `crank` | Flat, bores and peg holes vertical | As in M1. |
| `pusher` | Carriage flat, bullnose up | The return chamfer is the only expected overhang warning, and it is small. |
| `rod` | Long axis on the bed, head flat side down | The M1 rod warning came from the assembly pose. In this pose the head overhang should mostly disappear. Record the new area in the build report. |
| `spring` | Flat, bends in the bed plane | 0.2 mm layers, 100% infill. Beams run along the nozzle path so a fold is not a single weak start-stop. |
| `peg` | Head down, shaft up | Short print. Print spares in the same job. |
| `dummy` | Flat | As `packet_dummy` already prints. |

Everything except the spring and the shims uses the project's normal PETG profile. Layer height is 0.2 mm where a dimension in Z sets a gap (shims, separator, pusher height).

## Printed spring

The spring sits beside the rod, on the −Y side of it, between a pad on the rod and a seat on the chassis. It compresses by exactly the button travel. It is not on a metal guide. Out-of-plane stiffness comes from its height. In-plane folding is the serpentine.

Starting point, not a measured rate. The 0.30 N/mm catalog target is a durability-path number and is not a requirement here.

There is no coupon print. The prototype spring is variant B. Variants A and C are kept in the table only as contingency reprints if B fails on the bench. They are not modelled or printed for the first prototype, and no letter is "chosen" before the print.

| | Variant A (contingency) | Variant B (prototype) | Variant C (contingency) |
|---|---:|---:|---:|
| Beams | 12 | 12 | 12 |
| Beam thickness | 1.0 | 1.2 | 1.6 |
| Gap | 3.0 | 3.0 | 3.0 |
| Pitch | 4.0 | 4.2 | 4.6 |
| End pads | 3.0 | 3.0 | 3.0 |
| Free length | 51.0 | 53.4 | 58.2 |
| Height (layer direction) | 5.0 | 5.0 | 5.0 |
| Amplitude | 14 | 14 | 14 |

Variant B, the prototype spring and the one the housing is drawn around:

- Solid length is 12 × 1.2 + 2 × 3.0 = 20.4 mm. The pads do not fold.
- Installed length is 50.4 mm, so preload is 3 mm. That preload holds the home flange. It is not the old 10 mm metal preload.
- Full press length is 50.4 − 23.09 = 27.3 mm.
- Margin before the beams touch is 27.3 − 20.4 = 6.9 mm. The shoulder hits the forward lug first. The spring is not the stop.
- Compression available before solid is 33 mm, which covers the 23.09 mm stroke, the 3 mm preload, and that margin.

Variants A and C change only the beam thickness, so a contingency reprint does not teach three things at once. If B cannot be pressed by one thumb, the contingency is A (thinner, softer). If B cracks at a fold or will not return the rod, the contingency is C (thicker, stronger return). Do not adopt 1.50 mm beams on a 2.30 mm gap. That is the reference spring.

The same sums for the contingency variants. The margin before solid is the same by construction, because the pitch grows with the beam:

| | Variant A | Variant B | Variant C |
|---|---:|---:|---:|
| Solid length (12 × beam + 2 × 3.0 pads) | 18.0 | 20.4 | 25.2 |
| Installed length (free − 3.0 preload) | 48.0 | 50.4 | 55.2 |
| Full-press length (installed − 23.09) | 24.9 | 27.3 | 32.1 |
| Margin before solid at full press | 6.9 | 6.9 | 6.9 |

Because the free lengths differ, A and C do not drop into the B seat at the same preload. The chassis therefore holds a removable `spring_seat` insert. The B insert sets the installed length to 50.4 mm. An A contingency prints a new insert that moves the seat face 2.4 mm toward the rod (installed 48.0 mm). A C contingency prints an insert recessed 4.8 mm the other way (installed 55.2 mm). The chassis pocket must have that 4.8 mm of recess available behind the B insert. Only the spring and the insert are reprinted. The chassis and body are not.

Geometry that the table does not state, fixed here so the spring can be modelled without guessing:

- The 12 beams are straight, parallel, and joined by semicircular folds that alternate ends. Beam centreline length is the amplitude less one beam thickness, so the outside across the folds stays 14 mm for every variant.
- Fold inner radius is the larger of the beam thickness and 0.8 mm. The fold outer radius is the inner radius plus the beam thickness. No sharp inner corner.
- End pads are 3.0 mm along the spring axis, the full 14 mm wide, and the full 5.0 mm tall. They do not fold. Their seat faces are flat and square to the axis. No hole in a pad; the rod pad and the `spring_seat` insert clamp the pad faces.
- The spring axis is parallel to the rod travel. Its centreline sits on the −Y side of the rod, clear of the crank's swept disc and of the button slot. The Y offset is set in `prototype.py` and checked by the prototype sweep, since there is no fixture to set it on.
- Height is the layer direction (5.0 mm, 25 layers at 0.2 mm). The spring is not printed on edge.

Folds are semicircular, at least the beam thickness in radius, so the bend is not a sharp inner corner. The seat faces are flat and square to the rod. The spring is wider than the reference section on purpose (14 mm across the folds, 5 mm tall) so it does not buckle out of the plane the way a 6 mm-tall strip would over a 23 mm stroke.

The spring is not guided laterally except by its two seat faces and the chassis wall clearance beside it. Leave at least 0.5 mm per side between the folds and any wall, so a fold that spreads under compression does not rub. Rubbing is a seat failure to fix in the chassis or the insert, not by thinning the beam.

## Printed joints

M1 used a Ø4 steel dowel in a 4.30 mm slot and a Ø5 steel pivot in a Ø5.2 bore. PETG in PETG needs more room, and the peg has to come out when it wears.

| Joint | Peg | Hole or slot | Clearance |
|---|---|---|---|
| Pivot | Ø5.0, head on the chassis side | Ø5.4 bore in the 11 mm hub | 0.4 mm diametral |
| Pusher | Ø4.0, head keeps the carriage from lifting | 4.6 mm wide Y-slot | 0.6 mm |
| Button | Ø4.0, head keeps the rod on the crank | 4.6 mm wide radial slot | 0.6 mm |

Slot end arcs stay 1 mm beyond the peg-centre travel, as in M1. Pegs are not the stops. Each peg is a 4 mm grip in the crank or the rod plus a head. The hub outer diameter stays 11 mm.

What replaces what, so the M1 solids are not edited by mistake:

| M1 (steel, motion study only) | Prototype (printed) |
|---|---|
| Ø4.0 dowel, Ø4.1 holes, 4.30 mm slots | Ø4.0 pegs, 4.6 mm slots. The pusher Y-slot in the carriage and the radial button slot in the crank both widen. The crank hole that grips the pusher peg and the rod hole that grips the button peg stay a 4 mm grip fit. |
| Ø5.0 pivot pin, Ø5.2 bore, hub from the M1 review | Ø5.0 pivot peg, Ø5.4 bore in the same 11 mm hub. |

Peg construction, all three joints:

- Shaft diameter as in the table. Grip length 4.0 mm in the part that holds the peg (crank for the pusher peg, rod for the button peg, chassis boss for the pivot peg).
- The shaft then passes through the mating part with the clearance in the table, plus the 0.4 mm Z gap between the M1 layers. Total shaft length is grip + gap + mating thickness + 0.2 mm end allowance. Do not shorten it to make assembly easier.
- Head on the far side: 2.0 mm thick, shaft diameter + 3.0 mm across (Ø7.0 for the Ø4.0 pegs, Ø8.0 for the Ø5.0 pivot peg). The head is what stops the peg walking out. There is no second head and no cotter.
- A 0.5 mm × 45° chamfer on the shaft tip only. No chamfer on the grip, so the grip stays a grip.
- Pegs print head down. Three spares of each size are printed with the first set.

If the assembled prototype binds, open the sliding slots by 0.2 mm and reprint the crank or the rod, not the body. If a peg is sloppy, reprint the peg 0.2 mm larger. The crank angles do not change.

## Housing split and keep-outs

The body prints with the floor on the bed and the tube upward. Anything below the floor is the chassis, clipped on afterwards. The clip is a pair of printed hooks on the chassis and a pair of ledges on the body. The hooks are reached from outside. They are not inside the packet bore.

Two keep-outs are already known. Neither is fixed by moving the pivot.

- For part of the stroke the crank crosses the bore in plan. A magazine wall that continues down through the basement will hit it. The tube walls stop at the floor. The chassis wall on the crank side is outside the crank's swept disc (radius 54.5 mm about the pivot) by at least 1 mm.
- At full stroke the button peg centre is at x = −89.55. A 2.4 mm back wall whose inner face is at x = −85 would cut the peg. The back wall of the tube also stops at the floor. The chassis leaves a clear cylinder of Ø6 around that peg for the whole stroke.

The floor slot stays the M1 slot: the neck envelope plus 2 mm in X and 0.5 mm per side in Y. At the default packet it is x ∈ [−93.1, −35.1], y ∈ [−3.5, 3.5].

Housing sizes that follow from the locked numbers, stated so the body can be modelled:

- Tube internal size is the bore, 170 × 60 mm. Walls are `structure.min_wall` (2.4 mm) except the exit wall, which stays 3.0 mm as in the proposal. Outside the tube is therefore about 175 × 65 mm before the lip and button are added. Each part is checked against the 360 mm bed on its own; the assembled footprint is not a bed check.
- Tube height above the floor follows `magazine.capacity_test`: stack height `capacity_test × packet.height` (52 mm at 10) plus `magazine.headroom` (20 mm), so 72 mm above the floor at 10 packets. The top is open for loading. No lid is modelled for this prototype; a lid is styling and is not required below.
- The floor is 2.4 mm thick (`floor z ∈ [−2.4, 0]` in assembly coordinates, as in M1). The basement below it keeps the M1 Z bands (carriage, crank, rod, each 4.0 mm with 0.4 mm gaps), so the chassis is about 18 mm deep. The prototype does not re-space those bands.
- The rod guides are part of the chassis. They hold the rod on y = −28 for its full travel, with 0.3 mm per side, and they do not touch the crank's swept disc.
- The back wall and the side walls of the tube stop at the floor, per the keep-outs above. Only the chassis is below the floor, and its crank-side wall stays outside the swept disc.

The chassis clip: two hooks on the chassis engage two ledges on the body, reached from outside the packet bore. Each hook deflects at most 1.0 mm to engage, has a catching face square to −Z so the chassis cannot drop off without deflecting, and can be released by hand from outside. No hook, ledge, or finger tab sits inside the bore or in the crank sweep.

The lip's foil edges and the separator's lower edge are at least R0.8. The bullnose and the 30° × 1.2 mm return chamfer stay as drawn.

## Separator

The gap is measured from the floor (z = 0, the underside of the bottom packet) to the separator's lower edge on the lip. The ledge with no shim is a 5.35 mm gap. Printed shims stack on it. The lip clamps them when it is hooked on.

The lip hooks onto the body from outside the bore, like the chassis clip, and is removable by hand so the shim stack can be changed. No screw, insert, or tool. The lip carries the 18 mm presentation shelf and its side cheeks. The cheeks keep the presented packet from sliding sideways off the shelf and stay below the separator edge, so they cannot narrow the gap.

| Shims | Gap |
|---|---:|
| none | 5.35 |
| one 0.4 mm | **5.75** |
| one 0.8 mm, or two 0.4 mm | 6.15 |
| one 0.8 mm plus one 0.4 mm | 6.55 |

Two rigid packets are 10.4 mm, so every setting refuses a rigid pair. The bench starts at 5.75 mm. A jam on a thick seal moves one step coarser. A double feed of two real packets moves one step finer. The body is not reprinted to chase the gap.

## Order of work

### 0. Packet measurements, if packets are on hand

This does not block step 1. The progress report lists all of these as unmeasured, and the bench cannot close acceptance criterion 9 without them.

Measure and write down, before the body is modelled if possible, and on the bench day at the latest:

- Thickness at the centre and at both end seals, on at least three packets.
- Thickness of a stack of 10 (or the measured centre thickness × 10 next to the real stack, if the stack will not sit square for a caliper).
- Which edge carries the fin, and how far the fin sticks out past the sticks in X.
- Stick direction, from one opened packet: along the 165 mm length or across it. If the sticks run across the length, stop. That is the "+X has failed before printing" case in "After the run", and it is cheaper to learn it here.

Record the values in `projects/pocky/docs/prototype-log.md` when that file is created, with the date. Do not change `packet.height` in `params.toml` to a seal measurement. The 5.2 mm rigid envelope stays.

### 1. Model the prototype

Model `projects/pocky/models/prototype.py` in one step: `body`, `chassis`, `lip`, `shim` set, `spring_seat` (B insert), `crank`, `pusher`, `rod`, `spring` (variant B only), `peg` set, and `dummy` packets. No coupon model. No fixture model.

Reuse the M1 kinematics through `linkage_from` and the pose functions. Replace the steel-pin dimensions with the printed-peg dimensions in the prototype model only. Keep the M1 Z bands, the floor slot bounds, and the pivot.

Run the rigid checks in the next section before slicing. Do not slice a part whose check report has a FAIL.

Exit: `prototype.py` builds, the check report passes, and the prototype sweep passes.

### 2. Print the prototype

Print every part in "Parts", plus one spare spring, three spare pegs of each size, and two dummy packets. Print poses and slicing are in "Print orientation and slicing".

Measure the spring's free length before assembly and confirm 53.4 mm within 0.5 mm. A spring that prints short is a modelling or slicing error. Do not assemble it and call it a soft spring.

Assemble by hand. Confirm the clip holds the chassis on when the unit is lifted by the tube. No filing of a load-bearing face to make it assemble. A binding slot is a documented 0.2 mm reprint of the crank or the rod.

### 3. Dry cycle, on the assembled unit

This is the fixture gate, moved onto the prototype because there is no fixture. It runs before any real packet is loaded. All four are required:

1. The button reaches both stops. The spring is still short of solid at the forward stop (daylight between beams, or a 0.5 mm feeler).
2. Letting go returns the flange to the home stop without help, 20 times out of 20, with no packet.
3. No peg walks out, and no peg has sheared. No fold has cracked. Whitening at a fold is written down.
4. With a dummy packet: 10 pushes across the floor. The dummy moves forward and is left where the face stops supporting it when the button is released. The face parks behind the dummy's back edge.

A dry-cycle failure is reprinted as a peg, a slot, a spring, or a seat insert. It is not a reason to redraw the crank angles, and it does not start the bench run.

### 4. Bench

Follow the acceptance criteria below. Write the result in `projects/pocky/docs/prototype-log.md` (created when the print exists, not before): date, shim stack, spring variant, packet measurements taken that day, cycle count, and every failure in one line.

## What CAD must show before slicing

Headless, on the prototype model, with the printed clearances and the variant B spring envelope as a solid. Because there is no fixture print, this section is the only fit check before the full print. It is not optional and it is not reduced.

Commands, in this environment (see the progress report on `UV_NO_SYNC=1`):

```
UV_NO_SYNC=1 uv run cad build pocky/prototype --render --check --views standard
UV_NO_SYNC=1 uv run python projects/pocky/docs/prototype_sweep.py
```

- Every part is one valid solid, fits the 360 mm bed, and rests on z = 0 in its own print pose. `min_wall` does not FAIL. The spring is the one exception: set its `ModelPart.min_wall` to its beam thickness (1.2 mm for variant B), because the beams are the flexure. Its pads, the `spring_seat`, and every other part stay at `structure.min_wall` (2.4 mm). Do not set a low `min_wall` on any other part to hide a thin wall.
- Gate A again, at 21 button positions, forward and return: no crank-to-wall, peg-to-slot-end, or pusher-to-second-packet intersection. Designed contacts (face tangent to the bottom packet after contact, flange near the home stop, shoulder near the forward lug, spring pads on their seats) are listed and are not counted as failures. This runs in a new script, `projects/pocky/docs/prototype_sweep.py`, modelled on `m1_sweep.py` but using the printed clearances, the peg solids, the housing, and the spring envelope. It writes `out/pocky/prototype/gate_a.json`. `m1_sweep.py` and the M1 files are not edited.
- Gate B: a 5.2 mm packet passes the 5.75 mm gap. Two stacked rigid packets (10.4 mm) do not, at every shim setting from 5.35 to 6.55. The pusher face stays at or below z = 4.2, under the second packet at z = 5.2.
- The spring envelope at home and at full stroke does not intersect the rod, the chassis, or the crank. At full stroke its length is at least 6 mm longer than its solid length (27.3 mm against 20.4 mm for variant B, a 6.9 mm margin).
- Pegs, modelled as solids, stay at least 1 mm from every slot end at both stops, and the pivot peg clears the housing for the whole stroke. The Ø6 clear cylinder around the button peg at x = −89.55 (full stroke) is empty of housing.
- The chassis hooks do not intersect the body when seated, and the chassis cannot fall off along −Z without a hook deflecting.
- Add tests as `tests/test_pocky_prototype.py`: the spring solid length and free length for variant B, the peg clearances, the seat-insert offsets for the contingency variants, and that `prototype.py` builds every part in "Parts". Never edit a test to make the model pass. Fix the model.

A boolean failure here is fixed in the housing or the peg clearance. It is not fixed by editing R, the ±30° swing, or the pivot.

## Acceptance criteria

Judged on the assembled prototype, PETG only, real wrapped packets, shim at the setting the bench settled on. A dummy packet does not count toward these cycles.

The run is 10 cycles: load 10 packets, dispense until empty. One refill is allowed only to replace a packet that was set aside for inspection, not to retry a jam. A jam, a double feed, or a return that needs a finger ends the run as a fail.

1. **One press, one packet.** Each of the 10 cycles presents a single packet. A second packet does not come out on a full press, and it does not come out on a press that stops halfway and returns.
2. **Present and support.** The packet sticks out between 30 and 50 mm past the outer face, the lip still carries it, and it can be pinched past the lip without the dispenser being tipped.
3. **Return.** After the packet is taken, letting go of the button puts the flange on the home stop and parks the pusher fully behind the bore. The next packet is on the floor. It is not sitting on the bullnose. This happens on every cycle of the run, without touching the pusher.
4. **Stops.** The forward shoulder hits the lug while the spring beams still have daylight between them. The button head never enters the wall.
5. **Damage.** Open 3 of the 10 packets. No broken stick and no punctured wrapper. A light crease is written in the log and does not by itself fail the run.
6. **Separator.** At the shim setting used for the run, one real packet passes and two real packets do not, including when the second is pressed down by hand onto the first. The check is done once, before the 10 cycles, and once more after them.
7. **Printed only.** The unit as tested contains no metal pin, insert, screw, shim, or spring. A repair that adds one is a fail of this gate, and the start of the durability path instead.
8. **Assembly.** The parts go together by hand, the chassis stays on when the tube is lifted, and no load-bearing face was filed. A documented 0.2 mm slot reprint is allowed. Filing is not.
9. **Records.** `projects/pocky/docs/prototype-log.md` names the spring variant fitted, the shim stack, the dry-cycle result, the 10-cycle result, the three opened packets, the packet thickness at the centre and at both end seals, which edge is the fin and how far it sticks out, and the stick direction from the opened packets.

Passing all nine accepts the prototype. It does not accept a 25-packet machine, and it does not retire the durability plan.

## Not required of this prototype

- A spring coupon print, a coupon selection, or a linkage fixture print. All three are skipped by decision. The dry cycle in step 3 is not a fixture by another name. It uses the prototype's own parts.
- 25 packets, or the same run at half-full and nearly empty as a formal gate. Doing them as a look is fine. They are not acceptance.
- 50 or 100 consecutive cycles. Those belong to Gate D, after a metal spring and steel pegs if the printed ones wear out.
- A measured spring rate, a catalog spring, or the 10 mm / 0.30 N/mm metal preload.
- Heat-set inserts, stainless shims, or a centred button.
- Proof that foil never creases, or that a 25-high stack cannot squash two packets into the gap.
- Styling, a second magazine, electronics, or a wall mount.

## After the run

- All nine pass: stop. The next decision is whether to print the 25-packet tube on the same chassis, or to start the durability path. Neither starts automatically.
- A double feed or a jam at every shim setting: change the separator or the face, re-run the rigid checks, reprint only that part.
- The spring cracks or will not return: move one variant (A if B is too stiff to press by one thumb, C if B cracked or will not return) and reprint the spring and its `spring_seat` insert only. Do not lengthen the button stroke to make a weak spring feel softer. This contingency reprint is not a coupon programme. One variant change is tried. If that also fails, the printed spring is rejected and the durability path decides what replaces it.
- Sticks break or the far seal is punctured: stop this geometry. The +X choice has failed for this packet, and the next study is +Y. Do not add cycles hoping it was a bad packet.
- A peg shears inside 10 cycles: reprint the peg. If the replacement shears too, that joint is the first durability change (steel dowel in the existing hole) and criterion 7 is waived only for that peg, in writing, in the log.

## Final step: simulation and ejection video

This was not in the plan before. The CAD section gives static renders and a sweep JSON. Neither shows the cycle moving. This step adds both, after the bench decision above. It is a record of the geometry. It is not a bench result, it does not count toward the 10 cycles, and it does not prove the foil or the sticks are safe. Rigid packets do not compress, settle, or break.

### What is made

A new headless script, `projects/pocky/docs/prototype_animation.py`. It does not edit `m1_sweep.py`, `prototype_sweep.py`, or any M1 file. Run it in this environment with:

```
UV_NO_SYNC=1 uv run python projects/pocky/docs/prototype_animation.py
```

Outputs, all under `out/pocky/prototype/animation/` (generated, not committed):

| File | Contents |
|---|---|
| `ejection_iso.mp4` | Isometric video of one full cycle: press, one rigid packet ejected +X through the separator onto the 18 mm lip, packet taken away, release, pusher return, next packet drops to the floor. |
| `ejection_side.mp4` | Same cycle from the side (XZ plane), with the near tube wall and near chassis wall translucent or omitted, so the pusher face, the separator gap, the second packet, and the crank are visible. |
| `simulation.json` | One row per frame: button fraction, crank angle (deg), button travel, pusher face x, bottom-packet shift, protrusion past the outer face, second-packet z, slot-end clearances, and overlap status. |
| `ejection_poster.png` | Still contact sheet from the same frames: home, first contact, half stroke, full presentation, and parked after return. |
| `frames_iso/`, `frames_side/` | The numbered PNG frames the videos were encoded from, kept so a single frame can be inspected without decoding video. |

### How the cycle is scripted

One normalised button-travel parameter drives everything, through the same `phi_for_button_fraction` and `pose_at_phi` used by the prototype sweep. No pose is hand-placed.

- Sample the press at 0, 2, 4, …, 100 percent of button travel (51 poses), then the return on the same 51 poses in reverse. Hold 10 frames at home at the start, 10 frames at full presentation, and 10 frames at home at the end, so the ends can be read. 132 frames total.
- Forward branch: the bottom packet stays put until the face reaches its back edge, then follows the face (`packet_shift` from the pose). At full stroke it protrudes 40 mm past the outer face and rests on the lip. The second packet does not move in X and does not enter the gap.
- Presentation hold: the bottom packet is then removed from the scene (taken by hand). It is not dropped, and it is not pushed back in.
- Return branch: the packet shift stays at the parked value used by Gate A, so the pusher retracts behind the bore and leaves the presented packet's space empty. Only in the last 10 frames does the second packet translate down one packet thickness (5.2 mm) to the floor. That drop is a scripted translation, labelled as such in `simulation.json`. It is not a gravity or friction simulation.
- The spring is drawn compressed and extended by the button travel. The pegs are drawn as solids in their slots. The housing is the prototype housing, at the shim setting fitted on the bench (default 5.75 mm).

### Rendering and encoding

- Render headless with PyVista off-screen, as `cadkit/render.py` already does, at its 1400 × 1000 window size. Tessellate each pose once per view.
- The camera is fixed for the whole video, framed on the rest-pose assembly bounds. It does not track, zoom, or refit per frame. A moving camera would hide the 40 mm presentation.
- Encode with `ffmpeg` (already checked in this environment) to H.264 MP4, `yuv420p`, 15 fps, so the 132 frames run about 9 seconds. If `ffmpeg` is missing, the script fails and says so. It does not write the frames and report success as if a video existed.
- Run the prototype sweep's overlap check at every sampled pose before encoding. Any frame with a forbidden overlap, or a slot-end clearance under 1 mm, stops the script with a FAIL and no video is presented as passing. The per-frame status goes in `simulation.json`, and the video is only encoded from a passing run.

### Recording it

Append to `projects/pocky/docs/prototype-log.md`: the two video paths, the poster path, `simulation.json`, the frame count and duration, the shim setting and spring variant modelled, the sweep status the frames were checked against, and the exact command run. Note in the same entry that the packet drop at the end is scripted.

Acceptance is unchanged. A clean video with a failed bench is still a failed prototype, and a passed bench with no video is accepted but has an incomplete record until this step is run.
