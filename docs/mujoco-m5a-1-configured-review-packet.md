# M5a-1: ONE configured-review completion, read-only source

Read `docs/mujoco-m5a-1-s0-required-review-renewal.md` for independently verified
fixes, R3, limits and exact admission IDs. You are the OMP Turn Orchestrator
completing one missing review gate. Use the invoked orchestrator skill for your
actual role and preserve all existing accepted/partial source and evidence.

**Dispatch the native configured reviewer role explicitly.** In the native
`task` call, select `agent: "reviewer"` for this review. Omitting `agent` selects
the default task worker; naming such a worker 'reviewer' does not change its role.
This is normal invocation of the existing configured role, not permission to
choose/override its model, provider, effort, mappings or fallback. If unavailable,
stop and report it. No manual substitute or separate security-reviewer gate.

Give the reviewer read-only scope over:

- `tests/test_pocky_physics_s0_independent.py` against its pre-repair snapshot,
  and `tests/test_pocky_physics_s0_portability.py`;
- both S0 reports, R1/R2 and corrected claims about optional absence, strict
  corruption handling, and the two-timestep observation;
- current and original manifests, real source/data hashes, raw environment
  controls and the Supervisor's independent verification artifacts.

Independent current results are already recorded: **164 real-evidence checks
pass**, absent-evidence pair **36 pass / 102 explicitly skip**; final native full
suite **1064 pass**. All 348 original evidence hashes and 28 frozen entries
match. Reuse these facts. Reviewer may run necessary targeted checks, but no
new full suite, physics run/replay, test rewrite or solver investigation is
needed. Existing independent worker validation satisfies the separate test-worker
assignment; do not launch another general task worker as a reviewer substitute.

Require a native final APPROVE or REQUEST CHANGES and specific evidence. If
blocking source defects are found, return them without implementing a new fix
or starting another operation. If approved, update only review-attribution
documentation and final source/evidence index. Correct historical claims that
`S0PortabilityReview` was configured review: it was a default-role independent
worker; record the actual new reviewer role, transcript reference/hash, actual
model attribution and final verdict. Do not fabricate native evidence.

Keep original S0 run/freeze/checkpoint/replay bytes unchanged. The recorded
temporary hard-link incident restored content; do not claim literal read-only
history. Record authoritative current manifest counts rather than stale prose.
The portability manifest's `operation` field wrongly names the predecessor S0
operation; correct review/index metadata in a NEW final review-completion artifact,
with exact native operation/run IDs from this admission. Preserve historical
manifests; do not edit production, tests, scenarios, acceptance, options, CAD,
params, dependency or global configuration files.

Create review-completion evidence under
`out/mujoco-m5a/s0-review-completion/`, and write a concise result report there.
Any final source/report inventory is generated AFTER metadata edits. Do not
claim the dynamic validity breach resolved: all eight cases remain INVALID /
INCONCLUSIVE; no physical retention verdict follows. No tuning, P0–P3,
loaded/25/shared-state, M6/M7, commit/push/deploy. End this ONE operation for
independent Codex acceptance. No self-admission, new limit or followup.
