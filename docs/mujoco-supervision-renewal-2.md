# Supervision renewal2 after human-authorized provider switch

Human instruction2026-10-21: "switch workbuddy-ai/deepseek to opencode-go/deepseek
globally". This explicitly authorizes the provider-target replacement; the prior
temporary Step5 proposal is superseded and was never applied. This is not a temporary
switch: do not restore WorkBuddy at task completion absent a further human instruction.

## Reconciled state and actual usage

Original run `run_0mvhxwg5l2aa1ba8e92d0c92f` used3operations/0remediations, closed for
renewal by `dec_0mvi5dou2cf94b458663c3c0c`. Linked successor1
`run_0mvi5dou92f2f6dc40f0d6379` used9/21operations and4/6remediations, deadline
1792618090496, now escalated by REQUEST_HUMAN `dec_0mviggxh4797d258717c7e2b7` for
operation `op_0mvigcfsz9b96a73edd7684e7` (immediate WorkBuddy429, no implementation).
Cumulative usage is **12submitted bridge operations/4remediations**, not zero.
Provider reachability probes are separately recorded, not implementation operations.

M0/M1/M2a/M2b/M3generic are independently accepted. Final M3 snapshot:
`/Users/daniel_l_newman/.omp-bridge/backups/cadstudio-mujoco-m3-final-20261021T183412Z/`.
Independent455testpass remains the last code verification. Current manifest comparison
finds **no CAD/source/test changes** from that accepted snapshot. M4a report absent;
M4–M7 remain unimplemented/unverified. No acceptance of the provider-failed attempt.

## Authorized correction and independent live evidence

Replaced exactly9global modelRoles targets, from workbuddy-ai/deepseek-v4.1-flash to
opencode-go/deepseek-v4.1-flash. Preserved all role efforts (high/low/max), slow role
workbuddy-ai/step-5-preview:high, advisor enablement, fallback disabled/empty chains,
and every other configuration byte. Private full-config backup:
`/Users/daniel_l_newman/.omp/agent/config.yml.pre-opencode-deepseek-20261021T190856Z`.
Never print its contents or credentials. Native `omp config get modelRoles --json`
confirms the mappings. Tool-free native @default/@plan/@smol probes all exited0 and
their assistant records show provideropencode-go/modeldeepseek-v4.1-flash. These are
reachability tests, not M4's required substantive planning output.
Evidence: `/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-opencode-switch-20261021/`.

Created durable handoff `ho_0mvihky4i36017cb36bcc3a1c`, stopped only the idle cadstudio
host via supported tools, and restarted it. New hostPID62419 actually selects
opencode-go/deepseek-v4.1-flash. Worlds was not restarted or interrupted. Applied handoff
through supported context rotation, new_context_empty=true, current session
`01a15fdf-0c0b-7779-8ca9-8b0897bdc18b`, generation2 on this new host. Global settings
apply to other OMP sessions when they load their role targets; this is not a claim that
an unrelated already-running host's selected main model was switched in place.

## Renewal limits, next scope and stopping conditions

Open a linked successor2 for the SAME human-authorized plan-mujoco.md through M7.
The escalated old run is not reopened or given a second verdict. New limits:
**12operations/2remediations/480minutes from creation**. Counts preserve successor1's
remaining operation/remediation allowance; only the self-imposed deadline is renewed
to allow remaining milestones under the now-working authorized route. No human hard
budget or stop is overridden. This is not an attempt to repeat the same blocked route:
the human changed provider and three native live probes now succeed.

Next packet is the unchanged bounded `docs/mujoco-m4a-packet.md`, typed generic phase
runner/evaluation/evidence/CLI, before separate M4b replay/event review, then real Pocky
adapter/S0 M5a and remaining milestones. Usable actual configured native plan output
must precede edits. Preserve accepted mechanics, frozen criteria, product rigid packet
165x55x5.2mm, partly protruding supported pickup objective, and physical evidence gates.

No duplicate packets, new scheduler or invented trial evidence. If this new provider
also rejects requests, independently reconcile before another retry; no automatic new
provider/effort/fallback changes beyond the exact human instruction. Physical M7 may
remain unverified without real measurements, while independent software work continues.

Applied successor2: `run_0mvihmvsm9f3be51a0fd22543`, created1792609874806,
deadline1792638674806, max12operations/2remediations. Open with0submitted operations
before first admission; first operation requires no consumed next-turn authorization.
Exact chat binding reverified; same current host/session route. The escalated old run
remains closed to dispatch and its recorded decision is not duplicated.
