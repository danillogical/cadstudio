"""Scenario ``remove_body``: admission, parked-body invariants, determinism, replay, contracts.

Written from the behaviour spec on the registered ``drop_box`` fixture (free ``box`` above a
fixed ``floor``), not the Pocky model.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("mujoco", reason="optional physics extra not installed")

import cadkit.cli as cli  # noqa: E402
from cadkit.gui.trajectory import write_trajectory  # noqa: E402
from cadkit.physics.evaluate import resolve_references  # noqa: E402
from cadkit.physics.playback import Playback  # noqa: E402
from cadkit.physics.replay import replay_run  # noqa: E402
from cadkit.physics.runner import run_scenario_files  # noqa: E402
from cadkit.physics.scenario import (  # noqa: E402
    ScenarioError,
    acceptance_from_text,
    build_fixture,
    scenario_from_text,
)
from cadkit.project import Project  # noqa: E402

REMOVAL_T = 0.3  # settle (0.3 s at 1 ms) ends here; the "take" phase removes the box
PHASES = [
    {"name": "reset", "kind": "reset"},
    {"name": "settle", "kind": "settle", "duration_s": 0.3},
    {"name": "take", "kind": "hold", "duration_s": 0.2, "remove_body": "box"},
    {"name": "after", "kind": "hold", "duration_s": 0.1},
]
ACCEPTANCE = {
    "schema_version": "m4a-1", "acceptance_id": "rm_acc",
    "validity": {"max_penetration_m": 0.005},
    "checks": [{"name": "pen", "kind": "penetration_bound", "max": 0.005, "units": "m"}],
}


def scenario_doc(phases=PHASES, scenario_id="rm"):
    return {
        "schema_version": "m4a-1", "scenario_id": scenario_id, "fixture": "drop_box",
        "seed": 1, "timestep_s": 0.001, "sampling_interval_s": 0.02,
        "budgets": {"max_steps": 20000, "max_sim_time_s": 10.0, "max_trace_rows": 20000},
        "phases": phases,
    }


def acceptance_doc(checks=None, events=None):
    doc = dict(ACCEPTANCE)
    if checks is not None:
        doc["checks"] = checks
    if events is not None:
        doc["events"] = events
    return doc


def execute(base: Path, name: str, phases=PHASES, acceptance=None) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    s, a = base / f"{name}-s.json", base / f"{name}-a.json"
    s.write_text(json.dumps(scenario_doc(phases)), encoding="utf-8")
    a.write_text(json.dumps(acceptance or ACCEPTANCE), encoding="utf-8")
    summary = run_scenario_files(s, a, base / name)
    assert summary["status"] == "PASS", summary.get("detail")
    return base / name


def parse(phases=PHASES):
    return scenario_from_text(json.dumps(scenario_doc(phases)))


def admit(scenario, acceptance):
    spec = build_fixture("drop_box", 0.001)
    resolve_references(scenario, acceptance_from_text(json.dumps(acceptance)), spec)


@pytest.fixture(scope="module")
def run_a(tmp_path_factory) -> Path:
    return execute(tmp_path_factory.mktemp("rm_a"), "run")


@pytest.fixture(scope="module")
def run_b(tmp_path_factory) -> Path:
    return execute(tmp_path_factory.mktemp("rm_b"), "run")


def _states(run: Path):
    z = np.load(run / "states.npz")
    return {k: z[k] for k in z.files}


# ---------------------------------------------------------------- scenario loading / admission

def test_unknown_body_is_rejected():
    phases = [PHASES[0], PHASES[1], dict(PHASES[2], remove_body="ghost")]
    with pytest.raises(ScenarioError, match="unknown body"):
        admit(parse(phases), ACCEPTANCE)


def test_non_free_body_is_rejected():
    phases = [PHASES[0], PHASES[1], dict(PHASES[2], remove_body="floor")]
    with pytest.raises(ScenarioError, match="not a free body"):
        admit(parse(phases), ACCEPTANCE)


def test_removing_the_same_body_twice_is_rejected():
    phases = PHASES[:3] + [dict(PHASES[3], remove_body="box")]
    with pytest.raises(ScenarioError, match="already removed"):
        parse(phases)


def test_remove_body_on_reset_phase_is_rejected():
    phases = [dict(PHASES[0], remove_body="box")] + PHASES[1:]
    with pytest.raises(ScenarioError):
        parse(phases)


def test_scenario_without_remove_body_omits_the_key_and_keeps_its_hash():
    plain = [p for p in PHASES]
    plain[2] = {k: v for k, v in PHASES[2].items() if k != "remove_body"}
    spec = parse(plain)
    assert all("remove_body" not in phase for phase in spec.to_dict()["phases"])
    assert "remove_body" not in json.dumps(spec.to_dict())
    assert parse(plain).hash() == spec.hash()
    removing = parse()
    assert removing.to_dict()["phases"][2]["remove_body"] == "box"
    assert removing.hash() != spec.hash()


def test_body_speed_on_or_after_removal_is_rejected_and_before_is_allowed():
    scenario = parse()

    def speed(phase):
        return acceptance_doc(checks=[
            {"name": "speed", "kind": "body_speed", "body": "box", "phase": phase,
             "max": 1.0, "units": "m/s"}])

    admit(scenario, speed("settle"))
    for phase in ("take", "after"):
        with pytest.raises(ScenarioError, match="removed"):
            admit(scenario, speed(phase))


def _event(window_to):
    return {"name": "exit", "kind": "exit_crossing", "bodies": ["box"],
            "plane": {"point_m": [0, 0, 0], "normal": [1, 0, 0], "direction": 1},
            "object_half_extents_m": [0.01, 0.01, 0.01],
            "window_from": "settle", "window_to": window_to}


def test_event_window_reaching_the_removal_phase_is_rejected():
    scenario = parse([PHASES[0], PHASES[1], {"name": "pre", "kind": "hold", "duration_s": 0.1},
                      dict(PHASES[2]), PHASES[3]])
    count = {"name": "n", "kind": "event_count", "event": "exit", "expected": 0,
             "tolerance": 0, "units": "count"}
    admit(scenario, acceptance_doc(checks=[count], events=[_event("pre")]))
    for window_to in ("take", "after"):
        with pytest.raises(ScenarioError, match="removed"):
            admit(scenario, acceptance_doc(checks=[count], events=[_event(window_to)]))


# ---------------------------------------------------------------- recorded run invariants

def test_removed_body_is_parked_at_rest_with_no_contacts(run_a):
    st = _states(run_a)
    phases = [str(n) for n in st["phase_names"]]
    first = int(np.flatnonzero(st["phase_index"] == phases.index("take"))[0])
    assert first > 1
    later = slice(first, None)
    pos = st["qpos"][later, :3]
    assert np.array_equal(pos, np.repeat(pos[:1], len(pos), axis=0)), "parked pose moves"
    assert not np.array_equal(st["qpos"][first - 1, :3], pos[0]), "box was never moved"
    assert np.all(st["qvel"][later] == 0.0)
    assert np.max(np.abs(pos[0])) >= 5.0, "parked pose is not off-scene"
    # Before removal the box rested on the floor and had contacts.
    lines = (run_a / "contacts.csv").read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    t_col = header.index("state_time_s")
    times = [float(row.split(",")[t_col]) for row in lines[1:]]
    assert any(t <= REMOVAL_T + 1e-9 for t in times)
    assert not [t for t in times if t > REMOVAL_T + 1e-9], "contacts after removal"


def test_identical_runs_have_byte_identical_states(run_a, run_b):
    assert (run_a / "states.npz").read_bytes() == (run_b / "states.npz").read_bytes()


def test_run_directory_contract_is_unchanged(run_a, tmp_path):
    plain = [p for p in PHASES]
    plain[2] = {k: v for k, v in PHASES[2].items() if k != "remove_body"}
    other = execute(tmp_path, "plain", phases=plain)

    def listing(root):
        return sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))

    assert listing(run_a) == listing(other)


def test_playback_restore_after_removal_matches_the_record(run_a):
    pb = Playback(run_a)
    st = pb.state
    phases = [str(n) for n in st["phase_names"]]
    first = int(np.flatnonzero(st["phase_index"] == phases.index("take"))[0])
    assert pb.removed_at("box") == pytest.approx(REMOVAL_T)
    assert pb.removed_at("floor") is None
    for row in (first, first + 50, len(st["time"]) - 1):
        pb.restore(row)
        assert np.array_equal(pb.data.qpos, st["qpos"][row])
        assert pb.data.ncon == 0
    pb.restore(first - 1)  # before removal the box is back on the floor, in contact
    assert pb.data.ncon > 0


def test_replay_from_a_checkpoint_after_removal_reproduces(tmp_path):
    # The removal phase is the settle phase, so the post-settle checkpoint is past the removal.
    phases = [
        {"name": "reset", "kind": "reset"},
        {"name": "fall", "kind": "hold", "duration_s": 0.1},
        {"name": "settle", "kind": "settle", "duration_s": 0.1, "remove_body": "box"},
        {"name": "after", "kind": "hold", "duration_s": 0.1},
    ]
    run = execute(tmp_path, "rep_src", phases=phases)
    result = replay_run(run, tmp_path / "rep")
    assert result["status"] == "PASS"
    assert result["reproduced"] is True
    assert result["state_comparison"]["max_abs_diff"] == 0.0
    assert result["post_settle_continuation"]["ok"] is True


# ---------------------------------------------------------------- removedAt contracts

def test_trajectory_removed_at(run_a, tmp_path):
    target = tmp_path / "run"
    shutil.copytree(run_a, target)
    write_trajectory(target, fps=30)
    doc = json.loads((tmp_path / "run.gui" / "trajectory.json").read_text(encoding="utf-8"))
    by_name = {b["name"]: b for b in doc["bodies"]}
    assert by_name["box"]["removedAt"] == pytest.approx(REMOVAL_T)
    assert by_name["floor"]["removedAt"] is None


def test_live_json_removed_at_agrees_with_trajectory(tmp_path):
    mp = pytest.MonkeyPatch()
    project = Project(name="fakeproj", params_path=Path("unused.toml"),
                      load_params=lambda path: None, models=cli,
                      physics=lambda model, p: build_fixture("drop_box", 0.001))
    mp.setattr(cli, "resolve", lambda spec: (project, "drop"))
    try:
        s, a = tmp_path / "s.json", tmp_path / "a.json"
        s.write_text(json.dumps(scenario_doc()), encoding="utf-8")
        a.write_text(json.dumps(ACCEPTANCE), encoding="utf-8")
        out = tmp_path / "run"
        try:
            code = cli.main(["physics", "run", "fakeproj/drop", "--scenario", str(s),
                             "--acceptance", str(a), "--out", str(out)])
        except SystemExit as exc:
            code = exc.code
        assert code == 0
    finally:
        mp.undo()
    live = json.loads((tmp_path / "run.live" / "live.json").read_text(encoding="utf-8"))
    live_by = {b["name"]: b for b in live["bodies"]}
    assert live_by["box"]["removedAt"] == pytest.approx(REMOVAL_T)
    assert live_by["floor"]["removedAt"] is None
    write_trajectory(out, fps=30)
    traj = json.loads((tmp_path / "run.gui" / "trajectory.json").read_text(encoding="utf-8"))
    traj_by = {b["name"]: b for b in traj["bodies"]}
    for name in ("box", "floor"):
        assert live_by[name]["removedAt"] == traj_by[name]["removedAt"]
