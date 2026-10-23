# Fidelity repair review: not accepted; configured provider exhausted

Operation `op_0mvjdr70n550c446dbb4c5913`, generation 3, successor5
`run_0mvj62atk8b61da9fe2edf2ea`, turn 4, authorized by
`dec_0mvjdq99k6ffb0bc8c7fe5fa6`. The bridge calls the operation terminal
completed, but that is not implementation acceptance. The actual primary
transcript ends with provider errors, and the actual configured reviewer says
**not approved**. S0 scenario/evidence work remains unadmitted.

## Verified progress and unresolved findings

- Original bore/exit blocker negatives are repaired: 6843 points in 13 declared
  regions, plus retained seeds/transits. Independently reran both original 6 mm
  negatives; each now fails for the corresponding dense bore/exit grid.
- Exact source CAD, generic cadkit, params, dependencies and frozen presentation
  criteria remain preserved. Fresh export XML is byte-identical to the original
  physical scene. This repair modifies fidelity contracts, not the mechanism.
- Inspected grid generation/filtering and independent test source. Actual native
  configured reviewer transcript has 34 assistant messages all attributed to
  `anthropic/claude-opus-5-5`; its final visible verdict is **not approved**.
  Separate test worker has 92 assistant messages all configured DeepSeek.
  Fresh paths, hashes and visible final texts are retained at
  `out/mujoco-m5a-supervisor-fidelity/reviewer-verification.json`.
- Independently reproduced the reviewer's remaining channel defect: a 6 mm
  chassis blocker centered at `(-82,-28,-10.9)` has **zero overlap with every
  installed fraction-0 CAD solid** but still passes fidelity without violations.
  The same box intersects the actual moving rod by **41.2695 mm³ at f=.5** and
  **82.8000 mm³ at f=1**. The current `rod_channel_grid` is only a line at
  `(x,-28,-16)`, so it does not cover the claimed channel volume. Parent-filtered
  dynamics do not prove that the contact-sensitive CAD corridor is preserved.
- Independently removed the 12 bore-grid points in an interior 12 mm cube around
  `(0,0,40)`. The region-density test STILL PASSES because it checks only each
  axis's coordinate set. A 6 mm collider in that hole then also passes fidelity.
  Tests need a volumetric coverage/occupancy guarantee, not marginal axis counts
  or just the two fixed negative centres.
- The report's claim that filtering other independently moving parts is
  "stricter, not weaker" is incorrect. A part's own welded-group void differs
  from an assembly-empty region. Excluding the lip/rod at their initial positions
  can remove coverage where other bodies later move. Own-group material and
  welded pegs must remain excluded; separately owned moving-body occupancy must
  not silently be represented as a stronger void guarantee. Initial compiled
  overlap checks are an additional gate, not proof of this claim.
- After-manifest has 218 entries, with one stale hash for the adapter/static
  report; the new fidelity-repair report is absent. The actual reviewer confirms
  this. Final manifests/reports were not reconciled before the provider failed.
  Missing/stale evidence is not accepted.

Independent reproducer and raw results:
`out/mujoco-m5a-supervisor-fidelity/probe_remaining_coverage.py` and
`remaining-coverage-probes.json`. It runs actual CAD booleans, current fidelity
validation and the density test with an in-memory mutation. No source geometry
or criterion was changed by these probes.

## Provider gate and execution outcome

The primary managed OMP role actually failed twice after receiving the review:

```text
provider: opencode-go
model: deepseek-v4.1-flash
stopReason: error
errorStatus: 429
429 Go usage limit exceeded (type=GoUsageLimitError)
```

The final native record reports `retry-after-ms=304429000` at epoch
`1792668371454`, corresponding to **2026-10-26 00:00 UTC / October 25,
5 PM PDT** as the provider-reported retry time. This is well beyond the
current supervision deadline; no identical retry is credible now. This is not a
Codex account limit, reviewer approval, or a successful repair completion.
Raw primary error metadata is retained in
`out/mujoco-m5a-supervisor-fidelity/primary-errors.json`.

Current human-owned configuration still routes default/task roles to OpenCode Go
DeepSeek, ordinary review to configured Opus, fallback disabled with no chains
or overrides. No model/provider/effort/role/fallback settings were changed, and
no substitute role was used. Per the orchestrator skill's shared model policy,
an unavailable required role must be preserved and reported for the human to
handle; the Supervisor cannot choose a replacement or silently implement via a
different agent.

## Resume boundary after the human handles routing or the quota resets

1. Reconcile exact checkout/source hashes, host/session/queue state, current
   human-owned routing and actual role availability. Preserve all accepted and
   partial uncommitted work and raw negative/control evidence.
2. Fix the genuine remaining channel-volume coverage and volumetric test gap,
   clarify own-welded-group versus assembly-empty void claims, and refresh final
   reports/manifests AFTER final edits. Retain initial collision and all-five
   reset/clearance gates. Use configured ordinary review; no manual overrides,
   substitutes, CAD redesign, restraints or numeric criterion tuning.
3. Same approved M5a-1 objective. No S0, P0–P3, M6/M7, commit/push or deployment
   is authorized until the static repair passes independent review and a
   separate next increment is admitted.
4. Successor5 used **4 operations / 2 remediations of 6 / 2**, remaining
   **2 operations / 0 correction cycles**, deadline `1792679704903`. Cumulative
   **26 submitted operations / 11 remediation cycles**. No limits renewed here.
   A linked bounded successor requires the skill's fresh independent renewal
   review and concrete corrective advisement AFTER the provider gate is resolved;
   never reopen the old journal or reuse consumed authorizations.

The human was asked how to proceed with the unavailable configured provider.
That question is about human-owned routing/wait preference, not renewed
permission for already authorized implementation. The task is not complete.

## Supervisor regressions

Independently ran, with `~/.local/bin` on PATH:
`uv run --frozen --extra physics pytest tests/test_pocky_physics_assembly.py
tests/test_pocky_physics_colliders.py tests/test_pocky_physics_void_coverage.py
tests/test_cadkit_physics_export_cli.py -q`.
**119 passed in 231.05 s**, exit 0. This does not negate the independently
demonstrated coverage defects. Log retained at
`out/mujoco-m5a-supervisor-fidelity/focused-regressions.log`. Full CAD suite
remains due after final shared M5a-1 changes; it was not repeated here.

Exactly one review decision recorded for turn 4:
`REQUEST_HUMAN dec_0mvjgn8lk8c1c60f8bdc6e720`, idempotency key
`cadstudio-m5a1-fidelity-repair-provider-block`. The bridge confirms successor5
is **escalated**, no next-operation authorization. No renewal or duplicate
dispatch occurred. The configured provider remains unchanged; host was ready
with no active operation. Unaccepted partial source snapshot: 220 files under
`out/mujoco-m5a-supervisor-fidelity/partial-snapshot/`; this subsequent
Supervisor decision-record append is intentionally later than that snapshot.
