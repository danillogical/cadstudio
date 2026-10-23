# M5a-1 next increment: original adapter, colliders and static fidelity

## Objective and admission boundary

Implement the remaining adapter/static portion of approved
`docs/mujoco-m5a-plan.md` §6.1, from pulled checkpoint `c76a1df` plus the
independently accepted generic S0 checks. Read the handoff, accepted plan,
`docs/mujoco-m5a-plan-acceptance.md`, renewal5 and the generic-check repair
acceptance record before edits. Use the existing managed OMP Turn Orchestrator,
configured roles and repository guidance (`CLAUDE.md`, project README, original
geometry, `plan-mujoco.md`, architecture §21 superseding provisional values).

ONE increment only: handoff items 3–5, assembly/options/lazy hooks, collider
contracts, static preflight, compiled five-fraction reset/clearance checks,
overlays and independent tests/review. This is implementation under an already
approved plan; no new planner process or native-plan claim. The full S0
scenario/readiness runs and final full-suite gate follow in a separate admission
after this scene is independently reviewed. An export or smoke run is never S0
or product acceptance.

Authorized production surface:
`projects/pocky/physics/{assembly,colliders,options,support,clearance_audit}.py`
and minimal package helpers, plus lazy hooks in `projects/pocky/__init__.py`.
Add new independent `tests/test_pocky_physics_assembly.py` and
`tests/test_pocky_physics_colliders.py`, necessary focused docs, and
`docs/mujoco-m5a-1-adapter-static-report.md`. Existing tests and generic cadkit
sources are preserved. If an actual generic API gap blocks this scope, document
the concrete gap and stop for a new bounded admission; do not bypass the runner,
invent a competing CLI or relax a fidelity gate.

No CAD/params/export-source changes, frozen presentation-criteria edits,
dependency/configuration changes, packet simulation, P0–P3/M5a-2 decisions,
dispensing, support-seat/bracing redesign, M6, physical M7, commit/push or
deployment. Human owns model/provider/effort/role/fallback choices. No overrides,
manual substitutes or security-reviewer gate. Required configured-role failure
blocks its gate. No bridge-journal edits, supervisor verdicts or self-renewal.

## Assembly and physical inputs

- Use explicit `static_solids` + `moving_solids` inventory. Exclude the bench
  dummy and spare `shim_08`; every installed part appears exactly once. Preserve
  the installed spring length, original solids and assumptions/provenance. Do
  not enumerate `model.build()` as the assembly inventory.
- Runtime always builds at fraction 0. Group body+two installed shims; independent
  free lip; free chassis+spring-seat+pivot-peg; crank+pusher-peg hinged to chassis;
  rod+button-peg+installed spring visual/mass sliding on chassis; pusher sliding
  on chassis. No double mass/pegs. Only the legitimate analytic floor is fixed
  to the world, top z = −19.2 mm. Record masses, COM, inertia, grouping and units.
- Use actual CAD joint axes/anchors/ranges, pin-in-slot sibling contacts and
  default parent filtering as approved (§3.2–3.3). Parent-filtered guides and
  stops are joint/limit idealizations with force/return conclusions limited
  accordingly. No fixed-point connect, hidden weld/preload/restraint, clamped
  button or qpos writes after initialization. `pose_at_phi` is initial geometry
  and independent geometric reference only.
- Spring equivalent on `rod_x`: reference +0.003 m, nominal 500 N/m; approved
  200/1000 N/m sensitivity and 1/0.5 ms timesteps are strictly validated options.
  Keep contact and stop compliance fixed at 2 ms and declared damping/friction;
  do not enable colliding rigid spring beams. Record the unmeasured parameters
  and uncertainty. PETG is CAD/density-derived solid mass, not measured print.
- Baseline has zero packets. Reject unsupported loaded-packet/capacity options;
  packet seating, the 25-capacity variant and loaded/shared-state starts require
  later bounded planning approval. Read-only static reproduction of earlier
  seat geometry may be reported as a diagnostic; it authorizes no loaded scene.
- PETG colliders μ=0.40 priority 0; floor μ=0.50, with complete friction tuples
  and provenance. Lazy `physics` and `physics_with_options` hooks must work
  through existing project discovery/export paths; unrelated models still have
  no physics assembly. Strictly reject unknown, non-finite, unsupported or
  out-of-range options rather than silently ignoring them.

## Collider and compiled-scene gates

Follow the actual geometry and approved §3.5 recipes; counts there are estimates,
not permission to fill voids. Preserve body floor slot/local f=1 peg relief,
R2.1 bullnose and 0.4 mm underside gap, real clip surfaces/0.05 mm retention gap,
lip rails/feet/shims, exit/chamfer/separator, rod guides, boss bore and pin slots.
Concavities need explicit convex primitives. No whole-part hull, sealed hole,
filled slot end, long relief strip or invented downward housing seat.

Use fidelity contracts with meaningful independent probes/transits/coverage.
Critical planar surfaces and clearance mismatch tolerance remain 0.02 mm;
noncritical coverage gap 0.5 mm. The sector-approximated parent-filtered pivot
bore is a declared probe exception, not a global tolerance relaxation. Deliberate
hulled-body and slot-filled-crank variants must fail for the right reason.
Avoid diagnostics that merely compare a collider recipe to its own constants.

Derive ALL reset coordinates from `linkage_from`, `phi_for_button_fraction` and
`pose_at_phi` (§5.2), then compile/reset the runtime scene and inspect actual
`data.xpos/xquat` and `geom_xpos/geom_xmat` at fractions {0,.25,.5,.75,1}.
Quarter-stroke pusher travel must be 11.132495/38.867505 mm, not 12.5/37.5.
Compare crank rotation, rod/pusher displacement/sign and pin/face stations with
the independent CAD geometry at every fraction. Linear-reset and sign-flipped
pusher negatives must be rejected, including ≥1.367 mm quarter-stroke error.

Compute exact-solid initial overlap separately from collider penetration at all
five fractions. Any invalid overlap or a critical clearance mismatch is
SCENE_INVALID; it is never credible product FAIL. Clearance audits must use the
compiled transformed geoms at each reset, not just the fraction-0 recipe. Cover
body/pusher, body/chassis/clip, lip/body/shims, peg/slot, bullnose/floor and both
f=1 peg-head/relief and lip-rail/rod-head gaps using exact CAD distances and
independent collider distances. Report pairs, transforms, measured distances,
tolerances and provenance. No hidden separation or tolerance tuning.

Static bearing-direction and support-margin checks must report retention-only
clip geometry, hanging-group/body COMs, support hull/strip width, signed margins
and gravity moment. A support polygon cannot convert upward retention into a
downward bearing. The pre-recorded drop/load-path prediction stays a prediction
until actual S0 dynamics in the next admission.

## Evidence, independent tests and review

Regenerate missing planning geometry probes where necessary. Use existing
accepted generic APIs and `uv run --frozen --extra physics ...`. Evidence lives
under `out/mujoco-m5a/adapter-static/`: exact commands/logs, original and new
before/after manifests, explicit inventory/provenance/omission/idealization table,
CAD probe, static preflight, all-five compiled reset/clearance results, negative
cases, export XML/assets/hash reports, and overlays.

Show contrasting collider+CAD overlays for each relevant body and cutaway/
orthographic support, slot and exit views. Inspect the generated images, not
only file existence. Export `pocky/prototype` through the real CLI and compile
the resulting scene. One bounded no-actuation smoke (a few steps only) may verify
that sibling contacts execute; retain warnings and initial/numerical invalidity.
It is not an S0 verdict, spring validation or evidence of a physical prototype.

Assign tests to a worker other than the project implementation worker as required
by the handoff. Cover inventory/units/masses/grouping, openings/clearances/local
relief/bore, spring reference, all-five compiled transforms, negative resets,
negative hull/filled-slot contracts, only-floor-fixed/no hidden restraint, lazy
hooks and strict options. Use real compiled transforms and exact solids, not
only mocks or mirrored construction constants. Run focused new tests plus
relevant existing geometry/physics regressions. Full CAD suite once after the
final shared M5a-1 changes, in the following evidence increment.

Obtain configured ordinary code review of assembly/contact/load paths,
collider fidelity, tests and actual static/visual evidence; retain native
transcript path/hash and actual reviewer model attribution. Resolve demonstrated
in-scope defects without weakening original criteria. Record incomplete or
unavailable evidence truthfully and end for independent Codex review. Do not
claim M5a-1, S0, packet readiness or any physical gate complete, and do not start
the next scenario/evidence packet on your own.
