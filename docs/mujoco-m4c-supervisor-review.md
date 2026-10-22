# M4c independent review: bounded repair required

Operation op_0mvip9n4a2f8c085b8d0ef2ab, successor3
run_0mvip90biee013608fa104d9d, first turn. M4c is NOT accepted. M0–M3,
M4a and M4b remain accepted. No Pocky adapter/CAD/S0/physical claims.

The event layer, free-body real fixture, replay recomputation and frozen criteria
are meaningful progress. Supervisor independently ran159M4c/scenario/M4a/M4b tests,
all passed44.70s. OMP reports614full-suite passes409.50s; raw log inspected, not
repeated by the supervisor because the defects below already block acceptance.
The native substantive plan exists:22835bytes, actual path
/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4c-plan-20261021/plan3.txt
(the report incorrectly places it under cadstudio-m4c-20261021; correct its links).

Configured review actually ran: native M4cReview2.jsonl inspected, provideranthropic,
modelclaude-opus-5-5. The prior Muse429 is historical. No model/role substitute is
claimed or authorized. Human owns models/efforts/routing/fallbacks; no separate
security-reviewer gate, as explicitly removed by the human.

## 1. Powered release and powered hold falsely pass supported presentation

Pure tracker probe: release and hold both carry ctrl_zero=False, otherwise valid
crossing/support samples. It returns PASS/supported_presentation, continuous dwell
0.89s, evidence_complete=true. release_zero_ok is recorded false but its verdict
check only occurs inside the NOT-complete branch; complete observations bypass it.

More importantly, REAL MuJoCo probe wraps the real mj_step call and injects2N
control during all1900release/hold steps (t>=2.5s) of the actual presentation_aperture
fixture. No positions/velocities are written. Result is overall PASS, validity.ok=true,
no reasons, both event checksPASS. The run actually remained powered after the
commanded release and cannot establish supported presentation after input release.

A separate real probe leaves the declared release clean, then injects2N ONLY during
1500hold steps (t>=2.9s). It also reports overall PASS/validity.ok=true, and the archive
contains1499selected nonzero hold rows (filtert>=2.901). Merely checking the release
phase flag at finish will NOT fix this case: nonzero input after release/during dwell
is not tracked on hold samples at all. These are deliberate execution-fault probes,
not claims about a spontaneous failure or physical prototype.

Raw independent scripts, full generated runs and results:
/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4c-supervisor-20261021/
- probes.py, probe_results.json, powered-release/
- extra_probes.py, extra_results.json, powered-hold/

Repair the actual zero-input gate for the complete required post-release/dwell
interval, including hold phases, and apply it regardless of event evidence completeness.
Record a stage/time/reason and disqualify unexpected live input from valid presentation
under the established four-state semantics; a commanded zero is not proof of actual
zero. Preserve commanded/actual controls and partial event evidence. Do not repair/zero
live controls in observation or modify the acceptance criteria to hide a mismatch.
Use the same guard in runner and replay, without regressing M4b control alignment,
limited/negative gearing, or legitimate actuation before release.

Add meaningful synthetic and real tests for: nonzero at begin-release; nonzero on one
intermediate release step; nonzero only in hold/dwell; and clean real release/hold
stillPASS. Check event_verdict and overall status, retained diagnostics and replay of
an invalid source. A successful dwell must not retain success when later required
zero-input evidence fails, nor may a full/prefix replay mask the violation.

## 2. First-step crossing is misclassified as initial protrusion

The event window is activated by begin_phase but its geometry is seeded only on the
first POST-step observation. _observe_body sets seen/suppressed and returns there.
Consequently a real outward crossing during that first integration transition is
lost. This is acknowledged in OMP's report, but it is a demonstrated correctness
limitation that should be fixed before real product feed diagnosis.

Independent scripted-boundary probe: known packet inside at the final settle sample
(t=0.1), known outside at the FIRSTactuate sample(t=0.11), then remains out. The event
counts0and recordsinitial_protruding/zero_feed even though the transition occurs in
the actuation window. This is a SYNTHETIC detector trajectory, explicitly not a real
MuJoCo observation. Raw case in extra_results.json. An exit observer's PASS here is
its own observation status; event_count(expected1) would produce a falsezero-feedFAIL.

Seed each window from the coherent state AT its boundary, before the first mj_step;
retain appropriate previous geometry without importing pre-window crossings or stale
state. Separate a boundary geometry sample from post-release applied-control evidence
so the prior actuation command is not mistaken for a new release-phase input.
Test first-step crossing, initially protruding/outside suppression, pre-window
crossing, phase boundary timestamp and replay equivalence. Include a real or genuinely
integrated small-step boundary case when practical, without teleporting a dispense.

## Scope, preservation and stopping conditions

One M4c repair for1–2 plus report path correction. No M5 adapter/S0, product CAD,
new acceptance tuning, role/model/effort/fallback/config changes, security-reviewer
request or gate, scheduler or self-renewal. Frozen projects/pocky/physics/acceptance.toml
must retain its semantic/raw hashes. It has correct §21 defaults, including10mm
accessibility; masses/friction/spring/physical trials remain unverified.

Native configured plan must actually return substantive output before edits. Use the
configured ordinary code reviewer and record actual model usage, fixes and remaining
issues, no manual substitution on failure. Focused regression/adverse tests then full
suite once after final shared changes. Report docs/mujoco-m4c-repair-report.md and raw
evidence. Preserve all M3/M4a/M4b behaviors and separate synthetic fault tests from
actual physical evidence. End the bounded turn for independent Codex acceptance.

Before decision:successor3 uses1/8operations,0/2remediations;7ops2rem remaining,
deadline1792651464414 unchanged. Cumulative17submitted ops/6remediation cycles.
One REMEDIATE will spend1cycle; no renewal is needed. Host62419 ready/generation3,
no active operation. Keep exactly one review decision for this completed operation.
