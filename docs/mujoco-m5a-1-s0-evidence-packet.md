# M5a-1: bounded S0 scenarios, evidence and checkpoints

Execute ONE next increment as the existing OMP Turn Orchestrator, only after
the Supervisor's native CONTINUE admission naming the accepted static operation
`op_0mvjxlsbw7236ba3c1b344c3f`. Read the invoked orchestrator skill for your
actual role, repository instructions/Pocky README, approved
`docs/mujoco-m5a-plan.md` sections 5.2–5.4, 6.1, 7–9, the handoff's remaining
items 6–9, and `docs/mujoco-m5a-1-adapter-static-acceptance.md`. This packet
does not authorize P0–P3 or a second operation. Preserve all accepted generic
and static source, tests, reports and raw evidence.

## Deliverable and allowed surface

Implement the eight no-packet S0 scenarios (five initial fractions plus spring
low/high and half-dt), their strict options files, plan-verbatim frozen S0
acceptance, project diagnostics/report helper, independent project tests, actual
CLI run/replay evidence, saved checkpoints and final reports:
`docs/mujoco-m5a-report.md` and `projects/pocky/docs/physics-m5a.md`.
Allowed new project files: `projects/pocky/physics/scenarios/s0_*.json`,
`options/s0_*.toml`, `s0_acceptance.json`, `report.py`, and associated tests and
reports. Make only necessary lazy project hook wiring if genuinely missing.
Keep existing assembly/colliders/options/support/audits and accepted generic
production unchanged. If a demonstrated generic/adapter defect prevents valid
evidence, preserve its reproducer and report it for a separate bounded decision;
do not silently expand this operation or tune the scene to get a desired verdict.

## Scenarios and criteria: freeze before evidence

1. Runtime scene stays CAD fraction 0, no packets. Initial coordinates come from
   `reset_state`/actual CAD helpers at f=0,.25,.5,.75,1, never a rebuilt scene,
   linearized pusher quarter stroke or sign flip. All scenarios reset, settle
   **3.0 s**, then hold **0.5 s**, with real zero external input throughout.
   Preserve real spring preload/return, free housing/lip/chassis, joint/contact
   topology and floor at z=-19.2 mm. Verify all-five compiled reset/clearance
   checks and initial validity before drawing dynamic conclusions.

2. Base dt=0.001 s, spring=500 N/m. Low/high spring f=0 use 200/1000 N/m;
   half-dt f=0 uses 0.0005 s with baseline spring. Assembly options and scenario
   dt must match. Contact and stop compliance remain **0.002 s** at both dt;
   friction/priority, masses, seed, gravity and every other input stay fixed.
   Use existing strict hashed option interface, including canonical empty lock
   for base cases. No physical parameter is newly measured by running MuJoCo.

3. Every scenario explicitly sets `sampling_interval_s = timestep_s`, with
   trace/state/contact budgets derived to retain every integration sample for
   the whole run, especially the full 0.5 s hold. Overflow invalidates instead
   of truncating/downsampling. No reliance on the 0.002 s default.

4. Freeze `s0_acceptance.json` before the first run, record raw SHA256 and source
   inventory, enable the accepted **20% near-threshold** band, and use generic
   schema/locks/evaluator. Preserve these plan thresholds exactly:

   - `body_pose_retained`: body/chassis attached-local relative translation
     <=0.00020 m and rotation <=0.20 degrees, worst over hold from initial.
   - `body_drop`: body/chassis signed world-z change initial→hold in
     [-0.00010,+0.00010] m, worst over hold; report positive downward
     `max(0,-delta_z)` separately. Both downward and upward breach fail.
   - Body and lip against each of pusher, rod and crank: six body-pair contact
     duration checks, per-step **summed normal force** threshold **0.0715 N**,
     longest continuous interval <=**0.20 s**. Use the already accepted generic
     whole-run `contact_duration` semantics: `window=end`, no phase fields.
     Its integration-step watch is distinct from display CSV rows. Do not pass
     a forbidden `max_over_phase` contact-duration window or invent a sidecar.
   - `chassis_grounded`: chassis/floor relative translation <=0.001 m,
     rotation <=0.20 degrees, worst over hold.
   - Body and lip speed <=0.001 m/s, worst over hold.
   - Peak penetration <=0.0002 m; validity `max_penetration_m=0.0002`, warnings
     invalidate. The old 1 mm smoke bound must never replace this criterion.

   Use the accepted field names and reference validation, SI units and radians
   where required; independently check conversion and body ordering. Do not
   freeze an earlier wrong acceptance just to follow an artifact mechanically.
   Validate plan conformance before freezing and never edit thresholds after
   seeing results. Frozen presentation `acceptance.toml` stays byte-identical.

## Actual evidence and truthful interpretation

Run real `uv run --frozen --extra physics cad physics run pocky/prototype` for
all eight cases through the accepted project CLI, under a new clearly indexed
`out/mujoco-m5a/s0/` evidence root. Record exact command, exit code (including
expected failure/status codes), locks, options/params/source/scene hashes,
warnings, check values/times, trace/state/contact coverage and run manifests.
Do not abort remaining cases merely because one obtains a valid product FAIL.
Do not suppress numerical errors to finish a table.

Replay S0 f=0 through the real CLI from its saved verified state, preserving
scenario/acceptance/options locks, every-step sampling, physical inputs and
fixed compliance. Recompute and compare checks, worst sample times/values and
summed contact durations within one compiled sample interval and declared
numeric tolerance. Replay that cannot reproduce is INCONCLUSIVE, never PASS.
Save and index complete final checkpoints; incomplete runs/states are labelled
incomplete, never called settled checkpoints. No unsupported shared-state import.

Report **numerical validity separately from product checks**. Penetration or
warnings violating validity make conclusions INCONCLUSIVE/invalid, not a
physical product FAIL. Initial scene/overlap failure is SCENE_INVALID/ERROR.
Valid, hash-bound structural checks may truthfully FAIL. Near-threshold or
base/half-dt status changes make the comparison INCONCLUSIVE. Preserve raw
generic summaries; a diagnostic report may explain comparisons, never overwrite
bound run/check statuses or replace the evaluator with a sidecar.

The pre-run prediction remains historical: unsupported housing may drop onto
moving parts and fail `body_drop`/`body_on_pusher`. Exact static CAD subsequently
showed a bullnose tangency; do not force the predicted 0.4 mm/0.4 degree outcome.
The previous f=1 smoke peak of 0.7909 mm exceeds S0's 0.2 mm validity bound.
Observe and report the actual dynamics without geometry, mass, friction,
stiffness, damping, contact, stop, timestep-beyond-approved or criterion tuning.

Diagnostic tables may read bound summaries/trace/contacts: housing relative pose
and signed drop, body-pair forces/durations, chassis floor load, return time,
peak speeds and peg-head/lip-rail arrests. Describe metric definitions and
whether a diagnostic is sampled or every-step. Reference existing 23 CAD/
collider overlays and inspect relevant cutaway/slot/exit views; unchanged raw
XML should retain `997a20b79566bfc5452e334b98f149c292056312795ce85f763308d430a22a15`
and baseline scene identity `2c4bd425c55d9f56c39904e6ae01683836650fc84dabaa6ff645eb1077926e2f`.
Sensitivity scenes legitimately change identity only for their declared inputs.

## Independent checks and stop boundary

Assign a separate independent test worker for scenario/acceptance/options/report
semantics and evidence completeness, including threshold/body/sign/unit checks,
all-five reset derivation, no actuation, every-step/full hold coverage, budget
handling, worst/end distinction, valid FAIL versus invalid INCONCLUSIVE, and
replay identity. Test substantive new behavior, not serializer repetition.
Obtain actual configured ordinary reviewer approval of final code/data/evidence.
Keep native transcript references/hashes/model attribution/final verdicts. Use
configured roles as they stand; required-role failure blocks its gate. No manual
substitute, provider/model/role/effort/fallback/config edits, or separate security
review gate. No additional OMP operation self-admission or limit renewal.

Run meaningful focused tests and the required full
`uv run --frozen --extra physics pytest tests -q` once after final shared source/
test changes. The preceding 900-pass full suite covers the accepted static tree;
new scenarios/report code justify this final regression. Retain exact commands,
exit codes and raw logs. Generate final before/after source and evidence indexes
AFTER final source/report edits, with no missing or stale hashes. Do not claim
all phases/checkpoints complete if execution could not establish that fact.

Run `run_0mvjxlcc2e0e8c3a94941d366` limits stay 3 operations / 2 remediations,
deadline `1792711542961`. Before this admission: 1 operation / 0 cycles used,
2 / 2 remain, cumulative 28 submitted / 11 remediation cycles. This admission
makes cumulative 29 submissions. No renewal, no unrelated work. Stop for
Supervisor review after this S0 increment. No P0–P3, packets/25-capacity,
loaded-settle/shared-state decision, M6/M7, CAD redesign, commit/push/deploy or
physical reliability claim. Missing physical inputs remain unverified.
