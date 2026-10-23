# S0 independent review: evidence verified; test portability blocks acceptance

Reviewed `op_0mvk2au9ga733c488a5957acd`, successor7
`run_0mvjxlcc2e0e8c3a94941d366`, turn 2, admitted by CONTINUE
`dec_0mvk29rpu8c8d76e08aa67af9`. Bridge-terminal completed is not acceptance.
No S0 physical/product verdict is established. One new repository regression
must be corrected before accepting the implementation/evidence checkpoint.

## Verified evidence

- All **245 source / 348 evidence** entries in the final manifest re-hash with
  zero missing or stale files. Compared with accepted 228-file static snapshot:
  only 17 authorized additions and the exact previously recorded Supervisor
  acceptance append. No generic/adapter/CAD/params/dependency edits. Frozen
  presentation hash remains `518a45ffc4592ca602be4c33c59681038e43dedaa15b688312202c3a57ff6ca2`;
  global config remains `64460c56ddfa2e0b98284813dafeb3d15898e5184d040795ef32a500df436088`.
- All 28 freeze-record file hashes match current files. Formal eight-case
  evidence follows the freeze. Two exploratory probes preceded it; they are
  disclosed, not represented as frozen formal evidence. Independently read
  actual acceptance/scenarios against plan thresholds, signed drop/body ordering,
  degree/radian conversion, six summed-force whole-run contact checks and hold
  maxima. No post-result criterion change was found.
- All eight cases complete reset, 3 s settle and .5 s hold, one retained state
  per integration step: 3501 rows, or 7001 at half-dt. All eight are numerically
  **INVALID / INCONCLUSIVE**, with peaks .331558–.790912 mm against .2 mm.
  The bound structural FAILs are arithmetic on invalid telemetry, not hardware
  conclusions. Checkpoints are complete finite simulation states, not proof of
  physically valid settled behavior.
- Independently ran the two new test modules: **145 passed in 14.00 seconds**,
  exit 0, with generated evidence present. Independently invoked real baseline
  replay into `out/mujoco-m5a-supervisor-s0/replay_s0_f000/`: expected exit 2,
  INCONCLUSIVE, **reproduced true**, 3501 full-state rows / 501 hold-continuation
  rows, maximum absolute state difference **0.0**, no evaluation differences.
  Source run/evidence was not rewritten. Raw logs and audit JSON are under
  `out/mujoco-m5a-supervisor-s0/`.
- Inspected final native full-suite command/log: **1045 passed, 1 existing zip
  warning in 960.52 seconds**, final source/test revisions. Did not redundantly
  rerun that broad suite. This proves the evidence-populated workspace only;
  the missing-evidence environment finding below is independent of that pass.
- Actual native primary 581 assistant messages and separate independent worker
  214 messages use configured SG; no errors. Configured ordinary reviewer
  round-10 transcript has 19 assistant messages, all Opus, final **APPROVE**.
  Prior rejected rounds and repaired report/evidence findings were inspected;
  they do not waive the newly discovered portability defect. All native paths,
  hashes, attribution and visible final texts are retained in
  `out/mujoco-m5a-supervisor-s0/native-execution.json`. The automatic old-model
  watchdog quota errors supply no required-gate evidence and no substitute role
  was used. Configured primary/test/reviewer execution succeeded.

## R1: newly added tests fail without ignored generated evidence

`tests/test_pocky_physics_s0_independent.py` reads
`out/mujoco-m5a/s0/runs/*/summary.json`, states, replay and preflight unconditionally
in evidence-backed tests. `out/` is git-ignored and not delivered in a checkout.
The existing implementer S0 test module already handles absent generated
evidence; the new independent module does not. Thus a passing local full suite
does not establish a portable repository test suite.

Independent reproduction used an untouched copy of the independent test module
in a temporary project root, symlinking actual `projects/` and `cadkit/` sources
while leaving `out/` absent. No source or real evidence was moved or edited.
Selected the pure threshold control plus the eight parameterized
`test_invalid_runs_are_inconclusive_and_never_pass` cases:
**8 failed, 1 passed, 110 deselected in 2.10 seconds**, exit 1. Every failure is
FileNotFoundError for a generated summary. Command, temporary root and raw output:
`out/mujoco-m5a-supervisor-s0/no-generated-evidence.json` and `.log`.

Correct only these unaccepted test dependencies: use self-contained fixtures
where appropriate, or explicit optional generated-evidence prerequisites for
only the integration cases. Pure scenario/acceptance/CAD/synthetic tests must
still run when generated evidence is absent. Do not globally skip the module,
delete assertions, silently accept corrupt/incomplete evidence, change physics,
or commit large generated evidence to make tests pass. With real evidence present
all current verification must still execute and pass. Demonstrate empty-evidence,
present-evidence, and corrupted/partial-evidence controls.

## R2: timestep language exceeds the evidence

The reports correctly measure baseline .350 mm and half-dt .427 mm penetration,
but infer this is "not a timestep-resolution artifact". Two timestep values do
not establish convergence or rule out resolution effects. State only the actual
observation: the approved halving did not resolve the validity breach; its cause
and convergence remain undetermined. No additional dynamics, parameter tuning
or solver investigation is admitted by this wording correction.

## Decision and limits

Same approved M5a-1 objective; no P0–P3, loaded/25/shared-state, M6/M7 or physical
acceptance. Preserve all raw S0 runs, freeze, checkpoints, replay and reports.
The .2 mm validity gate remains open and cannot be waived by this review.

Successor7 used **2 operations / 0 remediation cycles** of 3 / 2; historical
remaining **1 / 2**, deadline `1792711542961` is now expired. Cumulative usage
**29 submitted operations / 11 native remediation cycles**. The admitted S0
operation settled after that deadline; it did not create or renew an operation.
Host is ready with no active operation. Exactly one STOP review decision will
close this expired run, recording R1/R2 as unaccepted; a linked successor requires
the separate independent renewal review and supported native admission.

Exactly one native decision saved: **STOP**
`dec_0mvkaozpned94fb025c462dc1`, idempotency key
`cadstudio-m5a1-s0-portability-expired-run-review`. Bridge confirms successor7
stopped with no next-operation authorization. No S0 evidence or dynamic result
was accepted by that closure; static acceptance remains intact. Continuation
requires the linked renewal8 admission, not reuse of the consumed CONTINUE.
