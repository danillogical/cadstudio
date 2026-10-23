# Independent portability review and renewal 9: configured review still required

Reviewed operation `op_0mvkar4kj5b520ae0a643fd4e`, successor8
`run_0mvkapstm71b768260259e1c2`, turn 1. The test/report corrections pass
independent checks, but the required configured ordinary-review role was not
invoked. This is a review-admission defect, not model unavailability or a new
physics defect. No S0 physical/dynamic conclusion is accepted.

## Independent checks of the correction

- Inspected the test diff: the new prerequisite guards only generated-evidence
  integration tests; hybrid tests are split so pure CAD/conformance checks stay
  active. Partial/corrupt evidence remains a loud failure. No assertion was
  removed to hide a model failure.
- Independently ran all three S0 test modules in the real-evidence environment:
  **164 passed in 49.53 seconds**, exit 0. Log will remain at
  `out/mujoco-m5a-supervisor-portability/real-evidence-tests.log`.
- Independently copied the current independent/portability modules into a
  temporary project root with actual source symlinks and no `out/`:
  **36 passed, 102 skipped in 12.04 seconds**, exit 0. Pure checks execute;
  only explicit generated-evidence prerequisites skip. The portable tests also
  exercise broken roots and truncation. Raw command/root/result:
  `out/mujoco-m5a-supervisor-portability/clean-checkout.json` and `.log`.
- Independently re-hashed current final manifest: **249 source / 370 evidence**,
  zero stale/missing. Original S0 historical manifest is byte-identical,
  SHA256 `8a569913f244999c9d010e3bf178d8e707ab2310dfe55cfc77176a9024158932`;
  all **348 original evidence hashes** match. Its three stale source entries are
  exactly the authorized test/two report edits. All 28 frozen entries match;
  global config remains `64460c56ddfa2e0b98284813dafeb3d15898e5184d040795ef32a500df436088`.
- The temporary hard-link corruption incident was disclosed by OMP. The original
  baseline summary was restored byte-for-byte and every original evidence hash
  now matches. Final fixture unlinks its corruption victim before writing and
  removes temporary roots. This is a restored-content incident, not evidence
  that the original files were literally read-only throughout the operation.
- Native full-suite log reports **1064 passed, 1 existing warning in 997.75
  seconds**. No accepted production, physics, criteria, CAD, params, dependency
  or config changed. Reports now correctly leave convergence and the validity
  breach's cause undetermined. Old minor timing/count metadata is superseded by
  the actual logs/current manifest counts cited here.

## R3: task worker mislabeled as configured reviewer

Native parent task-call arguments for both `PortabilityVerifier` and
`S0PortabilityReview` omit the `agent` selector. Both therefore executed as the
default task role: actual transcripts attribute 145 and 194 assistant messages
respectively to configured SG. The parent has 239 SG assistant records, no
errors. These are useful independent verification, but there is **no native
configured `reviewer` invocation or transcript** in this operation. Calling the
second worker 'configured ordinary reviewer' in reports does not satisfy that
gate. Previous properly dispatched review operations used the native reviewer
role explicitly. No model/provider change is needed or authorized to fix this.
Native task arguments, transcript paths, SHA256s, actual role/model execution
and visible verdicts are retained at
`out/mujoco-m5a-supervisor-portability/native-execution.json`; dispatch arguments
will be retained beside it. The automatic old-model watchdog failures are not
required-review evidence.

Invoke the already configured native `reviewer` role explicitly for one
read-only review of the final test/report correction. Preserve current code and
test results. If that role is unavailable, report the blocked gate without a
substitute. Correct the reports' role attribution and create a current index
after final review metadata; do not repeat dynamics or broad regressions.

## Independent limit renewal 9

Successor8 limits were **2 operations / 1 remediation / 120 minutes**, used
**1 / 0**, historical remaining **1 / 1**, deadline `1792726385962` now expired.
Cumulative **30 submitted operations / 11 native remediation cycles**. Exactly
one STOP decision will close this expired run with R3 unresolved; it is a
Supervisor workflow closure, not a human stop or completion. Do not reopen the
journal or reuse any old authorization. Exact STOP ID appended below.

Same human-authorized M5a-1 objective. Open linked successor9 with **1 operation /
0 remediation cycles / 90 minutes**: carry the single historical remaining
operation and reduce cycles to zero, renewing only time to complete the missing
configured review. Credible next action is explicit and limited: the source fix
already passes populated/absent/broken environment checks; only the role dispatch
and truthful review metadata need completion. No implementation exploration,
additional full suite, physics/model/criteria/config changes, tuning, P0–P3,
M6/M7, commit/push/deploy or product claim.

Next packet: `docs/mujoco-m5a-1-configured-review-packet.md`. Freshly verify idle
host/exact chat binding and empty work boundary before one non-queueing submit.
No required-role override/substitute, fallback or human model selection. Stop
with findings if configured review cannot approve; the Turn Orchestrator may
not self-admit fixes or renew limits. Old raw evidence and both independent
verification results are retained.

Exactly one decision saved for the portability operation: STOP
`dec_0mvkhj2k1330e85f24546dce3`, key
`cadstudio-m5a1-portability-missing-configured-review`. Successor8 is stopped,
no pending authorization. Native linked successor9 admission IDs will be
appended before its single review-only submission. No source work was undone.

Native successor9 `run_0mvkhjolr86162f8948d6876c`, open, exact current chat,
1 operation / 0 remediations, deadline `1792736057870`. Before submit 0 / 0 used,
cumulative 30 / 11. Reuse the known idle generation-3 session without another
rotation; exact binding reaffirmed, non-queueing submission enforces no queued
work. Request ID `cadstudio-m5a1-configured-review-01a1624d-1`.
