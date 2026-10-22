# Measuring the Chromebook lid

How to caliper the Lenovo IdeaPad 3 Chromebook 11AST5 (11.6") display lid. The numbers go into `projects/armor/params.toml`.

`projects/armor/params.toml` already holds a first set of measurements (lid 286.7 × 193 × 7.0, screen 260 × 147). Use this guide to re-check them, especially `lid.t`, and to measure the camera, the hinge and the edges.

## What you need

- Calipers, ideally 300 mm or longer, for the width. A steel rule also works for `lid.w` and `lid.h`, as long as you read it carefully.
- A white full-screen image, e.g. a blank browser tab in fullscreen (F4 on a Chromebook). It shows exactly where the lit area ends.
- The laptop open to about 90°, sitting on a table.

Measure each value **3 times** and write down all three readings. Use the **maximum** for lid sizes and the **average** for screen/camera positions.

---

## 1. Front view: lid size, screen area, camera

Look straight at the open screen. "Hinge edge" means the bottom edge of the lid, where it meets the hinge.

```
                        ◄──────────────── lid.w ────────────────►
                  ┌──────────────────────────────────────────────────┐  ─┬─ top edge
                  │                   ┌──────┐ ◄─ camera.w ─►        │   │
                  │  camera.top_offset│  ()  │ ▲                     │   │
                  │                   └──────┘ ▼ camera.h            │   │
                  │     ┌────────────────────────────────────┐   ─┬─ │   │
                  │     │                                    │    │  │   │
                  │     │                                    │    │  │   │
                  │     │        LIT DISPLAY AREA            │ screen.h│  lid.h
                  │     │       (white image on)             │    │  │   │
                  │     │                                    │    │  │   │
                  │     │                                    │    │  │   │
                  │     └────────────────────────────────────┘   ─┴─ │   │
                  │     ◄──────────── screen.w ─────────────►    ─┬─ │   │
                  │                                    screen.bottom │   │
                  └──────────────────────────────────────────────────┘  ─┴─ hinge edge
                          ════════╪═══════════════╪════════
                               hinge                hinge
```

| Key | Current | How to measure |
|---|---|---|
| `lid.w` | 286.7 | Side edge to side edge of the lid, at the widest point. Measure near the top, the middle and the bottom. |
| `lid.h` | 193 | Hinge edge of the lid up to the top edge. Measure on the lid itself, not the hinge barrel (see §3). |
| `screen.w` | 260 | Left to right edge of the **lit** area, not the glass. |
| `screen.h` | 147 | Bottom to top edge of the lit area. |
| `screen.bottom` | 27.0 | Lid hinge edge up to the bottom of the lit area. |
| `camera.w` | 20 | Width of whatever must stay uncovered: camera lens, sensor, LED and any raised bump around them. |
| `camera.h` | 8 | Height of that same region. |
| `camera.top_offset` | 8 | Lid top edge down to the **top** of the camera region. |

**Check the screen is centered:** measure from the left lid edge to the left of the lit area, then from the right lid edge to the right of the lit area. The model assumes those two are equal. If they differ by more than 1 mm, note both numbers.

**Check the camera is centered:** do the same left/right check for the camera region.

---

## 2. Side view: lid thickness (the critical one)

Close the lid partway, or look along the side edge. Measure **front face to back face** with the caliper jaws flat across the lid.

```
          SIDE VIEW (looking at the left edge of the open lid)

                 top edge
                   ┌─┐   ◄── T1  near the top
                   │ │
                   │ │
         screen ─► │ │ ◄─ back cover
          side     │ │   ◄── T2  middle
                   │ │
                   │ │
                   │ │   ◄── T3  near the hinge (above it)
                   └─┘
                 ══╪══   hinge
```

```
          CROSS-SECTION of the lid edge (cut through it horizontally)

       Square edge (what the model assumes)      Rounded / tapered edge

            back ┌──────────────                  back ╭─────────────
                 │                                     │
                 │◄─ lid.t ─►                    ◄─ lid.t ─►   (measure the full
                 │                                     │       thickness, not
           front └──────────────                 front ╰─────────────   the edge)

              screen face                         screen face
```

| Key | Current | How to measure |
|---|---|---|
| `lid.t` | 7.0 | Measure at **T1, T2 and T3** on **both** the left and right edges (6 readings), and at the center of the top edge. Use the **largest** reading. |

What to look for:
- **Wedge:** T3 (near the hinge) is noticeably thicker than T1 (near the top), by more than about 0.5 mm. Tell me both numbers, because the model is a flat box and a wedge needs a different base shape.
- **Rounded or tapered edge:** the edge is thinner than the middle of the lid. Measure the full thickness with the jaws reaching past the curve, and note roughly how wide the rounded band is.

The fit-test coupons sweep lid thickness 6.5 / 7.0 / 7.5 mm. If your reading is outside that range, set `lid.t` before printing the coupons.

---

## 3. Hinge clearance

The shell now runs all the way down to the lid's hinge edge (`fit.bottom_hinge_relief = 0`), so it covers the whole lid. Check that the hinge can still rotate with the shell on.

```
          FRONT VIEW, bottom of the lid

            │                                                │
            │            shell covers the full lid           │
            │        ▲                          ▲            │
            │        │ H                        │ H          │
            │    ┌───┴───┐                  ┌───┴───┐        │
            └────┤ hinge ├──────────────────┤ hinge ├────────┘   y = 0  (lid hinge edge = shell bottom edge)
                 └───────┘                  └───────┘
```

| What | How to measure |
|---|---|
| Hinge height **H** | From the lid's hinge edge up to the highest point of any hinge cover, barrel or trim attached to the lid. Anything here must fit inside the 0.5 mm rear / 0.8 mm front gaps, or the shell will hit it. |
| Hinge travel | Open and close the lid fully. Watch whether the base or the hinge cover swings into the space the shell's bottom edge now occupies (about 13 mm thick at the bottom edge). |

If the hinge interferes, set `fit.bottom_hinge_relief` to H plus a few mm (it was 14 mm before) and rebuild.

---

## 4. Things on the screen face and edges

The front bezel sits **0.8 mm** in front of the screen face (`fit.front_gap`), and the side walls and top cap wrap the lid edges.

```
          SIDE VIEW, close-up of the screen face

                 back cover │█│
                            │█│ ◄── rubber bumper sticks out by B
                            │█│▄▄
                            │█│
                  bezel ──► │█│ ░   ◄── printed front bezel, 0.8 mm gap
                            │█│ ░
```

| What | How to measure | Why |
|---|---|---|
| Rubber bumpers **B** | Caliper depth rod: how far each bumper sticks out above the screen-face bezel. Note where they are. | If B > 0.8 mm, the bezel either needs pockets there or a bigger `front_gap`. |
| Raised bezel lip | Same depth measurement for any raised plastic rim around the glass. | Same reason. |
| Side/top edge features | Note position and size of any mic hole, LED, vent or button on the lid's side or top edges. | The walls and top cap cover these edges and may need a hole. |
| Back cover features | Logo, raised feet or ridges on the back of the lid, and their height. | The rear gap is only 0.5 mm (`fit.rear_gap`). |

---

## Record sheet

Fill this in and paste it back to me, or edit `projects/armor/params.toml` directly.

```
lid.w              ____  ____  ____   → max  ____
lid.h              ____  ____  ____   → max  ____
lid.t  left  T1 ____  T2 ____  T3 ____
       right T1 ____  T2 ____  T3 ____
       top-center ____                → max  ____
screen.w           ____  ____  ____   → avg  ____
screen.h           ____  ____  ____   → avg  ____
screen.bottom      ____  ____  ____   → avg  ____
screen centered?   left margin ____  right margin ____
camera.w           ____    camera.h ____    camera.top_offset ____
camera centered?   left ____  right ____
hinge height H     ____   (check travel; current bottom_hinge_relief = 0)
bumpers B          ____   at ________________
edge features      ____________________________________
back features      ____________________________________
wedge / rounded?   ____________________________________
```

## After measuring

1. Update `projects/armor/params.toml`.
2. Rebuild the coupons: `uv run cad build armor/fit_test --render --check --views standard`.
3. Print `out/armor/fit_test/*.3mf` and continue with the print order in `README.md`.
