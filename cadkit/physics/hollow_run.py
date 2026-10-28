"""M2b evidence: live passage through the hollow channel, and the sealed-hull negative.

Two independent runs:

* **positive** — the correct recipe, exported and compiled, with a free cubic probe released
  above the cavity mouth. It must fall under gravity, enter the channel, and pass the fixed
  criterion plane under contact alone. No ``qpos`` is written after ``t = 0``.
* **negative (diagnostic)** — the *same* CAD, but collided as its convex hull, exactly as
  MuJoCo treats a single concave mesh. The probe must be stopped well above the criterion
  plane, demonstrating that the hull seals the cavity.

The diagnostic scene is a test-only artifact written into the run directory. It is never
produced by ``cadkit.physics.scene`` and is not a design of record.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
from datetime import datetime, timezone
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import require_mujoco
from .hollow import (
    CHANNEL_HEIGHT_MM,
    CHANNEL_LENGTH_MM,
    CONTACT_DAMPRATIO,
    CONTACT_TIMECONST_S,
    LAUNCH_SPEED_M_S,
    PROBE_RADIUS_MM,
    RESTING_Z_MM,
    TRANSIT_Z_MM,
    u_channel_spec,
)
from .scene import export_scene
from .units import mm_to_m

#: The probe's centre must get below this height, inside the cavity, to count as a passage.
CRITERION_Z_MM = CHANNEL_HEIGHT_MM / 2.0
#: Simulated duration and step, s.
DURATION_S = 0.8
TIMESTEP_S = 1.0e-3
#: A settled run must be slow and finite at the end.
TERMINAL_SPEED_TOL = 0.05
#: Solver warning counters must stay at zero.
WARNING_TOL = 0
#: The +X exit plane the whole probe must cross, mm. The probe centre must pass this.
EXIT_PLANE_X_MM = CHANNEL_LENGTH_MM / 2.0 + PROBE_RADIUS_MM
#: Allowed transient penetration of the probe into the floor, mm. Measured, not assumed.
MAX_CONTACT_DEPTH_MM = 1.0
#: Pre-launch settle time, s. Long enough for the initial contact to resolve; writes no state.
SETTLE_S = 0.05
#: Hard budget on a single trial's steps, so a mistyped duration cannot run unbounded.
MAX_TRIAL_STEPS = 200_000
#: A trial that begins already interpenetrating solid material is not a valid passage test:
#: that is what a convex hull over a hollow part produces, and it must never count as success.
MAX_INITIAL_PENETRATION_MM = 0.2


#: Every real warning counter, named from the installed enum. The sentinel ``mjNWARNING`` is
#: a count, not a warning, so it is excluded. Hand-written indices were previously
#: mislabelled and omitted BADQVEL/BADQACC/BADCTRL entirely.
WARNING_NAMES = (
    "mjWARN_INERTIA",
    "mjWARN_CONTACTFULL",
    "mjWARN_CNSTRFULL",
    "mjWARN_BADQPOS",
    "mjWARN_BADQVEL",
    "mjWARN_BADQACC",
    "mjWARN_BADCTRL",
)


def _warning_counters(mujoco, data) -> dict[str, int]:
    """MuJoCo's own warning counters, enumerated by name from the installed enum."""
    return {
        name.removeprefix("mjWARN_").lower(): int(data.warning[int(getattr(mujoco.mjtWarning, name))].number)
        for name in WARNING_NAMES
    }


@dataclass
class PassageResult:
    """One trial. ``valid`` is about numerics; ``passed`` is about the physical criterion."""

    valid: bool
    invalid_reasons: list[str]
    #: False when the scene itself is invalid: the probe starts inside solid material, which
    #: is a property of the collider representation, not of the trajectory. A scene-invalid
    #: trial can never be a PASS and its post-overlap motion is not predictive evidence.
    scene_valid: bool
    scene_invalid_reason: str
    passed: bool
    min_x_mm: float
    max_x_mm: float
    exit_x_mm: float
    crossed_exit: bool
    y_dev_mm: float
    z_dev_mm: float
    max_contact_depth_mm: float
    initial_penetration_mm: float
    n_contacts: int
    max_contact_count: int
    terminal_speed: float
    finite: bool
    warnings: dict[str, int]
    mass_kg: float
    wall_time_s: float
    #: Actual compiled solver step and phase boundaries, read from the model and the data.
    solver_dt_s: float
    settle_end_s: float
    trial_start_s: float
    trial_end_s: float
    trace: list[tuple[float, float, float, float, float]]

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "invalid_reasons": list(self.invalid_reasons),
            "scene_valid": self.scene_valid,
            "scene_invalid_reason": self.scene_invalid_reason,
            "passed": self.passed,
            "min_x_mm": self.min_x_mm,
            "max_x_mm": self.max_x_mm,
            "exit_plane_x_mm": self.exit_x_mm,
            "crossed_exit": self.crossed_exit,
            # None when the probe never reached the exit plane: there is no crossing to
            # measure, and a JSON null is honest where inf would be unparseable.
            "lateral_deviation_mm": _finite_or_none(self.y_dev_mm),
            "height_deviation_mm": _finite_or_none(self.z_dev_mm),
            "max_contact_depth_mm": self.max_contact_depth_mm,
            "initial_penetration_mm": self.initial_penetration_mm,
            "n_contacts": self.n_contacts,
            "max_contact_count": self.max_contact_count,
            "terminal_speed": self.terminal_speed,
            "finite": self.finite,
            "warnings": self.warnings,
            "mass_kg": self.mass_kg,
            "wall_time_s": self.wall_time_s,
            "solver_dt_s": self.solver_dt_s,
            "settle_end_s": self.settle_end_s,
            "trial_start_s": self.trial_start_s,
            "trial_end_s": self.trial_end_s,
            "trace_rows": len(self.trace),
        }


def _finite_or_none(value: float) -> float | None:
    return float(value) if math.isfinite(value) else None


def _simulate(xml: str, body_name: str, *, duration_s: float, timestep_s: float,
              base_dir: Path | None = None, launch_speed_m_s: float = 0.0,
              scene_path: Path | None = None,
              sample_every_s: float = 0.002) -> PassageResult:
    """Run one trial. Never writes ``qpos`` after the declared initial state."""
    mujoco = require_mujoco()
    if scene_path is not None:
        model = mujoco.MjModel.from_xml_path(str(scene_path))
    elif base_dir is not None:
        model = mujoco.MjModel.from_xml_path(str(base_dir / "scene.xml"))
    else:
        model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)

    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name)
    if body_id < 0:
        raise ValueError(f"no body {body_name!r} in the scene")

    # The compiled step is the only truth. Counting steps from the *requested* value while the
    # XML hard-codes another silently runs the wrong duration, so assert they agree and derive
    # every count and cadence from the compiled model.
    dt = float(model.opt.timestep)
    if not (math.isfinite(dt) and dt > 0.0):
        raise ValueError(f"compiled timestep is not positive and finite: {dt!r}")
    if abs(dt - timestep_s) > 1e-12 * max(dt, timestep_s):
        raise ValueError(
            f"requested timestep {timestep_s!r} s but the compiled model uses {dt!r} s; "
            f"the scene was not generated with this step")
    if not (math.isfinite(duration_s) and duration_s > 0.0):
        raise ValueError(f"duration_s must be finite and positive, got {duration_s!r}")
    settle_steps = int(round(SETTLE_S / dt))
    n_steps = int(round(duration_s / dt))
    if settle_steps + n_steps > MAX_TRIAL_STEPS:
        raise ValueError(
            f"settle and trial would take {settle_steps + n_steps} steps, "
            f"over the {MAX_TRIAL_STEPS} budget"
        )

    # Settle first, with zero velocity, so the probe is genuinely resting on the floor before
    # it is launched. Applying the velocity to a body that is still resolving its initial
    # contact makes it hop (measured: z rose 11 -> 13.6 mm), which is a launch artifact rather
    # than a transit. The settle phase writes no state; only the launch below does, once.
    # Initial penetration: how far the probe already overlaps solid material at t=0. A convex
    # hull over a hollow part swallows the cavity, so the probe starts inside it; that number
    # is the direct evidence that the hull is not the CAD.
    initial_penetration_mm = 0.0
    mujoco.mj_forward(model, data)
    for ci in range(data.ncon):
        initial_penetration_mm = max(initial_penetration_mm,
                                     max(0.0, -float(data.contact[ci].dist)) * 1e3)

    for _ in range(settle_steps):
        mujoco.mj_step(model, data)

    # A recorded initial velocity is a legitimate fixture input; it is applied once, here, and
    # never again. Everything after this comes from gravity and contact.
    settle_end_s = float(data.time)
    if launch_speed_m_s:
        data.qvel[0] = float(launch_speed_m_s)
        mujoco.mj_forward(model, data)
    trial_start_s = float(data.time)

    sample_every = max(1, int(round(sample_every_s / dt)))
    trace: list[tuple[float, float, float, float, float]] = []
    min_x = max_x = float(data.xipos[body_id][0])
    max_depth = 0.0
    # Deviation is sampled at the moment the probe crosses the exit plane, not at the end of
    # the run: after leaving the channel the probe is in free fall by design.
    exit_dev: tuple[float, float] | None = None
    exit_x_m = EXIT_PLANE_X_MM / 1e3
    # The crossing only counts if the probe was still inside the channel: a probe that left
    # sideways or upward has not traversed the passage.
    crossed_inside = False
    max_contacts = 0
    contact_steps = 0
    finite = True

    # Contact depth is measured from the actual contact list, not from a pose estimate: the
    # deepest negative distance along the contact normal is the true penetration.
    floor_top_m = None
    for g in range(model.ngeom):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g)
        if name == "u_floor":
            floor_top_m = float(model.geom_pos[g][2] + model.geom_size[g][2])
            break

    start = time.perf_counter()
    for step in range(n_steps + 1):
        pos = data.xipos[body_id]
        min_x = min(min_x, float(pos[0]))
        max_x = max(max_x, float(pos[0]))
        if exit_dev is None and float(pos[0]) >= exit_x_m:
            exit_dev = (abs(float(pos[1]) * 1e3),
                        abs(float(pos[2]) * 1e3 - RESTING_Z_MM))
            crossed_inside = exit_dev[0] <= PROBE_RADIUS_MM and exit_dev[1] <= PROBE_RADIUS_MM
        # Penetration is only meaningful while the probe is over the channel; outside its
        # span a free fall below the floor plane is expected, not a contact defect.
        over_channel = abs(float(pos[0]) * 1e3) <= CHANNEL_LENGTH_MM / 2.0 + PROBE_RADIUS_MM
        if data.ncon and over_channel:
            for ci in range(data.ncon):
                con = data.contact[ci]
                max_depth = max(max_depth, max(0.0, -float(con.dist)) * 1e3)
        max_contacts = max(max_contacts, int(data.ncon))
        if data.ncon:
            contact_steps += 1
        if step % sample_every == 0:
            trace.append((float(data.time), float(pos[0]) * 1e3, float(pos[1]) * 1e3,
                          float(pos[2]) * 1e3, float(data.ncon)))
        if not (np.all(np.isfinite(data.qpos)) and np.all(np.isfinite(data.qvel))
                and np.all(np.isfinite(data.xpos))):
            finite = False
            break
        if step < n_steps:
            mujoco.mj_step(model, data)
    wall = time.perf_counter() - start

    warnings = _warning_counters(mujoco, data)
    invalid: list[str] = []
    if not finite:
        invalid.append("non-finite state during the trial")
    for name, count in warnings.items():
        if count > WARNING_TOL:
            invalid.append(f"solver warning {name} raised {count} times")
    if not (model.body_mass[body_id] > 0.0):
        invalid.append(f"non-positive probe mass {float(model.body_mass[body_id])!r}")

    crossed = bool(max_x >= exit_x_m)
    y_dev, z_dev = exit_dev if exit_dev is not None else (float("inf"), float("inf"))
    scene_valid = initial_penetration_mm <= MAX_INITIAL_PENETRATION_MM
    scene_reason = "" if scene_valid else (
        f"probe starts {initial_penetration_mm:.3f} mm inside solid material at t=0: the "
        f"collider representation is invalid, so this trial is SCENE_INVALID")

    passed = bool(
        scene_valid
        and crossed
        and crossed_inside
        and max_depth <= MAX_CONTACT_DEPTH_MM
        and initial_penetration_mm <= MAX_INITIAL_PENETRATION_MM
        and finite
    )

    return PassageResult(
        valid=not invalid,
        invalid_reasons=invalid,
        scene_valid=scene_valid,
        scene_invalid_reason=scene_reason,
        passed=passed,
        min_x_mm=float(min_x * 1e3),
        max_x_mm=float(max_x * 1e3),
        exit_x_mm=EXIT_PLANE_X_MM,
        crossed_exit=crossed,
        y_dev_mm=float(y_dev),
        z_dev_mm=float(z_dev),
        max_contact_depth_mm=float(max_depth),
        initial_penetration_mm=float(initial_penetration_mm),
        n_contacts=contact_steps,
        max_contact_count=max_contacts,
        terminal_speed=float(abs(data.qvel[2])),
        finite=finite,
        warnings=warnings,
        mass_kg=float(model.body_mass[body_id]),
        wall_time_s=wall,
        solver_dt_s=dt,
        settle_end_s=settle_end_s,
        trial_start_s=trial_start_s,
        trial_end_s=float(data.time),
        trace=trace,
    )


def probe_start_mm(through_path: bool) -> tuple[float, float, float]:
    """The probe's initial centre, shared by the production scene and the mesh diagnostic."""
    from .hollow import _probe_start

    return _probe_start(through_path)


def default_channel_outdir(run_id: str) -> Path:
    """``out/fixtures/m2b_u_channel/physics/<run-id>/``, matching the M1 convention."""
    from ..workspace import workspace_root

    return workspace_root() / "out" / "fixtures" / "m2b_u_channel" / "physics" / run_id


def run_channel_evidence(outdir: Path | None = None, *, duration_s: float = DURATION_S,
                         timestep_s: float = TIMESTEP_S) -> dict:
    """Run the through-path positive and the concave-mesh negative, write all evidence.

    The positive trial launches the probe along +X through the open channel (not a vertical
    drop). The negative collides the same CAD as a mesh hull and is expected to be
    ``SCENE_INVALID``: the probe starts inside solid material.

    A fresh timestamped run directory is created unless one is supplied, so a second run can
    never overwrite the first run's traces or leave stale assets beside new ones.
    """
    from .hollow import concave_mesh_diagnostic_xml, write_channel_stl

    if outdir is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        outdir = default_channel_outdir(stamp)
    outdir = Path(outdir)
    if outdir.exists() and any(outdir.iterdir()):
        raise FileExistsError(
            f"refusing to write into non-empty {outdir}; use a fresh run directory")
    outdir.mkdir(parents=True, exist_ok=True)

    spec = u_channel_spec(through_path=True, timestep_s=timestep_s)
    export = export_scene(spec, outdir / "scene")
    xml = export.scene_xml.read_text(encoding="utf-8")

    positive = _simulate(xml, "probe", duration_s=duration_s, timestep_s=timestep_s,
                         base_dir=export.outdir, launch_speed_m_s=LAUNCH_SPEED_M_S)
    _write_trace(outdir / "trace_positive.csv", positive.trace)

    # Same probe, same launch, same contact settings; the only difference is the collider.
    diagnostic_dir = outdir / "mesh_diagnostic"
    diagnostic_dir.mkdir(parents=True, exist_ok=True)
    write_channel_stl(diagnostic_dir / "u_channel.stl")
    (diagnostic_dir / "scene_mesh_diagnostic.xml").write_text(
        concave_mesh_diagnostic_xml(through_path=True, timestep_s=timestep_s),
        encoding="utf-8")
    negative = _simulate_mesh_diagnostic(diagnostic_dir, duration_s=duration_s,
                                         timestep_s=timestep_s)
    _write_trace(outdir / "trace_mesh_diagnostic.csv", negative.trace)

    from .overlay import render_overlay

    overlay = render_overlay(spec.bodies[0], outdir / "collision_overlay.png",
                             transits=spec.bodies[0].fidelity.transits,
                             title="U-channel: CAD (translucent) vs colliders")

    status = _status(positive, negative)
    summary = {
        "scenario": "m2b_channel_passage",
        "run_id": outdir.name,
        "run_dir": str(outdir),
        "status": status,
        "criterion": {
            "exit_plane_x_mm": EXIT_PLANE_X_MM,
            "max_contact_depth_mm": MAX_CONTACT_DEPTH_MM,
            "launch_speed_m_s": LAUNCH_SPEED_M_S,
            "contact_timeconst_s": CONTACT_TIMECONST_S,
            "contact_dampratio": CONTACT_DAMPRATIO,
        },
        "positive": positive.to_dict(),
        "negative_mesh_diagnostic": negative.to_dict(),
        "scene_hash": export.scene_hash,
        "scene_xml": str(export.scene_xml),
        "mesh_diagnostic_xml": str(diagnostic_dir / "scene_mesh_diagnostic.xml"),
        "solver": {"requested_timestep_s": timestep_s,
                   "compiled_timestep_s": positive.solver_dt_s,
                   "duration_s": duration_s,
                   "integrator": "RK4", "cone": "elliptic", "solver": "Newton",
                   "iterations": 100},
        "versions": {"python": platform.python_version(),
                     "platform": platform.platform(),
                     "mujoco": _mujoco_version()},
        "artifacts": {
            "trace_positive": "trace_positive.csv",
            "trace_mesh_diagnostic": "trace_mesh_diagnostic.csv",
            "debug_overlay": overlay.name,
        },
    }
    (outdir / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (outdir / "report.md").write_text(_render(summary), encoding="utf-8")
    return summary


def _simulate_mesh_diagnostic(directory: Path, *, duration_s: float,
                              timestep_s: float) -> PassageResult:
    """Compile the test-only mesh diagnostic from its file, with the same launch input."""
    mujoco = require_mujoco()
    path = directory / "scene_mesh_diagnostic.xml"
    return _simulate(str(path), "probe", duration_s=duration_s, timestep_s=timestep_s,
                     scene_path=path, launch_speed_m_s=LAUNCH_SPEED_M_S)


def _mujoco_version() -> str:
    try:
        return require_mujoco().__version__
    except Exception:
        return "unavailable"


def _status(positive: PassageResult, negative: PassageResult) -> str:
    """Invalid numerics are never a physical verdict.

    A trial whose state went non-finite, whose solver raised warnings, or whose mass is
    invalid cannot be evidence either way, so it outranks the apparent plane crossing. A
    *positive* trial whose scene is invalid (initial interpenetration) is reported as
    ``ERROR``, not as a physical failure: the representation is wrong, not the dynamics. The
    per-trial ``scene_valid`` flag and ``scene_invalid_reason`` carry the distinction.
    """
    if not positive.valid or not negative.valid:
        return "INCONCLUSIVE"
    if not positive.scene_valid:
        # A positive trial that starts inside solid material cannot be a pass at all. The
        # status vocabulary stays at M1's four values; the cause is in scene_invalid_reason.
        return "ERROR"
    if positive.passed and not negative.passed:
        return "PASS"
    return "FAIL"


def _write_trace(path: Path, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        # Columns are mm and the count, matching what _simulate records.
        writer.writerow(["time_s", "probe_x_mm", "probe_y_mm", "probe_z_mm",
                         "contact_count"])
        for row in rows:
            writer.writerow([f"{v:.9g}" for v in row])


def _fmt(value, spec: str = ".2f") -> str:
    """Format a possibly-absent measurement without pretending it is a number."""
    return "n/a" if value is None else format(value, spec)


def _render(summary: dict) -> str:
    pos = summary["positive"]
    neg = summary["negative_mesh_diagnostic"]
    crit = summary["criterion"]
    return f"""# M2b hollow-channel evidence

Status: **{summary['status']}**

Through-path criterion: the probe starts outside the -X mouth with a recorded initial +X speed
of {crit['launch_speed_m_s']} m/s, and its **centre** must cross the exit plane at
x = {crit['exit_plane_x_mm']:.1f} mm while staying within one probe radius of the cavity axis.
Transient floor penetration must stay under {crit['max_contact_depth_mm']:.1f} mm.

| Run | max x (mm) | crossed exit | z dev (mm) | max depth (mm) | initial pen. (mm) | numeric valid | scene valid | passed |
|---|---|---|---|---|---|---|---|---|
| correct multi-box recipe | {_fmt(pos['max_x_mm'])} | {pos['crossed_exit']} | {_fmt(pos['height_deviation_mm'])} | {_fmt(pos['max_contact_depth_mm'], '.3f')} | {_fmt(pos['initial_penetration_mm'], '.3f')} | {pos['valid']} | {pos['scene_valid']} | {pos['passed']} |
| concave-mesh diagnostic | {_fmt(neg['max_x_mm'])} | {neg['crossed_exit']} | {_fmt(neg['height_deviation_mm'])} | {_fmt(neg['max_contact_depth_mm'], '.3f')} | {_fmt(neg['initial_penetration_mm'], '.3f')} | {neg['valid']} | {neg['scene_valid']} | {neg['passed']} |

Compiled solver step: `{summary['solver']['compiled_timestep_s']}` s (requested
`{summary['solver']['requested_timestep_s']}` s). Correct-recipe phases: settle ends at
{_fmt(pos['settle_end_s'], '.3f')} s, trial runs {_fmt(pos['trial_start_s'], '.3f')} to
{_fmt(pos['trial_end_s'], '.3f')} s.

**Two different failures, kept apart.** The concave-mesh trial is *numerically* valid — no
non-finite state, no solver warnings — but its **scene is invalid**: the probe starts
{_fmt(neg['initial_penetration_mm'], '.3f')} mm inside solid material, because the convex hull
of the mesh fills the cavity. That is the expected negative: the collider representation is
wrong. The probe's subsequent ejection is *not* predictive dynamics evidence, and this trial
is never counted as a physical traversal failure.

Solver warnings, correct recipe: `{pos['warnings']}`

The diagnostic scene collides the **original U-channel STL** as `type="mesh"`, which MuJoCo
replaces with its convex hull. `cad physics channel` *does* invoke it — it is the fixture's
expected-negative trial. What is diagnostic-only is the scene itself: it is generated by
`cadkit.physics.hollow_run` into the run directory, it is never a design of record, and the
**production** exporter (`export_scene`) refuses to emit a mesh collision geom at all.

Scene hash: `{summary['scene_hash']}`
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
