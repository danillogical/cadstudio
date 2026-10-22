# M3b bounded packet: mechanical fixture proof

Continue the existing human-authorized MuJoCo plan through M7, but this packet covers
only completion of generic M3 mechanics after reviewed M3a. Read the turn skill,
CLAUDE.md, this packet and M3a supervisor review. Use a SHORT actual native plan-role
request before production edits; preserve its inspectable output. Avoid long @file
planning calls/history dumps, which previously triggered provider failures. No global
model/provider/effort/fallback changes. Obtain independent code review and record it.

## Scope and interfaces

Own `cadkit/physics/mechanics.py`, `mechanics_run.py`, meaningful mechanics tests and
report. Minimal generic schema/emitter changes for explicit physically declared joint
stop compliance are allowed if necessary, with regressions. Preserve existing APIs
where reasonable and keep mechanics CLI working. No Pocky/armor CAD, product adapter,
M4 scenario framework or S0 claims. No new dependency required.

1. Use the declared 0.25kg slider mass through PartSpec.mass_kg, with provenance clearly
   marked assumed analytic-fixture input, not measured. Verify compiled mass/inertia.
   Ensure assembly-space solid and body-local collider frames agree. Select damping
   and settle duration analytically for this mass; do not rely on the old0.6g carriage.
2. Separate a no-friction loaded reference from a nonzero load/friction fixture.
   No-friction settled deflection must agree with independent F/k within2%; release
   must return to its reference/home within0.1mm after sufficient damping/settle.
   For nonzero friction, compare to independently derived static force/displacement
   bands (including friction/k residual) OR use an explicitly preloaded home stop for
   the0.1mm return check. Do not widen tolerances to fit outputs. Measure actual forces.
3. Exercise a joint stop under sustained bounded input sufficient to reach it, and
   again after release. State and test a finite penetration/overshoot allowance tied
   to declared physical compliance and resolution. Default range metadata or the
   existing0.428m excursion against0.05m limit is not stop validation. Keep compliance
   fixed in physical units across dt refinements; do not conceal failure with snapping.
4. Measure an undamped/frictionless slider release period against independent
   2*pi*sqrt(m/k) within5% (0.25kg and50N/m imply approximately0.44429s). This is distinct
   from the damped return test. Preserve independent hinge inertia and period reference,
   verify compiled effective inertia and period within5%, and a damped release case.
   A joint spring provides
   restoring force; rigid collision shapes cannot imply PETG elasticity.
5. Provide real absent/insufficient-input and missing-spring negatives. A valid dynamic
   negative must fail its named physical check, not be relabeled success. A zero spring
   may be represented by no spring; invalid schema inputs remain configuration errors.
   Do not weaken SpringSpec's positive stiffness contract to fabricate a valid zero.
6. Use jnt_dofadr for velocities/forces and jnt_qposadr for coordinates. CSV telemetry
   must distinguish requested control/effort, actual control, generalized actuation,
   spring/damping/friction/constraint forces, coordinates, velocities and input release.
   Record compiled dt, actual duration, mass/inertia, solver/contact/limit settings.
7. Before stepping, validate budgets. Nonfinite state/acceleration/input, every solver
   warning, excessive penetration, or declared huge energy/velocity spikes invalidates
   the trial and cannot yield PASS. Derive and document finite bounds for these analytic
   fixtures. Preserve raw strict JSON/CSV evidence; status and CLI exit must agree.
8. Compare actual base and half-dt runs with otherwise identical physical parameters,
   phase durations and thresholds; report convergence of relevant deflection, return,
   period, force and stop metrics. Same declared timestep is not evidence of refinement.

## Acceptance and evidence

Run meaningful live compiled integrations, adverse/invalid cases, existing M3a topology/
units/geared-force regressions, and relevant prior physics regressions. Full CAD suite
was checked by the supervisor after M3a; repeat only if shared changes justify it.
Write `docs/mujoco-m3b-report.md` with native plan evidence, completed work, independent
review/findings, exact commands/results, raw artifact paths, parameters/thresholds,
convergence results and unresolved issues. A partial result must be reported honestly.
Do not claim product success or physical calibration. Native short-plan failure is a
provider interruption; preserve/report it without changing model routing.

Existing successor run has max21operations/6remediations and deadline1792618090496;
before M3b it used6operations/3remediations, cumulative9operations across both runs.
One packet only, followed by independent Codex review. No self-renewal of limits.
