# Mechanism proposal — Pocky packet dispenser

M0 proposal for review. This is an original linkage sized from the packet and from `plan-pockey-dispenser.md` §4. The reference notes supplied the mechanism class and four measured problems: 12.7 mm of sideways tip scrub, a 5.0 mm exit gap against a 5.2 mm packet, four forward stops within 0.6 mm, and about 0.3 mm of full-diameter pin engagement. The dimensions below come from this packet, not from those meshes.

Nothing here is in `params.toml`. Do not start M1 from this file until the open questions at the end are answered.

The sweep that produced the pose table and `proposal-diagram.png` is `proposal_sweep.py` in this directory:

```
.venv/bin/python projects/pocky/docs/proposal_sweep.py
```

## Frame

Same origin as `geometry/packet.py`. The packet is centred on X and Y. Z is up, and the underside of the bottom packet is z = 0.

| | |
|---|---|
| Packet | x ∈ [−82.5, +82.5], y ∈ [−27.5, +27.5], z ∈ [0, 5.2] |
| Magazine bore | x ∈ [−85, +85], y ∈ [−30, +30] (`magazine.length_i` 170, `magazine.width_i` 60) |
| Exit | +X. The outer front face is at x = 88 (3 mm wall outside the bore) |
| Button | On the front, below the floor, centred at y = −28. Pressing moves it toward −X |

The 2.5 mm of slack at each end and each side is the slack already implied by the magazine and packet numbers. The packet sits centred at rest.

## Recommendation: dispense along +X

Push the 55 mm end, along `packet.length`. The contact face is the end seal.

| | +X, push the 55 mm end | +Y, push the 165 mm side |
|---|---|---|
| Stick load, if the six sticks lie along the 165 mm length | Compression along the sticks | Bending across the sticks |
| Edge that gets pushed | The end crimp | The long edge, which may only be a fold |
| Packet travel for 40 mm past the outer face | 45.5 mm | 45.5 mm |
| Length still on the magazine floor at full stroke | **122 mm** | **12 mm** |
| Clear of the 18 mm lip, for fingers | 22 mm, with 143 mm still supported | A longer lip still leaves a short, floppy seat |
| Pusher | 40 mm of the 55 mm end | A broad face on a 165 mm side is a large carriage |
| Side clearance that resists cocking | 2.5 mm on the short sides | 2.5 mm on the long ends, so a cock has a long lever |

+Y cannot meet the plan's 30–50 mm protrusion and still leave a supported packet. After a 40 mm presentation the packet occupies y = 18 to 73, and the floor ends at y = 30, so 12 mm remains on the floor. A 5.2 mm foil packet will hinge down at the exit. +X leaves 122 mm on the floor and 22 mm past the lip to grasp.

This rests on one assumption to confirm by feel or by opening one packet: the sticks are a single layer parallel to `packet.length`. If they lie the other way, the recommendation flips and M1 stops.

## Linkage

One slider, one crank, two pin-slots, one translating pusher.

The button rod slides on a straight line, y = −28, and carries a Ø4 steel pin. That pin runs in a short radial slot in the crank. The crank turns on a fixed pivot at **(−78, −8)**. The other end of the crank carries a second Ø4 steel pin in a cross-slot on the pusher carriage, so the carriage can only move in X. The contact face is fixed to the carriage, stays square to the packet, and travels in a straight line. Sideways scrub of the contact is zero. The reference tip moved 12.7 mm along the sachet edge because the tip was fixed to the rotating arm; a 40 mm face on a rotating arm would yaw and hit on a corner, so the face has to translate.

The crank included angle is **180°**. It is a straight reversing lever: the button pin and the pusher pin sit on opposite sides of the pivot, so a push toward −X drives the packet toward +X. A bend (the reference arm is 131°) lengthens the button slot and widens the speed-ratio swing. At 180° the button slot uses 3.09 mm of a 5.1 mm slot. Both slots stay at least 60° off the line of motion, so there is no dead point and no over-centre position in the stroke.

The crank, the button rod, and the carriage live **under the floor**. The face is the only part that enters the magazine, through a 7 mm floor slot on the centreline. In the plan view the dashed lines cross the packet; they are in the basement, not in the bore.

```
button rod  --pin-->  radial slot in the crank  --pivot-->  pin in the carriage cross-slot  -->  40 mm face
   y = −28                         (−78, −8)                         face travels in +X only
```

### Why these lengths

Pusher stroke is fixed by the presentation target and the packet:

```
stroke = presentation + exit_wall + (magazine.length_i − packet.length) + pocket_setback
       = 40 + 3 + 5 + 2
       = 50 mm
```

The face parks at x = −87, which is 2 mm behind the inner back wall, and finishes at x = −37. The packet back is at x = −82.5, so the first 4.5 mm of face travel (2.56 mm of button travel) is approach. The packet then moves 45.5 mm and protrudes 40.0 mm past x = 88.

The crank radius equals that 50 mm stroke because the arm swings symmetrically through ±30° about the +Y direction (crank angle from +X runs from 120° down to 60°). Travel in X is `R (cos 60° − cos 120°) = R`. The torque arm of the pusher force never drops below `R cos 30° = 43.3 mm`.

The button stands 20 mm off the pivot, on the magazine side of it (y = −28). Peak speed ratio is then `R / 20 = 2.50`, at mid-stroke, and the ends are `2.50 × sin³ 60° = 1.63`. Overall, 50 mm of pusher travel takes `2 × 20 × tan 30° = 23.09 mm` of button. A larger offset would soften the peak and lengthen the thumb stroke, and it would push the rod further off the packet. 23 mm and a peak of 2.5 is the compromise: the reference peaked at 3.6.

Ideal force ratio is the inverse of the speed ratio: 0.62 at each end, 0.40 at mid-stroke, before friction.

### Pose table

From `proposal_sweep.py`. Button travel is the press, from the home stop. Protrusion is the packet front relative to the outer face at x = 88; the negative value at rest is the 2.5 mm front gap plus the 3 mm wall.

| % | Button (mm) | Crank (deg) | Face x | Pusher-pin y | Slot radius | Packet shift | Protrusion |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0.00 | 0 | −87.00 | 35.30 | 23.09 | 0.00 | −5.50 |
| 25 | 6.19 | 15 | −74.94 | 40.30 | 20.71 | 7.56 | 2.06 |
| 50 | 11.55 | 30 | −62.00 | 42.00 | 20.00 | 20.50 | 15.00 |
| 75 | 16.91 | 45 | −49.06 | 40.30 | 20.71 | 33.44 | 27.94 |
| 100 | 23.09 | 60 | −37.00 | 35.30 | 23.09 | 45.50 | 40.00 |

Speed ratio at the ends of that table is 1.63, and 2.50 at 50%. The diagram plots the whole curve.

## Pusher face

A 40 mm × 4.2 mm bullnose, radius 2.1 mm, so the section is a full round. It covers the middle of the 55 mm end and leaves 7.5 mm of seal on each side.

- The face spans y = −20 to +20. The bore is at ±30. If the packet shifts by the whole 2.5 mm side clearance, the face still overlaps the packet by 37.5 mm and still clears the wall by 7.5 mm.
- The top of the face is at z = 4.2. A rigid second packet starts at z = 5.2, so the face passes 1.0 mm under it. The separator is at 5.75, so the face passes 1.55 mm under the lip.
- The lower rear edge carries a 30° chamfer, 1.2 mm long, so a return stroke that meets a sagging foil edge cams under it instead of hooking a wrinkle.
- The neck that drops through the floor is 6 mm wide. The slot is 7 mm wide (0.5 mm per side). The packet sits on the lands beside that slot, about 24 mm under each side of the packet.
- At rest the whole head is behind x = −85, in the pocket, clear of the stack. The head does not sit under the packet, so the floor does not need the reference's under-stack ramp. A 1 mm fillet where the floor meets the back wall is enough for the foil.

The nominal cycle is press, release, then take the packet. The stack drops after the head is home. If the packet is pulled out while the button is held, the head is still up in the magazine (at full stroke it is at x = −37, 4.2 mm tall and 40 mm wide) and the next packet lands on it. The bullnose keeps that from being a knife edge. It can still tilt the next packet. That case is misuse, and M4 should watch for it.

## Separator and shims

`separator.gap` stays **5.75 mm**. That is the assembled gap with the default shims. The housing does not grow or shrink to change it.

The lip is a separate PETG bar on two M3 screws into heat-set inserts. The screws clamp it onto a stack of **0.20 mm stainless shims**. The printed ledge, with no shims, sets the gap to **5.35 mm**. Two shims add 0.40 mm and land on 5.75. Each extra shim adds 0.20 mm. Six shims is the top of the slot in the screw pattern, at 6.55 mm.

| Shims per screw | Gap (mm) |
|---:|---:|
| 0 | 5.35 |
| 1 | 5.55 |
| 2 | **5.75** (default, `separator.gap`) |
| 3 | 5.95 |
| 4 | 6.15 |
| 5 | 6.35 |
| 6 | 6.55 |

A sliding slot would drift. A shim stack is a number you can write down. The lip's lower edge is rounded to R0.8. Two rigid packets are 10.4 mm, so even the 6.55 mm setting refuses a rigid pair. Whether two packets squashed by a 25-high stack can enter 5.75 mm is not something the rigid model can answer.

## Presentation lip

The floor continues 18 mm past the outer face, coplanar with z = 0, with side cheeks about 6 mm high. Edges that foil can touch are at least R1. Of the 40 mm protrusion, 22 mm hangs past the lip for a pinch grip, and the lip carries the rest so the packet does not hinge on the exit edge.

## Spring and stops

A metal compression spring on a Ø4 guide pin beside the button rod. The printed serpentine in the reference is not the baseline.

| | |
|---|---|
| Rate | 0.30 N/mm |
| Preload at the home stop | 10 mm, about 3.0 N |
| Compression at the forward stop | 33.1 mm, about 9.9 N |
| Travel before solid | at least 36 mm, so the stop hits first |
| Inside / outside | ID ≥ 5 mm on the Ø4 pin, OD ≤ 12 mm |
| Free length | about 70–80 mm, long enough for that travel |

A spring near 40 mm free length cannot take 33 mm of compression and still have a margin before it goes solid. The catalog part is an M1 purchase against the row above.

The spring is sized for a light, positive return, not from a measured dispense force. An allowance of 8 N at the pusher (snag, not a measurement) times the peak ratio 2.50 is 20 N, plus the 9.9 N spring, about 30 N at the thumb at the end of a hard stroke. A clean stroke is mostly the spring.

Stops, one in each direction, both on the button rod:

- **Home.** The flange bears on the inner face of the front wall (x = 85). The spring preload holds it there.
- **Forward.** A shoulder on the rod meets a housing lug after 23.09 mm. The lug is not the spring seat.

At both poses each pin is at least 1.0 mm from either end of its slot. The slots and the carriage rails are clearance, not stops. The button head is 14 mm long and its inner face stays at least 3 mm outside the wall, so the head never enters the hole. At rest the head sticks out about 40 mm; that is the stroke plus the 3 mm margin plus the head.

Pins are Ø4 steel dowels with a 4.30 mm slot (0.30 mm diametral clearance to tune at print time). Each pin bears on the full 4 mm thickness of the crank plate. The pivot is a Ø5 steel pin in an 8 mm hub, bore about Ø5.2. Walls elsewhere stay at or above `structure.min_wall` (2.4 mm). The exit wall is 3.0 mm.

## What stays the same for 10 and for 25 packets

The linkage, the floor, the separator, the lip, and the button do not change with `magazine.capacity_test`. Only the tube above the floor changes. Stack height is `capacity_test × packet.height` (52 mm at 10, 130 mm at 25) plus `magazine.headroom` (20 mm). The basement under the floor is about 18 mm. A 25-packet body is on the order of 230 × 110 × 175 mm, inside the 360 mm bed.

## Parameters

### Already in `params.toml` (unchanged)

| Name | Value | Role here |
|---|---:|---|
| `packet.length` | 165 | Long axis, the dispense direction |
| `packet.width` | 55 | End-seal width the face pushes |
| `packet.height` | 5.2 | Rigid thickness |
| `magazine.length_i` | 170 | Bore along X, centred |
| `magazine.width_i` | 60 | Bore along Y, centred |
| `magazine.headroom` | 20 | Room above the stack |
| `magazine.capacity_test` | 10 | Tube height only; 25 uses the same linkage |
| `separator.gap` | 5.75 | Default assembled gap, two shims |
| `structure.min_wall` | 2.4 | Floor for wall thickness |

### Proposed for M1, not yet in `params.toml`

| Name | Value | Where it comes from |
|---|---:|---|
| `presentation` | 40 mm | Middle of the plan's 30–50 mm |
| `exit_wall` | 3.0 mm | Above `structure.min_wall` |
| `pocket_setback` | 2.0 mm | Head parks fully behind the back wall |
| `pusher_stroke` | 50 mm | 40 + 3 + 5 + 2 |
| `crank_radius` | 50 mm | Equals the stroke for a ±30° swing |
| `crank_half_angle` | 30° | Keeps the pusher torque arm ≥ 43.3 mm |
| `crank_included_angle` | 180° | Straight reverser; shortest button slot |
| `pivot_xy` | (−78, −8) mm | Face lead 16 mm, rest face at x = −87 |
| `face_lead` | 16 mm | Face ahead of the pusher pin |
| `button_offset` | 20 mm | Sets the peak speed ratio to 2.50 |
| `button_y` | −28 mm | Rod just outside the packet edge |
| `button_stroke` | 23.09 mm | `2 × 20 × tan 30°` |
| `pusher_face_width` | 40 mm | Broad on the 55 mm end |
| `pusher_face_height` | 4.2 mm | 1.0 mm under a rigid second packet |
| `pusher_nose_radius` | 2.1 mm | Full bullnose |
| `return_chamfer` | 30° × 1.2 mm | Lower rear of the head |
| `floor_slot_width` | 7.0 mm | 6 mm neck plus 0.5 mm per side |
| `pin_diameter` | 4.0 mm | Steel dowel, both joints |
| `slot_width` | 4.30 mm | 0.30 mm clearance, to tune |
| `slot_end_margin` | 1.0 mm | Pins are not the stops |
| `pivot_pin_diameter` | 5.0 mm | Steel, in an 8 mm hub |
| `lip_length` | 18 mm | Leaves 22 mm to grasp |
| `shim_thickness` | 0.20 mm | Stainless; two shims hit `separator.gap` |
| `separator_gap_min` | 5.35 mm | Zero shims |
| `spring_rate` | 0.30 N/mm | Return feel, not a measured drag |
| `spring_preload` | 10 mm | About 3 N at home |

## Unverified physical behaviour

The sweep is geometry. It does not show any of the following.

- Real packet thickness at the centre, on the end seals, and under a stack of 10 and of 25. The rigid 5.2 mm envelope does not compress.
- Whether an end seal thicker than 5.75 mm in Z will jam, or a fin that sticks out in X will crumple under the bullnose.
- Stick direction, and whether an axial push cracks sticks or pokes one through the far seal.
- Stack drag and the real button force. The 8 N pusher allowance and the 30 N thumb figure are allowances.
- Foil catching on layer lines, on the floor-slot edges, or on the return chamfer.
- Two softened packets feeding together at 5.75 mm, especially under a 25-packet stack.
- The stack dropping square once the packet is taken.
- What happens when a packet is pulled while the button is held.
- Wear of the PETG slots on the steel pins, and whether 0.30 mm slot clearance is enough after printing.

## Open questions

1. **Dispense axis.** +X, pushing the 55 mm end seal, is the recommendation. It stands only if the sticks lie along the 165 mm length. Confirm that, or say to use +Y anyway.
2. **Presentation.** 40 mm past the outer face, 22 mm of it past the lip. Closer to 30 or to 50 changes the stroke, the crank, and the button.
3. **Button.** It sits at y = −28, beside the packet edge, and sticks out about 40 mm at rest. Say if it has to be on the centreline. A centred button needs a second reverser and was not drawn.
4. **Packet measurements** before the shim range is locked: thickness at centre and at both end seals, thickness under a 10-stack and a 25-stack, which edge is the fin, how far the fin extends past the sticks, and the stick direction.
5. **Shims.** 0.20 mm stainless is the scheme. Say if that stock is on hand. Printed shims under about 0.4 mm are not a substitute.
6. **Spring.** Buy to the spec in the spring table, or match a spring already on hand. A 40 mm spring does not have the travel.

M1 is not authorized by this proposal.
