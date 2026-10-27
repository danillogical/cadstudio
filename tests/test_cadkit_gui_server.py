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

TERMINAL = {"succeeded", "failed", "cancelled"}


def _env() -> dict:
    env = {k: v for k, v in os.environ.items() if k != "POCKY_POSE"}
    env["PATH"] = f"{Path.home() / '.local' / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    return env


@pytest.fixture(scope="module", autouse=True)
def _no_pose_env():
    saved = os.environ.pop("POCKY_POSE", None)
    try:
        yield
    finally:
        if saved is not None:
            os.environ["POCKY_POSE"] = saved


@pytest.fixture(scope="module")
def svc(tmp_path_factory):
    service = server.GuiService(out_root=tmp_path_factory.mktemp("gui_out"), port=0, quiet=True)
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


def build(svc, spec="pocky/packet_dummy", body=None):
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
    assert doc["repoRoot"] == str(REPO_ROOT.resolve())
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
    assert "pocky/packet_dummy" in doc["models"]
    projects = {p["name"]: p for p in doc["projects"]}
    assert projects["pocky"]["params_path"].endswith("params.toml")


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
    service = server.GuiService(repo_root=tmp_path, out_root=tmp_path / "out", port=0, quiet=True)
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
    service = server.GuiService(repo_root=tmp_path, out_root=tmp_path / "out", port=0, quiet=True)
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
    for method, path in (("GET", "/v1/models/pocky/nope/scene"),
                         ("GET", "/v1/models/nope/x/scene"),
                         ("POST", "/v1/models/pocky/nope/build")):
        status, doc, _ = req_json(svc, method, path, body={} if method == "POST" else None)
        assert status == 404, (path, doc)
        assert "error" in doc
    status, doc, _ = req_json(svc, "GET", "/v1/models/armor/armor_proto/scene")
    assert status == 404
    assert doc["command"] == "cad gui scene armor/armor_proto"


def test_artifact_path_traversal(svc, tmp_path):
    scene_dir = svc.out_root / "pocky" / "packet_dummy" / "scene"
    scene_dir.mkdir(parents=True, exist_ok=True)
    (scene_dir / "scene.json").write_text("{}")
    outside = tmp_path / "secret.json"
    outside.write_text("secret")
    for path in ("/v1/artifacts/../../etc/passwd",
                 "/v1/artifacts/%2E%2E/x",
                 "/v1/artifacts//etc/passwd",
                 "/v1/artifacts/%2Fetc%2Fpasswd",
                 "/v1/artifacts/pocky%5Cpacket_dummy%5Cscene%5Cscene.json"):
        status, doc, _ = req_json(svc, "GET", path)
        assert status == 403, (path, doc)
    status, _, _ = req_json(svc, "GET", "/v1/artifacts/.gui/service.json")
    assert status == 403

    link = scene_dir / "evil.json"
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(outside)
    try:
        status, _, _ = req_json(svc, "GET", "/v1/artifacts/pocky/packet_dummy/scene/evil.json")
        assert status == 403
    finally:
        link.unlink()

    scene_link = svc.out_root / "pocky" / "link_scene" / "scene"
    scene_link.parent.mkdir(parents=True, exist_ok=True)
    if scene_link.exists() or scene_link.is_symlink():
        scene_link.unlink()
    scene_link.symlink_to(tmp_path)
    try:
        status, _, _ = req_json(svc, "GET", "/v1/artifacts/pocky/link_scene/scene/secret.json")
        assert status == 403
    finally:
        scene_link.unlink()

    report = svc.out_root / "pocky" / "packet_dummy" / "report.json"
    report.write_text("{}")
    status, _, _ = req_json(svc, "GET", "/v1/artifacts/pocky/packet_dummy/report.json")
    assert status == 403


def test_build_job_serves_scene(svc):
    job = build(svc)
    finished = wait_job(svc, job["id"])
    assert finished["status"] == "succeeded", finished["error"]
    status, doc, _ = req_json(svc, "GET", "/v1/models/pocky/packet_dummy/scene")
    assert status == 200, doc
    assert doc["stale"] is False
    assert doc["error"] is None
    assert doc["job"] == job["id"]
    assert doc["artifactBase"] == "pocky/packet_dummy/scene"
    assert doc["scene"]["parts"][0]["id"] == "dummy"
    status, payload, headers = req(svc, "GET",
                                   "/v1/artifacts/pocky/packet_dummy/scene/parts/dummy.glb")
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
    status, before, _ = req_json(svc, "GET", "/v1/models/pocky/packet_dummy/scene")
    if status != 200:
        job = build(svc)
        assert wait_job(svc, job["id"])["status"] == "succeeded"
        status, before, _ = req_json(svc, "GET", "/v1/models/pocky/packet_dummy/scene")
    assert status == 200
    job = build(svc, body={"set": {"nope.key": 1}})
    failed = wait_job(svc, job["id"])
    assert failed["status"] == "failed"
    assert "unknown parameter" in failed["error"]
    status, after, _ = req_json(svc, "GET", "/v1/models/pocky/packet_dummy/scene")
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
    out = tmp_path / "out"
    path = server.discovery_path(out)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"pid": dead.pid, "port": 1, "token": "old",
                                "repoRoot": str(REPO_ROOT.resolve())}))
    service, record = server.start_service(repo_root=REPO_ROOT, out_root=out, quiet=True)
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
    service, record = server.start_service(repo_root=svc.repo_root, out_root=svc.out_root,
                                           quiet=True)
    assert service is None
    assert record["port"] == svc.port
    assert record["token"] == svc.token


def test_sigterm_removes_discovery(tmp_path):
    out = tmp_path / "out"
    code = ("import sys; from cadkit.gui.server import run; "
            "sys.exit(run(port=0, open_browser=False, as_json=True, out_root=sys.argv[1]))")
    proc = subprocess.Popen([sys.executable, "-c", code, str(out)], cwd=REPO_ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            env=_env())
    try:
        line = proc.stdout.readline()
        doc = json.loads(line)
        assert doc["reused"] is False
        status, payload, _ = req(_PortOnly(doc["port"]), "GET", "/v1/health", token=False)
        assert status == 200
        assert json.loads(payload)["repoRoot"] == str(REPO_ROOT.resolve())
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=10)
        assert not server.discovery_path(out).exists()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


class _PortOnly:
    """Just enough of a service for ``req``: the health route needs no token."""

    def __init__(self, port: int) -> None:
        self.port = port
        self.token = ""


def test_run_job_paths_and_cancel(svc, monkeypatch):
    for bad, expected in (({"scenario": "../../etc/passwd"}, 403),
                          ({"scenario": "/etc/passwd"}, 403),
                          ({"scenario": "physics/scenarios/nope.json"}, 400)):
        body = {"model": "pocky/syringe", "acceptance": "physics/syringe_two_cycle_acceptance.json",
                **bad}
        status, doc, _ = req_json(svc, "POST", "/v1/runs", body=body)
        assert status == expected, (body, status, doc)

    monkeypatch.setattr(server, "_physics_command",
                        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(60)"])
    body = {"model": "pocky/syringe", "scenario": "physics/scenarios/syringe_two_cycle.json",
            "acceptance": "physics/syringe_two_cycle_acceptance.json"}
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


def test_physics_cancel_before_subprocess_starts(svc, monkeypatch):
    calls: list[tuple] = []
    real_popen = subprocess.Popen

    def fake_popen(*args, **kwargs):
        calls.append(args)
        return real_popen(*args, **kwargs)

    job = server.Job(kind="run", key="pocky/syringe", model="pocky/syringe")
    job._cancel.set()
    monkeypatch.setattr(server.subprocess, "Popen", fake_popen)
    server._run_physics(svc, job, [sys.executable, "-c", "import time; time.sleep(60)"],
                        svc.out_root / "nope")
    assert calls == []
    assert job.status == "cancelled"


def test_physics_cancel_during_popen_kills_the_process(svc, monkeypatch):
    real_popen = subprocess.Popen
    job = server.Job(kind="run", key="pocky/syringe", model="pocky/syringe")
    job.status = "running"

    def fake_popen(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        job._cancel.set()  # cancel lands in the window between Popen and job._proc
        return proc

    monkeypatch.setattr(server.subprocess, "Popen", fake_popen)
    server._run_physics(svc, job, [sys.executable, "-c", "import time; time.sleep(60)"],
                        svc.out_root / "nope")
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
    fixture_dir = svc.out_root / "fixtures" / "drop"
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
    assert "fixtures/drop/run" in run_ids
    listed = next(run for run in doc["runs"] if run["runId"] == "fixtures/drop/run")
    assert listed["status"] == "PASS"

    status, doc, _ = req_json(svc, "GET", "/v1/runs/fixtures/drop/run/trajectory")
    assert status == 200, doc
    assert doc["runId"] == "fixtures/drop/run"
    assert doc["stale"] is False
    assert doc["artifactBase"] == "fixtures/drop/run.gui"
    assert doc["trajectory"]["units"] == "mm"

    status, payload, headers = req(svc, "GET", "/v1/artifacts/fixtures/drop/run.gui/poses.bin")
    assert status == 200
    assert payload
    assert headers["Content-Type"] == "application/octet-stream"
    status, _, _ = req_json(svc, "GET", "/v1/runs/fixtures/drop/nope/trajectory")
    assert status == 404


def test_runs_are_listed_newest_first(svc):
    # Listing only needs the two marker files, so fake runs with set mtimes are enough.
    stamps = {"old/run": 1_000_000.0, "new/run": 3_000_000.0, "mid/run": 2_000_000.0}
    for run_id, mtime in stamps.items():
        run_dir = svc.out_root / "ordering" / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "summary.json").write_text(json.dumps({"status": "PASS"}))
        (run_dir / "states.npz").write_bytes(b"")
        os.utime(run_dir / "summary.json", (mtime, mtime))

    status, doc, _ = req_json(svc, "GET", "/v1/runs")
    assert status == 200
    listed = [run for run in doc["runs"] if run["runId"].startswith("ordering/")]
    assert [run["runId"] for run in listed] == ["ordering/new/run", "ordering/mid/run",
                                                "ordering/old/run"]
    assert [run["modified"] for run in listed] == [3_000_000.0, 2_000_000.0, 1_000_000.0]
