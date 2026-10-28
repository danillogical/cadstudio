# CLAUDE.md

Instructions for Claude Code working in this repo. The human-facing overview is in `README.md`.

## What this is

cadstudio is a Python CAD workflow on build123d, which is a Python library on the OpenCascade B-rep kernel (not OpenSCAD). The generic engine is `cadkit/` (params, export, render, checks, CLI). Each design lives in its own project under `projects/<name>/`, which plugs into the engine through a `Project` record. Printer: Prusa XL, 360³ bed. Material: PETG.

Projects:

- `armor`: cyberdeck armor shell for a Lenovo IdeaPad 3 Chromebook lid. See "Armor project" below.
- `pocky`: Pocky packet dispenser. See "Pocky project" below.

## Commands

- `uv sync` installs the environment.
- `uv run cad list [--json]` lists models as `<project>/<model>` (every `projects/<project>/models/*.py` not starting with `_`), e.g. `armor/armor_industrial`.
- `uv run cad build <model> [--part NAME] [--render] [--check] [--scene] [--views standard|detail|sections|all] [--set KEY=VAL ...] [--params PATH] [--out DIR] [--json]` exports STEP, STL and 3MF, then optionally renders and checks. `--scene` also writes `out/<project>/<model>/scene/`, and is skipped if a check FAILs.
- `uv run cad render <model> [--views ...]` renders only.
- `uv run cad check <model> [--set ...]` runs checks only. Exit code is 1 if any check FAILs.
- `uv run cad gui scene <model> [--set ...] [--params P] [--out DIR] [--json]` writes `out/<project>/<model>/scene/` (`scene.json` and `parts/<id>.glb` in assembly coordinates, in mm).
- `uv run --frozen --extra physics cad gui trajectory RUN_DIR [--fps N] [--contacts] [--json]` writes `<run-name>.gui/` next to the run (`trajectory.json`, `poses.bin`, `meshes/*.glb`, optional `contacts.bin`, in mm). It never writes into the run dir.
- `uv run --frozen --extra physics cad gui serve [--port 0] [--no-browser] [--json]` starts the loopback GUI service and writes `out/.gui/service.json`.
- `uv run --frozen --extra physics cad physics run <model> --scenario S --acceptance A [--options F] [--params P] [--set KEY=VAL ...] [--out DIR] [--no-live] [--live-fps N]` writes the run dir and, unless `--no-live`, a sibling `<run-name>.live/` that streams poses while the run steps (`--live-fps` sets its sample rate, default 30).
- The GUI service follows external builds and runs: a followed model rebuilds on source edits, and new scenes and runs appear in the open panel (see "Live monitoring" in `README.md`).
- `uv run cad doctor [--json]` reports Python, uv, build123d, MuJoCo, node/npm, the output dir and the UI/extension builds.
- `uv run pytest tests -q` runs the test suite (about 3.5 minutes).

`--json` prints one JSON document on stdout and sends progress to stderr; the exit codes do not change.

`<model>` is `<project>/<model>`, or a bare model name when it is unique across projects (`fit_test` works, a name shared by two projects is an error). The default output dir is `out/<project>/<model>/` and the default params file is the project's `params.toml`.

`--views` defaults to `all` for both `build` and `render`, which is slow. Use `--views standard` while iterating.

## The iteration loop

1. Edit the project's `params.toml` or `projects/<project>/models/*.py`.
2. Run `uv run cad build <project>/<model> --render --check --views standard`.
3. Read `out/<project>/<model>/report.md`, then the PNGs in `out/<project>/<model>/renders/`.
4. Pick the render that answers the question. The `standard` set gives `iso.png`, `front.png`, `back.png`, `top.png` (overall shape) and `<part>_print.png` (print pose). Any other view set comes from the project's `extra_views` hook (armor's are listed below).
5. Never claim a geometry change works without reading the check report and at least one render.

Renders are not cleared between runs. A `--views standard` build leaves old `section_*` and `detail_*` files in place, so check timestamps (`ls -lt`) before reading one.

Use `--set KEY=VAL` for quick experiments, e.g. `--set fit.slide_clearance=0.5`. Use `--out` for a scratch directory. `--part` with `--check` writes a report containing only that part into the outdir, which overwrites the model's `report.md`, so pair `--part` with `--out`.

## Projects and models

A project is a package `projects/<name>/` whose `__init__.py` defines `PROJECT`, a `Project` (`cadkit/project.py:38`). Discovery is automatic. Its fields:

- `name`: the `<project>` in `<project>/<model>`.
- `params_path`: default params TOML.
- `load_params`: `load_params(path) -> params` for the project's schema.
- `models`: the package holding the model modules.
- `check_hook`: `check_hook(mp, p) -> list[CheckResult]`, run right after `bed_fit`. Default: none.
- `ghost_meshes`: `ghost_meshes(p) -> [(mesh, color, opacity)]`, drawn translucent in standard views. Default: none.
- `extra_views`: `extra_views(part_meshes, p, rdir, want) -> {filename: path}` for view sets beyond `standard`. Default: none.

A model is `projects/<name>/models/<model>.py` exposing `build(p) -> dict[str, ModelPart]`. Modules starting with `_` are libraries, not models.

`ModelPart` is defined in `cadkit/model.py`. Generic fields:

- `shape`: build123d shape in assembly coordinates.
- `print_location`: transform into the bed pose, with the part resting on z=0. `None` means identity. Set it for every printable part, because `bed_fit` fails if z-min is not 0.
- `wall_shape`: the undecorated structural base. Set it on any part with decoration, to the plain base, never to the decorated shape. When set, `min_wall` probes this shape instead of `shape`, and `min_feature` measures the decoration.
- `min_wall`: per-part override of `structure.min_wall` (2.4 mm for armor). Use it only where a part is intentionally thinner (armor's neon diffusers use 1.0 mm). Do not use it to hide a real thin wall.

Projects subclass `ModelPart` for their own per-part options (armor: `ArmorPart`, below).

### Adding a project

1. Create `projects/<name>/` with `__init__.py`, `params.toml`, `params.py` and a `models/` package.
2. In `params.py`, define frozen dataclass sections plus a `Params(Overridable)` class and `load_params(path)`. Use `load_sections` and the shared `Printer`/`Material` from `cadkit/params.py`.
3. In `__init__.py`, build a `PROJECT = Project(name=..., params_path=..., load_params=..., models=models)`. Add `check_hook`, `ghost_meshes` and `extra_views` only if needed. Import heavy modules lazily inside them (see `projects/armor/__init__.py`), so `cad list` stays fast.
4. Add models under `models/`, each with `build(p)`.
5. Add tests as `tests/test_<name>_*.py`.

## Generic checks

Results go to `out/<project>/<model>/report.md` and `report.json`. Source: `cadkit/checks.py`. Projects add checks through `check_hook`.

- `valid_solid`: FAIL if the shape is invalid or is not exactly one solid.
- `watertight`: FAIL if the tessellated mesh is not watertight.
- `bed_fit`: FAIL if the bounding box exceeds the 360 mm bed or the part is not resting on z=0.
- `min_wall`: FAIL if the 1st-percentile sampled ray thickness is under 95% of the required wall. WARN if the single thinnest ray is under 50% of it.
- `min_feature`: WARN only, never FAIL. Measures decoration (surface more than 0.05 mm from `wall_shape`). WARN if the 1st percentile is under 0.8 mm. Runs only when `wall_shape` is set.
- `overhangs`: WARN only, never FAIL. Area of downward faces steeper than 45° that are off the bed, in print pose. Those faces need support. PASS when there are none.
- `mass`: INFO only. Assumes a fully solid part, so slicer infill makes real prints lighter.

## Tests

- `uv run pytest tests -q`, about 3.5 minutes. Run it once at the end of a change, not after every edit.
- Tests are flat in `tests/`, named by what they cover: `test_cadkit_*.py` (engine: checks, params, export, CLI), `test_armor_*.py` (armor), and `test_pocky_*.py` (pocky, as they are added).
- `tests/test_armor_models.py` is parametrized over every `armor_*` model. `fit_test` has its own `test_fit_test_*` tests in the same file.
- Never edit a test to make a model pass. Fix the model. If a test looks wrong, say so and ask.

## Armor project

Code: `projects/armor/`. Params: `projects/armor/params.toml`. Models: `projects/armor/models/`.

### Context

A 3D-printed cyberdeck armor shell that slides over the display lid of a Lenovo IdeaPad 3 Chromebook 11AST5 (11.6"). The shell has two pieces, a front bezel and a rear shell, joined with M3 screws into heat-set inserts. It slides down from the top, the hinge edge is open, and the fit is loose so it never clamps the LCD. Original concept: `~/Downloads/armor-p1.scad`.

### Layout

- `params.py`: Lid/Screen/Camera/Fit/Structure/Fasteners, `lid_envelope`, `screen_prism`, and the coordinate-convention docstring.
- `part.py`: `ArmorPart(ModelPart)`.
- `checks.py`: the armor `check_hook` (lid and screen checks).
- `render.py`: the lid ghost, `detail` and `sections` views.
- `models/_armor_base.py` (`projects/armor/models/_armor_base.py`) is the shared shell: `frame(p)`, `rear_shell(p)`, `front_bezel(p)`, `front_decor_face(p)`, `rear_decor_face(p)`, `print_location_front(p)`, `print_location_rear(p)`, `screw_positions(p)`, and the constants `DECOR_KEEPOUT` (2.0 mm, `projects/armor/models/_armor_base.py:18`) and `DECOR_EDGE_INSET` (3.0 mm, `projects/armor/models/_armor_base.py:20`).
- Models: `armor_proto`, `armor_industrial`, `armor_neon`, `fit_test`, `demo_cube`. Every `armor_*` model is picked up by `tests/test_armor_models.py` automatically.
- Use the part names `rear` and `front` for the shell pair. Extra parts (neon diffusers, test blocks) are fine.

### ArmorPart

`ArmorPart` (`projects/armor/part.py`) adds these fields to `ModelPart`:

- `check_lid` (default True): run lid interference and gap checks. Set False for parts that never sit on the lid, such as diffusers and test blocks.
- `check_screen` (default True): run the screen-clearance check. Same use as `check_lid`.
- `lid_envelope`, `screen_prism`: overrides. `fit_test` uses `lid_envelope` so each coupon is checked against its own swept lid.

A plain `ModelPart` gets the lid checks by default, with the default envelope and prism.

### Coordinate convention

From the `projects/armor/params.py` docstring (lines 3-9):

- X: lid width, centered on 0 (lid spans `-lid.w/2 .. +lid.w/2`).
- Y: from the lid's hinge edge (`y=0`) up to the top edge (`y=lid.h`).
- Z: from the back face of the rear shell (`z=0`) toward the viewer. The lid occupies `z in [back_th + rear_gap, back_th + rear_gap + lid.t]`. The front bezel inner face is at `front_z = back_th + rear_gap + lid.t + front_gap`.

### Armor views

- `detail_*.png` (`--views detail`, height-coloured): decoration. Only parts named `front` and `rear` get these.
- `section_*.png` (`--views sections`): fit and clearances.

### Armor checks

Added by `check_hook` (`projects/armor/checks.py`), after `bed_fit`:

- `lid_interference`: FAIL if the part overlaps the lid envelope by more than 1e-3 mm³.
- `lid_min_gap`: FAIL if the gap to the lid envelope is under half of `fit.slide_clearance`. Otherwise INFO.
- `screen_clear`: FAIL if the part overlaps the screen prism.

### Decoration rules

These keep variants printable and safe.

- Raised decoration goes only on the front visible face, inside `front_decor_face(p)` (at `z = total_t`).
- The front bezel inner face (`z = front_z`) is the print-bed face and stays flat.
- Nothing goes in the screen prism or the camera notch.
- Keep counterbores clear. `front_decor_face` subtracts them with a `DECOR_KEEPOUT` margin.
- Rear decoration goes only as recesses into the skin layer below z=0, cut from the bed side. Keep them at most about 1 mm deep and 6 mm wide so they bridge (`REAR_RECESS_D` 0.6 and `VENT_W` 5.0 in `armor_industrial`; `GLOW_DEPTH` 1.0 and `GLOW_W` 4.5 in `armor_neon`). Never cut into z ≥ 0.
- Keep the rear back face full coverage so it sits flat on the bed.
- Decoration features must be at least 0.8 mm wide (`min_feature`).
- Set `wall_shape` to the plain base part (e.g. `front_bezel(p)`).

### Armor gotchas

- **Knurl pitch.** In `armor_industrial`, `KNURL_PITCH` (`projects/armor/models/armor_industrial.py:132`) must not divide the knurl panel size evenly. The code comment says grooves must never graze a corner. A pitch that does divide it has produced an invalid 3MF mesh. After any knurl change, confirm `valid_solid` and `watertight` pass and inspect the 3MF.
- **Bed fit.** The shell is the lid width + 2 × (slide_clearance + 10.4 mm side wall), about 308 mm for the 11AST5. It was 358.2 mm for a 14" lid, close to the 360 mm bed limit.
- **Front `min_wall` WARN at 1.20 mm is by design.** The front is 2.4 mm thick and each counterbore is 1.2 mm deep, leaving 1.2 mm under each counterbore. That is exactly the warn threshold (50% of 2.4). Do not thicken the bezel just to clear it.
- **`fit_test` warns on `min_wall`.** Each coupon reports single-ray minima between 0.00 and 1.20 mm, while the 1st percentile is 2.40 mm and passes. These are WARNs, not FAILs. The cause has not been investigated.
- **Neon env vars are read at import time.** `NEON_LED_STRIP_W` and `NEON_DIFFUSER` are module constants in `projects/armor/models/armor_neon.py:30` and `:41`. Set them on the command line of the run that needs them.
- **Bash runs under zsh.** Capture exit codes with `$?` right after the command, or redirect to a file. Use `$pipestatus` for pipelines. In zsh, a word that starts with `=` (such as `===`) is treated as a command path, so avoid it in `echo` separators.

## Pocky project

A Pocky packet dispenser (mechanical prototype), in `projects/pocky/`. Its README, `projects/pocky/README.md`, is the entry point. Reference material is in `projects/pocky/docs/` (`reference-notes.md`, `kinematic-diagram.png`). Read the README before changing anything there; the armor rules above do not apply to it.
