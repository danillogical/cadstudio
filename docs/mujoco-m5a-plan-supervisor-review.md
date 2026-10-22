# M5a planning review: bounded plan correction required

Operation op_0mviyqlkz462e1d0a2dee9f1e, successor4
run_0mviyq59q90622f804e919ceb, turn1. Planning is not yet approved;
no implementation authorization is issued by this review.

## Independently verified evidence

- Operation is terminal completed; host34491 ready/no active operation.
- All99 accepted production/test/dependency/instruction/plan hashes remain exact.
  Before/after and fresh full nonvolatile inventory agree: only authorized
  docs/mujoco-m5a-plan.md and docs/mujoco-m5a-plan-review.md added, nothing changed
  or removed. Evidence out/mujoco-m5a-supervisor-planning/boundary-verification.json.
- Reviewer transcript SHA256 matches review-evidence.json;45 actual assistant
  records are anthropic/claude-opus-5-5. Its final approve text and stated review
  limits were inspected. No substituted model or security-reviewer gate.
- Plan accurately declares artifact-based managed planning, not native plan mode.
  Independent review caught and repaired several earlier draft defects, but the
  final plan still has the demonstrated correctness issues below.
- No simulation or tests run by supervisor: this is a planning-only review.
  Source-based arithmetic/counterexamples saved in
  out/mujoco-m5a-supervisor-planning/independent-probes.json.

## Required plan fixes before implementation

1. **Quarter-stroke pusher resets are not the real CAD mechanism pose.**
   In projects/pocky/geometry/linkage.py, phi_for_button_fraction uses the cotangent
   of phi for linear button travel; pose_at_phi then uses radius*cos(phi) for
   pusher travel. Those are different functions. At button fractions0.25/0.75,
   pusher displacements are11.132495094/38.867504906mm, not12.5/37.5mm. The
   1.367504906mm reset error exceeds the0.3mm nominal pin/slot side clearance,
   creating an artificial initial overlap/contact impulse. Derive every reset
   coordinate from the actual CAD helpers, including angle relative to home,
   rod/button travel and pusher displacement. Add a planned compiled-transform
   cross-check at ALL five fractions, with a negative test for these linear
   pusher resets. Static CAD-only overlap at the correct pose is insufficient
   to verify the independently specified runtime resets.

2. **Relative-pose formula contradicts the named body_a frame.**
   Schema frames map local points into assembly/world coordinates. Under that
   convention the relative transform is inverse(T_a)*T_b, not T_b*inverse(T_a)
   as section5.3 states. Use p_rel=transpose(R_a)*(p_b-p_a),
   R_rel=transpose(R_a)*R_b, with explicit initial/current comparison and
   quaternion-angle convention. Counterexample: A at(1,0,0)mm and B at(1,1,0)mm,
   both yaw90deg. Correct p_rel=(1,0,0)mm. The planned order gives(0,1,0)mm and
   changes to(-1,0,0)mm after a common90deg world rotation, falsely measuring
   sqrt(2)mm of relative motion. Plan global rigid-transform invariance tests
   with translated/rotated frames plus a true relative-motion negative case.

3. **Downward-drop sign is unspecified and permits a false PASS.**
   relative_translation is described as a signed projected change with only
   an upper maximum. A0.4mm fall has delta_z=-0.0004m and satisfies
   delta_z<=+0.0001m. Define the body_drop predicate explicitly as positive
   downward displacement max(0,-delta_z), or use explicit lower/upper bounds;
   record axis/frame/order. Plan both downward-fall and upward-motion cases.
   Do not rely solely on a separate translation-norm check to mask this defect.

Clarify in the same revision how hold criteria observe the required entire
final0.5s and how threshold margins/force-duration sampling propagate through
replay. No code implementation is permitted to clarify these semantics.

## Approved direction, still subject to the corrected plan gate

Splitting M5a-1 adapter/static/S0 from M5a-2 packets is reasonable. Generic
friction/priority, hashed options routing and bound/replayed S0 checks address
real existing API gaps. Original product CAD and frozen criteria remain unchanged.
Guide/parent-contact idealizations may establish diagnostics only; they cannot
establish validated full mechanism/support or force conclusions if they remove
relevant load paths. Preserve the plan's INCONCLUSIVE limits and actual failures.
P0–P3 tilted seating,25-capacity parameter variant and loaded-settle/shared-state
import decisions are deferred until separate M5a-2 planning approval; they are
not implicitly approved now. No need to redo unrelated plan sections.

## Next bounded operation

REMEDIATE the PLAN ONLY: edit docs/mujoco-m5a-plan.md,
docs/mujoco-m5a-plan-review.md and evidence under out/mujoco-m5a-planning/.
Retain earlier review rounds/history; obtain configured ordinary reviewer
follow-up on the three fixes and hold/replay semantics. Capture before/after
manifests, reporting supervisor-authored review/orchestration additions as
pre-existing. No product/test/harness/config/service/CAD edits or implementation.
Return for independent Codex approval and a separate implementation operation.

Before decision successor4 uses1/10operations,0/2remediations, deadline1792667380525;
cumulative20submitted operations/7remediation cycles. One REMEDIATE will consume
one cycle; limits are not renewed or reset. Human owns model configuration.
