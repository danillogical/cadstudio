# M4c packet: generic events, synthetic failures and frozen presentation criteria

## Objective and boundaries

Finish generic M4 under the original human-authorized plan throughM7. M0–M3,
M4a and M4b are independently accepted. Read CLAUDE.md, plan-mujoco.md M4,
docs/mujoco-m4b-supervisor-acceptance.md, architecture §21 (overrides earlier
proposals), and your current orchestrator skill/OMP turn reference.

One bounded increment: typed generic event detection/evaluation integrated into
ordinary runs and replay, complete known synthetic failures, and immutable
provisional project acceptance configuration. NO actual Pocky physics adapter,
S0, product CAD edits, candidate redesign or physical trials in this packet.
The human removed the security-reviewer gate. Use only the configured ordinary
code reviewer; no separate security-reviewer request/gate. Models/providers,
role mappings, efforts, fallbacks and overrides remain exclusively human-owned.
No manual alternate-role review or model substitution on failure.

## Required generic behavior

- Add typed/schema-validated named event windows and event criteria using declared
  body identities, an exit plane/direction, rigid object extents and units. Avoid
  project-specific IDs/numbers in cadkit. APIs must work with typed run_assembly
  and allowlisted JSON fixture execution; no dynamic imports from config.
- Observe relevant state at EVERY integration step using coherent post-state
  data and explicit timestamp semantics, not sparse CSV alone. Preserve native
  complete-state archives, all M4a validity gates, bounded recording and M4b replay.
- Distinguish actual outward crossing in the configured direction from touching
  a plane, wrong-direction crossing or an object initially outside. Associate
  events with a bounded actuation/cycle window and stable body ID. Count distinct
  bodies, never count one object's crossing/re-crossing twice in one cycle.
  Distinguish zero-feed, exactly one, double feed and late/missed presentation.
- Presentation requires sufficient protrusion, accessible exposed length, supported
  COM and a continuous stable dwell AFTER input release in a named bounded window.
  Support must come from actual contacts/declared support surfaces with relevant
  gravity-normal load and the projected COM within their support hull. A body fixed
  to world, arbitrary pose, zero velocity, lone contact flag or upward normal alone
  cannot prove product support. Handle degeneracy/numerical uncertainty honestly.
- Detect loss of support before dwell, uncontrolled complete fallout, invalid/outside
  bounds and insufficient evidence. Report body IDs, crossing time/direction,
  protrusion/support/dwell evidence and clear machine-readable diagnosis codes.
  Numerical invalidity dominates a physical PASS. Empty or truncated observation
  must never pass; late success beyond the declared window must not rescue a failure.
- Phase/control semantics must identify release through real zero input; no setting
  packet qpos during a trial to manufacture events. Initial positions/reset are
  allowed. Explicit pickup/removal is only a recorded user action between cycles,
  never a way to make a failed dispense succeed; P9 pickup implementation is later.
- Save criteria and event configuration in the same locked/hash-bound run evidence.
  Replay must independently recompute events/criteria from actual re-stepped states
  and compare the results; copying saved event verdicts does not verify replay.
  Integrate with strict JSON/CSV/report schema, CLI status/exit consistency and all
  archive/resource/path guards. Update formats explicitly if necessary.

## Synthetic and real fixtures; acceptance evidence

- Use an independent non-Pocky generic physically driven fixture with a free rigid
  body, true open multipart aperture, contact support and bounded mechanical input.
  Show a real valid supported partial-presentation positive and physical negatives
  for missing force and blocked aperture. Reuse accepted hollow/actuation recipes;
  do not replace these with manually authored trajectories or qpos animation.
- Complete required M4 failures: no gravity, wrong unit scale, blocked opening,
  missing force and duplicate event. Attribute each honestly as ERROR, FAIL or
  INCONCLUSIVE under the established vocabulary. A deliberately malformed schema
  negative is distinct from an actual dynamics negative; label that distinction.
- Add event-unit/adverse tests for wrong direction, touch only, initial outside,
  same ID crossing/re-crossing, two distinct bodies, early/late windows, release
  timing, dwell just below/at threshold, support lost midway and total fallout.
  Synthetic trajectory tests are legitimate for pure detector edge cases, but
  must be explicitly synthetic and accompanied by real MuJoCo runner/replay tests.
- Repeat the real positive and a real failure in the pinned environment; verify
  toleranced metrics/events and equivalent verdicts under replay. Keep timestamps,
  contact sampling semantics, seeds/runtime and source/config hashes inspectable.
  Preserve failure artifacts; no GUI is needed to understand results.

## Freeze project criteria before M6 candidates

Read projects/pocky/README.md BEFORE writing there. It is permitted to add only the
versioned frozen acceptance configuration under projects/pocky/physics/acceptance.toml
(or a justified existing-project equivalent), not an adapter or CAD in this turn.
Use architecture §21's authoritative provisional defaults:
- rigid packet165x55x5.2mm, partly protruding supported pickup, exactly one identity;
- minimum30mm beyond outer face x=88mm, target40mm informational;
- at least10mm exposed beyond the18mm shelf;
- continuous hold>=0.5s after release, protrusion change<=1mm;
- supported COM, no uncontrolled fallout/no second packet and housing stability.
Record the source/provisional engineering provenance; these are NOT bench measurements.
Do not copy the superseded15mm accessibility proposal from architecture §16.
M5 adapter and S0 are NOT run or claimed here. No candidate may tune these criteria.
Freeze other necessary generic diagnostic tolerances explicitly with rationale;
near-threshold/contact-sensitive outcomes require refined trials or INCONCLUSIVE.

## Execution, review, limits and report

Obtain actual substantive configured native plan output BEFORE production edits;
recent native plans take~200–265s. Keep the native plan role, no custom planner.
Bound work/delegation as OMP Turn Orchestrator. Use configured ordinary reviewer
only, fix actual findings, then meaningful focused tests and full suite once after
final shared changes. No model/effort/fallback/config changes, separate security
review gate, new scheduler, bridge verdict or self-renewal.

Report docs/mujoco-m4c-report.md with exact APIs/files, schema changes, frozen
criteria hashes, actual review, commands/tests, raw positive/negative and replay
artifacts under ~/.omp-bridge/diagnostics/, limits and remaining uncertainty.
Do not claim M4 complete without all required real/synthetic event evidence. Stop
this bounded turn for independent Codex acceptance. M5a/S0/P0–P3 follows later,
then M5b/P4–P9, M6 bounded support redesign and M7 software/physical evidence.

Linked successor3 limits are in docs/mujoco-supervision-renewal-3.md:8operations,
2remediations,480minutes from creation. Cumulative prior16ops/6remediations retained.
This is the first operation of that successor, not permission to reopen the old run.
