# M5a implementation plan — original Pocky adapter, free assembly, S0 and P0–P3

**Status:** planning artifact only. This document does **not** authorize implementation.
Codex must approve the plan and then issue a separate implementation operation through the
bridge. No product, test, harness, configuration or service file was changed to produce it.

**Planning identity (actual):**

| Item | Value |
|---|---|
| Supervision run | `run_0mviyq59q90622f804e919ceb` (successor4) |
| Current operation | `op_0mviyqlkz462e1d0a2dee9f1e`, turn 1, `running`, no authorization id |
| Limits | 10 operations / 2 remediation cycles / deadline `1792667380525`; cumulative before this admission 19 operations / 7 remediation cycles |
| Executing model | `opencode-go/deepseek-v4.1-flash` (configured default; no override) |
| Native plan mode | **not available through the managed `omp-bridge` interface and not used**. This is **artifact-based planning** in the existing managed session. No `/plan`, separate planner process, routing change or role substitution was used. |
| Authorizing packet | `docs/mujoco-m5a-planning-packet.md` |
| Frozen future implementation scope | `docs/mujoco-m5a-packet.md` (not authorization for this turn) |

Frozen references:

| File | SHA256 |
|---|---|
| `plan-mujoco.md` | `4f69292c97bd03aab221f3c36b5569f8cbe546896b11907ac484555836092f76` |
| `projects/pocky/physics/acceptance.toml` | `518a45ffc4592ca602be4c33c59681038e43dedaa15b688312202c3a57ff6ca2` |
| `docs/mujoco-m5a-packet.md` | `178b11dbbd4bb634252e403a8dfec4aabf5e2c145ab14ab0dfd94dbc5dd60098` |
| `docs/mujoco-supervision-renewal-4.md` | `fb48c03690f5f78519923344dffedcf1c4864d7f135eb0384ab4d63ac2e600a7` |

Working-tree evidence before planning: `out/mujoco-m5a-planning/before-manifest.json`
(181 files, 3,951,928 bytes; excludes `out/**`, `.venv/**`, `__pycache__`, `*.pyc`,
`.pytest_cache`, `.DS_Store` and `.omp-bridge/**`). Against the accepted M4 snapshot
`/Users/daniel_l_newman/.omp-bridge/backups/cadstudio-mujoco-m4-final-20261022T004848Z/manifest.json`,
all `cadkit/`, `projects/`, `tests/` and root files match. Two `docs/` files differ:
`docs/mujoco-m5a-packet.md` and `docs/mujoco-orchestration.md`. They are pre-existing
supervisor-authored additions/updates after that snapshot, not changes made here; the
additional project documentation PNGs, `.gitignore`, `.python-version`, `MUJOCO_LOG.TXT` and
renewal/pause documents are also outside the snapshot and are preserved.

An independent configured review rejected the first draft of this plan. The demonstrated
defects (wrong pusher stroke, joint-zero contradiction, P0 back-wall overlap, wrong packet
drop, fidelity tolerances wider than the gaps, friction-combine error, missing assembly-option
path, unbindable S0 criteria, and unsettled P starts) are fixed below; the review and fixes
are recorded in `docs/mujoco-m5a-plan-review.md`.

---

## 1. Verified starting state

### 1.1 Accepted infrastructure and gaps

M0–M4 are independently accepted (`docs/mujoco-m4c-supervisor-acceptance.md`). The generic
layer provides `schema`, `scene.export_scene`, `collision` fidelity, `runner.run_assembly`,
`evaluate`, `telemetry`, `state_archive`, `replay`, `Project.physics` and the CLI verbs
`physics export|fixture|channel|mechanics|scenario|replay`.

Measured gaps this plan must close:

1. `projects/pocky/physics/` contains only `acceptance.toml`; **no adapter exists**.
2. No CLI verb calls `Project.physics` and `run_assembly` together.
3. `ColliderSpec` has **no friction or priority**. `AssemblySpec.friction` is one global
   triple, and MuJoCo combines equal-priority geom friction by **maximum**, so a packet at
   0.30 against PETG at 0.40 would silently become 0.40.
4. `AssemblySpec` has **no world floor**; a fixed analytic floor body must be declared.
5. Joints are one hinge/slide per body in a forest. There is no equality/connect joint and
   no variable-radius slot constraint; pin-in-slot must be real contact geometry.
6. `convex` colliders are rejected; only box/cylinder/capsule/sphere are available.
7. `Project.physics(model, params)` has no path for per-run assembly options (packet count,
   mass, spring rate, timestep, capacity), and `run_assembly` does not compare
   `scenario.timestep_s` with `spec.timestep_s`.
8. The generic `CheckSpec` set has no relative-pose, relative-translation or contact-duration
   predicate; S0 would otherwise be unbound to the run and unreplayed.
9. MuJoCo filters parent–child contacts by default; `scene.py` does not override it. The
   crank/rod/pusher are children of the chassis, so mechanism↔chassis contacts are filtered.
10. No `Project.physics_evaluate` or equivalent exists; this plan does **not** add one, because
    generic checks plus replay are the correct binding.

### 1.2 CAD facts measured from the actual sources

Read from `projects/pocky/geometry/{prototype,linkage,packet}.py`,
`projects/pocky/params.toml`, `docs/mujoco-architecture-review.md` and a read-only probe of
the solids on 2026-10-21. Geometry/provenance facts, not simulation results.

| Fact | Value | Source |
|---|---:|---|
| Packet envelope | 165 × 55 × 5.2 mm | `params.toml`, user-measured thickness |
| Magazine internal | 170 × 60 mm | `params.toml` |
| Separator gap / blade thickness | 5.75 / 2.4 mm | `params.toml`, `prototype.BLADE_T` |
| Button stroke | 23.094 mm | `linkage_from` |
| **Pusher stroke** | **50.000 mm** (pin x −103 → −53; face −87 → −37) | `linkage_from`, `pose_at_phi` |
| Crank swing / radius | 60° about (−78, −8) / 50.0 mm | `linkage.py` |
| Crank / carriage / rod Z bands | −11.2…−7.2 / −6.8…−2.8 / −15.6…−11.6 mm | `linkage_from` |
| Body floor underside | −2.4 mm; floor top 0.0 | `linkage_from` |
| Pusher carriage top | −2.8 mm; 0.4 mm below the body floor | `linkage_from` |
| Highest chassis surface under body | −11.6 mm; 9.2 mm void to the body floor | M0 evidence |
| Base plate top | −15.6 mm | `prototype._chassis` |
| Clip tooth underside / body rib top | +0.05 / 0.00 mm | `prototype._chassis_hook`, `_body` |
| Clip bearing patches | x 64…70, y 34…35 and x −36…−30, y −35…−34 mm | M0 evidence |
| Hanging group (body+lip+shims) | 145.89 g, COM (5.28, 0.00, 26.08) mm | M0 evidence |
| Support strip width / COM margin | 4.23 mm / −4.54 mm (group), −6.86 mm (body) | M0 evidence |
| Gravity moment | 9.4 mN·m body alone; ≈6.5 mN·m hanging group | recomputed from the margin |
| Spring B free / installed / full press | 53.4 / 50.4 / 27.306 mm | `PROTOTYPE_SPRING` |
| Spring compression at rest / full | 3.0 / 26.094 mm | derived |
| PETG density | 1.27 g/cm³ (datasheet) | `params.toml` |
| Total modeled solid mass (no packets) | 280.373 g (2.750 N) | CAD volumes × density |
| Body / chassis / lip | 139.432 / 102.567 / 6.426 g | CAD volumes × density |
| Rod / pusher / crank / spring | 16.151 / 8.759 / 3.858 / 1.919 g | CAD volumes × density |
| Pegs / seat / shims | 0.873 / 0.356 / 0.032 g | CAD volumes × density |

Exact-solid probes (read-only; raw output stored in `out/mujoco-m5a-planning/cad_probe.json`):

- `static_solids()` + `moving_solids()` with `compressed_length(0.0)`, excluding the bench
  `dummy` and parked `shim_08`, have **zero pairwise overlap at all five button fractions**.
- The free spring (53.4 mm) overlaps `spring_seat` by 210 mm³; the adapter must use
  `compressed_length(initial_travel)`.
- Packet 2 at nominal pitch 5.2 mm overlaps the lip blade by **256.446 mm³**. The correct
  derived seat is in §5; it is not a silent lift.
- The pusher-peg relief is **local**, not a long strip: the f=1 relief circle (R3.9 at
  x −53, y 35.301) cuts the body floor/side wall at approximately x −56.9…−49.1,
  y 31.4…32.4, z −2.4…−0.01. The f=0 circle lies outside the body's x range. A long relief
  strip would remove real floor/wall material.
- The tilt seat for packet 2 is 1.0368° (bottom line through (−82.5, 5.2) and the blade rear
  edge (80.5, 8.15)). The first tilted packet has zero exact-solid overlap with a 1 µm
  seating clearance; packet 2's front 2 mm overhangs the blade, and the blade's rear edge is
  the support line. The 10/25 tilted columns have zero overlap with the static assembly;
  tops are 54.98 / 132.97 mm, and the 25-stack top rear is at x ≈ −84.74 mm, 0.255 mm from
  the back wall. The earlier 61.67/139.66 mm values double-counted the packet-2 origin and
  are corrected in `cad_probe.json`.

### 1.3 Frozen presentation criteria

`projects/pocky/physics/acceptance.toml` (raw hash above) is frozen and **not edited by
M5a**. P0–P3 are gravity-only, so they do not evaluate `packet_exit` or
`packet_presentation`. M5b must bind every packet identity to that frozen file or a reviewed
extension before candidate evaluation. M5a's S0/gravity criteria are separate JSON files with
their own IDs and hashes.

---

## 2. Scope and boundaries

### 2.1 In scope (two bounded increments)

- A Pocky adapter through `Project.physics` / `Project.physics_with_options`, explicit
  assembly from `static_solids` + `moving_solids`, and the generic `run_assembly` path.
- Explicit convex collider recipes preserving the bore, exit, floor slot, local peg relief,
  pivot bore, separator gap and pin slots; fidelity probes/transits/coverage/critical
  surfaces plus a collider-vs-CAD clearance audit.
- Free baseline: free body (with shims), free lip, free chassis on a legitimate fixed
  analytic floor, jointed mechanism, equivalent spring, free packets. No hidden restraint.
- Static bearing-direction and support-margin checks.
- S0 at initial button fractions {0, 0.25, 0.5, 0.75, 1.0}, no actuation.
- P0 single-packet drop, P1 1→2, P2 10, P3 25 (parameter variant), all gravity-only with
  the actual assembly, each with an explicit settle phase and a post-settle measured window.
- Base/half-timestep convergence, same-runtime replay, overlays, report, focused tests, one
  full suite at the end.

### 2.2 Out of scope

- CAD redesign, support-seat/bracing (M6), mechanism/lip/blade redesign, threshold tuning.
- P4–P9 dispensing, manual input profiles, presentation events, pickup cycles.
- Editing `projects/pocky/physics/acceptance.toml`.
- Physical prints, bench measurements, calibration, or physical acceptance claims.
- Model/provider/effort/role/fallback changes; a security-reviewer gate.
- Rewriting accepted M0–M4 tests or generic behavior beyond §8.

### 2.3 Authorized implementation file surface (later turn)

Generic:

- `cadkit/physics/schema.py`: optional per-collider `friction` and `priority`.
- `cadkit/physics/scene.py`: emit geom friction/priority; no `filterparent` change.
- `cadkit/physics/runner.py`: friction/priority in physical inputs; scenario-vs-assembly
  timestep guard; assembly-options identity; contact watches for `contact_duration`.
- `cadkit/physics/scenario.py` / `evaluate.py` / `telemetry.py`: three new check kinds and
  their strict loading/evaluation/watch tracking.
- `cadkit/physics/support.py` (new pure geometry): bearing direction and support margin.
- `cadkit/cli.py`: one `cad physics run <project>/<model>` verb (not a second CLI module).
- `cadkit/project.py`: optional `physics_with_options` hook.
- `cadkit/physics/overlay.py`: optional camera/clip for cutaway evidence.

Project:

- `projects/pocky/physics/assembly.py`, `colliders.py`, `options.py`, `support.py`,
  `clearance_audit.py`, `report.py`, `scenarios/`, `s0_acceptance.json`,
  `gravity_acceptance.json`.
- `projects/pocky/__init__.py`: lazy `physics` and `physics_with_options` hooks.
- `docs/mujoco-m5a-report.md`, `projects/pocky/docs/physics-m5a.md`.
- `out/mujoco-m5a/**` evidence.

No other production file, CAD source, params file, test or configuration is edited.

---

## 3. Assembly model

### 3.1 Build convention (one convention, stated once)

**The runtime scene is always built at CAD button fraction 0.** The five S0 fractions are
initial joint coordinates written by the scenario reset phase; the moving parts are not
rebuilt per fraction. This keeps joint ranges and `springref` fixed and lets the runner's
allowed reset mechanism create the initial states.

`prototype_assembly(..., button_fraction=f)` remains available for the **static preflight and
tests** (exact-solid overlap checks at all five fractions), but the runtime adapter always
calls it with fraction 0. The spring visual/mass is at the installed 50.4 mm length and
translates rigidly with the rod; it is not re-compressed by the reset. Its colliders are
disabled (`contype=0`, `conaffinity=0`) and its mass is welded to the rod. That is a declared
rigid visual/mass approximation, not an elastic model.

### 3.2 Bodies, ownership and grouping

Explicit from `static_solids` + `moving_solids(..., compressed_length(0.0))`; never by
enumerating `model.build()`.

| Body | Parts | Joint | Role / assumption |
|---|---|---|---|
| `body` | `body`, `shim_04_a`, `shim_04_b` | free | Housing group. Shims welded: they sit on ledges and are captured by the lip feet. Declared rigid grouping; no double count. |
| `lip` | `lip` | free | Independent. Hook rails 0.15 mm from the body bars; do not weld. |
| `chassis` | `chassis`, `spring_seat`, `peg_pivot` | free | Base frame. Pivot peg welded to the chassis; not duplicated on the crank. |
| `crank` | `crank`, `peg_pusher` | hinge → `chassis` | Pivot at (−78, −8), +Z, q=0 at CAD fraction 0. Pusher peg welded to the crank. |
| `rod` | `rod`, `peg_button`, `spring` | slide → `chassis` | +X, q=0 at CAD fraction 0. Button peg welded to the rod. Spring visual/mass welded; see §3.1. |
| `pusher` | `pusher` | slide → `chassis` | +X, q=0 at CAD fraction 0. |
| `packet_01…` | one box each | free | 165 × 55 × 5.2 mm rigid box; separate bodies. |
| `floor_world` | one box | fixed to world, `fixture="analytic_fixture"` | Identity frame; the box collider is offset so its top is at z = −19.2 mm. Legitimate analytic floor, not a product body. |

Excluded: bench `dummy` and parked `shim_08`. Tests assert their absence and that every other
part appears exactly once.

### 3.3 Joints, stops and the contact loop

The CAD topology is a closed loop. The available schema is a forest with one hinge/slide per
body plus contact. MuJoCo **filters parent–child contacts by default**, and `scene.py` does
not disable that flag. Therefore:

- Mechanism↔chassis contacts (crank/boss, rod/guides, pusher/chassis, rod/stops) are
  **filtered** and represented by joints and joint limits. This is declared and tested.
- Sibling contacts (crank↔rod peg, crank↔pusher peg) and free-body contacts (body, lip,
  packets, floor) are **enabled**. The pin-in-slot loop is real.
- No `connect`, no fixed point, no slot-filling cylinder. `pose_at_phi` is used only for the
  initial CAD pose, reset coordinates and independent geometric checks.

Joint definitions:

| Joint | Kind | Range (SI) | Meaning |
|---|---|---:|---|
| `crank_phi` | hinge, +Z, anchor (−78, −8, −9.2) in the **crank body frame** (identity, so assembly coordinates) | −1.06…+0.01 rad | Guard just outside the 0…−1.0472 CAD swing, stop time constant 2 ms. The real stops are the rod limits. |
| `rod_x` | slide, +X | −0.023194…+0.0001 m | Home/forward stops derived from the CAD 0.1 mm flange/shoulder clearances. Stop time constant 2 ms. These limits represent the stop contacts that parent filtering removes. |
| `pusher_x` | slide, +X | −0.0005…+0.0505 m | **50 mm** stroke guard, stop time constant 2 ms. It must not become a fake mid-stroke stop. |

The button peg (Ø4, on `rod`) runs in the crank's radial stadium slot (width 4.6 mm, end
radii 19.000…24.094 mm). The pusher peg (Ø4, on `crank`) runs in the carriage's Y stadium slot
(width 4.6 mm, ends y 34.301…43.000 mm). Both are decomposed into side-wall boxes plus end
caps; peg shafts/heads are cylinders. The slot end 1 mm margins mean the pegs should not
reach the end caps in nominal motion; the caps are still colliders.

Spring: `SpringSpec` on `rod_x`, stiffness `k`, reference **+0.003 m** (q=0 at CAD rest, so
the installed 3 mm preload pushes +X). At f=1 the rod is reset to −0.023094 m, so the spring
force is `k × 0.026094`; the mechanism returns to the home stops. S0 at f>0 is therefore a
**spring-return transient**, not a held pose.

### 3.4 Mass, spring, friction and provenance

| Input | Nominal | Range / uncertainty | Provenance |
|---|---:|---|---|
| PETG density | 1.27 g/cm³ | printed infill unknown; solid upper bound | `derived`, datasheet |
| Packet mass | 7.0 g | 4.0…10.0 g | `assumed`; 10 g has no source, it is a sensitivity bound only |
| Packet dimensions | 165 × 55 × 5.2 mm | fixed proxy | measured thickness, params |
| Spring stiffness `k` | 0.5 N/mm | 0.2…1.0 N/mm | `assumed`: 12 × 14 mm × 5 mm × 1.2 mm PETG beams in series, E ≈ 2.0 GPa assumed; folds and modulus unverified |
| Spring reference | +3.0 mm | fixed by installed preload | derived from CAD |
| Damping | 0.5 N·s/m rod; 0.005 N·m·s/rad crank; 0.5 N·s/m pusher | 0.1…2.0 | `assumed` placeholder, not measured |
| PETG ↔ PETG friction | μ 0.40 | 0.25…0.60 | `assumed` |
| PETG ↔ wrapper friction | μ 0.30 | 0.15…0.60 | `assumed`; M7 ramp required |
| Wrapper ↔ wrapper friction | μ 0.30 | 0.15…0.60 | `assumed`; M7 two-packet ramp required |
| Floor friction | μ 0.50 | 0.30…0.80 | `assumed` analytic fixture |
| Contact compliance | 2 ms, damping ratio 1.0 | fixed for timestep studies | declared; equal to the 2·dt floor at 1 ms, above it at 0.5 ms |
| Solver | RK4, Newton, elliptic, 100 iterations | fixed | declared |

Friction/priority implementation:

- Add optional `friction: tuple[float,float,float] | None` and `priority: int = 0` to
  `ColliderSpec`; emit both on the geom.
- PETG geoms: priority 0, μ 0.40. Packet geoms: priority **1**, μ 0.30. Floor: priority 0,
  μ 0.50.
- MuJoCo uses the higher-priority geom's friction when priorities differ; packet↔PETG and
  packet↔packet therefore simulate 0.30, PETG↔PETG 0.40, PETG↔floor 0.50. A test reads the
  **effective `data.contact[i].friction`** for a mixed pair, not only `geom_friction`.
- With per-geom values, PETG↔wrapper and wrapper↔wrapper are the **same** packet parameter
  (0.30). Varying them independently requires explicit `<contact><pair>` elements, which this
  increment does not add; the M7 sensitivity must treat them as coupled and report that.
- Spring-rate sensitivity: S0 f=0 at k = 0.2 and 1.0 N/mm. Packet-mass sensitivity: P1/P2 at
  4.0 and 10.0 g where budget permits; otherwise load conclusions are INCONCLUSIVE. P3
  nominal only.

### 3.5 Collider recipes

All colliders are body-local boxes/cylinders. Counts are planning estimates; the recipe must
pass the declared fidelity contract.

| Body | Recipe (planning) | Voids / critical surfaces |
|---|---|---|
| `body` | ~22 boxes: floor split around the through-slot and the **local** f=1 peg relief; two side walls; front wall above z 9.20; back wall split into side bays plus a mid bay above the back notch; two ledges; two clip ribs; two lip bars; two ties; chamfer approximations. | Floor slot x −93.1…−35.1, y ±3.5; local relief x ≈ −57…−49, y 31.4…32.4, z −2.4…−0.01; back notch x −87.6…−84.95, z 0…4.4; exit x 85…88 above 9.20; bore x ±85, y ±30. **Convex hull forbidden.** |
| `chassis` | ~30 boxes: base plate; boss ring in two Z bands (bore 2.7 mm; head relief 4.4 mm below −15.55) by 8–12 sector boxes; home/forward stops + bridges; north/south guides and plinths; spring pocket floor/walls/steps; clip posts/teeth; artery/drops. | Pivot bore, spring pocket, clip geometry. No solid boss cylinder. |
| `lip` | ~15 boxes + nose cylinder: shelf, nose, blade, two cheeks, two feet, two risers/plates/rails/teeth. | Separator gap z 5.75…8.15; shelf top 0; hook rail/tooth clearances. R0.8 edge approximated and declared. |
| `crank` | ~15 boxes + peg cylinders: pusher arm, button arm split around the radial slot, inner/outer caps, hub ring sectors; pusher peg shaft/head. | Radial slot 19.000…24.094, width 4.6; pivot bore; hub. |
| `rod` | ~8 boxes + button peg: shaft, head lower/upper, flange, shoulder, pad, beam, web; peg shaft/head. | Pin hole occupied by its welded peg; guide clearance is a joint idealization. |
| `pusher` | ~6 boxes + bullnose: carriage west/east of the Y slot, south/north caps, neck, bullnose R2.1 axis Y, chamfer approximation. | Y slot 34.301…43.000, width 4.6; floor-slot/neck clearance; R2.1 contact face. |
| `spring_seat` | one box | none |
| `spring` | one mask-0 box for schema participation; visual mesh | no collision; equivalent joint spring only |
| pegs | 2 cylinders each | pivot head below the boss; pusher/button heads above their carriers |
| `packet_0N` | one box, half-extents 82.5 × 27.5 × 2.6 mm | rigid proxy |
| `floor_world` | one box | analytic floor |

Fidelity contracts on `body`, `chassis`, `lip`, `crank`, `rod`, `pusher`:

- Dense `ProbeSpec` grids (5 mm) through the bore, exit, floor slot, **local** peg relief,
  pivot bore, spring pocket and separator gap.
- `TransitSpec` for the pusher peg shaft/head path, button peg path and pusher neck; exact-CAD
  packet transit at z 0.1/2.6/5.1.
- `max_coverage_gap_mm = 0.5` for non-critical surfaces.
- `max_surface_deviation_mm = 0.02` on declared **planar critical surfaces**: body floor
  underside (z=−2.4), carriage top (z=−2.8), clip post inner faces, relief ceiling
  (z=−0.01), bullnose crest, slot walls, and the lip blade's top/rear support edge
  (z=8.15, x=80.5). The pivot bore is a probe only, not a 0.02 mm critical surface: 8–12
  sector boxes at r=2.7 deviate by ~0.09 mm, and the bore is parent-filtered from contact.
  These are the gaps S0 measures; a 0.2 mm tolerance would bias a 0.4 mm gap.
- A project `clearance_audit` computes collider-to-collider minimum distance for the critical
  pairs (body↔pusher 0.4 mm, body↔chassis 9.2 mm/0.05 clips, lip↔body 0.15 mm, lip↔shims
  0.05 mm, crank/pusher peg↔carriage 0.2 mm, rod/button peg↔crank slot 0.3 mm,
  body↔bullnose 0.027 mm, body↔peg/relief 0.19 mm, lip rail↔rod head 0.30 mm at rest /
  ≈0.25 mm after 0.05 mm lip settle) and compares it to the exact-CAD minimum. A mismatch
  >0.02 mm on a critical pair is `SCENE_INVALID`.
- The audit runs on the collider poses **after each of the five resets**, not only the
  fraction-0 build. It uses the compiled scene's `data.geom_xpos`/`geom_xmat` after the
  reset and the exact-CAD solids at the same fraction. This is what checks the two f=1-only
  gaps (pusher-peg head↔relief ceiling 0.19 mm; lip rail↔rod head 0.30/0.25 mm).
- `render_overlay` PNGs for each body plus cutaway/orthographic views of the support
  interface, slot chain and exit.

---

## 4. Static preflight (no MuJoCo)

Pure geometry, callable without the physics extra:

1. **Bearing direction.** Clip tooth underside +0.05 vs body rib top 0.00 at the measured
   patches → `retention_only_+Z`. A downward load separates rib from tooth.
2. **Support margin.** Body alone and body+lip+shims: COM, bearing hull, hull area, strip
   width, `com_inside`, signed margin, gravity moment. Expected strip 4.23 mm; margins
   −6.86/−4.54 mm; moment 9.4 mN·m (body) / ≈6.5 mN·m (group).
3. **Exact-solid overlap inventory** for every body group at all five fractions. Expected
   zero; any non-zero volume is `SCENE_INVALID`.
4. **Packet seat inventory.** Tilted seats, 10/25 columns, zero overlap; the 25 top-rear
   clearance is recorded.
5. **Collider-vs-CAD clearance audit** on the critical pairs.

Outputs: `out/mujoco-m5a/static_preflight.json`, `cad_probe.json`, plus a report table.

---

## 5. Packet seating and P0–P3

### 5.1 Derived tilted seat

The blade underside is z=5.75 and its top z=8.15; its rear edge is x=80.5. Packet 2 cannot
be horizontal at pitch 5.2 (256.446 mm³ overlap). The static seat a rigid box takes is a
**1.0368° tilt** whose bottom line passes through the bottom packet's rear top (−82.5, 5.2)
and the blade's rear edge (80.5, 8.15). Packet 2's front 2 mm overhangs the blade; the blade
rear edge is the front support line. Packets 3…N stack on packet 2 along the tilted normal.

- 10-packet top ≈ 54.98 mm (body top 72 mm).
- 25-packet top ≈ 132.97 mm (25-capacity body top 150 mm).
- 25-stack top rear x ≈ −84.74 mm (0.255 mm from the back wall); the stack is close to the
  wall and may contact during settle. That is evidence, not a reason to shift it silently.
- The "0.55 mm" value is the blade underside clearance above the bottom packet; packet 2's
  bottom is **2.95 mm** above packet 1 at the rear. Do not confuse the two.

The plan uses this near-static tilted seat rather than a 2.95 mm drop of the whole stack.
Both are defensible; the tilted seat is chosen to avoid an artificial impact and to match
the line support. The implementation must translate the **already seated** packet-2 box along
the tilted normal for packets 3…N; it must not add the packet-2 origin twice (an earlier
probe did, reporting tops 6.69 mm too high). The corrected probe gives 54.98 / 132.97 mm and
every packet origin/rotation is recorded in `cad_probe.json`. A 0.001 mm (1 µm) numerical
seating clearance removes a 9.1e−5 mm³ tangential overlap at the blade edge; that clearance
is below print tolerance and is recorded, not a hidden separation. The initial zero-overlap
check is a gate. If the implemented exact check finds any larger overlap, the seat is
corrected by at most 0.01 mm and recorded; no larger hidden separation is allowed.

### 5.2 Cases

All cases use the actual free assembly. No case fixes the body or chassis. No case sets
packet qpos after t=0.

Reset joint coordinates (the scene is built at fraction 0; these are the only positions the
runner may write, and they are initial states only). **Every value must be derived at runtime
from the actual CAD helpers**, not interpolated:

```python
link = linkage_from(p)
pose = pose_at_phi(link, phi_for_button_fraction(link, f))
crank_phi = pose.phi - link.phi0          # rad
rod_x = -pose.button_travel / 1000.0      # m
pusher_x = (pose.face_x - rest.face_x) / 1000.0  # m; equals pin x displacement
```

Quarter button fractions do **not** imply linear pusher travel: `phi_for_button_fraction`
is linear in the cotangent of phi, while the pusher follows `radius*cos(phi)`. The table is
the expected result of those helpers, not a second formula:

| Fraction | `crank_phi` (rad) | `rod_x` (m) | `pusher_x` (m) | Pusher displacement (mm) |
|---:|---:|---:|---:|---:|
| 0.00 | 0.000000000 | 0.000000000 | 0.000000000 | 0.000000 |
| 0.25 | −0.242563874 | −0.005773503 | 0.011132495 | 11.132495 |
| 0.50 | −0.523598776 | −0.011547005 | 0.025000000 | 25.000000 |
| 0.75 | −0.804633677 | −0.017320508 | 0.038867505 | 38.867505 |
| 1.00 | −1.047197551 | −0.023094011 | 0.050000000 | 50.000000 |

The wrong linear pusher resets 12.5 / 37.5 mm at f=0.25/0.75 differ by 1.367505 mm, which
exceeds the 0.3 mm nominal pin/slot side clearance; they are a negative test, not an
alternative.

**Compiled-transform cross-check (all five fractions).** After compile and reset, read the
compiled body transforms (or `data.xpos`/`data.xquat` at the reset boundary) and verify:

- crank rotation relative to the fraction-0 pose equals `crank_phi` within 1e−9 rad;
- rod translation along X equals `rod_x` within 1e−6 m;
- pusher translation equals `pusher_x` within 1e−6 m, and its sign is +X;
- the pusher peg/face station matches the CAD helper pose within 1e−6 m.

The check runs for **all five** fractions. Static CAD-only overlap at the helper pose is not
enough: it does not prove the independently specified runtime reset. A negative test injects
the linear 12.5/37.5 mm pusher resets and must fail the compiled cross-check by ≥1.367 mm.
A second negative injects the sign-flipped pusher reset and must fail. The compiled check is
in addition to, not a replacement for, the exact-CAD zero-overlap gate.

| Case | Initial content | Phases | Measured window |
|---|---|---|---|
| S0 f=0/0.25/0.5/0.75/1.0 | No packets; joint reset coordinates from the CAD fraction | reset; settle 3.0 s; hold 0.5 s (zero input) | post-settle hold |
| S0 spring low/high | No packets, f=0, k=0.2/1.0 N/mm | same | post-settle hold |
| S0 half-dt | No packets, f=0, dt=0.5 ms | same | post-settle hold |
| P0 | One packet at x=−2.4 mm (window −2.5…−2.0), z=30 mm; 0.1 mm rear and 0.4 mm front clearance | reset; settle/fall 2.0 s; hold 0.5 s | early free fall and post-settle |
| P1 | One packet; then two packets at the tilted seat | reset; settle 2.5 s; hold 0.5 s | post-settle |
| P2 | 10 packets at the tilted seat | reset; settle 3.0 s; hold 0.5 s | post-settle |
| P3 | 25 packets at the tilted seat; `capacity_test=25` variant | reset; settle 4.0 s; hold 0.5 s | post-settle |

**Settled-start choice:** P1–P3 begin with the loaded assembly at the CAD pose and include an
explicit settle phase; the measured window starts after it. No ideal CAD pose is restored
after settling. Each P report compares its post-settle housing pose with the S0 f=0 checkpoint
(body/chassis relative pose and body drop), so a different housing state is visible rather
than hidden. This is the chosen interpretation of "actually settled" for gravity-only
cases, because the packet bodies change the state layout: a no-packet S0 checkpoint cannot be
loaded into a packet scene without a named shared-state import. S0 checkpoints are saved for
M5b, where P4+ reuse the P2 body set and an import can be added with matching layout. If Codex
requires a literal cross-run import for P0–P3, that is a separate bounded generic feature and
M5a-2 is blocked at that gate rather than faked.

The 25-packet case is a **parameter variant** (`capacity_test=25`) that raises the tube top to
150 mm by the existing `_tube` formula. No source CAD or `params.toml` is edited; the option
is hashed. P3 conclusions apply to the parametric 25-tube, not a printed prototype (none
exists).

### 5.3 S0 criteria as generic, bound, replayable checks

S0 is evaluated by the accepted generic evaluator, not a post-run sidecar. Three small generic
check kinds are added. Frames are body-to-world (the schema `Frame` maps local points into
assembly/world coordinates), so the relative transform is **inverse(T_a)·T_b**:

```text
T_a = (R_a, p_a), T_b = (R_b, p_b)          # body-to-world
T_rel(t) = inverse(T_a(t)) · T_b(t)
p_rel(t) = transpose(R_a(t)) · (p_b(t) - p_a(t))
R_rel(t) = transpose(R_a(t)) · R_b(t)

Δp = p_rel(current) - p_rel(initial)
ΔR = R_rel(current) · transpose(R_rel(initial))
θ  = 2·acos(clamp(|w|, 0, 1))                # w = scalar part of unit quaternion of ΔR
```

`p_rel(t)` uses **body_a's attached local material axes at time t**. Those axes rotate with
body_a, so an exactly rigid pair that rotates together has constant `p_rel` and `Δp=0`.
Freezing `R_a(initial)` and subtracting world separation vectors is a different metric and is
forbidden: it reports drift for common physical rotation over time. `Δp` is the change of the
attached-local relative position, not a world-separation difference.

| Kind | Fields | Semantics |
|---|---|---|
| `relative_pose` | `body_a`, `body_b`, `phase`, `window` (`end` or `max_over_phase`), `maximum` (m), `max_rotation_rad` | `‖Δp‖` and `θ` from the `initial` boundary to `phase`, using the formulas above. `max_over_phase` evaluates every sample in the phase and reports the worst sample time and value. |
| `relative_translation` | `body_a`, `body_b`, `from_phase`, `to_phase`, `axis` (x/y/z), `frame` (`body_a` or `world`), `lower`, `upper` (m), `window` | For `frame=body_a`, project `Δp` on the axis of body_a's attached local axes (`Δp` is computed from `p_rel(t)` at each time, not by freezing `R_a(initial)`). For `frame=world`, use `Δp_world = (p_b1-p_a1) - (p_b0-p_a0)` and project on the world axis. Both lower and upper are required; the signed value must lie inside them. Report the signed value and, for z, the positive downward drop `max(0, -Δrel_z)`. |
| `contact_duration` | `body_a`, `body_b`, `force_threshold_n`, `maximum` (s), `window` | longest continuous interval in which the **sum of normal forces over all geom pairs between the two bodies** exceeds the threshold; zero contact is a valid measurement. |

Invariance and sign rules:

- **Time-varying common physical motion.** If both bodies undergo the same rigid
  translation/rotation over time (constant `T_rel`), `p_rel(t)` is constant and `Δp=0`.
  Numeric regression (mm): initially `R_a=I`, `p_a=(0,0,0)`, `p_b=(1,0,0)`; both bodies then
  rotate 90° about world Z, giving `R_a=R_z90`, `p_a=(0,0,0)`, `p_b=(0,1,0)`. True
  `p_rel=(1,0,0)` at both times, so `Δp=(0,0,0)`. The forbidden initial-frame/world-separation
  formula gives `(-1,1,0)` mm, norm **1.414214 mm**; the test must reject that value.
- **Fixed coordinate transform.** A constant `G` applied to the entire trajectory leaves
  `T_rel`, `Δp` and `ΔR` invariant: `inverse(G·T_a)·(G·T_b)=inverse(T_a)·T_b`. This is a
  different test from time-varying common physical motion; both are required.
  `frame="world"` translation is **not** claimed invariant under a common rotation, because
  gravity fixes the world frame.
- Counterexample test: A at (1,0,0) mm, B at (1,1,0) mm, both yaw 90°. Correct
  `p_rel=(1,0,0)` mm. The wrong `T_b·inverse(T_a)` order gives (0,1,0) mm and, after a common
  90° world yaw, (−1,0,0) mm — a false 1.414 mm relative motion. The test must reject the wrong
  order.
- A true-relative-motion test moves B along A's local +X and asserts `Δp=(d,0,0)` in A's
  attached local axes; superimposing a time-varying common translation/rotation must leave the
  `d` detection unchanged. A no-motion negative must give zero.
- `body_drop` remains a **separate world-frame** definition: `frame="world"`, `axis="z"`,
  `lower=-0.0001 m`, `upper=+0.0001 m`, where
  `Δrel_z=(z_body1-z_chassis1)-(z_body0-z_chassis0)`. A 0.4 mm fall gives
  `Δrel_z=-0.0004`, below the lower bound, and fails. A 0.4 mm upward motion gives `+0.0004`,
  above the upper bound. The report also records positive downward drop `max(0,-Δrel_z)`. A
  signed value compared only against an upper bound is explicitly forbidden as a drop
  predicate.

The summed force is the per-step contact metric. One box-on-box contact can produce several
contact points; applying the threshold per point would let a sustained distributed load pass.
`telemetry` tracks watched body pairs (from the acceptance checks) every step; `evaluate`
reads the tracked duration. Replay rebuilds the same watches from the hash-verified
acceptance and recomputes the checks. There is no `physics_evaluate` sidecar and no status
overwrite.

Frozen S0 checks (`projects/pocky/physics/s0_acceptance.json`):

| Check | Predicate | Rationale |
|---|---|---|
| `body_pose_retained` | body/chassis relative translation ≤0.20 mm; rotation ≤0.20° at hold | 50% of the 0.40 mm gap and predicted 0.4° arrest |
| `body_drop` | body/chassis world-z relative change initial→hold within [−0.10 mm, +0.10 mm]; positive downward `max(0,−Δz)` ≤0.10 mm | 25% of the 0.40 mm gap; both fall and lift fail |
| `body_on_pusher` | `body`↔`pusher` summed force above 0.0715 N (5% of the 145.89 g hanging group) ≤0.20 s | principal structural predicate; body-only 5% would be 0.0684 N |
| `body_on_rod`, `body_on_crank` | same threshold/duration | the body must not lean on any moving part; the welded pegs are included in those bodies |
| `lip_on_pusher`, `lip_on_rod`, `lip_on_crank` | duration above 0.0715 N ≤0.20 s | the hanging group includes the lip |
| `chassis_grounded` | chassis/floor relative translation ≤1 mm, rotation ≤0.20° at hold | floor contact is real; slide/lift is reported |
| `settled` | body and lip speed ≤1 mm/s at hold | final 0.5 s quiescence |
| `penetration` | peak ≤0.2 mm | validity, packet-scale |
| validity | `max_penetration_m=0.0002`; warnings invalidate | no invalid scene as a product verdict |

Peg-specific checks are intentionally absent: `peg_pusher` is welded to `crank` and
`peg_button` to `rod`, so a separate body pair cannot be distinguished. The crank/rod checks
cover them.

P0–P3 acceptance (`projects/pocky/physics/gravity_acceptance.json`) uses the same generic
kinds:

- `penetration_bound` 0.2 mm and validity `max_penetration_m=0.0002`.
- `body_speed` body/lip at hold ≤1 mm/s; packet speeds at hold ≤10 mm/s.
- `relative_pose` chassis/floor at hold (≤1 mm, ≤0.20°).
- `contact_duration` body/lip on pusher, rod and crank ≤0.20 s (the housing must not be
  loaded by moving parts).
- `relative_pose` packet_01/body and the top packet/body at hold: rotation ≤5° (a collapsed
  stack exceeds this), with the P0 packet ≤2°. The translation field is a declared 20 mm
  diagnostic bound, explicitly non-binding; the report records the actual value, and a stack
  that slides 20 mm is already visible in speeds/penetration/moving-part contacts.
- Per-packet positions, tilts, support contacts and penetrations are report-only metrics from
  `summary.json`/`trace.csv`/`contacts.csv`.
- P0 free-fall acceleration (9.81 ± 5% before first contact) is a **report-only diagnostic**
  computed from `trace.csv`; no check kind measures acceleration, and the plan does not invent
  one.

### 5.4 Final 0.5 s hold and replay semantics

- The `hold` phase is exactly 0.5 s of real zero input. Every S0/P scenario sets
  **`sampling_interval_s = timestep_s` explicitly** (0.001 s at base, 0.0005 s at half dt);
  the generic 0.002 s default is not used. The full sampled hold is retained in
  `trace.csv`/`states.npz`. Trace, state and contact-row budgets are sized from the total
  steps and the per-sample contact count; a budget overflow invalidates the run rather than
  silently sampling less.
- Checks marked `window="max_over_phase"` evaluate every hold sample. `body_pose_retained`,
  `body_drop`, `chassis_grounded`, packet relative poses and `body_speed` use the worst sample
  in the hold, not just the end boundary. `contact_duration` uses the per-step summed force.
  Results report the worst sample time, worst value, and end-boundary value.
- Near-threshold bands are applied to the worst sample. A result that changes status between
  base and half timestep, or within one sample interval, is `INCONCLUSIVE`.
- Replay re-steps from the saved verified state using the same scenario, acceptance and
  options locks, the same contact/stop compliance and the same sampling. It recomputes the
  hold-window maxima and per-step contact durations and compares worst-sample times/values
  within one sample interval and the declared numeric tolerance. A replay that cannot
  reproduce the sampling or a near-threshold status is `INCONCLUSIVE`, never PASS. Sparse
  `contacts.csv` rows are display evidence only; they are not the gate.

A near-threshold result within 20% of a threshold is `INCONCLUSIVE`, not PASS. A failed
scene/initial overlap is `SCENE_INVALID`/ERROR, never a product FAIL.

**Prediction, recorded before running:** the body has no downward chassis seat; it should
drop 0.4 mm onto the pusher carriage, produce sustained body-on-moving-part contact, and fail
`body_drop`/`body_on_pusher`. At f>0 the spring return is a transient; the final settled state
is the f=0 support state. A larger observed angle is not by itself a scene bug, and the scene
is not tuned to reproduce 0.4°.

The S0 report also records, as diagnostics only: contact pairs/forces/durations, body drop,
relative pose, chassis floor load, return time, peak speeds, and the pusher-peg-head/lip-rail
contacts that can arrest the body at f=1.

---

## 6. Implementation increments

### 6.1 M5a-1 — first bounded increment (recommended)

**Adapter + scene/fidelity + static preflight + S0 + checkpoints.**

1. Generic: per-collider friction/priority; `cad physics run` with hashed options; scenario
   timestep guard; `relative_pose`/`relative_translation`/`contact_duration` checks, signed
   bounds, `max_over_phase`, and telemetry watches; `cadkit.physics.support`; tests.
2. Project: assembly at fraction 0, colliders, options, support, clearance audit, overlays;
   **reset derivation and compiled-transform cross-check at all five fractions** (with the
   linear/sign negatives); S0 scenario JSON for five fractions + spring low/high + half-dt;
   S0 acceptance JSON; `PROJECT` hooks.
3. Run export, static preflight, five S0 cases, spring sensitivity, half-dt, replay S0 f=0,
   overlays; write `docs/mujoco-m5a-report.md` with S0 status and saved checkpoints.
4. Focused tests and one full suite.

Establishes: the free housing/chassis/lip and real contact paths; the mechanism contact loop
under gravity/preload; whether S0 fails for the reported support reason; numerical validity
separated from product status; complete settled checkpoints.

Does **not** establish: packet/stack behavior, 25-packet readiness, dispensing or physical
reliability. P0–P3 are deliberately the second increment because they add packet bodies and
seating geometry; running them before S0 is credible would stack conclusions on an
unvalidated housing.

### 6.2 M5a-2 — P0–P3

P0 one-packet drop, P1 1→2, P2 10, P3 25-capacity; tilted seating; post-settle windows;
packet-mass sensitivity where bounded; representative half-dt P3; replay P3; final report
and evidence index.

Establishes: gravity stack readiness and load paths for 1/2/10/25 packets under declared
inputs. Does **not** establish press/ejection, return, presentation, wrapper behavior,
physical reliability or the printed 25-tube.

### 6.3 Always INCONCLUSIVE in M5a

Packet mass, wrapper↔PETG and wrapper↔wrapper friction, spring rate/damping, guide/slot
friction, clip force/preload, wrapper flexibility and blade engagement, printed 25-tube,
print tolerance/infill, and any physical prototype claim. M7 remains unverified.

---

## 7. Acceptance criteria

M5a-1 is complete only when observed:

1. `cad physics export pocky/prototype` PASSes; inventory/hash recorded; `dummy`/`shim_08`
   absent and every other part once.
2. Static preflight reports retention-only bearing, margins, zero exact overlap at five
   fractions, zero tilted-seat overlap, and the collider/CAD clearance audit within 0.02 mm.
3. Fidelity contracts pass; a deliberately hulled body and a slot-filled crank are rejected.
4. The five reset coordinates are derived from the CAD helpers and the **compiled** transforms
   match at all five fractions; the linear 12.5/37.5 mm and sign-flipped pusher negatives are
   rejected by at least 1.367 mm.
5. The relative-pose check passes the A/B yaw-90 counterexample, the time-varying common
   physical rotation zero-drift case (old formula 1.414214 mm rejected), fixed-coordinate
   invariance and true/no-motion negatives; the drop predicate fails both a 0.4 mm fall and a
   0.4 mm lift under the signed world-z bounds.
6. Five S0 cases complete all phases; each scenario declares
   `sampling_interval_s = timestep_s`, hold checks use the full 0.5 s every-step window
   (`max_over_phase`), checks are hash-bound and replayed; validity and product status are
   separate; the result is PASS/FAIL/INCONCLUSIVE truthfully.
7. Spring low/high and half-dt S0 runs keep fixed compliance/friction/inputs/seed; status
   changes or near-threshold metrics are INCONCLUSIVE.
8. S0 f=0 replay reproduces the checks, worst-sample times/values and contact durations within
   one sample interval and the declared tolerance.
9. Overlays show CAD plus contrasting colliders, including cutaway/orthographic support,
   slot and exit views.
10. Focused tests pass; full suite once; no accepted test rewritten to hide a failure.
11. Before/after manifests show only authorized changes; CAD/params/exports/frozen acceptance
    unchanged.
12. `docs/mujoco-m5a-report.md` states commands, hashes, statuses, failures and unmodelled
    inputs; no physical claim.

M5a-2 adds P0–P3 with the same discipline and a credible product FAIL if observed.

---

## 8. Concrete APIs and ownership

### 8.1 Generic additions

```python
# schema.py
@dataclass(frozen=True)
class ColliderSpec:
    ...
    friction: tuple[float, float, float] | None = None
    priority: int = 0

# scenario.py CheckSpec fields
max_rotation_rad: float | None = None
axis: Literal["x", "y", "z"] | None = None
frame: Literal["body_a", "world"] | None = None
lower: float | None = None
upper: float | None = None
force_threshold_n: float | None = None
window: Literal["end", "max_over_phase"] = "end"
# kinds: relative_pose, relative_translation, contact_duration
# relative_translation requires lower+upper; relative_pose uses maximum+max_rotation_rad.
# body_speed gains window="max_over_phase"; its existing end semantics stay the default.
# Δp = p_rel(current)-p_rel(initial); p_rel(t)=R_a(t)^T(p_b(t)-p_a(t)); never freeze R_a(initial).
# frame="world" is used only for the separately defined signed world-z drop.

# support.py
@dataclass(frozen=True)
class SupportMargin:
    hull_area_mm2: float
    strip_width_mm: float
    com_inside: bool
    com_margin_mm: float
    gravity_moment_nm: float

def support_margin(com_xy_mm, patches_xy_mm, weight_n) -> SupportMargin: ...
def bearing_carries(load_direction, contact_normal) -> bool: ...

# project.py
physics_with_options: Callable[[str, Any, Mapping[str, Any]], Any] | None = None
```

```python
# cli.py
# cad physics run <project>/<model> --scenario PATH --acceptance PATH
#     [--options PATH] [--params PATH] [--set KEY=VAL ...] [--out DIR]
```

The run verb resolves/loads with existing helpers, reads a bounded strict TOML options file,
copies that file into the run directory as `assembly_options.lock.toml` with its raw SHA256,
calls `physics_with_options` (fallback `physics`), calls `run_assembly`, writes a fresh
`out/<project>/<model>/physics/<scenario_id>/<run-id>/`, and prints/exits with the existing
status codes. Options and their SHA256 are recorded in `summary`/`manifest` and compared by
replay. The scene hash covers geometry, mass, spring and timestep; the options hash covers
the explicit run choices.

Guards:

- `cad physics run` requires `scenario.timestep_s` to be present and equal to
  `spec.timestep_s`; a null scenario timestep is rejected for project runs. This is stricter
  than the generic fixture path, where the fixture supplies the timestep.
- Friction/priority values are finite, non-negative and in `physical_inputs`.
- `support_margin` treats collinear patches as a line and a lone point as degenerate.
- `relative_translation` with `frame="world"` requires `axis="z"`; the loader rejects any
  other world axis. World-frame translation exists only for the signed gravity drop, not for
  general relative-motion checks.
- `contact_duration` watches are declared; replay rebuilds them from the acceptance lock.
- `filterparent` stays at MuJoCo's default; the plan does not disable it.

### 8.2 Project APIs

```python
# projects/pocky/physics/assembly.py
def prototype_assembly(p, *, button_fraction=0.0, packets=0,
                       packet_mass_kg=0.007, timestep_s=1e-3,
                       capacity=None, spring_stiffness_n_m=500.0) -> AssemblySpec: ...

# options.py: strict option validation + defaults
# support.py: clip_connections, static_preflight
# clearance_audit.py: collider-vs-CAD critical-pair distances
# report.py: S0/P tables from summary/contacts/trace
```

Scenario/acceptance files:

- `scenarios/s0_f000.json` … `s0_f100.json`, `s0_spring_low.json`, `s0_spring_high.json`,
  `s0_half_dt.json`, `p0.json`, `p1a.json`, `p1b.json`, `p2.json`, `p3.json`. Each sets
  `sampling_interval_s` equal to its `timestep_s` (0.001 base, 0.0005 half-dt) and declares
  budgets sized for every-step rows plus the expected contact rows; no scenario relies on the
  0.002 s default.
- `s0_acceptance.json`, `gravity_acceptance.json` (generic schema; hashes frozen before
  runs).
- `options/s0_half_dt.toml`, `options/s0_spring_low.toml`, `options/s0_spring_high.toml`,
  `options/p0.toml` … `options/p3.toml` (packets/mass/capacity/timestep/spring).

The five reset states are in the scenario JSON (`initial` for `crank_phi`, `rod_x`,
`pusher_x`); the adapter does not rebuild per fraction.

Ownership: one generic owner (schema/scene/runner/CLI/checks/support) and one project owner
(adapter/colliders/options/preflight/scenarios/report). The reviewer is read-only.

---

## 9. Verification plan

```bash
/Users/daniel_l_newman/.local/bin/uv run cad physics export pocky/prototype \
  --out out/mujoco-m5a/export

/Users/daniel_l_newman/.local/bin/uv run cad physics run pocky/prototype \
  --scenario projects/pocky/physics/scenarios/s0_f000.json \
  --acceptance projects/pocky/physics/s0_acceptance.json \
  --out out/mujoco-m5a/s0_f000

/Users/daniel_l_newman/.local/bin/uv run cad physics run pocky/prototype \
  --scenario projects/pocky/physics/scenarios/s0_half_dt.json \
  --acceptance projects/pocky/physics/s0_acceptance.json \
  --options projects/pocky/physics/options/s0_half_dt.toml \
  --out out/mujoco-m5a/s0_half_dt

/Users/daniel_l_newman/.local/bin/uv run cad physics replay out/mujoco-m5a/s0_f000 \
  --out out/mujoco-m5a/replay_s0_f000
```

Half timestep: assembly `timestep_s=5e-4`, scenario declares 5e-4, contact/stop compliance
2 ms, friction/priority, spring, packet mass, initial fractions and seed unchanged. The guard
rejects a mismatch.

Focused tests:

- `tests/test_cadkit_physics_support.py`: margin/hull/line degeneracy, bearing direction,
  negative patch.
- `tests/test_cadkit_physics_friction_priority.py`: validation, XML, effective
  `data.contact.friction` for mixed pairs.
- `tests/test_cadkit_physics_checks_s0.py`: `relative_pose`/`relative_translation`/
  `contact_duration` on synthetic boundaries/contacts; the A/B yaw-90 counterexample gives
  `p_rel=(1,0,0)` and rejects the wrong order; the numeric rigid-pair common physical rotation
  over time gives `Δp=0` (old initial-frame/world-separation formula 1.414214 mm rejected);
  fixed world-coordinate transform invariance; a true relative motion along A's local +X with
  superimposed common motion, and a no-motion negative; signed world-z drop cases (0.4 mm down
  and 0.4 mm up both fail [−0.10,+0.10] mm); `frame="world"` with x or y axes is rejected;
  zero contact PASS; max-over-hold semantics;
  near-threshold INCONCLUSIVE; replay recomputation within one sample interval.
- `tests/test_cadkit_physics_cli_run.py`: fake project hook/options, missing hook, unknown
  model, timestep mismatch, status codes; no Pocky names.
- `tests/test_pocky_physics_assembly.py`: inventory, masses, grouping, pusher stroke 50 mm,
  exact reset values derived from `phi_for_button_fraction`/`pose_at_phi` at all five
  fractions, compiled-transform cross-check at all five (crank/rod/pusher translations),
  negative linear 12.5/37.5 mm pusher resets and sign-flipped pusher reset rejected, all five
  fractions zero exact-CAD overlap, spring, tilted 10/25 seats, no duplicate pegs; every S0/P
  scenario declares `sampling_interval_s = timestep_s` and budgets large enough for
  every-step rows plus expected contact rows.
- `tests/test_pocky_physics_colliders.py`: probes/transits/coverage, local relief, boss bore,
  slots, bullnose, negative hull/slot-filled cases, clearance audit.
- One short real MuJoCo smoke (compile + a few S0 steps) to prove the contact loop runs; the
  full S0 evidence is CLI runs, not unit tests.

Then `uv run pytest tests -q` once. Existing tests must not be edited to pass.

Evidence under `out/mujoco-m5a/`:

```text
before-manifest.json            # planning evidence (currently under out/mujoco-m5a-planning/)
after-manifest.json
cad_probe.json
static_preflight.json
export/{scene.xml,report.json,assets/}
s0_f000…s0_f100/{summary.json,report.md,states.npz,checkpoints.npz,contacts.csv,trace.csv}
s0_spring_low, s0_spring_high, s0_half_dt
p0, p1a, p1b, p2, p3, p3_half_dt
replay_s0_f000, replay_p3
overlays/*.png
```

`docs/mujoco-m5a-report.md` summarises commands, hashes, statuses, load paths, failures and
unmodelled inputs. `docs/mujoco-m5a-plan-review.md` records planning review separately.

---

## 10. Risks and unresolved decisions

| Risk | Why it matters | Mitigation / honest limit |
|---|---|---|
| Pusher stroke | Was 23.094 mm in the first draft; actual 50 mm. A wrong range errors or fakes a mid-stroke stop | 0…0.0505 m guard; test `pose_at_phi(phi1)−pose_at_phi(phi0)` = 50 mm |
| Quarter-stroke resets | Linear interpolation gives 12.5/37.5 mm; CAD gives 11.1325/38.8675 mm, a 1.3675 mm error above the 0.3 mm slot clearance | Derive every reset from CAD helpers; compiled-transform cross-check at all five; linear/sign negatives |
| Relative transform change | Freezing `R_a(initial)` and subtracting world separations reports 1.414214 mm drift for a rigid pair rotating together | `Δp=p_rel(current)−p_rel(initial)` with attached local axes; numeric common-rotation zero-drift, true-motion and fixed-coordinate tests |
| Drop sign | A signed −0.4 mm fall would pass an upper-only bound | World-z signed lower/upper bounds plus positive downward drop; down/up negative cases |
| Hold sampling | End-boundary-only checks do not observe the full 0.5 s | `max_over_phase` at every step; replay recomputes worst sample/durations within one interval |
| Closed pin-in-slot loop | 0.3 mm clearance, three bodies, two sibling contacts; chatter/false jam | Real boxes/cylinders, slot decomposition, contact/warnings, half-dt. If it cannot settle, S0 is INCONCLUSIVE, not tuned |
| Parent-child filtering | Crank/rod/pusher cannot contact the chassis; stops are limits | Declared; stop limits derived from CAD; mechanism↔chassis contact conclusions INCONCLUSIVE |
| Joint Z gaps | The designed 0.4+0.4 mm cascade is removed by slides | Body drop and rotation are lower bounds; report the idealization |
| Body floor local relief | A long strip would remove real floor/wall; a box would collide with the peg head | Local notch, probes/transit, exact overlap, clearance audit |
| Boss/bore | A solid boss cylinder fills the pivot bore/head relief | Two-band ring sectors; probes; negative test |
| Packet seating | Horizontal pitch overlaps 256 mm³; a 2.95 mm drop would impact the stack | Tilted 1.0368° seat, zero-overlap gate, ≤0.01 mm correction; report the 2 mm overhang and 25-stack wall clearance |
| Fidelity tolerance | 0.5 mm coverage / 0.2 mm deviation can bias a 0.4 mm gap | 0.02 mm critical planar surfaces + collider-to-CAD clearance audit |
| Friction combine | Equal-priority max would make packet↔PETG 0.40 | Packet priority 1; effective contact-friction test |
| Options routing | Hook signature cannot carry packets/mass/spring/timestep | Hashed options file + `physics_with_options`; recorded/compared |
| S0 binding | A sidecar after `manifest.json` is unbound and unreplayed | Generic check kinds, acceptance lock, replay recomputation |
| Settled P start | P1–P3 start loaded at CAD pose | Explicit settle phase; measured window post-settle; cross-run import deferred to M5b (same body set) |
| Contact-row budget | 25 packets exceed `max_trace_rows×16` | Size budgets per scenario; oversize invalidates, not truncates |
| No Git | Loss/unrecorded change | Before/after SHA256 manifests; no original CAD/params/export edits |

Unresolved decisions for Codex:

1. Accept the three generic S0 check kinds (recommended) rather than a project sidecar.
2. Accept per-collider friction + priority (recommended) rather than one global friction.
3. Accept the tilted 1.0368° packet seat and the 0.255 mm 25-stack wall clearance.
4. Accept `capacity_test=25` as the P3 geometry, or mark P3 blocked.
5. Accept the post-settle interpretation for P1–P3, or require a cross-run import (blocked
   gate until that generic feature is authorized).
6. Approve the S0 thresholds in §5.3 before implementation.
7. If the configured reviewer is unavailable, block the review gate; no substitute.

---

## 11. Approval and next gate

This plan is submitted for Codex planning review. An approving review is **not**
implementation authorization. Codex must inspect the plan, the review, the before/after
manifests and evidence, record one bridge decision, and—if acceptable—issue a **separate**
implementation operation for M5a-1 through the existing bridge authorization.

Until then: no product/test/harness/config/service edit, no CAD export, no test run that
writes product outputs, no implementation, no physical claim. The cancelled M5a attempt
`op_0mvitq0qz27686f5fdbcec231` is not reused or accepted; cumulative 19 operations / 7
remediation cycles remain historical.
