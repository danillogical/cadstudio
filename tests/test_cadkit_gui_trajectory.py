"""`cad gui trajectory`: the trajectory contract, mm units, determinism and run-dir safety."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from cadkit.params import REPO_ROOT
from cadkit.physics.runner import run_scenario_files

pytest.importorskip("mujoco")

from cadkit.gui.trajectory import write_trajectory  # noqa: E402

SCENARIO = {
    "schema_version": "m4a-1", "scenario_id": "drop", "fixture": "drop_box", "seed": 1,
    "timestep_s": 0.001, "sampling_interval_s": 0.05,
    "budgets": {"max_steps": 20000, "max_sim_time_s": 10.0, "max_trace_rows": 20000},
    "phases": [{"name": "reset", "kind": "reset"},
               {"name": "settle", "kind": "settle", "duration_s": 0.6},
               {"name": "hold", "kind": "hold", "duration_s": 0.2}],
}
ACCEPTANCE = {
    "schema_version": "m4a-1", "acceptance_id": "drop_acceptance",
    "validity": {"max_penetration_m": 0.001, "max_speed_m_s": 10.0, "max_energy_j": 1.0},
    "checks": [
        {"name": "contact", "kind": "contact_force_bound", "body_a": "box",
         "body_b": "floor", "max": 100.0, "units": "N"},
        {"name": "penetration", "kind": "penetration_bound", "max": 0.001, "units": "m"},
    ],
}


def _env() -> dict:
    env = {k: v for k, v in os.environ.items() if k != "POCKY_POSE"}
    env["PATH"] = f"{Path.home() / '.local' / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    return env


def cad(*args, timeout=300):
    return subprocess.run([sys.executable, "-m", "cadkit.cli", *args], cwd=REPO_ROOT,
                          capture_output=True, text=True, timeout=timeout, env=_env())


@pytest.fixture(scope="module")
def drop_run(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("trajectory_drop")
    scenario = root / "scenario.json"
    acceptance = root / "acceptance.json"
    scenario.write_text(json.dumps(SCENARIO), encoding="utf-8")
    acceptance.write_text(json.dumps(ACCEPTANCE), encoding="utf-8")
    out = root / "run"
    summary = run_scenario_files(scenario, acceptance, out)
    assert summary["status"] == "PASS", summary.get("detail")
    return out


@pytest.fixture
def run(tmp_path, drop_run) -> Path:
    target = tmp_path / "run"
    shutil.copytree(drop_run, target)
    return target


def snapshot(root: Path) -> dict:
    """Every path under ``root`` with its kind, size and mtime, plus the root's own mtime."""
    state = {"": ("dir", None, root.stat().st_mtime_ns)}
    for path in sorted(root.rglob("*")):
        stat = path.stat()
        kind = "dir" if path.is_dir() else "file"
        state[path.relative_to(root).as_posix()] = (kind, stat.st_size, stat.st_mtime_ns)
    return state


def load(gui: Path) -> tuple[dict, np.ndarray]:
    doc = json.loads((gui / "trajectory.json").read_text(encoding="utf-8"))
    poses = np.frombuffer((gui / "poses.bin").read_bytes(), dtype="<f4")
    return doc, poses.reshape(doc["poses"]["shape"])


def files(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_contract(run):
    r = cad("gui", "trajectory", str(run), "--json")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)  # the whole stdout is one document
    assert out["exit_code"] == 0
    gui = run.parent / "run.gui"
    assert Path(out["outdir"]) == gui
    doc, poses = load(gui)

    manifest_raw = (run / "manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    assert doc["schemaVersion"] == 1
    assert doc["units"] == "mm"
    assert doc["runId"] == manifest["run_id"]
    assert doc["manifestSha256"] == hashlib.sha256(manifest_raw).hexdigest()

    assert [b["name"] for b in doc["bodies"]] == ["floor", "box"]
    assert doc["bodies"][0]["fixed"] is True
    assert doc["bodies"][1]["fixed"] is False
    for body in doc["bodies"]:
        assert body["meshes"]
        for entry in body["meshes"]:
            assert entry["pose"][3:] == [1.0, 0.0, 0.0, 0.0]
            data = (gui / entry["mesh"]).read_bytes()
            assert data[:4] == b"glTF"
    assert poses.shape == (doc["frameCount"], len(doc["bodies"]), 7)
    assert (gui / "poses.bin").stat().st_size == doc["frameCount"] * len(doc["bodies"]) * 7 * 4

    assert [p["name"] for p in doc["phases"]] == ["reset", "settle", "hold"]
    for phase in doc["phases"]:
        assert phase["t0"] <= phase["t1"]
    assert doc["contacts"] is None
    assert not (gui / "contacts.bin").exists()


@pytest.mark.parametrize("fps", [60, 25])
def test_frame_count_matches_duration_times_fps(run, fps):
    state = write_trajectory(run, fps=fps)
    doc, poses = load(state["outdir"])
    expected = int(np.floor((0.8 - 0.0) * fps + 1e-9)) + 1
    assert doc["frameCount"] == expected
    assert expected == (49 if fps == 60 else 21)
    assert len(doc["times"]) == doc["frameCount"]
    assert poses.shape[0] == doc["frameCount"]
    assert np.allclose(np.diff(doc["times"]), 1.0 / fps)


def test_falling_box_z_decreases_in_mm(run):
    state = write_trajectory(run, fps=60)
    doc, poses = load(state["outdir"])
    box = [b["name"] for b in doc["bodies"]].index("box")
    times = np.asarray(doc["times"])
    z = poses[:, box, 2]
    falling = times < 0.08
    assert falling.sum() >= 4
    assert np.all(np.diff(z[falling]) < 0.0)
    assert z[-1] == pytest.approx(-40.0, abs=0.5)

    import trimesh

    entry = doc["bodies"][box]["meshes"][0]
    mesh = trimesh.load(state["outdir"] / entry["mesh"], file_type="glb", force="mesh")
    lo, hi = mesh.bounds
    assert lo[2] == pytest.approx(40.0, abs=0.05) and hi[2] == pytest.approx(60.0, abs=0.05)
    assert lo[0] == pytest.approx(-10.0, abs=0.05) and hi[0] == pytest.approx(10.0, abs=0.05)
    assert lo[1] == pytest.approx(-10.0, abs=0.05) and hi[1] == pytest.approx(10.0, abs=0.05)


def test_rerun_byte_identical(run):
    first = write_trajectory(run, contacts=True)["outdir"]
    before = files(first)
    second = write_trajectory(run, contacts=True)["outdir"]
    assert files(second) == before


def test_run_dir_untouched(run):
    before = snapshot(run)
    write_trajectory(run)
    write_trajectory(run, contacts=True)
    assert snapshot(run) == before
    assert (run.parent / "run.gui").is_dir()


def test_contacts_optional(run):
    state = write_trajectory(run, fps=60, contacts=True)
    doc, poses = load(state["outdir"])
    blob = (state["outdir"] / "contacts.bin").read_bytes()
    assert len(blob) == doc["contacts"]["count"] * 8 * 4
    assert doc["contacts"]["count"] > 0
    rows = np.frombuffer(blob, dtype="<f4").reshape(-1, 8)
    last = rows[rows[:, 0] == doc["frameCount"] - 1]
    assert last.size
    assert np.any(last[:, 7] > 0.0)
    assert np.all(np.abs(last[:, 6]) <= 1.0 + 1e-6)


def test_tampered_states_npz_is_error(run):
    with np.load(run / "states.npz", allow_pickle=False) as archive:
        arrays = {name: np.array(archive[name], copy=True) for name in archive.files}
    arrays["integration_state"][10, :] += 1e-3
    arrays["qpos"][10] += 1e-3
    np.savez_compressed(run / "states.npz", **arrays)

    r = cad("gui", "trajectory", str(run), "--json")
    assert r.returncode == 1
    doc = json.loads(r.stdout)
    assert doc["exit_code"] == 1
    assert "states.npz" in doc["error"]
    assert not (run.parent / "run.gui").exists()
    assert not [p for p in run.parent.iterdir() if p.name.startswith(".run.gui.")]


def test_truncated_states_npz_keeps_previous_export(run):
    good = write_trajectory(run)["outdir"]
    before = files(good)
    (run / "states.npz").write_bytes((run / "states.npz").read_bytes()[:512])
    r = cad("gui", "trajectory", str(run), "--json")
    assert r.returncode == 1
    assert json.loads(r.stdout)["error"]
    assert files(good) == before


def test_bad_inputs(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    r = cad("gui", "trajectory", str(empty), "--json")
    assert r.returncode == 1
    assert json.loads(r.stdout)["exit_code"] == 1

    r = cad("gui", "trajectory", str(empty), "--fps", "0", "--json")
    assert r.returncode == 1
    assert "fps" in json.loads(r.stdout)["error"]
