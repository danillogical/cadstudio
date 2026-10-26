"""Linear effort ramp on actuate phases: loader, per-step ctrl, telemetry, physics, replay."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("mujoco", reason="optional physics extra not installed")

from cadkit.physics.mechanics import SLIDER_K_N_PER_M  # noqa: E402
from cadkit.physics.replay import ReplayError, replay_run  # noqa: E402
from cadkit.physics.evidence import EvidenceError  # noqa: E402
from cadkit.physics.runner import run_assembly  # noqa: E402
from cadkit.physics.scenario import (  # noqa: E402
    AcceptanceSpec,
    BudgetSpec,
    CheckSpec,
    PhaseSpec,
    ScenarioError,
    ScenarioSpec,
    ValiditySpec,
    build_fixture,
    scenario_from_text,
)
from cadkit.physics.state_archive import ArchiveError  # noqa: E402

DT = 0.001


def _payload(push: dict | None = None, extra_phase: dict | None = None):
    phases = [
        {"name": "reset", "kind": "reset", "initial": {"carriage_slide": 0.0}},
        {"name": "push", "kind": "actuate", "duration_s": 0.1, "actuator": "push",
         "effort": 0.2, **(push or {})},
        {"name": "hold", "kind": "hold", "duration_s": 0.02},
    ]
    if extra_phase is not None:
        phases[-1] = extra_phase
    return {"schema_version": "m4a-1", "scenario_id": "ramp", "fixture": "loaded_slider",
            "seed": 0, "timestep_s": DT, "sampling_interval_s": DT,
            "budgets": {"max_steps": 20000, "max_sim_time_s": 10.0, "max_trace_rows": 20000},
            "phases": phases}


def _load(payload):
    return scenario_from_text(json.dumps(payload))


def _scenario(effort, effort_end, duration_s=0.1, hold_s=0.02):
    return ScenarioSpec(
        "ramp", "loaded_slider", 0,
        (PhaseSpec("reset", "reset", initial=(("carriage_slide", 0.0),)),
         PhaseSpec("push", "actuate", duration_s, actuator="push", effort=effort,
                   effort_end=effort_end),
         PhaseSpec("hold", "hold", hold_s)),
        DT, DT, BudgetSpec(20000, 10.0, 20000))


def _acceptance():
    return AcceptanceSpec("ramp_acc", (
        CheckSpec(name="moved", kind="joint_displacement", joint="carriage_slide",
                  to_phase="push", expected=0.0, tolerance=1.0, units="m"),), ValiditySpec())


def _run(tmp_path, fixture, effort, effort_end, duration_s=0.1, name="run"):
    spec = build_fixture(fixture, DT)
    summary = run_assembly(spec, _scenario(effort, effort_end, duration_s), _acceptance(),
                           tmp_path / name)
    assert summary["status"] == "PASS", summary.get("detail")
    return spec, summary, tmp_path / name


def _states(run):
    with np.load(run / "states.npz", allow_pickle=False) as data:
        return {k: np.array(data[k], copy=True) for k in data.files}


def _push_rows(arrays, steps):
    """Transition ctrl rows of the push phase: row k+1 holds step k's command."""
    return arrays["transition_ctrl"][1:1 + steps, 0]


def _expected(effort, effort_end, steps):
    return [effort + (effort_end - effort) * (k + 1) / steps for k in range(steps)]


# --------------------------------------------------------------------------- loader
def test_effort_end_loads_on_actuate_and_round_trips():
    spec = _load(_payload({"effort_end": 1.0}))
    push = spec.phases[1]
    assert push.effort_end == 1.0
    assert push.to_dict()["effort_end"] == 1.0
    assert _load(spec.to_dict()).phases[1].effort_end == 1.0


def test_absent_effort_end_keeps_the_canonical_dict_and_hash():
    spec = _load(_payload())
    assert spec.phases[1].effort_end is None
    assert "effort_end" not in spec.phases[1].to_dict()
    assert spec.phases[1].to_dict() == {
        "name": "push", "kind": "actuate", "duration_s": 0.1, "actuator": "push",
        "effort": 0.2}
    assert all("effort_end" not in p for p in spec.to_dict()["phases"])
    canonical = json.dumps(spec.to_dict(), sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False)
    assert spec.hash() == hashlib.sha256(canonical.encode()).hexdigest()


def test_effort_end_changes_the_scenario_hash():
    base = _load(_payload())
    ramp = _load(_payload({"effort_end": 1.0}))
    other = _load(_payload({"effort_end": 0.5}))
    assert len({base.hash(), ramp.hash(), other.hash()}) == 3


@pytest.mark.parametrize("phase", [
    {"name": "hold", "kind": "hold", "duration_s": 0.02, "effort_end": 1.0},
    {"name": "settle", "kind": "settle", "duration_s": 0.02, "effort_end": 1.0},
    {"name": "rel", "kind": "release", "duration_s": 0.02, "effort_end": 1.0},
])
def test_effort_end_rejected_on_non_actuate_timed_phases(phase):
    with pytest.raises(ScenarioError, match="effort_end"):
        _load(_payload(extra_phase=phase))


def test_effort_end_rejected_on_reset():
    payload = _payload()
    payload["phases"][0]["effort_end"] = 1.0
    with pytest.raises(ScenarioError):
        _load(payload)


@pytest.mark.parametrize("value", [True, False, "1.0", None, [1.0]])
def test_effort_end_rejects_bool_and_non_numbers(value):
    with pytest.raises(ScenarioError):
        _load(_payload({"effort_end": value}))


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_effort_end_rejects_non_finite(token):
    text = json.dumps(_payload({"effort_end": 0.0})).replace(
        '"effort_end": 0.0', f'"effort_end": {token}')
    assert token in text
    with pytest.raises(ScenarioError):
        scenario_from_text(text)


def test_effort_end_rejects_non_finite_typed_spec(tmp_path):
    spec = build_fixture("loaded_slider", DT)
    with pytest.raises((ScenarioError, ValueError)):
        run_assembly(spec, _scenario(0.2, math.nan), _acceptance(), tmp_path / "run")


# --------------------------------------------------------------------------- per-step ctrl
@pytest.mark.parametrize("fixture", ["loaded_slider", "loaded_slider_negative_gear"])
@pytest.mark.parametrize("effort,effort_end", [(0.2, 1.0), (1.0, 0.2), (-0.3, 0.5)])
def test_recorded_ctrl_follows_the_ramp(tmp_path, fixture, effort, effort_end):
    spec, summary, run = _run(tmp_path, fixture, effort, effort_end)
    gear = spec.actuators[0].gear
    assert (gear < 0) == (fixture.endswith("negative_gear"))
    steps = summary["phases"][1]["actual_steps"]
    assert steps == 100
    ctrl = _push_rows(_states(run), steps)
    want = _expected(effort, effort_end, steps)
    for k in (0, steps // 2 - 1, steps - 1):
        assert ctrl[k] * gear == pytest.approx(want[k], abs=1e-12), k
    assert ctrl * gear == pytest.approx(want, abs=1e-12)
    # The last step applies exactly effort_end, not a rounded neighbour.
    assert ctrl[-1] * gear == pytest.approx(effort_end, abs=1e-15)
    # Outside the push phase nothing is commanded.
    arrays = _states(run)
    assert arrays["transition_ctrl"][0, 0] == 0.0
    assert not arrays["transition_ctrl"][1 + steps:].any()


def test_constant_effort_is_unchanged_by_the_feature(tmp_path):
    spec = build_fixture("loaded_slider", DT)
    scenario = _scenario(0.4, None)
    assert "effort_end" not in scenario.phases[1].to_dict()
    summary = run_assembly(spec, scenario, _acceptance(), tmp_path / "run")
    assert summary["status"] == "PASS"
    ctrl = _push_rows(_states(tmp_path / "run"), 100)
    assert ctrl * spec.actuators[0].gear == pytest.approx([0.4] * 100, abs=1e-12)
    assert "requested_effort_end" not in summary["phases"][1]


def test_ramp_with_equal_endpoints_equals_constant(tmp_path):
    _, _, a = _run(tmp_path, "loaded_slider", 0.4, 0.4, name="a")
    spec = build_fixture("loaded_slider", DT)
    run_assembly(spec, _scenario(0.4, None), _acceptance(), tmp_path / "b")
    sa, sb = _states(a), _states(tmp_path / "b")
    assert np.array_equal(sa["transition_ctrl"], sb["transition_ctrl"])
    assert np.array_equal(sa["qpos"], sb["qpos"])


@pytest.mark.parametrize("fixture", ["loaded_slider", "loaded_slider_negative_gear"])
def test_ramp_is_bounded_by_max_effort_like_a_constant_effort(tmp_path, fixture):
    """The record keeps the raw request (as for constant effort); the applied effort is bounded."""
    spec = build_fixture(fixture, DT)
    limit = spec.actuators[0].max_effort
    gear = spec.actuators[0].gear
    end = 10.0 * limit
    _, summary, run = _run(tmp_path, fixture, 0.0, end)
    ctrl = _push_rows(_states(run), 100)
    assert ctrl * gear == pytest.approx(_expected(0.0, end, 100), abs=1e-12)
    push = summary["phases"][1]
    assert push["requested_effort_end"] == end
    assert push["ctrl_effective_peak"] == pytest.approx(limit / abs(gear))

    # Constant over-limit effort is recorded raw and bounded the same way.
    const = run_assembly(spec, _scenario(end, None), _acceptance(), tmp_path / "const")
    assert const["phases"][1]["ctrl_effective_peak"] == pytest.approx(limit / abs(gear))

    # A ramp whose every step exceeds the limit moves exactly like a constant at the limit.
    run_assembly(spec, _scenario(1.1 * limit, end), _acceptance(), tmp_path / "over")
    run_assembly(spec, _scenario(limit, None), _acceptance(), tmp_path / "at")
    over, at = _states(tmp_path / "over"), _states(tmp_path / "at")
    assert np.array_equal(over["qpos"], at["qpos"])


# --------------------------------------------------------------------------- telemetry
def test_phase_telemetry_reports_both_endpoints(tmp_path):
    _, summary, _ = _run(tmp_path, "loaded_slider", 0.2, 1.0)
    push = summary["phases"][1]
    assert push["requested_effort"] == 0.2
    assert push["requested_effort_end"] == 1.0
    assert push["actuator"] == "push"
    assert "requested_effort_end" not in summary["phases"][2]


# --------------------------------------------------------------------------- physics
@pytest.mark.parametrize("fixture", ["loaded_slider", "loaded_slider_negative_gear"])
def test_slow_ramp_tracks_quasi_static_spring_deflection(tmp_path, fixture):
    """Frictionless spring slide: q follows F/k, lagging by the damper, (c/k^2)*dF/dt."""
    duration, f_end = 4.0, 1.0
    _, summary, run = _run(tmp_path, fixture, 0.0, f_end, duration_s=duration)
    arrays = _states(run)
    steps = summary["phases"][1]["actual_steps"]
    assert steps == 4000
    q = arrays["qpos"][:, 0]
    t = arrays["time"]
    # Damping lag at ramp rate 0.25 N/s is about 0.5 mm; allow 1 mm absolute.
    for frac in (0.25, 0.5, 0.75, 1.0):
        row = int(frac * steps)
        force = f_end * t[row] / duration
        assert q[row] == pytest.approx(force / SLIDER_K_N_PER_M, abs=1.0e-3), frac
    # Positive effort drives the joint positively for either gear sign, monotonically.
    assert q[int(steps * 0.5)] > 0.0
    assert np.all(np.diff(q[: steps + 1][::100]) > 0.0)


# --------------------------------------------------------------------------- replay
@pytest.mark.parametrize("fixture", ["loaded_slider", "loaded_slider_negative_gear"])
def test_replay_reproduces_a_ramp_run(tmp_path, fixture):
    _, _, run = _run(tmp_path, fixture, 0.2, 1.0)
    result = replay_run(run, tmp_path / "rep")
    assert result["status"] == "PASS" and result["reproduced"] is True
    assert result["state_comparison"]["ok"] is True
    assert result["state_comparison"]["max_abs_diff"] == 0.0


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _rewrite_states(run, mutate):
    arrays = _states(run)
    mutate(arrays)
    with (run / "states.npz").open("wb") as fh:
        np.savez_compressed(fh, **arrays)
    manifest = json.loads((run / "manifest.json").read_text())
    manifest["artifacts"]["states.npz"] = {
        "sha256": _sha(run / "states.npz"), "bytes": (run / "states.npz").stat().st_size}
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _replay_rejects(run, tmp_path):
    """Replay must raise or report non-reproduction; a silent PASS is a hole."""
    try:
        result = replay_run(run, tmp_path / "rep")
    except (ReplayError, EvidenceError, ArchiveError):
        return True
    return not (result["status"] == "PASS" and result["reproduced"] is True)


@pytest.mark.parametrize("which", ["first", "middle", "last"])
@pytest.mark.parametrize("delta", [0.1, -0.1, 1e-3])
def test_tampered_ramp_ctrl_fails_replay(tmp_path, which, delta):
    """A ctrl that departs from the scenario's ramp must not replay as reproduced."""
    _, _, run = _run(tmp_path, "loaded_slider", 0.2, 1.0)
    row = {"first": 1, "middle": 50, "last": 100}[which]

    def mutate(arrays):
        arrays["transition_ctrl"][row, 0] += delta

    _rewrite_states(run, mutate)
    assert _replay_rejects(run, tmp_path), (
        f"replay accepted a ramp run whose recorded ctrl at row {row} was shifted by {delta}")


def test_tampered_ramp_ctrl_with_matching_ctrl_row_fails_replay(tmp_path):
    """Tamper the recorded ctrl (post-step snapshot) and the transition ctrl consistently."""
    _, _, run = _run(tmp_path, "loaded_slider", 0.2, 1.0)

    def mutate(arrays):
        arrays["transition_ctrl"][50, 0] += 0.3
        arrays["ctrl"][50, 0] += 0.3

    _rewrite_states(run, mutate)
    assert _replay_rejects(run, tmp_path)


def test_ramp_run_replayed_unmodified_is_not_rejected(tmp_path):
    """Control for the tamper tests: the same helper passes an untouched archive."""
    _, _, run = _run(tmp_path, "loaded_slider", 0.2, 1.0)
    _rewrite_states(run, lambda arrays: None)
    assert not _replay_rejects(run, tmp_path)
