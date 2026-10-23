# Fidelity followup: partial progress, required execution/review gate blocked

Operation `op_0mvjrenqx457b3b57d5f987d4`, first turn of successor6
`run_0mvjre53o25d566338987a193`, generation 1, is bridge-terminal completed.
It is **not accepted**. Native primary and independent test-worker transcripts
end in provider errors; no ordinary configured reviewer was dispatched and no
approval exists. No S0 batch or product acceptance follows from this event.

## Independently reconciled source and execution

Main remains `c76a1dff1c33f5e4176182b94d59c9c574b4aec3`. Compared every
file against the 220-file unaccepted partial snapshot. No file is missing.
Actual implementation changes are only `projects/pocky/physics/colliders.py`
and `tests/test_pocky_physics_void_coverage.py`, plus a partial supersession
notice in the old repair report. The old supervisor-review difference is its
already recorded decision append from before this operation. The renewal6
and followup-packet documents were Supervisor-authored before dispatch.
Accepted generic code/tests, CAD, parameters and dependencies remain preserved.
Frozen acceptance SHA256 remains
`518a45ffc4592ca602be4c33c59681038e43dedaa15b688312202c3a57ff6ca2`.
Global config SHA256 remains
`d6c4f26edd9fea9b2d054b5ac267f9b7910f9b92f91ee99c010f071a400e782d`;
no routing/model/effort/role/fallback change or manual substitute occurred.

Inspected native primary transcript: 134 assistant messages, all attributed to
`workbuddy-ai/deepseek-v4.1-flash`. Separate `PockyFidelityTests` transcript:
144 assistant messages, all the same configured implementation provider/model.
The test worker authored volumetric tests and mutation checks and has a raw
44-pass test log, but its native task ends failed, without a completed handoff.
No reviewer transcript exists in this session's task directory; the primary
dispatched only the test worker. Saved native paths, hashes, errors and tool
counts are at `out/mujoco-m5a-supervisor-followup/native-execution.json`.
This is observed execution, not inference from configuration alone.

The primary encountered HTTP 400 `request illegal`, then HTTP 429. The test
worker also ended on HTTP 429. Both actual final errors say usage exceeds the
WorkBuddy frequency limit and report reset at **2026-10-24 00:25:44 UTC+8**,
equivalent to **2026-10-23 16:25:44 UTC / October 23, 9:25:44 AM PDT**.
That is provider-reported availability, not a guaranteed recovery or scheduled
retry. It lies beyond the current supervision deadline. Raw HTTP request files
were not opened; only native error metadata was inspected. No repeated quota
retry, substitute role or model override is justified by this completion notice.

## Partial repair and remaining review work

The channel now has a three-dimensional `rod_corridor_grid` derived from rod
and button-peg CAD sections across the stroke. Other-body initial occupancy is
kept and classified instead of silently deleting own-group void points. New
tests sample volumes and exercise the interior-hole mutation. These changes
are preserved as unaccepted partial work.

Implementation/review issues still require the configured review and final
reconciliation. In particular, claims that midpoint sections produce an
**exact** swept solid need geometric justification for curved cross-sections;
vertices and face bounding-box stations alone do not establish constancy of
every section between stations. The `VoidOccupancy` class docstring still says
other-occupied points are not counted as own-void coverage, contradicting the
implementation, `_void_grid` documentation and tests that keep them as a subset.
Some slot notes still say the independently owned peg is excluded. Correct
these claims without weakening coverage or altering the physical mechanism.

The 222-file OMP after-manifest predates final edits: fresh hash checks find
three stale entries (colliders, void-coverage tests, old repair report).
`docs/mujoco-m5a-1-fidelity-followup-report.md` does not exist even though the
partial supersession notice links to it. The false historical 'stricter, not
weaker' limitation remains below that notice. Reports cannot yet claim all four
findings corrected. The required final report and after-manifest must be written
after final edits and actual configured ordinary review. Preserve historical
unaccepted verdicts and raw outputs.

Export scene identity in report remains
`2c4bd425c55d9f56c39904e6ae01683836650fc84dabaa6ff645eb1077926e2f`.
Independently compared raw XML bytes: original adapter/static, prior repair,
followup export and followup compiled XML are identical, raw file SHA256
`997a20b79566bfc5452e334b98f149c292056312795ce85f763308d430a22a15`.
The scene identity and raw XML checksum are distinct values. OMP records
SCENE_VALID, all-five resets/clearance and both reset negatives; these records
do not replace configured review, S0 admission or physical measurement.

Independently reran actual CAD booleans and contract evaluation in
`out/mujoco-m5a-supervisor-followup/probe_corrections.py`, exit 0. Both original
bore/exit negatives still reject. Both channel cubes (-82 and -88, y=-28,
z=-10.9) have zero overlap with every installed fraction-0 solid and now reject
on `rod_corridor_grid`; the first still intersects the moving rod by 41.2695
mm3 at f=.5 and 82.8 mm3 at f=1. The body-void/lip-occupied cube also rejects,
with zero own-group overlap and 60.7771 mm3 other-body overlap.

The current volumetric bore audit passes the real grid and fails after removal
of the exact 12 interior points: the worst sample is 7.12665 mm from a remaining
probe, exceeding the independently justified 4.33013 mm covering radius. The
6 mm cube at (0,0,40) rejects with the real grid but passes the mutated contract,
confirming that the audit catches the previous concrete defect. Raw results:
`out/mujoco-m5a-supervisor-followup/correction-probes.json`. These checks verify
the specific correction; they do not waive unfinished review/report gates.

Independently ran, with ~/.local/bin on PATH:
`uv run --frozen --extra physics pytest tests/test_pocky_physics_assembly.py tests/test_pocky_physics_colliders.py tests/test_pocky_physics_void_coverage.py tests/test_cadkit_physics_export_cli.py -q`.
**136 passed in 459.17 seconds**, exit 0. The initial sandbox attempt could not
read uv's cache; the identical command succeeded with supported escalation.
Log: `out/mujoco-m5a-supervisor-followup/focused-regressions.log`.
No full CAD suite was rerun at this unfinished intermediate checkpoint.

## Limits and resume boundary

Successor6 used **1 operation / 0 remediation cycles** of 4 / 2; remaining
3 / 2, deadline `1792708329299`. Cumulative usage is **27 submitted operations /
11 remediation cycles** across linked runs. No limits are renewed here and no
consumed authorization is reused. Ready host PID 10005 has no active operation.

Preserve partial source, actual tests, native errors and review evidence. A
required implementation role is unavailable and the ordinary review gate was
never reached. The invoked skill says: "If a required role is unavailable,
preserve work, report the blocked gate, and wait for the human to handle the
model change." Human ownership covers provider/model/role/effort/fallback
choices. After human routing resolution or provider recovery, freshly reconcile
host/queue/binding/source, then finish the same bounded review/report repair
through supported supervision admission. Never silently reopen a closed run.
No S0, CAD redesign, generic production edits, criterion tuning, dependency
changes, P0–P3, M6/M7, commit/push or deployment is authorized by this event.
Full CAD suite remains due once shared M5a-1 changes are final. Previous .7909 mm
smoke penetration still does not satisfy the .2 mm S0 validity bound; numerical
INCONCLUSIVE must not become physical FAIL or product PASS.

Exactly one review decision saved: `REQUEST_HUMAN
dec_0mvjxg328a401cea0b673a1f4`, idempotency key
`cadstudio-m5a1-followup-workbuddy-provider-block`. Bridge confirms successor6
**escalated**, no authorization for another operation. No retry or new dispatch
occurred. A 223-file unaccepted source snapshot is saved under
`out/mujoco-m5a-supervisor-followup/partial-snapshot/`; this subsequent decision
record append is intentionally later than that snapshot. All independent
commands finished before this decision; no test process was left running.
