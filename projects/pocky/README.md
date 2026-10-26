# Pocky packet dispenser

A 3D-printed, manual spring-return dispenser that ejects one wrapped Pocky packet at a time from the bottom of a stack. Plan: `plan-pockey-dispenser.md` at the repo root.

## Status

M1 motion proof passed Gate A. The next build is a 10-packet prototype made only of printed PETG. Plan and acceptance criteria: `plan-first-prototype.md` at the repo root. Current progress: `report-current-progress.md`. A metal spring and the long cycle test come after that prototype.

## Build

```
uv run cad build pocky/packet_dummy --render --check --views standard
POCKY_POSE=0 uv run cad build pocky/linkage_motion --render --check --views standard
POCKY_POSE=100 uv run cad build pocky/linkage_motion --render --check --views standard --out out/pocky/linkage_motion_100
uv run cad build pocky/prototype --render --check --views standard
```

`POCKY_POSE` is the percent of button travel (`0`, `25`, `50`, `75`, `100`). Output goes to `out/pocky/<model>/`. The M1 sweep is `projects/pocky/docs/m1_sweep.py`. The prototype sweep is `projects/pocky/docs/prototype_sweep.py`; it writes `out/pocky/prototype/gate_a.json`. The ejection cycle is `projects/pocky/docs/prototype_animation.py`; with the OCP CAD Viewer open it plays in the viewer.

## Parameters

`params.toml` is the single source of truth (mm). Override one-off with `--set KEY=VAL`.

| Key | Default | Meaning |
|---|---:|---|
| `packet.length` | 165.0 | Packet long axis (X) |
| `packet.width` | 55.0 | Packet short axis (Y) |
| `packet.height` | 5.2 | Packet thickness (Z), user-measured |
| `magazine.length_i` | 170.0 | Magazine internal length |
| `magazine.width_i` | 60.0 | Magazine internal width |
| `magazine.headroom` | 20.0 | Loading room above the stack |
| `magazine.capacity_test` | 10 | Packets in the current test (25 is the second test) |
| `separator.gap` | 5.75 | Separator slot height; adjustable by shims |
| `structure.min_wall` | 2.4 | Minimum printable wall |
| `printer.bed_x/y/z` | 360 | Prusa XL bed |
| `material.*` | PETG | Density and filament diameter |

Derived: `stack_nominal_height = magazine.capacity_test * packet.height`.

## Coordinates

X = packet long axis, Y = short axis, Z = vertical with stacked packets at increasing Z; the bottom packet's underside is at z = 0.

## Layout

- `geometry/packet.py`: packet envelope and stacks.
- `geometry/linkage.py`: crank, rod, pusher, floor fixture, and stops. Constants are proposed; they are not in `params.toml`.
- `geometry/prototype.py`: the printed housing, variant-B spring, and printed pegs. Kinematics come from `linkage.py`.
- `models/packet_dummy.py`: dummy packet.
- `models/linkage_motion.py`: one pose of the linkage (`POCKY_POSE`).
- `models/prototype.py`: the 10-packet PETG dispenser. Tube walls stop at the floor. The pivot stays at (−78, −8).
- Later: the 25-packet tube, a metal spring, and the long cycle test. They wait on the bench result for this prototype.

## Previewing a run

`preview.py` plays back a saved physics run (any `cad physics run` directory) from its `scene.xml` and `states.npz`. It never writes into the run dir. Contact points and forces are shown by default (`--no-contacts` hides them), and `--transparent body,lip` makes those bodies see-through so the mechanism shows.

```
uv run --frozen --extra physics python projects/pocky/preview.py out/mujoco-sim-valid/s1/run
uv run --frozen --extra physics mjpython projects/pocky/preview.py out/mujoco-sim-valid/s1/run
uv run --frozen --extra physics python projects/pocky/preview.py out/mujoco-sim-valid/s1/run --video /tmp/s1.mp4 --start 2.9 --end 3.6 --transparent body,lip
```

The first opens an interactive viewer that loops at 0.25x. On macOS the viewer needs `mjpython`, and plain `python` works for it too: the script re-launches itself under the venv's `mjpython`. With a uv-managed Python, `mjpython` also needs a link to that interpreter's libpython inside the MuJoCo app bundle, and the script creates or repairs it on each interactive start (a `uv sync` or mujoco reinstall removes it). `--check-viewer` does the re-launch and the viewer import without opening a window. Keys: space pause, left/right step one frame while paused, `[` / `]` halve or double the speed, `r` restart. The second renders an mp4 through `ffmpeg`. `--speed` is sim seconds per playback second, `--start`/`--end` pick a sim-time window, and `--dry-run` prints the frame schedule without opening anything. The CAD meshes are shown and the collision primitives hidden; `--colliders` shows the primitives. Force arrows are scaled to the strongest contact in the window, so `--force-scale` (a multiplier) shortens them when a high-load window clutters the frame.

## Dispense pass/fail

A headless run that checks the packet makes it out of the body and the body does not move. The packet criteria (`packet_exit`, `packet_presentation`, `exactly_one_packet`, `pickup_ready`) are the frozen `physics/acceptance.toml`, copied verbatim into `physics/dispense_acceptance.json`. The housing criteria (body/chassis pose, signed world-z drop, body contact with pusher, rod and crank, penetration) are the `physics/s0_acceptance.json` thresholds, applied in each of the actuate, press_hold, release and hold phases. The scenario is a 3 s settle, a 2 s linear ramp of the button from 0 to -25 N, 1 s held, a 0.5 s release and a 1.5 s hold.

```
uv run --frozen --extra physics cad physics run pocky/prototype --scenario projects/pocky/physics/scenarios/dispense.json --acceptance projects/pocky/physics/dispense_acceptance.json --options projects/pocky/physics/options/dispense.toml --out out/mujoco-dispense/run
```

Exit codes: 0 PASS, 1 FAIL, 2 INCONCLUSIVE, 3 ERROR. It takes roughly 5 minutes. The current prototype is expected to FAIL. `preview.py` can view the resulting run directory (see "Previewing a run").

### Syringe dispense pass/fail

The syringe model's default separator is the wedge (`separator = "blade"` in an options file selects the blade); the earlier single-cycle syringe runs under `out/mujoco-syringe/` were recorded with the blade.

The same packet criteria and housing thresholds applied to the `pocky/syringe` model, in `physics/syringe_dispense3_acceptance.json`. What differs from the prototype run:

- The body is one printed housing (the lip plus body in one piece), so `packet_presentation` names `housing` as its support body (the frozen value is `["lip", "body"]`). The "housing doesn't move" checks compare `housing` with `floor_world`. There are no pusher, rod or crank bodies, so the S0 contact checks against them are left out.
- The actuator `pull` acts on the slider on the same side as the stirrup, pulling +X. The scenario ramps it from 0 to +30 N over 2 s (full stroke needs about 26.8 N at 500 N/m), holds 30 N for 1 s, then releases for 0.5 s and holds 1.5 s.

Free housing:

```
uv run --frozen --extra physics cad physics run pocky/syringe --scenario projects/pocky/physics/scenarios/syringe_dispense.json --acceptance projects/pocky/physics/syringe_dispense3_acceptance.json --options projects/pocky/physics/options/syringe_dispense3.toml --out out/mujoco-syringe-dispense/run
```

Housing clamped to the table (user-declared boundary condition):

```
uv run --frozen --extra physics cad physics run pocky/syringe --scenario projects/pocky/physics/scenarios/syringe_dispense.json --acceptance projects/pocky/physics/syringe_dispense3_acceptance.json --options projects/pocky/physics/options/syringe_dispense3_clamped.toml --out out/mujoco-syringe-dispense/clamped
```

Exit codes: 0 PASS, 1 FAIL, 2 INCONCLUSIVE, 3 ERROR. Each run simulates 8 s at 62.5 us and should take about as long as the prototype dispense run (roughly 5 minutes); this is an estimate, not yet measured.

### Two-cycle dispense

Dispense packet 1, the operator pulls it out, then dispense packet 2 (`physics/scenarios/syringe_two_cycle.json`, acceptance `physics/syringe_two_cycle_acceptance.json`, 14.75 s simulated). After the first release and a 0.25 s wait, a gentle `body_force` ramps 0 to 3 N in +X on `packet` over 1 s and then holds 3 N for 1 s so the hand pulls it clear. A 1 s `settle_2` lets packet 2 drop, then the actuate, press, release and hold sequence repeats.

- Cycle 1 uses the same events and checks as the single-cycle acceptance. Cycle 2 repeats them with a `_2` suffix, numbers unchanged, over bodies `packet_02` and `packet_03` (packet 1 is gone and must not count).
- `slider_home_release` asserts the slider is within 1 mm of home at the end of `release`, before the pickup.
- The housing "doesn't move" checks run in every actuate, press, release and hold phase but not during pickup, because the hand may tug the housing.
- Dwell: `dwell_min_s` stays 0.5 s, but the dwell window is release plus hold (0.75 s) in cycle 1, so the packet must be stable from the start of release.
- Four option sets, `physics/options/syringe_two_cycle_{blade,wedge}[_clamped].toml`, select the separator and a free or clamped housing.

```
uv run --frozen --extra physics cad physics run pocky/syringe --scenario projects/pocky/physics/scenarios/syringe_two_cycle.json --acceptance projects/pocky/physics/syringe_two_cycle_acceptance.json --options projects/pocky/physics/options/syringe_two_cycle_wedge_clamped.toml --out out/mujoco-syringe-two-cycle/wedge-clamped
```

Results (`out/mujoco-two-cycle/verdict.md`): wedge clamped PASSes all 22 checks. Blade clamped FAILs: packet 2 stays perched on the blade and the slider jams at 7.5 mm in cycle 2. Both free-housing runs FAIL because the housing recoils about 9-10 mm at each release.

## Docs

- `docs/reference-notes.md`: observations from the reference dispenser.
- `docs/kinematic-diagram.png`: kinematic diagram of that reference.
- `docs/mechanism-proposal.md`: independent mechanism proposal, for review before M1.
- `docs/proposal-diagram.png`: linkage sweep drawn by `docs/proposal_sweep.py`.
- `docs/m0-report.md`: M0 gate report.
- `docs/m1_sweep.py`: Gate A pose sweep. Writes `out/pocky/linkage_motion/gate_a.json`.
- `docs/prototype_sweep.py`: the same sweep on the printed prototype. Writes `out/pocky/prototype/gate_a.json`.
- `docs/prototype_animation.py`: one ejection cycle in the OCP CAD Viewer. Writes `out/pocky/prototype/animation/simulation.json`.
- `docs/print_plate.py`: lays every `pocky/syringe` part on one Prusa XL plate and writes the PrusaSlicer project `out/pocky/syringe/syringe_plate.3mf` (XL 2T, 0.20mm STRUCTURAL, Generic PETG). Needs `prusa-slicer` on PATH.
- `docs/assembly.md`: how the printed parts go together, with renders of the STL meshes.
- `plan-first-prototype.md` (repo root): first printed prototype, and the criteria for accepting it.
- `report-current-progress.md` (repo root): what is done and what is not.

## Licence

The purchased reference meshes and video are never stored in this repo.
