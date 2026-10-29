"""M3 evidence runs: slider statics, dynamics, a stop, negatives, and the hinge oscillator.

Every trial records what actually entered the simulation and what actually came out:

* requested control (``ctrl_requested``), the **raw stored** control (``ctrl_stored``;
  MuJoCo does not rewrite ``data.ctrl`` when it clips), and the effective/applied signal
  (``ctrl_effective``, the limited force of cadkit's unity-gain motor before gearing),
* ``actuator_force`` and the generalized ``qfrc_actuator`` it transmits,
* ``qfrc_spring``, ``qfrc_damper``, ``qfrc_constraint``,
* the joint coordinate and velocity, read through ``jnt_qposadr`` / ``jnt_dofadr``,
* the input-release instant, so a return can be measured from a named time.

Nothing writes ``qpos`` after the declared initial state: motion comes from the bounded input,
the declared spring, damping, friction and the declared stop. A trial whose numerics are
invalid is ``INCONCLUSIVE`` and can never be ``PASS``.
"""
from __future__ import annotations

import csv
import json
import math
import platform
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import require_mujoco
from .mechanics import (
    HINGE_AMP_RAD,
    HINGE_K_NM_PER_RAD,
    SLIDER_DAMPING_RATIO,
    SLIDER_FORCE_N,
    SLIDER_FRICTIONLOSS,
    SLIDER_K_N_PER_M,
    SLIDER_KG,
    SLIDER_PRELOAD_M,
    SLIDER_RANGE_M,
    STOP_DAMPRATIO,
    STOP_DRIVE_N,
    STOP_PEAK_PENETRATION_M,
    STOP_RANGE_M,
    STOP_STEADY_PENETRATION_M,
    STOP_TIMECONST_S,
    analytic_hinge_inertia_kg_m2,
    analytic_period_s,
    analytic_slider_deflection,
    hinge_cad_inertia_kg_m2,
    hinge_oscillator_spec,
    slider_analytic_stiffness_damping,
    slider_damped_spec,
    hinge_damping_nm_s_per_rad,
    slider_friction_band,
    slider_friction_spec,
    slider_frictionless_spec,
    slider_period_s,
    slider_release_residual_bound,
    slider_stop_spec,
    stop_penetration_estimate_m,
)
from .scene import export_scene

#: Warning counters, by name, from the installed enum. The sentinel is excluded.
WARNING_NAMES = (
    "mjWARN_INERTIA", "mjWARN_CONTACTFULL", "mjWARN_CNSTRFULL", "mjWARN_BADQPOS",
    "mjWARN_BADQVEL", "mjWARN_BADQACC", "mjWARN_BADCTRL",
)

#: Phase durations, s. The settle time follows from the declared damping: 4τ with
#: ζ=0.7 and ω=√(k/m)=14.14 rad/s is ≈ 0.40 s, so 0.60 s is a real settle, not a guess.
#: Push duration, s. The static band is a *statics* prediction, so the sample must be settled:
#: the transient decays as e^(-zeta*omega*t) from the free deflection, and at 0.60 s its
#: amplitude is 0.08 mm — twelve times under the 1.0 mm band half-width. A 0.30 s hold leaves
#: 1.5 mm of transient, larger than the band, so the check would pass only by phase luck.
PUSH_S = 0.60
RELEASE_S = 0.60
STOP_HOLD_S = 1.00
STOP_RELEASE_S = 0.50
HINGE_WINDOW_S = 1.20
#: Telemetry sampling interval, s.
SAMPLE_S = 0.002
#: Step budget for any single trial.
MAX_STEPS = 200_000

#: Acceptance thresholds. Every one is derived in the packet, not fitted to an output.
DEFLECTION_RTOL = 0.02          # F/k within 2%
SLIDER_PERIOD_RTOL = 0.05       # 2*pi*sqrt(m/k) within 5%
HINGE_PERIOD_RTOL = 0.05        # 2*pi*sqrt(I/k) within 5%
RETURN_TOL_M = 0.1e-3           # return to home within 0.1 mm
SETTLED_SPEED_M_S = 0.02        # "at rest" for a return check
#: Convergence between base and half timestep.
CONVERGENCE_DEFLECTION_M = 0.1e-3
CONVERGENCE_PENETRATION_M = 0.1e-3
CONVERGENCE_PERIOD_RTOL = 0.01

#: Guard bounds derived from the fixtures (see the module docstring of ``mechanics``).
#: Peak speed for a released oscillator is A*omega with A=F/k and omega=sqrt(k/m).
SLIDER_VMAX_M_S = 2.0 * (SLIDER_FORCE_N / SLIDER_K_N_PER_M) * math.sqrt(
    SLIDER_K_N_PER_M / SLIDER_KG)
#: Total mechanical energy is bounded by the initial spring energy 0.5*k*A^2, with margin
#: for the drive doing work while it is applied.
SLIDER_EMAX_J = 4.0 * 0.5 * SLIDER_K_N_PER_M * (SLIDER_FORCE_N / SLIDER_K_N_PER_M) ** 2
#: Hinge peak speed is A*omega with omega=sqrt(k/I); the bound is twice that, so it catches a
#: gross blow-up without rejecting a physically correct release.
HINGE_VMAX_RAD_S = 2.0 * HINGE_AMP_RAD * math.sqrt(
    HINGE_K_NM_PER_RAD / analytic_hinge_inertia_kg_m2())
#: Hinge energy bound: the released oscillator's total energy is 0.5*k*A^2, and the bound is
#: twice that for the same reason as the speed bound.
HINGE_EMAX_J = 2.0 * 0.5 * HINGE_K_NM_PER_RAD * HINGE_AMP_RAD ** 2


def _warnings(mujoco, data) -> dict[str, int]:
    return {n.removeprefix("mjWARN_").lower():
            int(data.warning[int(getattr(mujoco.mjtWarning, n))].number)
            for n in WARNING_NAMES}


def _preflight(timestep_s: float, total_s: float) -> int:
    """Validate the budget **before** any stepping, so a bad run cannot burn time first."""
    if not (math.isfinite(timestep_s) and timestep_s > 0.0):
        raise ValueError(f"timestep_s must be finite and positive, got {timestep_s!r}")
    if not (math.isfinite(total_s) and total_s > 0.0):
        raise ValueError(f"total duration must be finite and positive, got {total_s!r}")
    n = int(round(total_s / timestep_s))
    if n > MAX_STEPS:
        raise ValueError(f"{n} steps exceeds the {MAX_STEPS} budget")
    return n


#: MuJoCo's refsafe safety floor is two timesteps (solver parameters documentation):
#: when ``mjDSBL_REFSAFE`` is clear, the *effective* constraint time constant is
#: ``max(solref[0], 2*dt)``. A declared compliance below that floor is silently softened at
#: run time, so the same stored ``solreflimit`` can mean different physics at different steps.
REFSAFE_DT_FLOOR = 2.0


def refsafe_enabled(mujoco, model) -> bool:
    """Whether MuJoCo will apply the two-timestep refsafe floor for this model."""
    bit = int(mujoco.mjtDisableBit.mjDSBL_REFSAFE)
    return not (int(model.opt.disableflags) & bit)


def effective_timeconst(mujoco, model, stored: float) -> float:
    """The time constant actually used at run time, after the refsafe floor.

    This is the value the solver uses, not the value stored in the model. Reporting both is
    what makes a base/half comparison honest: equal stored ``solref`` does not imply equal
    effective compliance when the two runs have different steps.
    """
    if not refsafe_enabled(mujoco, model):
        return float(stored)
    return max(float(stored), REFSAFE_DT_FLOOR * float(model.opt.timestep))


def check_timeconst_resolvable(mujoco, model, declared: float, what: str) -> dict:
    """Reject a run whose declared compliance the chosen step cannot resolve.

    Called **before any stepping**. Disabling refsafe, or quietly raising the stored value,
    would change the declared physical compliance to make a test pass; refusing the step
    instead keeps the declared constant authoritative and makes the incompatibility explicit.
    """
    dt = float(model.opt.timestep)
    effective = effective_timeconst(mujoco, model, declared)
    info = {
        "declared_timeconst_s": float(declared),
        "stored_timeconst_s": float(declared),
        "effective_timeconst_s": effective,
        "refsafe_enabled": refsafe_enabled(mujoco, model),
        "refsafe_floor_s": REFSAFE_DT_FLOOR * dt,
        "timestep_s": dt,
        "resolved": True,
    }
    if effective > declared * (1.0 + 1e-12):
        info["resolved"] = False
        raise ValueError(
            f"{what}: declared time constant {declared!r} s is below MuJoCo's refsafe floor "
            f"of 2*dt = {REFSAFE_DT_FLOOR * dt!r} s at timestep {dt!r} s. The effective "
            f"compliance would silently become {effective!r} s, so this step cannot test the "
            f"declared value. Use a step of at most {declared / REFSAFE_DT_FLOOR!r} s, or "
            f"declare a compliance the step can resolve. Lowering the stored constant, or "
            f"disabling refsafe, is not an acceptable fix: both change the physical model.")
    return info


def _compile(spec, outdir: Path, requested_dt: float, *, declared_timeconst: float | None = None,
             what: str = "limit") -> tuple:
    export = export_scene(spec, Path(outdir))
    mujoco = require_mujoco()
    model = mujoco.MjModel.from_xml_path(str(export.scene_xml))
    dt = float(model.opt.timestep)
    if abs(dt - requested_dt) > 1e-12 * max(dt, requested_dt):
        raise ValueError(f"requested timestep {requested_dt!r} but compiled {dt!r}")
    # Refuse an unresolvable compliance before a single step is taken.
    if declared_timeconst is not None:
        check_timeconst_resolvable(mujoco, model, declared_timeconst, what)
    return mujoco, model, mujoco.MjData(model), export


@dataclass
class Trial:
    name: str
    valid: bool
    invalid_reasons: list[str]
    metrics: dict[str, float]
    checks: list[dict]
    warnings: dict[str, int]
    solver_dt_s: float
    compiled: dict = field(default_factory=dict)
    trace: list[tuple] = field(default_factory=list)
    trace_header: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "valid": self.valid,
            "invalid_reasons": list(self.invalid_reasons),
            # None rather than NaN/inf: the artifact must be strict JSON.
            "metrics": {k: (float(v) if math.isfinite(v) else None)
                        for k, v in self.metrics.items()},
            "checks": list(self.checks),
            "warnings": dict(self.warnings),
            "solver_dt_s": self.solver_dt_s,
            "compiled": dict(self.compiled),
            "trace_rows": len(self.trace),
        }


def _check(name: str, ok: bool, detail: str, value: float | None = None) -> dict:
    """A named verdict. Non-finite values become ``None`` so the artifact stays strict JSON."""
    if value is not None and not math.isfinite(value):
        value = None
    return {"name": name, "ok": bool(ok), "detail": detail, "value": value}


#: Telemetry columns. Requested and actual control are separate columns on purpose: a
#: saturated input is not the same thing as the input the caller asked for.
#: Three distinct control quantities, because they are not the same number and conflating
#: them makes the evidence false:
#:
#: ``ctrl_requested``  what the caller asked for.
#: ``ctrl_stored``     what was written into ``data.ctrl`` (the raw stored control). MuJoCo
#:                     does **not** rewrite this when it clips, so it still reads 1e6 for an
#:                     over-request.
#: ``ctrl_effective``  the applied drive after limiting for cadkit's unity-gain motor:
#:                     ``actuator_force``. The gear acts afterwards, at the joint.
#: ``qfrc_actuator``   the generalized force that reached the joint: ``gear * actuator_force``.
TRACE_HEADER = [
    "time_s", "phase", "qpos", "qvel", "ctrl_requested", "ctrl_stored", "ctrl_effective",
    "actuator_force", "qfrc_actuator", "qfrc_spring", "qfrc_damper", "qfrc_constraint",
    "energy_j", "contacts",
]


#: Column of ``qfrc_spring`` in the trace, derived rather than hard-coded so a header change
#: cannot make a check silently read a neighbouring column.
SPRING_COL = TRACE_HEADER.index("qfrc_spring")


class _Recorder:
    """Steps a model while recording telemetry and enforcing the validity guards."""

    def __init__(self, mujoco, model, data, joint_name: str, actuator_name: str | None,
                 mass_kg: float, *, vmax: float, emax: float,
                 inertia_kg_m2: float | None = None):
        self.mujoco = mujoco
        self.model = model
        self.data = data
        self.mass_kg = mass_kg
        #: Generalized inertia of this coordinate: linear mass for a slide, effective
        #: rotational inertia about the axis for a hinge. Defaults to the linear mass.
        self.inertia_kg_m2 = mass_kg if inertia_kg_m2 is None else float(inertia_kg_m2)
        self.vmax = vmax
        self.emax = emax
        self.joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
        if self.joint < 0:
            raise ValueError(f"joint {joint_name!r} not found in the compiled model")
        self.qadr = int(model.jnt_qposadr[self.joint])
        self.dofadr = int(model.jnt_dofadr[self.joint])
        # Indexing is checked, not assumed: qpos and qvel have different addresses whenever
        # any other joint precedes this one, and mixing them silently reads the wrong value.
        if not (0 <= self.qadr < model.nq):
            raise ValueError(f"jnt_qposadr {self.qadr} outside nq={model.nq}")
        if not (0 <= self.dofadr < model.nv):
            raise ValueError(f"jnt_dofadr {self.dofadr} outside nv={model.nv}")
        self.actuator = (mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, actuator_name)
                         if actuator_name else -1)
        self.trace: list[tuple] = []
        self.invalid: list[str] = []
        self.peak_qpos = -math.inf
        self.min_qpos = math.inf
        self.peak_speed = 0.0
        self.peak_energy = 0.0
        self.peak_constraint = 0.0
        self.peak_spring = 0.0
        self.peak_effective_ctrl = 0.0
        self.peak_requested_ctrl = 0.0
        self.sample_every = max(1, int(round(SAMPLE_S / float(model.opt.timestep))))
        self._phase = "init"
        #: Per-step sums, keyed by phase name. The 2 ms telemetry grid aliases a 0.44 s
        #: oscillation when a whole period is averaged from sampled rows; these accumulators
        #: cover every integration step, so a phase mean is unbiased by the sampling rate.
        self.sums: dict[str, dict[str, float]] = {}

    def effective_ctrl(self, actuator_force: float) -> float:
        """Effective drive of the unity-gain motors emitted by cadkit.

        For a ``motor`` actuator ``actuator_force`` is the motor force after the solver's own
        clamping, and the generalized force is ``gear * actuator_force``. Motor force equals
        effective drive here; dividing it by gear would apply the transmission twice and
        reverse the control sign for negative gears. This is not a general inverse for
        arbitrary gain/bias/activation actuators.
        """
        if self.actuator < 0:
            return 0.0
        return float(actuator_force)

    def phase(self, name: str) -> None:
        self._phase = name

    def phase_mean(self, name: str, field: str) -> float:
        """Mean of ``field`` over every step taken in phase ``name``. NaN if no steps."""
        bucket = self.sums.get(name)
        if not bucket or not bucket.get("n"):
            return float("nan")
        return bucket.get(field, 0.0) / bucket["n"]

    def _accumulate(self, q: float, v: float) -> None:
        bucket = self.sums.setdefault(self._phase, {"n": 0.0, "q": 0.0, "v_last": 0.0,
                                                    "vabs_last": 0.0, "vabs_max": 0.0})
        bucket["n"] += 1.0
        bucket["q"] += q
        bucket["v_last"] = v
        bucket["vabs_last"] = abs(v)
        bucket["vabs_max"] = max(bucket["vabs_max"], abs(v))

    def settled_speed(self, name: str) -> float:
        """|velocity| at the last step of phase ``name``. NaN if the phase never ran.

        This is the evidence that a static comparison was made on a settled carriage: the
        position is only a static deflection if the speed there is negligible.
        """
        bucket = self.sums.get(name)
        if not bucket or not bucket.get("n"):
            return float("nan")
        return float(bucket["vabs_last"])

    def energy(self) -> float:
        """Mechanical energy of the generalized coordinate about its declared reference.

        ``inertia_kg_m2`` is the generalized inertia of this coordinate: the body mass for a
        slide joint, or the effective inertia about the hinge axis from ``mj_fullM`` for a
        hinge. Using a linear mass for a rotational joint would compute the wrong quantity, so
        the caller passes it explicitly.

        ``0.5*k*q**2`` is only the spring potential when the reference is zero. A preloaded
        spring stores ``0.5*k*(q - springref)**2``; using the raw coordinate overstated the
        friction fixture's energy by 123% and would eventually trip a spurious bound.
        """
        v = float(self.data.qvel[self.dofadr])
        q = float(self.data.qpos[self.qadr])
        ref = float(self.model.qpos_spring[self.qadr])
        kinetic = 0.5 * self.inertia_kg_m2 * v * v
        spring = 0.5 * float(self.model.jnt_stiffness[self.joint]) * (q - ref) ** 2
        return kinetic + spring

    def step(self, n: int, ctrl: float) -> None:
        d = self.data
        for i in range(n):
            requested = ctrl
            self.peak_requested_ctrl = max(self.peak_requested_ctrl, abs(ctrl))
            if self.actuator >= 0:
                d.ctrl[self.actuator] = ctrl
            self.mujoco.mj_step(self.model, d)
            q = float(d.qpos[self.qadr])
            v = float(d.qvel[self.dofadr])
            e = self.energy()
            self.peak_qpos = max(self.peak_qpos, q)
            self.min_qpos = min(self.min_qpos, q)
            self.peak_speed = max(self.peak_speed, abs(v))
            self.peak_energy = max(self.peak_energy, e)
            force = float(d.actuator_force[self.actuator]) if self.actuator >= 0 else 0.0
            actuation = float(d.qfrc_actuator[self.dofadr])
            self.peak_constraint = max(self.peak_constraint, abs(float(d.qfrc_constraint[self.dofadr])))
            self.peak_spring = max(self.peak_spring, abs(float(d.qfrc_spring[self.dofadr])))
            self._accumulate(q, v)
            if i % self.sample_every == 0:
                # ``ctrl_stored`` is the raw value in data.ctrl and is deliberately NOT
                # rewritten to look clamped: MuJoCo clips internally, so rewriting it would
                # fabricate evidence. The applied signal is recovered from the force the
                # actuator actually produced.
                stored = float(d.ctrl[self.actuator]) if self.actuator >= 0 else 0.0
                self.trace.append((
                    float(d.time), self._phase, q, v, requested, stored,
                    self.effective_ctrl(force), force, actuation,
                    float(d.qfrc_spring[self.dofadr]), float(d.qfrc_damper[self.dofadr]),
                    float(d.qfrc_constraint[self.dofadr]), e, int(d.ncon),
                ))
                self.peak_effective_ctrl = max(self.peak_effective_ctrl,
                                               abs(self.effective_ctrl(force)))
            # Finiteness of every quantity the trial reports on. Acceleration and the input
            # are included because a NaN qacc or a NaN control can leave qpos/qvel finite for
            # one step while the run is already meaningless.
            if not (np.all(np.isfinite(d.qpos)) and np.all(np.isfinite(d.qvel))):
                self.invalid.append(f"non-finite state at t={float(d.time):.6g} s")
                return
            if not np.all(np.isfinite(d.qacc)):
                self.invalid.append(f"non-finite acceleration at t={float(d.time):.6g} s")
                return
            if not np.all(np.isfinite(d.qfrc_actuator)):
                self.invalid.append(
                    f"non-finite actuation force at t={float(d.time):.6g} s")
                return
            if not (math.isfinite(e) and math.isfinite(force)
                    and np.all(np.isfinite(d.qfrc_spring))
                    and np.all(np.isfinite(d.qfrc_damper))
                    and np.all(np.isfinite(d.qfrc_constraint))):
                self.invalid.append(f"non-finite force or energy at t={float(d.time):.6g} s")
                return
            if not (math.isfinite(ctrl) and math.isfinite(float(d.ctrl[self.actuator]))
                    if self.actuator >= 0 else math.isfinite(ctrl)):
                self.invalid.append(f"non-finite control input at t={float(d.time):.6g} s")
                return
            _ = force, actuation  # recorded in the trace; peaks are per-trial metrics
            if abs(v) > self.vmax:
                self.invalid.append(
                    f"speed {abs(v):.6g} exceeds the declared bound {self.vmax:.6g}")
                return
            if e > self.emax:
                self.invalid.append(
                    f"energy {e:.6g} J exceeds the declared bound {self.emax:.6g} J")
                return

    def finish(self) -> None:
        for name, count in _warnings(self.mujoco, self.data).items():
            if count:
                self.invalid.append(f"solver warning {name} raised {count} times")


def _compiled_facts(model, mujoco, joint_name: str) -> dict:
    """What the compiler actually holds, so declared-vs-compiled drift cannot pass silently."""
    j = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
    return {
        "timestep_s": float(model.opt.timestep),
        "integrator": int(model.opt.integrator),
        "joint_type": int(model.jnt_type[j]),
        "jnt_qposadr": int(model.jnt_qposadr[j]),
        "jnt_dofadr": int(model.jnt_dofadr[j]),
        "stiffness": float(model.jnt_stiffness[j]),
        "qpos_spring": float(model.qpos_spring[int(model.jnt_qposadr[j])]),
        "range": [float(v) for v in model.jnt_range[j]],
        "limited": bool(model.jnt_limited[j]),
        "damping": float(model.dof_damping[int(model.jnt_dofadr[j])]),
        "frictionloss": float(model.dof_frictionloss[int(model.jnt_dofadr[j])]),
        "solreflimit": [float(v) for v in model.jnt_solref[j]],
    }


def _declared_vs_compiled(declared: dict, compiled: dict, invalid: list[str]) -> None:
    """Any mismatch between a declared physical value and the compiled one invalidates."""
    for key, value in declared.items():
        if key not in compiled:
            continue
        got = compiled[key]
        if isinstance(value, (list, tuple)):
            if not np.allclose(np.array(got, dtype=float), np.array(value, dtype=float),
                               rtol=0.0, atol=1e-12):
                invalid.append(f"compiled {key} {got!r} != declared {value!r}")
        elif isinstance(value, bool):
            if bool(got) != value:
                invalid.append(f"compiled {key} {got!r} != declared {value!r}")
        elif isinstance(value, float):
            if not math.isclose(float(got), value, rel_tol=1e-12, abs_tol=1e-15):
                invalid.append(f"compiled {key} {got!r} != declared {value!r}")


def _carriage_mass(model, mujoco, body_name: str = "carriage") -> float:
    bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name)
    if bid < 0:
        raise ValueError(f"body {body_name!r} not found in the compiled model")
    return float(model.body_mass[bid])


def _zero_crossing_period(t, q) -> float:
    """Period from upward zero crossings, linearly interpolated. 0.0 if fewer than two."""
    crossings = []
    for i in range(1, len(q)):
        if q[i - 1] < 0.0 <= q[i]:
            span = q[i] - q[i - 1]
            frac = (-q[i - 1] / span) if span else 0.0
            crossings.append(t[i - 1] + frac * (t[i] - t[i - 1]))
    if len(crossings) < 2:
        return 0.0
    return float(np.mean(np.diff(crossings)))


# --------------------------------------------------------------------------- trials
def run_frictionless_deflection(outdir: Path, *, timestep_s: float = 1.0e-3) -> Trial:
    """Undamped ``F/k``: the driven carriage oscillates about ``F/k``.

    There is no steady state without damping, so the measured quantity is the **centre** of
    the oscillation, which is exactly ``F/k`` for ``x = (F/k)(1-cos ωt)``. The push is an
    integer number of periods long so the mean over the whole push phase is that centre; a
    fractional number of cycles would bias the mean by the residual sine term.
    """
    period = slider_period_s()
    n_cycles = max(1, int(round(PUSH_S / period)))
    push_s = n_cycles * period
    _preflight(timestep_s, push_s + 2.0 * period)
    spec = slider_frictionless_spec(timestep_s=timestep_s)
    mujoco, model, data, export = _compile(spec, Path(outdir) / "scene", timestep_s)

    invalid: list[str] = []
    compiled = _compiled_facts(model, mujoco, "carriage_slide")
    declared = {
        "timestep_s": timestep_s, "stiffness": SLIDER_K_N_PER_M, "qpos_spring": 0.0,
        "range": list(SLIDER_RANGE_M), "limited": True, "damping": 0.0, "frictionloss": 0.0,
    }
    _declared_vs_compiled(declared, compiled, invalid)
    mass = _carriage_mass(model, mujoco)
    if not math.isclose(mass, SLIDER_KG, rel_tol=1e-12):
        invalid.append(f"compiled carriage mass {mass!r} != declared {SLIDER_KG!r}")

    rec = _Recorder(mujoco, model, data, "carriage_slide", "push", mass,
                    vmax=SLIDER_VMAX_M_S, emax=SLIDER_EMAX_J)
    rec.phase("push")
    rec.step(int(round(push_s / timestep_s)), SLIDER_FORCE_N)
    rec.phase("release")
    rec.step(int(round(2.0 * period / timestep_s)), 0.0)
    rec.finish()
    invalid.extend(rec.invalid)

    # The measured quantity is the centre of the oscillation **while the drive is applied**,
    # where x(t) = (F/k)(1 - cos wt). The push lasts an integer number of periods, so the mean
    # over every push step is exactly F/k. After release the same undamped carriage oscillates
    # about the spring reference (0), so a release-phase mean would measure 0.
    #
    # The mean is taken over integration steps, not over the 2 ms telemetry rows: sampling a
    # 0.444 s oscillation on a coarse grid aliases the residual sine term into a ~0.08 mm bias,
    # which is the same size as the convergence tolerance and would be mistaken for a dt effect.
    centre = rec.phase_mean("push", "q")
    predicted = analytic_slider_deflection()
    rel = abs(centre - predicted) / predicted
    peak = rec.peak_qpos

    metrics = {
        "predicted_x_ss_m": predicted,
        "measured_centre_m": centre,
        "relative_error": rel,
        "peak_displacement_m": peak,
        "compiled_mass_kg": mass,
        "stiffness_n_per_m": SLIDER_K_N_PER_M,
        "peak_speed_m_s": rec.peak_speed,
        "peak_energy_j": rec.peak_energy,
        "peak_spring_force_n": rec.peak_spring,
    }
    checks = [
        _check("compiled_mass", math.isclose(mass, SLIDER_KG, rel_tol=1e-12),
               f"compiled carriage mass {mass:.6g} kg vs declared {SLIDER_KG} kg", mass),
        _check("deflection_matches_force_over_k", rel <= DEFLECTION_RTOL,
               f"oscillation centre {centre:.6f} m vs F/k {predicted:.6f} m "
               f"({rel:.2%}, tolerance {DEFLECTION_RTOL:.0%})", rel),
        _check("spring_is_the_restoring_force", rec.peak_spring > 0.0,
               f"peak |qfrc_spring| {rec.peak_spring:.6g} N; the restoring force is the "
               f"declared joint spring, not contact", rec.peak_spring),
    ]
    return Trial("frictionless_deflection", not invalid, invalid, metrics, checks,
                 _warnings(mujoco, data), timestep_s, compiled, rec.trace, TRACE_HEADER)


def run_frictionless_period(outdir: Path, *, timestep_s: float = 1.0e-3) -> Trial:
    """Released period of the undamped slider against ``2π√(m/k)``."""
    _preflight(timestep_s, PUSH_S + 4.0 * slider_period_s())
    spec = slider_frictionless_spec(timestep_s=timestep_s)
    mujoco, model, data, export = _compile(spec, Path(outdir) / "scene", timestep_s)

    invalid: list[str] = []
    compiled = _compiled_facts(model, mujoco, "carriage_slide")
    _declared_vs_compiled({"stiffness": SLIDER_K_N_PER_M, "damping": 0.0,
                           "frictionloss": 0.0}, compiled, invalid)
    mass = _carriage_mass(model, mujoco)
    if not math.isclose(mass, SLIDER_KG, rel_tol=1e-12):
        invalid.append(f"compiled carriage mass {mass!r} != declared {SLIDER_KG!r}")

    rec = _Recorder(mujoco, model, data, "carriage_slide", "push", mass,
                    vmax=SLIDER_VMAX_M_S, emax=SLIDER_EMAX_J)
    rec.phase("push")
    rec.step(int(round(PUSH_S / timestep_s)), SLIDER_FORCE_N)
    rec.phase("release")
    rec.step(int(round(4.0 * slider_period_s() / timestep_s)), 0.0)
    rec.finish()
    invalid.extend(rec.invalid)

    release = [row for row in rec.trace if row[1] == "release"]
    t = np.array([row[0] for row in release])
    # A released, undamped, zero-reference slider oscillates about the **spring reference**
    # (0), not about F/k. F/k is the centre only while the drive is applied; after release the
    # drive is gone and the oscillation is symmetric about home. Measuring crossings about the
    # compiled spring reference is therefore the physically correct offset.
    reference = float(compiled["qpos_spring"])
    q = np.array([row[2] - reference for row in release])
    measured = _zero_crossing_period(t, q)
    predicted = slider_period_s()
    rel = abs(measured - predicted) / predicted if measured else math.inf

    metrics = {
        "predicted_period_s": predicted,
        "measured_period_s": measured,
        "relative_error": rel,
        "compiled_mass_kg": mass,
        "compiled_stiffness_n_per_m": compiled["stiffness"],
        "release_reference_m": reference,
        "release_centre_m": float(np.mean(q)) if q.size else float("nan"),
    }
    checks = [
        _check("period_matches_2pi_sqrt_m_over_k", rel <= SLIDER_PERIOD_RTOL,
               f"measured {measured:.6f} s vs 2*pi*sqrt(m/k) {predicted:.6f} s "
               f"({rel:.2%}, tolerance {SLIDER_PERIOD_RTOL:.0%})", rel),
        _check("compiled_mass", math.isclose(mass, SLIDER_KG, rel_tol=1e-12),
               f"compiled carriage mass {mass:.6g} kg vs declared {SLIDER_KG} kg", mass),
    ]
    return Trial("frictionless_period", not invalid, invalid, metrics, checks,
                 _warnings(mujoco, data), timestep_s, compiled, rec.trace, TRACE_HEADER)


def run_damped_return(outdir: Path, *, timestep_s: float = 1.0e-3,
                      with_spring: bool = True) -> Trial:
    """Push, release, and return to home within 0.1 mm.

    ``with_spring=False`` is the missing-spring negative: without a declared spring nothing
    restores the carriage, so the return check must fail by name rather than pass by silence.
    """
    _preflight(timestep_s, PUSH_S + RELEASE_S)
    spec = slider_damped_spec(timestep_s=timestep_s)
    if not with_spring:
        rail, carriage = spec.bodies
        carriage = type(carriage)(
            body_id=carriage.body_id, parts=carriage.parts, frame=carriage.frame,
            fixed_to_world=carriage.fixed_to_world, fixture=carriage.fixture,
            source=carriage.source, fidelity=carriage.fidelity, parent=carriage.parent,
            joint=type(carriage.joint)(**{
                **{f.name: getattr(carriage.joint, f.name)
                   for f in carriage.joint.__dataclass_fields__.values()},
                "spring": None,
            }),
        )
        spec = type(spec)(**{
            **{f.name: getattr(spec, f.name) for f in spec.__dataclass_fields__.values()},
            "bodies": (rail, carriage),
        })
    mujoco, model, data, export = _compile(spec, Path(outdir) / "scene", timestep_s)

    invalid: list[str] = []
    compiled = _compiled_facts(model, mujoco, "carriage_slide")
    expected_damping = slider_analytic_stiffness_damping()
    declared = {"stiffness": SLIDER_K_N_PER_M if with_spring else 0.0,
                "damping": expected_damping, "frictionloss": 0.0}
    _declared_vs_compiled(declared, compiled, invalid)
    mass = _carriage_mass(model, mujoco)
    if not math.isclose(mass, SLIDER_KG, rel_tol=1e-12):
        invalid.append(f"compiled carriage mass {mass!r} != declared {SLIDER_KG!r}")

    rec = _Recorder(mujoco, model, data, "carriage_slide", "push", mass,
                    vmax=SLIDER_VMAX_M_S, emax=SLIDER_EMAX_J)
    rec.phase("push")
    rec.step(int(round(PUSH_S / timestep_s)), SLIDER_FORCE_N)
    x_after_push = float(data.qpos[rec.qadr])
    rec.phase("release")
    rec.step(int(round(RELEASE_S / timestep_s)), 0.0)
    rec.finish()
    invalid.extend(rec.invalid)

    x_final = float(data.qpos[rec.qadr])
    speed = float(data.qvel[rec.dofadr])
    residual = abs(x_final)

    # The **settled statics** check the packet asks for. This fixture is damped, so unlike the
    # undamped one it really does reach a steady state, and at the end of the push it is at
    # x = F/k. The end-of-push velocity is the evidence that the sample is settled rather than
    # mid-transient: a static comparison against a moving carriage would be meaningless.
    settled_deflection = x_after_push
    settled_speed = abs(float(rec.settled_speed("push")))
    predicted_deflection = analytic_slider_deflection()
    static_rel = abs(settled_deflection - predicted_deflection) / predicted_deflection

    metrics = {
        "x_after_push_m": x_after_push,
        "settled_deflection_m": settled_deflection,
        "settled_deflection_predicted_m": predicted_deflection,
        "settled_deflection_relative_error": static_rel,
        "settled_deflection_speed_m_s": settled_speed,
        "x_final_m": x_final,
        "residual_m": residual,
        "settled_speed_m_s": speed,
        "return_tolerance_m": RETURN_TOL_M,
        "compiled_damping_n_s_per_m": compiled["damping"],
        "damping_ratio": SLIDER_DAMPING_RATIO,
        "peak_speed_m_s": rec.peak_speed,
    }
    checks = [
        _check("settled_statics_matches_force_over_k", static_rel <= DEFLECTION_RTOL
               and settled_speed <= SETTLED_SPEED_M_S,
               f"settled x {settled_deflection:.6f} m vs F/k {predicted_deflection:.6f} m "
               f"({static_rel:.2%}, tolerance {DEFLECTION_RTOL:.0%}) at end-of-push speed "
               f"{settled_speed:.2e} m/s (<= {SETTLED_SPEED_M_S} m/s)", static_rel),
        _check("driven_displacement", x_after_push > 0.5 * analytic_slider_deflection(),
               f"x after push {x_after_push:.6f} m; the bounded input moved the carriage",
               x_after_push),
        _check("returns_to_home", residual <= RETURN_TOL_M,
               f"final |x| {residual * 1e3:.4f} mm vs tolerance {RETURN_TOL_M * 1e3:.2f} mm",
               residual),
        _check("settled", abs(speed) <= SETTLED_SPEED_M_S,
               f"final |v| {abs(speed):.5f} m/s vs {SETTLED_SPEED_M_S} m/s", abs(speed)),
        _check("spring_restoring_force_present", rec.peak_spring > 0.0,
               f"peak |qfrc_spring| {rec.peak_spring:.6g} N", rec.peak_spring),
    ]
    name = "damped_return" if with_spring else "damped_return_missing_spring"
    return Trial(name, not invalid, invalid, metrics, checks,
                 _warnings(mujoco, data), timestep_s, compiled, rec.trace, TRACE_HEADER)


def run_friction_static(outdir: Path, *, timestep_s: float = 1.0e-3,
                        apply_force: bool = True) -> Trial:
    """Preloaded, damped, Coulomb-friction slider against its declared static band.

    ``apply_force=False`` is the missing-input negative: with no input the carriage must stay
    inside the stiction band, so the driven-displacement check fails on evidence.
    """
    _preflight(timestep_s, PUSH_S + RELEASE_S)
    spec = slider_friction_spec(timestep_s=timestep_s)
    mujoco, model, data, export = _compile(spec, Path(outdir) / "scene", timestep_s)

    invalid: list[str] = []
    compiled = _compiled_facts(model, mujoco, "carriage_slide")
    declared = {"stiffness": SLIDER_K_N_PER_M, "qpos_spring": SLIDER_PRELOAD_M,
                "frictionloss": SLIDER_FRICTIONLOSS,
                "damping": slider_analytic_stiffness_damping()}
    _declared_vs_compiled(declared, compiled, invalid)
    mass = _carriage_mass(model, mujoco)
    if not math.isclose(mass, SLIDER_KG, rel_tol=1e-12):
        invalid.append(f"compiled carriage mass {mass!r} != declared {SLIDER_KG!r}")

    rec = _Recorder(mujoco, model, data, "carriage_slide", "push", mass,
                    vmax=SLIDER_VMAX_M_S, emax=SLIDER_EMAX_J)
    rec.phase("push")
    rec.step(int(round(PUSH_S / timestep_s)), SLIDER_FORCE_N if apply_force else 0.0)
    x_after_push = float(data.qpos[rec.qadr])
    rec.phase("release")
    rec.step(int(round(RELEASE_S / timestep_s)), 0.0)
    rec.finish()
    invalid.extend(rec.invalid)

    lo, hi = slider_friction_band()
    x_final = float(data.qpos[rec.qadr])
    residual = abs(x_final - SLIDER_PRELOAD_M)   # the spring reference is the home position
    bound = slider_release_residual_bound()
    metrics = {
        "band_low_m": lo,
        "band_high_m": hi,
        "preload_m": SLIDER_PRELOAD_M,
        "x_after_push_m": x_after_push,
        "x_final_m": x_final,
        "release_residual_m": residual,
        "residual_bound_m": bound,
        "frictionloss_n": SLIDER_FRICTIONLOSS,
        "peak_constraint_n": rec.peak_constraint,
        "peak_energy_j": rec.peak_energy,
    }
    checks = [
        _check("static_band", lo <= x_after_push <= hi,
               f"x after push {x_after_push:.6f} m vs declared band [{lo:.6f}, {hi:.6f}] "
               f"from preload {SLIDER_PRELOAD_M} m and friction {SLIDER_FRICTIONLOSS} N",
               x_after_push),
        _check("release_residual_within_friction", residual <= bound,
               f"|x - springref| {residual * 1e3:.4f} mm vs frictionloss/k "
               f"{bound * 1e3:.3f} mm", residual),
        _check("stop_never_engaged",
               SLIDER_RANGE_M[0] < rec.min_qpos and rec.peak_qpos < SLIDER_RANGE_M[1],
               f"travel stayed within ({rec.min_qpos:.6f}, {rec.peak_qpos:.6f}) m inside the "
               f"limits {list(SLIDER_RANGE_M)}: the residual comes from declared friction, not "
               f"from resting on a stop", rec.peak_qpos),
    ]
    name = "friction_static" if apply_force else "friction_static_missing_input"
    return Trial(name, not invalid, invalid, metrics, checks,
                 _warnings(mujoco, data), timestep_s, compiled, rec.trace, TRACE_HEADER)


def run_stop(outdir: Path, *, timestep_s: float = 1.0e-3) -> Trial:
    """Sustained drive into a compliant stop with a **declared** penetration budget."""
    _preflight(timestep_s, STOP_HOLD_S + STOP_RELEASE_S)
    spec = slider_stop_spec(timestep_s=timestep_s)
    # The stop compliance is the physical constant under test, so refuse a step that cannot
    # resolve it before stepping (see check_timeconst_resolvable).
    mujoco, model, data, export = _compile(
        spec, Path(outdir) / "scene", timestep_s,
        declared_timeconst=STOP_TIMECONST_S, what="joint stop")

    invalid: list[str] = []
    compiled = _compiled_facts(model, mujoco, "carriage_slide")
    declared = {"stiffness": 0.0, "range": list(STOP_RANGE_M), "limited": True,
                "solreflimit": [STOP_TIMECONST_S, STOP_DAMPRATIO]}
    _declared_vs_compiled(declared, compiled, invalid)
    mass = _carriage_mass(model, mujoco)
    if not math.isclose(mass, SLIDER_KG, rel_tol=1e-12):
        invalid.append(f"compiled carriage mass {mass!r} != declared {SLIDER_KG!r}")
    # Record the effective (refsafe-floored) compliance, not just the stored one: equal stored
    # solref does not imply equal effective physics at different steps.
    effective = effective_timeconst(mujoco, model, STOP_TIMECONST_S)
    if abs(effective - STOP_TIMECONST_S) > 1e-15 * STOP_TIMECONST_S:
        invalid.append(
            f"effective stop time constant {effective!r} s differs from the declared "
            f"{STOP_TIMECONST_S!r} s at dt {float(model.opt.timestep)!r} s")

    rec = _Recorder(mujoco, model, data, "carriage_slide", "push", mass,
                    vmax=SLIDER_VMAX_M_S, emax=SLIDER_EMAX_J)
    rec.phase("sustained_drive")
    rec.step(int(round(STOP_HOLD_S / timestep_s)), STOP_DRIVE_N)
    x_held = float(data.qpos[rec.qadr])
    held_constraint = float(data.qfrc_constraint[rec.dofadr])
    rec.phase("release")
    rec.step(int(round(STOP_RELEASE_S / timestep_s)), 0.0)
    rec.finish()
    invalid.extend(rec.invalid)

    x_released = float(data.qpos[rec.qadr])
    hi = STOP_RANGE_M[1]
    steady = x_held - hi
    peak = rec.peak_qpos - hi
    estimate = stop_penetration_estimate_m()
    metrics = {
        "stop_high_m": hi,
        "x_held_m": x_held,
        "steady_penetration_m": steady,
        "peak_penetration_m": peak,
        "steady_budget_m": STOP_STEADY_PENETRATION_M,
        "peak_budget_m": STOP_PEAK_PENETRATION_M,
        "penetration_estimate_m": estimate,
        "held_constraint_n": held_constraint,
        "x_after_release_m": x_released,
        "drive_n": STOP_DRIVE_N,
        "stop_timeconst_s": STOP_TIMECONST_S,
        "stop_timeconst_effective_s": effective,
        "stop_timeconst_resolved": abs(effective - STOP_TIMECONST_S) <= 1e-15 * STOP_TIMECONST_S,
        "peak_effective_ctrl": rec.peak_effective_ctrl,
        "peak_requested_ctrl": rec.peak_requested_ctrl,
    }
    checks = [
        _check("stop_reached", x_held > hi,
               f"held position {x_held:.6f} m is past the stop at {hi:.6f} m", x_held),
        _check("steady_penetration_within_declared_budget",
               steady <= STOP_STEADY_PENETRATION_M,
               f"steady penetration {steady * 1e3:.4f} mm vs declared budget "
               f"{STOP_STEADY_PENETRATION_M * 1e3:.2f} mm (estimate F*tc^2/m = "
               f"{estimate * 1e3:.4f} mm)", steady),
        _check("peak_penetration_within_declared_budget",
               peak <= STOP_PEAK_PENETRATION_M,
               f"peak penetration {peak * 1e3:.4f} mm vs declared budget "
               f"{STOP_PEAK_PENETRATION_M * 1e3:.2f} mm", peak),
        _check("stop_engaged", abs(held_constraint) > 0.0,
               f"held |qfrc_constraint| {abs(held_constraint):.6g} N: the stop carries the "
               f"drive, not the spring", abs(held_constraint)),
        _check("released_inside_range",
               STOP_RANGE_M[0] <= x_released <= STOP_RANGE_M[1],
               f"position after release {x_released:.6f} m vs range {list(STOP_RANGE_M)}: "
               f"releasing the drive lets the carriage come off the stop", x_released),
    ]
    return Trial("stop_loaded", not invalid, invalid, metrics, checks,
                 _warnings(mujoco, data), timestep_s, compiled, rec.trace, TRACE_HEADER)


def run_hinge(outdir: Path, *, damping: float = 0.0,
              timestep_s: float = 1.0e-3) -> Trial:
    """Release the arm from a declared angle and measure the oscillation period."""
    _preflight(timestep_s, HINGE_WINDOW_S)
    spec = hinge_oscillator_spec(damping=damping, timestep_s=timestep_s)
    mujoco, model, data, export = _compile(spec, Path(outdir) / "scene", timestep_s)

    invalid: list[str] = []
    compiled = _compiled_facts(model, mujoco, "arm_hinge")
    _declared_vs_compiled({"stiffness": HINGE_K_NM_PER_RAD, "damping": damping}, compiled,
                          invalid)
    joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "arm_hinge")
    qadr = int(model.jnt_qposadr[joint])
    dofadr = int(model.jnt_dofadr[joint])

    # Declared initial condition at independent reset: a small angle, zero velocity.
    data.qpos[qadr] = HINGE_AMP_RAD
    data.qvel[dofadr] = 0.0
    mujoco.mj_forward(model, data)

    # Route the hinge through the same recorder as the slider, so the two paths share one set
    # of guards: finite qpos/qvel/qacc, finite input, finite generalized force, speed and
    # energy bounds, and every solver warning counter. A hand-rolled loop here previously had
    # only a subset, which is exactly the inconsistency the review flagged.
    inertia = analytic_hinge_inertia_kg_m2()
    rec = _Recorder(mujoco, model, data, "arm_hinge", None, inertia,
                    vmax=HINGE_VMAX_RAD_S, emax=HINGE_EMAX_J, inertia_kg_m2=inertia)
    rec.phase("release")
    rec.step(int(round(HINGE_WINDOW_S / timestep_s)), 0.0)
    rec.finish()
    invalid.extend(rec.invalid)
    trace = rec.trace
    peak_speed = rec.peak_speed

    t = np.array([row[0] for row in trace])
    q = np.array([row[2] for row in trace])
    measured = _zero_crossing_period(t, q)
    ratio = _damping_ratio(model, joint)
    predicted = analytic_period_s(damping_ratio=ratio)
    rel = (abs(measured - predicted) / predicted if measured else float("inf"))

    metrics = {
        "predicted_period_s": predicted,
        "measured_period_s": measured,
        "period_relative_error": rel,
        "inertia_analytic_kg_m2": analytic_hinge_inertia_kg_m2(),
        "inertia_cad_kg_m2": hinge_cad_inertia_kg_m2(),
        "compiled_inertia_kg_m2": _hinge_axis_inertia(model, joint),
        "stiffness_nm_per_rad": HINGE_K_NM_PER_RAD,
        "amplitude_rad": HINGE_AMP_RAD,
        "damping_ratio": ratio,
        "peak_speed_rad_s": peak_speed,
    }
    checks = [
        _check("period", rel <= HINGE_PERIOD_RTOL,
               f"measured {measured:.6f} s vs analytic {predicted:.6f} s "
               f"({rel:.2%}, tolerance {HINGE_PERIOD_RTOL:.0%})", rel),
        _check("inertia_agrees",
               abs(metrics["inertia_cad_kg_m2"] - analytic_hinge_inertia_kg_m2())
               <= 1e-9 * analytic_hinge_inertia_kg_m2(),
               f"CAD {metrics['inertia_cad_kg_m2']:.9g} vs analytic "
               f"{analytic_hinge_inertia_kg_m2():.9g} kg m2",
               metrics["inertia_cad_kg_m2"]),
        _check("compiled_inertia_agrees",
               abs(metrics["compiled_inertia_kg_m2"] - analytic_hinge_inertia_kg_m2())
               <= 1e-6 * analytic_hinge_inertia_kg_m2(),
               f"compiled mj_fullM entry {metrics['compiled_inertia_kg_m2']:.9g} vs analytic "
               f"{analytic_hinge_inertia_kg_m2():.9g} kg m2",
               metrics["compiled_inertia_kg_m2"]),
        _check("range_respected", bool(np.all(np.abs(q) <= math.radians(60.0) + 1e-6)),
               f"max |angle| {float(np.max(np.abs(q))):.5f} rad vs limit "
               f"{math.radians(60.0):.5f} rad", float(np.max(np.abs(q)))),
        _check("spring_force_present",
               bool(np.max(np.abs(np.array([r[SPRING_COL] for r in trace]))) > 0),
               "the restoring force comes from the declared joint spring, not from contact",
               float(np.max(np.abs(np.array([r[SPRING_COL] for r in trace]))))),
    ]
    name = "hinge_oscillator" if damping == 0.0 else "hinge_damped"
    return Trial(name, not invalid, invalid, metrics, checks,
                 _warnings(mujoco, data), timestep_s, compiled, trace, TRACE_HEADER)


def _damping_ratio(model, joint_id: int) -> float:
    """The damping ratio implied by the compiled joint damping and the spring."""
    k = float(model.jnt_stiffness[joint_id])
    c = float(model.dof_damping[int(model.jnt_dofadr[joint_id])])
    inertia = _hinge_axis_inertia(model, joint_id)
    if k <= 0.0 or inertia <= 0.0:
        return 0.0
    return c / (2.0 * math.sqrt(k * inertia))


def _hinge_axis_inertia(model, joint_id: int) -> float:
    """The generalized inertia about the hinge axis, from the compiled model.

    ``mj_fullM`` gives the joint-space mass matrix; its diagonal entry for this joint is
    exactly the effective inertia the hinge rotates, including the offset-COM parallel-axis
    term. Reading a body-frame diagonal component instead would be wrong for any body whose
    principal axes are not the joint axis.
    """
    mujoco = require_mujoco()
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    full = np.zeros((model.nv, model.nv), dtype=np.float64)
    mujoco.mj_fullM(model, data, full)
    dof = int(model.jnt_dofadr[joint_id])
    return float(full[dof, dof])


# --------------------------------------------------------------------------- driver
def _write_trace(path: Path, trial: Trial) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(trial.trace_header)
        for row in trial.trace:
            writer.writerow([f"{v:.9g}" if isinstance(v, float) else v for v in row])


def default_mechanics_outdir(run_id: str) -> Path:
    from ..workspace import fixtures_root

    return fixtures_root() / "m3_mechanics" / "physics" / run_id


def _run_set(outdir: Path, timestep_s: float) -> dict[str, Trial]:
    """Every trial at one timestep. The base and half-dt runs share these physical inputs."""
    return {
        "frictionless_deflection": run_frictionless_deflection(
            outdir / "frictionless_deflection", timestep_s=timestep_s),
        "frictionless_period": run_frictionless_period(
            outdir / "frictionless_period", timestep_s=timestep_s),
        "damped_return": run_damped_return(outdir / "damped_return", timestep_s=timestep_s),
        "friction_static": run_friction_static(outdir / "friction_static",
                                               timestep_s=timestep_s),
        "stop_loaded": run_stop(outdir / "stop_loaded", timestep_s=timestep_s),
        "hinge_oscillator": run_hinge(outdir / "hinge_oscillator", timestep_s=timestep_s),
        "hinge_damped": run_hinge(outdir / "hinge_damped",
                                  damping=hinge_damping_nm_s_per_rad(),
                                  timestep_s=timestep_s),
    }


def _negative_trials(outdir: Path, timestep_s: float) -> dict[str, Trial]:
    """Adverse cases. Each must fail its named physical check, not be relabelled success."""
    return {
        "missing_input": run_friction_static(outdir / "missing_input", timestep_s=timestep_s,
                                             apply_force=False),
        "missing_spring": run_damped_return(outdir / "missing_spring", timestep_s=timestep_s,
                                            with_spring=False),
    }


def _convergence(base: dict[str, Trial], half: dict[str, Trial]) -> dict:
    """Compare base and half-dt runs of the same physical fixture, metric by metric.

    Each metric is compared against a tolerance stated in physical units (or relative), and a
    transient metric gets a transient-sized tolerance: the first-impact peak is a sampled
    maximum, so it cannot be expected to agree to a steady-state tolerance.
    """
    rows = []

    def add(name, metric, tol, kind):
        a = base[name].metrics.get(metric)
        b = half[name].metrics.get(metric)
        finite_a = a is not None and math.isfinite(a)
        finite_b = b is not None and math.isfinite(b)
        if not finite_a or not finite_b:
            rows.append({"trial": name, "metric": metric,
                         "base": a if finite_a else None, "half": b if finite_b else None,
                         "delta": None, "tolerance": tol, "kind": kind, "ok": False})
            return
        delta = abs(a - b) if kind == "abs" else abs(a - b) / max(abs(a), 1e-30)
        ok = delta <= tol
        rows.append({"trial": name, "metric": metric, "base": a, "half": b,
                     "delta": delta, "tolerance": tol, "kind": kind, "ok": ok})

    add("frictionless_deflection", "measured_centre_m", CONVERGENCE_DEFLECTION_M, "abs")
    add("frictionless_period", "measured_period_s", CONVERGENCE_PERIOD_RTOL, "rel")
    add("damped_return", "residual_m", CONVERGENCE_DEFLECTION_M, "abs")
    add("friction_static", "x_after_push_m", CONVERGENCE_DEFLECTION_M, "abs")
    add("stop_loaded", "steady_penetration_m", CONVERGENCE_PENETRATION_M, "abs")
    # The first-impact peak is a sampled maximum of a collision transient, so it is
    # grid-dependent by construction (measured 0.48 / 0.38 / 0.44 mm at 1 / 0.5 / 0.25 ms).
    # It is reported with an explicit transient tolerance instead of being asserted to
    # converge, and it is separately bounded by STOP_PEAK_PENETRATION_M in the trial itself.
    add("stop_loaded", "peak_penetration_m", STOP_PEAK_PENETRATION_M, "abs")
    add("hinge_oscillator", "measured_period_s", CONVERGENCE_PERIOD_RTOL, "rel")
    # The damped hinge is compared too. The supervisor's finding 1 said either include it or
    # explicitly limit the claim; including it is the honest option, since both runs already
    # measure it.
    add("hinge_damped", "measured_period_s", CONVERGENCE_PERIOD_RTOL, "rel")
    return {
        "rows": rows,
        "ok": all(r["ok"] for r in rows),
        "base_dt_s": base["frictionless_deflection"].solver_dt_s,
        "half_dt_s": half["frictionless_deflection"].solver_dt_s,
    }


def _fmt(value) -> str:
    return "n/a" if value is None else f"{value:.6g}"


def _render(summary: dict) -> str:
    lines = [
        "# M3 mechanics evidence", "",
        f"Status: **{summary['status']}**  ",
        f"Base step: `{summary['solver']['base_timestep_s']}` s, half step: "
        f"`{summary['solver']['half_timestep_s']}` s  ",
        f"MuJoCo {summary['versions']['mujoco']}", "",
    ]
    # Base AND half, keyed by set. report.md is the artifact the repo's iteration loop names,
    # so a gated half failure that only appeared in summary.json would be invisible in the
    # document a reader actually opens.
    for key, trial in {**summary["trials"], **summary["half_trials"],
                       **summary.get("negative_trials", {})}.items():
        lines.append(f"## {key}")
        lines.append("")
        lines.append(f"valid: `{trial['valid']}`  ")
        if trial["invalid_reasons"]:
            lines.append(f"invalid: {trial['invalid_reasons']}  ")
        lines.append("")
        lines.append("| check | ok | detail |")
        lines.append("|---|---|---|")
        for c in trial["checks"]:
            lines.append(f"| {c['name']} | {c['ok']} | {c['detail']} |")
        lines.append("")
        lines.append(f"Warnings: `{trial['warnings']}`  ")
        lines.append(f"Trace rows: {trial['trace_rows']}")
        lines.append("")
    conv = summary["convergence"]
    lines.append("## Convergence (base vs half timestep)")
    lines.append("")
    lines.append("| trial | metric | base | half | delta | tolerance | ok |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in conv["rows"]:
        lines.append(f"| {r['trial']} | {r['metric']} | {_fmt(r['base'])} | {_fmt(r['half'])} "
                     f"| {_fmt(r['delta'])} | {_fmt(r['tolerance'])} ({r['kind']}) | {r['ok']} |")
    lines.append("")
    return "\n".join(lines)


def run_mechanics(outdir: Path | None = None, *, timestep_s: float = 1.0e-3) -> dict:
    """Run every fixture at ``timestep_s`` and at half that, then write traces and a summary."""
    if outdir is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        outdir = default_mechanics_outdir(stamp)
    outdir = Path(outdir)
    if outdir.exists() and any(outdir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {outdir}")
    outdir.mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()
    base = _run_set(outdir / "base", timestep_s)
    half = _run_set(outdir / "half", timestep_s / 2.0)
    negatives = _negative_trials(outdir / "negatives", timestep_s)
    convergence = _convergence(base, half)
    wall = time.perf_counter() - start

    # Every set is persisted, half included: a discarded half run cannot be reviewed.
    # Names must be distinct per set, because base and half trials share their trial names and
    # a bare ``trace_<name>.csv`` would let the half set silently overwrite the base one.
    for key, trial in base.items():
        _write_trace(outdir / f"trace_base_{key}.csv", trial)
    for key, trial in half.items():
        _write_trace(outdir / f"trace_half_{key}.csv", trial)
    for key, trial in negatives.items():
        _write_trace(outdir / f"trace_{key}.csv", trial)

    # A negative passes only when it fails its named physical check. Passing a negative means
    # the fixture failed to distinguish the adverse case from success.
    negative_ok = {}
    for key, trial in negatives.items():
        named = {
            "missing_input": "static_band",
            "missing_spring": "returns_to_home",
        }[key]
        verdict = next(c for c in trial.checks if c["name"] == named)
        negative_ok[key] = (not verdict["ok"]) and trial.valid

    # Gate BOTH sets. A half-dt trial that is numerically invalid, or that fails a required
    # physical check, is a failure of the evidence: the comparison is only meaningful between
    # two runs that each stand on their own. Previously only base was consulted, so an invalid
    # or physically wrong half run was silently discarded and the summary still said PASS.
    all_positive = {**{f"base/{k}": t for k, t in base.items()},
                    **{f"half/{k}": t for k, t in half.items()}}
    valid = all(t.valid for t in all_positive.values()) and convergence["ok"] and all(
        negative_ok.values())
    # ``all()`` over an empty iterable is True, so a trial that somehow reported no checks
    # would pass silently. Require at least one check per gated trial.
    physical = all(bool(t.checks) and all(c["ok"] for c in t.checks)
                   for t in all_positive.values())
    if not valid:
        status = "INCONCLUSIVE"
    elif physical:
        status = "PASS"
    else:
        status = "FAIL"

    summary = {
        "scenario": "m3_mechanics",
        "status": status,
        "run_id": outdir.name,
        "run_dir": str(outdir),
        "trials": {f"base/{k}": t.to_dict() for k, t in base.items()},
        "half_trials": {f"half/{k}": t.to_dict() for k, t in half.items()},
        "negative_trials": {k: t.to_dict() for k, t in negatives.items()},
        "convergence": convergence,
        "negatives": {k: {"ok": v} for k, v in negative_ok.items()},
        "parameters": {
            "slider_mass_kg": SLIDER_KG,
            "slider_stiffness_n_per_m": SLIDER_K_N_PER_M,
            "slider_force_n": SLIDER_FORCE_N,
            "slider_preload_m": SLIDER_PRELOAD_M,
            "slider_frictionloss_n": SLIDER_FRICTIONLOSS,
            "slider_damping_ratio": SLIDER_DAMPING_RATIO,
            "slider_damping_n_s_per_m": slider_analytic_stiffness_damping(),
            "slider_range_m": list(SLIDER_RANGE_M),
            "stop_range_m": list(STOP_RANGE_M),
            "stop_drive_n": STOP_DRIVE_N,
            "stop_timeconst_s": STOP_TIMECONST_S,
            "stop_dampratio": STOP_DAMPRATIO,
            "stop_steady_budget_m": STOP_STEADY_PENETRATION_M,
            "stop_peak_budget_m": STOP_PEAK_PENETRATION_M,
            "provenance": "assumed analytic-fixture inputs, not measurements",
        },
        "solver": {"requested_timestep_s": timestep_s,
                   "base_timestep_s": base["frictionless_deflection"].solver_dt_s,
                   "half_timestep_s": half["frictionless_deflection"].solver_dt_s},
        "versions": {"python": platform.python_version(), "platform": platform.platform(),
                     "mujoco": _mujoco_version()},
        "runtime_wall_s": wall,
        "gating": {
            "positive_trials_gated": sorted(all_positive),
            "base_invalid": sorted(k for k, t in base.items() if not t.valid),
            "half_invalid": sorted(k for k, t in half.items() if not t.valid),
            "base_failed_checks": sorted(
                f"{k}:{c['name']}" for k, t in base.items() for c in t.checks if not c["ok"]),
            "half_failed_checks": sorted(
                f"{k}:{c['name']}" for k, t in half.items() for c in t.checks if not c["ok"]),
        },
        "artifacts": {
            **{f"trace_base_{k}": f"trace_base_{k}.csv" for k in base},
            **{f"trace_half_{k}": f"trace_half_{k}.csv" for k in half},
            **{f"trace_{k}": f"trace_{k}.csv" for k in negatives},
        },
    }
    (outdir / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (outdir / "report.md").write_text(_render(summary), encoding="utf-8")
    return summary


def _mujoco_version() -> str:
    try:
        return require_mujoco().__version__
    except Exception:
        return "unavailable"
