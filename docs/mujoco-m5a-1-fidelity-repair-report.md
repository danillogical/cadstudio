# M5a-1 adapter/static fidelity repair — dense void grids

> **SUPERSEDED IN PART — see `docs/mujoco-m5a-1-fidelity-followup-report.md`.**
> Independent review (`docs/mujoco-m5a-1-fidelity-repair-supervisor-review.md`) rejected this
> attempt: the `rod_channel_grid` was a single 1-D line, the density tests only checked
> per-axis coordinate sets (so an interior hole passed), the claim that excluding other
> installed parts is "stricter, not weaker" was **false**, and the after-manifest was stale.
> All four findings are corrected in the followup operation, whose final state was approved by
> the configured ordinary reviewer in round 5 and passed by an independent test worker
> (`docs/mujoco-m5a-1-fidelity-followup-report.md`). One of them is corrected *beyond* what this
> report claimed: the swept rod corridor was still under-covering after this attempt, missing
> 3.8391 mm3 of the true swept CAD volume, and that is fixed there too. The parts of this report
> that remain true are the two original bore/exit blocker negatives (retained and re-verified),
> the dense grids for the other eleven regions, and the unchanged collider geometry, scene
> hash, static preflight and compiled audits. The verdict recorded below is **historical and
> was not accepted**; it is preserved rather than rewritten.

**Status (historical):** bounded R1 correction implemented and evidenced for independent
Codex review. This is **not** M5a-1 acceptance, not S0, not packet readiness, not M6/M7 and
not a physical claim. The original adapter/static evidence is preserved; repair artifacts
live under `out/mujoco-m5a/adapter-static/fidelity-repair/`.

## Authorization and actual execution

| Item | Value |
|---|---|
| Supervisor review | `docs/mujoco-m5a-1-adapter-static-supervisor-review.md` |
| Review decision | `REMEDIATE dec_0mvjdq99k6ffb0bc8c7fe5fa6` (prior completed operation `op_0mvjabe8s901d98bf04f78aa6`) |
| Supervision run | `run_0mvj62atk8b61da9fe2edf2ea` (successor5), limits 6 operations / 2 remediation cycles, deadline `1792679704903`, unchanged |
| Bridge usage | before admission 3 operations / 2 remediations used, cumulative 25 submitted / 11 remediation cycles; this admission makes 26 submitted and spends the last cycle; **0 cycles remain** |
| Handoff / session | `ho_0mvjdqacdc1a33db1ba75c57c`; session `01a16316-9fb7-764b-8352-ada5f3e548e2`, generation 3, empty-context start |
| Request | `cadstudio-m5a1-fidelity-repair-01a1624d-1` |
| Executing model | `opencode-go/deepseek-v4.1-flash` (configured default; no override) |
| Native plan mode | not available through the managed `omp-bridge` interface and **not used**; this implements the already approved `docs/mujoco-m5a-plan.md` §3.5/§6.1 |
| Model / provider / effort / role / fallback changes | none; no substitute or override used |

## Defect accepted from R1

The previous increment declared sparse probe lists: body `floor_slot` 4, `back_notch` 3,
`peg_relief` 3, `bore` 4, `exit` 2 points. The Supervisor appended two 6 mm boxes
(`bore_block` at body-local `(30, 0, 20)`, `exit_block` at `(86.5, -20, 5)`); each had exactly
**0 mm³** exact-CAD overlap with the body yet `validate_fidelity` returned
`ok=true, violations=[]`, because coverage-of-material cannot detect invented material.
Raw observation: `out/mujoco-m5a-supervisor-adapter/void-coverage-probe.json`.

## Implementation (project `colliders.py` only)

Deterministic half-offset grids are generated from CAD-derived extents and filtered against
the exact fraction-0 installed solids before they become `ProbeSpec`s:

* `_installed_cad(p, link)` — cached exact `static_solids` + `moving_solids` at fraction 0
  (bench `dummy` and parked `shim_08` excluded), grouped exactly as the `BodySpec` parts.
* `_grid(lo, hi, step)` — `ceil((hi-lo)/step)` equal cells, one point at each cell centre; the
  pitch is therefore **<= step** and no point lies on a region boundary.
* `_void_grid(points, own, others)` — own-group points use exact `is_inside` (default 1e-6)
  so a legitimate void-face probe is kept; points of every **other installed part** must clear
  it by **0.15 mm** (`is_inside(point, 0.1499)` behind an expanded AABB prefilter). This
  rejects near-tangent points that a 0.15 mm probe sphere would intersect while preserving
  exact tangency (the rod/guide 0.15 mm lane). Welded pegs and shims are part of their
  carrier group and can never contain a grid point.
* `_dense_probe` rejects a grid at build time if it is too sparse (`minimum` per region), so
  an accidentally occupied region fails the build instead of silently declaring a void.
* No collider geometry, tolerance, CAD, params, assembly, restraint or criteria was changed.
  The compiled scene hash is unchanged (`2c4bd425…26e2f`); only the declared probes grew.

Seed probes and transits are retained. Three seed points were moved because they sat in
installed material at fraction 0 (not because any criterion was relaxed): the body
`floor_slot` west seed moved from `x=-90` (inside the resting pusher neck) to
`sx0+1.1 = -92.0`; the two crank `button_slot` seeds inside the installed button peg moved to
free slot points. The crank `pivot_bore` remains the declared parent-filtered exception: it is
true crank-CAD void, the welded pivot peg legitimately fills the assembled bore, and it is
neither a critical surface nor a new dense grid.

## Dense coverage actually declared

| Body | Probe | Region (CAD-derived) | Pitch mm | Points |
|---|---|---|---:|---:|
| body | `bore_grid` | magazine tube `x ±85, y ±30, z 0…72` | 5 | 6108 |
| body | `exit_grid` | `x 85…88`, both lateral sides `y ±30`, below the 2.6 mm chamfer | 1.5 / 5 / 2 | 72 |
| body | `floor_slot_grid` | through-slot `x -93.1…-35.1, y ±3.5, z -2.4…0` | 5 / 1.75 / 1.2 | 88 |
| body | `peg_relief_grid` | local f=1 relief circle R3.9 at `(-53.0, 35.30)` | 1.5 / 1.5 / 1.2 | 48 |
| body | `back_notch_grid` | bullnose notch `x -87.6…-84.95, y ±20.2, z -0.02…4.4` | 1.3 / 5 / 1.1 | 107 |
| lip | `separator_gap_grid` | `x 80.5…91, y ±29.7, z 0…5.75` | 5 / 5 / 2.5 | 108 |
| chassis | `spring_pocket_grid` | B-insert pocket `x -39.2…-30.4, y -81.5…-66.5, z -16.8…-2.5` | 2 / 3 / 3 | 105 |
| chassis | `head_relief_ring` | 0.4 mm annulus at r 4.2, z -17.0 | 16 stations | 16 |
| chassis | `rod_channel_grid` | guide span at `y -28, z -16.0` (0.4 mm below the rod) | 5 | 43 |
| crank | `button_slot_grid` | radial slot r 19…24.094, width ±2.3, in the crank frame | 1 / 1 / 2 | 20 |
| rod | `guide_gap_grid` | both 0.15 mm clearance lanes, guide span, `z -13.6` | 5 | 84 |
| pusher | `y_slot_grid` | Y slot stadium width ±2.3, `z -6.3…-3.3` | 1 / 1.5 / 2 | 32 |
| pusher | `return_chamfer_grid` | 30° return wedge below the exact CAD line | 0.6 / 1.5 / 0.5 | 12 |

13 grids, **6843** points, plus the 48 retained boundary seeds and 9 unchanged transits.
Filter evidence: `void_coverage_probe.json` records **0** grid points inside any installed
solid and **0** inside a welded peg or shim.

## Blocker negatives (the R1 failure, re-tested)

Each 6 mm box is in real CAD void (exact body intersection **0.0 mm³**) and each is appended
alone to the body's collider tuple with CAD and every other input unchanged:

| Negative | Centre mm | CAD overlap mm³ | Contract | Violation |
|---|---|---:|---|---|
| `bore_block` | `(30, 0, 20)` | 0.0 | rejected | `probe 'bore_grid' … declared void is filled` at `(27.5, -2.5, 21.6)` |
| `exit_block` | `(86.5, -20, 5)` | 0.0 | rejected | `probe 'exit_grid' … declared void is filled` at `(85.75, -22.5, 2.475)` |

## Fresh evidence (`out/mujoco-m5a/adapter-static/fidelity-repair/`)

| Check | Result |
|---|---|
| `cad physics export pocky/prototype` (real CLI) | **PASS**; scene hash `2c4bd425c55d9f56c39904e6ae01683836650fc84dabaa6ff645eb1077926e2f`, 9 bodies, 202 geoms, MuJoCo 3.16.0 |
| Export fidelity contracts | body/lip/chassis/crank/rod/pusher all **ok**; coverage worst 0.2 / 0.0 / 0.325 / 0.083 / 0.0 / 0.071 mm (limit 0.5); critical deviation <= 3.2e-15 mm (limit 0.02) |
| `compiled/reset_audit.json` | **PASS** at all five fractions |
| `compiled/negative_resets.json` | linear quarter-stroke and sign-flip **both rejected** |
| `compiled/clearance_audit.json` | **PASS**, critical tolerance 0.02 mm at all five fractions |
| `compiled/validity.json` | **SCENE_VALID**, zero exact overlap, no collider penetrations |
| `void_coverage_probe.json` | 13 grids / 6843 points, 0 material points, 0 welded-peg points, both blockers rejected |
| `manifest/` | accepted-snapshot comparison and pre-repair adapter/static comparison, both truthful |

The no-actuation smoke is unchanged (same colliders and scene). Its f=1 0.7909 mm numerical
peak remains a residual risk for a later separately admitted S0 batch, not a physical FAIL and
not repaired here.

## Independent tests

Authored by a worker separate from the implementer:
`tests/test_pocky_physics_void_coverage.py` (27 tests). It derives every region, pitch, span
and CAD expectation from the geometry helpers, not from `colliders.py` constants, and covers:

* every dense point outside the exact CAD of **all** installed solids, with a deterministic
  0.15 mm sphere-boolean sample; explicit welded-peg/shim exclusion;
* region bounds, per-axis pitch <= 5 mm, spans within one step of the CAD extent, the
  independent 34 x 12 bore plane floor, both exit lateral sides (`y > 20` and `y < -20`);
* both 6 mm blocker negatives, including 0 mm³ exact-CAD proof and the named grid violation;
* retained positives: all six contracts, whole-body AABB hull, filled crank slot, floor slot,
  local f=1 relief and no-hull; and
* the compiled reset, both reset negatives, critical clearances at five fractions and
  `SCENE_VALID`.

```
PATH="$HOME/.local/bin:$PATH" uv run --frozen --extra physics \
  pytest tests/test_pocky_physics_void_coverage.py -q
27 passed in 68.94 s
```

The worker also re-verified every point of all 13 grids (not only the sample): worst 0.15 mm
sphere overlap with any installed solid is **0.0 mm³**; the only 0.15 mm tangencies are the
rod/guide lane points, whose sphere is empty. The earlier near-tangent point
`(-104.5, 36.62595264191645, -5.55)` in `pusher/y_slot_grid` is gone after the clearance
filter (`y_slot_grid` 36 -> 32 points).

Focused regressions (all Pocky tests plus the physics export CLI):

```
PATH="$HOME/.local/bin:$PATH" uv run --frozen --extra physics \
  pytest tests/test_pocky_*.py tests/test_cadkit_physics_export_cli.py -q
164 passed
```

Log: `fidelity-repair/regressions-focused.log`. The full CAD suite remains due in the later
evidence increment, as the packet requires.

## Scope and manifests

Only these files changed relative to the pre-repair state: `projects/pocky/physics/colliders.py`
(the fidelity contracts and their CAD-filtered grid helpers), the new independent test file,
and documentation. No generic cadkit source, CAD model, params, dependency, configuration or
frozen acceptance file changed. No original evidence was deleted or overwritten. Fresh
manifest comparisons are under `fidelity-repair/manifest/`.

## Declared limitations

* The crank `pivot_bore` is not gridded: the welded pivot peg fills the assembled bore. It
  stays the documented parent-filtered probe exception, and no welded peg is treated as void.
* Grids filter against their own body group and every installed part; a separate free body
  that legitimately transits a body void (for example the lip blade through the body bore)
  is treated as installed material and excluded. **This was NOT stricter, not weaker** — that
  claim was false, as the Supervisor review found: silently dropping a point because another
  body happens to occupy it at fraction 0 discards the tested carrier's own void guarantee
  exactly where another body later moves away. The followup operation replaces the deletion
  with an explicit occupancy annotation (see
  `docs/mujoco-m5a-1-fidelity-followup-report.md`); the historical wording is preserved here
  because this report's verdict is historical and was not accepted.
* Narrow features use adapted pitches; exact tangency at the rod/guide 0.15 mm lane is kept
  because a 0.15 mm sphere there has zero volume.
* Fidelity `coverage_max_gap_mm` is a recipe-vs-CAD metric and is unchanged; the new grids
  are the independent check that invented material cannot hide inside a declared void.

## Review

Configured ordinary reviewer follow-up: see the verdict and native transcript metadata below
once complete.

## Non-claims

No S0 scenario or evidence batch, packet seating/capacity, P0–P3, M6/M7, dispensing result,
physical print, commit, push or deployment is claimed or performed. No bridge journal or
supervisor verdict was edited. End of this bounded repair; independent Codex review owns the
next decision.
