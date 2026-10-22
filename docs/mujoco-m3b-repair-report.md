# M3b repair report — gating, refsafe, control telemetry, settled statics

Supervisor follow-up: this report describes OMP's pre-review source. Additional
non-unit-gear telemetry, nonfinite evidence serialization, passive-force guards and
generic joint-stop validation were corrected by Codex; final455tests pass. See
`docs/mujoco-m3b-supervisor-acceptance.md` for the authoritative final result. In
particular the actuator_force/gear control formula stated below was incorrect and
has been superseded for cadkit's unity-gain motors.

Date: 2026-10-21. Packet: **M3b remediation of findings 1–4 only**, decision
`dec_0mviemrs686ee2cc3f112e20b`, run `run_0mvi5dou92f2f6dc40f0d6379`.
Scope authority: `docs/mujoco-m3b-supervisor-review.md`.

Preserved prior state: `/Users/daniel_l_newman/.omp-bridge/backups/cadstudio-mujoco-m3b-partial-20261021T174604Z/`.
No M4, no product adapter, no CAD edit, no dependency change, and no global
provider/model/effort/fallback change. M0–M2b and M3a stay accepted; S0 real housing
instability remains M5a; physical calibration remains unverified.

---

## 1. Native plan — two provider interruptions, recorded honestly

The configured `plan` role was invoked twice with **short** prompts (no `@file`, no history
dump). Both calls returned only the word `Working...` and no plan text:

- attempt 1, 150 s timeout → `/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m3b-repair-plan-20261021/attempt1.txt`
- attempt 2, 120 s timeout, shorter prompt → `.../attempt2.txt`

No routing, model, effort or fallback setting was changed, per the packet. Rather than retry a
third time, the turn proceeded on the inspectable plan in
`.../plan-derivation.txt`, which reconciles the supervisor's four numbered findings into
concrete changes. **This is a documented deviation**: the planning step did not produce model
output, so the plan is the orchestrator's, derived from review evidence rather than from the
`plan` role.

---

## 2. The four fixes

### 2.1 Finding 1 — PASS while the half-dt trial was invalid

`run_mechanics` aggregated validity and physical success from `base.values()` only. The half
set fed a subset of convergence numbers and was then dropped from the summary entirely, so an
invalid or physically wrong half run could not be seen or gated.

Now:

- `all_positive` = base + half, keyed `base/<name>` and `half/<name>`.
- validity = every positive valid **and** convergence OK **and** every negative correctly failed.
- physical success = every check of every positive trial, in both sets.
- `half_trials` and `negative_trials` are separate, fully populated summary blocks, and trace
  CSVs are written for all three sets as `trace_base_<name>.csv`, `trace_half_<name>.csv` and
  `trace_<name>.csv` (negatives). The base/half prefixes are not cosmetic: the two sets share
  trial names, so an unprefixed filename let the half run silently overwrite the base evidence.
- a `gating` block records `positive_trials_gated`, `base_invalid`, `half_invalid`,
  `base_failed_checks`, `half_failed_checks`, so the decision is inspectable rather than implied.

Regressions (`tests/test_cadkit_physics_mechanics.py`):

| Test | What it does |
|---|---|
| `test_half_dt_invalidity_cannot_yield_pass` | runs real base/half physics, marks **only** half `hinge_damped` invalid, asserts `INCONCLUSIVE`; also asserts `convergence["rows"]` is **identical** to a clean run, so the status change is attributable to gating, not to disturbed physics |
| `test_half_dt_failed_physical_check_cannot_yield_pass` | forces half `hinge_damped:period` to fail, asserts `FAIL`; asserts convergence rows **and** the half trial's metrics are identical to the clean run |
| `test_both_sets_are_persisted_with_traces` | 7 base + 7 half trials, each with checks, warnings and its **own** CSV; base dt 1 ms, half dt 0.5 ms; asserts both prefixed files exist so a name collision cannot silently drop one |
| `test_half_dt_hinge_is_in_convergence` | **both** hinges are compared (`hinge_oscillator` and `hinge_damped`), so the convergence claim is not silently narrowed |

### 2.2 Finding 2 — equal stored `solref` did not mean equal effective physics

MuJoCo's refsafe safety floor makes the **effective** constraint time constant
`max(solref[0], 2*dt)` when `mjDSBL_REFSAFE` is clear. The runner accepted `dt = 0.002 s`
with a declared `tc = 0.002 s`, so the effective compliance silently doubled while the stored
value still read `0.002`.

Reproduced independently before the fix (same state, `q = 0.0201 m`, `ctrl = 2 N`):

| dt | stored `solref` | constraint force |
|---|---|---|
| 0.001 s | (0.002, 1) | **−7.423890582 N** |
| 0.002 s | (0.002, 1) | **−3.207472645 N** |

Fix — reject before any stepping, never soften the model:

- `refsafe_enabled(mujoco, model)` reads `mjDSBL_REFSAFE` from `opt.disableflags`.
- `effective_timeconst(...)` returns `max(stored, 2*dt)`.
- `check_timeconst_resolvable(...)` raises when `effective > declared`, naming the floor, the
  maximum usable step and why lowering the constant or disabling refsafe is unacceptable.
- `_compile(declared_timeconst=...)` calls it **before** the first `mj_step`; wired for the
  stop fixture, whose compliance is the physical constant under test.
- The trial records `stop_timeconst_effective_s` and `stop_timeconst_resolved`, and marks
  itself invalid if the effective value differs from the declared one.

Observed:

```
dt=0.001  ACCEPTED  steady penetration 3.5654 um, effective tc 0.002 (resolved)
dt=0.002  REJECTED  joint stop: declared time constant 0.002 s is below MuJoCo's refsafe
                    floor of 2*dt = 0.004 s at timestep 0.002 s ...
```

Regressions: `test_unresolvable_stop_compliance_is_rejected_before_stepping`,
`test_default_steps_resolve_the_declared_stop_compliance`,
`test_same_state_limit_force_agrees_at_the_supported_pair` (1 ms vs 0.5 ms identical to 1e-12).
The declared physical constant and refsafe are untouched; the default 1 ms / 0.5 ms pair
remains valid and its results are unchanged.

### 2.3 Finding 3 — raw control mislabelled as "actual clamped control"

MuJoCo clips the applied signal internally without rewriting `data.ctrl`, so the old column
labelled `ctrl_actual` read `1e6` for an over-request while the force was correctly `2 N`.

`TRACE_HEADER` now carries three distinct quantities plus the force:

| column | meaning |
|---|---|
| `ctrl_requested` | what the caller asked for |
| `ctrl_stored` | the raw value in `data.ctrl`, **never rewritten** |
| `ctrl_effective` | the signal actually applied, recovered as `actuator_force / gear` |
| `actuator_force` | the motor force after the solver's own limiting |
| `qfrc_actuator` | the generalized force that reached the joint (`gear * actuator_force`) |

`data.ctrl` is not rewritten; the effective value is *derived* from the force the actuator
actually produced, which is evidence rather than cosmetics.

Regression `test_over_request_distinguishes_stored_effective_and_applied`: with `ctrl = 1e6`,
`ctrl_stored` stays `1e6`, while `ctrl_effective`, `actuator_force` and `qfrc_actuator` are all
`<= 2 N`, and `ctrl_effective == actuator_force` at gear 1.

### 2.4 Finding 4 — settled statics, reference-centred period, uniform guards

**Settled statics (the missing packet requirement).** The damped trial now has a named check
`settled_statics_matches_force_over_k`: `|x_after_push − F/k| / (F/k) <= 2%`, with the
end-of-push speed as settled evidence.

```
settled x 0.019960 m vs F/k 0.020000 m (0.20%, tolerance 2%)
  at end-of-push speed 2.31e-04 m/s (<= 0.02 m/s)
```

This replaces the previous one-sided `x_after_push > 0.5*F/k` as the statics proof. The
undamped oscillation-centre check `deflection_matches_force_over_k` (0.06%) is **kept** and
documented as additional dynamic evidence, not as steady state.

**Reference-centred period.** A released undamped slider oscillates about the **spring
reference**, not about `F/k`: `F/k` is the centre only while the drive is applied. Crossings
are now measured about the compiled `qpos_spring`, and the reference and resulting centre are
recorded:

```
measured 0.444288310 s vs 2*pi*sqrt(m/k) 0.444288294 s (3.6e-08 relative)
release_reference_m 0.0, release_centre_m 1.5e-05
```

**Uniform guards across slider and hinge.** `run_hinge` previously hand-rolled its loop and
therefore had none of the recorder's guarantees. It now runs through `_Recorder`, which gains:

- `qacc` finiteness (a NaN acceleration can leave `qpos`/`qvel` finite for a step),
- control-input finiteness,
- the existing `qpos`/`qvel` and generalized-force finiteness,
- speed and energy bounds, and every solver warning counter,
- timestamps in every invalid reason (`... at t=0.123 s`) so a failing artifact is diagnosable
  without re-running.

`_Recorder` also takes `inertia_kg_m2`, because energy for a hinge must be `½Iω² + ½k(q−ref)²`
with the effective inertia from `mj_fullM`; using a linear mass would compute the wrong
quantity. `HINGE_EMAX_J = 2·½kA²` was added alongside the existing speed bound. The hinge's
`qfrc_spring` column is now located via `SPRING_COL = TRACE_HEADER.index("qfrc_spring")`
instead of a hard-coded index, so a header change cannot silently read a neighbour.

---

## 3. Commands and results

All from `/Users/daniel_l_newman/src/cadstudio`, `/Users/daniel_l_newman/.local/bin/uv`,
MuJoCo 3.16.0, Python 3.12, macOS arm64.

```
PATH="$HOME/.local/bin:$PATH" uv run pytest tests/test_cadkit_physics_mechanics.py -q
72 passed in 10.83s

PATH="$HOME/.local/bin:$PATH" uv run pytest tests/test_cadkit_physics_scene.py \
  tests/test_cadkit_physics_hollow.py tests/test_cadkit_physics_units.py \
  tests/test_cadkit_physics_export_cli.py tests/test_cadkit_physics_optional.py \
  tests/test_cadkit_physics_gravity_drop.py tests/test_cadkit_physics_mechanics.py -q
220 passed in 64.20s

PATH="$HOME/.local/bin:$PATH" uv run pytest tests/ -q
444 passed in 367.70s (6:07)

PATH="$HOME/.local/bin:$PATH" uv run cad physics mechanics
→ exit 0, {"status": "PASS", "scenario": "m3_mechanics",
           "detail": "base step 0.001 s, half step 0.0005 s"}
→ wrote out/fixtures/m3_mechanics/physics/20261021T181756Z/
```

The **full suite was re-run**, because this packet touches a shared file: `schema.py` now
requires `contact_timeconst_s >= 2*timestep_s`, which every scene in the repo passes through.
Result **444 passed, 0 failed** (428 at the start of this packet, +16 mechanics tests).
Shared files touched: `cadkit/cli.py` (mechanics handler only), `cadkit/physics/mechanics_run.py`,
and the one `schema.py` validation branch. `scene.py` and every CAD/armor/pocky module are
unchanged, so no CAD geometry or model behaviour is in the blast radius — and the passing full
suite measures that rather than assuming it.

### 3.1 Gating evidence (base + half, all 14 gated)

```
positive_trials_gated: base/{damped_return,friction_static,frictionless_deflection,
                              frictionless_period,hinge_damped,hinge_oscillator,stop_loaded}
                       half/{...same seven...}
base_invalid: []      half_invalid: []
base_failed_checks: [] half_failed_checks: []
convergence: ok (7 rows)
```

### 3.2 Trial results (base dt = 1 ms; half set reports the same checks)

| Trial | Check | Measured |
|---|---|---|
| frictionless_deflection | deflection (dynamic centre) | 0.020013 m vs 0.020000 (0.06%) |
| frictionless_period | period | 0.444288310 s vs 0.444288294 (3.6e-08) |
| damped_return | **settled statics** | 0.019960 m vs 0.020000 (0.20%), speed 2.31e-04 m/s |
| | return / settled | 0.0398 mm ≤ 0.1 mm; 2.3e-04 m/s ≤ 0.02 |
| friction_static | static band | 0.030330 m in [0.029, 0.031] |
| | release residual | 0.0942 mm ≤ 1.000 mm |
| stop_loaded | steady penetration | 0.0036 mm ≤ 0.10 mm budget |
| | peak penetration | 0.4825 mm ≤ 1.00 mm budget |
| | effective compliance | 0.002 s, resolved |
| | released inside range | 0.019693 m in [−0.02, 0.02] |
| hinge_oscillator | period / inertia | 0.03550040 s (1.0e-05 rel); 6.384512e-07 kg·m² |
| hinge_damped | period | 0.03721369 s vs 0.03721414 (1.2e-05 rel) |

Routing the hinge through `_Recorder` moved its telemetry onto the shared 2 ms sampling grid
(18 samples per 35.5 ms period instead of 71). The measured period was re-checked for that
regression: 0.03550040 s against 0.03550003 s, a 1.0e-05 relative error, so the coarser grid
did not degrade the measurement.

### 3.3 Negatives (each fails its own named check; runs stay valid)

- `missing_input`: `static_band` **False** (x = 0.0095 m vs band [0.029, 0.031]).
- `missing_spring`: `settled_statics_matches_force_over_k`, `returns_to_home` and
  `spring_restoring_force_present` **False** (49.99 mm, 0 N spring).

### 3.4 Convergence (base vs half)

All **eight** rows OK. The damped hinge is included as the supervisor required (rather than
narrowing the claim):

| trial | metric | base | half | delta |
|---|---|---|---|---|
| frictionless_deflection | centre | 0.0200130 | 0.0199905 | 2.25e-05 m |
| frictionless_period | period | 0.44428831 | 0.44428829 | 2e-08 s |
| damped_return | residual | 3.98418e-05 | 3.98418e-05 | 0 |
| friction_static | x_after_push | 0.0303298 | 0.0303298 | 3e-09 m |
| stop_loaded | steady penetration | 3.5654e-06 | 3.5654e-06 | 0 |
| stop_loaded | peak penetration | 4.825e-04 | 3.829e-04 | 9.96e-05 m (transient budget 1.0 mm) |
| hinge_oscillator | period | 0.03550040 | 0.03550005 | 1.51e-05 s |
| hinge_damped | period | 0.03721369 | 0.03721433 | 1.72e-05 s |

The transient `peak_penetration_m` row is compared within the declared 1.0 mm transient budget,
since a sampled impact maximum oscillates with dt (482 / 383 / 435 / 444 µm) and is not
asserted to converge.

---

## 4. Raw artifacts

`out/fixtures/m3_mechanics/physics/20261021T181756Z/`

```
summary.json        status, trials (base), half_trials, negative_trials, gating, convergence
report.md           per-trial tables + convergence
base/ half/ negatives/    per-trial scene.xml + assets + report.json
trace_base_<name>.csv     one per base-dt trial (7)
trace_half_<name>.csv     one per half-dt trial (7)
trace_<name>.csv          one per negative trial (2)
                          -- 16 traces total; base and half are prefixed because their trial
                             names are identical and an unprefixed name would let the half run
                             overwrite the base evidence
```

Trace columns: `time_s, phase, qpos, qvel, ctrl_requested, ctrl_stored, ctrl_effective,
actuator_force, qfrc_actuator, qfrc_spring, qfrc_damper, qfrc_constraint, energy_j, contacts`.

Plan evidence: `/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m3b-repair-plan-20261021/`
(`attempt1.txt`, `attempt2.txt`, `plan-derivation.txt`).

---

## 5. Independent review

Reviewer agent `M3bRepairReview` (read-only, instructed to re-execute every trial and probe the
rejection path) **returned a completed review** (22 min, confidence 0.88).

**Verdict: all four required fixes VERIFIED.**

| # | Fix | Reviewer verdict | Reviewer's own evidence |
|---|---|---|---|
| 1 | Both sets gated, half persisted | VERIFIED | Injected **four** distinct half-only faults through the real `_run_set` (invalid; one check failed; all five stop checks failed; metrics cleared) → INCONCLUSIVE / FAIL / FAIL / INCONCLUSIVE. No `base.values()`-only path remains |
| 2 | Unresolvable dt rejected pre-step | VERIFIED | Traced the call to `_compile` before any `MjData` step; confirmed boundaries 4e-3 accepted / 3.99e-3 rejected; CLI exits 3 on `--timestep 0.002`; refsafe flags never touched |
| 3 | Raw/effective/applied control | VERIFIED | `ctrl=1e6` → stored 1e6, effective 2.0, force 2.0, qfrc 2.0; `data.ctrl` never rewritten post-step |
| 4 | Settled statics, reference-centred period, guards | VERIFIED | Confirmed the 2% test is **two-sided**, and that it *discriminates* by re-deriving against a halved spring (fails at 96.9%); NaN `qacc`/`ctrl`/inf `qfrc_actuator` guards fire on both slider and hinge paths |

The reviewer also independently confirmed the trace-name collision fix it had flagged mid-review
(`trace_base_*` / `trace_half_*`), and that no hard-coded column index remains.

### 5.1 Reviewer defects, all fixed in this turn

| # | Severity | Defect | Fix |
|---|---|---|---|
| F-1 | nit | Module docstring still said "requested control vs **actual** control (`data.ctrl` after clamping)" — the exact false claim finding 3 removed, since MuJoCo never rewrites `data.ctrl` | Docstring now names `ctrl_requested` / `ctrl_stored` (raw, not rewritten) / `ctrl_effective` |
| F-2 | nit | `_render` iterated `summary["trials"]` (base only), so `report.md` — the artifact the repo's iteration loop names — silently omitted all half evidence. Verified with a poisoned half run: `summary.json` said INCONCLUSIVE while `report.md` had no half section | Renders base + half + negatives, keyed by set. Regression `test_report_shows_both_sets_and_negative_trials` |
| F-3 | nit | `all(c["ok"] ...)` over an empty check list is vacuously `True`; a trial reporting no checks would pass | Now `bool(t.checks) and all(...)`. Regression `test_a_trial_with_no_checks_cannot_pass` |
| F-4 | nit | CLI printed base and half trials with identical labels, indistinguishable to an operator | Prints the summary key (`base/...`, `half/...`). Regression `test_cli_labels_base_and_half_distinctly` |

The reviewer explicitly judged that none of the four could produce a false PASS, and that no
behavioural bug blocks acceptance. All four were documentation/reporting hygiene and are now
closed with regressions for the two that had a code path.

Orchestrator's own verification, for the supervisor to re-run independently:

| Supervisor finding | Verification performed here | Result |
|---|---|---|
| 1. False PASS on invalid half | Injected half `hinge_damped` invalidity after real physics; status `INCONCLUSIVE`, and `convergence["rows"]` identical to a clean run | Confirmed fixed |
| 1. False PASS on failed half check | Forced half `hinge_damped:period` False; status `FAIL`; half metrics identical to clean run | Confirmed fixed |
| 1. Half evidence discarded | 7 half trials in `half_trials` with checks/warnings, plus 7 `trace_half_*.csv`; 16 traces total | Confirmed fixed |
| 2. dt = 2 ms accepted | `run_stop(timestep_s=2e-3)` raises before any step, naming the 2*dt floor | Confirmed fixed |
| 2. Effective vs stored compliance | `effective_timeconst` recorded per stop trial; `stop_timeconst_resolved` true at 1 ms and 0.5 ms | Confirmed fixed |
| 2. Same-state force diverged | Same-state probe at 1 ms vs 0.5 ms now agrees to 1e-12 | Confirmed fixed |
| 2. Contact constants unguarded | `AssemblySpec.validate` now requires `contact_timeconst_s >= 2*dt`; default pair sits exactly on the floor and still passes | Fixed beyond the literal finding |
| 3. Raw control labelled actual | `ctrl=1e6` keeps `ctrl_stored=1e6`; `ctrl_effective`, `actuator_force`, `qfrc_actuator` all `<= 2 N`; `data.ctrl` never rewritten | Confirmed fixed |
| 4. No settled 2% statics check | Named `settled_statics_matches_force_over_k`, 0.20% with 2.31e-04 m/s settled-speed evidence | Confirmed fixed |
| 4. Period offset wrong | Crossings about compiled `qpos_spring` = 0; relative error 3.6e-08; reference and centre recorded | Confirmed fixed |
| 4. Hinge guards missing | `run_hinge` routed through `_Recorder`; `qacc`/input/force/energy finiteness, rotational `inertia_kg_m2`, `HINGE_EMAX_J` | Confirmed fixed |
| 1. Damped hinge omitted from convergence | Added as an eighth convergence row (1.72e-05 relative); the claim is no longer narrowed | Confirmed fixed |

A defect found by the orchestrator during this work, not by the supervisor: the trace writer
iterated `{**base, **half, **negatives}`, and because base and half trials share names the
half set **silently overwrote the base CSVs**. Traces are now `trace_base_*`, `trace_half_*`,
`trace_*`, and a test asserts all 16 exist. Without that, the "persist the half evidence"
requirement would have been satisfied on paper while destroying the base evidence.

Independence: the reviewer ran as a separate read-only agent that re-executed the trials and
wrote its own probes; it observed the file change mid-review and re-verified against the final
source. The supervisor's own review remains the required independent check before acceptance.

---

## 6. Remaining issues and limitations

1. **The native planning step produced no model output.** Two short `plan` calls returned only
   `Working...`. The plan used is therefore orchestrator-authored from review evidence. This is
   recorded rather than papered over; no routing change was made.
2. **All physical inputs remain assumed fixture values.** Mass, stiffness, preload,
   frictionloss and stop compliance are declared, not measured. M7 calibration is unverified.
3. **The stop compliance is a fixture declaration, not a PETG property.** `tc = 0.002 s` is
   chosen so the steady penetration is sub-millimetre and the refsafe floor is satisfied at the
   default step; the real part's compliance is unknown.
4. **Contact compliance is now guarded at the schema boundary.** `AssemblySpec.validate` used
   to require only `contact_timeconst_s >= timestep_s`; it now requires `>= 2*timestep_s`,
   matching the same refsafe floor that applies to joint limits. Previously a scene at
   `dt = 1 ms` with `tc = 1 ms` stored 1 ms while the solver used 2 ms, so the declared contact
   compliance was not the simulated one. The default 2 ms / 1 ms pair sits exactly on the floor
   and remains valid; every prior physics scene still passes (220 physics tests; 444 in the full suite). Regressions:
   `test_contact_timeconst_must_clear_the_refsafe_floor`,
   `test_contact_solref_is_not_softened_at_the_default_step`.
5. **Friction is a single Coulomb `frictionloss`.** No velocity dependence, no static/kinetic
   distinction.
6. **No product claim.** S0 real housing instability is M5a; no adapter exists.
