"""Scenario ``body_force`` ``damping_n_s_m``: loading, hashing, speed limiting, determinism, replay.

Uses the registered ``drop_box`` fixture (free ``box`` on a fixed ``floor``).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("mujoco", reason="optional physics extra not installed")

from cadkit.physics.replay import replay_run  # noqa: E402
from cadkit.physics.runner import run_scenario_files  # noqa: E402
from cadkit.physics.scenario import ScenarioError, scenario_from_text  # noqa: E402

ACCEPTANCE = {
    "schema_version": "m4a-1", "acceptance_id": "bf_acc",
    "validity": {"max_penetration_m": 0.005},
    "checks": [{"name": "pen", "kind": "penetration_bound", "max": 0.005, "units": "m"}],
}


def phases(damping=None, end=(0.09, 0.0, 0.0), start=(0.0, 0.0, 0.0)):
    force = {"body": "box", "force_n": list(start), "force_end_n": list(end)}
    if damping is not None:
        force["damping_n_s_m"] = damping
    return [{"name": "reset", "kind": "reset"},
            {"name": "settle", "kind": "settle", "duration_s": 0.3},
            {"name": "pull", "kind": "hold", "duration_s": 1.5, "body_force": force}]


def scenario_doc(ph):
    return {"schema_version": "m4a-1", "scenario_id": "bf", "fixture": "drop_box",
            "seed": 1, "timestep_s": 0.001, "sampling_interval_s": 0.02,
            "budgets": {"max_steps": 20000, "max_sim_time_s": 10.0, "max_trace_rows": 20000},
            "phases": ph}


def execute(base: Path, name: str, ph) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    s, a = base / f"{name}-s.json", base / f"{name}-a.json"
    s.write_text(json.dumps(scenario_doc(ph)), encoding="utf-8")
    a.write_text(json.dumps(ACCEPTANCE), encoding="utf-8")
    summary = run_scenario_files(s, a, base / name)
    assert summary["status"] == "PASS", summary.get("detail")
    return base / name


def _states(run: Path):
    z = np.load(run / "states.npz")
    return {k: z[k] for k in z.files}


def _speed_x(run: Path):
    st = _states(run)
    return st["time"], st["qvel"][:, 0]


@pytest.fixture(scope="module")
def damped_a(tmp_path_factory) -> Path:
    return execute(tmp_path_factory.mktemp("bf_a"), "run", phases(damping=1.0))


@pytest.fixture(scope="module")
def damped_b(tmp_path_factory) -> Path:
    return execute(tmp_path_factory.mktemp("bf_b"), "run", phases(damping=1.0))


def test_damping_is_validated():
    for bad in (-1.0, float("nan"), float("inf"), "x", True):
        doc = json.dumps(scenario_doc(phases(damping=bad)), allow_nan=True)
        with pytest.raises(ScenarioError):
            scenario_from_text(doc)


def test_unset_damping_is_omitted_and_keeps_the_hash():
    plain = scenario_from_text(json.dumps(scenario_doc(phases())))
    assert "damping_n_s_m" not in json.dumps(plain.to_dict())
    damped = scenario_from_text(json.dumps(scenario_doc(phases(damping=1.0))))
    assert damped.to_dict()["phases"][2]["body_force"]["damping_n_s_m"] == 1.0
    assert damped.hash() != plain.hash()


def test_damping_limits_speed_where_a_pure_force_runs_away(tmp_path, damped_a):
    # The 0 -> 0.09 N ramp stays below mg (0.1 N) so the cube slides instead of tipping;
    # friction is 0.4 mg = 0.04 N, so it breaks free about two thirds of the way through.
    free = execute(tmp_path, "free", phases())
    t, v_free = _speed_x(free)
    t_d, v_damped = _speed_x(damped_a)
    for label, tt, vv in (("pure force", t, v_free), ("damping 1.0", t_d, v_damped)):
        print(label, [(round(float(tt[i]), 2), round(float(vv[i]), 3))
                      for i in range(0, len(tt), 150)])
    assert v_free.max() > 1.0, "pure force should accelerate without bound once it breaks free"
    assert 0.0 < v_damped.max() < 0.2
    assert v_damped.min() > -0.05, "damping must not push the body backwards"


def test_damped_speed_settles_near_force_minus_friction_over_damping(tmp_path):
    # Constant 0.08 N, c = 1 N s/m, Coulomb friction 0.4 m g = 0.0398 N: v -> 0.040 m/s.
    constant = (0.08, 0.0, 0.0)
    run = execute(tmp_path, "steady", phases(damping=1.0, end=constant, start=constant))
    t, v = _speed_x(run)
    print("steady", [(round(float(t[i]), 2), round(float(v[i]), 4))
                     for i in range(0, len(t), 150)])
    # Stop before ~1.6 s, when the box reaches the edge of the 120 mm floor and falls.
    window = v[(t >= 0.6) & (t <= 1.4)]
    assert window.mean() == pytest.approx((0.08 - 0.4 * 0.01016 * 9.80665) / 1.0, rel=0.25)


def test_identical_damped_runs_are_byte_identical(damped_a, damped_b):
    assert (damped_a / "states.npz").read_bytes() == (damped_b / "states.npz").read_bytes()


def test_replay_and_post_settle_checkpoint_replay_match(damped_a, tmp_path):
    # The checkpoint continuation restarts mid-run (after settle) and replays the damped pull.
    result = replay_run(damped_a, tmp_path / "rep")
    assert result["status"] == "PASS"
    assert result["reproduced"] is True
    assert result["state_comparison"]["max_abs_diff"] == 0.0
    assert result["post_settle_continuation"]["ok"] is True
