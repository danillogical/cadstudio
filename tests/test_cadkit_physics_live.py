"""``cad physics run`` live sidecar and its service routes, written from the behaviour spec.

The project is a stand-in whose physics hook returns the registered drop-box assembly,
injected by patching the CLI's ``resolve`` (as ``test_cadkit_physics_cli_run.py`` does).
"""
from __future__ import annotations

import http.client
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("mujoco", reason="optional physics extra not installed")

import cadkit.cli as cli  # noqa: E402
from cadkit.gui import server  # noqa: E402
from cadkit.params import REPO_ROOT  # noqa: E402
from cadkit.physics import live as live_mod  # noqa: E402
from cadkit.physics.scenario import build_fixture  # noqa: E402
from cadkit.project import Project  # noqa: E402

MODEL = "drop"
SETTLE_S = 20.0

SCENARIO = {
    "schema_version": "m4a-1", "scenario_id": "fake_drop", "fixture": "drop_box", "seed": 3,
    "timestep_s": 0.001, "sampling_interval_s": 0.01,
    "budgets": {"max_steps": 20000, "max_sim_time_s": 20.0, "max_trace_rows": 20000},
    "phases": [{"name": "reset", "kind": "reset"},
               {"name": "settle", "kind": "settle", "duration_s": SETTLE_S}],
}
ACCEPTANCE = {
    "schema_version": "m4a-1", "acceptance_id": "fake_drop_acc",
    "validity": {"max_penetration_m": 0.005},
    "checks": [{"name": "pen", "kind": "penetration_bound", "max": 0.005, "units": "m"}],
}


def _env() -> dict:
    env = {k: v for k, v in os.environ.items() if k != "POCKY_POSE"}
    env["PATH"] = f"{Path.home() / '.local' / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    return env


def _patch_project(mp: pytest.MonkeyPatch) -> None:
    project = Project(name="fakeproj", params_path=Path("unused.toml"),
                      load_params=lambda path: None, models=cli,
                      physics=lambda model, p: build_fixture("drop_box", 0.001))

    def fake_resolve(spec):
        if spec != f"fakeproj/{MODEL}":
            raise KeyError(f"unknown model {spec!r}")
        return project, MODEL

    mp.setattr(cli, "resolve", fake_resolve)


def _inputs(base: Path, settle_s: float = SETTLE_S) -> tuple[Path, Path]:
    base.mkdir(parents=True, exist_ok=True)
    scenario, acceptance = base / "scenario.json", base / "acceptance.json"
    phases = [SCENARIO["phases"][0], dict(SCENARIO["phases"][1], duration_s=settle_s)]
    scenario.write_text(json.dumps(dict(SCENARIO, phases=phases)), encoding="utf-8")
    acceptance.write_text(json.dumps(ACCEPTANCE), encoding="utf-8")
    return scenario, acceptance


def _run(inputs: tuple[Path, Path], out: Path, *extra: str) -> int:
    argv = ["physics", "run", f"fakeproj/{MODEL}", "--scenario", str(inputs[0]),
            "--acceptance", str(inputs[1]), "--out", str(out), *extra]
    try:
        return cli.main(argv)
    except SystemExit as exc:
        return exc.code


def _listing(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))


def _live_doc(live_dir: Path) -> dict:
    return json.loads((live_dir / "live.json").read_text(encoding="utf-8"))


def _load_poses(live_dir: Path, doc: dict) -> np.ndarray:
    n_bodies = len(doc["bodies"])
    raw = np.frombuffer((live_dir / "poses.bin").read_bytes(), dtype="<f4")
    frame_floats = doc["poses"]["frameBytes"] // 4
    assert frame_floats == n_bodies * 7
    return raw[: doc["frames"] * frame_floats].reshape(doc["frames"], n_bodies, 7)


@pytest.fixture(scope="module")
def patched():
    mp = pytest.MonkeyPatch()
    _patch_project(mp)
    try:
        yield
    finally:
        mp.undo()


@pytest.fixture(scope="module")
def inputs(tmp_path_factory):
    return _inputs(tmp_path_factory.mktemp("live_inputs"))


@pytest.fixture(scope="module")
def short_inputs(tmp_path_factory):
    """A 0.5 s scenario for the tests that do not need the run to last."""
    return _inputs(tmp_path_factory.mktemp("live_short_inputs"), settle_s=0.5)


@pytest.fixture(scope="module")
def under_out():
    """A scratch dir under the repo's ``out/`` (gitignored) so ``runId`` can be derived."""
    base = REPO_ROOT / "out" / f"_pytest_live_{uuid.uuid4().hex[:8]}"
    base.mkdir(parents=True)
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


@pytest.fixture(scope="module")
def live_run(patched, inputs, under_out):
    """One real run with live on, sampled from a background thread while it runs."""
    out = under_out / "live_on"
    live_dir = out.parent / f"{out.name}.live"
    samples: list[int] = []
    stop = threading.Event()

    def sampler():
        while not stop.is_set():
            try:
                frames = json.loads((live_dir / "live.json").read_text(encoding="utf-8"))["frames"]
                if isinstance(frames, int):
                    samples.append(frames)
            except (OSError, ValueError, KeyError):
                pass
            time.sleep(0.01)

    thread = threading.Thread(target=sampler, daemon=True)
    thread.start()
    code = _run(inputs, out)
    stop.set()
    thread.join(5)
    return {"out": out, "live": live_dir, "code": code, "samples": samples}


def test_live_dir_is_a_sibling_with_live_json_and_poses(live_run):
    assert live_run["code"] == 0
    out, live_dir = live_run["out"], live_run["live"]
    assert live_dir.parent == out.parent and live_dir.name == f"{out.name}.live"
    assert (live_dir / "live.json").is_file() and (live_dir / "poses.bin").is_file()
    assert not any(p.name.endswith(".live") for p in out.rglob("*"))


def test_no_live_flag_writes_no_live_dir(patched, short_inputs, tmp_path):
    out = tmp_path / "nolive"
    assert _run(short_inputs, out, "--no-live") == 0
    assert not (tmp_path / "nolive.live").exists()
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".live")]


def test_run_dir_listing_identical_with_live_on_and_off(patched, short_inputs, tmp_path):
    on, off = tmp_path / "on", tmp_path / "off"
    assert _run(short_inputs, on) == 0 and _run(short_inputs, off, "--no-live") == 0
    assert (tmp_path / "on.live").is_dir() and not (tmp_path / "off.live").exists()
    assert _listing(on) == _listing(off)


def test_frames_grow_during_the_run_and_finish_done(live_run, under_out):
    samples = live_run["samples"]
    doc = _live_doc(live_run["live"])
    assert doc["done"] is True and doc["status"] == "PASS" and doc["error"] is None
    final = doc["frames"]
    assert final > 100
    assert samples == sorted(samples), "frames must never decrease"
    mid = {s for s in samples if 0 < s < final}
    assert len(mid) >= 2, f"frames did not grow while running: {sorted(set(samples))[:20]}"
    expected = live_run["out"].resolve().relative_to((REPO_ROOT / "out").resolve()).as_posix()
    assert doc["runId"] == expected


def test_poses_bin_layout_and_size(live_run):
    live_dir = live_run["live"]
    doc = _live_doc(live_dir)
    assert doc["units"] == "mm" and doc["poses"]["positionUnits"] == "mm"
    assert doc["poses"]["dtype"] == "float32" and doc["poses"]["byteOrder"] == "little"
    frame_bytes = doc["poses"]["frameBytes"]
    assert frame_bytes == len(doc["bodies"]) * 7 * 4
    assert (live_dir / "poses.bin").stat().st_size >= doc["frames"] * frame_bytes
    poses = _load_poses(live_dir, doc)
    assert poses.shape == (doc["frames"], len(doc["bodies"]), 7)
    quat = poses[:, :, 3:]
    assert np.allclose(np.linalg.norm(quat, axis=2), 1.0, atol=1e-3)


def test_finished_live_poses_equal_the_trajectory_export(live_run):
    out, live_dir = live_run["out"], live_run["live"]
    doc = _live_doc(live_dir)
    r = subprocess.run([sys.executable, "-m", "cadkit.cli", "gui", "trajectory", str(out),
                        "--fps", str(doc["fps"]), "--json"], cwd=REPO_ROOT,
                       capture_output=True, text=True, timeout=300, env=_env())
    assert r.returncode == 0, r.stderr
    gui = out.parent / f"{out.name}.gui"
    tdoc = json.loads((gui / "trajectory.json").read_text(encoding="utf-8"))
    traj = np.frombuffer((gui / "poses.bin").read_bytes(), dtype="<f4").reshape(
        tdoc["poses"]["shape"])
    live = _load_poses(live_dir, doc)
    assert [b["name"] for b in tdoc["bodies"]] == [b["name"] for b in doc["bodies"]]
    assert live.shape == traj.shape
    assert np.max(np.abs(live[:, :, :3].astype(float) - traj[:, :, :3])) <= 1e-4


def test_stale_live_dir_is_replaced(patched, short_inputs, tmp_path):
    out = tmp_path / "run"
    stale = tmp_path / "run.live"
    stale.mkdir()
    (stale / "stale.txt").write_text("old")
    (stale / "live.json").write_text(json.dumps({"frames": 999999, "done": True}))
    assert _run(short_inputs, out) == 0
    assert not (stale / "stale.txt").exists()
    doc = _live_doc(stale)
    assert doc["frames"] != 999999 and doc["done"] is True


@pytest.mark.parametrize("method", ["_write_doc", "_flush"])
def test_writer_failure_never_fails_the_run(patched, short_inputs, tmp_path, monkeypatch, method, capsys):
    baseline = tmp_path / "baseline"
    assert _run(short_inputs, baseline, "--no-live") == 0
    summary = json.loads((baseline / "summary.json").read_text(encoding="utf-8"))

    def boom(self, *a, **k):
        raise OSError("simulated live write failure")

    monkeypatch.setattr(live_mod.LiveWriter, method, boom)
    out = tmp_path / "failing"
    assert _run(short_inputs, out) == 0
    got = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert got["status"] == summary["status"] == "PASS"
    assert _listing(out) == _listing(baseline)


def test_live_dir_made_unwritable_does_not_fail_the_run(patched, short_inputs, tmp_path):
    out = tmp_path / "run"
    blocker = tmp_path / "run.live"
    blocker.mkdir()
    (blocker / "keep").write_text("x")
    blocker.chmod(0o500)
    try:
        code = _run(short_inputs, out)
    finally:
        blocker.chmod(0o700)
    assert code == 0
    assert json.loads((out / "summary.json").read_text(encoding="utf-8"))["status"] == "PASS"


# ----------------------------------------------------------------------- service routes


def _http(svc, path, headers=None, token=True):
    conn = http.client.HTTPConnection("127.0.0.1", svc.port, timeout=30)
    hdrs = dict(headers or {})
    if token:
        hdrs["Authorization"] = f"Bearer {svc.token}"
    try:
        conn.request("GET", path, headers=hdrs)
        resp = conn.getresponse()
        return resp.status, resp.read(), dict(resp.getheaders())
    finally:
        conn.close()


@pytest.fixture(scope="module")
def svc(live_run, tmp_path_factory):
    out_root = tmp_path_factory.mktemp("live_svc_out")
    run = out_root / "demo" / "run1"
    run.parent.mkdir(parents=True)
    shutil.copytree(live_run["out"], run)
    shutil.copytree(live_run["live"], run.parent / "run1.live")
    service = server.GuiService(out_root=out_root, port=0, quiet=True, watch=False)
    service.start()
    try:
        yield service
    finally:
        service.close()


def test_get_live_lists_the_sidecar(svc):
    status, payload, _ = _http(svc, "/v1/live")
    assert status == 200
    ids = [entry["liveId"] for entry in json.loads(payload)["lives"]]
    assert "demo/run1" in ids
    assert _http(svc, "/v1/live", token=False)[0] == 401


def test_get_live_id_returns_live_json(svc):
    status, payload, _ = _http(svc, "/v1/live/demo/run1")
    assert status == 200
    disk = json.loads((svc.out_root / "demo" / "run1.live" / "live.json").read_text("utf-8"))
    assert json.loads(payload) == disk
    assert _http(svc, "/v1/live/demo/nope")[0] == 404


def test_range_requests_on_poses_bin(svc):
    path = "/v1/artifacts/demo/run1.live/poses.bin"
    data = (svc.out_root / "demo" / "run1.live" / "poses.bin").read_bytes()
    size, start = len(data), len(data) - 56
    status, body, headers = _http(svc, path, {"Range": f"bytes={start}-"})
    assert status == 206
    assert body == data[start:]
    assert headers["Content-Range"] == f"bytes {start}-{size - 1}/{size}"
    status, body, _ = _http(svc, path)
    assert status == 200 and body == data
    status, _, _ = _http(svc, path, {"Range": f"bytes={size}-"})
    assert status == 416


@pytest.mark.parametrize("path", [
    "/v1/live/..%2F..%2Fetc",
    "/v1/live/%2e%2e/%2e%2e/etc",
    "/v1/live/demo/%2e%2e/%2e%2e/x",
    "/v1/live//etc/passwd",
    "/v1/artifacts/%2e%2e/%2e%2e/etc/passwd",
    "/v1/artifacts/demo/run1.live/%2e%2e/%2e%2e/%2e%2e/etc/passwd",
])
def test_path_traversal_is_refused(svc, path):
    status, body, _ = _http(svc, path)
    assert status in (403, 404), (status, body[:200])
    assert b"root:" not in body
