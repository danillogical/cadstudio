"""Replay read caps are derived from the run's own declared scenario budgets."""
from __future__ import annotations

import json

import pytest

pytest.importorskip("mujoco")

from cadkit.physics import replay  # noqa: E402
from cadkit.physics.evidence import EvidenceError  # noqa: E402
from cadkit.physics.replay import (  # noqa: E402
    HARD_EVIDENCE_BYTES,
    ReplayError,
    load_verified_run,
    replay_run,
)
from cadkit.physics.runner import run_scenario_files  # noqa: E402
from cadkit.physics.state_archive import MAX_ARCHIVE_BYTES, MAX_ARCHIVE_ROWS  # noqa: E402

GIB = 1024 ** 3
MIB = 1024 ** 2

PHASES = [
    {"name": "reset", "kind": "reset", "initial": {"carriage_slide": 0.0}},
    {"name": "push", "kind": "actuate", "duration_s": 0.1, "actuator": "push",
     "effort": 1.0},
    {"name": "hold", "kind": "hold", "duration_s": 0.02},
]
CHECKS = [{"name": "held", "kind": "joint_displacement", "joint": "carriage_slide",
           "to_phase": "push", "expected": 0.02, "tolerance": 0.02, "units": "m"}]


def _scenario(**budget_overrides):
    budgets = {"max_steps": 20000, "max_sim_time_s": 10.0, "max_trace_rows": 20000}
    budgets.update(budget_overrides)
    return {"schema_version": "m4a-1", "scenario_id": "caps", "fixture": "loaded_slider",
            "seed": 1, "timestep_s": 0.001, "sampling_interval_s": 0.002,
            "budgets": budgets, "phases": PHASES}


def _raw(**budget_overrides) -> bytes:
    return json.dumps(_scenario(**budget_overrides)).encode("utf-8")


def _caps(raw, max_bytes=MAX_ARCHIVE_BYTES, max_rows=MAX_ARCHIVE_ROWS):
    return replay._declared_caps(raw, max_bytes=max_bytes, max_rows=max_rows)


def _make_run(tmp_path, **budget_overrides):
    sp = tmp_path / "s.json"
    ap = tmp_path / "a.json"
    sp.write_text(json.dumps(_scenario(**budget_overrides)), encoding="utf-8")
    ap.write_text(json.dumps({"schema_version": "m4a-1", "acceptance_id": "caps_acc",
                              "validity": {}, "checks": CHECKS}), encoding="utf-8")
    summary = run_scenario_files(sp, ap, tmp_path / "run")
    assert summary["status"] == "PASS"
    return tmp_path / "run"


# ------------------------------------------------------------ derivation helper
def test_hard_ceiling_is_8_gib():
    assert HARD_EVIDENCE_BYTES == 8 * GIB


def test_default_budgets_keep_old_floor_for_states_and_rows():
    caps, state_bytes, rows = _caps(_raw())
    assert state_bytes == MAX_ARCHIVE_BYTES
    assert rows == MAX_ARCHIVE_ROWS
    assert "states.npz" not in caps
    assert set(caps) == {"contacts.csv", "trace.csv"}
    assert all(MAX_ARCHIVE_BYTES <= v <= HARD_EVIDENCE_BYTES for v in caps.values())


def test_state_cap_is_state_budget_plus_header_allowance():
    caps, state_bytes, _ = _caps(_raw(max_state_bytes=2 * GIB))
    assert state_bytes == caps["states.npz"]
    assert 2 * GIB < state_bytes <= 2 * GIB + 16 * MIB


def test_state_cap_never_below_floor():
    caps, state_bytes, _ = _caps(_raw(max_state_bytes=1024))
    assert state_bytes == MAX_ARCHIVE_BYTES == caps["states.npz"]


def test_state_cap_never_above_hard_ceiling():
    caps, state_bytes, _ = _caps(_raw(max_state_bytes=64 * GIB))
    assert state_bytes == caps["states.npz"] == HARD_EVIDENCE_BYTES


def test_trace_caps_grow_with_max_trace_rows_and_are_clamped():
    small = _caps(_raw(max_trace_rows=10))[0]
    mid = _caps(_raw(max_trace_rows=100_000))[0]
    huge = _caps(_raw(max_trace_rows=10 ** 9))[0]
    for name in ("contacts.csv", "trace.csv"):
        assert small[name] == MAX_ARCHIVE_BYTES
        assert mid[name] >= small[name]
        assert huge[name] == HARD_EVIDENCE_BYTES
    # 100k rows at the configured per-row ceilings exceed the floor for the trace file.
    assert mid["trace.csv"] > MAX_ARCHIVE_BYTES


def test_row_cap_follows_state_rows_but_never_below_floor():
    assert _caps(_raw(max_state_rows=10))[2] == MAX_ARCHIVE_ROWS
    assert _caps(_raw(max_state_rows=MAX_ARCHIVE_ROWS + 5_000))[2] == MAX_ARCHIVE_ROWS + 5_000


def test_custom_floor_is_respected():
    caps, state_bytes, rows = _caps(_raw(max_state_bytes=1000), max_bytes=4096, max_rows=7)
    assert state_bytes == 4096 or state_bytes >= 4096
    assert all(v >= 4096 for v in caps.values())
    assert rows == 7


@pytest.mark.parametrize("raw", [b"not json", b"\xff\xfe", b"{}",
                                 json.dumps({"schema_version": "m4a-1"}).encode()])
def test_unparseable_scenario_yields_floor(raw):
    caps, state_bytes, rows = _caps(raw)
    assert caps == {}
    assert state_bytes == MAX_ARCHIVE_BYTES
    assert rows == MAX_ARCHIVE_ROWS


# ------------------------------------------------------------ end to end
def test_default_budget_run_behaves_as_before(tmp_path):
    run_dir = _make_run(tmp_path)
    verified = load_verified_run(run_dir)
    assert verified.file_caps["trace.csv"] >= MAX_ARCHIVE_BYTES
    assert "states.npz" not in verified.file_caps
    result = replay_run(run_dir, tmp_path / "rep")
    assert result["status"] == "PASS" and result["reproduced"] is True
    assert result["state_comparison"]["max_abs_diff"] == 0.0


def test_declared_state_budget_run_replays_and_records_caps(tmp_path):
    run_dir = _make_run(tmp_path, max_state_bytes=64 * MIB, max_state_rows=1000)
    verified = load_verified_run(run_dir)
    assert verified.file_caps["states.npz"] >= MAX_ARCHIVE_BYTES
    result = replay_run(run_dir, tmp_path / "rep")
    assert result["status"] == "PASS" and result["reproduced"] is True


def test_file_larger_than_derived_cap_is_rejected(tmp_path):
    run_dir = _make_run(tmp_path)
    # states.npz has no declared budget here, so its cap is the floor; pass a tiny floor.
    floor = 2000
    assert (run_dir / "states.npz").stat().st_size > floor
    assert (run_dir / "scenario.json").stat().st_size < floor
    with pytest.raises(ReplayError, match=r"exceeds the \d+-byte evidence budget"):
        load_verified_run(run_dir, max_bytes=floor)


def test_oversized_file_over_real_cap_is_rejected(tmp_path, monkeypatch):
    run_dir = _make_run(tmp_path)
    # Shrink the floor and per-row ceilings so the derived trace cap is smaller than a
    # padded trace.csv, while the other files stay readable under their own caps.
    monkeypatch.setattr(replay, "_TRACE_ROW_BYTES", 1)
    monkeypatch.setattr(replay, "_CONTACT_ROW_BYTES", 1)
    caps, _, _ = replay._declared_caps(
        (run_dir / "scenario.json").read_bytes(), max_bytes=100_000, max_rows=MAX_ARCHIVE_ROWS)
    assert caps["trace.csv"] == 100_000  # floor dominates tiny derived values
    with (run_dir / "trace.csv").open("ab") as fh:
        fh.write(b"x" * 100_001)
    with pytest.raises(EvidenceError, match=r"exceeds the 100000-byte evidence budget"):
        replay._read_all_evidence(run_dir, max_bytes=100_000, file_caps=caps)


def test_tampered_scenario_budget_fails_verification(tmp_path):
    run_dir = _make_run(tmp_path)
    path = run_dir / "scenario.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["budgets"]["max_trace_rows"] = 10 ** 9
    doc["budgets"]["max_state_bytes"] = 4 * GIB
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises((EvidenceError, ReplayError)):
        load_verified_run(run_dir)
    with pytest.raises((EvidenceError, ReplayError)):
        replay_run(run_dir, tmp_path / "rep")
