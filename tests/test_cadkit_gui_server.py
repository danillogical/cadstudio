"""``cad gui serve``: auth, Host/Origin, path rules, jobs, SSE and discovery (packet G3a)."""
from __future__ import annotations

import http.client
import json
import os
import signal
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from cadkit.gui import server
from cadkit.params import REPO_ROOT
from layout_workspace import make_starter_workspace, project_out, write_fake_run
from physics_workspace import ACCEPTANCE, SCENARIO, make_physics_workspace, workspace_env

TERMINAL = {"succeeded", "failed", "cancelled"}

# Engine signatures assumed here (layout change; the workspace is ``repo_root``, no ``out_root``):
#   GuiService(repo_root=ws, port=, quiet=, watch=, ui_dist=)       (no ``out_root`` kwarg/attribute)
#   server.discovery_path(ws) -> ws/.cadstudio/gui/service.json
#   server.read_discovery(ws), server.existing_service(ws), server.start_service(repo_root=ws, ...)
#   server.run(port=, open_browser=, as_json=, repo_root=ws)


def _env() -> dict:
    env = dict(os.environ)
    env["PATH"] = f"{Path.home() / '.local' / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    return env


@pytest.fixture(scope="module")
def svc(tmp_path_factory):
    ws = make_starter_workspace(tmp_path_factory.mktemp("gui_ws"))
    with workspace_env(ws):
        service = server.GuiService(repo_root=ws, port=0, quiet=True)
        service.start()
        service.write_discovery()
        try:
            yield service
        finally:
            service.close()


def req(svc, method, path, *, token=True, headers=None, body=None, timeout=120):
    conn = http.client.HTTPConnection("127.0.0.1", svc.port, timeout=timeout)
    hdrs = dict(headers or {})
    if token:
        hdrs.setdefault("Authorization", f"Bearer {svc.token}")
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    try:
        conn.request(method, path, body=data, headers=hdrs)
        resp = conn.getresponse()
        payload = resp.read()
        return resp.status, payload, dict(resp.getheaders())
    finally:
        conn.close()


def req_json(svc, method, path, **kw):
    status, payload, headers = req(svc, method, path, **kw)
    doc = json.loads(payload) if payload else None
    return status, doc, headers


def wait_job(svc, job_id, timeout=300):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, doc, _ = req_json(svc, "GET", f"/v1/jobs/{job_id}")
        assert status == 200, doc
        if doc["job"]["status"] in TERMINAL:
            return doc["job"]
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


def build(svc, spec="starter/box", body=None):
    status, doc, _ = req_json(svc, "POST", f"/v1/models/{spec}/build", body=body)
    assert status == 202, doc
    return doc["job"]


def test_health(svc):
    status, payload, headers = req(svc, "GET", "/v1/health", token=False)
    assert status == 200
    doc = json.loads(payload)
    assert doc["schemaVersion"] == 1
    assert doc["service"] == "cadstudio"
    assert doc["protocolVersion"] == server.PROTOCOL_VERSION
    assert doc["repoRoot"] == str(svc.repo_root)
    assert doc["pid"] == os.getpid()
    assert svc.token.encode() not in payload
    assert headers["Content-Type"] == "application/json"


def test_requires_token(svc):
    status, doc, _ = req_json(svc, "GET", "/v1/models", token=False)
    assert status == 401 and "error" in doc
    status, doc, _ = req_json(svc, "GET", "/v1/models",
                              headers={"Authorization": "Bearer nope"})
    assert status == 401
    status, doc, _ = req_json(svc, "GET", f"/v1/models?token={svc.token}", token=False)
    assert status == 200
    assert "starter/box" in doc["models"]
    projects = {p["name"]: p for p in doc["projects"]}
    assert projects["starter"]["params_path"].endswith("params.toml")


def test_bad_host_or_origin(svc):
    bad_host = {"Host": f"evil.example:{svc.port}"}
    status, _, _ = req(svc, "GET", "/v1/models", headers=bad_host)
    assert status == 403
    status, _, _ = req(svc, "GET", "/v1/health", token=False, headers=bad_host)
    assert status == 403
    status, _, _ = req(svc, "GET", "/v1/models", headers={"Origin": "http://evil.example"})
    assert status == 403
    status, _, _ = req(svc, "GET", "/v1/models", headers={"Origin": "null"})
    assert status == 403
    status, _, _ = req(svc, "GET", "/v1/models",
                       headers={"Origin": f"http://localhost:{svc.port}"})
    assert status == 200
    status, _, _ = req(svc, "GET", "/v1/models",
                       headers={"Host": f"localhost:{svc.port}"})
    assert status == 200


def test_root_fallback_page_without_ui_dist(tmp_path):
    service = server.GuiService(repo_root=tmp_path, ui_dist=tmp_path / "ui" / "dist", port=0,
                                quiet=True)
    service.start()
    try:
        status, payload, headers = req(service, "GET", "/", token=False)
        assert status == 200
        assert headers["Content-Type"].startswith("text/html")
        assert b"npm run build" in payload
        status, _, _ = req(service, "GET", "/assets/app.js", token=False)
        assert status == 404
    finally:
        service.close()


def test_serves_ui_dist_when_present(tmp_path):
    dist = tmp_path / "ui" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    service = server.GuiService(repo_root=tmp_path, ui_dist=tmp_path / "ui" / "dist", port=0,
                                quiet=True)
    service.start()
    try:
        status, payload, headers = req(service, "GET", "/", token=False)
        assert status == 200
        assert headers["Content-Type"].startswith("text/html")
        assert payload == b"<html>app</html>"
        status, payload, headers = req(service, "GET", "/assets/app.js", token=False)
        assert status == 200
        assert payload == b"console.log(1)"
        assert headers["Content-Type"].startswith("text/javascript")
        status, _, _ = req(service, "GET", "/../secret", token=False)
        assert status == 404
        status, _, _ = req(service, "GET", "/missing.js", token=False)
        assert status == 404
    finally:
        service.close()


def test_wrong_method_405(svc):
    status, doc, _ = req_json(svc, "POST", "/v1/health", body={})
    assert status == 405 and "error" in doc
    job = build(svc)
    wait_job(svc, job["id"])
    status, _, _ = req_json(svc, "GET", f"/v1/jobs/{job['id']}/cancel")
    assert status == 405
    status, _, _ = req_json(svc, "DELETE", f"/v1/jobs/{job['id']}")
    assert status == 405
    status, _, _ = req_json(svc, "GET", "/v1/nope")
    assert status == 404


def test_unknown_model_404(svc):
    for method, path in (("GET", "/v1/models/starter/nope/scene"),
                         ("GET", "/v1/models/nope/x/scene"),
                         ("POST", "/v1/models/starter/nope/build")):
        status, doc, _ = req_json(svc, method, path, body={} if method == "POST" else None)
        assert status == 404, (path, doc)
        assert "error" in doc
    status, doc, _ = req_json(svc, "GET", "/v1/models/starter/hinge/scene")
    assert status == 404
    assert doc["command"] == "cad gui scene starter/hinge"


def test_artifact_path_traversal(svc, tmp_path):
    scene_dir = project_out(svc.repo_root) / "box" / "scene"
    scene_dir.mkdir(parents=True, exist_ok=True)
    (scene_dir / "scene.json").write_text("{}")
    outside = tmp_path / "secret.json"
    outside.write_text("secret")
    for path in ("/v1/artifacts/../../etc/passwd",
                 "/v1/artifacts/%2E%2E/x",
                 "/v1/artifacts//etc/passwd",
                 "/v1/artifacts/%2Fetc%2Fpasswd",
                 "/v1/artifacts/projects%5Cstarter%5Cout%5Cbox%5Cscene%5Cscene.json"):
        status, doc, _ = req_json(svc, "GET", path)
        assert status == 403, (path, doc)
    status, _, _ = req_json(svc, "GET", "/v1/artifacts/.cadstudio/gui/service.json")
    assert status == 403

    link = scene_dir / "evil.json"
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(outside)
    try:
        status, _, _ = req_json(svc, "GET", "/v1/artifacts/projects/starter/out/box/scene/evil.json")
        assert status == 403
    finally:
        link.unlink()

    scene_link = project_out(svc.repo_root) / "link_scene" / "scene"
    scene_link.parent.mkdir(parents=True, exist_ok=True)
    if scene_link.exists() or scene_link.is_symlink():
        scene_link.unlink()
    scene_link.symlink_to(tmp_path)
    try:
        status, _, _ = req_json(svc, "GET", "/v1/artifacts/projects/starter/out/link_scene/scene/secret.json")
        assert status == 403
    finally:
        scene_link.unlink()

    report = project_out(svc.repo_root) / "box" / "report.json"
    report.write_text("{}")
    status, _, _ = req_json(svc, "GET", "/v1/artifacts/projects/starter/out/box/report.json")
    assert status == 403


def test_artifacts_are_contained_to_project_out_and_fixtures(svc):
    ws = svc.repo_root
    scene = project_out(ws) / "box" / "scene"
    scene.mkdir(parents=True, exist_ok=True)
    (scene / "scene.json").write_text("{}")
    (ws / "pyproject.toml").write_text("")
    fixtures = ws / ".cadstudio" / "fixtures" / "drop" / "run.gui"
    fixtures.mkdir(parents=True, exist_ok=True)
    (fixtures / "poses.bin").write_bytes(b"x")
    svc.discovery_path.with_name("service.log").write_text("log")
    status, _, _ = req_json(svc, "GET", "/v1/artifacts/projects/starter/out/box/scene/scene.json")
    assert status == 200
    status, _, _ = req(svc, "GET", "/v1/artifacts/.cadstudio/fixtures/drop/run.gui/poses.bin")
    assert status == 200
    for path in ("projects/starter/params.toml",          # project source, not output
                 "projects/starter/models/box.py",
                 "pyproject.toml",                       # workspace file
                 ".cadstudio/gui/service.json",          # hidden state is never served
                 ".cadstudio/gui/service.log",
                 "out/starter/box/scene/scene.json"):    # the retired top-level out/
        status, _, _ = req_json(svc, "GET", f"/v1/artifacts/{path}")
        assert status == 403, path


def test_build_job_serves_scene(svc):
    job = build(svc)
    finished = wait_job(svc, job["id"])
    assert finished["status"] == "succeeded", finished["error"]
    status, doc, _ = req_json(svc, "GET", "/v1/models/starter/box/scene")
    assert status == 200, doc
    assert doc["stale"] is False
    assert doc["error"] is None
    assert doc["job"] == job["id"]
    assert doc["artifactBase"] == "projects/starter/out/box/scene"
    assert (project_out(svc.repo_root) / "box" / "scene" / "scene.json").is_file()
    assert not (svc.repo_root / "out").exists()
    assert doc["scene"]["parts"][0]["id"] == "tray"
    status, payload, headers = req(svc, "GET",
                                   "/v1/artifacts/projects/starter/out/box/scene/parts/tray.glb")
    assert status == 200
    assert payload.startswith(b"glTF")
    assert headers["Content-Type"] == "model/gltf-binary"


def test_concurrent_builds_same_model_in_order(svc, monkeypatch):
    real = server._build_model
    events: list[tuple[str, str, float]] = []
    lock = threading.Lock()

    def wrapper(service, job, project, model, sets):
        with lock:
            events.append((job.id, "start", time.monotonic()))
        try:
            return real(service, job, project, model, sets)
        finally:
            with lock:
                events.append((job.id, "end", time.monotonic()))

    monkeypatch.setattr(server, "_build_model", wrapper)
    first = build(svc)
    second = build(svc)
    a = wait_job(svc, first["id"])
    b = wait_job(svc, second["id"])
    assert a["status"] == "succeeded", a["error"]
    assert b["status"] == "succeeded", b["error"]
    with lock:
        recorded = list(events)
    assert [e[0] for e in recorded] == [first["id"], first["id"], second["id"], second["id"]]
    assert [e[1] for e in recorded] == ["start", "end", "start", "end"]
    assert recorded[1][2] <= recorded[2][2]
    assert a["finishedAt"] <= b["startedAt"]


def test_cancel_rules(svc, monkeypatch):
    real = server._build_model
    release = threading.Event()
    entered = threading.Event()
    ran: list[str] = []

    def wrapper(service, job, project, model, sets):
        ran.append(job.id)
        entered.set()
        assert release.wait(timeout=120)
        return real(service, job, project, model, sets)

    monkeypatch.setattr(server, "_build_model", wrapper)
    first = build(svc)
    assert entered.wait(timeout=60)
    second = build(svc)  # queued behind the first
    status, doc, _ = req_json(svc, "POST", f"/v1/jobs/{second['id']}/cancel")
    assert status == 200, doc
    assert doc["job"]["status"] == "cancelled"
    status, doc, _ = req_json(svc, "POST", f"/v1/jobs/{first['id']}/cancel")
    assert status == 409
    assert "cannot be cancelled" in doc["error"]
    release.set()
    assert wait_job(svc, first["id"])["status"] == "succeeded"
    assert wait_job(svc, second["id"])["status"] == "cancelled"
    assert ran == [first["id"]]


def test_failed_build_keeps_scene_stale(svc):
    status, before, _ = req_json(svc, "GET", "/v1/models/starter/box/scene")
    if status != 200:
        job = build(svc)
        assert wait_job(svc, job["id"])["status"] == "succeeded"
        status, before, _ = req_json(svc, "GET", "/v1/models/starter/box/scene")
    assert status == 200
    job = build(svc, body={"set": {"nope.key": 1}})
    failed = wait_job(svc, job["id"])
    assert failed["status"] == "failed"
    assert "unknown parameter" in failed["error"]
    status, after, _ = req_json(svc, "GET", "/v1/models/starter/box/scene")
    assert status == 200
    assert after["stale"] is True
    assert after["error"] == failed["error"]
    assert after["job"] == job["id"]
    assert after["scene"]["provenance"]["builtAt"] == before["scene"]["provenance"]["builtAt"]


def _sse_reader(svc, events: list[dict], stop: threading.Event,
                ready: threading.Event) -> None:
    conn = http.client.HTTPConnection("127.0.0.1", svc.port, timeout=30)
    conn.request("GET", f"/v1/events?token={svc.token}")
    resp = conn.getresponse()
    assert resp.status == 200
    assert resp.getheader("Content-Type") == "text/event-stream"
    ready.set()
    current: dict = {}
    try:
        while not stop.is_set():
            line = resp.fp.readline()
            if not line:
                break
            text = line.decode("utf-8").rstrip("\n")
            if not text:
                if current:
                    events.append(current)
                current = {}
                continue
            key, _, value = text.partition(": ")
            if key == "id":
                current["id"] = int(value)
            elif key == "event":
                current["event"] = value
            elif key == "data":
                current["data"] = json.loads(value)
    finally:
        conn.close()


def test_sse_delivers_job_events(svc):
    events: list[dict] = []
    stop = threading.Event()
    ready = threading.Event()
    reader = threading.Thread(target=_sse_reader, args=(svc, events, stop, ready), daemon=True)
    reader.start()
    assert ready.wait(timeout=10), "SSE stream did not open"
    deadline = time.monotonic() + 10
    while svc.events.subscriber_count() == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    job = build(svc, body={"set": {"nope.key": 1}})
    wait_job(svc, job["id"])
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if any(e.get("event") == "job" and e["data"]["job"]["id"] == job["id"]
               and e["data"]["job"]["status"] == "failed" for e in events):
            break
        time.sleep(0.05)
    stop.set()
    reader.join(timeout=5)
    ours = [e for e in events
            if e.get("event") == "job" and e["data"]["job"]["id"] == job["id"]]
    assert ours, events
    assert any(e["data"]["job"]["status"] in {"queued", "running"} for e in ours)
    assert ours[-1]["data"]["job"]["status"] == "failed"
    assert ours[-1]["id"] >= 1


def test_stale_discovery_file_replaced(tmp_path):
    dead = subprocess.Popen([sys.executable, "-c", ""])
    dead.wait()
    ws = make_starter_workspace(tmp_path)
    path = server.discovery_path(ws)
    assert path == ws / ".cadstudio" / "gui" / "service.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"pid": dead.pid, "port": 1, "token": "old",
                                "repoRoot": str(ws.resolve())}))
    service, record = server.start_service(repo_root=ws, quiet=True)
    try:
        assert service is not None
        assert record["pid"] == os.getpid()
        assert record["port"] == service.port
        assert record["token"] == service.token
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600, oct(mode)
    finally:
        service.close()
    assert not path.exists()


def test_healthy_service_is_reused(svc):
    service, record = server.start_service(repo_root=svc.repo_root, quiet=True)
    assert service is None
    assert record["port"] == svc.port
    assert record["token"] == svc.token


def test_sigterm_removes_discovery(tmp_path):
    ws = make_starter_workspace(tmp_path)
    code = ("import sys; from cadkit.gui.server import run; "
            "sys.exit(run(port=0, open_browser=False, as_json=True, repo_root=sys.argv[1]))")
    proc = subprocess.Popen([sys.executable, "-c", code, str(ws)], cwd=ws,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            env={**_env(), "PYTHONPATH": str(REPO_ROOT)})
    try:
        line = proc.stdout.readline()
        doc = json.loads(line)
        assert doc["reused"] is False
        status, payload, _ = req(_PortOnly(doc["port"]), "GET", "/v1/health", token=False)
        assert status == 200
        assert json.loads(payload)["repoRoot"] == str(ws)
        assert doc["discovery"] == str(ws / ".cadstudio" / "gui" / "service.json")
        assert server.discovery_path(ws).is_file()
        assert not (ws / "out").exists()
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=10)
        assert not server.discovery_path(ws).exists()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


class _PortOnly:
    """Just enough of a service for ``req``: the health route needs no token."""

    def __init__(self, port: int) -> None:
        self.port = port
        self.token = ""


@pytest.fixture
def phys_svc(tmp_path):
    """A service over a workspace whose ``rig`` project has physics input files."""
    ws = make_physics_workspace(tmp_path)
    with workspace_env(ws):
        service = server.GuiService(repo_root=ws, port=0, quiet=True, watch=False)
        service.start()
        try:
            yield service
        finally:
            service.close()


def test_run_job_paths_and_cancel(phys_svc, monkeypatch):
    svc = phys_svc
    for bad, expected in (({"scenario": "../../etc/passwd"}, 403),
                          ({"scenario": "/etc/passwd"}, 403),
                          ({"scenario": "physics/scenarios/nope.json"}, 400)):
        body = {"model": "rig/box", "acceptance": ACCEPTANCE, **bad}
        status, doc, _ = req_json(svc, "POST", "/v1/runs", body=body)
        assert status == expected, (body, status, doc)

    monkeypatch.setattr(server, "_physics_command",
                        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(60)"])
    body = {"model": "rig/box", "scenario": SCENARIO, "acceptance": ACCEPTANCE}
    status, doc, _ = req_json(svc, "POST", "/v1/runs", body=body)
    assert status == 202, doc
    job = doc["job"]
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        status, current, _ = req_json(svc, "GET", f"/v1/jobs/{job['id']}")
        if current["job"]["status"] == "running":
            break
        time.sleep(0.05)
    assert current["job"]["status"] == "running"
    status, cancelled, _ = req_json(svc, "POST", f"/v1/jobs/{job['id']}/cancel")
    assert status == 200, cancelled
    finished = wait_job(svc, job["id"], timeout=15)
    assert finished["status"] == "cancelled"
    deadline = time.monotonic() + 10
    while svc.jobs[job["id"]]._proc is not None and time.monotonic() < deadline:
        time.sleep(0.05)
    assert svc.jobs[job["id"]]._proc is None


def test_run_job_writes_under_project_runs_and_reports_workspace_relative_run_id(
        phys_svc, monkeypatch):
    svc = phys_svc
    seen: list[str] = []

    def fake_command(*args, **kwargs):
        out = str(args[-1])  # the signature keeps ``out`` as the last positional argument
        seen.append(out)
        return [sys.executable, "-c", "import os, sys; os.makedirs(sys.argv[1])", out]

    monkeypatch.setattr(server, "_physics_command", fake_command)
    body = {"model": "rig/box", "scenario": SCENARIO, "acceptance": ACCEPTANCE}
    status, doc, _ = req_json(svc, "POST", "/v1/runs", body=body)
    assert status == 202, doc
    finished = wait_job(svc, doc["job"]["id"], timeout=30)
    assert finished["status"] == "succeeded", finished
    runs_dir = svc.repo_root / "projects" / "rig" / "out" / "box" / "runs"
    out = Path(seen[0])
    assert out.is_relative_to(runs_dir) and out != runs_dir, out
    run_id = finished["artifacts"]["runId"]
    assert run_id == out.relative_to(svc.repo_root).as_posix()
    assert run_id.startswith("projects/rig/out/box/runs/")
    assert not (svc.repo_root / "out").exists()


def test_physics_cancel_before_subprocess_starts(svc, monkeypatch):
    calls: list[tuple] = []
    real_popen = subprocess.Popen

    def fake_popen(*args, **kwargs):
        calls.append(args)
        return real_popen(*args, **kwargs)

    job = server.Job(kind="run", key="starter/box", model="starter/box")
    job._cancel.set()
    monkeypatch.setattr(server.subprocess, "Popen", fake_popen)
    server._run_physics(svc, job, [sys.executable, "-c", "import time; time.sleep(60)"],
                        project_out(svc.repo_root) / "nope")
    assert calls == []
    assert job.status == "cancelled"


def test_physics_cancel_during_popen_kills_the_process(svc, monkeypatch):
    real_popen = subprocess.Popen
    job = server.Job(kind="run", key="starter/box", model="starter/box")
    job.status = "running"

    def fake_popen(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        job._cancel.set()  # cancel lands in the window between Popen and job._proc
        return proc

    monkeypatch.setattr(server.subprocess, "Popen", fake_popen)
    server._run_physics(svc, job, [sys.executable, "-c", "import time; time.sleep(60)"],
                        project_out(svc.repo_root) / "nope")
    assert job.status == "cancelled"
    assert job._proc is None
    assert job._terminating is True


def test_runs_and_trajectory(svc):
    pytest.importorskip("mujoco")
    from cadkit.physics.runner import run_scenario_files

    scenario = {
        "schema_version": "m4a-1", "scenario_id": "drop", "fixture": "drop_box", "seed": 1,
        "timestep_s": 0.001, "sampling_interval_s": 0.05,
        "budgets": {"max_steps": 20000, "max_sim_time_s": 10.0, "max_trace_rows": 20000},
        "phases": [{"name": "reset", "kind": "reset"},
                   {"name": "settle", "kind": "settle", "duration_s": 0.6},
                   {"name": "hold", "kind": "hold", "duration_s": 0.2}],
    }
    acceptance = {
        "schema_version": "m4a-1", "acceptance_id": "drop_acceptance",
        "validity": {"max_penetration_m": 0.001, "max_speed_m_s": 10.0, "max_energy_j": 1.0},
        "checks": [
            {"name": "contact", "kind": "contact_force_bound", "body_a": "box",
             "body_b": "floor", "max": 100.0, "units": "N"},
            {"name": "penetration", "kind": "penetration_bound", "max": 0.001, "units": "m"},
        ],
    }
    fixture_dir = svc.repo_root / ".cadstudio" / "fixtures" / "drop"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    scenario_path = fixture_dir / "scenario.json"
    acceptance_path = fixture_dir / "acceptance.json"
    scenario_path.write_text(json.dumps(scenario))
    acceptance_path.write_text(json.dumps(acceptance))
    run_dir = fixture_dir / "run"
    summary = run_scenario_files(scenario_path, acceptance_path, run_dir)
    assert summary["status"] == "PASS", summary.get("detail")

    status, doc, _ = req_json(svc, "GET", "/v1/runs")
    assert status == 200
    run_ids = {run["runId"] for run in doc["runs"]}
    assert ".cadstudio/fixtures/drop/run" in run_ids
    listed = next(run for run in doc["runs"] if run["runId"] == ".cadstudio/fixtures/drop/run")
    assert listed["status"] == "PASS"
    assert listed["project"] is None and listed["model"] is None

    status, doc, _ = req_json(svc, "GET", "/v1/runs/.cadstudio/fixtures/drop/run/trajectory")
    assert status == 200, doc
    assert doc["runId"] == ".cadstudio/fixtures/drop/run"
    assert doc["stale"] is False
    assert doc["artifactBase"] == ".cadstudio/fixtures/drop/run.gui"
    assert doc["trajectory"]["units"] == "mm"

    status, payload, headers = req(svc, "GET", "/v1/artifacts/.cadstudio/fixtures/drop/run.gui/poses.bin")
    assert status == 200
    assert payload
    assert headers["Content-Type"] == "application/octet-stream"
    status, _, _ = req_json(svc, "GET", "/v1/runs/.cadstudio/fixtures/drop/nope/trajectory")
    assert status == 404


def test_runs_are_listed_newest_first(svc):
    # Listing only needs the two marker files, so fake runs with set mtimes are enough.
    stamps = {"old/run": 1_000_000.0, "new/run": 3_000_000.0, "mid/run": 2_000_000.0}
    base = "projects/starter/out/box/runs/ordering"
    for run_id, mtime in stamps.items():
        run_dir = write_fake_run(svc.repo_root / base / run_id)
        os.utime(run_dir / "summary.json", (mtime, mtime))

    status, doc, _ = req_json(svc, "GET", "/v1/runs")
    assert status == 200
    listed = [run for run in doc["runs"] if run["runId"].startswith(f"{base}/")]
    assert [run["runId"] for run in listed] == [f"{base}/new/run", f"{base}/mid/run",
                                                f"{base}/old/run"]
    assert {(run["project"], run["model"]) for run in listed} == {("starter", "starter/box")}
    assert [run["modified"] for run in listed] == [3_000_000.0, 2_000_000.0, 1_000_000.0]
