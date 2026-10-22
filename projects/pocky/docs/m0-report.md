# M0 report — Pocky packet dispenser

M0 is complete and stopped for review. **M1 is not authorized until the user reviews this report and the mechanism proposal.**

Plan item text is `plan-pockey-dispenser.md` §9. The reference linkage is identified, and permission to analyse the reference is recorded. The dispense axis is still an open choice, so §9's stop condition applies.

## §9 items

| Item | Result | Evidence |
|---|---|---|
| Tooling access | PASS | build123d, trimesh, pyvista and ffmpeg were checked in the previous session (build123d 0.13.0, trimesh 5.1.1, pyvista 0.49.1, ffmpeg 9.0.2). This session ran the documented `cad` commands and the test suite. |
| Project skeleton | PASS | `projects/pocky/` with params, `geometry/packet.py`, `models/packet_dummy.py`. `cad build pocky/packet_dummy --render --check --views standard` → 5 pass, 0 fail, 0 warn. |
| Kinematic diagram from the reference | PASS | `projects/pocky/docs/reference-notes.md`, `projects/pocky/docs/kinematic-diagram.png`. Pivot, slot and button are pinned there. |
| Pivot / slot / button, and the uncertainties | PASS | Reference notes, "Reconstructed linkage" and "Unresolved items". The reference channel is clearance only. Four forward stops sit within 0.6 mm. Pin engagement is about 0.3 mm. |
| Rigid packet 165 × 55 × 5.2 mm | PASS | `projects/pocky/params.toml`. Tests check the bounding box and stacks of 10 (52 mm) and 25 (130 mm). |
| Independent parameterized mechanism | PASS | `projects/pocky/docs/mechanism-proposal.md`, `proposal_sweep.py`, `proposal-diagram.png`. Linkage numbers are not in `params.toml`. |
| No vending enclosure, no extra magazines | PASS | One magazine tube. Height follows `magazine.capacity_test`. No second magazine, no electronics. |
| Stop before M1 while packet orientation is unresolved | PASS | This file. +X is recommended and not accepted. |

## Docs check (step 3)

`CLAUDE.md`, `README.md` and `MEASURING.md` match the tree. Nothing in them was rewritten.

`sed -n` on every `path:line` in `CLAUDE.md`:

| Citation | Line contents |
|---|---|
| `cadkit/project.py:38` | `class Project:` |
| `projects/armor/models/_armor_base.py:18` | `DECOR_KEEPOUT = 2.0` |
| `projects/armor/models/_armor_base.py:20` | `DECOR_EDGE_INSET = 3.0` |
| `projects/armor/params.py` lines 3–9 | The lid coordinate convention quoted in CLAUDE.md |
| `projects/armor/models/armor_industrial.py:132` | `KNURL_PITCH = 4.3` |
| `projects/armor/models/armor_neon.py:30` | `LED_STRIP_W = float(os.environ.get("NEON_LED_STRIP_W", 5.0))` |
| `projects/armor/models/armor_neon.py:41` | `DIFFUSER_ENABLED = os.environ.get("NEON_DIFFUSER", "1") != "0"` |

`CLAUDE.md` lines 160–162 are the Pocky section. They point at `projects/pocky/README.md`.

`uv run` could not reach the package index (DNS failure fetching `hatchling`), so it tried to rebuild the project and exited 2. The same `cad` entry point was run from `.venv/bin/cad`. Outputs went to `/tmp/docs-check/` with `--views standard`. Every command exited 0, and every `--check` report had 0 fail.

| Command | Exit | Check summary | Time |
|---|---:|---|---:|
| `cad list` | 0 | six models: five `armor/*`, `pocky/packet_dummy` | 2 s |
| `cad check armor/demo_cube --out /tmp/docs-check/demo_cube_check` | 0 | 7 pass, 0 fail, 0 warn | 3 s |
| `cad render armor/demo_cube --views standard --out /tmp/docs-check/demo_cube_render` | 0 | renders written | 32 s |
| `cad build pocky/packet_dummy --render --check --views standard --out /tmp/docs-check/packet_dummy` | 0 | 5 pass, 0 fail, 0 warn | 5 s |
| `cad build armor/armor_proto --render --check --views standard --out /tmp/docs-check/armor_proto` | 0 | 13 pass, 0 fail, 1 warn | 8 s |
| `cad build armor/armor_industrial --render --check --views standard --out /tmp/docs-check/armor_industrial` | 0 | 11 pass, 0 fail, 3 warn | 450 s |
| `cad build armor/armor_neon --render --check --views standard --out /tmp/docs-check/armor_neon` | 0 | 21 pass, 0 fail, 3 warn | 101 s |
| `cad build armor/fit_test --render --check --views standard --out /tmp/docs-check/fit_test` | 0 | 48 pass, 0 fail, 20 warn | 51 s |
| `NEON_DIFFUSER=0 cad build armor/armor_neon --views standard --out /tmp/docs-check/armor_neon_nodiffuser` | 0 | rear and front only; no diffuser files | 34 s |

The `cad check` and `cad render` lines are the templates in `CLAUDE.md`'s Commands section, run on `armor/demo_cube`. The builds are the concrete commands in `README.md` and `MEASURING.md`. Masses in `README.md` match these reports (proto 246.2 / 70.5 g, industrial 318.3 / 105.8 g, neon 359.2 / 83.6 / 2.7 g, coupons about 19.2–20.2 g, insert 3.5 g). The one proto `min_wall` warn and the industrial front warn at 1.20 mm are the warns CLAUDE.md already describes.

`projects/pocky/README.md` listed `mechanism-proposal.md` as "being written". That line now names the proposal and `proposal-diagram.png`.

## Tests

```
UV_NO_SYNC=1 uv run pytest tests -q
```

**212 passed** in 309 s.

A first run without `UV_NO_SYNC` was 206 passed and 6 failed. All six call `uv run cad` and failed on the same hatchling DNS error, before `cad` started. `UV_NO_SYNC=1` makes `uv run` use the environment that is already installed. With that set, those six pass.

## Mechanism proposal

Recommend **+X**: push the 55 mm end seal with a 40 mm bullnose on a carriage that translates. A straight reversing crank (included angle 180°) turns a 23.09 mm button press into 50 mm of straight pusher travel. Lateral scrub is zero. The separator stays at `separator.gap` 5.75 mm by two 0.20 mm shims on a 5.35 mm ledge. Return is a metal compression spring, about 0.30 N/mm, and the home and forward stops are both on the button rod.

The derivation, the pose table, the +Y comparison (12 mm left on the floor), and the open questions are in `mechanism-proposal.md`. The figure is `proposal-diagram.png`.

## Artifacts

| Path | What it is |
|---|---|
| `projects/pocky/docs/reference-notes.md` | Reference measurements |
| `projects/pocky/docs/kinematic-diagram.png` | Reference linkage diagram |
| `projects/pocky/docs/mechanism-proposal.md` | Proposed linkage |
| `projects/pocky/docs/proposal_sweep.py` | Analytic sweep |
| `projects/pocky/docs/proposal-diagram.png` | Proposal figure |
| `projects/pocky/docs/m0-report.md` | This file |
| `projects/pocky/params.toml` | Unchanged packet, magazine, separator, wall |
| `projects/pocky/geometry/packet.py` | Rigid packet and stack |
| `projects/pocky/models/packet_dummy.py` | Printable envelope |
| `/tmp/docs-check/` | This session's doc-check builds |

## Unresolved

- **Dispense axis.** +X is the recommendation. It depends on the sticks lying along the 165 mm length. Not confirmed.
- **Separator gap.** 5.75 mm is the default shim setting. Real thickness, and thickness under a stack, is unmeasured.
- **Scrub.** The proposal removes sideways scrub by sliding the face. Whether a 40 mm bullnose is kind to the end seal is untested.
- **Packet thickness distribution and seal width.** Centre, end seals, fin length, and which edge is the fin are unmeasured.
- Button offset (y = −28, about 40 mm stick-out at rest), presentation length (40 mm), shim stock, and the spring's catalog part.

## Loose ends, left as they are

- Old output directories `out/armor_industrial`, `out/armor_neon`, `out/armor_proto`, `out/demo_cube` and `out/fit_test` still sit beside `out/armor/`.
- `magazine.capacity_test` loads as a float, because the shared override coerces to float.
- `test_cli_check_set_reflected` treats `"150"` as a substring of the report detail.
- The baseline snapshots named in the handoff (`/tmp/cadstudio-baseline`, `/tmp/cadstudio-base-out1`) are not on disk.

## Stop

M1 is not authorized. No magazine, crank, or separator solid was modelled.
