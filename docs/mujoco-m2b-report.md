# M2b report — hollow-collision fidelity (remediated)

Date: 2026-10-21. Packet: **M2b final runtime/evidence repair**, supervisor decision
`dec_0mvi7d77obcabe900e420cf66` (operation `op_0mvi7d77w43e3da7d8964e30a`) under run
`run_0mvi5dou92f2f6dc40f0d6379`. Previous repair scope: `dec_0mvi6lbev5c2900c5e70c7917`.
Prior scope: `docs/mujoco-m2b-supervisor-review.md`. No M3, no Pocky adapter.

---

## 1. Gate result

**M2b gate: PASS**, after remediation of all eight supervisor defects.

| Supervisor defect | Status | Evidence |
|---|---|---|
| 1. Compound inverse rotation wrong | **Fixed** | `_local` uses `R.T @ (p - pos)`; the supervisor's exact repro now returns interior |
| 2. False PASS on invalid dynamics | **Fixed** | validity gates status; `INCONCLUSIVE` for non-finite/warnings |
| 3. Negative was a box, not a mesh | **Fixed** | real `<mesh type="mesh">` over the original STL |
| 4. Through-path dynamics absent | **Fixed** | probe traverses the 120 mm channel and exits past x = 66 mm |
| 5. Excess contact compliance hidden | **Fixed** | declared `solref`; depth measured from the contact list |
| 6. Surface metric zero for buried surfaces | **Fixed** | signed distance; over-thick wall now fails |
| 7. Overlay primitive fidelity | **Fixed** | cylinder rotation, real capsule ends, explicit reject |
| 8. Missing report; table-breaking cell | **Fixed** | this file; trace header corrected |
| 9. Evidence could be overwritten | **Fixed** | timestamped run dirs; reuse refused (ERROR/3) |
| 10. Overlay camera set after projection | **Fixed** | projection first, then camera, then render |
| 11. Transit end point unmeasured | **Fixed** | swept start *and* end recorded |
| 12. Requested timestep never reached the model | **Fixed** | propagated into both scenes; compiled dt asserted equal to the request |
| 13. Contact compliance scaled with dt | **Fixed** | `solref` is now absolute SI seconds, so refinement changes integration only |
| 14. Half-step convergence claim was false | **Fixed** | real baseline/half pair below; depth 0.029 → 0.000 mm |
| 15. Invalid scene conflated with physical failure | **Fixed** | per-trial `scene_valid` + `scene_invalid_reason`; status stays M1's four values |

---

## 2. Changed files

| File | State | SHA-256 |
|---|---|---|
| `cadkit/physics/collision.py` | new | `1197a15b1ec94ca11cb464a23ea5c7e49e2164eeb1b6844b96d91eb4ce8cd914` |
| `cadkit/physics/hollow.py` | new | `911ebe9c451444b59a8d73e5caf79360597b0e003c96ea224acfb5b599d0cc37` |
| `cadkit/physics/hollow_run.py` | new | `81774cd849ff19e1b333520cf7f0e112809607a43762596aaf1e60b8b878f2a8` |
| `cadkit/physics/overlay.py` | new | `bc75fae08fc415fcc6eacb1c4918c65d5ca49a8dfd268a5dc9f9ce8a9ca9a31a` |
| `cadkit/physics/scene.py` | modified (fidelity gate, validation before `mkdir`, friction/solref) | `f8d3757b9c6491f9dd224bdf217075399a3687a4e2676ae73fc9395c1d7c4ab4` |
| `cadkit/physics/schema.py` | modified (`BodySpec.fidelity`, `friction`, contact model) | `f11a2ab2a44d9ea1688d1df2a5aa14b48f40737bfe277142b58e1f6c08497441` |
| `cadkit/cli.py` | modified (`physics channel`) | `1a8882b3f5260270f7cfed90ce5ae6f7d0105bfac5846cb1696da31958c78adb` |
| `cadkit/physics/__init__.py` | modified (`SCENE_INVALID` status) | `54d94fd619cb317ca4513aeb84cf4d915446ae6273ba12909091a6c406600b57` |
| `tests/test_cadkit_physics_hollow.py` | new | `3a9709564e43f11350130336428700e2c9020d618d623db7a0bcea590f74829d` |

No Pocky or armor CAD, params, plans or global configuration changed.

---

## 3. Commands and results

```
.venv/bin/cad physics channel                       → PASS, scene 89df9e65fbccabbc, exit 0
.venv/bin/cad physics channel --out <fresh-dir>     → same, artifacts written
.venv/bin/cad physics channel --out <used-dir>      → ERROR/3, refuses to overwrite evidence
physics channel (mujoco import blocked)             → ERROR/3, "uv sync --extra physics"
export_scene(u_channel_spec_bad_recipe())           → SceneInvalid, no output directory created
pytest tests/test_cadkit_physics_hollow.py -q       → 46 passed
pytest tests/test_cadkit_physics_*.py -q            → 147 passed in 49.8 s
```

Artifacts under `out/fixtures/m2b_u_channel/physics/<run-id>/` (a fresh timestamped
directory per run; a second run into a non-empty directory is refused rather than
overwriting evidence):

| File | SHA-256 (prefix) |
|---|---|
| `summary.json` | `bed46e9e8bc684a8` (records `run_id`, `run_dir`, MuJoCo version) |
| `scene/scene.xml` (+ `report.json`, `assets/`) | `e87955d02486ace6` |
| `mesh_diagnostic/u_channel.stl` | `fd3f2a2643fbab97` |
| `mesh_diagnostic/scene_mesh_diagnostic.xml` | test-only |
| `trace_positive.csv`, `trace_mesh_diagnostic.csv` | raw per-step |
| `collision_overlay.png` | inspected |

---

## 4. The physical result

Fixture: U-channel, walls 120 mm long, cavity 30 mm wide × 35 mm high, floor with a 30 mm
lead-in/lead-out at each end. Probe: 12 mm cube, 1.24 g/cm³, resting on the floor at z = 11 mm.

| Trial | initial pen. (mm) | crossed exit | y dev (mm) | z dev (mm) | max depth (mm) | valid | verdict |
|---|---|---|---|---|---|---|---|
| correct multi-box recipe | 0.000 | yes | 0.00 | 1.08 | 0.029 | yes | **pass** |
| concave-mesh diagnostic | **11.389** | — | — | **109.92** | 0.000 | yes | **fail** |

The probe starts outside the −X mouth with one recorded initial velocity of 2.2 m/s, applied
once at t=0 after a 50 ms settle. Everything after that is gravity and contact; no `qpos` is
written again (asserted by a source scan in the tests).

**Correct recipe**: it slides the open length, crosses the exit plane at x = 66 mm within
1.08 mm of the declared resting height, and the deepest contact is 0.029 mm. All seven solver
warning counters are zero.

**Concave-mesh diagnostic**: the same CAD, collided as the original STL with `type="mesh"`.
MuJoCo replaces it with its convex hull, which fills the cavity — so the probe begins
**11.389 mm inside solid material**. This is reported as **`scene_valid = false`**, distinct
from numeric validity: there are no non-finite states and no solver warnings, the *collider
representation* is wrong. The probe's subsequent ejection is not predictive dynamics evidence
and is never counted as a physical traversal failure. A positive trial with initial overlap
can never be a PASS (asserted by a test).

**Contact validity** (defect 5): the scene emits an explicit `solref="0.002 1"`. The time
constant is **absolute SI seconds**, not a timestep multiple, so refining the step changes
integration resolution without also stiffening the contact — otherwise the convergence check
would be confounded. Measured depth is read from the actual contact list (`-contact.dist`),
not from a pose estimate.

**Timestep convergence** (defect 12/14). The requested step is now propagated into the
production spec *and* the generated diagnostic XML, and `_simulate` derives every step count
and sampling cadence from `model.opt.timestep`, asserting it equals the request. A mismatch
raises rather than silently running the wrong duration.

| Trial | compiled dt | settle end | trial window | max depth (mm) | max x (mm) | z dev (mm) | verdict |
|---|---|---|---|---|---|---|---|
| baseline | 0.001 s | 0.050 s | 0.050–0.850 s | 0.029 | 1350.32 | 1.084 | pass |
| half step | 0.0005 s | 0.050 s | 0.050–0.850 s | 0.000 | 1402.72 | 0.969 | pass |

Both phases now last exactly as declared, and the depth difference (0.029 → 0.000 mm) is a
real measured change, not an artifact of an unchanged compiled model. The earlier claim that
depth was "unchanged at half timestep" was wrong: the compiled model had never received the
requested step.

---

## 5. What each fix changed

1. **Inverse rotation.** `_local` now applies `R.T @ (p − pos)`. The supervisor's repro —
   box `(10, 2, 1)` at `(25, 35, 45)°`, interior point `(9, 0, 0)` mapped to
   `(5.2130516881, 7.3103562623, −0.6186949299)` — previously returned `False` and now returns
   `True`. Parametrised over five rotations including non-palindromic and single-axis cases.
2. **Validity gating.** `_status` returns `INCONCLUSIVE` whenever either trial is invalid,
   before any physical verdict. `valid` requires finite `qpos`/`qvel`/`xpos`, all seven warning
   counters at zero, and positive mass. Counters are enumerated by name from the installed
   `mjtWarning` enum, excluding the `mjNWARNING` sentinel; the previous four hand-indexed
   counters were mislabelled and omitted `BADQVEL`/`BADQACC`/`BADCTRL`.
3. **Real mesh negative.** `concave_mesh_diagnostic_xml` writes `<mesh file="u_channel.stl"
   scale="0.001 …">` and a `type="mesh"` collision geom over the original CAD STL, compiled
   from file. It is produced only by `hollow_run`; no CLI path reaches it, and production
   rejects mesh collision geoms.
4. **Through path.** The probe starts at x = −81 mm and must cross x = 66 mm with the centre
   within one probe radius of the cavity axis *at the crossing*, so a probe that leaves
   sideways or upward does not count. The earlier vertical drop remains available as
   `u_channel_spec(through_path=False)` and is not the pass criterion.
5. **Contact validity.** See §4.
6. **Surface metric.** `signed_distance_mm` reports negative depth inside a primitive, so a
   buried CAD surface registers. The critical samples were also moved onto the actual CAD
   surfaces; an over-thick wall that leaves the centre line clear now fails on deviation while
   the transit still passes.
7. **Overlay.** Cylinders honour `rot_deg`, capsules render real hemispherical ends, and an
   unsupported kind raises rather than drawing a misleading shape. The inspected PNG shows the
   translucent CAD, three distinct colliders and the transit tube through the open cavity.
8. **Report and table.** This file; trace header now `probe_x_mm, probe_y_mm, probe_z_mm`
   (the old header was both mislabelled and contained a table-breaking pipe).

---

## 6. Tests

46 tests in `tests/test_cadkit_physics_hollow.py`:

- geometry: the CAD really is a U-channel; no collider spans the cavity;
- probe occupancy: correct recipe passes with clearances tied to CAD dimensions (15 mm cavity
  half-width, 2 mm transit clearance, 0 mm coverage gap);
- negatives: spanning recipe rejected, oversized collider blocks, offset collider blocks,
  missing wall caught by coverage, spare-with-collider rejected;
- transforms: rotated channel passes, the mapped transit path lies inside the rotated body,
  probes are body-local not world;
- primitives: containment and distance for all four kinds, rotated-box frame;
- **supervisor regressions**: compound-rotation inverse (the exact repro), five rotations,
  invalid-numerics never PASS, warning enumeration complete, over-thick wall fails on surface
  deviation while the centre line stays clear, overlay rotation and capsule ends;
- dynamics: through-path passage, concave-mesh cavity sealing, no post-release `qpos`,
  determinism, artifact completeness, strict JSON;
- CLI: PASS path, missing-extra ERROR/3, malformed-contract rejection, fidelity in `report.json`;
- evidence integrity: a fresh run directory per run, reuse refused, MuJoCo version and `run_id`
  recorded in `summary.json`, swept transit start *and* end compared to the declared path.

---

## 7. Remaining limits (honest scope)

1. **Sampled, not exhaustive.** Coverage and probe checks sample the CAD surface and the
   declared paths. They are not a proof that no point anywhere is misrepresented.
2. **Primitives only.** `convex` colliders remain rejected; the mesh path exists only as a
   test diagnostic.
3. **Fixture contact model.** `solref="0.002 1"` is justified for a 12 mm probe at 1 ms. It is
   not evidence that 5.2 mm packet clearances converge; that needs its own convergence study
   in M5.
4. **No friction calibration.** The declared 0.4 is a fixture input, not a measured wrapper
   coefficient. No real-wrapper friction claim is made.
5. **Channel transit is not product presentation.** The probe leaves the channel and is
   expected to fall afterwards; nothing here supports a supported-pickup claim.
6. **Pocky not wired.** `Project.physics` is `None` for every project. Exit-recipe validation
   for the dispenser is deferred to M5a, not faked here.

---

## 8. Recommendation

Accept M2b and proceed to **M3** on Codex's decision. Carry forwards: keep the validity gate
ahead of any physical verdict; keep `convex` rejected; do not reuse this fixture's contact
model for packet-scale clearances without a convergence study.

No M3 work was started.
