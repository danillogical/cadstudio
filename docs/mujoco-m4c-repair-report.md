# M4c repair report: actual zero-input gate and pre-step boundary seed

**Status:** the bounded M4c repair for supervisor findings 1–2 is implemented and verified.
The configured ordinary reviewer completed on **anthropic/claude-opus-5-5**; it found one
blocking boundary-seed defect (P1), which was fixed and independently rechecked. Focused
regressions pass and the full suite ran once after the final shared changes:

```text
627 passed, 1 warning in 436.39 s, exit 0
```

M4c is submitted for Codex acceptance; M4 is not claimed complete. No M5 adapter/S0, product
CAD, candidate tuning, dependency, threshold, model/role/effort/routing/fallback/config
change, security-reviewer gate, scheduler, bridge verdict or self-renewal was made. Physical
M7 remains unverified.

Run context: `run_0mvip90biee013608fa104d9d`, remediation decision
`dec_0mviscutk8c097ba263322091`; one remediation cycle authorized, cumulative 17 submitted
operations/7 remediation cycles, max 8 operations, deadline `1792651464414` unchanged.

## Native configured plan

The configured native plan role ran before production edits with `--no-tools` (the
tool-enabled attempts had previously timed out; no custom planner was created). Exit 0 after
**166.23 s**, **24,203 bytes**:

`/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4c-repair-20261022/plan.txt`

The plan was executed with the existing APIs; the implementation keeps the established
typed tracker rather than adding a second schema layer.

## Finding 1: powered release/hold falsely passed

### Root cause

- `release_zero_ok` was written only at release begin.
- The verdict check sat inside the `not evidence_complete` branch, so complete evidence
  bypassed it.
- Hold samples were never checked at all.
- The real powered-release probe injected 2 N during all 1900 release/hold steps and still
  returned PASS/validity ok; the powered-hold probe injected 2 N only during hold and left
  1499 nonzero hold rows in the archive, also PASS.

### Fix

- `StepObservation.ctrl_max_abs` carries the actual post-step `max |data.ctrl|` from the
  forwarded observation.
- `EventTracker` tracks every required post-release sample from release start through the end
  of `dwell_to`, including every hold/dwell sample. It reads **actual** `data.ctrl`, not the
  commanded control; it never writes, zeros or corrects control.
- The first nonzero sample is sticky: phase, simulation time, step and actual max |ctrl| are
  recorded, `release_zero_ok` becomes false, and any existing success is revoked.
- A nonzero-input event is INCONCLUSIVE regardless of `evidence_complete`; the existing
  `event_verdict` check is INCONCLUSIVE. Physical PASS/FAIL cannot override it.
- `EventResult` exposes `release_zero_ok`, `release_zero_checked_samples`,
  `release_zero_violation` and `invalid_reasons`; `evaluate` appends the invalid reason to
  `validity.reasons`, so `validity.ok` is false with stage `release_input`.
- The trace's `ctrl_stored` column now reads the actual stepped `data.ctrl`; commanded values
  remain in `ctrl_requested`. The state archive already stored actual `ctrl`.
- Replay re-steps the recorded actual transition controls and recomputes the same violation;
  no saved flag is trusted. Full and tail replays both use the repaired recorder.

### Evidence

Pre-fix (supervisor raw, copied as `red-probe_results.json` / `red-extra_results.json`):

| Probe | Pre-fix |
|---|---|
| real powered release, 1900 injected steps | **PASS**, validity ok, presentation PASS |
| real powered hold, 1500 injected steps, 1499 nonzero rows | **PASS**, validity ok |
| synthetic nonzero release | PASS `supported_presentation` |

Post-fix (`green-probes.txt`, `green-extra-probes.txt`):

| Probe | Post-fix |
|---|---|
| real powered release | **INCONCLUSIVE**, validity false; release, step 2501, t=2.501 s, max |ctrl|=2; replayed reproduced |
| real powered hold | **INCONCLUSIVE**, validity false; hold, step 2901, t=2.901 s, max |ctrl|=2; replayed reproduced |
| synthetic nonzero release | INCONCLUSIVE `nonzero_input_after_release` |
| clean positive | PASS; 1900 checked zero-input samples; dwell 1.899 s |

The invalid-source replays are INCONCLUSIVE with `reproduced=True`,
`event_comparison.ok=True`, `evaluation_comparison.ok=True` and full-state max diff `0.0`.

## Finding 2: first-step crossing misclassified

### Root cause

The window was activated by `begin_phase`, but crossing geometry was seeded on the first
post-step sample. A crossing during that first integration transition was labelled
`initial_protruding` and lost.

### Fix

- `TelemetryRecorder.begin_phase` captures a coherent **pre-step** boundary sample and passes
  it to `EventTracker.begin_phase(..., boundary=...)`.
- `_event_boundary_observation` calls `self._observe()` once and reads pose, quaternion, COM,
  velocity and time from that forwarded copy. It never reads live `self.data`, whose
  kinematics can be stale after `mj_step` and unforwarded in replay. This was the reviewer's
  P1 blocker.
- `_seed_boundary` only seeds previous geometry and initial-outside/protruding suppression.
  It is never counted as a crossing and is never release-input evidence; the previous
  actuation command is not treated as a release sample.
- The first post-step sample compares against the seeded geometry, so a first-step crossing
  is a real crossing. Initial-outside and pre-window crossings remain suppressed.
- Replay reconstructs the same boundary from the re-stepped, forwarded state at the phase
  start; it does not trust a saved geometry or flag.

### Evidence

| Probe | Result |
|---|---|
| synthetic boundary crossing, first actuation step | count 1, `initial_protruding=False`, crossing t=0.102857 |
| synthetic initially outside at boundary | count 0, `initial_outside` |
| synthetic pre-window crossing | count 0, `initial_protruding` |
| real Euler crossing in the last step before `window_from=release` | count 0, `initial_protruding`; seed pose equals forwarded coherent pose; replay reproduced |
| real `window_from=settle` (first timed phase) | source PASS, replay PASS, event comparison equal |
| real recorder boundary integration | boundary phase `actuate`, time 0.5, step 500, packet pose present |

The supervisor's original `extra_probes.py` first-step case is a pure tracker call that does
not pass the new boundary argument, so it still reports 0; `green_boundary_probe.py` runs the
same synthetic geometry **with** the boundary and reports count 1. The real recorder test
proves the integrated path supplies the boundary.

## Tests and commands

```text
uv run pytest tests/test_cadkit_physics_m4c_events.py \
  tests/test_cadkit_physics_m4c_acceptance.py \
  tests/test_cadkit_physics_m4c_fixture.py \
  tests/test_cadkit_physics_scenario.py -q
82 passed in 34.30 s

uv run pytest tests/test_cadkit_physics_m4a.py tests/test_cadkit_physics_m4b_replay.py \
  tests/test_cadkit_physics_m4b_adversarial.py tests/test_cadkit_physics_m4b_typed.py -q
90 passed, 1 warning in 25.95 s

uv run pytest tests/test_cadkit_physics_mechanics.py tests/test_cadkit_physics_scene.py \
  tests/test_cadkit_physics_export_cli.py tests/test_cadkit_physics_optional.py \
  tests/test_cadkit_physics_units.py tests/test_cadkit_physics_gravity_drop.py \
  tests/test_cadkit_physics_hollow.py -q
231 passed in 68.28 s

PATH=/Users/daniel_l_newman/.local/bin:$PATH uv run pytest tests/ -q
627 passed, 1 warning in 436.39 s, exit 0
```

Adverse coverage added: nonzero at begin-release; one intermediate release sample; hold-only
nonzero; late hold violation revoking success; boundary command not counted as release input;
first-step crossing; initially outside; pre-window crossing; Euler pre-window boundary;
first-timed-phase replay; powered release/hold real probes and their replays; recorder
boundary integration. The one warning is the existing deliberate duplicate-ZIP-member test.

## Review

The configured ordinary `reviewer` agent (model role `slow`) completed on
**anthropic/claude-opus-5-5**, verified in
`M4cRepairReview.jsonl` (34 model records; provider anthropic). No override or substitute was
used. First pass: zero-input gate correct; boundary seed P1 blocked (stale live-state read).
After the forwarded-copy fix and two new real tests, the follow-up verdict was **correct, no
remaining blocker** (confidence 0.85). The reviewer did not run the full suite; it was run
once after the final shared change. `review.md` records the model and finding/fix map. No
separate security-reviewer gate was requested; that role remains disabled.

## Preservation and hashes

`projects/pocky/physics/acceptance.toml` is untouched:

- raw SHA-256 `518a45ffc4592ca602be4c33c59681038e43dedaa15b688312202c3a57ff6ca2`
- semantic acceptance hash `5109a0a4cb5ed70c3605ac9b1148eda58cae0a05ba18725807d645e474d216d3`

M3/M4a/M4b behavior is preserved (90 focused regressions and the full suite). The native-plan
paths in `docs/mujoco-m4c-report.md` now point to the actual
`cadstudio-m4c-plan-20261021/plan3.txt` and label the failed attempts there.

## Artifacts

Under `/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4c-repair-20261022/`:

- `prompt.md`, `plan.txt` (native plan, 24,203 bytes), `plan.err`;
- `red-probe_results.json`, `red-extra_results.json` (pre-fix false PASS);
- `green-probes.txt`, `green-extra-probes.txt`, `green-boundary-probe.txt`/`.json`;
- `powered-release/`, `powered-hold/`, `cli-run-positive/`, `cli-replay-positive/`,
  `cli-replay-powered-release/`, `cli-replay-powered-hold/`;
- `focused-m4c.txt`, `m4a-m4b.txt`, `other-physics.txt`, `full-suite.txt`;
- `review.md`, `final-hashes.sha256`.

## Limits

- The boundary sample is reconstructed from the forwarded, re-stepped state during replay,
  not serialized as a separate artifact. Re-stepping is deterministic in the pinned
  environment, and the real Euler pre-window and first-phase replay tests confirm source and
  replay agree; a fully coordinated archive rewrite is outside the hash guarantee.
- Nonzero actual control during the required interval is an execution invalidity
  (INCONCLUSIVE), not a physical FAIL; an invalid run cannot distinguish a physical failure
  from actuation.
- The first-step crossing evidence is a synthetic detector trajectory plus a real recorder
  boundary-integration test. The product fixture does not naturally dispense on the first
  actuation step.
- No Pocky adapter/CAD/S0, M5 or physical M7 evidence is present. Wrapper flexibility,
  friction, spring rate and packet mass remain unmeasured.
