# M3a report — generic MJCF exporter repair

Date: 2026-10-21. Packet: **M3a generic exporter repair only**, supervision run
`run_0mvi5dou92f2f6dc40f0d6379`, pending retry decision `dec_0mvi8f48s09a0e9a7ce70e493`,
handoff `ho_0mvi8f48ye3bbc1b62ef46bec`. Scope authority:
`docs/mujoco-m3-supervisor-review.md` and `docs/mujoco-m3a-retry-review.md`.

No M3b fixture expansion, no product adapter, no CAD changes. M3a is not M3, and this report
makes no M3 or product claim.

---

## 1. Result

| Supervisor defect | Status | Evidence |
|---|---|---|
| 1. Flat body hierarchy (all `body_parentid == 0`) | **Fixed** | true nested `<body>` tree; `test_compiled_body_parent_graph_is_nested` |
| 2. Parent-relative pose used unverified Euler extraction | **Fixed** | relative rotation emitted as a unit `quat`; FK/pose regressions below |
| 3. Hinge `range` and `springref` interpreted as degrees | **Fixed** | compiler is now `angle="radian"`; `test_compiled_hinge_range_and_springref_are_radians` |
| 4. `max_effort` only bounded `ctrlrange`, not transmitted effort | **Fixed** | `forcerange = max_effort/|gear|`; `test_compiled_actuator_bounds_generalized_effort` |
| 5. `n_free_joints` type counting | **Preserved** | unchanged; `test_body_and_freejoint_counts` still passes |
| 6. Four tests expected construction-time validation | **Fixed at the documented boundary** | tests now call `AssemblySpec.validate()`, which `export_scene` always runs |
| 7. New spring-sign test was physically wrong | **Fixed from the formula** | `F = -k(q - ref)`; at `q = 0`, `ref = 0.02`, `k = 50` → `+1.0 N` |
| 8. Collider `euler` silently reinterpreted by the compiler | **Fixed** | collider rotation emitted as `quat`, checked against build123d |
| 9. XML text capped every pose at ~1e-9 | **Fixed** | `_f` is now shortest round-trip `repr`, not `%.9g` |

Two additional real defects surfaced while making the graph tests meaningful, and were fixed
in the source rather than in the tests:

- `BodySpec.validate` reported "needs a parent body" before "cannot be fixed to the world",
  so the more fundamental conflict was masked. Ordering fixed, message now names the rule.
- The joint/body-id mismatch message did not name the `body_id` field. Message fixed.

---

## 2. What changed

`cadkit/physics/scene.py`

- `_relative_pose` replaces `_relative_frame`. The parent-relative rotation is emitted as
  MuJoCo `quat="w x y z"`, normalised and sign-fixed for determinism. `_euler_from_matrix`
  (an XYZ extraction whose composition order did not match build123d) is deleted.
- `export_scene` builds the body tree explicitly: a `prepared` map plus `children_of`, then a
  recursive `render(body_id, depth)` that nests each child inside its parent's element.
  Roots are emitted at depth 2; nested children indent correctly at every level.
- `_body_xml` takes `depth` and pre-rendered `children`, emits `quat` instead of `euler`, and
  indents joints, freejoints, inertials, visuals and colliders at the body's own depth.
- `_collider_xml` emits `quat` from `_quat_from_rot_deg` (`build123d.Rot(...).GetRotation()`).
- `_joint_xml` no longer branches on hinge vs slide: with `angle="radian"` both emit the SI
  value verbatim, so nothing can be converted twice.
- `_actuator_xml` is new: `ctrlrange` **and** `forcerange` are `max_effort / |gear|`.
- `_assemble_xml` declares `angle="radian"`.
- `_f` returns `repr(float)`, the shortest round-trip decimal.

`cadkit/physics/schema.py`

- `SpringSpec.force_at` docstring states the correct sign (positive below the reference).
- `JointSpec` documents `anchor_mm` as body-local mm and states that the XML carries radians.
- `ActuatorSpec` documents `max_effort` as **generalized** effort after the gear, for either
  sign of gear.
- `BodySpec.validate` reports fixed-to-world before missing-parent, and names `body_id`.

`tests/test_cadkit_physics_mechanics.py`

- Graph tests validate through `AssemblySpec.validate()`, with the boundary stated once.
- Spring test corrected from `-k(q - ref)`.
- Eight compiled-integration regressions added, one parametrized over three gear ratios
  (eleven test cases), plus one export-level boundary regression; see §3.1.

---

## 3. Commands and results

All commands run from `/Users/daniel_l_newman/src/cadstudio` with
`/Users/daniel_l_newman/.local/bin/uv`. MuJoCo 3.16.0, Python 3.12, macOS arm64.

```
uv run pytest tests/test_cadkit_physics_mechanics.py -q
33 passed in 0.31s

uv run pytest tests/test_cadkit_physics_scene.py tests/test_cadkit_physics_export_cli.py \
             tests/test_cadkit_physics_units.py tests/test_cadkit_physics_optional.py \
             tests/test_cadkit_physics_gravity_drop.py -q
101 passed in 37.71s

uv run pytest tests/test_cadkit_physics_hollow.py -q
47 passed in 12.35s

PATH="$HOME/.local/bin:$PATH" uv run pytest tests/ -q
403 passed, 1 failed in 5:51   # the one failure is the pre-existing locale defect, §5.7
```

The five pre-existing failures are gone (`5 failed, 16 passed` → `33 passed`).

### 3.1 Compiled integration regressions (new)

Every one reads the compiled `MjModel`/`MjData`, never the XML text.

| Test | What it proves |
|---|---|
| `test_compiled_body_parent_graph_is_nested` | `body_parentid` is `base→l1→l2→l3`, and the leaf is explicitly not parented to the world |
| `test_compiled_world_poses_match_independent_forward_kinematics` | `xpos`/`xmat` at `qpos = 0` equal the assembly frame, recomputed independently (`Rx@Ry@Rz` per build123d) |
| `test_compiled_chain_moves_correctly_under_nontrivial_joint_angles` | with `q = (0.3, -0.45, 0.011)`, poses match an independent FK that applies each hinge about its own anchor in the child frame and the slide along its axis |
| `test_compiled_joint_anchors_and_axes_follow_the_parent_rotation` | `xanchor`/`xaxis` include every ancestor rotation |
| `test_compiled_com_and_inertia_survive_the_nested_placement` | `body_mass`, `body_ipos`, `xipos` and the tensor rebuilt from `body_inertia`/`body_iquat` match the CAD-derived inertial |
| `test_compiled_hinge_range_and_springref_are_radians` | `jnt_range = [-0.5, 1.1]` rad and `qpos_spring = 0.25` rad; `qfrc_spring = -k(q-ref)` at three coordinates |
| `test_compiled_slide_range_and_springref_are_metres` | slide range/`springref` survive as metres |
| `test_compiled_collider_rotation_is_the_declared_rotation` | `geom_xmat` equals `Rx(30)Ry(12)Rz(55)` from the declared `rot_deg` |
| `test_compiled_actuator_bounds_generalized_effort[1.0/2.0/-1.5]` | with `ctrl = ±1e6`, `|qfrc_actuator| <= 1.5 N` exactly at the bound; `|actuator_force| <= 1.5/|gear|`; sign follows the gear; holds for 1000 saturated steps |
| `test_export_enforces_the_graph_boundary_before_writing` | an orphan parent and a two-body cycle passed to `export_scene` raise `ValueError` and leave **no output directory**, so the boundary is enforced in production, not only by a direct `validate()` call |

The three-level chain (`base` fixed → `l1` hinge Z → `l2` hinge Y → `l3` slide X) has
non-axis-aligned, non-commuting frames (`(12,-25,40)`, `(35,10,-20)`, `(-15,50,25)`,
`(60,-30,15)` degrees) and offset anchors, so a flat hierarchy, a transposed rotation, or an
Euler-order slip cannot pass.

### 3.2 Live mechanics run (unchanged fixtures, new exporter)

`cad physics mechanics` **is** reachable from the public CLI (`cadkit/cli.py:308`, parser
`:413`), which corrects the supervisor review's "public mechanics CLI absent" finding. Actual
invocation and exit code:

```
PATH="$HOME/.local/bin:$PATH" uv run cad physics mechanics --out /tmp/m3a-mech-cli2
→ exit 0
{"status": "PASS", "scenario": "m3_mechanics", "detail": "step 0.001 s"}
loaded_slider: valid True, 4/4 checks pass
hinge_oscillator: valid True, 4/4 checks pass
```

The same two fixtures through `cadkit.physics.mechanics_run.run_mechanics` into a temporary
directory:

```
status PASS
loaded_slider    driven_displacement  x after push 0.02000 m vs band [0.01900, 0.02100]
                 returns_to_reference final |x| 0.000 mm vs 2.0 mm
                 settled              final |v| 0.0000 m/s
                 bounded_input        peak |actuator force| 1.0000 N vs 2.0 N
hinge_oscillator period               measured 0.03550 s vs analytic 0.03550 s (0.00%)
                 inertia_agrees       CAD 6.384512e-07 vs analytic 6.384512e-07 kg m2
                 range_respected      max |angle| 0.17453 rad vs 1.04720 rad
                 spring_force_present restoring force is the declared spring
```

This is a smoke run of the repaired exporter through the existing fixtures. It is **not** M3b
evidence and does not establish the M3 gate.

---

## 4. Deviations from the retry-review plan

The native plan (three steps: nested world transforms with an independent three-level check;
SI conversion at the boundary; bounded physical input with boundary/NaN tests) was followed.
Two deliberate differences:

1. **Units.** The plan suggested converting joint commands to SI at the boundary. The emitter
   instead declares `angle="radian"` and emits the schema's already-SI numbers unchanged, and
   the *collider* Euler degrees are converted once, to a quaternion. One convention, one
   conversion site, no chance of a 57× error.
2. **Effort bound.** The plan said to validate against declared min/max before applying.
   Validation already rejects non-positive/non-finite `max_effort`; the gap the supervisor
   found was in *transmission*, so the fix is `forcerange` plus a documented generalized-effort
   contract, proven on `qfrc_actuator` rather than on `ctrl`.

`SLIDER_KG` remains unused. That is M3b fixture scope (`docs/mujoco-m3-supervisor-review.md`),
deliberately not touched here.

---

## 5. Unresolved issues

1. **Joint stops are soft, and a saturated input can push well past the declared range.**
   MuJoCo limit constraints are compliant (`solref` time constant 0.02 s by default), so on
   this very light carriage (≈0.6 g, because `SLIDER_KG` is unused) a saturated 1.5 N reaches
   an equilibrium penetration of order `F·tc²/m`, far beyond the 0.05 m range: observed
   `qpos = 0.428 m` against `range = ±0.05 m`. This is expected soft-limit behaviour, not a
   broken limit, and the actuator test therefore asserts only the effort bound it is about
   (1000 saturated steps still peak at exactly 1.5 N). Whether stops must be stiffened, or the
   carriage given its declared 0.25 kg, is an M3b physical-fixture decision. The exporter
   emits no limit `solref`/`solimp`, so it inherits the compiler default.
2. **`n_free_joints` is still a count, not a topology check.** Unchanged and correct for its
   purpose; no test asserts it stays zero for jointed bodies beyond the existing count test.
3. **`anchor_mm` is body-local by documentation, not by type.** Both existing fixtures happen
   to use anchors that read correctly either way for the fixed parent, so a wrong-frame anchor
   in a *rotated* parent would only be caught by a fixture that exercises it. The compiled
   anchor/axis regression covers that case for the chain, but no schema-level guard exists.
4. **Provider interruption risk.** The previous attempt died on an HTTP400 from the model
   provider during a long planning request. This turn used narrow reads and no long planning
   call. If the same error recurs, source changes are on disk and this report records them.
5. **No independent review yet.** `test_cadkit_physics_mechanics.py` is authored by the same
   agent that wrote the exporter; the FK in the tests is written from MJCF semantics, not
   copied from the emitter, but an independent reviewer should re-derive at least the hinge
   anchor formula `rel_p' = rel_p + rel_R (I - K) a`.
6. **One `angle="degree"` compiler remains, in the M2b diagnostic only.**
   `cadkit/physics/hollow.py:303` (`concave_mesh_diagnostic_xml`) still declares
   `angle="degree"`. It is harmless today — that XML carries no `euler`, `range`, `axis` or
   `springref` attribute, so the setting is never consulted — but it is now the only degree
   compiler left in the package, and a hinge or spring added there later would silently repeat
   the 57× error. Left unchanged because it is M2b test-only code outside this packet's scope;
   the one-line fix for its owner is `angle="radian"`.
7. **Pre-existing suite failure, not caused by M3a, not fixed here.** In a full-suite run,
   `tests/test_cadkit_physics_hollow.py::test_no_qpos_is_written_after_release` fails with
   `UnicodeDecodeError: 'ascii' codec can't decode byte 0xe2`. Cause: `build123d.Mesher().write()`
   (called by `cadkit/export.py:23` for STL/3MF) leaves the process `LC_CTYPE` at `C`/US-ASCII,
   so a later locale-dependent `Path.read_text()` on UTF-8 source fails. Minimal repro, two
   tests only:

   ```
   uv run pytest "tests/test_cadkit_export_cli.py::test_export_part" \
                 "tests/test_cadkit_physics_hollow.py::test_no_qpos_is_written_after_release" -q
   → 1 failed, 1 passed
   ```

   The same pair fails identically on the untouched partial-M3 snapshot
   (`/Users/daniel_l_newman/.omp-bridge/backups/cadstudio-mujoco-m3-partial-20261021T144357Z`),
   and `cadkit/export.py`, `cadkit/mesh.py`, `hollow_run.py` and both tests are byte-identical
   to that snapshot. `cadkit/export.py` is CAD-side code that this packet is forbidden to
   change, so the fix is deferred to the CAD owner. Two candidate fixes for that owner: pass
   an explicit `encoding="utf-8"` at the affected read, or restore `locale.setlocale` around
   the mesher write. Neither is applied here.

   Full-suite result with the defect present: **403 passed, 1 failed** in 5:51 (reproduced
   twice, identical).

   Note also that `tests/test_cadkit_export_cli.py` shells out to bare `uv`, so the suite needs
   `~/.local/bin` on `PATH`; without it, six CLI tests fail with `FileNotFoundError: 'uv'`.
   That is an environment requirement, not a code defect.

---

## 6. Files changed

- `cadkit/physics/scene.py`
- `cadkit/physics/schema.py`
- `tests/test_cadkit_physics_mechanics.py`
- `docs/mujoco-m3a-report.md` (this file)

No CAD, project, CLI, or model file was touched. No dependency, provider, or model-routing
configuration was changed.
