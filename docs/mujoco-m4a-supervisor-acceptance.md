# M4a independent final review

Review of repair operation op_0mvijlkomac81e7100982fcc0, successor2
run_0mvihmvsm9f3be51a0fd22543, turn2, remediation
dec_0mvijl1n986b934ae0bba0982. The bounded M4a increment is independently accepted. Continue to M4b;
this does not close M4 or the full M0–M7 objective.

## Repairs independently checked

The four concrete findings in docs/mujoco-m4a-supervisor-review.md are resolved:
coherent post-state body/COM/velocity observations, initial validity before stepping,
canonical/reloadable criteria locks, and bounded regular-file config loading.
The native plan output is present (actual configured role,156.53s), and separate
read-only default-role review evidence is present. Configured WorkBuddy Step5
reviewer429 and unregistered security reviewer are disclosed, without role changes.

Forces/contacts/energy in M4a are forward-evaluated on scratch data at the recorded
state timestamp; force_time_s == state_time_s, with an explicit force_stage. They
are not the integrator-stage forces or intermediate RK4 impulses. Euler and RK4
are supported; other integrators are rejected. The live integration trajectory is
unchanged by observation, including a bit-equality regression. Complete optional
state transfer and replay remain M4b; no claim of full integration-state archival
is accepted on the strength of selected M4a arrays alone.

## Additional supervisor correction after the OMP repair

Independent fault injection after a REAL mj_step set live qacc[0] to NaN. The
submitted repair's scratch forward recomputed finite acceleration, masking the
live failure and reporting PASS. This was a deliberate numerical fault probe,
not a spontaneous simulation failure or physical observation. Preserved before
run and probe under ~/.omp-bridge/diagnostics/cadstudio-m4a-final-supervisor-20261021/
before-live-guard/.

The supervisor added a read-only live finite check before scratch observation
(initial and every step), retained the final failed state row, and checked solver
warning counters on BOTH live and observation data. No values are repaired or
reset. Ten regression cases cover live acceleration, actuator/passive/constraint/
spring/damper/actuation forces, energy, observation warnings and initial live
acceleration. This small local correction was independently exercised here;
OMP's earlier reviewer did not review this final supervisor patch.

## Validation

- OMP repair reported61new+231prior physics tests and516full-suite passes381.14s.
- Supervisor before final follow-up:144focused tests passed29.27s.
- Supervisor after live/scratch guard:153focused tests passed30.41s, then the
  additional initial-nonfinite regression passed independently (1passed0.44s).
- Supervisor final full suite: **526 passed in388.93s (6:28), exit0**. This
  includes all ten final guard regressions and all existing CAD/physics tests.
- Fresh real CLI: driven slider PASS/exit0; same fixture with missing input force
  FAIL/exit1. The injected live nonfinite acceleration now returns INCONCLUSIVE
  at t0.001 after exactly one actual step with explicit live-acceleration reason,
  retained strict JSON and state archive.
- Independent source comparison against accepted M3 snapshot: existing changes
  only cadkit/cli.py and M4a/orchestration docs; all prior physics modules, CAD,
  dependencies, preexisting tests and acceptance architecture are unchanged.

Raw final diagnostics, CLI/probe artifacts, before/after fault evidence and test
log: /Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4a-final-supervisor-20261021/.

## Scope and continuation

M4a is only generic phase execution/typed criteria/telemetry/evidence. M4 as a whole
is still open. Next M4b packet docs/mujoco-m4b-packet.md covers complete-state replay,
hash/path/archive integrity and a typed AssemblySpec execution API. M4c separately
covers identity/direction/windows/anti-doublecount/supported dwell and the complete
synthetic failure suite. No Pocky CAD or adapter changed, S0 is still M5a, and
physical M7 evidence remains UNVERIFIED. The user's rigid165x55x5.2mm packet and
partly protruding supported pickup objective remain authoritative.

Before next admission: successor2 uses2/12operations,1/2remediations, deadline
1792638674806 unchanged; cumulative14submitted operations/5remediation cycles.
No renewal, new model selection, fallback, scheduler or extra human approval.
