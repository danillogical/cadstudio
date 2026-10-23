# M5a-1: ONE bounded test portability and report correction

As the existing OMP Turn Orchestrator, read repository/Pocky guidance, invoked
orchestrator skill for your actual role, independent R1/R2 in
`docs/mujoco-m5a-1-s0-supervisor-review.md`, and renewal/admission IDs in
`docs/mujoco-supervision-renewal-8.md`. Same approved M5a-1 scope. The completed
S0 evidence is preserved and every run stays numerically INCONCLUSIVE.

## R1: portable new tests without weakening evidence validation

The new `tests/test_pocky_physics_s0_independent.py` fails on clean checkouts
because it unconditionally reads git-ignored generated S0 evidence. Independent
counterexample is documented with exact temporary-root command/raw output:
`out/mujoco-m5a-supervisor-s0/no-generated-evidence.{json,log}`: 8 failed,
1 pure conformance control passed. The real populated workspace's 145 passing
tests do not cover this environment.

Fix only the new, still-unaccepted S0 test module(s). Keep all meaningful
threshold/sign/unit/CAD/synthetic assertions running without generated evidence.
For evidence integration checks, use self-contained suitable fixtures or a clear
optional prerequisite when the entire generated evidence set is absent. Do not
blanket-skip the module, weaken assertions, commit `out/`, rename/remove current
evidence, or hide corruption/partial outputs. Existing malformed/partial evidence
must remain a loud failure, not be treated as ordinary optional absence. Prove:

1. A clean-like temporary root without generated evidence passes pure tests and
   explicitly skips only integration prerequisites (or generates valid fixtures).
2. With current real evidence present all substantive checks execute and pass;
   source statuses, checkpoints and replay reproduction remain verified.
3. A malformed/partial evidence control still fails clearly; no broad
   FileNotFoundError/Exception catch or `skipif` swallows broken evidence.

Temporary copied test/project roots are permitted; preserve accepted source and
real evidence directories. Add meaningful environment-boundary regression proof
without mirroring the helper implementation. Separate worker independently
validates the fix; actual configured ordinary reviewer must approve it.

## R2 and evidence preservation

Correct both S0 reports' inference that a .350→.427 mm peak after halving dt rules
out resolution artifacts. It only establishes that this approved halving did not
resolve the .2 mm validity breach. Numerical convergence and the root cause
remain undetermined. Do not re-run dynamics, investigate/tune the solver, alter
criteria/inputs, or reinterpret invalid results as physical FAIL/PASS.

Update test-count/environment documentation accurately. Preserve the original
S0 manifest as historical pre-repair evidence, with a clear pointer to NEW
final source/evidence manifest under `out/mujoco-m5a/s0-portability-repair/`.
Do not overwrite any original S0 raw run/replay/freeze/checkpoint evidence or
historical review. The final manifest must hash current source/reports plus the
retained original evidence and new correction evidence AFTER final edits.
Supervisor review/renewal/packet docs are pre-existing inputs; preserve them.

Use `PATH="$HOME/.local/bin:$PATH" uv run --frozen --extra physics ...`.
Run both new S0 modules in the real-evidence environment, the absent and broken
environment controls, then the full `pytest tests -q` once after final test
changes. Do not repeatedly run the full suite for report-only edits. Retain
exact commands, exit codes and raw logs. Required actual configured review and
independent worker handoff: record native transcript references/hashes, actual
model attribution and final verdicts; no substitute or role/model/provider/
effort/fallback/global configuration changes. No security-reviewer gate.

## Boundaries and stop

Allowed source surface: unaccepted new S0 tests, their documentation and the
two S0 reports; no generic/project production edits, scenarios/options/frozen
acceptance changes, CAD/params/dependencies, new runs or checkpoint changes.
Frozen presentation hash remains
`518a45ffc4592ca602be4c33c59681038e43dedaa15b688312202c3a57ff6ca2`;
S0 acceptance raw hash remains
`150c037b2e985dac46b66670c46291872d9e0cc9d287d7946eadf4d9185b5a3a`.
No scope expansion to solve physical/numerical validity, P0–P3, loaded/25/shared
state, M6/M7, commit/push/deploy. End this ONE operation for independent
Supervisor acceptance; do not self-admit followups or renew limits.
