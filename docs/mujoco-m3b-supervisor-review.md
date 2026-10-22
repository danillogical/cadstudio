# M3b independent review: remediation required

Operation `op_0mviawaimea8746dbb0fccbab`, generation3, run
`run_0mvi5dou92f2f6dc40f0d6379`, admitted by
`dec_0mviavva9e5940f67ff9da7dc`. M3b/M3 gate **not accepted**.

Substantial progress is real: declared mass, force-driven slider/hinge periods,
damped return, friction band, loaded limits, and expected negative trials execute.
Supervisor independently ran56mechanics tests (2.47s) plus96scene/hollow/export CLI
tests (29.04s), all passing. OMP reports428full-suite passing; supervisor did not
repeat the entire CAD suite this turn. Source comparison confirms changes are in
the permitted mechanics/schema/emitter/CLI/test scope, with no product CAD changes.
Native plan evidence and its limitations are inspectable at the reported plan path.

## 1. False PASS when half-dt trial is invalid or fails a physical check

`run_mechanics` computes validity and physical success from base.values() only.
Half trials feed only a subset of convergence metrics, then are discarded from the
summary and CSV output. `_convergence` does not consult trial.valid/checks.

Independent fault-injection test runs actual base/half physics, then marks only the
half-dt hinge_damped invalid with a sentinel reason. Summary still returns **PASS**.
The sentinel is an injected validity fault, not an observed spontaneous solver failure;
it demonstrates the acceptance aggregation bug directly. A failed physical check in
the half run has the same unhandled path. Raw evidence preserved at:
`/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m3b-supervisor-20261021/probes/supervisor_probe.json`
and its aggregate subdirectory.

Required: every base AND half positive must be valid and pass all required checks;
invalid -> INCONCLUSIVE, valid physical failure -> FAIL (subject to explicit numerical
convergence precedence). Persist the complete half trials, checks, warnings and CSVs.
Add regressions for injected half invalidity AND failed required check while keeping
the comparison metrics unchanged. Include the damped hinge in convergence or explicitly
limit the claim; add relevant force/return comparisons requested by the packet.

## 2. Equal stored solref does not establish equal effective physics at accepted dt

The runner accepts timestep_s=0.002 and returns PASS with stop tc=0.002 in both stored
models. MuJoCo refsafe is enabled, so the effective time constant is clamped to at least
2*dt for RK4. The base and half runs therefore have different effective compliance.
Independent identical-state q=0.0201m, zero velocity, ctrl=2N probe:

| dt | stored solref | constraint force |
|---|---|---|
|0.001s|(0.002,1)|-7.4238905817174174N|
|0.002s|(0.002,1)|-3.207472645429354N|

Full actual dt0.002 run reports PASS and steady penetration14.2582um versus3.5654um
at half dt0.001. Raw run preserved under diagnostic `dt002/run` above. Official primary
reference: [MuJoCo solver parameters](https://mujoco.readthedocs.io/en/stable/modeling.html#solver-parameters)
documents the two-timestep safety floor. The existing default1ms/half0.5ms pair meets
this requirement; its results are not disproved by this separate accepted-input bug.

Required: reject incompatible requested dt BEFORE any stepping (or explicitly report
and compare a fixed effective compliance with a justified supported method). Keep the
declared physical constant unchanged; do not disable refsafe merely to make a test pass.
Guard relevant contact and limit time constants for both compiled models. Record the
effective boundary and show the same-state force agrees at the supported default pair.
Minimal generic validation tightening is in scope; preserve M2b default/convergence.

## 3. Telemetry calls raw control 'actual clamped control'

Real oversaturation probe through _Recorder with ctrl=1e6 yields
ctrl_requested=1e6, ctrl_actual=1e6, actuator_force=2N, qfrc_actuator=2N.
MuJoCo clips the applied signal internally without rewriting data.ctrl. The force cap
works, but this column/docstring is misleading. Preserve raw stored control explicitly,
record effective/clipped control separately under the fixture's declared transmission
and solver flags, and retain actual generalized force. Test over-request input so raw,
effective and applied force are distinguished. Do not rewrite data.ctrl to fake evidence.

## 4. Required settled frictionless F/k check is still absent

Undamped oscillation centre over an integer period is useful dynamic evidence, but the
packet requires settled static deflection within2%. Existing damped trial already has
x_after_push=0.01996009192053467m versus F/k=0.020m, so add a named2% settled statics
check with suitable settled-speed evidence there. Keep the oscillation-centre test as
additional evidence; do not present it as steady state. No tolerance widening needed.
The released undamped oscillator is centered on springref0, not F/k: fix the erroneous
period-extraction offset/comment and measure crossings about its actual reference.

## Bounded repair and preserved state

One M3b remediation packet for findings1–4 only, including per-step finite qacc/input/
force/energy checks consistently across both slider and hinge paths as originally
required. Preserve previously passing physical fixtures and all tolerances. No M4,
product adapter, CAD edits or global model/provider/effort/fallback changes. Use a SHORT
native plan and focused compiled/adverse regressions, then independent review. Write
`docs/mujoco-m3b-repair-report.md` with actual evidence and limitations.

Preserved partial snapshot:
`/Users/daniel_l_newman/.omp-bridge/backups/cadstudio-mujoco-m3b-partial-20261021T174604Z/`.
Before remediation decision: successor7/21ops,3/6remediations; cumulative10submitted
ops/3remediations,14ops remain. Deadline1792618090496 unchanged. M0–M2b and M3a stay
accepted; M3b and M4–M7 remain open. S0 real housing instability remains M5a.
