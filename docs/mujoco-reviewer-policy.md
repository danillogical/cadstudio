# Reviewer policy clarification — 2026-10-21

Human clarification in the supervising chat: no fallbacks. This applies to manual
substitution of a default-role review agent as well as automatic retry chains.
This supersedes earlier packet permission to use a default-role substitute when
the configured reviewer returns429. Historical reports are retained as evidence;
they do not authorize repeating that substitution.

At the initial clarification, reviewer bundled agent selected @slow, then
workbuddy-ai/step-5-preview:high. The human's WorkBuddyDeepSeek -> OpenCodeGoDeepSeek
instruction changed only DeepSeek role targets; it did not change the Step5 slow
role. retry.modelFallback=false and retry.fallbackChains={} remain set. No reviewer
model/effort/override change is authorized by this clarification alone.

Current operation op_0mvinjpd9419e484e2900857b may continue its bounded M4b repair and
tests. Use only the configured reviewer for the independent OMP review. If unavailable,
preserve partial work, report review blocked with exact evidence and stop that review
step; never spawn a substitute model/role or call a default-role review equivalent.
Native plan/default implementation roles remain as configured and are not fallback
reviewers. Do not accept the packet as fully reviewed if required review is missing.
Codex will reconcile on completion and determine the next authorized step.

## Subsequent explicit human change and skill update

The human explicitly set global slow to Muse Wonder Medium. Applied exactly that
one setting: muse-code/muse-wonder-1.0:medium. All other config bytes unchanged,
including fallbackfalse/emptychains; fresh native @slow no-tools probe exited0
and used actual muse-code/muse-wonder-1.0. This is a direct human choice, not an
orchestrator-selected substitute. No live reviewer completion is claimed by that
probe. Reviewer continues to select the configured @slow role.

The human then requested the orchestration skill make model changes human-owned.
Updated shared SKILL.md and both Codex-plan/OMP-turn references: neither orchestrator
may choose/change/override/restore routing, effort, fallback, or use manual model/
role substitution. Packets cannot delegate model changes. Unavailable required roles
block their gates for human handling. Current operation must follow this updated
skill; prior default-role substitute permissions remain withdrawn.

## Human removes the security-reviewer gate

Human explicitly instructed: "remove the security-reviewer gate I don't use a
security-reviewer". This supersedes the earlier separate-role requirement and
blocked-gate advice for this role. The orchestration SKILL.md and OMP turn reference
now require only configured ordinary code review; no separate security-reviewer
request or gate. Relevant security/correctness issues stay in the normal review
scope. No OMP configuration or model setting changed. Human-owned routing and
no model/role substitution remain in force. Prior historical blocked records are
preserved, not rewritten as though a security-role review occurred.

## Subsequent human global configuration update

Human reports they updated OMP global config. Native omp config get modelRoles
now returns slow=anthropic/claude-opus-5-5:medium. Other role mappings remain
OpenCode Go DeepSeek at their prior efforts. retry.modelFallback=false and
retry.fallbackChains={} remain; security-reviewer is still disabled and has no
gate. This supersedes Muse as the current global slow target. Codex did not edit
configuration or choose this model. Observe the human's configured role for future
invocations; never force task/CLI/env model overrides to bypass cached settings.
Already-running subagents may retain their launch settings; report actual usage
and any reload issue honestly. Do not interrupt work via host restart automatically.
