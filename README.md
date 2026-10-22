# cadstudio

Python CAD projects on [build123d](https://github.com/gumyr/build123d), which runs on the OpenCascade B-rep kernel. The generic engine is `cadkit/` (params, STEP/STL/3MF export, renders, printability checks, the `cad` CLI). Each design is a project under `projects/`. Target printer: Prusa XL (360 × 360 × 360 mm bed), material PETG.

| Project | What it is | Docs |
|---|---|---|
| `armor` | Cyberdeck lid armor: a two-piece shell for a Lenovo IdeaPad 3 Chromebook 11AST5. | This file, `MEASURING.md` |
| `pocky` | Pocky packet dispenser (mechanical prototype, early skeleton). | `projects/pocky/README.md` |

## Setup

```
uv sync
uv run cad list
```

`cad list` prints every model as `<project>/<model>`, for example `armor/armor_industrial`. Commands take `<project>/<model>`, or a bare model name when it is unique across projects.

Output goes to `out/<project>/<model>/`. Adding `--check` writes `report.md` with a check table, and `--render` writes PNGs to `out/<project>/<model>/renders/`. Each project's default params file is `projects/<project>/params.toml`. To rebuild one model with both:

```
uv run cad build armor/armor_proto --render --check --views standard
```

Run the tests with `uv run pytest tests -q` (about 3.5 minutes).

## Optional physics

Rigid-body physics is an optional extra. The CAD commands above never import it, so they work
without it installed.

```
uv sync --extra physics
uv run cad physics smoke
```

`cad physics smoke` drops a 20 mm box 100 mm onto a fixed floor and checks the free fall
against `z = ½gt²` (1 % gate), the contact time against `√(2h/g)` (a coarse sanity check at
trace resolution, about ±8.5 %), the rest height (0.1 mm), the mass
(`volume_mm3 × g/cm3 × 1e-6` kg) and the cube inertia (`m a²/6`). It writes `scene.xml`,
`manifest.json`, `summary.json`, `report.md` and `trace.csv` under
`out/fixtures/gravity_drop/physics/<run-id>/`. Exit codes: `0` PASS, `1` FAIL, `2`
INCONCLUSIVE, `3` ERROR. A physics *usage* error also exits `3`, not argparse's `2`, so a
typo can never be mistaken for an INCONCLUSIVE verdict. There is no GUI and no rendering on
this path.

The fixed floor is an intentional analytic test fixture. It is not a product restraint and
does not make the result a diagnostic-only run.

## Pocky project

The printed prototype CAD and motion proof are in
[projects/pocky/README.md](projects/pocky/README.md). The MuJoCo workflow is paused
after accepted generic M0–M4 infrastructure and the approved M5a-1 adapter/S0
implementation plan. The product adapter has not been implemented or validated.
Physical measurements and prototype trials remain unverified.

Resume from [the checkpoint](docs/mujoco-paused.md),
[planning acceptance](docs/mujoco-m5a-plan-acceptance.md) and
[the approved plan](docs/mujoco-m5a-plan.md). Portable review evidence is in
[docs/evidence/mujoco-m5a-plan](docs/evidence/mujoco-m5a-plan/README.md).

# Armor project

A 3D-printable armor shell that slides over the display lid of a Lenovo IdeaPad 3 Chromebook 11AST5 (11.6"). It has two pieces, a front bezel and a rear shell, joined with M3 screws into heat-set inserts. The shell slides down from the top of the lid. The hinge edge stays open, and the fit is loose so it never clamps the LCD. The original concept is `armor-p1.scad`, which is not part of this repo.

The code is in `projects/armor/`, the params in `projects/armor/params.toml`, and the models in `projects/armor/models/`: `armor_industrial`, `armor_neon`, `armor_proto`, `demo_cube`, `fit_test`.

## Models

Masses are PETG estimates for fully solid parts, from `out/armor/*/report.md`. Sliced prints with infill weigh less.

| Model | What it is | Parts (mass) |
|---|---|---|
| `fit_test` | Nine corner coupons sweeping slide clearance and lid thickness, plus an insert test. | `c040_t65` … `c100_t75` (about 19.2–20.2 g each), `insert_test` (3.5 g) |
| `armor_proto` | Plain shell with no decoration. Use it to check the full fit. | `rear` (246.2 g), `front` (70.5 g) |
| `armor_industrial` | Segmented bezel plates, corner guards, hex bolt and nut guards, stencil text, knurled rear skin. | `rear` (318.3 g), `front` (105.8 g) |
| `armor_neon` | LED-strip channel with angular plates on the bezel, glow slots on the back. | `rear` (359.2 g), `front` (83.6 g), `diffuser_left` and `diffuser_right` (2.7 g each) |
| `demo_cube` | A 20 mm test cube for checking the toolchain. Not part of the armor. | `cube` |

Coupon names read as `c<clearance × 100>_t<thickness × 10>`. For example, `c070_t65` is clearance 0.7 mm and lid thickness 6.5 mm.

## Measuring your lid

Measure with calipers, then put each value in `projects/armor/params.toml`. See `MEASURING.md` for the step-by-step guide with diagrams and a record sheet.

| Measurement | Key | Notes |
|---|---|---|
| Lid width, side edge to side edge | `lid.w` | |
| Lid height, hinge-side edge to top edge | `lid.h` | |
| Lid thickness | `lid.t` | Measure at several points and use the largest. |
| Active display width (lit area) | `screen.w` | |
| Active display height (lit area) | `screen.h` | |
| Bottom edge of active area, from hinge edge | `screen.bottom` | |
| Camera notch width | `camera.w` | |
| Camera notch height | `camera.h` | |
| Camera notch top, gap below lid top edge | `camera.top_offset` | |

After changing any of these, rebuild every model, for example:

```
uv run cad build armor/armor_proto --render --check --views standard
uv run cad build armor/armor_industrial --render --check --views standard
uv run cad build armor/armor_neon --render --check --views standard
uv run cad build armor/fit_test --render --check --views standard
```

## Print order

1. **Print `fit_test` first.** The nine corner coupons sweep clearance {0.4, 0.7, 1.0} mm against lid thickness {6.5, 7.0, 7.5} mm. Each one is labelled on its side wall, for example `C0.4 T6.5`. Print `insert_test` with them. Print the coupons standing on their cut face.
2. **Fit the coupons to the lid.** Slide each coupon onto the lid's top-left corner and pick the one that slides freely without rattling. Set `fit.slide_clearance` and `lid.t` in `projects/armor/params.toml` to match.
3. **Choose the insert size.** `insert_test` has three bores at `insert_d` −0.3, 0 and +0.3 mm, labelled `-`, `0` and `+`. Pick the bore the heat-set insert seats in best, and set `fasteners.insert_d`.
4. **Check the full fit.** Rebuild and print `armor_proto`.
5. **Print a decorated variant.** Once the fit is confirmed, print `armor_industrial` or `armor_neon`.

## PETG settings

These are recommended starting points.

- 0.4 mm nozzle, 0.2 mm layers.
- 4–6 perimeters, 15–20% gyroid infill.
- Textured PEI sheet, no supports. The design avoids supports. Overhang warnings are short bridges.
- Front bezel: print with the visible face up. Rear shell: print with the back face down.
- Neon diffusers: clear or natural PETG.
- Heat-set M3 inserts: soldering iron at about 230 °C.

## Hardware

- **M3 screws.** The shank length is `front_th + insert_depth − counterbore_depth` = 2.4 + 5.0 − 1.2 = 6.2 mm. Use M3×6, the nearest standard length. It ends 0.2 mm short of the insert bottom.
- **Heat-set inserts.** Six, one per screw position.
- **Neon LED strip.** A 5 mm-wide COB LED strip. The model's default strip width is 5.0 mm, set by `LED_STRIP_W` in `projects/armor/models/armor_neon.py:30`. Override it with `NEON_LED_STRIP_W`. The channel is the strip width plus 0.4 mm clearance.
  - At 5 mm, all 26 path segments fit in a single run.
  - At 8 mm, only 18 of 26 segments fit, split into 4 runs. The 8 mm strip therefore only partly fits. Measured with `NEON_LED_STRIP_W=8`.
- **Neon diffusers.** Thin press-fit clear strips in the channel. Skip them with `NEON_DIFFUSER=0`. Use a separate `--out` directory, so the diffuser files from the main build are not left behind in `out/armor/armor_neon`:

  ```
  NEON_DIFFUSER=0 uv run cad build armor/armor_neon --out out/armor/armor_neon_nodiffuser --views standard
  ```
