# M1 report — optional MuJoCo extra and the primitive gravity fixture

Date: 2026-10-21 (America/Los_Angeles). Packet: **M1 only**. Baseline plan: `plan-mujoco.md`
§M1. Supervisor resolutions: `docs/mujoco-architecture-review.md` §21 (authoritative).
M0 decision: `dec_0mvhznmhv90c2edd931bdbed8`, run `run_0mvhxwg5l2aa1ba8e92d0c92f`.

---

## 1. Gate result

**M1 gate: PASS.**

| Requirement | Result | Evidence |
|---|---|---|
| Real MuJoCo installs and imports on Apple Silicon / Python 3.12 | PASS — 3.16.0, `cp312-macosx_11_0_arm64` wheel | §3 |
| Optional extra, pinned; CAD commands unaffected | PASS | §3, §6 |
| SI conversion, canonical mass formula locked by test | PASS — `1e-6` factor, mutation-proven | §5, §7 |
| Free fall matches `½gt²` within 1 % at 0.1 s | PASS — 6.5e-14 relative | §5 |
| Rests with bottom on the floor within 0.1 mm | PASS — 0.0005 mm | §5 |
| Finite values, valid contacts, low terminal velocity | PASS — 1.5e-13 m/s, no divergence | §5 |
| Two same-input runs identical | PASS — same scene hash, byte-identical trace | §5 |
| Negative cases return non-PASS | PASS — zero-g, wrong scale, bad mass, bad gravity | §5 |
| No-extra behavior verified in an import-blocked subprocess | PASS — 5 tests | §6 |
| Full existing suite green | PASS — **275 passed**, exit 0 | §8 |

No Pocky or armor CAD was touched. No physical claim is made: this packet proves the solver
and the units, not the dispenser.

---

## 2. Changed files

| File | State | SHA-256 |
|---|---|---|
| `pyproject.toml` | modified | `7b94ff6a65879931005a115072c9423d94a738d9d8eced282284152becfa635a` |
| `uv.lock` | regenerated | `a53eaa687da8fcb880032ee9a647b9bf3f7c47afb40a82fa7bb0eb0ebab1eeee` |
| `cadkit/cli.py` | modified (physics subparser, `cmd_physics`, usage-error mapping) | `aeb5ccad8b5cccd724268858cfd7ecff7877e7b221af5e70f68c8e804e8e9693` |
| `cadkit/physics/__init__.py` | new | `721d4a18c5f6c8c17d7f9bdd57a78ced80b8a4c15ae5bbf5bd363b8a0200f89d` |
| `cadkit/physics/units.py` | new | `2074216c83a9ee1bb7319d6c57a9bdcc44e794c1a18aa21b445dc055afe3a215` |
| `cadkit/physics/gravity_drop.py` | new | `c479b1a11818a91466316f3ca1302a385e1128f01a0784b818b1da5b2e0a93da` |
| `cadkit/physics/run.py` | new | `481930e5fd8a6ef10b93f69a685af2e7928a93fbcde800bf8fe39d9839b195ab` |
| `tests/test_cadkit_physics_units.py` | new | `13be6c87d5d17384f94e23f8dd0a6fa4c2e3f78b748375c2e721ab633fedb437` |
| `tests/test_cadkit_physics_gravity_drop.py` | new | `0144b4b0b506bef77ecd12f0347c12a2baf57bdcccf28afff83a1c3f947f68b6` |
| `tests/test_cadkit_physics_optional.py` | new | `282a44ab71fcb9aad04bdc3f50d58f5238b481f3f8f275be93ca76e3c4575853` |
| `README.md` | modified (Optional physics section) | `b5e413638dae42f50806f8384f2ce435fab3aede6e021a0e48e4fb0644ba1e4a` |
| `docs/mujoco-m1-report.md` | this file | see the packet completion message |

Generated, under `out/fixtures/gravity_drop/physics/` (gitignored):

- `m1-presnapshot/` — pre-mutation `pyproject.toml`, `uv.lock`, `pip-metadata.json` (95 pkgs)
- `20261021T114821Z-8d66ac43/` — canonical run: `manifest.json`, `scene.xml`,
  `summary.json`, `report.md`, `trace.csv`
- `m1-full-suite.txt` — full-suite log (275 passed)

Whole-snapshot diff against `~/.omp-bridge/backups/cadstudio-mujoco-20261021T095832Z/manifest.json`
(69 files): **exactly four baseline files changed** — `README.md`, `cadkit/cli.py`,
`pyproject.toml`, `uv.lock` — and everything else is hash-identical. Verified explicitly:

```
changed vs baseline: ['README.md', 'cadkit/cli.py', 'pyproject.toml', 'uv.lock']
pocky/armor/plans touched: none
```

`README.md` is an authorized docs change (a new "Optional physics" section); `pyproject.toml`
and `uv.lock` are the authorized dependency change (§3); `cadkit/cli.py` is the approved CLI
wiring. No `projects/pocky/**`, `projects/armor/**`, `plan-*.md` or M0 document was modified.

---

## 3. Dependency change, before → after

`pyproject.toml`:

```diff
+[project.optional-dependencies]
+physics = ["mujoco==3.16.0"]
+
 [[tool.uv.index]]
-url = "https://pypi.apple.com/simple"
+url = "https://pypi.org/simple"
```

Installed with `~/.local/bin/uv sync --extra physics --inexact` (exit 0). `--inexact`
preserves packages the lockfile does not manage, so the editor stack survived.

Environment diff, measured against `m1-presnapshot/pip-metadata.json`:

| Change | Packages |
|---|---|
| added | `mujoco 3.16.0`, `PyOpenGL 3.1.10`, `absl-py 2.5.1`, `etils 1.14.0`, `fsspec 2026.9.0`, `glfw 2.11.0`, `zipp 4.1.1` |
| changed | `websockets 17.2 → 17.3` — **installed-environment reconciliation only**; the lock already selected 17.3 (see §3 note) |
| removed | **none** |
| preserved | `ocp_vscode 4.2.0`, `ocp_tessellate 3.6.3`, `ocp_viewer_core 1.1.2`, `ipython 9.17.1`, `cyclopts 5.2.0` |

`uv.lock`: 94 → 102 packages. All existing CAD dependency versions are unchanged.

**Correction (M2a, supervisor finding).** An earlier revision of this report claimed the
`websockets` 17.2 → 17.3 change was a lockfile change forced by MuJoCo's floor. That was
wrong: the lock already selected 17.3 before this packet, and MuJoCo 3.16.0 declares
`websockets>=13`, not `>=16`. The change was reconciliation of a stale *installed* 17.2 to the
already-locked 17.3. No dependency version churn was caused by the physics extra.

Ordinary documented commands now work without any environment override — verified, not
assumed:

```
~/.local/bin/uv run cad list                         → exit 0, 8 models
~/.local/bin/uv run cad check armor/demo_cube --out … → exit 0
~/.local/bin/uv run cad physics smoke --out …         → exit 0, status PASS
```

`UV_NO_SYNC=1` is no longer needed. No global or user package-manager configuration was
modified.

---

## 4. Design of the package

`cadkit/physics/` — four modules, 773 lines, deliberately smaller than the M0 sketch:

| Module | Responsibility |
|---|---|
| `__init__.py` | `require_mujoco()`, `PhysicsUnavailable`, `CheckResult`, `RunResult`, `EXIT_CODES` |
| `units.py` | the single SI boundary; `mass_kg`, `inertia_kg_m2`, `mm_to_m`, `GRAVITY` |
| `gravity_drop.py` | `DropSpec`, MJCF emission, `simulate()`, analytic references |
| `run.py` | `evaluate()`, artifact writing, report rendering |

Not pre-implemented (M2+): part/body/collider schema, MJCF for CAD solids, scenarios,
telemetry, sweeps, viewer. The M0 contracts remain the design; only the pieces M1 needs exist.

Laziness is structural, not conventional: `cadkit/cli.py` imports `cadkit.physics` **inside**
`cmd_physics`, and `gravity_drop` imports `mujoco` only inside `simulate()` via
`require_mujoco()`. Importing `cadkit.cli` and `cadkit.physics` leaves `mujoco` out of
`sys.modules` — asserted by a test.

---

## 5. The fixture and its evidence

20 mm cube, density 1.27 g/cm³, bottom released 100 mm above a fixed floor, RK4, dt = 1 ms,
0.6 s, seed 0.

| Quantity | Analytic reference | Measured | Verdict |
|---|---|---|---|
| Mass | `8000 mm³ × 1.27 × 1e-6` = **0.01016 kg** | 0.01016 kg | PASS (4.9e-10 rel) |
| Inertia (cube, COM) | `m a²/6` = **6.773333e-7 kg·m²** | 6.773333e-7 | PASS (4.9e-10 rel) |
| Free-fall displacement ≤ **0.1142 s** (0.8 × `t_c`) | `½gt²` | max rel. error **6.5e-14** | PASS (tol 1 %) |
| Contact time | `√(2h/g)` = 0.14281 s | 0.1450 s (5 ms sampling) | PASS (1.53 %, tol 8.5 %) |
| Rest height | bottom at 0 | **−0.0005 mm** | PASS (tol 0.1 mm) |
| Terminal speed | 0 | 1.5e-13 m/s | PASS (tol 0.01 m/s) |
| Settled penetration | 0 | 0.0005 mm | PASS (tol 0.1 mm) |
| Impact penetration | `v·τ` = 1.400 × 0.002 = **2.80 mm** | 1.097 mm | PASS |
| Compiled vs declared gravity (signed z) | **−9.80665 m/s²** | −9.80665 m/s² | PASS (0 delta) |
| Compiled vs declared SI size/mass, plus absolute window | 0.01 m / 0.01016 kg; window 1e-5..2 m, 1e-4..1000 kg | equal, inside | PASS |
| build123d vs analytic | volume 8000 mm³, inertia 6.773333e-7 | equal | PASS (2.3e-16) |

The penetration bound is a **scale estimate**, not a closed-form limit: `impact speed ×
solref time constant` (1.400 × 0.002 = 2.80 mm) is the order of magnitude a compliant contact
can be compressed at that impact speed. The first draft used an arbitrary 0.5 mm and failed at
1.10 mm; the fix was to derive the scale, not to widen an arbitrary number. The real acceptance
criterion is the **settled** penetration, which keeps the tight 0.1 mm limit.

Free-fall window: the analytic comparison stops at **0.8 ×** the analytic contact time, which
keeps several trace samples of headroom so a sample landing after contact cannot clip the
displacement and cause a spurious failure. The gate is against the continuum `½gt²`; with RK4
at 1 ms the residual is 6.5e-14, so the integrator's own convergence is not what is being
measured.

Determinism: two runs with identical inputs produce the same `scene_hash`
(`8d66ac43…`), byte-identical `scene.xml` and byte-identical `trace.csv`; the run id differs
only by its UTC timestamp.

Runtime: 600 steps in **6.3 ms** wall time; whole `cad physics smoke` ≈ 2 s including
interpreter start.

Negative cases, each exercised through the real CLI:

| Case | Status | Exit |
|---|---|---|
| `--gravity 0` | FAIL (`freefall`/`contact_detected` INCONCLUSIVE, `rest_on_floor` FAIL) | 1 |
| `--gravity -9.8` | ERROR, rejected as invalid input | 3 |
| `--edge-mm 20000` (20 m: a unit mix-up) | FAIL (`si_plausibility` outside the absolute SI window) | 1 |
| `--edge-mm 200` (legitimate 200 mm fixture) | **PASS** — self-consistent, not a wrong-scale case | 0 |
| `--density 0` | ERROR, rejected as invalid input | 3 |
| `--out /` (unwritable) | ERROR with machine-readable status, no traceback | 3 |
| missing extra | ERROR with `uv sync --extra physics` on stderr | 3 |
| `cad physics` (no verb), `--bogus` | ERROR, not argparse's 2 | 3 |
| `--duration 1e6` | ERROR, exceeds the 200 000-step budget | 3 |

---

## 6. Optional-dependency isolation

`tests/test_cadkit_physics_optional.py` installs an `__import__` hook in a subprocess that
raises `ModuleNotFoundError` for `mujoco`, then runs the real CLI. Nothing is uninstalled.

| Check | Result |
|---|---|
| `cad list` | exit 0, models listed |
| `cad check armor/demo_cube` | exit 0, `report.json` written |
| `cad build armor/demo_cube` | exit 0, `cube.step` written |
| `cad physics smoke` | exit 3, `"status": "ERROR"` on stdout, actionable stderr, no traceback |
| `import cadkit.cli, cadkit.physics` | `mujoco` not in `sys.modules` |

---

## 7. Tests added

51 tests in three flat modules, matching the repo convention.

- `test_cadkit_physics_units.py` (8): `1e-6` mass factor including the supervisor's
  `20×40×25 @ 1.27 → 0.0254 kg`; explicit assertion that the `/1000` answer is wrong;
  inertia `1e-12` factor cross-checked against `m(a²+b²)/12`; rejection of zero, negative,
  NaN and infinite inputs.
- `test_cadkit_physics_gravity_drop.py` (38): analytic free fall, contact time, rest,
  terminal speed, all-checks-pass, scene-hash identity, two-run equality, wrong gravity,
  zero gravity, wrong scale, invalid specs, artifact completeness, strict-JSON parsing of
  every artifact, and CLI exit codes.
- `test_cadkit_physics_optional.py` (5): the isolation matrix above.

Every expected number is a closed-form formula written in the test. **Mutation-proven**:
setting `MASS_FACTOR = 1e-3` fails 7 tests; setting `MM_TO_M = 1e-2` fails 11. Both factors
are load-bearing.

---

## 8. Commands, exit codes, evidence

| Command | Exit | Note |
|---|---|---|
| `~/.local/bin/uv lock` | 0 | 94 → 102 packages |
| `~/.local/bin/uv sync --extra physics --inexact` | 0 | 9 installed, 0 removed |
| `uv run cad list` | 0 | ordinary documented path, no override |
| `uv run cad check armor/demo_cube --out /tmp/…` | 0 | CAD regression |
| `uv run cad physics smoke --out /tmp/…` | 0 | PASS |
| `.venv/bin/cad physics smoke` | 0 | canonical run `20261021T114821Z-8d66ac43` |
| `pytest tests/test_cadkit_physics_*.py -q` | 0 | 51 passed |
| `PATH=~/.local/bin:$PATH pytest tests -q` | 0 | **275 passed in 325.8 s** |

Log: `out/fixtures/gravity_drop/physics/m1-full-suite.txt` (275 passed in 325.8 s).

---

## 9. Independent review

One reviewer subagent (`M1Review`) audited the package read-only. Three findings, all valid,
all fixed:

1. **Non-strict JSON.** `summary.json` emitted `NaN` and `manifest.json` emitted `Infinity`
   on the zero-gravity path; strict parsers reject the whole file. Fixed: non-finite metrics
   serialize as `null`. Regression test parses every artifact with a rejecting
   `parse_constant`.
2. **Status line missing on artifact-write failure.** An `OSError` from an unwritable
   `--out` escaped as a traceback with no machine-readable status. Fixed: `OSError` is caught
   and returns ERROR/3. Verified with `--out /`.
3. **`si_plausibility` was a dead check.** The fixed ranges scaled with the box size, so the
   check could not fail. Fixed: it compares the compiled SI values against the declared
   mm/kg values *and* against an absolute window. Mutation-verified both ways: widening the
   window makes the unit-mixup test pass when it must fail.

The reviewer also reported no defect in false-PASS paths, lazy imports, exit codes, or
determinism.

A second review round found further defects, all fixed and each with a regression:

4. **Signed gravity.** `simulate()` stored `abs(gravity_z)` and the check compared magnitudes,
   so a scene emitting `+9.80665` would have passed the very check meant to catch it. Now
   stores the signed z component and compares against `-spec.gravity_m_s2`; a monkeypatched
   sign flip fails the check.
5. **Usage errors collided with INCONCLUSIVE.** argparse exits 2 on any usage error, and
   `cad physics` / `cad physics smoke --bogus` never reached `cmd_physics`, so no status line
   was emitted. A typo would have read as a legitimate INCONCLUSIVE verdict. Physics usage
   errors now emit `{"status": "ERROR"}` and exit 3; non-physics verbs keep argparse's 2.
6. **Unbounded duration.** `duration_s` was unbounded, so `--duration 1e6` preallocated a
   multi-GB trace and raised `MemoryError`, which escaped as a traceback. A 200 000-step
   budget now rejects it in `validate()`.
7. **A pipe in a detail string** (`|vz|`) split the Markdown table row into extra columns.
   Changed to `abs(vz)`, with a test asserting every row has the same cell count.
8. **A stale plausibility claim.** `--edge-mm 200` is a legitimate fixture and passes; the
   earlier "wrong scale" negative was invalid. Replaced with a 20 m box, which can only be a
   unit error, plus an absolute SI window alongside the self-consistency comparison, proven
   load-bearing by mutation.
9. **Trace headroom.** The free-fall window was 0.9 × `t_c`, only ~1.5 trace samples from
   contact; now 0.8 ×.

Two defects I found myself and fixed:

- **Encoding.** `report.md` contained a non-ASCII em dash and was written without
  `encoding=`, which raised `UnicodeEncodeError` under an ASCII locale. All artifacts are now
  written UTF-8 and are pure ASCII. Verified with `LC_ALL=C`.
- **Negative gravity.** `gravity_m_s2 < 0` was silently emitted as `+g` because `simulate`
  takes `abs()`. Now rejected as invalid input.

Also corrected: the plausibility check was reading the floor plane's 1 m half-size instead of
the box's 0.01 m; it now scopes to the body's own geoms.

---

## 10. Remaining risks and limitations

1. **One fixture only.** This proves the solver, the units and the reporting skeleton. It
   says nothing about CAD-derived geometry, concave colliders, contacts between printed parts,
   joints or springs. Those are M2/M3 and remain entirely unvalidated.
2. **MuJoCo version pin.** `mujoco==3.16.0` is exact. A bump may change contact behaviour and
   therefore `transient_penetration`; the scene hash includes the version, so a bump
   invalidates cached results by construction.
3. **`websockets` installed version moved 17.2 → 17.3.** This was *not* a lockfile change: the
   lock already selected 17.3, and MuJoCo 3.16.0 requires only `websockets>=13`. A stale
   installed 17.2 was reconciled to the locked 17.3. No project dependency version changed.
4. **Index change is project-local.** `pyproject.toml` now defaults to `pypi.org`. Anyone
   relying on the Apple index inside this repo will see different resolution. No global
   config was touched.
5. **No CI.** All verification is local and manual. There is no automated gate that would
   catch a regression on another machine.
6. **Exit code 2 (INCONCLUSIVE) still has no CLI coverage.** Every path that produces
   INCONCLUSIVE also produces a FAIL, so the overall status never reaches 2. Usage errors now
   correctly map to 3, so 2 is unambiguous when it does occur. M4 will exercise it with
   scenarios whose validity checks fail independently of their predicates.
7. **Physical behaviour remains unverified.** Nothing here is evidence about the dispenser,
   the body support defect, packet feeding, or any printed part. M1 is infrastructure.

---

## 11. Recommendation

Accept M1 and proceed to **M2a** (CAD part/frame/visual export and collider recipes). Three
carry-forwards:

1. Keep `si_plausibility` as the conversion guard; do not replace it with fixed ranges.
2. Every new artifact writer must be strict-JSON safe and UTF-8, and must return ERROR/3 on
   `OSError` — the two defects this packet found are the class of bug that silently breaks
   downstream consumers.
3. The M0 support finding (§1.4: clips are retention-only, no downward load path) is untouched
   and still requires the S0 scenario in M3/M5a. M1 neither confirms nor weakens it.

No M2 work was started. Codex owns acceptance.
