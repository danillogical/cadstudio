"""Central validity and acceptance evaluation for generic scenarios.

Four states, one precedence:

* **ERROR** — the scene/build/unit/compile/file layer failed. Raised by the loader, exporter
  or artifact writer; never awarded a physical verdict.
* **INCONCLUSIVE** — the run was admitted but its evidence is not trustworthy: non-finite
  state/forces/control, a solver warning, unresolvable contact/stop compliance, a declared
  numerical bound was exceeded, a required boundary or contact pair is missing, or no
  required checks exist.
* **FAIL** — the run is numerically valid and at least one declared physical predicate is
  unmet.
* **PASS** — the run is numerically valid and every required check is satisfied.

Invalidity short-circuits PASS even when every physical predicate happens to read true.
Acceptance thresholds are literal values from the separately loaded acceptance file; this
module never derives or loosens one from the candidate's geometry or measured outcome.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from . import Status
from .scenario import AcceptanceSpec, CheckSpec, ScenarioError, ScenarioSpec
from .schema import AssemblySpec


@dataclass
class CheckOutcome:
    name: str
    kind: str
    status: Status
    ok: bool | None
    detail: str
    value: float | None
    units: str
    stage: str = "evaluate"
    time_s: float | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name, "kind": self.kind, "status": self.status,
            "ok": self.ok, "detail": self.detail,
            "value": self.value if self.value is None or math.isfinite(self.value) else None,
            "units": self.units, "stage": self.stage, "time_s": self.time_s,
        }


@dataclass
class Evaluation:
    status: Status
    checks: list[CheckOutcome]
    validity: dict
    metrics: dict

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "checks": [c.to_dict() for c in self.checks],
            "validity": self.validity,
            "metrics": self.metrics,
        }


_JOINT_UNITS = {"slide": ("m", "m/s"), "hinge": ("rad", "rad/s")}
_EFFORT_UNITS = {"slide": {"N"}, "hinge": {"N m", "Nm", "N.m"}}


def resolve_references(scenario: ScenarioSpec, acceptance: AcceptanceSpec,
                       spec: AssemblySpec) -> None:
    """Reject references and units that do not exist in the assembled scene (ERROR)."""
    joint_kind = {
        body.joint.joint_id: body.joint.kind
        for body in spec.bodies if body.joint is not None
    }
    actuators = {a.actuator_id: a for a in spec.actuators}
    bodies = {b.body_id for b in spec.bodies}
    phases = {p.name for p in scenario.phases} | {"initial"}
    for check in acceptance.checks:
        where = f"acceptance check {check.name!r}"
        if check.kind == "body_speed":
            if check.body not in bodies:
                raise ScenarioError(f"{where}: unknown body {check.body!r}")
        if check.kind in ("joint_displacement", "return_displacement", "terminal_speed"):
            if check.joint not in joint_kind:
                raise ScenarioError(f"{where}: unknown joint {check.joint!r}")
            kind = joint_kind[check.joint]
            position_units, speed_units = _JOINT_UNITS[kind]
            expected_units = speed_units if check.kind == "terminal_speed" else position_units
            if check.units != expected_units:
                raise ScenarioError(
                    f"{where}: units {check.units!r} do not match {kind} joint "
                    f"{check.joint!r}, which needs {expected_units!r}")
        if check.kind == "effort_bound":
            if check.actuator not in actuators:
                raise ScenarioError(f"{where}: unknown actuator {check.actuator!r}")
            actuator = actuators[check.actuator]
            kind = joint_kind[actuator.joint_id]
            if check.units not in _EFFORT_UNITS[kind]:
                raise ScenarioError(
                    f"{where}: units {check.units!r} do not match actuator "
                    f"{check.actuator!r} on a {kind} joint")
        if check.kind == "contact_force_bound":
            for body in (check.body_a, check.body_b):
                if body not in bodies:
                    raise ScenarioError(f"{where}: unknown body {body!r}")
        for phase in (check.phase, check.from_phase, check.to_phase):
            if phase is not None and phase not in phases:
                raise ScenarioError(f"{where}: unknown phase {phase!r}")
    event_specs = {event.name: event for event in acceptance.events}
    phase_specs = {phase.name: phase for phase in scenario.phases}
    phase_order = {phase.name: index for index, phase in enumerate(scenario.phases)}
    for event in acceptance.events:
        where = f"acceptance event {event.name!r}"
        for body in event.bodies:
            if body not in bodies:
                raise ScenarioError(f"{where}: unknown body {body!r}")
            if any(b.body_id == body and b.fixed_to_world for b in spec.bodies):
                raise ScenarioError(
                    f"{where}: candidate body {body!r} is fixed to the world; "
                    f"it cannot provide motion evidence")
        for body in event.support_bodies:
            if body not in bodies:
                raise ScenarioError(f"{where}: unknown support body {body!r}")
        for phase in (event.window_from, event.window_to, event.release_phase,
                      event.dwell_from, event.dwell_to):
            if phase == "initial":
                raise ScenarioError(
                    f"{where}: event windows must name timed scenario phases, not 'initial'")
            if phase is not None and phase not in phases:
                raise ScenarioError(f"{where}: unknown phase {phase!r}")
        start = phase_order[event.window_from]
        end = phase_order[event.window_to]
        if phase_specs[event.window_from].is_reset:
            raise ScenarioError(f"{where}: window_from must be a timed phase")
        if start >= end:
            raise ScenarioError(
                f"{where}: window_from {event.window_from!r} must precede window_to "
                f"{event.window_to!r}")
        if event.kind == "supported_presentation":
            release = phase_specs[event.release_phase]
            if release.kind != "release":
                raise ScenarioError(
                    f"{where}: release_phase {event.release_phase!r} must be a release "
                    f"phase with real zero input, got {release.kind!r}")
            indices = [phase_order[event.window_from], phase_order[event.release_phase],
                       phase_order[event.dwell_from], phase_order[event.dwell_to], end]
            if indices != sorted(indices):
                raise ScenarioError(
                    f"{where}: phases must satisfy window_from <= release_phase <= "
                    f"dwell_from <= dwell_to <= window_to")
            for index in range(phase_order[event.release_phase],
                               phase_order[event.dwell_to] + 1):
                if scenario.phases[index].kind == "actuate":
                    raise ScenarioError(
                        f"{where}: dwell window from {event.release_phase!r} to "
                        f"{event.dwell_to!r} spans an actuate phase; a dwell must follow "
                        f"real zero input")
    for check in acceptance.checks:
        if check.kind not in ("event_count", "event_verdict"):
            continue
        where = f"acceptance check {check.name!r}"
        if check.event not in event_specs:
            raise ScenarioError(f"{where}: unknown event {check.event!r}")
        event = event_specs[check.event]
        if check.kind == "event_count" and event.kind != "exit_crossing":
            raise ScenarioError(
                f"{where}: event_count requires an exit_crossing event, "
                f"{check.event!r} is {event.kind!r}")
        if check.kind == "event_verdict" and event.kind != "supported_presentation":
            raise ScenarioError(
                f"{where}: event_verdict requires a supported_presentation event, "
                f"{check.event!r} is {event.kind!r}")
    for phase in scenario.phases:
        if phase.kind != "actuate":
            continue
        if phase.actuator not in actuators:
            raise ScenarioError(
                f"scenario phase {phase.name!r}: unknown actuator {phase.actuator!r}")
        actuator = actuators[phase.actuator]
        if phase.effort is not None and not math.isfinite(phase.effort):
            raise ScenarioError(f"scenario phase {phase.name!r}: non-finite effort")
        _ = actuator  # bounds are enforced by the runner and the emitted ctrlrange


def _reason(stage: str, reason: str, time_s: float | None = None) -> dict:
    return {"stage": stage, "reason": reason, "time_s": time_s}


def initial_bound_reasons(acceptance: AcceptanceSpec, telemetry) -> list[dict]:
    """Declared validity bounds already breached by the reset state.

    These are named with ``stage="initial"`` so an already-invalid initial scene cannot be
    laundered into a valid trial by the first integration step.
    """
    reasons: list[dict] = []
    v = acceptance.validity
    if (v.max_penetration_m is not None
            and telemetry.initial_penetration_m > v.max_penetration_m):
        reasons.append(_reason(
            "initial",
            f"initial penetration {telemetry.initial_penetration_m:.9g} m exceeds declared "
            f"bound {v.max_penetration_m:.9g} m", 0.0))
    if v.max_speed_m_s is not None and telemetry.initial_speed_m_s > v.max_speed_m_s:
        reasons.append(_reason(
            "initial",
            f"initial speed {telemetry.initial_speed_m_s:.9g} m/s exceeds declared bound "
            f"{v.max_speed_m_s:.9g} m/s", 0.0))
    if (v.max_angular_speed_rad_s is not None
            and telemetry.initial_angular_speed_rad_s > v.max_angular_speed_rad_s):
        reasons.append(_reason(
            "initial",
            f"initial angular speed {telemetry.initial_angular_speed_rad_s:.9g} rad/s "
            f"exceeds declared bound {v.max_angular_speed_rad_s:.9g} rad/s", 0.0))
    if v.max_energy_j is not None and telemetry.initial_energy_j > v.max_energy_j:
        reasons.append(_reason(
            "initial",
            f"initial energy {telemetry.initial_energy_j:.9g} J exceeds declared bound "
            f"{v.max_energy_j:.9g} J", 0.0))
    return reasons


def _validity_breaches(acceptance: AcceptanceSpec, telemetry) -> list[dict]:
    """All declared bound breaches, initial first, without losing a larger later peak."""
    reasons = initial_bound_reasons(acceptance, telemetry)
    v = acceptance.validity
    initial = {r["reason"].split()[1]: r for r in reasons}
    if (v.max_penetration_m is not None and telemetry.peak_penetration_m > v.max_penetration_m
            and telemetry.peak_penetration_m > telemetry.initial_penetration_m):
        reasons.append(_reason(
            "validity",
            f"peak penetration {telemetry.peak_penetration_m:.9g} m exceeds declared bound "
            f"{v.max_penetration_m:.9g} m"))
    if (v.max_speed_m_s is not None and telemetry.peak_speed > v.max_speed_m_s
            and telemetry.peak_speed > telemetry.initial_speed_m_s):
        reasons.append(_reason(
            "validity",
            f"peak speed {telemetry.peak_speed:.9g} m/s exceeds declared bound "
            f"{v.max_speed_m_s:.9g} m/s"))
    if (v.max_angular_speed_rad_s is not None
            and telemetry.peak_angular_speed_rad_s > v.max_angular_speed_rad_s
            and telemetry.peak_angular_speed_rad_s > telemetry.initial_angular_speed_rad_s):
        reasons.append(_reason(
            "validity",
            f"peak angular speed {telemetry.peak_angular_speed_rad_s:.9g} rad/s exceeds "
            f"declared bound {v.max_angular_speed_rad_s:.9g} rad/s"))
    if (v.max_energy_j is not None and telemetry.peak_energy_j > v.max_energy_j
            and telemetry.peak_energy_j > telemetry.initial_energy_j):
        reasons.append(_reason(
            "validity",
            f"peak energy {telemetry.peak_energy_j:.9g} J exceeds declared bound "
            f"{v.max_energy_j:.9g} J"))
    _ = initial
    return reasons


def _boundary(telemetry, name: str):
    snap = telemetry.boundaries.get(name)
    if snap is None:
        return None, _reason("evaluate", f"no recorded state boundary for phase {name!r}")
    return snap, None


def _outcome(check: CheckSpec, *, ok: bool | None, status: Status, detail: str,
             value: float | None, time_s: float | None = None) -> CheckOutcome:
    if value is not None and not math.isfinite(value):
        return CheckOutcome(check.name, check.kind, "INCONCLUSIVE", None,
                            f"{detail}; measured value is not finite", None, check.units,
                            "evaluate", time_s)
    return CheckOutcome(check.name, check.kind, status, ok, detail, value, check.units,
                        "evaluate", time_s)


def _evaluate_check(check: CheckSpec, telemetry) -> CheckOutcome:
    if check.kind == "joint_displacement":
        start, reason = _boundary(telemetry, check.from_phase or "initial")
        if reason:
            return _outcome(check, ok=None, status="INCONCLUSIVE",
                            detail=reason["reason"], value=None)
        end, reason = _boundary(telemetry, check.to_phase)
        if reason:
            return _outcome(check, ok=None, status="INCONCLUSIVE",
                            detail=reason["reason"], value=None)
        value = end.qpos[check.joint] - start.qpos[check.joint]
        measured = abs(value - check.expected)
        ok = measured <= check.tolerance
        return _outcome(
            check, ok=ok, status="PASS" if ok else "FAIL",
            detail=(f"displacement {value:.9g} {check.units} from {check.from_phase or 'initial'}"
                    f" to {check.to_phase}; expected {check.expected:.9g} "
                    f"+/- {check.tolerance:.9g} {check.units}"),
            value=value, time_s=end.time_s)

    if check.kind == "return_displacement":
        snap, reason = _boundary(telemetry, check.phase)
        if reason:
            return _outcome(check, ok=None, status="INCONCLUSIVE",
                            detail=reason["reason"], value=None)
        value = abs(snap.qpos[check.joint] - check.reference)
        ok = value <= check.maximum
        return _outcome(
            check, ok=ok, status="PASS" if ok else "FAIL",
            detail=(f"abs(q - reference) = {value:.9g} {check.units} at end of "
                    f"{check.phase!r}; bound {check.maximum:.9g} {check.units}"),
            value=value, time_s=snap.time_s)

    if check.kind == "terminal_speed":
        snap, reason = _boundary(telemetry, check.phase)
        if reason:
            return _outcome(check, ok=None, status="INCONCLUSIVE",
                            detail=reason["reason"], value=None)
        value = abs(snap.qvel[check.joint])
        ok = value <= check.maximum
        return _outcome(
            check, ok=ok, status="PASS" if ok else "FAIL",
            detail=(f"abs(velocity) = {value:.9g} {check.units} at end of {check.phase!r}; "
                    f"bound {check.maximum:.9g} {check.units}"),
            value=value, time_s=snap.time_s)

    if check.kind == "body_speed":
        snap, reason = _boundary(telemetry, check.phase)
        if reason:
            return _outcome(check, ok=None, status="INCONCLUSIVE",
                            detail=reason["reason"], value=None)
        entry = snap.bodies.get(check.body)
        if entry is None or "linear_velocity_m_s" not in entry:
            return _outcome(
                check, ok=None, status="INCONCLUSIVE",
                detail=f"no body velocity telemetry for {check.body!r}", value=None)
        value = float(np.linalg.norm(entry["linear_velocity_m_s"]))
        ok = value <= check.maximum
        return _outcome(
            check, ok=ok, status="PASS" if ok else "FAIL",
            detail=(f"body speed {value:.9g} m/s at end of {check.phase!r}; "
                    f"bound {check.maximum:.9g} m/s"),
            value=value, time_s=snap.time_s)

    if check.kind == "effort_bound":
        if check.actuator not in telemetry.commanded_actuators:
            return _outcome(
                check, ok=None, status="INCONCLUSIVE",
                detail=(f"actuator {check.actuator!r} was never part of an actuate phase; "
                        f"a zero peak is not evidence that the bound was exercised"),
                value=None)
        value = telemetry.peak_effort.get(check.actuator)
        if value is None:
            return _outcome(check, ok=None, status="INCONCLUSIVE",
                            detail=f"no telemetry for actuator {check.actuator!r}", value=None)
        ok = value <= check.maximum
        return _outcome(
            check, ok=ok, status="PASS" if ok else "FAIL",
            detail=(f"peak transmitted generalized effort {value:.9g} {check.units} on "
                    f"{check.actuator!r}; bound {check.maximum:.9g} {check.units}"),
            value=value)

    if check.kind == "contact_force_bound":
        pair = {check.body_a, check.body_b}
        matches = [row for row in telemetry.contacts()
                   if {row["body_a"], row["body_b"]} == pair]
        if not matches:
            return _outcome(
                check, ok=None, status="INCONCLUSIVE",
                detail=(f"no contact was observed between {check.body_a!r} and "
                        f"{check.body_b!r}; the predicate has no evidence"),
                value=None)
        value = max(row["max_normal_force_n"] for row in matches)
        ok = value <= check.maximum
        return _outcome(
            check, ok=ok, status="PASS" if ok else "FAIL",
            detail=(f"peak normal force {value:.9g} N on {check.body_a!r}/{check.body_b!r}; "
                    f"bound {check.maximum:.9g} N"),
            value=value)

    if check.kind == "penetration_bound":
        value = telemetry.peak_penetration_m
        ok = value <= check.maximum
        return _outcome(
            check, ok=ok, status="PASS" if ok else "FAIL",
            detail=(f"peak penetration {value:.9g} m; bound {check.maximum:.9g} m"),
            value=value)

    if check.kind == "event_count":
        result = getattr(telemetry, "event_results", {}).get(check.event)
        if result is None:
            return _outcome(
                check, ok=None, status="INCONCLUSIVE",
                detail=f"no event evidence for {check.event!r}", value=None)
        if not result.evidence_complete:
            return _outcome(
                check, ok=None, status="INCONCLUSIVE",
                detail=(f"event {check.event!r} evidence is incomplete: "
                        f"{result.verdict_code}"),
                value=None)
        if check.expected is None or check.tolerance is None:
            return _outcome(
                check, ok=None, status="INCONCLUSIVE",
                detail=f"event_count check {check.name!r} has no expected/tolerance",
                value=None)
        value = float(result.distinct_bodies_crossed)
        ok = abs(value - float(check.expected)) <= float(check.tolerance)
        return _outcome(
            check, ok=ok, status="PASS" if ok else "FAIL",
            detail=(f"{int(value)} distinct body identity(ies) crossed; expected "
                    f"{int(check.expected)} +/- {int(check.tolerance)}; diagnoses "
                    f"{result.verdict_code}"),
            value=value)

    if check.kind == "event_verdict":
        result = getattr(telemetry, "event_results", {}).get(check.event)
        if result is None:
            return _outcome(
                check, ok=None, status="INCONCLUSIVE",
                detail=f"no event evidence for {check.event!r}", value=None)
        if result.status == "INCONCLUSIVE":
            return _outcome(
                check, ok=None, status="INCONCLUSIVE",
                detail=f"event {check.event!r}: {result.verdict_code} - {result.detail}",
                value=None)
        ok = result.status == "PASS"
        return _outcome(
            check, ok=ok, status="PASS" if ok else "FAIL",
            detail=f"event {check.event!r}: {result.verdict_code} - {result.detail}",
            value=None)

    return _outcome(check, ok=None, status="INCONCLUSIVE",
                    detail=f"unsupported check kind {check.kind!r}", value=None)


def evaluate(scenario: ScenarioSpec, acceptance: AcceptanceSpec, telemetry,
             *, compliance_reasons: list[dict] | None = None) -> Evaluation:
    """Evaluate every declared check plus numerical validity, with fixed precedence."""
    outcomes = [_evaluate_check(check, telemetry) for check in acceptance.checks]
    reasons: list[dict] = []
    reasons.extend(dict(r) for r in telemetry.invalid)
    for result in getattr(telemetry, "event_results", {}).values():
        for reason in getattr(result, "invalid_reasons", ()):
            reasons.append(dict(reason))
    reasons.extend(compliance_reasons or [])
    reasons.extend(_validity_breaches(acceptance, telemetry))
    # Belt-and-braces: a warning counter raised by the solver must invalidate the run even if
    # it first appeared after the last recorded accumulation.
    for name, count in getattr(telemetry, "warnings", {}).items():
        if count and not any(name in r["reason"] for r in reasons):
            reasons.append(_reason("finish", f"solver warning {name} raised {count} times"))
    if not outcomes:
        reasons.append(_reason("evaluate", "acceptance declares no required checks"))

    metrics = telemetry.metrics()
    metrics["checks_declared"] = len(acceptance.checks)
    metrics["checks_passed"] = sum(1 for c in outcomes if c.status == "PASS")
    metrics["checks_failed"] = sum(1 for c in outcomes if c.status == "FAIL")
    metrics["checks_inconclusive"] = sum(
        1 for c in outcomes if c.status == "INCONCLUSIVE")

    validity = {"ok": not reasons, "reasons": reasons}
    if reasons:
        status: Status = "INCONCLUSIVE"
    elif any(c.status == "INCONCLUSIVE" for c in outcomes):
        status = "INCONCLUSIVE"
        if validity["ok"]:
            validity["ok"] = False
            validity["reasons"].append(
                _reason("evaluate", "at least one required check lacks sufficient evidence"))
    elif any(c.status == "FAIL" for c in outcomes):
        status = "FAIL"
    elif outcomes and all(c.status == "PASS" for c in outcomes):
        status = "PASS"
    else:
        status = "INCONCLUSIVE"
        reasons.append(_reason("evaluate", "insufficient evidence for a verdict"))
        validity["ok"] = False

    return Evaluation(status, outcomes, validity, metrics)
