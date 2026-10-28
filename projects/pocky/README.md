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
uv run cad build pocky/syringe3 --render --check --views standard
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
| `syringe3.exit_gap` | 7.8 | Syringe3 exit window height, 1.5x the packet (`syringe` keeps `separator.gap`) |
| `syringe3.bore_length` | 176.0 | Syringe3 bore along X (x −91 to 85); 6 mm over `magazine.length_i`, grown at the back for the 8 mm rear ramp (`syringe` keeps `magazine.length_i`) |
| `syringe3.target_protrusion` | 75.0 | Presented packet's leading edge past the exit wall at full stroke (57 mm past the shelf) |
| `syringe3.min_protrusion` | 65.0 | Minimum protrusion (sets the minimum stroke) |
| `syringe3.min_past_shelf` | 47.0 | Leading edge must clear the shelf end by this much |
| `syringe3.plate_z0` | 0.2 | Pusher plate underside above the floor top |
| `syringe3.plate_h` | 4.7 | Pusher plate thickness (top 4.9, 0.3 under packet 2) |
| `syringe3.slot_h` | 5.2 | Rear wall slot height the plate runs in (and the rear ramp's underside) |
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

## syringe3 (next prototype)

`pocky/syringe3` (`geometry/syringe3.py`, `models/syringe3.py`) fixes four bench problems. Values are from `params.toml` `[syringe3]` and the geometry docstring.

- Exit gap 7.8 mm (`syringe3.exit_gap`, 1.5x the packet): one 5.2 mm packet passes, two (10.4 mm) do not. The wedge separator replaces the blade, with 60 deg lead-ins (`WEDGE_LEAD_IN_DEG`) so a packet landing off-centre rests on a slope, not a ledge.
- Protrusion 75 mm (`target_protrusion`; `min_protrusion` 65, stroke 85 mm) with a return spring of 200 N/m: 42 beams, 7.5 mm tall, 10 mm preload, 19.0 N at full stroke.
- Bore 176 mm (`bore_length`), lengthened 6 mm at the back, so the exit and the protrusion do not move. The rear-wall ramp is 8 mm deep at 35 deg from vertical (`RAMP_DEG`), its toe at x = −83 (0.5 mm behind a centred packet) and its face up to z = 19. At home the pusher plate face sits at x = −87, mid-way between the toe and the rear wall's inner face, 4 mm from each (`PLATE_WINDOW_MARGIN` requires at least 3). It meets a centred packet after 4.5 mm.
- Pusher plate z 0.2 to 4.9 mm (`plate_z0` 0.2, `plate_h` 4.7), with an undercut lip: a 1.3 mm land, then 15 deg back to 0.6 mm behind the face, so a soft packet end is caught under it.
- Pickup: `body_force` on `packet` ramps 0 to 1.0 N in +X over 1 s with `damping_n_s_m` 2.0; `remove_body` takes packet 1 out at the start of `settle_2`.
- Assembly: the slider goes on from behind. The spring slides in from the open rear end, then the slider is pushed forward onto the rails (`geometry/syringe3.py` assembly steps 2-3). It cannot be dropped on from above.
- Backstop clips (`clip_n`, `clip_s`), fitted last (assembly step 5): each snaps into a slab socket with the housing legs' split pin, and its plate stands 0.05 mm behind the slider leg at home (x 63.95 to 83.95). Pushing the handle back stops the legs on the clips, so the plate cannot leave the rear slot. The grooves' closed ends on the rails' front ends are the backup stop, 0.5 mm further back. The plate also sits 0.35 mm outside the arm, so an arm spreads 0.35 mm before it touches, against the 1.65 mm that unhooks it from its V rail. A flat screwdriver in the pry notch levers a clip off, and only then can the slider come off backwards. When the handle is let go from full stroke, the slider hits the clips at about 3 m/s, so check the clips for wear or cracking on the bench.
- Assembly step 5: fit the clips last, with the slider home. To remove them, slide a flat screwdriver into the pry notch and lever each clip off; only then can the slider come off.
- One clip per side guards the arm near the home stop. If the bench shows the arm bowing out mid-span, a second clip at about x −55 is the fix.

Two-cycle runs, free and clamped housing:

```
uv run --frozen --extra physics cad physics run pocky/syringe3 --scenario projects/pocky/physics/scenarios/syringe3_two_cycle.json --acceptance projects/pocky/physics/syringe3_two_cycle_acceptance.json --options projects/pocky/physics/options/syringe3_two_cycle.toml --out out/mujoco-syringe3-two-cycle/free
uv run --frozen --extra physics cad physics run pocky/syringe3 --scenario projects/pocky/physics/scenarios/syringe3_two_cycle.json --acceptance projects/pocky/physics/syringe3_two_cycle_acceptance.json --options projects/pocky/physics/options/syringe3_two_cycle_clamped.toml --out out/mujoco-syringe3-two-cycle/clamped
```

Exit codes: 0 PASS, 1 FAIL, 2 INCONCLUSIVE, 3 ERROR.

Push-back: after a 2 s settle the pull actuator ramps to −30 N over 1 s (the handle pushed back), holds 1 s, releases and holds. The slider must stay within 0.5 mm of home, held by the legs on the backstop clips, and the plate must stay in the slot. Run it with the housing clamped: a free housing's contacts with its slider are filtered, so the joint's 0.5 mm guard is the stop instead.

```
uv run --frozen --extra physics cad physics run pocky/syringe3 --scenario projects/pocky/physics/scenarios/syringe3_push_back.json --acceptance projects/pocky/physics/syringe3_push_back_acceptance.json --options projects/pocky/physics/options/syringe3_two_cycle_clamped.toml --out out/mujoco-syringe3-push-back/clamped
```

Plate: `uv run --frozen python projects/pocky/docs/print_plate.py --model syringe3` writes `out/pocky/syringe3/syringe3_plate.3mf` (needs `prusa-slicer`). The footprint is 286.4 x 318.0 mm on the 360 mm bed (10 parts, four rows).

Reprint from `syringe`: only the `handle` is unchanged (identical geometry), so `--skip handle` writes `out/pocky/syringe3/syringe3_plate_without_handle.3mf` with the other 9 parts. The feet are 2.3 mm shorter than the syringe's because the slab is deeper.

Results (2026-10-27, `out/mujoco-syringe3/`): `v6-clamped` PASSes all 22 checks with the 176 mm bore, 8 mm ramp and front backstop clips (peak penetration 0.16 mm, bound 0.2). Packet 2 drops flat in front of the pusher and dispenses to 75 mm past the exit in cycle 2; the pickup stays hand speed. `push-back2-clamped` PASSes all 19 checks: a 30 N push on the handle stops the slider 0.05 mm behind home, on the clips. With the housing free, the housing still recoils at each release and drags packets out. That is accepted; the clamped run is the declared boundary condition.

## Docs

- `docs/reference-notes.md`: observations from the reference dispenser.
- `docs/kinematic-diagram.png`: kinematic diagram of that reference.
- `docs/mechanism-proposal.md`: independent mechanism proposal, for review before M1.
- `docs/proposal-diagram.png`: linkage sweep drawn by `docs/proposal_sweep.py`.
- `docs/m0-report.md`: M0 gate report.
- `docs/m1_sweep.py`: Gate A pose sweep. Writes `out/pocky/linkage_motion/gate_a.json`.
- `docs/prototype_sweep.py`: the same sweep on the printed prototype. Writes `out/pocky/prototype/gate_a.json`.
- `docs/prototype_animation.py`: one ejection cycle in the OCP CAD Viewer. Writes `out/pocky/prototype/animation/simulation.json`.
- `docs/print_plate.py`: lays every `pocky/syringe` part (or `--model syringe3`) on one Prusa XL plate and writes the PrusaSlicer project `out/pocky/<model>/<model>_plate.3mf` (XL 2T, 0.20mm STRUCTURAL, Generic PETG). Needs `prusa-slicer` on PATH.
- `docs/assembly.md`: how the printed parts go together, with renders of the STL meshes.
- `plan-first-prototype.md` (repo root): first printed prototype, and the criteria for accepting it.
- `report-current-progress.md` (repo root): what is done and what is not.

## Licence

The purchased reference meshes and video are never stored in this repo.
