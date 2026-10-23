# M5a-1 adapter/static increment — report

**Status:** implementation and static evidence complete for this bounded turn; submitted for
independent Codex review. This is **not** M5a-1 acceptance, not S0, not packet readiness, not
M6/M7 and not a physical claim.

> **R1 correction (applied after independent review).** The independent Supervisor review
> found the declared void probes sparse: two 6 mm blockers in real CAD void were not detected.
> A bounded repair replaced the sparse lists with deterministic, CAD-derived dense grids
> (<= 5 mm; **6843** points across 13 grids) filtered against exact installed CAD, and added
> independent tests for extents, pitch, exact-CAD void and both blocker negatives. The
> colliders, compiled scene hash, static preflight, compiled audits and smoke results in this
> report are unchanged; only the fidelity contracts and tests grew. See
> `docs/mujoco-m5a-1-fidelity-repair-report.md` and
> `out/mujoco-m5a/adapter-static/fidelity-repair/`.

## Authorization and actual execution

| Item | Value |
|---|---|
| Supervisor decision | `dec_0mvjaa93m7c7fe330fbbb475a` (`CONTINUE` after repair `op_0mvj94k0p6eaf0732bc596115`) |
| Supervision run | `run_0mvj62atk8b61da9fe2edf2ea` (successor5), limits 6 ops / 2 remediation cycles, deadline `1792679704903`, unchanged |
| Cumulative bridge submissions | 24 before this admission; this packet makes 25 |
| Handoff / session | `ho_0mvjaaafa6a581d682a906a18`; session `01a162be-5736-724c-aa53-9e7e8dac5958`, generation 2, empty-context start |
| Chat binding / request | `01a1624d-8caf-7102-991f-d6ca998446b4`; `cadstudio-m5a1-adapter-static-01a1624d-1` |
| Executing model | `opencode-go/deepseek-v4.1-flash` (configured default; no override) |
| Native plan mode | not available through the managed `omp-bridge` interface and **not used**; this is implementation of the already-approved plan `docs/mujoco-m5a-plan.md` §6.1, not artifact-based planning |
| Model / provider / effort / role changes | none; no substitute or fallback used |

Scope: handoff items 3–5, the assembly/options/lazy hooks, explicit collider contracts, static
preflight, all-five compiled reset and critical-clearance audits, negative fidelity/reset
cases, overlays, independent tests and configured review. The full S0 scenario/readiness batch,
loaded-packet seating, the 25-capacity variant and P0–P3 remain outside this admission.

## Preserved baseline

The accepted generic S0-check work and the accepted source snapshot
`out/mujoco-m5a-supervisor-repair/accepted-snapshot/` are preserved. The fresh manifest
comparison (`out/mujoco-m5a/adapter-static/manifest/comparison.json`) against that snapshot
shows only:

* added: `projects/pocky/physics/{__init__,assembly,colliders,options,support,clearance_audit}.py`;
* changed: `projects/pocky/__init__.py` (authorized lazy hooks) and
  `docs/mujoco-m5a-1-s0-checks-acceptance.md` (the legitimate subsequent Supervisor
  acceptance-note append);
* removed: nothing; 205 files otherwise byte-identical.

No CAD, params, model, export-source or frozen acceptance change. Frozen
`projects/pocky/physics/acceptance.toml` raw SHA256 remains
`518a45ffc4592ca602be4c33c59681038e43dedaa15b688312202c3a57ff6ca2`.

## Implemented surface

| File | Content |
|---|---|
| `projects/pocky/physics/assembly.py` | explicit `static_solids` + `moving_solids` inventory, grouped bodies, CAD joints/limits, equivalent spring, analytic floor, CAD-derived `reset_state`, strict rejection of packets/capacity/nonzero build fraction |
| `projects/pocky/physics/colliders.py` | explicit convex recipes for body (44), lip (15), chassis (55), crank (33 incl. peg), rod (11 incl. peg/mask), pusher (29); declared probes/transits/coverage/critical surfaces |
| `projects/pocky/physics/options.py` | strict support for 200/500/1000 N/m and 1 ms/0.5 ms; rejects loaded packets, capacity, packet mass, compliance/friction/fraction and unknown keys |
| `projects/pocky/physics/support.py` | bearing direction, support margin, exact-solid overlap at five fractions, tilted 10/25 seat inventory, full static preflight |
| `projects/pocky/physics/clearance_audit.py` | compiled reset audit, linear/sign negatives, critical collider-vs-CAD clearance audit, exact-overlap vs collider-penetration validity audit |
| `projects/pocky/__init__.py` | lazy `physics` and `physics_with_options` hooks; other models still return `None` |
| `tests/test_pocky_physics_assembly.py`, `tests/test_pocky_physics_colliders.py` | independent tests, written by a separate worker (see Tests) |
| `docs/mujoco-m5a-1-adapter-static-report.md` | this report |

### Assembly and contact loop

* Runtime scene **always built at CAD button fraction 0**. The five reset states are derived
  at runtime from `linkage_from`, `phi_for_button_fraction` and `pose_at_phi`; no interpolation.
* Bodies: `body` (with both installed shims), free `lip`, free `chassis` (with `spring_seat`
  and `peg_pivot`), `crank` hinge on `chassis`, `rod` slide on `chassis` (with `peg_button`
  and the masked spring visual/mass), `pusher` slide on `chassis`, and the sole world-fixed
  analytic floor (`fixture="analytic_fixture"`, top z = −19.2 mm).
* Joints: hinge `crank_phi` +Z at the CAD pivot with limits −1.06…+0.01 rad; slide `rod_x`
  +X −0.023194…+0.0001 m; slide `pusher_x` +X −0.0005…+0.0505 m. Stop compliance 2 ms;
  contact compliance 2 ms; RK4/Newton/elliptic/100.
* Spring: `rod_x` equivalent, 500 N/m default, reference +0.003 m; approved 200/1000 N/m and
  1/0.5 ms options only. No colliding spring beams.
* Mechanism↔chassis contacts are **parent-filtered** by MuJoCo's default and are represented
  by joints/stops; sibling pin-in-slot and free-body contacts are real geometry. This is a
  declared load-path idealization, not a hidden restraint.
* The bench `dummy` and parked `shim_08` are excluded; every installed part appears once.

## Static preflight (no MuJoCo)

| Group | Mass g | COM (x, y) mm | Strip mm | COM margin mm | Gravity moment mN·m |
|---|---:|---|---:|---:|---:|
| body | 139.46 | (1.21, 0.000) | 4.23 | −6.85 | 9.37 |
| hanging group | 145.89 | (5.28, 0.000) | 4.23 | −4.54 | 6.50 |

* Bearing: clip tooth underside +0.05 mm vs body rib top 0.00 mm → **retention-only +Z**.
  `carries_gravity_downward = False`; a downward load separates the rib from the tooth. A
  support polygon cannot convert upward retention into a downward bearing.
* Exact-solid overlap of the installed groups: **0 mm³ at all five fractions** (worst 0,
  noise threshold 1e−3 mm³).
* Tilted seat (1.036835°): 10 packets top 54.979 mm, top-rear x −83.347 mm; 25 packets top
  132.966 mm, top-rear x −84.758 mm, 0.242 mm from the back wall, zero overlap with the
  installed solids after the declared 1 µm seating clearance. This is a read-only static
  diagnostic; it authorizes no loaded scene.

## Compiled evidence

Exact commands and logs are in `out/mujoco-m5a/adapter-static/` (index below). Summary:

| Check | Result |
|---|---|
| `cad physics export pocky/prototype` (real CLI) | **PASS**, scene hash `2c4bd425c55d9f56c39904e6ae01683836650fc84dabaa6ff645eb1077926e2f`; 7 bodies (one fixed), 188 colliders, 14 visual meshes (202 geoms); MuJoCo 3.16.0 |
| Fidelity contracts | body/lip/chassis/crank/rod/pusher all **pass** at export; coverage worst 0.2 / 0.0 / 0.325 / 0.083 / 0.0 / 0.071 mm (limit 0.5); critical-surface deviation 0.0 mm (limit 0.02) |
| Compiled reset audit, five fractions | **PASS**; all errors ≤1.2e−16 (crank 1e−9 rad, translation/station 1e−6 m limits) |
| Quarter-stroke negative (linear 12.5/37.5 mm) | **rejected**, min pusher error 1.367505 mm (≥1.367) |
| Sign-flipped pusher negative | **rejected**, max error 77.735 mm |
| Critical clearance audit, five fractions | **PASS**; max collider-vs-CAD difference 2.2e−7 mm (limit 0.02) |
| Validity: exact overlap vs collider penetration | **SCENE_VALID** at all five; exact overlap 0 mm³, worst initial contact −2.6e−18 m |
| No-actuation execution smoke, f=0, 5 steps | **PASS**; peak penetration 3.95e−6 m; no warnings |
| No-actuation execution smoke, f=1, 20 steps | **PASS only against the smoke's own 1 mm bound**; peak penetration 7.909e−4 m at t = 11 ms, above 0.2 mm in 13 of 20 steps and still 2.21e−4 m at the last step. Sibling contacts observed: crank `peg_button_shaft`/`cap_east` vs rod, and crank `peg_pusher_shaft` vs `carriage_west`/`pusher_cap_*`. This is **not** S0 and would breach the frozen S0 0.2 mm penetration limit; it is a residual risk for f>0 S0 starts. |
| Half-timestep smoke (0.5 ms, 5 steps) | **PASS**; peak penetration 1.56e−6 m |
| Spring 200 N/m smoke | **PASS**; peak penetration 6.41e−6 m |
| Scenario/assembly timestep mismatch | **ERROR** before a run directory: `scenario timestep_s 0.001 differs from the assembly timestep 0.0005` |
| `packets = 1` option through the real CLI | **ERROR** before a run directory: loaded packets need a later bounded planning approval |

Critical pair clearances measured on the compiled scene (CAD / collider, mm): body floor ↔
pusher carriage top 0.400/0.400; body floor ↔ chassis boss top 9.200/9.200; clip tooth ↔ body
rib 0.050/0.050; lip tooth ↔ body bar 0.150/0.150 (both sides); lip foot ↔ shim 0.050/0.050
(both sides); crank pusher-peg ↔ carriage 0.200/0.200; button peg ↔ crank slot 0.300/0.300;
f=1 peg head ↔ local relief ceiling 0.190/0.190; f=1 lip rail ↔ rod head 0.300/0.300.

The plan's body↔bullnose 0.027 mm is the **bullnose underside resting on the body floor top**:
exact CAD distance **0.000 mm** at all five fractions (a sliding line contact over the full
bullnose width outside the floor slot). The audit now measures exactly that pair
(`body_pusher_bullnose_contact`, CAD 0.000 mm, compiled collider −0.000143…−2e−9 mm). The
separate back-wall face above the notch measures 0.760 mm in both CAD and colliders and is
reported as **informational**, not as the plan's critical pair. The zero-clearance bullnose
contact is a declared load-path consequence, not hidden separation or a tolerance change.

## Overlays inspected

23 PNGs under `out/mujoco-m5a/adapter-static/overlays/`, each contrasting translucent CAD with
solid colliders. Inspected images include: `body_iso`, `body_top`,
`body_side_cutaway_yneg`, `body_iso_cutaway_ypos`, `focus_body_relief`,
`focus_body_slot`, `focus_chassis_boss`, `focus_chassis_hook`, `focus_crank_slot`,
`pusher_iso`, `pusher_top`, `focus_pusher_slot`, `pusher_side_cutaway_yneg`,
`focus_pusher_bullnose`, `lip_iso`, `lip_side`, `focus_lip_exit`, `chassis_iso_cutaway_yneg`
and `rod_iso`. The focused views show the local f=1 relief tiling (not a long strip), the open
floor slot, the boss bore with ring sectors, the crank and pusher slot end fans, the bullnose
and the separator/exit gap. Numeric fidelity remains the gate; the images are diagnostic.

## Tests

Independent worker (separate from the implementation): `tests/test_pocky_physics_assembly.py`
(27 tests) and `tests/test_pocky_physics_colliders.py` (56 test cases). The worker derived
expected values from the actual CAD helpers and exact solids, and independently verified every
declared probe and transit against exact-CAD sphere booleans.

```
/Users/daniel_l_newman/.local/bin/uv run --frozen --extra physics \
  pytest tests/test_pocky_physics_assembly.py tests/test_pocky_physics_colliders.py -q
83 passed in 61.74 s
```

The worker found one real production defect before the final run: the declared
`return_chamfer` probe sat in CAD material, and the pusher neck omitted a real CAD corner
above the 30° wedge (`coverage_max_gap_mm` reported 0.455 only because the 400-vertex sample
missed it). Fixed in `colliders.py` by rebuilding the neck as `neck_south`, `neck_east` and
eight bands above the wedge line, and by replacing the probe with two exact-CAD void points
(`face_x - 4.1, 0, 0.10` and `face_x - 3.9, 0, 0.0`). No assertion was weakened; the strict
xfail marker was removed after the fix, and the pusher coverage fell to 0.071 mm. Final
re-run: 83 passed.

Focused existing regressions:
`tests/test_cadkit_physics_scene.py`, `_support.py`, `_friction_priority.py`, `_cli_run.py`,
`_export_cli.py`, `_relative_checks.py`, `tests/test_pocky_{geometry,linkage,params,prototype}.py`
gave **235 passed, 2 failed**; both failures are environmental (`test_cli_list` and
`test_cli_check_set_reflected` invoke a bare `uv`, which is not on this shell's PATH). Re-running
`tests/test_pocky_geometry.py` with `~/.local/bin` on PATH gave **19 passed**. Full CAD suite
remains due in the following evidence increment, as the packet requires.

## Review

Configured ordinary code review (the `reviewer` role, configured Opus; no model/role
override) returned **findings, not approve** on the first pass. Four demonstrated defects were
fixed without changing any criterion:

| Finding | Fix |
|---|---|
| D1: body↔bullnose audited on the back-wall faces; the real pair is the bullnose underside resting on the body floor top (CAD 0.000 mm at all five fractions) | added `body_pusher_bullnose_contact` (`floor_*` vs `bullnose`, moving window) at every fraction; renamed the 0.760 mm back-wall face pair to informational; report corrected |
| D2: the f=1 smoke peak was described as a 1 ms transient | report now states 0.7909 mm at t = 11 ms, 13/20 steps above 0.2 mm, 0.221 mm at the end, pin-in-slot pairs, not S0, would breach the frozen 0.2 mm limit |
| D3: back-wall gap sign inverted in `static_preflight.json` | now `top.min.X − tube["x0"]`: +1.6531 mm (10) / +0.2417 mm (25) |
| D4: relief tiling intruded 0.124 mm into the declared void | `y_cut` now uses each band's nearest x to the pin; minimum pin-to-band distance 3.900 mm against R=3.900; f=1 peg/relief clearance unchanged at 0.19 mm |

The reviewer also noted renderer/legend limitations and a non-critical body↔rod clearance
difference (0.151 mm at f=0.75, under the 0.5 mm coverage limit); both are reported above
rather than tuned.

**Follow-up verdict: approve**, no new demonstrated defects. The reviewer re-checked D1–D4 on
the current code and regenerated evidence; it also confirmed the independent test now asserts
`model.neq == 0` / `model.nu == 0` and the exact `PAIRS × pair.fractions` clearance set. Its
remaining observations were a symmetric-window note, a slightly loose relief under-cover
comment (corrected to ~0.3 mm, still inside 0.5 mm) and the oblique/legend-limited
`focus_body_notch` image. Reviewer transcript:
`out/mujoco-m5a/adapter-static/review/M5a1AdapterReview.jsonl`, SHA256
`9242e4341d1d5f6cb1df1fa1c355233b547c15f777c46fb448431154b524ecf5`, 57 assistant messages,
all `anthropic/claude-opus-5-5` (provider `anthropic`). Test worker transcript:
`out/mujoco-m5a/adapter-static/review/PockyPhysicsTests.jsonl`, SHA256
`38aa64357b733fba99638c4080697900226cade3083d4bc3ca21a0921ea84880`, 66 assistant messages,
`opencode-go/deepseek-v4.1-flash`. No model, provider, effort, role or fallback override was
used; the required configured roles executed.

## Deviations, limitations and non-claims

* `prototype_assembly` accepts only `button_fraction=0`. The plan's §3.1 note that the function
  "remains available" at any fraction is implemented as exact-CAD solids at every fraction in
  `support.assembly_solids`, not as a per-fraction compiled scene. A nonzero build fraction
  raises rather than producing a scene whose joint reference silently shifts.
* The pivot bore is a 12-sector polygon and a declared probe exception; it is not a 0.02 mm
  critical surface. The boss plate hole is an octagonal tiling with ≤0.36 mm over-cut at the
  corners. Slot end caps are tangent-box fans with ≤0.1 mm chord gap; both are declared
  approximations, not filled voids.
* Chamfers are approximated: the notch ceiling and exit underside by adjacent boxes, the R0.8
  blade edge by the blade box, and the bullnose 30° return by eight bands above the exact wedge
  line plus `neck_south`/`neck_east`, so the wedge void stays open and no CAD material is
  omitted. The f=1 relief tiling uses each band's nearest x to the pin and never enters the
  circle (minimum pin-to-band distance 3.900 mm against R=3.900); it under-covers the far side
  of a band by less than 0.2 mm, inside the 0.5 mm non-critical coverage limit. The measured
  clearances above are the CAD values, not collider-constant echoes.
* One non-critical pair differs more than the critical 0.02 mm: body↔rod at f=0.75 measures
  1.264 mm in CAD against 1.113 mm for the colliders (body ledge vs rod head), 0.151 mm. This
  is not a declared critical pair and is inside the 0.5 mm coverage limit; it is reported, not
  tuned.
* The 25-stack top-rear x is −84.758 mm (plan −84.74, difference 0.018 mm) and its back-wall
  clearance is **+0.2417 mm** (plan 0.255); the JSON now reports the gap with the correct
  positive sign (`top.min.X − tube["x0"]`). Both values are inside the 0.02 mm comparison
  tolerance and are reported as measured.
* The f=1 20-step smoke is **not** S0: it shows the spring-return transient with a 0.791 mm
  peak penetration at t = 11 ms (above 0.2 mm for 13/20 steps, 0.221 mm at the last step),
  concentrated in the two pin-in-slot pairs. Initial reset validity is separate and zero. This
  is a residual risk for f>0 S0 starts and would breach the frozen S0 0.2 mm penetration limit;
  no threshold or compliance was changed to hide it. S0 status must come from the later,
  separately admitted scenario/readiness batch.
* The bullnose rests on the body floor with zero clearance, so every S0 run will have
  pusher↔body sliding contact and friction. This is a real CAD load path, not a collider
  artifact.
* The tilted-seat zero-overlap result is checked against the 72 mm, 10-capacity tube; packets
  above 72 mm have no walls to hit, so for the top of the 25-stack it proves no wall
  interference only. The 25-capacity variant remains unapproved and unrun.
* No loaded-packet scene, 25-capacity variant, shared-state start, P0–P3 decision, M6 design,
  dispensing result, physical print or bench claim is made. Packet mass, wrapper friction,
  spring rate/damping, guide/slot friction, clip force and print tolerance remain unmeasured.

## Evidence index (`out/mujoco-m5a/adapter-static/`)

| Path | Content |
|---|---|
| `export/{scene.xml,report.json,assets/*}` + `export.log` | real-CLI export, compiled scene, fidelity report, assets |
| `export/hash-report.json` | SHA256 of scene, assets and report |
| `cad_probe.json` | CAD volumes/masses/bounds, linkage/spring values, five resets, quarter-stroke values |
| `static_preflight.json`, `static_preflight.md` | bearing, margins, exact overlap, tilted seat, resets |
| `inventory.md` | inventory/provenance/omission/idealization table |
| `compiled/reset_audit.json` | compiled transforms vs CAD at five fractions |
| `compiled/negative_resets.json` | linear and sign-flipped reset negatives |
| `compiled/clearance_audit.json` | CAD vs collider critical clearances at five fractions |
| `compiled/validity.json` | exact overlap vs collider penetration at five fractions |
| `smoke/{scenario*.json,acceptance.json,options_*.toml}` | evidence-local smoke inputs |
| `smoke/run*` + `*.log` | CLI smoke runs and option/direction rejections |
| `overlays/*.png`, `overlays/index.json` | inspected CAD+collider overlays |
| `manifest/{before,after}-manifest.json`, `manifest/comparison.json` | accepted snapshot vs current tree |
| `regressions-focused.log`, `regressions-pocky-geometry.log`, `regressions-new-tests.log` | focused existing and independent regressions |
| `review/{request.md,verdict.md,tests.md,verification.json,*.jsonl}` | configured review and worker transcripts/hashes |
| `scripts/generate_evidence.py` | reproducible evidence generator |
