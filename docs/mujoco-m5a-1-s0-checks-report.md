# M5a-1 packet report — bound S0 checks, every-step watches and replay

Date: 2026-10-22. Repository: `/Users/daniel_l_newman/src/cadstudio`. HEAD:
`c76a1df` (clean fast-forward from `ca9a305`) plus uncommitted authorized changes. This
document covers the original packet turn and the one authorized R1–R3 remediation. No
commit, push, deployment or bridge verdict was made.

## Authorization and correlation

- Original packet: human invoked `$codex-omp-orchestrator` with
  `docs/mujoco-m5a-1-handoff.md` and directed `pull from git`; the Supervisor
  fast-forwarded `ca9a305 -> c76a1df` and independently ran the physics regressions
  (488 passed, 125.69 s). Packet: `docs/mujoco-m5a-1-s0-checks-packet.md`. Scope was
  handoff items 1–2 only: generic bound checks, every-step/max-over-phase watches,
  `body_speed` window, opt-in near-threshold band, runner/replay recomputation,
  independently authored tests and configured ordinary review including the pulled commit.
- Independent renewal: `docs/mujoco-supervision-renewal-5.md`. Supervision run
  `run_0mvj62atk8b61da9fe2edf2ea`, chat `01a1624d-8caf-7102-991f-d6ca998446b4`,
  successor5 bounds 6 operations / 2 remediations, deadline `1792679704903`. Cumulative
  before the first admission: 22 operations / 9 remediations. The first admission spent one
  operation; the Supervisor then verified 529 physics tests, all 204 after-manifest hashes,
  59 reviewer messages attributed to `anthropic/claude-opus-5-5` and 84 test-worker
  messages on the configured DeepSeek role, and recorded `REMEDIATE
  dec_0mvj93wc4ee431c23c04f7fb2` (idempotency key `cadstudio-m5a1-s0-review-remediate-1`)
  for completed `op_0mvj62z0p3dcdad31cbfa078c`. Cumulative after that decision: 23 submitted
  operations / 10 remediation cycles; the remediation admission is
  `cadstudio-m5a1-s0-checks-repair-01a1624d-1`.
- Supervisor review: `docs/mujoco-m5a-1-s0-checks-supervisor-review.md`, with R1–R3 and the
  authoritative probe `out/mujoco-m5a-supervisor-resume/probe_s0_checks.py` and original
  artifacts `out/mujoco-m5a-supervisor-resume/s0-probes/`. Those originals were preserved;
  an identical copy was rerun into fresh output directories
  (`out/mujoco-m5a-s0-checks/remediation-probe/`).
- Planning gate: the packet pre-authorized the bounded implementation increment and the
  remediation decision authorized the bounded repair. No native plan mode, separate planner
  process, or literal `/plan` was used. Executing agent: the managed OMP Turn Orchestrator
  under the configured default role; the host reports `opencode-go/deepseek-v4.1-flash`. No
  model, provider, effort, role mapping, or fallback setting was changed or overridden.
- OMP did not submit, renew, or mutate anything in the bridge and cannot start another packet.

## What was implemented

Production files (authorized generic surface plus one documented conformance file):

| File | Change |
|---|---|
| `cadkit/physics/scenario.py` | New kinds `relative_pose`, `relative_translation`, `contact_duration`; fields `max_rotation_rad`, `axis`, `frame`, `lower`, `upper`, `force_threshold_n`, `window`; `window` on `body_speed`; acceptance-level `near_threshold_fraction`; strict loading; hash-stable canonical serialization; `CheckSpec.validate_semantics()` and `AcceptanceSpec.__post_init__` for typed/file parity (R3). |
| `cadkit/physics/telemetry.py` | Relative-transform/pose-delta math; per-step watches for max-over-phase pose/translation/speed; summed-force contact-duration state machine; evidence storage. |
| `cadkit/physics/evaluate.py` | Reference/phase validation (including typed semantics, R3); bound evaluation with both pose components; signed two-sided translation bounds and world-z drop; whole-run contact durations; opt-in near bands on pose/translation, max-over-phase speed and contact duration (R2); fail-closed coverage gates. |
| `cadkit/physics/runner.py` | Passes acceptance checks to the recorder; strict finite options validation at the `run_assembly` boundary; parses the selected canonical scenario/acceptance text through the strict loader before claiming a run directory (R3). |
| `cadkit/physics/replay.py` | Rebuilds the same watches from the verified acceptance and re-steps; recomputes every watch/max/time/status; rejects non-finite or overflowed evidence before tolerance arithmetic (R1); takes the worst-sample time tolerance from the verified compiled model timestep, never from the mutable summary plan (remediation review finding). |
| `docs/physics-m4a-acceptance.schema.json` | Publishes the new kinds, the `body_speed` window and `near_threshold_fraction`. Required by the existing published-schema test. |

New tests: `tests/test_cadkit_physics_relative_checks.py`, authored by a worker other than
the implementation worker (58 collected cases).

No CAD, params, project hook, adapter, scenario, options, criteria, configuration or
dependency file changed. `projects/pocky/physics/` still contains only `acceptance.toml`.

## Frozen semantics and explicit decisions

- Relative pose uses current attached axes every sample:
  `p_rel(t)=R_a(t)^T(p_b(t)-p_a(t))`, `R_rel(t)=R_a(t)^T R_b(t)`,
  `Δp=p_rel(t)-p_rel(ref)`, `ΔR=R_rel(t)R_rel(ref)^T`, `θ=2 acos(clamp(|w|,0,1))`.
  The initial axes are never frozen and the transform order is never reversed.
- `relative_pose` reference is the `initial` state. `relative_translation` reference is the
  end boundary of `from_phase` (`initial` allowed); `to_phase` must be timed and follow it.
  Both signed bounds are required and tested on both sides. `frame="world"` is accepted only
  for `axis="z"`; it compares world separation vectors and reports the signed value and
  `drop_m=max(0,-value)` for the reported value. `drop_m` is `null` for local frames.
- `window="end"` (default) evaluates the declared terminal boundary. `window="max_over_phase"`
  evaluates every recorded post-step state of the phase, reports worst value/time and the
  terminal value, and requires `samples == phase.actual_steps` with a completed phase;
  otherwise INCONCLUSIVE. Pose keeps both translation and rotation evidence; either breach is
  FAIL.
- `body_speed` keeps terminal semantics by default and gains every-step worst speed under
  `max_over_phase`. Reset/`initial` phases are rejected for that window.
- `contact_duration` is a whole-run quantity: the reset state and every post-step state
  contribute; normal forces are summed over all contact points/geoms of the pair in either
  body order before the strict `>` threshold comparison. Interruption is any state at or
  below the threshold. A run's duration is last-minus-first above-threshold state time, so N
  consecutive states contribute `(N-1)*dt`; an isolated one-state excursion is `0.0 s` and is
  reported through `samples_above`/`run_samples`. Zero contact is a valid zero; a missing
  watch or incomplete coverage is INCONCLUSIVE.
- Near-threshold band: opt-in top-level `near_threshold_fraction` in `[0, 0.5]`, default 0
  (off). Applied to `relative_pose` translation and rotation, `relative_translation`
  lower/upper, max-over-phase `body_speed`, and `contact_duration`, using worst-over-phase
  evidence. Width is `fraction*abs(bound)`; a zero bound has width zero and therefore no
  band; negative bounds behave symmetrically. A passing value inside the band is
  INCONCLUSIVE; FAIL stays FAIL. Structured evidence records the declared bound
  (`bound_m_s`/`bound_s`), the fraction and the band result.
- Canonical serialization omits `window="end"`, the default `frame="body_a"`, and
  `near_threshold_fraction=0`, so every earlier acceptance document keeps its hash. Typed
  `CheckSpec` construction stays permissive; `resolve_references` and the canonical-text
  parse enforce the same strict rules as the file loader before any run directory is claimed.
- Strict loading rejects unknown bodies/phases, reset phases where timed ones are required,
  non-preceding phases, identical body pairs, world x/y, missing/reversed bounds,
  `max_over_phase` on `contact_duration`, unknown fields, and non-finite numbers.
- Replay never trusts recorded derived values. Numeric evidence and times must be finite
  before any tolerance arithmetic (`inf`, `-inf`, `nan`, and `1e999`-style overflow are
  differences, including when both sides are non-finite); finite values use the declared
  metric tolerance and worst-sample times use one verified model timestep.

## Remediation of supervisor findings R1–R3

- **R1 — overflowed recorded metrics falsely reproduced as PASS.** Fixed in
  `cadkit/physics/replay.py`: `_finite_number` plus non-finite rejection before tolerance
  arithmetic for every compared value, evidence number and time. The remediation review then
  demonstrated a further bypass — the time tolerance was read from the mutable
  `summary["plan"]["timestep_s"]`, so a tampered `1e999` (or `1e6`) plan timestep widened it
  without bound. `replay_run` now uses `float(model.opt.timestep)` from the verified compiled
  model and raises `ReplayError` if it is not finite and positive.
- **R2 — opt-in band ignored S0 speed/contact gates.** Fixed in `cadkit/physics/evaluate.py`:
  the band now applies to max-over-phase `body_speed` and `contact_duration` maxima with the
  same `_near_upper` rule, plus structured bound/band evidence. Default off, zero-bound and
  true-breach semantics preserved; legacy `body_speed` end semantics unchanged.
- **R3 — typed forbidden combinations emitted PASS locks their own loader rejects.** Fixed by
  `CheckSpec.validate_semantics()` called from `resolve_references`, `AcceptanceSpec`
  validation, and a strict-loader parse of the selected canonical scenario/acceptance text in
  `_run_with_spec` before `_claim_run_dir`. The file loader was not weakened.

Fresh rerun of the unchanged supervisor probe (copy at
`out/mujoco-m5a-s0-checks/remediation-probe/probe_s0_checks.py`, byte-identical to the
original; fresh outputs under `remediation-probe/s0-probes/`):

| Probe | Before | After |
|---|---|---|
| Untampered base + replay | PASS / reproduced true | PASS / reproduced true (control) |
| 20% band on speed 0.8826/0.9807 m/s and contact 0.29/0.3222 s | PASS (band ignored) | INCONCLUSIVE for both |
| `1e999` recorded `pose.value` + `evidence.translation_m` | replay PASS, reproduced true, no differences | INCONCLUSIVE, reproduced false, differences name both non-finite fields |
| Typed `frame="world", axis="x"` | run PASS, replay `ReplayError` | `ScenarioError` before a run directory; no evidence written |
| Typed `contact_duration(window="max_over_phase")` | run PASS, replay `ReplayError` | `ScenarioError` before a run directory; no evidence written |

The fresh `s0-probes/` directory contains only `base`, `baseline-replay`, `near`, `overflow`,
`overflow-replay` and `results.json`; the typed probes created no directories.

## Verification

All commands used `/Users/daniel_l_newman/.local/bin/uv run --frozen --extra physics ...`;
`uv.lock` is unchanged.

| Check | Command | Result |
|---|---|---|
| New focused tests | `pytest tests/test_cadkit_physics_relative_checks.py -q` | **58 passed**, exit 0, 2.56 s (`logs/relative-checks.log`) |
| Physics regressions (remediation) | `pytest tests/test_cadkit_physics_*.py -q` | **546 passed, 1 warning**, exit 0, 125.63 s (`logs/physics-regressions-remediation-final.log`) |
| Supervisor probe rerun | `python out/mujoco-m5a-s0-checks/remediation-probe/probe_s0_checks.py` | exit 0, table above (`remediation-probe/probe-run.log`, `results.json`) |
| Baseline references | Supervisor at `c76a1df` 488 passed; pre-remediation 529 passed | 488 + 58 new = 546 |
| Frozen `acceptance.toml` | `518a45ff…ff6ca2` | unchanged |

Live behaviour exercised: real `drop_box` runs with max-over-phase pose, local and world
translation, speed and contact checks; a reversed-gravity lift; same-runtime replay of PASS,
INCONCLUSIVE and world-frame runs (`reproduced=True`, no differences); tampered `summary.json`
records (positive and negative overflow, infinite and huge plan timestep, tampered times) not
trusted. The yaw-90 counterexample, common-rotation zero drift (old 1.414214 mm result
rejected), fixed-coordinate invariance, true/no motion and the 0.4 mm fall/lift signed bounds
are covered; exact rotation-only and near-band values use synthetic snapshot telemetry fed to
the public evaluator. No real hinge/rotation assembly was run.

The full CAD suite was not run; the handoff defers it until final shared M5a-1 changes.

## Independent tests

`tests/test_cadkit_physics_relative_checks.py` was written and extended by a separate OMP task
worker from the approved semantics and public APIs. Its report is
`out/mujoco-m5a-s0-checks/test-worker-report.md`, including the remediation R1–R3 section. It
covers the required yaw/order, common-rotation, invariance, signed-drop, loader-rejection,
every-step interior maxima, multi-point summed contact, interruption/boundary, zero-contact,
near-band, real run/replay and tampered-record cases, the review-fix regressions, and the
R1–R3 remediation regressions (17 cases), including the tampered-plan time-tolerance case.

## Code review

Configured ordinary review with the `reviewer` role; no substitute or override. Native
transcript: `history://S0ChecksReview`, `history://S0RemediationReview`; exported
`out/mujoco-m5a-s0-checks/reviewer-transcript.md` and `reviewer-report.md`. The Supervisor
independently verified the actual model attribution for the first review (59 assistant
messages, all `anthropic/claude-opus-5-5`, transcript SHA256
`3a89d4c9953edf2e70096394c65e7a6f168dc518909b7f8e4f72aeff419368ef`, retained with the
Supervisor's `reviewer-verification.json`). The harness transcript does not itself expose a
provider model string, so this report cites the Supervisor's attribution rather than claiming
an independent observation.

- Round 1 (original packet): target (a) `ca9a305..c76a1df` approve with findings, target (b)
  request changes (F1–F5). All fixed and re-probed; round 2 approved.
- Round 3 (remediation): R2 and R3 confirmed fixed; R1 fixed for compared values but a
  remaining demonstrated bypass was found (unverified `plan.timestep_s` widening the replay
  time tolerance). Fixed as described above and covered by a new regression test.
- Round 4 (final remediation verification): **approve with findings**, overall correctness
  correct. The reviewer independently re-probed the bypass with `plan.timestep_s` set to
  `1e999`, `1e6`, `1e-30` and `-1` plus tampered pose times; every case was INCONCLUSIVE with
  `reproduced=false` and all four time differences named, while a legitimate 0.5 ms time drift
  still replayed PASS. It re-ran the focused file (58 passed) and confirmed logs, probe
  results, manifests, frozen inputs and the attribution caveat. Its two P3 findings were
  report wording only (the remediation case count is 17, and this report is in the modified
  list); both are corrected here. No remaining code defect was found in scope.
- Remaining review observations: the typed `CheckSpec` constructor is intentionally
  permissive (rejection happens at reference resolution/execution); legacy `_compare_value`
  can raise `OverflowError` on a huge integer in old-style metrics, which fails closed rather
  than producing a false PASS; both are surfaced, not changed.

## Scope, manifests and frozen inputs

- Original packet manifests: `out/mujoco-m5a-s0-checks/before-manifest.json` (independent
  Supervisor baseline at `c76a1df`, 200 files) and the prior `after-manifest.json`
  (204 files), preserved as `before-remediation-manifest.json` with
  `manifest-diff-before-remediation.json`.
- Remediation manifests: `after-remediation-manifest.json` and `remediation-diff.json`.
  Modified by the remediation: `cadkit/physics/{evaluate,replay,runner,scenario}.py`,
  `tests/test_cadkit_physics_relative_checks.py` and this report; added: the Supervisor review
  document; removed: none; `uv_lock_unchanged=true`.
- No existing test was edited or weakened; the only earlier existing-test edit in the
  checkpoint (`test_project_physics_defaults_to_none`) was human-approved and remains as
  pulled. The two Supervisor documents and the Supervisor review were preserved.
- Frozen `projects/pocky/physics/acceptance.toml` raw SHA256:
  `518a45ffc4592ca602be4c33c59681038e43dedaa15b688312202c3a57ff6ca2` — unchanged.
- Diffs: `out/mujoco-m5a-s0-checks/s0-checks.diff` (cumulative against `c76a1df`),
  `pulled-checkpoint.diff` (`ca9a305..c76a1df`).

## Limitations and claims not made

- No Pocky collider, adapter, assembly, static preflight, scenario, S0 acceptance or
  simulation evidence was created. Handoff items 3–9, P0–P3, M6 and M7 are untouched.
- No M5a-1 completion, product verdict, dispensing result, physical reliability, calibration
  of PETG friction/spring/mass, or M7 claim is made.
- Replay determinism is same-runtime/same-platform and within `REPLAY_TOLERANCES`; a
  worst-sample time is compared within one verified model timestep.
- Synthetic snapshot telemetry covers exact rotation-only, signed-bound and near-band cases;
  live coverage uses `drop_box` (and a reversed-gravity variant), not a hinge assembly.
- Contact CSV rows are display evidence; checks gate on per-step telemetry.
- Full CAD suite deferred per the handoff; the pulled commit's 488-test claim was
  independently verified by the Supervisor.

## Next gate

Codex owns the next admission. A credible next step is the Pocky adapter/static/S0 increment
under a separate packet, which must not assume this packet's checks are product-accepted.
