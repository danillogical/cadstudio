# M4b report: trustworthy generic replay and adapter boundary

**Status:** the bounded M4b packet (`docs/mujoco-m4b-packet.md`) is implemented and
independently reviewed; submitted for Codex review. M4 is not complete: M4c
(presentation events and the complete synthetic-failure suite) remains. No Pocky
adapter, product CAD, S0 or M5 work was done. M0–M3 and the accepted M4a runner are
preserved.

## Native plan (required before production edits)

- Command: `omp -p --model @plan --no-session --tools read,grep,glob --max-time 300
  --cwd /Users/daniel_l_newman/src/cadstudio "<M4b planning prompt>"`
- Exit `0`, wall time `197.64 s`, output `9503` bytes.
- Raw: `/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4b-plan-20261021/plan.txt`
  (stderr empty).

The plan's 12 steps covered a native state-archive module, telemetry refactor, a typed
`run_assembly` API, scene identity exposure, untrusted-evidence helpers, replay
verification/replay, CLI support, and focused/adversarial tests. Implementation followed it;
notable deviations are recorded below.

## Implemented

### Complete native integration-state archive

- `cadkit/physics/state_archive.py` derives the mask and layout from the installed runtime:
  `mjSTATE_INTEGRATION` (mask `16383`, size `30` for the slider; `mj_stateSize` per bit),
  with per-component offset/size/present recorded for TIME, QPOS, QVEL, ACT, WARMSTART,
  CTRL, QFRC_APPLIED, XFRC_APPLIED, EQ_ACTIVE, MOCAP_POS, MOCAP_QUAT, USERDATA, PLUGIN.
  Zero-size components are recorded as present with size 0, and component sizes must sum to
  the mask size.
- Rows are `mj_getState` values: `state[0]` is the post-reset state (no step), `state[k]`
  is the state after exactly `k` `mj_step` calls. Recorded transition inputs
  (`transition_ctrl`, `transition_qfrc_applied`, `transition_xfrc_applied`, mocap) are the
  inputs applied before step `k` producing row `k`. `phase_index` is zero-based into
  `phase_names` (reset = 0); `phase_code = phase_index + 1`. Row semantics are written to
  `state_meta.json`.
- `checkpoints.npz` stores the full native state and row index for the initial, post-settle
  and terminal checkpoints; `state_meta.json` records their hashes. Ordinary runs write
  `states.npz`, `state_meta.json`, `checkpoints.npz`, and the manifest hashes them.

### Deterministic replay

- `cadkit/physics/replay.py` verifies the source run, recompiles the **saved** `scene.xml`
  and assets in memory (`MjModel.from_xml_string` with a verified asset map, no filesystem
  reopen), restores the saved native state with `mj_setState`, applies the recorded
  transition inputs, calls real `mj_step`, and compares every resulting native state row
  with the source under pinned tolerances (`REPLAY_TOLERANCES`, state `atol/rtol 1e-9`).
- It also restores the post-settle checkpoint and replays the tail, recomputes the
  acceptance evaluation (checks, metrics, verdict, validity reasons) with the recorded
  effort/contact/compliance budgets, and writes `replay.json`, `replayed_states.npz` and
  `replay_report.md` to a fresh output directory. The source run is never written; source
  hashes are re-checked after replay.
- `cad physics replay <run-dir> --out <fresh-dir>` exposes this in the existing CLI. Replay
  mirrors the source verdict when reproduced, INCONCLUSIVE on divergence, and ERROR/3 for
  invalid or tampered evidence.

### Integrity, runtime and untrusted input

- Raw and semantic hashes of `scenario.json` and `acceptance.lock.json` are verified, as are
  the manifest artifact hashes, the recomputed semantic scene hash (from the saved XML bytes
  and verified asset hashes, not from the report's copy of itself), the run identity hash,
  and the manifest/summary solver facts and runtime identity (MuJoCo/Python/NumPy/platform,
  timestep, integrator, cone, solver, iterations, tolerances, gravity, wind, density,
  viscosity, margin, enable/disable flags, state mask/size).
- The saved scene is parsed as XML: DTD/entities, `<include>`, `<plugin>`, compiler directory
  attributes and unsafe `file` values are rejected; every `file` attribute is read from the
  parsed tree (single quotes and character references included) and must be a safe
  `assets/*.stl` key in the verified map, so MuJoCo cannot fall back to the filesystem.
- Evidence files are read through bounded, regular-file, non-symlink helpers; the archive is
  inspected from the ZIP central directory before decompression (allowlisted/unique members,
  no directories/encryption/traversal, declared-uncompressed byte cap, declared row count
  before `np.load`), loaded with `allow_pickle=False`, and checked for object/unsupported
  dtypes and non-finite values (non-finite rows are accepted only for a non-PASS source with
  a recorded stop). Scenario/acceptance are parsed from the same bytes that are hashed.

### State budgets and typed API

- Scenario budgets gained optional `max_state_rows`/`max_state_bytes`; the row budget is
  enforced in ordinary preflight and the byte budget after compile but before any state array
  is created; the recorder also stops on a runtime budget breach.
- `run_assembly(spec, scenario, acceptance, out, ...)` is a public typed entry point that
  validates an `AssemblySpec` and reuses the same runner/evidence/evaluation path with no
  dynamic import and no fixture-registry edit. JSON scenarios still select only allowlisted
  registry fixtures.

## Independent review

The configured `reviewer` role returned 429 and `security-reviewer` is unregistered; neither
was reconfigured. A separate default-role OMP agent performed the independent read-only
review (`/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4b-20261021/review-m4b.md`)
and found: truncated archives replaying PASS (H1), a scene hash recomputed from the report
rather than the bytes (H2), a bypassable single-quoted/char-ref asset path plus MuJoCo
filesystem fallback (H3), multi-read TOCTOU (M1), hand-copied scratch state (M2), uncaught
malformed-evidence exceptions mapping to exit 1 (M3), one-sided NaN treated as a match (M4),
unbounded metadata/manifest completeness gaps (M5), omitted replay effort/contact/compliance
reproduction (M6), partial runtime identity checks (M7), unverified row/phase/control mapping
(M8) and a post-allocation row budget (M9). All were fixed with regressions; the follow-up
focused suites pass and tamper now yields ERROR.

## Verification and raw evidence

```text
uv run pytest tests/test_cadkit_physics_m4b_replay.py tests/test_cadkit_physics_m4b_adversarial.py tests/test_cadkit_physics_m4b_typed.py -q
31 passed

uv run pytest tests/test_cadkit_physics_scenario.py tests/test_cadkit_physics_m4a.py \
  tests/test_cadkit_physics_mechanics.py tests/test_cadkit_physics_scene.py \
  tests/test_cadkit_physics_export_cli.py tests/test_cadkit_physics_optional.py \
  tests/test_cadkit_physics_units.py tests/test_cadkit_physics_gravity_drop.py \
  tests/test_cadkit_physics_hollow.py -q
302 passed in 81.10s

PATH=/Users/daniel_l_newman/.local/bin:$PATH uv run pytest tests/ -q
557 passed in 391.91s (6:31), exit 0
```

Raw: `/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4b-20261021/full-suite-final.txt`.

### Real CLI saves and replays

Diagnostics: `/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4b-20261021/`
(`evidence_summary.json`, per-case `.stdout`/`.stderr`/`.exit`, `run-*`, `replay-*`).

| Case | Save | Replay | Result |
|---|---:|---:|---|
| loaded spring slider | 0/PASS | 0/PASS | reproduced, 501 rows, max abs state diff `0.0`, post-settle tail ok, source hashes unchanged |
| negative gear, `1e6 N` request clipped to `2 N` | 0/PASS | 0/PASS | reproduced, 301 rows, diff `0.0` |
| free fall, Euler | 0/PASS | 0/PASS | reproduced, 51 rows, diff `0.0` |
| free fall, RK4 | 0/PASS | 0/PASS | reproduced, 51 rows, diff `0.0` |
| tampered `scene.xml` | — | 3/ERROR | `artifact 'scene.xml' sha256 does not match the manifest` |

Adversarial focused tests additionally cover: truncated archive (ERROR), scene comment/inert
tamper with updated hashes (ERROR), single-quoted external asset (ERROR), ERROR-source replay
(ERROR), missing archive member (ERROR), one-sided NaN mismatch, forged summary solver
identity (ERROR), unmanifested state metadata (ERROR), object/duplicate/traversal/oversized
ZIP members, non-finite PASS archive, checkpoint tamper, path traversal and symlink evidence,
state row/byte budget rejection before arrays exist, and replay-output containment.

## Hash guarantee and limits

- Hashes guarantee **internal consistency** of a run directory: a coordinated rewrite of the
  files *and* the manifest/summary hashes cannot be detected by hashes alone. Tamper tests
  therefore also rewrite hashes to exercise the semantic/completeness checks. Authenticity
  against a fully coordinated rewrite is not claimed.
- Same-platform replay within pinned tolerances is claimed; bit equality across platforms is
  not. Replay wall time is checked after the run; rows are bounded before stepping.
- Contact-force telemetry remains forward-evaluated at the recorded state (provenance is
  explicit); intermediate integrator-stage impulses are not claimed. Scratch observation now
  uses the complete native state transfer.
- M4c still owns named presentation events (identity, direction, windows, anti-double-count,
  supported dwell), the complete synthetic-failure suite and frozen provisional thresholds.
  M5a/M5b own the real Pocky adapter/S0/P0–P9; M7 physical data remain UNVERIFIED. No
  physical-trial claim is made.
- No global role/model/effort/fallback configuration was changed; the human-authorized
  OpenCode Go DeepSeek routing is unchanged.
