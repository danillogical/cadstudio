"""M4a generic runner: real phases, bounded effort, telemetry, four-state evidence."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from cadkit.params import REPO_ROOT
from cadkit.physics.runner import run_scenario_files
from cadkit.physics.scenario import (
    AcceptanceSpec,
    BudgetSpec,
    CheckSpec,
    PhaseSpec,
    ScenarioSpec,
    ValiditySpec,
    load_acceptance,
    load_scenario,
)

pytest.importorskip("mujoco")

from cadkit.physics.scenario import build_fixture  # noqa: E402
from cadkit.physics.telemetry import TelemetryRecorder  # noqa: E402


def _env():
    env = dict(os.environ)
    env["PATH"] = f"{Path.home() / '.local' / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    return env


def cad(*args, timeout=300):
    return subprocess.run([sys.executable, "-m", "cadkit.cli", *args], cwd=REPO_ROOT,
                          capture_output=True, text=True, encoding="utf-8",
                          timeout=timeout, env=_env())


def scenario_dict(fixture="loaded_slider", effort=1.0, initial=0.0, sampling=0.002,
                  phases=None, **overrides):
    payload = {
        "schema_version": "m4a-1",
        "scenario_id": "m4a_" + fixture,
        "fixture": fixture,
        "seed": 7,
        "timestep_s": 0.001,
        "sampling_interval_s": sampling,
        "budgets": {"max_steps": 20000, "max_sim_time_s": 10.0,
                    "max_trace_rows": 20000},
        "phases": phases or [
            {"name": "reset", "kind": "reset", "initial": {"carriage_slide": initial}},
            {"name": "settle", "kind": "settle", "duration_s": 0.3},
            {"name": "push", "kind": "actuate", "duration_s": 0.6,
             "actuator": "push", "effort": effort},
            {"name": "release", "kind": "release", "duration_s": 0.6},
            {"name": "hold", "kind": "hold", "duration_s": 0.2},
        ],
    }
    payload.update(overrides)
    return payload


def acceptance_dict(expected=0.02, tolerance=0.001, return_max=0.0002,
                    max_speed=1.0, **overrides):
    payload = {
        "schema_version": "m4a-1",
        "acceptance_id": "m4a_acceptance",
        "validity": {"max_penetration_m": 0.001, "max_speed_m_s": max_speed,
                     "max_energy_j": 1.0},
        "checks": [
            {"name": "held_displacement", "kind": "joint_displacement",
             "joint": "carriage_slide", "to_phase": "push",
             "expected": expected, "tolerance": tolerance, "units": "m"},
            {"name": "release_return", "kind": "return_displacement",
             "joint": "carriage_slide", "phase": "release", "reference": 0.0,
             "max": return_max, "units": "m"},
            {"name": "terminal_speed", "kind": "terminal_speed",
             "joint": "carriage_slide", "phase": "hold", "max": 0.02,
             "units": "m/s"},
            {"name": "effort_bounded", "kind": "effort_bound", "actuator": "push",
             "max": 2.0, "units": "N"},
        ],
    }
    payload.update(overrides)
    return payload


def run_case(tmp_path, scenario, acceptance, name="run"):
    sp = tmp_path / "scenario.json"
    ap = tmp_path / "acceptance.json"
    sp.write_text(json.dumps(scenario), encoding="utf-8")
    ap.write_text(json.dumps(acceptance), encoding="utf-8")
    out = tmp_path / name
    summary = run_scenario_files(sp, ap, out)
    return summary, out, sp, ap


def test_loaded_slider_runs_generic_phases_and_passes(tmp_path):
    summary, out, _, _ = run_case(tmp_path, scenario_dict(), acceptance_dict())
    assert summary["status"] == "PASS", summary.get("detail")
    assert [p["kind"] for p in summary["phases"]] == \
        ["reset", "settle", "actuate", "release", "hold"]
    assert all(p["complete"] for p in summary["phases"])
    assert summary["phases"][2]["actual_steps"] == 600
    held = next(c for c in summary["checks"] if c["name"] == "held_displacement")
    assert held["status"] == "PASS"
    assert held["value"] == pytest.approx(0.02, abs=0.001)
    # It really stepped: states and traces are non-empty, and the terminal state moved.
    assert (out / "trace.csv").is_file()
    assert (out / "contacts.csv").is_file()
    assert (out / "states.npz").is_file()
    state = np.load(out / "states.npz", allow_pickle=False)
    assert state["qpos"].shape[0] == summary["telemetry"]["state_rows"]
    assert state["qpos"].shape[0] > 1
    assert state["qvel"].shape[1] == 1
    assert set(state.files) >= {"time", "qpos", "qvel", "act", "ctrl",
                                "qacc_warmstart", "qfrc_applied"}
    assert summary["states"]["terminal"]["qpos"]["carriage_slide"] < 0.0005
    # Strict JSON artifacts.
    json.loads((out / "summary.json").read_text(encoding="utf-8"),
               parse_constant=lambda value: (_ for _ in ()).throw(
                   AssertionError(f"non-strict JSON {value}")))
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "PASS"
    assert manifest["scenario"]["hash"] == summary["scenario"]["hash"]
    assert manifest["acceptance"]["hash"] == summary["acceptance"]["hash"]
    assert manifest["scene"]["xml_sha256"]
    assert manifest["physical_inputs"]["bodies"]
    report = (out / "report.md").read_text(encoding="utf-8")
    assert "Status: **PASS**" in report and "held_displacement" in report
    assert (out / "acceptance.lock.json").is_file()
    assert (out / "scenario.json").is_file()


def test_force_limited_actuation_records_raw_and_bounded_effort(tmp_path):
    # 2 N is the declared actuator bound; 1e6 N must be clipped to 2 N, not simulated.
    expected = 2.0 / 50.0
    summary, out, _, _ = run_case(
        tmp_path, scenario_dict(effort=1.0e6),
        acceptance_dict(expected=expected, tolerance=0.001))
    assert summary["status"] == "PASS", summary.get("detail")
    assert summary["metrics"]["peak_effort"]["push"] == pytest.approx(2.0)
    assert summary["metrics"]["peak_ctrl_stored"]["push"] == pytest.approx(1.0e6)
    assert summary["metrics"]["peak_ctrl_effective"]["push"] == pytest.approx(2.0)
    assert summary["metrics"]["effort_tracking_error"]["push"] == 0.0
    held = next(c for c in summary["checks"] if c["name"] == "held_displacement")
    assert held["value"] == pytest.approx(expected, abs=0.001)
    assert summary["solver"]["actuators"]["push"]["ctrlrange"] == [-2.0, 2.0]
    assert summary["solver"]["actuators"]["push"]["forcerange"] == [-2.0, 2.0]


def test_negative_gear_preserves_effort_sign_and_limit(tmp_path):
    summary, _, _, _ = run_case(
        tmp_path, scenario_dict(fixture="loaded_slider_negative_gear", effort=0.5),
        acceptance_dict(expected=0.01, tolerance=0.001), name="gear-sign")
    assert summary["status"] == "PASS", summary.get("detail")
    assert summary["metrics"]["peak_effort"]["push"] == pytest.approx(0.5)
    assert summary["metrics"]["peak_ctrl_stored_signed"]["push"] == pytest.approx(-0.25)
    assert summary["metrics"]["peak_ctrl_effective"]["push"] == pytest.approx(0.25)
    held = next(c for c in summary["checks"] if c["name"] == "held_displacement")
    assert held["value"] > 0.0

    clipped, _, _, _ = run_case(
        tmp_path, scenario_dict(fixture="loaded_slider_negative_gear", effort=1.0e6),
        acceptance_dict(expected=0.04, tolerance=0.001), name="gear-clipped")
    assert clipped["status"] == "PASS", clipped.get("detail")
    assert clipped["metrics"]["peak_effort"]["push"] == pytest.approx(2.0)
    assert clipped["metrics"]["peak_ctrl_stored_signed"]["push"] == pytest.approx(-5.0e5)
    assert clipped["metrics"]["peak_ctrl_effective_signed"]["push"] == pytest.approx(-1.0)
    assert clipped["solver"]["actuators"]["push"]["gear"] == -2.0


def test_missing_force_is_a_real_named_failure(tmp_path):
    summary, out, _, _ = run_case(
        tmp_path, scenario_dict(effort=0.0), acceptance_dict(),
        name="missing-force")
    assert summary["status"] == "FAIL"
    held = next(c for c in summary["checks"] if c["name"] == "held_displacement")
    assert held["status"] == "FAIL"
    assert "0" in held["detail"]
    assert "Status: **FAIL**" in (out / "report.md").read_text(encoding="utf-8")


def test_missing_spring_is_a_real_named_failure(tmp_path):
    summary, out, _, _ = run_case(
        tmp_path, scenario_dict(fixture="loaded_slider_no_spring"),
        acceptance_dict(), name="missing-spring")
    assert summary["status"] == "FAIL"
    ret = next(c for c in summary["checks"] if c["name"] == "release_return")
    assert ret["status"] == "FAIL"
    assert ret["value"] > 0.01
    # The drive did move the carriage; only the mechanical return is absent.
    held = next(c for c in summary["checks"] if c["name"] == "held_displacement")
    assert held["status"] == "FAIL"  # no spring, so F/k is not the applicable static model
    assert (out / "trace.csv").is_file()


def test_same_seed_reset_repeats_identically(tmp_path):
    first, out1, _, _ = run_case(tmp_path, scenario_dict(), acceptance_dict(),
                                name="repeat-a")
    second, out2, _, _ = run_case(tmp_path, scenario_dict(), acceptance_dict(),
                                 name="repeat-b")
    assert first["status"] == second["status"] == "PASS"
    assert first["scene"]["scene_hash"] == second["scene"]["scene_hash"]
    assert first["scenario"]["hash"] == second["scenario"]["hash"]
    assert first["acceptance"]["hash"] == second["acceptance"]["hash"]
    assert first["states"]["terminal"]["hash"] == second["states"]["terminal"]["hash"]
    for key in ("peak_speed_m_s", "peak_energy_j", "peak_penetration_m",
                "peak_contact_force_n"):
        assert first["metrics"][key] == pytest.approx(second["metrics"][key], abs=1e-15)
    assert first["metrics"]["peak_effort"] == second["metrics"]["peak_effort"]
    # Same trace bytes are stronger than a metric comparison on one platform.
    assert (out1 / "trace.csv").read_bytes() == (out2 / "trace.csv").read_bytes()
    assert (out1 / "states.npz").read_bytes() == (out2 / "states.npz").read_bytes()


def test_reset_writes_only_declared_coordinate_and_motion_is_not_scripted(tmp_path):
    checks = [
        {"name": "held_displacement", "kind": "joint_displacement",
         "joint": "carriage_slide", "from_phase": "settle", "to_phase": "push",
         "expected": 0.0, "tolerance": 0.0005, "units": "m"},
        {"name": "release_return", "kind": "return_displacement",
         "joint": "carriage_slide", "phase": "release", "reference": 0.0,
         "max": 0.0002, "units": "m"},
        {"name": "terminal_speed", "kind": "terminal_speed",
         "joint": "carriage_slide", "phase": "hold", "max": 0.02, "units": "m/s"},
        {"name": "effort_bounded", "kind": "effort_bound", "actuator": "push",
         "max": 2.0, "units": "N"},
    ]
    summary, out, _, _ = run_case(
        tmp_path, scenario_dict(initial=0.005, effort=0.0),
        acceptance_dict(checks=checks),
        name="reset-check")
    assert summary["status"] == "PASS"
    assert summary["states"]["initial"]["qpos"]["carriage_slide"] == pytest.approx(0.005)
    # With zero input the only motion is the declared spring/damping, not a scripted write.
    assert summary["states"]["terminal"]["qpos"]["carriage_slide"] == pytest.approx(
        0.0, abs=0.0002)
    assert summary["metrics"]["peak_effort"]["push"] == 0.0


def test_free_body_reset_is_rejected(tmp_path):
    payload = scenario_dict(fixture="drop_box", sampling=0.002)
    payload["phases"] = [
        {"name": "reset", "kind": "reset", "initial": {"box_free": 0.1}},
        {"name": "settle", "kind": "settle", "duration_s": 0.2},
    ]
    acceptance = acceptance_dict(
        expected=0.0, tolerance=0.1, return_max=1.0,
        checks=[{"name": "pen", "kind": "penetration_bound", "max": 0.01,
                 "units": "m"}])
    summary, _, _, _ = run_case(tmp_path, payload, acceptance, name="free-reset")
    assert summary["status"] == "ERROR"
    assert "not a hinge or slide" in summary["detail"]


def test_named_contact_telemetry_and_per_step_maxima(tmp_path):
    scenario = {
        "schema_version": "m4a-1", "scenario_id": "drop", "fixture": "drop_box",
        "seed": 1, "timestep_s": 0.001, "sampling_interval_s": 0.05,
        "budgets": {"max_steps": 20000, "max_sim_time_s": 10.0,
                    "max_trace_rows": 20000},
        "phases": [{"name": "reset", "kind": "reset"},
                   {"name": "settle", "kind": "settle", "duration_s": 0.6},
                   {"name": "hold", "kind": "hold", "duration_s": 0.2}],
    }
    acceptance = {
        "schema_version": "m4a-1", "acceptance_id": "drop_acceptance",
        "validity": {"max_penetration_m": 0.001, "max_speed_m_s": 10.0,
                     "max_energy_j": 1.0},
        "checks": [
            {"name": "contact", "kind": "contact_force_bound", "body_a": "box",
             "body_b": "floor", "max": 100.0, "units": "N"},
            {"name": "penetration", "kind": "penetration_bound", "max": 0.001,
             "units": "m"},
        ],
    }
    summary, out, _, _ = run_case(tmp_path, scenario, acceptance, name="drop")
    assert summary["status"] == "PASS", summary.get("detail")
    pairs = {(row["body_a"], row["body_b"]) for row in summary["contacts"]}
    assert ("box", "floor") in pairs or ("floor", "box") in pairs
    assert summary["metrics"]["peak_contact_force_n"] > 0.1
    assert summary["metrics"]["peak_penetration_m"] > 0.0
    # The sparse display trace must not be the source of the per-step maximum.
    assert summary["telemetry"]["trace_rows"] < 30
    assert summary["telemetry"]["state_rows"] == 801
    contacts_csv = (out / "contacts.csv").read_text()
    assert "normal_force_n" in contacts_csv.splitlines()[0]
    assert "box" in contacts_csv and "floor" in contacts_csv


def test_free_body_speed_bound_is_not_a_false_pass(tmp_path):
    scenario = {
        "schema_version": "m4a-1", "scenario_id": "drop_speed", "fixture": "drop_box",
        "seed": 1, "timestep_s": 0.001, "sampling_interval_s": 0.05,
        "budgets": {"max_steps": 20000, "max_sim_time_s": 10.0,
                    "max_trace_rows": 20000},
        "phases": [{"name": "reset", "kind": "reset"},
                   {"name": "settle", "kind": "settle", "duration_s": 0.6}],
    }
    acceptance = {
        "schema_version": "m4a-1", "acceptance_id": "drop_speed_acceptance",
        "validity": {"max_penetration_m": 0.01, "max_speed_m_s": 1e-12,
                     "max_energy_j": 1.0},
        "checks": [{"name": "penetration", "kind": "penetration_bound",
                    "max": 0.01, "units": "m"},
                   {"name": "terminal_body_speed", "kind": "body_speed",
                    "body": "box", "phase": "settle", "max": 0.1, "units": "m/s"}],
    }
    summary, out, _, _ = run_case(tmp_path, scenario, acceptance, name="drop-speed")
    assert summary["status"] == "INCONCLUSIVE"
    assert summary["metrics"]["peak_speed_m_s"] > 0.8
    terminal = summary["states"]["terminal"]
    assert terminal["free_joints"]["box_free"]["qvel"]
    assert terminal["bodies"]["box"]["linear_velocity_m_s"]
    assert any("peak speed" in reason["reason"]
               for reason in summary["validity"]["reasons"])
    assert next(c for c in summary["checks"]
                if c["name"] == "terminal_body_speed")["status"] == "PASS"


def test_effort_bound_without_an_actuate_phase_is_inconclusive(tmp_path):
    scenario = scenario_dict(phases=[
        {"name": "reset", "kind": "reset", "initial": {"carriage_slide": 0.0}},
        {"name": "settle", "kind": "settle", "duration_s": 0.2},
        {"name": "release", "kind": "release", "duration_s": 0.2},
    ])
    acceptance = acceptance_dict(checks=[
        {"name": "effort_only", "kind": "effort_bound", "actuator": "push",
         "max": 2.0, "units": "N"}])
    summary, _, _, _ = run_case(tmp_path, scenario, acceptance, name="no-actuate")
    assert summary["status"] == "INCONCLUSIVE"
    assert summary["checks"][0]["status"] == "INCONCLUSIVE"


def test_numerical_stop_records_actual_terminal_boundary(tmp_path, monkeypatch):
    import cadkit.physics.runner as runner_module

    mujoco = pytest.importorskip("mujoco")
    real_step = mujoco.mj_step
    calls = {"n": 0}

    def injected(model, data):
        real_step(model, data)
        calls["n"] += 1
        if calls["n"] == 10:
            data.qvel[0] = float("nan")

    monkeypatch.setattr(mujoco, "mj_step", injected)
    summary, out, _, _ = run_case(tmp_path, scenario_dict(), acceptance_dict(),
                                  name="numerical-stop")
    assert summary["status"] == "INCONCLUSIVE"
    assert summary["telemetry"]["stopped"] is True
    assert any(not phase["complete"] for phase in summary["phases"])
    assert summary["states"]["terminal"]["time_s"] > 0.0
    assert summary["states"]["terminal"]["qpos"]
    assert (out / "states.npz").is_file()


def test_locked_acceptance_bytes_and_hash_match_input(tmp_path):
    import hashlib

    summary, out, sp, ap = run_case(tmp_path, scenario_dict(), acceptance_dict())
    scenario_bytes = sp.read_bytes()
    acceptance_bytes = ap.read_bytes()
    assert (out / "scenario.json").read_bytes() == scenario_bytes
    assert (out / "acceptance.lock.json").read_bytes() == acceptance_bytes
    assert summary["scenario"]["sha256"] ==         hashlib.sha256(scenario_bytes).hexdigest()
    assert summary["acceptance"]["sha256"] == \
        hashlib.sha256(acceptance_bytes).hexdigest()


def test_numerical_bound_breach_is_inconclusive_even_when_checks_pass(tmp_path):
    summary, _, _, _ = run_case(
        tmp_path, scenario_dict(), acceptance_dict(max_speed=1e-12),
        name="bound-breach")
    assert summary["status"] == "INCONCLUSIVE"
    assert all(check["status"] == "PASS" for check in summary["checks"])
    assert any("peak speed" in reason["reason"]
               for reason in summary["validity"]["reasons"])


def test_numerical_fault_in_recorder_is_inconclusive():
    from cadkit.physics import require_mujoco
    from cadkit.physics.scene import export_scene

    mujoco = require_mujoco()
    spec = build_fixture("loaded_slider", 0.001)
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        export = export_scene(spec, Path(tmp))
        model = mujoco.MjModel.from_xml_path(str(export.scene_xml))
        data = mujoco.MjData(model)
        recorder = TelemetryRecorder(mujoco, model, data, sample_every=1,
                                     effort_units={"push": "N"})
        recorder.record_initial()
        recorder.begin_phase(PhaseTelemetryStub(), {"push": 0.0}, {})
        data.qvel[0] = float("nan")
        assert recorder._accumulate(recorder._observe(), 0.001) is False
        assert recorder.telemetry.invalid
        assert "non-finite state" in recorder.telemetry.invalid[0]["reason"]


class PhaseTelemetryStub:
    name = "fault"
    kind = "settle"
    requested_duration_s = 0.001
    actual_duration_s = None
    requested_steps = 1
    actual_steps = 0
    start_time_s = None
    end_time_s = None
    complete = True
    actuator = None
    requested_effort = 0.0
    effort_units = ""
    ctrl_requested = 0.0
    ctrl_effective_peak = None


def test_execution_exception_preserves_partial_evidence(tmp_path, monkeypatch):
    from cadkit.physics.telemetry import TelemetryRecorder

    original = TelemetryRecorder.step

    def explode(self, n):
        original(self, min(1, n))
        raise RuntimeError("injected execution fault")

    monkeypatch.setattr(TelemetryRecorder, "step", explode)
    summary, out, _, _ = run_case(tmp_path, scenario_dict(), acceptance_dict(),
                                  name="partial")
    assert summary["status"] == "ERROR"
    assert "injected execution fault" in summary["detail"]
    assert (out / "trace.csv").is_file()
    assert (out / "states.npz").is_file()
    assert (out / "manifest.json").is_file()
    assert (out / "summary.json").is_file()
    partial = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert partial["telemetry"]["trace_rows"] >= 1
    assert partial["artifacts"]["states"] == "states.npz"


def test_empty_checks_and_rejected_budget_create_no_run(tmp_path):
    payload = scenario_dict()
    payload["budgets"]["max_steps"] = 10
    sp = tmp_path / "scenario.json"
    ap = tmp_path / "acceptance.json"
    sp.write_text(json.dumps(payload), encoding="utf-8")
    ap.write_text(json.dumps(acceptance_dict()), encoding="utf-8")
    from cadkit.physics.scenario import ScenarioError

    with pytest.raises(ScenarioError, match="step count"):
        run_scenario_files(sp, ap, tmp_path / "run")
    assert not (tmp_path / "run").exists()


def test_output_path_that_is_a_file_is_error(tmp_path):
    target = tmp_path / "not-a-directory"
    target.write_text("file", encoding="utf-8")
    sp = tmp_path / "scenario.json"
    ap = tmp_path / "acceptance.json"
    sp.write_text(json.dumps(scenario_dict()), encoding="utf-8")
    ap.write_text(json.dumps(acceptance_dict()), encoding="utf-8")
    with pytest.raises(OSError):
        run_scenario_files(sp, ap, target)
    assert target.read_text() == "file"


def test_non_empty_output_directory_is_never_overwritten(tmp_path):
    out = tmp_path / "occupied"
    out.mkdir()
    (out / "keep.txt").write_text("keep", encoding="utf-8")
    sp = tmp_path / "scenario.json"
    ap = tmp_path / "acceptance.json"
    sp.write_text(json.dumps(scenario_dict()), encoding="utf-8")
    ap.write_text(json.dumps(acceptance_dict()), encoding="utf-8")
    with pytest.raises(FileExistsError):
        run_scenario_files(sp, ap, out)
    assert (out / "keep.txt").read_text() == "keep"


def test_cli_reports_all_four_statuses(tmp_path):
    good_sp = tmp_path / "good.json"
    good_ap = tmp_path / "acc.json"
    good_sp.write_text(json.dumps(scenario_dict()), encoding="utf-8")
    good_ap.write_text(json.dumps(acceptance_dict()), encoding="utf-8")

    passed = cad("physics", "scenario", str(good_sp), "--acceptance", str(good_ap),
                 "--out", str(tmp_path / "cli-pass"))
    assert passed.returncode == 0, passed.stdout + passed.stderr
    assert '"status": "PASS"' in passed.stdout

    fail_sp = tmp_path / "fail.json"
    fail_sp.write_text(json.dumps(scenario_dict(effort=0.0)), encoding="utf-8")
    failed = cad("physics", "scenario", str(fail_sp), "--acceptance", str(good_ap),
                 "--out", str(tmp_path / "cli-fail"))
    assert failed.returncode == 1, failed.stdout + failed.stderr
    assert '"status": "FAIL"' in failed.stdout

    inconclusive_ap = tmp_path / "inconclusive.json"
    inconclusive_ap.write_text(json.dumps(acceptance_dict(max_speed=1e-12)),
                               encoding="utf-8")
    inconclusive = cad("physics", "scenario", str(good_sp),
                       "--acceptance", str(inconclusive_ap),
                       "--out", str(tmp_path / "cli-inconclusive"))
    assert inconclusive.returncode == 2, inconclusive.stdout + inconclusive.stderr
    assert '"status": "INCONCLUSIVE"' in inconclusive.stdout

    bad_sp = tmp_path / "bad.json"
    bad_sp.write_text('{"schema_version": "m4a-1"}', encoding="utf-8")
    error = cad("physics", "scenario", str(bad_sp), "--acceptance", str(good_ap),
                "--out", str(tmp_path / "cli-error"))
    assert error.returncode == 3, error.stdout + error.stderr
    assert '"status": "ERROR"' in error.stdout
    assert not (tmp_path / "cli-error").exists()


def test_stop_compliance_is_checked_on_the_right_joint():
    """A fixture that declares a joint stop must compare that joint's compiled solref."""
    import tempfile

    from cadkit.physics import require_mujoco
    from cadkit.physics.mechanics import slider_stop_spec
    from cadkit.physics.runner import _verify_compiled
    from cadkit.physics.scene import export_scene

    mujoco = require_mujoco()
    spec = slider_stop_spec()
    with tempfile.TemporaryDirectory() as tmp:
        export = export_scene(spec, Path(tmp))
        model = mujoco.MjModel.from_xml_path(str(export.scene_xml))
        facts, compliance = _verify_compiled(mujoco, model, spec, export)
    joint = facts["joints"]["carriage_slide"]
    assert joint["stop_effective_timeconst_s"] == pytest.approx(
        joint["solreflimit"][0])
    assert compliance == []


def test_crlf_input_is_locked_byte_for_byte(tmp_path):
    import hashlib

    scenario = json.dumps(scenario_dict(), indent=2).replace(
        "\n", "\r\n").encode("utf-8")
    acceptance = json.dumps(acceptance_dict(), indent=2).replace(
        "\n", "\r\n").encode("utf-8")
    assert b"\r\n" in scenario and b"\r\n" in acceptance
    sp = tmp_path / "scenario.json"
    ap = tmp_path / "acceptance.json"
    sp.write_bytes(scenario)
    ap.write_bytes(acceptance)
    summary = run_scenario_files(sp, ap, tmp_path / "crlf-run")
    out = tmp_path / "crlf-run"
    assert summary["status"] == "PASS"
    assert (out / "scenario.json").read_bytes() == scenario
    assert (out / "acceptance.lock.json").read_bytes() == acceptance
    assert summary["acceptance"]["sha256"] == hashlib.sha256(acceptance).hexdigest()


def test_cli_maps_overflow_prone_configuration_to_error(tmp_path):
    scenario = scenario_dict(sampling_interval_s=1e308)
    sp = tmp_path / "overflow.json"
    ap = tmp_path / "acceptance.json"
    sp.write_text(json.dumps(scenario), encoding="utf-8")
    ap.write_text(json.dumps(acceptance_dict()), encoding="utf-8")
    r = cad("physics", "scenario", str(sp), "--acceptance", str(ap),
            "--out", str(tmp_path / "overflow-run"))
    assert r.returncode == 3, r.stdout + r.stderr
    assert '"status": "ERROR"' in r.stdout
    assert not (tmp_path / "overflow-run").exists()


def test_scenario_modules_do_not_import_mujoco():
    code = ("import sys, cadkit.physics.scenario, cadkit.physics.runner, "
            "cadkit.physics.evaluate, cadkit.physics.telemetry; "
            "print('mujoco' in sys.modules)")
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT,
                       capture_output=True, text=True, timeout=120, env=_env())
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "False"


# ----------------------------------------------------------------- M4a repair regressions
def _patch_fixture(monkeypatch, mutate):
    import cadkit.physics.runner as runner_module

    original = runner_module.build_fixture

    def patched(name, timestep_s=None):
        spec = original(name, timestep_s)
        return mutate(name, spec)

    monkeypatch.setattr(runner_module, "build_fixture", patched)


def _one_step_scenario():
    return {
        "schema_version": "m4a-1", "scenario_id": "one_step", "fixture": "drop_box",
        "seed": 0, "timestep_s": 0.001, "sampling_interval_s": 0.001,
        "budgets": {"max_steps": 10, "max_sim_time_s": 0.01, "max_trace_rows": 10},
        "phases": [{"name": "reset", "kind": "reset"},
                   {"name": "fall", "kind": "hold", "duration_s": 0.001}],
    }


def _speed_acceptance(maximum=100.0, validity=None):
    return {
        "schema_version": "m4a-1", "acceptance_id": "speed_check",
        "validity": validity or {},
        "checks": [{"name": "body_slow", "kind": "body_speed", "body": "box",
                    "phase": "fall", "max": maximum, "units": "m/s"}],
    }


def test_euler_one_step_body_state_is_coherent(tmp_path, monkeypatch):
    _patch_fixture(monkeypatch,
                   lambda name, spec: replace(spec, integrator="Euler")
                   if name == "drop_box" else spec)
    summary, out, _, _ = run_case(tmp_path, _one_step_scenario(),
                                  _speed_acceptance(0.005), name="euler-one-step")
    assert summary["status"] == "FAIL"  # a real unmet speed predicate, not a stale PASS
    check = summary["checks"][0]
    assert check["status"] == "FAIL"
    assert check["value"] == pytest.approx(9.80665e-3, rel=1e-6)
    terminal = summary["states"]["terminal"]
    assert terminal["free_joints"]["box_free"]["qvel"][2] == pytest.approx(-9.80665e-3)
    assert terminal["bodies"]["box"]["linear_velocity_m_s"][2] == pytest.approx(-9.80665e-3)
    assert terminal["bodies"]["box"]["xipos"][2] == pytest.approx(
        0.05 - 9.80665e-6, abs=1e-9)
    sampling = summary["solver"]["force_sampling"]
    assert sampling["force_time_s"] == "state_time_s"
    assert sampling["state_rewrites"] is False
    header = (out / "trace.csv").read_text(encoding="utf-8").splitlines()[0]
    assert "force_stage" in header


def test_rk4_free_fall_and_jointed_body_states_are_coherent(tmp_path):
    scenario = _one_step_scenario()
    scenario["phases"][1]["duration_s"] = 0.05
    scenario["budgets"]["max_steps"] = 200
    scenario["budgets"]["max_sim_time_s"] = 0.1
    scenario["budgets"]["max_trace_rows"] = 200
    summary, _, _, _ = run_case(tmp_path, scenario, _speed_acceptance(100.0),
                                name="rk4-fall")
    assert summary["status"] == "PASS"
    terminal = summary["states"]["terminal"]
    t = terminal["time_s"]
    assert terminal["free_joints"]["box_free"]["qvel"][2] == pytest.approx(-9.80665 * t)
    assert terminal["bodies"]["box"]["linear_velocity_m_s"][2] == pytest.approx(-9.80665 * t)
    assert terminal["bodies"]["box"]["xipos"][2] == pytest.approx(
        0.05 - 0.5 * 9.80665 * t * t, abs=2e-6)

    # Jointed body: the carriage body velocity must agree with the joint coordinate velocity.
    summary, _, _, _ = run_case(tmp_path, scenario_dict(effort=1.0), acceptance_dict(),
                                name="jointed-state")
    assert summary["status"] == "PASS"
    terminal = summary["states"]["terminal"]
    qvel = terminal["qvel"]["carriage_slide"]
    body_velocity = terminal["bodies"]["carriage"]["linear_velocity_m_s"]
    assert body_velocity[0] == pytest.approx(qvel, abs=1e-9)
    assert body_velocity[1] == pytest.approx(0.0, abs=1e-9)
    assert body_velocity[2] == pytest.approx(0.0, abs=1e-9)


def test_sampling_does_not_perturb_the_trajectory():
    import tempfile

    from cadkit.physics import require_mujoco
    from cadkit.physics.scene import export_scene
    from cadkit.physics.telemetry import PhaseTelemetry

    mujoco = require_mujoco()
    spec = build_fixture("drop_box", 0.001)
    with tempfile.TemporaryDirectory() as tmp:
        export = export_scene(spec, Path(tmp))
        model = mujoco.MjModel.from_xml_path(str(export.scene_xml))
        model.opt.enableflags |= int(mujoco.mjtEnableBit.mjENBL_ENERGY)

        plain = mujoco.MjData(model)
        mujoco.mj_resetData(model, plain)
        mujoco.mj_forward(model, plain)
        for _ in range(50):
            mujoco.mj_step(model, plain)

        recorded = mujoco.MjData(model)
        mujoco.mj_resetData(model, recorded)
        mujoco.mj_forward(model, recorded)
        recorder = TelemetryRecorder(mujoco, model, recorded, sample_every=1,
                                     effort_units={})
        assert recorder.record_initial("reset") is True
        phase = PhaseTelemetry(name="fall", kind="hold", requested_duration_s=0.05,
                               requested_steps=50)
        recorder.begin_phase(phase, {}, {})
        recorder.step(50)

    assert np.array_equal(plain.qpos, recorded.qpos)
    assert np.array_equal(plain.qvel, recorded.qvel)
    assert float(plain.time) == float(recorded.time)


def test_initial_overlap_is_rejected_with_zero_steps(tmp_path, monkeypatch):
    from build123d import Box, Pos

    def lowered(name, spec):
        if name != "drop_box":
            return spec
        bodies = []
        for body in spec.bodies:
            if body.body_id != "box":
                bodies.append(body)
                continue
            part = body.parts[0]
            bodies.append(replace(body, parts=(replace(
                part,
                shape=Pos(0.0, 0.0, 9.8) * Box(20.0, 20.0, 20.0),
                colliders=(replace(part.colliders[0], pos_mm=(0.0, 0.0, 9.8)),),
            ),)))
        return replace(spec, integrator="RK4", bodies=tuple(bodies))

    _patch_fixture(monkeypatch, lowered)
    summary, out, _, _ = run_case(
        tmp_path, _one_step_scenario(),
        _speed_acceptance(100.0, validity={"max_penetration_m": 0.00019}),
        name="initial-overlap")
    assert summary["status"] == "INCONCLUSIVE"
    assert summary["telemetry"]["initial_rejected"] is True
    reasons = summary["validity"]["reasons"]
    assert [r["stage"] for r in reasons] == ["initial"]
    assert "initial penetration" in reasons[0]["reason"]
    assert summary["metrics"]["initial_penetration_m"] == pytest.approx(0.0002, abs=1e-12)
    assert summary["metrics"]["peak_penetration_m"] == pytest.approx(
        summary["metrics"]["initial_penetration_m"])
    assert all(phase["actual_steps"] == 0 for phase in summary["phases"][1:])
    assert all(not phase["complete"] for phase in summary["phases"][1:])
    assert (out / "trace.csv").is_file()
    assert (out / "states.npz").is_file()
    assert (out / "summary.json").is_file()


@pytest.mark.parametrize("validity", [{}, {"max_speed_m_s": 1.0}])
def test_programmatic_acceptance_lock_round_trips(tmp_path, validity):
    from dataclasses import replace as dc_replace

    from cadkit.physics.runner import run_scenario

    sp = tmp_path / "s.json"
    ap = tmp_path / "a.json"
    sp.write_text(json.dumps(scenario_dict()), encoding="utf-8")
    ap.write_text(json.dumps(acceptance_dict(validity=validity)), encoding="utf-8")
    scenario = load_scenario(sp)
    acceptance = load_acceptance(ap)
    # Clear the source text exactly as a programmatic caller would.
    scenario = dc_replace(scenario, source_text="")
    acceptance = dc_replace(acceptance, source_text="")
    summary = run_scenario(scenario, acceptance, tmp_path / "prog")
    lock = load_acceptance(tmp_path / "prog" / "acceptance.lock.json")
    assert lock.hash() == summary["acceptance"]["hash"]
    payload = json.loads((tmp_path / "prog" / "acceptance.lock.json").read_text(
        encoding="utf-8"))
    assert all(value is not None for value in payload["validity"].values())
    assert payload["validity"] == {k: v for k, v in validity.items()}


def test_unsupported_integrator_is_rejected_before_stepping(tmp_path, monkeypatch):
    _patch_fixture(monkeypatch,
                   lambda name, spec: replace(spec, integrator="implicit")
                   if name == "drop_box" else spec)
    from cadkit.physics.scenario import ScenarioError

    with pytest.raises(ScenarioError, match="not supported"):
        run_case(tmp_path, _one_step_scenario(), _speed_acceptance(100.0),
                 name="implicit")
    assert not (tmp_path / "implicit").exists()


def test_read_json_bounds_the_read_and_rejects_nonregular_inputs(tmp_path, monkeypatch):
    import os

    from cadkit.physics import scenario as scenario_module

    cap = scenario_module.MAX_CONFIG_BYTES
    requested = []
    real_read = os.read

    def counting_read(fd, size):
        requested.append(size)
        return real_read(fd, size)

    monkeypatch.setattr(scenario_module.os, "read", counting_read)
    big = tmp_path / "big.json"
    with big.open("wb") as fh:
        fh.truncate(cap + 4096)
    with pytest.raises(scenario_module.ScenarioError, match="above the"):
        scenario_module._read_json(big, "scenario")
    assert requested and max(requested) <= cap + 1

    body = b'{"a": 1}'
    exact = tmp_path / "exact.json"
    exact.write_bytes(body + b" " * (cap - len(body)))
    assert scenario_module._read_json(exact, "scenario")[0] == {"a": 1}

    directory = tmp_path / "adir"
    directory.mkdir()
    with pytest.raises(scenario_module.ScenarioError, match="not a regular file"):
        scenario_module._read_json(directory, "scenario")

    fifo = tmp_path / "afifo"
    os.mkfifo(fifo)
    with pytest.raises(scenario_module.ScenarioError, match="not a regular file"):
        scenario_module._read_json(fifo, "scenario")

    link = tmp_path / "link.json"
    link.symlink_to(exact)
    assert scenario_module._read_json(link, "scenario")[0] == {"a": 1}


def test_solver_warning_forces_inconclusive(tmp_path, monkeypatch):
    import mujoco as mujoco_module

    real_step = mujoco_module.mj_step
    state = {"done": False}

    def warning_step(model, data):
        real_step(model, data)
        if not state["done"]:
            state["done"] = True
            data.warning[int(mujoco_module.mjtWarning.mjWARN_BADQVEL)].number = 1

    monkeypatch.setattr(mujoco_module, "mj_step", warning_step)
    summary, out, _, _ = run_case(tmp_path, scenario_dict(), acceptance_dict(),
                                  name="warning-gate")
    assert summary["status"] == "INCONCLUSIVE"
    assert any("solver warning badqvel" in reason["reason"]
               for reason in summary["validity"]["reasons"])
    assert summary["telemetry"]["warnings"]["badqvel"] == 1
    assert (out / "trace.csv").is_file()


def test_mutated_acceptance_does_not_copy_a_stale_lock(tmp_path):
    from dataclasses import replace as dc_replace

    from cadkit.physics.runner import run_scenario

    sp = tmp_path / "s.json"
    ap = tmp_path / "a.json"
    sp.write_text(json.dumps(scenario_dict()), encoding="utf-8")
    ap.write_text(json.dumps(acceptance_dict(max_speed=100.0)), encoding="utf-8")
    scenario = load_scenario(sp)
    acceptance = load_acceptance(ap)
    mutated = dc_replace(acceptance, validity=dc_replace(acceptance.validity,
                                                         max_speed_m_s=1e-12))
    assert mutated.source_text  # stale file text retained by the dataclass
    summary = run_scenario(scenario, mutated, tmp_path / "mutated")
    lock = load_acceptance(tmp_path / "mutated" / "acceptance.lock.json")
    assert lock.hash() == summary["acceptance"]["hash"]
    assert lock.validity.max_speed_m_s == 1e-12


@pytest.mark.parametrize("field", [
    "qacc", "actuator_force", "qfrc_actuator", "qfrc_passive",
    "qfrc_constraint", "qfrc_spring", "qfrc_damper", "energy",
])
def test_scratch_forward_cannot_hide_nonfinite_live_solver_output(tmp_path, monkeypatch, field):
    import mujoco as mujoco_module

    real_step = mujoco_module.mj_step
    injected = False

    def corrupted_step(model, data):
        nonlocal injected
        real_step(model, data)
        if not injected:
            injected = True
            getattr(data, field).flat[0] = np.nan

    monkeypatch.setattr(mujoco_module, "mj_step", corrupted_step)
    summary, out, _, _ = run_case(tmp_path, scenario_dict(), acceptance_dict(),
                                  name="live-nonfinite")
    assert summary["status"] == "INCONCLUSIVE"
    assert any(r["stage"] == "step" and "non-finite live" in r["reason"]
               for r in summary["validity"]["reasons"])
    assert sum(p["actual_steps"] for p in summary["phases"]) == 1
    assert any(not p["complete"] for p in summary["phases"])
    # Strict JSON and an archive survive the injected numerical failure.
    assert json.loads((out / "summary.json").read_text())["status"] == "INCONCLUSIVE"
    assert (out / "states.npz").is_file()


def test_scratch_forward_warning_rejects_initial_state(tmp_path, monkeypatch):
    import mujoco as mujoco_module

    real_observe = TelemetryRecorder._observe

    def warning_observe(self):
        observed = real_observe(self)
        observed.warning[int(mujoco_module.mjtWarning.mjWARN_BADQACC)].number = 1
        return observed

    monkeypatch.setattr(TelemetryRecorder, "_observe", warning_observe)
    summary, _, _, _ = run_case(tmp_path, scenario_dict(), acceptance_dict(),
                                 name="observation-warning")
    assert summary["status"] == "INCONCLUSIVE"
    assert any(r["stage"] == "initial" and "observation solver warning badqacc" in r["reason"]
               for r in summary["validity"]["reasons"])
    assert sum(p["actual_steps"] for p in summary["phases"]) == 0


def test_initial_nonfinite_live_acceleration_takes_zero_steps(tmp_path, monkeypatch):
    from cadkit.physics import runner

    real_reset = runner._apply_reset

    def corrupted_reset(mujoco_module, model, data, phase):
        real_reset(mujoco_module, model, data, phase)
        data.qacc[0] = np.inf

    monkeypatch.setattr(runner, "_apply_reset", corrupted_reset)
    summary, _, _, _ = run_case(tmp_path, scenario_dict(), acceptance_dict(),
                                 name="initial-live-nonfinite")
    assert summary["status"] == "INCONCLUSIVE"
    assert any(r["stage"] == "initial" and r["reason"] == "non-finite live acceleration"
               for r in summary["validity"]["reasons"])
    assert sum(p["actual_steps"] for p in summary["phases"]) == 0


def test_reset_phase_name_is_used_in_rows(tmp_path):
    scenario = scenario_dict(phases=[
        {"name": "start", "kind": "reset", "initial": {"carriage_slide": 0.0}},
        {"name": "settle", "kind": "settle", "duration_s": 0.2},
        {"name": "hold", "kind": "hold", "duration_s": 0.1},
    ])
    acceptance = acceptance_dict(checks=[
        {"name": "speed", "kind": "terminal_speed", "joint": "carriage_slide",
         "phase": "hold", "max": 1.0, "units": "m/s"}])
    summary, out, _, _ = run_case(tmp_path, scenario, acceptance, name="reset-name")
    assert summary["status"] == "PASS"
    first_row = (out / "trace.csv").read_text(encoding="utf-8").splitlines()[1]
    assert ",start,0," in first_row
    assert summary["states"]["initial"]["hash"]


def test_direct_checkspec_requires_units():
    from cadkit.physics.scenario import CheckSpec

    with pytest.raises(ValueError, match="units"):
        CheckSpec(name="p", kind="penetration_bound", maximum=0.01)
