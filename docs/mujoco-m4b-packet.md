# M4b packet: trustworthy generic replay and adapter boundary

## Objective and current authority

Continue the original human instruction to orchestrate plan-mujoco.md through M7.
One bounded increment: deterministic replay and evidence identity for the accepted
M4a generic runner, plus the small typed AssemblySpec execution interface needed
by later project adapters. M4 is NOT complete until a separate M4c event/synthetic
packet is reviewed. Do not start M4c, Pocky adapter, product CAD or M5 in this turn.
Read CLAUDE.md, the orchestration skill's OMP Turn Orchestrator reference,
docs/mujoco-m4a-supervisor-acceptance.md and current generic runner/telemetry.

The supervisor's final local follow-up checks live solver finiteness BEFORE a
scratch forward can replace derived values and checks both live/scratch warnings.
Preserve it and its regression tests. M0–M3 are accepted. M4a's fresh final suite
and limitations are recorded in its acceptance review. Do not change global role,
model, effort or fallback settings. The human's OpenCode Go DeepSeek routing is
permanent until further human instruction. Configured Step5 reviewer may still429;
security reviewer is unregistered. Disclose unavailability; use separate read-only
default-role reviewers where needed without reconfiguring anything.

## Required implementation and interfaces

1. Save complete integration state using this installed MuJoCo runtime's native
   mj_getState / mj_setState / mj_stateSize and mjSTATE_INTEGRATION (or justified
   versioned complete mask), recording mask, dimensions and runtime identity.
   qpos/qvel alone and selected hand-copied arrays are insufficient. Preserve
   actual reset and gravity-settled state identity. Record all inputs needed for
   each transition, including ctrl/applied forces and relevant activation,
   warmstart, mocap, equality/user/plugin/history fields supported by that mask.
   Clearly define row-to-control and phase-code-to-name mapping, especially the
   initial row and zero-duration reset. No one-based/zero-based ambiguity.
   Use the same complete native state transfer for scratch observations where
   applicable, so optional inputs and solver warmstart do not silently differ;
   preserve the read-only live validity checks and post-state force provenance.
2. Implement a public replay API and `cad physics replay <run-dir> --out <fresh-dir>`
   in the existing CLI. Rebuild/compile the SAVED scene and assets, restore saved
   initial integration state, apply recorded physical inputs at each transition,
   actually call mj_step, and compare the resulting state and independently
   recomputed checks/metrics/verdict with the source run using documented pinned
   runtime tolerances. Loading saved metrics, setting terminal qpos or regenerating
   current CAD instead of using saved scene does not prove replay. Retain source
   run provenance and replay comparison evidence. No source evidence overwrite.
   Restore and hash-check a post-settle checkpoint too; demonstrate that continuation
   from it reproduces the rest of the same run without teleporting outcomes.
3. Verify raw and semantic scenario/acceptance hashes, scene/assets, saved state/
   controls, manifest relationships and runtime/solver identity before replay.
   All effective compiled settings (including runtime-enabled energy flag or other
   post-XML changes) must be reproducible. Reject changed XML, assets, config,
   acceptance, archive or incompatible runtime as explicit ERROR. Corrupted evidence
   must never yield a PASS. State what hashes guarantee: internal consistency,
   not authenticity against coordinated rewriting of all hashes.
4. Treat replay files as untrusted input: bounded regular-file reads before parse,
   strict JSON and numeric shapes/dtypes, finite states, allow_pickle=False,
   safe archive members and decompressed byte/row/step/wall-time budgets checked
   BEFORE allocating or stepping. Reject zip bombs, duplicate/unexpected members,
   object arrays, malformed phase/control alignment and out-of-range state masks.
   Constrain all scene/asset references to the saved run; no absolute/parent traversal,
   symlink escapes, external XML includes or arbitrary module imports. Prefer a
   verified in-memory asset map for compilation. Avoid TOCTOU between checking
   bytes and compiling/loading those bytes. Keep tests fast with small fixtures.
5. Enforce state-archive byte/row budgets during ordinary run preflight as well,
   before creating huge per-step arrays. Existing step/trace/contact budgets and
   all four statuses remain effective. No materialized unbounded arrays just to
   inspect a header. Reject unsupported integrators explicitly as M4a does.
6. Expose a small typed `run_assembly(spec, scenario, acceptance, out, ...)` public
   API (or clear equivalent) so M5 project adapters can use the same generic runner
   without editing fixture registry. Keep JSON fixture names allowlisted and no
   dynamic imports from config. Prove this API on an independent non-Pocky fixture.
   Do not introduce Pocky names or criteria into cadkit.

## Acceptance and evidence

- Genuine replay at least: loaded spring slider, negative gear/effort clipping,
  and freely falling body under Euler AND RK4. Repeated pinned-runtime runs must
  agree on classification and justified state/metric tolerances. Save raw CLI runs.
- Positive and physical FAIL source runs replay equivalently; invalid/incomplete
  source runs must be explicitly handled without upgrading them to acceptance.
  Preserve INCONCLUSIVE for numerical invalidity and ERROR for invalid inputs.
- Distinct adversarial tests for scene, mesh asset, scenario, acceptance, state,
  controls, version/mask/shape and path/archive tampering. Demonstrate failures
  before mj_step/allocation where applicable, and unchanged source hashes after
  replay. A metadata-only replay test is insufficient.
- Native configured plan role must return inspectable substantive output BEFORE
  production edits. It can take ~160s; native reachability is not planning evidence.
- Independent read-only OMP review, including archive/path/runtime boundary review.
  Fix demonstrated defects before reporting completion. No new scheduler, model
  fallback or broad project edits. OMP must not issue bridge acceptance decisions.
- Focused meaningful tests, accepted prior mechanics/runner regressions, then full
  suite once after final shared changes. Do not rewrite existing expectations to
  hide defects. Preserve CAD and all M3 behavior. Raw evidence outside source tree
  under ~/.omp-bridge/diagnostics/, report docs/mujoco-m4b-report.md with commands,
  runtime, outcomes, actual review and residual limits. No claim of physical trials.

## Limits and next increment

Current successor2 run run_0mvihmvsm9f3be51a0fd22543, max12operations/2remediations,
deadline1792638674806. Before M4b dispatch:2operations/1remediation in this run,
cumulative14submitted operations/5remediations across linked runs. This packet uses
one operation;10operations/1remediation remain before admission. Do not self-renew.
If blocked, retain partial artifacts and report the specific cause. End this bounded
turn when replay/adapter evidence is ready for independent Codex review.

Next M4c will cover named presentation events (identity, direction, windows,
anti-doublecount, supported dwell), all required synthetic failures and frozen
provisional Pocky thresholds from architecture §21. M5a then implements actual
Pocky assembly/S0/P0–P3; M5b P4–P9. M6 support-seat/bracing remains authorized only
after a concrete supervisor design review. M7 physical data remain UNVERIFIED.
