# M2a report — generic CAD → physics scene adapter

Date: 2026-10-21. Packet: **M2a only**. M1 accepted via `dec_0mvi25xt3a48c43a5baf133a7`
(`run_0mvhxwg5l2aa1ba8e92d0c92f`). Contracts: `docs/mujoco-architecture-review.md` §2, §4–§7,
and the authoritative §21.

---

## 1. Gate result

**M2a gate: PASS.**

| Requirement | Result |
|---|---|
| Typed immutable scene/body/part/frame metadata | PASS — frozen dataclasses, explicit unit suffixes |
| CAD → body-local visual mesh, collisions disabled, SI once | PASS — `<mesh scale>` is the single conversion |
| Explicit primitive collision recipes; no silent hull | PASS — missing recipe is `SCENE_INVALID` |
| CAD-derived mass, COM and **full** inertia tensor | PASS — off-diagonal preserved via `fullinertia` |
| Parallel-axis aggregation for a multi-part rigid body | PASS — analytic check |
| Deterministic readable MJCF, compiled by installed MuJoCo | PASS — two exports byte-identical |
| Asymmetric translated/rotated assembly, not a Pocky substitute | PASS — `cadkit.physics.fixtures` |
| Lazy imports; existing CAD behaviour preserved | PASS — **325 passed**, exit 0 |
| `cad physics export` under the existing dispatcher | PASS |
| Unconfigured/no-physics model is an explicit error | PASS — ERROR/3 with a fix, never a false PASS |

No Pocky or armor CAD, params, plans or M0/M1 documents were modified apart from the M1
`websockets` attribution correction noted in §7.

---

## 2. Changed files

| File | State | SHA-256 |
|---|---|---|
| `cadkit/physics/schema.py` | new | `de131fe00fe9d221a202649654b345f0815332f3563c2dcb0b6afbc31471ebd8` |
| `cadkit/physics/inertia.py` | new | `edb794888b5e942dc6c83f751bb1e87af6990c9d0793b86d64493fc865b1ef54` |
| `cadkit/physics/scene.py` | new | `24bfb174b4b68f078d4c602fc51dee577f25d3bb620a814cbe79810aed62f985` |
| `cadkit/physics/fixtures.py` | new | `d30a6d7afc1c314c805eae8c675469553c9793dbf14f85d3909c70177d70ca30` |
| `cadkit/project.py` | modified (`physics` field) | `e3b5bec68791c23b10555ebfc0afe926cd09d61a35432f0014b69e2646a5e4ef` |
| `cadkit/cli.py` | modified (`export`, `fixture` verbs) | `2f8f3d0ddac21462c65b809f24ab6b8305111a5fd0681ae1fb31c46902761b90` |
| `tests/test_cadkit_physics_scene.py` | new | `5fe4a99b7ae5518fc4535f44ad124fbbe0e7bdae0621e0fabf09c4996f577e77` |
| `tests/test_cadkit_physics_export_cli.py` | new | `bec0cc935d6e08cefbcf24cf2b8fdcff61bc50cd040b9155a8699058e19f927a` |
| `docs/mujoco-m1-report.md` | corrected (§7) | — |

880 new lines across four modules. `ModelPart`, `export.py`, `checks.py` and every project are
untouched.

Generated under `out/fixtures/m2a_asymmetric/physics/`: `export/` (`scene.xml`, `report.json`,
3 STL assets) and `m2a-full-suite.txt`.

---

## 3. API and CLI

```python
from cadkit.physics.fixtures import fixture_assembly
from cadkit.physics.scene import export_scene, SceneInvalid

spec = fixture_assembly()                    # AssemblySpec, immutable
result = export_scene(spec, Path("out/x"))   # writes scene.xml + assets, compiles
result.scene_hash                            # stable identity
result.bodies[0].com_world_m                 # == MuJoCo data.xipos
result.report()                              # strict-JSON dict
```

```bash
cad physics fixture [--out DIR]                 # the built-in asymmetric assembly
cad physics export <project>/<model> [--out DIR]  # a project's scene, via Project.physics
```

`Project.physics` is `physics(model_name, params) -> AssemblySpec | None`, default `None`.
It takes the **model name** so one project's distinct models can never be silently assigned a
single assembly. No project opts in yet, by design (M5).

Exit codes: `0` PASS, `3` ERROR. Every error path prints
`{"status": "ERROR", "scenario": …, "detail": …}` on stdout plus an actionable line on stderr.

---

## 4. Coordinate contract, and the bugs it caught

`PartSpec.shape` is authored in **assembly** coordinates. `BodySpec.frame` places the body.
One mapping:

```
assembly_point = frame.pos_mm + R(frame.rot_deg) @ local_point
```

Meshes are written **body-local, in millimetres**, and converted by
`<mesh scale="0.001 0.001 0.001">`. Colliders and body poses convert with `mm_to_m`.

`Frame.rotation_matrix()` is taken from build123d's own `Location.Transformation()`, so the
convention cannot drift. Verified against `Pos*Rot` applied to a box at three poses, including
a compound `(12, 34, 56)°` rotation: agreement to 1e-9 mm, and `to_local` round-trips exactly.

Four conversion defects were found and fixed during this packet, each by comparing against an
independent value rather than against another call of the same code:

1. **Double-applied frame in `part_inertial`.** build123d already reports the COM and tensor in
   the shape's own (assembly) axes, so applying the body frame again moved any rotated part's
   COM. Caught by a hand-computed assembly COM.
2. **Missing mesh scale.** STL was written in mm and declared as metres, so visuals were 1000×
   too large. `build123d.scale()` was the wrong fix — it scales about the *centroid*, moving
   the part. `<mesh scale>` is a pure vertex multiply and is exact.
3. **World COM ignored rotation.** `com_m + frame.pos_mm` componentwise gave
   `(0.1524, 0.0508, 0)` against an independent `(0.0976, −0.0508, 0.02)` for a 90° body. Now
   `frame.apply(com_local)`, and it equals `data.xipos`.
4. **`inertial pos` converted twice.** `inertial.com_m` is already metres; passing it through
   `mm_to_m` again put the COM at the body origin and silently discarded an offset COM.

The last one is the reason the offset-COM test asserts **both** `data.xipos` (COM) and
`data.xpos` (frame origin) and requires them to differ by more than 10 mm.

---

## 5. Evidence

Fixture: two parts welded into one rigid body (`link_ab`: 40×10×6 mm arm + a 12×30×10 mm tab
rotated 25°), plus a separate free post. Body frame `(100, −50, 20) mm`, `90°` about Z.
Density 1.24 g/cm³.

| Quantity | Independent reference | Measured |
|---|---|---|
| `link_ab` mass | `Σ volume × 1.24 × 1e-6` = 0.00744 kg | 0.00744 kg |
| `link_ab` world COM | mass-weighted mean of the two transformed shapes = (0.0976, −0.0508, 0.02) m | identical |
| compiled `data.xipos` | same | identical |
| compiled `data.xpos` | frame origin (0.1, −0.05, 0.02) | identical, and ≠ COM |
| Two-cube parallel axis | `2·I_self` in x; `2(I_self + m d²)` in y,z | matches to 1e-9 |
| Visual vs collider world AABB | must coincide | coincide to 1e-6 m for all 3 parts |
| Visual geoms | `contype=0, conaffinity=0` | all 3 |
| Mesh scale | arm half-extents 0.02 × 0.005 × 0.003 m | matches |
| Body / freejoint / geom counts | 4 / 2 / 6 | matches |
| Determinism | two exports | identical `scene.xml`, identical asset hashes |
| Provenance artifact | `report.json` | scene hash, MuJoCo version, solver settings, asset hashes, per-body mass/COM/inertia |
| Off-diagonal inertia | `link_ab` product term 2.36e-7 kg·m² | emitted via `fullinertia`; MuJoCo's parsed principal moments match |
| Collider bitmasks | declared `contype`/`conaffinity` | compiled values equal the declared ones |

Commands, all exit 0:

```
.venv/bin/cad physics fixture                                  # PASS, scene ee7b5c744e23b2cb
.venv/bin/cad physics export armor/demo_cube                   # ERROR/3, "no physics assembly"
.venv/bin/cad physics export no/such_model                     # ERROR/3
pytest tests/test_cadkit_physics_*.py -q                       # 101 passed
pytest tests -q                                                # 325 passed in 350 s
```

Artifacts: `out/fixtures/m2a_asymmetric/physics/export/{scene.xml,report.json,assets/*.stl}`.
Scene identity `ee7b5c744e23b2cb66532aa5af0ce29d6f24b51aa428eae971084b984dfd0b3c`.
`report.json` is written with `allow_nan=False`, so a non-finite value fails at export rather
than producing invalid JSON.

Both bodies from `report.json`, matching the independent references above:

| Body | Mass (kg) | World COM (m) |
|---|---|---|
| `link_ab` | 0.00744 | (0.0976, −0.0508, 0.02) |
| `post_free` | 0.00190464 | (0.07, −0.01, 0.02) |

Negative cases: missing collider recipe → `SceneInvalid`; a spare part that declares colliders
→ `SceneInvalid` (its colliders would never be simulated); `convex` colliders → rejected until
the mesh-asset path exists; unsafe IDs (`../escape`, `.hidden`,
65 chars) → `ValueError`; zero/negative/NaN mass or density → `ValueError`; duplicate part or
body IDs → `ValueError`; `fixed_to_world` without a declared fixture → `ValueError`;
asymmetric, non-positive-definite, or triangle-violating inertia → `ValueError`;
MuJoCo unimportable → ERROR/3 with `uv sync --extra physics`; spare parts contribute neither
geometry nor mass.

A thin-shell tensor (`100 mm` box with a `99.6 mm` cavity) is explicitly **accepted** — its
inertia legitimately exceeds the uniform-solid `m b²/12` bound, so that bound is not used as a
rejection criterion.

---

## 6. Tests added

49 new tests in two flat modules (101 physics tests total).

- `test_cadkit_physics_scene.py` (40): frame agreement with build123d, canonical mass, offset
  COM end-to-end, measured-mass override rescaling, parallel-axis aggregation, visual/collider
  world-AABB coincidence for every part, visual geoms non-colliding, mesh scale once, body and
  freejoint counts, two-export determinism, hash sensitivity to geometry, off-diagonal inertia
  reaching `fullinertia`, declared collider bitmasks, body euler convention under a general
  rotation, platform-independent scene hash, and the negative matrix.
- `test_cadkit_physics_export_cli.py` (9): `Project.physics` default and signature, unconfigured
  project is ERROR not success, unknown model, fixture export contents, export determinism,
  missing-extra path, and `cad check` still working with MuJoCo blocked.

Mutation checks confirmed the tests are load-bearing: removing the post collider offset fails
the AABB test; disabling the `fullinertia` branch fails the inertia test; flattening collider
bitmasks to zero fails the bitmask test.

---

## 7. Corrections to the M1 report

The M1 report claimed the `websockets 17.2 → 17.3` change was a lockfile change forced by
MuJoCo's floor. The supervisor disproved this and the M1 report is now corrected:

- the lock **already** selected 17.3 before the physics extra;
- MuJoCo 3.16.0 declares `websockets>=13`, not `>=16`;
- the observed change was reconciliation of a stale *installed* 17.2 to the already-locked
  17.3.

No project dependency version changed in M1.

---

## 8. Remaining risks

1. **Collision fidelity is unproven.** M2a proves that a declared primitive lands where its CAD
   part is. It proves nothing about whether the primitives *represent* the part — that is M2b
   (hollow U-channel, aperture passage, transit). A box recipe over a hollow shell would pass
   every M2a test and be physically wrong.
2. **No joints, actuators or scenarios.** Every body is either free or fixed. `data.xipos`
   correctness is asserted for free bodies only.
3. **`world_frame`** is an empty named body kept for future attachment points; it adds one to
   `nbody` and is otherwise inert. If M2b needs a cleaner body count, remove it.
4. **`convex` colliders are rejected, not implemented.** The type exists and validation refuses
   it with an actionable message, because emitting `type="mesh"` without an asset makes MuJoCo
   reject the whole scene. M2b must add the asset path *and* a convexity proof before this is
   re-enabled.
5. **Pocky is not wired.** `Project.physics` is `None` everywhere, so `cad physics export
   pocky/prototype` correctly reports "no physics assembly". Opting in is M5 work, and the
   M0 support finding (retention-only clips, no downward load path) is still unaddressed.

---

## 8a. Independent review

One bounded reviewer pass (`M2aReview`, read-only, 25+ mutation experiments). Six findings, all
valid, all fixed:

1. **`convex` colliders always failed compilation** — the schema accepted them but the emitter
   produced `type="mesh"` with no asset. Now rejected at validation with an actionable message.
2. **Spare-part colliders were silently discarded** — an explicitly declared collider vanished
   and the export still reported PASS. Now `SceneInvalid`.
3. **Off-diagonal inertia was unasserted** — disabling `fullinertia` passed every test. Now
   asserted in the XML *and* against MuJoCo's parsed principal moments.
4. **Collider bitmasks were unasserted** — flattening them to zero made every collider inert
   while still exporting PASS. Now compiled values are compared to the declared ones.
5. **`scene_hash` included `platform.platform()`**, so identical scenes hashed differently
   across machines. Removed; the hash now covers only the XML, assets and spec.
6. **No non-palindromic body rotation** — the only fixture rotation was `(0,0,90)`, invariant
   under Euler-order reversal. Added a `(30,12,55)°` test comparing the emitted euler against
   `Frame.rotation_matrix()`.

Also closed on review feedback: `report.json` is now written (it had no caller), and ids
containing `__` are rejected so `(body "a__b", part "c")` cannot alias `(body "a", part "b__c")`.

## 9. Recommendation

Accept M2a and proceed to **M2b** (hollow-geometry and collider-fidelity validation). Carry
forwards:

1. Keep the `<mesh scale>` + `mm_to_m` split exactly as is; a second conversion anywhere will
   reintroduce the visual/collider misalignment this packet fixed four times.
2. `convex` colliders stay rejected until M2b supplies both the mesh-asset path and a real
   convexity proof. Do not re-enable the type by merely emitting a mesh reference.
3. M2b must not treat compilation as fidelity. The U-channel negative and the aperture transit
   test are the actual gate.

No M2b work was started. Codex owns acceptance.
