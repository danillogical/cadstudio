# Plan — Pocky Packet Dispenser (Mechanical Prototype)

**Status:** Planning only; no CAD implementation has been started.  
**Prototype gate:** A reliable, **single-magazine dispenser holding 10–25 packets**, with a **manual spring-return push button**, **no removable cartridge**, and **no electronics**.  
**Do not scale to 100 packets until this gate passes.**

## 1. Project context

The eventual goal is an unattended Halloween Pocky vending machine. There are **100 individually wrapped Halloween Pocky packets** available, each containing six fragile sticks. We are **not** designing the 100-packet enclosure now.

The user prefers the motion of Riva3D's [Tea Sachet Dispenser V2](https://cults3d.com/en/3d-model/home/dispensador-de-sobres-de-te-v2): press a button, eject one sachet from the bottom of a stack, release the button, and reset. The user correctly noticed a **curved slot in its floor**. The ejector is not a simple straight-line pusher: a linkage below the floor moves an ejector tip along an arc.

### Confirmed packet dimensions

| Parameter | Value | Notes |
|---|---:|---|
| Packet length | **165 mm** | Nominal exterior envelope |
| Packet width | **55 mm** | Nominal exterior envelope |
| Packet thickness | **5.2 mm** | User-measured; use as rigid simulation thickness |
| Quantity available | **100** | Future capacity, **not** the prototype target |
| Prototype magazine | **10–25 packets** | One fixed, top-loaded magazine |

For CAD/kinematic tests, create each packet as a **rigid 165 × 55 × 5.2 mm rectangular solid**. This is an *envelope model*, not a prediction of foil compression or whether the chocolate sticks will fracture.

A stack of 10 has a nominal uncompressed height of **52 mm**; 25 has **130 mm**. Real stack height and dispensing drag must be verified experimentally. Do **not** assume each wrapper compresses to exactly 5.2 mm under load.

## 2. Reference material: purchased Tea Sachet Dispenser V2

**Source archive supplied by user:** `Archivos STL + Video de armado.zip`  
**Original model:** Riva3D, *Tea Sachet Dispenser V2*, Cults3D design 3878237.

The archive contains **eight STL meshes plus one assembly video** (and ignorable macOS `__MACOSX` metadata). The filenames below are copied exactly. Size values are STL bounding-box extents, interpreted as **millimeters** for inspection; they are **not** dimensions to scale automatically.

| File in archive | Approx. mesh extent (X × Y × Z) | Role / observations |
|---|---|---|
| `Cuerpo.stl` | 80 × 90 × 150 mm | Main upright body and sachet magazine; fixed walls and support features. |
| `Base.stl` | 73.6 × 85.1 × 3 mm | Stationary bottom floor; its **curved channel** allows the rotating ejector tip to pass through the floor. |
| `B.part 1.stl` | 38.4 × 14.1 × 14.2 mm | Short **pivoting linkage / bell-crank-like lever** with a slot/connection for actuation. Confirm its assembled pivot in the video. |
| `B. part 2.stl` | 20 × 86.7 × 6 mm | Long **button/linear actuator** that transmits finger movement into the linkage. |
| `Resorte.stl` | 9.7 × 62.5 × 6 mm | Flexible, printed **serpentine return spring** associated with the actuator. |
| `Soporte.stl` | 43.6 × 25.4 × 10 mm | Internal support/retaining component for the actuator assembly; inspect exact retention points before redesign. |
| `Tapa.stl` | 80 × 80 × 11 mm | Removable top cover. |
| `Pinza.stl` | 46.9 × 199.9 × 10 mm | Long, clip/tweezer-shaped auxiliary part; **exact use is not yet established** and is not assumed essential to the ejector. |
| `Demo de armado/Demo de armado.mp4` | ~130 s | Assembly sequence and mechanism reference. **Use this to confirm connections and direction of motion.** |

### Motion hypothesis to validate (not a completed reverse engineering)

1. The **button moves linearly** against a spring.
2. The button drives the short **pivoting lever** via a pin/slot or comparable engagement.
3. A protruding ejector tip attached to that lever **sweeps along the curved channel** in the stationary floor.
4. The tip moves the **lowest** packet to the exit while a floor/exit separator restrains the stack above it.
5. Releasing the button retracts the tip and permits the next packet to settle.

This is most usefully described as a **slider-actuated bell crank / pin-and-slot linkage with a pivoting ejector**. Do not hard-code its pivot center, angular sweep, lever lengths, or force advantage based solely on photos; reconstruct and verify the geometry from the actual assembly before deciding on dimensions for our independent design.

### Reference licensing / handling

The source listing shows **Cults Personal Use** and **No AI** markings. Keep the purchased ZIP, video, and STL meshes **out of a public repository and out of distributable project outputs**. Do not publish, trace, rescale, or redistribute those meshes as our model. Before using licensed geometry as a source for AI-assisted derivative modeling, **confirm permissions with the creator**. The intended deliverable is an **original parametric mechanism based on general linkage principles and our own packet requirements**, not a modified reference STL. If the proposed use would exceed permission, pause and resolve it before proceeding.

## 3. Scope and boundaries

### In scope — first prototype

- **One** fixed magazine with a top loading opening or simple removable lid.
- Holds and dispenses **10 packets**, then extends/testing to **25** without changing mechanism type.
- **Manual push button** with positive mechanical travel limits and **spring return**.
- **Rotary/pivoting ejector** guided by a curved floor opening; use a bell crank or an alternative compact lever if justified by testing.
- Single-packet exit geometry with **adjustable/shimmed separator height**.
- Safe presentation lip/tray: packet remains supported and exposed enough to take by hand.
- Parametric design in **build123d**, including moving assembly, rigid packet models, scripted kinematic checks, printable STEP/STL exports, and mechanical test results.
- Prints only of the **mechanism and one magazine** needed to test it; the shell can be plain.

### Explicitly out of scope until the gate passes

- No 100-packet storage design or four-magazine array.
- **No cartridge system**, cartridge rails, quick-swap magazine, loading cassette, or refill dock.
- No motors, electronics, sensors, microcontroller, illuminated button, or vending-payment features.
- No decorative enclosure, branding, final outdoor/weatherproof case, or child-proof access system.
- No full flexible-wrapper simulation, granular dynamics, stress/fracture FEA, or claims that rigid-body clearance tests prove Pocky cannot break.

## 4. Mechanical architecture for build123d

### Coordinate convention

Model the packet lying **flat**, with `X = 165 mm` (long axis), `Y = 55 mm` (short axis), and `Z = 5.2 mm` (height). `Z` is vertical; stacked packets occupy increasing `Z`.

Use `dispense_axis` as an explicit design choice: compare **long-axis ejection (+X)** and **short-axis ejection (+Y)** in the kinematic study before locking the prototype layout. The goal is to push on a **reinforced/sealed wrapper edge** with minimal crosswise bending of the sticks. Do not assume that a single narrow contact point near the middle of the packet is safe. Prefer a rounded, sufficiently broad ejector contact or a small supported pusher plate, and test the actual wrapper orientation.

The moving ejector may travel through a **curved slot** below the magazine floor even when the packet's exit path is straight. Keep those two motions distinct.

### Initial parametric values (starting points, not fixed specifications)

| Parameter | Initial assumption | How to validate |
|---|---|---|
| `packet_length` | `165.0` | Confirm outside dimensions of several wrapped packets |
| `packet_width` | `55.0` | Same |
| `packet_height` | `5.2` | User measurement; record measurement method |
| `capacity_test` | `10`, then `25` | Both must work with same mechanism |
| `magazine_length_i` | `170.0` mm | ~2.5 mm side clearance per end; adjust for crinkled seals |
| `magazine_width_i` | `60.0` mm | ~2.5 mm side clearance per side |
| `stack_nominal_height` | `capacity_test * 5.2` | 52 / 130 mm before real-world variation |
| `headroom` | `15–25` mm | Allow loading and slight stack variation; tune by printing |
| `separator_gap` | **Adjustable**; trial around `5.5–6.0` mm | Must pass one packet but reject two *compressed* packets |
| `separator_adjustment` | Shims or slotted screw mount | Test multiple clearances without reprinting the whole housing |
| `ejector_tip_radius` | Rounded; TBD | Avoid snagging or puncturing wrapper |
| `presentation_distance` | Aim for `30–50` mm accessible protrusion | Check grip access; packet must remain supported |
| `button_stroke` | Linkage-derived; TBD | Choose from contact path, not arbitrary handle travel |
| `pivot_location / sweep` | TBD | Derive independently and verify from motion study |

Printing details, walls, clearances, and fastening points should be configurable. Use **fillets or printed radii** wherever foil can contact a part. Avoid unnecessary compression of the lowest packet by the full stack.

### Physical behavior to prioritize

- **Singulation:** Only the bottom packet clears the exit; second packet never follows.
- **Controlled contact:** The ejector touches wrapper/sealed edge, not the bare candy or an unsupported region.
- **No pinching:** Slot and floor edges never trap the wrapper during forward or return stroke.
- **Gentle return:** Ejector retracts below the remaining stack and cannot hook the next packet.
- **Gravity reset:** After return, the next packet settles into position unaided.
- **Bounded push:** Mechanical stop prevents overtravel and crushed/creased packaging.
- **Usability:** Simple one-handed button press, no need to tilt or shake dispenser.

## 5. Implementation plan — build123d

Implement an **original, editable parametric design**. Do not use the STL meshes as CAD primitives for the final parts. Build the mechanism with native profiles, pads/extrudes, holes, radii, and mating features.

Suggested repository layout:

```text
pocky-dispenser/
├── README.md
├── pyproject.toml                  # pinned Python/build123d tooling
├── src/pocky_dispenser/
│   ├── parameters.py               # dimensions and validation
│   ├── packet.py                   # rigid packet and optional stack
│   ├── magazine.py                 # fixed housing, floor, exit separator
│   ├── actuator.py                 # push button, stops, spring seats
│   ├── linkage.py                  # pivot lever, contact face, curved slot
│   ├── assembly.py                 # part placements and constraints
│   └── export.py                   # STEP/STL and assembly poses
├── simulations/
│   ├── sweep.py                    # full forward/return kinematics
│   ├── clearance.py                # intersection & margin checks
│   └── scenarios.py                # 1 / 2 / 10 / 25 packet cases
├── tests/
│   ├── test_parameters.py
│   ├── test_kinematics.py
│   └── test_clearance.py
├── outputs/                       # generated artifacts, ignored in VCS
└── docs/
    ├── reference-notes.md         # descriptions only, NO purchased meshes
    ├── test-report.md
    └── assembly.md
```

Use `build123d` solids for housing, lever, linkage, packet and clearance analysis. Use `RevoluteJoint` / `LinearJoint` **where appropriate for assembly positioning**, or explicitly calculate transforms/poses if easier to make deterministic; don't assume joints automatically solve dynamics or all coupled linkages. Drive the full motion with a **single normalized button-travel parameter** and satisfy the pin-slot constraint geometrically. Check each pose independently.

### Work package A — derive the kinematics

1. Describe the reference linkage in a **simple 2D diagram** (pivot, slider path, link/slot, ejector tip path); use assembly observations to label known vs. uncertain details.
2. Build an independent parameterized linkage in a 2D mechanism study before generating the housing.
3. Compute button travel → lever angle → ejector contact point `(x, y)`.
4. Verify that the tip passes through the full curved floor aperture with a defined clearance.
5. Confirm the tip advances the packet to a hand-grabbable position without excessive lateral sweep or side-loading.
6. Find and eliminate over-center lock-up, singular configurations, and ambiguous end positions.

**Deliverable:** pose drawings at 0%, 25%, 50%, 75%, 100%, plus the return path. Provide a plotted tip trajectory and the corresponding curved slot centerline.

**Gate A:** Valid linkage geometry with no self-interference at any sampled pose.

### Work package B — packet / magazine / separator

1. Generate the nominal rigid `165 × 55 × 5.2 mm` packet solid, with a distinctive color in the viewer only if desired.
2. Create **1, 2, 10, and 25** packets as separate rigid solids, stacked without overlap (optionally introduce measured gaps/height variation).
3. Create a fixed top-loaded magazine with adjustable side clearances and **no detachable cartridge**.
4. Design the floor and curved aperture; create an adjustable or shimmed **single-packet exit gap**.
5. Explore ejection along both +X and +Y (especially contact location and packet support); select one based on the least-risk geometry and physical tests.
6. Provide a supported collection lip; do not rely on the packet falling onto a hard surface.

**Gate B:** Only the bottom modeled packet can pass the separator, and the ejector does not invade the volume of the second packet through the full forward/return cycle.

### Work package C — automated kinematic / geometric simulation

For each scenario, advance the button in small, repeatable increments (e.g. **101 poses forward + 101 poses return**). Derive the lever rotation from the linkage constraint; model packet displacement from first contact through presentation. Do not simply teleport the packet to the exit and call that a successful dispense.

At each step check:

- No forbidden solid overlaps: ejector vs. magazine, linkage vs. guide, packet vs. floor/walls, first vs. second packet.
- Designed **contact** between ejector and bottom packet is expected; classify it separately from forbidden penetration.
- Clearances for slot edges, wrapper edge and exit separator meet named tolerances.
- Button reaches a hard stop and spring return can restore the home pose geometrically.
- Second packet is restrained while bottom packet exits, then is permitted to descend after reset.
- A packet can be grasped and removed at full stroke; packet does not have to fall freely.

Output a **CSV/JSON report** with scenario, normalized travel, lever angle, tip position, minimum clearance, intersection volume where relevant, and pass/fail reason. Export several `STEP` assembly poses and screenshots/animation of the motion. Prefer solid-intersection checks in build123d and simple independent analytic 2D tests for the linkage. The script must be runnable headlessly.

**Important modeling limit:** build123d supplies geometry, joints and programmable transforms, **not frictional contact dynamics, gravity settlement, spring force simulation, foil deformation, or chocolate fracture prediction**. Include these as *unverified physical behaviors* in the report; do not present clearance PASS as proof the candy is safe.

**Gate C:** No unintended modeled collisions or double-feed paths in any tested pose. All assumptions and intentional contacts documented.

### Work package D — print and bench-test the single module

1. Print a small **linkage-only bench fixture** first to verify pivot, pin-slot movement, spring seat, and required button travel.
2. Use a replaceable **metal compression spring** as the durability baseline; a printed spring may be a comparison experiment. Do not require reliance on the reference's spring STL.
3. Print a **short magazine** for initial tests (10 packets). Adjust clearance with shims rather than full reprints.
4. Test real packets through repeated complete push/return cycles; observe wrapper snagging, fold formation, uneven contact and Pocky breakage.
5. Extend **the same mechanism** to 25 packets in a fixed taller magazine; evaluate increased stack weight, friction, tilt and settling. No swappable cartridge.
6. Iterate only the failed geometry (separator, tip, pivot, spring, button stroke). Re-run scripted checks after each design change.

Capture notes/photos of all failures and actual values for packet thickness distribution, ten-packet stack height, spring travel, and separator gap. If access to food is not needed for test, use representative empty packets or 3D-printed rigid envelope dummies for early checks; finish with the real product in unopened wrappers.

**Gate D:** The actual dispenser meets the acceptance criteria below at both 10-packet and 25-packet fills.

## 6. Acceptance criteria: hard stop before scaling

All criteria are required for the **single-magazine 10–25 packet prototype**:

1. **One press → at most one packet.** No unintended second packet follows, including a partial press and immediate return.
2. **Full-cycle operation:** Button travels to stop, dispenses/presents one, and returns reliably without manual reset.
3. **Damage:** No observed broken Pocky sticks or torn/punctured wrappers attributable to dispensing in the acceptance batch. Inspect contents of a representative sample after tests, not just packet exteriors.
4. **10-packet fill:** At least **50 recorded consecutive cycles** across refills, with **zero double feeds, jams, or manual interventions**.
5. **25-packet fill:** At least **100 recorded consecutive cycles** across refills, with **zero double feeds, jams, or manual interventions**. Test at full, half-full and nearly empty states.
6. **User safety:** No exposed sharp edges, pinching at normal button/collection touch points, or uncontrolled hard drops.
7. **Manufacturability:** STL/STEP exports are reproducible from parameters; printed mechanical components assemble without filing critical load-bearing features beyond explicitly documented tolerance tuning.
8. **Documentation:** Parameter table, assembly instructions, kinematic animation, clearance report, and real-world test log accurately reflect the final printed revision.

A failure means **iterate on the single module**. Do not start the 100-packet machine, extra magazines, electronics, or styling while any criterion is outstanding. If repeated failures show the rotary ejector is intrinsically too rough on Pocky, explicitly evaluate a gentler packet-supporting shuttle rather than forcing the original concept.

## 7. Milestones / order of work

| Milestone | Output | Exit condition |
|---|---|---|
| **M0 — Inputs and mechanism study** | Reference-file inventory; linkage sketch; packet measurements and assumptions | Kinematic hypothesis clear, licensing constraints acknowledged |
| **M1 — Motion proof** | Parametric lever + slider + curved slot, scripted sweep | Gate A PASS |
| **M2 — Magazine + rigid packets** | Fixed 10–25 packet magazine, adjustable separator, rigid packet stack | Gate B PASS |
| **M3 — Collision/clearance proof** | Automated scenarios, report, motion visualization | Gate C PASS |
| **M4 — Physical prototype** | Printable components, spring, assembly instructions; printed 10-packet unit | 10-packet bench test PASS |
| **M5 — Capacity gate** | Same mechanism tested at 25 packets with revised fixed magazine as needed | **Gate D and all acceptance criteria PASS** |
| **Later — 100-packet vending machine** | **Not authorized by this plan** | Requires a separate decision after M5 |

## 8. Build and review rules for an AI coding/CAD agent

- **Read this plan first.** Record unknowns rather than silently guessing mechanical dimensions.
- Keep all dimensions centralized and editable; **avoid baked-in mesh dimensions and scaled purchased STLs**.
- Make the kinematic solver and tests run without a GUI; use build123d primarily for CAD and geometric checking.
- Prefer one working printable module over elaborate features, decorations or multiple concepts developed simultaneously.
- Show **actual motions and evidence** at each milestone, not just a static rendered assembly.
- Maintain a running list of physical assumptions that scripted rigid-body testing cannot validate.
- At each gate report **PASS/FAIL**, exact commands run, exported artifact paths, changed design parameters, unresolved issues, and whether the next milestone is authorized.
- The **100-packet concept is intentionally deferred**, even though total available inventory is 100.

## 9. First task for the implementing agent

> Implement **M0 only**: verify package/tooling access, establish the project skeleton, write a clear kinematic diagram from the reference observations, identify pivot/slot/button relationships and remaining uncertainties, record the rigid packet dimensions (`165 × 55 × 5.2 mm`), and propose an independently parameterized build123d mechanism. Do not implement a full vending enclosure or multiple magazines. Stop for review before M1 if linkage identification, license permission or packet orientation remains unresolved.
