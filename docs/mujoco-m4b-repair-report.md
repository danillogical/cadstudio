# M4b repair report: six supervisor findings

**Status:** all six findings in `docs/mujoco-m4b-supervisor-review.md` are implemented and
covered by real adversarial regressions; focused and full suites pass. The configured
reviewer was used exactly as configured (no substitute, no override): the first attempt
still resolved the old slow target and returned 429, which was recorded; after the human's
slow-role change to `muse-code/muse-wonder-1.0:medium` a normal configured invocation
completed and reviewed the repair. Its P2/P3 findings were fixed with regressions.

Scope: bounded M4b repair only. No M4c events, Pocky adapter/CAD, threshold tuning, physical
measurements, model/effort/fallback changes or new scheduler. M0–M3 and accepted M4a
behaviour, CAD, dependencies and the JSON fixture-registry boundary are preserved.

## Native plan (before edits)

- `omp -p --model @plan --no-session --tools read,grep,glob --max-time 300 …`
- Exit `0`, wall `265.41 s`, output `8200` bytes.
- Raw: `/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4b-repair-plan-20261021/plan.txt`.

## Fixes

### 1. Tail/suffix completeness cannot report reproduced

- `_replay_steps` now takes a shared `deadline`, replays the remaining rows of a mid-phase
  `start_row`, and returns `expected_rows`, `completed`, `stopped` and `invalid` reasons.
- `_compare_states` requires the exact expected suffix length (`expected_rows`) and fails on
  any shortfall; `replay_run` marks a stopped/invalid tail as not ok, so a post-settle
  continuation that stops after 2 of 401 rows is INCONCLUSIVE with reasons, never
  `reproduced`. A successful full pass can no longer hide a failed tail.

### 2. Strict NPY preallocation validation

- `state_archive._parse_npy_header` / `_validate_npy_members` parse magic, version, bounded
  header text and shape/dtype for every member before `np.load`; payload length must equal
  `header_bytes + product(shape) * itemsize`, dtype kinds are allowlisted (object/structured
  rejected), itemsize and dimensions are bounded, per-row members must match the `time` row
  count, aggregate payload is capped, and the row budget comes from the declared shape, not
  `file_size // 8`.
- A 185-byte ZIP whose `time.npy` header claims shape `(1_000_000_000,)` is rejected with
  zero `np.load` calls and no allocation request.

### 3. One bounded read; same bytes hashed and parsed

- `load_verified_run` reads every artifact once via `bounded_regular_bytes` into an immutable
  `raw_files` map, then parses JSON/XML/assets/NPZ/meta from those same bytes;
  `verify_manifest_relationships(raw_files=…)` hashes the supplied bytes and never reopens;
  `read_state_archive` accepts `Path | bytes` (`read_state_archive_bytes`) and
  `load_state_meta_bytes` parses metadata bytes. `source_hashes` are the verified bytes, and
  the end-of-run check fails if a source file changed. A deterministic regression counts
  reads (`states.npz`/`state_meta.json` exactly once) and shows a post-verification mutation
  fails against the manifest digest instead of being adopted.

### 4. Nonblocking, confined descriptor open

- `evidence._open_confined` walks each path component with `O_NOFOLLOW|O_DIRECTORY` relative
  to the previous descriptor and opens the final file with `O_RDONLY|O_NONBLOCK|O_NOFOLLOW`;
  `fstat` requires a regular file before any read. FIFOs/sockets/devices are rejected without
  blocking (probe 0.038 s), and symlinked components cannot escape the run root. Regression
  uses a bounded subprocess timeout.

### 5. Strict recursive comparison

- `_compare_states` treats one-sided NaN/infinity and opposite-signed infinities as
  mismatches, matches same-signed infinities only, and tolerates finite values.
- `_compare_evaluations` uses `_compare_value` to compare the required schema recursively:
  exact check identity/status/units and set, explicit `None` mismatches, nested metrics
  dictionaries/arrays, and validity `ok`/reasons. Missing or extra checks/metrics fail.
  Regressions cover one-sided `+inf`, nested `peak_effort.push` 1 N vs 2 N and a missing
  check.

### 6. Enforceable budgets and pre-simulation validation

- A shared deadline (`MAX_REPLAY_WALL_S`) is checked before each `mj_step` and before/between
  passes; expiry raises a ReplayError and a partial `replay.json` with `status: ERROR` and the
  reason is retained.
- `load_verified_run` validates exact per-phase counts against the locked rounded plan
  (allowing a truncated final phase only for a recorded stop), phase end times, zero-based
  row/phase mapping, native component vs legacy arrays, and transition-input shapes before
  any stepping; malformed evidence is ERROR.
- Runner state budgets now account for every archived array (integration state, legacy,
  index, transition, name and checkpoint payloads) and are described as an uncompressed
  payload bound, not peak Python/list/stack memory.

## Evidence

Focused (all M4b, M4a/scenario and prior physics):

```text
uv run pytest tests/test_cadkit_physics_m4b_*.py tests/test_cadkit_physics_scenario.py \
  tests/test_cadkit_physics_m4a.py tests/test_cadkit_physics_mechanics.py \
  tests/test_cadkit_physics_scene.py tests/test_cadkit_physics_export_cli.py \
  tests/test_cadkit_physics_optional.py tests/test_cadkit_physics_units.py \
  tests/test_cadkit_physics_gravity_drop.py tests/test_cadkit_physics_hollow.py -q
346 passed in 88.73s
```

Full suite once after final fixes:

```text
PATH=/Users/daniel_l_newman/.local/bin:$PATH uv run pytest tests/ -q
570 passed in 399.91s (6:39), exit 0
```

Raw: `/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4b-repair-20261021/full-suite-final.txt`.

### Before/after supervisor probes

Re-run against the repaired code; raw results in
`/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4b-repair-20261021/probe_results.json`
(refreshed after the reviewer fixes; keys `tail_fault_final`, `wall_budget_final`, `race_final`).

| Probe | Before | After |
|---|---|---|
| tail NaN after a successful full replay | PASS, reproduced true, tail 2/401 rows | INCONCLUSIVE, reproduced false, tail 2/401 with `tail_invalid` reason |
| 185-byte forged-shape NPY (caps 1024 B / 100 rows) | intercepted 8 GB allocation | `ArchiveError` before any `np.load` call or allocation |
| archive changed after verification | PASS, altered digest adopted | ERROR before any result is published (`source evidence 'states.npz' changed during replay`) |
| FIFO evidence file | open blocked (2 s timeout) | rejected in 0.038 s without blocking |
| one-sided `+inf` / nested metric / missing check | reported ok | all report mismatch |
| replay wall budget | checked only after both passes | stops before a step; `replay.json` status ERROR retained (`stage: full`) |

## API changes (explained)

- `read_state_archive(Path | bytes, …, allow_nonfinite=False)` and new
  `read_state_archive_bytes` / `load_state_meta_bytes`.
- `verify_manifest_relationships(..., raw_files=...)` verifies supplied immutable bytes.
- `replay_run` uses an internal shared deadline; `MAX_REPLAY_WALL_S` is still the constant.
- Scenario JSON `fixture` accepts a safe label for typed `run_assembly` callers, but JSON
  execution still goes through the `_FIXTURES` allowlist (`build_fixture` rejects unknown
  labels); no dynamic imports and no registry bypass.
- No schema, threshold, fixture, dependency, CAD or model/role/effort/fallback change.

## Configured reviewer

The configured reviewer agent was invoked without any model/role/effort override. The first
attempt still resolved the old slow target and failed immediately with
`[workbuddy-ai/step-5-preview] 429 UpstreamError`; per `docs/mujoco-reviewer-policy.md` no
substitute was spawned and no configuration was changed. After the human set global slow to
Muse Wonder Medium, a normal configured-role read showed
`slow: muse-code/muse-wonder-1.0:medium`, and a second configured invocation completed
(3m8s) and reviewed the repair. Findings:

| Reviewer finding | Disposition |
|---|---|
| Runner byte accounting omitted separately archived legacy/index arrays | Fixed: payload estimate sums every archived array and is labelled a payload bound (the reviewer saw a stale revision; current code covers them). |
| Post-pass wall check could raise before the retained failure report; `partial` stage stayed `full` | Fixed: wall and source-unchanged checks run inside the failure-report path; `partial` advances to `tail`. |
| PASS `replay.json` could be published before the source-unchanged check | Fixed: the check runs before any result is written. |
| `_validate_npy_members` did not require the expected member set | Fixed: missing required members rejected before `np.load`, model-aware for zero-size components. |
| Legacy arrays could be reshaped to match a native component | Fixed: exact shape equality (only the scalar 1-D case normalised); `transition_mocap_quat` shape-checked. |
| Every phase could be truncated for a stopped run; phase names not bound to the plan | Fixed: names must equal the locked plan order; only the stopping phase may be truncated, earlier phases exact, later phases zero. |

Raw: `review-configured.md` and `review-blocked.md` in this directory.

## Limits

- Hashes still guarantee internal consistency only; a fully coordinated rewrite is not
  detectable by hashes alone (tamper tests rewrite hashes to exercise semantic checks).
- The wall budget stops between native calls; it does not interrupt a single `mj_step`.
- Same-platform replay within pinned tolerances only; cross-platform bit equality is not
  claimed.
- M4c events/synthetic failures, Pocky adapter/S0 (M5a/b) and physical M7 remain later work.
- Supervision: remediation `dec_0mvinjeeldb7056aeb2828420`; before admission 3/12 operations
  and 2/2 remediations used, cumulative 15 operations/6 remediation cycles; this consumed the
  last currently allotted remediation cycle. No self-renewal, no scheduler, no bridge
  decision.
