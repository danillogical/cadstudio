"""Phase ``body_force``: loader, hash, per-step xfrc_applied, telemetry, physics, replay."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("mujoco", reason="optional physics extra not installed")

from cadkit.physics.evidence import EvidenceError  # noqa: E402
from cadkit.physics.replay import ReplayError, replay_run  # noqa: E402
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
from cadkit.physics.evaluate import resolve_references  # noqa: E402
from cadkit.physics.state_archive import ArchiveError  # noqa: E402

DT = 0.001
GRAVITY = 9.80665
SETTLE_S = 0.3
HOLD_S = 0.2


def _payload(phase: dict | None = None, fixture: str = "drop_box"):
    phases = [
        {"name": "reset", "kind": "reset"},
        {"name": "settle", "kind": "settle", "duration_s": 0.05},
        phase or {"name": "hold", "kind": "hold", "duration_s": 0.02,
                  "body_force": {"body": "box", "force_n": [0.01, 0.0, 0.0]}},
    ]
    return {"schema_version": "m4a-1", "scenario_id": "bf", "fixture": fixture,
            "seed": 0, "timestep_s": DT, "sampling_interval_s": DT,
            "budgets": {"max_steps": 20000, "max_sim_time_s": 10.0, "max_trace_rows": 20000},
            "phases": phases}


def _load(payload):
    return scenario_from_text(json.dumps(payload))


def _with(body_force):
    return {"name": "hold", "kind": "hold", "duration_s": 0.02, "body_force": body_force}


# --------------------------------------------------------------------------- loader
def test_body_force_loads_and_round_trips():
    spec = _load(_payload(_with({"body": "box", "force_n": [1, 0, 0],
                                 "force_end_n": [2, 0, 0.5]})))
    bf = spec.phases[2].body_force
    assert bf.body == "box"
    assert tuple(bf.force_n) == (1.0, 0.0, 0.0)
    assert tuple(bf.force_end_n) == (2.0, 0.0, 0.5)
    assert spec.phases[2].to_dict()["body_force"] == {
        "body": "box", "force_n": [1.0, 0.0, 0.0], "force_end_n": [2.0, 0.0, 0.5]}
    again = _load(spec.to_dict())
    assert again.phases[2].body_force == bf
    assert again.hash() == spec.hash()


@pytest.mark.parametrize("kind", ["actuate", "hold", "release"])
def test_body_force_allowed_on_actuate_hold_release(kind):
    phase = {"name": "p", "kind": kind, "duration_s": 0.02,
             "body_force": {"body": "box", "force_n": [0.0, 0.0, 0.0]}}
    if kind == "actuate":
        phase.update(actuator="push", effort=0.1)
    spec = _load(_payload(phase))
    assert spec.phases[2].body_force is not None


def test_body_force_rejected_on_settle():
    phase = {"name": "s2", "kind": "settle", "duration_s": 0.02,
             "body_force": {"body": "box", "force_n": [0.0, 0.0, 0.0]}}
    with pytest.raises(ScenarioError, match="body_force"):
        _load(_payload(phase))


def test_body_force_rejected_on_reset():
    payload = _payload()
    payload["phases"][0]["body_force"] = {"body": "box", "force_n": [0.0, 0.0, 0.0]}
    with pytest.raises(ScenarioError):
        _load(payload)


@pytest.mark.parametrize("bf", [
    {"body": "box", "force_n": [1, 0, 0], "extra": 1},
    {"body": "box", "force_n": [1, 0, 0], "torque_n_m": [0, 0, 0]},
    {"body": "box"},
    {"force_n": [1, 0, 0]},
    {"body": "box", "force_n": [1, 0]},
    {"body": "box", "force_n": [1, 0, 0, 0]},
    {"body": "box", "force_n": []},
    {"body": "box", "force_n": [1, 0, 0], "force_end_n": [1, 0]},
    {"body": "box", "force_n": [1, 0, 0], "force_end_n": [1, 0, 0, 0]},
    {"body": "box", "force_n": [True, 0, 0]},
    {"body": "box", "force_n": [1, 0, 0], "force_end_n": [False, 0, 0]},
    {"body": "box", "force_n": ["1", 0, 0]},
    {"body": "box", "force_n": [None, 0, 0]},
    {"body": "box", "force_n": 1.0},
    {"body": "box", "force_n": [1, 0, 0], "force_end_n": None},
    {"body": 7, "force_n": [1, 0, 0]},
    {"body": True, "force_n": [1, 0, 0]},
    {"body": "", "force_n": [1, 0, 0]},
    "box",
    [1, 0, 0],
    None,
])
def test_body_force_rejects_malformed(bf):
    with pytest.raises(ScenarioError):
        _load(_payload(_with(bf)))


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("field", ["force_n", "force_end_n"])
def test_body_force_rejects_non_finite_json(token, field):
    bf = {"body": "box", "force_n": [1.0, 0.0, 0.0], "force_end_n": [1.0, 0.0, 0.0]}
    text = json.dumps(_payload(_with(bf)))
    marker = f'"{field}": [1.0, 0.0, 0.0]'
    assert marker in text
    text = text.replace(marker, f'"{field}": [{token}, 0.0, 0.0]')
    with pytest.raises(ScenarioError):
        scenario_from_text(text)


# --------------------------------------------------------------------------- references
def _resolve(fixture, phase):
    spec = build_fixture(fixture, DT)
    scenario = _load(_payload(phase, fixture=fixture))
    resolve_references(scenario, AcceptanceSpec("a", (), ValiditySpec()), spec)


def test_resolve_accepts_a_free_body():
    _resolve("drop_box", _with({"body": "box", "force_n": [0.0, 0.0, 0.0]}))


@pytest.mark.parametrize("body", ["nobody", "floor"])
def test_resolve_rejects_unknown_and_fixed_bodies(body):
    with pytest.raises(ScenarioError, match="body_force"):
        _resolve("drop_box", _with({"body": body, "force_n": [0.0, 0.0, 0.0]}))


def test_resolve_rejects_a_jointed_body():
    phase = _with({"body": "carriage", "force_n": [0.0, 0.0, 0.0]})
    with pytest.raises(ScenarioError, match="body_force"):
        _resolve("loaded_slider", phase)


def test_resolve_rejects_non_finite_typed_spec():
    spec = build_fixture("drop_box", DT)
    scenario = _scenario([PhaseSpec("hold", "hold", 0.02, body_force=_bf(
        (math.nan, 0.0, 0.0)))])
    with pytest.raises((ScenarioError, ValueError)):
        resolve_references(scenario, _acceptance(), spec)


# --------------------------------------------------------------------------- hash
def test_absent_body_force_keeps_dict_and_hash():
    payload = _payload({"name": "hold", "kind": "hold", "duration_s": 0.02})
    spec = _load(payload)
    assert spec.phases[2].body_force is None
    assert "body_force" not in spec.phases[2].to_dict()
    assert all("body_force" not in p for p in spec.to_dict()["phases"])
    canonical = json.dumps(spec.to_dict(), sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False)
    assert spec.hash() == hashlib.sha256(canonical.encode()).hexdigest()


def test_body_force_changes_the_scenario_hash():
    base = _load(_payload({"name": "hold", "kind": "hold", "duration_s": 0.02}))
    a = _load(_payload(_with({"body": "box", "force_n": [1, 0, 0]})))
    b = _load(_payload(_with({"body": "box", "force_n": [2, 0, 0]})))
    c = _load(_payload(_with({"body": "box", "force_n": [1, 0, 0],
                              "force_end_n": [1, 0, 0]})))
    assert len({base.hash(), a.hash(), b.hash(), c.hash()}) == 4


# --------------------------------------------------------------------------- run helpers
def _bf(force, end=None, body="box"):
    from cadkit.physics.scenario import BodyForceSpec
    return BodyForceSpec(body, tuple(force), None if end is None else tuple(end))


def _scenario(phases, fixture="drop_box"):
    return ScenarioSpec("bf", fixture, 0,
                        (PhaseSpec("reset", "reset"),) + tuple(phases),
                        DT, DT, BudgetSpec(20000, 10.0, 20000))


def _acceptance(body="box"):
    """A deliberately loose check: the loader requires one, the tests read the archive."""
    return AcceptanceSpec("bf_acc", (
        CheckSpec(name="speed", kind="body_speed", body=body, phase="settle",
                  maximum=10.0, window="max_over_phase", units="m/s"),), ValiditySpec())


def _run(tmp_path, phases, fixture="drop_box", name="run"):
    spec = build_fixture(fixture, DT)
    body = "packet" if fixture == "presentation_aperture" else "box"
    summary = run_assembly(spec, _scenario(phases, fixture), _acceptance(body),
                           tmp_path / name)
    assert summary["status"] == "PASS", summary.get("detail")
    return summary, tmp_path / name


def _states(run):
    with np.load(run / "states.npz", allow_pickle=False) as data:
        return {k: np.array(data[k], copy=True) for k in data.files}


def _phase_rows(summary):
    """name -> (first, last) transition row of each timed phase (row k+1 holds step k)."""
    rows, start = {}, 1
    for phase in summary["phases"]:
        steps = phase.get("actual_steps", 0)
        if phase["kind"] == "reset" or not steps:
            continue
        rows[phase["name"]] = (start, start + steps)
        start += steps
    return rows


def _force_column(arrays):
    xf = arrays["transition_xfrc_applied"]
    moved = np.flatnonzero(np.abs(xf).sum(axis=(0, 2)))
    assert len(moved) == 1, moved
    return xf[:, moved[0], :]


def _expected(f0, f1, steps):
    f0, f1 = np.asarray(f0, float), np.asarray(f1, float)
    return [f0 + (f1 - f0) * (k + 1) / steps for k in range(steps)]


def _box_x(arrays):
    return arrays["qpos"][:, 0]


# --------------------------------------------------------------------------- xfrc record
def test_ramped_force_is_recorded_per_step_and_zero_elsewhere(tmp_path):
    f0, f1 = (0.0, 0.0, 0.0), (0.06, -0.02, 0.01)
    summary, run = _run(tmp_path, [
        PhaseSpec("settle", "settle", 0.1),
        PhaseSpec("pull", "hold", 0.1, body_force=_bf(f0, f1)),
        PhaseSpec("after", "hold", 0.05),
    ])
    arrays = _states(run)
    first, end = _phase_rows(summary)["pull"]
    steps = end - first
    assert steps == 100
    col = _force_column(arrays)
    want = _expected(f0, f1, steps)
    for k in (0, steps // 2 - 1, steps - 1):
        assert col[first + k, :3] == pytest.approx(want[k], abs=1e-12), k
    assert col[first:end, :3] == pytest.approx(np.array(want), abs=1e-12)
    # The last step applies exactly force_end_n, and there is never a torque.
    assert tuple(col[end - 1, :3]) == pytest.approx(f1, abs=1e-15)
    assert not col[:, 3:].any()
    # Zero before the phase (including the initial row) and after it.
    assert not col[:first].any()
    assert not col[end:].any()


def test_constant_force_is_held_every_step_and_cleared_at_the_boundary(tmp_path):
    force = (0.015, 0.0, 0.0)
    summary, run = _run(tmp_path, [
        PhaseSpec("settle", "settle", 0.1),
        PhaseSpec("push", "hold", 0.05, body_force=_bf(force)),
        PhaseSpec("next", "hold", 0.05),
    ])
    col = _force_column(_states(run))
    first, end = _phase_rows(summary)["push"]
    assert col[first:end, :3] == pytest.approx(np.tile(force, (end - first, 1)), abs=1e-15)
    assert not col[:first].any() and not col[end:].any()


def test_back_to_back_force_phases_do_not_leak_into_each_other(tmp_path):
    summary, run = _run(tmp_path, [
        PhaseSpec("settle", "settle", 0.1),
        PhaseSpec("a", "hold", 0.03, body_force=_bf((0.02, 0.0, 0.0))),
        PhaseSpec("plain", "release", 0.03),
        PhaseSpec("b", "hold", 0.03, body_force=_bf((0.0, 0.03, 0.0))),
    ])
    col = _force_column(_states(run))
    rows = _phase_rows(summary)
    a0, a1 = rows["a"]
    p0, p1 = rows["plain"]
    b0, b1 = rows["b"]
    assert np.all(col[a0:a1, :3] == (0.02, 0.0, 0.0))
    assert not col[p0:p1].any()
    assert np.all(col[b0:b1, :3] == (0.0, 0.03, 0.0))
    assert not col[b1:].any()


# --------------------------------------------------------------------------- telemetry
def test_phase_telemetry_reports_the_requested_force(tmp_path):
    summary, _ = _run(tmp_path, [
        PhaseSpec("settle", "settle", 0.1),
        PhaseSpec("ramp", "hold", 0.02, body_force=_bf((0.0, 0.0, 0.0), (0.03, 0.0, 0.0))),
        PhaseSpec("const", "hold", 0.02, body_force=_bf((0.01, 0.0, 0.0))),
        PhaseSpec("plain", "hold", 0.02),
    ])
    by_name = {p["name"]: p for p in summary["phases"]}
    ramp = by_name["ramp"]
    assert ramp["body_force_body"] == "box"
    assert list(ramp["requested_force_n"]) == [0.0, 0.0, 0.0]
    assert list(ramp["requested_force_end_n"]) == [0.03, 0.0, 0.0]
    const = by_name["const"]
    assert const["body_force_body"] == "box"
    assert list(const["requested_force_n"]) == [0.01, 0.0, 0.0]
    assert "requested_force_end_n" not in const
    for key in ("body_force_body", "requested_force_n", "requested_force_end_n"):
        assert key not in by_name["plain"]
        assert key not in by_name["settle"]


# --------------------------------------------------------------------------- physics
def _box_mass_kg():
    return (0.020 ** 3) * 1270.0


def _slide_scenario(force, end=None, hold_s=HOLD_S):
    return [PhaseSpec("settle", "settle", SETTLE_S),
            PhaseSpec("shove", "hold", hold_s, body_force=_bf(force, end))]


def _displacement(tmp_path, force, end=None, name="run"):
    summary, run = _run(tmp_path, _slide_scenario(force, end), name=name)
    arrays = _states(run)
    first, last = _phase_rows(summary)["shove"]
    x = _box_x(arrays)
    return x[last - 1] - x[first - 1]


def _limit():
    spec = build_fixture("drop_box", DT)
    return spec.friction[0] * _box_mass_kg() * GRAVITY


def test_force_below_static_friction_does_not_slide_the_box(tmp_path):
    limit = _limit()
    assert 0.03 < limit < 0.05  # sanity: mu 0.4 on a 10.2 g cube
    dx = _displacement(tmp_path, (0.5 * limit, 0.0, 0.0))
    assert abs(dx) < 1.0e-4


def test_force_above_static_friction_slides_the_box_in_the_force_direction(tmp_path):
    limit = _limit()
    dx = _displacement(tmp_path, (0.0, 0.0, 0.0), (4.0 * limit, 0.0, 0.0), name="ramp")
    assert dx > 5.0e-3


def test_constant_force_above_the_limit_slides_the_box(tmp_path):
    dx = _displacement(tmp_path, (3.0 * _limit(), 0.0, 0.0))
    assert dx > 5.0e-3


def test_force_sign_sets_the_slide_direction(tmp_path):
    limit = _limit()
    pos = _displacement(tmp_path, (3.0 * limit, 0.0, 0.0), name="pos")
    neg = _displacement(tmp_path, (-3.0 * limit, 0.0, 0.0), name="neg")
    assert pos > 5.0e-3 and neg < -5.0e-3
    assert neg == pytest.approx(-pos, rel=1e-3, abs=1e-5)


def test_ramp_slides_only_after_crossing_the_friction_limit(tmp_path):
    """Up to the limit the box stays put; the late part of the ramp carries it away."""
    limit = _limit()
    summary, run = _run(tmp_path, _slide_scenario((0.0, 0.0, 0.0), (4.0 * limit, 0.0, 0.0)))
    arrays = _states(run)
    first, last = _phase_rows(summary)["shove"]
    x = _box_x(arrays)
    steps = last - first
    quarter = first - 1 + int(0.2 * steps)  # force at 0.2*4*limit = 0.8*limit
    assert abs(x[quarter] - x[first - 1]) < 1.0e-4
    assert x[last - 1] - x[first - 1] > 5.0e-3


# --------------------------------------------------------------------------- not actuator input
def test_body_force_is_not_actuator_input(tmp_path):
    phases = [
        PhaseSpec("settle", "settle", 0.05),
        PhaseSpec("drive", "actuate", 0.03, actuator="push", effort=0.5),
        PhaseSpec("let_go", "release", 0.05, body_force=_bf((0.01, 0.0, 0.0),
                                                           (0.02, 0.0, 0.0), body="packet")),
    ]
    summary, run = _run(tmp_path, phases, fixture="presentation_aperture")
    arrays = _states(run)
    rows = _phase_rows(summary)
    r0, r1 = rows["let_go"]
    # The release phase carries a real force on the packet...
    xf = arrays["transition_xfrc_applied"][r0:r1]
    assert np.abs(xf).sum() > 0.0
    # ...yet commands no actuator input at all, and the actuate phase did.
    assert not arrays["transition_ctrl"][r0:r1].any()
    d0, d1 = rows["drive"]
    assert arrays["transition_ctrl"][d0:d1].any()
    release = {p["name"]: p for p in summary["phases"]}["let_go"]
    assert release["body_force_body"] == "packet"
    assert "actuator" not in release or release.get("actuator") is None


# --------------------------------------------------------------------------- replay
def _force_run(tmp_path, name="run"):
    return _run(tmp_path, [
        PhaseSpec("settle", "settle", 0.1),
        PhaseSpec("shove", "hold", 0.1, body_force=_bf((0.0, 0.0, 0.0), (0.1, 0.0, 0.0))),
        PhaseSpec("after", "hold", 0.02),
    ], name=name)


def test_replay_reproduces_a_body_force_run(tmp_path):
    _, run = _force_run(tmp_path)
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
    try:
        result = replay_run(run, tmp_path / "rep")
    except (ReplayError, EvidenceError, ArchiveError):
        return True
    return not (result["status"] == "PASS" and result["reproduced"] is True)


def test_body_force_run_replayed_through_the_rewrite_helper_is_not_rejected(tmp_path):
    """Control for the tamper tests: an untouched but rewritten archive is accepted."""
    _, run = _force_run(tmp_path)
    _rewrite_states(run, lambda arrays: None)
    assert not _replay_rejects(run, tmp_path)


@pytest.mark.parametrize("which", ["first", "middle", "last"])
@pytest.mark.parametrize("delta", [0.05, -0.05, 1e-3])
def test_tampered_recorded_force_fails_replay(tmp_path, which, delta):
    summary, run = _force_run(tmp_path)
    first, end = _phase_rows(summary)["shove"]
    row = {"first": first, "middle": (first + end) // 2, "last": end - 1}[which]
    body = int(np.flatnonzero(np.abs(_states(run)["transition_xfrc_applied"])
                              .sum(axis=(0, 2)))[0])

    def mutate(arrays):
        arrays["transition_xfrc_applied"][row, body, 0] += delta

    _rewrite_states(run, mutate)
    assert _replay_rejects(run, tmp_path), (
        f"replay accepted a body_force run whose recorded force at row {row} moved by {delta}")


def test_recorded_force_outside_the_phase_fails_replay(tmp_path):
    summary, run = _force_run(tmp_path)
    first, end = _phase_rows(summary)["shove"]
    body = int(np.flatnonzero(np.abs(_states(run)["transition_xfrc_applied"])
                              .sum(axis=(0, 2)))[0])

    def mutate(arrays):
        arrays["transition_xfrc_applied"][end + 2, body, 1] = 0.05

    _rewrite_states(run, mutate)
    assert _replay_rejects(run, tmp_path)
