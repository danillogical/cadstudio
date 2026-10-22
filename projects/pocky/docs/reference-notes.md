# Reference notes: Riva3D "Tea Sachet Dispenser V2" ejector linkage

M0 reverse-engineering of a purchased reference design, done for the Pocky packet dispenser plan (`plan-pockey-dispenser.md` §2, §4, §9). This file describes the reference. It is **not** our design and it is not a specification for one.

## Licence and handling

- The user obtained the creator's permission for AI-assisted analysis. The listing is marked Cults Personal Use / No AI.
- **The meshes, the video, extracted frames and any mesh-derived outlines are not included in this repository and must not be added.** This file holds only numbers and prose. `kinematic-diagram.png` is a schematic drawn from the scalar parameters below: circles, lines, rectangles and arcs. It is not a traced mesh section.
- Inputs were read in place from `~/Downloads/Archivos STL + Video de armado/`. Scratch scripts and frames are in `/tmp/pocky-ref-scripts/` and `/tmp/pocky-ref/`, outside the repo.

## Labels used in this file

- **known**: measured from the meshes, or seen directly in the video.
- **inferred**: follows from known facts by geometry or calculation, but was not observed directly (for example a hard stop that the video never shows being hit).
- **uncertain**: plausible, but not supported by enough evidence.

## Methods

Every dimension in this file comes from one of the methods below. Each number is tagged with its method code.

- **[M-bbox]** Load the STL with `trimesh`. Take the axis-aligned bounding box from `mesh.bounds`. Read the distinct vertex Z levels to find layer heights.
- **[M-sec]** Planar section: `mesh.section(plane_origin, plane_normal=Z)`, then `to_planar(to_2D=identity)` so XY stays in STL coordinates, then the loops from `path.discrete`. Each loop gets an algebraic least-squares circle fit with max residual reported, plus shapely area and centroid. Sections were repeated at 2 to 4 heights per feature. The numbers agreed to ±0.01–0.02 mm across heights, apart from fillets and chamfers, which are called out.
- **[M-stad]** Stadium (slot) fit: shapely `minimum_rotated_rectangle` of the slot loop gives overall length, width and axis angle. The end-arc centres are at ±(L−W)/2 along the axis.
- **[M-arc]** Channel fit: densify the Base outline at 0.1 mm, keep the points in the channel region, and split them into the inner and outer wall by radius about the pivot. Circle-fit each wall. Probe the width with radial rays every 5°.
- **[M-vsec]** Vertical section (`plane_normal = X` or `Y`), simplified with shapely at 0.03–0.05 mm, to read wall, slot and ramp coordinates.
- **[M-ray]** Line intersections on a section polygon, used for the spring beam thickness and gap counts.
- **[M-ovl]** Assembly-pose check: sample about 60k interior points per part (`trimesh.sample.volume_mesh`) and test them with `contains` against every other part, giving an approximate overlap volume.
- **[M-kin]** Kinematic solve: the slider pin moves on a straight line, and the lever angle θ(s) is solved with `scipy.optimize.brentq` so that the pin centre lies on the (rotated) slot centreline. Tip pose is the pivot plus R(θ)·(tip − pivot). Collisions were checked every 0.1 mm of travel (0.005 mm near the stops) as shapely intersections of the rotated lever sections and the translated slider sections at three layers (z = 4.6, 6.2, 8.6 STL), plus the Cuerpo sections at the same layers.
- **[M-vid]** Video `Demo de armado.mp4`: 640×360, 30 fps, 130.0 s. `ffmpeg` scene detection at thresholds 0.25 and 0.10 returned **zero** frames because the clip is one continuous hand-held take. Frames were therefore taken at 0.5 fps for the whole clip (65 frames, tiled 4×4), at 2–5 fps for 60–76 s, 84–100 s and 89–94 s, and at 1–3 fps for 94–130 s. All frames were viewed directly. Times below are ±1 s.

## Coordinate frames

- **STL frame (known, [M-bbox]/[M-ovl]).** Cuerpo, Base, `B.part 1`, `B. part 2` and Resorte are exported in **one shared assembly frame, in the rest pose**. Evidence:
  - Lever, slider and Base overlap nothing.
  - The slider pin centre coincides with the lever slot's outer end-arc centre to 0.01 mm.
  - The Cuerpo pivot pin is coaxial with the lever bore to 0.002 mm.
  - The only overlap is Resorte vs Cuerpo, about 108 mm³: the spring is exported at free length and penetrates its seat rib by its preload.
  - Tapa, Soporte and Pinza are placed arbitrarily. Soporte overlaps Cuerpo by about 560 mm³ and Tapa sits beside the body.

  In the STL frame Z is up, Cuerpo's bottom is at z = 0, and the sachet exit is on the **−Y** face.
- **Frame R (used below).** Origin at the Base outline centre, which is STL (0, 0). **+X_R points toward the sachet exit.** Z_R = 0 at the Base top surface, which is the magazine floor (STL z = 12.4). The mapping is X_R = −y_STL, Y_R = +x_STL, Z_R = z_STL − 12.4. This is a proper rotation of +90° about Z, so the sense of rotation is preserved. Angles are measured counter-clockwise from +X_R, viewed from above.

## File inventory

| File | Extent X×Y×Z (mm) [M-bbox] | Matches plan §2 | Role | Label |
|---|---|---|---|---|
| `Cuerpo.stl` | 80.00 × 90.00 × 150.00 | yes | Main body and magazine. Has a mechanism cavity under the floor (STL z 3.0–9.4), the pivot pin, the slider opening, the spring seat rib, Base support ribs and snap detents, a full-width exit slot, a 10 mm front viewing window, and a wall-hanger rail pair on the back face. | known |
| `Base.stl` | 73.60 × 85.10 × 3.00 | yes | Floor plate. Holds the curved clearance channel for the ejector tip, has four 15 × 2 flexure slots, and snaps into the body. | known |
| `B.part 1.stl` | 38.39 × 14.11 × 14.20 | yes | Bell-crank lever. Has a pivot bore, a slotted clevis short arm, and an upright tip pin on the long arm. | known |
| `B. part 2.stl` | 20.00 × 86.66 × 6.00 | yes | Push-button slider: button head, stop flange, rod, and a tongue carrying a double-ended pin. | known |
| `Resorte.stl` | 9.72 × 62.50 × 6.00 | yes | Printed serpentine compression spring that returns the slider. | known |
| `Soporte.stl` | 43.60 × 25.43 × 10.00 | yes | **Wall-mount bracket**, not an actuator support. Has two Ø3.0 screw holes with Ø7.0 counterbores. | role known from geometry, mating inferred |
| `Tapa.stl` | 80.00 × 80.00 × 11.00 | yes | Lid with a drop-in plug. | known |
| `Pinza.stl` | 46.86 × 199.85 × 10.00 | yes | Long printed tongs: two 3 mm-wide arms joined by a U spring, with barbed tips. Used as an **assembly tool**, not part of the mechanism. | known (seen) |
| `Demo de armado/Demo de armado.mp4` | 130.0 s | yes | Assembly video. Shows no tea sachets. | known |

All bounding boxes match the plan §2 table to within its rounding, so the meshes are in **mm**. The units check passed.

## Measured features (frame R unless marked STL)

### Pivot

- Cuerpo pivot pin: **Ø3.57** for STL z 4.5–9.0, with a filleted root of Ø3.78 at z 3.6 [M-sec, 4 heights, residual ≤ 0.007]. It stands on the cavity floor, which is at STL z 3.0, and its top is at STL z 9.0. **known**
- Lever bore: **Ø3.99** (3.983–3.995 across three heights), with a chamfer at the bottom face (Ø5.4 at z 3.25) [M-sec]. Diametral clearance is about **0.42**. **known**
- Pivot centre: **O = (−36.50, 16.87)**. In STL this is (16.868, 36.500). Pin and bore centres agree to 0.002 [M-sec]. **known**
- The Base and Soporte have **no** pivot pin or bore. The Base channel is concentric with this pin, as described below [M-sec/M-arc]. **known**

### Lever (`B.part 1`)

- Body: STL z 3.2–9.2, 6.0 thick [M-bbox]. It has three layers [M-sec]:
  - bottom fork, z 3.2–5.0;
  - middle web, z 5.0–7.4, which has no short arm;
  - top fork, z 7.4–9.2.

  The short arm is therefore a clevis with a **2.4 mm** gap. **known**
- Tip pin: **Ø4.00** at STL (−8.50, 37.00), which is R **(−37.00, −8.50)** at rest. It rises from the lever top at z 9.2 to STL z 17.4, so it stands **5.0 above the floor** (Z_R 0 → 5.0). The root fillet is Ø4.57 at z 9.5 [M-sec]. **known**
- The tip has a **45° chamfer on its trailing (+Y_STL, i.e. −X_R) side**. Going from STL (y 39.0, z 14.87) to (y 36.47, z 17.4), the leading (exit-facing) side stays vertical [M-vsec at x = −8.5]. **known**
- Tip arm length, pivot to tip centre: **25.37**, at a rest angle of **268.87°** in R [M-sec + arithmetic]. **known**
- Slot in the short arm, in both fork layers [M-stad]:
  - overall **8.20 × 3.20**, end-arc centres 5.00 apart;
  - centre at rest **(−30.79, 22.31)**;
  - axis along **40° / 220°**;
  - the axis passes **0.50** from the pivot, so it is almost but not exactly radial;
  - end-arc centres are at radius **10.38** (outer end) and **5.39** (inner end) from the pivot.

  **known**
- Bell-crank included angle between the tip arm and the outward slot axis: **131.1°** [M-sec/M-stad + arithmetic]. **known**

### Slider (`B. part 2`)

- Overall length 86.66; Z 6.0, STL z 3.2–9.2 [M-bbox]. Sections at z 3.25, 6.2 and 8.0 show the following parts, listed from the button inward [M-sec]. **known**

  | Part | Size (mm) | Position along X_R | Notes |
  |---|---|---|---|
  | Button head | 15.95 wide | +41.80 to +54.80 | Rounded corners. Protrudes **9.8** beyond the front face (X_R = 45.0) at rest. |
  | Stop flange | 20.0 wide, 2.68 thick | +39.12 to +41.80 | |
  | Rod | 6.0 wide (Y_R 20.92–26.92), full 6.0 height | +39.12 to −23.88 | |
  | Tongue | 6.0 wide, **2.0 thick** (STL z 5.2–7.2) | to −31.86 | Rounded end. |

- Slider pin on the tongue: **Ø2.98**, centre at rest **(−28.88, 23.92)**, on the rod centreline. It runs from STL z 4.2 to 8.2, which is 1.0 proud of each tongue face. Each tip has a 0.5 × 45° chamfer down to Ø1.99, so the full diameter only exists for z 4.7–7.7 [M-sec at 0.1 mm steps]. **known**
- Pin-in-fork engagement [M-sec + arithmetic]:
  - About 0.8 mm of pin length sits inside each fork, but only **about 0.3 mm of it is full diameter**.
  - Slot width minus pin diameter gives 0.22 diametral clearance.
  - The tongue (2.0) in the fork gap (2.4) leaves 0.2 per side.

  **known**
- Slider line offset from the pivot: **e = 7.05** (Y_R 23.92 vs 16.87). The pin starts 7.62 on the +X_R side of the pivot and moves toward −X_R when the button is pressed [M-sec + arithmetic]. **known**

### Slider guide and travel stops

- **Front-wall button opening:** 16.35 wide (Y_R 15.72–32.12), STL z 3.0–9.4, through the 3.0 front wall. It fits the 15.95 head with about 0.2 per side [M-vsec at y = −43.5]. **known**
- **Vertical guidance:** the slider (STL z 3.2–9.2) is sandwiched between the cavity floor (z 3.0) and the Base underside (z 9.4), with 0.2 gaps [M-bbox/M-sec]. **known**
- **Lateral guidance at the back:** the rod's +x_STL face is 0.16 from the spring, and the spring is 0.20 from the side wall (STL x = 37.0). The −x_STL side has nothing near the rod. A rib at STL x 9–12, y −42 to −33 is 1.9 from the flange end [M-sec z 6]. So the rod is guided mainly by the button opening and the spring, and the pin-in-slot also restrains it. **inferred**
- **Rest stop:** the flange front face (X_R 41.80) is **0.20** from the inner face of the front wall (X_R 42.00). The pin is concentric with the outer end of the slot, with **0.10** radial clearance. Both seat at about the same point. Which one carries the spring preload depends on print tolerance [M-sec z 6 + M-stad + arithmetic]. **known (gaps), inferred (which bears)**
- **Forward stops, first contact by sweep [M-kin]:**
  1. The lever's short-arm outer corner meets the inside of the back wall (STL y = 42.0) at **s = 9.53**, Δθ = 61.2°.
  2. The button face becomes flush with the front face at s = 9.80 (54.80 − 45.00, arithmetic).
  3. The tip meets the channel end cap at s = 9.89, Δθ = 64.0°.
  4. The tongue end meets the back wall at s = 10.14.

  These four stops fall within 0.6 mm of each other, so there is no single obvious designed hard stop. The working stroke is **about 9.5–9.8 mm**. **inferred** (the video shows only partial presses; see below)
- No lever-to-slider or lever-to-spring interference anywhere in s = 0–9.5 [M-kin]. **known by calculation**

### Spring (`Resorte`) and seats

- Serpentine shape, 9.72 wide × 6.0 tall [M-bbox/M-ray at the centreline STL x = 31.95]:
  - 13 straight beams **1.50** thick with **2.30** gaps, a pitch of 3.80;
  - end pads 1.7 thick;
  - free length **62.50**.

  **known**
- Seats: the front pad bears on the slider flange's inner face (X_R 39.12). The back pad bears on a Cuerpo rib at STL x 28–37, y 20.88–23.88, whose face is at X_R = −20.88 [M-sec z 6, M-ovl]. **known**
- Installed length is 60.00, so the **preload is 2.5**. At s = 9.53 the spring is 50.5 long (12.0 compressed). The total gap along the centreline is 34.0, so the spring never goes solid [M-ray + arithmetic]. **known (geometry)**; spring force is **uncertain**, since material and printed stiffness are unknown.
- Spring position in the video: on the +x_STL side of the slider rod, between the flange and a rib near the lever, placed with the Pinza at about 44–60 s. **known (seen)**

### Floor channel (`Base`)

- Inner wall R **22.86**, outer wall R **27.86**, width **5.00** (4.98–5.00 by ray probe at 5° steps), centreline R **25.36** [M-arc, three heights, wall residuals ≤ 0.015]. **known**
- The fitted centre is **within 0.003–0.016 of the pivot pin axis**. The channel is therefore an arc concentric with the pivot, and its centreline radius equals the tip arm (25.36 vs 25.37). Tip clearance is 0.5 per side. **known**
- Sweep:
  - The channel is open at the Base back edge (X_R = −41.8). The mouth spans Y_R −10.76 to −5.56, and the centreline reaches the edge at about 257.9°.
  - It runs past the tip rest position (268.87°) to an end cap centred at **331.7°**, at **(−14.14, 4.85)**. The end-cap circle fit is poor (R 2.64, residual 0.37); it is 2.5 nominal.
  - Usable tip sweep from rest to the cap is 64.0°.

  [M-arc]. **known**
- Base plate: 73.6 × 83.6 × 3.0 (STL z 9.4–12.4). Snap bumps stand 0.25–0.75 proud at Y_R = ±24.3 on the two X_R edges. Behind each bump is a 15.0 × 2.0 flexure slot 2.5 in from the edge [M-sec]. These engage detent grooves about 0.7 deep in the Cuerpo walls at STL z 9.3–11.3 [M-vsec x = 24]. Four ribs whose tops are at STL z 9.2 support the Base underside (z 9.4). **known**

### Magazine, exit and rest pocket (`Cuerpo`)

- Magazine bore 74.0 × 74.0 (X_R −32 to 42, Y_R ±37) above Z_R ≈ 10. The outer body is 80 × 80, with 3.0 walls [M-sec z 60, 145]. **known**
- **Exit / separator:** the front wall bottom edge is at **Z_R = 5.0** (STL z 17.4). The exit slot is 5.0 high over the full 74 inner width [M-vsec y = −43.5]. The tip pin top is also at Z_R 5.0. **known**
- **Rest pocket:** at floor level the floor runs back to X_R = −42 (84 long), but the magazine back face is at X_R = −32. Between them a **45° chamfer** joins (X_R −42, Z_R 0) to (−32, 9.96) [M-vsec x = −8.5]. The tip rests at X_R −37 under this overhang. Its 45° trailing chamfer sits parallel to the body ramp with about 0.49 vertical clearance at both ends of the chamfer. **known**
- Front face (seen in the video at about 100–115 s): a vertical window of 10.0 × 110 (STL x ±5, z 30–140), the full-width exit slot, and the button below the exit slot, right of centre [M-vsec y = −43.5, M-vid]. **known (mesh + seen)**

### Tapa and Soporte retention

- **Tapa:** a 3.0 plate on an 80 × 80 rim 2.0 thick, plus a plug 73.6 × 73.6 × 6.0 with 3.0 walls. The plug slips into the 74.0 bore with 0.2 per side; the lid rests on the rim and has no latch features [M-sec, four heights]. The video shows it dropped on top at about 121–126 s. Retention is gravity plus the slip fit. **known**
- **Soporte:** a 3.0 base plate 43.6 wide with a 2.0 perimeter wall to 5.8, plus two screw bosses Ø7 OD × Ø3 ID reaching 10.0, at ±9.8 (19.6 apart). It has Ø7.0 counterbores at the plate face [M-sec]. The Cuerpo back face (STL z ≈ 100–129) carries two rails, each an upright at x ±22–25 with an inward lip at x ±19–22, standing 6.2–9.2 off the back face, with a lead-in taper at the bottom and cross-ribs near the top [M-sec/M-vsec]. Fitting the parameters gives:
  - plate and wall width ±21.8 inside the uprights at ±22 (0.2 per side);
  - plate and wall depth 5.8 under the lips at 6.2 (0.4 clearance);
  - bosses passing between the lips (at ±19) to the wall.

  This is consistent with screwing Soporte to a wall and sliding the dispenser down onto it. **inferred**. Not shown in the video, so the mating is **uncertain**.

## Reconstructed linkage (frame R)

The mechanism is a **slider-driven slotted bell crank**, sometimes called an offset slider with a slotted crank. The button slider carries a pin. The pin runs in a nearly radial slot in the lever's short arm, so straight-line travel of the slider becomes rotation of the lever about the fixed pin O. The long arm carries the tip pin on a fixed radius of 25.37. The floor channel is only a **clearance slot** concentric with O. It does not guide or shape the tip path. [M-kin] **known by calculation from known geometry**

| Quantity | Value | Method / label |
|---|---|---|
| Pivot O | (−36.50, 16.87) | M-sec, known |
| Slider line | Y_R = 23.92, offset e = 7.05 from O, pressed toward −X_R | M-sec, known |
| Tip arm | 25.37 at 268.87° (rest) | M-sec, known |
| Pin radius along the stroke | 10.38 (rest) → min 7.05 (s ≈ 7.6) → 7.30 (s = 9.53) | M-kin, known by calc |
| Pin position in slot | −2.50 (outer end) → +0.84 max (s ≈ 7.6) → +0.58; only 3.34 of the 5.00 end-to-end is used, and the inner end is never reached | M-kin, known by calc |
| Angle between slot axis and slider direction | 40° (rest) → 90° (Δθ ≈ 50°) → 101° (stop); never 0° or 180°, so there is no dead point or over-centre position in travel | M-kin, known by calc |
| Button stroke | about 9.53 (first geometric stop) to 9.8 (flush) | M-kin, inferred |
| Lever rotation at stop | 61.2° counter-clockwise viewed from above | M-kin, inferred |
| Tip arc | 61.2° × 25.37 = 27.1 mm | M-kin, inferred |
| Tip chord | (−37.00, −8.50) → (−14.50, 4.22): ΔX +22.5 toward the exit, ΔY +12.7 sideways | M-kin, inferred |
| Tip speed (tip mm per button mm) | 1.57 at rest, rising to 3.60 at s ≈ 7.5–8.0, then 3.42 at s = 9.53; mean 2.85 | M-kin, known by calc |
| Ideal force ratio (tip/button) | the inverse: about 0.64 at the start falling to 0.28 near the end, before friction | M-kin, inferred |

Pose table at 0/25/50/75/100% of the 9.53 stroke [M-kin]:

| % | s | Δθ (°) | Tip centre (X_R, Y_R) | Pin centre | Pin radius |
|---|---|---|---|---|---|
| 0 | 0.00 | 0.00 | (−37.00, −8.50) | (−28.88, 23.91) | 10.38 |
| 25 | 2.38 | 10.11 | (−32.54, −8.19) | (−31.26, 23.91) | 8.78 |
| 50 | 4.76 | 24.17 | (−26.57, −6.48) | (−33.64, 23.91) | 7.60 |
| 75 | 7.15 | 42.10 | (−19.86, −2.29) | (−36.03, 23.91) | 7.06 |
| 100 | 9.53 | 61.23 | (−14.50, 4.22) | (−38.41, 23.91) | 7.30 |

Notes on the poses and stops:

- **Singular and over-centre positions:** none in travel (see the slot-angle row). The ratio dθ/ds peaks at 8.14 °/mm near s = 8 and falls slightly toward the stop, which is not a lock-up. **known by calculation**
- **End-of-travel ambiguity:** four geometric stops lie within 0.6 mm (9.53, 9.80, 9.89, 10.14). If the lever's corner contact at 9.53 is the real stop, it loads the lever arm against the back wall. **inferred / uncertain** which stop is intended.
- **Rest:** the outer end of the slot is exactly at the pin, so the pin bottoming in the slot and the flange touching the front wall happen together. **known (geometry)**

## Motion sequence

1. **Rest.** The spring preload (2.5 mm) holds the slider out, with the button 9.8 proud. The tip sits under the 45° back overhang at X_R −37. That is 3 mm behind a full-depth sachet's back edge if the sachet lies against the X_R = −32 back face. **known geometry; sachet position uncertain**
2. **Press.** The slider moves −X_R, *away from the exit*. The pin drives the short arm, and the lever turns counter-clockwise. The bell crank reverses direction, so the tip moves **toward the exit (+X_R)** while drifting +Y_R. **known (mesh), direction seen in video**
3. **Contact.** For a sachet against the back face, the tip's vertical leading face reaches X_R −32 at **s ≈ 1.7** (tip centre at −34). **inferred** (no sachet in the video)
4. **Push.** The tip pushes the bottom sachet's back edge. The contact point slides about 12.7 mm sideways along the edge and crosses the centreline (Y_R = 0) at s ≈ 8.05. The bottom sachet passes under the front-wall edge at Z_R 5.0, and the edge holds back the sachets above it. At s = 9.53 the leading face is at X_R ≈ −12.5, so the sachet has moved about **19.5** and its front edge stands out about 16.5 beyond the front face. That is a **partial ejection for hand pickup**, not a drop. **inferred** (sachet size and behaviour assumed)
5. **Release.** The spring returns the slider, and the tip swings back clockwise to the rest pocket. The trailing face is the 45° chamfer, which is needed to clear the body ramp at rest. It may also help the tip slip back under a sachet that has not yet been taken. **chamfer known; secondary benefit uncertain**
6. **Reset.** Once the presented sachet is pulled out, the stack drops onto the floor. The tip is already back behind the stack's footprint. **inferred**

### Video timeline [M-vid]

| Time (s) | What is seen |
|---|---|
| 0–8 | The slider is lowered from the open top into the under-floor cavity. The button head goes into the front-wall opening. **known** |
| 8–36 | The lever is set onto the pivot pin at the back right, by fingers and the Pinza. The long arm points toward −Y_R along the back, and the forks straddle the slider tongue. It takes many attempts, which is consistent with the forks having to spring over the 1.0-proud chamfered pin ends. **seen; snap mechanism inferred** |
| 38–42 | Clear top view of the rest pose. It matches the mesh pose and is not mirrored. **known** |
| 44–60 | The spring is inserted with the Pinza between the flange and the rib. **known** |
| 64–76 | Presses before the Base is fitted: the slider moves inward and the long arm swings toward the front, with the slot visible at the short arm. Presses are partial, at most about 25–30° in the perspective image, so the full stroke is not shown. **known (sense), partial stroke** |
| 72–86 | The Base is pressed in from the top. **known** |
| 86–94 | One Pinza arm goes through the front exit slot while the Base is being seated. One frame shows the Base front edge lifted. Its purpose may be seating the Base or prying it out, and is **uncertain**. |
| 100–112 | The front face is shown: window, full-width exit slot, and the button below the exit right of centre. The Pinza tip is slid into the exit slot and out again. Purpose **uncertain**. |
| 116–121 | Presses with the Base fitted. The green tip moves from the back mouth along the curved channel toward the front and +Y_R, then returns. These presses are partial. **known** |
| 121–126 | The Tapa is dropped onto the top. **known** |

The video never shows a sachet being dispensed, Soporte being mounted, or the end of travel. A small green part on the table at the bottom right of many frames was not identified (**uncertain**).

## Plan §2 checks

The table roles:

| Plan §2 claim | Verdict |
|---|---|
| Cuerpo is the body and magazine | **Confirmed** (known). |
| Base is a stationary floor whose curved channel lets the rotating tip through | **Confirmed, refined**: the channel is concentric with the pivot, 5.00 wide, and gives clearance only. It does not guide the tip (known). |
| B.part 1 is a short pivoting bell crank with a slot or connection | **Confirmed**: it is a slotted clevis bell crank with a 131° included angle (known). |
| B. part 2 is a long button / linear actuator | **Confirmed** (known). |
| Resorte is a printed serpentine return spring | **Confirmed** (known). |
| Soporte is an internal support or retainer for the actuator | **Refuted.** Soporte is a wall-mount bracket. The actuator is retained by the Cuerpo cavity, ribs and Base (known). The bracket mating is inferred. |
| Tapa is a removable top cover | **Confirmed**: a drop-in plug lid (known). |
| Pinza use is not established | **Resolved in part**: it is a long assembly tweezer used to reach about 140 mm down into the body (known, seen). Its use in the exit slot is uncertain. It is not part of the mechanism. |

The motion hypothesis:

1. *The button moves linearly against a spring.* **Confirmed** (known). The spring has a 2.5 mm preload.
2. *The button drives the pivoting lever by pin and slot or similar.* **Confirmed** (known). A Ø2.98 double-ended pin on the slider runs in an 8.2 × 3.2 slot in the clevis short arm.
3. *A tip on the lever sweeps along the curved floor channel.* **Confirmed** (known), with a refinement: the path is a pivot arc (R 25.37), and the channel only clears it. The sweep is 61° (inferred stop).
4. *The tip moves the lowest packet to the exit while a separator holds the stack.* **Partly confirmed.** The separator geometry (5.0 gap under the front wall; tip 5.0 tall) is known. Sachet behaviour is **not shown**, so it remains inferred. Also, the tip motion is not a straight push: it includes about 12.7 mm of sideways travel.
5. *Release retracts the tip and lets the next packet settle.* **Confirmed for the retraction** (spring return seen; rest pocket known). Settling is inferred.

**Surprises:**

- The button is on the exit face, directly below the exit slot, and is pushed *away* from the exit. The bell crank reverses the motion.
- The stroke only presents the sachet, by about 19.5 mm, rather than ejecting it.
- Soporte is a wall mount.
- There is no single designed forward stop.
- The pin's full-diameter engagement in each fork is only about 0.3 mm.

## Unresolved items that block or constrain M1

1. **Packet orientation and dispense axis** (plan §4: +X long axis vs +Y short axis). The reference does not settle it. Its about 22.5 mm push toward the exit, at about 3:1 tip/button gain, presents a 74 mm sachet. A 165 × 55 Pocky packet needs a decision on presentation distance before arm lengths can be set.
2. **Sideways scrub of the tip.** The reference contact point moves about 12.7 mm along the packet edge, with a lateral force component. The plan asks for broad contact without side-loading, and whether that is acceptable for Pocky needs our own analysis. The reference video gives no evidence of how sachets behave.
3. **Separator and tip height.** The reference uses 5.0 for both. Pocky is 5.2 nominal (plan §4: separator 5.5–6.0 adjustable), so the numbers cannot be reused.
4. **Spring force and button force.** These are unknown, because printed-spring material and stiffness are not determinable from the mesh. The plan already prefers a metal spring.
5. **Intended forward stop.** It is ambiguous (four contacts within 0.6 mm), so our design must define one explicit stop.
6. **Pin retention.** About 0.3 mm of full-diameter engagement per fork is a likely failure point under load, because the chamfered tips can cam the forks apart. This is a design risk to avoid, not a measurement gap.
7. **Not observable:** real stack drag, friction, and whether the 45° trailing chamfer helps on return.

**Assessment.** The pivot, slot and slider relationship of the *reference* is fully determined from the meshes:

- the channel is concentric with the pivot to under 0.02;
- the pin sits on the slot end to 0.01;
- the kinematics solve without singularities.

That is enough to base an independent design on the *principle*: an offset slider driving a slotted bell crank, about 61° of rotation, and a 3:1 average gain. It is not a source of dimensions to copy. The Pocky packet's size, thickness and presentation requirements make the reference's numbers inapplicable without re-derivation. Items 1–3 above must be resolved before M1 parameters are chosen.
