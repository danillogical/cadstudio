# Plan: cadstudio multi-project refactor and Pocky dispenser M0

## Context

`plan-pockey-dispenser.md` asks for **M0 only** of a Pocky packet dispenser. M0 means:
- check the tooling;
- set up the project skeleton;
- draw a kinematic diagram of the Riva3D Tea Sachet Dispenser V2 reference;
- record the packet dimensions (165 × 55 × 5.2 mm);
- propose an independent parametric mechanism.

It then **stops for review** before M1.

What the user decided this session:
- **Licence:** Riva3D's permission has been obtained, so agents may measure the STLs and pull frames from the video. Meshes, frames and the video still stay **out of the repo and out of the outputs**.
- **Location:** the project goes inside cadstudio, and cadstudio is reworked to handle more than one project.
- **Reference copy:** delete `cadstudio/Archivos STL + Video de armado/`. It is byte-identical (`diff -rq`) to `~/Downloads/Archivos STL + Video de armado/`, which becomes the only copy the agents read.

Today cadkit only knows about the lid:
- `cadkit/params.py:117` (`Params`) hard-codes the lid sections.
- `cadkit/model.py:24-30` has the `check_lid`, `lid_envelope` and `screen_prism` fields.
- `cadkit/checks.py:180-183` always runs the lid and screen checks.
- `cadkit/render.py:96-110` always draws the lid ghost, and `:305-333` draws the lid sections.
- `cadkit/cli.py` loads `params/lid.toml` and takes models from one flat `models/` package.

cadstudio is **not a git repo**, so every before/after comparison uses file snapshots.

## Target architecture

```
cadkit/                      generic engine, no lid knowledge
  model.py                   ModelPart: shape, print_location, wall_shape, min_wall
  params.py                  load_sections(path, schema) + generic dotted override(); shared Printer/Material/Structure(min_wall)
  checks.py                  generic checks + a project hook that inserts project checks after bed_fit (preserves order)
  render.py                  generic standard views + print view; hook supplies extra "ghost" meshes, which also feed camera bounds
  project.py                 Project record (name, params path/loader, models package, check hook, render hooks) + discovery
  cli.py                     `cad list` → `armor/armor_proto …`; `cad build <project>/<model>` (bare name OK when unique); out `out/<project>/<model>/`
projects/
  armor/                     everything lid-specific, behaviour unchanged
    __init__.py              PROJECT = Project(...)
    params.toml, params.py   was params/lid.toml; Lid/Screen/Camera/Fit/Fasteners, lid_envelope, screen_prism, derived Z
    part.py                  ArmorPart(ModelPart) adds check_lid/check_screen/lid_envelope/screen_prism; plain ModelPart gets lid checks by default (demo_cube relies on it)
    checks.py                lid_interference, lid_min_gap, screen_clear
    render.py                owns detail_* and section_* views wholesale, plus the lid/screen ghost
    models/                  _armor_base, armor_*, fit_test, demo_cube
  pocky/
    __init__.py, params.toml, params.py
    geometry/packet.py       rigid packet solid + non-overlapping stack (1/2/10/25); a library, not a model
    models/packet_dummy.py   printable rigid 165×55×5.2 envelope dummy (the plan's §5-D early-test dummy)
    docs/                    reference-notes.md, kinematic-diagram.png, mechanism-proposal.md, proposal-diagram.png, m0-report.md
tests/                       flat (conftest imports break with subdirs): test_cadkit_*, test_armor_*, test_pocky_*
```

`projects/pocky/` only gets the M0 files, with no empty stubs for actuator, linkage or simulations. Its README says where those will go in M1 and later.

## Steps

- [ ] 1. Tooling and baseline → **orchestrator** (a handful of commands).
  - Tooling check: `uv sync`, `import build123d`, `ffmpeg -version`.
  - Snapshot the repo to `/tmp/cadstudio-baseline`, leaving out `.venv`, `out` and the reference folder.
  - Build all 5 models with `--render --check --views all` **twice**, into `/tmp/cadstudio-base-out{1,2}`. This shows whether the PNGs and STLs are reproducible.
  - Save the test IDs from `pytest --collect-only -q`.
  - `rm -rf` the in-repo reference folder.
- [ ] 2a. Mechanical move, with no change to the API, CLI or output paths → **worker-easy** (every edit is listed in the brief).
  - Move `models/` to `projects/armor/models/` and `params/lid.toml` to `projects/armor/params.toml`.
  - Update the pointers in `cadkit/registry.py:8,13,20`, `cadkit/params.py:21` and `pyproject.toml` (`packages`).
  - Fix the `models._armor_base` imports in the 4 model files, `tests/test_models.py:18` and `tests/test_cadkit_export_cli.py:78`.
- [ ] 2b. The multi-project contract → **worker-hard** (this sets the contract every later step builds on, and a wrong boundary across four modules is expensive to undo).
  - `cadkit/project.py`, the hooks, `ArmorPart`, armor's `checks.py` and `render.py`, CLI addressing, output paths.
  - The hook decisions from the target architecture are written into the brief.
  - Test edits are limited to imports and paths, `ModelPart`→`ArmorPart`, model-name strings (`armor/…`), and call-site signature changes.
  - Fix the `startswith("armor_")` filter at `tests/test_models.py:20` so the parametrised suite isn't silently emptied.
  - Rename the test files to the flat `test_cadkit_*`, `test_armor_*` and `test_pocky_*` prefixes.
- [ ] 3. Update `CLAUDE.md`, `README.md` and `MEASURING.md` for the new layout, commands, output paths and moved `path:line` references, including a short pocky section → **worker-medium** (a prose edit where deciding what's stale takes judgement).
- [ ] 4. Reverse-engineer the reference linkage from `~/Downloads/Archivos STL + Video de armado/` → **worker-hard** (spatial reasoning from video frames and mesh sections, where a better model materially changes the result).
  - Measure the STL features with trimesh sections: pivot bores, pin and slot widths, and the radius, centre and sweep of the channel in `Base`. Confirm the units are mm against the bounding boxes in the plan.
  - Extract frames with ffmpeg (scene detection, plus 1 fps around the mechanism shots) into `/tmp/pocky-ref/`.
  - Run Python on the reference files with `-I`, from scripts kept in `/tmp`.
  - Write `projects/pocky/docs/reference-notes.md`: the numbers and how each was measured, every item labelled known, inferred or uncertain, and what `Pinza` is for.
  - Write `kinematic-diagram.png`, drawn from the **measured parameters**, not from mesh polylines.
- [ ] 5. Pocky skeleton → **worker-medium** (follows the armor project pattern from 2b).
  - `projects/pocky/{__init__,params}.py` and `params.toml`, with the packet, magazine, separator, printer, material and structure values from the plan's §4 table.
  - `geometry/packet.py` and `models/packet_dummy.py`.
- [ ] 6. `tests/test_pocky_*.py`, written from the spec in plan §1 and §4, not from step 5's code → **worker-medium** (a fresh worker; the pattern exists in `tests/test_cadkit_*`). It tests that:
  - the packet bounding box is 165×55×5.2;
  - a stack of N has N solids with no overlapping pairs and height N×5.2 (52 for 10, 130 for 25);
  - `--set` reaches the pocky params;
  - `packet_dummy` passes valid_solid, watertight and bed_fit.
- [ ] 7. Mechanism proposal, `projects/pocky/docs/mechanism-proposal.md` plus `proposal-diagram.png` from a short analytic 2D sweep → **worker-hard** (mechanism design judgement; a fresh worker that reads step 4's notes, so the design is independent rather than a trace). It covers:
  - a slider driving a bell crank through a pin and slot to move the ejector;
  - each named parameter, with its starting value and how it was derived;
  - a comparison of dispensing along +X versus +Y, with a recommendation;
  - how the separator gap is adjusted;
  - open questions for review.

  Names shared with `params.toml` (packet, magazine, separator) must match it. Linkage parameters stay in the proposal, marked for M1. Step 7 does **not** edit `params.toml`.
- [ ] 8. Run the full `uv run pytest tests -q`, then write `projects/pocky/docs/m0-report.md` → **orchestrator**. The report gives PASS/FAIL for each M0 item in plan §9, the commands run, artifact paths, unresolved items, and says M1 is not authorized until review.

### Order and concurrency
- 1 runs first. Then 2a and 4 run in parallel: the files don't overlap, and it's one Haiku and one Opus.
- I take a snapshot after 2a.
- 2b runs after 2a, and also after 4, since only one Opus runs at a time.
- 3 and 5 run in parallel after 2b (two Sonnet).
- 6 runs after 5.
- 7 runs after 4 and 5. It is Opus, so it can overlap 3 and 6.
- 8 runs last.

### Verification per step
1. The two baseline runs exist. I record whether the PNGs and STLs come out byte-identical. The tooling versions are recorded. The in-repo reference folder is gone, and the `~/Downloads` copy is intact.
2a. Same commands as the baseline. STLs, PNGs and render filename lists are byte-identical (or within the pixel tolerance if step 1 showed the renders aren't deterministic). `report.json` matches. The test IDs collected are the same as the baseline's.
2b. **I hold this gate.**
  - Per model, between `out/armor/<model>/` and the baseline: same render filenames; PNGs identical or within the pixel tolerance; STL bytes identical; `report.json` matches on names, order, statuses, `detail` strings and values (to 1e-6).
  - Collected test IDs equal the baseline's apart from the renames, with no new skips.
  - In the diff of `tests/` against the post-2a snapshot, every change is one of the allowed kinds.
  - `grep -rn 'lid\|screen' cadkit/` finds nothing lid-specific.
3. Grep the docs for `params/lid.toml`, `models/armor_`, `out/<model>` and the old command forms. Run every command quoted in a Commands section.
4. I read the notes and look at the diagram. Every dimension states its method. `find projects \( -name '*.stl' -o -name '*.mp4' -o -name '*.jpg' \)` finds nothing.
5. `uv run cad build pocky/packet_dummy --render --check --views standard` gives no FAIL, and I read the iso render.
6. The tests pass against step 5's code unmodified. If one fails, I work out whether the spec or the code is wrong before either side is edited.
7. The shared names match `params.toml`, the diagram renders, and the recommendation cites the contact-edge reasoning from plan §4.
8. pytest is green, and the report covers every M0 item in plan §9.

### What could invalidate the plan
- **Renders aren't reproducible:** if the two step-1 runs give different PNGs, render comparison falls back to a pixel tolerance, or a visual check if the tolerance is meaningless. In that case 2b's gate leans on the reports and STLs.
- **The reference doesn't pin down the linkage:** if the video and meshes don't fix the pivot/slot relationship, step 4 marks it uncertain and M0 stops for review there. Step 7 still proposes a design and flags this.
- **The hook API keeps growing:** if 2b needs more than check and ghost hooks, I stop and re-plan rather than let cadkit absorb armor concepts.

## End state
As plan §9 requires, M0 stops for review. The linkage identification, the dispense axis and the separator scheme wait for the user's approval before M1 starts.
