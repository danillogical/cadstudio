"""Pocky M5a-1 S0 evidence tests: frozen scenarios, acceptance, options and diagnostics.

Written from ``docs/mujoco-m5a-plan.md`` sections 5.2-5.4, not from the frozen documents:

* the acceptance is checked through the typed spec with in-memory mutations, so a
  unit slip (degrees for radians), a swapped body order, a relaxed bound, a forbidden
  check window, a changed threshold, a disabled near-threshold band, the old smoke
  penetration bound or a dropped check each have to be reported;
* the scenario resets are recomputed from the CAD helpers and compared with the JSON,
  and the naive linear pusher interpolation has to miss by at least 1.3 mm;
* every scenario's budgets are recomputed from its own timestep, including the contact
  row cap, rather than compared with the numbers already in the file;
* the diagnostics are exercised on a completed run (generated evidence, skipped when
  absent) and on synthetic minimal runs built in ``tmp_path``.

Run with the optional physics extra:
``uv run --frozen --extra physics pytest tests/test_pocky_physics_s0.py -q``.
"""
from __future__ import annotations

import csv
import json
import math
import tomllib
from dataclasses import replace
from pathlib import Path

import pytest

from cadkit.physics.scenario import (
    AcceptanceSpec,
    CheckSpec,
    ValiditySpec,
    load_acceptance,
    load_scenario,
)
from projects.pocky.geometry.linkage import (
    linkage_from,
    phi_for_button_fraction,
    pose_at_phi,
)
from projects.pocky.params import load_params
from projects.pocky.physics import report
from projects.pocky.physics.assembly import reset_state
from projects.pocky.physics.options import load_options

REPO_ROOT = Path(__file__).resolve().parents[1]
PHYSICS_DIR = REPO_ROOT / "projects" / "pocky" / "physics"
ACCEPTANCE_PATH = PHYSICS_DIR / "s0_acceptance.json"
SCENARIO_DIR = PHYSICS_DIR / "scenarios"
OPTIONS_DIR = PHYSICS_DIR / "options"

#: A completed S0 run with the full 12-check acceptance.
FULL_RUN = REPO_ROOT / "out" / "mujoco-m5a" / "s0" / "runs" / "s0_f000"
#: The completed probe run the ticket names.
PROBE_RUN = REPO_ROOT / "out" / "mujoco-m5a" / "s0" / "probe" / "run0"
#: The completed replay of ``FULL_RUN`` (generic ``replay.json``, no replayed summary).
REPLAY_RUN = REPO_ROOT / "out" / "mujoco-m5a" / "s0" / "replay_s0_f000"
#: The all-five compiled reset/clearance/validity audit and derived budgets.
PREFLIGHT = REPO_ROOT / "out" / "mujoco-m5a" / "s0" / "preflight" / "preflight.json"

#: Plan 5.2 reset table: fraction -> (crank_phi rad, rod_x m, pusher_x m).
PLAN_RESETS = {
    0.0: (0.0, 0.0, 0.0),
    0.25: (-0.242563874, -0.005773503, 0.011132495),
    0.5: (-0.523598776, -0.011547005, 0.025),
    0.75: (-0.804633677, -0.017320508, 0.038867505),
    1.0: (-1.047197551, -0.023094011, 0.05),
}
#: The naive linear pusher interpolation is wrong by this much at quarter fractions.
LINEAR_NEGATIVE_MIN_MM = 1.3
#: Plan 5.2: settle 3.0 s then a 0.5 s zero-input hold, so 3.5 s of every-step rows.
FULL_DURATION_S = 3.5
#: A plausible worst-case contact row count per integration state for the S0 scene
#: (the probe run peaks at 121 geoms in one state; 210 leaves headroom).
CONTACT_ROWS_PER_STATE = 210
#: The trace budget is the bound the contact row cap is expressed against.
TRACE_ROWS_PER_CONTACT_ROW = 16
#: Approved option axis values.
APPROVED_SPRINGS_N_M = (200.0, 1000.0)
APPROVED_BASE_SPRING_N_M = 500.0
APPROVED_DT_S = 1.0e-3
APPROVED_HALF_DT_S = 5.0e-4


# --------------------------------------------------------------------------- helpers
def _scenario_paths() -> list[Path]:
    paths = sorted(SCENARIO_DIR.glob("s0_*.json"))
    assert paths, f"no S0 scenarios under {SCENARIO_DIR}"
    return paths


def _load() -> AcceptanceSpec:
    return load_acceptance(ACCEPTANCE_PATH)


def _with_check(spec: AcceptanceSpec, name: str, **changes) -> AcceptanceSpec:
    """Replace fields on one named check of a frozen acceptance."""
    checks = tuple(replace(c, **changes) if c.name == name else c for c in spec.checks)
    assert any(c.name == name for c in spec.checks), f"no check {name!r}"
    return replace(spec, checks=checks)


def _drop_check(spec: AcceptanceSpec, name: str) -> AcceptanceSpec:
    checks = tuple(c for c in spec.checks if c.name != name)
    assert len(checks) == len(spec.checks) - 1, f"no check {name!r}"
    return replace(spec, checks=checks)


def _check(spec: AcceptanceSpec, name: str) -> CheckSpec:
    for item in spec.checks:
        if item.name == name:
            return item
    raise AssertionError(f"no check {name!r}")


def _write_minimal_run(run_dir: Path, *, status: str, valid: bool,
                       check_status: str) -> Path:
    """One synthetic run directory: a check, an empty contact table, two trace rows."""
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "status": status,
        "validity": {"ok": valid, "reasons": [] if valid else [
            {"stage": "validity", "time_s": None, "reason": "synthetic breach"}]},
        "scenario": {"id": "synthetic"},
        "plan": {"sample_every_steps": 1},
        "solver": {
            "timestep_s": 1.0e-3,
            "bodies": {"body": {"mass_kg": 0.1}},
        },
        "physical_inputs": {"gravity_m_s2": [0.0, 0.0, -9.80665]},
        "phases": [],
        "checks": [{
            "name": "synthetic_penetration",
            "kind": "penetration_bound",
            "status": check_status,
            "ok": check_status == "PASS",
            "value": 0.0001,
            "units": "m",
            "time_s": None,
            "detail": "synthetic",
        }],
        "metrics": {},
        "contacts": [],
        "telemetry": {},
    }
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (run_dir / "contacts.csv").write_text(
        "state_time_s,force_time_s,force_stage,phase,body_a,geom_a,body_b,geom_b,"
        "normal_force_n,penetration_m\n", encoding="utf-8")
    (run_dir / "trace.csv").write_text(
        "state_time_s,phase,qvel:crank_phi (rad/s)\n"
        "0.0,reset,0.5\n"
        "0.001,reset,0.0\n", encoding="utf-8")
    return run_dir


# ------------------------------------------------- 1. acceptance plan conformance
def test_acceptance_conformance_passes_for_the_frozen_document():
    spec = _load()
    assert report.acceptance_conformance(spec) == []
    frozen = report.conformance_report()
    assert frozen["ok"] is True, frozen["problems"]
    assert frozen["problems"] == []
    assert frozen["acceptance_hash"] == spec.hash()
    # Every frozen scenario is present and individually conforming.
    assert set(frozen["scenarios"]) == {
        "s0_f000", "s0_f025", "s0_f050", "s0_f075", "s0_f100",
        "s0_spring_low", "s0_spring_high", "s0_half_dt",
    }
    for stem, item in frozen["scenarios"].items():
        assert item["problems"] == [], stem


def test_acceptance_conformance_has_teeth_on_each_mutation():
    spec = _load()
    assert report.acceptance_conformance(spec) == []

    contact = "body_on_rod"
    mutations = {
        "pose bound": (
            _with_check(spec, "body_pose_retained", maximum=0.00025),
            "body_pose_retained.max",
        ),
        "rotation in degrees": (
            _with_check(spec, "body_pose_retained", max_rotation_rad=0.20),
            "body_pose_retained.max_rotation_rad",
        ),
        "drop bodies swapped": (
            _with_check(spec, "body_drop", body_a="body", body_b="chassis"),
            "body_drop.body_a",
        ),
        "drop lower relaxed": (
            _with_check(spec, "body_drop", lower=-0.0004),
            "body_drop.lower",
        ),
        "contact window": (
            _with_check(spec, contact, window="max_over_phase"),
            f"{contact}.window",
        ),
        "contact threshold": (
            _with_check(spec, contact, force_threshold_n=0.0684),
            f"{contact}.force_threshold_n",
        ),
        "near band disabled": (
            replace(spec, near_threshold_fraction=0.0),
            "near_threshold_fraction",
        ),
        "smoke penetration bound": (
            replace(spec, validity=ValiditySpec(max_penetration_m=0.001)),
            "validity.max_penetration_m",
        ),
        "missing check": (
            _drop_check(spec, "body_on_crank"),
            "body_on_crank",
        ),
        "chassis translation units": (
            _with_check(spec, "chassis_grounded", units="rad"),
            "chassis_grounded.units",
        ),
        "chassis rotation in degrees": (
            _with_check(spec, "chassis_grounded", max_rotation_rad=0.20),
            "chassis_grounded.max_rotation_rad",
        ),
        "settled speed bound": (
            _with_check(spec, "settled_body", maximum=0.002),
            "settled_body.max",
        ),
        "contact window relative": (
            _with_check(spec, contact, phase="hold"),
            f"{contact}.phase",
        ),
    }

    # The degrees mutation must really be the radian value times 180/pi.
    degrees = _check(spec, "body_pose_retained").max_rotation_rad
    assert math.isclose(math.degrees(degrees), 0.20, rel_tol=0.0, abs_tol=1.0e-12)

    for label, (mutated, needle) in mutations.items():
        problems = report.acceptance_conformance(mutated)
        assert problems, f"{label}: mutation was not reported"
        assert any(needle in problem for problem in problems), (label, problems)
        # The pristine spec stays conforming: the mutation, not the helper, is the cause.
        assert report.acceptance_conformance(spec) == []


# ------------------------------------------- 2. reset derivation at five fractions
def test_scenario_resets_equal_the_cad_helpers_at_all_five_fractions():
    p = load_params()
    link = linkage_from(p)
    rest = pose_at_phi(link, link.phi0)
    seen: dict[float, dict[str, float]] = {}

    for path in _scenario_paths():
        scenario = load_scenario(path)
        fraction = report.path_fraction(scenario.scenario_id)
        if fraction is None:
            continue
        written = dict(scenario.reset_phase.initial)
        assert set(written) == {"crank_phi", "rod_x", "pusher_x"}, path.name
        seen[fraction] = written

        state = reset_state(p, fraction)
        assert math.isclose(written["crank_phi"], state.crank_phi_rad,
                            rel_tol=0.0, abs_tol=1.0e-15), path.name
        assert math.isclose(written["rod_x"], state.rod_x_m,
                            rel_tol=0.0, abs_tol=1.0e-15), path.name
        assert math.isclose(written["pusher_x"], state.pusher_x_m,
                            rel_tol=0.0, abs_tol=1.0e-15), path.name

        # Independent derivation from the plan's three helper calls, no compiled scene.
        pose = pose_at_phi(link, phi_for_button_fraction(link, fraction))
        assert math.isclose(written["crank_phi"], pose.phi - link.phi0,
                            rel_tol=0.0, abs_tol=1.0e-15), path.name
        assert math.isclose(written["rod_x"], -pose.button_travel / 1000.0,
                            rel_tol=0.0, abs_tol=1.0e-15), path.name
        assert math.isclose(written["pusher_x"], (pose.face_x - rest.face_x) / 1000.0,
                            rel_tol=0.0, abs_tol=1.0e-15), path.name

        # Plan 5.2 table, printed to nine decimals, is the source of truth.
        crank, rod, pusher = PLAN_RESETS[fraction]
        assert math.isclose(written["crank_phi"], crank, rel_tol=0.0, abs_tol=1.0e-9)
        assert math.isclose(written["rod_x"], rod, rel_tol=0.0, abs_tol=1.0e-9)
        assert math.isclose(written["pusher_x"], pusher, rel_tol=0.0, abs_tol=1.0e-9)

    assert set(seen) == set(PLAN_RESETS)

    # Quarter stroke is not quarter pusher travel: the linear reset misses by >=1.3 mm.
    for fraction in (0.25, 0.75):
        linear = fraction * 0.050
        error_mm = abs(seen[fraction]["pusher_x"] - linear) * 1000.0
        assert error_mm >= LINEAR_NEGATIVE_MIN_MM, (fraction, error_mm)
    # At f=0.5 the two agree by construction, so the negative is genuinely a shape test.
    assert abs(seen[0.5]["pusher_x"] - 0.5 * 0.050) < 1.0e-6


def test_reset_derivation_needs_no_compiled_scene():
    """The scenario resets are pure CAD-helper values, so no MuJoCo compile is involved.

    Plan 5.2's compiled-transform cross-check has 1e-9 rad and 1e-6 m tolerances. The JSON
    carries the helper floats bit-for-bit (below), so a compiled re-measurement of the same
    quantities can only re-confirm them; this file therefore never imports MuJoCo.
    """
    p = load_params()
    link = linkage_from(p)
    rest = pose_at_phi(link, link.phi0)
    pose = pose_at_phi(link, phi_for_button_fraction(link, 0.75))
    state = reset_state(p, 0.75)

    # The three written coordinates are exactly the helper expressions; nothing about them
    # is read from a compiled model.
    assert state.joint_coordinates() == {
        "crank_phi": pose.phi - link.phi0,
        "rod_x": -pose.button_travel / 1000.0,
        "pusher_x": (pose.face_x - rest.face_x) / 1000.0,
    }
    # Bit-for-bit, not merely within a compiled tolerance.
    written = dict(load_scenario(SCENARIO_DIR / "s0_f075.json").reset_phase.initial)
    assert written["crank_phi"] == pose.phi - link.phi0
    assert written["rod_x"] == -pose.button_travel / 1000.0
    assert written["pusher_x"] == (pose.face_x - rest.face_x) / 1000.0

    # reset_state carries the helper pose it came from, so a compiled cross-check would be
    # redundant evidence for the scenario file.
    assert state.fraction == 0.75
    assert state.face_x_mm == pose.face_x
    assert state.phi_rad == pose.phi


def test_frozen_acceptance_equals_the_plan_numbers_as_literals():
    """Pin the frozen document against plan 5.3's numbers written out here, independently.

    ``report.PLAN_THRESHOLDS`` restates the same plan table, so a test that compared the
    document only with that dict would pass if both were wrong in the same way. These values
    are transcribed from ``docs/mujoco-m5a-plan.md`` section 5.3 by hand.
    """
    spec = _load()
    checks = {c.name: c for c in spec.checks}

    assert spec.acceptance_id == "pocky_m5a1_s0"
    assert spec.near_threshold_fraction == 0.2
    assert spec.validity.max_penetration_m == 0.0002
    assert spec.validity.max_speed_m_s is None
    assert spec.validity.max_angular_speed_rad_s is None
    assert spec.validity.max_energy_j is None
    assert not spec.events

    assert set(checks) == {
        "body_pose_retained", "body_drop", "body_on_pusher", "body_on_rod",
        "body_on_crank", "lip_on_pusher", "lip_on_rod", "lip_on_crank",
        "chassis_grounded", "settled_body", "settled_lip", "penetration",
    }

    pose = checks["body_pose_retained"]
    assert (pose.body_a, pose.body_b, pose.phase, pose.window) == (
        "body", "chassis", "hold", "max_over_phase")
    assert pose.maximum == 0.0002
    assert math.isclose(math.degrees(pose.max_rotation_rad), 0.20, abs_tol=1e-12)
    assert pose.units == "m"

    drop = checks["body_drop"]
    # Signed world-z change of (body - chassis): a fall is negative, so the bounds are
    # asymmetric in sign only, not in magnitude.
    assert (drop.body_a, drop.body_b, drop.from_phase, drop.to_phase) == (
        "chassis", "body", "initial", "hold")
    assert (drop.axis, drop.frame, drop.window) == ("z", "world", "max_over_phase")
    assert drop.lower == -0.0001
    assert drop.upper == 0.0001
    assert drop.units == "m"

    for name in ("body_on_pusher", "body_on_rod", "body_on_crank",
                 "lip_on_pusher", "lip_on_rod", "lip_on_crank"):
        check = checks[name]
        assert check.kind == "contact_duration", name
        assert check.force_threshold_n == 0.0715, name
        assert check.maximum == 0.20, name
        # A hold-relative window would turn a sustained load into a duration ratio; the
        # plan requires the whole-run window.
        assert check.window == "end", name
        assert check.phase is None and check.from_phase is None, name
        assert check.to_phase is None, name
        assert check.units == "s", name

    grounded = checks["chassis_grounded"]
    assert (grounded.body_a, grounded.body_b) == ("chassis", "floor_world")
    assert grounded.maximum == 0.001
    assert math.isclose(math.degrees(grounded.max_rotation_rad), 0.20, abs_tol=1e-12)

    for name, body in (("settled_body", "body"), ("settled_lip", "lip")):
        check = checks[name]
        assert check.kind == "body_speed", name
        assert check.body == body, name
        assert check.maximum == 0.001, name
        assert check.phase == "hold" and check.window == "max_over_phase", name
        assert check.units == "m/s", name

    penetration = checks["penetration"]
    assert penetration.kind == "penetration_bound"
    assert penetration.maximum == 0.0002


# --------------------------------------------------------- 3. scenario invariants
@pytest.mark.parametrize("path", _scenario_paths(), ids=lambda p: p.stem)
def test_scenario_invariants(path: Path):
    scenario = load_scenario(path)
    is_half_dt = "half_dt" in path.stem
    dt = APPROVED_HALF_DT_S if is_half_dt else APPROVED_DT_S

    assert scenario.fixture == "pocky_prototype"
    assert scenario.seed == 0
    assert scenario.timestep_s == dt, path.stem
    assert scenario.sampling_interval_s == scenario.timestep_s
    assert scenario.sampling_interval_s == dt

    assert [p.kind for p in scenario.phases] == ["reset", "settle", "hold"]
    assert scenario.reset_phase.initial, path.stem
    settle, hold = scenario.phases[1], scenario.phases[2]
    assert settle.duration_s == 3.0
    assert hold.duration_s == 0.5
    for phase in scenario.phases:
        assert phase.actuator is None, (path.stem, phase.name)
        assert phase.effort is None, (path.stem, phase.name)

    # Budgets recomputed from this scenario's own timestep, never copied from the file.
    total_time_s = settle.duration_s + hold.duration_s
    assert total_time_s == FULL_DURATION_S
    total_steps = int(round(total_time_s / dt))
    assert total_steps * dt == pytest.approx(total_time_s, abs=1.0e-12)

    budgets = scenario.budgets
    assert budgets.max_steps >= total_steps, path.stem
    assert budgets.max_state_rows is not None
    assert budgets.max_state_rows >= total_steps + 1, path.stem
    assert budgets.max_trace_rows >= total_steps + 1, path.stem
    assert budgets.max_sim_time_s >= total_time_s, path.stem

    # Every-step trace rows over the full run, with the contact row cap covered at 16:1.
    contact_row_cap = total_steps * CONTACT_ROWS_PER_STATE
    assert budgets.max_trace_rows * TRACE_ROWS_PER_CONTACT_ROW >= contact_row_cap, (
        path.stem, budgets.max_trace_rows, contact_row_cap)

    problems = report.scenario_conformance(scenario, expect_dt=dt)
    assert problems == [], (path.stem, problems)


def test_scenario_conformance_rejects_a_perturbed_scenario():
    """The per-scenario check is not a rubber stamp: dt, phases and budgets have teeth."""
    path = SCENARIO_DIR / "s0_f000.json"
    scenario = load_scenario(path)
    assert report.scenario_conformance(scenario, expect_dt=APPROVED_DT_S) == []

    # Wrong expected timestep for this file.
    assert report.scenario_conformance(scenario, expect_dt=APPROVED_HALF_DT_S)
    # A hold phase that carries an effort.
    phases = tuple(
        replace(p, effort=0.5) if p.kind == "hold" else p for p in scenario.phases)
    assert report.scenario_conformance(replace(scenario, phases=phases),
                                       expect_dt=APPROVED_DT_S)
    # A trace budget below one every-step row per integration state.
    tight = replace(scenario.budgets, max_trace_rows=100)
    assert report.scenario_conformance(replace(scenario, budgets=tight),
                                       expect_dt=APPROVED_DT_S)
    # Sampling that no longer equals the timestep.
    assert report.scenario_conformance(
        replace(scenario, sampling_interval_s=2.0e-3), expect_dt=APPROVED_DT_S)


# ------------------------------------------------------------------- 4. options
def test_option_files_are_the_approved_axes():
    expected = {
        "s0_spring_low.toml": (APPROVED_SPRINGS_N_M[0], APPROVED_DT_S),
        "s0_spring_high.toml": (APPROVED_SPRINGS_N_M[1], APPROVED_DT_S),
        "s0_half_dt.toml": (APPROVED_BASE_SPRING_N_M, APPROVED_HALF_DT_S),
    }
    for name, (spring, dt) in expected.items():
        table = tomllib.loads((OPTIONS_DIR / name).read_text(encoding="utf-8"))
        assert set(table) == {"spring_stiffness_n_m", "timestep_s"}, name
        assert table["spring_stiffness_n_m"] == spring, name
        assert table["timestep_s"] == dt, name
        options = load_options(table)
        assert options.spring_stiffness_n_m == spring
        assert options.timestep_s == dt
    assert report.options_conformance() == []


def test_base_cases_have_no_options_file_and_defaults_apply():
    for stem in ("s0_f000", "s0_f025", "s0_f050", "s0_f075", "s0_f100"):
        assert not (OPTIONS_DIR / f"{stem}.toml").exists(), stem
    for empty in ({}, None):
        options = load_options(empty)
        assert options.spring_stiffness_n_m == APPROVED_BASE_SPRING_N_M
        assert options.timestep_s == APPROVED_DT_S
    # An explicitly empty options lock is the canonical base-case document.
    assert load_options({}).as_dict() == {
        "spring_stiffness_n_m": APPROVED_BASE_SPRING_N_M,
        "timestep_s": APPROVED_DT_S,
    }


@pytest.mark.parametrize("table", [
    {"spring_stiffness_n_m": 300.0},
    {"timestep_s": 2.0e-3},
    {"spring_stiffness_n_m": 500.0, "timestep_s": 1.0e-3, "packets": 11},
])
def test_options_outside_the_approved_axes_are_rejected(table):
    with pytest.raises(ValueError):
        load_options(table)


# ------------------------------------------------ 5. diagnostics on a real run
def _require_probe_run() -> Path:
    if not (PROBE_RUN / "summary.json").exists():
        pytest.skip(f"generated run evidence absent: {PROBE_RUN}")
    return PROBE_RUN


def test_diagnostics_on_the_probe_run_keeps_the_evaluator_status():
    run_dir = _require_probe_run()
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    diag = report.diagnostics(run_dir)

    # Status and validity are copied, never recomputed: this run is INCONCLUSIVE because
    # its validity bound was breached while the one check FAILed.
    assert diag["status"] == summary["status"]
    assert diag["validity"] == summary["validity"]
    assert diag["run_id"] == summary.get("run_id")
    assert diag["timestep_s"] == summary["solver"]["timestep_s"]
    assert diag["sampling_interval_s"] == (
        summary["solver"]["timestep_s"] * summary["plan"]["sample_every_steps"])
    assert [c["name"] for c in diag["checks"]] == [c["name"] for c in summary["checks"]]
    assert [c["status"] for c in diag["checks"]] == [c["status"] for c in summary["checks"]]

    # Every body-pair row, when present, is check evidence with consistent counts.
    evidence = {c["name"]: c.get("evidence") for c in summary["checks"]}
    for row in diag["body_pairs"]:
        assert row["samples_above"] <= row["samples"]
        assert row["threshold_n"] == evidence[row["check"]]["threshold_n"]
        assert row["samples"] == evidence[row["check"]]["samples"]
        assert row["status"] == next(
            c["status"] for c in summary["checks"] if c["name"] == row["check"])

    # Floor-load state count is the number of distinct state times in contacts.csv.
    with (run_dir / "contacts.csv").open(newline="", encoding="utf-8") as fh:
        times = {row["state_time_s"] for row in csv.DictReader(fh)}
    assert times, "contacts.csv has no rows"
    assert diag["floor_load"]["states"] == len(times)

    # Return time is resolved to the sampling grid, never precedes its bracket, and is
    # reported per joint in that joint's own unit: a crank angle rate is rad/s, a carriage
    # rate is m/s, and the two are never ranked against one another.
    ret = diag["return_time"]
    assert ret["time_s"] is not None
    assert ret["time_s"] >= ret["after_time_s"]
    assert ret["time_s"] - ret["after_time_s"] == pytest.approx(
        diag["sampling_interval_s"], abs=1.0e-12)
    assert ret["units"] == sorted({j["units"] for j in ret["joints"]})
    assert {j["units"] for j in ret["joints"]} <= {"m/s", "rad/s"}
    for joint in ret["joints"]:
        assert joint["units"] in ("m/s", "rad/s"), joint
        assert joint["peak"] >= joint["terminal"] - 1.0e-12, joint
        if joint["time_s"] is not None:
            assert joint["time_s"] >= joint["after_time_s"], joint
    # The slowest joint sets the run's quiescence time; no joint may be quieter than it.
    assert ret["time_s"] == max(j["time_s"] for j in ret["joints"]
                               if j["time_s"] is not None)

    # The rendered report carries the evaluator's own status and invents no PASS.
    text = report.render_markdown(diag)
    assert f"**{summary['status']}**" in text
    assert "PASS" not in text
    for check in summary["checks"]:
        if check["status"] != "PASS":
            assert f"| {check['name']} | {check['kind']} | PASS |" not in text


def test_diagnostics_body_pairs_come_from_check_evidence_on_the_full_run():
    if not (FULL_RUN / "summary.json").exists():
        pytest.skip(f"generated run evidence absent: {FULL_RUN}")
    summary = json.loads((FULL_RUN / "summary.json").read_text(encoding="utf-8"))
    diag = report.diagnostics(FULL_RUN)

    assert diag["body_pairs"], "the full S0 acceptance declares six contact checks"
    evidence = {c["name"]: c["evidence"] for c in summary["checks"]
                if "evidence" in c}
    # Literal, so the expected pair set does not come from the module under test.
    declared = ["body_on_pusher", "body_on_rod", "body_on_crank",
                "lip_on_pusher", "lip_on_rod", "lip_on_crank"]
    assert [row["check"] for row in diag["body_pairs"]] == declared
    for row in diag["body_pairs"]:
        item = evidence[row["check"]]
        assert row["samples_above"] == item["samples_above"]
        assert row["samples"] == item["samples"]
        assert row["samples_above"] <= row["samples"]
        assert row["longest_s"] == item["longest_s"]
        assert row["peak_force_n"] == item["peak_force_n"]
        assert row["threshold_n"] == item["threshold_n"]
    assert diag["status"] == summary["status"]
    assert diag["validity"] == summary["validity"]

    # Every PASS in the render is one the evaluator set, and the run status is not PASS.
    text = report.render_markdown(diag)
    evaluator_pass = sum(1 for c in summary["checks"] if c["status"] == "PASS")
    evaluator_pass += sum(1 for row in diag["body_pairs"] if row["status"] == "PASS")
    assert text.count("| PASS |") == evaluator_pass, text.count("| PASS |")
    assert diag["status"] != "PASS"


# ------------------------------------- 6. valid FAIL vs invalid INCONCLUSIVE
def test_diagnostics_copies_fail_and_inconclusive_without_recomputing(tmp_path):
    failing = _write_minimal_run(tmp_path / "fail", status="FAIL", valid=True,
                                 check_status="FAIL")
    diag = report.diagnostics(failing)
    assert diag["status"] == "FAIL"
    assert diag["validity"]["ok"] is True
    assert diag["checks"][0]["status"] == "FAIL"
    assert json.loads((failing / "summary.json").read_text(encoding="utf-8"))["status"] \
        == "FAIL"

    invalid = _write_minimal_run(tmp_path / "invalid", status="INCONCLUSIVE", valid=False,
                                 check_status="PASS")
    diag = report.diagnostics(invalid)
    assert diag["status"] == "INCONCLUSIVE"
    assert diag["validity"]["ok"] is False
    assert diag["validity"]["reasons"][0]["reason"] == "synthetic breach"
    # The passing check is not promoted to a run status.
    assert diag["checks"][0]["status"] == "PASS"
    assert diag["status"] != "PASS"

    # diagnostics() is read-only: neither summary nor the evidence files changed.
    for run_dir, expected in ((failing, "FAIL"), (invalid, "INCONCLUSIVE")):
        after = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        assert after["status"] == expected
        assert (run_dir / "contacts.csv").read_text(encoding="utf-8").count("\n") == 1
        assert (run_dir / "trace.csv").read_text(encoding="utf-8").count("\n") == 3


# ------------------------------------------------------------- 7. replay identity
def test_compare_reports_a_flipped_check_status(tmp_path):
    source_dir = _require_probe_run()
    source_summary = json.loads(
        (source_dir / "summary.json").read_text(encoding="utf-8"))
    source_check = source_summary["checks"][0]
    flipped = "PASS" if source_check["status"] != "PASS" else "FAIL"

    replay_dir = tmp_path / "replay"
    replayed = _write_minimal_run(replay_dir / "replay_source" / "run",
                                  status="PASS", valid=True, check_status=flipped)
    replayed_summary = json.loads(
        (replayed / "summary.json").read_text(encoding="utf-8"))
    replayed_summary["checks"][0]["name"] = source_check["name"]
    replayed_summary["checks"][0]["value"] = source_check.get("value")
    (replayed / "summary.json").write_text(json.dumps(replayed_summary),
                                           encoding="utf-8")
    (replay_dir / "replay.json").write_text(json.dumps({
        "status": "PASS",
        "source_status": source_summary["status"],
        "reproduced": True,
        "state_comparison": {"ok": True, "max_abs_diff": 0.0},
        "post_settle_continuation": {"ok": True},
        "evaluation_comparison": {"ok": True},
    }), encoding="utf-8")

    cmp = report.compare(source_dir, replay_dir)
    assert cmp["replay_status"] == "PASS"


    assert cmp["source_status"] == source_summary["status"]
    rows = {row["name"]: row for row in cmp["checks"]}
    assert rows[source_check["name"]]["source_status"] == source_check["status"]
    assert rows[source_check["name"]]["replay_status"] == flipped
    assert any(source_check["name"] in item and "status changed" in item
               for item in cmp["inconclusive"]), cmp["inconclusive"]
    # The verdict is the replay's own bound comparison, not a recomputed one.
    assert cmp["evaluation_comparison"] == {"ok": True}
    text = report.render_comparison(cmp)
    assert "Inconclusive" in text
    assert source_check["name"] in text


def test_compare_reads_the_generic_replay_without_a_replayed_summary():
    """The shipped replay path: ``replay.json`` only, no ``replay_source/run/summary.json``.

    The generic ``cad physics replay`` writes its per-check comparison into ``replay.json``
    and does not re-emit a run directory. That is the layout every real replay has, so the
    comparison must work there — and it must not turn an INCONCLUSIVE source into a PASS.
    """
    replay_dir = REPLAY_RUN
    if not (replay_dir / "replay.json").exists():
        pytest.skip(f"generated replay evidence absent: {replay_dir}")
    if not (FULL_RUN / "summary.json").exists():
        pytest.skip(f"generated run evidence absent: {FULL_RUN}")

    replay = json.loads((replay_dir / "replay.json").read_text(encoding="utf-8"))
    cmp = report.compare(FULL_RUN, replay_dir)

    assert cmp["per_check_available"] is False
    assert cmp["checks"] == []
    assert cmp["reproduced"] is True
    assert cmp["replay_status"] == replay["status"] == "INCONCLUSIVE"
    assert cmp["source_status"] == replay["source_status"] == "INCONCLUSIVE"
    assert cmp["evaluation_comparison"]["ok"] is True
    assert cmp["evaluation_comparison"]["differences"] == []
    assert cmp["inconclusive"] == [], cmp["inconclusive"]

    text = report.render_comparison(cmp)
    # No PASS anywhere, and the status is stated as the evaluator's own.
    assert "PASS" not in text
    assert "**INCONCLUSIVE**" in text
    assert "reproduction, not a replay failure" in text


# ------------------------------------------------ 8. preflight evidence completeness
def test_preflight_binds_the_accepted_compiled_audits_at_all_five_fractions():
    """The five compiled resets, clearances and initial validity the packet requires."""
    record = PREFLIGHT
    if not record.exists():
        pytest.skip(f"preflight evidence absent: {record}")
    doc = json.loads(record.read_text(encoding="utf-8"))
    compiled = doc["compiled"]

    assert compiled["ok"] is True, compiled["problems"]
    assert compiled["scenarios_match_audit"] is True
    assert [row["fraction"] for row in compiled["resets"]] == [0.0, 0.25, 0.5, 0.75, 1.0]
    for row in compiled["resets"]:
        assert row["ok"] is True, row
        assert row["sign_bad"] is False, row
        assert row["exceeded"] == {}, row
        # The compiled transforms agree with the CAD helpers to floating-point noise, far
        # inside the audit's own 1e-9 rad / 1e-6 m tolerances. Translation and rotation are
        # separate fields because they are separate units.
        assert row["worst_translation_error_m"] < 1.0e-12, row
        assert row["worst_angular_error_rad"] < 1.0e-12, row

    assert compiled["clearance"]["ok"] is True
    assert compiled["clearance"]["tolerance_mm"] == 0.02
    assert compiled["clearance"]["fractions"] == 5
    for row in compiled["validity"]:
        assert row["ok"] is True, row
        # No initial collider penetration and no exact solid overlap at any fraction.
        assert abs(row["worst_collider_penetration_m"]) < 1.0e-12, row
        assert row["worst_exact_overlap_mm3"] == 0.0, row

    # Both wrong-reset negatives are rejected, and the linear one by the plan's 1.367 mm.
    assert compiled["negatives"]["linear"]["rejected"] is True
    assert compiled["negatives"]["linear"]["min_pusher_error_mm"] >= 1.367
    assert compiled["negatives"]["sign_flip"]["rejected"] is True


def test_preflight_budgets_cover_every_integration_sample():
    """Each scenario's declared budgets are derived from its own dt, not copied."""
    record = PREFLIGHT
    if not record.exists():
        pytest.skip(f"preflight evidence absent: {record}")
    budgets = json.loads(record.read_text(encoding="utf-8"))["budgets"]

    assert budgets["ok"] is True, budgets["problems"]
    assert len(budgets["scenarios"]) == 8
    for row in budgets["scenarios"]:
        steps = row["steps"]
        assert row["sampling_interval_s"] == row["timestep_s"], row["scenario"]
        assert steps == int(round(3.5 / row["timestep_s"])), row["scenario"]
        # One trace row and one state row per integration step, plus the initial state.
        assert row["required_trace_rows"] == steps + 1, row["scenario"]
        assert row["declared_trace_rows"] >= steps + 1, row["scenario"]
        assert row["declared_state_rows"] >= steps + 1, row["scenario"]
        assert row["declared_steps"] >= steps, row["scenario"]
        # The runner's contact cap is 16 rows per declared trace row.
        assert row["contact_row_cap"] == row["declared_trace_rows"] * 16, row["scenario"]
        if row["observed_contact_rows"] is not None:
            assert row["observed_contact_rows"] <= row["contact_row_cap"], row["scenario"]
            assert row["observed_contact_rows"] >= steps, row["scenario"]
