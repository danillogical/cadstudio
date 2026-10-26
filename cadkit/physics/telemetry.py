"""Headless telemetry for the generic M4a phase runner.

Every integration step is checked for finiteness and accumulated into per-step maxima, so a
rare transient cannot disappear between the sparse CSV samples. The sparse trace is a display
artifact; the signed maxima in the summary are computed from **every** step.

All observed quantities belong to one state timestamp. After ``mj_step`` the integration
state is copied to a private scratch ``MjData`` and ``mj_forward`` is run there, so poses,
COM, velocities, energy, contacts and forces are evaluated at ``state_time``
(``force_time_s == state_time_s``, ``force_stage`` names the origin). The live state is never
rewritten and the integration sequence is unchanged; RK4 intermediate stages are not sampled.
Solver warning counters are read from the live stepped ``MjData``, where ``mj_step`` sets
them.

The state archive contains the full integration state needed by a later deterministic replay
(``time``, ``qpos``, ``qvel``, ``act``, ``ctrl``, ``qacc_warmstart``, applied forces and
mocap), not just ``qpos``/``qvel``. It is a compressed NumPy archive, never pickle.
"""
from __future__ import annotations

import csv
import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .events import (
    EventTracker,
    ObservedBody,
    ObservedContact,
    StepObservation,
)
from .state_archive import (
    get_native_state,
    set_native_state,
    state_bytes_estimate,
    state_layout,
)

#: Warning counters, by name, from the installed enum. The sentinel is excluded.
WARNING_NAMES = (
    "mjWARN_INERTIA", "mjWARN_CONTACTFULL", "mjWARN_CNSTRFULL", "mjWARN_BADQPOS",
    "mjWARN_BADQVEL", "mjWARN_BADQACC", "mjWARN_BADCTRL",
)


def warning_counts(mujoco, data) -> dict[str, int]:
    return {name.removeprefix("mjWARN_").lower():
            int(data.warning[int(getattr(mujoco.mjtWarning, name))].number)
            for name in WARNING_NAMES}


def state_hash(*arrays: np.ndarray) -> str:
    digest = hashlib.sha256()
    for array in arrays:
        contiguous = np.ascontiguousarray(array, dtype=np.float64)
        digest.update(str(contiguous.shape).encode("ascii"))
        digest.update(contiguous.tobytes())
    return digest.hexdigest()


# --------------------------------------------------------------- relative motion math
def quat_to_matrix(quat_wxyz) -> np.ndarray:
    """Body-to-world rotation matrix from a MuJoCo ``(w, x, y, z)`` quaternion."""
    w, x, y, z = (float(v) for v in quat_wxyz)
    norm_sq = w * w + x * x + y * y + z * z
    if not (math.isfinite(norm_sq) and norm_sq > 0.0):
        raise ValueError(f"quaternion {quat_wxyz!r} is not normalizable")
    s = 2.0 / norm_sq
    return np.asarray([
        [1.0 - s * (y * y + z * z), s * (x * y - w * z), s * (x * z + w * y)],
        [s * (x * y + w * z), 1.0 - s * (x * x + z * z), s * (y * z - w * x)],
        [s * (x * z - w * y), s * (y * z + w * x), 1.0 - s * (x * x + y * y)],
    ], dtype=np.float64)


def matrix_to_quaternion(matrix) -> tuple[float, float, float, float]:
    """Unit ``(w, x, y, z)`` quaternion of a rotation matrix, robust near 180 degrees."""
    m = np.asarray(matrix, dtype=np.float64).reshape(3, 3)
    trace = float(m[0, 0] + m[1, 1] + m[2, 2])
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * s
        x = (m[2, 1] - m[1, 2]) / s
        y = (m[0, 2] - m[2, 0]) / s
        z = (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(max(0.0, 1.0 + m[0, 0] - m[1, 1] - m[2, 2])) * 2.0
        w = (m[2, 1] - m[1, 2]) / s
        x = 0.25 * s
        y = (m[0, 1] + m[1, 0]) / s
        z = (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(max(0.0, 1.0 + m[1, 1] - m[0, 0] - m[2, 2])) * 2.0
        w = (m[0, 2] - m[2, 0]) / s
        x = (m[0, 1] + m[1, 0]) / s
        y = 0.25 * s
        z = (m[1, 2] + m[2, 1]) / s
    else:
        s = math.sqrt(max(0.0, 1.0 + m[2, 2] - m[0, 0] - m[1, 1])) * 2.0
        w = (m[1, 0] - m[0, 1]) / s
        x = (m[0, 2] + m[2, 0]) / s
        y = (m[1, 2] + m[2, 1]) / s
        z = 0.25 * s
    norm = math.sqrt(w * w + x * x + y * y + z * z)
    if not (math.isfinite(norm) and norm > 0.0):
        raise ValueError("rotation matrix did not produce a finite quaternion")
    return (w / norm, x / norm, y / norm, z / norm)


def relative_transform(pos_a, quat_a, pos_b, quat_b) -> tuple[np.ndarray, np.ndarray]:
    """``inverse(T_a) . T_b`` for body-to-world poses.

    ``p_rel = R_a^T (p_b - p_a)`` is the position of body b in body a's **current** attached
    local axes, and ``R_rel = R_a^T R_b`` the relative orientation. Both bodies undergoing the
    same rigid motion leaves both quantities constant; freezing the initial axes and
    subtracting world separations does not.
    """
    rotation_a = quat_to_matrix(quat_a)
    p_rel = rotation_a.T @ (np.asarray(pos_b, dtype=np.float64)
                            - np.asarray(pos_a, dtype=np.float64))
    rotation_rel = rotation_a.T @ quat_to_matrix(quat_b)
    if not (np.all(np.isfinite(p_rel)) and np.all(np.isfinite(rotation_rel))):
        raise ValueError("relative transform is not finite")
    return p_rel, rotation_rel


def rotation_angle_rad(rotation) -> float:
    """Angle of a rotation matrix: ``2 acos(clamp(|w|, 0, 1))``."""
    w = matrix_to_quaternion(rotation)[0]
    return 2.0 * math.acos(min(1.0, max(0.0, abs(w))))


def pose_delta(p_rel_0, rotation_rel_0, p_rel_1, rotation_rel_1
               ) -> tuple[np.ndarray, float]:
    """Change of the attached-local relative pose: ``Δp`` and the angle of ``ΔR``."""
    delta_p = (np.asarray(p_rel_1, dtype=np.float64)
               - np.asarray(p_rel_0, dtype=np.float64))
    delta_rotation = np.asarray(rotation_rel_1, dtype=np.float64) @ np.asarray(
        rotation_rel_0, dtype=np.float64).T
    return delta_p, rotation_angle_rad(delta_rotation)


_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


@dataclass(frozen=True)
class Snapshot:
    time_s: float
    qpos: dict[str, float]
    qvel: dict[str, float]
    hash: str
    free_joints: dict[str, dict] = field(default_factory=dict)
    bodies: dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"time_s": self.time_s, "qpos": dict(self.qpos), "qvel": dict(self.qvel),
                "free_joints": {k: dict(v) for k, v in self.free_joints.items()},
                "bodies": {k: dict(v) for k, v in self.bodies.items()},
                "hash": self.hash}


def body_force_command(mujoco, model, phase: "PhaseSpec", steps: int):
    """``force_at(step) -> (nbody, 6)`` xfrc_applied for a ``body_force`` phase, else ``None``.

    The force is world-frame at the body COM (MuJoCo's ``xfrc_applied`` point); torque is zero.
    Replay recomputes it through this function, so run and replay cannot disagree.
    """
    if phase.body_force is None:
        return None
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, phase.body_force.body)
    if body_id < 0:
        raise ValueError(f"model has no body {phase.body_force.body!r}")
    nbody = int(model.nbody)

    def force_at(step: int):
        xfrc = np.zeros((nbody, 6), dtype=np.float64)
        xfrc[body_id, :3] = phase.body_force.force_at(step, steps)
        return xfrc

    return force_at


@dataclass
class PhaseTelemetry:
    name: str
    kind: str
    requested_duration_s: float | None
    actual_duration_s: float | None = None
    requested_steps: int = 0
    actual_steps: int = 0
    start_time_s: float | None = None
    end_time_s: float | None = None
    complete: bool = True
    actuator: str | None = None
    requested_effort: float | None = None
    requested_effort_end: float | None = None
    body_force_body: str | None = None
    requested_force_n: tuple[float, float, float] | None = None
    requested_force_end_n: tuple[float, float, float] | None = None
    effort_units: str = ""
    ctrl_requested: float | None = None
    ctrl_effective_peak: float | None = None

    def to_dict(self) -> dict:
        out = self._base_dict()
        if self.requested_effort_end is not None:
            out["requested_effort_end"] = self.requested_effort_end
        if self.requested_force_n is not None:
            out["body_force_body"] = self.body_force_body
            out["requested_force_n"] = list(self.requested_force_n)
            if self.requested_force_end_n is not None:
                out["requested_force_end_n"] = list(self.requested_force_end_n)
        return out

    def _base_dict(self) -> dict:
        return {
            "name": self.name, "kind": self.kind,
            "requested_duration_s": self.requested_duration_s,
            "actual_duration_s": self.actual_duration_s,
            "requested_steps": self.requested_steps,
            "actual_steps": self.actual_steps,
            "start_time_s": self.start_time_s,
            "end_time_s": self.end_time_s,
            "complete": self.complete,
            "actuator": self.actuator,
            "requested_effort": self.requested_effort,
            "effort_units": self.effort_units,
            "ctrl_requested": self.ctrl_requested,
            "ctrl_effective_peak": self.ctrl_effective_peak,
        }


@dataclass
class Telemetry:
    phases: list[PhaseTelemetry] = field(default_factory=list)
    boundaries: dict[str, Snapshot] = field(default_factory=dict)
    boundary_rows: dict[str, int] = field(default_factory=dict)
    layout: dict = field(default_factory=dict)
    trace_header: list[str] = field(default_factory=list)
    trace_rows: list[list] = field(default_factory=list)
    contact_header: list[str] = field(default_factory=list)
    contact_rows: list[list] = field(default_factory=list)
    state: dict[str, np.ndarray] = field(default_factory=dict)
    invalid: list[dict] = field(default_factory=list)
    warnings: dict[str, int] = field(default_factory=dict)
    peak_speed: float = 0.0
    peak_angular_speed_rad_s: float = 0.0
    peak_joint_speed: dict[str, float] = field(default_factory=dict)
    peak_energy_j: float = 0.0
    peak_penetration_m: float = 0.0
    peak_contact_force_n: float = 0.0
    peak_effort: dict[str, float] = field(default_factory=dict)
    peak_effort_signed: dict[str, float] = field(default_factory=dict)
    peak_ctrl_stored: dict[str, float] = field(default_factory=dict)
    peak_ctrl_stored_signed: dict[str, float] = field(default_factory=dict)
    peak_ctrl_effective: dict[str, float] = field(default_factory=dict)
    peak_ctrl_effective_signed: dict[str, float] = field(default_factory=dict)
    effort_tracking_error: dict[str, float] = field(default_factory=dict)
    contact_pairs: dict[tuple, dict] = field(default_factory=dict)
    event_results: dict[str, object] = field(default_factory=dict)
    #: Every-step evidence for bound relative-pose/translation, max-over-phase speed, and
    #: whole-run summed contact-duration watches, keyed by check name. Empty unless the
    #: acceptance declares those kinds; older runs therefore serialize identically.
    watch_evidence: dict[str, dict] = field(default_factory=dict)
    commanded_actuators: set[str] = field(default_factory=set)
    initial_penetration_m: float = 0.0
    initial_contact_force_n: float = 0.0
    initial_speed_m_s: float = 0.0
    initial_angular_speed_rad_s: float = 0.0
    initial_energy_j: float = 0.0
    initial_rejected: bool = False
    stopped: bool = False

    def metrics(self) -> dict:
        return {
            "peak_speed_m_s": self.peak_speed,
            "peak_angular_speed_rad_s": self.peak_angular_speed_rad_s,
            "peak_joint_speed": dict(self.peak_joint_speed),
            "peak_energy_j": self.peak_energy_j,
            "peak_penetration_m": self.peak_penetration_m,
            "peak_contact_force_n": self.peak_contact_force_n,
            "peak_effort": dict(self.peak_effort),
            "peak_effort_signed": dict(self.peak_effort_signed),
            "peak_ctrl_stored": dict(self.peak_ctrl_stored),
            "peak_ctrl_stored_signed": dict(self.peak_ctrl_stored_signed),
            "peak_ctrl_effective": dict(self.peak_ctrl_effective),
            "peak_ctrl_effective_signed": dict(self.peak_ctrl_effective_signed),
            "effort_tracking_error": dict(self.effort_tracking_error),
            "commanded_actuators": sorted(self.commanded_actuators),
            "initial_penetration_m": self.initial_penetration_m,
            "initial_contact_force_n": self.initial_contact_force_n,
            "initial_speed_m_s": self.initial_speed_m_s,
            "initial_angular_speed_rad_s": self.initial_angular_speed_rad_s,
            "initial_energy_j": self.initial_energy_j,
            "initial_rejected": self.initial_rejected,
        }

    def contacts(self) -> list[dict]:
        rows = []
        for (body_a, geom_a, body_b, geom_b), values in sorted(self.contact_pairs.items()):
            rows.append({
                "body_a": body_a, "geom_a": geom_a, "body_b": body_b, "geom_b": geom_b,
                "max_normal_force_n": values["max_normal_force_n"],
                "max_penetration_m": values["max_penetration_m"],
                "samples": values["samples"],
            })
        return rows


class TelemetryRecorder:
    """Steps a compiled model while recording every reported quantity."""

    def __init__(self, mujoco, model, data, *, sample_every: int,
                 effort_units: dict[str, str], max_contact_rows: int | None = None,
                 max_state_rows: int | None = None,
                 max_state_bytes: int | None = None,
                 events: tuple = (), checks: tuple = (),
                 gravity_m_s2: tuple[float, float, float] =
                 (0.0, 0.0, -9.80665)):
        self.mujoco = mujoco
        self.model = model
        self.data = data
        self.scratch = mujoco.MjData(model)
        self.event_tracker = (EventTracker(events, gravity_m_s2=gravity_m_s2)
                              if events else None)
        self._event_body_ids = ({body_id for event in events
                                 for body_id in (*event.bodies, *event.support_bodies)}
                                if events else set())
        self._observed = None
        self.dt = float(model.opt.timestep)
        self.sample_every = max(1, int(sample_every))
        self.telemetry = Telemetry()
        self._phase: PhaseTelemetry | None = None
        self._step_index = 0
        self._phase_code = 0
        self._phase_index = 0
        self._phase_names: list[str] = []
        self._warned: set[str] = set()
        self._ctrl_by_actuator: dict[str, float] = {}
        self._command_at = None
        self._force_at = None
        self._effort_by_actuator: dict[str, float] = {}
        self._effort_units = dict(effort_units)
        self.max_contact_rows = max_contact_rows
        self.max_state_rows = max_state_rows
        self.max_state_bytes = max_state_bytes
        self.layout = state_layout(mujoco, model)
        self.telemetry.layout = self.layout

        self.free_joints: list[tuple[str, int, int, int]] = []
        for j in range(model.njnt):
            if int(model.jnt_type[j]) != int(mujoco.mjtJoint.mjJNT_FREE):
                continue
            name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j)
            if not name:
                raise ValueError(f"free joint {j} has no name; telemetry needs named joints")
            self.free_joints.append((name, int(model.jnt_dofadr[j]),
                                     int(model.jnt_qposadr[j]),
                                     int(model.jnt_bodyid[j])))

        self.joints: list[tuple[str, int, int, str, str, str]] = []
        for j in range(model.njnt):
            jtype = int(model.jnt_type[j])
            if jtype not in (int(mujoco.mjtJoint.mjJNT_HINGE),
                             int(mujoco.mjtJoint.mjJNT_SLIDE)):
                continue
            name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j)
            if not name:
                raise ValueError(f"joint {j} has no name; telemetry needs named joints")
            coord = "rad" if jtype == int(mujoco.mjtJoint.mjJNT_HINGE) else "m"
            vel = "rad/s" if coord == "rad" else "m/s"
            force = "N m" if coord == "rad" else "N"
            self.joints.append((name, j, int(model.jnt_qposadr[j]), coord, vel, force))
            self.telemetry.peak_joint_speed[name] = 0.0

        self.bodies: list[tuple[str, int]] = []
        for b in range(1, model.nbody):
            name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, b) or f"body{b}"
            self.bodies.append((name, b))

        self._body_ids = {name: body_id for name, body_id in self.bodies}
        # Every-step watches derived from the acceptance checks. Only the kinds whose
        # semantics need per-step evidence are registered; terminal-only checks are
        # evaluated from recorded phase boundaries.
        self._pose_watches: dict[str, dict] = {}
        self._translation_watches: dict[str, dict] = {}
        self._speed_watches: list[dict] = []
        self._contact_watches: dict[str, dict] = {}
        self._contact_state: dict[str, dict] = {}
        self._build_watches(checks)

        self.actuators: list[tuple[str, int, int, float, str]] = []
        for a in range(model.nactuator):
            name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, a) or f"actuator{a}"
            joint_id = int(model.actuator_trnid[a][0])
            if not 0 <= joint_id < model.njnt:
                raise ValueError(f"actuator {name!r} is not attached to a joint")
            dof = int(model.jnt_dofadr[joint_id])
            gear = float(model.actuator_gear[a][0])
            jtype = int(model.jnt_type[joint_id])
            units = "N m" if jtype == int(mujoco.mjtJoint.mjJNT_HINGE) else "N"
            self.actuators.append((name, a, dof, gear, units))
            self.telemetry.peak_effort[name] = 0.0
            self.telemetry.peak_effort_signed[name] = 0.0
            self.telemetry.peak_ctrl_stored[name] = 0.0
            self.telemetry.peak_ctrl_stored_signed[name] = 0.0
            self.telemetry.peak_ctrl_effective[name] = 0.0
            self.telemetry.peak_ctrl_effective_signed[name] = 0.0
            self.telemetry.effort_tracking_error[name] = 0.0

        self._array_rows: dict[str, list] = {
            "time": [], "qpos": [], "qvel": [], "act": [], "ctrl": [],
            "qacc_warmstart": [], "qfrc_applied": [], "mocap_pos": [], "mocap_quat": [],
            "phase_code": [], "phase_index": [], "step_index": [],
            "integration_state": [], "transition_ctrl": [],
            "transition_qfrc_applied": [], "transition_xfrc_applied": [],
            "transition_mocap_pos": [], "transition_mocap_quat": [],
        }
        self.telemetry.trace_header = self._make_trace_header()
        self.telemetry.contact_header = [
            "state_time_s", "force_time_s", "force_stage", "phase", "body_a", "geom_a",
            "body_b", "geom_b", "normal_force_n", "penetration_m",
        ]

    # ------------------------------------------------------------------ watches
    def _watch_body(self, name: str) -> int:
        try:
            return self._body_ids[name]
        except KeyError as exc:
            raise ValueError(
                f"watch body {name!r} is not a named non-world body in the compiled model"
            ) from exc

    def _build_watches(self, checks) -> None:
        """Register the every-step watches declared by the acceptance checks.

        Called once from both the runner and the replay from the hash-verified acceptance,
        so neither path can drift from the other or trust a recorded derived value.
        """
        for check in checks:
            kind = getattr(check, "kind", None)
            name = getattr(check, "name", None)
            window = getattr(check, "window", "end")
            if kind == "relative_pose" and window == "max_over_phase":
                self._pose_watches[name] = {
                    "a": self._watch_body(check.body_a),
                    "b": self._watch_body(check.body_b),
                    "phase": check.phase, "p0": None, "r0": None,
                }
                self.telemetry.watch_evidence[name] = {
                    "kind": kind, "window": window, "phase": check.phase, "samples": 0,
                    "translation_m": 0.0, "translation_time_s": None,
                    "rotation_rad": 0.0, "rotation_time_s": None,
                    "end_translation_m": None, "end_rotation_rad": None,
                    "end_time_s": None,
                }
            elif kind == "relative_translation" and window == "max_over_phase":
                self._translation_watches[name] = {
                    "a": self._watch_body(check.body_a),
                    "b": self._watch_body(check.body_b),
                    "axis": check.axis, "frame": check.frame or "body_a",
                    "from_phase": check.from_phase, "to_phase": check.to_phase,
                    "reference": None,
                }
                self.telemetry.watch_evidence[name] = {
                    "kind": kind, "window": window, "frame": check.frame or "body_a",
                    "axis": check.axis, "from_phase": check.from_phase,
                    "to_phase": check.to_phase, "samples": 0,
                    "min_m": None, "min_time_s": None,
                    "max_m": None, "max_time_s": None,
                    "terminal_m": None, "terminal_time_s": None,
                }
            elif kind == "body_speed" and window == "max_over_phase":
                self._speed_watches.append({
                    "name": name, "body_id": self._watch_body(check.body),
                    "body": check.body, "phase": check.phase,
                })
                self.telemetry.watch_evidence[name] = {
                    "kind": kind, "window": window, "phase": check.phase,
                    "body": check.body, "samples": 0, "speed_m_s": 0.0,
                    "time_s": None, "terminal_speed_m_s": None,
                    "terminal_time_s": None,
                }
            elif kind == "contact_duration":
                # The longest uninterrupted interval above the summed force threshold is a
                # whole-run quantity, independent of the display sampling interval.
                pair = tuple(sorted((self._watch_body(check.body_a),
                                     self._watch_body(check.body_b))))
                self._contact_watches[name] = {
                    "pair": pair, "threshold_n": float(check.force_threshold_n),
                }
                self._contact_state[name] = {
                    "start_s": None, "samples": 0,
                }
                self.telemetry.watch_evidence[name] = {
                    "kind": kind, "window": "end",
                    "threshold_n": float(check.force_threshold_n),
                    "samples": 0, "samples_above": 0, "longest_s": 0.0,
                    "start_s": None, "end_s": None, "run_samples": 0,
                    "peak_force_n": 0.0, "terminal_force_n": None,
                    "terminal_time_s": None,
                }

    def _update_pose_watches(self, data, t: float, stage: str) -> bool:
        """Accumulate the attached-local relative pose and signed translation every state."""
        if not (self._pose_watches or self._translation_watches):
            return True
        phase = self._phase_label()
        for name, watch in self._pose_watches.items():
            a, b = watch["a"], watch["b"]
            try:
                p_rel, r_rel = relative_transform(
                    data.xpos[a], data.xquat[a], data.xpos[b], data.xquat[b])
            except ValueError as exc:
                self.telemetry.invalid.append(
                    {"stage": stage, "time_s": float(t), "reason": str(exc)})
                return False
            if stage == "initial":
                watch["p0"], watch["r0"] = p_rel.copy(), r_rel.copy()
                continue
            if phase != watch["phase"] or watch["p0"] is None:
                continue
            delta_p, angle = pose_delta(watch["p0"], watch["r0"], p_rel, r_rel)
            translation = float(np.linalg.norm(delta_p))
            evidence = self.telemetry.watch_evidence[name]
            evidence["samples"] += 1
            if translation >= evidence["translation_m"]:
                evidence["translation_m"] = translation
                evidence["translation_time_s"] = float(t)
            if angle >= evidence["rotation_rad"]:
                evidence["rotation_rad"] = angle
                evidence["rotation_time_s"] = float(t)
            evidence["end_translation_m"] = translation
            evidence["end_rotation_rad"] = angle
            evidence["end_time_s"] = float(t)

        for name, watch in self._translation_watches.items():
            a, b = watch["a"], watch["b"]
            try:
                p_rel, _ = relative_transform(
                    data.xpos[a], data.xquat[a], data.xpos[b], data.xquat[b])
            except ValueError as exc:
                self.telemetry.invalid.append(
                    {"stage": stage, "time_s": float(t), "reason": str(exc)})
                return False
            if watch["frame"] == "world":
                vector = (np.asarray(data.xpos[b], dtype=np.float64)
                          - np.asarray(data.xpos[a], dtype=np.float64))
            else:
                vector = p_rel
            if watch["from_phase"] == "initial":
                if stage == "initial":
                    watch["reference"] = vector.copy()
            elif stage == "step" and phase == watch["from_phase"]:
                watch["reference"] = vector.copy()
            if (stage != "step" or phase != watch["to_phase"]
                    or watch["reference"] is None):
                continue
            delta = vector - watch["reference"]
            signed = float(delta[_AXIS_INDEX[watch["axis"]]])
            evidence = self.telemetry.watch_evidence[name]
            evidence["samples"] += 1
            if evidence["min_m"] is None or signed < evidence["min_m"]:
                evidence["min_m"] = signed
                evidence["min_time_s"] = float(t)
            if evidence["max_m"] is None or signed > evidence["max_m"]:
                evidence["max_m"] = signed
                evidence["max_time_s"] = float(t)
            evidence["terminal_m"] = signed
            evidence["terminal_time_s"] = float(t)
        return True

    def _update_contact_watches(self, pair_forces: dict, t: float) -> None:
        """Track the longest uninterrupted above-threshold run of the summed pair force.

        A state's run duration is the elapsed simulated time between its first and last
        above-threshold states, so a run that spans N consecutive integration states counts
        ``(N - 1) * dt``. An isolated one-state excursion is 0.0 s and is reported with its
        sample count. A state at or below the threshold ends the run, so an interruption
        can never merge two episodes, and a phase boundary cannot add an extra step.
        """
        for name, watch in self._contact_watches.items():
            force = float(pair_forces.get(watch["pair"], 0.0))
            evidence = self.telemetry.watch_evidence[name]
            state = self._contact_state[name]
            evidence["samples"] += 1
            evidence["terminal_force_n"] = force
            evidence["terminal_time_s"] = float(t)
            if force > evidence["peak_force_n"]:
                evidence["peak_force_n"] = force
            if force > watch["threshold_n"]:
                evidence["samples_above"] += 1
                if state["start_s"] is None:
                    state["start_s"] = float(t)
                state["samples"] += 1
                duration = float(t) - state["start_s"]
                if duration > evidence["longest_s"]:
                    evidence["longest_s"] = duration
                    evidence["start_s"] = state["start_s"]
                    evidence["end_s"] = float(t)
                    evidence["run_samples"] = state["samples"]
            else:
                state["start_s"] = None
                state["samples"] = 0

    # ------------------------------------------------------------------ headers
    def _make_trace_header(self) -> list[str]:
        header = ["state_time_s", "force_time_s", "force_stage", "phase", "step"]
        for name, _, _, coord, vel, force in self.joints:
            header.extend([f"qpos:{name} ({coord})", f"qvel:{name} ({vel})",
                           f"qfrc_passive:{name} ({force})",
                           f"qfrc_constraint:{name} ({force})",
                           f"qfrc_spring:{name} ({force})",
                           f"qfrc_damper:{name} ({force})"])
        for name, _ in self.bodies:
            header.extend([f"body_pos:{name}.x (m)", f"body_pos:{name}.y (m)",
                           f"body_pos:{name}.z (m)", f"body_quat:{name}.w",
                           f"body_quat:{name}.x", f"body_quat:{name}.y",
                           f"body_quat:{name}.z", f"com_pos:{name}.x (m)",
                           f"com_pos:{name}.y (m)", f"com_pos:{name}.z (m)"])
        for name, _, _, _, _ in self.actuators:
            units = self._effort_units.get(name, "")
            header.extend([f"ctrl_requested:{name} ({units} control)",
                           f"ctrl_stored:{name} ({units} control)",
                           f"actuator_force:{name} ({units} motor)",
                           f"qfrc_actuator:{name} ({units})"])
        header.extend(["energy_j", "ncon"])
        return header

    # ------------------------------------------------------------------ phases
    def begin_phase(self, phase: PhaseTelemetry, ctrl_by_actuator: dict[str, float],
                    effort_by_actuator: dict[str, float], command_at=None,
                    force_at=None) -> None:
        """``effort_by_actuator`` is the requested effort after the actuator's own bound.

        The runner clamps to ``ActuatorSpec.max_effort`` here, so a million-unit request is
        expected to transmit exactly the declared bound; telemetry is never rewound to look
        like the unclipped request. ``command_at(step) -> (ctrl, effort)`` supplies the
        per-step command of a ramped phase; ``None`` keeps the constant command.
        ``force_at(step) -> (nbody, 6)`` array supplies the external ``xfrc_applied`` of a
        ``body_force`` phase; ``xfrc_applied`` is zeroed at every phase boundary.
        """
        self._phase = phase
        self._command_at = command_at
        self._force_at = force_at
        if self.data.xfrc_applied.size:
            self.data.xfrc_applied[:] = 0.0
        self._phase_names.append(phase.name)
        if phase.kind == "actuate" and phase.actuator:
            self.telemetry.commanded_actuators.add(phase.actuator)
        self._phase_code = len(self._phase_names)
        self._phase_index = len(self._phase_names) - 1
        self._ctrl_by_actuator = dict(ctrl_by_actuator)
        self._effort_by_actuator = dict(effort_by_actuator)
        phase.start_time_s = float(self.data.time)
        self.telemetry.phases.append(phase)
        if self.event_tracker is not None:
            ctrl_zero = all(abs(float(value)) <= 1e-12
                            for value in ctrl_by_actuator.values())
            self.event_tracker.begin_phase(
                phase.name, phase.kind, phase.start_time_s, ctrl_zero,
                boundary=self._event_boundary_observation(phase))

    def _event_boundary_observation(self, phase: PhaseTelemetry):
        """The coherent pre-step state at a phase boundary, or ``None``.

        This sample only seeds crossing geometry. It is never a crossing sample and never
        release-input evidence, so its control flag is deliberately not derived from the
        previous phase's command.
        """
        if self.event_tracker is None:
            return None
        data = self._observe()
        bodies: dict[str, ObservedBody] = {}
        for body_name, body_id in self.bodies:
            if body_name not in self._event_body_ids:
                continue
            velocity = np.zeros(6, dtype=np.float64)
            self.mujoco.mj_objectVelocity(
                self.model, data, self.mujoco.mjtObj.mjOBJ_BODY,
                body_id, velocity, 0)
            bodies[body_name] = ObservedBody(
                body_id=body_name,
                pos_m=tuple(float(v) for v in data.xpos[body_id]),
                quat_wxyz=tuple(float(v) for v in data.xquat[body_id]),
                com_m=tuple(float(v) for v in data.xipos[body_id]),
                linear_velocity_m_s=tuple(float(v) for v in velocity[3:]),
                mass_kg=float(self.model.body_mass[body_id]),
            )
        return StepObservation(
            time_s=float(data.time), step_index=int(self._step_index),
            phase_name=phase.name, phase_kind=phase.kind, ctrl_zero=True,
            bodies=bodies, contacts=(), ctrl_max_abs=0.0)

    def _observe(self):
        """Evaluate derived quantities at the current state on a private scratch ``MjData``.

        The complete native integration state (``mj_getState`` with the runtime mask,
        including warmstart, user and plugin components where present) is transferred to
        scratch with ``mj_setState`` and forwarded there. This is observational only: the
        live state is never rewritten and the integration sequence is unchanged. A
        non-finite live state cannot be forwarded, so it is returned for diagnostics and the
        live finiteness guard reports it.
        """
        live = self.data
        state = get_native_state(self.mujoco, self.model, live)
        if not np.all(np.isfinite(state)):
            self._observed = live
            return live
        scratch = self.scratch
        set_native_state(self.mujoco, self.model, scratch, state)
        self.mujoco.mj_forward(self.model, scratch)
        self._observed = scratch
        return scratch

    def _snapshot_from(self, data, name: str) -> Snapshot:
        qpos = {j[0]: float(data.qpos[j[2]]) for j in self.joints}
        qvel = {name: float(data.qvel[self._joint_dof(name)]) for name in qpos}
        free = {
            name: {"qpos": [float(v) for v in data.qpos[qadr:qadr + 7]],
                   "qvel": [float(v) for v in data.qvel[dof:dof + 6]]}
            for name, dof, qadr, _ in self.free_joints
        }
        bodies = {}
        for body_name, body_id in self.bodies:
            velocity = np.zeros(6, dtype=np.float64)
            self.mujoco.mj_objectVelocity(
                self.model, data, self.mujoco.mjtObj.mjOBJ_BODY, body_id, velocity, 0)
            bodies[body_name] = {
                "xpos": [float(v) for v in data.xpos[body_id]],
                "xquat": [float(v) for v in data.xquat[body_id]],
                "xipos": [float(v) for v in data.xipos[body_id]],
                "angular_velocity_rad_s": [float(v) for v in velocity[:3]],
                "linear_velocity_m_s": [float(v) for v in velocity[3:]],
            }
        self.telemetry.boundary_rows[name] = max(
            0, len(self._array_rows["time"]) - 1)
        snap = Snapshot(float(data.time), qpos, qvel,
                        state_hash(np.asarray(data.qpos), np.asarray(data.qvel),
                                   np.asarray(data.act), np.asarray([data.time])),
                        free, bodies)
        self.telemetry.boundaries[name] = snap
        return snap

    def snapshot(self, name: str) -> Snapshot:
        return self._snapshot_from(self._observe(), name)

    def _joint_dof(self, name: str) -> int:
        for joint_name, joint_id, _, _, _, _ in self.joints:
            if joint_name == name:
                return int(self.model.jnt_dofadr[joint_id])
        raise KeyError(name)

    def record_initial(self, phase_name: str = "reset") -> bool:
        """Validate and record the reset state before any step.

        Returns ``False`` when the reset state is numerically invalid or raises a solver
        warning; the caller must then take zero steps and report the named initial reason.
        """
        self._phase_names[:] = [phase_name]
        self._phase_code = 1
        live_ok = self._check_live_numerics("initial")
        if not live_ok:
            # The reset state is already invalid; record the failed row and boundary but do
            # not forward or accumulate, and let the caller take zero steps.
            if not self._append_state_row():
                return False
            self._append_trace_row(requested={}, stored={}, force_stage="initial_forward")
            self._snapshot_from(self.data, "initial")
            return False
        observed = self._observe()
        ok = self._accumulate(observed, float(observed.time), stage="initial",
                              warning_data=self.data)
        if not self._append_state_row():
            return False
        self._append_trace_row(requested={}, stored={}, force_stage="initial_forward")
        self.snapshot("initial")
        return ok

    def _check_live_numerics(self, stage: str) -> bool:
        """Inspect integrator outputs before observational forward can replace them.

        A finite scratch acceleration/force does not establish that the live solver output
        was finite. This check only reads live data and never repairs or resets it.
        """
        data = self.data
        for label, array in (
            ("time", np.asarray([data.time])),
            ("state", data.qpos), ("velocity", data.qvel),
            ("acceleration", data.qacc), ("activation", data.act),
            ("control", data.ctrl), ("actuator force", data.actuator_force),
            ("actuation force", data.qfrc_actuator),
            ("passive force", data.qfrc_passive),
            ("constraint force", data.qfrc_constraint),
            ("spring force", data.qfrc_spring), ("damper force", data.qfrc_damper),
            ("applied force", data.qfrc_applied), ("energy", data.energy),
        ):
            if not np.all(np.isfinite(array)):
                self.telemetry.invalid.append({
                    "stage": stage, "time_s": float(data.time),
                    "reason": f"non-finite live {label}",
                })
                return False
        return True

    # ------------------------------------------------------------------ stepping
    def _one_step(self, *, ctrl_vector: np.ndarray, requested: dict[str, float],
                  stored: dict[str, float], qfrc_applied=None, xfrc_applied=None,
                  mocap_pos=None, mocap_quat=None) -> bool:
        """One real ``mj_step`` with explicit transition inputs, then record the state.

        The live finiteness check runs before the scratch observation so a non-finite
        integrator output cannot be hidden by a finite scratch forward. The failed final
        state row is retained.
        """
        data = self.data
        phase = self._phase
        data.ctrl[:] = np.asarray(ctrl_vector, dtype=np.float64)
        if qfrc_applied is not None:
            data.qfrc_applied[:] = np.asarray(qfrc_applied, dtype=np.float64)
        if xfrc_applied is not None and data.xfrc_applied.size:
            data.xfrc_applied[:] = np.asarray(xfrc_applied, dtype=np.float64)
        if mocap_pos is not None and self.model.nmocap:
            data.mocap_pos[:] = np.asarray(mocap_pos, dtype=np.float64)
            if mocap_quat is not None:
                data.mocap_quat[:] = np.asarray(mocap_quat, dtype=np.float64)
        self.mujoco.mj_step(self.model, data)
        self._step_index += 1
        if phase is not None:
            phase.actual_steps += 1
        live_ok = self._check_live_numerics("step")
        if not live_ok:
            self.telemetry.stopped = True
            if phase is not None:
                phase.complete = False
            self._append_state_row()
            return False
        observed = self._observe()
        state_time = float(observed.time)
        if not self._accumulate(observed, state_time, stage="step", warning_data=data):
            self.telemetry.stopped = True
            if phase is not None:
                phase.complete = False
            self._append_state_row()
            return False
        if self._step_index % self.sample_every == 0:
            self._append_trace_row(requested=requested, stored=stored)
        return self._append_state_row()

    def step(self, n: int) -> None:
        data = self.data
        if self._phase is None:
            raise RuntimeError("step() called without begin_phase()")
        for _ in range(n):
            ctrl_vector = np.zeros(self.model.nu, dtype=np.float64)
            requested: dict[str, float] = {}
            stored: dict[str, float] = {}
            if self._command_at is not None:
                self._ctrl_by_actuator, self._effort_by_actuator = self._command_at(
                    self._phase.actual_steps)
            for name, actuator_id, _, _, _ in self.actuators:
                value = self._ctrl_by_actuator.get(name, 0.0)
                ctrl_vector[actuator_id] = value
                requested[name] = value
                stored[name] = value
            xfrc = (None if self._force_at is None
                    else self._force_at(self._phase.actual_steps))
            if not self._one_step(ctrl_vector=ctrl_vector, requested=requested,
                                  stored=stored, xfrc_applied=xfrc):
                return

    def step_with_transition(self, *, ctrl, qfrc_applied=None, xfrc_applied=None,
                             mocap_pos=None, mocap_quat=None,
                             effort_by_actuator=None) -> bool:
        """Replay one step with recorded transition inputs (ctrl/applied/mocap).

        ``effort_by_actuator`` replaces the expected bounded effort for this step (ramps).
        """
        if effort_by_actuator is not None:
            self._effort_by_actuator = dict(effort_by_actuator)
        if self._phase is None:
            raise RuntimeError("step_with_transition() called without begin_phase()")
        ctrl_vector = np.asarray(ctrl, dtype=np.float64)
        requested = {name: float(ctrl_vector[actuator_id])
                     for name, actuator_id, _, _, _ in self.actuators}
        return self._one_step(ctrl_vector=ctrl_vector, requested=requested,
                              stored=dict(requested), qfrc_applied=qfrc_applied,
                              xfrc_applied=xfrc_applied, mocap_pos=mocap_pos,
                              mocap_quat=mocap_quat)

    def _phase_label(self) -> str:
        """The declared phase name, including the reset phase before any step starts."""
        if self._phase is not None:
            return self._phase.name
        return self._phase_names[0] if self._phase_names else "reset"

    def _accumulate(self, observed, state_time: float, *, stage: str = "step",
                    warning_data=None) -> bool:
        """Validate and accumulate one observed state.

        ``observed`` is the scratch ``MjData`` evaluated by :meth:`_observe`, so every value
        (pose, COM, velocity, energy, contact, force) belongs to the same state timestamp.
        ``stage`` labels the origin in every reason: ``initial`` for the reset state,
        ``step`` for a post-integration state.
        """
        data = observed
        mujoco = self.mujoco
        t = state_time
        invalid = self.telemetry.invalid

        def bad(reason: str) -> bool:
            invalid.append({"stage": stage, "time_s": t, "reason": reason})
            return False

        # Warning counters live on the stepped data, not on the scratch forward. Report each
        # warning once, with the state time at which it was first seen.
        for source, sample in (("live", warning_data), ("observation", data)):
            if sample is None:
                continue
            for name, count in warning_counts(mujoco, sample).items():
                key = f"{source}:{name}"
                if count and key not in self._warned:
                    self._warned.add(key)
                    return bad(f"{source} solver warning {name} raised {count} times")
        if not (np.all(np.isfinite(data.qpos)) and np.all(np.isfinite(data.qvel))):
            return bad("non-finite state")
        if not np.all(np.isfinite(data.qacc)):
            return bad("non-finite acceleration")
        if not (np.all(np.isfinite(data.xpos)) and np.all(np.isfinite(data.xquat))
                and np.all(np.isfinite(data.xipos))):
            return bad("non-finite body pose")
        if not np.all(np.isfinite(data.ctrl)):
            return bad("non-finite control")
        for label, array in (
            ("actuation force", data.qfrc_actuator),
            ("passive force", data.qfrc_passive),
            ("constraint force", data.qfrc_constraint),
            ("spring force", data.qfrc_spring),
            ("damper force", data.qfrc_damper),
            ("applied force", data.qfrc_applied),
        ):
            if not np.all(np.isfinite(array)):
                return bad(f"non-finite {label}")

        energy = abs(float(np.sum(data.energy)))
        if not math.isfinite(energy):
            return bad("non-finite energy")
        self.telemetry.peak_energy_j = max(self.telemetry.peak_energy_j, energy)
        for name, joint_id, qadr, coord, _, _ in self.joints:
            dof = int(self.model.jnt_dofadr[joint_id])
            speed = abs(float(data.qvel[dof]))
            self.telemetry.peak_joint_speed[name] = max(
                self.telemetry.peak_joint_speed[name], speed)
            if coord == "m":
                self.telemetry.peak_speed = max(self.telemetry.peak_speed, speed)
            else:
                self.telemetry.peak_angular_speed_rad_s = max(
                    self.telemetry.peak_angular_speed_rad_s, speed)
        for name, dof, qadr, _ in self.free_joints:
            linear = float(np.linalg.norm(data.qvel[dof:dof + 3]))
            angular = float(np.linalg.norm(data.qvel[dof + 3:dof + 6]))
            if not (math.isfinite(linear) and math.isfinite(angular)):
                return bad(f"non-finite free-joint velocity for {name!r}")
            self.telemetry.peak_speed = max(self.telemetry.peak_speed, linear)
            self.telemetry.peak_angular_speed_rad_s = max(
                self.telemetry.peak_angular_speed_rad_s, angular)
        event_bodies: dict[str, ObservedBody] = {}
        event_contacts: list[ObservedContact] = []
        for body_name, body_id in self.bodies:
            velocity = np.zeros(6, dtype=np.float64)
            mujoco.mj_objectVelocity(
                self.model, data, mujoco.mjtObj.mjOBJ_BODY, body_id, velocity, 0)
            linear = float(np.linalg.norm(velocity[3:]))
            angular = float(np.linalg.norm(velocity[:3]))
            if not (math.isfinite(linear) and math.isfinite(angular)):
                return bad(f"non-finite body velocity for {body_name!r}")
            self.telemetry.peak_speed = max(self.telemetry.peak_speed, linear)
            self.telemetry.peak_angular_speed_rad_s = max(
                self.telemetry.peak_angular_speed_rad_s, angular)
            if self.event_tracker is not None and body_name in self._event_body_ids:
                event_bodies[body_name] = ObservedBody(
                    body_id=body_name,
                    pos_m=tuple(float(v) for v in data.xpos[body_id]),
                    quat_wxyz=tuple(float(v) for v in data.xquat[body_id]),
                    com_m=tuple(float(v) for v in data.xipos[body_id]),
                    linear_velocity_m_s=tuple(float(v) for v in velocity[3:]),
                    mass_kg=float(self.model.body_mass[body_id]),
                )
            for watch in self._speed_watches:
                if (watch["body"] != body_name or stage != "step"
                        or self._phase_label() != watch["phase"]):
                    continue
                evidence = self.telemetry.watch_evidence[watch["name"]]
                evidence["samples"] += 1
                if linear >= evidence["speed_m_s"]:
                    evidence["speed_m_s"] = linear
                    evidence["time_s"] = float(t)
                evidence["terminal_speed_m_s"] = linear
                evidence["terminal_time_s"] = float(t)

        if not self._update_pose_watches(data, t, stage):
            return False

        # Actuation telemetry. ``actuator_force`` is the unity-gain motor's limited drive
        # before gearing; the generalized force is ``gear * actuator_force``.
        for name, actuator_id, dof, gear, units in self.actuators:
            force = float(data.actuator_force[actuator_id])
            stored = float(data.ctrl[actuator_id])
            effort = float(data.qfrc_actuator[dof])
            if not (math.isfinite(force) and math.isfinite(stored) and math.isfinite(effort)):
                return bad(f"non-finite actuator telemetry for {name!r}")
            if abs(stored) >= self.telemetry.peak_ctrl_stored[name]:
                self.telemetry.peak_ctrl_stored[name] = abs(stored)
                self.telemetry.peak_ctrl_stored_signed[name] = stored
            if abs(force) >= self.telemetry.peak_ctrl_effective[name]:
                self.telemetry.peak_ctrl_effective[name] = abs(force)
                self.telemetry.peak_ctrl_effective_signed[name] = force
            if abs(effort) >= self.telemetry.peak_effort[name]:
                self.telemetry.peak_effort[name] = abs(effort)
                self.telemetry.peak_effort_signed[name] = effort
            expected = self._effort_by_actuator.get(name)
            if expected is not None:
                tolerance = 1.0e-6 * max(1.0, abs(expected))
                error = abs(effort - expected)
                self.telemetry.effort_tracking_error[name] = max(
                    self.telemetry.effort_tracking_error[name], error)
                if error > tolerance:
                    return bad(
                        f"actuator {name!r} generalized effort {effort:.9g} does not match "
                        f"the requested bounded effort {expected:.9g} (gear {gear:.9g})")
            if self._phase is not None:
                self._phase.ctrl_effective_peak = max(
                    self._phase.ctrl_effective_peak or 0.0, abs(force))

        # Contacts at the observed state: named pairs, normal force and penetration. The
        # per-step maxima are what the acceptance predicates use; the sparse rows are display
        # evidence only.
        pair_forces: dict[tuple[int, int], float] = {}
        for i in range(int(data.ncon)):
            contact = data.contact[i]
            geom1, geom2 = int(contact.geom1), int(contact.geom2)
            body1 = int(self.model.geom_bodyid[geom1])
            body2 = int(self.model.geom_bodyid[geom2])
            body_a = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_BODY, body1) or "world"
            body_b = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_BODY, body2) or "world"
            geom_a = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, geom1) or f"geom{geom1}"
            geom_b = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, geom2) or f"geom{geom2}"
            penetration = max(0.0, -float(contact.dist))
            normal = np.zeros(6, dtype=np.float64)
            mujoco.mj_contactForce(self.model, data, i, normal)
            normal_force = abs(float(normal[0]))
            if not (math.isfinite(penetration) and math.isfinite(normal_force)):
                return bad(f"non-finite contact telemetry on {body_a}/{body_b}")
            pair = (min(body1, body2), max(body1, body2))
            pair_forces[pair] = pair_forces.get(pair, 0.0) + normal_force
            if (self.event_tracker is not None
                    and (body_a in self._event_body_ids
                         or body_b in self._event_body_ids)):
                frame = np.asarray(contact.frame, dtype=np.float64).reshape(3, 3)
                event_contacts.append(ObservedContact(
                    body_a=body_a, body_b=body_b,
                    position_m=tuple(float(v) for v in contact.pos),
                    normal_force_n=normal_force,
                    normal_world=tuple(float(v) for v in frame[0]),
                ))
            key = (body_a, geom_a, body_b, geom_b)
            values = self.telemetry.contact_pairs.setdefault(
                key, {"max_normal_force_n": 0.0, "max_penetration_m": 0.0, "samples": 0})
            values["samples"] += 1
            values["max_normal_force_n"] = max(values["max_normal_force_n"], normal_force)
            values["max_penetration_m"] = max(values["max_penetration_m"], penetration)
            self.telemetry.peak_contact_force_n = max(
                self.telemetry.peak_contact_force_n, normal_force)
            self.telemetry.peak_penetration_m = max(
                self.telemetry.peak_penetration_m, penetration)
            if (self.max_contact_rows is not None
                    and len(self.telemetry.contact_rows) >= self.max_contact_rows):
                invalid.append({"stage": stage, "time_s": t,
                                "reason": "contact trace row budget exceeded"})
                return False
            if self._step_index % self.sample_every == 0:
                self.telemetry.contact_rows.append([
                    state_time, state_time,
                    "initial_forward" if stage == "initial" else "post_step_forward",
                    self._phase_label(),
                    body_a, geom_a, body_b, geom_b, normal_force, penetration,
                ])

        self._update_contact_watches(pair_forces, t)

        if self.event_tracker is not None and stage == "step" and self._phase is not None:
            ctrl_zero = all(abs(float(v)) <= 1e-12 for v in data.ctrl)
            ctrl_max_abs = (float(np.max(np.abs(data.ctrl)))
                            if data.ctrl.size else 0.0)
            self.event_tracker.observe(StepObservation(
                time_s=float(t), step_index=int(self._step_index),
                phase_name=self._phase.name, phase_kind=self._phase.kind,
                ctrl_zero=ctrl_zero, bodies=event_bodies,
                contacts=tuple(event_contacts), ctrl_max_abs=ctrl_max_abs))

        if stage == "initial":
            # Seed the initial observations explicitly so a later smaller post-step value
            # cannot hide an initial violation, and so the reported reason names the reset
            # state rather than a step.
            self.telemetry.initial_energy_j = self.telemetry.peak_energy_j
            self.telemetry.initial_speed_m_s = self.telemetry.peak_speed
            self.telemetry.initial_angular_speed_rad_s = self.telemetry.peak_angular_speed_rad_s
            self.telemetry.initial_penetration_m = self.telemetry.peak_penetration_m
            self.telemetry.initial_contact_force_n = self.telemetry.peak_contact_force_n
        return True

    # ------------------------------------------------------------------ rows
    def _append_trace_row(self, *, requested: dict[str, float],
                          stored: dict[str, float],
                          force_stage: str = "post_step_forward") -> None:
        data = self._observed if self._observed is not None else self._observe()
        state_time = float(data.time)
        # Forces are evaluated at the recorded state time by the observational forward, so
        # state_time and force_time are the same number; the stage column records how they
        # were obtained. RK4's intermediate stages are not sampled.
        force_time = state_time
        row: list = [state_time, force_time, force_stage,
                     self._phase_label(), self._step_index]
        for name, joint_id, qadr, _, _, _ in self.joints:
            dof = int(self.model.jnt_dofadr[joint_id])
            row.extend([
                float(data.qpos[qadr]), float(data.qvel[dof]),
                float(data.qfrc_passive[dof]), float(data.qfrc_constraint[dof]),
                float(data.qfrc_spring[dof]), float(data.qfrc_damper[dof]),
            ])
        for _, body_id in self.bodies:
            row.extend([
                float(data.xpos[body_id][0]), float(data.xpos[body_id][1]),
                float(data.xpos[body_id][2]),
                float(data.xquat[body_id][0]), float(data.xquat[body_id][1]),
                float(data.xquat[body_id][2]), float(data.xquat[body_id][3]),
                float(data.xipos[body_id][0]), float(data.xipos[body_id][1]),
                float(data.xipos[body_id][2]),
            ])
        for name, actuator_id, dof, _, _ in self.actuators:
            row.extend([
                float(requested.get(name, 0.0)),
                # ``ctrl_stored`` is the actual control read from the stepped state; a
                # deliberate execution fault can differ from the commanded value.
                float(data.ctrl[actuator_id]),
                float(data.actuator_force[actuator_id]), float(data.qfrc_actuator[dof]),
            ])
        row.extend([abs(float(np.sum(data.energy))), int(data.ncon)])
        self.telemetry.trace_rows.append(row)

    def _append_state_row(self) -> bool:
        data = self.data
        rows = self._array_rows
        rows_now = len(rows["time"])
        if self.max_state_rows is not None and rows_now >= self.max_state_rows:
            self.telemetry.invalid.append({
                "stage": "state", "time_s": float(data.time),
                "reason": f"state archive row budget {self.max_state_rows} exceeded"})
            self.telemetry.stopped = True
            return False
        if self.max_state_bytes is not None:
            extra = (8 * int(self.model.nu) + 8 * int(self.model.nv)
                     + 8 * 6 * int(self.model.nbody) if data.xfrc_applied.size else 0)
            estimate = state_bytes_estimate(self.layout, rows_now + 1, extra_per_row=extra)
            if estimate > self.max_state_bytes:
                self.telemetry.invalid.append({
                    "stage": "state", "time_s": float(data.time),
                    "reason": f"state archive byte budget {self.max_state_bytes} exceeded"})
                self.telemetry.stopped = True
                return False
        rows["time"].append(float(data.time))
        rows["qpos"].append(np.array(data.qpos, dtype=np.float64, copy=True))
        rows["qvel"].append(np.array(data.qvel, dtype=np.float64, copy=True))
        rows["act"].append(np.array(data.act, dtype=np.float64, copy=True))
        rows["ctrl"].append(np.array(data.ctrl, dtype=np.float64, copy=True))
        rows["qacc_warmstart"].append(
            np.array(data.qacc_warmstart, dtype=np.float64, copy=True))
        rows["qfrc_applied"].append(
            np.array(data.qfrc_applied, dtype=np.float64, copy=True))
        rows["mocap_pos"].append(np.array(data.mocap_pos, dtype=np.float64, copy=True))
        rows["mocap_quat"].append(np.array(data.mocap_quat, dtype=np.float64, copy=True))
        rows["phase_code"].append(self._phase_code)
        rows["phase_index"].append(self._phase_index)
        rows["step_index"].append(self._step_index)
        rows["integration_state"].append(get_native_state(self.mujoco, self.model, data))
        rows["transition_ctrl"].append(np.array(data.ctrl, dtype=np.float64, copy=True))
        rows["transition_qfrc_applied"].append(
            np.array(data.qfrc_applied, dtype=np.float64, copy=True))
        if data.xfrc_applied.size:
            rows["transition_xfrc_applied"].append(
                np.array(data.xfrc_applied, dtype=np.float64, copy=True))
        if self.model.nmocap:
            rows["transition_mocap_pos"].append(
                np.array(data.mocap_pos, dtype=np.float64, copy=True))
            rows["transition_mocap_quat"].append(
                np.array(data.mocap_quat, dtype=np.float64, copy=True))
        return True

    def end_phase(self) -> None:
        phase = self._phase
        if phase is None:
            return
        phase.end_time_s = float(self.data.time)
        if phase.start_time_s is not None:
            phase.actual_duration_s = phase.end_time_s - phase.start_time_s
        if self.event_tracker is not None:
            self.event_tracker.end_phase(
                phase.name, complete=bool(phase.complete),
                end_time_s=phase.end_time_s, stopped=self.telemetry.stopped)
        self.snapshot(phase.name)
        self._phase = None

    def finish(self) -> None:
        self.telemetry.warnings = warning_counts(self.mujoco, self.data)
        if self.telemetry.stopped:
            self.telemetry.invalid.append({
                "stage": "step", "time_s": float(self.data.time),
                "reason": "stepping stopped at the first numerical invalidity",
            })
        if self.event_tracker is not None:
            self.telemetry.event_results = self.event_tracker.finish(
                stopped=self.telemetry.stopped, final_time_s=float(self.data.time))

    def freeze_state(self) -> None:
        rows = self._array_rows
        telemetry = self.telemetry
        if rows["time"]:
            telemetry.state = {
                "time": np.asarray(rows["time"], dtype=np.float64),
                "qpos": np.stack(rows["qpos"]),
                "qvel": np.stack(rows["qvel"]),
                "act": np.stack(rows["act"]),
                "ctrl": np.stack(rows["ctrl"]),
                "qacc_warmstart": np.stack(rows["qacc_warmstart"]),
                "qfrc_applied": np.stack(rows["qfrc_applied"]),
                "mocap_pos": np.stack(rows["mocap_pos"]),
                "mocap_quat": np.stack(rows["mocap_quat"]),
                "phase_code": np.asarray(rows["phase_code"], dtype=np.int64),
                "phase_index": np.asarray(rows["phase_index"], dtype=np.int64),
                "step_index": np.asarray(rows["step_index"], dtype=np.int64),
                "integration_state": np.stack(rows["integration_state"]),
                "transition_ctrl": np.stack(rows["transition_ctrl"]),
                "transition_qfrc_applied": np.stack(rows["transition_qfrc_applied"]),
            }
            if rows["transition_xfrc_applied"]:
                telemetry.state["transition_xfrc_applied"] = np.stack(
                    rows["transition_xfrc_applied"])
            if rows["transition_mocap_pos"]:
                telemetry.state["transition_mocap_pos"] = np.stack(
                    rows["transition_mocap_pos"])
                telemetry.state["transition_mocap_quat"] = np.stack(
                    rows["transition_mocap_quat"])
        else:
            telemetry.state = {
                "time": np.zeros(0, dtype=np.float64),
                "qpos": np.zeros((0, self.model.nq), dtype=np.float64),
                "qvel": np.zeros((0, self.model.nv), dtype=np.float64),
                "act": np.zeros((0, self.model.na), dtype=np.float64),
                "ctrl": np.zeros((0, self.model.nu), dtype=np.float64),
                "qacc_warmstart": np.zeros((0, self.model.nv), dtype=np.float64),
                "qfrc_applied": np.zeros((0, self.model.nv), dtype=np.float64),
                "mocap_pos": np.zeros((0, self.model.nmocap, 3), dtype=np.float64),
                "mocap_quat": np.zeros((0, self.model.nmocap, 4), dtype=np.float64),
                "phase_code": np.zeros(0, dtype=np.int64),
                "phase_index": np.zeros(0, dtype=np.int64),
                "step_index": np.zeros(0, dtype=np.int64),
                "integration_state": np.zeros((0, self.layout["size"]), dtype=np.float64),
                "transition_ctrl": np.zeros((0, self.model.nu), dtype=np.float64),
                "transition_qfrc_applied": np.zeros((0, self.model.nv), dtype=np.float64),
            }
            telemetry.state["transition_xfrc_applied"] = np.zeros(
                (0, self.model.nbody, 6), dtype=np.float64)
            if self.model.nmocap:
                telemetry.state["transition_mocap_pos"] = np.zeros(
                    (0, self.model.nmocap, 3), dtype=np.float64)
                telemetry.state["transition_mocap_quat"] = np.zeros(
                    (0, self.model.nmocap, 4), dtype=np.float64)
        telemetry.state["phase_names"] = np.asarray(self._phase_names, dtype=str)
        telemetry.state["joint_names"] = np.asarray([j[0] for j in self.joints], dtype=str)
        telemetry.state["body_names"] = np.asarray([b[0] for b in self.bodies], dtype=str)
        telemetry.state["actuator_names"] = np.asarray(
            [a[0] for a in self.actuators], dtype=str)
        telemetry.state["timestep_s"] = np.asarray(float(self.dt))
        telemetry.state["integration_mask"] = np.asarray(int(self.layout["mask"]))
        telemetry.state["integration_size"] = np.asarray(int(self.layout["size"]))


def write_trace_csv(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for row in rows:
            writer.writerow([f"{v:.12g}" if isinstance(v, float) else v for v in row])


def write_contacts_csv(path: Path, header: list[str], rows: list[list]) -> None:
    write_trace_csv(path, header, rows)


def write_state_archive(path: Path, state: dict[str, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        np.savez_compressed(fh, **state)
