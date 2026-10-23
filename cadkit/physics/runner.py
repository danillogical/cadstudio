"""Generic headless M4a phase runner: reset, settle, actuate, release, hold.

The runner is deliberately independent of any product project. A scenario selects a
registered analytic fixture, declares the only positions that may be written (reset), then
advances the compiled MuJoCo model. After reset, motion comes only from actuator force,
spring/damping, contact and gravity: nothing here writes ``qpos`` or script-corrects an
outcome.

Budgets are preflighted from the **total rounded** phase plan before export or stepping. A
run gets its own directory, is never overwritten, and preserves partial evidence when it was
admitted but failed during execution.
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
import random
import time
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import PhysicsUnavailable, require_mujoco
from .evaluate import (
    Evaluation,
    evaluate,
    initial_bound_reasons,
    resolve_references,
)
from .mechanics_run import effective_timeconst
from .scenario import (
    AcceptanceSpec,
    PhaseSpec,
    ScenarioError,
    ScenarioSpec,
    acceptance_from_text,
    acceptance_text_matches,
    build_fixture,
    canonical_json,
    content_hash,
    load_acceptance,
    load_scenario,
    scenario_from_text,
    scenario_text_matches,
)
from .scene import SceneInvalid, export_scene
from .schema import safe_filename
from .state_archive import (
    DEFAULT_MAX_STATE_BYTES,
    REPLAY_TOLERANCES,
    state_bytes_estimate,
    state_layout,
    state_sha256,
    write_archive,
    write_state_meta,
)
from .telemetry import (
    PhaseTelemetry,
    TelemetryRecorder,
    state_hash,
    write_contacts_csv,
    write_state_archive,
    write_trace_csv,
)

MANIFEST_VERSION = "m4a-1"
SUMMARY_VERSION = "m4a-1"
OPTIONS_LOCK = "assembly_options.lock.toml"


# --------------------------------------------------------------------------- plan
@dataclass(frozen=True)
class PlannedPhase:
    phase: PhaseSpec
    steps: int
    start_step: int


@dataclass(frozen=True)
class RunPlan:
    dt_s: float
    sample_every: int
    phases: tuple[PlannedPhase, ...]
    total_steps: int
    total_time_s: float
    trace_rows: int
    state_rows: int = 0

    def to_dict(self) -> dict:
        return {
            "timestep_s": self.dt_s,
            "sample_every_steps": self.sample_every,
            "total_steps": self.total_steps,
            "total_time_s": self.total_time_s,
            "planned_trace_rows": self.trace_rows,
            "state_rows": self.state_rows,
            "phases": [
                {
                    "name": item.phase.name, "kind": item.phase.kind,
                    "requested_duration_s": item.phase.duration_s,
                    "actual_duration_s": item.steps * self.dt_s,
                    "steps": item.steps, "start_step": item.start_step,
                }
                for item in self.phases
            ],
        }


def preflight(scenario: ScenarioSpec, spec) -> RunPlan:
    """Resolve every phase to whole steps and enforce the total budgets.

    Nothing is exported, compiled or stepped before this returns. A timed phase that rounds
    to zero steps, or a total that exceeds any declared budget, is rejected explicitly.
    """
    spec.validate()
    dt = float(spec.timestep_s)
    if not (math.isfinite(dt) and 0.0 < dt <= 1.0e-2):
        raise ScenarioError(f"fixture timestep_s {dt!r} is outside (0, 0.01]")
    try:
        ratio = scenario.sampling_interval_s / dt
        if not math.isfinite(ratio):
            raise OverflowError
        sample_every = max(1, int(round(ratio)))
    except (OverflowError, ValueError) as exc:
        raise ScenarioError(
            f"sampling_interval_s {scenario.sampling_interval_s!r} is not representable "
            f"at timestep {dt!r} s") from exc
    planned: list[PlannedPhase] = [
        PlannedPhase(scenario.reset_phase, 0, 0),
    ]
    start = 0
    trace_rows = 1  # the initial/reset row
    for phase in scenario.timed_phases:
        assert phase.duration_s is not None
        try:
            ratio = phase.duration_s / dt
            if not math.isfinite(ratio):
                raise OverflowError
            steps = int(round(ratio))
        except (OverflowError, ValueError) as exc:
            raise ScenarioError(
                f"phase {phase.name!r}: duration {phase.duration_s!r} s is not representable "
                f"at timestep {dt!r} s") from exc
        if steps < 1:
            raise ScenarioError(
                f"phase {phase.name!r}: duration {phase.duration_s!r} s rounds to zero steps "
                f"at timestep {dt!r} s; increase the duration or refine the timestep")
        actual = steps * dt
        if not math.isfinite(actual) or actual <= 0.0:
            raise ScenarioError(
                f"phase {phase.name!r}: duration {phase.duration_s!r} s is not representable "
                f"at timestep {dt!r} s")
        planned.append(PlannedPhase(phase, steps, start))
        start += steps
        trace_rows += steps // sample_every + 1
    total_steps = start
    total_time = total_steps * dt
    budgets = scenario.budgets
    if total_steps > budgets.max_steps:
        raise ScenarioError(
            f"total rounded step count {total_steps} exceeds the declared budget "
            f"{budgets.max_steps}")
    if total_time > budgets.max_sim_time_s + 1e-12:
        raise ScenarioError(
            f"total simulated time {total_time!r} s exceeds the declared budget "
            f"{budgets.max_sim_time_s!r} s")
    if trace_rows > budgets.max_trace_rows:
        raise ScenarioError(
            f"planned trace rows {trace_rows} exceeds the declared budget "
            f"{budgets.max_trace_rows}")
    state_rows = total_steps + 1
    if budgets.max_state_rows is not None and state_rows > budgets.max_state_rows:
        raise ScenarioError(
            f"state archive needs {state_rows} rows, above the declared budget "
            f"{budgets.max_state_rows}")
    return RunPlan(dt, sample_every, tuple(planned), total_steps, total_time, trace_rows,
                   state_rows)


# --------------------------------------------------------------------------- helpers
def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mujoco_version_safe() -> str:
    try:
        return str(require_mujoco().__version__)
    except Exception:
        return "unavailable"


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json_safe(value):
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    return value


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(_json_safe(payload), indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def _source(source) -> dict:
    return {"kind": source.kind, "note": source.note, "date": source.date}


def _resolved_inputs(spec) -> dict:
    """Every physical input and its provenance, without CAD shape objects."""
    bodies = []
    for body in spec.bodies:
        parts = []
        for part in body.parts:
            parts.append({
                "part_id": part.part_id, "role": part.role,
                "density_g_cm3": part.density_g_cm3, "mass_kg": part.mass_kg,
                "source": _source(part.source),
                "colliders": [
                    {"collider_id": c.collider_id, "kind": c.kind,
                     "size_mm": list(c.size_mm), "pos_mm": list(c.pos_mm),
                     "rot_deg": list(c.rot_deg), "role": c.role,
                     "contype": c.contype, "conaffinity": c.conaffinity,
                     "friction": list(c.friction if c.friction is not None
                                      else spec.friction),
                     "priority": c.priority,
                     "source": _source(c.source)}
                    for c in part.colliders
                ],
            })
        joint = None
        if body.joint is not None:
            j = body.joint
            joint = {
                "joint_id": j.joint_id, "kind": j.kind, "axis": list(j.axis),
                "anchor_mm": list(j.anchor_mm), "limits": list(j.limits)
                if j.limits is not None else None,
                "damping": j.damping, "frictionloss": j.frictionloss,
                "armature": j.armature, "stop_timeconst_s": j.stop_timeconst_s,
                "stop_dampratio": j.stop_dampratio,
                "spring": ({"stiffness": j.spring.stiffness,
                            "reference": j.spring.reference,
                            "source": _source(j.spring.source)}
                           if j.spring is not None else None),
                "source": _source(j.source),
            }
        bodies.append({
            "body_id": body.body_id, "parent": body.parent,
            "frame": {"pos_mm": list(body.frame.pos_mm),
                      "rot_deg": list(body.frame.rot_deg)},
            "fixed_to_world": body.fixed_to_world, "fixture": body.fixture,
            "source": _source(body.source), "parts": parts, "joint": joint,
        })
    return {
        "assembly": spec.name,
        "gravity_m_s2": list(spec.gravity_m_s2),
        "timestep_s": spec.timestep_s, "integrator": spec.integrator,
        "cone": spec.cone, "solver": spec.solver, "iterations": spec.iterations,
        "friction": list(spec.friction),
        "contact_timeconst_s": spec.contact_timeconst_s,
        "contact_dampratio": spec.contact_dampratio,
        "source": _source(spec.source),
        "bodies": bodies,
        "actuators": [
            {"actuator_id": a.actuator_id, "joint_id": a.joint_id, "kind": a.kind,
             "max_effort": a.max_effort, "gear": a.gear,
             "source": _source(a.source)}
            for a in spec.actuators
        ],
    }


def _select_document_text(document, explicit: str | None, matcher) -> str:
    for candidate in (explicit, document.source_text):
        if candidate and matcher(document, candidate):
            return candidate
    return canonical_json(document.to_dict()) + "\n"


def _claim_run_dir(scenario: ScenarioSpec, outdir: Path | None) -> tuple[Path, str]:
    scenario_hash = scenario.hash()[:8]
    if outdir is None:
        from ..params import REPO_ROOT

        parent = REPO_ROOT / "out" / "fixtures" / "m4a" / scenario.scenario_id / "physics"
        run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{scenario_hash}"
        run_dir = parent / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir, run_id
    run_dir = Path(outdir)
    if run_dir.exists():
        raise FileExistsError(f"refusing to write into existing path {run_dir}")
    try:
        run_dir.parent.mkdir(parents=True, exist_ok=True)
        run_dir.mkdir(exist_ok=False)
    except FileExistsError as exc:
        raise FileExistsError(f"refusing to overwrite existing run directory {run_dir}") from exc
    return run_dir, run_dir.name


def _apply_reset(mujoco, model, data, phase: PhaseSpec) -> None:
    """Reset every coordinate, then write only the declared reset positions."""
    mujoco.mj_resetData(model, data)
    for joint_name, value in phase.initial:
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
        if joint_id < 0:
            raise ScenarioError(f"reset references unknown joint {joint_name!r}")
        jtype = int(model.jnt_type[joint_id])
        if jtype not in (int(mujoco.mjtJoint.mjJNT_HINGE),
                         int(mujoco.mjtJoint.mjJNT_SLIDE)):
            raise ScenarioError(
                f"reset joint {joint_name!r} is not a hinge or slide; free-body positions "
                f"must come from the declared scene, not a reset write")
        if bool(model.jnt_limited[joint_id]):
            lo, hi = (float(v) for v in model.jnt_range[joint_id])
            if not lo - 1e-12 <= value <= hi + 1e-12:
                raise ScenarioError(
                    f"reset joint {joint_name!r} coordinate {value!r} is outside its "
                    f"declared range [{lo!r}, {hi!r}]")
        qadr = int(model.jnt_qposadr[joint_id])
        data.qpos[qadr] = value
    mujoco.mj_forward(model, data)


def _verify_compiled(mujoco, model, spec, export) -> tuple[dict, list[dict]]:
    """Declared-vs-compiled equality. A mismatch is a build error, not a tolerance."""
    facts: dict = {
        "timestep_s": float(model.opt.timestep),
        "integrator": int(model.opt.integrator),
        "gravity_m_s2": [float(v) for v in model.opt.gravity],
        "joints": {}, "actuators": {}, "bodies": {},
    }
    if abs(facts["timestep_s"] - float(spec.timestep_s)) > 1e-12:
        raise ScenarioError(
            f"compiled timestep {facts['timestep_s']!r} != declared {spec.timestep_s!r}")
    if not np.allclose(np.asarray(model.opt.gravity), np.asarray(spec.gravity_m_s2),
                       rtol=0.0, atol=1e-12):
        raise ScenarioError("compiled gravity differs from the declared gravity")
    integrators = {"Euler": "mjINT_EULER", "RK4": "mjINT_RK4",
                   "implicit": "mjINT_IMPLICIT", "implicitfast": "mjINT_IMPLICITFAST"}
    cones = {"pyramidal": "mjCONE_PYRAMIDAL", "elliptic": "mjCONE_ELLIPTIC"}
    solvers = {"PGS": "mjSOL_PGS", "CG": "mjSOL_CG", "Newton": "mjSOL_NEWTON"}
    if int(model.opt.integrator) != int(getattr(mujoco.mjtIntegrator,
                                                integrators[spec.integrator])):
        raise ScenarioError("compiled integrator differs from the declared integrator")
    if int(model.opt.cone) != int(getattr(mujoco.mjtCone, cones[spec.cone])):
        raise ScenarioError("compiled cone differs from the declared cone")
    if int(model.opt.solver) != int(getattr(mujoco.mjtSolver, solvers[spec.solver])):
        raise ScenarioError("compiled solver differs from the declared solver")
    if int(model.opt.iterations) != spec.iterations:
        raise ScenarioError("compiled solver iterations differ from declared")
    # Per-collider check, mapped by geom name; visual mesh geoms (contype=0) are not colliders.
    collider_geoms: dict[str, dict] = {}
    for body in spec.bodies:
        for part in body.parts:
            for c in part.colliders:
                gname = safe_filename(c.collider_id)
                gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, gname)
                if gid < 0:
                    raise ScenarioError(f"compiled model has no collider geom {gname!r}")
                declared = np.asarray(c.friction if c.friction is not None
                                      else spec.friction, dtype=float)
                if not np.allclose(model.geom_friction[gid], declared, rtol=0.0, atol=1e-12):
                    raise ScenarioError(
                        f"compiled friction for collider {c.collider_id!r} differs from "
                        f"the declared friction {declared.tolist()!r}")
                if int(model.geom_priority[gid]) != c.priority:
                    raise ScenarioError(
                        f"compiled priority for collider {c.collider_id!r} is "
                        f"{int(model.geom_priority[gid])!r}, declared {c.priority!r}")
                collider_geoms[gname] = {
                    "friction": [float(v) for v in model.geom_friction[gid]],
                    "priority": int(model.geom_priority[gid]),
                }
    facts["collider_geoms"] = collider_geoms
    facts["solver_settings"] = {
        "integrator": int(model.opt.integrator), "cone": int(model.opt.cone),
        "solver": int(model.opt.solver), "iterations": int(model.opt.iterations),
        "friction": [float(v) for v in spec.friction],
    }
    facts["runtime_identity"] = {
        "mujoco": str(require_mujoco().__version__),
        "mj_version": str(getattr(mujoco, "mj_version", lambda: "unknown")()),
        "numpy": np.__version__, "python": platform.python_version(),
        "platform": platform.platform(),
        "enableflags": int(model.opt.enableflags),
        "disableflags": int(model.opt.disableflags),
        "timestep_s": float(model.opt.timestep),
        "integrator": int(model.opt.integrator), "cone": int(model.opt.cone),
        "solver": int(model.opt.solver), "iterations": int(model.opt.iterations),
        "tolerance": float(model.opt.tolerance),
        "ls_tolerance": float(model.opt.ls_tolerance),
        "ccd_tolerance": float(model.opt.ccd_tolerance),
        "impratio": float(model.opt.impratio),
        "gravity_m_s2": [float(v) for v in model.opt.gravity],
        "wind_m_s": [float(v) for v in model.opt.wind],
        "density_kg_m3": float(model.opt.density),
        "viscosity_pa_s": float(model.opt.viscosity),
        "o_margin_m": float(model.opt.o_margin),
    }
    facts["force_sampling"] = {
        "method": "mj_step, then observational mj_forward on a private MjData at the "
                  "post-step state",
        "force_time_s": "state_time_s",
        "force_stage": "post_step_forward",
        "initial_force_stage": "initial_forward",
        "state_rewrites": False,
        "integrator_preserved": True,
        "note": ("derived poses/COM/velocities/energy/contacts/forces are evaluated at the "
                 "recorded state time; RK4 intermediate stages are not sampled and no "
                 "qpos/qvel/act is written"),
    }

    reports = {report.body_id: report for report in export.bodies}
    for body in spec.bodies:
        body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body.body_id)
        if body_id < 0:
            raise ScenarioError(f"compiled model has no body {body.body_id!r}")
        mass = float(model.body_mass[body_id])
        expected = float(reports[body.body_id].mass_kg)
        if abs(mass - expected) > 1e-12 * max(1.0, abs(expected)):
            raise ScenarioError(
                f"compiled mass {mass!r} for body {body.body_id!r} != exported {expected!r}")
        facts["bodies"][body.body_id] = {
            "mass_kg": mass,
            "com_m": [float(v) for v in model.body_ipos[body_id]],
        }
        if body.joint is not None:
            joint = body.joint
            joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint.joint_id)
            if joint_id < 0:
                raise ScenarioError(f"compiled model has no joint {joint.joint_id!r}")
            dof = int(model.jnt_dofadr[joint_id])
            qadr = int(model.jnt_qposadr[joint_id])
            expected_type = (int(mujoco.mjtJoint.mjJNT_HINGE)
                             if joint.kind == "hinge"
                             else int(mujoco.mjtJoint.mjJNT_SLIDE))
            if int(model.jnt_type[joint_id]) != expected_type:
                raise ScenarioError(f"compiled joint {joint.joint_id!r} has the wrong type")
            if joint.spring is not None:
                if abs(float(model.jnt_stiffness[joint_id]) - joint.spring.stiffness) > 1e-12:
                    raise ScenarioError(
                        f"compiled spring stiffness for {joint.joint_id!r} differs")
                if abs(float(model.qpos_spring[qadr]) - joint.spring.reference) > 1e-12:
                    raise ScenarioError(
                        f"compiled spring reference for {joint.joint_id!r} differs")
            for name, declared in (("damping", joint.damping),
                                   ("frictionloss", joint.frictionloss),
                                   ("armature", joint.armature)):
                compiled_value = float(getattr(model, f"dof_{name}")[dof])
                if abs(compiled_value - declared) > 1e-12:
                    raise ScenarioError(
                        f"compiled joint {joint.joint_id!r} {name} differs from declared")
            if joint.limits is not None:
                if not bool(model.jnt_limited[joint_id]):
                    raise ScenarioError(
                        f"compiled joint {joint.joint_id!r} lost its declared limits")
                if not np.allclose(np.asarray(model.jnt_range[joint_id]),
                                   np.asarray(joint.limits), rtol=0.0, atol=1e-12):
                    raise ScenarioError(
                        f"compiled joint {joint.joint_id!r} limits differ from declared")
            facts["joints"][joint.joint_id] = {
                "type": int(model.jnt_type[joint_id]),
                "qposadr": qadr, "dofadr": dof,
                "range": [float(v) for v in model.jnt_range[joint_id]],
                "limited": bool(model.jnt_limited[joint_id]),
                "stiffness": float(model.jnt_stiffness[joint_id]),
                "qpos_spring": float(model.qpos_spring[qadr]),
                "damping": float(model.dof_damping[dof]),
                "frictionloss": float(model.dof_frictionloss[dof]),
                "armature": float(model.dof_armature[dof]),
                "solreflimit": [float(v) for v in model.jnt_solref[joint_id]],
            }

    for actuator in spec.actuators:
        aid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR,
                                actuator.actuator_id)
        if aid < 0:
            raise ScenarioError(f"compiled model has no actuator {actuator.actuator_id!r}")
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, actuator.joint_id)
        if int(model.actuator_trnid[aid][0]) != joint_id:
            raise ScenarioError(
                f"compiled actuator {actuator.actuator_id!r} drives the wrong joint")
        gear = float(model.actuator_gear[aid][0])
        if abs(gear - actuator.gear) > 1e-12:
            raise ScenarioError(
                f"compiled gear for {actuator.actuator_id!r} is {gear!r}, declared "
                f"{actuator.gear!r}")
        limit = actuator.max_effort / abs(actuator.gear)
        ctrlrange = [float(v) for v in model.actuator_ctrlrange[aid]]
        forcerange = [float(v) for v in model.actuator_forcerange[aid]]
        if not (bool(model.actuator_ctrllimited[aid])
                and bool(model.actuator_forcelimited[aid])):
            raise ScenarioError(
                f"actuator {actuator.actuator_id!r} is not bounded by both ctrlrange and "
                f"forcerange")
        if not (np.allclose(ctrlrange, (-limit, limit), rtol=0.0, atol=1e-12)
                and np.allclose(forcerange, (-limit, limit), rtol=0.0, atol=1e-12)):
            raise ScenarioError(
                f"actuator {actuator.actuator_id!r} compiled limits {ctrlrange}/"
                f"{forcerange} do not encode max_effort {actuator.max_effort!r} at gear "
                f"{actuator.gear!r}")
        facts["actuators"][actuator.actuator_id] = {
            "joint": actuator.joint_id, "gear": gear,
            "ctrlrange": ctrlrange, "forcerange": forcerange,
            "max_effort": actuator.max_effort,
        }

    compliance: list[dict] = []
    contact_tc = float(spec.contact_timeconst_s)
    if model.ngeom:
        contact_solref = [float(v) for v in model.geom_solref[0]]
        if not np.allclose(contact_solref,
                           (contact_tc, float(spec.contact_dampratio)),
                           rtol=0.0, atol=1e-12):
            raise ScenarioError(
                f"compiled contact solref {contact_solref!r} != declared "
                f"{[contact_tc, spec.contact_dampratio]!r}")
    effective = effective_timeconst(mujoco, model, contact_tc)
    if effective > contact_tc * (1.0 + 1e-12):
        compliance.append({
            "stage": "compliance",
            "reason": (f"declared contact time constant {contact_tc!r} s is below the "
                       f"effective {effective!r} s at timestep {facts['timestep_s']!r} s"),
            "time_s": 0.0,
        })
    facts["contact_timeconst"] = {
        "declared_s": contact_tc, "effective_s": effective,
        "refsafe_floor_s": 2.0 * facts["timestep_s"],
    }
    for body in spec.bodies:
        joint = body.joint
        if joint is None or joint.stop_timeconst_s is None:
            continue
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint.joint_id)
        if joint_id < 0:
            raise ScenarioError(f"compiled model has no joint {joint.joint_id!r}")
        compiled_stop = [float(v) for v in model.jnt_solref[joint_id]]
        if not np.allclose(compiled_stop,
                           (joint.stop_timeconst_s, joint.stop_dampratio),
                           rtol=0.0, atol=1e-12):
            raise ScenarioError(
                f"compiled stop solref for {joint.joint_id!r} {compiled_stop!r} != "
                f"declared {[joint.stop_timeconst_s, joint.stop_dampratio]!r}")
        effective_stop = effective_timeconst(mujoco, model, joint.stop_timeconst_s)
        facts["joints"][joint.joint_id]["stop_effective_timeconst_s"] = effective_stop
        if effective_stop > joint.stop_timeconst_s * (1.0 + 1e-12):
            compliance.append({
                "stage": "compliance",
                "reason": (f"joint stop {joint.joint_id!r} declared {joint.stop_timeconst_s!r}"
                           f" s but effective {effective_stop!r} s at timestep "
                           f"{facts['timestep_s']!r} s"),
                "time_s": 0.0,
            })
    return facts, compliance


SUPPORTED_INTEGRATORS = ("Euler", "RK4")


def _require_supported_integrator(spec) -> None:
    """The M4a observational sampler is validated for Euler and RK4 only.

    Other MuJoCo integrators are rejected before any run directory is created, so they are
    never exported or stepped with semantics that were never tested.
    """
    if spec.integrator not in SUPPORTED_INTEGRATORS:
        raise ScenarioError(
            f"integrator {spec.integrator!r} is not supported by the M4a observational "
            f"sampler; supported integrators are {list(SUPPORTED_INTEGRATORS)}")


def _effort_units(spec, actuator) -> str:
    body = next(b for b in spec.bodies if b.joint is not None
                and b.joint.joint_id == actuator.joint_id)
    return "N m" if body.joint.kind == "hinge" else "N"


def _phase_command(spec, phase: PhaseSpec) -> tuple[dict[str, float], dict[str, float],
                                                    PhaseTelemetry]:
    actuators = {a.actuator_id: a for a in spec.actuators}
    effort_units = {a.actuator_id: _effort_units(spec, a) for a in spec.actuators}
    ctrl = {name: 0.0 for name in actuators}
    bounded_effort: dict[str, float] = {}
    progress = PhaseTelemetry(name=phase.name, kind=phase.kind,
                              requested_duration_s=phase.duration_s)
    if phase.kind == "actuate":
        actuator = actuators[phase.actuator]
        requested = float(phase.effort)
        # A positive requested generalized effort always drives the joint positively,
        # whatever the gear sign. ctrl is the motor-side quantity, hence effort/gear.
        ctrl[actuator.actuator_id] = requested / actuator.gear
        bounded = max(-actuator.max_effort, min(actuator.max_effort, requested))
        bounded_effort[actuator.actuator_id] = bounded
        progress.actuator = actuator.actuator_id
        progress.requested_effort = requested
        progress.effort_units = effort_units[actuator.actuator_id]
        progress.ctrl_requested = ctrl[actuator.actuator_id]
    else:
        # Settle/release/hold are explicit zero input on every actuator.
        progress.requested_effort = 0.0
        progress.effort_units = ""
        progress.ctrl_requested = 0.0
    return ctrl, bounded_effort, progress


def _execute(mujoco, model, data, spec, scenario: ScenarioSpec, plan: RunPlan,
             recorder: TelemetryRecorder, acceptance: AcceptanceSpec):
    # Reset is recorded as a phase boundary but contributes no timed steps.
    reset = plan.phases[0].phase
    reset_progress = PhaseTelemetry(name=reset.name, kind="reset",
                                    requested_duration_s=None,
                                    actual_duration_s=0.0, requested_steps=0,
                                    actual_steps=0, start_time_s=float(data.time),
                                    end_time_s=float(data.time), complete=True)
    recorder.telemetry.phases.append(reset_progress)
    initial_ok = recorder.record_initial(reset.name)
    recorder.telemetry.boundaries[reset.name] = recorder.telemetry.boundaries["initial"]
    initial_reasons = initial_bound_reasons(acceptance, recorder.telemetry)
    if not initial_ok or initial_reasons:
        # An already invalid reset state must not become a valid trial through dynamics:
        # take zero steps. Numerical reasons are already in ``telemetry.invalid`` from the
        # initial accumulation; declared bound reasons are emitted once by evaluation.
        recorder.telemetry.initial_rejected = True
    for planned in (() if recorder.telemetry.initial_rejected else plan.phases[1:]):
        ctrl, bounded, progress = _phase_command(spec, planned.phase)
        progress.requested_steps = planned.steps
        recorder.begin_phase(progress, ctrl, bounded)
        recorder.step(planned.steps)
        recorder.end_phase()
        if recorder.telemetry.stopped:
            break
    started = {p.name for p in recorder.telemetry.phases}
    for planned in plan.phases[1:]:
        if planned.phase.name in started:
            continue
        recorder.telemetry.phases.append(PhaseTelemetry(
            name=planned.phase.name, kind=planned.phase.kind,
            requested_duration_s=planned.phase.duration_s,
            actual_duration_s=0.0, requested_steps=planned.steps,
            actual_steps=0, start_time_s=float(data.time),
            end_time_s=float(data.time), complete=False))
    recorder.finish()
    recorder.freeze_state()
    return recorder.telemetry


# --------------------------------------------------------------------------- report
def _fmt(value, digits: int = 6) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}g}"
    return str(value)


def render_report(summary: dict) -> str:
    lines = [
        f"# M4a scenario: {summary['scenario']['id']}",
        "",
        f"Status: **{summary['status']}**  ",
        f"Fixture: `{summary['fixture']}`  ",
        f"Seed: `{summary['seed']}`  ",
        f"Timestep: `{summary['solver']['timestep_s']}` s  ",
        f"Scene hash: `{summary['scene']['scene_hash']}`  ",
        f"Acceptance hash: `{summary['acceptance']['hash']}`  ",
        "",
        "## Phases",
        "",
        "| phase | kind | requested s | actual s | requested steps | actual steps | complete |",
        "|---|---|---|---|---|---|---|",
    ]
    for phase in summary["phases"]:
        lines.append(
            f"| {phase['name']} | {phase['kind']} | "
            f"{_fmt(phase['requested_duration_s'])} | {_fmt(phase['actual_duration_s'])} | "
            f"{phase['requested_steps']} | {phase['actual_steps']} | {phase['complete']} |")
    lines.extend([
        "",
        "## Validity",
        "",
        f"Numerically valid: `{summary['validity']['ok']}`",
        "",
    ])
    if summary["validity"]["reasons"]:
        lines.append("| stage | time s | reason |")
        lines.append("|---|---|---|")
        for reason in summary["validity"]["reasons"]:
            lines.append(f"| {reason['stage']} | {_fmt(reason['time_s'])} | "
                         f"{reason['reason']} |")
        lines.append("")
    lines.extend([
        "## Checks",
        "",
        "| check | kind | status | value | units | detail |",
        "|---|---|---|---|---|---|",
    ])
    for check in summary["checks"]:
        lines.append(f"| {check['name']} | {check['kind']} | {check['status']} | "
                     f"{_fmt(check['value'])} | {check['units']} | {check['detail']} |")
    lines.extend([
        "",
        "## Per-step maxima",
        "",
        "| metric | value |",
        "|---|---|",
    ])
    for key in ("peak_speed_m_s", "peak_angular_speed_rad_s", "peak_energy_j",
                "peak_penetration_m", "peak_contact_force_n"):
        lines.append(f"| {key} | {_fmt(summary['metrics'][key])} |")
    for name, value in sorted(summary["metrics"]["peak_effort"].items()):
        lines.append(f"| peak_effort:{name} | {_fmt(value)} |")
    lines.append("")
    lines.append("## States")
    lines.append("")
    lines.append("| state | time s | hash |")
    lines.append("|---|---|---|")
    for name in ("initial", "post_settle", "terminal"):
        snap = summary["states"][name]
        lines.append(f"| {name} | {_fmt(snap['time_s'])} | `{snap['hash']}` |")
    lines.append("")
    if summary.get("events"):
        lines.append("## Named events")
        lines.append("")
        lines.append("| event | kind | status | code | distinct bodies | crossings | diagnostics |")
        lines.append("|---|---|---|---|---|---|---|")
        for event in summary["events"]:
            crossings = ", ".join(
                f"{row['body_id']}@{_fmt(row['time_s'])}s" for row in event["crossings"])
            diagnostics = ", ".join(
                f"{row['code']}({row['body_id']})" for row in event["diagnostics"])
            lines.append(
                f"| {event['name']} | {event['kind']} | {event['status']} | "
                f"{event['verdict_code']} | {event['distinct_bodies_crossed']} | "
                f"{crossings or 'none'} | {diagnostics or 'none'} |")
        for event in summary["events"]:
            dwell = event.get("dwell")
            if dwell:
                lines.append(
                    f"- `{event['name']}` dwell: {dwell['duration_s']} s, "
                    f"protrusion {dwell['protrusion_min_m']}..{dwell['protrusion_max_m']} m, "
                    f"support fraction {dwell['support_fraction_min']}")
        lines.append("")
    if summary["contacts"]:
        lines.append("## Named contacts")
        lines.append("")
        lines.append("| body a | geom a | body b | geom b | peak normal N | peak penetration m | samples |")
        lines.append("|---|---|---|---|---|---|---|")
        for row in summary["contacts"]:
            lines.append(
                f"| {row['body_a']} | {row['geom_a']} | {row['body_b']} | "
                f"{row['geom_b']} | {_fmt(row['max_normal_force_n'])} | "
                f"{_fmt(row['max_penetration_m'])} | {row['samples']} |")
        lines.append("")
    lines.extend([
        "## Provenance",
        "",
        f"Python {summary['versions']['python']}, MuJoCo {summary['versions']['mujoco']}, "
        f"NumPy {summary['versions']['numpy']}, platform `{summary['versions']['platform']}`.",
        "",
        "Analytic-fixture parameters are declared assumptions, not calibrated PETG "
        "measurements. A PASS is a statement about this declared scene only; S0 and physical "
        "M7 remain unverified.",
        "",
        "## Artifacts",
        "",
    ])
    for name, rel in summary["artifacts"].items():
        lines.append(f"- {name}: `{rel}`")
    lines.append("")
    return "\n".join(lines)


def _artifact_manifest(run_dir: Path) -> dict:
    artifacts = {}
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path.name == "manifest.json":
            continue
        rel = path.relative_to(run_dir).as_posix()
        artifacts[rel] = {"sha256": _sha256(path), "bytes": path.stat().st_size}
    return artifacts


# --------------------------------------------------------------------------- run
def run_scenario(scenario: ScenarioSpec, acceptance: AcceptanceSpec,
                 outdir: Path | None = None, *, scenario_text: str | None = None,
                 acceptance_text: str | None = None) -> dict:
    """Run one admitted registered-fixture scenario and return the strict-JSON summary."""
    spec = build_fixture(scenario.fixture, scenario.timestep_s)
    return _run_with_spec(spec, scenario, acceptance, outdir, scenario_text=scenario_text,
                          acceptance_text=acceptance_text, fixture_label=scenario.fixture)


def _validate_options_document(options) -> None:
    """Strict, finite options document at the runner boundary.

    Mirrors the CLI's scalar/flat-array rule and additionally rejects non-finite floats:
    TOML admits ``inf``/``nan``, but a run summary is strict JSON, so writing them as ``null``
    would produce a PASS record that its own lock cannot reproduce.
    """
    if not isinstance(options, dict):
        raise ScenarioError("assembly options must be a TOML table")

    def check_value(key: str, value) -> None:
        if isinstance(value, bool) or isinstance(value, str):
            return
        if isinstance(value, int):
            return
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ScenarioError(
                    f"assembly option {key!r} must be finite, got {value!r}")
            return
        raise ScenarioError(
            f"assembly option {key!r} must be a scalar or an array of scalars")

    for key, value in options.items():
        if isinstance(value, list):
            for index, item in enumerate(value):
                check_value(f"{key}[{index}]", item)
        else:
            check_value(key, value)


def run_assembly(spec, scenario: ScenarioSpec, acceptance: AcceptanceSpec,
                 outdir: Path | None = None, *, scenario_text: str | None = None,
                 acceptance_text: str | None = None,
                 fixture_label: str | None = None,
                 options_text: str | None = None,
                 require_scenario_timestep: bool = False) -> dict:
    """Public typed execution API: run an ``AssemblySpec`` without the fixture registry.

    M5 project adapters can build their own assembly and reuse the same generic runner,
    evidence format, budgets and evaluation. JSON scenarios still select only allowlisted
    registry fixtures; this entry point never performs a dynamic import.

    ``options_text`` is the raw TOML of the explicit assembly options the spec was built
    with. When given it is copied into the run as ``assembly_options.lock.toml`` and its
    SHA256 joins the run identity; ``None`` leaves the evidence exactly as before.
    ``require_scenario_timestep`` rejects a scenario whose ``timestep_s`` is absent or
    differs from the spec's, for project runs where the spec supplies the timestep.
    """
    spec.validate()
    if require_scenario_timestep:
        declared = scenario.timestep_s
        if declared is None:
            raise ScenarioError(
                f"scenario {scenario.scenario_id!r} has no timestep_s; project runs require "
                f"it to equal the assembly timestep {spec.timestep_s!r}")
        if abs(float(declared) - float(spec.timestep_s)) > 1e-15:
            raise ScenarioError(
                f"scenario timestep_s {declared!r} differs from the assembly timestep "
                f"{spec.timestep_s!r}")
    options = None
    if options_text is not None:
        try:
            options = tomllib.loads(options_text)
        except tomllib.TOMLDecodeError as exc:
            raise ScenarioError(f"assembly options are not valid TOML: {exc}") from exc
        _validate_options_document(options)
    return _run_with_spec(spec, scenario, acceptance, outdir, scenario_text=scenario_text,
                          acceptance_text=acceptance_text,
                          fixture_label=fixture_label or spec.name,
                          options_text=options_text, options=options)


def _run_with_spec(spec, scenario: ScenarioSpec, acceptance: AcceptanceSpec,
                   outdir: Path | None, *, scenario_text: str | None,
                   acceptance_text: str | None, fixture_label: str,
                   options_text: str | None = None, options: dict | None = None) -> dict:
    resolve_references(scenario, acceptance, spec)
    plan = preflight(scenario, spec)
    _require_supported_integrator(spec)
    # Copy a source document only when it still parses to the document being evaluated;
    # otherwise emit a canonical typed document that its own loader accepts. A mutated typed
    # spec keeps stale ``source_text``, and copying that would attest criteria never run.
    scenario_text = _select_document_text(scenario, scenario_text, scenario_text_matches)
    acceptance_text = _select_document_text(acceptance, acceptance_text,
                                            acceptance_text_matches)
    # The typed path must satisfy the same strict loader that replay applies to the lock.
    # This runs before any run directory is claimed, so a rejected typed criterion cannot
    # leave PASS evidence whose own replay refuses to load.
    try:
        scenario_from_text(scenario_text)
        acceptance_from_text(acceptance_text)
    except ScenarioError as exc:
        raise ScenarioError(
            f"typed scenario/acceptance is not admissible by the strict loader: {exc}"
        ) from exc
    run_dir, run_id = _claim_run_dir(scenario, outdir)
    started = time.perf_counter()
    stage = "export"
    recorder = None
    try:
        (run_dir / "scenario.json").write_bytes(scenario_text.encode("utf-8"))
        (run_dir / "acceptance.lock.json").write_bytes(acceptance_text.encode("utf-8"))
        if options_text is not None:
            (run_dir / OPTIONS_LOCK).write_bytes(options_text.encode("utf-8"))
        scene_export = export_scene(spec, run_dir)
        stage = "compile"
        mujoco = require_mujoco()
        model = mujoco.MjModel.from_xml_path(str(scene_export.scene_xml))
        compiled, compliance = _verify_compiled(mujoco, model, spec, scene_export)
        # Energy is a telemetry flag, not a physical setting: it makes MuJoCo populate
        # ``data.energy`` without changing integration or constraints.
        model.opt.enableflags |= int(mujoco.mjtEnableBit.mjENBL_ENERGY)
        compiled["energy_reporting_enabled"] = True
        layout = state_layout(mujoco, model)
        state_cap = (scenario.budgets.max_state_bytes
                     if scenario.budgets.max_state_bytes is not None
                     else DEFAULT_MAX_STATE_BYTES)
        # Payload estimate for every archived array: integration state plus the separately
        # archived legacy, index, transition, name and checkpoint arrays. This is an
        # uncompressed payload bound, not a peak Python list/stack/np.stack memory bound.
        per_row_floats = (int(model.nq) + int(model.nv) + int(model.na) + int(model.nv)
                          + int(model.nu) + int(model.nv) + 3 + 7 * int(model.nmocap)
                          + int(model.nu) + int(model.nv) + 6 * int(model.nbody)
                          + 7 * int(model.nmocap))
        estimate = (state_bytes_estimate(layout, plan.state_rows,
                                         extra_per_row=per_row_floats)
                    + 8 * 3 * int(layout["size"]) + 4096)
        if estimate > state_cap:
            raise ScenarioError(
                f"state archive payload would need about {estimate} bytes for "
                f"{plan.state_rows} rows, above the {state_cap} budget")
        compiled["runtime_identity"]["enableflags"] = int(model.opt.enableflags)
        compiled["runtime_identity"]["state_mask"] = int(layout["mask"])
        compiled["runtime_identity"]["state_size"] = int(layout["size"])
        compiled["state_archive"] = {
            "mask": layout["mask"], "size": layout["size"], "rows": plan.state_rows,
            "payload_estimate_bytes": estimate, "payload_budget_bytes": state_cap,
            "estimate_kind": "uncompressed payload of archived arrays, not peak Python memory",
        }
        data = mujoco.MjData(model)
        stage = "reset"
        random.seed(scenario.seed)
        np.random.seed(scenario.seed)
        _apply_reset(mujoco, model, data, scenario.reset_phase)
        stage = "run"
        recorder = TelemetryRecorder(
            mujoco, model, data, sample_every=plan.sample_every,
            effort_units={a.actuator_id: _effort_units(spec, a) for a in spec.actuators},
            max_contact_rows=scenario.budgets.max_trace_rows * 16,
            max_state_rows=(scenario.budgets.max_state_rows
                            if scenario.budgets.max_state_rows is not None
                            else plan.state_rows),
            max_state_bytes=state_cap,
            events=acceptance.events,
            checks=acceptance.checks,
            gravity_m_s2=tuple(spec.gravity_m_s2),
        )
        telemetry = _execute(mujoco, model, data, spec, scenario, plan, recorder,
                             acceptance)
        evaluation: Evaluation = evaluate(
            scenario, acceptance, telemetry, compliance_reasons=compliance)
        stage = "artifacts"
        summary = _build_summary(
            scenario, acceptance, spec, plan, compiled, telemetry, evaluation, run_dir,
            run_id, started, scenario_text, acceptance_text, fixture_label,
            options_text=options_text, options=options,
        )
        _write_artifacts(run_dir, telemetry, summary)
        return summary
    except (ScenarioError, SceneInvalid, PhysicsUnavailable, OSError, ValueError) as exc:
        return _write_failure(run_dir, run_id, scenario, acceptance, stage, exc,
                              scenario_text, acceptance_text, recorder=recorder)
    except Exception as exc:  # defensive: never let a crash look like PASS
        return _write_failure(run_dir, run_id, scenario, acceptance, stage, exc,
                              scenario_text, acceptance_text, recorder=recorder)


def _build_summary(scenario, acceptance, spec, plan, compiled, telemetry, evaluation,
                   run_dir, run_id, started, scenario_text, acceptance_text,
                   fixture_label, *, options_text: str | None = None,
                   options: dict | None = None) -> dict:
    metrics = evaluation.metrics
    phases = [p.to_dict() for p in telemetry.phases]
    for planned in plan.phases:
        match = next((p for p in phases if p["name"] == planned.phase.name), None)
        if match is not None:
            match["requested_duration_s"] = planned.phase.duration_s
            match["requested_steps"] = planned.steps
    boundaries = telemetry.boundaries
    initial = boundaries.get("initial")
    settle = next((p for p in telemetry.phases if p.kind == "settle"), None)
    post_settle = boundaries.get(settle.name) if settle is not None else initial
    # The last *recorded* boundary, not the last declared phase: after a numerical stop the
    # remaining phases are reported as unstarted and must not become the terminal state.
    terminal = next(reversed(boundaries.values())) if boundaries else initial
    if post_settle is None:
        post_settle = initial
    if terminal is None:
        terminal = initial
    states = {
        "initial": initial.to_dict() if initial else
        {"time_s": 0.0, "qpos": {}, "qvel": {}, "hash": ""},
        "post_settle": post_settle.to_dict() if post_settle else
        {"time_s": 0.0, "qpos": {}, "qvel": {}, "hash": ""},
        "terminal": terminal.to_dict() if terminal else
        {"time_s": 0.0, "qpos": {}, "qvel": {}, "hash": ""},
    }
    rows = int(telemetry.state["time"].shape[0]) if telemetry.state else 0
    settle_phase = next((p for p in telemetry.phases if p.kind == "settle"), None)
    post_settle_row = (telemetry.boundary_rows.get(settle_phase.name, 0)
                       if settle_phase is not None else 0)
    checkpoint_rows = {
        "initial_row": 0,
        "post_settle_row": int(min(max(post_settle_row, 0), max(rows - 1, 0))),
        "terminal_row": int(max(rows - 1, 0)),
        "rows": rows,
    }
    artifacts = {
        "scenario": "scenario.json",
        "acceptance_lock": "acceptance.lock.json",
        "scene": "scene.xml",
        "scene_report": "report.json",
        "manifest": "manifest.json",
        "summary": "summary.json",
        "report": "report.md",
        "trace": "trace.csv",
        "contacts": "contacts.csv",
        "states": "states.npz",
        "state_meta": "state_meta.json",
        "checkpoints": "checkpoints.npz",
    }
    options_sha = (hashlib.sha256(options_text.encode("utf-8")).hexdigest()
                   if options_text is not None else None)
    if options_sha:
        artifacts["assembly_options_lock"] = OPTIONS_LOCK
    summary = {
        "schema_version": SUMMARY_VERSION,
        "status": evaluation.status,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "created_utc": _iso_utc(),
        "scenario": {"id": scenario.scenario_id, "hash": scenario.hash(),
                     "sha256": hashlib.sha256(scenario_text.encode("utf-8")).hexdigest()},
        "acceptance": {"id": acceptance.acceptance_id, "hash": acceptance.hash(),
                       "sha256": hashlib.sha256(
                           acceptance_text.encode("utf-8")).hexdigest()},
        "fixture": fixture_label,
        "assembly": spec.name,
        "seed": scenario.seed,
        "timestep_s": spec.timestep_s,
        "versions": {
            "python": platform.python_version(), "platform": platform.platform(),
            "mujoco": str(require_mujoco().__version__), "numpy": np.__version__,
        },
        "solver": compiled,
        "plan": plan.to_dict(),
        "phases": phases,
        "validity": evaluation.validity,
        "checks": [c.to_dict() for c in evaluation.checks],
        "metrics": metrics,
        "contacts": telemetry.contacts(),
        "events": [result.to_dict()
                   for result in getattr(telemetry, "event_results", {}).values()],
        "states": states,
        "control_names": [a.actuator_id for a in spec.actuators],
        "state_archive": {
            "state_format": "m4b-1",
            **{k: v for k, v in (compiled.get("state_archive") or {}).items()},
            "checkpoints": checkpoint_rows,
        },
        "replay_tolerances": REPLAY_TOLERANCES,
        "telemetry": {
            "trace_rows": len(telemetry.trace_rows),
            "state_rows": int(telemetry.state["time"].shape[0]),
            "contact_rows": len(telemetry.contact_rows),
            "contact_pairs": len(telemetry.contact_pairs),
            "initial_rejected": telemetry.initial_rejected,
            "stopped": telemetry.stopped,
            "warnings": telemetry.warnings,
        },
        "scene": {
            "scene_hash": _scene_hash_from_report(run_dir),
            "xml": "scene.xml",
            "xml_sha256": _sha256(run_dir / "scene.xml"),
            "assets": _assets(run_dir),
        },
        "identity": content_hash({
            "scene_hash": _scene_hash_from_report(run_dir),
            "scenario_hash": scenario.hash(),
            "acceptance_hash": acceptance.hash(),
            "seed": scenario.seed,
            "timestep_s": spec.timestep_s,
            "mujoco": str(require_mujoco().__version__),
            "platform": platform.platform(),
            **({"assembly_options_sha256": options_sha} if options_sha else {}),
        }),
        "physical_inputs": _resolved_inputs(spec),
        "artifacts": artifacts,
        "runtime_wall_s": time.perf_counter() - started,
        "detail": "",
    }
    if options_sha:
        summary["assembly_options"] = options or {}
        summary["assembly_options_sha256"] = options_sha
    return summary


def _scene_hash_from_report(run_dir: Path) -> str:
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    return str(payload["scene_hash"])


def _assets(run_dir: Path) -> dict[str, str]:
    assets = {}
    root = run_dir / "assets"
    if root.is_dir():
        for path in sorted(root.rglob("*")):
            if path.is_file():
                assets[path.relative_to(run_dir).as_posix()] = _sha256(path)
    return assets


def _write_artifacts(run_dir: Path, telemetry, summary: dict) -> None:
    write_trace_csv(run_dir / "trace.csv", telemetry.trace_header, telemetry.trace_rows)
    write_contacts_csv(run_dir / "contacts.csv", telemetry.contact_header,
                       telemetry.contact_rows)
    write_state_archive(run_dir / "states.npz", telemetry.state)
    rows = int(telemetry.state["time"].shape[0]) if telemetry.state else 0
    checkpoints = summary["state_archive"]["checkpoints"]
    integration = telemetry.state.get("integration_state")
    if integration is not None and rows:
        write_archive(run_dir / "checkpoints.npz", {
            "initial": np.array(integration[checkpoints["initial_row"]]),
            "initial_row": np.asarray(checkpoints["initial_row"], dtype=np.int64),
            "post_settle": np.array(integration[checkpoints["post_settle_row"]]),
            "post_settle_row": np.asarray(checkpoints["post_settle_row"], dtype=np.int64),
            "terminal": np.array(integration[checkpoints["terminal_row"]]),
            "terminal_row": np.asarray(checkpoints["terminal_row"], dtype=np.int64),
        })
        meta = dict(checkpoints)
        meta["hashes"] = {
            "initial": state_sha256(integration[checkpoints["initial_row"]]),
            "post_settle": state_sha256(integration[checkpoints["post_settle_row"]]),
            "terminal": state_sha256(integration[checkpoints["terminal_row"]]),
        }
    else:
        meta = dict(checkpoints)
    write_state_meta(run_dir / "state_meta.json", layout=telemetry.layout,
                     summary=summary, checkpoints=meta,
                     phase_names=[str(v) for v in telemetry.state.get(
                         "phase_names", [])],
                     control_names=[str(v) for v in telemetry.state.get(
                         "actuator_names", [])])
    (run_dir / "summary.json").write_text(
        json.dumps(_json_safe(summary), indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (run_dir / "report.md").write_text(render_report(_json_safe(summary)), encoding="utf-8")
    manifest = {
        "schema_version": MANIFEST_VERSION,
        "created_utc": summary["created_utc"],
        "run_id": summary["run_id"],
        "run_dir": summary["run_dir"],
        "identity": summary["identity"],
        "scenario": summary["scenario"],
        "acceptance": summary["acceptance"],
        "fixture": summary["fixture"],
        "seed": summary["seed"],
        "versions": summary["versions"],
        "solver": summary["solver"],
        "plan": summary["plan"],
        "scene": summary["scene"],
        "physical_inputs": summary["physical_inputs"],
        "states": summary["states"],
        "events": summary.get("events", []),
        "status": summary["status"],
        "artifacts": _artifact_manifest(run_dir),
    }
    if "assembly_options_sha256" in summary:
        manifest["assembly_options"] = summary["assembly_options"]
        manifest["assembly_options_sha256"] = summary["assembly_options_sha256"]
    _write_json(run_dir / "manifest.json", manifest)


def _write_failure(run_dir: Path, run_id: str, scenario, acceptance, stage: str,
                   exc: Exception, scenario_text: str, acceptance_text: str,
                   *, recorder=None) -> dict:
    detail = f"{type(exc).__name__}: {exc}"
    summary = {
        "schema_version": SUMMARY_VERSION,
        "status": "ERROR",
        "run_id": run_id,
        "run_dir": str(run_dir),
        "created_utc": _iso_utc(),
        "scenario": {"id": scenario.scenario_id, "hash": scenario.hash(),
                     "sha256": hashlib.sha256(scenario_text.encode("utf-8")).hexdigest()},
        "acceptance": {"id": acceptance.acceptance_id, "hash": acceptance.hash(),
                       "sha256": hashlib.sha256(
                           acceptance_text.encode("utf-8")).hexdigest()},
        "fixture": scenario.fixture,
        "seed": scenario.seed,
        "stage": stage,
        "detail": detail,
        "versions": {"python": platform.python_version(),
                     "platform": platform.platform(), "numpy": np.__version__,
                     "mujoco": _mujoco_version_safe()},
        "solver": {},
        "plan": {},
        "phases": [],
        "validity": {"ok": False, "reasons": [
            {"stage": stage, "reason": detail, "time_s": None}]},
        "checks": [],
        "metrics": {},
        "contacts": [],
        "events": [],
        "states": {"initial": {"time_s": 0.0, "qpos": {}, "qvel": {}, "hash": ""},
                   "post_settle": {"time_s": 0.0, "qpos": {}, "qvel": {}, "hash": ""},
                   "terminal": {"time_s": 0.0, "qpos": {}, "qvel": {}, "hash": ""}},
        "telemetry": {},
        "scene": {},
        "physical_inputs": {},
        "artifacts": {"summary": "summary.json", "report": "report.md",
                      "failure": "failure.json"},
    }
    try:
        if recorder is not None:
            try:
                recorder.finish()
                recorder.freeze_state()
            except Exception:
                pass
            telemetry = recorder.telemetry
            if telemetry.trace_rows:
                write_trace_csv(run_dir / "trace.csv", telemetry.trace_header,
                                telemetry.trace_rows)
                summary["artifacts"]["trace"] = "trace.csv"
            if telemetry.contact_rows:
                write_contacts_csv(run_dir / "contacts.csv", telemetry.contact_header,
                                   telemetry.contact_rows)
                summary["artifacts"]["contacts"] = "contacts.csv"
            if telemetry.state:
                write_state_archive(run_dir / "states.npz", telemetry.state)
                summary["artifacts"]["states"] = "states.npz"
            summary["telemetry"] = {
                "trace_rows": len(telemetry.trace_rows),
                "state_rows": int(telemetry.state.get("time", np.zeros(0)).shape[0]),
                "contact_rows": len(telemetry.contact_rows),
                "initial_rejected": telemetry.initial_rejected,
                "stopped": telemetry.stopped,
                "warnings": telemetry.warnings,
            }
            summary["phases"] = [p.to_dict() for p in telemetry.phases]
            summary["events"] = [result.to_dict()
                                 for result in getattr(telemetry, "event_results",
                                                       {}).values()]
            initial = telemetry.boundaries.get("initial")
            terminal = (next(reversed(telemetry.boundaries.values()))
                        if telemetry.boundaries else initial)
            if initial is not None:
                summary["states"]["initial"] = initial.to_dict()
                summary["states"]["terminal"] = terminal.to_dict()
        summary["artifacts"]["manifest"] = "manifest.json"
        _write_json(run_dir / "failure.json", summary)
        _write_json(run_dir / "summary.json", summary)
        (run_dir / "report.md").write_text(
            f"# M4a scenario: {scenario.scenario_id}\n\nStatus: **ERROR**  \n"
            f"Stage: `{stage}`  \nDetail: {detail}\n", encoding="utf-8")
        manifest = {
            "schema_version": MANIFEST_VERSION, "status": "ERROR",
            "run_id": run_id, "run_dir": str(run_dir),
            "scenario": summary["scenario"], "acceptance": summary["acceptance"],
            "fixture": scenario.fixture, "seed": scenario.seed,
            "versions": summary["versions"], "stage": stage, "detail": detail,
            "artifacts": _artifact_manifest(run_dir),
        }
        _write_json(run_dir / "manifest.json", manifest)
    except OSError:
        pass
    return summary


def run_scenario_files(scenario_path: str | Path, acceptance_path: str | Path,
                       outdir: Path | None = None) -> dict:
    """Load strict JSON files, then run. Loader errors are ERROR and create no run."""
    scenario_path = Path(scenario_path)
    acceptance_path = Path(acceptance_path)
    scenario = load_scenario(scenario_path)
    acceptance = load_acceptance(acceptance_path)
    return run_scenario(scenario, acceptance, outdir,
                        scenario_text=scenario.source_text,
                        acceptance_text=acceptance.source_text)
