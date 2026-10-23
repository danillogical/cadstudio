"""S0 diagnostics for the Pocky prototype: read a completed run, derive tables, compare.

Read-only by construction. This module never writes into a run directory, never rewrites
``summary.json``/checks/status and never replaces the generic evaluator: the generic
``cad physics run``/``cad physics replay`` path stays the only gate. Everything here is a
diagnostic view of evidence that is already bound and hashed.

Two evidence classes are kept apart on purpose:

* **every integration state** — ``summary.json`` check evidence (the pose/translation/speed
  watches and the per-step summed-force contact watches) plus ``summary["contacts"]`` and
  ``summary["metrics"]``. These are what the checks are evaluated from.
* **display rows** — ``contacts.csv`` is written on the sampling grid
  (``step_index % sample_every == 0``) and is display evidence only; it is never the gate.
  With ``sampling_interval_s == timestep_s`` it happens to be every step, which the tables
  state explicitly per metric.

CLI::

    python -m projects.pocky.physics.report --run out/mujoco-m5a/s0/runs/s0_f000 --out FILE
    python -m projects.pocky.physics.report --run ... --compare out/mujoco-m5a/s0/replay_s0_f000
    python -m projects.pocky.physics.report --conformance
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from cadkit.physics.scenario import (
    AcceptanceSpec,
    ScenarioSpec,
    load_acceptance,
    load_scenario,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PHYSICS_DIR = Path(__file__).resolve().parent
SCENARIO_DIR = PHYSICS_DIR / "scenarios"
OPTIONS_DIR = PHYSICS_DIR / "options"
ACCEPTANCE_PATH = PHYSICS_DIR / "s0_acceptance.json"

#: The plan's frozen S0 numbers, restated here so conformance is checked against the plan
#: rather than against the acceptance document it is meant to police.
PLAN_THRESHOLDS: dict[str, Any] = {
    "acceptance_id": "pocky_m5a1_s0",
    "near_threshold_fraction": 0.2,
    "validity_max_penetration_m": 0.0002,
    "penetration_max_m": 0.0002,
    "body_pose_max_m": 0.00020,
    "body_pose_max_rotation_rad": 0.20 * math.pi / 180.0,
    "body_drop_lower_m": -0.00010,
    "body_drop_upper_m": 0.00010,
    "contact_force_threshold_n": 0.0715,
    "contact_max_s": 0.20,
    "chassis_grounded_max_m": 0.001,
    "chassis_grounded_max_rotation_rad": 0.20 * math.pi / 180.0,
    "body_speed_max_m_s": 0.001,
    "contact_pairs": (
        ("body", "pusher"), ("body", "rod"), ("body", "crank"),
        ("lip", "pusher"), ("lip", "rod"), ("lip", "crank"),
    ),
    "settle_s": 3.0,
    "hold_s": 0.5,
    "seed": 0,
    "fixture": "pocky_prototype",
}

#: Base spring rate and the two approved sensitivity values (N/m).
BASE_SPRING_N_M = 500.0
SPRING_SENSITIVITY_N_M = (200.0, 1000.0)
#: Base and half timestep (s).
BASE_DT_S = 1.0e-3
HALF_DT_S = 5.0e-4
#: Contact and stop compliance stay at 2 ms at both timesteps.
CONTACT_TIMECONST_S = 0.002

#: The peg and lip geoms that can arrest the housing (plan 5.4 diagnostics).
ARREST_GEOMS = {
    "peg_pusher": ("peg_pusher_head", "peg_pusher_shaft"),
    "peg_button": ("peg_button_head", "peg_button_shaft"),
}
LIP_GEOM_PREFIXES = ("tooth", "lip", "rail")

#: Quiescence threshold for the sampled return-time diagnostic, in **each joint's own unit**.
#: Translational joints are metres per second and the crank joint is radians per second, so a
#: single numeric bound is only meaningful as a per-joint test; the report never compares a
#: rad/s value against a m/s label.
RETURN_SPEED = 1.0e-3


class ReportError(RuntimeError):
    """The run directory cannot support the requested diagnostic."""


# --------------------------------------------------------------------------- loading
def _read_json(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError(f"cannot read {path}: {exc}") from exc


@dataclass(frozen=True)
class RunEvidence:
    """One run directory, parsed into the pieces the diagnostics need."""

    run_dir: Path
    summary: dict
    contacts: tuple[dict[str, str], ...]
    trace_header: tuple[str, ...]
    trace_rows: tuple[tuple[str, ...], ...]

    @property
    def scenario_id(self) -> str:
        return str(self.summary.get("scenario", {}).get("id", self.run_dir.name))

    @property
    def status(self) -> str:
        return str(self.summary.get("status", "ERROR"))

    @property
    def sample_every(self) -> int:
        return int(self.summary.get("plan", {}).get("sample_every_steps", 1))

    @property
    def timestep_s(self) -> float:
        return float(self.summary.get("solver", {}).get("timestep_s",
                                                        self.summary.get("timestep_s", 0.0)))

    @property
    def sampling_interval_s(self) -> float:
        return self.timestep_s * self.sample_every

    @property
    def display_is_every_step(self) -> bool:
        return self.sample_every == 1

    def check(self, name: str) -> dict | None:
        for item in self.summary.get("checks", []):
            if item.get("name") == name:
                return item
        return None

    def evidence(self, name: str) -> dict:
        item = self.check(name)
        evidence = (item or {}).get("evidence")
        if not isinstance(evidence, dict):
            raise ReportError(f"run {self.run_dir} has no evidence for check {name!r}")
        return evidence


def read_run(run_dir: str | Path) -> RunEvidence:
    """Parse a completed run directory. Never mutates it."""
    run_dir = Path(run_dir)
    summary = _read_json(run_dir / "summary.json")
    contacts: list[dict[str, str]] = []
    contact_path = run_dir / "contacts.csv"
    if contact_path.exists():
        with contact_path.open(newline="", encoding="utf-8") as fh:
            contacts = list(csv.DictReader(fh))
    header: tuple[str, ...] = ()
    rows: list[tuple[str, ...]] = []
    trace_path = run_dir / "trace.csv"
    if trace_path.exists():
        with trace_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            header = tuple(next(reader))
            rows = [tuple(row) for row in reader]
    return RunEvidence(run_dir=run_dir, summary=summary, contacts=tuple(contacts),
                       trace_header=header, trace_rows=tuple(rows))


# ------------------------------------------------------------------ plan conformance
#: Scenario id suffix -> the CAD button fraction whose reset it must carry.
_FRACTIONS = {"f000": 0.0, "f025": 0.25, "f050": 0.5, "f075": 0.75, "f100": 1.0,
              "spring_low": 0.0, "spring_high": 0.0, "half_dt": 0.0}


def path_fraction(scenario_id: str) -> float | None:
    """CAD button fraction named by an S0 scenario id, or None if it names none."""
    prefix = "m5a1_s0_"
    if not scenario_id.startswith(prefix):
        return None
    return _FRACTIONS.get(scenario_id[len(prefix):])


def _cad_reset(fraction: float | None) -> dict[str, float] | None:
    """The CAD-derived reset for one fraction, from the actual helpers (no interpolation)."""
    if fraction is None:
        return None
    from projects.pocky.params import load_params  # local: keeps this module light
    from projects.pocky.physics.assembly import reset_state

    state = reset_state(load_params(), fraction)
    return {"crank_phi": state.crank_phi_rad, "rod_x": state.rod_x_m,
            "pusher_x": state.pusher_x_m}


def acceptance_conformance(acceptance: AcceptanceSpec) -> list[str]:
    """Compare a frozen acceptance with the plan's thresholds. Empty list means conforming.

    Runs against the typed spec, so unit conversions (degrees to radians), body ordering and
    the contact window are checked independently of the JSON that was loaded.
    """
    problems: list[str] = []

    def expect(name: str, actual: Any, expected: Any, tol: float = 1.0e-12) -> None:
        if isinstance(expected, float):
            if not isinstance(actual, (int, float)) or isinstance(actual, bool):
                problems.append(f"{name}: expected number {expected!r}, got {actual!r}")
            elif not math.isclose(float(actual), expected, rel_tol=0.0, abs_tol=tol):
                problems.append(f"{name}: expected {expected!r}, got {actual!r}")
        elif actual != expected:
            problems.append(f"{name}: expected {expected!r}, got {actual!r}")

    expect("acceptance_id", acceptance.acceptance_id, PLAN_THRESHOLDS["acceptance_id"])
    expect("near_threshold_fraction", acceptance.near_threshold_fraction,
           PLAN_THRESHOLDS["near_threshold_fraction"])
    expect("validity.max_penetration_m", acceptance.validity.max_penetration_m,
           PLAN_THRESHOLDS["validity_max_penetration_m"])
    for field in ("max_speed_m_s", "max_angular_speed_rad_s", "max_energy_j"):
        expect(f"validity.{field}", getattr(acceptance.validity, field), None)

    by_name = {c.name: c for c in acceptance.checks}
    expected_names = {
        "body_pose_retained", "body_drop", "chassis_grounded", "settled_body",
        "settled_lip", "penetration",
    } | {f"{a}_on_{b}" for a, b in PLAN_THRESHOLDS["contact_pairs"]}
    missing = sorted(expected_names - set(by_name))
    extra = sorted(set(by_name) - expected_names)
    if missing:
        problems.append(f"missing checks: {missing}")
    if extra:
        problems.append(f"unexpected checks: {extra}")

    pose = by_name.get("body_pose_retained")
    if pose is not None:
        expect("body_pose_retained.kind", pose.kind, "relative_pose")
        expect("body_pose_retained.body_a", pose.body_a, "body")
        expect("body_pose_retained.body_b", pose.body_b, "chassis")
        expect("body_pose_retained.phase", pose.phase, "hold")
        expect("body_pose_retained.window", pose.window, "max_over_phase")
        expect("body_pose_retained.max", pose.maximum, PLAN_THRESHOLDS["body_pose_max_m"])
        expect("body_pose_retained.max_rotation_rad", pose.max_rotation_rad,
               PLAN_THRESHOLDS["body_pose_max_rotation_rad"])
        expect("body_pose_retained.units", pose.units, "m")

    drop = by_name.get("body_drop")
    if drop is not None:
        expect("body_drop.kind", drop.kind, "relative_translation")
        # body_a=chassis, body_b=body: the signed value is (body - chassis), so a fall is
        # negative and max(0, -dz) is the positive downward drop the plan reports.
        expect("body_drop.body_a", drop.body_a, "chassis")
        expect("body_drop.body_b", drop.body_b, "body")
        expect("body_drop.from_phase", drop.from_phase, "initial")
        expect("body_drop.to_phase", drop.to_phase, "hold")
        expect("body_drop.axis", drop.axis, "z")
        expect("body_drop.frame", drop.frame, "world")
        expect("body_drop.lower", drop.lower, PLAN_THRESHOLDS["body_drop_lower_m"])
        expect("body_drop.upper", drop.upper, PLAN_THRESHOLDS["body_drop_upper_m"])
        expect("body_drop.window", drop.window, "max_over_phase")
        expect("body_drop.units", drop.units, "m")

    for a, b in PLAN_THRESHOLDS["contact_pairs"]:
        name = f"{a}_on_{b}"
        check = by_name.get(name)
        if check is None:
            continue
        expect(f"{name}.kind", check.kind, "contact_duration")
        expect(f"{name}.body_a", check.body_a, a)
        expect(f"{name}.body_b", check.body_b, b)
        expect(f"{name}.force_threshold_n", check.force_threshold_n,
               PLAN_THRESHOLDS["contact_force_threshold_n"])
        expect(f"{name}.max", check.maximum, PLAN_THRESHOLDS["contact_max_s"])
        expect(f"{name}.window", check.window, "end")
        expect(f"{name}.units", check.units, "s")
        for field in ("phase", "from_phase", "to_phase"):
            expect(f"{name}.{field}", getattr(check, field), None)

    grounded = by_name.get("chassis_grounded")
    if grounded is not None:
        expect("chassis_grounded.kind", grounded.kind, "relative_pose")
        expect("chassis_grounded.body_a", grounded.body_a, "chassis")
        expect("chassis_grounded.body_b", grounded.body_b, "floor_world")
        expect("chassis_grounded.phase", grounded.phase, "hold")
        expect("chassis_grounded.window", grounded.window, "max_over_phase")
        expect("chassis_grounded.max", grounded.maximum,
               PLAN_THRESHOLDS["chassis_grounded_max_m"])
        expect("chassis_grounded.max_rotation_rad", grounded.max_rotation_rad,
               PLAN_THRESHOLDS["chassis_grounded_max_rotation_rad"])
        # ``units`` labels the translation bound; the rotation bound is ``max_rotation_rad``
        # and is compared in radians above, so a degrees value cannot slip through either.
        expect("chassis_grounded.units", grounded.units, "m")

    for name, body in (("settled_body", "body"), ("settled_lip", "lip")):
        speed = by_name.get(name)
        if speed is None:
            continue
        expect(f"{name}.kind", speed.kind, "body_speed")
        expect(f"{name}.body", speed.body, body)
        expect(f"{name}.phase", speed.phase, "hold")
        expect(f"{name}.window", speed.window, "max_over_phase")
        expect(f"{name}.max", speed.maximum, PLAN_THRESHOLDS["body_speed_max_m_s"])
        expect(f"{name}.units", speed.units, "m/s")

    penetration = by_name.get("penetration")
    if penetration is not None:
        expect("penetration.kind", penetration.kind, "penetration_bound")
        expect("penetration.max", penetration.maximum,
               PLAN_THRESHOLDS["penetration_max_m"])
        expect("penetration.units", penetration.units, "m")

    if acceptance.events:
        problems.append("the S0 acceptance must declare no events")
    return problems


def scenario_conformance(scenario: ScenarioSpec, *, expect_dt: float) -> list[str]:
    """Check one S0 scenario against the plan's phases, sampling and seed."""
    problems: list[str] = []

    def expect(name: str, actual: Any, expected: Any) -> None:
        if isinstance(expected, float):
            if not isinstance(actual, (int, float)) or isinstance(actual, bool):
                problems.append(f"{name}: expected number {expected!r}, got {actual!r}")
            elif not math.isclose(float(actual), expected, rel_tol=0.0, abs_tol=1.0e-15):
                problems.append(f"{name}: expected {expected!r}, got {actual!r}")
        elif actual != expected:
            problems.append(f"{name}: expected {expected!r}, got {actual!r}")

    expect("fixture", scenario.fixture, PLAN_THRESHOLDS["fixture"])
    expect("seed", scenario.seed, PLAN_THRESHOLDS["seed"])
    expect("timestep_s", scenario.timestep_s, expect_dt)
    expect("sampling_interval_s", scenario.sampling_interval_s, expect_dt)
    kinds = [p.kind for p in scenario.phases]
    expect("phase kinds", tuple(kinds), ("reset", "settle", "hold"))
    if len(scenario.phases) == 3:
        expect("settle duration_s", scenario.phases[1].duration_s,
               PLAN_THRESHOLDS["settle_s"])
        expect("hold duration_s", scenario.phases[2].duration_s, PLAN_THRESHOLDS["hold_s"])
        reset = scenario.reset_phase
        # The strict loader normalizes ``initial`` to a name-sorted mapping.
        expect("reset joints", tuple(sorted(name for name, _ in reset.initial)),
               ("crank_phi", "pusher_x", "rod_x"))
        expected_reset = _cad_reset(path_fraction(scenario.scenario_id))
        if expected_reset is None:
            problems.append(f"scenario id {scenario.scenario_id!r} has no CAD fraction")
        else:
            for joint, value in reset.initial:
                want = expected_reset[joint]
                if not math.isclose(float(value), want, rel_tol=0.0, abs_tol=1.0e-15):
                    problems.append(f"reset {joint}: {value!r} != CAD helper {want!r}")
        for phase in scenario.timed_phases:
            if phase.actuator is not None or phase.effort is not None:
                problems.append(f"phase {phase.name!r} declares an actuator or effort; "
                                f"S0 runs zero external input")
    total_steps = sum(int(round((p.duration_s or 0.0) / float(scenario.timestep_s)))
                      for p in scenario.timed_phases)
    budgets = scenario.budgets
    if budgets.max_steps < total_steps:
        problems.append(f"max_steps {budgets.max_steps} < needed {total_steps}")
    if budgets.max_state_rows is None or budgets.max_state_rows < total_steps + 1:
        problems.append(f"max_state_rows {budgets.max_state_rows} < needed "
                        f"{total_steps + 1}")
    if budgets.max_trace_rows < total_steps + 1:
        problems.append(f"max_trace_rows {budgets.max_trace_rows} < needed "
                        f"{total_steps + 1} every-step rows")
    if budgets.max_sim_time_s + 1.0e-12 < total_steps * float(scenario.timestep_s):
        problems.append(f"max_sim_time_s {budgets.max_sim_time_s} < needed "
                        f"{total_steps * float(scenario.timestep_s)}")
    return problems


def options_conformance() -> list[str]:
    """Check the three sensitivity option files against the approved axis values."""
    import tomllib

    problems: list[str] = []
    expected = {
        "s0_spring_low.toml": (SPRING_SENSITIVITY_N_M[0], BASE_DT_S),
        "s0_spring_high.toml": (SPRING_SENSITIVITY_N_M[1], BASE_DT_S),
        "s0_half_dt.toml": (BASE_SPRING_N_M, HALF_DT_S),
    }
    for name, (spring, dt) in expected.items():
        path = OPTIONS_DIR / name
        if not path.exists():
            problems.append(f"missing options file {path}")
            continue
        table = tomllib.loads(path.read_text(encoding="utf-8"))
        if set(table) != {"spring_stiffness_n_m", "timestep_s"}:
            problems.append(f"{name}: unexpected keys {sorted(table)}")
            continue
        if not math.isclose(table["spring_stiffness_n_m"], spring, abs_tol=1.0e-12):
            problems.append(f"{name}: spring {table['spring_stiffness_n_m']!r} != {spring!r}")
        if not math.isclose(table["timestep_s"], dt, abs_tol=1.0e-15):
            problems.append(f"{name}: timestep {table['timestep_s']!r} != {dt!r}")
    for name in ("s0_f000", "s0_f025", "s0_f050", "s0_f075", "s0_f100"):
        path = OPTIONS_DIR / f"{name}.toml"
        if path.exists():
            problems.append(f"{path} exists; base cases use the canonical empty lock")
    return problems


# -------------------------------------------------------------------- diagnostics
def _unit_vector(quat: Sequence[float]) -> tuple[float, float, float, float]:
    norm = math.sqrt(sum(float(v) * float(v) for v in quat))
    if not (math.isfinite(norm) and norm > 0.0):
        raise ReportError(f"non-finite or zero quaternion {quat!r}")
    return tuple(float(v) / norm for v in quat)  # type: ignore[return-value]


def _quat_angle(a: Sequence[float], b: Sequence[float]) -> float:
    """Angle in radians between two orientation quaternions (wxyz)."""
    qa, qb = _unit_vector(a), _unit_vector(b)
    dot = abs(sum(x * y for x, y in zip(qa, qb)))
    return 2.0 * math.acos(min(1.0, max(-1.0, dot)))


def _column(run: RunEvidence, name: str) -> int:
    try:
        return run.trace_header.index(name)
    except ValueError as exc:
        raise ReportError(f"trace.csv has no column {name!r}") from exc


def _float(row: Sequence[str], index: int) -> float:
    return float(row[index])


def _phase_span(run: RunEvidence, phase: str) -> tuple[int, int]:
    """Trace-row index range (inclusive) for a phase name."""
    phase_index = _column(run, "phase")
    indices = [i for i, row in enumerate(run.trace_rows) if row[phase_index] == phase]
    if not indices:
        raise ReportError(f"trace.csv has no rows for phase {phase!r}")
    return indices[0], indices[-1]


def _trace_value(run: RunEvidence, phase: str, column: str,
                 reducer) -> tuple[float, float]:
    """Worst value and its time over one phase, from display rows."""
    col = _column(run, column)
    time_col = _column(run, "state_time_s")
    start, end = _phase_span(run, phase)
    worst: float | None = None
    worst_time = math.nan
    for row in run.trace_rows[start:end + 1]:
        value = _float(row, col)
        if not math.isfinite(value):
            continue
        if worst is None or reducer(value, worst):
            worst, worst_time = value, _float(row, time_col)
    if worst is None:
        raise ReportError(f"no finite {column} samples in phase {phase!r}")
    return worst, worst_time


def _contacts_by_state(run: RunEvidence) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in run.contacts:
        grouped[row["state_time_s"]].append(row)
    return grouped


def _pair_load(rows: Iterable[dict[str, str]], a: str, b: str) -> float:
    """Sum of normal forces over every geom pair between two bodies in one state."""
    total = 0.0
    for row in rows:
        if {row["body_a"], row["body_b"]} == {a, b}:
            total += float(row["normal_force_n"])
    return total


def _geom_load(rows: Iterable[dict[str, str]], bodies: Sequence[str],
               geom_prefixes: Sequence[str],
               against: Sequence[str]) -> dict:
    """Peak per-geom normal force between one body's named geoms and a set of other bodies.

    ``rows`` are display rows (one per geom pair per sampled state), so the row count is a
    count of sampled contacts, not distinct geoms: a peg head held against the housing for
    3500 states is 3500 rows. Only contacts with ``against`` are counted, because a peg
    inside its own slot drives the mechanism and is not an arrest.
    """
    peak = 0.0
    count = 0
    partners: set[str] = set()
    for row in rows:
        for body, geom, other in ((row["body_a"], row["geom_a"], row["body_b"]),
                                  (row["body_b"], row["geom_b"], row["body_a"])):
            if body not in bodies or other not in against:
                continue
            if not any(geom.startswith(prefix) for prefix in geom_prefixes):
                continue
            force = float(row["normal_force_n"])
            peak = max(peak, force)
            if force > 0.0:
                count += 1
                partners.add(f"{other}/{geom}")
    return {"peak_force_n": peak, "contact_rows": count, "against": sorted(partners)}


def diagnostics(run_dir: str | Path) -> dict:
    """Derive the S0 diagnostic tables for one completed run."""
    run = read_run(run_dir)
    summary = run.summary
    phases = [
        {"name": p["name"], "kind": p["kind"], "requested_s": p["requested_duration_s"],
         "actual_s": p["actual_duration_s"], "steps": p["actual_steps"],
         "complete": p["complete"]}
        for p in summary.get("phases", [])
    ]
    checks = [
        {"name": c["name"], "kind": c["kind"], "status": c["status"],
         "value": c.get("value"), "units": c.get("units"), "time_s": c.get("time_s"),
         "detail": c.get("detail")}
        for c in summary.get("checks", [])
    ]

    housing: dict[str, Any] = {}
    if run.check("body_pose_retained") is not None:
        pose = run.evidence("body_pose_retained")
        housing["relative_pose"] = {
            "translation_m": pose["translation_m"],
            "translation_time_s": pose["translation_time_s"],
            "rotation_deg": math.degrees(pose["rotation_rad"]),
            "rotation_time_s": pose["rotation_time_s"],
            "end_translation_m": pose["end_translation_m"],
            "end_rotation_deg": math.degrees(pose["end_rotation_rad"]),
            "samples": pose["samples"],
            "source": "summary check evidence, every integration state of the hold",
        }
    if run.check("body_drop") is not None:
        drop = run.evidence("body_drop")
        housing["drop"] = {
            "signed_min_m": drop["min_m"], "signed_min_time_s": drop["min_time_s"],
            "signed_max_m": drop["max_m"], "signed_max_time_s": drop["max_time_s"],
            "terminal_m": drop["terminal_m"], "terminal_time_s": drop["terminal_time_s"],
            "downward_drop_m": drop.get("drop_m"),
            "samples": drop["samples"],
            "source": "summary check evidence, every integration state of the hold",
        }
    grounded: dict[str, Any] = {}
    if run.check("chassis_grounded") is not None:
        pose = run.evidence("chassis_grounded")
        grounded = {
            "translation_m": pose["translation_m"],
            "translation_time_s": pose["translation_time_s"],
            "rotation_deg": math.degrees(pose["rotation_rad"]),
            "rotation_time_s": pose["rotation_time_s"],
            "samples": pose["samples"],
            "source": "summary check evidence, every integration state of the hold",
        }

    pairs = []
    for a, b in PLAN_THRESHOLDS["contact_pairs"]:
        name = f"{a}_on_{b}"
        if run.check(name) is None:
            continue
        evidence = run.evidence(name)
        pairs.append({
            "check": name, "body_a": a, "body_b": b,
            "threshold_n": evidence["threshold_n"],
            "longest_s": evidence["longest_s"],
            "start_s": evidence["start_s"], "end_s": evidence["end_s"],
            "samples_above": evidence["samples_above"], "samples": evidence["samples"],
            "run_samples": evidence["run_samples"],
            "peak_force_n": evidence["peak_force_n"],
            "terminal_force_n": evidence["terminal_force_n"],
            "status": (run.check(name) or {}).get("status"),
            "source": "summary check evidence, per-step summed normal force, whole run",
        })

    speeds = []
    for name, body in (("settled_body", "body"), ("settled_lip", "lip")):
        if run.check(name) is None:
            continue
        evidence = run.evidence(name)
        speeds.append({
            "check": name, "body": body,
            "worst_speed_m_s": evidence["speed_m_s"],
            "worst_time_s": evidence["time_s"],
            "terminal_speed_m_s": evidence["terminal_speed_m_s"],
            "samples": evidence["samples"],
            "source": "summary check evidence, every integration state of the hold",
        })

    grouped = _contacts_by_state(run)
    state_keys = sorted(grouped, key=float)
    floor_loads = [_pair_load(grouped[key], "chassis", "floor_world") for key in state_keys]
    masses = {name: body["mass_kg"] for name, body in summary["solver"]["bodies"].items()}
    gravity = float(summary["physical_inputs"]["gravity_m_s2"][2])
    hanging = ("body", "lip", "chassis", "crank", "rod", "pusher")
    hanging_weight = sum(abs(masses.get(name, 0.0) * gravity) for name in hanging)
    floor = {
        "max_n": max(floor_loads) if floor_loads else None,
        "mean_n": (sum(floor_loads) / len(floor_loads)) if floor_loads else None,
        "terminal_n": floor_loads[-1] if floor_loads else None,
        "hanging_weight_n": hanging_weight,
        "terminal_fraction_of_weight": (
            floor_loads[-1] / hanging_weight if floor_loads and hanging_weight else None),
        "states": len(floor_loads),
        "max_contacts_per_state": max((len(v) for v in grouped.values()), default=0),
        "source": ("contacts.csv display rows on the sampling grid"
                   + (" (every step here)" if run.display_is_every_step else
                      f" (every {run.sample_every} steps)")),
    }

    # An arrest is a peg or lip feature loading the housing, not the crank pin inside its own
    # pusher slot: those drive contacts are reported separately as ``drive``.
    housing_bodies = ("body", "lip")
    arrests = {}
    for name, prefixes in ARREST_GEOMS.items():
        owners = ("crank", "rod", "pusher")
        item = _geom_load(run.contacts, owners, prefixes, housing_bodies)
        item["drive"] = _geom_load(run.contacts, owners, prefixes,
                                   ("pusher", "rod", "chassis", "crank"))
        arrests[name] = item
    lip_item = _geom_load(run.contacts, ("lip",), LIP_GEOM_PREFIXES,
                          housing_bodies + ("chassis",))
    arrests["lip_rail"] = lip_item
    for item in arrests.values():
        item["source"] = ("contacts.csv display rows on the sampling grid"
                          + (" (every step here)" if run.display_is_every_step else
                             f" (every {run.sample_every} steps)"))
        drive = item.get("drive")
        if drive is not None:
            drive["source"] = item["source"]

    # What actually holds the housing up at the end of the hold, as display rows for the
    # single terminal hold state. Diagnostic only: the structural predicates are the checks.
    support = []
    if state_keys:
        last = grouped[state_keys[-1]]
        per_geom: dict[tuple[str, str], float] = defaultdict(float)
        for row in last:
            force = float(row["normal_force_n"])
            if force <= 0.0:
                continue
            for body, other, other_geom in (
                    (row["body_a"], row["body_b"], row["geom_b"]),
                    (row["body_b"], row["body_a"], row["geom_a"])):
                if body == "body":
                    per_geom[(other, other_geom)] += force
        support = [{"support": f"{other}/{other_geom}", "normal_force_n": force}
                   for (other, other_geom), force in sorted(per_geom.items(),
                                                            key=lambda kv: -kv[1])[:10]]
    housing_support = {
        "state_time_s": float(state_keys[-1]) if state_keys else None,
        "rows": support,
        "source": ("contacts.csv display rows for the single terminal hold state"
                   + (" (every step here)" if run.display_is_every_step else "")),
    }

    return_time: dict[str, Any] = {}
    if run.trace_rows:
        time_col = _column(run, "state_time_s")
        # One quiescence test per joint, in that joint's own unit: a crank angle rate is rad/s
        # and a carriage rate is m/s, so they are never ranked against each other.
        joints = []
        overall = 0.0
        after = 0.0
        for column in (name for name in run.trace_header if name.startswith("qvel:")):
            label = column.split(":", 1)[1]
            unit = "rad/s" if "(rad/s)" in label else "m/s"
            name = label.split(" (", 1)[0]
            index = _column(run, column)
            first_quiet = 0
            for position in range(len(run.trace_rows) - 1, -1, -1):
                if abs(_float(run.trace_rows[position], index)) > RETURN_SPEED:
                    first_quiet = position + 1
                    break
            quiet_at = (_float(run.trace_rows[first_quiet], time_col)
                        if first_quiet < len(run.trace_rows) else None)
            before = (_float(run.trace_rows[first_quiet - 1], time_col)
                      if first_quiet else 0.0)
            joints.append({"joint": name, "units": unit,
                           "peak": max(abs(_float(row, index)) for row in run.trace_rows),
                           "terminal": abs(_float(run.trace_rows[-1], index)),
                           "time_s": quiet_at, "after_time_s": before})
            overall = max(overall, quiet_at if quiet_at is not None else math.inf)
            after = max(after, before)
        return_time = {
            "threshold_per_joint_unit": RETURN_SPEED,
            "units": sorted({j["units"] for j in joints}),
            "time_s": None if math.isinf(overall) else overall,
            "after_time_s": after,
            "joints": joints,
            "source": ("trace.csv display rows; each joint is tested against "
                       f"{RETURN_SPEED:g} in its own unit and the run is quiescent at the "
                       "last sample any joint is above it, plus one sample, so it is "
                       "resolved to the sampling interval"
                       + (" (every step here)" if run.display_is_every_step else "")),
        }

    metrics = summary.get("metrics", {})
    return {
        "run_dir": str(run.run_dir),
        "scenario_id": run.scenario_id,
        "run_id": summary.get("run_id"),
        "status": run.status,
        "validity": summary.get("validity"),
        "detail": summary.get("detail"),
        "timestep_s": run.timestep_s,
        "sampling_interval_s": run.sampling_interval_s,
        "sample_every_steps": run.sample_every,
        "scene": summary.get("scene", {}),
        "acceptance": summary.get("acceptance", {}),
        "assembly_options": summary.get("assembly_options"),
        "assembly_options_sha256": summary.get("assembly_options_sha256"),
        "phases": phases,
        "checks": checks,
        "housing": housing,
        "chassis": grounded,
        "body_pairs": pairs,
        "speeds": speeds,
        "floor_load": floor,
        "housing_support": housing_support,
        "arrests": arrests,
        "return_time": return_time,
        "peak_metrics": {
            "peak_speed_m_s": metrics.get("peak_speed_m_s"),
            "peak_penetration_m": metrics.get("peak_penetration_m"),
            "initial_penetration_m": metrics.get("initial_penetration_m"),
            "peak_contact_force_n": metrics.get("peak_contact_force_n"),
            "source": "summary per-step maxima, every integration state",
        },
        "penetration_pairs": sorted(
            ({"body_a": c["body_a"], "geom_a": c["geom_a"], "body_b": c["body_b"],
              "geom_b": c["geom_b"], "max_penetration_m": c["max_penetration_m"],
              "max_normal_force_n": c["max_normal_force_n"], "samples": c["samples"]}
             for c in summary.get("contacts", [])),
            key=lambda item: item["max_penetration_m"], reverse=True)[:5],
        "coverage": {
            "trace_rows": summary.get("telemetry", {}).get("trace_rows"),
            "state_rows": summary.get("telemetry", {}).get("state_rows"),
            "contact_rows": summary.get("telemetry", {}).get("contact_rows"),
            "contact_pairs": summary.get("telemetry", {}).get("contact_pairs"),
            "planned_trace_rows": summary.get("plan", {}).get("planned_trace_rows"),
            "planned_state_rows": summary.get("plan", {}).get("state_rows"),
            "checkpoints": summary.get("state_archive", {}).get("checkpoints"),
            "source": "summary telemetry/plan/state_archive",
        },
    }


# --------------------------------------------------------------------- rendering
def _fmt(value: Any, digits: int = 6) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "n/a"
        return f"{value:.{digits}g}"
    return str(value)


def render_markdown(diag: dict, *, title: str | None = None) -> str:
    """Render the diagnostic tables. Never contains a status the evaluator did not set."""
    lines: list[str] = []
    heading = title or f"S0 diagnostics: {diag['scenario_id']}"
    lines += [f"# {heading}", ""]
    lines += [
        f"Status (generic evaluator): **{diag['status']}**  ",
        f"Numerically valid: `{_fmt((diag.get('validity') or {}).get('ok'))}`  ",
        f"Run: `{diag['run_dir']}`  ",
        f"Timestep: `{_fmt(diag['timestep_s'])}` s; sampling: "
        f"`{_fmt(diag['sampling_interval_s'])}` s "
        f"(every {diag['sample_every_steps']} step(s))  ",
        f"Scene hash: `{(diag.get('scene') or {}).get('scene_hash', 'n/a')}`  ",
        f"Acceptance hash: `{(diag.get('acceptance') or {}).get('hash', 'n/a')}`  ",
        f"Assembly options: `{_fmt(diag.get('assembly_options_sha256'))}`  ",
        "",
    ]
    validity = diag.get("validity") or {}
    if validity.get("reasons"):
        lines += ["## Validity", "", "| stage | time s | reason |", "|---|---|---|"]
        for reason in validity["reasons"]:
            lines.append(f"| {reason.get('stage', '')} | {_fmt(reason.get('time_s'))} | "
                         f"{reason.get('reason', '')} |")
        lines.append("")

    lines += ["## Phases", "",
              "| phase | kind | requested s | actual s | steps | complete |",
              "|---|---|---|---|---|---|"]
    for phase in diag["phases"]:
        lines.append(f"| {phase['name']} | {phase['kind']} | {_fmt(phase['requested_s'])} | "
                     f"{_fmt(phase['actual_s'])} | {phase['steps']} | "
                     f"{_fmt(phase['complete'])} |")
    lines.append("")

    lines += ["## Checks (bound, generic)", "",
              "| check | kind | status | value | units | worst time s |",
              "|---|---|---|---|---|---|"]
    for check in diag["checks"]:
        lines.append(f"| {check['name']} | {check['kind']} | {check['status']} | "
                     f"{_fmt(check['value'])} | {check['units']} | {_fmt(check['time_s'])} |")
    lines.append("")

    housing = diag.get("housing") or {}
    if housing:
        lines += ["## Housing (body vs chassis)", "",
                  "| metric | value | worst time s | evidence |", "|---|---|---|---|"]
        pose = housing.get("relative_pose")
        if pose:
            lines.append(f"| attached-local relative translation | "
                         f"{_fmt(pose['translation_m'])} m | "
                         f"{_fmt(pose['translation_time_s'])} | {pose['source']} |")
            lines.append(f"| attached-local relative rotation | "
                         f"{_fmt(pose['rotation_deg'])} deg | "
                         f"{_fmt(pose['rotation_time_s'])} | {pose['source']} |")
            lines.append(f"| end-boundary translation | {_fmt(pose['end_translation_m'])} m | "
                         f"n/a | {pose['source']} |")
        drop = housing.get("drop")
        if drop:
            lines.append(f"| signed world-z change, min | {_fmt(drop['signed_min_m'])} m | "
                         f"{_fmt(drop['signed_min_time_s'])} | {drop['source']} |")
            lines.append(f"| signed world-z change, max | {_fmt(drop['signed_max_m'])} m | "
                         f"{_fmt(drop['signed_max_time_s'])} | {drop['source']} |")
            lines.append(f"| positive downward drop max(0,-dz) | "
                         f"{_fmt(drop['downward_drop_m'])} m | n/a | {drop['source']} |")
            lines.append(f"| terminal signed change | {_fmt(drop['terminal_m'])} m | "
                         f"{_fmt(drop['terminal_time_s'])} | {drop['source']} |")
        lines.append("")

    chassis = diag.get("chassis") or {}
    if chassis:
        lines += ["## Chassis (vs analytic floor)", "",
                  "| metric | value | worst time s |", "|---|---|---|",
                  f"| relative translation | {_fmt(chassis['translation_m'])} m | "
                  f"{_fmt(chassis['translation_time_s'])} |",
                  f"| relative rotation | {_fmt(chassis['rotation_deg'])} deg | "
                  f"{_fmt(chassis['rotation_time_s'])} |", ""]

    if diag["body_pairs"]:
        lines += ["## Body-pair summed contact force (whole run, per step)", "",
                  "| check | threshold N | longest s | start s | end s | states above/total "
                  "| peak N | terminal N | status |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for pair in diag["body_pairs"]:
            lines.append(
                f"| {pair['check']} | {_fmt(pair['threshold_n'])} | "
                f"{_fmt(pair['longest_s'])} | {_fmt(pair['start_s'])} | "
                f"{_fmt(pair['end_s'])} | {pair['samples_above']}/{pair['samples']} | "
                f"{_fmt(pair['peak_force_n'])} | {_fmt(pair['terminal_force_n'])} | "
                f"{pair['status']} |")
        lines.append("")

    if diag["speeds"]:
        lines += ["## Hold speeds", "",
                  "| body | worst m/s | worst time s | terminal m/s |", "|---|---|---|---|"]
        for speed in diag["speeds"]:
            lines.append(f"| {speed['body']} | {_fmt(speed['worst_speed_m_s'])} | "
                         f"{_fmt(speed['worst_time_s'])} | "
                         f"{_fmt(speed['terminal_speed_m_s'])} |")
        lines.append("")

    floor = diag.get("floor_load") or {}
    if floor:
        lines += ["## Chassis floor load", "",
                  "| metric | value |", "|---|---|",
                  f"| peak summed normal force | {_fmt(floor['max_n'])} N |",
                  f"| mean summed normal force | {_fmt(floor['mean_n'])} N |",
                  f"| terminal summed normal force | {_fmt(floor['terminal_n'])} N |",
                  f"| hanging-group weight (6 bodies) | {_fmt(floor['hanging_weight_n'])} N |",
                  f"| terminal fraction of that weight | "
                  f"{_fmt(floor['terminal_fraction_of_weight'], 4)} |",
                  f"| max contact geoms in one state | {floor['max_contacts_per_state']} |",
                  f"| states in contacts.csv | {floor['states']} |", ""]

    support = diag.get("housing_support") or {}
    if support.get("rows"):
        lines += [f"## Body support at the terminal hold state "
                  f"({_fmt(support['state_time_s'])} s)", "",
                  "| support | normal force N |", "|---|---|"]
        lines += [f"| {row['support']} | {_fmt(row['normal_force_n'])} |"
                  for row in support["rows"]]
        lines += ["", f"Source: {support['source']}.", ""]

    arrests = diag.get("arrests") or {}
    if arrests:
        lines += ["## Peg-head and lip-rail contacts", "",
                  "Housing contacts only: a peg loading the body or lip is an arrest, while "
                  "the same peg inside its own slot is the normal drive path.", "",
                  "| probe | housing peak N | housing rows | against | drive peak N |",
                  "|---|---|---|---|---|"]
        for name, item in arrests.items():
            drive = item.get("drive") or {}
            lines.append(f"| {name} | {_fmt(item['peak_force_n'])} | "
                         f"{item['contact_rows']} | "
                         f"{', '.join(item.get('against', [])) or 'n/a'} | "
                         f"{_fmt(drive.get('peak_force_n'))} |")
        lines.append("")

    ret = diag.get("return_time") or {}
    if ret:
        lines += ["## Return time (diagnostic)", "",
                  f"Each joint is tested against "
                  f"`{_fmt(ret['threshold_per_joint_unit'])}` in its **own** unit "
                  f"({', '.join(ret['units'])}). Last sampled state with any joint above it: "
                  f"`{_fmt(ret['after_time_s'])}` s; quiescent from "
                  f"`{_fmt(ret['time_s'])}` s.  ",
                  "", "| joint | units | peak | terminal | quiet from s | last above s |",
                  "|---|---|---|---|---|---|"]
        for joint in ret["joints"]:
            lines.append(f"| {joint['joint']} | {joint['units']} | {_fmt(joint['peak'])} | "
                         f"{_fmt(joint['terminal'])} | {_fmt(joint['time_s'])} | "
                         f"{_fmt(joint['after_time_s'])} |")
        lines += ["", f"Source: {ret['source']}.", ""]

    peaks = diag.get("peak_metrics") or {}
    if peaks:
        lines += ["## Per-step maxima", "",
                  "| metric | value |", "|---|---|",
                  f"| peak speed | {_fmt(peaks['peak_speed_m_s'])} m/s |",
                  f"| peak penetration | {_fmt(peaks['peak_penetration_m'])} m |",
                  f"| initial penetration | {_fmt(peaks['initial_penetration_m'])} m |",
                  f"| peak contact force | {_fmt(peaks['peak_contact_force_n'])} N |", ""]
        if diag["penetration_pairs"]:
            lines += ["| pair | max penetration m | max force N | samples |",
                      "|---|---|---|---|"]
            for item in diag["penetration_pairs"]:
                lines.append(f"| {item['body_a']}/{item['geom_a']} vs "
                             f"{item['body_b']}/{item['geom_b']} | "
                             f"{_fmt(item['max_penetration_m'])} | "
                             f"{_fmt(item['max_normal_force_n'])} | {item['samples']} |")
            lines.append("")

    coverage = diag.get("coverage") or {}
    if coverage:
        lines += ["## Coverage", "",
                  "| item | value |", "|---|---|",
                  f"| trace rows / planned | {coverage['trace_rows']} / "
                  f"{coverage['planned_trace_rows']} |",
                  f"| state rows / planned | {coverage['state_rows']} / "
                  f"{coverage['planned_state_rows']} |",
                  f"| contact rows | {coverage['contact_rows']} |",
                  f"| contact pairs | {coverage['contact_pairs']} |"]
        checkpoints = coverage.get("checkpoints") or {}
        for name in ("initial_row", "post_settle_row", "terminal_row", "rows"):
            if name in checkpoints:
                lines.append(f"| checkpoint {name} | {checkpoints[name]} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------- comparison
def compare(source_dir: str | Path, replay_dir: str | Path) -> dict:
    """Compare a source run with its replay using the replay's own bound comparison.

    The replay directory carries ``replay.json`` written by the generic replay command, which
    already re-evaluates every check from the replayed telemetry and compares worst-sample
    values/times within one compiled sample interval and the declared tolerances. This
    function never recomputes a verdict: it surfaces that comparison and adds the per-check
    deltas when the replay directory also carries the replayed summary. A replay that does
    not reproduce, changes status, or has non-empty evaluation differences is INCONCLUSIVE.
    """
    source = read_run(source_dir)
    replay_dir = Path(replay_dir)
    report = _read_json(replay_dir / "replay.json")
    # The generic replay writes both ``status`` and ``replay_status``; accept either so a
    # hand-built comparison document cannot silently read as a missing status.
    replay_status = report.get("replay_status", report.get("status"))
    interval = source.sampling_interval_s
    replayed_summary = replay_dir / "replay_source" / "run" / "summary.json"
    replay_checks: dict[str, dict] = {}
    per_check_available = replayed_summary.exists()
    if per_check_available:
        replay_checks = {c["name"]: c for c in
                         _read_json(replayed_summary).get("checks", [])}
    out: dict[str, Any] = {
        "source": str(source.run_dir),
        "replay": str(replay_dir),
        "replay_status": replay_status,
        "source_status": report.get("source_status"),
        "reproduced": report.get("reproduced"),
        "state_comparison": report.get("state_comparison"),
        "post_settle_continuation": report.get("post_settle_continuation"),
        "evaluation_comparison": report.get("evaluation_comparison"),
        "tolerances": report.get("tolerances"),
        "sample_interval_s": interval,
        "per_check_available": per_check_available,
        "checks": [],
        "inconclusive": [],
    }
    # Rows exist only when the replay actually produced replayed check evidence. Emitting
    # rows with ``replay_status: None`` would read as "the replay disagreed on every check".
    for check in source.summary.get("checks", []) if per_check_available else []:
        name = check["name"]
        other = replay_checks.get(name)
        row = {"name": name, "source_status": check.get("status"),
               "replay_status": (other or {}).get("status"),
               "source_value": check.get("value"),
               "replay_value": (other or {}).get("value"),
               "source_time_s": check.get("time_s"),
               "replay_time_s": (other or {}).get("time_s")}
        if other is not None and check.get("value") is not None:
            row["value_delta"] = abs(float(other.get("value", math.nan))
                                     - float(check["value"]))
        if (other is not None and row["source_time_s"] is not None
                and row["replay_time_s"] is not None):
            row["time_delta_s"] = abs(float(row["replay_time_s"])
                                      - float(row["source_time_s"]))
        out["checks"].append(row)
        if other is None:
            out["inconclusive"].append(
                f"{name}: the replayed run has no check named {name!r}")
            continue
        if row["source_status"] != row["replay_status"]:
            out["inconclusive"].append(
                f"{name}: status changed {row['source_status']} -> {row['replay_status']}")
        if "time_delta_s" in row and row["time_delta_s"] > interval + 1.0e-12:
            out["inconclusive"].append(
                f"{name}: worst time differs by {row['time_delta_s']:.9g} s, above one "
                f"sample interval {interval:.9g} s")
    if report.get("reproduced") is not True:
        out["inconclusive"].append(f"reproduced is {report.get('reproduced')!r}, not True")
    if replay_status != report.get("source_status"):
        out["inconclusive"].append(
            f"replay status {replay_status!r} != source "
            f"{report.get('source_status')!r}")
    if report.get("source_status") != source.status:
        out["inconclusive"].append(
            f"replay.json names source status {report.get('source_status')!r}, but the "
            f"source run is {source.status!r}")
    if not (report.get("evaluation_comparison") or {}).get("ok", False):
        out["inconclusive"].append("the generic evaluation comparison did not match")
    return out


def render_comparison(cmp: dict) -> str:
    lines = [
        "# S0 replay comparison", "",
        f"Source: `{cmp['source']}`  ",
        f"Replay: `{cmp['replay']}`  ",
        f"Replay status: **{cmp['replay_status']}** (source {cmp['source_status']}); "
        f"reproduced `{_fmt(cmp['reproduced'])}`  ",
        f"Sample interval: `{_fmt(cmp['sample_interval_s'])}` s  ",
        f"Full state max abs diff: "
        f"`{_fmt((cmp.get('state_comparison') or {}).get('max_abs_diff'))}`  ",
        f"Post-settle continuation ok: "
        f"`{_fmt((cmp.get('post_settle_continuation') or {}).get('ok'))}`  ",
        f"Evaluation comparison ok: "
        f"`{_fmt((cmp.get('evaluation_comparison') or {}).get('ok'))}`  ",
        "",
        "The replay status is the source status re-derived from the replayed telemetry, not a "
        "separate verdict. An INCONCLUSIVE source stays INCONCLUSIVE on replay when the "
        "validity breach reproduces; that is reproduction, not a replay failure.",
        "",
    ]
    if not cmp["per_check_available"]:
        lines += [
            "The generic replay command does not write a replayed `summary.json`; it reports "
            "its per-check comparison in `replay.json`. The per-check table below is therefore "
            "omitted and the authoritative comparison is `evaluation_comparison`, which "
            "compares every check value, worst-sample time, metric and validity reason.",
            "",
        ]
        differences = (cmp.get("evaluation_comparison") or {}).get("differences") or []
        lines += ["## Evaluation differences", ""]
        lines += [f"- {item}" for item in differences] or ["None."]
        lines.append("")
    else:
        lines += ["## Checks", "",
                  "| check | source | replay | source value | replay value | value delta | "
                  "source time s | replay time s | time delta s |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for row in cmp["checks"]:
            lines.append(
                f"| {row['name']} | {row['source_status']} | {row['replay_status']} | "
                f"{_fmt(row['source_value'])} | {_fmt(row['replay_value'])} | "
                f"{_fmt(row.get('value_delta'))} | {_fmt(row['source_time_s'])} | "
                f"{_fmt(row['replay_time_s'])} | {_fmt(row.get('time_delta_s'))} |")
        lines.append("")
    if cmp["inconclusive"]:
        lines += ["## Inconclusive", ""]
        lines += [f"- {item}" for item in cmp["inconclusive"]]
        lines.append("")
    else:
        lines += ["No status change, no worst-time drift above one sample interval.", ""]
    tolerances = cmp.get("tolerances") or {}
    if tolerances:
        lines += ["## Declared replay tolerances", "", "| item | value |", "|---|---|"]
        lines += [f"| {key} | {_fmt(value)} |" for key, value in tolerances.items()]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ----------------------------------------------------------------------------- CLI
SWEEP_ORDER = ("s0_f000", "s0_f025", "s0_f050", "s0_f075", "s0_f100",
               "s0_spring_low", "s0_spring_high", "s0_half_dt")


def sweep(root: str | Path) -> dict:
    """Derive every S0 case under ``root`` and summarise the comparison across cases."""
    root = Path(root)
    cases: dict[str, dict] = {}
    for name in SWEEP_ORDER:
        run_dir = root / name
        if not (run_dir / "summary.json").exists():
            continue
        diag = diagnostics(run_dir)
        cases[name] = {
            "status": diag["status"],
            "valid": (diag.get("validity") or {}).get("ok"),
            "validity_reasons": [r.get("reason") for r in
                                 (diag.get("validity") or {}).get("reasons", [])],
            "check_status": {c["name"]: c["status"] for c in diag["checks"]},
            "check_value": {c["name"]: c["value"] for c in diag["checks"]},
            "check_detail": {c["name"]: c["detail"] for c in diag["checks"]},
            "pose_translation_m": (diag["housing"].get("relative_pose") or {}).get(
                "translation_m"),
            "pose_rotation_deg": (diag["housing"].get("relative_pose") or {}).get(
                "rotation_deg"),
            "drop_downward_m": (diag["housing"].get("drop") or {}).get("downward_drop_m"),
            "drop_signed_min_m": (diag["housing"].get("drop") or {}).get("signed_min_m"),
            "drop_signed_max_m": (diag["housing"].get("drop") or {}).get("signed_max_m"),
            "body_speed_m_s": next((s["worst_speed_m_s"] for s in diag["speeds"]
                                    if s["body"] == "body"), None),
            "lip_speed_m_s": next((s["worst_speed_m_s"] for s in diag["speeds"]
                                   if s["body"] == "lip"), None),
            "peak_penetration_m": diag["peak_metrics"]["peak_penetration_m"],
            "peak_contact_force_n": diag["peak_metrics"]["peak_contact_force_n"],
            "floor_peak_n": diag["floor_load"]["max_n"],
            "floor_terminal_n": diag["floor_load"]["terminal_n"],
            "return_time_s": diag["return_time"].get("time_s"),
            "return_time_joints": diag["return_time"].get("joints"),
            "contact_durations_s": {p["check"]: p["longest_s"] for p in diag["body_pairs"]},
            "arrest_peak_n": {k: v["peak_force_n"] for k, v in diag["arrests"].items()},
            "drive_peak_n": {k: (v.get("drive") or {}).get("peak_force_n")
                             for k, v in diag["arrests"].items()},
            "coverage": diag["coverage"],
            "timestep_s": diag["timestep_s"],
            "assembly_options_sha256": diag["assembly_options_sha256"],
        }
    check_names: list[str] = []
    for case in cases.values():
        for name in case["check_status"]:
            if name not in check_names:
                check_names.append(name)
    return {"root": str(root), "cases": cases, "check_names": check_names}


def render_sweep(result: dict) -> str:
    cases = result["cases"]
    names = list(cases)
    lines = [
        "# S0 sweep", "",
        f"Runs under `{result['root']}`. Statuses below are copied from each run's bound "
        f"generic evaluator; nothing here recomputes a verdict.", "",
        "## Status", "",
        "| case | status | numerically valid | peak penetration m |",
        "|---|---|---|---|",
    ]
    for name in names:
        case = cases[name]
        lines.append(f"| {name} | {case['status']} | {_fmt(case['valid'])} | "
                     f"{_fmt(case['peak_penetration_m'])} |")
    lines += ["", "## Checks", "",
              "| check | " + " | ".join(n.replace("s0_", "") for n in names) + " |",
              "|---|" + "---|" * len(names)]
    for check in result["check_names"]:
        cells = [cases[name]["check_status"].get(check, "n/a") for name in names]
        lines.append(f"| {check} | " + " | ".join(cells) + " |")
    lines += ["", "## Housing and support diagnostics", "",
              "| metric | " + " | ".join(n.replace("s0_", "") for n in names) + " |",
              "|---|" + "---|" * len(names)]
    for label, key in (("attached-local translation m", "pose_translation_m"),
                       ("attached-local rotation deg", "pose_rotation_deg"),
                       ("signed world-z min m", "drop_signed_min_m"),
                       ("signed world-z max m", "drop_signed_max_m"),
                       ("positive downward drop m", "drop_downward_m"),
                       ("body hold speed m/s", "body_speed_m_s"),
                       ("lip hold speed m/s", "lip_speed_m_s"),
                       ("peak contact force N", "peak_contact_force_n"),
                       ("floor peak N", "floor_peak_n"),
                       ("floor terminal N", "floor_terminal_n"),
                       ("return time s", "return_time_s")):
        lines.append(f"| {label} | "
                     + " | ".join(_fmt(cases[name][key]) for name in names) + " |")
    lines.append("")
    pair_names: list[str] = []
    for case in cases.values():
        for name in case["contact_durations_s"]:
            if name not in pair_names:
                pair_names.append(name)
    lines += ["## Body-pair longest sustained contact (s)", "",
              "| check | " + " | ".join(n.replace("s0_", "") for n in names) + " |",
              "|---|" + "---|" * len(names)]
    for pair in pair_names:
        lines.append(f"| {pair} | " + " | ".join(
            _fmt(cases[name]["contact_durations_s"].get(pair)) for name in names) + " |")
    lines.append("")
    arrest_names: list[str] = []
    for case in cases.values():
        for name in case["arrest_peak_n"]:
            if name not in arrest_names:
                arrest_names.append(name)
    lines += ["## Peg-head and lip-rail peak normal force (N)", "",
              "| probe | " + " | ".join(n.replace("s0_", "") for n in names) + " |",
              "|---|" + "---|" * len(names)]
    for probe in arrest_names:
        lines.append(f"| {probe} | " + " | ".join(
            _fmt(cases[name]["arrest_peak_n"].get(probe)) for name in names) + " |")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def conformance_report() -> dict:
    """Validate the frozen S0 artifacts against the plan before any run is read."""
    acceptance = load_acceptance(ACCEPTANCE_PATH)
    problems = [f"acceptance: {item}" for item in acceptance_conformance(acceptance)]
    problems += [f"options: {item}" for item in options_conformance()]
    scenarios = {}
    for path in sorted(SCENARIO_DIR.glob("s0_*.json")):
        dt = HALF_DT_S if "half_dt" in path.stem else BASE_DT_S
        scenario = load_scenario(path)
        found = scenario_conformance(scenario, expect_dt=dt)
        scenarios[path.stem] = {"hash": scenario.hash(), "problems": found}
        problems += [f"{path.stem}: {item}" for item in found]
    missing = sorted({"s0_f000", "s0_f025", "s0_f050", "s0_f075", "s0_f100",
                      "s0_spring_low", "s0_spring_high", "s0_half_dt"}
                     - set(scenarios))
    if missing:
        problems.append(f"missing scenarios: {missing}")
    return {"ok": not problems, "problems": problems,
            "acceptance_hash": acceptance.hash(), "scenarios": scenarios}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pocky S0 diagnostics and report helper")
    ap.add_argument("--run", help="completed run directory")
    ap.add_argument("--out", help="write the rendered markdown here (default stdout)")
    ap.add_argument("--json-out", help="write the diagnostics as JSON here")
    ap.add_argument("--compare", help="replay directory holding replay.json")
    ap.add_argument("--sweep", help="directory holding the eight completed S0 run dirs")
    ap.add_argument("--conformance", action="store_true",
                    help="validate the frozen scenarios/options/acceptance against the plan")
    args = ap.parse_args(argv)

    if args.conformance:
        report = conformance_report()
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1
    if args.sweep:
        result = sweep(args.sweep)
        text = render_sweep(result)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
        if args.json_out:
            Path(args.json_out).write_text(json.dumps(result, indent=2) + "\n",
                                           encoding="utf-8")
        return 0 if result["cases"] else 1
    if not args.run:
        ap.error("--run, --sweep or --conformance is required")
    if args.compare:
        comparison = compare(args.run, args.compare)
        text = render_comparison(comparison)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
        return 0
    diag = diagnostics(args.run)
    text = render_markdown(diag)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(diag, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
