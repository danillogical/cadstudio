# M5a-1: S0 scenarios, evidence and checkpoints

Bounded increment executed as the OMP Turn Orchestrator under Supervisor decision
`CONTINUE dec_0mvk29rpu8c8d76e08aa67af9` (successor7 `run_0mvjxlcc2e0e8c3a94941d366`),
after acceptance of the original adapter/static operation
`op_0mvjxlsbw7236ba3c1b344c3f`. This report covers **S0 only**. It is not M5a-1
completion, not packet readiness, not M6/M7 and not a physical product claim.

**Headline:** all eight no-packet S0 cases ran and completed every phase with
`sampling_interval_s == timestep_s`, and **every case is numerically INVALID** (peak
penetration 0.33–0.79 mm against the 0.2 mm validity bound). Under the evaluator's
declared precedence a validity breach makes the **run INCONCLUSIVE**, so **no S0 dynamic
result — PASS or FAIL — is a physical product verdict**, and that includes the recorded
per-check FAILs on `body_pose_retained`, `body_drop`, `body_on_pusher` and `body_on_rod`
in every case and on `chassis_grounded` at f=1. Those FAILs are what the bound evaluator
computed from the telemetry; they are **not** established conclusions about the hardware.
What the runs do establish is narrower and still useful: the contact pattern is
qualitatively consistent with the pre-run prediction (the housing settles onto moving
parts) and the measured magnitudes (drop 4.25–4.67 mm, rotation 2.96–3.24°) disagree with
the predicted 0.4 mm / 0.4° by an order of magnitude, on a scene whose contacts are 1.7–4×
past the declared penetration tolerance. Whether the housing is retained is **not
established** by this increment.

## 1. Scope executed

| Item | Value |
|---|---|
| Increment | M5a-1 §6.1 step 3: S0 scenarios, acceptance, diagnostics, runs, replay, checkpoints |
| Scenarios | 8 no-packet cases: f = 0, 0.25, 0.5, 0.75, 1.0; spring 200/1000 N/m; dt 0.5 ms |
| Runtime scene | CAD button fraction 0, zero packets, one scene (`scene_hash 2c4bd425…`) |
| Phases | reset → settle **3.0 s** → hold **0.5 s**, zero external input throughout |
| Sampling | `sampling_interval_s == timestep_s` explicitly in every scenario |
| Acceptance | `projects/pocky/physics/s0_acceptance.json`, frozen before the first run |
| Evidence root | `out/mujoco-m5a/s0/` |
| Limits | 3 operations / 2 remediation cycles / deadline `1792711542961`; this admission is operation 2 of 3 and cumulative submission 29. No renewal, no further operation, no self-admission. |

Not done, by packet: P0–P3, packets, the 25-capacity tube, loaded-settle or shared-state
import, M6/M7, CAD redesign, commit/push/deploy, physical reliability claims.

## 2. Commands (exact, with exit codes)

Every case ran through the accepted project CLI; the drivers are
`out/mujoco-m5a/s0/scripts/{preflight_s0.py,freeze_s0.py,run_s0.sh,replay_and_diagnose.sh,make_manifests.py}`.

```bash
UV=/Users/daniel_l_newman/.local/bin/uv
# 0. Preflight: bind the accepted compiled audits and derive the budgets
$UV run --frozen python out/mujoco-m5a/s0/scripts/preflight_s0.py --write
$UV run --frozen python out/mujoco-m5a/s0/scripts/preflight_s0.py --verify

# 1. Freeze scenarios + options + acceptance, then verify the freeze is reproducible
$UV run --frozen --extra physics python out/mujoco-m5a/s0/scripts/freeze_s0.py --write
$UV run --frozen --extra physics python out/mujoco-m5a/s0/scripts/freeze_s0.py --verify

# 2. Eight S0 cases (base cases pass no --options: canonical empty lock)
$UV run --frozen --extra physics cad physics run pocky/prototype \
  --scenario projects/pocky/physics/scenarios/s0_f000.json \
  --acceptance projects/pocky/physics/s0_acceptance.json \
  --out out/mujoco-m5a/s0/runs/s0_f000
# … f025, f050, f075, f100 the same; then the two spring cases and half-dt with
# --options projects/pocky/physics/options/s0_{spring_low,spring_high,half_dt}.toml

# 3. Replay S0 f=0 from its saved verified state
$UV run --frozen --extra physics cad physics replay out/mujoco-m5a/s0/runs/s0_f000 \
  --out out/mujoco-m5a/s0/replay_s0_f000

# 4. Diagnostics, sweep, replay comparison, conformance
$UV run --frozen python -m projects.pocky.physics.report --run <run> --out <md> --json-out <json>
$UV run --frozen python -m projects.pocky.physics.report --sweep out/mujoco-m5a/s0/runs \
  --out out/mujoco-m5a/s0/diagnostics/sweep.md --json-out out/mujoco-m5a/s0/diagnostics/sweep.json
$UV run --frozen python -m projects.pocky.physics.report --run out/mujoco-m5a/s0/runs/s0_f000 \
  --compare out/mujoco-m5a/s0/replay_s0_f000 --out out/mujoco-m5a/s0/diagnostics/replay_s0_f000.md
$UV run --frozen python -m projects.pocky.physics.report --conformance
```

Exit codes (`out/mujoco-m5a/s0/logs/`):

| step | exit | meaning |
|---|---|---|
| `preflight_s0.py --verify` | 0 | compiled audits bound, budgets derived, no drift |
| `preflight_s0.py --write` | 0 | record written; `--verify` then reproduces it exactly |
| eight `cad physics run` cases | **2** each | INCONCLUSIVE (validity breach), not ERROR |
| `freeze_s0.py --write` / `--verify` | 0 / 0 | frozen artifacts written; verification found no drift |
| `cad physics replay` s0_f000 | **2** | source INCONCLUSIVE reproduced (see the note below) |
| per-case diagnostics, sweep, comparison, conformance | 0 | diagnostics are read-only views |

`2` is the declared exit code for INCONCLUSIVE. No run returned ERROR or SCENE_INVALID.

**Retained replay exit code.** An earlier invocation of `replay_and_diagnose.sh` overwrote
the replay log with `exit: 0 (skipped, existing replay kept)` because the replay directory
already existed, so for a time the retained log did not show the replay's own exit code. The
script now preserves the original log and writes any later skip to
`logs/replay_s0_f000.skipped.txt`; the replay was re-executed into a fresh directory and the
whole evidence chain regenerated. `logs/replay_s0_f000.log` now contains the replay command,
its output and `exit: 2`, and `logs/evidence-exit-codes.txt` records `replay_s0_f000 2`.

## 3. Preflight: compiled resets, clearances, initial validity and budgets

`out/mujoco-m5a/s0/preflight/preflight.json` (driver `scripts/preflight_s0.py`, `--verify`
exits 0) binds the **accepted** compiled audits and derives the run budgets. It re-hashes
`reset_audit.json`, `negative_resets.json`, `clearance_audit.json` and `validity.json` under
`out/mujoco-m5a/adapter-static/compiled/` rather than re-deriving them, and then cross-checks
each frozen S0 scenario's reset against the audited coordinates.

| Fraction | worst translation error (m) | worst angular error (rad) | sign | initial collider penetration / exact overlap |
|---|---|---|---|---|
| 0.00 | 0.0 | 0.0 | ok | −2.6e-18 m / 0.0 mm³ |
| 0.25 | 1.39e-17 | 0.0 | ok | −2.6e-18 m / 0.0 mm³ |
| 0.50 | 1.39e-17 | 0.0 | ok | −2.6e-18 m / 0.0 mm³ |
| 0.75 | 1.39e-17 | 1.11e-16 | ok | −2.6e-18 m / 0.0 mm³ |
| 1.00 | 1.39e-17 | 0.0 | ok | −2.6e-18 m / 0.0 mm³ |

The two units are kept apart: maximising a metre-valued and a radian-valued error into one
number would produce a figure with no unit. The angular value at f=0.75 is 1.11e-16 **rad**,
not metres.

The validity column is the audit's `worst_m`, which is the lowest MuJoCo contact `dist`
starting from 0 (`clearance_audit.py:276-296`); MuJoCo reports overlap as a negative
distance, so **negative means overlapping**. The audit only lists a pair when
`dist < −1e-6 m` (`PENETRATION_TOL_M`, `clearance_audit.py:50`), so −2.6e-18 m is a
floating-point-scale overlap — effectively zero contact, not a measurable penetration and not
a gap. The eight runs report the same contact as `initial_penetration_m` **+2.6e-18 m**
because the runner takes `max(0, −dist)`
(`cadkit/physics/telemetry.py:994`) — the same magnitude, opposite sign convention. Exact
solid overlap is 0.0 mm³ at every fraction, so the initial state is valid by the audit's own
0.001 mm³ noise threshold and no pair reaches its 1e-6 m penetration tolerance.

Critical clearance passes at 0.02 mm on all five fractions. Both wrong-reset negatives are
rejected: the linear quarter-stroke pusher by **1.36750 mm** (required ≥1.367 mm) and the sign
flip by up to **77.735 mm** (fields `min_pusher_error_mm` / `required_min_mm` /
`max_pusher_error_mm`, converted from the audit's metres and renamed so no millimetre value
carries an `_m` suffix). Every scenario's reset equals the audited joint coordinates
(`scenarios_match_audit: true`).

Budgets are derived, not copied. Each scenario is recomputed from its own dt: 3500 steps and
3501 rows at 1 ms, 7000/7001 at 0.5 ms; declared trace budgets are 60 000 and 140 000, so the
runner's contact cap (`max_trace_rows × 16`, `cadkit/physics/runner.py:958`) is 960 000 and
2 240 000. The observed worst case is **113.5 contact rows per integration state**, which
would need a trace budget of 28 552 (57 094 at half-dt) — well under the declared 60 000 /
140 000, with the largest actual contact count 397 232 (731 202 at half-dt) inside its cap.

Observed cost, from each run's own `runtime_wall_s` (whole CLI run, including export and
archive writes): 6.08–6.28 ms per integration step at 1 ms and 3.72 ms at 0.5 ms, i.e. 21.3–22.0 s
per 3500-step case and 26.0 s for the 7000-step half-dt case. That rate is why the budgets are
sized for full retention rather than sampling.

## 4. Frozen artifacts and their hashes

Frozen before the first S0 run; `freeze_s0.py --verify` recomputes every document from the
CAD helpers and re-hashes it (exit 0, no drift). Full inventory:
`out/mujoco-m5a/s0/freeze/freeze-record.json`, which records `frozen_utc`
`2026-10-22T21:57:24.893380+00:00`, `first_s0_run_utc` `2026-10-22T21:59:59.306148+00:00`,
`recorded_before_first_s0_run: true` derived from those two timestamps, and the two
pre-freeze exploratory probe runs it did not cover (`probe_runs`).

| Artifact | raw SHA256 |
|---|---|
| `projects/pocky/physics/s0_acceptance.json` | `150c037b2e985dac46b66670c46291872d9e0cc9d287d7946eadf4d9185b5a3a` |
| acceptance semantic hash (`spec.hash()`, run lock) | `9ff3e969ec0d518c7e77163ea4ded2eb9459f8b2c97c4e5ada455f8daa137ece` |
| `scenarios/s0_f000.json` | `b263c204cf9313c98aba3e2c958481941265df15606041099698232e2bd029c2` |
| `scenarios/s0_f025.json` | `c1f181e5f259877eb620e1ffdad2a95814bf489af1f3e3cd5551a44372874b6b` |
| `scenarios/s0_f050.json` | `0af599b35783f75f292f32ea2cd3e1a578c2a088269a4503c1692aa5db7023df` |
| `scenarios/s0_f075.json` | `a75e80163d7f5bb9536f254a7e81d861bc72abcf8da37d97ea754fc8a795e42e` |
| `scenarios/s0_f100.json` | `4530c80b681b53ca199c35189dc0d5dce7c05b0df43bca45501b198982bf24a7` |
| `scenarios/s0_spring_low.json` | `648d2a1e252bdb47a4b51362b73f18e27b1ef66c6b8474bc241b61d9158ba4d8` |
| `scenarios/s0_spring_high.json` | `f7f3f54aefd0f39bb5389e6d93ad9a388e700dce42186dd28d89cdfe84bcc565` |
| `scenarios/s0_half_dt.json` | `a6fe8edce50a93d4d3fefa941c979659049b8950c6b154868ae3695ca66991b2` |
| `options/s0_spring_low.toml` | `be62228065455d001011568a1b09df4d4ccdb82439be58b98c83716a58b8a18f` |
| `options/s0_spring_high.toml` | `2d7af6281c846b80482c369d905bb5ccddab58aa87dc45ffe0a92b50b5715ed8` |
| `options/s0_half_dt.toml` | `0bec909c9854462896d206193f869155117f609d5c97bfc295aab1ee7829d74a` |
| frozen presentation `acceptance.toml` (unchanged) | `518a45ffc4592ca602be4c33c59681038e43dedaa15b688312202c3a57ff6ca2` |
| scene XML (unchanged, base cases) | `997a20b79566bfc5452e334b98f149c292056312795ce85f763308d430a22a15` |
| baseline scene identity | `2c4bd425c55d9f56c39904e6ae01683836650fc84dabaa6ff645eb1077926e2f` |

Every value above is `shasum -a 256` of the file as it exists on disk, and each one equals
the corresponding `acceptance.lock.json`/`scenario.json` lock inside the eight run
directories and the `freeze-record.json` inventory — a cross-check a reader can repeat with
`shasum -a 256 projects/pocky/physics/s0_acceptance.json`. `spec.hash()` is a different,
semantic hash of the parsed document and is listed separately so the two are never confused.

`freeze_s0.py --write` was run a second time (after the eight runs) to regenerate the record
with derived chronology. It rewrote the frozen scenario/options/acceptance files
byte-for-byte identically — every run's `scenario.json` and `acceptance.lock.json` still equal
the current files — so no run was produced against a different document than the one now on
disk. `freeze_s0.py --verify` exits 0 after the rewrite.

`conformance_report()` (`--conformance`, exit 0) validates the frozen acceptance against the
plan's own numbers rather than against itself: 0.20 mm / 0.20° pose, ±0.10 mm signed world-z
with `body_a=chassis, body_b=body` ordering, six 0.0715 N / 0.20 s contacts with
`window=end` and no phase fields, 1 mm / 0.20° chassis, 1 mm/s body and lip, 0.2 mm
penetration and validity, 20% near band. Each of those is mutation-tested in
`tests/test_pocky_physics_s0.py`.

The three sensitivity cases legitimately change the scene identity, because the declared
input changes:

| Case | spring N/m | dt s | scene hash | XML SHA256 | options SHA256 |
|---|---|---|---|---|---|
| base (5 cases) | 500 | 0.001 | `2c4bd425c55d…` | `997a20b79566…` | `b3f4a4db51e7…` (`# assembly options: none`) |
| spring_low | 200 | 0.001 | `c53a22c65866…` | `99f9a2e71bea…` | `be6222806545…` |
| spring_high | 1000 | 0.001 | `017203d85f6e…` | `acfbb8a8452a…` | `2d7af6281c84…` |
| half_dt | 500 | 0.0005 | `1a36409d1a43…` | `e16e06717f91…` | `0bec909c9854…` |

Contact and stop compliance stayed 0.002 s effective in all eight runs (declared 0.002 s,
`refsafe_floor_s` 0.002 s at base and 0.001 s at half-dt); friction, priority, masses, seed,
gravity, solver and integrator are identical, and the only `physical_inputs` difference
between base and half-dt is `timestep_s`.

## 5. Per-case results

Statuses are the bound generic evaluator's, copied unchanged.

| Case | Status | Valid | peak pen. mm | pose mm | rot ° | signed dz mm | body-on-pusher s | body-on-rod s |
|---|---|---|---|---|---|---|---|---|
| s0_f000 | INCONCLUSIVE | no | 0.350 | 4.764 | 2.959 | −4.665 | 3.460 | 3.419 |
| s0_f025 | INCONCLUSIVE | no | 0.447 | 5.745 | 3.015 | −4.582 | 3.448 | 3.420 |
| s0_f050 | INCONCLUSIVE | no | 0.592 | 7.827 | 3.074 | −4.501 | 3.385 | 3.141 |
| s0_f075 | INCONCLUSIVE | no | 0.639 | 8.086 | 3.077 | −4.499 | 3.414 | 3.388 |
| s0_f100 | INCONCLUSIVE | no | 0.791 | 15.404 | 3.237 | −4.253 | 3.385 | 3.382 |
| s0_spring_low | INCONCLUSIVE | no | 0.406 | 4.769 | 2.959 | −4.664 | 3.460 | 3.422 |
| s0_spring_high | INCONCLUSIVE | no | 0.332 | 4.764 | 2.959 | −4.665 | 3.460 | 3.415 |
| s0_half_dt | INCONCLUSIVE | no | 0.427 | 4.766 | 2.959 | −4.665 | 3.461 | 3.421 |

Check matrix (`out/mujoco-m5a/s0/diagnostics/sweep.md`):

| check | f000 | f025 | f050 | f075 | f100 | spring_low | spring_high | half_dt |
|---|---|---|---|---|---|---|---|---|
| body_pose_retained | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL |
| body_drop | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL |
| body_on_pusher | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL |
| body_on_rod | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL |
| body_on_crank | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| lip_on_pusher | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| lip_on_rod | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| lip_on_crank | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| chassis_grounded | PASS | PASS | PASS | PASS | **FAIL** | PASS | PASS | PASS |
| settled_body | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| settled_lip | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| penetration | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL |

### 5.1 How to read the per-check statuses under invalidity

The evaluator computes every check from the telemetry and then applies precedence: a validity
breach makes the **run** INCONCLUSIVE while the individual check statuses keep the values
they were evaluated to (`cadkit/physics/evaluate.py:854-899`). So the FAIL/PASS column above
is the evaluator's own arithmetic, not a verdict:

- `body_pose_retained` (4.76–15.40 mm against 0.20 mm, 23.8–77.0× the bound),
  `body_drop` (−4.25…−4.67 mm against ±0.10 mm, 42.5–46.7×) and the body-on-pusher /
  body-on-rod durations (3.385–3.4605 s and 3.141–3.422 s against 0.20 s, 15.7–17.3×) are the
  checks that would carry the "housing not retained" claim **if the run were valid**. They are not: the same
  runs breach the penetration bound by 1.7–4×, so that claim is **INCONCLUSIVE**, not a
  physical product FAIL.
- `settled_body` (worst over the eight cases 3.2e-5 m/s at f=0.25), `settled_lip` (worst
  1.4e-5 m/s) and the lip pair durations (0 s, except `lip_on_rod` at 0.001 s at f=0.25, 0.5
  and 0.75 — one sample) are PASS against their bounds. A PASS under an invalid run is
  equally not a product statement.
- `chassis_grounded` at f=1 rotates 0.0041 rad (0.234°) against the 0.20° bound while
  translating only 0.67 mm. Its FAIL is likewise recorded, and likewise INCONCLUSIVE as a
  physical claim. It is not hidden behind the validity breach either.
- The near-threshold band was never entered: no check in any of the eight runs carries
  `near_threshold: true` (checked for all 12 checks × 8 cases), so no status is a
  near-threshold artifact. Note that a *failing* check is never in the band by construction —
  the band only demotes a passing value that is close to its bound.

### 5.2 Why the dynamics are INCONCLUSIVE

Every case breaches `max_penetration_m = 0.0002` m. The peaks are 0.332–0.791 mm and the
worst pairs are, per case:

| Case | peak penetration pair | mm |
|---|---|---|
| s0_f000 | body `floor_front` vs chassis `guide_north` | 0.350 |
| s0_f025 | body `shim_04_a` vs lip `foot_n` | 0.447 |
| s0_f050 | crank `peg_pusher_shaft` vs pusher `pusher_cap_n_06` | 0.592 |
| s0_f075 | crank `peg_pusher_shaft` vs pusher `pusher_cap_n_06` | 0.639 |
| s0_f100 | crank `peg_pusher_shaft` vs pusher `pusher_cap_n_06` | 0.791 |
| s0_spring_low | body `floor_front` vs chassis `guide_north` | 0.406 |
| s0_spring_high | body `shim_04_a` vs lip `foot_n` | 0.332 |
| s0_half_dt | body `shim_04_a` vs lip `foot_n` | 0.427 |

The f=1 peak of 0.7909 mm matches the earlier smoke value (0.7909 mm) exactly. The approved
half-timestep sensitivity (`s0_half_dt`, 0.5 ms) *raises* the f=0 peak from 0.350 mm to
0.427 mm. That is the whole observation: this one approved halving did not resolve the
validity breach. Two timestep values do not establish convergence, so they neither show nor
exclude a timestep-resolution contribution, and the cause of the breach remains undetermined.
At 0.2 mm the bound is the declared numerical validity threshold, and these contacts exceed it
by 1.7–4×. Consequences, stated honestly:

- The **direction and repeatability** of the motion is consistent across all eight cases: the
  body moves down 4.25–4.67 mm in every one of them, with the same qualitative support set
  (pusher carriage, rod, residual chassis guide). That consistency is an observation about
  the model, not a validated physical measurement.
- The **magnitudes** (pose translation, rotation, contact durations) are computed on a scene
  whose contacts are 1.7–4× past the declared penetration tolerance. They are reported as
  diagnostics and **not** as quantitatively trustworthy physics, and they are not used here
  to assert either retention or non-retention. The plan's rule applies: invalid dynamics are
  INCONCLUSIVE, never a physical product FAIL.
- The near band was never entered: no check in any case carries a near-threshold flag, so no
  status change is attributable to near-threshold behaviour. (The band can only demote a
  *passing* value; these runs fail their structural checks outright.)

### 5.3 Observed support versus the historical prediction

The pre-run prediction (`docs/mujoco-m5a-plan.md` §5.4) was: no downward chassis seat, a
0.4 mm drop onto the pusher carriage, sustained body-on-moving-part contact, and
`body_drop`/`body_on_pusher` FAIL. Observed:

| Prediction | Observed |
|---|---|
| drop ≈ 0.4 mm | **4.25–4.67 mm** (10.6–11.7× larger) |
| body-on-moving-part contact | **observed**: 3.385–3.4605 s of body-on-pusher, 3.141–3.422 s of body-on-rod |
| `body_drop` / `body_on_pusher` FAIL | **computed FAIL, but INCONCLUSIVE as a physical claim** (validity breach) |
| rotation ≈ 0.4° | **2.96–3.24°** (7.4–8.1× larger) |

The loads at the end of the hold (f=0, terminal state 3.5 s, normal forces) are pusher
`carriage_east` 0.683 N, chassis `guide_north` 0.510 N, rod `shaft` 0.198 N, lip `foot_n`
0.023 N. At f=1: pusher `carriage_east` 0.744 N, rod `shaft` 0.394 N, chassis `guide_north`
0.253 N, crank `peg_pusher_head` 0.041 N. The support set is the moving parts plus a residual
chassis guide contact — the same mechanism the plan predicted — but on an invalid scene, so
the split of load between those contacts is diagnostic. The scene was **not** tuned to
reproduce 0.4 mm/0.4°: the observed values stand as computed, and the disagreement with the
prediction is reported rather than resolved.

The chassis floor load tells the same story from the other side: terminal floor force is
2.7494 N in seven of the eight cases and 2.7431 N at f=0.25 (ratios 1.0000 and 0.9977 of the
analytic weight of the six hanging bodies, 2.74938 N), so the chassis still carries the whole
group on the floor while the housing has settled onto the mechanism. Peak floor force is
19.8–27.0 N during the settle transient.

### 5.4 Peg-head and lip-rail arrests

Reported separately from drive contacts, because a peg inside its own slot is the normal
drive path and only a peg loading the *housing* is an arrest:

| Case | peg_pusher → housing peak N (rows) | peg_pusher drive peak N | peg_button → housing | lip_rail peak N |
|---|---|---|---|---|
| s0_f000 | 0 (0) | 0.070 | 0 | 0.422 |
| s0_f025 | 0 (0) | 0.827 | 0 | 0.221 |
| s0_f050 | **3.755** (3457) | 0.860 | 0 | 0.619 |
| s0_f075 | 0.027 (833) | 1.034 | 0 | 0.137 |
| s0_f100 | **1.338** (6782) | 1.891 | 0 | 0.269 |
| s0_spring_low | 0 (0) | 0.073 | 0 | 0.426 |
| s0_spring_high | 0 (0) | 0.072 | 0 | 0.429 |
| s0_half_dt | 0 (0) | 0.071 | 0 | 0.375 |

At f=0.5 and f=1.0 the pusher-peg head reaches the body floor (3.755 N over 3457 sampled
states at f=0.5, 1.338 N over 6782 at f=1.0); at f=0.75 it grazes it (0.027 N over 833
states), and at f=0, the spring cases and half-dt it does not reach the housing at all. The
button peg never loads the housing. The lip teeth carry 0.14–0.62 N against the body in every
case — small, but non-zero. All of these are display-row (sampled) counts on an invalid
scene, so they identify *which* contact is loading, not how much.

## 6. Coverage, checkpoints and replay

Every case retained every integration sample for the whole 3.5 s:

| Case | dt s | trace rows | state rows | contact rows | checkpoints (initial / post-settle / terminal) |
|---|---|---|---|---|---|
| s0_f000 | 0.001 | 3501 | 3501 | 365 518 | 0 / 3000 / 3500 |
| s0_f025 | 0.001 | 3501 | 3501 | 366 283 | 0 / 3000 / 3500 |
| s0_f050 | 0.001 | 3501 | 3501 | 383 144 | 0 / 3000 / 3500 |
| s0_f075 | 0.001 | 3501 | 3501 | 379 916 | 0 / 3000 / 3500 |
| s0_f100 | 0.001 | 3501 | 3501 | 397 232 | 0 / 3000 / 3500 |
| s0_spring_low | 0.001 | 3501 | 3501 | 364 865 | 0 / 3000 / 3500 |
| s0_spring_high | 0.001 | 3501 | 3501 | 366 565 | 0 / 3000 / 3500 |
| s0_half_dt | 0.0005 | 7001 | 7001 | 731 202 | 0 / 6000 / 7000 |

No budget overflow, no solver warning (`inertia`, `contactfull`, `cnstrfull`, `badqpos`,
`badqvel`, `badqacc`, `badctrl` all zero), `initial_rejected: false` in every case, and
`initial_penetration_m` 2.6e-18 m (floating-point zero). All three checkpoints are finite and complete in all eight
cases, so these **are** settled checkpoints (post-settle row 3000 / 6000, terminal row 3500 /
7000). They are complete for M5b's use with the same body layout; no shared-state import was
attempted or claimed.

Replay of s0_f000 (`out/mujoco-m5a/s0/replay_s0_f000/replay.json`):

| comparison | result |
|---|---|
| full state, 3501 rows | ok, max abs diff **0.0** |
| post-settle continuation, 501 rows | ok, max abs diff **0.0** |
| evaluation comparison (every check value, worst-sample time, metrics, validity) | ok, **no differences** |
| events recomputed identically | ok |
| replayed status vs source status | INCONCLUSIVE vs INCONCLUSIVE |

`reproduced: true`, so the replay reproduces the checks, the worst-sample times/values and
the summed contact durations within the declared tolerances (`state_atol` 1e-9,
`state_rtol` 1e-9, `check_value_atol` 1e-9, `metric_atol` 1e-9, `time_atol` 1e-12,
`control_atol` 1e-12) and within one sample interval. The replay status
is INCONCLUSIVE **because the source is** — the same validity breach reproduces exactly. That
is reproduction, not a replay failure, and it is not reported as PASS.

### 6.1 Independent review

The increment was reviewed read-only by the configured ordinary reviewer, in sequential
rounds recorded under `out/mujoco-m5a/s0/review/`. Rounds 1–3 **rejected** on report and
evidence defects — invalid runs described as valid results, a wrong hash table, an
overwritten replay exit code, wrong factual ratios, an index that predated the last edit, and
three wrong numeric statements. Round 4 **approved** (48 claim groups, zero mismatches).
Round 5 **rejected** again over the newly added preflight driver and independent test module:
a stale addition count and a radian value labelled in metres. Round 6 **rejected** on two
further points: the full suite predated the test edits, and the review-round count here was
stale. Round 7 **rejected** once more because the fix for the initial-contact sign convention
had it backwards (negative contact distance means overlap, not separation). Round 8
**approved** the corrected text. Round 9 **rejected** because a late documentation edit
landed after the manifest was written, and round 10 **approved** once the manifest was
regenerated over the shipped text. Every one of those defects is fixed in the shipped tree, and
the full suite below was re-run after the last test edit. The verdicts are evidence; they are not a Supervisor
acceptance, which only Codex can issue.
These ten rounds reviewed the S0 increment. The two review rounds of the later portability
correction ran as default task-role workers, not the configured reviewer. The first configured
review of that correction, `op_0mvkhk9qbe119da649774136c`, returned REQUEST CHANGES; its findings
are in `out/mujoco-m5a/s0-review-completion/report.md` and are addressed in
`out/mujoco-m5a/s0-test-report-correction/report.md`. The configured reviewer has not yet reviewed
that fix.

The independent test module was authored by a separate test worker and then edited by the
implementer to match the corrected `_mm` / `_rad` field names. The assertions were not
weakened — the module still fails for a swapped drop ordering, a `max_over_phase` contact
window, a truncated run or a PASS on an invalid run.

## 7. Verification

| Check | Result |
|---|---|
| `uv run --frozen --extra physics pytest tests/test_pocky_physics_s0.py -q` | **26 passed** in 2.36 s |
| `uv run --frozen --extra physics pytest tests/test_pocky_physics_s0_independent.py -q` | **131 passed** in 11.39 s (real evidence present) |
| Same module in a copied root with `out/` absent | **32 passed, 99 skipped** — conformance cases run, evidence cases skip on the explicit optional prerequisite |
| Same module with an empty `out/mujoco-m5a/s0/` (compiled tree present) | **99 failed, 32 passed** — partial evidence is a loud failure, not a skip |
| Same module with a complete mirror of both trees and one `summary.json` halved | **14 failed, 117 passed** — every one of the 14 failures is a `JSONDecodeError` on the halved file (28 occurrences in the traceback), zero `FileNotFoundError`; all failing cases read `s0_f000`, so the cause is the injected corruption |
| Same module with a regular file at `out/mujoco-m5a/s0` | **99 failed, 32 passed** — a non-directory evidence root is broken evidence, not absence |
| Same module with a dangling symlink at `out/mujoco-m5a/s0` | **99 failed, 32 passed** — a dangling link is broken evidence, not absence |
| Same module with the S0 tree present and the compiled audits absent | **99 failed, 32 passed** — the prerequisite is both generated trees |
| `uv run --frozen --extra physics pytest tests/test_pocky_physics_s0_portability.py -q` | **7 passed** (environment-boundary regression, one test per state) |
| `uv run --frozen --extra physics pytest tests/test_pocky_physics_s0.py tests/test_pocky_physics_s0_independent.py tests/test_pocky_physics_s0_portability.py -q` | **164 passed** in 48.92 s |
| `uv run --frozen --extra physics pytest tests -q` (full suite, once, after the final test edit) | **1064 passed**, 1 warning, 997.75 s |
| `report.py --conformance` | exit 0, `ok: true`, no problems |
| `freeze_s0.py --verify` | exit 0, no drift |
| accepted anchors | `acceptance.toml` and the base `scene.xml` re-hash to the accepted values |

### 7.0 Generated evidence is an optional test prerequisite

`out/` is git-ignored, so a clean checkout has no S0 runs, replay or preflight. The
independent module therefore gates **only** its evidence-reading cases behind
`_require_generated_evidence`, which skips when the whole generated evidence set is absent and
never when it is present-but-broken. The prerequisite is **two** generated trees, because the
S0 preflight cross-checks the accepted adapter/static compiled audits: `out/mujoco-m5a/s0/`
and `out/mujoco-m5a/adapter-static/compiled/`. Both are generated, neither is source, and the
gate requires both. Plan thresholds, the SI unit table, the CAD reset derivation, the scenario
declarations and the synthetic `tmp_path` diagnostics need no generated evidence and run
everywhere.

"Absent" means the S0 evidence root does not exist at all. A directory that exists but is
empty or incomplete, a regular file or a dangling symlink at that path, or an S0 tree without
the compiled audits, are all broken evidence and fail loudly. The regression module
`tests/test_pocky_physics_s0_portability.py` proves each state from outside by copying the real
module into a temporary root with symlinked `cadkit`/`projects` sources and controlling `out/`;
raw logs are in `out/mujoco-m5a/s0-portability-repair/controls/`. Its `truncated` state mirrors
both real trees by hard link and then replaces exactly one `summary.json` with its own halved
bytes, unlinking first so the mirror cannot write through to the real inode. No assertion was
deleted or weakened, no module was blanket-skipped, and no generated evidence was committed.

The module reads each outcome and cause from a `--junitxml` report (the testsuite counts and the
first line of each failure's `message`, `<ExceptionType>: ...`), not from substrings of captured
output, because pytest echoes source and docstring text into that output.

In a clean checkout the portability module itself runs **3 passed, 4 skipped**: `absent`, `file`
and `dangling` build their own state and pass, while `partial`, `truncated`, `missing_compiled`
and `present` skip on the explicit real-evidence prerequisite. Measured in a temp root with
symlinked sources and no `out/`: independent module **32 passed, 99 skipped**, portability module
**3 passed, 4 skipped**, both together **35 passed, 103 skipped**. On the real checkout the
independent and portability modules give **138 passed, 0 skipped** (40.57 s), and the focused set
(s0, independent, portability, relative checks) gives **222 passed** (48.61 s). Logs and exact
commands: `out/mujoco-m5a/s0-test-report-correction/logs/`; the correction, the errata for the
earlier portability report and the scope are in
`out/mujoco-m5a/s0-test-report-correction/report.md`. The 7, 164 and 36/102 counts above and in
the table are from the earlier test revision.


### 7.1 Full suite

The original increment's run:

```
$ PATH="$HOME/.local/bin:$PATH" uv run --frozen --extra physics pytest tests -q
1045 passed, 1 warning in 960.52s (0:16:00)
```

Log: `out/mujoco-m5a/s0/logs/full-suite.log`; exit 0. It ran **after** the final edits to
`projects/pocky/physics/report.py`, `tests/test_pocky_physics_s0.py`,
`tests/test_pocky_physics_s0_independent.py` and `out/mujoco-m5a/s0/scripts/preflight_s0.py`,
so the suite covers the shipped source; the `after-manifest.json` `source` hashes were written
afterwards. An earlier run of the suite predated the `_mm` / `_rad` rename in the two test
modules; it is not the run reported here.

The portability correction re-ran the whole suite once, after its final test edit:

```
$ PATH="$HOME/.local/bin:$PATH" uv run --frozen --extra physics pytest tests -q
1064 passed, 1 warning in 997.75s (0:16:37)
```

Log: `out/mujoco-m5a/s0-portability-repair/logs/full-suite.log`; exit 0. That is the original
1045 plus 12 new cases from splitting three hybrid tests into pure/evidence halves plus 7
environment-boundary cases in `tests/test_pocky_physics_s0_portability.py`. The original
1045-case log is preserved at `out/mujoco-m5a/s0/logs/full-suite.log` and was not rewritten.

An earlier invocation of the same command produced `8 failed, 914 passed`. All eight
failures were `FileNotFoundError: [Errno 2] No such file or directory: 'uv'` in
`tests/test_cadkit_export_cli.py` (6) and `tests/test_pocky_geometry.py` (2): those tests
spawn `uv` from `PATH` (`tests/test_cadkit_export_cli.py:31`), and that invocation was
started from a shell whose `PATH` lacked `~/.local/bin`. Re-running the two affected modules
with `~/.local/bin` on `PATH` gave `27 passed in 18.46s`, and the clean full run above
confirms it. The failure was environmental, not a regression, and the accepted static tree's
900 passing tests are unchanged plus this increment's test modules (26 + 131 cases; the 119
originally recorded here grew to 131 when the hybrid cases were split so the pure half could
run without generated evidence, and `test_pocky_physics_s0_portability.py` adds 7).

`out/mujoco-m5a/s0/after-manifest.json` was regenerated **after** every source and report edit
of the original increment. It re-hashes all 228 accepted-snapshot paths (0 removed, 1 modified
— the Supervisor's own append to `docs/mujoco-m5a-1-adapter-static-acceptance.md`), hashes
every addition (17: the 8 scenarios, 3 options, acceptance, `report.py`, both test modules and
both reports — `source_count` = 228 accepted + 17 added), and records `unexpected_added: []`,
`unexpected_modified: []`, `clean: true`. The evidence index hashes every file under
`out/mujoco-m5a/s0/`; it excludes only the manifest itself, which cannot contain its own hash.
That manifest was the last artifact written for the original increment, and its
`evidence_count` was authoritative for the tree at that moment — the tree grows whenever a
review verdict is added, so no count is quoted here.

That file is now **historical pre-correction evidence** and is preserved byte-for-byte. The
portability correction edited three files it indexes (`tests/test_pocky_physics_s0_independent.py`
and both reports), so its source entries for those paths are deliberately stale: re-hashing it
against the current tree is expected to show exactly those three, and nothing else. It was not
rewritten, because the Supervisor's review relies on the state it recorded.

The **current** index for this correction is
`out/mujoco-m5a/s0-portability-repair/final-manifest.json`, written after the last source, test,
report and log edit by
`out/mujoco-m5a/s0-portability-repair/make_repair_manifest.py`. It (a) re-hashes the historical
manifest and every path it lists, proving the original S0 evidence — all runs, replay, freeze,
checkpoints, diagnostics and reports — is byte-identical and only the three authorized source
files changed; (b) hashes the current source tree on the same scan surface as the S0 index; and
(c) hashes the retained original evidence, the accepted `out/mujoco-m5a/adapter-static/compiled/`
audits the S0 preflight cross-checks, and the new correction evidence under
`out/mujoco-m5a/s0-portability-repair/`. `--check` exits non-zero if the original evidence moves,
an unauthorized source file changes, or any recorded hash is stale. It compares instead of
rewriting, so verification does not mutate what it verifies.

The **before** index is the accepted snapshot itself,
`out/mujoco-m5a-supervisor-finalize/accepted-snapshot/manifest.json`: 228 source files at
revision `c76a1dff1c33f5e4176182b94d59c9c574b4aec3`, operation
`op_0mvjxlsbw7236ba3c1b344c3f`. It covers the source tree only (no `out/` entries — the
accepted snapshot deliberately excludes evidence), so the matching before-evidence index is
the empty set: `out/mujoco-m5a/s0/` did not exist before this increment. `after-manifest.json`
therefore carries the whole before/after pair: the accepted 228 re-hashed in place, and every
file this increment wrote. Re-running `make_manifests.py --check-accepted` against the
pre-correction tree exited 0.

## 8. Files added

| File | Purpose |
|---|---|
| `projects/pocky/physics/scenarios/s0_*.json` (8) | frozen scenarios, CAD-derived resets |
| `projects/pocky/physics/options/s0_*.toml` (3) | strict hashed sensitivity options |
| `projects/pocky/physics/s0_acceptance.json` | frozen plan-verbatim S0 acceptance |
| `projects/pocky/physics/report.py` | read-only diagnostics, sweep, comparison, conformance |
| `out/mujoco-m5a/s0/scripts/preflight_s0.py` | binds the accepted compiled audits, derives budgets |
| `tests/test_pocky_physics_s0.py` | implementer-authored project tests (26) |
| `tests/test_pocky_physics_s0_independent.py` | independent test worker's module (131 cases: 32 need no generated evidence, 99 require it) |
| `tests/test_pocky_physics_s0_portability.py` | environment-boundary regression: absent evidence skips, partial/corrupt evidence fails |
| `docs/mujoco-m5a-report.md` | this report |
| `projects/pocky/docs/physics-m5a.md` | project-facing S0 summary |
| `out/mujoco-m5a/s0/review/request.md` + `verdict*.md/json` | the configured ordinary review request and every verdict round; the rounds and their outcomes are enumerated in §6.1 |

No accepted generic, adapter, collider, options, support, audit, params, CAD, dependency or
config file was changed; `out/mujoco-m5a/s0/after-manifest.json` lists the accepted-snapshot
diff explicitly (additions and documentation only).

## 9. Failures, limits and unmodelled inputs

- **Validity breach in every case.** 0.33–0.79 mm peak penetration against 0.2 mm. This is a
  numerical/contact-model result that the packet forbids tuning away. It makes every run
  INCONCLUSIVE and therefore makes every dynamic conclusion — including "the housing is not
  retained" — unestablished. A separate Supervisor decision would be needed to investigate
  the contact stiffness/penetration model; this increment does not touch compliance,
  friction, mass or geometry to chase a verdict.
- **The retention question is open.** The evaluator records FAIL on the structural checks in
  all eight cases by large margins (23.8–77.0× the pose bound, 42.5–46.7× the drop bound,
  15.7–17.3× the contact bound), but those statuses sit under an invalid run. They are
  evidence that *something* in the modelled assembly lets the body move, not a physical
  product verdict.
- **Chassis rotation at f=1** exceeds 0.20° (0.234°), also under an invalid run and therefore
  likewise not a physical FAIL.
- **Pre-freeze probe runs are disclosed, not hidden.** Two exploratory single-case runs
  (`out/mujoco-m5a/s0/probe/run0` at 21:44:15Z and `probe_f1/run0` at 21:46:36Z) completed
  before the freeze was written at 21:57:24Z and before the first S0 case at 21:59:59Z. They
  used exploratory scenario/acceptance documents, not the frozen ones, and the frozen
  thresholds are copied verbatim from plan §5.3, so they could not have been used to tune a
  criterion. `freeze-record.json` now derives and lists them (`probe_runs`) and derives
  `recorded_before_first_s0_run` from the freeze and first-run timestamps instead of
  asserting it.
- **Half-dt did not resolve the breach** (0.350 → 0.427 mm at f=0). Only that is established:
  one approved halving of the timestep left the .2 mm validity gate breached. Numerical
  convergence and the root cause are undetermined; two timestep values do not rule out a
  resolution contribution.
- **Still INCONCLUSIVE in M5a** (plan §6.3): packet mass, wrapper↔PETG and wrapper↔wrapper
  friction, spring rate/damping, guide/slot friction, clip force/preload, wrapper
  flexibility and blade engagement, the printed 25-tube, print tolerance/infill, and any
  physical prototype claim. M7 remains unverified. No physical input was newly measured by
  running MuJoCo.
- **Stop-limit and mechanism↔chassis contacts** remain governed by MuJoCo's parent-child
  filtering; conclusions that depend on crank/rod/pusher contacting the chassis are
  INCONCLUSIVE by construction.
- **Not executed by design:** P0–P3, packets, 25-capacity, loaded settle, shared-state
  import, M6/M7, CAD redesign, commit/push/deploy.

## 10. Stop boundary

This increment stops here, at Supervisor review. Its admission was the **second of 3**
operations under `run_0mvjxlcc2e0e8c3a94941d366` (cumulative submission 29; before it, 1 of 3
operations and 0 of 2 remediation cycles were used, so 1 operation and 2 cycles remain). It
did not renew, self-admit or request a third operation. No threshold, compliance, friction, mass, geometry or acceptance value was tuned
after seeing a result; the frozen documents are byte-identical to the freeze record and
`freeze_s0.py --verify` exits 0.

Remaining open items, all requiring a separate Supervisor decision rather than more work here:

1. **The 0.2 mm validity breach.** Every case penetrates 1.66–3.95× the bound. Nothing in this
   increment may be tuned to fix it. Investigating contact stiffness, solver settings or
   collider recipes is a new increment with its own authorized surface.
2. **Retention is unestablished.** The evaluator's structural FAILs sit under invalid runs.
   Answering the retention question needs either a valid run or a Supervisor-accepted
   decision that the modelled margins are conclusive despite invalidity.
3. **P0–P3, packets, the 25-capacity tube, loaded settle, shared-state import, M6/M7** are
   untouched by design.
4. **Physical inputs remain unmeasured** (plan §6.3): packet mass, wrapper/wrapper and
   wrapper/PETG friction, spring rate and damping, guide/slot friction, clip force and
   preload, wrapper flexibility, blade engagement, print tolerance and infill — and therefore
   any physical prototype claim.
5. **No commit, push or deploy.** `out/` is git-ignored; the source additions are uncommitted
   working-tree changes awaiting Supervisor review.

What a reader may rely on: the eight cases ran through the real project CLI and completed
every phase; the scenarios, options and acceptance are frozen and hash-bound; the replay
reproduces the source run within tolerance; the tests and the configured review are recorded.
What a reader may **not** infer: that the housing is or is not retained, that any check
PASS/FAIL is a physical product verdict, or that M5a-1, M6 or M7 is complete.
