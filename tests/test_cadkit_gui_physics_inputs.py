"""``GET /v1/models/{project}/{model}/physics-inputs`` and the run-path allowlist (packet G3c)."""
from __future__ import annotations

import http.client
import json
import sys
import time
import types
from pathlib import Path

import pytest

from cadkit.gui import server
from physics_workspace import ACCEPTANCE, NOT_LISTED, OPTIONS, PY_FILE, SCENARIO, make_physics_workspace, workspace_env

INPUTS = "/v1/models/rig/box/physics-inputs"


@pytest.fixture(scope="module")
def ws(tmp_path_factory):
    return make_physics_workspace(tmp_path_factory.mktemp("gui_inputs_ws"))


@pytest.fixture(scope="module")
def svc(ws, tmp_path_factory):
    with workspace_env(ws):
        service = server.GuiService(repo_root=ws, out_root=tmp_path_factory.mktemp("gui_inputs_out"),
                                    port=0, quiet=True)
        service.start()
        try:
            yield service
        finally:
            service.close()


def req_json(svc, method, path, *, token=True, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", svc.port, timeout=60)
    headers = {"Authorization": f"Bearer {svc.token}"} if token else {}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    try:
        conn.request(method, path, body=data, headers=headers)
        resp = conn.getresponse()
        payload = resp.read()
        return resp.status, (json.loads(payload) if payload else None)
    finally:
        conn.close()


def expected(ws: Path, subdir: str, pattern: str) -> list[str]:
    return sorted(p.relative_to(ws).as_posix() for p in (ws / "projects" / "rig" / subdir).glob(pattern)
                  if p.is_file() and not p.is_symlink())


def test_listing_matches_project_files(svc, ws):
    status, doc = req_json(svc, "GET", INPUTS)
    assert status == 200, doc
    assert doc["schemaVersion"] == 1
    assert (doc["project"], doc["model"]) == ("rig", "box")
    want = {"scenarios": expected(ws, "physics/scenarios", "*.json"),
            "acceptance": expected(ws, "physics", "*_acceptance.json"),
            "options": expected(ws, "physics/options", "*.toml")}
    for key, paths in want.items():
        assert paths, key
        assert [entry["path"] for entry in doc[key]] == paths
        for entry in doc[key]:
            assert set(entry) == {"name", "path"}
            assert not Path(entry["path"]).is_absolute()
            assert entry["name"] == Path(entry["path"]).name
            assert (ws / entry["path"]).is_file()
    assert f"projects/rig/{SCENARIO}" in want["scenarios"]
    assert f"projects/rig/{ACCEPTANCE}" in want["acceptance"]
    assert f"projects/rig/{OPTIONS}" in want["options"]


def test_listing_for_project_without_physics_is_empty(svc):
    status, doc = req_json(svc, "GET", "/v1/models/bare/box/physics-inputs")
    assert status == 200, doc
    assert (doc["scenarios"], doc["acceptance"], doc["options"]) == ([], [], [])


def test_listing_requires_token(svc):
    status, doc = req_json(svc, "GET", INPUTS, token=False)
    assert status == 401, doc


def test_listing_refuses_unknown_and_traversal(svc):
    for path in ("/v1/models/rig/nope/physics-inputs",
                 "/v1/models/nope/box/physics-inputs",
                 "/v1/models/%2E%2E/box/physics-inputs",
                 "/v1/models/rig/%2E%2E/physics-inputs",
                 "/v1/models/rig/..%2F..%2Fbox/physics-inputs"):
        status, doc = req_json(svc, "GET", path)
        assert status == 404, (path, doc)
    status, _ = req_json(svc, "POST", INPUTS, body={})
    assert status == 405


def test_helper_skips_symlinks_and_other_files(tmp_path):
    root = tmp_path / "repo"
    project_dir = root / "projects" / "demo"
    (project_dir / "models").mkdir(parents=True)
    (project_dir / "models" / "__init__.py").write_text("")
    (project_dir / "physics" / "scenarios").mkdir(parents=True)
    (project_dir / "physics" / "options").mkdir()
    (project_dir / "physics" / "scenarios" / "a.json").write_text("{}")
    (project_dir / "physics" / "scenarios" / "notes.txt").write_text("")
    (project_dir / "physics" / "options" / "o.toml").write_text("")
    (project_dir / "physics" / "x_acceptance.json").write_text("{}")
    (project_dir / "physics" / "acceptance.toml").write_text("")
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    (project_dir / "physics" / "scenarios" / "link.json").symlink_to(outside)
    project = types.SimpleNamespace(
        name="demo", models=types.SimpleNamespace(__file__=str(project_dir / "models" / "__init__.py")))
    listing = server._physics_inputs(project, root)
    assert [e.path for e in listing["scenarios"]] == ["projects/demo/physics/scenarios/a.json"]
    assert [e.path for e in listing["acceptance"]] == ["projects/demo/physics/x_acceptance.json"]
    assert [e.project_path for e in listing["options"]] == ["physics/options/o.toml"]


def test_run_rejects_paths_not_in_listing(svc, ws):
    good = {"model": "rig/box",
            "scenario": f"projects/rig/{SCENARIO}",
            "acceptance": f"projects/rig/{ACCEPTANCE}"}
    cases = (
        ({"scenario": "projects/rig/params.toml"}, 403),         # exists, not a scenario
        ({"scenario": "params.toml"}, 403),                      # same, project-relative
        ({"scenario": PY_FILE}, 403),
        ({"scenario": good["acceptance"]}, 403),                 # listed, but as acceptance
        ({"acceptance": f"projects/rig/{NOT_LISTED}"}, 403),
        ({"options": f"projects/rig/{SCENARIO}"}, 403),
        ({"scenario": "pyproject.toml"}, 403),                   # repo file outside the project
        ({"scenario": "projects/rig/physics/scenarios/nope.json"}, 400),
        ({"scenario": f"projects/../projects/rig/{SCENARIO}"}, 403),
        ({"scenario": str(ws / good["scenario"])}, 403),         # absolute
    )
    before = len(svc.jobs)
    for override, expected_status in cases:
        status, doc = req_json(svc, "POST", "/v1/runs", body={**good, **override})
        assert status == expected_status, (override, status, doc)
        assert "error" in doc
    assert len(svc.jobs) == before


@pytest.mark.parametrize("spelling", ["repo", "project"])
def test_run_accepts_listed_paths(svc, ws, monkeypatch, spelling):
    seen: list[tuple] = []

    def fake_command(*args, **kwargs):
        seen.append(args)
        return [sys.executable, "-c", "import time; time.sleep(60)"]

    monkeypatch.setattr(server, "_physics_command", fake_command)
    prefix = "projects/rig/" if spelling == "repo" else ""
    body = {"model": "rig/box",
            "scenario": f"{prefix}{SCENARIO}",
            "acceptance": f"{prefix}{ACCEPTANCE}",
            "options": f"{prefix}{OPTIONS}"}
    status, doc = req_json(svc, "POST", "/v1/runs", body=body)
    assert status == 202, doc
    job_id = doc["job"]["id"]
    try:
        deadline = time.monotonic() + 30
        while not seen and time.monotonic() < deadline:
            time.sleep(0.05)
        spec, scenario, acceptance, options, _out = seen[0]
        rig = ws / "projects" / "rig"
        assert spec == "rig/box"
        assert Path(scenario) == rig / SCENARIO
        assert Path(acceptance) == rig / ACCEPTANCE
        assert Path(options) == rig / OPTIONS
    finally:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            _, current = req_json(svc, "GET", f"/v1/jobs/{job_id}")
            if current["job"]["status"] in {"running", "succeeded", "failed", "cancelled"}:
                break
            time.sleep(0.05)
        if current["job"]["status"] in {"queued", "running"}:
            req_json(svc, "POST", f"/v1/jobs/{job_id}/cancel")
        deadline = time.monotonic() + 15
        while svc.jobs[job_id].status not in {"succeeded", "failed", "cancelled"} \
                and time.monotonic() < deadline:
            time.sleep(0.05)
        assert svc.jobs[job_id].status == "cancelled"
