"""On-disk layout: per-project ``out/``, physics run dirs, hidden ``.cadstudio`` state.

For a workspace ``ws``: model outputs go to ``ws/projects/<p>/out/<m>/``; default physics runs to
``ws/projects/<p>/out/<m>/runs/<scenario_id>-<stamp>``; engine fixture runs to
``ws/.cadstudio/fixtures/...``; nothing is written to ``ws/out``.

Engine signatures assumed beyond the CLI: none (the GUI-facing ones are pinned in the GUI tests).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from layout_workspace import make_tiny_workspace, run_cad, write_fake_run


@pytest.fixture(scope="module")
def ws(tmp_path_factory) -> Path:
    return make_tiny_workspace(tmp_path_factory.mktemp("layout"))


# ------------------------------------------------------------------ model outputs


def test_build_check_scene_write_only_under_project_out(ws):
    proc = run_cad(ws, "build", "tiny/box", "--check", "--scene", "--json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = ws / "projects" / "tiny" / "out" / "box"
    assert Path(json.loads(proc.stdout)["outdir"]).resolve() == out
    for pattern in ("*.step", "*.stl", "*.3mf"):
        assert list(out.glob(pattern)), pattern
    assert (out / "report.md").is_file() and (out / "report.json").is_file()
    assert (out / "scene" / "scene.json").is_file()
    assert (out / "scene" / "parts").is_dir()
    assert not (ws / "out").exists()


def test_gui_scene_writes_under_project_out(tmp_path):
    ws = make_tiny_workspace(tmp_path)
    proc = run_cad(ws, "gui", "scene", "tiny/box", "--json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (ws / "projects" / "tiny" / "out" / "box" / "scene" / "scene.json").is_file()
    assert not (ws / "out").exists()


def test_render_writes_under_project_out(tmp_path):
    ws = make_tiny_workspace(tmp_path)
    proc = run_cad(ws, "build", "tiny/box", "--render", "--views", "standard")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    renders = ws / "projects" / "tiny" / "out" / "box" / "renders"
    assert list(renders.glob("*.png"))
    assert not (ws / "out").exists()


def test_explicit_out_still_wins(tmp_path):
    ws = make_tiny_workspace(tmp_path)
    scratch = tmp_path / "scratch"
    proc = run_cad(ws, "build", "tiny/box", "--out", str(scratch))
    assert proc.returncode == 0, proc.stderr
    assert list(scratch.glob("*.step"))
    assert not (ws / "out").exists()
    assert not (ws / "projects" / "tiny" / "out").exists()


# ------------------------------------------------------------------ physics defaults

MODEL = "drop"
SCENARIO = {
    "schema_version": "m4a-1", "scenario_id": "fake_drop", "fixture": "drop_box", "seed": 3,
    "timestep_s": 0.001, "sampling_interval_s": 0.01,
    "budgets": {"max_steps": 20000, "max_sim_time_s": 10.0, "max_trace_rows": 20000},
    "phases": [{"name": "reset", "kind": "reset"},
               {"name": "settle", "kind": "settle", "duration_s": 0.3}],
}
ACCEPTANCE = {
    "schema_version": "m4a-1", "acceptance_id": "fake_drop_acc",
    "validity": {"max_penetration_m": 0.005},
    "checks": [{"name": "pen", "kind": "penetration_bound", "max": 0.005, "units": "m"}],
}


@pytest.fixture
def physics(tmp_path, monkeypatch):
    """A temp workspace plus a stand-in ``fakeproj`` whose physics hook is the drop-box fixture."""
    pytest.importorskip("mujoco", reason="optional physics extra not installed")
    import cadkit.cli as cli
    from cadkit.physics.scenario import build_fixture
    from cadkit.project import Project

    root = (tmp_path / "pws").resolve()
    (root / "projects").mkdir(parents=True)
    monkeypatch.setenv("CADSTUDIO_WORKSPACE", str(root))
    project = Project(name="fakeproj", params_path=Path("unused.toml"),
                      load_params=lambda path: None, models=cli,
                      physics=lambda model, p: build_fixture("drop_box", 0.001))

    def fake_resolve(spec):
        if spec != f"fakeproj/{MODEL}":
            raise KeyError(f"unknown model {spec!r}")
        return project, MODEL

    monkeypatch.setattr(cli, "resolve", fake_resolve)
    scenario = tmp_path / "scenario.json"
    acceptance = tmp_path / "acceptance.json"
    scenario.write_text(json.dumps(SCENARIO))
    acceptance.write_text(json.dumps(ACCEPTANCE))

    def run(*extra: str) -> int:
        argv = ["physics", "run", f"fakeproj/{MODEL}", "--scenario", str(scenario),
                "--acceptance", str(acceptance), *extra]
        try:
            return cli.main(argv)
        except SystemExit as exc:
            return exc.code

    return root, run, cli


def test_default_physics_run_dir_is_project_runs_scenario_stamp(physics):
    root, run, _ = physics
    assert run() == 0
    runs = root / "projects" / "fakeproj" / "out" / MODEL / "runs"
    made = sorted(p for p in runs.iterdir() if p.is_dir() and p.suffix not in (".live", ".gui"))
    assert len(made) == 1, list(runs.iterdir())
    assert made[0].name.startswith("fake_drop-") and len(made[0].name) > len("fake_drop-")
    assert (made[0] / "summary.json").is_file() and (made[0] / "states.npz").is_file()
    # The live sidecar sits beside the run dir.
    assert (runs / f"{made[0].name}.live" / "live.json").is_file()
    assert not (root / "out").exists()


def test_two_default_runs_get_distinct_dirs(physics):
    root, run, _ = physics
    assert run("--no-live") == 0
    assert run("--no-live") == 0
    runs = root / "projects" / "fakeproj" / "out" / MODEL / "runs"
    names = [p.name for p in runs.iterdir() if p.is_dir()]
    assert len(names) == 2 and all(n.startswith("fake_drop-") for n in names)


def test_nested_explicit_run_dir_keeps_sidecar_and_workspace_relative_ids(physics):
    root, run, _ = physics
    runs = root / "projects" / "fakeproj" / "out" / MODEL / "runs"
    out = runs / "group" / "named"
    assert run("--out", str(out)) == 0
    live = json.loads((runs / "group" / "named.live" / "live.json").read_text())
    assert live["runId"] == "projects/fakeproj/out/drop/runs/group/named"


def test_physics_export_default_dir_is_project_out(physics):
    root, _, cli = physics
    try:
        code = cli.main(["physics", "export", f"fakeproj/{MODEL}"])
    except SystemExit as exc:
        code = exc.code
    assert code == 0
    export = root / "projects" / "fakeproj" / "out" / MODEL / "physics" / "export"
    assert export.is_dir() and any(export.iterdir())
    assert not (root / "out").exists()


def test_fixture_runs_go_to_hidden_state_dir(tmp_path):
    pytest.importorskip("mujoco", reason="optional physics extra not installed")
    ws = make_tiny_workspace(tmp_path)
    scenario, acceptance = tmp_path / "s.json", tmp_path / "a.json"
    scenario.write_text(json.dumps(SCENARIO))
    acceptance.write_text(json.dumps(ACCEPTANCE))
    proc = run_cad(ws, "physics", "scenario", str(scenario), "--acceptance", str(acceptance))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    runs = list((ws / ".cadstudio" / "fixtures").rglob("summary.json"))
    assert len(runs) == 1, runs
    assert not (ws / "out").exists()
    # Fixtures are engine state, not a project's output.
    assert not (ws / "projects" / "tiny" / "out").exists()


def test_fixture_export_default_dir_is_hidden_state_dir(tmp_path):
    pytest.importorskip("mujoco", reason="optional physics extra not installed")
    ws = make_tiny_workspace(tmp_path)
    proc = run_cad(ws, "physics", "fixture")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    export = ws / ".cadstudio" / "fixtures" / "m2a_asymmetric" / "physics" / "export"
    assert export.is_dir() and any(export.iterdir())
    assert not (ws / "out").exists()


# ------------------------------------------------------------------ hidden state / doctor


def test_doctor_output_dir_is_hidden_state_dir(ws):
    proc = run_cad(ws, "doctor", "--json")
    checks = json.loads(proc.stdout)["checks"]
    assert Path(checks["output_dir"]["path"]).resolve() == ws / ".cadstudio"
    assert not (ws / "out").exists()


def test_gui_open_run_outside_allowed_roots_is_exit_2(tmp_path):
    ws = make_tiny_workspace(tmp_path)
    outside = write_fake_run(tmp_path / "elsewhere" / "run")
    inside_ws = write_fake_run(ws / "scratch" / "run")
    for target in (outside, inside_ws):
        proc = run_cad(ws, "gui", "open", "--run", str(target), "--no-open", "--json")
        assert proc.returncode == 2, (target, proc.stdout, proc.stderr)
