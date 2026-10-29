# AGENTS.md

Instructions for coding agents (Claude Code, Codex) working with cadstudio. The human-facing overview is in `README.md`. For driving the GUI and the build/check/render loop end to end, use the `cadstudio` skill.

## What this is

cadstudio is a Python CAD workflow on build123d, which is a Python library on the OpenCascade B-rep kernel (not OpenSCAD). The generic engine is `cadkit/` (params, export, render, checks, CLI). Each design lives in its own project under `projects/<name>/`, which plugs into the engine through a `Project` record. Default printer: 360³ mm bed (Prusa XL). Default material: PETG.

The engine bundles one project, `projects/starter`, with the models `starter/box` and `starter/hinge`. It is the worked example for new projects.

Platform: macOS on Apple silicon (arm64) only.

## Setup

- `./setup.sh` installs the environment, builds the GUI and the VS Code extension, and links the skills.
- `uv run cad doctor` reports Python, uv, build123d, MuJoCo, node/npm, the output dir and the UI/extension builds. Run it first if anything looks broken.

## Workspace

The workspace is the nearest ancestor of the current directory that contains a `projects/` directory, or `$CADSTUDIO_WORKSPACE` when set. Projects are loaded from `<workspace>/projects/`, and default outputs go under `<workspace>/projects/<project>/out/` (model outputs and physics runs), while GUI state goes to `<workspace>/.cadstudio/`. The engine checkout is itself a workspace (it holds `projects/starter`). A project collection can live in its own repo as a workspace with a `projects/` directory and a path dependency on cadstudio; run `uv run cad ...` from inside it. Source: `cadkit/workspace.py`.

## Commands

- `uv run cad list [--json]` lists models as `<project>/<model>` (every `projects/<project>/models/*.py` not starting with `_`), e.g. `starter/box`.
- `uv run cad build <model> [--part NAME] [--render] [--check] [--scene] [--views standard|detail|sections|all] [--set KEY=VAL ...] [--params PATH] [--out DIR] [--json]` exports STEP, STL and 3MF, then optionally renders and checks. `--scene` also writes `projects/<project>/out/<model>/scene/`, and is skipped if a check FAILs.
- `uv run cad render <model> [--views ...]` renders only.
- `uv run cad check <model> [--set ...]` runs checks only. Exit code is 1 if any check FAILs.
- `uv run cad gui scene <model> [--set ...] [--params P] [--out DIR] [--json]` writes `projects/<project>/out/<model>/scene/` (`scene.json` and `parts/<id>.glb` in assembly coordinates, in mm).
- `uv run cad gui open [<model> | --run RUN_DIR] [--editor auto|vscode|browser] [--no-open] [--json]` shows a model or run in the CADStudio panel (see "Live monitoring").
- `uv run --frozen --extra physics cad gui trajectory RUN_DIR [--fps N] [--contacts] [--json]` writes `<run-name>.gui/` next to the run (`trajectory.json`, `poses.bin`, `meshes/*.glb`, optional `contacts.bin`, in mm). It never writes into the run dir.
- `uv run --frozen --extra physics cad gui serve [--port 0] [--no-browser] [--json]` starts the loopback GUI service and writes `.cadstudio/gui/service.json` (and `service.log` beside it).
- `uv run --frozen --extra physics cad physics run <model> --scenario S --acceptance A [--options F] [--params P] [--set KEY=VAL ...] [--out DIR] [--no-live] [--live-fps N]` writes the run dir and, unless `--no-live`, a sibling `<run-name>.live/` that streams poses while the run steps (`--live-fps` sets its sample rate, default 30).
- `uv run cad doctor [--json]` reports the local toolchain.

`--json` prints one JSON document on stdout and sends progress to stderr; the exit codes do not change.

`<model>` is `<project>/<model>`, or a bare model name when it is unique across projects (a name shared by two projects is an error). The default output dir is `projects/<project>/out/<model>/` and the default params file is the project's `params.toml`. Physics runs default to `projects/<project>/out/<model>/runs/<scenario_id>-<UTC stamp>/`, and `--out` overrides that.

`--views` defaults to `all` for both `build` and `render`, which is slow. Use `--views standard` while iterating.

## The iteration loop

1. Edit the project's `params.toml` or `projects/<project>/models/*.py`.
2. Run `uv run cad build <project>/<model> --render --check --views standard`, e.g. `uv run cad build starter/box --render --check --views standard`.
3. Read `projects/<project>/out/<model>/report.md`, then the PNGs in `projects/<project>/out/<model>/renders/`.
4. Pick the render that answers the question. The `standard` set gives `iso.png`, `front.png`, `back.png`, `top.png` (overall shape) and `<part>_print.png` (print pose). Any other view set comes from the project's `extra_views` hook.
5. Never claim a geometry change works without reading the check report and at least one render.

Renders in `projects/<project>/out/<model>/renders/` are not cleared between runs. A `--views standard` build leaves old `section_*` and `detail_*` files in place, so check timestamps (`ls -lt`) before reading one.

Use `--set KEY=VAL` for quick experiments, e.g. `--set box.wall=3`. Use `--out` for a scratch directory. `--part` with `--check` writes a report containing only that part into the outdir, which overwrites the model's `report.md`, so pair `--part` with `--out`.

## Projects and models

A project is a package `projects/<name>/` whose `__init__.py` defines `PROJECT`, a `Project` (`cadkit/project.py`). Discovery is automatic. Its fields:

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
- `min_wall`: per-part override of the project's minimum wall. Use it only where a part is intentionally thinner. Do not use it to hide a real thin wall.

Projects subclass `ModelPart` for their own per-part options (starter: `StarterPart` in `projects/starter/part.py`).

### Adding a project

`projects/starter/` is the worked example: copy it and rename. A project can live in this repo's `projects/`, or in its own repo as a workspace (a `projects/` directory plus a path dependency on cadstudio in its `pyproject.toml`).

1. Create `projects/<name>/` with `__init__.py`, `params.toml`, `params.py` and a `models/` package.
2. In `params.py`, define frozen dataclass sections plus a `Params(Overridable)` class and `load_params(path)`. Use `load_sections` and the shared `Printer`/`Material` from `cadkit/params.py` (see `projects/starter/params.py`).
3. In `__init__.py`, build a `PROJECT = Project(name=..., params_path=..., load_params=..., models=models)`. Add `check_hook`, `ghost_meshes` and `extra_views` only if needed. Import heavy modules lazily inside them, so `cad list` stays fast.
4. Add models under `models/`, each with `build(p)`.
5. Add tests as `tests/test_<name>_*.py`.

## Generic checks

Results go to `projects/<project>/out/<model>/report.md` and `report.json`. Source: `cadkit/checks.py`. Projects add checks through `check_hook`.

- `valid_solid`: FAIL if the shape is invalid or is not exactly one solid.
- `watertight`: FAIL if the tessellated mesh is not watertight.
- `bed_fit`: FAIL if the bounding box exceeds the bed or the part is not resting on z=0.
- `min_wall`: FAIL if the 1st-percentile sampled ray thickness is under 95% of the required wall. WARN if the single thinnest ray is under 50% of it.
- `min_feature`: WARN only, never FAIL. Measures decoration (surface more than 0.05 mm from `wall_shape`). WARN if the 1st percentile is under 0.8 mm. Runs only when `wall_shape` is set.
- `overhangs`: WARN only, never FAIL. Area of downward faces steeper than 45° that are off the bed, in print pose. Those faces need support. PASS when there are none.
- `mass`: INFO only. Assumes a fully solid part, so slicer infill makes real prints lighter.

## Live monitoring

Open the panel once with `uv run cad gui open <model>`. After that, run builds with `--scene` and physics runs as usual: with Follow on (the default), the panel follows them. Edits to the shown model's sources rebuild it, and a `cad physics run` streams poses into the panel while it steps. Don't re-run `cad gui open` for each change; each call reveals the panel again. See "Live monitoring" in `README.md`.

## Tests

- `uv run pytest tests -q` runs the engine suite (about 3.5 minutes). Run it once at the end of a change, not after every edit.
- Tests are flat in `tests/`, named by what they cover: `test_cadkit_*.py` (engine: checks, params, export, CLI, GUI, physics).
- Never edit a test to make a model pass. Fix the model. If a test looks wrong, say so and ask.
- The GUI and extension have their own suites: `npm test` in `ui/` and in `editor/vscode/`.

## Skills

The `cadstudio` skill (`.claude/skills/cadstudio/`, also at `.agents/skills/cadstudio/`) covers the build/check/render loop, `cad gui open`, live monitoring and physics runs. The `connect-ide` skill opens reports, renders and videos in the VS Code window with `code`. Use the `cadstudio` skill whenever you build, check or view a model or run.
