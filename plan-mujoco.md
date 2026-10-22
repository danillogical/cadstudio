# Plan — MuJoCo Physics Simulation for cadstudio

**Status:** Planning only — implementation not authorized by this document.  
**Target:** `cadstudio` (Python, `build123d`, `uv`; multi-project CAD workspace).  
**New capability:** Optional, headless, reproducible rigid-body physics testing that agents can use to revise parametric CAD designs before printing.  
**Initial validation project:** The existing Pocky packet dispenser; the physics infrastructure must remain project-agnostic.  
**Owner's immediate problem:** A mechanism animated correctly and parts printed, but gravity-dependent physical operation failed. A kinematic animation is not evidence of successful gravity feeding.

> **Repository access note:** This plan draws on cadstudio conventions established in prior work (`cadkit/`, `projects/<name>/`, `out/<project>/<model>/`, CLI selection `<project>/<model>`). The current local checkout and `CLAUDE.md` were not available for direct inspection while drafting. **M0 must inspect them and reconcile paths/names before writing code**; preserve existing commands and do not create a second competing CLI. No files in the local checkout were modified by this plan.

## 1. Goal and success definition

Enable this iterative loop:

```
Parametric build123d model + explicit physics metadata
        │
        ▼
Validate solids, print clearances, transforms, units
        │
        ▼
Generate MuJoCo model (MJCF) + visual and collision geometry
        │
        ▼
Run scripted gravity / contact / actuator scenarios HEADLESS
        │
        ▼
Capture measurements + classify PASS / FAIL / INCONCLUSIVE
        │
        ▼
Agent changes only permitted CAD parameters / mechanism choices
        │
        └──────► regenerate, compare, retest, retain evidence
                              │
                              ▼
                  Print and physically validate
                              │
                    Calibrate simulation parameters
```

A successful first release must:

1. Export an independently authored build123d assembly into a **physically plausible**, inspectable MuJoCo scene with true openings, gravity and contact.
2. Simulate uncontrolled rigid bodies falling, stacking, sliding and settling; distinguish physically driven motion from manually positioned animation.
3. Drive specified joints with physical input profiles (force/limited-position control where justified), realistic stops, and return springs, rather than teleporting outcomes.
4. Produce machine-readable failure diagnoses (blocked gravity feed, jamming, double feed, out-of-bounds, excess force, solver failure) and replayable evidence.
5. Support reproducible parameter sweeps and agent-guided CAD revisions without changing MuJoCo scene geometry by hand.
6. Allow independent projects to declare different objects, joints, tests, materials and pass criteria without Pocky-specific logic in `cadkit`.
7. Demonstrate a prediction that can be checked against an actual printed prototype; **simulation-only PASS is never equivalent to physical acceptance**.

## 2. Scope and non-goals

### In scope

- Optional MuJoCo dependency in the existing `uv` environment; macOS Apple Silicon support.
- `build123d` → explicit physical scene model → MJCF export → `mujoco.MjModel`/`MjData` simulation.
- Per-body visual meshes **separate** from simplified physical collision geometry.
- Mass, center of mass, inertia, friction, contact properties, gravity, initial placement, joints, springs, stops and actuators.
- Generic scenarios, trajectory/event logging, test metrics, failure classification, headless batch execution and optional visualization.
- Small, bounded experimental sweeps and revision comparison for AI-assisted CAD.
- Integration with existing geometric checks, existing CLI/discovery conventions and `out/` layout.
- First real pilot: fixed-magazine, manual/spring-return dispenser of **10 then 25** Pocky packets, no cartridge.

### Explicitly out of scope for initial implementation

- Replacing build123d as the source of CAD geometry or changing existing STEP/STL export semantics.
- Full finite-element stress/strain, brittle chocolate fracture, high-fidelity foil wrapper crumpling, granular contents or accurate food damage predictions.
- Guaranteed real-world correctness from guessed material constants.
- Design of a 100-packet machine, cartridges, electronics, motors, or decorative enclosure for the Pocky pilot.
- An autonomous agent modifying unlimited geometry, rewriting tests to improve a score, or bypassing physical verification.
- GPU differentiable optimization, reinforcement learning, cloud simulation farms or a GUI-first workflow.

## 3. Engineering principles and hard rules

1. **Single source of geometry:** `projects/<name>/` build123d parameters generate printable geometry. MuJoCo models are derived artifacts. Never edit generated MJCF as the persistent design of record.
2. **Motion must come from forces/constraints:** Only initialize object positions and reset between independent trials. During a scenario, packets move by gravity and contact. Do not set `qpos` on packets to make them dispense or settle. Controlled joint actuation is allowed only when it represents an actual input and is recorded as such.
3. **Accurate voids:** MuJoCo geom collisions are convex; concave geometry exported as a single mesh may collide as its convex hull. A hollow housing, curved slot, exit aperture or U-channel must be described as a **union of multiple convex colliders** (ideally simple boxes/capsules/cylinders) with openings left empty. A visual STL alone is not a reliable collider.
4. **Explicit units:** Existing build123d designs are in **millimeters**, MuJoCo is SI (**meters, kilograms, seconds, newtons, radians**). Convert length by `0.001`, mass from measured g to kg, density to kg/m³ and inertia to kg·m². Reject mixed-unit or implausible configurations.
5. **Physics model is an approximation:** Record whether a parameter is measured, derived, assumed or calibrated; save uncertainty ranges. Rigid packets approximate wrappers; do not claim they predict folds, punctures or broken Pocky sticks.
6. **Geometry and dynamics are complementary:** Retain build123d exact-solid clearance/overlap testing. Use MuJoCo for gravity, dynamics, contact and mechanism forces; one cannot replace the other.
7. **Strict test integrity:** Keep immutable acceptance scenarios, thresholds and baseline results separate from candidate design parameters. Optimizers may change candidate parameters but not evaluation rules.
8. **Reproducible evidence:** Record seed, solver/integrator settings, timestep, MuJoCo and Python versions, platform, CAD parameter snapshot/hash, scene hashes and material presets. Determinism is expected within a pinned environment, not bit-for-bit across platforms.
9. **Failure is not silently tolerated:** An invalid scene, nonphysical interpenetration, divergence, timeout, missing collision mesh or unmeasured critical coefficient is never a PASS.
10. **License separation:** Reference vendor meshes/video remain outside cadstudio and output bundles. Use only original build123d geometry and authorized numeric measurements/observations. No purchased meshes, traced outlines or frames in generated physics assets.

## 4. Proposed architecture

The following paths are **proposed**, subject to M0 inspection of `CLAUDE.md`, `cadkit.project` discovery and existing CLI patterns.

```text
cadstudio/
├── pyproject.toml                       # optional physics extra, lockfile
├── cadkit/
│   ├── ...                              # existing generic CAD utilities
│   └── physics/
│       ├── __init__.py
│       ├── schema.py                    # typed scene/part/joint/material/scenario specs
│       ├── units.py                     # mm → m, g → kg, inertia validation
│       ├── geometry.py                  # build123d part + transforms → visual meshes
│       ├── collision.py                 # explicit convex collider recipes + validation
│       ├── mjcf.py                      # deterministic MJCF authoring/export
│       ├── runner.py                    # headless stepping, reset, input profiles
│       ├── telemetry.py                 # contacts, poses, forces, event detection
│       ├── evaluate.py                  # domain-independent assertions / result schema
│       ├── sweep.py                     # seeded parameter variations and comparisons
│       ├── report.py                    # JSON/CSV/Markdown and replay artifacts
│       └── viewer.py                    # optional interactive playback, not on CI path
├── projects/
│   └── pocky/
│       ├── params.py                    # existing CAD parameter authority
│       ├── params.toml                  # existing design configuration
│       ├── geometry/ ...                # existing physical solids
│       ├── models/ ...                  # existing model discovery
│       ├── physics/                     # NEW, pilot-specific; exact path may change
│       │   ├── assembly.py              # bodies, colliders, joints, coordinate frames
│       │   ├── materials.toml           # friction/mass/spring ranges and provenance
│       │   ├── scenarios.py             # stack, gravity, push, return, refill tests
│       │   └── acceptance.toml          # fixed pilot thresholds, not tuned by sweeps
│       └── docs/
│           └── physics-calibration.md   # bench measurements and revisions
├── tests/
│   ├── physics/                          # generic unit + analytic integration tests
│   └── projects/ ...                    # adapt to actual existing test convention
└── out/<project>/<model>/physics/<run_id>/
    ├── manifest.json                    # version and provenance, source parameter hash
    ├── scene.xml                        # deterministic MJCF
    ├── assets/                          # generated ORIGINAL visual/collision meshes
    ├── summary.json                     # status, threshold results, diagnostics
    ├── report.md                        # human/agent-readable failure analysis
    ├── traces/*.csv                     # time series for defined scenarios
    ├── states/*.npz                     # replay qpos/qvel/act/ctrl snapshots as needed
    └── frames/                          # optional captured images/videos
```

Design rules:

- `cadkit.physics` is a **generic optional feature**; all non-physics commands must still work without MuJoCo installed. Lazy-import physics dependencies.
- Every physics-enabled model supplies a small `PhysicsAssemblySpec` referencing CAD part IDs; absence of physics data does not break CAD rendering/printing.
- Generic primitives/scenarios live in `cadkit`. Dispensing-specific event predicates (one packet crossed an exit plane, another followed, next packet settled) live under `projects/pocky/physics/`.
- Do not multiply sources of truth: design dimensions in the existing parameter model, physics-only measured coefficients in physics config, pass/fail criteria in independently reviewed acceptance config.
- Keep outputs beneath existing `out/<project>/<model>/`, honoring ignored/generated-output rules. CAD source remains readable and versionable even though cadstudio is currently **not a Git repository**; take dated file snapshots and hash source files before/after agents modify them.

### Core contract (conceptual, not an implementation API commitment)

| Concept | Fields/requirements | Responsible for |
|---|---|---|
| `PartSpec` | stable ID, build123d shape, transform, visual mesh ID, collision recipe ID, material, mass/inertia source | Traceability to printable CAD |
| `ColliderSpec` | box/capsule/cylinder/sphere/convex mesh, local pose, category, collision groups and tolerances | Correct contacts, especially apertures |
| `JointSpec` | parent/child, anchors/axes, hinge/slide/etc., limits, damping, friction, spring specification | Mechanical constraints |
| `PhysicsAssemblySpec` | fixed and free bodies, initial conditions, ground/world, gravity, constraints and actuators | Simulator construction |
| `ScenarioSpec` | fixture, preparation, initial count/pose, input force/time profile, seed, duration, expected outcomes | Repeatable test execution |
| `EvaluationSpec` | named predicate and threshold, severity, validity checks, unambiguous units | Objective testing |
| `SimulationResult` | PASS/FAIL/INCONCLUSIVE/ERROR, metrics, events, timings, hashes and links to traces | AI feedback and evidence |

**ID convention:** Stable scene body and collider names map directly back to CAD model parts and declared sub-shapes. Names must be unique, filesystem-safe and deterministic across regeneration; meaningful diagnostics require such a mapping.

## 5. Geometry → MuJoCo pipeline

### 5.1 Model assembly and coordinate frames

- Enumerate parts from actual project model discovery; do not assume a Compound alone preserves joints, physical mass, or semantic roles.
- Record explicit local frames for each rigid component, its center of mass, joint anchors and simulator body origin. Preserve transform hierarchy; test orientation and axis handedness with asymmetric fixtures.
- `Z` is up (gravity `(0, 0, -9.81)` m/s² by default). For Pocky, nominal packet envelope is **165 × 55 × 5.2 mm**, flat in XY and stacked along +Z.
- Visual triangulation may use existing STL tessellation settings, but keep **physics collider generation independent of visual mesh resolution**.
- Ensure units are converted **exactly once**, not by ad hoc scaling both the mesh and XML attributes.

### 5.2 Separate visual and collision representations

| CAD feature | Visual asset | Preferred collision representation |
|---|---|---|
| Long straight magazine walls | Exact/decimated STL | Multiple thin boxes around the open volume |
| Housing with openings or curved slot | Detailed STL | Explicitly positioned convex pieces leaving apertures open |
| Base/floor and rails | Detailed STL | Boxes or convex segments with no artificial lid |
| Lever / button / round-ended pusher | Detailed STL | Capsules, cylinders or convex segments matched to critical contact surfaces |
| Rigid Pocky packet | Simple display box | Rounded/boxed **proxy** with measured dimensions and mass |
| Complicated convex part | STL | Convex mesh after validation |
| Complicated concave part | STL | Explicit decomposition into **multiple convex** colliders, each validated |

Rules:

1. Prefer manually declared primitives tied to build123d parameter expressions for important contact paths; consider automated convex decomposition only as a later opt-in **with explicit accuracy checks**.
2. Never silently use a convex hull over a magazine opening. Flag a concave part lacking a collider recipe as `SCENE_INVALID`.
3. For every important channel, separator, slot and exit opening, programmatically check **free-space occupancy** at sampled probe poses and relevant cross-sections. Compare collider envelope to original CAD where practical.
4. Verify that colliders do not unintentionally fill narrow gaps or omit a wall that provides necessary support. Report maximum collider-to-CAD surface deviations near critical contacts in **mm**, not only global mesh error.
5. Avoid dozens of nearly coincident colliders, unnecessary self-contacts and solver-costly mesh triangles. Use collision filters deliberately; contact between distinct packet bodies and housing must remain enabled.
6. Show visual **and** collision geometry together in a debug view (separate colors/opacity) to detect proxy errors. Preserve a per-revision collision overlay screenshot or mesh inspection artifact.

### 5.3 Mass, inertia, constraints and contact

- For printed parts, start from known/estimated print density and part volume, or weigh the printed part; report which method was used. Explicit body mass/inertia must be positive and physically plausible for mobile bodies.
- Use measured packet mass and COM if available; otherwise label provisional. Calculate inertia using full solids/analytical approximations and check units, eigenvalues, symmetry and coordinate-frame transforms.
- Define physical contact material pairs (e.g. PLA ↔ wrapper, wrapper ↔ wrapper, PLA ↔ PLA), not only one generic friction scalar. Include sliding friction, and only enable torsional/rolling terms when justified and supported by contact model.
- Define mechanical joint axes, limits, stops, damping and any spring preload/force. A real manually pushed button gets a **scripted external force or physically justified bounded servo input**, with return driven by the modeled spring; don't pretend a permanently powered motor exists in the physical product.
- Model a linkage with correctly constrained bodies; a visual-only pose mapping cannot validate required physical input forces. If the closed-chain linkage/pin-and-slot is not stable with MuJoCo's supported joint/equality/contact modeling, simplify conservatively and **mark linkage-force conclusions inconclusive** until a physically credible representation is verified.
- Distinguish desired contact from unreasonable penetration and solver artifacts. Watch contact count, normal forces, solver warnings, kinetic energy and motion stability.

### 5.4 MJCF build and compilation

- Author readable, deterministic MJCF (XML) first; it is diffable and easy to inspect. `MjSpec` is an optional future internal builder if it reduces errors, but exported MJCF remains part of evidence.
- Use referenced mesh assets in the output directory with deterministic relative paths; compile by `mujoco.MjModel.from_xml_path(...)` and create `mujoco.MjData(model)`.
- Confirm all referenced assets exist, mesh scales are right, body counts match, joints compile, and no unsupported mesh assumptions appear. Do not treat "compiled" as "physically correct."
- Use MuJoCo's currently supported VFS/MjSpec mechanism if an in-memory pipeline is later needed; do not anchor a new implementation to deprecated Python `assets` dictionaries.

## 6. Simulation execution and observability

### 6.1 Headless first

The simulation runner must work without a window or GPU renderer:

1. Load scene and scenario, validate fixed inputs and physics metadata.
2. Initialize all rigid bodies once, separated as appropriate; call `mj_forward` and detect unexpected initial penetrations.
3. Run a **settling phase** under gravity, not scripted packet motion; save start-of-action state and settle diagnostics.
4. Apply a time-based input to the real actuated part and advance with `mj_step` over physical simulation time.
5. Release input, simulate spring return and further gravity settling.
6. Check named event predicates and hard validity invariants at each step.
7. Save final positions, contact/force measurements, trajectories, failure reasons and optional sampled replay states.

**Suggested starting solver configuration:** Fixed timestep **1 ms** (adjust only after convergence tests), clearly documented solver iterations/tolerances and scenario duration. Test the same scenes with smaller timestep and tighter solver settings; decisions must not flip solely because a numerical artifact vanished or appeared. Trial durations and stopping criteria should be explicit and bounded.

### 6.2 Input profiles

- Free-fall test: **no actuation**.
- Passive refill/settling test: no actuation, release supported stack and evaluate arrival at ready position.
- Dispense: controlled press force over a measured time interval, bounded to a plausible manual input; test partial press and quick release as separate profiles.
- Return: input returns to zero; spring and mechanism restore the home position without numerical snapping.
- Recovery: stop, reset, or manual intervention is counted as failure unless explicitly part of the scenario.
- Store both commanded control signals and resulting generalized input force, stroke and work; label any control method that can inject unrealistic energy.

### 6.3 Telemetry and test oracles

Required generic measurements: wall-clock runtime, simulated time, body poses/velocities, joint states, contact pairs/depths/forces, actuator/spring-related forces, penetration and stability warnings.

For the dispenser pilot, derive at least:

| Metric | Meaning | Example failure mode |
|---|---|---|
| `gravity_settle_success` | Next packet enters dispense-ready pose after the previous is removed and ejector retracts **without a scripted move** | Packet hangs above mechanism |
| `settle_time_s` | Time from clearance until stable/ready pose | Excess friction or hang-up |
| `dispensed_packet_count` | Distinct packets that cross a defined pickup/exit plane | Zero feed or double feed |
| `double_feed_count` | More than one packet escapes per complete/partial actuation | Separator too open |
| `jam_count` / `jam_reason` | Stationary/blocking state with incomplete expected progress within timeout | Wrapper proxy stuck at gap |
| `return_success` | Button/ejector restores home position under spring action | Inadequate return force |
| `peak_button_force_N` | Worst expected human input force | Mechanism too stiff |
| `peak_contact_force_N` | Contact loading at named packet surfaces | Potential damage risk, **not a fracture proof** |
| `max_forbidden_penetration_mm` | Invalid overlap beyond solver-specific tolerance | Collider or solver problem |
| `packet_roll_pitch_deg` | Excess tipping or edge snag | Stack instability |
| `cycle_time_s` | Time to move, present, return and settle | Throughput / delayed feed |
| `solver_warning_count` | Instability / invalid numerical conditions | Invalid physics inference |

Definitions must be independent of candidate dimensions. An exit event must have a direction, packet identity, time window and anti-double-counting logic. A packet merely touching a plane is not a successful dispense. Success also requires a hand-accessible position and a supported output condition if applicable.

### 6.4 Three-valued truth (plus execution error)

- **PASS:** all applicable physical criteria satisfied, the numerical validity checks pass, required calibrated inputs present, and robustness coverage met.
- **FAIL:** a valid trial violates a requirement (zero feed, jam, duplicate, no spring return, etc.).
- **INCONCLUSIVE:** weak physics model, unmeasured material coefficient with outcome sensitivity, insufficient runtime, solver sensitivity, questionable collider or missing evidence.
- **ERROR:** build/compile failure, bad asset, unit mismatch, crash or timeout. No success score awarded.

Report the individual statuses alongside a single overall status. An agent must not optimize `INCONCLUSIVE` into `PASS` by altering thresholds.

## 7. Iterative agent-driven CAD design loop

### 7.1 Candidate parameters versus fixed evaluation

Allow modification of explicit design variables, examples:

- Magazine interior length/width, wall profile and guide clearances.
- Exit/separator height and shims.
- Ejector tip shape, radius, contact width, pivot location, travel envelope and stops.
- Button stroke, leverage and spring choice (where a physical spring is selectable).

Do **not** let the candidate editor mutate acceptance criteria, packet dimensions/mass distributions, material measurements, input constraints or reference physical test data. An AI can propose a new mechanism class, but that changes the hypothesis and requires a named review gate.

### 7.2 Two-stage evaluation, cheapest checks first

1. **Static CAD:** regenerate part(s); assert watertight solids, dimensions, print feasibility and exact geometric clearances.
2. **Physics scene validation:** export/compile scene; verify units, collider free spaces, inertia, contact groups, stable floor/stack.
3. **Cheap dynamics:** one/few packets with nominal conditions, partial cycles, no viewer.
4. **Robust dynamics:** varied fill levels, tolerances, friction, packet placement and user input profiles, with multiple seeded trials.
5. **Physical gate:** print/test promising revision; compare failures and tune model.

Reject candidates at the earliest authoritative failing step and record the reason. Don't hide a cheap-stage failure with a later approximate physics success.

### 7.3 Parameter search and selection

Implement a bounded search interface, not an unreviewed self-modifying optimization system:

```text
CAD parameter snapshot / baseline
  -> sampled candidate param set
  -> exact geometry checks
  -> physics suite (same scenarios/seeds as baseline)
  -> metrics + diagnosis + sensitivity
  -> choose feasible Pareto-improving candidate
  -> save design diff + simulation evidence
  -> repeat, with explicit budget / stop rule
```

- Start with **manual/AI-selected experiments and small grids** over 2–4 parameters; use seeded sampling for uncertain inputs. More advanced Bayesian optimization is optional later.
- Hard constraints outrank weighted goals: no double feeds, reliable reset, correct clearances, modeled contact validity and force safety. Optimize lower button effort, faster settling and print material usage only among feasible designs.
- Use a fixed evaluation set and held-out perturbations to reduce overfitting. Keep a known-bad baseline and a known-good synthetic fixture in regression tests.
- Store complete parameter deltas and reasons for accepting/rejecting candidate versions. Since cadstudio is not yet a Git repo, automatically write timestamped snapshots and SHA-256 checksums, and ensure rollback does not overwrite active user work.
- Every run has a max candidate count, max simulated seconds, max real runtime and disk artifact budget, all settable by CLI/config.
- Never declare a physical prototype ready merely because optimization reaches a numeric score.

### 7.4 Agent-readable failure analysis

The report should answer:

- **What failed?** (e.g., packet 2 bridged across the separator).
- **When and where?** (time, named bodies, frame, contact pairs, relevant coordinates).
- **Why is that a likely hypothesis?** (e.g., wall friction prevented gravity feed; must distinguish correlation from proof).
- **How confident is the hypothesis?** (measured versus assumed friction and solver sensitivity).
- **Which CAD parameter(s) may address it?** (suggestions, not automatic silent edits).
- **Did the candidate regress anything else?** (side-by-side metrics and fixed acceptance cases).

Use a stable JSON schema and an accessible Markdown summary. Supply optional trajectory plot/render via offline output; GUI opening is never needed in batch tests.

## 8. Pilot scenarios — Pocky dispenser

The dispenser remains **one fixed top-loaded magazine of 10–25 packets**, manually pushed with spring return, with no cartridge or electronics. Build upon the existing design rather than recreating a parallel mechanism. The nominal rigid packet envelope is **165 × 55 × 5.2 mm**, but measured packet mass, height distribution, inter-wrapper friction and wall-wrapper friction must be captured before making physical reliability claims.

### Scenario matrix

| Scenario | Fill / input | Physics requirement | Acceptance evidence |
|---|---|---|---|
| P0 — unit sanity | Single packet released above floor | Falls under gravity and comes to rest; correct scale | Analytic drop/settle comparison |
| P1 — gravity feed | 1 then 2 packets; ejector clear | Lowest free packet settles onto support without teleportation | Position/time trace |
| P2 — short stack | 10 packets | Stable stack, proper alignment and support | Contact, tilt, penetration data |
| P3 — loaded stack | 25 packets | No spontaneous double feed or numerical explosion | Contact/weight balance and stability |
| P4 — full press | 10 packets; bounded manual press/release | Exactly one packet presented, button returns, next packet descends | Identity-tracked count + trace |
| P5 — capacity press | 25 packets; same mechanism | As above; load-induced jamming and input effort evaluated | All metrics and cause of failure |
| P6 — adversarial inputs | Partial stroke, fast release, slow press | No uncontrolled duplicate; clear pass/fail for no-dispense partials | Per-profile event report |
| P7 — friction extremes | Low/nominal/high plausible friction pairs | Detect sensitivity to unmeasured wrapper interactions | Sweep with ranges/provenance |
| P8 — tolerance extremes | Packet height variation, separator gap, minor yaw/offset | No fragile single-value success | Seeded robust trials |
| P9 — repeat | Multiple cycles/refills | No forced reset of packet positions inside a run; successful gravity replenishment | Per-cycle event log |

**Important:** For P9, once a presented packet is removed by a simulated *user pickup* event, log that removal explicitly as an external action; do not silently delete/move it while claiming fully unassisted operation. A no-pickup variant should also be tested where relevant.

### Physical acceptance remains unchanged

The previous dispenser plan requires **50 recorded consecutive physical cycles at 10 packets and 100 at 25 packets** with zero jams, double feeds or manual interventions, plus checks for wrapper/candy damage. This new physics plan supplements those gates; it does **not** weaken them or assert they can be replaced by simulated cycles. Do not scale to 100 packets until the physical prototype passes.

## 9. Calibration: connect simulation to the printed world

Before trusting predictive scores, log at least:

1. **Packet mass:** weigh multiple sealed packets, record spread.
2. **Envelope variation:** thickness distribution across packets and 10/25-stack height under their own weight; nominal 5.2 mm is not an incompressible law.
3. **Wrapper ↔ PLA friction:** measure critical ramp sliding angle across relevant print orientations; `mu_static ≈ tan(theta)` is a **first approximation** on a slowly tilted incline, not a complete dynamic contact model.
4. **Wrapper ↔ wrapper friction:** similar controlled slip/tilt measurements with two packets.
5. **Spring:** force versus displacement, free length, installation preload, return time.
6. **Manual push:** actual travel, estimated or measured peak force and typical actuation duration.
7. **Printed geometry:** floor roughness, corner/fillet behavior, actual separator opening, print tolerance/shrinkage.
8. **Observed failure:** record actual jam location, wrapper folding/snagging and whether packets tilt or bridge.

Save results under `projects/pocky/docs/physics-calibration.md` with date, method, sample count, measurement uncertainty and photos/notes paths as locally permissible. Set nominal model parameters from measurements; run a range around them. Compare simulated events to at least one **known failed** printed configuration and a subsequently improved configuration. If the simulation cannot reproduce the observed failure, improve assumptions/collider/contact model before trusting AI optimization.

Limitations to declare on every pilot report: rigid proxy cannot faithfully represent flexible foil seals, bending, wrapper adhesion, granular sticks, or candy fracture. A physics model predicting low force is not evidence that candy remains unbroken.

## 10. CLI and automation contract (proposed)

Adapt to existing command dispatcher rather than creating a duplicate entry point. Preserve the existing `<project>/<model>` selection convention.

```bash
# Illustrative only — final syntax is determined in M0.
uv sync --extra physics

# Export assets and compile/validate an inspectable MJCF scene.
uv run cadstudio physics export pocky/<model>

# Run one named scenario with no viewer.
uv run cadstudio physics run pocky/<model> --scenario gravity-feed --seed 42

# Run the project acceptance suite and write JSON + Markdown results.
uv run cadstudio physics test pocky/<model> --suite smoke

# Bounded design/uncertainty sweep; NEVER modifies the design implicitly.
uv run cadstudio physics sweep pocky/<model> --config <sweep.toml>

# Optional viewer: replay the exact scene and saved state/trajectory.
uv run --extra physics mjpython -m <existing-cli-module> physics replay <run-id>
```

`cadstudio` executable, `<model>` and `<existing-cli-module>` are **placeholders until the actual checkout is inspected**. The implementation should expose an in-process Python API regardless of CLI name. For macOS **nonblocking passive viewer**, use `mjpython`; ordinary headless `mujoco.mj_step()` and standard viewer invocation do not require inserting the viewer into batch tests. In M0, verify the exact `uv` environment and installed `mjpython` command path.

Each command must exit nonzero on `FAIL`, `INCONCLUSIVE` or `ERROR` for gates that require proven success; emit the machine-readable status even when exiting nonzero. Do not make screenshot/video rendering a dependency of export/test/sweep.

## 11. Milestones, deliverables and acceptance gates

**Implementation rule:** Each milestone is a self-contained agent packet. After completing it, report changed files, reproducible commands, test output, observed evidence, risks and explicit **PASS/FAIL**. Do not roll into the next milestone on unsupported assumptions. Existing user files remain intact; take a snapshot before substantial edits.

### M0 — Inventory and design review (no implementation)

**Tasks**

- Read `CLAUDE.md`, actual `cadkit` architecture, CLI, package metadata, existing `projects/pocky` build123d model, CAD tests, animations and print/export pipeline.
- Record current project status and exactly which component failed in the printed dispenser if existing notes disclose it; don't infer a cause merely from animation.
- Confirm Python/`uv` versions, installed MuJoCo-compatible platform, existing dependencies, project discovery and output conventions.
- Prototype on paper the part/coordinate/joint mapping. Inventory which parts need handmade convex collision recipes versus simple primitives.
- Propose interface contracts and any changes to the above suggested paths. Identify missing critical physical measurements.

**Deliverable:** `docs/mujoco-architecture-review.md` (or repo-convention equivalent): exact integration points, minimal dependency plan, scene schema, licensing guardrails, execution commands and unresolved questions.

**Gate M0:** No duplicate CLI; all CAD source conventions preserved; explicit plan to represent concavity, correctly place bodies and measure gravity feed. **Stop for review before code if architectural conflicts remain.**

### M1 — Dependency, solver and gravity smoke test

- Add `mujoco` as an optional `uv` extra with a pinned lockfile; no mandatory import for projects that don't use physics.
- Implement an independent primitive fixture: free box drops onto a fixed floor; check gravitational acceleration in free flight, contacts, rest, mass and distance units.
- Add runner/seed/config basics, headless exit status, one report and a smoke test that runs on Apple Silicon without GUI.
- Verify any GUI smoke tests only when explicitly requested; don't block CI on graphics.

**Gate M1:** `uv` install, import, deterministic headless trial, plausible SI displacement and floor settle; missing optional extra produces a clear actionable message, not a CAD import failure.

### M2 — Build123d geometry and collision fidelity

- Implement part/frame export, CAD-derived visual meshes and collision-recipe schema.
- Generate compound convex colliders with explicit free spaces for a hollow magazine and exit opening; support boxes first, convex meshes only where needed.
- Unit test rotated/local transforms, mesh scale, primitive half-extents, mass frames, collider naming and scene compilation.
- Add an explicit **negative regression**: a single concave mesh-as-collider incorrectly seals a U-shaped channel; validation rejects that configuration, while the multipart collision recipe allows a test object through.

**Gate M2:** Generated scene visually matches CAD at selected poses, critical holes are physically open, collision proxies are conservative/validated and no massive false collider occupies the channel.

### M3 — Joints, forces, springs and physical motion

- Add hinge/slider joints, constrained stops, damping, force input/actuation and spring return with measured/declared coefficients.
- Build an independent mechanically actuated test fixture with nonzero load and friction; verify its displacement/required force against an analytic or simple physical reference.
- Add validity warnings for unstable constraints, nonpositive inertia, excessive penetration and huge energy/velocity spikes.

**Gate M3:** Actuation and gravity are physically driven, not positional puppetry; release returns mechanically; force observations agree within documented tolerance of the chosen independent fixture.

### M4 — Scenario runner, evaluation and evidence

- Typed scenario loading, deterministic seed setting, reset/settle/actuate/release phases.
- Generic telemetry and validity/error states; contact pairing, named event windows and robust file outputs.
- JSON schema and human-readable report, CSV trace, replay/state serialization. Prove replay refers to **the same scene/config**; reject mismatched hashes.
- Tests with known pass/fail synthetic fixtures (no gravity, wrong unit scale, blocked opening, missing force, duplicate event).

**Gate M4:** Every synthetic failure is detected and attributed; repeat on same pinned runtime gives equivalent pass/fail and toleranced numeric metrics; report is useful without opening a GUI.

### M5 — First Pocky gravity/dispensing simulation

- Build a physics description for the **current original** dispenser, not a substitute example model.
- Add rigid packet proxies, fixed magazine, floor, separator, pusher/lever/button linkage and spring.
- Run P0–P8; then P9 for a short repeated sequence with explicit packet pickup events.
- Perform convergence/sensitivity checks for contact and timestep. Identify model-validity gaps (wrapper flexibility, uncertain friction).
- Correlate at least one physical symptom already observed with its simulated behavior, where measurements permit.

**Gate M5:** Simulator demonstrates genuine gravity settlement and attempts one-packet dispense under bounded input. It correctly reports any failure; a **credible FAIL is acceptable as an informative milestone**. The gate is readiness and diagnostic fidelity, **not a fabricated dispenser PASS**.

### M6 — Bounded AI iteration workflow

- Implement candidate parameter snapshots, approval-controlled edits, compare-to-baseline reports, quick/full suites and rigid budget limits.
- Show at least one improvement iteration: identify a failed event, hypothesize one geometry change, rerun geometry checks and the same MuJoCo tests, compare metrics.
- Verify the evaluator can't be accidentally altered by sweep candidates and that physical parameters remain traceable.
- Keep an undo/rollback mechanism appropriate for a **non-Git workspace**; do not clobber existing files.

**Gate M6:** Automated evaluation yields transparent reasons and measurable changes, all source artifacts recoverable; no score improvement may bypass immutable acceptance tests.

### M7 — Physical calibration and validation

- Collect the minimum measurements from §9 and record provenance. Fit measured friction/spring settings and assess uncertainty.
- Compare simulated failure/settling/stroke trends to printed results. Check whether the preferred design remains viable over plausible extremes, not a single nominal point.
- Re-run full simulation suite on the revised model; print only after passing basic checks, then execute the **separate** 10- and 25-packet physical acceptance gates.
- Document remaining discrepancy, model trust boundary and decisions for next mechanical iteration.

**Gate M7:** Physics outputs are calibrated, their blind spots explicit, and at least one real-world prediction has been compared with measurement. Existing Pocky physical acceptance criteria still govern readiness.

## 12. Test strategy and quality bar

| Layer | Tests | Must detect |
|---|---|---|
| Schema and units | Dimension conversion, missing masses, nonpositive inertia, basis transforms, zero gravity | Wrong units/invalid bodies |
| Export | STL/mesh pose, MJCF name stability, missing assets, unchanged parameter hash | Stale or malformed models |
| Collision fidelity | Hollow U-channel, open separator, rotated wall, sliding packet clearance | Convex-hull false blockage / phantom gaps |
| Physics analyticals | Free-fall acceleration, rest on plane, incline friction onset, known spring oscillator | Wrong force/physics settings |
| Contact robustness | High/low friction, different timesteps, solver settings, initial rotations | Solver artifact mistaken for pass |
| Scenario events | Zero feed, exact one, two feed, late feed, mid-cycle pickup, stuck return | Incomplete or false event detection |
| Parameter search | Fixed seeds, immutable acceptance cases, bounded resources, baseline regression | Reward hacking / invalid comparison |
| Replay/report | Scene/run hashes, saved controls, correct timestamps, no rendering dependency | Unreproducible evidence |
| Physical comparison | Known jam + improved revision, spring and sliding tests | Calibration blind spots |

Minimum acceptance rules:

- Every generic physics module has automated tests; tests must be runnable headlessly with `uv run`.
- All important tests include **negative fixtures**, not just successful examples.
- Document numeric tolerances and why they're acceptable; avoid hard-coded broad tolerances that hide failure at the 5.2 mm packet scale.
- Version and cache generated assets by effective CAD+physics input hashes. Changing geometry, masses or friction must invalidate affected cached results.
- Use fixed seed lists for regression; additional random seeds broaden coverage but don't replace the fixed cases.
- Limit parallel simulator jobs to resource budgets to avoid thrashing local Apple Silicon RAM/CPU; serial smoke tests must work.
- For near-threshold results, run a tighter integration/convergence trial and return `INCONCLUSIVE` when status changes with solver settings.

## 13. Risks and mitigations

| Risk | Consequence | Mitigation |
|---|---|---|
| Concave mesh becomes convex collider | False blocked magazine or exit | Multiple explicit convex colliders + aperture tests |
| Incorrect mm↔m conversion | Implausible gravity, friction and force | Unit-aware conversion boundary + analytic drop tests |
| Unknown wrapper friction/mass | Simulation optimizes a fiction | Measured coefficients and uncertainty sweeps |
| Rigid packet misses folds and foil catches | Simulated PASS / real jam | Physical correlation; conservative envelopes; defer flexible solver until justified |
| Scripted position controls overpower mechanism | Unrealistically easy dispensing | Force-limited input, measure required force, spring-driven return |
| Closed-loop linkage unstable in solver | Invalid effort/return conclusions | Simplified validated constraints, timestep tests, report INCONCLUSIVE |
| Many contact points at 25 packets | Slow or unstable batch runs | Convex primitives, short early exits, solver tuning, performance budgets |
| Agent tunes acceptance criteria | False design improvement | Frozen evaluator/config snapshots and held-out trials |
| No Git history in cadstudio | Accidental loss of working CAD | Before/after snapshots + hashes + atomic writes |
| Stale visuals or MJCF assets | Testing different revision than printed | Geometry/config hash in every report and export |
| Reference-file/license contamination | Unauthorized reproduction | Strict original geometry and no vendor meshes/video in outputs |

## 14. Required deliverables at completion

- A generic `cadkit.physics` adapter (or M0-approved equivalent), optional MuJoCo extra and concise documentation.
- At least one non-Pocky analytic physics fixture proving this isn't bespoke dispenser code.
- Build123d part → MJCF export with verified **hollow** geometry, units, transforms and inertia.
- A pure headless `physics run/test` path, plus optional viewer and replay.
- Named evaluation events, stable JSON/CSV output, failure report and seed/version/parameter provenance.
- Fixed synthetic positive/negative tests and a fully documented first Pocky suite.
- Before/after AI candidate comparison with bounded resource use and rollback.
- Physical measurement template and a calibrated observed-failure comparison.
- A final milestone report with commands, PASS/FAIL/INCONCLUSIVE evidence and unsolved physics limitations.

## 15. Recommended first implementation instruction

> **Do M0 only.** Inspect the real cadstudio checkout, `CLAUDE.md`, current build123d model APIs, `uv` setup, project discovery and current Pocky geometry. Produce an exact integration design for an optional project-agnostic MuJoCo physics layer, a validated part/collider/frame schema, current-architecture file map and a measurement-gap list. Treat `build123d` as CAD source of truth; represent hollow geometry with multiple convex colliders. Do **not** start a full simulator, replace the existing mechanism, implement deformable packaging, touch licensed reference assets, or edit nonessential project files. Report the M0 gate result and stop for review.

## 16. Primary technical references

- [MuJoCo overview — geometry, convex collision and MJCF](https://mujoco.readthedocs.io/en/stable/overview.html)
- [MuJoCo Python bindings — `MjModel`, `MjData`, `MjSpec`, viewers](https://mujoco.readthedocs.io/en/stable/python.html)
- [MuJoCo model editing and compilation](https://mujoco.readthedocs.io/en/stable/programming/modeledit.html)
- [MuJoCo XML reference — joints, actuators, geoms, contact, sensors](https://mujoco.readthedocs.io/en/stable/XMLreference.html)
- [MuJoCo API — stepping and contact forces](https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html)
- [build123d documentation](https://build123d.readthedocs.io/)

---

**Decision at the end of this plan:** Ship the smallest trustworthy headless physics loop that detects the *real* gravity problem. Do not spend effort making an impressive-looking animation that can conceal invalid collisions, missing gravity settlement or unrealistically powered actuation.
