# Independent renewal 6: resume after human routing change

The human changed the global OMP provider from `opencode-go` to `workbuddy-ai`
and then directed `Resume` in chat `01a1624d-8caf-7102-991f-d6ca998446b4`.
This renews only the existing approved M5a-1 objective (plan section 6.1).

## Independent reconciliation

Successor5 `run_0mvj62atk8b61da9fe2edf2ea` remains escalated, pending
authorization false. Its last operation `op_0mvjdr70n550c446dbb4c5913` is
terminal; exactly one decision, `REQUEST_HUMAN dec_0mvjgn8lk8c1c60f8bdc6e720`,
was saved. Native result transitions confirm completion of execution, not
acceptance. The configured reviewer rejected the partial repair and the primary
then encountered quota errors. Do not reopen this run or reuse consumed
`dec_0mvjdq99k6ffb0bc8c7fe5fa6`.

Prior operations in that run: `op_0mvj62z0p3dcdad31cbfa078c` followed by
REMEDIATE `dec_0mvj93wc4ee431c23c04f7fb2`;
`op_0mvj94k0p6eaf0732bc596115` followed by CONTINUE
`dec_0mvjaa93m7c7fe330fbbb475a` (accepted generic checks only);
`op_0mvjabe8s901d98bf04f78aa6` followed by the dense-void REMEDIATE above.
Neither adapter/static nor S0 has been accepted.

Fresh source reconciliation at main revision
`c76a1dff1c33f5e4176182b94d59c9c574b4aec3` compared all 220 files in
`out/mujoco-m5a-supervisor-fidelity/partial-snapshot/manifest.json`: none
missing; only the supervisor review changed, by its already recorded decision
append. No implementation, tests, CAD or dependencies changed since independent
119-test regression (231.05 seconds). Raw comparison is
`out/mujoco-m5a-supervisor-resume6/reconciliation.json`. Frozen acceptance hash
remains `518a45ffc4592ca602be4c33c59681038e43dedaa15b688312202c3a57ff6ca2`.
The previous passing tests do not negate the actual CAD/blocker and interior-hole
counterexamples in `docs/mujoco-m5a-1-fidelity-repair-supervisor-review.md`.

Verified global config change is exactly the nine authorized provider-prefix
replacements, with efforts, other roles and fallback policy preserved. Before
SHA256 `1b871a81d88dc47ada978672ae99c35b0548e3ebbc4ba83b8b5c779157bbd98b`;
after `d6c4f26edd9fea9b2d054b5ac267f9b7910f9b92f91ee99c010f071a400e782d`.
Backup: `/Users/daniel_l_newman/.omp/agent/config.yml.pre-workbuddy-20261022T162400393774Z`.
The initial graceful-stop approval was rejected over possible active work;
fresh read-only status/doctor established idle state and the same supported
graceful-stop retry succeeded without force. Supported start with resume=false
created fresh session `01a16470-5d51-7624-b605-8c8d77b4e4cc`, generation 1,
PID 10005. Fresh status/doctor confirm ready, no active operation, no last error,
and actual host provider `workbuddy-ai/deepseek-v4.1-flash`. This proves host
routing, not successful inference or required review. Those remain execution
gates. No unrelated workspace was restarted.

Exact chat binding was reaffirmed through the bridge, bounded autonomy, with
global wakeups enabled. There is no separate work-queue API: fresh resume=false
host, ready/no active operation, and submission with allow_queue=false enforce
the empty-work boundary. Doctor's queued wakeup notices are not work items.

## Revised limits and corrective advisement

Old limits: 6 operations / 2 remediations / 480 minutes; actual usage 4 / 2;
historical remaining 2 / 0; deadline 1792679704903 has expired. Cumulative usage
across all linked runs is **26 submitted operations / 11 remediation cycles**.
Imported external work has unknown usage and is not invented as bridge usage.

Open linked successor6 with **4 operations / 2 remediation cycles / 360 minutes**.
This is a smaller operation cap; renewed corrections and time cover one concrete
project-only fidelity repair, independent acceptance, and separately admitted S0
evidence/full regression if acceptance permits. There is no human hard budget
or stop being overridden. The human resolved the provider choice and requested
resumption. Fresh counters never erase previous attempts.

A credible bounded correction is available: the exact channel and bore-hole
counterexamples identify the missing volumetric guarantees, while original
bore/exit negatives now reject and all physical colliders/export remain unchanged.
Next ONE operation is `docs/mujoco-m5a-1-fidelity-followup-packet.md`: genuinely
3D channel coverage derived from CAD/swept rod; independent volumetric coverage
tests that fail interior-hole mutations; own-welded-group void semantics distinct
from initial other-body occupancy; final reports/manifests refreshed after edits;
separate test worker and configured ordinary review. Do not repeat the failed
axis-marginal coverage approach. No S0 batch in this first operation.

Stop on required-role unavailability, unknown host/operation state, exhausted
limits, scope violation, or no credible correction. Preserve partial evidence;
no manual model/role/provider/effort/fallback changes or substitutions. No source
CAD/params/frozen criteria/dependency changes, generic production edits, P0–P3,
M6/M7, commit/push or deployment. Full CAD suite remains due after final shared
M5a-1 changes. Physical M7 inputs remain unverified. The supervisor will review
the result independently and record exactly one decision before any next turn.

Native supervision admission created successor6
`run_0mvjre53o25d566338987a193`, open, exact current chat authorized, bounded
autonomy, 4 operations / 2 remediations, deadline `1792708329299`.
Before first submit: 0 / 0 used; cumulative 26 / 11. First request ID is
`cadstudio-m5a1-fidelity-followup-01a1624d-1`. Submission is non-queueing;
its operation ID is retained by the bridge and reconciled at completion.
