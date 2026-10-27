"""Playback sizes its states.npz caps from the run's own scenario budgets, as replay does."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("mujoco")

from cadkit.physics import playback  # noqa: E402
from cadkit.physics.runner import run_scenario_files  # noqa: E402

ACCEPTANCE = {
    "schema_version": "m4a-1", "acceptance_id": "drop_acceptance",
    "validity": {"max_penetration_m": 0.001, "max_speed_m_s": 10.0, "max_energy_j": 1.0},
    "checks": [{"name": "penetration", "kind": "penetration_bound", "max": 0.001, "units": "m"}],
}


def _drop_run(root: Path, budgets: dict) -> Path:
    scenario = {
        "schema_version": "m4a-1", "scenario_id": "drop", "fixture": "drop_box", "seed": 1,
        "timestep_s": 0.001, "sampling_interval_s": 0.05,
        "budgets": {"max_steps": 20000, "max_sim_time_s": 10.0, "max_trace_rows": 20000,
                    **budgets},
        "phases": [{"name": "reset", "kind": "reset"},
                   {"name": "settle", "kind": "settle", "duration_s": 0.3}],
    }
    root.mkdir(parents=True)
    (root / "scenario.json").write_text(json.dumps(scenario), encoding="utf-8")
    (root / "acceptance.json").write_text(json.dumps(ACCEPTANCE), encoding="utf-8")
    summary = run_scenario_files(root / "scenario.json", root / "acceptance.json", root / "run")
    assert summary["status"] == "PASS", summary.get("detail")
    return root / "run"


def test_declared_state_budget_raises_the_playback_cap(tmp_path, monkeypatch):
    declared = _drop_run(tmp_path / "declared", {"max_state_bytes": 64 * 1024 * 1024})
    undeclared = _drop_run(tmp_path / "undeclared", {})
    # Shrink the default so these tiny archives stand in for runs above the 512 MiB default.
    monkeypatch.setattr(playback, "MAX_ARCHIVE_BYTES", 1024)

    loaded = playback.Playback(declared)
    assert len(loaded.times) > 1

    with pytest.raises(playback.PlaybackError, match="budget"):
        playback.Playback(undeclared)
