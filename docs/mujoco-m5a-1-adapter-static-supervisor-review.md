# Independent adapter/static review: void coverage correction required

Completed operation `op_0mvjabe8s901d98bf04f78aa6`, generation 2, successor5
`run_0mvj62atk8b61da9fe2edf2ea`, turn 3, authorized by
`dec_0mvjaa93m7c7fe330fbbb475a`. Implementation is preserved but not yet
accepted as the adapter/static increment. No S0 evidence batch is admitted.

## Independently verified progress

- With `~/.local/bin` on PATH, independently ran
  `uv run --frozen --extra physics pytest tests/test_pocky_*.py
  tests/test_cadkit_physics_export_cli.py -q`: **137 passed in 86.16 s**, exit 0.
  This includes both new project test files and existing Pocky/CLI regressions;
  the two earlier PATH-related failures do not reproduce. Log retained at
  `out/mujoco-m5a-supervisor-adapter/project-regressions.log`.
- All **216** after-manifest hashes freshly match. Accepted generic source,
  original CAD/params/dependencies/frozen criteria remain byte-identical.
  Against the accepted snapshot, only authorized project hooks and the legitimate
  Supervisor acceptance-note append differ among pre-existing files. No removal.
- Inspected the assembly/options/hooks, collider recipes/contracts, support and
  compiled audits, independent tests and static/compiled/negative artifacts.
  The all-five compiled reset tests, wrong-linear/sign negatives, critical
  clearances, exact overlaps, sole fixed analytic floor and absence of
  equalities/actuators pass. Current fused body groups retain their complete
  part volumes; no disconnected part was silently dropped.
- Inspected hook, crank-slot, body-relief and lip-exit PNGs. They are diagnostic
  overlays; scale/legend/occlusion limit some views. Numerical evidence remains
  necessary. The default scene has not been demonstrated wrong by the negative
  tests below; the defect is in the required fidelity acceptance coverage.
- Read actual native ordinary reviewer transcript: 57 assistant messages all
  `anthropic/claude-opus-5-5`, final approval after D1–D4 fixes, SHA256
  `9242e4341d1d5f6cb1df1fa1c355233b547c15f777c46fb448431154b524ecf5`.
  Separate test worker: 66 configured DeepSeek messages. Exported copy hash
  `38aa64357b733fba99638c4080697900226cade3083d4bc3ca21a0921ea84880`
  matches all first 221 native records; native now has one extra `custom`
  lifecycle record and hash
  `c8b4e7cdb6674ff937ed1ea35c904b7094d61e72291e375d287c84141d1db7af`.
  No message/review substitution is implied by that lifecycle append. Saved
  fresh metadata/final text in the Supervisor output directory.
- Full-press smoke uses its own 1 mm smoke threshold, not the planned S0 0.2 mm
  gate. Its **0.7909 mm** peak, 13/20 steps over 0.2 mm and 0.221 mm terminal
  penetration are retained. This is a numerical/fidelity risk, not physical FAIL
  or S0 acceptance. The real bullnose/floor tangency is zero clearance, changing
  the prior geometric prediction; the original CAD was not altered.
- Frozen acceptance raw SHA256 remains
  `518a45ffc4592ca602be4c33c59681038e43dedaa15b688312202c3a57ff6ca2`.

## R1 — P2: mandatory dense void probes were replaced by sparse points

Approved plan §3.5 explicitly calls for dense ProbeSpec grids at 5 mm through
the relevant bore, exit, floor slot, local relief, bore/pocket and separator
voids. The implementation's body contract has only 4 floor-slot points, 3 notch
points, 3 relief points, 4 magazine-bore points and 2 exit points. Existing tests
prove declared points are voids but never verify the required spatial coverage.

Independent negative probe added each of these colliders separately to the body
part's collider tuple, leaving CAD and every other input unchanged:

```python
ColliderSpec('bore_block', 'box', (3., 3., 3.), pos_mm=(30., 0., 20.))
ColliderSpec('exit_block', 'box', (3., 3., 3.), pos_mm=(86.5, -20., 5.))
```

Exact CAD intersection of each 6 mm blocker with the body is **0 mm³**: both
occupy actual void. Yet `validate_fidelity(mutated_body, body.fidelity)` returns
**ok=true, violations=[]** for BOTH. Raw observations and point counts:
`out/mujoco-m5a-supervisor-adapter/void-coverage-probe.json`.
Coverage-of-material metrics do not detect invented material, so the sparse
contracts can falsely approve material blocking the real magazine/exit path.

## ONE bounded remediation

- Implement the already approved spatial void coverage using deterministic
  grids with spacing at most 5 mm in the applicable usable void regions,
  denser/adapted coordinates where a narrow slot/bore requires it. Cover both
  lateral sides of the exit and the actual extent of the magazine bore, not
  merely the two negative centres. Preserve small-clearance boundary probes
  and transits as well as dense interior coverage. Do not place probes in CAD
  material or treat a welded peg as an empty assembled bore.
- Derive/check grid extents against actual CAD and installed-part geometry.
  Retain declared parent-filtered bore exceptions and documented approximation
  limits. If the expanded coverage exposes a real collider defect, correct only
  that original proxy; do not change CAD, add restraints, move the assembly,
  relax criteria or silently omit the failing void.
- Add independently authored tests for region extents/spacing, exact-CAD void
  validity and both blocker negatives, retaining the existing positive, hull,
  slot, local-relief and all-five reset/clearance checks. Do not merely add the
  two failing centres to a hand-picked point list or mirror a list's own length.
- Run fresh export/fidelity/compiled evidence and independent focused/regression
  tests. Preserve original evidence; write repair artifacts under a fresh
  `out/mujoco-m5a/adapter-static/fidelity-repair/` directory. Update report and
  manifests truthfully. Obtain configured ordinary reviewer follow-up, preserving
  native transcript/model evidence. No manual override or substitute if a
  required role fails.
- File surface remains project `colliders.py`, necessary project audit helpers,
  independent project tests and documentation. No generic production, CAD,
  params, frozen criteria, dependency or configuration changes. No S0 scenario
  batch, P0–P3, M6/M7, commit/push, deployment or supervisor/bridge mutations.

Limits before decision: successor5 used 3 operations / 1 remediation of 6 / 2;
3 operations / 1 cycle remain, deadline `1792679704903` unchanged. Cumulative
25 submitted operations / 10 remediation cycles. One REMEDIATE spends the last
cycle (cumulative 11); its next admission makes cumulative submissions 26.
No limits renewed. End repair for independent Codex review.

Current OMP context reports 369863 prompt tokens without compaction; supported
idle handoff/rotation may prepare this bounded repair after the decision. Preserve
all files/identifiers, keep remaining limits and confirm empty context plus exact
current-chat binding before admission. Rotation is not limit renewal or acceptance.

Exactly one review decision recorded for turn 3:
`REMEDIATE dec_0mvjdq99k6ffb0bc8c7fe5fa6`, idempotency key
`cadstudio-m5a1-adapter-static-remediate-void-grids`. Successor5 is now
3 operations / 2 remediations used; 3 operations / 0 cycles remain. Supported
handoff `ho_0mvjdqacdc1a33db1ba75c57c` applied to session
`01a16316-9fb7-764b-8352-ada5f3e548e2`, generation 3, confirmed empty. Host
ready/no active operation and exact current-chat wakeup binding reaffirmed.
Next request: `cadstudio-m5a1-fidelity-repair-01a1624d-1`. No renewal.
