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
from .telemetry import pose_delta, relative_transform


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
    #: Structured measurement evidence for the bound relative checks. ``None`` for the
    #: earlier kinds, whose serialized form must stay byte-identical.
    evidence: dict | None = None

    def to_dict(self) -> dict:
        out = {
            "name": self.name, "kind": self.kind, "status": self.status,
            "ok": self.ok, "detail": self.detail,
            "value": self.value if self.value is None or math.isfinite(self.value) else None,
            "units": self.units, "stage": self.stage, "time_s": self.time_s,
        }
        if self.evidence is not None:
            out["evidence"] = self.evidence
        return out


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
_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


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
        try:
            check.validate_semantics()
        except ValueError as exc:
            raise ScenarioError(f"{where}: {exc}") from exc
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
        if check.kind in ("relative_pose", "relative_translation", "contact_duration"):
            for body in (check.body_a, check.body_b):
                if body not in bodies:
                    raise ScenarioError(f"{where}: unknown body {body!r}")
        for phase in (check.phase, check.from_phase, check.to_phase):
            if phase is not None and phase not in phases:
                raise ScenarioError(f"{where}: unknown phase {phase!r}")
    event_specs = {event.name: event for event in acceptance.events}
    phase_specs = {phase.name: phase for phase in scenario.phases}
    phase_order = {phase.name: index for index, phase in enumerate(scenario.phases)}
    for check in acceptance.checks:
        where = f"acceptance check {check.name!r}"
        if check.kind == "relative_pose":
            if check.phase == "initial" or phase_specs[check.phase].is_reset:
                raise ScenarioError(
                    f"{where}: phase must name a timed scenario phase, got "
                    f"{check.phase!r}")
        if check.kind == "relative_translation":
            if check.to_phase == "initial" or phase_specs[check.to_phase].is_reset:
                raise ScenarioError(
                    f"{where}: to_phase must name a timed scenario phase, got "
                    f"{check.to_phase!r}")
            if check.from_phase == "initial":
                start = -1
            else:
                if phase_specs[check.from_phase].is_reset:
                    raise ScenarioError(
                        f"{where}: from_phase must be 'initial' or a timed phase, got "
                        f"{check.from_phase!r}")
                start = phase_order[check.from_phase]
            if start >= phase_order[check.to_phase]:
                raise ScenarioError(
                    f"{where}: from_phase {check.from_phase!r} must precede to_phase "
                    f"{check.to_phase!r}")
        if check.kind == "body_speed" and check.window == "max_over_phase":
            # The reset state takes no steps, so a max-over-phase speed watch there has no
            # duration evidence. Reject it rather than producing a zero-sample verdict.
            if check.phase == "initial" or phase_specs[check.phase].is_reset:
                raise ScenarioError(
                    f"{where}: body_speed with window='max_over_phase' needs a timed "
                    f"scenario phase, got {check.phase!r}")
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
             value: float | None, time_s: float | None = None,
             evidence: dict | None = None, units: str | None = None) -> CheckOutcome:
    report_units = units or check.units
    if value is not None and not math.isfinite(value):
        return CheckOutcome(check.name, check.kind, "INCONCLUSIVE", None,
                            f"{detail}; measured value is not finite", None, report_units,
                            "evaluate", time_s, evidence)
    return CheckOutcome(check.name, check.kind, status, ok, detail, value, report_units,
                        "evaluate", time_s, evidence)


def _near_upper(value: float, bound: float | None, fraction: float) -> bool:
    """A passing value within ``fraction`` of an upper bound is inconclusive.

    The band width is ``fraction * abs(bound)``, so a negative upper bound behaves
    symmetrically. A zero bound has no relative scale and therefore no band.
    """
    if fraction <= 0.0 or bound is None or bound == 0.0:
        return False
    return value <= bound and (bound - value) <= fraction * abs(bound)


def _near_lower(value: float, bound: float | None, fraction: float) -> bool:
    """A passing value within ``fraction`` of a signed lower bound is inconclusive.

    The band width is ``fraction * abs(bound)``. A zero bound has no relative scale, so its
    band width is zero: an exact zero is not reported as near-threshold.
    """
    if fraction <= 0.0 or bound is None or bound == 0.0:
        return False
    return value >= bound and (value - bound) <= fraction * abs(bound)


def _snapshot_relative(snapshot, body_a: str, body_b: str):
    try:
        entry_a = snapshot.bodies[body_a]
        entry_b = snapshot.bodies[body_b]
    except KeyError as exc:
        raise KeyError(f"boundary state has no body telemetry for {exc.args[0]!r}") from exc
    return relative_transform(entry_a["xpos"], entry_a["xquat"],
                              entry_b["xpos"], entry_b["xquat"])


def _phase_record(telemetry, name: str):
    for phase in telemetry.phases:
        if phase.name == name:
            return phase
    return None


def _coverage_reason(telemetry, phase_name: str, samples: int) -> str | None:
    """Reject a phase-scoped watch that did not see every integration state of the phase."""
    phase = _phase_record(telemetry, phase_name)
    if phase is None:
        return f"no recorded phase {phase_name!r} for the watch"
    if int(samples) <= 0:
        return f"the watch for phase {phase_name!r} recorded no integration state"
    if not phase.complete:
        return f"phase {phase_name!r} did not complete; every-step evidence is partial"
    if int(phase.actual_steps) != int(samples):
        return (f"phase {phase_name!r} took {phase.actual_steps} steps but the watch saw "
                f"{samples} integration states")
    return None


def _contact_coverage_reason(telemetry, samples: int) -> str | None:
    """A whole-run duration needs one state per integration step plus the reset state."""
    if not telemetry.phases:
        return "no recorded phases; the run has no duration evidence"
    incomplete = [phase.name for phase in telemetry.phases if not phase.complete]
    if incomplete:
        return f"phase(s) {incomplete} did not complete; duration evidence is partial"
    expected = 1 + sum(int(phase.actual_steps) for phase in telemetry.phases)
    if int(samples) != expected:
        return (f"duration watch saw {samples} integration states, expected {expected} "
                f"from the recorded phases")
    return None


def _signed_worst(lower_value: float, upper_value: float, lower: float,
                  upper: float) -> tuple[float, str]:
    """The passing sample closest to either bound, by bound-relative distance."""
    low_margin = (lower_value - lower) / abs(lower) if lower != 0.0 else lower_value - lower
    up_margin = (upper - upper_value) / abs(upper) if upper != 0.0 else upper - upper_value
    if low_margin <= up_margin:
        return lower_value, "lower"
    return upper_value, "upper"


def _evaluate_check(check: CheckSpec, telemetry, near_threshold_fraction: float = 0.0
                    ) -> CheckOutcome:
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

    if check.kind == "body_speed" and check.window == "end":
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

    if check.kind == "relative_pose":
        initial = telemetry.boundaries.get("initial")
        if initial is None:
            return _outcome(
                check, ok=None, status="INCONCLUSIVE",
                detail="no recorded initial boundary; the relative pose has no reference",
                value=None)
        try:
            p_ref, r_ref = _snapshot_relative(initial, check.body_a, check.body_b)
        except KeyError as exc:
            return _outcome(
                check, ok=None, status="INCONCLUSIVE",
                detail=f"missing body telemetry for {exc.args[0]}", value=None)
        if check.window == "max_over_phase":
            evidence = getattr(telemetry, "watch_evidence", {}).get(check.name)
            if evidence is None:
                return _outcome(
                    check, ok=None, status="INCONCLUSIVE",
                    detail=(f"no every-step pose watch for phase {check.phase!r}; the "
                            f"max-over-phase bound has no evidence"),
                    value=None)
            reason = _coverage_reason(telemetry, check.phase, evidence["samples"])
            if reason:
                return _outcome(check, ok=None, status="INCONCLUSIVE", detail=reason,
                                value=None)
            required = ("translation_m", "translation_time_s", "rotation_rad",
                        "rotation_time_s", "end_translation_m", "end_rotation_rad",
                        "end_time_s")
            if any(evidence.get(key) is None for key in required):
                return _outcome(
                    check, ok=None, status="INCONCLUSIVE",
                    detail=f"the pose watch for phase {check.phase!r} has incomplete evidence",
                    value=None)
            translation = float(evidence["translation_m"])
            rotation = float(evidence["rotation_rad"])
            time_translation = evidence["translation_time_s"]
            time_rotation = evidence["rotation_time_s"]
            end_translation = evidence["end_translation_m"]
            end_rotation = evidence["end_rotation_rad"]
            end_time = evidence["end_time_s"]
            samples = int(evidence["samples"])
        else:
            snapshot, reason = _boundary(telemetry, check.phase)
            if reason:
                return _outcome(check, ok=None, status="INCONCLUSIVE",
                                detail=reason["reason"], value=None)
            try:
                p_end, r_end = _snapshot_relative(snapshot, check.body_a, check.body_b)
            except KeyError as exc:
                return _outcome(
                    check, ok=None, status="INCONCLUSIVE",
                    detail=f"missing body telemetry for {exc.args[0]}", value=None)
            delta_p, rotation = pose_delta(p_ref, r_ref, p_end, r_end)
            translation = float(np.linalg.norm(delta_p))
            time_translation = time_rotation = snapshot.time_s
            end_translation, end_rotation, end_time = translation, rotation, snapshot.time_s
            samples = 1
        near_translation = _near_upper(translation, check.maximum, near_threshold_fraction)
        near_rotation = _near_upper(rotation, check.max_rotation_rad,
                                    near_threshold_fraction)
        evidence = {
            "kind": check.kind, "window": check.window, "phase": check.phase,
            "translation_m": translation, "translation_time_s": time_translation,
            "rotation_rad": rotation, "rotation_time_s": time_rotation,
            "end_translation_m": end_translation, "end_rotation_rad": end_rotation,
            "end_time_s": end_time,
            "bound_translation_m": check.maximum,
            "bound_rotation_rad": check.max_rotation_rad,
            "samples": samples,
            "near_threshold_fraction": near_threshold_fraction,
            "translation_near_threshold": near_translation,
            "rotation_near_threshold": near_rotation,
        }
        detail = (
            f"attached-local relative pose over {check.window} of {check.phase!r}: "
            f"translation {translation:.9g} m (bound {check.maximum:.9g} m), "
            f"rotation {rotation:.9g} rad (bound {check.max_rotation_rad:.9g} rad); "
            f"terminal {end_translation:.9g} m / {end_rotation:.9g} rad")
        if translation > check.maximum:
            return _outcome(check, ok=False, status="FAIL", detail=detail,
                            value=translation, time_s=time_translation, evidence=evidence)
        if rotation > check.max_rotation_rad:
            return _outcome(check, ok=False, status="FAIL", detail=detail,
                            value=rotation, time_s=time_rotation, evidence=evidence,
                            units="rad")
        if near_translation or near_rotation:
            band = " and ".join(name for name, flag in
                                (("translation", near_translation),
                                 ("rotation", near_rotation)) if flag)
            report_rotation = near_rotation and not near_translation
            return _outcome(
                check, ok=None, status="INCONCLUSIVE",
                detail=(f"{detail}; within the {near_threshold_fraction:.3g} near-threshold "
                        f"band of the {band} bound"),
                value=rotation if report_rotation else translation,
                time_s=time_rotation if report_rotation else time_translation,
                evidence=evidence, units="rad" if report_rotation else None)
        return _outcome(check, ok=True, status="PASS", detail=detail, value=translation,
                        time_s=time_translation, evidence=evidence)

    if check.kind == "relative_translation":
        reference_name = check.from_phase
        reference, reason = _boundary(telemetry, reference_name)
        if reason:
            return _outcome(check, ok=None, status="INCONCLUSIVE",
                            detail=reason["reason"], value=None)
        if check.window == "max_over_phase":
            evidence = getattr(telemetry, "watch_evidence", {}).get(check.name)
            if evidence is None:
                return _outcome(
                    check, ok=None, status="INCONCLUSIVE",
                    detail=(f"no every-step translation watch for phase {check.to_phase!r}; "
                            f"the max-over-phase bound has no evidence"),
                    value=None)
            reason = _coverage_reason(telemetry, check.to_phase, evidence["samples"])
            if reason:
                return _outcome(check, ok=None, status="INCONCLUSIVE", detail=reason,
                                value=None)
            required = ("min_m", "min_time_s", "max_m", "max_time_s", "terminal_m",
                        "terminal_time_s")
            if any(evidence.get(key) is None for key in required):
                return _outcome(
                    check, ok=None, status="INCONCLUSIVE",
                    detail=(f"the translation watch for phase {check.to_phase!r} has "
                            f"incomplete evidence"),
                    value=None)
            lower_value = float(evidence["min_m"])
            upper_value = float(evidence["max_m"])
            time_lower = evidence["min_time_s"]
            time_upper = evidence["max_time_s"]
            terminal = evidence["terminal_m"]
            terminal_time = evidence["terminal_time_s"]
            samples = int(evidence["samples"])
        else:
            end_snapshot, reason = _boundary(telemetry, check.to_phase)
            if reason:
                return _outcome(check, ok=None, status="INCONCLUSIVE",
                                detail=reason["reason"], value=None)
            try:
                p_from, _ = _snapshot_relative(reference, check.body_a, check.body_b)
                p_to, _ = _snapshot_relative(end_snapshot, check.body_a, check.body_b)
            except KeyError as exc:
                return _outcome(
                    check, ok=None, status="INCONCLUSIVE",
                    detail=f"missing body telemetry for {exc.args[0]}", value=None)
            if check.frame == "world":
                p_from = (np.asarray(reference.bodies[check.body_b]["xpos"],
                                     dtype=np.float64)
                          - np.asarray(reference.bodies[check.body_a]["xpos"],
                                       dtype=np.float64))
                p_to = (np.asarray(end_snapshot.bodies[check.body_b]["xpos"],
                                   dtype=np.float64)
                        - np.asarray(end_snapshot.bodies[check.body_a]["xpos"],
                                     dtype=np.float64))
            signed = float((p_to - p_from)[_AXIS_INDEX[check.axis]])
            lower_value = upper_value = terminal = signed
            time_lower = time_upper = terminal_time = end_snapshot.time_s
            samples = 1
        evidence = {
            "kind": check.kind, "window": check.window,
            "frame": check.frame or "body_a", "axis": check.axis,
            "from_phase": check.from_phase, "to_phase": check.to_phase,
            "min_m": lower_value, "min_time_s": time_lower,
            "max_m": upper_value, "max_time_s": time_upper,
            "terminal_m": terminal, "terminal_time_s": terminal_time,
            "lower_m": check.lower, "upper_m": check.upper,
            "drop_m": None,
            "samples": samples,
            "near_threshold_fraction": near_threshold_fraction,
        }
        world_z = (check.frame or "body_a") == "world" and check.axis == "z"

        def drop_suffix(value: float) -> str:
            if not world_z:
                return ""
            return f"; positive downward drop {max(0.0, -value):.9g} m"

        near_lower = _near_lower(lower_value, check.lower, near_threshold_fraction)
        near_upper = _near_upper(upper_value, check.upper, near_threshold_fraction)
        evidence["near_lower"] = near_lower
        evidence["near_upper"] = near_upper
        if lower_value < check.lower:
            value, time_s = lower_value, time_lower
            if world_z:
                evidence["drop_m"] = max(0.0, -value)
            detail = (f"signed {check.frame or 'body_a'} {check.axis} displacement "
                      f"{lower_value:.9g} m below the lower bound {check.lower:.9g} m "
                      f"(worst over {check.window} of {check.to_phase!r})"
                      f"{drop_suffix(value)}")
            return _outcome(check, ok=False, status="FAIL", detail=detail, value=value,
                            time_s=time_s, evidence=evidence)
        if upper_value > check.upper:
            value, time_s = upper_value, time_upper
            if world_z:
                evidence["drop_m"] = max(0.0, -value)
            detail = (f"signed {check.frame or 'body_a'} {check.axis} displacement "
                      f"{upper_value:.9g} m above the upper bound {check.upper:.9g} m "
                      f"(worst over {check.window} of {check.to_phase!r})"
                      f"{drop_suffix(value)}")
            return _outcome(check, ok=False, status="FAIL", detail=detail, value=value,
                            time_s=time_s, evidence=evidence)
        worst, _side = _signed_worst(lower_value, upper_value, check.lower, check.upper)
        worst_time = time_lower if _side == "lower" else time_upper
        if world_z:
            evidence["drop_m"] = max(0.0, -worst)
        detail = (f"signed {check.frame or 'body_a'} {check.axis} displacement "
                  f"{worst:.9g} m within [{check.lower:.9g}, {check.upper:.9g}] m "
                  f"(worst over {check.window} of {check.to_phase!r}); terminal "
                  f"{terminal:.9g} m{drop_suffix(worst)}")
        if near_lower or near_upper:
            band = " and ".join(name for name, flag in
                                (("lower", near_lower), ("upper", near_upper)) if flag)
            return _outcome(
                check, ok=None, status="INCONCLUSIVE",
                detail=(f"{detail}; within the {near_threshold_fraction:.3g} near-threshold "
                        f"band of the {band} bound"),
                value=worst, time_s=worst_time, evidence=evidence)
        return _outcome(check, ok=True, status="PASS", detail=detail, value=worst,
                        time_s=worst_time, evidence=evidence)

    if check.kind == "contact_duration":
        evidence = getattr(telemetry, "watch_evidence", {}).get(check.name)
        if evidence is None:
            return _outcome(
                check, ok=None, status="INCONCLUSIVE",
                detail=(f"no every-step summed-force watch for {check.body_a!r}/"
                        f"{check.body_b!r}; a zero duration would be fabricated"),
                value=None)
        reason = _contact_coverage_reason(telemetry, evidence["samples"])
        if reason:
            return _outcome(check, ok=None, status="INCONCLUSIVE", detail=reason, value=None)
        value = float(evidence["longest_s"])
        ok = value <= check.maximum
        near = _near_upper(value, check.maximum, near_threshold_fraction)
        evidence = dict(evidence)
        evidence["bound_s"] = check.maximum
        evidence["near_threshold_fraction"] = near_threshold_fraction
        evidence["near_threshold"] = near
        detail = (f"longest uninterrupted run above the summed normal-force threshold "
                  f"{check.force_threshold_n:.9g} N on {check.body_a!r}/{check.body_b!r} is "
                  f"{value:.9g} s ({evidence['run_samples']} integration states from "
                  f"{evidence['start_s']} s to {evidence['end_s']} s, "
                  f"{evidence['samples_above']} above of {evidence['samples']} states); "
                  f"bound {check.maximum:.9g} s")
        if not ok:
            return _outcome(check, ok=False, status="FAIL", detail=detail,
                            value=value, time_s=evidence["end_s"], evidence=evidence)
        if near:
            return _outcome(
                check, ok=None, status="INCONCLUSIVE",
                detail=(f"{detail}; within the {near_threshold_fraction:.3g} "
                        f"near-threshold band"),
                value=value, time_s=evidence["end_s"], evidence=evidence)
        return _outcome(check, ok=True, status="PASS", detail=detail,
                        value=value, time_s=evidence["end_s"], evidence=evidence)

    if check.kind == "body_speed" and check.window == "max_over_phase":
        evidence = getattr(telemetry, "watch_evidence", {}).get(check.name)
        if evidence is None:
            return _outcome(
                check, ok=None, status="INCONCLUSIVE",
                detail=(f"no every-step speed watch for {check.body!r} in "
                        f"{check.phase!r}"),
                value=None)
        reason = _coverage_reason(telemetry, check.phase, evidence["samples"])
        if reason:
            return _outcome(check, ok=None, status="INCONCLUSIVE", detail=reason, value=None)
        if evidence.get("time_s") is None or evidence.get("terminal_speed_m_s") is None:
            return _outcome(
                check, ok=None, status="INCONCLUSIVE",
                detail=f"the speed watch for phase {check.phase!r} has incomplete evidence",
                value=None)
        value = float(evidence["speed_m_s"])
        ok = value <= check.maximum
        near = _near_upper(value, check.maximum, near_threshold_fraction)
        evidence = dict(evidence)
        evidence["bound_m_s"] = check.maximum
        evidence["near_threshold_fraction"] = near_threshold_fraction
        evidence["near_threshold"] = near
        detail = (f"worst body speed {value:.9g} m/s over every step of {check.phase!r}; "
                  f"bound {check.maximum:.9g} m/s; terminal "
                  f"{evidence['terminal_speed_m_s']:.9g} m/s")
        if not ok:
            return _outcome(check, ok=False, status="FAIL", detail=detail, value=value,
                            time_s=evidence["time_s"], evidence=evidence)
        if near:
            return _outcome(
                check, ok=None, status="INCONCLUSIVE",
                detail=(f"{detail}; within the {near_threshold_fraction:.3g} "
                        f"near-threshold band"),
                value=value, time_s=evidence["time_s"], evidence=evidence)
        return _outcome(check, ok=True, status="PASS", detail=detail, value=value,
                        time_s=evidence["time_s"], evidence=evidence)

    return _outcome(check, ok=None, status="INCONCLUSIVE",
                    detail=f"unsupported check kind {check.kind!r}", value=None)


def evaluate(scenario: ScenarioSpec, acceptance: AcceptanceSpec, telemetry,
             *, compliance_reasons: list[dict] | None = None) -> Evaluation:
    """Evaluate every declared check plus numerical validity, with fixed precedence."""
    outcomes = [_evaluate_check(check, telemetry, acceptance.near_threshold_fraction)
                for check in acceptance.checks]
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
