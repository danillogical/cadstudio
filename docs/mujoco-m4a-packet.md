# M4a: typed scenario execution and evidence

This is the next bounded increment after accepted generic M3 mechanics. Implement only
M4a, then return evidence for Codex review. M4b will add complete replay/hash-tamper and
identity/direction/dwell event fixtures before M4 acceptance. M5 owns the real Pocky
adapter and S0. No product CAD, candidate redesign, dependency/global model changes.

Read the turn skill, CLAUDE.md, plan-mujoco.md M4, architecture sections12/21 and the
M3b acceptance review. Use narrow reads. Before production edits, obtain an actual short
configured native plan-role result covering this packet. A timeout or 'Working...' is
not a completed plan: retrieve/resolve it through the native mechanism before edits;
report interruption honestly if unavailable. Preserve roles, effort and fallback config.
OMP owns routine API/file choices and bounded delegation. Obtain independent code review;
request the configured security reviewer if applicable to the loader/path boundary.
If disabled/unavailable, disclose that without enabling/changing it and have the independent
reviewer explicitly inspect parsing, asset paths and output handling.

## Required behavior

1. Add typed/versioned scenario and phase definitions, plus strict JSON loading. Use
   declarative allowlisted fields/fixture registry, not eval/exec, shell commands,
   arbitrary imports or deserialized Python objects. Reject unknown fields, nonfinite
   values, invalid references, invalid ranges/durations and unsupported versions.
   Publish machine-readable JSON schemas without adding dependencies unnecessarily.
2. Implement a generic headless runner over AssemblySpec/exported MuJoCo models with
   reset/settle/actuate/release/hold phases. Each run has independent state, a recorded
   seed and deterministic ordering. Positions may only be set for declared reset initial
   conditions; motion after reset must come from force/contact/gravity. Explicit zero
   input on release. Record phase boundaries, requested and actual durations/step counts.
   Preflight the TOTAL rounded phase step count, time and trace budgets before stepping;
   reject zero-step or unrepresentable phases explicitly, without silently dropping them.
3. Drive named actuators with bounded physical effort (N/Nm), record requested effort,
   raw/effective motor control and actual generalized force with correct gear/sign/limits.
   Reuse the accepted schema/exporter and mechanics references; don't create competing
   units, silently fixed product bodies or scripted outcome corrections. Import solver
   lazily so existing CAD commands work without the optional extra.
4. Sample states, joint coordinate/dof velocity, body/COM poses, input/passive/constraint
   forces and named contact body/geom pairs with normal forces/penetration. Keep SI in
   the raw data, make units explicit, and record per-step maxima independently of sparse
   display sampling. Distinguish state time and force-evaluation time or synchronize them
   without rewriting physical state. Include initial, post-settle and terminal states.
5. Centralize validity and evaluation. Invalid scene/build/unit/compile/file failure is
   ERROR/3; numerical invalidity, sensitivity or insufficient evidence is INCONCLUSIVE/2;
   valid unmet physical predicate is FAIL/1; valid complete satisfied checks is PASS/0.
   Invalidity must prevent PASS even when a physical predicate appears true. Empty or
   missing required checks cannot pass. Keep per-check reasons and stage/time of failure.
   Check finite states/acceleration/forces/energy/control, every solver warning, declared
   penetration/speed/energy bounds and resolvable contact/limit compliance. No silent resets.
6. Use declarative named metric windows/predicates sufficient for generic fixtures
   (e.g. held displacement, release return, terminal speed, effort bound). Freeze/copy
   acceptance separately from candidate design inputs and hash it. Do not derive a looser
   threshold from a candidate's geometry or outcomes. Analytic fixtures may PASS under
   declared assumed parameters; this is distinct from calibrated product acceptance.
7. Write a versioned manifest, strict JSON summary, readable report, CSV telemetry and
   numeric state archive for later replay. Include runtime/platform/solver versions,
   resolved physical inputs/provenance, scene XML/assets, scenario/seed/acceptance identity,
   initial and settled states and hashes. Use explicit UTF-8, safe asset references and
   unique output directories; never overwrite an existing run. Failure artifacts should
   preserve diagnosable partial evidence when a run was admitted. Do not deserialize pickle.
   Choose state capture compatible with full deterministic M4b replay, not just qpos/qvel.
8. Expose a thin CLI using the current `cad physics` family for the generic fixtures and
   JSON scenario input. Do not advertise Pocky support yet. API result, summary, report
   and CLI exit must agree for all four statuses. Existing smoke/export/channel/mechanics
   commands and CAD export semantics must keep working.

## Evidence and scope boundary

Execute the same loaded slider in the GENERIC runner, not by simply returning the old
mechanics summary. Show two same-seed/reset runs agree within stated tolerances, actual
force-limited actuation followed by spring return, and real missing-force / missing-spring
named failures. Add numerical-fault tests, malformed configuration/budget/asset/output
negatives and regression coverage preventing false PASS. Inspect report and raw states/
trace yourself. Run relevant prior physics tests and shared CLI/lazy-import regressions.
Run full suite once if shared changes justify it. Required report:
`docs/mujoco-m4a-report.md`, with native plan output, independent review, exact commands,
raw artifact paths, statuses, determinism results and remaining M4b work. No M4 or product
acceptance claims yet. S0 and physical M7 measurements remain unverified.

Supervision is the existing human-authorized M0–M7 objective, not a new task. Current
linked successor2 is `run_0mvihmvsm9f3be51a0fd22543`, max12ops/2remediations,
deadline1792638674806. It starts at0operations/0remediations while preserving cumulative
prior12submitted bridge operations/4remediations. Prior M4a attempt failed immediately
on WorkBuddy429, no implementation. Human explicitly switched the global DeepSeek role
targets to opencode-go/deepseek-v4.1-flash with efforts preserved; native default/plan/smol
reachability passed. Do not revert that global change or make further model/fallback edits.
Independent renewal review: `docs/mujoco-supervision-renewal-2.md`; handoff
`ho_0mvihky4i36017cb36bcc3a1c`. No self-renewal or new scheduler.
