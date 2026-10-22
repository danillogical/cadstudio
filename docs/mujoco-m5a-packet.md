# M5a packet: original Pocky adapter, assembly stability and gravity readiness

## Objective and boundaries

Continue the human-authorized plan-mujoco.md through M7. Generic M0–M4 is
independently accepted (docs/mujoco-m4c-supervisor-acceptance.md). One bounded
M5a increment implements the ORIGINAL Pocky prototype physics adapter, real S0
assembly stability, and P0–P3 gravity readiness under declared assumptions.
A credible product FAIL is acceptable and useful. Never manufacture a product
PASS by adding restraints, rewriting geometry or tuning criteria.

Read CLAUDE.md, projects/pocky/README.md, plan-mujoco.md M5/P0–P3,
architecture §§1.4,7.2,8,10.1,17,21, the current CAD sources and project docs.
Architecture §21 overrides earlier provisional values/predictions. User objective:
one individually wrapped packet represented by a rigid165x55x5.2mm box, partly
protruding and supported for pickup after release; current housing allegedly
rests on only two chassis posts. This is a user observation, not measured trial data.

NO product CAD redesign, decorative/mechanism replacement, P4–P9 dispensing suite,
M6 candidates, printing or physical acceptance in this turn. M6 support-seat/bracing
is already authorized only after a concrete design review by Codex. Keep all original
CAD/params/exports recoverable and unchanged. Follow the updated managed-session
planning gate below and use the configured ordinary reviewer; human owns all
model/provider/effort/role/fallback choices.
No manual substitute or security-reviewer gate.

## Planning and separate implementation authorization

This packet defines the intended implementation scope, but its first resumed
operation is PLAN ONLY. Read docs/mujoco-m5a-planning-packet.md and the updated
orchestrator skill. The managed bridge exposes no native plan-mode activation API.
Produce the Markdown plan in the existing managed session with its configured
model, accurately recording actual mode/model. Do not launch a separate planner,
send literal /plan, or change routing. Codex must review the plan and boundary
evidence, then admit a SEPARATE explicitly authorized implementation operation.
No production, test, harness, configuration or service changes in the planning turn.

## Adapter and scene fidelity

1. Add the project adapter through existing Project.physics/discovery and generic
   run_assembly/export/CLI paths. Do not create a competing CLI or put Pocky names,
   geometry constants or thresholds in cadkit. Small generic additions actually
   needed by this adapter may be made with meaningful independent fixture tests.
2. Build an EXPLICIT assembly from static_solids/moving_solids, not model.build()
   enumeration. Exclude parked dummy and spare shim_08. Use correctly installed/
   compressed spring geometry at each initial button fraction, not the free spring
   intersecting the seat. Record exact-solid initial overlaps/clearances as well as
   collision penetration; do not silently separate a scene until it becomes valid.
3. Baseline chassis and housing must be free, chassis resting on the world floor,
   real clip contacts only: NO fixed_to_world, weld, hidden stabilization, retention
   preload or invented downward seat in the baseline. World floor is legitimate.
   Keep lip independent and its rail/shim support represented. Record any rigid
   grouping assumptions, masses, COM and inertia; never double-count pegs or shims.
4. Preserve actual voids/contact-sensitive surfaces: floor slot around pusher neck,
   R2.1 bullnose, carriage top0.4mm below body floor, clip underside/rib top0.05mm
   gap, ledges/shims/lip feet, front exit/chamfer/separator, rod guides, pivot boss,
   pins and slots. Decompose concavities into explicit convex proxies. A whole-part
   STL hull, bounding box sealing a hole, or solid cylinder filling a slot end is
   unacceptable. Validate proxy geometry/real pin travel/openings against CAD.
   Export overlays with the visual mesh and contrasting colliders, including
   cutaway/orthographic views answering the support, slot and exit questions.
5. Model the real constraint chain: free chassis root, crank hinge, rod and pusher
   sliders with actual pin-in-slot contact and travel. A fixed-point connect does
   not represent a variable-radius slot. Use pose_at_phi ONLY for initial geometry
   and independent geometric cross-checks; never set qpos from it during a run.
   Joint guide idealizations must be explicit and tied to actual CAD constraints.
   Preserve contact-enabled dynamic reaction/load paths; do not clamp the button
   to keep an initial fraction unless the whole run is labelled diagnostic.
6. Printed PETG spring return is a declared equivalent mechanical spring, not
   elasticity from rigid beam colliders. Choose/justify assumed or derived spring
   parameters with uncertainty/provenance, not a fictitious measured rate or the
   metal-catalogue proposal. Deforming spring geometry/contact limitations must
   be explicit; do not force rigid beam overlaps as it changes length. If linkage
   or spring fidelity cannot be validated, cap affected force/return/product
   conclusions at INCONCLUSIVE. A conservative carriage-force diagnostic is
   allowed only when labelled as such, never as a validated original linkage.
7. Packet proxies are free rigid boxes at165x55x5.2mm. Packet mass/friction are
   unknown: explicit assumed mass and ranges/provenance are required, not PETG
   density applied to the food packet or a claim that printed dummy mass is real
   packet mass. Printed structural masses may be CAD/density-derived assumptions
   (solid density vs actual infill unknown). Record all physical input sources.

## S0: actual assembly support, before gravity feed

- Run no-actuation gravity settlement for all initial button fractions
  {0,.25,.5,.75,1}. Fractions are INITIAL states only; mechanisms may respond to
  springs, gravity and contact during each independent trial.
- Report relative body/chassis translation and rotation, vertical body drop,
  contact body/part pairs, normal loads/duration especially housing resting on
  moving pusher/rod/peg, chassis grounding and final0.5s settling. Global uprightness
  alone cannot pass S0. The load path must carry downward weight via real contacts.
- Implement/retain static bearing-direction and support-margin checks. Retention-only
  upward clips cannot become downward supports because a support polygon looks good.
- Declare numeric diagnostic/load-duration tolerances and their geometry/solver
  rationale before candidates. Architecture's tight pose tolerances are provisional;
  principal failure is sustained unintended weight-bearing onto moving mechanisms.
  Do not force a0.4degree rotation or any preselected trajectory to match M0 prediction.
- Initial overlaps/invalid physics must not be labelled credible product failure.
  Separate numerical validity from actual observed support failure. Record both
  prediction and genuine dynamics, investigate discrepancies, never tune the scene
  to get the expectedFAIL. No unmeasured clip preload or friction rescue.
- Save complete native initial and gravity-settled checkpoints and hashes. Later
  gravity/feed cases start from ACTUALLY settled assembly state; do not silently
  restore the ideal CAD housing pose to make feeding work.

## P0–P3: gravity and stack readiness

- P0: one packet above the actual support/floor, verify early free-fall scale and
  settlement/contact. P1: one then two packets with the ejector genuinely clear,
  real gravity settlement. P2:10packet stack. P3:25packet stack. Record identity,
  positions/tilts, support/load balance, collisions/penetration and numerical validity.
- Do not achieve clearance by hidden fixed mechanism positions. If a diagnostic
  fixture is necessary, mark fixture=diagnostic and product predicates INCONCLUSIVE.
- All cases use the actual original assembly/proxies and bounded inputs, not the
  generic M4c fixture. Physics failure from an unstable housing may propagate as
  product FAIL; a credibleFAIL is accepted as a diagnostic milestone. Missing fidelity
  or solver sensitivity is INCONCLUSIVE, not a physical design result.
- Repeat a representative S0 case and the25packet case at base/half timestep with
  FIXED physical contact/stop compliance, friction, input and seed. Preserve M3
  refsafe guards. Status-changing/near-threshold results are INCONCLUSIVE; keep
  invalid/half-run evidence and do not choose the convenient timestep.
- Freeze the M4c presentation acceptance file unchanged (raw518a45ffc4592ca602be4c33c59681038e43dedaa15b688312202c3a57ff6ca2).
  Gravity-only cases may have their own frozen readiness criteria. For later
  dispensing, bind every potential packet identity from the full assembly catalogue
  into a resolved typed criterion, recording both base-criteria and resolved hashes;
  never monitor only the preferred packet or change numeric criteria to improve scores.

## Required outputs and validation

- Project adapter/modules/scenarios/criteria and concise commands through existing CLI;
  an explicit assembly inventory/provenance/omission/idealization table; CAD-vs-proxy
  checks, visual overlays and initial/settled complete state identities.
- Real S0 five-fraction results, P0–P3 results, representative convergence/sensitivity
  and same-runtime replay. Reports must be understandable without a GUI, retaining
  every failure/inconclusive artifact and unmeasured-input limitations.
- A truthful gate conclusion: whether original assembly readiness and diagnostic
  fidelity are established, what actually failed, what remains unmodelled and the
  concrete M6 support hypothesis if appropriate. No verified physical prototype claim.
- The approved planning artifact and separate implementation authorization must
  precede edits. Configured ordinary
  reviewer must inspect the adapter/load paths/constraints and actual evidence;
  record model used, fix demonstrated findings. No substitute if unavailable.
- Meaningful focused tests (proxy openings/units/transform/inventory/negative hidden
  restraints/initial overlap/state and output classification), existing physics/CAD
  regressions, then full suite once after final shared changes. Do not rewrite old
  tests to hide a failure. No CAD change is authorized in this packet.
- Write docs/mujoco-m5a-report.md with raw artifacts under out/mujoco-m5a/,
  exact commands, statuses and remaining uncertainty. End this bounded turn for
  independent Codex review. If the complete original linkage is not credible yet,
  retain partial work and explicitly identify the missing bounded subpacket; do
  not claim completeness from a simplified fixed-housing demonstration.

Successor3 run_0mvip90biee013608fa104d9d remains stopped after human pause;
its cancelled M5a attempt is not accepted. Explicit human resume and independent
renewal4 are recorded in docs/mujoco-supervision-renewal-4.md. Before resumed
planning admission cumulative19submitted ops/7remediations. New bounded successor
limits are10operations/2remediations/480minutes, including separate plan-only and
implementation admissions. No OMP self-renewal, scheduler or bridge verdict.
