# M4a repair report: four supervisor-identified defects

**Status:** bounded M4a repair of the four defects in
`docs/mujoco-m4a-supervisor-review.md` is implemented and independently reviewed;
submitted for Codex remediation decision. No M4 acceptance is claimed.
**Not in scope:** M4b replay/hash-tamper/event fixtures, the real Pocky adapter, S0, or
physical M7. No product CAD, dependency, threshold, fixture-registry, model or global
configuration change; the human-authorized OpenCode route and all role/effort/fallback
settings are untouched.

## Native plan (required before production edits)

- Command: `omp -p --model @plan --no-session --tools read,grep,glob --max-time 240
  --cwd /Users/daniel_l_newman/src/cadstudio "<four-repair planning prompt>"`
- Exit `0`, wall time `156.53 s`, output `5502` bytes.
- Raw: `/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4a-repair-plan-20261021/plan.txt`
  (stderr empty).

The plan proposed: immutable per-step copies plus a scratch observational evaluation;
stage-labelled force provenance; a supported-integrator gate; pre-step initial accumulation
and a rejection gate; canonical acceptance documents with raw-byte locking; and a bounded
`os.open`/`fstat`/read-cap loader. Implementation followed it with one deliberate deviation:
the observational forward is run on a **scratch `MjData`** and all observed quantities are
labelled `force_time_s == state_time_s` with `force_stage`, instead of integrator-specific
stale labels (`state_time - dt` for Euler, `None` for RK4). This is coherent at one timestamp
and testable; implicit integrators are rejected rather than sampled.

## Repairs

### 1. Coherent post-step body/COM/velocity telemetry and exact force semantics

- `TelemetryRecorder._observe()` copies the live integration state
  (`qpos`, `qvel`, `act`, `ctrl`, `qfrc_applied`, mocap, and `eq_active`/`xfrc_applied` when
  present) into a private scratch `MjData` and runs `mj_forward` there. The live state is
  never rewritten; `mj_step` remains the only integrator call (no `mj_step1`/`mj_step2`
  split, so RK4 is preserved).
- Poses, COM (`xipos`), velocities (`mj_objectVelocity`), energy, contacts and forces are
  read from that observed state, so trace rows, `Snapshot.bodies`, `body_speed` and per-step
  speed/energy peaks all belong to `state_time`.
- `force_time_s == state_time_s` and `force_stage` (`post_step_forward` for steps,
  `initial_forward` for the reset row) are recorded in the trace/contact CSVs and in
  `solver.force_sampling` in the summary/manifest. RK4 intermediate stages are explicitly
  not sampled.
- `_require_supported_integrator` rejects any integrator other than `Euler`/`RK4` before a
  run directory is created (CLI ERROR/3; API `ScenarioError`).
- Regression: a 50-step equality test proves the observational sampling does not perturb
  `qpos`/`qvel`/`time`.

### 2. Initial reset-state validity and contact accumulation

- `record_initial` now runs the same finite/force/energy/warning/contact accumulation as a
  step, with `stage="initial"` and live warning counters, and returns whether the reset state
  is admissible.
- Declared-bound breaches of the reset state are emitted by `initial_bound_reasons` with
  `stage="initial"` and time `0.0`; `evaluate` does not duplicate them and still reports a
  larger later peak.
- `_execute` sets `initial_rejected` and takes **zero** steps when the reset state is invalid;
  all timed phases are recorded as unstarted/incomplete, and the admitted run still writes
  `trace.csv`, `contacts.csv`, `states.npz`, summary, report and manifest. No initial state is
  corrected or teleported.

### 3. Canonical, coherent acceptance/scenario lock

- `ValiditySpec.to_dict` omits unset optional bounds instead of emitting `null`, so a
  programmatic `AcceptanceSpec` with `{}` or partial validity round-trips through its own
  loader.
- `scenario_text_matches` / `acceptance_text_matches` re-parse a candidate document strictly
  and compare typed hashes; `_select_document_text` copies a source document only when it
  still describes the document being evaluated, otherwise it emits a canonical typed
  document. A typed spec mutated after loading can no longer write a lock for the old
  criteria.
- Locks are written with `write_bytes`, preserving exact input bytes (including CRLF) and the
  raw SHA-256; the semantic/content hash remains separate.
- `CheckSpec.__post_init__` rejects empty units, so a directly constructed check cannot
  produce an unloadable lock.

### 4. Bounded configuration read

- `_read_json` opens with `os.open(..., O_RDONLY | O_NONBLOCK)`, `fstat`s and requires a
  regular file, then reads at most `MAX_CONFIG_BYTES + 1` bytes before decoding/parsing.
  Directories, FIFOs, devices and sockets are rejected before decoding; symlinks to regular
  files are accepted; the descriptor is closed on every path; exact bytes are retained.
- Tests cover the cap+1 request bound, an exact-cap document, directory/FIFO rejection, and
  symlink-to-regular acceptance.

## Independent review

The configured `reviewer` role (workbuddy-ai/step-5-preview) returned 429 and the configured
`security-reviewer` is not registered; neither was enabled, reconfigured or replaced. A
separate default-role OMP agent performed the independent read-only review
(`/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4a-repair-20261021/review-repair.md`,
follow-up `review-repair-followup.md`).

It found and the repair fixed:

| Finding | Severity | Disposition |
|---|---|---|
| Solver warnings were scanned on scratch data, so a real warning could PASS | HIGH | Live `mj_step` counters read every step (once per name, stage/time) plus evaluation fallback; regression test forces INCONCLUSIVE |
| A mutated typed acceptance/scenario could copy a stale lock | MEDIUM | Typed-hash text matching; canonical fallback; regression test |
| Module docstring still described `force_time = state_time - dt` | MEDIUM | Docstring now states `force_time_s == state_time_s` and `force_stage` |
| CRLF test emitted no newlines | LOW | `indent=2` plus explicit `\r\n` byte assertions |
| Reset phase name replaced by literal `"reset"` in rows | LOW | `_phase_label()`; regression test |
| Direct `CheckSpec` could emit empty `units` | LOW | `__post_init__` validation |
| Integrator gate ran after export; validity de-duplication could hide a larger peak | LOW | Gate moved before run-dir creation; explicit initial/peak comparison |

Follow-up verification marked all items ADDRESSED and found no remaining false-PASS path in
the reviewed surfaces. Its one residual (initial warnings attributed to the first step) was
fixed immediately afterward by passing live warning data into the initial accumulation.

## Verification and raw evidence

Focused after all fixes:

```text
uv run pytest tests/test_cadkit_physics_scenario.py tests/test_cadkit_physics_m4a.py -q
61 passed in 15.33s
```

Prior physics regressions (mechanics, scene, export/CLI, optional, units, gravity drop,
hollow): `231 passed in 65.50s`.

Final full suite:

```text
PATH=/Users/daniel_l_newman/.local/bin:$PATH uv run pytest tests/ -q
516 passed in 381.14s (6:21), exit 0
```

Raw: `/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4a-repair-20261021/full-suite-final.txt`.

### Probe evidence

Runs and `probe_results.json`:
`/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4a-repair-20261021/`.

| Probe | Result |
|---|---|
| Euler one step (`dt=1 ms`, `body_speed <= 0.005 m/s`) | **FAIL**, body speed `0.00980665 m/s`; free `qvel_z = -0.00980665`; `xipos_z = 0.04999019335` (was stale 0 / PASS) |
| RK4 free fall 50 ms | **PASS**, `qvel_z = -0.4903325`, `xipos_z = 0.0377416875`, both matching `g·t` and `z0 − ½g t²` |
| Sampling perturbation (50 steps, plain vs recorder) | `qpos`, `qvel`, `time` bit-equal |
| Initial overlap `0.0002 m` vs bound `0.00019 m` (RK4) | **INCONCLUSIVE**, `stage="initial"` reason, zero timed steps, artifacts retained; initial == peak penetration |
| Injected solver warning (`mjWARN_BADQVEL`) | **INCONCLUSIVE**, `step` reason `solver warning badqvel raised 1 times` (was PASS) |
| Mutated acceptance (`max_speed_m_s = 1e-12`, stale source text) | canonical lock reloads, hash matches summary, bound `1e-12` |
| Programmatic `{}`/partial validity lock | reloads through `load_acceptance`, hash matches |
| Oversized config (cap + 4096) | rejected after a `cap + 1` request (`1048577`); directory/FIFO rejected; exact-cap document accepted |
| CLI `positive` / `missing_force` / `numerical` | exit `0` PASS / `1` FAIL / `2` INCONCLUSIVE, unchanged |

## Limits and remaining work

- M4b still owns full deterministic replay and hash-tamper rejection, event
  identity/direction/dwell fixtures, full integration-state identity, explicit archive
  resource budgets, and the complete synthetic-failure set.
- Contact-force maxima are forward-evaluated at the recorded state, not the force applied
  inside the integrator step; provenance is labelled and mid-step impulses are not claimed.
  `_observe` copies the integration state and applied/mocap data but not every optional
  `MjData` field.
- `S0` remains M5a and physical M7 remains unverified; analytic fixture inputs are declared
  assumptions, not PETG measurements.
- Supervision: bounded repair under remediation `dec_0mvijl1n986b934ae0bba0982`, successor2
  `run_0mvihmvsm9f3be51a0fd22543`; no self-renewal, no new scheduler, no model/fallback
  change, no bridge review decision dispatched.
