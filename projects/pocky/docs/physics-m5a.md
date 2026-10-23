# S0 physics: the no-packet housing under gravity

Project-facing summary of the M5a-1 S0 increment. The full evidence report, with every
command, hash and status, is `docs/mujoco-m5a-report.md`; the plan is
`docs/mujoco-m5a-plan.md` §5.2–5.4. This page answers one question: **with no packets, does
the free housing stay where the CAD puts it?**

Short answer: **not established.** Every run is numerically invalid (peak contact penetration
0.33–0.79 mm against the 0.2 mm validity bound), and under the declared precedence an invalid
run is INCONCLUSIVE: no dynamic result from these eight cases is a physical verdict, in either
direction. What the runs show is that the body moves 4.25–4.67 mm down and rotates 2.96–3.24°
onto the pusher carriage and the rod in every case — a consistent, repeatable observation
about this model, computed on contacts that are themselves 1.7–4× past the declared penetration
tolerance. It is **not** evidence that the real housing is unretained. The *direction and repeatability* of the
motion are the part a later valid run can confirm or refute; the magnitudes are not.

## Update: valid numerics (read this first)

The statements below describe the original 2 ms-compliance runs and are kept as the historical record. A follow-up traced the invalidity to impact transients in the first 50 ms of settle and reran S0 with contact and stop time constant 0.25 ms at timestep 0.0625 ms. All eight S0 cases are then valid (peak penetration at most 0.1032 mm) and the evaluator reports FAIL, not INCONCLUSIVE: the body drops 4.4711 to 4.6600 mm and rotates 2.9598 to 3.0907 degrees. An S1 slow-press run (peak penetration 0.1290 mm) shows the body lifted about 1.1 mm and the button stalling at 59.1% of its stroke. The full account, with the convergence sweep, the code changes and a comparison with the physical prototype, is `docs/mujoco-sim-valid-report.md`.

## What was run

Eight no-packet cases through `cad physics run pocky/prototype`, all on the runtime scene at
CAD button fraction 0 (`scene_hash 2c4bd425…`), each reset → settle 3.0 s → hold 0.5 s with
zero external input:

| Case | Initial joint reset | Spring N/m | dt s |
|---|---|---|---|
| `s0_f000` … `s0_f100` | CAD fraction 0, 0.25, 0.5, 0.75, 1.0 | 500 | 0.001 |
| `s0_spring_low` / `s0_spring_high` | fraction 0 | 200 / 1000 | 0.001 |
| `s0_half_dt` | fraction 0 | 500 | 0.0005 |

The reset coordinates are the CAD helpers' values, not interpolated: the pusher moves
11.132 mm at f=0.25 and 38.868 mm at f=0.75, where a linear quarter stroke would say 12.5 and
37.5 mm. `tests/test_pocky_physics_s0.py` pins that difference at ≥1.3 mm against the 0.3 mm
slot clearance.

Sampling is `sampling_interval_s == timestep_s` in every case, so all 3501 (or 7001 at
half-dt) states of the 3.5 s are retained; nothing is downsampled and no budget overflowed.

## Preflight

Before any dynamic conclusion, the five compiled resets, critical clearances and initial
validity were re-bound from the accepted static evidence
(`out/mujoco-m5a/s0/preflight/preflight.json`): every fraction agrees with the CAD helpers to
floating-point noise (worst translation 1.39e-17 m, worst angle 1.11e-16 rad), critical
clearance passes at 0.02 mm, the initial collider penetration is
−2.6e-18 m (MuJoCo reports overlap as a negative contact distance, so this is a
floating-point-scale overlap, i.e. effectively zero) with zero exact solid overlap, and both
wrong-reset negatives are rejected (linear quarter-stroke by 1.3675 mm, sign flip by 77.7 mm). Each scenario's reset
equals the audited joint coordinates, so no scenario drifts from the audited assembly.

Budgets are derived per scenario from its own timestep. The observed worst case is 113.5
contact rows per integration state, which needs a trace budget of 28 552; the declared budgets
are 60 000 (base) and 140 000 (half-dt), giving contact caps of 960 000 and 2 240 000 against
observed maxima of 397 232 and 731 202. No run truncated or downsampled. The observed cost is
6.1–6.3 ms per 1 ms step (21–22 s per case) and 3.7 ms per 0.5 ms step (26 s), so full
retention is affordable at these sizes.

## Result

| Case | Status | Valid | pose mm | rot ° | drop mm | body-on-pusher s | body-on-rod s |
|---|---|---|---|---|---|---|---|
| s0_f000 | INCONCLUSIVE | no | 4.764 | 2.959 | 4.665 | 3.460 | 3.419 |
| s0_f025 | INCONCLUSIVE | no | 5.745 | 3.015 | 4.582 | 3.448 | 3.420 |
| s0_f050 | INCONCLUSIVE | no | 7.827 | 3.074 | 4.501 | 3.385 | 3.141 |
| s0_f075 | INCONCLUSIVE | no | 8.086 | 3.077 | 4.499 | 3.414 | 3.388 |
| s0_f100 | INCONCLUSIVE | no | 15.404 | 3.237 | 4.253 | 3.385 | 3.382 |
| s0_spring_low | INCONCLUSIVE | no | 4.769 | 2.959 | 4.664 | 3.460 | 3.422 |
| s0_spring_high | INCONCLUSIVE | no | 4.764 | 2.959 | 4.665 | 3.460 | 3.415 |
| s0_half_dt | INCONCLUSIVE | no | 4.766 | 2.959 | 4.665 | 3.461 | 3.421 |

Bounds: pose 0.20 mm, rotation 0.20°, signed drop ±0.10 mm, pair contact 0.20 s.

Read it this way:

- **The status column is the run's, and it is INCONCLUSIVE.** The per-check FAILs below are
  the evaluator's arithmetic on invalid telemetry, not product verdicts.
- `body_pose_retained` and `body_drop` exceed their bounds by 23.8–77.0× and 42.5–46.7×, and
  the body carries sustained summed force from the pusher for 3.385–3.4605 s and from the rod
  for 3.141–3.422 s of the 3.5 s. If these runs were valid, that would be the retention
  failure; they are not, so it is recorded and left open.
- All three lip pairs are 0 s, except `lip_on_rod` at 0.001 s (one sample) at f=0.25, 0.5 and
  0.75. `body_on_crank` is 0.154 s at f=0.5 and 0.156 s at f=1 (0 s elsewhere), so the crank
  does load the body at those two fractions, with up to
  3.755 N of pusher-peg-head force at f=0.5 — a sampled display-row count on an invalid scene,
  which says which contact carries load, not how much.
- Both bodies are quiescent at the end of the hold: the worst hold speed over all eight cases
  is 3.2e-5 m/s for the body (f=0.25) and 1.4e-5 m/s for the lip (spring_high), against the
  1e-3 m/s bound.
- f=1 rotates the chassis past its 0.20° bound (0.234°) while translating only 0.67 mm. Its
  FAIL is recorded; it is also under an invalid run and is not a physical verdict.

The terminal loads (f=0, state at 3.5 s) are pusher `carriage_east` 0.683 N, chassis
`guide_north` 0.510 N, rod `shaft` 0.198 N, lip `foot_n` 0.023 N. At f=1 the crank's
pusher-peg head also carries 0.041 N under the body floor. The support set is the moving parts
plus a residual chassis guide contact, as the plan predicted; the measured drop is 10.6–11.7×
and the rotation 7.4–8.1× the predicted 0.4 mm / 0.4°, on an invalid scene. The disagreement
is reported, not smoothed over, and the scene was not tuned toward the prediction.

The chassis still carries the whole group on the floor: terminal floor force is 2.7494 N in
seven of the eight cases and 2.7431 N at f=0.25 — the analytic weight of the six hanging
bodies is 2.74938 N (ratios 1.0000 and 0.9977).

## Why the status is INCONCLUSIVE and not FAIL

Peak contact penetration is 0.332–0.791 mm against the declared 0.2 mm validity bound, in
every case, at pairs that move around with the fraction (body floor vs chassis guide at f=0;
body shim vs lip foot at f=0.25; crank peg shaft vs pusher cap at f=0.5–1.0). The declared
rule is that a validity breach makes the dynamics INCONCLUSIVE, never a physical product
FAIL, and the scene was not tuned — no change to mass, friction, stiffness, damping, contact
compliance, geometry or timestep beyond the approved 0.5 ms sensitivity.

Two facts keep the conclusion useful anyway:

- The f=1 peak, 0.7909 mm, reproduces the earlier smoke value exactly.
- The approved half-timestep sensitivity *raises* the f=0 peak from 0.350 to 0.427 mm. That
  establishes one thing only: this approved halving did not resolve the validity breach.
  Numerical convergence and the root cause remain undetermined, so neither a resolution
  contribution nor its absence is established.

The direction and repeatability of the motion are consistent across all eight cases; its
exact size is not trustworthy, and no retention verdict follows from it either way.

## Replay and checkpoints

`s0_f000` replays bit-exactly from its saved verified state: full state 3501 rows with
`max_abs_diff 0.0`, post-settle continuation 501 rows with `max_abs_diff 0.0`, and no
evaluation differences (every check value, worst-sample time, metric and validity reason
recomputed identically). The replay status is INCONCLUSIVE because the source is; that is
reproduction, not a replay failure.

All eight runs saved complete checkpoints — initial row 0, post-settle row 3000 (6000 at
half-dt), terminal row 3500 (7000) — with every state finite, and the replay's own exit code 2
is retained in `out/mujoco-m5a/s0/logs/replay_s0_f000.log`. These are settled checkpoints for
the no-packet body set. Nothing was imported across runs; M5b's packet scenes have a
different body layout and will need a named shared-state import, which this increment did
not add.

## Where the evidence is

```text
out/mujoco-m5a/s0/
  freeze/freeze-record.json          # raw SHA256 of every frozen artifact + source inventory
  logs/                              # exact commands, exit codes, raw output per case
  runs/s0_*/                         # summary.json, report.md, trace.csv, contacts.csv,
                                     # states.npz, checkpoints.npz, locks, scene.xml
  replay_s0_f000/                    # replay.json + replayed_states.npz
  diagnostics/                       # per-case .md/.json, sweep.md, replay comparison
  scripts/                           # freeze_s0.py, run_s0.sh, replay_and_diagnose.sh,
                                     # make_manifests.py
  after-manifest.json                # historical pre-correction source/evidence index
```

The current index is `out/mujoco-m5a/s0-portability-repair/final-manifest.json`, written after
the portability correction's last edit. It re-hashes the historical `after-manifest.json` and
every path it lists, so the original runs, replay, freeze, checkpoints and reports are proven
byte-identical; it also hashes the current source tree and the new correction evidence. The
historical `after-manifest.json` is deliberately not rewritten: its entries for the three files
the correction edited (`tests/test_pocky_physics_s0_independent.py` and the two reports) are
expected to differ from the current tree, and nothing else should.

Regenerate any table with:

```bash
uv run --frozen python -m projects.pocky.physics.report --sweep out/mujoco-m5a/s0/runs \
  --out out/mujoco-m5a/s0/diagnostics/sweep.md
uv run --frozen python -m projects.pocky.physics.report --conformance
```

## Tests and full suite

```bash
uv run --frozen --extra physics pytest tests/test_pocky_physics_s0.py -q   # 26 passed
uv run --frozen --extra physics pytest tests/test_pocky_physics_s0_independent.py -q  # 131 passed
uv run --frozen --extra physics pytest tests -q                            # 1064 passed, 997.75 s
```

The S0 run, replay and preflight evidence under `out/` is git-ignored, so it is an **optional**
prerequisite for the independent module, not a source file. The prerequisite is both generated
trees the module reads: `out/mujoco-m5a/s0/` and `out/mujoco-m5a/adapter-static/compiled/` (the
preflight cross-checks the accepted compiled audits). In a clean checkout the module runs its
32 conformance cases (thresholds, units, CAD resets, scenario declarations, synthetic
`tmp_path` diagnostics) and skips only the 99 cases that read generated evidence, naming the
prerequisite in the skip reason.

An evidence set that exists but is partial or corrupt is a loud failure, never a skip: a
directory that is empty or incomplete, a regular file or a dangling symlink at the evidence
root, or an S0 tree without the compiled audits. `tests/test_pocky_physics_s0_portability.py`
proves each of those states by running the real module in a temporary root with `out/` controlled.
It reads each outcome and cause from a `--junitxml` report (testsuite counts and the first line of
each failure's `message`), not from substrings of captured output. In a clean checkout it is itself
3 passed, 4 skipped: `absent`, `file` and `dangling` build their own state and pass, and `partial`,
`truncated`, `missing_compiled` and `present` skip on the same prerequisite. Measured clean-checkout
totals for the independent and portability modules together: 35 passed, 103 skipped. Counts and
commands: `out/mujoco-m5a/s0-test-report-correction/report.md`.

The full suite ran once after the portability correction's final test edit: `1064 passed` in
997.75 s, log `out/mujoco-m5a/s0-portability-repair/logs/full-suite.log`. The original
increment's own run, `1045 passed` in 960.52 s, is preserved unchanged at
`out/mujoco-m5a/s0/logs/full-suite.log`. An earlier invocation failed 8 tests with
`FileNotFoundError: 'uv'` because it ran with `~/.local/bin` off `PATH`; those tests spawn
`uv` as a subprocess. It was environmental, not a regression.

## What this does not say

It says nothing about packets, stacks, the 25-capacity tube, dispensing, return-to-home under
load, or a printed part. Packet mass, wrapper and guide friction, spring rate and damping,
clip preload, wrapper flexibility, print tolerance and infill all remain unmeasured inputs
and stay INCONCLUSIVE, as the plan requires. M7 is unverified. No physical reliability claim
is made, and nothing here was committed, pushed or deployed.

## Stop boundary

This S0 increment stops at Supervisor review. Its admission was the second of three authorized
operations, and it used no remediation cycles. The scenarios, options and acceptance are frozen and byte-identical to
the freeze record; nothing was tuned after seeing a result. The next steps - investigating
the penetration model, or deciding whether the modelled margins are conclusive despite the
invalid runs - need a separate Supervisor decision, not more work inside this increment.
