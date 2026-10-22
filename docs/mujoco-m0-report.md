# M0 report — MuJoCo physics layer: inventory, design review, gate

Date: 2026-10-21 (America/Los_Angeles). Packet: **M0 only** — no feature implementation, no
dependency installed, no parameter or source change.
Companion document: `docs/mujoco-architecture-review.md` (the architecture deliverable).
Authoritative plan: `plan-mujoco.md`. Orchestration: `docs/mujoco-orchestration.md`.

---

## 1. Gate result

**M0 gate: PASS — architecture readiness only.**

Justification: every M0 task in `plan-mujoco.md` §M0 and every deliverable named in the
dispatch is produced with evidence; the integration map is exact and verified against the
checkout; the concavity, unit and frame strategies are specified with named APIs; and the
plan's guessed paths/commands are corrected rather than copied.

**Separately: unverified physical behaviour.** No simulation ran (MuJoCo is not installed,
by M0 scope). **No physical trial is claimed and print status is unverified** (F9). The
user's structural observation — the body resting on two chassis posts — is confirmed as a
*CAD design finding* from the solids, not as a simulated or measured outcome. The M0 gate says
nothing about whether the dispenser works.

Five items are recorded for Codex (§7). Two block M1 as written — the package-index policy
and the freezing of the protrusion threshold. The other three (the S0 predicate set, the scope
of a bounded support redesign, and whether a measured clip force gates the S0 verdict) are
design questions for later packets and do not block the architecture.

---

## 2. Commands run (all recorded; nothing installed, nothing edited)

Environment and inventory:

```
uv --version                     → error: command not found: uv      (PATH lacks ~/.local/bin)
~/.local/bin/uv --version        → uv 0.13.0 (4ecd0eff2 2026-10-09 aarch64-apple-darwin)
python3 --version                → Python 3.9.6                      (system python, not the venv)
.venv/bin/python -V              → Python 3.12.15
uname -m; sw_vers -productVersion → arm64; 27.0.1
git status                       → fatal: not a git repository
.venv/bin/python -c "import mujoco" → ModuleNotFoundError: No module named 'mujoco'
```

Package inventory (measured, no installs):

```
build123d 0.13.0   trimesh 5.1.1   numpy 2.5.4   manifold3d 3.5.4
pyvista 0.49.1     rtree 1.4.1     shapely 2.2.0 pytest 9.1.1
ocp_vscode 4.2.0   cadstudio 0.1.0
```

Reachability, with no configuration change:

```
curl https://pypi.org/simple/mujoco/          → 200
curl https://pypi.apple.com/simple/           → curl: (6) Could not resolve host
~/.local/bin/uv run cad list                  → exit 2, "Failed to fetch: https://pypi.apple.com/simple/hatchling/"
UV_NO_SYNC=1 ~/.local/bin/uv run cad list     → exit 0, 8 models listed
UV_NO_SYNC=1 .venv/bin/cad list               → exit 0, same 8 models
```

Baseline tests (full artifact: `out/pocky/prototype/physics/m0-20261021/pytest-baseline.txt`,
1580 lines, with summary and exit code):

```
UV_NO_SYNC=1 .venv/bin/python -m pytest tests -q
  → 8 failed, 216 passed in 287.21 s   (exit 1)
  → all 8 failures: FileNotFoundError: [Errno 2] No such file or directory: 'uv'
     (tests/test_cadkit_export_cli.py ×6, tests/test_pocky_geometry.py ×2)

PATH="$HOME/.local/bin:$PATH" UV_NO_SYNC=1 .venv/bin/python -m pytest \
  tests/test_pocky_params.py tests/test_pocky_prototype.py tests/test_pocky_linkage.py \
  tests/test_pocky_geometry.py tests/test_cadkit_export_cli.py -q
  → 53 passed in 20.57 s   (exit 0)
  (artifact: out/pocky/prototype/physics/m0-20261021/pytest-targeted.txt)
```

Conclusion: **no pre-existing model or check failure.** The 8 failures are purely
environmental and were *tested as such*: the tests shell out to bare `uv`, and the harness
`PATH` lacks `~/.local/bin`. With `PATH` set they pass. Recorded, not fixed. This makes the M1
prerequisite **"fix PATH *and* the index"**, not "fix the index" alone.

Targeted Pocky tests (fast, model-only):

```
UV_NO_SYNC=1 .venv/bin/python -m pytest tests/test_pocky_params.py tests/test_pocky_prototype.py -q
  → 18 passed in 1.28 s
```

Geometry/evidence probes (read-only; all preserved in
`out/pocky/prototype/physics/m0-20261021/scripts/`):

```
.venv/bin/python out/pocky/prototype/physics/m0-20261021/scripts/m0_verify.py
.venv/bin/python out/pocky/prototype/physics/m0-20261021/scripts/m0_support_chain.py
.venv/bin/python out/pocky/prototype/physics/m0-20261021/scripts/m0_fork.py
… plus the 23 further probes listed in §6
```

Snapshot integrity (no source change in this packet):

```
manifest entries: 69; missing: []; changed: []
plan-mujoco.md sha256: 4f69292c97bd03aab221f3c36b5569f8cbe546896b11907ac484555836092f76
snapshot source.tar.gz sha256: 7ab3cc26e5f8466bd5b7d1bba849ccbf9075d8a017cc96bffc8bc2e9c879ea8f
```

---

## 3. Findings

### F1. Environment is Python 3.12.15 + build123d 0.13.0 on arm64 macOS; MuJoCo absent

`mujoco 3.16.0` publishes `mujoco-3.16.0-cp312-cp312-macosx_11_0_arm64.whl`, matching this
interpreter and platform exactly (`https://pypi.org/pypi/mujoco/json`; `requires-python
>=3.10`; Apache-2.0). There is no macOS x86_64 wheel in 3.16.0.

### F2. The blocker is the package index, not the package

`pyproject.toml` sets `https://pypi.apple.com/simple` as the default index; that host does not
resolve here while `pypi.org` returns 200. `uv run …` therefore fails while rebuilding the
project (`hatchling`), which is why `UV_NO_SYNC=1` is the working invocation and is documented
in `report-current-progress.md`. Any M1 install must resolve this first (review §11, §20 Q1).

### F3. The body has no designed downward load path; the clips are retention-only

Measured from the current `projects/pocky/geometry/prototype.py`:

| Quantity | Value | Script |
|---|---|---|
| Designed body→chassis connections | 2 clips (`_chassis_hook:631`, calls at `:608–609`) | code read |
| Clip tooth underside vs body rib top | **+0.05 mm vs 0.00 mm — the tooth is *above* the rib** | direct probe |
| Bearing direction | **+Z lift only**; a downward load separates rib from tooth | direct probe |
| Body floor underside → highest chassis surface under it | −2.4 → **−11.6** (guides/boss), a **9.2 mm void**; base plate at −15.6 | direct probe |
| First surface under the body | pusher carriage top at −2.8, **0.4 mm below the floor** | `m0_verify.py` |
| Measured body↔pusher minimum at rest | 0.027 mm at (−89.43, 9.07, 0) | `m0_pairs2.py` |
| Mechanism gaps below that | carriage→crank 0.4 mm, crank→boss 0.4 mm, peg head 0.2 mm above carriage | `linkage.py:131–138` |
| Clip bearing patches (if they bore) | 2 × (6 mm × 1 mm), collinear, **121.5 mm apart** | `m0_verify.py` |
| Hull of those patches | 520 mm², **4.23 mm wide** perpendicular (2A/P = 4.05) | `m0_hull.py` |
| Hanging group COM vs that strip | **outside by 4.54 mm** (body alone 6.86 mm) | `m0_verify.py` |
| X play on the teeth | 6 mm tooth over a 14 mm rib → **±4 mm free slide** | direct probe |
| Y play | post inner 35.3 vs rib outer 35.0 → 0.3 mm | code read |
| First incidental arrest, rotating about the clip line | **0.4°** onto the pusher carriage (0.42 mm sag) | `m0_verify.py` |
| With the mechanism ignored | 8.4° onto the chassis base plate | `m0_verify.py` |
| Arrest across the stroke | 0.4° (rest) → 0.3° (half) → 0.2° (full, onto the peg head) | `m0_stroke.py` |

**Determination: a missing downward load path, not merely weak support.** The designed
connection is retention-only; under gravity the body falls ~0.4 mm onto a translating
mechanism part, and the only further stops are a chain of designed gaps through two peg
joints. The resting state is not statically determinate. This matches the *structural half* of
the user's observation ("resting on only two posts"). It is **not** a simulated result and
does not establish friction, print tolerance, clip preload, or any physical failure.

Note on precision: the earlier draft of this packet called the chain "1.2 mm of vertical
slack". Only the first 0.4 mm (floor onto carriage) is in the body's own downward path; the
next two open only if the carriage is pushed down. Correct statement: **0.4 mm to first
contact, plus up to 0.8 mm of further cascade**, and the settle will therefore exceed 0.4° of
rotation because the mechanism drops before it can hold anything.

**Collider artifact to guard against.** The chassis bbox tops at z 2.45 (the tooth tops)
against a real base top of −15.6. A convex-hull chassis collider would present 4.85 mm of
phantom material under the body and manufacture a "rests on two posts" result. The baseline
scene must show zero body↔chassis contact and reproduce the free-fall-onto-pusher outcome; any
scenario where the body looks supported by chassis geometry at the nominal pose is a collider
bug (review §7.2, §8.4).

The architecture response: `S0 assembly_stability` is a prerequisite scenario sweeping button
fractions {0, 0.25, 0.5, 0.75, 1.0}, the baseline fixes nothing to the world, and
`body_contact_with_moving_part == none` is a required predicate (review §8.4).

### F4. Presentation support at 40 mm is geometrically sound, dynamically unproven

The 40 mm target is measured **past the outer face** (`link.outer_x = 88.0`,
`linkage.py:129`), matching `plan-first-prototype.md:34` and `Pose.protrusion`
(`linkage.py:206`), not past the bore front (85.0). So the packet spans **x −37…128**, 22 mm
past the 18 mm lip shelf (ends at x = 106), consistent with `mechanism-proposal.md`.

86.1 % of the underside has body floor or lip shelf within 3 mm; the support hull spans
x −36.0…104.3 (7 436 mm²) and the packet COM at x = 45.5 is inside it. **Forward** margin to
the lip-shelf end is **60.5 mm**; rear margin 81.5 mm. The 26.5 mm figure is the **lateral**
margin to the ±26.5 mm y edge and must not be quoted as a tipping margin.

The load path is packet → lip shelf → lip feet on two 0.4 mm shims → body ledges → the
retention-only clips — i.e. it inherits F3. The 40 mm figure is a documented provisional
target, not a user measurement.

### F5. Concavity is decisive and the plan's warning is correct

The bore (x −85…85), the exit (x 85…88, z 0…9.20), the 5.75 mm separator gap, the 4.4 mm back
notch and the floor slot (x −93.1…−35.1, y ±3.5) are all destroyed by a convex hull. Official
statement: "Meshes specified by the user can be non-convex, and are rendered as such. For
collision purposes however they are replaced with their convex hulls"
(<https://mujoco.readthedocs.io/en/stable/computation/index.html#collision>). Manual recipes
per part are in review §7.2, with three independent aperture checks (§7.3).

### F6. Units and inertia are the two silent-error risks

MuJoCo "does not specify basic physical units" (<https://mujoco.readthedocs.io/en/stable/overview.html>),
so one explicit conversion boundary is mandatory (review §5). `build123d` inertia is
`matrix_of_inertia` in **mm⁵ about the COM** — established empirically, not assumed: a
20 × 40 × 25 box returns `3.708333e6 / 1.708333e6 / 3.333333e6`, exactly
`m(b²+c²)/12` with `m = volume`. Conversion is `I_kg_m2 = I_mm5 · ρ_kg_m3 · 1e-15`.

Also verified: `Shape.center` does **not** exist on the base class (`AttributeError`);
`center(CenterOf.MASS)` is on `Solid`/`Compound`. `ModelPart.shape` is typed `object`
(`cadkit/model.py:21`), so the physics layer must reject non-solids with a clear message.

### F7. The plan's paths and commands are wrong in five places

`cadstudio physics` → real entry point is `cad`; `tests/physics/`, `tests/projects/` → real
convention is flat `tests/`; `projects/pocky/geometry/` "physical solids" → the model is
`models/prototype.py` + `geometry/prototype.py`; `docs/physics-calibration.md` does not exist;
"current checkout not available" → it is. Corrected in review §19.1.

### F8. Deprecated/version-sensitive APIs confirmed against current docs

| Claim | Verdict | Evidence |
|---|---|---|
| `MjModel.from_xml_path` + `MjData` is the load path | SUPPORTED | python.html |
| `assets=` dict | **DEPRECATED** → `MjVfs` | python.html (the same page's minimal example still shows the old form) |
| `MjSpec` | stable since 3.2.5 | changelog |
| `mj_step(model, data)` headless | SUPPORTED | python.html / computation |
| `launch_passive` on macOS needs `mjpython` | SUPPORTED | python.html |
| mesh geoms collide as convex hulls | SUPPORTED | computation |
| `timestep` default 0.002 s, `integrator` Euler, `cone` pyramidal, `solver` Newton, `iterations` 100 | defaults to state explicitly | XMLreference |

### F9. Print status is UNVERIFIED; the user's sentence is a simulation prediction

Three claims, kept separate:

1. `report-current-progress.md:5,82` and `projects/pocky/docs/assembly.md:3` (2026-10-18/19)
   say nothing was printed.
2. `plan-mujoco.md:6` says "parts printed, but gravity-dependent physical operation failed".
   **No log, artifact or measurement backs this**, and it is not adopted.
3. The user's 2026-10-21 wording is "the body model isn't stable and would immediately fall
   down **in a physics simulation**, it's resting on only two posts from the chasis" — a
   prediction about a simulation plus a structural observation, **not** a reported print trial.

The only repository artifact suggesting print preparation is `out/pocky/prototype/plate.3mf`
(PrusaSlicer metadata, 2026-10-19 00:39): a plate was **sliced**. There is no
`projects/pocky/docs/prototype-log.md` and no bench record. Accurate statement: **a plate was
sliced; a print is unverified; no bench record exists.**

The structural half of the user's observation is verified independently from the solids in F3;
nothing here asserts that a print exists or that a physical failure occurred. The files are
not edited. Full table: review §19.2.

### F10. Stage gates reconciled without weakening

Stage 1 = `plan-first-prototype.md` nine criteria + 10-cycle run, PETG only. Stage 2 =
`plan-pockey-dispenser.md:220–221` 50 cycles at 10 packets and 100 at 25, after a metal
spring. Precedence is claimed by `plan-first-prototype.md:11` and restated by
`report-current-progress.md:3`. Simulation satisfies neither. Review §19.3.

---

## 4. Baseline validation performed

- **Static model build:** `prototype_solids(p)` succeeds, 15 parts, 1.18 s; tessellation 1.49 s,
  17 248 triangles. All parts are valid single solids with zero interference on the pairs
  checked (`m0_overlap.py`: body/chassis, body/pusher, body/rod, body/crank, chassis/crank,
  chassis/rod, body/lip, lip/shim, spring/rod, spring/chassis — all 0.0000 mm³).
- **Existing checks:** `out/pocky/prototype/report.md` (2026-10-18 22:56) reads
  `69 pass, 0 fail, 6 warn, 15 info`. Not regenerated in M0; it is the pre-existing record.
- **Tests:** 216 passed / 8 environmental failures without `uv` on `PATH`; 53 passed with
  `PATH` fixed, including the 8 that had failed (§2). No model or check failure exists.
- **Assembly source trap confirmed:** `build()` output has the free spring 3 mm inside its
  seat — measured overlap **210.0 mm³** vs **0.0 mm³** using `compressed_length(0.0)`. It also
  ships a parked `dummy` (y 77.5…132.5) and spare `shim_08` (x 112…124). So the physics
  adapter must use an explicit assembly source, not `build()` enumeration (review §8.2).
- **Snapshot:** 69 manifest entries, zero changed, zero missing.
- **No simulation was run.** No MuJoCo import, no MJCF compiled, no physical trial.

---

## 5. Remaining measurements (nothing here is inferred)

These are the inputs that would turn any of the above into a physical claim. None exists in
the repository; all are `assumed`/`template` in the proposed schema.

| # | Quantity | Unit | Why it gates a result |
|---|---|---|---|
| 1 | Packet mass | g | every force/energy/settle metric |
| 2 | Wrapper↔PETG static/dynamic friction | — | decides whether gravity feed works at all |
| 3 | Printed spring rate | N/mm | return success, button force |
| 4 | Clip retention force (pull-off, +Z) | N | whether the clips hold at all (F3) |
| 4b | Body↔carriage static friction | — | how much the incidental stop resists the settle |
| 5 | Wrapper↔wrapper friction | — | double-feed discrimination at 5.75 mm |
| 6 | Packet thickness (centre + both seals) | mm | stack height, separator margin |
| 7 | Print tolerance at peg/slot features | mm | body motion play |
| 8 | Manual press force and duration | N, s | actuator bound |
| 9 | Lip shelf deflection under a packet | mm | presentation support |
| 10 | Wrapper surface (fin, seal) | mm | contact geometry |

Template and provenance rules: review §17.

---

## 6. Evidence artifacts (paths, sizes, hashes)

Directory: `out/pocky/prototype/physics/m0-20261021/` (generated output; `out/` is gitignored).

| File | Purpose | SHA-256 (prefix) |
|---|---|---|
| `evidence.json` | consolidated numbers: masses, clip bearing direction + void depths, support polygon + strip width, COM, tipping, reactions, pusher support, presentation support (outer-face datum, forward/lateral margins), apertures, interference | `891a340e…` |
| `support_chain.txt` | the support-chain statics quoted in F3, including the retention-only clip statement | `c16658ab…` |
| `fork.txt` | where the pusher sits relative to the body floor across the stroke: the neck passes up through the floor slot and the bullnose runs above the floor inside the bore, by design | `4f8d261a…` |
| `pytest-baseline.txt` | full-suite baseline (1580 lines, summary + exit code) including the 8 `uv`-not-found failures | `64b34623…` |
| `pytest-targeted.txt` | the same tests with `PATH` fixed: 53 passed | `2ccdeccb…` |
| `scripts/m0_verify.py` | regenerates `evidence.json` (outer-face datum, clip direction, strip width) | `8c73f295…` |
| `scripts/m0_support_chain.py` | regenerates `support_chain.txt` | `b7ae856e…` |
| `scripts/m0_fork.py` | regenerates `fork.txt` | `f56c8b83…` |
| `scripts/m0_{clear,conn,drop,hooks,hull,overlap,pairs,pairs2,poly,present,probe,pusher,react,rock,stab,stroke,support,support2,tip,tip2,tip3,tip4,tipdir}.py` | the individual probes behind each number | see directory |

Every script is read-only, imports the project's own modules, and writes nothing.

---

## 7. Issues requiring Codex design resolution

1. **Package index.** Add a fallback `pypi.org` index to `pyproject.toml`, or require
   `UV_INDEX_URL` at sync time? The first is reproducible from the manifest; the second leaves
   the lockfile un-regenerable from `pyproject.toml` alone. M1 cannot install without a
   decision.
2. **Protrusion threshold.** Freeze `protrusion_mm ≥ 30` (informational, with 40 as the
   documented target), or defer? The user specified protrusion without a distance.
3. **S0 required predicates.** Is `resting_on_mechanism == false` acceptable as *required*, or
   should the gate be `support_com_margin_mm > 0` plus a settle test only?
4. **Support redesign scope.** F3 shows there is no downward bearing seat; a candidate will
   need a real body–chassis support surface, which is a geometry change, not a parameter, and
   "add a third clip in Z" does not address it. Does that stay inside M6's bounded-candidate
   scope with unchanged evaluation rules, or does it need its own review gate?
5. **Clip force before S0 upgrade.** Should a measured clip pull-off force be required before
   an S0 verdict can move from `INCONCLUSIVE` to PASS/FAIL, given that friction and preload
   decide whether the physical body really falls?

---

## 8. Changed files

Created by this packet (nothing else in the workspace was modified):

| File | SHA-256 |
|---|---|
| `docs/mujoco-architecture-review.md` | `f1566e0fda113bbe252b349708eb02b06d28ef5ec5b7f9234a39d615d9f0960d` (current; also repeated in the packet completion message) |
| `docs/mujoco-m0-report.md` | see the packet completion message; a file cannot contain its own final hash |
| `out/pocky/prototype/physics/m0-20261021/**` | §6 |

Verified unchanged: all 69 files of the source snapshot
(`~/.omp-bridge/backups/cadstudio-mujoco-20261021T095832Z/manifest.json` — 0 missing,
0 changed), including `plan-mujoco.md`, `pyproject.toml`, `uv.lock`, `projects/pocky/**`,
`cadkit/**`, `tests/**`. `docs/mujoco-orchestration.md` is not in the 69-file snapshot (it was
written after the snapshot was taken) and was amended by the orchestrator during M0, not by
this packet; its current hash is `3bfdcf23534095f5297e8088ccd0421e2d294a35fa946900cd4f16637eb54d76`.

---

## 9. Recommendation

Proceed to **M1** on Codex acceptance, with three conditions carried forward:

1. Resolve **both** install blockers before any install (§7.1): `uv` is not on `PATH`
   (measured: 8 tests fail for that reason alone) and the default index does not resolve.
   M1's gate must also include "`cad build/render/check/list` work with `mujoco` absent".
2. Keep `S0 assembly_stability` as a prerequisite in M3 and M5a, and keep the baseline
   assembly unfixed. The `diagnostic` fixture stays labelled and returns `INCONCLUSIVE` for
   required predicates.
3. Do not let any later packet treat the F3 finding as solved by a model change, and do not
   let it be "fixed" by adding only a third clip in Z: the finding is that there is **no
   downward bearing seat at all** and that the load resolves into a moving part. Any fix is a
   design change that needs review before it is simulated, and the evaluator must be unchanged.

Do not proceed to M1 on the strength of this report alone; Codex owns acceptance.
