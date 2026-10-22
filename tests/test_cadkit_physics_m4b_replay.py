"""M4b genuine replay: real saved-scene stepping, checkpoints, tamper rejection."""
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
from cadkit.physics.mechanics import hinge_oscillator_spec
from cadkit.physics.replay import ReplayError, replay_run
from cadkit.physics.runner import run_assembly, run_scenario_files
from cadkit.physics.scenario import (
    AcceptanceSpec,
    BudgetSpec,
    CheckSpec,
    PhaseSpec,
    ScenarioSpec,
    ValiditySpec,
    build_fixture,
)

pytest.importorskip("mujoco")


def _env():
    env = dict(os.environ)
    env["PATH"] = f"{Path.home() / '.local' / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    return env


def cad(*args, timeout=300):
    return subprocess.run([sys.executable, "-m", "cadkit.cli", *args], cwd=REPO_ROOT,
                          capture_output=True, text=True, encoding="utf-8",
                          timeout=timeout, env=_env())


def _write(path: Path, payload) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def scenario(fixture, phases, scenario_id="m4b", **overrides):
    payload = {
        "schema_version": "m4a-1", "scenario_id": scenario_id, "fixture": fixture,
        "seed": 7, "timestep_s": 0.001, "sampling_interval_s": 0.002,
        "budgets": {"max_steps": 20000, "max_sim_time_s": 10.0, "max_trace_rows": 20000},
        "phases": phases,
    }
    payload.update(overrides)
    return payload


def acceptance(checks, validity=None):
    return {"schema_version": "m4a-1", "acceptance_id": "m4b_acc",
            "validity": validity or {}, "checks": checks}


SLIDER_PHASES = [
    {"name": "reset", "kind": "reset", "initial": {"carriage_slide": 0.0}},
    {"name": "settle", "kind": "settle", "duration_s": 0.1},
    {"name": "push", "kind": "actuate", "duration_s": 0.2, "actuator": "push",
     "effort": 1.0},
    {"name": "release", "kind": "release", "duration_s": 0.2},
]


def _run(tmp_path, sc, ac, name="run"):
    sp = _write(tmp_path / f"{name}-s.json", sc)
    ap = _write(tmp_path / f"{name}-a.json", ac)
    summary = run_scenario_files(sp, ap, tmp_path / name)
    return summary, tmp_path / name, sp, ap


def _replay(tmp_path, run_dir, name="rep"):
    return replay_run(run_dir, tmp_path / name)


def test_slider_replay_reproduces_and_keeps_source_hashes(tmp_path):
    summary, run_dir, _, _ = _run(tmp_path, scenario("loaded_slider", SLIDER_PHASES),
                                  acceptance([
                                      {"name": "held", "kind": "joint_displacement",
                                       "joint": "carriage_slide", "to_phase": "push",
                                       "expected": 0.02, "tolerance": 0.005, "units": "m"},
                                      {"name": "return", "kind": "return_displacement",
                                       "joint": "carriage_slide", "phase": "release",
                                       "reference": 0.0, "max": 0.005, "units": "m"},
                                  ]))
    assert summary["status"] == "PASS"
    before = {rel: (run_dir / rel).read_bytes()
              for rel in ("manifest.json", "summary.json", "states.npz", "scene.xml")}
    result = _replay(tmp_path, run_dir)
    assert result["status"] == "PASS"
    assert result["reproduced"] is True
    assert result["state_comparison"]["ok"] is True
    assert result["state_comparison"]["max_abs_diff"] == 0.0
    assert result["post_settle_continuation"]["ok"] is True
    assert result["evaluation_comparison"]["differences"] == []
    assert (tmp_path / "rep" / "replay.json").is_file()
    assert (tmp_path / "rep" / "replayed_states.npz").is_file()
    for rel, raw in before.items():
        assert (run_dir / rel).read_bytes() == raw, rel


def test_negative_gear_clipping_replays(tmp_path):
    phases = [
        {"name": "reset", "kind": "reset", "initial": {"carriage_slide": 0.0}},
        {"name": "push", "kind": "actuate", "duration_s": 0.2, "actuator": "push",
         "effort": 1.0e6},
        {"name": "hold", "kind": "hold", "duration_s": 0.1},
    ]
    summary, run_dir, _, _ = _run(
        tmp_path, scenario("loaded_slider_negative_gear", phases, scenario_id="gear"),
        acceptance([
            {"name": "held", "kind": "joint_displacement", "joint": "carriage_slide",
             "to_phase": "push", "expected": 0.04, "tolerance": 0.005, "units": "m"},
            {"name": "effort", "kind": "effort_bound", "actuator": "push", "max": 2.0,
             "units": "N"},
        ]))
    assert summary["status"] == "PASS"
    assert summary["metrics"]["peak_effort"]["push"] == pytest.approx(2.0)
    result = _replay(tmp_path, run_dir)
    assert result["status"] == "PASS" and result["reproduced"] is True


@pytest.mark.parametrize("integrator", ["Euler", "RK4"])
def test_free_fall_replays_under_euler_and_rk4(tmp_path, integrator):
    spec = replace(build_fixture("drop_box", 0.001), integrator=integrator)
    scenario_spec = ScenarioSpec(
        f"drop_{integrator}", "drop_box", 0,
        (PhaseSpec("reset", "reset"), PhaseSpec("fall", "hold", 0.05)),
        0.001, 0.002, BudgetSpec(20000, 10.0, 20000))
    acceptance_spec = AcceptanceSpec("drop_acc", (
        CheckSpec(name="speed", kind="body_speed", body="box", phase="fall",
                  maximum=1.0, units="m/s"),), ValiditySpec())
    run_dir = tmp_path / f"drop-{integrator}"
    summary = run_assembly(spec, scenario_spec, acceptance_spec, run_dir)
    assert summary["status"] == "PASS"
    result = replay_run(run_dir, tmp_path / f"rep-{integrator}")
    assert result["status"] == "PASS" and result["reproduced"] is True
    assert result["state_comparison"]["max_abs_diff"] == 0.0


def test_physical_fail_source_replays_equivalently(tmp_path):
    phases = [
        {"name": "reset", "kind": "reset", "initial": {"carriage_slide": 0.0}},
        {"name": "push", "kind": "actuate", "duration_s": 0.2, "actuator": "push",
         "effort": 0.0},
        {"name": "hold", "kind": "hold", "duration_s": 0.1},
    ]
    summary, run_dir, _, _ = _run(
        tmp_path, scenario("loaded_slider", phases, scenario_id="fail"),
        acceptance([{"name": "held", "kind": "joint_displacement",
                     "joint": "carriage_slide", "to_phase": "push", "expected": 0.02,
                     "tolerance": 0.005, "units": "m"}]))
    assert summary["status"] == "FAIL"
    result = _replay(tmp_path, run_dir)
    assert result["status"] == "FAIL" and result["reproduced"] is True


def test_inconclusive_source_replays_equivalently(tmp_path):
    summary, run_dir, _, _ = _run(
        tmp_path, scenario("loaded_slider", SLIDER_PHASES, scenario_id="inconclusive"),
        acceptance([{"name": "held", "kind": "joint_displacement",
                     "joint": "carriage_slide", "to_phase": "push", "expected": 0.02,
                     "tolerance": 0.005, "units": "m"}],
                   validity={"max_speed_m_s": 1e-12}))
    assert summary["status"] == "INCONCLUSIVE"
    result = _replay(tmp_path, run_dir)
    assert result["status"] == "INCONCLUSIVE" and result["reproduced"] is True


def test_numerical_stop_source_replays_inconclusive(tmp_path, monkeypatch):
    import mujoco

    real_step = mujoco.mj_step
    calls = {"n": 0}

    def injected(model, data):
        real_step(model, data)
        calls["n"] += 1
        if calls["n"] == 5:
            data.qvel[0] = float("nan")

    monkeypatch.setattr(mujoco, "mj_step", injected)
    summary, run_dir, _, _ = _run(
        tmp_path, scenario("loaded_slider", SLIDER_PHASES, scenario_id="stop"),
        acceptance([{"name": "held", "kind": "joint_displacement",
                     "joint": "carriage_slide", "to_phase": "push", "expected": 0.02,
                     "tolerance": 0.005, "units": "m"}]))
    assert summary["status"] == "INCONCLUSIVE"
    assert summary["telemetry"]["state_rows"] < summary["plan"]["state_rows"]
    calls["n"] = 0  # replay injects the same fault on its own fifth step
    result = replay_run(run_dir, tmp_path / "rep-stop")
    assert result["status"] == "INCONCLUSIVE"
    assert result["reproduced"] is True


def test_cli_replay_exit_codes_and_fresh_output(tmp_path):
    summary, run_dir, _, _ = _run(tmp_path, scenario("loaded_slider", SLIDER_PHASES),
                                  acceptance([{"name": "held", "kind": "joint_displacement",
                                               "joint": "carriage_slide",
                                               "to_phase": "push", "expected": 0.02,
                                               "tolerance": 0.005, "units": "m"}]))
    assert summary["status"] == "PASS"
    ok = cad("physics", "replay", str(run_dir), "--out", str(tmp_path / "cli-rep"))
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert '"status": "PASS"' in ok.stdout
    again = cad("physics", "replay", str(run_dir), "--out", str(tmp_path / "cli-rep"))
    assert again.returncode == 3, again.stdout + again.stderr
    assert '"status": "ERROR"' in again.stdout
