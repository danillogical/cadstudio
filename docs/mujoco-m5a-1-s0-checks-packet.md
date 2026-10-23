# M5a-1 resumed packet: bound S0 checks and replay

## Authorization and scope

The human invoked the OMP orchestrator with `docs/mujoco-m5a-1-handoff.md`, then
directed `pull from git`. The checkout fast-forwarded from `ca9a305` to `c76a1df`.
Resume the approved plan §6.1 from that partial implementation checkpoint.
Read `docs/mujoco-supervision-renewal-5.md`, the handoff, approved plan §5.3–5.4,
§8.1, and its acceptance record. This is a separate implementation authorization
for ONE bounded generic increment: handoff items 1–2, followed by configured
ordinary code review. It does not admit the Pocky adapter in this operation.

Use the existing managed OMP session and configured roles. Human-owned model,
provider, effort, role mappings and fallback settings must not be changed or
overridden. Do not substitute a reviewer if the configured role fails. No
security-reviewer gate, separate planner process, literal `/plan`, bridge
internals, journal edits, autonomous renewal or supervisor decisions.

Preserve the pulled additions and the human-approved narrowing of
`test_project_physics_defaults_to_none`. Production scope is
`cadkit/physics/{scenario,evaluate,telemetry,runner,replay}.py`, with a small
generic helper only if necessary and documented. Add new focused tests and a
packet report `docs/mujoco-m5a-1-s0-checks-report.md`. Do not edit existing tests
to hide failures. Do not edit CAD, params, frozen criteria, dependencies,
configuration, project hooks or adapter files. No commit, push or deployment.

## Required behavior

- Strictly load and round-trip `relative_pose`, `relative_translation` and
  `contact_duration`, with `max_rotation_rad`, `axis`, `frame`, `lower`, `upper`,
  `force_threshold_n`, and `window`. Validate body/phase references, units,
  finiteness and kind-specific fields. `relative_translation` requires both
  bounds and `lower <= upper`; world frame is permitted only for z. Fail
  closed for missing/incomplete measurement evidence.
- Compute attached-local relative position at EACH time:
  `p_rel(t) = R_a(t).T @ (p_b(t)-p_a(t))`; relative rotation is `R_a.T @ R_b`.
  Compare against the specified reference boundary. Never freeze the initial
  axes or reverse transform order. World-z translation separately compares
  world separation vectors, reports signed displacement and positive drop.
- Add `window="max_over_phase"` to the new pose/translation checks and
  `body_speed`. Preserve default end semantics. Every required integration-step
  observation in the phase contributes, including brief interior excursions.
  Record worst sample time/value and terminal value. For pose, retain evidence
  for BOTH translation and rotation so the smaller normalized threshold margin
  cannot hide failure of the other component. For signed bounds, test BOTH sides.
- Derive body-pair watches from acceptance in both runner and replay. Sum normal
  forces over ALL contact points/geoms in either body-pair order BEFORE applying
  the force threshold. Track the longest uninterrupted time above threshold at
  integration-step resolution. Zero contact is a valid zero; unknown evidence
  is not zero. Document phase/window endpoints and duration integration so a
  boundary or a short interruption cannot merge separate runs or add a step.
- Add an opt-in acceptance-level near-threshold band, 20% for future S0 files,
  off by default. Preserve prior M4 outcomes. Apply it to each relevant bound
  (both relative-pose components and both signed translation bounds), using
  worst-over-phase evidence; close results are INCONCLUSIVE, never fabricated
  PASS. Define zero/negative signed-bound behavior explicitly.
- Replay independently re-steps and recomputes the same watches, maxima, signed
  values, durations and near-threshold statuses from verified locks. Compare
  values with declared numeric tolerances and times within one sample interval.
  Do not trust recorded derived values or use sparse contact display rows as
  the gate. Preserve existing budget and validity guards.

## Independent test assignment and evidence

Assign tests to a worker OTHER than the implementation worker, as required by
the handoff. Give that worker the approved semantics and public APIs; coordinate
file ownership. Required cases include:

- yaw-90 A/B counterexample and wrong-order negative;
- rigid common rotation gives zero drift; reject the old 1.414214 mm result;
- fixed-coordinate invariance; true relative motion with superimposed common
  motion; no-motion negative; rotation-only threshold breach;
- both 0.4 mm fall and 0.4 mm lift fail the ±0.10 mm world-z bounds;
- reject world x/y and malformed, missing, incompatible fields/references;
- every-step interior maxima for pose, translation and speed; missing evidence;
- multi-point summed load versus per-point threshold, reversed pair order,
  longest separated episodes, interruption and exact phase-boundary cases;
- zero contact passes; opt-in near-threshold and unchanged default behavior;
- real generic fixture runs and same-runtime replay, including a tampered
  derived-record negative. Synthetic math tests alone do not prove live watches.

Use `uv run --frozen --extra physics ...`; the physics extra is required and
`uv.lock` must remain unchanged. Run new focused tests and existing physics
regressions. Defer the full CAD suite until final shared M5a-1 changes, per the
handoff; explicitly report that limitation. Record exact commands, exit codes,
logs, actual reviewer model/transcript evidence, before/after source manifests,
remaining defects and limitations under `out/mujoco-m5a-s0-checks/` and the report.
Have the configured ordinary reviewer inspect the new work AND pulled generic
changes in `ca9a305..c76a1df`; no completed reviewer evidence accompanied that
checkpoint. Resolve demonstrated findings within this packet's scope; surface
broader findings to Codex without silently expanding scope.

End the turn for independent Codex review. Do not start adapter/collider work,
P0–P3, M6 or M7, and do not claim M5a-1 or any product/physical gate complete.
Stop on an unavailable required role, unauthorized source changes, numerical
evidence failure or a scope conflict. The Supervisor owns the next admission.
