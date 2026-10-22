# M4b independent review: bounded remediation required

Operation op_0mvilakl5b3aeebf0e141e944, run run_0mvihmvsm9f3be51a0fd22543,
turn3, authorization dec_0mvilaa0a89b2f2d205afc7fc. M4b is NOT accepted.
M0–M3 and M4a remain accepted. No M4c/Pocky CAD/adapter/physical claims.

The implementation performs genuine native-state replay, records useful state
metadata/checkpoints, validates saved-scene bytes and supplies a typed assembly
API. Native configured plan output9503bytes/197.64s is present. OMP independently
reviewed using a separate default-role reviewer after disclosed Step5 reviewer429
and unregistered security reviewer. No unauthorized routing changes are apparent.

Supervisor independently ran77tests (new M4b + accepted M4a), all passing24.42s.
OMP reports557full-suite passes391.91s; the supervisor did not repeat the full
suite because the concrete defects below already block acceptance. Source hash
comparison with accepted M4a snapshot shows changes in CLI, runner, scenario,
scene, telemetry, schema, scenario tests and orchestration docs, plus new M4b
modules/tests/report. No product CAD, dependencies or prior mechanics source changed.
The old scenario allowlist tests were adapted for typed labels; JSON execution
still enforces the fixture registry. Preserve that boundary and explain API changes.

All raw cases/scripts/results below are retained under:
/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4b-supervisor-20261021/.
Injected faults and malformed files are software probes, not physical observations.

## 1. Post-settle continuation can stop early yet replay reports PASS

Actual saved slider:501rows, post-settle checkpoint row100, required tail401rows.
Supervisor wrapped REAL mj_step and injected qacc[0]=NaN on the first tail step,
after the complete full replay had succeeded. The live validity guard correctly
stops the tail after one step. Nevertheless replay reports **PASS/reproduced=true**:
full501rows match, tail only2rows (checkpoint+one step) reports ok=true versus
401required. Raw tail-fault-replay/replay.json and probe_results.json prove this.

_compare_states compares only source[start:start+len(replayed)] and never demands
the full remaining length. replay_run ignores the tail's numerical validity/stop.
Fix BOTH: require exact expected suffix length, terminal time/row and completion;
propagate tail stop/invalidity to INCONCLUSIVE with reasons even if a prefix matches.
No truncated replay may be called reproduced. Preserve full-run metrics/status;
a tail failure must not be hidden by a successful full rerun. Add a real stepping
regression matching this probe, plus direct prefix-length comparison negatives.

## 2. Tiny malformed NPY header bypasses preallocation byte/row budgets

read_state_archive checks ZIP central-directory bytes then calls np.load before
validating NPY dtype/shape. Actual185-byte ZIP contains only a128-byte time.npy
header claiming float64 shape(1_000_000_000,), no payload. With max_bytes1024 and
max_rows100, it reaches numpy.ndarray(count=1_000_000_000), an8GB request, before
rejection. The supervisor INTERCEPTED that allocation and raised BlockedAllocation;
no8GB buffer was allocated. probe_results.json has the intercepted element count.
The row estimate file_size//8 counts the header and does not inspect the shape.

Parse every NPY header through bounded decompression/header reads BEFORE np.load
or ndarray allocation; validate supported non-object dtype, dimensions/products
using overflow-safe arithmetic, exact payload length vs member size, required
member set, model/layout-based shapes and aggregate memory/row caps. Reject huge
zero-itemsize strings, malformed headers, shape products, missing members and
extra dimensions before materialization. Do not rely on compressed ZIP sizes or
checking shape after load. Retain allow_pickle=False. Tests must spy on allocation
or np.load and demonstrate rejection BEFORE the oversized request.

## 3. Multi-read race still accepts bytes that fail the manifest

Verification reads artifacts repeatedly. verify_manifest_relationships hashes
states.npz, then read_state_archive reopens it; source_hashes later re-reads it and
adopts the new digest. Supervisor simulated a change between hash verification
and archive loading by changing body_names in the archive (no manifest update).
Real replay reports **PASS/reproduced=true**, while the manifest archive hash is
762ba6b6ce72c421c457daa0c85de0cd2d94f25e2f5722f147671b20b6280844
and actual archive hash is
6f37405414b5282625ad95d40a518c5d9115f4aeaee7caacd6419da7f2634e77.
The result's source_hashes explicitly accepts the altered digest. Raw race_probe.py,
race_results.json and race-replay/ retain the proof. This is not a coordinated
rewrite of all hashes; the manifest was never changed.

Read each source artifact once into bounded immutable bytes (or a validated
snapshot/descriptor), hash and parse/load those SAME bytes, including metadata,
archives and initial JSON. Avoid check-then-reopen paths. Source_hashes must be
those VERIFIED bytes, never adopted later reads; end-of-run mutation checks
must fail against the original verified digest. Ensure changes between verify
and parse cannot be compiled/allocated/accepted. Add a deterministic race test.

## 4. Regular-file helper blocks forever opening a FIFO

bounded_regular_bytes calls os.open(O_RDONLY) before fstat rejects nonregular
files. A FIFO with no writer blocks there. Actual subprocess probe timed out at2s,
killed safely, without reaching rejection. See probe_results.json/fifo case.
Use nonblocking descriptor opening and regular-file checks before reads. Preserve
path confinement with race-resistant descriptor traversal/no-follow checks for
all path components; reject symlink escapes and special files without blocking.
Test FIFO rejection with a bounded subprocess timeout, not a potentially hung
in-process call. No external network/service or global configuration changes.

## 5. Comparison overlooks nonfinite/nested/missing evidence

Direct _compare_states(source=[[+inf]], replay=[[0]]) returns ok=true because
inf > (atol + rtol*inf) is false. Direct _compare_evaluations with source
peak_effort.push1N and replay2N returns ok=true: nested metrics are never compared.
Check sets are only traversed on the replay side and None-vs-number is skipped.

Implement a strict recursive toleranced comparison of the required evaluation
schema: exact check identity/set/status/unit structure, numeric finite values,
explicit None mismatch handling, nested metrics/arrays and validity stage/time/
reasons. Handle signed infinities and one-sided nonfinite values explicitly;
never classify an invalid value as a numeric match through tolerance arithmetic.
Keep the documented invalid-source behavior honest; do not upgrade it to PASS.
Add adverse tests for all above, plus missing/extra required metrics/checks.

## 6. Resource/completeness claims need enforceable boundaries

Replay wall budget is only checked AFTER both replays. Enforce a shared elapsed
budget before/between steps and checkpoint passes, so exceeding it actually stops
work and retains a useful failure report; no claim that it interrupts a single
native call is required. Validate all array shapes/phase-step-time mappings and
per-transition input alignment before simulation rather than relying on broadcasting
or a later divergence. Check exact per-phase counts against the locked rounded
scenario plan, not merely the total sum and a nonnegative phase index. Fail malformed
evidence as ERROR before stepping. Correct ordinary state-byte accounting to cover
all archived arrays and clearly distinguish payload caps from peak Python/list/stack
memory estimates; do not describe an undercounted selected-array estimate as a hard
memory bound. These are required M4b budgets, not M4c work.

## Bounded repair and stopping conditions

One M4b repair for1–6 only. No M4c events, Pocky adapter/CAD, new threshold tuning,
physical measurements, model/effort/fallback changes or separate scheduler. Obtain
actual native configured plan output before edits, preserve accepted mechanics/
M4a gates, perform independent read-only review (including archive/path boundary;
disclose configured reviewer availability and use default-role reviewer without
reconfiguring), then meaningful focused tests and full suite once after final fixes.
Report docs/mujoco-m4b-repair-report.md with raw commands/probes, no assumed success.

Before remediation decision:successor2 uses3/12operations,1/2remediations,9operations
and1remediation remaining, deadline1792638674806. Cumulative15submitted operations/
5remediations. This repair consumes the last currently allotted remediation cycle;
do not self-renew or hide cumulative counts. A later Codex limit review is separate.
