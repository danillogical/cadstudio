# MuJoCo physics layer — architecture review (M0)

Date: 2026-10-21 (America/Los_Angeles). Packet: **M0 only**, no feature implementation.
Authoritative plan: `plan-mujoco.md` (SHA-256 `4f69292c…092f76`). Orchestration and user
amendments: `docs/mujoco-orchestration.md`.
Evidence produced by this packet: `docs/mujoco-m0-report.md`,
`out/pocky/prototype/physics/m0-20261021/`.

This document is an **architecture and interface design**, written after reading the actual
checkout. Where the plan guessed a path or an API, the real one is given and the plan's
guess is marked. Every number below is either measured by a script in the M0 evidence
directory, quoted from a repository file with a line number, or quoted from official
documentation with a URL. Nothing here is a simulation result: MuJoCo is **not installed**
in this environment (M0 forbids installing it), so no dynamics claim is made.

---

## 1. Verified starting state

### 1.1 Platform and toolchain (measured)

| Item | Value | How |
|---|---|---|
| OS / arch | macOS 27.0.1, `arm64` | `sw_vers`, `uname -m` |
| Interpreter | `.venv/bin/python` 3.12.15 | `.venv/bin/python -V` |
| `requires-python` | `>=3.11,<3.14` | `pyproject.toml` |
| `.python-version` | `3.12` | file |
| `uv` | 0.13.0, at `~/.local/bin/uv` | `~/.local/bin/uv --version` |
| `uv` on `PATH` | **no** — `PATH` is `/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin` | `echo $PATH` |
| Default package index | `https://pypi.apple.com/simple` (`pyproject.toml`) | DNS **unreachable**; `pypi.org` returns 200 |
| Git | **absent** (`.git` missing) | `git status` → *not a git repository* |

Installed in `.venv` (measured): `build123d 0.13.0`, `trimesh 5.1.1`, `numpy 2.5.4`,
`manifold3d 3.5.4`, `pyvista 0.49.1`, `rtree 1.4.1`, `shapely 2.2.0`, `pytest 9.1.1`,
`ocp_vscode 4.2.0`, `cadstudio 0.1.0`. **`mujoco` is not installed.**

Two consequences that constrain later packets:

1. `uv run …` rebuilds the project and therefore resolves `hatchling` from the unreachable
   Apple index. It fails. `UV_NO_SYNC=1 uv run …` and `.venv/bin/cad` work. This is
   pre-existing, documented in `report-current-progress.md` §Environment, and must not be
   "fixed" by editing tests.
2. Any test that shells out to `uv run cad` fails when `~/.local/bin` is not on `PATH`
   (8 of 224 tests in this session's baseline). With `PATH` corrected they pass. See the
   M0 report for the exact split.

### 1.2 Existing entry points and conventions (exact)

| Concern | Real location | Notes |
|---|---|---|
| Console script | `pyproject.toml` → `cad = cadkit.cli:main` | single entry point; must stay |
| CLI parser | `cadkit/cli.py:112` `main()`; subparsers added at `:115` and `:119` | argparse, one subparser per verb |
| Verbs | `list`, `build`, `render`, `check` (`cadkit/cli.py:79,85,99,106`) | `--part --params --set --out`; `--views` on build/render |
| Project record | `cadkit/project.py:38` `Project` (frozen dataclass) | `name, params_path, load_params, models, check_hook, ghost_meshes, extra_views` |
| Discovery | `cadkit/project.py:60` `discover()`; `:72` `list_models`; `:77` `load_model`; `:85` `all_models`; `:90` `resolve` | `pkgutil` over `projects/`; `_`-prefixed modules are libraries |
| Part record | `cadkit/model.py:10` `ModelPart` | `shape, print_location, wall_shape, min_wall` |
| Model contract | `build(p) -> dict[str, ModelPart]` | three implementations: `models/prototype.py:17`, `linkage_motion.py:18`, `packet_dummy.py:10` |
| Export | `cadkit/export.py:12` `export_part`, `:29` `export_assembly` | STEP in assembly coords; STL/3MF in print pose |
| Meshing | `cadkit/mesh.py:10` `shape_to_mesh(tolerance=0.02, angular=0.1)`, `:21` `posed_shape` | vertex-merged trimesh |
| Checks | `cadkit/checks.py:160` `run_checks`, `:201` `write_report`, `:42` `overlap_volume`, `:34` `CheckResult` | statuses `pass/fail/warn/info` |
| Params | `cadkit/params.py` `load_sections`, `override`, `REPO_ROOT`; `projects/pocky/params.py` | frozen dataclasses; `--set` dotted keys |
| Render | `cadkit/render.py` `render_model`, `render_part`, `VIEW_SETS` | off-screen PyVista; no GUI needed |
| Output | `out/<project>/<model>/` (+ `renders/`, `report.md`, `report.json`) | `out/` is in `.gitignore` |
| Tests | flat `tests/test_<project>_<area>.py`, shared fixtures in `tests/conftest.py` | `uv run pytest tests -q` |

The plan's proposed `cadstudio physics …` executable, `tests/physics/` and
`tests/projects/` directories **do not match the repository**. They are replaced in §12 by
`cad physics …` and flat `tests/test_cadkit_physics_*.py` / `tests/test_pocky_physics_*.py`.

### 1.3 Pocky model as it exists (measured)

`projects/pocky/geometry/prototype.py` builds 15 solids at one button fraction:
`body, chassis, lip, shim_04_a, shim_04_b, shim_08, spring_seat, crank, pusher, rod, spring,
peg_pivot, peg_pusher, peg_button, dummy`. `PART_ROLES` (`:118`) names the role set.

| Fact | Value | Source |
|---|---|---|
| Build cost | `prototype_solids(p)` 1.18 s; `import` 1.77 s | timed |
| Tessellation | 1.49 s for all 15 parts, 17 248 triangles | timed |
| Pose math | 21 poses < 1 ms (closed form, no B-rep) | timed |
| Bore | x −85…85, y ±30, floor top z = 0 | `_tube` `:418` |
| Exit aperture | x 85…88, z 0…9.20, y ±30, 2.6 mm chamfer on the underside | `_body` `:438` |
| Separator gap | 5.75 mm (5.35 ledge + 0.4 shim); blade 2.4 mm thick, x 80.5…91 | `_lip` `:669` |
| Floor slot | x −93.1…−35.1, y ±3.5 (through slot for the pusher neck) | `floor_slot_bounds` `:228` |
| Back notch | x −87.4…−85, z 0…4.4, y ±20 | `_body` |
| Clip posts | x 62…72 and −38…−28; post y 34.0…37.7 / −37.7…−34.0; z −19.2…2.45 | `_chassis_hook` `:631` |
| Clip bearing | tooth underside z = +0.05 over rib top z = 0; 1.0 mm Y overlap | same |
| Mechanism Z stack | rod −15.6…−11.6, crank −11.2…−7.2, carriage −6.8…−2.8, bullnose 0…4.2 | `linkage_from` `:122` |
| Body floor | z −2.4…0; underside 9.2 mm above the highest chassis surface under it, 13.2 mm above the base plate | measured |
| Stroke | 50.0 mm face travel, 23.094 mm button travel, pivot (−78, −8) | `linkage_from` |

Measured part mass at PETG 1.27 g/cm³ (fully solid; slicer infill is lighter):
body 139.4 g, chassis 102.6 g, rod 16.2 g, pusher 8.8 g, lip 6.4 g, crank 3.9 g,
spring 1.9 g, spring_seat 0.4 g, pegs 0.4/0.3/0.3 g, shims 0.04/0.04/0.2 g, dummy 59.9 g.
All 15 solids together are 340.5 g, of which the dispenser's own parts are **280.6 g** — the
remaining 59.9 g is the bench `dummy`, which is not part of the machine. These are CAD-volume
estimates at datasheet density, **not** weights of any printed object (print status is
unverified, §19.2).

### 1.4 The support defect (the central M0 finding)

The user reports the body "isn't stable and would immediately fall down in a physics
simulation, it's resting on only two posts from the chassis". That sentence is a **prediction
about a simulation plus a structural observation**, not a record of a physical trial. What
follows is independent CAD evidence, measured from the solids; it does not depend on the
user's sentence being right, and it does not confirm that any print exists (§19.2).

**The clips do not carry the body's weight.** `_chassis_hook` (`:631`, called at `:608–609`)
puts the tooth underside at `z_catch = rib_top + STOP_EPS` = **+0.05 mm**, while the body rib
spans `floor_z0…floor_z1` = **−2.4…0.0 mm** (`linkage.py:131–132`). Measured directly: the
tooth occupies z 0.05…2.45 and the rib occupies z −2.4…0.0 at the same (x, y). The tooth is
0.05 mm *above* the rib top, so a downward body load **moves the rib away from the tooth**.
The clips are **retention-only** (+Z lift), which is exactly what `assembly.md:99` describes
("the tooth … reaches back over that rib") and what `plan-first-prototype.md:299` tests
("the chassis cannot fall off along −Z"). Neither is a downward bearing seat.

Consequences, all measured:

1. **No downward load path exists.** The body floor underside is at z = −2.4. Sampling the
   chassis top surface over the body's ±32.4 mm footprint, the highest material is the guide
   tops / boss at **z = −11.6** — a **9.2 mm void** — and the base plate is at −15.6
   (`prototype.py:539`), 13.2 mm below. Nothing designed bears the body.
2. **The first thing under it is a moving part.** The pusher carriage top is at z = −2.8,
   **0.4 mm below the floor underside**; measured body→pusher minimum distance at rest is
   0.027 mm at (−89.43, 9.07, 0). So a gravity settle drops the body ~0.4 mm onto a part that
   translates 50 mm during the stroke.
3. **The mechanism itself has designed vertical gaps**, so that stop is not rigid:
   carriage bottom −6.8 over crank top −7.2 (0.4 mm), crank bottom −11.2 over boss top −11.6
   (0.4 mm), and the pusher peg head sits 0.2 mm above the carriage. A load therefore cascades
   through three unconstrained interfaces. **Only the first 0.4 mm is in the body's own
   downward path** (floor onto carriage); the next two open only if the carriage is pushed
   down, so the total is *0.4 mm to first contact plus up to 0.8 mm of further cascade*, not a
   flat 1.2 mm of body sag.
4. **The clips are a degenerate support anyway, and also loose in X.** Their bearing patches
   (6 mm × 1 mm at x 64…70 / −36…−30) are collinear, 121.5 mm apart, and the hull of the two
   patches is 520 mm² over that span — a strip **4.23 mm wide** perpendicular to the line
   (2A/P = 4.05 mm), not "about 1 mm". The hanging group (body + lip + two shims, 145.9 g)
   has its COM at (5.28, 0.00, 26.08), **4.54 mm outside** that strip (body alone 6.86 mm).
   In X, each 6 mm tooth overlaps a 14 mm rib, giving **±4 mm of free slide**; in Y the post
   gives 0.3 mm. So the "two posts" locate the body in neither Z nor X.
5. **The rest-pose arrest is incidental and migrates.** Rotating the hanging group about the
   clip line, the first new contact is the pusher at **0.4°** (0.42 mm of sag at that contact —
   exactly the floor-to-carriage gap). With the mechanism ignored the body rotates 8.4° onto
   the chassis base plate. Across the stroke the arrest moves: 0.4° onto the carriage at rest,
   0.3° at half stroke, 0.2° onto the **pusher peg head** at full stroke. A single rest-pose
   check would therefore pass while the mechanism is loaded at other poses.
6. That arrest will not survive a settle. Because the carriage and crank each have 0.4 mm
   below them, the mechanism drops before it can hold anything, so the measured settle will be
   **larger** than 0.4°, and the final resting surface moves down with it.

**Determination: a missing downward load path, not merely weak support.** The designed
body→chassis connection is retention-only; under gravity the body lands on a translating
mechanism part, through a chain of designed gaps, and the resulting resting state is not
statically determinate. This matches the *structural half* of the user's observation ("resting
on only two posts"). It is **not** a simulated result, and it does not establish friction,
print tolerance, clip preload or any physical failure.

**A collider artifact that could fake the opposite conclusion.** The chassis bounding box tops
out at z = 2.45 (the two tooth tops). A convex-hull chassis collider would therefore present
phantom material 4.85 mm above the real body floor underside and make the body appear to rest
on "two posts". Any scenario in which the body looks supported by chassis geometry at the
nominal pose is a collider bug, and the baseline scene must show **zero body↔chassis contact**
and reproduce the free-fall-onto-pusher outcome.

This is why `S0 assembly_stability` is a **prerequisite scenario**, not a diagnostic (§8). No
packet-feed result is meaningful while the housing's own equilibrium is accidental.

### 1.5 Presentation target, checked statically

The 40 mm target is measured **past the outer face**, `link.outer_x = 88.0`
(`linkage.py:129`), not past the bore front (85.0) — `plan-first-prototype.md:34` says "past
the outer face", and `Pose.protrusion` (`linkage.py:206`) returns exactly 40.0 at full stroke.
The packet therefore spans **x −37…128**, and its front edge sits **22 mm past the 18 mm lip
shelf** (which ends at x = 106) — consistent with `mechanism-proposal.md`.

Of an 80 × 25 underside sample grid, **86.1 %** has body floor or lip shelf within 3 mm below
it; the support hull spans x −36.0…104.3 (7 436 mm²) and the packet COM at x = 45.5 is inside
it. The **forward** margin to the lip-shelf end is **60.5 mm**; the **rear** margin to the
first supported sample is 81.5 mm; the **26.5 mm** figure is the *lateral* margin to the
±26.5 mm y edge, and must not be quoted as a tipping margin.

So the 40 mm pose is geometrically supportable. That says nothing about dynamics, friction, or
whether the body holding that lip stays put: the load path is packet → lip shelf → lip feet on
two 0.4 mm shims → body ledges → retention-only clips → a moving carriage (§1.4).

---

## 2. Integration points — the exact change surface

Everything below is *proposed*. M0 changes no source file.

| File | Change | Why it is minimal |
|---|---|---|
| `pyproject.toml` | add `[project.optional-dependencies] physics = ["mujoco==3.16.0"]`; add a non-default `pypi` index entry | optional extra; no new required dependency |
| `cadkit/project.py` | add one field `physics: Callable[[Any], PhysicsAssemblySpec \| None] = _no_physics` to `Project` (`:38`) | default keeps every existing project and every existing test unchanged |
| `cadkit/cli.py` | one `physics` subparser with nested verbs, added in `main()` (`:112`), handler imported lazily | one entry point preserved; no duplicate CLI |
| `cadkit/physics/*` | new package (§3) | no existing module is edited |
| `projects/pocky/__init__.py` | set `physics=` on `PROJECT` | project opts in |
| `projects/pocky/physics/*` | new package: assembly, materials, scenarios, acceptance | Pocky-specific only |
| `tests/test_cadkit_physics_*.py`, `tests/test_pocky_physics_*.py` | new flat test modules | matches existing convention |

Deliberately **not** changed:

- `cadkit/model.py` `ModelPart` — physics metadata must not be bolted onto the CAD record.
  A part that has no physics description is still a valid, printable part.
- `cadkit/export.py` — STEP/STL/3MF semantics are frozen. Physics writes its own assets.
- `cadkit/checks.py` — physics reuses `overlap_volume` and `CheckResult` but does not add
  physics checks to `run_checks`, so `cad build --check` stays MuJoCo-free.
- `projects/pocky/params.toml` — measured physics coefficients are not CAD parameters.
- `projects/pocky/geometry/linkage.py` — constants there are the linkage's design of record.

### 2.1 Why `Project.physics` and not a new registry

`discover()` (`cadkit/project.py:60`) already imports every `projects.<name>` package and
checks for a `Project` instance. A `physics` field therefore costs one import of the project
package — which is already paid — and no new discovery mechanism, no second source of truth
about which projects have physics, and no file-name convention to violate.

The callable, not a module import, keeps the heavy path lazy: `Project.physics` is only
called by `cad physics …`.

---

## 3. `cadkit.physics` package

```
cadkit/physics/
├── __init__.py        # lazy surface; raises an actionable error if mujoco is absent
├── schema.py          # typed specs (§4) — no mujoco import
├── units.py           # the single SI boundary (§5)
├── inertia.py         # mass / COM / inertia extraction and validation (§6)
├── geometry.py        # build123d shape + frame -> visual mesh; support-polygon preflight
├── collision.py       # collider recipes, aperture probes, negative checks (§7)
├── mjcf.py            # deterministic MJCF emission (§7.4)
├── runner.py          # stepping, phases, reset, determinism
├── telemetry.py       # contacts, poses, forces, events
├── evaluate.py        # frozen predicates -> RunResult
├── report.py          # summary.json / report.md / traces / states
├── sweep.py           # bounded candidate search (M6)
├── cli.py             # `cad physics …` handlers
└── viewer.py          # optional replay; never on the batch path
```

`schema.py`, `units.py` and `inertia.py` must import **no** MuJoCo symbol. That is what makes
the M0-era static preflight (support polygon, unit checks, inertia validation, collider
coverage) testable without the extra installed.

### 3.1 Optional-import discipline

`cadkit/physics/__init__.py` exposes names lazily:

```python
def require_mujoco():
    try:
        import mujoco  # noqa: F401
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "physics needs the optional extra: uv sync --extra physics "
            "(mujoco 3.16.0; see docs/mujoco-architecture-review.md §11)"
        ) from exc
```

Only `mjcf.py`, `runner.py`, `telemetry.py` and `viewer.py` import `mujoco`, and only inside
functions or at module import time *after* `require_mujoco()`. `cad list`, `cad build`,
`cad render`, `cad check` and the whole existing test suite must pass with `mujoco` absent —
that is the M1 gate, and it is testable by asserting `import cadkit.cli` works in a
subprocess with `mujoco` blocked.

---

## 4. Typed contracts

Authored in millimetres, grams, newtons, degrees — the units the CAD already uses. Frozen
dataclasses, so a scenario cannot be mutated by a sweep. `Provenance` is mandatory on every
physical quantity.

```python
Provenance = Literal["measured", "derived", "assumed", "calibrated"]

@dataclass(frozen=True)
class Source:
    kind: Provenance
    note: str                 # "PETG datasheet 1.27 g/cm3" / "plan §9 item 3, not yet measured"
    date: str | None = None

@dataclass(frozen=True)
class Frame:                  # assembly coordinates, mm and degrees
    pos: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rot: tuple[float, float, float] = (0.0, 0.0, 0.0)   # XYZ Euler, build123d order

@dataclass(frozen=True)
class ColliderSpec:
    kind: Literal["box", "cylinder", "capsule", "sphere", "convex"]
    size: tuple[float, ...]        # box: half-extents; cylinder: (r, half-length); convex: ()
    frame: Frame
    role: Literal["structure", "floor", "aperture_edge", "separator", "packet", "mechanism"]
    contype: int = 1
    conaffinity: int = 1
    margin_mm: float = 0.0
    vertices_mm: tuple[tuple[float, float, float], ...] | None = None  # convex only

@dataclass(frozen=True)
class PartSpec:
    part_id: str                   # MUST equal the model's dict key
    body_id: str
    colliders: tuple[ColliderSpec, ...]
    visual: Literal["cad", "none"] = "cad"
    density_kg_m3: float | None = None      # derived mass
    mass_kg: float | None = None            # measured override; wins over density
    source: Source = Source("derived", "CAD volume x PETG density")

@dataclass(frozen=True)
class SpringSpec:
    stiffness_N_per_mm: float
    rest_length_mm: float
    preload_mm: float = 0.0
    source: Source = Source("assumed", "unmeasured")

@dataclass(frozen=True)
class JointSpec:
    name: str
    kind: Literal["hinge", "slide", "free", "weld"]
    parent: str                    # body_id, "world" allowed
    child: str
    anchor_mm: tuple[float, float, float]
    axis: tuple[float, float, float] = (0.0, 0.0, 1.0)
    limit_mm_or_rad: tuple[float, float] | None = None
    spring: SpringSpec | None = None
    damping: float = 0.0
    armature: float = 0.0
    frictionloss: float = 0.0
    source: Source = Source("derived", "CAD joint geometry")

@dataclass(frozen=True)
class ActuatorSpec:
    name: str
    joint: str
    kind: Literal["force", "position_limited"]
    force_max_N: float
    profile: str                   # named profile in the scenario module
    source: Source = Source("assumed", "manual press, unmeasured")

@dataclass(frozen=True)
class BodySpec:
    body_id: str
    parts: tuple[str, ...]
    fixed_to_world: bool = False
    fixture: Literal["none", "diagnostic_fixture"] = "none"

@dataclass(frozen=True)
class ContactPair:
    a: str                         # material name, e.g. "petg", "wrapper", "wrapper_wrapper"
    b: str
    sliding_friction: float
    torsional: float = 0.0
    rolling: float = 0.0
    source: Source = Source("assumed", "unmeasured")

@dataclass(frozen=True)
class AssemblySpec:
    name: str
    bodies: tuple[BodySpec, ...]
    joints: tuple[JointSpec, ...] = ()
    actuators: tuple[ActuatorSpec, ...] = ()
    contacts: tuple[ContactPair, ...] = ()
    gravity_m_s2: tuple[float, float, float] = (0.0, 0.0, -9.81)
    source: Source = Source("derived", "current CAD")

@dataclass(frozen=True)
class Phase:
    kind: Literal["settle", "actuate", "release", "pickup", "hold"]
    duration_s: float
    actuator: str | None = None
    target: str | None = None      # pickup target body_id
    profile: str | None = None

@dataclass(frozen=True)
class ScenarioSpec:
    name: str
    phases: tuple[Phase, ...]
    timestep_s: float = 1e-3
    seed: int = 0
    fill: int = 1                  # packet count
    initial: str                   # named initial-condition function
    fixture: Literal["none", "diagnostic_fixture"] = "none"

@dataclass(frozen=True)
class Predicate:
    metric: str
    op: Literal["<", "<=", ">", ">=", "=="]
    value: float
    units: str
    severity: Literal["required", "informational"]

@dataclass(frozen=True)
class EvaluationSpec:
    name: str
    predicates: tuple[Predicate, ...]
    invalidates_on: tuple[str, ...] = ("penetration", "divergence", "missing_input")

@dataclass(frozen=True)
class RunResult:
    status: Literal["PASS", "FAIL", "INCONCLUSIVE", "ERROR"]
    scenario: str
    metrics: dict[str, float]
    events: list[dict]
    failed: list[str]
    provenance: dict
    artifacts: dict[str, str]
```

Notes that matter for implementation:

- `PartSpec.part_id` must match the `build()` dict key exactly. `cadkit.project.load_model`
  gives the dict; the validator rejects a spec whose ids are not a subset, and rejects a
  CAD part with no `PartSpec` **only if** it is declared in the assembly (not every part is
  simulated: `dummy` and `shim_08` are bench/slicer artifacts).
- `BodySpec.fixed_to_world` exists, but `fixture="diagnostic_fixture"` must be set with it.
  The evaluator refuses a `required` predicate on a run whose `fixture != "none"` (§8.3).
- `EvaluationSpec` and `ContactPair` are the frozen set. Sweeps may vary `AssemblySpec`
  geometry, never these.

---

## 5. The SI conversion boundary

MuJoCo does not define units ("Units are unspecified — MuJoCo does not specify basic
physical units. The user may interpret the system of units as they choose, as long as it is
consistent", <https://mujoco.readthedocs.io/en/stable/overview.html>). That makes a single
conversion boundary a correctness requirement, not a style choice.

**Rule:** every spec above is authored in **mm, g, N, degrees**. Exactly one module,
`cadkit/physics/units.py`, converts to **m, kg, N, radians**, and it is called from exactly
one place — MJCF emission (`mjcf.py`) — plus the inertia conversion (§6).

```python
MM_TO_M = 1e-3
G_PER_CM3_TO_KG_PER_M3 = 1000.0
N_PER_MM_TO_N_PER_M = 1e3          # spring stiffness
DEG_TO_RAD = math.pi / 180.0
MM5_TO_KG_M2 = lambda rho_kg_m3: rho_kg_m3 * 1e-9 * 1e-6   # see §6
```

Enforcement (all cheap, all testable without MuJoCo):

1. `units.py` has no default arguments — every factor is explicit at the call site.
2. MJCF emission asserts the emitted model is in a plausible SI envelope: every geom size
   in `1e-5 … 2.0` m, every body mass in `1e-4 … 10` kg, every length in `1e-5 … 2.0` m,
   timestep in `1e-5 … 1e-2` s.
3. A round-trip test: convert a known 165 × 55 × 5.2 mm box → 0.165 × 0.055 × 0.0052 m, mass
   from a stated density, and compare against an analytic drop: `z(t) = ½gt²`. 0.1 s of free
   fall must be 49.05 mm ± 1 %.
4. The MJCF writer must never scale a mesh *and* its `pos`/`size`: meshes are written in
   metres already, or written in millimetres with exactly one `<mesh scale="0.001 0.001
   0.001">`. One of the two, never both, asserted by a test that reads back the emitted XML.

---

## 6. Mass, centre of mass and inertia

Measured API surface in `build123d 0.13.0` (verified in this environment, and against
<https://build123d.readthedocs.io/en/latest/direct_api_reference.html>):

| Need | Call | Verified fact |
|---|---|---|
| volume | `shape.volume` | property, mm³ |
| COM | `shape.center(CenterOf.MASS)` | **not** on base `Shape`; on `Solid`/`Compound` (`Shape.center` → `AttributeError`) |
| inertia | `shape.matrix_of_inertia` | `list[list[float]]`, 3×3, **about the COM**, units **mm⁵** |
| validity | `shape.is_valid` | property, no parentheses since 0.10.0 |
| tessellate | `shape.tessellate(tolerance, angular_tolerance=0.1)` | returns a **2-tuple** `(vertices, triangles)` |

The inertia unit was established empirically, not assumed: a 20 × 40 × 25 mm `Box` returns
diagonal `3.708333e6, 1.708333e6, 3.333333e6`, which equals `m(b²+c²)/12` with
`m = volume = 20 000`. So `matrix_of_inertia` is `∫r² dV` in mm⁵ (unit density), and

```
I_kg_m2 = I_mm5 * rho_kg_m3 * 1e-9 * 1e-6      # == I_mm5 * rho_g_cm3 * 1e-12
mass_kg  = volume_mm3 * rho_g_cm3 * 1e-6
```

For PETG at 1.27 g/cm³ (1 270 kg/m³) that is `1.27e-12` per mm⁵. Feeding `params.toml`'s
`density_g_cm3 = 1.27` straight into a kg/m³ formula is wrong by 1e3; feeding it into a
kg/mm³ formula is wrong by 1e6. The two formulas above are the only accepted ones. Spot values: body 1.78e-4 / 5.80e-4 /
5.95e-4 kg·m²; chassis 1.18e-4 / 3.83e-4 / 4.99e-4; crank 1.58e-6 / 5.5e-7 / 2.12e-6.

**Validation rules** (M2 gate, all pure `numpy`):

1. `mass > 0`, `det(I) > 0`, all eigenvalues `> 0` (positive definite).
2. Triangle inequality on principal moments: `I1 + I2 ≥ I3` (within 1e-9 relative).
3. Upper bound: `I_i ≤ m * (d_j² + d_k²)` where `d` is the bbox diagonal component — the
   point-mass bound.
4. **Do not** bound inertia by the solid-bbox value `m(b²+c²)/12`. That is only valid for a
   uniform solid; a thin shell legitimately exceeds it. Measured counter-example: the Pocky
   body's ratios to that value are 1.43 / 1.18 / 1.22. A check written that way would reject
   correct geometry.
5. Cross-check `mass` from `volume × density` against a measured mass when one exists; a
   mismatch above 10 % is `INCONCLUSIVE`, not a silent preference.
6. For a body whose parts are fixed together, sum masses and combine inertia with the
   parallel-axis theorem about the group COM — never average the parts' matrices.

`Shape.center` not existing on the base class is a real trap: `ModelPart.shape` is typed
`object` (`cadkit/model.py:21`), so the physics layer must accept only `Solid`/`Compound` and
fail with a clear message otherwise.

---

## 7. Geometry → MJCF

### 7.1 Visual vs collision

Visual: `cadkit.mesh.shape_to_mesh` at its existing tolerance (0.02 mm linear, 0.1 rad
angular) — the same tessellation the renderer and the checks already use, so a physics
picture and a render picture cannot disagree about shape. Written to
`<run>/assets/<part_id>.stl` in **metres**.

Collision: never the visual mesh, except for a genuinely convex part. MuJoCo replaces a mesh
collider with its convex hull — "Meshes specified by the user can be non-convex, and are
rendered as such. For collision purposes however they are replaced with their convex hulls"
(<https://mujoco.readthedocs.io/en/stable/computation/index.html#collision>). For a housing
with a bore, an exit aperture and a floor slot, that is fatal: the hull seals every opening.

**Rule:** a part with any opening must declare `ColliderSpec`s. A part declared in the
assembly with `visual="cad"` and zero colliders is `SCENE_INVALID`, never silently hulled.
An opt-in `convex_hull` fallback exists only for parts flagged `role="mechanism"` where a
hull is conservative in the harmless direction, and it must be declared explicitly.

### 7.2 Pocky collider recipe (manual, from measured CAD)

| Part | Recipe | Preserves |
|---|---|---|
| `body` | 4 floor boxes around the floor slot; 2 side walls (y ±30…32.4); front wall above z 9.20; back wall split into 3 boxes around the 4.4 mm notch; 2 shim-ledge boxes; 2 lip bars + ties; 2 chassis-hook ribs | floor slot, exit aperture, back notch, bore. **The floor boxes are load-bearing for S0**: the body lands on the pusher through them, so they must not be merged across the slot |
| `chassis` | base plate box; boss cylinder; 2 stop boxes; 2 guide rails + plinths; spring pocket floor + 3 walls; 2 clip posts + 2 teeth | pivot bore, pocket, clip geometry. **A convex hull of the chassis is forbidden**: its bbox tops at z 2.45 (the tooth tops) against a real base top of −15.6, so a hull would invent 4.85 mm of phantom support under the body and fake the "rests on two posts" result (§1.4) |
| `lip` | shelf box (with a 0.8 mm chamfer box at the packet-facing edge); 2 cheeks; separator blade box; 2 feet; 2 hook rails + teeth | separator gap, shelf height |
| `crank`, `rod`, `pusher` | boxes + one cylinder for the bullnose; the bullnose **must** be a cylinder, its radius is the contact surface | joint holes are irrelevant to collision |
| `spring` | 12 beam boxes + 2 pads + 11 fold cylinders, or one convex `convex` per fold group | rigid collision geometry only; equivalent joint/tendon spring defines stiffness, not collider decomposition |
| `shim_04_*` | one box each | ledge height |
| `packet` | **one rigid box 165 × 55 × 5.2** (user-directed proxy) | — |

The packet is a rigid rectangular proxy by explicit user instruction
(`docs/mujoco-orchestration.md`, objective amendment). It is not a retail-box redesign and
not a foil model. Wrapper deformation, creasing and puncture remain outside the model.

### 7.3 Aperture preservation and negative tests

Three independent checks, each with a failing case:

1. **Free-space probe.** Sample a grid through each declared opening — for Pocky, the exit
   (x 85…88, z 0.1…5.1, y ±27.5) and the bore interior (x −84…84, y ±29, z 0.1…4.9) — and
   assert no collider occupies any sample point. Failing case: a hull collider of `body`
   occupies the bore, and the probe reports the first blocked sample.
2. **Transit test.** Translate the packet proxy from its ready pose to 40 mm past the exit
   along +X in 0.5 mm steps and assert zero intersection with any structure collider.
   Failing case: the same hull makes transit fail at x ≈ 85.
3. **U-channel regression** (project-agnostic, per `plan-mujoco.md` §M2). A U-channel solid
   with one collider = hull, drop a sphere, assert it is blocked; with a 3-box recipe, assert
   it passes. This test lives in `tests/test_cadkit_physics_collision.py` and is the
   proof that the recipe machinery is real, not Pocky-specific.

Additionally, per part: max collider-to-CAD surface deviation near critical contacts, in mm,
computed with `trimesh.proximity.closest_point` in both directions and reported. Anything
above 0.2 mm near the bore, the separator or the clip bearing patches is a scene warning.

### 7.4 MJCF emission

Author readable XML, deterministically. Version-sensitive choices, checked against current
docs:

- Load path: `mujoco.MjModel.from_xml_path(...)` + `mujoco.MjData(model)` — the documented
  factory ("The `mujoco.MjModel` class does not have a Python constructor. Instead, we
  provide three static factory functions", <https://mujoco.readthedocs.io/en/stable/python.html>).
- **Do not** use the `assets=` dictionary. It is deprecated: "The previous way of passing
  assets via a dictionary mapping asset names to bytes is deprecated and will be removed in
  the next release … `MjVfs` should be used as a drop-in replacement"
  (<https://mujoco.readthedocs.io/en/stable/python.html>). Note that the same page's minimal
  example still shows the deprecated form; the surrounding warning is authoritative. Use
  `mujoco.MjVfs` if an in-memory pipeline is ever needed; for the normal path, relative
  asset paths in `<run>/assets/` are simpler and are what the replay hash covers.
- `MjSpec` is stable and usable for programmatic authoring ("introduced in 3.2.0 as an
  in-development feature, is now stable and recommended for general use",
  <https://mujoco.readthedocs.io/en/stable/changelog.html>), but the plan's choice stands:
  emit XML first, because XML is diffable and is itself evidence. `MjSpec` is an M4+
  internal option only if XML emission proves error-prone.
- Defaults that must be stated explicitly in every emitted model rather than inherited:
  `timestep` (MuJoCo default 0.002 s; the plan wants 1e-3 s —
  <https://mujoco.readthedocs.io/en/stable/XMLreference.html>), `integrator` (default
  `Euler`), `cone` (default `pyramidal`), `solver` (default `Newton`), `iterations`
  (default 100). A model that omits them is not reproducible across a MuJoCo upgrade.
- Contact parameters: `contype`/`conaffinity` filter by common bit
  (`(contype1 & conaffinity2) || (contype2 & conaffinity1)`); `condim` selects 1/3/4/6;
  `solref` is `(timeconst, dampratio)` or negative `(-stiffness, -damping)`. Use `condim=3`
  for structure/packet and reserve torsional terms for a measured justification.
- Headless stepping: `mujoco.mj_step(model, data)` only. `viewer.launch_passive` requires
  `mjpython` on macOS ("On MacOS, `launch_passive` requires that the user script is executed
  via a special `mjpython` launcher", same Python page) and is therefore a **separate,
  optional** command that no batch test touches.

Determinism: bodies, geoms, joints, actuators and materials are emitted in a fixed sorted
order; floats are formatted with `repr`-stable `%.9g`; the scene XML is hashed and the hash
is part of the run id.

---

## 8. Assembly stability as a first-class scenario

This section is the architecture response to §1.4 and to the user amendment.

### 8.1 Three distinct claims, never conflated

| Claim | Modeled how | Counts as |
|---|---|---|
| `support_static` | pure geometry: bearing **direction** per connection + support polygon vs COM; no solver | design check, cheap, deterministic |
| `assembly_stability` | every body free, real connections only, gravity, no actuation | **product prerequisite** |
| `fixture_stability` | body or chassis welded/fixed to world | diagnostic only, never acceptance |

### 8.2 Baseline assembly, declared honestly

The baseline must be built from an **explicit assembly source**, not by enumerating
`build()` output. Measured reasons:

- `prototype_solids` (`projects/pocky/geometry/prototype.py:835`) passes
  `PROTOTYPE_SPRING.free_length` (53.4 mm) to `moving_solids`, and its own docstring says the
  free spring "runs 3 mm into the seat insert". Measured overlap spring ∩ `spring_seat`:
  **210.0 mm³**. A contact solver given that as an initial state starts in deep
  interpenetration. Using `compressed_length(0.0)` = 50.4 mm gives **0.0 mm³**.
- It also returns a bench `dummy` parked at y 77.5…132.5 and a spare `shim_08` at
  x 112…124, neither of which is part of the unit. Enumerating `build()` would put a 59.9 g
  mass 105 mm off-axis into any COM or stability computation.

So `AssemblySpec` is assembled from `static_solids(...)` + `moving_solids(..., compressed_length(0))`
minus the spares, with an explicit initial-penetration gate that would catch a regression.

Bodies:

- `body` + `shim_04_a` + `shim_04_b`: one free body (the shims sit on the body's ledges and
  are not otherwise retained).
- `lip`: its own free body, resting on the two shims and located by its two hook rails against
  the body's bars, measured at **0.15 mm** clearance (`m0_pairs2.py`). Grouping it with the
  body would silently delete that degree of freedom; M5a must confirm the lip cannot walk off
  its bars under presentation load, or the grouping must be justified by a measured preload.
- `chassis`: free body resting on the world floor plane.
- `crank`, `rod`, `pusher`, `spring`, `spring_seat`, three pegs: jointed mechanism bodies,
  with the joint chain the CAD actually has (pivot on the chassis boss, pegs through their
  holes/slots, spring between its seat and the rod pad).
- `packet`s: free bodies.
- **Excluded**: `dummy` (bench artifact) and `shim_08` (parked spare). The schema needs an
  explicit `role: housing | mechanism | packet | spare` rather than implicit enumeration.

No `fixed_to_world` anywhere in the baseline. The clips are **contacts**, not welds — a weld
would assume a connection the design does not have.

### 8.3 The static preflight (no MuJoCo required)

Two independent checks, both pure geometry:

1. **Bearing-direction check.** For each declared connection, assert the contact normal can
   carry the load direction that gravity applies. For the current clips this returns
   `bearing_direction = +Z only` (tooth underside z 0.05 above rib top 0.00), i.e. a
   **retention-only** connection with no downward seat. This is the check that states the
   finding directly.
2. **Support-margin check.** `support_margin(com, bearing_patches)` returns
   `support_polygon_area_mm2`, `convex_hull_vertices`, `strip_width_mm`, `com_inside`,
   `com_margin_mm`, and `gravity_moment_Nm`.

For the current CAD: `bearing_direction=+Z`, `com_inside=False`, margin **−4.54 mm**
(hanging group) / −6.86 mm (body alone), strip width 4.23 mm, moment 9.5 mN·m
(evidence: `out/pocky/prototype/physics/m0-20261021/evidence.json`). Both numbers are
reported; the conclusion does not rest on the polygon alone.

### 8.4 Scenario `S0 assembly_stability`

The gate must be a **relative-pose** test, not "the assembly stays upright". Measured: the
unit without the dummy is 280.6 g with COM (0.19, −0.84) mm, inside the base-plate footprint
(x −115…110, y −20.2…55), so the *unit* is comfortably stable on the bed whatever the body
does. An uprightness test passes trivially.

```
phases: settle 3.0 s (no actuation), chassis on the ground, nothing fixed
sweep:  button fractions {0, 0.25, 0.5, 0.75, 1.0} — the arrest point migrates across the
        stroke (carriage at rest -> peg head at full), so one pose is not enough
metrics: rel_rotation_deg(body,chassis), rel_translation_mm(body,chassis),
         body_contact_with_moving_part (part name, point, normal force),
         body_drop_mm, settled_last_0.5s_mm, initial_penetration_mm3
required (per fraction): rel_rotation <= 0.1 deg
                         rel_translation <= 0.05 mm
                         body_contact_with_moving_part == none
                         initial_penetration <= 0.01 mm3
```

**Expected baseline result for the current CAD: FAIL**, with body rotation > 0.4° (the
mechanism settles before it can hold anything, §1.4 item 6) and contact on the pusher
carriage. That is the honest expected outcome, recorded before M5a runs so that a larger
measured angle is not mistaken for a scene bug. M6 must fix it by changing CAD support, never
by touching the evaluator.

Two further requirements that follow from the settle:

- The packet-feed scenarios must start from the **settled** pose, not the CAD pose: the 0.4 mm
  body settle lowers the bore floor relative to the crank-fixed bullnose and therefore changes
  the pusher face's height on the packet.
- `resting_on_mechanism` remains a named metric so a candidate cannot pass by leaning on a
  moving part.

An explicitly labelled diagnostic may exist for debugging:

```
cad physics run pocky/prototype --scenario S0 --fixture diagnostic
```

It fixes the body to the world, is written with `fixture="diagnostic_fixture"` in its
manifest, its report header says `DIAGNOSTIC — NOT ACCEPTANCE`, and the evaluator returns
`INCONCLUSIVE` for any required predicate on such a run. Fixing the housing to the world to
make the feed scenarios look clean is exactly the failure mode the amendment forbids.

### 8.5 What "supported" means for the packet

Per the user amendment, product success is: **exactly one identified packet** advances
through the actual exit aperture in the intended direction, reaches a stable, partly
protruding, supported, accessible pickup pose, and **stays there after the input is
released**. Not a momentary plane crossing; not a complete fall-out; not two packets; not a
protrusion sustained by an unrealistically fixed or unstable housing.

Encoded as: an `exit_crossing` event with packet identity, direction (+X), and a dwell
requirement (packet centre beyond the outer face, `protrusion_mm` stable within ±1 mm for
0.5 s after release, and the packet's COM inside its own support hull, computed from the
contacts actually present). The 40 mm number is a **provisional design target**
(`plan-first-prototype.md:34`), stored with `Source("assumed", "documented target, not user-measured")`,
and used as an informational metric until Codex or the user fixes a threshold.

Packet pickup in repeated cycles is an explicit `pickup` phase event: the runner logs
`external_action: pickup, body: packet_k, t: …` and removes the body from the world. It is
never a silent repositioning, and a run that needs a scripted packet pose is a FAIL by
construction (the runner has no API to set a packet `qpos` after `t=0`).

---

## 9. Generic vs Pocky responsibilities

| Generic (`cadkit.physics`) | Pocky (`projects/pocky/physics/`) |
|---|---|
| schema, units, inertia, mesh export | `assembly.py`: the body/chassis/lip/mechanism/joint map for this CAD |
| collider primitives + validation + U-channel regression | collider recipes for the bore, exit, separator, slot, clips |
| MJCF emission, solver options, determinism | `materials.toml`: PETG↔wrapper, wrapper↔wrapper, provenance |
| runner phases: settle/actuate/release/pickup | `scenarios.py`: P0–P9 and S0 concrete definitions |
| telemetry primitives: poses, contacts, forces, energy | packet-identity tracking, exit event, double-feed, jam |
| predicate evaluation, RunResult, report, replay | `acceptance.toml`: this pilot's thresholds, frozen |
| support-polygon preflight | which patches are bearing surfaces here |
| sweep harness with frozen evaluator | candidate parameter list and budgets |
| viewer (optional) | nothing |

A rule worth stating: **`cadkit` must contain no word "pocky", no packet dimension, no
separator height.** The independent fixtures in §14 are how that is proved.

---

## 10. Contact-sensitive geometry inventory

Parts and features whose contact behaviour decides a result, and therefore may not be
approximated silently:

| Feature | Where | Why it is sensitive | Recipe |
|---|---|---|---|
| Exit aperture lip and its 2.6 mm chamfer | `_body` | the packet must exit and not snag; a hull seals it | front wall box starting at z 9.20; chamfer ignored or one rotated box |
| Separator blade lower R0.8 edge | `_lip` | decides one-vs-two packets; 0.8 mm is the discrimination scale | blade box + 0.8 mm chamfer box |
| Floor slot around the pusher neck | `_body` | the pusher must travel through it, and it is a body support hole | 4 floor boxes |
| Bullnose (R2.1 cylinder) | `pusher_solid` | the only packet-driving surface; it is above the floor, not on it | cylinder, not a box |
| Carriage top under the body floor | `pusher_solid` | 0.4 mm clearance — the incidental body support found in §1.4 | box; must exist or the defect is hidden |
| Clip tooth underside and rib top | `_chassis_hook` | 0.05 mm gap; the entire body retention | box pair, 0.05 mm gap preserved |
| Shim ledges and shim plates | `_body`, `_shims` | set the separator gap; 0.4 mm parts | box each |
| Lip feet on the shims | `_lip` | the lip's whole load path | box each |
| Spring beams and folds | `spring_solid` | rigid geometry clearance; calibrated equivalent spring supplies return force | 12 beams + 11 fold cylinders |
| Rod guides and their 0.3 mm clearance | `_chassis` | jamming sensitivity | boxes |
| Pivot boss and counterbore | `_chassis` | crank location; the peg seats there | cylinder + box |

Every one of these must appear in the run's `collision_overlay` artifact: visual mesh at
20 % opacity with colliders in a second colour, so a wrong proxy is visible rather than
inferred.

### 10.1 The linkage is simulated as a linkage, never as a pose map

`projects/pocky/geometry/linkage.py` already contains a *kinematic* solution: `pose_at_phi`
maps a crank angle to a face position, a button travel and a packet shift, and
`projects/pocky/docs/prototype_animation.py` plays that map in a viewer. That map is a
geometry record and is explicitly not a bench result (`report-current-progress.md` §Not done).
It must **not** be reused as the physics input, because a pose map can move the pusher through
the packet without any force, which is precisely the "powered pose mapping" the plan forbids.

The MuJoCo model therefore contains the real constraint chain, one body per rigid part. The
actual topology, read from the CAD rather than assumed:

- `crank`: a 180° bar on a **hinge** at (−78, −8) about Z, sitting **below** the carriage and
  **above** the rod (crank z −11.2…−7.2; carriage −6.8…−2.8; rod −15.6…−11.6).
- `rod`: **prismatic** along X at y = −28. Its pin (Ø4) sits in the crank's **radial** slot
  (`button_slot_radii` → a stadium along crank-local −X, radii 19.0…24.1, width 4.6), so the
  pin's radius from the pivot varies with button travel.
- `pusher`: **prismatic** along X, y free-constrained by its own geometry. Its slot is a
  stadium along **Y** at the pin's x (`pusher_slot_ends` → y 34.3…43.0, width 4.6), and the
  crank's second pin rides in it.
- `spring`: between the seat on the chassis and the rod's pad face.

Both crank interfaces are therefore **pin-in-slot with a varying radius**, not point-to-point
constraints. That rules out a plain `connect` equality (it would pin the pin at a fixed crank
point and delete the slot travel). The physically faithful model is **contact**: a cylinder
collider for each pin, and two boxes plus two end-arc cylinders for each slot. That is real
work and it belongs in M3, not M2 — but it is the only representation in which the required
button force means anything.

`pose_at_phi` is used only for two legitimate purposes: (a) generating the *initial*
configuration of the mechanism at button travel 0, and (b) as an independent cross-check —
if the simulated crank angle and the analytic pose disagree by more than a stated tolerance at
the same button travel, that is a modelling bug (`INCONCLUSIVE`), not a design result.

The pin-in-slot pairs are the risky part. `plan-mujoco.md` §5.3 already anticipates this:
if the closed chain is not stable under MuJoCo's joint/equality/contact modelling, the
conservative simplification is a `slide` joint on the carriage with the crank's motion driving
it through a declared force, **and the linkage-force conclusions are marked `INCONCLUSIVE`**
until a physically credible representation is verified. What is never allowed is deleting the
chain and setting the pusher's position from `pose_at_phi` per step.

---

## 11. Dependency and index proposal

`mujoco 3.16.0` (released 2026-10-14) is Apache-2.0, `requires-python >=3.10`, and ships
`mujoco-3.16.0-cp312-cp312-macosx_11_0_arm64.whl` — the exact wheel this machine needs
(verified from `https://pypi.org/pypi/mujoco/json`). There is **no** macOS x86_64 wheel, so
the extra is arm64-macOS/Linux/Windows only and must say so.

**Two independent blockers, both measured.** M1's "uv install" gate cannot pass until both
are addressed:

1. **`uv` is not on `PATH`.** It exists only at `~/.local/bin/uv`. Any test or helper that
   shells out to bare `uv` fails; 6 of 8 tests in `tests/test_cadkit_export_cli.py` and 2 in
   `tests/test_pocky_geometry.py` currently fail this way. Fix: either add `~/.local/bin` to
   `PATH`, or change the test helper to resolve the interpreter via
   `shutil.which("uv") or sys.executable`. **Not** an M1 silent edit — the test helper is
   existing user code.
2. **The default index does not resolve.** `pyproject.toml` sets
   `https://pypi.apple.com/simple`; DNS fails here while `pypi.org` returns 200. `uv run`
   fails before physics is involved, because building the project needs `hatchling`.

Changing `[[tool.uv.index]]` or adding a fallback index is a **config decision for Codex/the
user**, not something M1 may do silently. Proposed, minimal:

```toml
[project.optional-dependencies]
physics = ["mujoco==3.16.0"]

[[tool.uv.index]]
name = "pypi"
url = "https://pypi.org/simple"
explicit = false      # keep it a fallback, not the default
```

`explicit = false` means the Apple index is still tried first and `pypi.org` is a fallback;
`uv lock` then records both. If Codex prefers zero index change, the alternative is a
documented `UV_INDEX_URL=https://pypi.org/simple uv sync --extra physics` invocation — but
then the lockfile is not reproducible from `pyproject.toml` alone, which conflicts with the
plan's reproducibility requirement. **This is a decision for Codex** (§20 Q1).

Not proposed: installing MuJoCo globally, adding it to `[project.dependencies]`, or adding
`coacd`/`vhacdx` (verified absent). Convex decomposition is explicitly a later opt-in; the
recipes in §7.2 are manual and checked.

---

## 12. Output, cache, provenance, replay

```
out/<project>/<model>/physics/<run_id>/
├── manifest.json      # versions, platform, hashes, all inputs with provenance, seeds
├── scene.xml          # the emitted MJCF, byte-identical to what was compiled
├── assets/*.stl       # generated ORIGINAL meshes, metres
├── summary.json       # RunResult
├── report.md          # human/agent readable; states every INCONCLUSIVE reason
├── traces/*.csv       # per-step series, named columns, SI units in the header
├── states/*.npz       # sampled qpos/qvel/act/ctrl for replay
├── collision_overlay.png
└── acceptance.lock.json  # copy of the frozen evaluation, with its hash
```

- `run_id = <UTC compact timestamp>-<scene_hash[:8]>`.
- `scene_hash` covers: the emitted XML, every asset's SHA-256, the resolved `AssemblySpec`,
  the frozen `EvaluationSpec`, the `mujoco` version and the platform tag.
- **Cache:** a result is reusable only when all of `scene_hash` plus the scenario name, seed
  and MuJoCo version match. Changing a CAD parameter, a mass, a friction coefficient or an
  acceptance threshold invalidates it. Cache index at
  `out/<project>/<model>/physics/.cache.json`.
- **Immutable acceptance:** `acceptance.toml` lives in the project, is read once per run,
  copied into the run dir, and hashed. `cad physics replay` refuses to run when the copied
  lock and the current acceptance file differ, and says which predicate changed. Sweeps
  cannot write acceptance; a test asserts the file's hash is unchanged across a sweep.
- **Replay:** load `scene.xml`, set `qpos/qvel` from the first saved state, re-run with the
  recorded controls, and compare the final state and the metric vector against `summary.json`
  within a stated tolerance. Cross-platform bit-equality is not claimed; same-platform
  reproduction within tolerance is.
- **Non-Git safety:** before any sweep or candidate edit, write a timestamped copy of the
  affected source files plus SHA-256 into `out/<project>/<model>/physics/snapshots/`. The M0
  snapshot at `~/.omp-bridge/backups/cadstudio-mujoco-20261021T095832Z/` (69 files, manifest
  verified unchanged by this packet) is the baseline of record.

---

## 13. CLI

One entry point, one new verb, same `<project>/<model>` selection:

```bash
cad physics export pocky/prototype [--out DIR]        # emit scene.xml + assets, compile-check
cad physics run    pocky/prototype --scenario S0 [--seed 0] [--fixture diagnostic]
cad physics test   pocky/prototype --suite smoke|full
cad physics sweep  pocky/prototype --config sweep.toml
cad physics replay <run-dir> [--viewer]               # --viewer needs mjpython
```

- Exit codes: `0` PASS, `1` FAIL, `2` INCONCLUSIVE, `3` ERROR. `cad check` already uses `1`
  for FAIL; this extends rather than changes that convention, and every non-PASS is nonzero.
- Every `physics` verb needs the extra, including `export`, because `export` compiles the
  emitted XML to prove it is valid. Each must print the actionable missing-extra message
  (`uv sync --extra physics`), never a CAD import traceback, and must exit `3` (ERROR) rather
  than `0`.
- `--views`/`--render` semantics do not apply. Rendering is never a dependency of
  export/test/sweep.
- `replay --viewer` runs `viewer.launch_passive`, which on macOS requires launching the
  process as `mjpython -m cadkit.cli physics replay …`; the CLI detects a non-`mjpython`
  interpreter and prints the exact command instead of failing obscurely.

---

## 14. Independent, non-Pocky fixtures (required by the plan)

These prove the layer is not bespoke dispenser code. Each is a few lines of `build123d`.

1. **`gravity_drop`** — a 20 mm box released 100 mm above a fixed plane. Assert: free-fall
   displacement matches `½gt²` within 1 % at 0.1 s; rest height equals the box half-height
   within 0.1 mm; no penetration beyond `solref` tolerance. Detects unit errors, wrong
   gravity sign, wrong mass.
2. **`incline_friction`** — a box on a plane tilted in 1° steps. Assert: the box stays until
   `tan θ > μ` within 1°, then slides. Detects a friction coefficient applied to the wrong
   pair or in the wrong units.
3. **`u_channel`** — the concavity negative regression (§7.3).
4. **`loaded_spring`** — a slider joint with a declared `SpringSpec`, a mass, and an applied
   force. Assert: static deflection `F/k` within 2 %; release oscillation period
   `2π√(m/k)` within 5 %; return to the preloaded rest within 0.1 mm after damping. Detects
   `N/mm → N/m` errors, wrong `springref`, and positional puppetry.
5. **`stack_settle`** — three boxes dropped with a small gap. Assert: final order preserved,
   no interpenetration, total energy non-increasing. Detects solver instability.
6. **`clip_retention`** — a cantilever tooth clipped over a rib (the Pocky clip shape,
   generalised). Assert: pull-off force within the beam estimate, and the body does not pass
   through when pushed. This is the fixture that would have exposed §1.4 in isolation.

---

## 15. Spring scope: printed PETG now, metal later

- **Current prototype:** variant B, printed PETG serpentine, 12 beams × 1.2 mm, 3.0 mm gaps,
  53.4 mm free, 50.4 mm installed, 3.0 mm preload, solid length 20.4 mm (measured from CAD,
  `prototype.py` `SpringSpec`, and locked by `tests/test_pocky_prototype.py`).
  Its stiffness is **not measured** — no coupon was printed and no rate was recorded
  (`plan-first-prototype.md:303–308`). Any value used is `Source("assumed", …)`.
- **Durability path:** metal compression spring, catalogue ≈ 0.30 N/mm per
  `projects/pocky/docs/m0-report.md:68` — that is a *proposal* number, not a measurement, and
  it is superseded for the current print by `plan-first-prototype.md:41`.
- Consequence for the physics layer: the spring model must take `(k, free_length, preload)`
  with provenance, not a hard-coded constant, and any scenario whose outcome depends on the
  return force is capped at `INCONCLUSIVE` until a measured `k` exists. The M3 loaded-spring
  fixture is therefore mandatory *before* any Pocky return-force conclusion.

---

## 16. Packet-feed acceptance, stated once

Frozen for all later packets (thresholds live in `projects/pocky/physics/acceptance.toml`,
reviewed by Codex, never edited by a sweep):

| Predicate | Threshold | Provenance |
|---|---|---|
| `exactly_one_dispensed` | 1 packet crosses the exit in +X per actuation | user objective |
| `no_double_feed` | no second packet escapes in the same actuation | `plan-first-prototype.md:289` |
| `protrusion_mm` | ≥ 30 (informational 30–50, target 40) | documented target, **not** user-measured |
| `dwell_after_release_s` | ≥ 0.5 with protrusion stable within ±1 mm | user: "remain there after input release" |
| `packet_supported` | COM inside the contact support hull | user: "supported" |
| `packet_accessible` | protruding end outside the housing envelope and graspable past the lip (provisional ≥ 15 mm; the lip is 18 mm) | documented 18 mm lip, threshold **proposed, not measured** |
| `no_fallout` | packet not free-falling at end of hold | user: "not complete uncontrolled fall-out" |
| `return_success` | joint back to its stop within 0.5 mm | `plan-first-prototype.md:291` |
| `assembly_stable` | S0 predicates | user amendment |
| `no_forbidden_penetration` | ≤ 0.2 mm on non-packet pairs | numeric |

`protrusion_mm ≥ 30` is *informational* until the user or Codex fixes it: the user specified
"sticking out of the hole" and no distance, and the 40 mm figure is a design target from the
prototype plan.

---

## 17. Physical measurement gaps (prioritised) and the M7 bench template

Ordered by how many results they can invalidate. Nothing here may be invented; a missing
`P1` item caps the affected scenario at `INCONCLUSIVE`.

| Priority | Quantity | Symbol / unit | Why it dominates | Method |
|---|---|---|---|---|
| P1 | Packet mass | `m_packet`, g | every force, energy and settle metric | 10 packets, 0.01 g scale |
| P1 | Wrapper ↔ PETG friction | `μ_s`, `μ_k` | decides whether gravity feed works at all | ramp, `μ_s ≈ tan θ`, 5 trials per print orientation |
| P1 | Printed spring rate | `k`, N/mm | return success and button force | load cell, 0.5 mm steps, 53.4→27 mm |
| P1 | Clip retention force | `F_pull`, N | the support defect in §1.4 | pull the body off the chassis with a spring scale; per clip |
| P2 | Wrapper ↔ wrapper friction | `μ_ww` | double-feed discrimination at 5.75 mm | two-packet ramp |
| P2 | Packet thickness distribution | `t`, mm | stack height and separator margin | 10 packets, centre + both seals |
| P2 | Print tolerance at joints | mm | peg/slot play feeds body motion | measure 4.6/5.4 mm features |
| P3 | Manual press force / time | N, s | actuator bound | hand press on a scale, 10 trials |
| P3 | Lip shelf deflection under a packet | mm | presentation support | dial gauge |
| P3 | Wrapper surface (fin, seal) | mm | contact geometry | 3 opened packets |

**Bench template** — `projects/pocky/docs/physics-calibration.md` (M7a deliverable), with a
machine-readable twin `projects/pocky/physics/bench.toml`:

```toml
[[measurement]]
quantity = "packet_mass"
unit = "g"
method = "0.01 g scale, 10 sealed packets"
samples = [7.1, 7.2, 6.9]          # actual readings only
uncertainty = 0.05
provenance = "measured"             # measured | derived | assumed | calibrated
date = "2026-11-02"
operator = "…"
notes = "…"
artifact = "photos/…"               # optional local path
```

A `provenance = "template"` value is allowed and must be rendered as `MISSING` everywhere;
the loader must refuse to treat a template row as a measurement.

---

## 18. Packet plan M1–M7 with acceptance and runtime

Times are what this machine actually showed for the CAD side: model build 1.18 s,
tessellation 1.49 s. MuJoCo step cost is **unmeasured** (not installed), so each packet that
introduces solver work must record its own measurement before a budget is treated as fixed.

| Packet | Scope | Acceptance (observable) | Runtime limit |
|---|---|---|---|
| **M1** | optional extra; lazy import; `gravity_drop` fixture; run skeleton; report | `cad build/render/check/list` work with `mujoco` absent; `uv sync --extra physics` installs 3.16.0; drop matches `½gt²` ±1 %; rest within 0.1 mm; same seed → same result twice | ≤ 60 s per run; suite ≤ 3 min |
| **M2a** | part/frame/visual export; collider schema; mass/COM/inertia; MJCF emission | every part's collider count and mass validated; inertia passes §6 rules; emitted XML hashes stable across two runs; rotated-frame test passes; 3MF/STEP untouched | ≤ 30 s for 15 parts |
| **M2b** | hollow fidelity; aperture probes; transit test; pin/slot collider pair; overlay | U-channel negative regression fails-with-hull / passes-with-recipe; Pocky exit probe clean; packet transit to 40 mm clean; overlay artifact written | ≤ 60 s |
| **M3** | joints (hinge + 2 prismatic + pin-in-slot contact), limits, damping, spring, actuator; `loaded_spring`; `clip_retention`; **S0 static preflight + stability scenario** | deflection `F/k` ±2 %; period ±5 %; return to stop within 0.1 mm; S0 reports `bearing_direction=+Z only` and body contact on a moving part at every button fraction — i.e. the defect is detected, not hidden | ≤ 120 s |
| **M4** | phases, telemetry, evaluation, reports, replay | each synthetic negative fixture produces its own named failure; replay reproduces metrics within tolerance; acceptance-hash mismatch refused; exit nonzero on non-PASS | ≤ 2 min per scenario |
| **M5a** | current Pocky assembly; S0 + P0–P3 | S0 honest **FAIL** with the real supports (expected: body rotation > 0.4°, contact on the carriage) at all five button fractions; P0 analytic; P1/P2/P3 start from the **settled** pose, never a scripted packet move; initial penetration ≤ 0.01 mm³; every unmeasured coefficient listed | ≤ 5 min for P0–P3 |
| **M5b** | P4–P9 dispense, partial stroke, friction extremes, tolerance, repeat with logged pickups | exactly-one-packet with identity; dwell after release; no double feed; partial stroke produces no dispense; pickup is a logged external action; honest diagnosis per failure | ≤ 15 min for the suite, serial |
| **M6** | bounded candidate iteration; snapshots; comparison | evaluator hash unchanged across a sweep (asserted); ≤ N candidates and ≤ T simulated seconds enforced; baseline and candidate run the same scenarios/seeds; a candidate that improves one metric and regresses another is reported as such | ≤ 30 min per sweep |
| **M7a** | calibration ingestion, bench protocol, provenance | bench template loads; template rows render as MISSING; measured values flow into materials/spring; ranges drive sweeps | ≤ 1 min |
| **M7b** | correlation and final audit | at least one simulated prediction compared with a measurement; disagreement reported, not smoothed; 50/100-cycle gates restated as **physical** gates, not simulated | ≤ 5 min |

Stage gates, reconciled (see §19.2): the **first prototype** is judged by
`plan-first-prototype.md`'s nine criteria and its 10-cycle run; the **50- and 100-cycle**
Gate D numbers stay the final reliability gates and are never satisfied by simulation.

---

## 19. Conflicts found, and how they are resolved

### 19.1 Paths and APIs in the plan that do not exist

| Plan says | Reality | Resolution |
|---|---|---|
| `uv run cadstudio physics …` | entry point is `cad` (`pyproject.toml`) | `cad physics …` |
| `tests/physics/`, `tests/projects/` | flat `tests/` | flat `tests/test_cadkit_physics_*.py` |
| `projects/pocky/geometry/ …` "existing physical solids" | `geometry/` exists, but the model is `geometry/prototype.py` + `models/prototype.py` | use `load_model(project, model).build(p)` |
| `projects/pocky/docs/physics-calibration.md` | does not exist | create in M7a |
| "current local checkout … not available" | it is available | this document supersedes the guesses |

### 19.2 Evidence provenance: print status is UNVERIFIED

Three separate claims, not interchangeable. Keeping them apart is what prevents a fabricated
trial:

| # | Claim | Source | Date | Status |
|---|---|---|---|---|
| 1 | "Nothing has been printed." / "No STL has been sliced or printed." | `report-current-progress.md:5`, `:82` | 2026-10-18 | historical record of that session |
| 2 | "Nothing here has been printed, and a picture is not a cycle count." | `projects/pocky/docs/assembly.md:3` | 2026-10-19 | same |
| 3 | "a mechanism animated correctly and parts printed, but gravity-dependent physical operation failed" | `plan-mujoco.md:6` | plan narrative | **no log, artifact or measurement behind it**; not adopted |
| 4 | "the body model isn't stable and would immediately fall down in a physics simulation, it's resting on only two posts from the chassis" | user, via `docs/mujoco-orchestration.md` amendment | 2026-10-21 | **a prediction about a simulation** plus a structural observation — not a reported print trial |
| 5 | "No spring, body, chassis, lip, or shim solid exists yet" | `plan-first-prototype.md:5` | same file | stale line, contradicted by the rest of that file |

**Print status: UNVERIFIED.** The only repository artifact that suggests print preparation is
`out/pocky/prototype/plate.3mf` (PrusaSlicer metadata, 2026-10-19 00:39) — a plate was
**sliced**. There is no `projects/pocky/docs/prototype-log.md`, no photograph of a print, and
no bench record. So the accurate statement is: **a plate was sliced; a print is unverified; no
bench record exists.**

The user's sentence is a prediction, and its structural half ("resting on only two posts") is
what §1.4 verifies independently from the solids. Nothing in this packet asserts that a print
exists, and nothing asserts a physical failure occurred. `plan-mujoco.md`'s framing is
recorded as claim 3 and explicitly not adopted.

### 19.3 Gates: first prototype vs 50/100 cycles

`plan-first-prototype.md:11` claims precedence over `plan-pockey-dispenser.md` "where it asks
for a metal spring or for Gate D cycle counts … until the printed prototype has been accepted
or rejected", and `report-current-progress.md:3` agrees. Therefore:

- **Stage 1 (the first prototype, whether or not it has been printed yet):** nine criteria +
  a 10-cycle run, PETG only, no metal parts (`plan-first-prototype.md:285–297`).
- **Stage 2 (durability):** 50 consecutive cycles at 10 packets and 100 at 25 packets, zero
  double feeds/jams/interventions (`plan-pockey-dispenser.md:220–221`), after a metal spring.
- **Neither stage is weakened**, and simulation satisfies neither. The physics layer's job is
  to predict and diagnose, not to accept.

### 19.4 Numeric conflicts inside the existing docs (recorded, not silently fixed)

- `projects/pocky/docs/m0-report.md:68` says the return spring is metal at ≈ 0.30 N/mm and
  the separator uses two 0.20 mm shims; the current print uses a printed PETG spring and
  0.4 mm shims. `plan-first-prototype.md:41–43` supersedes both. Physics must take the spring
  from the prototype spec, not from the M0 report.
- `projects/pocky/docs/prototype-plan.md` is a 205-byte stub; it is not a source of truth.

---

## 20. Open questions for Codex

1. **Install blockers (blocks M1).** Two independent ones: `uv` is not on `PATH`, and the
   default index `https://pypi.apple.com/simple` does not resolve. Add a fallback `pypi.org`
   index to `pyproject.toml`, or require `UV_INDEX_URL` at sync time? And is changing the
   `uv`-shelling test helper in scope, or must the environment `PATH` be fixed instead?
2. **`protrusion_mm` threshold.** Keep 30 mm as informational with 40 mm as the documented
   target (measured from `link.outer_x`), or freeze a number now? The user specified
   protrusion without a distance.
3. **S0 pass criterion.** Confirm the proposed relative-pose gate: `rel_rotation ≤ 0.1°`,
   `rel_translation ≤ 0.05 mm`, `body_contact_with_moving_part == none`, swept over button
   fractions {0, 0.25, 0.5, 0.75, 1.0}. Should `support_com_margin_mm > 0` also be required
   given the clips are retention-only and that number is now hypothetical?
4. **Bounded support redesign in M6.** §1.4 shows there is no downward bearing seat; a
   candidate needs a real body–chassis support surface, which is a geometry change beyond a
   parameter, and "add a third clip in Z" does not address it. Does that stay inside M6's
   "bounded candidate" scope with unchanged evaluation rules, or does it need its own review
   gate before implementation?
5. **Measured clip force.** Should M7a's `F_pull` (retention, +Z) and a body↔carriage friction
   value be required before any S0 verdict is upgraded from `INCONCLUSIVE`, given that they
   decide how far the body actually settles?
6. **Settled-pose baseline.** Confirm that M5a's feed scenarios must initialise from the
   settled assembly rather than the CAD pose (the 0.4 mm body settle changes the bore floor
   height relative to the crank-fixed bullnose), and that the settled pose is recorded as
   part of the scene hash.


## 21. Codex supervisor resolutions after M0 (authoritative over proposals above)

M0 independently reviewed on 2026-10-21. These resolutions remove the listed M1 blockers and qualify the conceptual contracts; they are not measured physical findings.

1. **Corrected mass formula:** `mass_kg = volume_mm3 * rho_g_cm3 * 1e-6`. The earlier draft's `/1000` was off by 1000; the actual M0 probe correctly divided twice and its recorded masses remain valid. Independently checked a 20 × 40 × 25 mm box at 1.27 g/cm³: 0.0254 kg; body volume 109789.2323 mm³ gives 0.139432325 kg. M1 must lock this with an analytic unit test.
2. **Project installation:** replace the unreachable project's default index with standard `https://pypi.org/simple` in `pyproject.toml`, regenerate `uv.lock` and install the optional physics extra. This local manifest fix is authorized as necessary setup. Preserve existing dependency versions where available, document any unavoidable resolution changes and run CAD regression checks; never modify user/global package-manager configuration. Use `/Users/daniel_l_newman/.local/bin/uv` or prepend that directory in the test process environment. Do not rewrite existing tests to hide PATH failures. Record how ordinary documented commands work with the corrected local environment.
3. **Acceptance defaults to freeze by M4:** minimum 30 mm protrusion measured beyond outer face x=88 mm; target 40 mm informational; at least 10 mm exposed beyond the 18 mm lip shelf; hold ≥0.5 s after release, protrusion change ≤1 mm. These are explicit provisional engineering choices based on current design, not user measurements. Exact one identity, supported COM, no uncontrolled fallout, no second packet, and actual housing stability are required. Freeze all before candidate evaluation; report their provenance.
4. **S0 stability:** evaluate real load paths and relative body/chassis motion, with no hidden restraints. All five initial button fractions remain required. No unintended sustained weight-bearing contact onto moving parts is the principal structural predicate. Proposed tight numeric pose tolerances are provisional engineering diagnostics to review/freeze against real clearance and solver convergence in M3/M4, not physical measurements. Do not require a hard-coded 0.4° outcome: the CAD prediction must be compared with genuine dynamics, and discrepancies investigated rather than forcing the trajectory. Valid numerical failures can be reported as scenario FAIL under declared inputs; physical reliability remains INCONCLUSIVE if critical unmeasured inputs matter. Positive support margin is supplementary and cannot turn retention-only clips into weight-bearing seats.
5. **Later support correction:** a small original CAD support-seat/bracing redesign is authorized within M6 to achieve the user's stable dispenser objective; preserve source baseline, present a concrete design before implementation for Codex review, avoid mechanism replacement, and run unchanged CAD/physics gates. It is not authorized inside M1. No new human permission is required for this bounded reversible work.
6. **Clip calibration:** missing pull-off force does not prevent an informative static finding or simulated failure. Physical PASS involving clip retention requires measured evidence or documented robust bounds. Do not add unmeasured retention preload to rescue the scene.
7. **Initial state:** derive from actual gravity-settled assembly and record initial and settled states. The scene/initial-state identity must include the resulting state before feed trials; never teleport packets to satisfy readiness. Restraining a baseline housing produces diagnostic results only.
8. **Rigid-body scope:** spring collision primitives do not produce elastic stiffness. Use a justified equivalent joint/tendon spring and declared spring constant for the printed PETG return element. Do not attempt flexible clip/PETG beam deformation in the initial implementation; a rigid clip fixture cannot validate elastic pull-off force. Defer that proposed fixture and mark related physical claims unverified.
9. **Generic fixtures:** a fixed floor/fixture is legitimate for analytic gravity/spring tests and is not automatically a non-acceptance diagnostic. Distinguish intentionally fixed analytic test fixtures from unjustified product restraints. Only the latter disqualify product-acceptance claims.
10. **Conceptual schema only:** the sample dataclasses above must not be copied blindly (default ordering and mixed authoring units need explicit implementation decisions). Use unambiguous field units, finite-value validation, status-specific exit codes (ERROR=3) and lazy imports. Do not infer quality from emitted tokens or configuration alone.
