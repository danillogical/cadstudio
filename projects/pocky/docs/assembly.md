# Assemble the printed prototype

Hand assembly of the 10-packet PETG dispenser. The pictures are the print meshes in `out/pocky/prototype/`, put back into the pose they have on the unit. Nothing here has been printed, and a picture is not a cycle count.

The orange part in each step is the one you add. The exit is the open end of the tube, the end with the two small ledges and, once it is on, the lip. The button is the tall pad on the long side, the same side as the spring pocket. Where a triad is drawn, red points toward the exit and blue is up.

No screws, inserts, or metal pins. Leave load-bearing faces as printed.

## Parts

Each box below is zoomed to fill, so a small part looks as large as the tube. The next picture is the small parts at one scale. These are the poses they had on the printer: peg heads on the bed, bullnose up, separator face of the lip down, chassis open side up.

![Printed parts](assembly/00-parts.png)

![Small parts at one scale](assembly/00b-small-parts.png)

The two Ø4 pegs are the same shape. One holds the pusher, one holds the button. The pivot peg is the one with the wider head.

| Leave off the unit | Count |
|---|---:|
| Spare spring | 1 |
| 0.8 mm shim | 1 |
| Spare pivot pegs | 3 |
| Spare Ø4 pegs | 6 |
| Spare dummy | 1 |

The copies are laid out in `out/pocky/prototype/plate.3mf`. The springs on that plate are solid. The shims have no brim.

Measure a spring along its length before it goes in the pocket. It should be 53.4 mm, within 0.5 mm. A short spring is a slicing error. Reprint it. The second spring stays in the spare pile.

If a slot binds, reprint the crank or the rod 0.2 mm more open. If a peg is sloppy, reprint that peg 0.2 mm larger. The crank angles stay as printed.

## 1. Chassis

![Chassis, open side up](assembly/01-chassis.png)

Set the chassis open side up, the way it printed. The round boss is the pivot. The rectangular bay on the button side is the spring pocket. The two rails beside that bay are the rod guides. The two towers are the clips that will catch the body.

## 2. Spring seat

![Seat in the pocket](assembly/02-seat.png)

Drop the seat into the pocket, against the steps at the back of the bay. The face toward the open end of the pocket is the face the spring pushes on. It is a 4 × 14 × 5 mm block. The A and C seats are not in this print.

## 3. Spring

![Free spring against the seat](assembly/03-spring.png)

Lay the spring in the pocket with one pad against the seat. The bends stay in the horizontal plane. The printed spring is 53.4 mm, and the picture is that mesh sitting on the seat. The far pad stands 3 mm past where the rod will land. That 3 mm is the preload. Leave the spring at its printed length. The rod takes the 3 mm up in the next step.

Pictures after this one show the spring at the installed length, 50.4 mm. That length is the same spring, squeezed by the preload. It is not a second part.

## 4. Rod

![Rod in the guides](assembly/04-rod.png)

Slide the rod into the two rails, tall pad on the same side as the spring. The pad's home position is toward the exit. Pressing it moves the rod toward the back of the chassis and squeezes the spring. Letting go lets the spring push the rod back until the flange meets the stop.

The blue spring in this picture is the installed length. Once the rod is in, the flange should sit on the home stop without you holding it.

## 5. Crank

![Crank on the pivot boss](assembly/05-crank.png)

Lay the crank flat on the boss. The middle hole goes over the boss. The slotted end points toward the button. The round hole at the other end is for the pusher peg. This is the home angle. Leave it there.

## 6. Pivot peg

![Pivot peg from the side](assembly/06-pivot-peg.png)

![Pivot peg from below](assembly/06b-pivot-below.png)

Use the wider peg. Come up from below the chassis. The chamfered tip goes through the boss and shows in the crank's middle hole. The head stops in the round recess on the underside. There is no second head.

## 7. Pusher

![Pusher, bullnose up](assembly/07-pusher.png)

Set the pusher on the crank with the bullnose up and the carriage down. The round hole in the crank is under the slot in the carriage. The body is still off. When the body comes down, the bullnose passes up through the slot in the floor.

## 8. Pusher peg

![Pusher peg](assembly/08-pusher-peg.png)

Take one Ø4 peg. The head goes up. The chamfered tip goes down through the slot in the carriage and into the round hole in the crank. The head stays above the carriage. Do this before the body is on. The head lives in the relief under the floor, and it will not pass through that floor afterward.

## 9. Button peg

![Button peg](assembly/09-button-peg.png)

The other Ø4 peg goes through the slot in the crank and into the rod. Head up, chamfered tip down. The head stays above the crank. The peg slides in the slot as the button moves. It is not a stop.

## 10. Body

![Body lowered onto the chassis](assembly/10-body.png)

![Chassis hook](assembly/11-hook.png)

Lower the body, floor down, onto the chassis. The bullnose comes up through the floor slot. Each tower on the chassis clips over a rib on the body. The tooth at the top of the tower reaches back over that rib. To release a clip, ease the tooth outward about 1 mm. Both clips are outside the tube.

Lift the unit by the tube. The chassis has to stay on.

## 11. Shims

![One shim on each ledge](assembly/12-shims.png)

![Shim on the ledge](assembly/13-shim-close.png)

Put one 0.4 mm shim on each ledge at the exit. One ledge, one shim. Leave the 0.8 mm plate off the unit. This stack is the 5.75 mm gap. Leave the faces as printed.

## 12. Lip

![Lip on the exit](assembly/14-lip.png)

![Lip hook](assembly/14b-lip-hook.png)

Hook the lip on from the exit, from outside the tube. Push until the tooth on each hook sits behind the bar on the body. It comes off by hand, outward about 1 mm. The underside of the separator blade was the face on the printer bed. Leave that face flat. The shelf is the 18 mm landing in front of the tube.

## Assembled

![Assembled, no packet](assembly/15-finished.png)

![The same assembly with the body translucent](assembly/16-inside.png)

This is the unit for the empty dry cycle. The spare spring, the 0.8 mm shim, the spare pegs, and the second dummy stay off it. No packet is in the tube.

## Dry cycle

Run this before any real packet. All four are required.

1. The button reaches both stops. At the forward stop the spring still has daylight between the beams, or a 0.5 mm feeler still fits. The spring is not the stop.
2. Letting go returns the flange to the home stop without help, 20 times out of 20, with no packet in the tube.
3. No peg walks out, and no peg has sheared. No fold has cracked. Write down any whitening at a fold.
4. Then one dummy, laid on the floor of the tube. Ten pushes. The dummy moves forward and is left where the face stops supporting it when the button is released. The face parks behind the dummy's back edge.

![One dummy on the floor](assembly/17-dummy.png)

The second dummy is a spare. A dry-cycle failure is a reprint of a peg, a slot, the spring, or the seat. The crank angles stay as printed, and the bench does not start. When a print exists, write the result in `projects/pocky/docs/prototype-log.md`.

## Separator gap

The bench starts at one 0.4 mm shim on each ledge. A jam on a thick seal moves one step coarser. A double feed moves one step finer. The body is not reprinted to chase the gap. Print another 0.8 mm shim only if both ledges need one.

| On each ledge | Gap |
|---|---:|
| nothing | 5.35 mm |
| one 0.4 mm | 5.75 mm |
| one 0.8 mm, or two 0.4 mm | 6.15 mm |
| one 0.8 mm plus one 0.4 mm | 6.55 mm |
