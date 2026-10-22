"""M4b deterministic replay of a saved M4a run directory.

Replay recompiles the **saved** scene and assets in memory, restores the saved native
integration state, applies the recorded transition inputs and actually calls ``mj_step``.
It never regenerates CAD, never sets terminal positions and never rewrites source evidence.
The result is compared with the source run under pinned same-runtime tolerances.

All run-directory input is untrusted: files are read through bounded regular-file helpers,
JSON is strict, archives are inspected before decompression, and scene/asset references are
confined to the saved run.
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import PhysicsUnavailable, require_mujoco
from .evidence import (
    EvidenceError,
    bounded_regular_bytes,
    raw_sha256,
    require,
    verify_manifest_relationships,
)
from .evaluate import evaluate
from .mechanics_run import effective_timeconst
from .scenario import (
    ScenarioError,
    _parse_json_text,
    acceptance_from_text,
    content_hash,
    scenario_from_text,
)
from .scene import compute_scene_hash
from .state_archive import (
    MAX_ARCHIVE_BYTES,
    MAX_ARCHIVE_ROWS,
    MAX_REPLAY_WALL_S,
    REPLAY_TOLERANCES,
    ArchiveError,
    get_native_state,
    load_state_meta_bytes,
    read_state_archive_bytes,
    required_members,
    set_native_state,
    state_layout,
    state_sha256,
    validate_layout,
    write_archive,
)
from .telemetry import PhaseTelemetry, TelemetryRecorder

REPLAY_FORMAT = "m4b-1"
MAX_REPLAY_STEPS = MAX_ARCHIVE_ROWS
_CHECKPOINT_MEMBERS = {
    "initial", "initial_row", "post_settle", "post_settle_row", "terminal", "terminal_row",
}
_STATE_MEMBERS = {
    "time", "qpos", "qvel", "act", "ctrl", "qacc_warmstart", "qfrc_applied",
    "mocap_pos", "mocap_quat", "phase_code", "phase_index", "step_index",
    "integration_state", "integration_mask", "integration_size",
    "transition_ctrl", "transition_qfrc_applied", "transition_xfrc_applied",
    "transition_mocap_pos", "transition_mocap_quat",
    "phase_names", "joint_names", "body_names", "actuator_names", "timestep_s",
}


class ReplayError(ValueError):
    """The source run cannot be verified or the replay cannot proceed."""


@dataclass
class VerifiedRun:
    run_dir: Path
    manifest: dict
    summary: dict
    report: dict
    scenario: object
    acceptance: object
    scenario_text: str
    acceptance_text: str
    scene_xml: bytes
    assets: dict[str, bytes]
    state: dict[str, np.ndarray]
    checkpoints: dict[str, np.ndarray]
    state_meta: dict
    source_hashes: dict[str, str] = field(default_factory=dict)


def _load_json(root: Path, rel: str) -> tuple[dict, str]:
    """One bounded read, parsed strictly; the same text is used for hashing and parsing."""
    raw = bounded_regular_bytes(root, rel, max_bytes=MAX_ARCHIVE_BYTES)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceError(f"{rel!r} is not valid UTF-8: {exc}") from exc
    try:
        return _parse_json_text(text, rel), text
    except ScenarioError as exc:
        raise EvidenceError(str(exc)) from exc


def _parse_json_bytes(raw: bytes, rel: str) -> dict:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceError(f"{rel!r} is not valid UTF-8: {exc}") from exc
    try:
        return _parse_json_text(text, rel)
    except ScenarioError as exc:
        raise EvidenceError(str(exc)) from exc


def _read_all_evidence(run_dir: Path, *, max_bytes: int) -> dict[str, bytes]:
    """Read every evidence file once into immutable bytes; nothing is reopened later."""
    required = ("manifest.json", "summary.json", "scenario.json", "acceptance.lock.json",
                "scene.xml", "states.npz", "report.json", "state_meta.json",
                "checkpoints.npz", "trace.csv", "contacts.csv")
    raw_files = {rel: bounded_regular_bytes(run_dir, rel, max_bytes=max_bytes)
                 for rel in required}
    manifest = _parse_json_bytes(raw_files["manifest.json"], "manifest.json")
    summary = _parse_json_bytes(raw_files["summary.json"], "summary.json")
    extra = set(manifest.get("artifacts", {})) | set(summary.get("scene", {}).get("assets", {}))
    for rel in sorted(extra - set(raw_files)):
        raw_files[rel] = bounded_regular_bytes(run_dir, rel, max_bytes=max_bytes)
    return raw_files


def _verify_scene(raw_files: dict[str, bytes], summary: dict,
                  report: dict) -> tuple[bytes, dict]:
    xml = raw_files["scene.xml"]
    require(raw_sha256(xml) == summary["scene"]["xml_sha256"],
            "scene.xml sha256 does not match the summary")
    identity = report.get("scene_identity")
    require(isinstance(identity, dict), "report.json has no scene_identity payload")
    assets = summary["scene"]["assets"]
    require(isinstance(assets, dict) and assets, "summary has no asset hashes")
    asset_bytes: dict[str, bytes] = {}
    for rel, digest in assets.items():
        raw = raw_files.get(rel)
        require(raw is not None, f"asset {rel!r} was not read")
        require(raw_sha256(raw) == digest, f"asset {rel!r} sha256 does not match the summary")
        asset_bytes[rel] = raw
    # Bind the semantic identity to the bytes that will actually be compiled, not to the
    # report's copy of itself.
    recomputed = {
        "xml": xml.decode("utf-8"),
        "assets": {rel: raw_sha256(raw) for rel, raw in asset_bytes.items()},
        "assembly": identity.get("assembly"),
        "bodies": identity.get("bodies"),
    }
    require(compute_scene_hash(recomputed) == summary["scene"]["scene_hash"],
            "recomputed semantic scene hash from saved bytes does not match the summary")
    require(identity.get("assets") == assets,
            "report scene identity assets differ from the summary asset set")
    require(identity.get("xml") == recomputed["xml"],
            "report scene identity XML differs from the saved scene.xml")
    return xml, asset_bytes


def _verify_runtime_header(summary: dict, manifest: dict) -> dict:
    identity = manifest.get("solver", {}).get("runtime_identity")
    require(isinstance(identity, dict), "manifest has no runtime identity")
    require(identity.get("mujoco") == str(require_mujoco().__version__),
            "MuJoCo version differs from the recorded runtime")
    require(identity.get("python") == platform.python_version(),
            "Python version differs from the recorded runtime")
    require(identity.get("platform") == platform.platform(),
            "platform differs from the recorded runtime")
    require(identity.get("numpy") == np.__version__,
            "NumPy version differs from the recorded runtime")
    return identity


def load_verified_run(run_dir: Path, *, max_rows: int = MAX_ARCHIVE_ROWS,
                      max_bytes: int = MAX_ARCHIVE_BYTES) -> VerifiedRun:
    run_dir = Path(run_dir)
    if run_dir.is_symlink():
        raise ReplayError(f"run directory {run_dir} is a symlink; refusing")
    if not run_dir.is_dir():
        raise ReplayError(f"run directory {run_dir} does not exist")
    try:
        raw_files = _read_all_evidence(run_dir, max_bytes=max_bytes)
        manifest = _parse_json_bytes(raw_files["manifest.json"], "manifest.json")
        summary = _parse_json_bytes(raw_files["summary.json"], "summary.json")
        report = _parse_json_bytes(raw_files["report.json"], "report.json")
        scenario_text = raw_files["scenario.json"].decode("utf-8")
        acceptance_text = raw_files["acceptance.lock.json"].decode("utf-8")
        verify_manifest_relationships(run_dir, manifest, summary, report,
                                      raw_files=raw_files, max_bytes=max_bytes)
        require(summary.get("status") != "ERROR",
                "source run status is ERROR and is not replayable")

        require(raw_sha256(scenario_text.encode("utf-8")) == summary["scenario"]["sha256"],
                "scenario.json raw sha256 does not match the summary")
        require(raw_sha256(acceptance_text.encode("utf-8")) == summary["acceptance"]["sha256"],
                "acceptance.lock.json raw sha256 does not match the summary")
        scenario = scenario_from_text(scenario_text)
        acceptance = acceptance_from_text(acceptance_text)
        require(scenario.hash() == summary["scenario"]["hash"],
                "scenario semantic hash does not match the summary")
        require(acceptance.hash() == summary["acceptance"]["hash"],
                "acceptance semantic hash does not match the summary")

        xml, assets = _verify_scene(raw_files, summary, report)
        runtime_identity = _verify_runtime_header(summary, manifest)
        # The summary's runtime identity must agree with the manifest's; a forged summary
        # alone is rejected even though the summary file itself is not hashed.
        require(summary["solver"]["runtime_identity"] == manifest["solver"]["runtime_identity"],
                "summary and manifest runtime identities differ")
        require(summary.get("events", []) == manifest.get("events", []),
                "summary and manifest event evidence differ")
        recomputed_identity = content_hash({
            "scene_hash": summary["scene"]["scene_hash"],
            "scenario_hash": summary["scenario"]["hash"],
            "acceptance_hash": summary["acceptance"]["hash"],
            "seed": summary["seed"],
            "timestep_s": summary["timestep_s"],
            "mujoco": str(require_mujoco().__version__),
            "platform": platform.platform(),
        })
        require(recomputed_identity == summary.get("identity") == manifest.get("identity"),
                "run identity hash does not recompute from the summary")

        state_meta = load_state_meta_bytes(raw_files["state_meta.json"])
        allow_nonfinite = summary.get("status") != "PASS"
        state = read_state_archive_bytes(raw_files["states.npz"],
                                         expected_members=required_members(
                                             state_meta["layout"]),
                                         max_bytes=max_bytes, max_rows=max_rows,
                                         allow_nonfinite=allow_nonfinite)
        if not allow_nonfinite:
            require(np.all(np.isfinite(state["integration_state"])),
                    "PASS run archive contains non-finite state values")
        rows = int(state["time"].shape[0])
        require(rows <= MAX_REPLAY_STEPS,
                f"archive has {rows} rows, above the {MAX_REPLAY_STEPS} replay step budget")
        require(rows == int(summary["telemetry"]["state_rows"]),
                "states.npz row count differs from the summary")
        require(rows >= 1, "states.npz has no rows")
        require(rows <= int(scenario.budgets.max_steps) + 1,
                "states.npz row count exceeds the scenario step budget")
        planned = int(summary["plan"]["state_rows"])
        stopped = bool(summary["telemetry"].get("stopped")) or bool(
            summary["telemetry"].get("initial_rejected"))
        require(rows == planned or (stopped and rows <= planned),
                f"states.npz covers {rows} of {planned} planned rows without a recorded stop")
        actual_steps = sum(int(phase.get("actual_steps", 0))
                           for phase in summary["phases"])
        require(actual_steps == rows - 1,
                "recorded phase step counts do not sum to the archive rows")
        for phase in summary["phases"]:
            if phase.get("complete"):
                require(int(phase.get("actual_steps", -1))
                        == int(phase.get("requested_steps", -2)),
                        f"complete phase {phase.get('name')!r} step count differs")
        if not stopped:
            require(all(phase.get("complete") for phase in summary["phases"]),
                    "unstopped run has incomplete phases")
        require(int(state["integration_mask"]) == int(runtime_identity["state_mask"]),
                "recorded state mask differs from the runtime identity")
        require(int(state["integration_size"]) == int(runtime_identity["state_size"]),
                "recorded state size differs from the runtime identity")
        require(int(state["integration_state"].shape[1]) == int(state["integration_size"]),
                "integration_state width differs from the recorded state size")
        step_index = state["step_index"]
        require(np.array_equal(step_index, np.arange(rows, dtype=step_index.dtype)),
                "step_index is not a zero-based row counter")
        phase_names = [str(v) for v in state["phase_names"]]
        phase_index = state["phase_index"]
        require(np.all(phase_index >= 0) and np.all(phase_index < len(phase_names)),
                "phase_index is out of range for phase_names")
        require(phase_index[0] == 0, "row 0 must be the reset phase (index 0)")
        # Exact per-phase counts and end times against the locked rounded plan.
        counts = np.bincount(phase_index, minlength=len(phase_names))
        require(int(counts[0]) == 1, "the reset phase must own exactly row 0")
        plan_phases = summary["plan"]["phases"]
        planned_names = [str(item["name"]) for item in plan_phases]
        require(phase_names[:len(planned_names)] == planned_names
                if len(phase_names) >= len(planned_names) else
                phase_names == planned_names[:len(phase_names)],
                "archive phase names do not match the locked plan order")
        stop_phase = int(np.max(phase_index)) if stopped else None
        for index, planned in enumerate(plan_phases):
            if index == 0:
                continue  # the reset phase owns exactly the initial row, no steps
            actual = int(counts[index]) if index < len(counts) else 0
            if stopped and index < stop_phase:
                require(actual == int(planned["steps"]),
                        f"phase {planned['name']!r} has {actual} steps, plan says "
                        f"{planned['steps']} (only the stopping phase may be truncated)")
            elif stopped and index == stop_phase:
                require(actual <= int(planned["steps"]),
                        f"phase {planned['name']!r} has {actual} steps above the plan")
            elif stopped and index > stop_phase:
                require(actual == 0,
                        f"phase {planned['name']!r} has {actual} steps after the stop")
            else:
                require(actual == int(planned["steps"]),
                        f"phase {planned['name']!r} has {actual} steps, plan says "
                        f"{planned['steps']}")
            if index > 0 and actual:
                rows_in_phase = np.where(phase_index == index)[0]
                recorded = summary["phases"][index]
                require(abs(float(state["time"][rows_in_phase[-1]])
                            - float(recorded["end_time_s"])) <= 1e-9,
                        f"phase {planned['name']!r} end time differs from the plan")
        recorded_checkpoints = summary.get("state_archive", {}).get("checkpoints", {})
        require(int(recorded_checkpoints.get("rows", -1)) == rows,
                "summary checkpoint row count differs from the archive")
        require(int(recorded_checkpoints.get("terminal_row", -1)) == rows - 1,
                "summary terminal checkpoint row differs from the archive")
        require(int(recorded_checkpoints.get("initial_row", -1)) == 0,
                "summary initial checkpoint row must be 0")

        require(int(state["transition_ctrl"].shape[0]) == rows,
                "transition_ctrl rows differ from state rows")
        require(np.array_equal(state["phase_code"], phase_index + 1),
                "phase_code is not phase_index + 1")
        require(phase_names == [str(v) for v in state_meta.get("phase_names", [])],
                "archive phase_names differ from state metadata")
        require([str(v) for v in state["actuator_names"]]
                == [str(v) for v in state_meta.get("control_names", [])],
                "archive actuator_names differ from state metadata control_names")
        components = {c["name"]: c for c in state_meta["layout"]["components"]}
        ctrl_size = int(components.get("mjSTATE_CTRL", {}).get("size", 0))
        qfrc_size = int(components.get("mjSTATE_QFRC_APPLIED", {}).get("size", 0))
        require(state["transition_ctrl"].shape == (rows, ctrl_size),
                f"transition_ctrl shape {state['transition_ctrl'].shape} != {(rows, ctrl_size)}")
        require(state["transition_qfrc_applied"].shape == (rows, qfrc_size),
                f"transition_qfrc_applied shape {state['transition_qfrc_applied'].shape} != "
                f"{(rows, qfrc_size)}")
        xfrc_size = int(components.get("mjSTATE_XFRC_APPLIED", {}).get("size", 0))
        if xfrc_size:
            require("transition_xfrc_applied" in state
                    and state["transition_xfrc_applied"].shape == (rows, xfrc_size // 6, 6),
                    "transition_xfrc_applied shape does not match the native component")
        mocap_pos_size = int(components.get("mjSTATE_MOCAP_POS", {}).get("size", 0))
        if mocap_pos_size:
            require("transition_mocap_pos" in state
                    and state["transition_mocap_pos"].shape == (rows, mocap_pos_size // 3, 3),
                    "transition_mocap_pos shape does not match the native component")
        mocap_quat_size = int(components.get("mjSTATE_MOCAP_QUAT", {}).get("size", 0))
        if mocap_quat_size:
            require("transition_mocap_quat" in state
                    and state["transition_mocap_quat"].shape == (rows, mocap_quat_size // 4, 4),
                    "transition_mocap_quat shape does not match the native component")
        for member, component, legacy in (
                ("integration_state", "mjSTATE_TIME", "time"),
                ("integration_state", "mjSTATE_QPOS", "qpos"),
                ("integration_state", "mjSTATE_QVEL", "qvel")):
            comp = components.get(component)
            if comp is None or not comp.get("size"):
                continue
            off = int(comp["offset"])
            size = int(comp["size"])
            component_values = state["integration_state"][:, off:off + size]
            legacy_values = np.asarray(state[legacy])
            if size == 1 and legacy_values.ndim == 1:
                legacy_values = legacy_values.reshape(rows, 1)
            require(legacy_values.shape == component_values.shape,
                    f"archive member {legacy!r} shape {legacy_values.shape} != native "
                    f"component shape {component_values.shape}")
            require(np.allclose(component_values, legacy_values, rtol=0.0, atol=0.0,
                                equal_nan=allow_nonfinite),
                    f"archive member {legacy!r} does not match native component {component}")
        for member, component in (("transition_ctrl", "mjSTATE_CTRL"),
                                  ("transition_qfrc_applied", "mjSTATE_QFRC_APPLIED")):
            comp = components.get(component)
            if comp is None or not comp.get("size"):
                continue
            off = int(comp["offset"])
            size = int(comp["size"])
            require(np.allclose(state["integration_state"][:, off:off + size],
                                state[member], rtol=0.0, atol=0.0,
                                equal_nan=allow_nonfinite),
                    f"{member} does not match the native state component {component}")

        checkpoints = read_state_archive_bytes(raw_files["checkpoints.npz"],
                                               expected_members=_CHECKPOINT_MEMBERS,
                                               max_bytes=max_bytes, max_rows=4,
                                               allow_nonfinite=allow_nonfinite)
        meta = state_meta.get("checkpoints", {})
        hashes = meta.get("hashes", {}) if isinstance(meta, dict) else {}
        for name in ("initial", "post_settle", "terminal"):
            row = int(meta.get(f"{name}_row", -1))
            require(0 <= row < rows, f"checkpoint {name} row {row} is out of range")
            require(int(checkpoints[f"{name}_row"]) == row,
                    f"checkpoint {name} row differs between metadata and archive")
            require(np.array_equal(checkpoints[name], state["integration_state"][row],
                                   equal_nan=True),
                    f"checkpoint {name} does not equal state row {row}")
            if hashes.get(name):
                require(state_sha256(state["integration_state"][row]) == hashes[name],
                        f"checkpoint {name} hash does not match state row {row}")
        require(int(meta.get("initial_row", -1)) == 0, "initial checkpoint row must be 0")
        require(int(meta.get("terminal_row", -1)) == rows - 1,
                "terminal checkpoint row must be the last archive row")

        source_hashes = {rel: raw_sha256(raw) for rel, raw in raw_files.items()}
    except ReplayError:
        raise
    except (EvidenceError, ArchiveError, ScenarioError) as exc:
        raise ReplayError(str(exc)) from exc
    except (KeyError, IndexError, TypeError, AttributeError, ValueError,
            RecursionError) as exc:
        raise ReplayError(f"malformed run evidence: {type(exc).__name__}: {exc}") from exc
    return VerifiedRun(run_dir, manifest, summary, report, scenario, acceptance,
                       scenario_text, acceptance_text, xml, assets, state, checkpoints,
                       state_meta, source_hashes)


def parse_saved_scene(xml: bytes, assets: dict[str, bytes]):
    """Parse and compile the saved scene in memory, with no filesystem reopen.

    Every ``file`` attribute is read from the **parsed** tree (so single quotes and XML
    character references cannot hide a path), required to be a safe ``assets/*.stl`` key in
    the verified map, and the full map is supplied to MuJoCo so it cannot fall back to the
    filesystem.
    """
    mujoco = require_mujoco()
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise ReplayError("scene.xml contains a DTD/entity declaration")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ReplayError(f"scene.xml is not well-formed XML: {exc}") from exc
    referenced: list[str] = []
    for element in root.iter():
        tag = element.tag.lower()
        if tag in ("include", "plugin", "extension"):
            raise ReplayError(f"scene.xml contains unsupported element <{element.tag}>")
        for key, value in element.attrib.items():
            if key.lower() in ("plugin", "meshdir", "texturedir", "assetdir", "compiler"):
                raise ReplayError(f"scene.xml uses unsupported attribute {key!r}")
            if key.lower() != "file":
                continue
            if value.startswith("/") or value.startswith("\\") or ".." in value \
                    or "://" in value or "\\" in value:
                raise ReplayError(f"scene.xml references unsafe asset path {value!r}")
            if not value.startswith("assets/") or not value.endswith(".stl"):
                raise ReplayError(f"scene.xml references unexpected asset {value!r}")
            referenced.append(value)
    if len(set(referenced)) != len(referenced):
        raise ReplayError("scene.xml references a duplicate mesh name")
    if set(referenced) != set(assets):
        raise ReplayError("scene.xml asset set differs from the verified asset set")
    asset_map = {value: assets[value] for value in referenced}
    try:
        model = mujoco.MjModel.from_xml_string(xml.decode("utf-8"), asset_map)
    except Exception as exc:
        raise ReplayError(f"MuJoCo rejected the saved scene: {exc}") from exc
    return model


def _verify_compiled_against_record(mujoco, model, summary: dict) -> None:
    identity = summary["solver"]["runtime_identity"]
    layout = state_layout(mujoco, model)
    require(layout["mask"] == int(identity["state_mask"]),
            "runtime state mask differs from the recorded runtime")
    require(layout["size"] == int(identity["state_size"]),
            "runtime state size differs from the recorded runtime")
    model.opt.enableflags = int(identity["enableflags"])
    model.opt.disableflags = int(identity["disableflags"])
    checks = {
        "timestep_s": float(model.opt.timestep), "integrator": int(model.opt.integrator),
        "cone": int(model.opt.cone), "solver": int(model.opt.solver),
        "iterations": int(model.opt.iterations),
    }
    for key, value in checks.items():
        require(value == identity[key], f"compiled {key} differs from the recorded runtime")
    for key in ("tolerance", "ls_tolerance", "ccd_tolerance", "impratio"):
        require(float(getattr(model.opt, key)) == float(identity[key]),
                f"compiled {key} differs from the recorded runtime")
    require(np.allclose(model.opt.gravity, identity["gravity_m_s2"], rtol=0.0, atol=1e-12),
            "compiled gravity differs from the recorded runtime")
    require(np.allclose(model.opt.wind, identity["wind_m_s"], rtol=0.0, atol=1e-12),
            "compiled wind differs from the recorded runtime")
    for key in ("density", "viscosity", "o_margin"):
        require(float(getattr(model.opt, key)) == float(identity[
            {"density": "density_kg_m3", "viscosity": "viscosity_pa_s",
             "o_margin": "o_margin_m"}[key]]),
            f"compiled {key} differs from the recorded runtime")
    settings = summary["solver"]["solver_settings"]
    require(int(model.opt.integrator) == int(settings["integrator"]),
            "compiled integrator differs from the recorded solver settings")
    require(int(model.opt.cone) == int(settings["cone"]), "compiled cone differs")
    require(int(model.opt.solver) == int(settings["solver"]), "compiled solver differs")
    require(int(model.opt.iterations) == int(settings["iterations"]),
            "compiled iterations differ")
    if model.ngeom:
        require(np.allclose(model.geom_friction[0], settings["friction"],
                            rtol=0.0, atol=1e-12), "compiled friction differs")
    for name, recorded in summary["solver"]["bodies"].items():
        bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
        require(bid >= 0, f"compiled model is missing body {name!r}")
        require(abs(float(model.body_mass[bid]) - float(recorded["mass_kg"])) <= 1e-12,
                f"compiled mass for body {name!r} differs")
        require(np.allclose(model.body_ipos[bid], recorded["com_m"], rtol=0.0, atol=1e-12),
                f"compiled COM for body {name!r} differs")
    for name, recorded in summary["solver"]["joints"].items():
        jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        require(jid >= 0, f"compiled model is missing joint {name!r}")
        dof = int(model.jnt_dofadr[jid])
        qadr = int(model.jnt_qposadr[jid])
        require(abs(float(model.jnt_stiffness[jid]) - recorded["stiffness"]) <= 1e-12,
                f"compiled spring stiffness for {name!r} differs")
        require(abs(float(model.qpos_spring[qadr]) - recorded["qpos_spring"]) <= 1e-12,
                f"compiled spring reference for {name!r} differs")
        require(np.allclose(model.jnt_range[jid], recorded["range"], rtol=0.0, atol=1e-12),
                f"compiled range for {name!r} differs")
        require(abs(float(model.dof_damping[dof]) - recorded["damping"]) <= 1e-12,
                f"compiled damping for {name!r} differs")
        require(abs(float(model.dof_frictionloss[dof]) - recorded["frictionloss"]) <= 1e-12,
                f"compiled frictionloss for {name!r} differs")
        require(abs(float(model.dof_armature[dof]) - recorded["armature"]) <= 1e-12,
                f"compiled armature for {name!r} differs")
    for name, recorded in summary["solver"]["actuators"].items():
        aid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
        require(aid >= 0, f"compiled model is missing actuator {name!r}")
        require(abs(float(model.actuator_gear[aid][0]) - recorded["gear"]) <= 1e-12,
                f"compiled gear for {name!r} differs")
        require(np.allclose(model.actuator_ctrlrange[aid], recorded["ctrlrange"],
                            rtol=0.0, atol=1e-12),
                f"compiled ctrlrange for {name!r} differs")
        require(np.allclose(model.actuator_forcerange[aid], recorded["forcerange"],
                            rtol=0.0, atol=1e-12),
                f"compiled forcerange for {name!r} differs")


def _phase_kind(scenario, name: str) -> str:
    for phase in scenario.phases:
        if phase.name == name:
            return phase.kind
    raise ReplayError(f"phase {name!r} is not declared in the saved scenario")


def _replay_steps(mujoco, model, verified: VerifiedRun, *, start_row: int,
                  deadline: float | None = None) -> dict:
    """Restore ``start_row`` and replay every later recorded transition with real mj_step."""
    state = verified.state
    rows = int(state["time"].shape[0])
    data = mujoco.MjData(model)
    set_native_state(mujoco, model, data, state["integration_state"][start_row])
    round_trip = get_native_state(mujoco, model, data)
    require(np.array_equal(round_trip, state["integration_state"][start_row],
                           equal_nan=True),
            "native state restore does not round-trip")
    plan = verified.summary["plan"]
    solver = verified.summary["solver"]
    joint_types = {name: int(rec.get("type", -1)) for name, rec in solver["joints"].items()}
    effort_units = {}
    for name, rec in solver["actuators"].items():
        jtype = joint_types.get(rec.get("joint"), -1)
        effort_units[name] = "N m" if jtype == 3 else "N"
    recorder = TelemetryRecorder(
        mujoco, model, data, sample_every=int(plan["sample_every_steps"]),
        effort_units=effort_units,
        max_contact_rows=int(verified.scenario.budgets.max_trace_rows) * 16,
        events=verified.acceptance.events,
        gravity_m_s2=tuple(float(v) for v in
                           verified.summary["solver"]["runtime_identity"]["gravity_m_s2"]))
    phase_names = [str(v) for v in state["phase_names"]]
    phase_index = state["phase_index"]
    if start_row == 0:
        recorder.record_initial(phase_names[0])
    replayed_rows = [np.array(state["integration_state"][start_row])]
    for p in range(1, len(phase_names)):
        indices = [k for k in range(rows) if int(phase_index[k]) == p and k > start_row]
        if not indices:
            continue
        phase_spec = next(ph for ph in verified.scenario.phases if ph.name == phase_names[p])
        progress = PhaseTelemetry(name=phase_names[p],
                                  kind=_phase_kind(verified.scenario, phase_names[p]),
                                  requested_duration_s=phase_spec.duration_s,
                                  requested_steps=len(indices))
        progress.actuator = phase_spec.actuator
        progress.requested_effort = phase_spec.effort
        ctrl = np.asarray(state["transition_ctrl"][indices[0]])
        ctrl_map = {name: float(ctrl[i])
                    for i, name in enumerate([str(v) for v in state["actuator_names"]])}
        bounded = {}
        if phase_spec.kind == "actuate" and phase_spec.actuator in solver["actuators"]:
            record = solver["actuators"][phase_spec.actuator]
            bounded[phase_spec.actuator] = max(
                -float(record["max_effort"]),
                min(float(record["max_effort"]), float(phase_spec.effort or 0.0)))
        recorder.begin_phase(progress, ctrl_map, bounded)
        for k in indices:
            if deadline is not None and time.perf_counter() > deadline:
                raise ReplayError("replay wall budget exceeded before a step")
            ok = recorder.step_with_transition(
                ctrl=state["transition_ctrl"][k],
                qfrc_applied=state["transition_qfrc_applied"][k],
                xfrc_applied=(state["transition_xfrc_applied"][k]
                              if "transition_xfrc_applied" in state else None),
                mocap_pos=(state["transition_mocap_pos"][k]
                           if "transition_mocap_pos" in state else None),
                mocap_quat=(state["transition_mocap_quat"][k]
                            if "transition_mocap_quat" in state else None),
            )
            replayed_rows.append(np.array(get_native_state(mujoco, model, data)))
            if not ok:
                break
        recorder.end_phase()
        if recorder.telemetry.stopped:
            break
    recorder.finish()
    recorder.freeze_state()
    expected_rows = rows - start_row
    completed = len(replayed_rows) == expected_rows and not recorder.telemetry.stopped
    return {"rows": np.asarray(replayed_rows), "telemetry": recorder.telemetry,
            "start_row": start_row, "expected_rows": expected_rows,
            "completed": completed, "stopped": bool(recorder.telemetry.stopped),
            "invalid": list(recorder.telemetry.invalid)}


def _compliance_reasons(mujoco, model, summary: dict) -> list[dict]:
    """Recompute the M4a contact/stop compliance gate for the replayed model."""
    reasons: list[dict] = []
    contact = summary["solver"].get("contact_timeconst", {})
    declared = contact.get("declared_s")
    if declared is not None:
        effective = effective_timeconst(mujoco, model, float(declared))
        if effective > float(declared) * (1.0 + 1e-12):
            reasons.append({"stage": "compliance", "time_s": 0.0,
                            "reason": f"declared contact time constant {declared!r} s is "
                                      f"below the effective {effective!r} s"})
    for name, record in summary["solver"]["joints"].items():
        effective = record.get("stop_effective_timeconst_s")
        solref = record.get("solreflimit")
        if effective is None or not solref:
            continue
        if float(effective) > float(solref[0]) * (1.0 + 1e-12):
            reasons.append({"stage": "compliance", "time_s": 0.0,
                            "reason": f"joint stop {name!r} declared {solref[0]!r} s but "
                                      f"effective {effective!r} s"})
    return reasons


def _compare_states(source: np.ndarray, replayed: np.ndarray, start_row: int,
                    expected_rows: int | None = None) -> dict:
    """Elementwise comparison with explicit nonfinite and exact-length semantics."""
    expected = source[start_row:start_row + len(replayed)]
    if expected.shape != replayed.shape:
        return {"ok": False, "reason":
                f"replayed {replayed.shape} rows vs source {expected.shape}",
                "rows": int(replayed.shape[0]), "start_row": int(start_row),
                "expected_rows": expected_rows, "max_abs_diff": None,
                "nonfinite_mismatches": 0, "first_mismatch": None}
    if expected_rows is not None and len(replayed) != expected_rows:
        return {"ok": False, "reason":
                f"replayed {len(replayed)} rows of {expected_rows} required",
                "rows": int(len(replayed)), "start_row": int(start_row),
                "expected_rows": expected_rows, "max_abs_diff": None,
                "nonfinite_mismatches": 0, "first_mismatch": None}
    a = np.asarray(expected, dtype=np.float64)
    b = np.asarray(replayed, dtype=np.float64)
    a_nan, b_nan = np.isnan(a), np.isnan(b)
    a_inf, b_inf = np.isinf(a), np.isinf(b)
    both_nan = a_nan & b_nan
    both_inf_same = a_inf & b_inf & (np.sign(a) == np.sign(b))
    both_finite = np.isfinite(a) & np.isfinite(b)
    mismatch = (a_nan ^ b_nan) | (a_inf ^ b_inf) | (a_inf & b_inf & ~both_inf_same)
    allowed = REPLAY_TOLERANCES["state_atol"] + REPLAY_TOLERANCES["state_rtol"] * np.abs(
        np.where(both_finite, a, 0.0))
    finite_diff = np.zeros_like(a)
    np.subtract(a, b, out=finite_diff, where=both_finite)
    finite_diff = np.abs(finite_diff)
    bad = (finite_diff > allowed) & both_finite | mismatch
    finite_values = finite_diff[both_finite]
    return {
        "ok": not bool(np.any(bad)),
        "rows": int(replayed.shape[0]),
        "start_row": int(start_row),
        "expected_rows": expected_rows,
        "max_abs_diff": float(np.max(finite_values)) if finite_values.size else 0.0,
        "nonfinite_mismatches": int(np.count_nonzero(mismatch)),
        "first_mismatch": (None if not np.any(bad) else
                           [int(v) for v in np.argwhere(bad)[0]]),
    }


def _compare_value(source, replayed, path: str, differences: list[str]) -> None:
    """Recursive strict comparison used for metrics, checks and validity evidence."""
    if isinstance(source, dict) or isinstance(replayed, dict):
        if not isinstance(source, dict) or not isinstance(replayed, dict):
            differences.append(f"{path}: type {type(source).__name__} vs "
                               f"{type(replayed).__name__}")
            return
        if set(source) != set(replayed):
            differences.append(f"{path}: key set differs "
                               f"(missing {sorted(set(source) - set(replayed))}, "
                               f"extra {sorted(set(replayed) - set(source))})")
        for key in sorted(set(source) & set(replayed)):
            _compare_value(source[key], replayed[key], f"{path}.{key}", differences)
        return
    if isinstance(source, (list, tuple)) or isinstance(replayed, (list, tuple)):
        if not isinstance(source, (list, tuple)) or not isinstance(replayed, (list, tuple)):
            differences.append(f"{path}: sequence type differs")
            return
        if len(source) != len(replayed):
            differences.append(f"{path}: length {len(source)} vs {len(replayed)}")
            return
        for index, (left, right) in enumerate(zip(source, replayed)):
            _compare_value(left, right, f"{path}[{index}]", differences)
        return
    if source is None or replayed is None:
        if source is not replayed:
            differences.append(f"{path}: {source!r} vs {replayed!r}")
        return
    if isinstance(source, bool) or isinstance(replayed, bool):
        if source != replayed:
            differences.append(f"{path}: {source!r} vs {replayed!r}")
        return
    if isinstance(source, str) or isinstance(replayed, str):
        if source != replayed:
            differences.append(f"{path}: {source!r} vs {replayed!r}")
        return
    if isinstance(source, (int, float)) and isinstance(replayed, (int, float)):
        left, right = float(source), float(replayed)
        if math.isnan(left) or math.isnan(right):
            if not (math.isnan(left) and math.isnan(right)):
                differences.append(f"{path}: one-sided NaN ({left!r} vs {right!r})")
            return
        if math.isinf(left) or math.isinf(right):
            if not (math.isinf(left) and math.isinf(right) and math.copysign(1, left)
                    == math.copysign(1, right)):
                differences.append(f"{path}: nonfinite {left!r} vs {right!r}")
            return
        if abs(left - right) > (REPLAY_TOLERANCES["metric_atol"]
                                + REPLAY_TOLERANCES["metric_rtol"] * abs(left)):
            differences.append(f"{path}: {left!r} vs {right!r}")
        return
    if source != replayed:
        differences.append(f"{path}: {source!r} vs {replayed!r}")


def _compare_evaluations(source: dict, replayed_status: str, checks: list[dict],
                         metrics: dict, validity: dict | None = None) -> dict:
    """Strict recursive comparison of status, checks, metrics and validity evidence."""
    differences: list[str] = []
    if replayed_status != source["status"]:
        differences.append(f"status {replayed_status!r} != source {source['status']!r}")
    source_checks = {c["name"]: c for c in source["checks"]}
    replay_checks = {c["name"]: c for c in checks}
    if set(source_checks) != set(replay_checks):
        differences.append(
            f"check set differs (missing {sorted(set(source_checks) - set(replay_checks))}, "
            f"extra {sorted(set(replay_checks) - set(source_checks))})")
    for name in sorted(set(source_checks) & set(replay_checks)):
        _compare_value(source_checks[name], replay_checks[name], f"check[{name}]",
                       differences)
    _compare_value(source.get("metrics", {}), metrics, "metrics", differences)
    if validity is not None:
        _compare_value(source.get("validity", {}), validity, "validity", differences)
    return {"ok": not differences, "differences": differences}


def _compliance_reasons(mujoco, model, summary: dict) -> list[dict]:
    """Recompute the M4a contact/stop compliance gate for the replayed model."""
    reasons: list[dict] = []
    contact = summary["solver"].get("contact_timeconst", {})
    declared = contact.get("declared_s")
    if declared is not None:
        effective = effective_timeconst(mujoco, model, float(declared))
        if effective > float(declared) * (1.0 + 1e-12):
            reasons.append({"stage": "compliance", "time_s": 0.0,
                            "reason": f"declared contact time constant {declared!r} s is "
                                      f"below the effective {effective!r} s"})
    for name, record in summary["solver"]["joints"].items():
        effective = record.get("stop_effective_timeconst_s")
        solref = record.get("solreflimit")
        if effective is None or not solref:
            continue
        if float(effective) > float(solref[0]) * (1.0 + 1e-12):
            reasons.append({"stage": "compliance", "time_s": 0.0,
                            "reason": f"joint stop {name!r} declared {solref[0]!r} s but "
                                      f"effective {effective!r} s"})
    return reasons


def _compare_states(source: np.ndarray, replayed: np.ndarray, start_row: int,
                    expected_rows: int | None = None) -> dict:
    """Elementwise comparison with explicit nonfinite and exact-length semantics."""
    expected = source[start_row:start_row + len(replayed)]
    if expected.shape != replayed.shape:
        return {"ok": False, "reason":
                f"replayed {replayed.shape} rows vs source {expected.shape}",
                "rows": int(replayed.shape[0]), "start_row": int(start_row),
                "expected_rows": expected_rows, "max_abs_diff": None,
                "nonfinite_mismatches": 0, "first_mismatch": None}
    if expected_rows is not None and len(replayed) != expected_rows:
        return {"ok": False, "reason":
                f"replayed {len(replayed)} rows of {expected_rows} required",
                "rows": int(len(replayed)), "start_row": int(start_row),
                "expected_rows": expected_rows, "max_abs_diff": None,
                "nonfinite_mismatches": 0, "first_mismatch": None}
    a = np.asarray(expected, dtype=np.float64)
    b = np.asarray(replayed, dtype=np.float64)
    a_nan, b_nan = np.isnan(a), np.isnan(b)
    a_inf, b_inf = np.isinf(a), np.isinf(b)
    both_nan = a_nan & b_nan
    both_inf_same = a_inf & b_inf & (np.sign(a) == np.sign(b))
    both_finite = np.isfinite(a) & np.isfinite(b)
    mismatch = (a_nan ^ b_nan) | (a_inf ^ b_inf) | (a_inf & b_inf & ~both_inf_same)
    allowed = REPLAY_TOLERANCES["state_atol"] + REPLAY_TOLERANCES["state_rtol"] * np.abs(
        np.where(both_finite, a, 0.0))
    finite_diff = np.zeros_like(a)
    np.subtract(a, b, out=finite_diff, where=both_finite)
    finite_diff = np.abs(finite_diff)
    bad = (finite_diff > allowed) & both_finite | mismatch
    finite_values = finite_diff[both_finite]
    return {
        "ok": not bool(np.any(bad)),
        "rows": int(replayed.shape[0]),
        "start_row": int(start_row),
        "expected_rows": expected_rows,
        "max_abs_diff": float(np.max(finite_values)) if finite_values.size else 0.0,
        "nonfinite_mismatches": int(np.count_nonzero(mismatch)),
        "first_mismatch": (None if not np.any(bad) else
                           [int(v) for v in np.argwhere(bad)[0]]),
    }


def _compare_value(source, replayed, path: str, differences: list[str]) -> None:
    """Recursive strict comparison used for metrics, checks and validity evidence."""
    if isinstance(source, dict) or isinstance(replayed, dict):
        if not isinstance(source, dict) or not isinstance(replayed, dict):
            differences.append(f"{path}: type {type(source).__name__} vs "
                               f"{type(replayed).__name__}")
            return
        if set(source) != set(replayed):
            differences.append(f"{path}: key set differs "
                               f"(missing {sorted(set(source) - set(replayed))}, "
                               f"extra {sorted(set(replayed) - set(source))})")
        for key in sorted(set(source) & set(replayed)):
            _compare_value(source[key], replayed[key], f"{path}.{key}", differences)
        return
    if isinstance(source, (list, tuple)) or isinstance(replayed, (list, tuple)):
        if not isinstance(source, (list, tuple)) or not isinstance(replayed, (list, tuple)):
            differences.append(f"{path}: sequence type differs")
            return
        if len(source) != len(replayed):
            differences.append(f"{path}: length {len(source)} vs {len(replayed)}")
            return
        for index, (left, right) in enumerate(zip(source, replayed)):
            _compare_value(left, right, f"{path}[{index}]", differences)
        return
    if source is None or replayed is None:
        if source is not replayed:
            differences.append(f"{path}: {source!r} vs {replayed!r}")
        return
    if isinstance(source, bool) or isinstance(replayed, bool):
        if source != replayed:
            differences.append(f"{path}: {source!r} vs {replayed!r}")
        return
    if isinstance(source, str) or isinstance(replayed, str):
        if source != replayed:
            differences.append(f"{path}: {source!r} vs {replayed!r}")
        return
    if isinstance(source, (int, float)) and isinstance(replayed, (int, float)):
        left, right = float(source), float(replayed)
        if math.isnan(left) or math.isnan(right):
            if not (math.isnan(left) and math.isnan(right)):
                differences.append(f"{path}: one-sided NaN ({left!r} vs {right!r})")
            return
        if math.isinf(left) or math.isinf(right):
            if not (math.isinf(left) and math.isinf(right) and math.copysign(1, left)
                    == math.copysign(1, right)):
                differences.append(f"{path}: nonfinite {left!r} vs {right!r}")
            return
        if abs(left - right) > (REPLAY_TOLERANCES["metric_atol"]
                                + REPLAY_TOLERANCES["metric_rtol"] * abs(left)):
            differences.append(f"{path}: {left!r} vs {right!r}")
        return
    if source != replayed:
        differences.append(f"{path}: {source!r} vs {replayed!r}")


def replay_run(run_dir: Path, out_dir: Path) -> dict:
    """Verify a source run, replay it, and write comparison evidence to a fresh directory."""
    started = time.perf_counter()
    source = load_verified_run(Path(run_dir))
    out_dir = Path(out_dir)
    source_resolved = source.run_dir.resolve()
    out_resolved = out_dir.resolve()
    if out_dir.exists():
        raise ReplayError(f"refusing to write into existing path {out_dir}")
    if out_resolved == source_resolved or source_resolved in out_resolved.parents:
        raise ReplayError("replay output must not be inside the source run directory")
    if out_resolved in source_resolved.parents:
        raise ReplayError("replay output must not be an ancestor of the source run")
    out_dir.mkdir(parents=True, exist_ok=False)

    mujoco = require_mujoco()
    model = parse_saved_scene(source.scene_xml, source.assets)
    _verify_compiled_against_record(mujoco, model, source.summary)
    validate_layout(source.state_meta["layout"], model, mujoco)

    deadline = started + MAX_REPLAY_WALL_S
    partial = {"stage": "full", "rows": 0}
    wall = 0.0
    try:
        full = _replay_steps(mujoco, model, source, start_row=0, deadline=deadline)
        partial["rows"] = int(full["rows"].shape[0])
        full_cmp = _compare_states(source.state["integration_state"], full["rows"], 0,
                                   expected_rows=full["expected_rows"])
        partial["stage"] = "tail"
        meta = source.state_meta["checkpoints"]
        tail_start = int(meta["post_settle_row"])
        tail_state = source.state["integration_state"][tail_start]
        if not np.all(np.isfinite(tail_state)):
            if source.summary["status"] == "PASS":
                raise ReplayError("PASS run has a non-finite post-settle checkpoint")
            # A numerical-stop run may have a non-finite checkpoint; the finite prefix was
            # already compared above, so continuation is explicitly skipped rather than faked.
            tail_cmp = {"ok": True, "rows": 0, "start_row": tail_start,
                        "skipped": "non-finite checkpoint row in a non-PASS source",
                        "max_abs_diff": 0.0, "first_mismatch": None}
        else:
            tail = _replay_steps(mujoco, model, source, start_row=tail_start, deadline=deadline)
            tail_cmp = _compare_states(source.state["integration_state"], tail["rows"], tail_start,
                                       expected_rows=tail["expected_rows"])
            if tail["stopped"] or tail["invalid"]:
                tail_cmp = dict(tail_cmp)
                tail_cmp["ok"] = False
                tail_cmp["reason"] = ("tail stopped or invalid: "
                                      + "; ".join(r.get("reason", "") for r in tail["invalid"]))
                tail_cmp["tail_invalid"] = True
        replayed_status = None
        evaluation = None
        if full["telemetry"] is not None:
            evaluation = evaluate(source.scenario, source.acceptance, full["telemetry"],
                                  compliance_reasons=_compliance_reasons(mujoco, model,
                                                                         source.summary))
            replayed_status = evaluation.status
        eval_cmp = _compare_evaluations(source.summary, replayed_status or "ERROR",
                                        [c.to_dict() for c in (evaluation.checks
                                                               if evaluation else [])],
                                        evaluation.metrics if evaluation else {},
                                        evaluation.validity if evaluation else None)
        replayed_events = ([result.to_dict()
                            for result in full["telemetry"].event_results.values()]
                           if full["telemetry"] is not None else [])
        event_differences: list[str] = []
        _compare_value(source.summary.get("events", []), replayed_events,
                       "events", event_differences)
        event_cmp = {"ok": not event_differences, "differences": event_differences}
        full_complete = len(full["rows"]) == int(full["expected_rows"])
        tail_complete = bool(tail_cmp.get("ok")) and (
            bool(tail_cmp.get("rows", 0)) or bool(tail_cmp.get("skipped")))
        reproduced = bool(full_cmp["ok"] and tail_cmp["ok"] and eval_cmp["ok"]
                          and event_cmp["ok"] and full_complete and tail_complete)
        wall = time.perf_counter() - started
        if wall > MAX_REPLAY_WALL_S:
            raise ReplayError(
                f"replay wall time {wall:.3f}s exceeded {MAX_REPLAY_WALL_S}s")
        # Source evidence must be byte-identical before any result is published.
        for rel, digest in source.source_hashes.items():
            require(raw_sha256(bounded_regular_bytes(source.run_dir, rel)) == digest,
                    f"source evidence {rel!r} changed during replay")
    except (ReplayError, EvidenceError, ArchiveError, ScenarioError, ValueError) as exc:
        failure = {
            "schema_version": REPLAY_FORMAT, "status": "ERROR",
            "source_run": str(source.run_dir), "source_status": source.summary["status"],
            "detail": str(exc), "partial": partial,
            "source_hashes": source.source_hashes,
            "wall_s": time.perf_counter() - started,
        }
        (out_dir / "replay.json").write_text(
            json.dumps(_jsonable(failure), indent=2, allow_nan=False) + "\n",
            encoding="utf-8")
        (out_dir / "replay_report.md").write_text(
            f"# M4b replay\n\nStatus: **ERROR**  \nStage: `{partial['stage']}`  \n"
            f"Detail: {exc}\n", encoding="utf-8")
        raise
    if reproduced:
        status = source.summary["status"]
    else:
        status = "INCONCLUSIVE"

    result = {
        "schema_version": REPLAY_FORMAT,
        "status": status,
        "source_run": str(source.run_dir),
        "source_status": source.summary["status"],
        "replay_status": replayed_status,
        "reproduced": reproduced,
        "tolerances": REPLAY_TOLERANCES,
        "state_comparison": full_cmp,
        "post_settle_continuation": tail_cmp,
        "evaluation_comparison": eval_cmp,
        "event_comparison": event_cmp,
        "runtime": source.manifest["solver"]["runtime_identity"],
        "source_hashes": source.source_hashes,
        "wall_s": wall,
        "replayed_state_rows": int(full["rows"].shape[0]),
        "detail": "",
    }
    (out_dir / "replay.json").write_text(
        json.dumps(_jsonable(result), indent=2, allow_nan=False) + "\n", encoding="utf-8")
    write_archive(out_dir / "replayed_states.npz",
                  {"integration_state": full["rows"],
                   "start_row": np.asarray(0, dtype=np.int64)})
    (out_dir / "replay_report.md").write_text(_render_replay(result), encoding="utf-8")
    return result


def _jsonable(value):
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    return value


def _render_replay(result: dict) -> str:
    lines = [
        "# M4b replay", "",
        f"Status: **{result['status']}**  ",
        f"Source run: `{result['source_run']}`  ",
        f"Source status: `{result['source_status']}`; replayed status: "
        f"`{result['replay_status']}`  ",
        f"Reproduced: `{result['reproduced']}`  ",
        "",
        "| comparison | ok | rows | max abs diff | first mismatch |",
        "|---|---|---|---|---|",
    ]
    for name, key in (("full state", "state_comparison"),
                      ("post-settle continuation", "post_settle_continuation")):
        cmp = result[key]
        lines.append(f"| {name} | {cmp['ok']} | {cmp.get('rows', 'n/a')} | "
                     f"{cmp.get('max_abs_diff', 'n/a')} | {cmp.get('first_mismatch')} |")
    lines.extend([
        "",
        f"Events recomputed identically: `{result.get('event_comparison', {}).get('ok')}`",
        f"Evaluation differences: {result['evaluation_comparison']['differences']}",
        "",
        f"Wall time: {result['wall_s']:.3f} s",
        "",
    ])
    return "\n".join(lines)
