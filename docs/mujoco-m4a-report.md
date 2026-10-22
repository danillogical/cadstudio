# M4a report: typed generic scenario runner and evidence

**Status:** M4a implemented in this bounded turn; submitted for Codex independent review.
**Not claimed:** M4 acceptance, M4b replay/event coverage, product Pocky adapter, S0, or
physical M7 validation. `S0` remains M5a; physical measurements remain unverified.

## Scope and starting state

The accepted generic M3 mechanics/scene source was reused unchanged. This increment adds a
generic, optional, headless scenario layer; no product CAD, project adapter, dependency,
provider/model/effort/fallback or global configuration was changed. Prior supervisor fixes
remain intact: effective drive is `actuator_force` **before** gearing; non-finite comparison
values serialize as `null`; no M3 trial gating was relaxed; contact and joint-stop refsafe
compatibility is still checked.

New production files:

- `cadkit/physics/scenario.py` — versioned strict JSON scenario/acceptance types, allowlisted
  fixture registry, canonical identities, separate acceptance hash.
- `cadkit/physics/telemetry.py` — per-step validity/telemetry recorder, CSV and state archive.
- `cadkit/physics/evaluate.py` — central four-state validity and acceptance evaluation.
- `cadkit/physics/runner.py` — generic reset/settle/actuate/release/hold runner, budgets,
  manifest/summary/report, failure evidence.
- `cadkit/cli.py` — only the new `cad physics scenario` handler/parser.
- `docs/physics-m4a-scenario.schema.json`,
  `docs/physics-m4a-acceptance.schema.json`,
  `docs/physics-m4a-summary.schema.json`.
- `tests/test_cadkit_physics_scenario.py`, `tests/test_cadkit_physics_m4a.py`.

## Native plan (required before production edits)

Configured native `plan` role executed successfully before production edits:

- Command: `omp -p --model @plan --no-session --tools read,grep,glob --max-time 240
  --cwd /Users/daniel_l_newman/src/cadstudio "<M4a planning prompt>"`
- Exit: `0`, wall time `154.31 s`, output `7706` bytes.
- Raw output:
  `/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4a-plan-20261021/plan.txt`
- Stderr: empty file at the same directory.

The plan's 12 steps were: strict typed scenario/acceptance `scenario.py`; registry-only
fixtures; phase planning and total step/time/trace preflight; `run_assembly`/`run_scenario`
with one compiled model and independent `MjData`; bounded `effort/gear` actuation with
requested/stored/effective/generalized force; per-step telemetry/state archive; centralized
validity/evaluation precedence; declarative metrics/predicates; manifest/summary/report/
acceptance lock with unique directories; thin CLI; focused tests and independent review.
Implementation followed it, with the deviations below.

Significant deviation from the plan's file split: telemetry and artifact code were kept in
`telemetry.py` + `runner.py` rather than separate `actuation.py`, `validity.py`,
`metrics.py`, `artifacts.py`. The required boundaries (strict loader, recorder, evaluation,
runner) are unchanged and there is no competing implementation.

## Implemented behavior

### Scenario and acceptance boundary

- Two strict JSON documents, version `m4a-1`: scenario (fixture, seed, timestep, sampling,
  budgets, reset/settle/actuate/release/hold phases) and acceptance (literal checks plus
  validity bounds). Acceptance is loaded and copied separately, never editable by the
  scenario.
- Rejected: unknown fields at every level, duplicate keys, `NaN`/`Infinity`, unrepresentable
  numbers, deeply nested JSON, unsupported versions, unknown fixtures/kinds, unsafe IDs,
  non-positive durations, zero-step phases, invalid reset order/uniqueness, unknown
  joints/actuators/bodies/phases, wrong units, empty checks, budget overflow.
- Fixtures are a fixed registry: `loaded_slider`, `loaded_slider_no_spring`,
  `loaded_slider_negative_gear`, `drop_box`. Scenario input cannot name files, imports,
  commands, arbitrary Python objects, or assets.
- JSON schemas are published in `docs/physics-m4a-*.schema.json`; no schema-validation
  dependency was added.

### Runner and actuation

- One compiled `MjModel`; one independent `MjData` per run. `mj_resetData` then only the
  declared reset joint coordinates are written, followed by `mj_forward`. After that no code
  writes `qpos`; motion comes from actuator effort, spring/damping, contact and gravity.
- Settle/release/hold set every actuator control explicitly to zero. `actuate` requests a
  physical generalized effort in N (slide) or N·m (hinge); raw control is `effort / gear`,
  and the actuator's emitted `ctrlrange`/`forcerange` bound the transmitted effort. The
  recorder keeps requested effort, requested raw control, raw stored control,
  `actuator_force` (effective drive **before** gear), and `qfrc_actuator` (actual generalized
  force), including signed peaks.
- Phase durations are converted to whole steps from the **total** plan before export or
  stepping; zero-step phases, total steps, total simulated time and planned trace rows are
  preflighted. Requested and actual durations/steps and completion are recorded.
- Initial, post-settle and terminal states are recorded with hashes. Free-joint coordinates,
  body/COM poses and body velocities are included; the numeric state archive contains
  `time`, `qpos`, `qvel`, `act`, `ctrl`, `qacc_warmstart`, `qfrc_applied`, mocap, phase codes
  and names.

### Validity and evidence

- Central precedence: invalid scene/build/unit/compile/file -> ERROR/3; non-finite
  state/acceleration/body pose/forces/energy/control, every solver warning read from the
  live stepped `MjData` (corrected in `docs/mujoco-m4a-repair-report.md`), unresolved
  contact/stop compliance, declared penetration/speed/angular-speed/energy breach, missing
  evidence or empty checks -> INCONCLUSIVE/2; valid unmet predicate -> FAIL/1; valid complete
  checks -> PASS/0. Invalidity cannot PASS.
- Telemetry is checked and accumulated on **every** integration step; the CSV trace is a
  sparse display sample. State time and force-evaluation time are separate columns. Contact
  rows carry body/geom pair, normal force and penetration and are bounded by the contact-row
  cap; per-pair maxima are independent of sparse sampling.
- Run directory: unique default (UTC microseconds + scenario hash), atomic creation, existing
  explicit paths refused. Manifest has runtime/platform/solver versions, resolved physical
  inputs with `Source` provenance, scene/assets hashes, scenario/seed/acceptance identities,
  state hashes, budgets/plan and artifact hashes. Summary/report are UTF-8; JSON is strict
  with non-finite values written as `null`. Admitted failures preserve partial
  trace/states/contacts plus failure summary/report/manifest.

## Independent review and fixes

The configured `reviewer` role (workbuddy-ai/step-5-preview) returned an immediate 429 and
could not review. The configured `security-reviewer` is not registered in this harness.
Neither was enabled, reconfigured, or replaced in configuration. A separate default-role OMP
agent performed the independent read-only review and explicitly inspected parsing, asset
paths and output handling. Raw review: 
`/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4a-20261021/review-fallback.md`;
targeted follow-up verification:
`/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4a-20261021/review-followup.md`.

Findings and disposition:

| Finding | Disposition |
|---|---|
| H1 free-body speed/state invisible; tight speed bound could PASS | Fixed: free joints and all-body velocities tracked; body/free state in snapshots; new `body_speed` predicate; `drop_box` tight-bound regression now INCONCLUSIVE. |
| H2 huge numbers/step ratios/deep nesting escaped as CLI 1 | Fixed: representability guards, finite-ratio preflight, `RecursionError` handling, CLI ERROR mapping; regression tests. |
| M1 files read multiple times; lock could differ | Fixed: one read retained in the loaded spec; lock bytes and hash tests added. |
| M2 summary `sha256` was not a file hash | Fixed: exact UTF-8 byte SHA-256; test asserts equality. |
| M3 execution exceptions lost partial telemetry | Fixed: recorder exists before execution; failure path writes partial trace/states/contacts and manifest; fault-injection test. |
| M4 stopped run could report initial terminal state | Fixed: terminal state is the last recorded boundary; numerical-stop test. |
| L1 reserved state names | Fixed and tested. |
| L2 schema/code budget drift | Fixed: budgets required in schema/code. |
| L3 `effort_bound` on unexercised actuator | Fixed: requires an actuate phase for that actuator; tested. |
| L4 explicit output atomicity/symlink reuse | Fixed: atomic `mkdir(exist_ok=False)`, existing paths refused. |
| L5 partial compiled solver comparison | Fixed: integrator, cone, solver, iterations, friction, contact solref, joint stop solref. |
| L6 unbudgeted contact rows | Fixed: contact-row cap derived from `max_trace_rows`. |
| L7 dead code / inconclusive validity flag | Fixed. |

### Follow-up independent verification

The same fallback reviewer performed a targeted read-only verification of the fixes (no
edits, no configuration change). It confirmed H1, H2, M1-M4, L1-L4 and the new telemetry
behavior, and found two residual defects:

- L5 regression: the joint-stop solref comparison used a leaked `joint_id` from an earlier
  loop, so a stop declared on any joint but the last jointed/actuated one would compare the
  wrong compiled joint. Fixed by resolving `joint_id` inside the stop loop; new regression
  `test_stop_compliance_is_checked_on_the_right_joint` exercises a real declared stop.
- M1/M2 residual: text-mode reads normalized CRLF, so a CRLF input was not byte-identical to
  the frozen lock/hash. Fixed by reading bytes and decoding UTF-8 without newline translation;
  new regression `test_crlf_input_is_locked_byte_for_byte` asserts byte-identical lock and
  matching SHA-256.

The follow-up found no remaining false-PASS in the fixed areas. Residual M4b items it named:
replay/state hash-tamper, identity/direction/dwell event fixtures, cross-platform determinism,
contact-row-cap behavior, richer failure-summary metadata, and richer schema ID constraints.

## Verification and raw evidence

Focused tests after all review fixes:

```text
uv run pytest tests/test_cadkit_physics_scenario.py tests/test_cadkit_physics_m4a.py -q
49 passed in 13.82s
```

Prior physics regressions (mechanics, scene, export/CLI, optional, units, gravity drop,
hollow):

```text
uv run pytest tests/test_cadkit_physics_mechanics.py tests/test_cadkit_physics_scene.py \
  tests/test_cadkit_physics_export_cli.py tests/test_cadkit_physics_optional.py \
  tests/test_cadkit_physics_units.py tests/test_cadkit_physics_gravity_drop.py \
  tests/test_cadkit_physics_hollow.py -q
231 passed in 65.03s
```

Final full suite (after the last review fixes):

```text
PATH=/Users/daniel_l_newman/.local/bin:$PATH uv run pytest tests/ -q
504 passed in 381.88s (6:21), exit 0
```

Raw output:
`/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4a-20261021/full-suite-final2.txt`.

### Public CLI evidence

Configs: `/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4a-20261021/configs/`
Runs: `/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4a-20261021/runs-final/`

Each command was `uv run cad physics scenario <scenario.json> --acceptance
<acceptance.json> --out <run-dir>`.

| Case | Exit | Status | Key raw result |
|---|---:|---|---|
| `positive_a` / `positive_b` | 0 / 0 | PASS / PASS | held displacement `0.0199600919 m`; release residual `3.98418e-05 m`; terminal speed `0.000139959 m/s`; peak effort `1 N` |
| `clip` (request `1e6 N`, bound `2 N`) | 0 | PASS | held displacement `0.0399201838 m`; stored ctrl `1e6`; effective `2 N`; generalized effort `2 N` |
| `missing_force` (effort 0) | 1 | FAIL | `held_displacement` FAIL at `0.0 m`; other checks pass |
| `missing_spring` | 1 | FAIL | held `0.0501718742 m`; release residual `0.0499598167 m` |
| `numerical` (peak speed bound `1e-12`) | 2 | INCONCLUSIVE | all four predicates PASS, validity breach `peak speed 0.129701876 m/s` |
| `drop` (contact fixture) | 0 | PASS | `box`/`floor` peak normal `1.18320405 N`, penetration `0.0005868176 m`; terminal free-joint velocity recorded |
| `malformed` | 3 | ERROR | loader rejected before any run directory |
| `budget` (max 10 steps) | 3 | ERROR | total `1700` steps rejected before export |
| `collision` (existing run dir) | 3 | ERROR | refused to overwrite `positive_a_run` |

Determinism (`positive_a` vs `positive_b`, same scenario/seed/reset):

- scene hash, scenario hash, acceptance hash, terminal state hash and run identity: identical;
- metric dictionary: identical;
- `trace.csv`, `states.npz`, `contacts.csv`: byte-identical;
- `trace.csv` SHA-256 `58a673be97a1603dd388218755d3dbaf48d3cb7b21c37a758fde8df7f964dae2`;
- `states.npz` SHA-256 `c00aa4709977a07478cfe71f81fbda172253e38e630c11782a4aa62b4bc6fefd`;
- acceptance lock SHA-256 equals the input file SHA-256 and summary `acceptance.sha256`.

Inspected artifacts for `positive_a_run`: `summary.json` (strict), `manifest.json` (artifact
hashes/provenance), `report.md` (readable status/checks/phases/states), `trace.csv`
(explicit SI units and separate state/force times), `contacts.csv`, `states.npz`
(replay-compatible arrays), `acceptance.lock.json`, `scenario.json`, `scene.xml`, assets.
For `drop_run`, the named contact pair and per-step penetration maximum are present even with
a 50 ms display sampling interval.

## Limits and remaining work

- M4a only. M4b must add full deterministic replay and hash-tamper rejection, identity/
  direction/dwell event fixtures, and the complete synthetic-failure set required before M4
  acceptance.
- No product Pocky adapter or S0. M5a owns the real adapter; physical M7 calibration and
  correlation remain unverified.
- Analytic fixture coefficients, contact compliance and spring inputs are declared
  assumptions, not PETG measurements. PASS is only a statement about the declared scene.
- Cross-platform bit equality is not claimed; determinism shown here is on macOS arm64 with
  MuJoCo 3.16.0, NumPy 2.5.4, Python 3.12.15.
- No M4 acceptance or physical design decision is claimed by this report.

Supervision: this turn executed under linked successor2
`run_0mvihmvsm9f3be51a0fd22543` (12 operations / 2 remediations / 480 min,
deadline `1792638674806`), with no self-renewal or new scheduler. The configured reviewer
429 is recorded as a process limitation, not hidden; the fallback review and all fix tests
are disclosed above.
