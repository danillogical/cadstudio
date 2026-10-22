# M3b final independent review

Operation `op_0mvienkny1843e0717c70612b`, generation3, run
`run_0mvi5dou92f2f6dc40f0d6379`, admitted by remediation
`dec_0mviemrs686ee2cc3f112e20b`. Codex independently reviewed source/diffs, real
compiled tests and CLI evidence. The final decision follows completion of regression.

## Verified corrections

Both base and half-dt validity and physical checks now gate the summary. Full half
checks/warnings and sixteen distinct base/half/negative CSVs are retained and rendered.
Fault-injection regressions isolate half invalidity (INCONCLUSIVE) and half physical
failure (FAIL) without changing comparison metrics. Empty checks do not pass.
Contact compliance is checked at the two-timestep boundary; explicit joint stops are
checked in the runner and, after supervisor hardening, generic AssemblySpec validation.
The supported1ms/0.5ms pair gives identical same-state limit force;2ms is rejected.
The damped slider now proves settled two-sided F/k within2% and0.1mm release return.
Slider release period uses its real spring reference; both hinges are compared during
refinement and use the common finite-state/input/force/energy/warning guards.

Independent pre-follow-up tests:159 mechanics/scene/hollow cases passed in23.50s.
OMP reported444 full tests; the final supervisor run below supersedes that count.

## Supervisor follow-up corrections

Two defects survived OMP's own review and were reproduced independently:

1. Effective motor control was calculated as actuator_force/gear. At gear2, the
   actual clipped motor drive1 and joint force2 were reported as effective0.5; at
   gear-2 the reported control incorrectly reversed sign. The unit-gain motors emitted
   by cadkit have actuator_force equal to their effective limited drive BEFORE gearing.
   Corrected the method/docstrings accordingly. Added actual compiled tests at gear1,
   gear2 and gear-2 for both unsaturated and million-unit control requests. This does
   not claim a general inverse for arbitrary servo/gain/bias/activation models.
2. An invalid half metric NaN propagated into convergence rows; strict summary writing
   then raised rather than preserving INCONCLUSIVE evidence. Nonfinite comparison
   values now become null, delta null, comparison false. Actual-run fault-injection
   tests cover NaN/+inf/-inf and verify strict summary plus readable failure report.

Also added generic pre-export joint-stop refsafe validation so callers outside the
fixture runner cannot silently compile a different effective limit compliance, and
finite checks for every reported passive/constraint force and energy. Four injected
fault regressions follow actual MuJoCo steps; these are test faults, not observed
spontaneous physical instability. Existing physical thresholds remain unchanged.

Final focused mechanics tests: **83 passed in16.14s**. Final full suite:
`PATH=/Users/daniel_l_newman/.local/bin:$PATH uv run pytest tests/ -q` ->
**455 passed in374.34s (6:14), exit0**. Full suite is justified by the additional
shared schema validation.

Fresh independent public CLI run:
`cad physics mechanics --out /tmp/cadstudio-m3b-supervisor-final-20261021` -> PASS/exit0,
all14 positive trials valid and satisfying checks, expected named missing-input and
missing-spring failures, eight comparison rows, sixteen distinct traces.
`--timestep0.002` with a separate fresh directory -> ERROR/exit3 at validation, with
an explicit contact-timeconstant/refsafe reason. No stepping occurs.

## Planning deviation and remaining scope

The repair's two native-plan calls timed out without usable plan output; OMP candidly
used its own inspectable derivation from the four supervisor findings. These attempts
do NOT establish a completed native plan. The original M3b increment had produced a
native plan before its implementation; this repair is a continuation of that increment,
but its requested new native planning result is a recorded process deviation. The code
gate is assessed independently; do not rewrite history or call the attempts successful.
M4a explicitly requires usable native plan output before production changes, resolving
any native background result rather than treating 'Working...' as completion.

Generic M3 readiness is independently accepted with the passing final regression. Real product S0,
pin/slot/linkage assembly behavior, packet presentation and physical correlation remain
in M5–M7. Analytic fixture coefficients and compliance are declared assumptions, not
PETG measurements. No CAD or global role/effort/provider/fallback settings changed.

Next bounded increment is `docs/mujoco-m4a-packet.md`: typed generic phase runner,
telemetry, four-state evaluation and reproducible evidence. M4b then adds full replay
and identity/direction/dwell event fixtures. Real Pocky adapter/S0 remains M5a. A fresh
OMP context with durable handoff is appropriate at this milestone boundary to avoid
accumulated implementation/test history; no model or supervision limit change needed.

Before next dispatch: successor8/21ops,4/6remediations; cumulative11submittedops and
4remediations.13ops remain, deadline1792618090496 unchanged. The same human-authorized
M0–M7 objective continues; no new scheduler or task is created.

Fresh raw final evidence is preserved at
`/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m3b-final-20261021/`.
