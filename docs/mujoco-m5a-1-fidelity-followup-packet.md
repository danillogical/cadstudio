# M5a-1: bounded remaining fidelity repair

You are the existing OMP Turn Orchestrator. Execute ONE project-only repair of
the unaccepted adapter/static fidelity contract. This is the first operation of
linked successor6, not a reopening or retry under successor5's consumed decision.
Read `docs/mujoco-supervision-renewal-6.md` for actual prior usage, reconciliation,
new limits, concrete advisement and admission IDs. End this operation after
configured ordinary review and evidence reconciliation; do not start S0.

Read the invoked orchestrator skill using your actual OMP role and repository
guidance (including Pocky README), approved `docs/mujoco-m5a-plan.md` section 6.1,
its acceptance, `docs/mujoco-m5a-1-adapter-static-packet.md`, adapter/static report,
and especially `docs/mujoco-m5a-1-fidelity-repair-supervisor-review.md`. Treat old
reports as claims to verify. Preserve all accepted generic work and unaccepted
partial project work. No reset/checkout/clean/commit/push/deployment.

## Required corrections

1. Replace the line-only rod-channel contract with genuine three-dimensional
   coverage of the CAD-derived relevant void/swept-rod corridor. Independently
   reproduced 6 mm cube centered (-82,-28,-10.9) mm has zero installed fraction-0
   CAD overlap, passes current fidelity, but intersects the actual moving rod by
   41.2695 mm3 at fraction .5 and 82.8 mm3 at 1. Reviewer's (-88,-28,-10.9) is
   another counterexample. Current (x,-28,-16) samples miss the upper channel.
   Derive full cross-section and sweep from actual CAD, including rod upper
   extent (about -11.6 mm), not merely chassis floor to rod bottom. Validate
   extents, boundary clipping and <=5 mm spacing (adapt narrower features) in
   three dimensions. Do not add just known blocker points or alter the CAD.

2. Correct the independent coverage proof. Removing 12 bore-grid points in an
   interior 12 mm cube about (0,0,40) mm leaves current projected-axis density
   test passing and admits a 6 mm blocker. Add a meaningful independent
   volumetric/voxel occupancy guarantee over the claimed CAD void regions,
   clipped to actual own-group material/boundaries. It must fail this interior
   hole mutation and analogous channel/interior defects without relying on
   marginal coordinate counts, copying production grid generation, expected
   list length, or only the two original blocker centres. Exercise additional
   spatial blockers and appropriate material/boundary controls. Strengthen the
   unaccepted void-coverage tests; never narrow accepted tests to force PASS.

3. Separate a carrier's own-welded-group void from assembly-global empty space.
   Current `_void_grid` excludes all other independent parts at fraction 0;
   reporting this as 'stricter, not weaker' is false and can silently drop a
   part's void where another body later moves. Preserve exclusions for the
   tested carrier's own material and welded pegs. Independently moving other
   bodies need explicit occupancy classification/audit, without silently
   deleting own-group void guarantees. Keep initial compiled overlap checks as
   an additional gate. Document any pivot/peg exception precisely. For example
   body-void blocker (82,-27,7) overlaps lip at fraction 0: explain and test the
   distinct own-body void and assembly-overlap guarantees. Do not probe inside
   the tested welded group's real material or count other-body exclusion as
   proof of the stronger contract. Default parent filtering idealizes guides;
   it does not establish corridor preservation or physical mechanism success.

4. Reconcile reports and final evidence after final changes. Previous after-
   manifest has stale adapter/static-report hash and omits new repair report.
   Produce truthful before/after inventories including pre-existing supervisor
   documents and new repair report, after all source/report edits. Preserve
   original output directories; use `out/mujoco-m5a/fidelity-followup/` for new
   artifacts and a new clearly named report. Update earlier report status with
   accurate supersession/final findings; preserve historical verdicts. Capture
   exact commands, exit codes, raw logs, CAD/scene hashes and native reviewer /
   independent-test-worker transcript references, model attribution and final
   visible verdict. Missing/stale evidence or reviewer rejection is not success.

## Scope and gates

Allowed production changes: project-only fidelity-contract generation/audits in
`projects/pocky/physics/`; physical colliders stay unchanged unless expanded
coverage proves a real proxy defect. Report such a defect honestly and repair
only that proxy within the approved static scope. No CAD design/params edits,
new restraints, criterion tuning, generic `cadkit/` production edits, dependency
or global config edits, routing/role/model/effort/fallback changes or overrides.
Preserve frozen acceptance hash
`518a45ffc4592ca602be4c33c59681038e43dedaa15b688312202c3a57ff6ca2`.

Retain original bore/exit blocker negatives; hull/filled-slot negatives, local
relief controls, all-five compiled CAD-derived resets, initial overlap and
critical clearance audits, static SCENE_VALID and export/overlay gates. Preserve
free housing/lip/chassis groups, crank hinge, rod/pusher slides, real sibling
pin-slot contacts, existing mass/spring/timestep/compliance and floor semantics.
No linearized quarter-stroke resets, sign flips or default geometry changes.
If physical colliders are unchanged, prove export XML matches existing scene
hash `2c4bd425c55d9f56c39904e6ae01683836650fc84dabaa6ff645eb1077926e2f`.

Assign an independent test worker to author/check semantic tests and negatives,
then obtain actual configured ordinary code-reviewer approval of final changes.
Use configured roles as they stand; a required role failure blocks its gate.
Preserve native execution evidence. No substitute or separate security-reviewer
gate. Implementation self-review and mocked-only checks do not satisfy this.

Focused regression minimum (with ~/.local/bin on PATH):
`uv run --frozen --extra physics pytest tests/test_pocky_physics_assembly.py tests/test_pocky_physics_colliders.py tests/test_pocky_physics_void_coverage.py tests/test_cadkit_physics_export_cli.py -q`.
Run exact real CAD/coverage reproducer and new negatives, plus applicable export
audits/overlays. Do not update the lock or omit physics extras. Full
`uv run --frozen --extra physics pytest tests -q` remains due once shared M5a-1
changes are final; report what was actually run, without redundant broad runs.

No S0 evidence/scenario batch, P0–P3, loaded/25-packet/shared-state decision,
M6/M7 or physical product PASS in this operation. Previous f=1 smoke reached
.7909 mm penetration: its separate 1 mm smoke bound does not satisfy planned
S0 .2 mm validity. Preserve numerical INCONCLUSIVE versus physical FAIL and
unverified physical measurements. End with changed files, proof of corrections,
tests/review evidence and unresolved findings for independent Codex acceptance.
