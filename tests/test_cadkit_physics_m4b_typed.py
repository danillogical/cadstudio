"""M4b typed AssemblySpec execution API on an independent non-Pocky fixture."""
from __future__ import annotations

import json

import pytest

from cadkit.physics.mechanics import hinge_oscillator_spec
from cadkit.physics.replay import replay_run
from cadkit.physics.runner import run_assembly, run_scenario_files
from cadkit.physics.scenario import (
    AcceptanceSpec,
    BudgetSpec,
    CheckSpec,
    PhaseSpec,
    ScenarioSpec,
    ScenarioError,
    ValiditySpec,
    build_fixture,
)

pytest.importorskip("mujoco")


def _hinge_scenario():
    return ScenarioSpec(
        "hinge_api", "hinge_oscillator", 0,
        (PhaseSpec("reset", "reset", initial=(("arm_hinge", 0.0),)),
         PhaseSpec("release", "release", 0.2)),
        0.001, 0.002, BudgetSpec(20000, 10.0, 20000))


def _hinge_acceptance():
    return AcceptanceSpec("hinge_acc", (
        CheckSpec(name="speed", kind="terminal_speed", joint="arm_hinge",
                  phase="release", maximum=10.0, units="rad/s"),), ValiditySpec())


def test_run_assembly_executes_typed_non_registry_fixture(tmp_path):
    spec = hinge_oscillator_spec()
    summary = run_assembly(spec, _hinge_scenario(), _hinge_acceptance(),
                           tmp_path / "run")
    assert summary["status"] == "PASS"
    assert summary["assembly"] == "m3_hinge_oscillator"
    assert summary["fixture"] == "m3_hinge_oscillator"
    assert summary["telemetry"]["state_rows"] == 201
    assert (tmp_path / "run" / "states.npz").is_file()
    assert (tmp_path / "run" / "state_meta.json").is_file()
    assert (tmp_path / "run" / "checkpoints.npz").is_file()
    # The typed run is itself replayable.
    result = replay_run(tmp_path / "run", tmp_path / "rep")
    assert result["status"] == "PASS" and result["reproduced"] is True


def test_json_execution_still_enforces_the_registry_allowlist(tmp_path):
    payload = {
        "schema_version": "m4a-1", "scenario_id": "pocky", "fixture": "pocky",
        "phases": [{"name": "reset", "kind": "reset"},
                   {"name": "hold", "kind": "hold", "duration_s": 0.001}],
        "budgets": {"max_steps": 10, "max_sim_time_s": 1.0, "max_trace_rows": 10},
    }
    sp = tmp_path / "s.json"
    ap = tmp_path / "a.json"
    sp.write_text(json.dumps(payload), encoding="utf-8")
    ap.write_text(json.dumps({"schema_version": "m4a-1", "acceptance_id": "a",
                              "validity": {},
                              "checks": [{"name": "p", "kind": "penetration_bound",
                                          "max": 0.01, "units": "m"}]}), encoding="utf-8")
    with pytest.raises(ScenarioError, match="unknown fixture"):
        run_scenario_files(sp, ap, tmp_path / "run")
    assert not (tmp_path / "run").exists()
