# M4a independent review: remediation required

Operation `op_0mvihnw126d5d0128e3ed9422`, host62419/generation2/session
`01a15fdf-0c0b-7779-8ca9-8b0897bdc18b`, successor2
`run_0mvihmvsm9f3be51a0fd22543`, first turn. M4a not accepted yet.

The typed loader, real generic execution, separate frozen criteria, failure artifacts,
state archive and independent review are substantive progress. Native plan output is
present. Configured WorkBuddy Step5 reviewer429 was disclosed; separate default-role
review occurred without changing configuration, and disabled security reviewer was
disclosed. Global OpenCode route remains human-authorized; no other role changes.

Supervisor independently ran49new scenario/M4a tests (13.88s), plus97mechanics/optional/
export-CLI regressions (40.66s), all passing. OMP reports504full-suite passes; that was
not repeated by the supervisor because demonstrated defects below already block this
increment. M3 remains accepted. No new product CAD/adapter/S0 or physical evidence.

## 1. Body kinematics/velocity can be stale at a new state timestamp: false PASS

Telemetry reads data.xpos/xipos/xquat and mj_objectVelocity immediately after mj_step,
but those derived fields are not necessarily recomputed at the final qpos/qvel. They
are then labeled with data.time, including boundary predicates.

Actual one-step Euler test: declared drop_box, dt0.001, reset then0.001s hold; body_speed
bound0.005m/s, no separate global speed bound. AssemblySpec is modified only to select
its supported Euler integrator through the fixture builder; actual MuJoCo dynamics run.
At t0.001, free qvel_z=-0.00980665m/s and per-step peak speed0.00980665, but the box body
snapshot velocity is0 and its body_speed predicate returns **PASS** (overall PASS).
Snapshot COM_z remains0.05m although final qpos_z=-9.80665e-6m implies COM_z0.04999019335m.
Raw run/probe at
`/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4a-supervisor-20261021/state/`.

Also the unconditional force_time=state_time-dt label is not a valid universal claim
for RK4's final-stage force arrays. Fix/document exact sampling semantics. Use coherent
body/COM/world velocity at the state timestamp, with observational recomputation/copies
if appropriate; do not rewrite physical state or silently change the integrator. Do
not blindly split mj_step1/mj_step2 and thereby replace requested RK4 with Euler.
Support declared integrators correctly or reject unsupported modes before stepping.
Test free and jointed moving bodies, state/pose consistency and analytic speed under
at least Euler and RK4. Preserve actual applied effort/contact evidence with accurately
defined force timestamps/stage provenance, and prove sampling does not perturb dynamics.

## 2. Reset-state validity/penetration is omitted: false PASS

record_initial appends data but never performs validity accumulation. All maxima start
at the first post-step solver state, so a bad starting configuration can disappear.

Actual RK4 probe lowers the real20mm drop cube from COM_z50mm to9.8mm with both shape
and collider moved consistently. Initial contact penetration is0.00020000000000000052m;
declared max_penetration_m=0.00019. After one0.001s step, recorded peak is only
0.00018799449367576902m, and the run reports **PASS** with no validity reasons.
This is an intentionally invalid generic fixture, not a Pocky measurement. Raw evidence:
`.../cadstudio-m4a-supervisor-20261021/initial-overlap/`.

Validate/accumulate reset state, initial contacts and warnings BEFORE the first step;
an already violated declared initial-penetration bound must not become a valid trial
through dynamics. Record initial/per-step values and a named stage/time reason with
honest ERROR/INCONCLUSIVE classification under the existing vocabulary. Verify zero
steps on rejected initial scenes and retain diagnostically useful admitted artifacts.
Include other initial finite-state/force/energy validity; no silent initial correction.

## 3. Programmatic acceptance lock cannot round-trip through its own loader

ValiditySpec.to_dict emits unset optional values as null; load_acceptance rejects null
for numeric fields. Calling public run_scenario(load_scenario(...),load_acceptance(...))
without explicit source-text arguments writes an acceptance.lock.json that then raises
`acceptance.validity.max_penetration_m must be a number, got None` on reload when the
input had validity={}. File-wrapper path preserves input text and hides this defect.

Emit a schema-valid canonical acceptance document (e.g. omit unset optional bounds),
and test typed/document round trips with empty and partially populated validity. Keep
raw input-byte locking and semantic/content hashes coherent; CRLF preservation remains
required. Do not copy a lock unrelated to the criteria actually evaluated.

## 4. Configuration size cap runs after unbounded allocation

_read_json uses Path.read_bytes() before checking MAX_CONFIG_BYTES. The claimed1MiB
cap therefore does not bound memory or a special file's read. Enforce bounded input
read before parsing/decoding, retain exact bytes, and handle unsupported/nonregular
inputs explicitly if applicable. Test the read bound without reading an actual unbounded
device. No new dependencies or global security/model settings are needed.

## Scope, limits, follow-up

One bounded M4a repair for1–4 only; do not implement M4b replay/event fixtures or Pocky
adapter/CAD. Preserve physical thresholds, independent state, deterministic metadata,
existing source and current global OpenCode role/effort/fallback settings. Use an actual
short native plan, independent read-only code review (disclose configured reviewer
unavailability, do not reconfigure it), actual compiled regression/adverse tests, and
write `docs/mujoco-m4a-repair-report.md` including raw evidence and unresolved issues.

Later M4b still needs full replay/tamper rejection and event identity/direction/dwell,
full integration-state identity rather than just selected arrays, explicit archive
resource budgets, complete synthetic failures, and a usable AssemblySpec adapter API
before M5. These are future gates, not claimed complete by M4a.

Before remediation: successor2 uses1/12operations,0/2remediations; cumulative13submitted
operations and4remediations across all runs. Deadline1792638674806 unchanged. Host ready,
no active operation. Preserve partial snapshot recorded in orchestration notes; M3's
accepted snapshot/tests remain intact.
