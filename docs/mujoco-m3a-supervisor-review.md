# M3a independent supervisor review

Operation `op_0mvi8iy8tf593583e58167495`, generation3, run
`run_0mvi5dou92f2f6dc40f0d6379`, admitted by RETRY
`dec_0mvi8f48s09a0e9a7ce70e493`. Reviewed by Codex Plan Orchestrator.

## Verified exporter changes

Compared source directly against the preserved partial-M3 tar/manifest. OMP changed
only `scene.py`, `schema.py`, the new mechanics tests, and its M3a report. Existing CAD,
CLI, dependency and global provider/model configuration were preserved. Orchestration
notes and the UTF-8 test correction below are supervisor changes.

True MJCF nesting now follows declared parents even when input lists children first.
Exact build123d relative transforms are emitted as unit quaternions. All emitted body
and collider orientations use quaternions; compiler angle is radian, matching joint
limits and spring references. Both motor control and force bounds account for absolute
gear, with max_effort defined as generalized joint effort after transmission.

Independent focused run: `PATH=/Users/daniel_l_newman/.local/bin:$PATH uv run pytest
tests/test_cadkit_physics_mechanics.py tests/test_cadkit_physics_scene.py
tests/test_cadkit_physics_hollow.py -q` -> **120 passed in12.94s**.

Additional supervisor-authored real compiled diagnostic:
`/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m3a-supervisor-20261021/check.py`
and `result.json`. It constructs different assembly-space solids with body-local
colliders and offset COMs, lists a four-body tree in reverse order, and uses arbitrary
axis (1,2,-3), two hinges, a slider and three nonzero/zero coordinate configurations.
Expected poses are computed by successive WORLD-axis/pivot Rodrigues transforms of
descendants, independently of the emitter's parent-relative algebra. Maximum pose,
rotation, COM and collider-center error was4.440892098500626e-16. An actual hinge
motor with gear-2.5 transmits at most0.003Nm under positive/negative million-unit
requests. This complements OMP's compiled slider force/gear tests.

Validation at explicit AssemblySpec.validate/export boundary is coherent; production
export tests reject missing parents and cycles before creating directories. The new
spring-sign test correction follows -k(q-ref), without changing correct spring code.

## Test-order failure and supervisor correction

Reproduced the reported failure independently: CAD export followed by
`test_no_qpos_is_written_after_release` yielded1failed/1passed with ASCII decoding
of UTF-8 Python source. The test used locale-dependent read_text(). Changed ONLY that
read to encoding="utf-8"; both no-position-puppetry assertions remain unchanged.
The identical adverse test order then yielded2passed in0.25s. This corrects the
test's source-decoding precondition rather than changing physical behavior or criteria.
Full-suite result after this correction: `PATH=/Users/daniel_l_newman/.local/bin:$PATH
uv run pytest tests/ -q` -> **405 passed in359.16s (5:59)**, exit0. This independently
resolves the blocking regression result, without changing physics assertions.

Preserved exporter/source snapshot before final review documentation:
`/Users/daniel_l_newman/.omp-bridge/backups/cadstudio-mujoco-m3a-20261021T155742Z/`
(128 source/doc files, manifest and source.tar.gz). Later changes are review documents.

## Limits and next increment

M3a exporter fixes are independently accepted with the passing full regression. M3 as a
whole is still incomplete. Existing mechanics smoke PASS is not M3 acceptance.
SLIDER_KG remains unused; existing 10%/2mm fixture checks and missing loaded-stop,
negative and convergence evidence remain M3b work. Actual default soft-stop excursion
reported by OMP demonstrates why range metadata alone is not a mechanical stop test.

Correction to the earlier supervisor review: public mechanics CLI is present in the
preserved partial source; earlier assertion that it was absent was inaccurate.

Next authorized increment, after a recorded CONTINUE, is generic M3b mechanics
fixtures/validity/telemetry only, under `docs/mujoco-m3b-packet.md`. S0 real product
stability remains M5a; no product adapter or CAD geometry changes in M3b. The rigid
packet presentation objective and all physical M7 evidence gates remain unchanged.

Usage before the next dispatch: successor6/21 operations and3/6 remediation cycles;
cumulative9 submitted operations and3 remediation cycles across both runs. Fifteen
operations remain; deadline1792618090496 is unchanged. No limit renewal is needed.
