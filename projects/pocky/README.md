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

## Docs

- `docs/reference-notes.md`: observations from the reference dispenser.
- `docs/kinematic-diagram.png`: kinematic diagram of that reference.
- `docs/mechanism-proposal.md`: independent mechanism proposal, for review before M1.
- `docs/proposal-diagram.png`: linkage sweep drawn by `docs/proposal_sweep.py`.
- `docs/m0-report.md`: M0 gate report.
- `docs/m1_sweep.py`: Gate A pose sweep. Writes `out/pocky/linkage_motion/gate_a.json`.
- `docs/prototype_sweep.py`: the same sweep on the printed prototype. Writes `out/pocky/prototype/gate_a.json`.
- `docs/prototype_animation.py`: one ejection cycle in the OCP CAD Viewer. Writes `out/pocky/prototype/animation/simulation.json`.
- `docs/assembly.md`: how the printed parts go together, with renders of the STL meshes.
- `plan-first-prototype.md` (repo root): first printed prototype, and the criteria for accepting it.
- `report-current-progress.md` (repo root): what is done and what is not.

## Licence

The purchased reference meshes and video are never stored in this repo.
