# M5a-1: finish static fidelity review and evidence

Execute ONE bounded operation as the existing OMP Turn Orchestrator. Read the
invoked orchestrator skill for your actual OMP role, repository instructions and
Pocky README, approved M5a-1 plan section 6.1 and acceptance. Read
`docs/mujoco-supervision-renewal-7.md` for exact admission/history/limits and
`docs/mujoco-m5a-1-fidelity-followup-supervisor-review.md` for independently
verified progress and remaining findings. Earlier packets/reports are context
and claims to verify; this packet bounds the new operation. Preserve all partial
and accepted uncommitted work. End after review and final evidence. No S0 batch.

## Start from the verified partial

Current production/tests are unchanged since Supervisor's 136-test focused pass
(459.17 seconds). Both real-CAD channel blocker negatives now reject; the
12-point interior bore-hole mutation fails the new volumetric audit; original
bore/exit blockers and body-void/other-body-occupancy negative reject. The native
test worker authored 44 void-coverage tests and wrote a passing log, but its task
ended with provider errors before a successful handoff. The primary likewise
ended with provider errors; configured ordinary review was never dispatched.
Do not pretend those tasks completed successfully or restart exploratory work
from scratch. Reuse raw Supervisor checks in
`out/mujoco-m5a-supervisor-followup/`, preserving historical output unchanged.

## Required work

1. Resolve the geometric justification of `_rod_corridor_prisms`. Vertex and
   face-bounding-box x stations do not by themselves prove every YZ cross-section
   is constant between stations: curved/cylindrical faces can vary continuously.
   Current midpoint extrusion is called an exact Minkowski sweep. Independently
   establish the property for the actual CAD rod/peg, or correct the contract
   generation and truthfully state conservative approximation/coverage bounds.
   Do not simply remove the word 'exact' while leaving required coverage
   unproved. Demonstrate protection of actual swept CAD volume, including thin
   bands and upper rod extent; preserve volumetric coverage and material/void
   controls. Do not fill the tested carrier's own material with probes, omit bad
   voids, add only known blocker centres, loosen numeric criteria, or redesign
   CAD. A new production change needs evidence of the defect it resolves.

2. Reconcile contradictory own-void documentation with actual kept points and
   occupancy accounting. `VoidOccupancy` says other-occupied points are not
   counted as own-void; `_void_grid` and tests correctly retain them as a subset
   of own void. Slot notes still say independently owned pegs are excluded.
   Own welded-group material remains excluded; other independent bodies at
   fraction 0 are classified without shrinking the tested carrier's void.
   Initial compiled overlap is a separate gate. Preserve parent-filtered pivot
   exception and report joint/guide idealizations truthfully.

3. Assign a separate independent test worker to validate final correction and
   provide a completed native handoff. Keep existing meaningful tests; add/change
   tests only where needed for actual new geometry/contract findings. Obtain
   actual configured ordinary code-reviewer approval of final implementation
   and evidence. Address findings within scope. Preserve native transcript
   references, hashes, actual model attribution and final visible verdicts.
   Use configured roles as they stand. Required-role failure blocks its gate;
   no role/model/provider/effort/fallback changes, overrides or substitutes.
   No separate security-reviewer gate. Self-review cannot replace ordinary review.

4. Write `docs/mujoco-m5a-1-fidelity-followup-report.md`, which is currently
   missing, and reconcile old partial report supersession claims and false
   historical 'stricter, not weaker' limitation with accurate annotations.
   Preserve historical verdicts as historical. Current 222-file after-manifest
   has stale hashes for colliders, void tests and old repair report. Regenerate
   truthful final source/report manifests AFTER all final edits, including
   pre-existing supervisor/renewal/packet documents and new report. Clearly
   distinguish scene identity from raw XML SHA256. Use NEW
   `out/mujoco-m5a/fidelity-finalize/` evidence, retaining all old raw evidence.

## Scope, acceptance and reporting

Project fidelity-contract/audit fixes only in `projects/pocky/physics/`, associated
tests and reports. Existing physical collider geometry stays unchanged unless
expanded fidelity evidence proves a real proxy defect. No source CAD/params,
generic `cadkit/` production, dependency/lock/global config changes, new restraints,
criterion tuning, reset/sign interpolation, commit/push/deploy. Frozen acceptance
SHA256 `518a45ffc4592ca602be4c33c59681038e43dedaa15b688312202c3a57ff6ca2`.

Retain original bore/exit, whole-hull, filled-slot, local relief, volumetric-hole,
extra spatial-blocker and real material/boundary controls; all five CAD-derived
compiled resets, quarter-stroke linear/sign negatives, critical-clearance 0.02 mm,
initial overlap and SCENE_VALID. Preserve free housing/lip/chassis groups, crank
hinge, rod/pusher slides, real sibling pin-slot contact, floor/mass/spring/dt/
compliance semantics. Preserve overlay evidence; generate fresh overlays if any
physical proxy changes. Otherwise prove XML byte-identical to previous export:
raw SHA256 `997a20b79566bfc5452e334b98f149c292056312795ce85f763308d430a22a15`,
scene identity `2c4bd425c55d9f56c39904e6ae01683836650fc84dabaa6ff645eb1077926e2f`.

Use ~/.local/bin on PATH and `uv run --frozen --extra physics ...`. After code or
test changes, run relevant new negatives plus focused regression:
`pytest tests/test_pocky_physics_assembly.py tests/test_pocky_physics_colliders.py tests/test_pocky_physics_void_coverage.py tests/test_cadkit_physics_export_cli.py -q`.
Avoid redundant broad runs on unchanged code. Full
`uv run --frozen --extra physics pytest tests -q` remains due after final shared
M5a-1 changes; report what actually ran. Supply exact commands/exit codes/raw logs,
source inventories and actual configured review/test-worker evidence.

Prior .7909 mm no-actuation smoke does not satisfy S0 .2 mm validity. No S0
scenario/evidence batch, P0–P3, loaded/25-packet/shared-state decision, M6/M7 or
physical/product PASS. Stop after this repair/review evidence for independent
Codex acceptance and separate next-increment admission. Report unresolved
findings honestly rather than claiming required gates were waived.
