"""Service builds run in a fresh process, so source edits show up; ``cad build --scene``."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from gui_tiny_repo import PROJECT, Sse, TinyService, child_env, make_repo

MODEL = f"{PROJECT}/box"


@pytest.fixture(scope="module")
def tiny(tmp_path_factory):
    root = tmp_path_factory.mktemp("fresh")
    repo = make_repo(root, size=10.0)
    work = root / "work"
    work.mkdir()
    svc = TinyService(repo, work, stub=False)
    try:
        yield svc
    finally:
        svc.close()


def _build_and_wait(svc) -> dict:
    status, doc, _ = svc.req("POST", f"/v1/models/{MODEL}/build")
    assert status == 202, doc
    job = svc.wait_job(doc["job"]["id"])
    assert job["status"] == "succeeded", job
    return job


def _x_extent(svc) -> float:
    status, doc, _ = svc.req("GET", f"/v1/models/{MODEL}/scene")
    assert status == 200, doc
    bbox = doc["scene"]["parts"][0]["bbox"]
    return bbox["max"][0] - bbox["min"][0]


def test_source_edit_between_service_builds_changes_the_served_scene(tiny):
    sse = Sse(tiny)
    try:
        _build_and_wait(tiny)
        assert _x_extent(tiny) == pytest.approx(10.0, abs=1e-3)
        time.sleep(1.5)
        scenes = [a for a in sse.artifacts("scene") if a["model"] == MODEL]
        assert len(scenes) == 1, scenes  # one scene event per service build, not two

        path = tiny.repo / "projects" / PROJECT / "models" / "box.py"
        path.write_text(path.read_text().replace("SIZE = 10.0", "SIZE = 25.0"))

        _build_and_wait(tiny)
        assert _x_extent(tiny) == pytest.approx(25.0, abs=1e-3)
        time.sleep(1.5)
        scenes = [a for a in sse.artifacts("scene") if a["model"] == MODEL]
        assert len(scenes) == 2, scenes
    finally:
        sse.close()


def _cad_build(repo: Path, out: Path, *flags: str):
    return subprocess.run(
        [sys.executable, "-m", "cadkit.cli", "build", MODEL, "--json", "--out", str(out), *flags],
        cwd=repo, capture_output=True, text=True, timeout=300, env=child_env())


def test_cad_build_scene_flag_writes_scene_and_reports_path(tmp_path_factory):
    root = tmp_path_factory.mktemp("cli_scene")
    repo = make_repo(root)
    with_scene = root / "with_scene"
    r = _cad_build(repo, with_scene, "--scene")
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout)  # the whole stdout is one document
    assert doc["scene"] == str(with_scene / "scene" / "scene.json")
    assert (with_scene / "scene" / "scene.json").is_file()

    without = root / "without_scene"
    r = _cad_build(repo, without)
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout)
    assert "scene" in doc and doc["scene"] is None
    assert not (without / "scene").exists()
