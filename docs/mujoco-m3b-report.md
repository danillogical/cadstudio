# M3b report — mechanical fixture proof

Date: 2026-10-21. Packet: **M3b generic mechanics fixtures/validity/telemetry only**,
decision `dec_0mviavva9e5940f67ff9da7dc`, run `run_0mvi5dou92f2f6dc40f0d6379`.
Scope authority: `docs/mujoco-m3b-packet.md`; prior acceptance
`docs/mujoco-m3a-supervisor-review.md`.

No Pocky/armor CAD, no product adapter, no M4 scenario framework, no dependency change, no
provider/model/effort/fallback change. **M3b is not product success and not physical
calibration**: every physical input below is an assumed analytic-fixture number. S0 real
product support remains M5a.

---

## 1. Native plan (actual execution, not a label)

The configured `plan` role (`workbuddy-ai/deepseek-v4.1-flash:max`) was invoked once, with a
**short** prompt (no `@file`, no history dump), and returned an eight-step plan in 120 s.
Raw evidence: `/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m3b-native-plan-20261021/plan.txt`.

Plan as executed (abbreviated; full text in the artifact):

1. Apply the declared carriage mass through `PartSpec.mass_kg=0.25`; guard compiled
   `body_mass` equals it exactly — a mismatch is a bug, not a tolerance.
2. Frictionless deflection and release period vs `F/k` (1%) and `2π√(m/k)` (5%).
3. Separate friction/preload fixture with a dead band and `frictionloss/k` residual.
4. Stop under sustained input with declared SI compliance and a penetration budget.
5. Missing-input and missing-spring negatives that fail by name.
6. `jnt_dofadr`/`jnt_qposadr` separation and full force telemetry.
7. Validity guards: preflight, declared-vs-compiled equality, finiteness, warnings.
8. Base and half-dt convergence with solref fixed in absolute seconds.

**Deviations from the plan, with reasons:**

- Step 2's `F/k` tolerance: the plan said 1%; the packet's acceptance is 2%. The packet
  governs, and the measured error is 0.065%, so the looser number is not being leaned on.
- Step 2 measures the oscillation **centre over the push phase**, not a "steady state": an
  undamped carriage has no steady state. See §5.1.
- Step 8's transient-peak metric is **not asserted to converge**: it is a sampled maximum of
  a collision transient and oscillates with dt (482 / 383 / 435 / 444 µm at 1 / 0.5 / 0.25 /
  0.125 ms). It is instead bounded by a declared 1.0 mm transient budget, and the steady
  penetration — a real equilibrium — is what must converge. See §5.4 and §6.1 finding 3.

---

## 2. Completed work

`cadkit/physics/mechanics.py` (rewritten)

- `SLIDER_KG = 0.25` is now actually applied via `PartSpec.mass_kg` with `density_g_cm3=None`
  and `Source("assumed", ...)`, so the compiled carriage is 0.25 kg rather than the 6.349e-4 kg
  mass of the 8 mm decorative block (~394× lighter).
- Four separate fixtures: `slider_frictionless_spec` (no friction, no damping, gravity off),
  `slider_damped_spec` (frictionless but damped), `slider_friction_spec` (preload + Coulomb
  friction), `slider_stop_spec` (short range, declared stop compliance).
- Damping is **derived**: `slider_analytic_stiffness_damping()` = ζ·2√(km) = 4.9497 N·s/m at
  ζ = 0.7, giving a 4τ settle of 0.40 s inside the 0.60 s release window. The hinge damping
  is derived the same way (`hinge_damping_nm_s_per_rad`, ζ = 0.3) because a hand-picked
  0.02 N·m·s/rad is 88× critical for the arm's 6.38e-7 kg·m² inertia and is overdamped.
- `slider_friction_band()` predicts `reference + (F ± frictionloss)/k`; `slider_release_residual_bound()`
  predicts `frictionloss/k`; `stop_penetration_estimate_m()` predicts `F·tc²/m`.
- Deleted the dead `analytic_slider_band` shim (no remaining callers).

`cadkit/physics/mechanics_run.py` (rewritten)

- `_Recorder` resolves `jnt_qposadr`/`jnt_dofadr` by name, range-checks both against `nq`/`nv`,
  and records requested control, **actual** control, `actuator_force`, `qfrc_actuator`,
  `qfrc_spring`, `qfrc_damper`, `qfrc_constraint`, coordinate, velocity, energy, contacts.
- Validity guards: preflight budget before stepping; declared-vs-compiled equality for
  stiffness, `qpos_spring`, range, damping, frictionloss, solref, mass; per-step finiteness of
  state and actuation; per-step speed and energy bounds; every solver warning counter.
- Negatives are first-class trials whose named check must fail; `run_mechanics` marks a
  negative `ok` only when its named check is False **and** the run was otherwise valid.
- Status logic: any invalid trial or failed convergence → `INCONCLUSIVE`; valid but a physical
  check fails → `FAIL`; otherwise `PASS`.
- `_convergence` runs every fixture at `dt` and `dt/2` with identical physical parameters.

`cadkit/physics/schema.py` + `cadkit/physics/scene.py` (minimal, allowed change)

- `JointSpec.stop_timeconst_s` / `stop_dampratio`, validated finite/positive, emitted as
  MJCF `solreflimit` in **absolute SI seconds**. This is what makes a stop test a physical
  test: MuJoCo's default 0.02 s is soft enough that 2 N holds this carriage 20 mm past a
  20 mm range. `None` keeps the compiler default and is documented as unusable for a stop test.

`cadkit/cli.py`

- `_physics_mechanics` updated to the new summary shape (base/half steps, negatives,
  convergence). Exit code is `EXIT_CODES[status]`, verified equal to PASS/0.

`tests/test_cadkit_physics_mechanics.py`

- 55 tests: schema contracts, analytic predictions, compiled-mass/stop-compliance/indexing/
  telemetry regressions, live fixtures, guard violations, and convergence.

---

## 3. Commands and results

All from `/Users/daniel_l_newman/src/cadstudio` with `/Users/daniel_l_newman/.local/bin/uv`.
MuJoCo 3.16.0, Python 3.12, macOS arm64.

```
PATH="$HOME/.local/bin:$PATH" uv run pytest tests/test_cadkit_physics_mechanics.py -q
56 passed in 2.45s

PATH="$HOME/.local/bin:$PATH" uv run pytest tests/test_cadkit_physics_scene.py \
  tests/test_cadkit_physics_hollow.py tests/test_cadkit_physics_units.py \
  tests/test_cadkit_physics_export_cli.py tests/test_cadkit_physics_optional.py \
  tests/test_cadkit_physics_gravity_drop.py -q
204 passed in 53.35s

PATH="$HOME/.local/bin:$PATH" uv run pytest tests/ -q
428 passed in 355.55s (5:55)

PATH="$HOME/.local/bin:$PATH" uv run cad physics mechanics
→ exit 0, {"status": "PASS", "scenario": "m3_mechanics",
           "detail": "base step 0.001 s, half step 0.0005 s"}
→ wrote out/fixtures/m3_mechanics/physics/20261021T173652Z/
```

The full CAD suite was re-run because `cadkit/cli.py` and `schema.py` are shared files; it
passes, so the M3a supervisor's 405-test baseline is preserved and grew by the 23 new tests
(405 → 428). All numbers above are the post-review run.

### 3.1 Live trial results (base step 1 ms)

| Trial | Check | Measured | Prediction / tolerance |
|---|---|---|---|
| frictionless_deflection | compiled mass | 0.25 kg | declared 0.25 kg (exact) |
| | deflection | centre 0.0200130 m | `F/k` 0.0200000 m, **0.065%** vs 2% |
| | restoring force | peak \|qfrc_spring\| 2.000 N | spring, not contact |
| frictionless_period | period | 0.44428817 s | `2π√(m/k)` 0.44428829 s, **0.00003%** vs 5% |
| damped_return | return | residual 0.0416 mm | ≤ 0.1 mm |
| | settled | 0.00025 m/s | ≤ 0.02 m/s |
| friction_static | static band | 0.0303298 m | declared band [0.029000, 0.031000] m |
| | release residual | 0.0942 mm from springref | ≤ `frictionloss/k` = 1.000 mm |
| | peak energy | 0.01035 J | analytic ½k(q−ref)² = 0.01030 J |
| stop_loaded | stop reached | 0.020004 m > 0.020000 m | drive 2 N > k·range |
| | steady penetration | **0.0036 mm** | ≤ **0.1 mm** budget; estimate `F·tc²/m` = 0.032 mm |
| | peak penetration | 0.4825 mm | ≤ **1.0 mm** budget |
| | stop engaged | \|qfrc_constraint\| = 2.000 N | stop carries the drive |
| hinge_oscillator | period | 0.03550034 s | analytic 0.03550003 s, 0.001% vs 5% |
| | compiled inertia | 6.384512e-07 kg·m² | analytic 6.384512e-07 (mj_fullM) |
| hinge_damped | period | 0.03721428 s | damped analytic 0.037214144 s, ζ = 0.3 |

All seven valid trials report every solver warning counter at 0 and remain finite.

### 3.2 Negatives — each fails its own named check

| Negative | Named check | Result |
|---|---|---|
| `missing_input` (ctrl = 0) | `static_band` | **False** — x = 0.009453 m vs band [0.029, 0.031]; valid run, failed check |
| `missing_spring` (spring=None) | `returns_to_home` | **False** — 49.99 mm vs 0.1 mm; also `spring_restoring_force_present` False (0 N) |

Both are `valid: True` with `ok: True` as negatives: they are genuine dynamic outcomes, not
crashes and not relabelled successes.

### 3.3 Convergence, base vs half dt

| Trial | Metric | Base | Half | Criterion | OK |
|---|---|---|---|---|---|
| frictionless_deflection | centre | 0.0200129861 | 0.0199904745 | Δ ≤ 0.1 mm (Δ = 0.0225 mm) | yes |
| frictionless_period | period | 0.4442881679 | 0.4442897946 | rel ≤ 1% (3.7e-6) | yes |
| damped_return | residual | 3.98418e-05 | 3.98418e-05 | Δ ≤ 0.1 mm (5.3e-14) | yes |
| friction_static | x_after_push | 0.0303297559 | 0.0303297525 | Δ ≤ 0.1 mm (3.4e-12) | yes |
| stop_loaded | steady penetration | 3.5654e-06 | 3.5654e-06 | Δ ≤ 0.1 mm (2.4e-15) | yes |
| stop_loaded | peak penetration | 0.4825 mm | 0.3829 mm | Δ ≤ 1.0 mm transient budget (0.0996 mm) | yes |
| hinge_oscillator | period | 0.0355003403 | 0.0355000484 | rel ≤ 1% (8.2e-6) | yes |

`solreflimit` is identical in both runs (`test_stop_compliance_does_not_scale_with_timestep`),
so refinement changes integration resolution only.

---

## 4. Raw artifacts

Committed evidence run: `out/fixtures/m3_mechanics/physics/20261021T173652Z/`, produced by
`PATH="$HOME/.local/bin:$PATH" uv run cad physics mechanics` (the runner mints the run id and
refuses to write into a non-empty directory). Regenerate with
`uv run cad physics mechanics --out <empty-dir>`.

```
summary.json                        strict JSON, no NaN/Infinity tokens
report.md                           human-readable, per-trial tables + convergence
base/  half/  negatives/            per-trial scene.xml + assets + report.json
trace_frictionless_deflection.csv   time_s,phase,qpos,qvel,ctrl_requested,ctrl_actual,
trace_frictionless_period.csv         actuator_force,qfrc_actuator,qfrc_spring,qfrc_damper,
trace_damped_return.csv               qfrc_constraint,energy_j,contacts
trace_friction_static.csv
trace_stop_loaded.csv
trace_hinge_oscillator.csv
trace_hinge_damped.csv
trace_missing_input.csv
trace_missing_spring.csv
```

`tests/test_summary_is_strict_json` parses the artifact with `parse_constant` raising, so a
non-finite value cannot slip into the evidence.

---

## 5. Findings and deviations worth review

1. **An undamped fixture has no steady state.** `run_frictionless_deflection` measures the
   mean of `qpos` over the push phase, which is exactly `F/k` for `x(t) = (F/k)(1−cos ωt)`
   provided the push is an integer number of periods. The push is therefore
   `round(PUSH_S/T)·T = 0.44429 s`, not a fixed 0.30 s. A first attempt that averaged the
   *release* phase measured 0.0001 m (the release oscillates about the spring reference, 0),
   and a second that averaged a fractional number of cycles measured 0.0242 m (21% high);
   both were caught by the check, and both were fixed by correcting the measurement window
   rather than the tolerance.
2. **Phase means are accumulated per integration step, not per telemetry row.** The 2 ms
   telemetry grid aliases a 0.444 s oscillation and biased the centre by 7.7e-5 m — the same
   size as the 1e-4 m convergence tolerance, which would have been misread as a timestep
   effect. `_Recorder.phase_mean` sums every step instead; the convergence delta fell from
   8.97e-5 m to 2.25e-5 m.
3. **The stop budgets had to be tightened after review to discriminate.** At 0.5 mm / 5 mm the
   compiler-default compliance passed both (0.3144 mm / 4.28 mm), which is exactly the failure
   the packet forbids. They are now 0.1 mm / 1.0 mm and a regression test fails if the default
   ever passes again. See §6.1 finding 1.
4. **Transient peak penetration is reported against a transient tolerance, not asserted to
   converge.** The first-impact peak is a sampled maximum and oscillates with dt (482 / 383 /
   435 / 444 µm at 1 / 0.5 / 0.25 / 0.125 ms). It is bounded by a physical budget and compared
   within 1.0 mm; steady penetration, a true equilibrium, is still required to agree within
   0.1 mm.
5. **`qfrc_constraint` is not a stop detector.** MuJoCo routes joint `frictionloss` through
   `qfrc_constraint`, so a friction fixture has nonzero peak constraint by construction
   (measured 0.05 N). The check was replaced by a positional one: travel must stay inside the
   declared range, so the residual is demonstrably friction rather than a stop.
6. **Stop compliance is declared only by the stop fixture.** `_slider_bodies` takes
   `stop_timeconst_s=None` by default, so the frictionless, damped and friction fixtures emit
   no `solreflimit`. Declaring a compliance on a fixture that can never reach its limit would
   silently bless a stop nobody validated; a future range change would then engage an
   unvalidated stop. Verified: only `slider_stop_spec` carries `stop_timeconst_s=0.002`.
7. **`mass_kg` and `density_g_cm3` are mutually exclusive in practice.** `part_inertial`
   rescales the tensor by `mass_kg / (volume·density)`, so declaring both would silently
   imply an absurd density. `_massed_block` sets `density_g_cm3=None` and records
   `Source("assumed", ...)`.

---

## 6. Independent review

Reviewer agent `M3bReview` (read-only; instructed to re-execute every trial live and to sweep
dt from 2 ms to 3.1e-5 s, push durations 0.10–0.99 s, and the compiler-default stop). It
verified claims 1–4 and 6–8, and raised one major, three minor and one nit finding. **All five
were acted on**; none was rejected.

### 6.1 Findings and resolutions

| # | Severity | Finding | Resolution |
|---|---|---|---|
| 1 | **major** | The 0.5 mm steady / 5 mm peak stop budgets did **not** discriminate: the MuJoCo default compliance (tc = 0.02 s) measured 0.3144 mm / 4.28 mm and **passed both**. The comment claiming the budget "still fails a compiler-default stop" was false. | Budgets tightened to 0.1 mm / 1.0 mm, which sit between the declared (0.0036 mm / 0.48 mm) and default (0.3144 mm / 4.28 mm) values. Re-measured: default now **FAILS both** by 3.1x and 4.3x; declared passes with 28x and 2.1x margin. New regression `test_stop_budget_discriminates_against_the_compiler_default` fails if the gate ever accepts the default again. Comment rewritten with both measured rows. |
| 2 | minor | The static band passed by transient phase luck: at `PUSH_S = 0.30` the residual transient amplitude (1.54 mm) exceeded the 1.0 mm band half-width, so 14 of 90 swept durations fell outside the band. | `PUSH_S` raised to 0.60 s, where the transient is 0.08 mm (12x under the half-width). `friction_static` x moves 0.0303161 → 0.0303298 m, still inside the band, now by statics rather than by phase. |
| 3 | minor | `peak_penetration_m` used a bespoke `nonincreasing` criterion, which a non-converging metric passes; refinement gives 482/383/435/444 µm, i.e. it oscillates. | `nonincreasing` removed from `_convergence` entirely. The peak is now compared against an explicit 1.0 mm transient tolerance and separately bounded by `STOP_PEAK_PENETRATION_M` in the trial. §5.4 and §3.3 updated to state this honestly rather than claiming convergence. |
| 4 | minor | `_Recorder.energy()` used `0.5*k*q²`, ignoring `qpos_spring`; for the preloaded fixture this overstated energy by 123% (0.02298 vs 0.01032 J) and exported the wrong value as evidence. | Energy now uses `(q - qpos_spring)`. Measured peak energy 0.01035 J vs analytic 0.01030 J. `peak_energy_j` is now surfaced as a metric so the corrected value is visible in the artifact. |
| 5 | nit | Dead code: `_accumulate` kept an unused `qabs` and discarded `v`/`e`; `peak_actuator_force`/`peak_actuation` were tracked and never read; `no_soft_limit_excursion` duplicated `steady_penetration_within_declared_budget` verbatim; `x_after_release_m` was recorded but never asserted. | `qabs` and the `v, e` parameters deleted; the two unused peaks deleted; the duplicate check replaced by `released_inside_range`, which asserts the post-release position (0.019693 m, inside ±0.02 m) and so finally tests the packet's "and again after release" requirement. |

### 6.2 Additional corrections from follow-up review

| Item | Finding | Resolution |
|---|---|---|
| Stop compliance scope | `_slider_bodies` declared `stop_timeconst_s=STOP_TIMECONST_S` on **every** slider, including the three fixtures that never reach their limit, silently blessing a stop no fixture validated. | Now a parameter defaulting to `None`; only `slider_stop_spec` declares it. Verified across all four specs and re-ran the suite: results identical. |
| Friction docstring | Claimed "motion needs the drive to exceed preload + friction", which is false: with reference 0.010 m the spring already pushes 0.5 N at q = 0, so the carriage moves with zero drive. | Docstring corrected to state that a spring reference is a rest coordinate, not a stop; the band is the equilibrium interval `reference + (F ± frictionloss)/k`, and home is the reference, not zero. |
| Report §1 deviation 3 | Still described the removed `non-increasing` peak criterion. | Rewritten to the actual treatment: the peak is not asserted to converge (482/383/435/444 µm with dt) and is bounded by the declared 1.0 mm transient budget. |

### 6.3 Reviewer non-findings, recorded

- `analytic_slider_band` no longer exists; no back-compat shims remain (it was deleted in this packet).
- Guard tightness: `SLIDER_VMAX_M_S` / `SLIDER_EMAX_J` are the derived free-flight values and the
  stop run reaches 99.0% / 98.0% of them, leaving under 0.1% headroom. Left as-is: they are
  derived, they do not falsely trip at any tested dt, and loosening a guard to create headroom
  would be the wrong direction. Flagged here as a brittleness risk if the integrator changes.
- `qfrc_friction` does not exist in MuJoCo 3.16; joint friction lands in `qfrc_constraint`. The
  telemetry records `qfrc_constraint` and the trial measures peak constraint (0.05 N) as the
  friction evidence, which is the honest representation of what the solver exposes.
- All contacts are zero in every trace, so no fixture's restoring force comes from contact.

---

## 7. Unresolved issues

1. **All physical inputs are assumed, not measured.** Mass, stiffness, preload, frictionloss
   and stop compliance are declared analytic-fixture values. M7 calibration is still unverified
   and nothing here is evidence about the real Pocky dispenser.
2. **The stop compliance is a fixture declaration, not a PETG property.** `STOP_TIMECONST_S =
   0.002` was chosen so the steady penetration is sub-millimetre; the real printed part's
   compliance is unknown and must not be inferred from it.
3. **No product adapter exists.** S0 (real product support/stability) is M5a and remains open;
   the user's reported two-post instability has not been simulated.
4. **`SLIDER_PRELOAD_M` is a fixture input with no physical referent.** It exists so the
   static band has a nonzero centre; it is not derived from any real preload.
5. **Friction is modelled as a single Coulomb `frictionloss`.** Velocity-dependent or
   stick-slip behaviour, and any difference between static and kinetic friction, is out of
   scope for M3b.
6. **Provider interruption risk persists.** The M3a attempt died on an HTTP400 during a long
   planning request. This turn used a short plan prompt and narrow reads; no routing change.
