# M5a-1 fidelity followup: corrected swept-rod corridor and occupancy reconciliation

**Status:** bounded static correction implemented and evidenced for independent Codex review.
The configured ordinary reviewer approved the final state in round 5 and the independent test
worker returned pass; both are recorded with their raw evidence below. This is still **not**
M5a-1 acceptance, not S0, not packet readiness, not M6/M7, and not a physical claim. No S0 scenario or evidence batch, no P0–P3, no loaded/25-packet/shared-state decision
and no product PASS follows from this document. The verdict of this operation is
**unaccepted pending independent review**.

Supersedes the rejected repair attempt in
`docs/mujoco-m5a-1-fidelity-repair-report.md`, whose verdict stays recorded there as
historical. This report covers exactly the four findings the Supervisor left open in
`docs/mujoco-m5a-1-fidelity-followup-supervisor-review.md`.

## Authorization and actual execution

| Item | Value |
|---|---|
| Supervision run | `run_0mvjxlcc2e0e8c3a94941d366` (successor7), open, limits 3 operations / 2 remediations, deadline `1792711542961` |
| Bridge usage before admission | 27 submitted operations / 11 remediation cycles |
| Request | `cadstudio-m5a1-fidelity-finalize-01a1624d-1` |
| Executing model | `workbuddy-ai/deepseek-v4.1-flash-sg` (configured; no override, no substitution) |
| Native plan mode | not available through the managed `omp-bridge` interface and **not used**; this implements the already approved `docs/mujoco-m5a-plan.md` §6.1 |
| Prior escalated run | `run_0mvjre53o25d566338987a193`, decision `REQUEST_HUMAN dec_0mvjxg328a401cea0b673a1f4` — not reopened, no authorization reused |

Preserved unchanged: every accepted generic `cadkit/` production change, all CAD geometry,
`params.toml`, dependencies and the frozen acceptance file. Verified:
`sha256(projects/pocky/physics/acceptance.toml)` =
`518a45ffc4592ca602be4c33c59681038e43dedaa15b688312202c3a57ff6ca2`.

## Finding 1 — the "exact midpoint swept solid" claim was false, and is now corrected

**What was claimed before.** `_rod_corridor_prisms` said it computed "the exact swept volume"
by splitting x at every station where the cross-section can change and taking "the exact YZ
section at the middle of each interval". The Supervisor required geometric justification for
curved cross-sections, noting that vertices and face bounding boxes alone do not establish
constancy between stations.

**What is actually true.** The rod group has 38 faces: 34 planar faces with axis-aligned
normals and 4 surfaces of revolution about Z at the button-peg axis (`(-66.4529946, -28.0)`) —
three cylinders (Ø4 grip, Ø7 head, Ø4.1 pin-bore wall) and one cone (the tip chamfer).
Between planar stations the YZ section really is constant. Inside the revolution band it is
not: the section is a circular arc whose radius varies continuously with x, so **no** set of x
stations makes the section constant there, and a single midpoint section is neither exact nor
even a superset.

**Measured defect.** The construction that actually shipped in the unaccepted partial
snapshot (16 pieces, 957 probes: stations from vertices and face bounding boxes only, one
midpoint section per interval, no band subdivision) missed **3.8391 mm³** of true swept
material against the 241-copy converged reference. That is unsafe under-coverage: a probe
lattice built from it cannot protect material it does not enclose.

The independent test worker then measured the four variants separately, which is what makes
the causal story unambiguous (`out/mujoco-m5a/fidelity-finalize/worker-review/negatives.json`):

| Variant | Prisms | Missing mm³ | Excess mm³ |
|---|---:|---:|---:|
| A. shipped: midpoint, no axis station, no subdivision | 16 | **3.8391** | 13.958 |
| B. add the axis station only | 17 | **45.5516** | 10.450 |
| C. add band subdivision only, one section per interval | 35 | **4.3422** | 2.514 |
| D. endpoint union, no band subdivision | 17 | **1.6e-9** | 24.195 |
| **Shipped correction: endpoint union + band subdivision** | 35 | **1.1e-8** | **8.123** |

Sources: variants A and B are the first two configurations in
`out/mujoco-m5a/fidelity-finalize/probe_superset.json`; variants C and D exist only in the test
worker's `out/mujoco-m5a/fidelity-finalize/worker-review/negatives.json`, which measured those
combinations directly. The shipped-correction row is
`out/mujoco-m5a/fidelity-finalize/probe_validate_corridor.json`. (The superset probe also
carries a third configuration that subdivides only around the axis; it is not the production
construction and is not used for any claim here.)

The two mechanisms do different jobs, and it is worth stating precisely which is which:

* **The multi-section union produces containment.** Variant D shows that unioning each
  interval's three sections with no band subdivision already misses only 1.6e-9 mm³.
* **Band subdivision makes the enclosure tight.** It cuts the slack from 24.195 mm³ to
  8.123 mm³. It does not by itself give containment — variant C still misses 4.3422 mm³,
  because one section per sub-interval is still one section.

Adding the axis station *alone* makes things much worse (45.5516 mm³): it splits the peg band
at its widest point, so a midpoint section on each half misses the outer part of each half.
Both mechanisms are kept, because containment without tightness would make the corridor's
probes reject colliders that are legal in the true swept volume.

**A second, sharper finding.** The obvious repair — "the section is monotone toward the axis,
so the interval's endpoint union is a superset" — is also **false** for this CAD. Measured on
single planes, the section area is 74.95 mm² at the peg axis and 43.99 mm² at 3.4 mm out, but
the section 1.0 mm out has **0.164 mm² outside** the section 0.5 mm out, because the Ø4.1 pin
bore and the head's z extent vary independently. Neither monotonicity nor nesting holds. The
failure is local: 3.0 mm out *is* nested inside 2.0 mm out, so no single rule covers the whole
band. The code and tests now say so explicitly rather than asserting a convenient lemma.

**A third finding, caught by the configured reviewer.** The first version of the band test and
the evidence probe cut the solid with a 1e-6 mm-thick box and kept both faces of the slab. Near
a tangency that doubles the measured area (149.9 mm² at the axis against a true 74.95 mm²), and
the "3× ratio" assertion passed only because of that artifact. Sections are now taken with
`group & Plane.YZ.offset(x)`, which returns the single section face. Likewise, the non-nesting
check originally used a 2-D face *difference*, which returns the whole first face for coincident
or opposite-orientation operands and therefore "proved" non-nesting unconditionally. It now uses
intersection area. It also originally measured the wrong direction — the nearer section is the
*larger* one (74.18 vs 71.74 mm²), so "nearer outside further" is at least 2.45 mm² even for
perfectly nested sections. The check now asks how much of the **further** section lies outside
the nearer one, which is 0.164 mm² and can actually fail.

**The correction actually implemented** (`projects/pocky/physics/colliders.py`):

* `_x_stations` adds the x of every surface-of-revolution axis (when the axis is not parallel
  to the sweep) as a station, in addition to vertex and face-bounding-box x values.
* `_revolution_bands` reports the **full x extent** of each such surface — the Ø7 head spans
  `axis ± 3.5` mm, so keying subdivision on the axis alone leaves most of the band unsplit.
* `_band_subdivided` splits every interval that overlaps a band into
  `CORRIDOR_BAND_SUBDIVISIONS = 4` equal parts.
* `_rod_corridor_prisms` takes the single-plane CAD YZ section at each interval's two ends
  **and** its midpoint, **translates all three into one common plane**, unions them, and
  extrudes that section along the interval plus the stroke.

**Why the plane translation matters.** Unioning `Face` objects that lie in *different* planes
produces a non-coplanar compound. Extruding that emits one full-length prism per sample, which
inflated the measured excess from ~20 mm³ to **5,685 mm³** in a first attempt. The translation
is the fix, and it is commented in the code so it is not "cleaned up" later.

**Result, measured against the 241-copy converged reference sweep**
(`out/mujoco-m5a/fidelity-finalize/probe_validate_corridor.json`):

| Quantity | Value |
|---|---:|
| Reference (converged) swept volume | 27,552.6598 mm³ |
| Corrected corridor volume | 27,560.7828 mm³ |
| **Missing (true − corridor)** | **1.1e-8 mm³** (boolean noise) |
| **Excess (corridor − true)** | **8.123 mm³** = 0.029% |
| Excess location | `x -93.047…-62.953, y -31.5…-24.5, z -11.6…-4.6` (peg-head band) |
| Pieces | 35 (was 16 in the unaccepted partial snapshot) |

So containment is established by measurement at a sampling density far finer than the
construction, the enclosing slack is bounded and reported rather than claimed away, and the
docstring distinguishes what is *proven* (planar intervals are exactly constant) from what is
*measured* (band containment).

**Probe lattice.** `chassis:rod_corridor_grid` grew from 957 to **1455** points (35 prisms).
Every point is still clipped to its own prism at `-CORRIDOR_MIN_INSIDE_MM = 0.15 mm`, and no
pitch exceeds `VOID_GRID_STEP_MM = 5.0 mm`. Independent audit: 3,183 samples of the true swept
volume, worst distance to the nearest declared probe **3.7934 mm**, against the 4.33013 mm
covering radius of a 5 mm pitch. `probe_z_max = 9.7`, so the lattice reaches the rod's upper
face (`rod_z1 = -11.6`) rather than stopping at the shaft.

## Finding 2 — `VoidOccupancy` contradicted the implementation

The class docstring said other-occupied points are "not counted as own-void coverage" and that
"such a point cannot be a probe of a free carrier". Both statements were false against
`_void_grid`, which **keeps** every point that is outside the carrier's own welded group and
records other-body occupancy as an annotation. The docstring now states the implemented
invariant: `other_occupied ⊆ own_void`, `own_void_count` equals the declared probe count, and a
point is dropped only for own-group material. The quoted counts were refreshed to the actual
current values (chassis 1455 kept / 650 annotated: rod 572, peg_button 39, spring 27, crank 12).

## Finding 3 — slot notes implying a peg is excluded

The crank `button_slot` seed note said "button slot void, clear of the installed button peg",
which reads as a peg exclusion. The three seeds are in fact outside the peg's fraction-0 CAD
(verified by exact `is_inside` and a 0.15 mm sphere boolean: 0.0 mm³ in all three), and the
dense `button_slot_grid` keeps and annotates peg occupancy rather than excluding it. The note
now says that explicitly.

## Finding 4 — report and manifests

* This report did not exist; the partial supersession notice in the old repair report linked to
  it. It exists now.
* The false "stricter, not weaker" limitation in the old repair report is now marked false in
  place, with a pointer here, while the historical verdict stays recorded.
* The after-manifest is regenerated **after** all source and report edits, under
  `out/mujoco-m5a/fidelity-finalize/manifest/`, and its staleness is checked against the live
  tree. The older `out/mujoco-m5a/fidelity-followup/manifest/` predates these edits and is
  preserved as the historical followup snapshot, not presented as current.

## Preserved behaviour (no proxy or criterion was weakened)

| Gate | Result |
|---|---|
| `cad physics export pocky/prototype` (real CLI) | PASS; scene hash `2c4bd425c55d9f56c39904e6ae01683836650fc84dabaa6ff645eb1077926e2f`, 9 bodies, 202 geoms, MuJoCo 3.16.0 |
| Raw scene XML SHA256 | `997a20b79566bfc5452e334b98f149c292056312795ce85f763308d430a22a15` (unchanged) |
| Export fidelity contracts | body/lip/chassis/crank/rod/pusher all **ok**; coverage worst 0.2 / 0.0 / 0.3245 / 0.0835 / 0.0 / 0.0711 mm (limit 0.5) |
| Compiled reset / negatives / clearance / validity | see `compiled-audits.json` |

Collider geometry, tolerances, CAD, params, assembly, restraints and criteria are unchanged.
The scene hash is byte-identical, which is the proof that this operation only touched declared
probes and their generation.

## Tests

### Focused regression (required minimum)

```
PATH="$HOME/.local/bin:$PATH" uv run --frozen --extra physics \
  pytest tests/test_pocky_physics_assembly.py tests/test_pocky_physics_colliders.py \
         tests/test_pocky_physics_void_coverage.py tests/test_cadkit_physics_export_cli.py -q
```

**139 passed, exit 0, 535.58 s.** Raw log:
`out/mujoco-m5a/fidelity-finalize/focused-regression-final.log`. This ran after the final source
and report edits.

### Full suite (due once shared M5a-1 changes are final)

```
PATH="$HOME/.local/bin:$PATH" uv run --frozen --extra physics pytest tests -q
```

**900 passed, exit 0, 950.33 s**, one unrelated `UserWarning` about a duplicate `time.npy`
name inside a zip. Raw log: `out/mujoco-m5a/fidelity-finalize/full-suite.log`. This ran after
every source, test and report edit, and is the last test execution of the operation.

### The three geometric tests that carry the claim

| Test | What it proves | Result |
|---|---|---|
| `test_rod_corridor_contains_the_true_swept_cad_volume` | The corridor contains a 121-copy converged reference sweep (`reference - corridor` empty) and its excess stays under 0.5% of the sweep | pass |
| `test_rod_corridor_band_sections_are_not_nested_so_endpoint_union_is_required` | The band section varies (74.95 → 43.99 mm²), the further section is **not** contained in the nearer one (0.164 mm² outside), the failure is local (3.0 mm out *is* nested in 2.0 mm out) | pass |
| `test_rod_corridor_band_subdivision_keeps_the_enclosure_tight` | Production subdivides the bands (35 prisms vs 17) and encloses 8.283 mm³ where the unsubdivided variant encloses 24.355 mm³ | pass |

The third test exists because the independent worker found a **test-strength gap**: variant D
(three-section union with no band subdivision) already contains the sweep, so no test detected
removal of `_band_subdivided`. That test compares **production** against a locally built
unsubdivided mutant and asserts production builds more prisms and encloses less. Verified by
mutation: with `_band_subdivided` stubbed out, it fails with "production builds 17 prisms and
the unsubdivided variant 17".

### Test file size

`tests/test_pocky_physics_void_coverage.py` collects **47 tests** (44 in the repair increment
plus the three geometric tests added here).

### Independent test worker

Authored/checked by a worker separate from the implementer. Verdict: **pass**, no defect in
the contract. Its evidence is under
`out/mujoco-m5a/fidelity-finalize/worker-review/`, including independently built reference
sweeps (`reference_sweep_{30,60,120,240}.brep`), a containment run that reproduces the shipped
numbers exactly (missing 1.1360554399019556e-08 mm³, excess 8.122939146293769 mm³, 35 prisms),
and a four-variant negative table (`negatives.json`) that is the basis of the defect table in
Finding 1. Its own checks: `between_samples.json` (`all_contained: true`), 
`random_translations.json` (`all_contained_le_1e-6: true`), `probe_quality.json`
(`probes_outside_corridor: 0` of 1455), `occupancy.json` (accounting failures: none; per-part
recount agrees: rod 572, peg_button 39, spring 27, crank 12).

### Configured ordinary reviewer

Four review rounds are recorded in `out/mujoco-m5a/fidelity-finalize/review/`, preserved as
`verdict-round1.*` … `verdict-round5.*`. The rounds found real defects, which is why all of
them are kept, including the four rejections:

| Round | Verdict | Blocking findings |
|---|---|---|
| 1 | reject | doubled section areas from a thin-box cut; band subdivision did not match its own claims; cited evidence did not support the claims |
| 2 | reject | non-nesting measured the wrong direction (nearer is the *larger* section, so it could never fail); report claimed a current manifest that was stale; report cited sections that did not exist |
| 3 | reject | false claim that subdivision *and* union were both required for containment (variant D already contains); table mislabelled stations as prisms |
| 4 | reject | the after-manifest was again stale, because the round-3 wording fixes postdated it |
| 5 | **approve** | none |

**Final verdict: approve (round 5).** The reviewer re-hashed all 226 manifest entries against
the live tree (none stale or missing), re-ran the new subdivision test on production and on the
stubbed mutant, and confirmed the test prose, the 47-test count and every headline number.
It recorded one non-blocking note: the report sentence "ran after the final source and report
edits" is true for every source and test edit, and the report edit that came 8 s after the run
was the one recording the result.

The independent test worker returned **pass** with no contract defect, and additionally
identified a test-strength gap (removing band subdivision was undetected), which is now closed
by `test_rod_corridor_band_subdivision_keeps_the_enclosure_tight`.

Every blocking finding was fixed in the code, tests or report as described in the findings
above, and each was re-confirmed as fixed in the following round. Round 4's sole remaining
finding was the manifest; after it was regenerated, round 5 re-hashed all 226 entries and
approved. The manifest is regenerated once more after this paragraph so that its own
`after-manifest.json` covers this text; verify currency by hashing
`out/mujoco-m5a/fidelity-finalize/manifest/after-manifest.json` against the live tree rather
than trusting this sentence.

## Non-claims and remaining risk

* The previous no-actuation smoke reached **0.7909 mm** penetration. That is a numerical
  INCONCLUSIVE against the planned S0 **0.2 mm** validity bound, not a physical FAIL and not a
  product PASS. It is not repaired here and no S0 batch is authorized by this operation.
* Physical inputs remain unverified. Numerical INCONCLUSIVE stays distinct from physical FAIL.
* The corridor encloses 8.123 mm³ beyond the true sweep by design. That slack can, in
  principle, reject a collider that is legal in the true swept volume but inside the enclosing
  slack. No such collider is currently declared; this is a bounded, measured trade against the
  alternative of unsafe under-coverage, and it is stated rather than hidden.
* Guide/peg parent filtering remains a joint idealization. It does not establish corridor
  preservation or physical mechanism success.
