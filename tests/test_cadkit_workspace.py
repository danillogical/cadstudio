"""Workspace rule: the engine finds ``projects/`` (and each project's ``out/``) from the cwd, not from its own repo.

The workspace is the nearest ancestor of the cwd (itself included) holding a ``projects/``
directory; ``CADSTUDIO_WORKSPACE`` overrides the search. Every test runs the real engine at the
repo root against a temp workspace that has no ``cadkit`` of its own.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from gui_tiny_repo import _BOX_MODEL, _INIT, _PARAMS, _PARAMS_TOML, PROJECT

ENGINE = Path(__file__).resolve().parents[1]


def make_workspace(root: Path, name: str = "ws", project: str = PROJECT) -> Path:
    """A workspace with only ``projects/__init__.py`` and one tiny project (no ``cadkit``)."""
    ws = root / name
    proj = ws / "projects" / project
    (proj / "models").mkdir(parents=True)
    (ws / "projects" / "__init__.py").write_text("")
    (proj / "__init__.py").write_text(_INIT.replace('name="tiny"', f'name="{project}"'))
    (proj / "params.py").write_text(_PARAMS)
    (proj / "params.toml").write_text(_PARAMS_TOML)
    (proj / "models" / "__init__.py").write_text("")
    (proj / "models" / "box.py").write_text(_BOX_MODEL.format(size=10.0))
    return ws.resolve()


def cad_env(**extra: str) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in ("CADSTUDIO_WORKSPACE", "POCKY_POSE", "PYTHONPATH")}
    env["PYTHONPATH"] = str(ENGINE)
    env.update(extra)
    return env


def run_cad(cwd: Path, *args: str, **env_extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "cadkit.cli", *args], cwd=cwd,
                          env=cad_env(**env_extra), capture_output=True, text=True, timeout=300)


def listed(proc: subprocess.CompletedProcess) -> list[str]:
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    models = doc["models"] if isinstance(doc, dict) else doc
    return sorted(m if isinstance(m, str) else m.get("name", m.get("model", "")) for m in models)


@pytest.fixture(scope="module")
def ws(tmp_path_factory) -> Path:
    return make_workspace(tmp_path_factory.mktemp("workspace"))


def test_list_shows_only_workspace_projects(ws):
    names = listed(run_cad(ws, "list", "--json"))
    assert names == ["tiny/box"]
    assert not any(n.startswith(("armor/", "pocky/")) for n in names)


def test_list_from_subdirectory_finds_ancestor_workspace(ws):
    sub = ws / "projects" / "tiny" / "models"
    assert listed(run_cad(sub, "list", "--json")) == ["tiny/box"]


def test_build_writes_to_project_out(ws):
    proc = run_cad(ws, "build", "tiny/box")
    assert proc.returncode == 0, proc.stderr
    box_out = ws / "projects" / "tiny" / "out" / "box"
    assert (box_out / "box.step").exists() or any(box_out.glob("*.step"))
    assert not (ws / "out").exists()
    assert not (ENGINE / "out" / "tiny").exists()


def test_env_override_beats_cwd_workspace(tmp_path):
    a = make_workspace(tmp_path, "a", project="alpha")
    b = make_workspace(tmp_path, "b", project="beta")
    assert listed(run_cad(b, "list", "--json")) == ["beta/box"]
    assert listed(run_cad(b, "list", "--json", CADSTUDIO_WORKSPACE=str(a))) == ["alpha/box"]


def test_no_workspace_is_an_error(tmp_path):
    empty = tmp_path / "nothing"
    empty.mkdir()
    proc = run_cad(empty, "list")
    assert proc.returncode != 0
    assert "projects" in proc.stderr
    assert "CADSTUDIO_WORKSPACE" in proc.stderr


def test_doctor_reports_hidden_state_dir_and_engine_ui(ws):
    proc = run_cad(ws, "doctor", "--json")
    checks = json.loads(proc.stdout)["checks"]
    assert Path(checks["output_dir"]["path"]).resolve() == ws / ".cadstudio"
    if (ENGINE / "ui" / "dist").is_dir():
        assert checks["ui_dist"]["present"] is True
        assert Path(checks["ui_dist"]["path"]).resolve() == (ENGINE / "ui" / "dist").resolve()


class Served:
    """``cad gui serve --no-browser --json`` in a workspace."""

    def __init__(self, cwd: Path, **env_extra: str) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "cadkit.cli", "gui", "serve", "--no-browser", "--json"],
            cwd=cwd, env=cad_env(**env_extra), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True)
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("service did not start: " + self.proc.stderr.read())
        self.doc = json.loads(line)

    def get(self, path: str, token: str | None = None):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.doc["port"], timeout=60)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            conn.request("GET", path, headers=headers)
            resp = conn.getresponse()
            return resp.status, json.loads(resp.read() or b"null")
        finally:
            conn.close()

    def close(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def test_gui_service_is_rooted_at_workspace(tmp_path):
    ws = make_workspace(tmp_path)
    phys = ws / "projects" / "tiny" / "physics"
    for rel in ("scenarios/x.json", "x_acceptance.json", "options/x.toml"):
        (phys / rel).parent.mkdir(parents=True, exist_ok=True)
        (phys / rel).write_text("{}" if rel.endswith(".json") else "")
    svc = Served(ws)
    try:
        record = json.loads((ws / ".cadstudio" / "gui" / "service.json").read_text())
        assert Path(record["repoRoot"]).resolve() == ws
        status, health = svc.get("/v1/health")
        assert status == 200
        assert Path(health["repoRoot"]).resolve() == ws
        status, doc = svc.get("/v1/models/tiny/box/physics-inputs", record["token"])
        assert status == 200, doc
        assert [e["path"] for e in doc["scenarios"]] == ["projects/tiny/physics/scenarios/x.json"]
        assert [e["path"] for e in doc["acceptance"]] == ["projects/tiny/physics/x_acceptance.json"]
        assert [e["path"] for e in doc["options"]] == ["projects/tiny/physics/options/x.toml"]
    finally:
        svc.close()
