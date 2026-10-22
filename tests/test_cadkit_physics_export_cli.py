"""CLI and project-hook behaviour for the scene adapter."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cadkit.params import REPO_ROOT
from cadkit.project import Project, discover


def _env():
    env = dict(os.environ)
    env["PATH"] = f"{Path.home() / '.local' / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    return env


def cad(*args, timeout=240):
    return subprocess.run([sys.executable, "-m", "cadkit.cli", *args], cwd=REPO_ROOT,
                          capture_output=True, text=True, timeout=timeout, env=_env())


def test_project_physics_defaults_to_none():
    """The dataclass defaults are None, and the armor project opts into neither hook."""
    import dataclasses

    fields = {f.name: f for f in dataclasses.fields(Project)}
    assert fields["physics"].default is None
    assert fields["physics_with_options"].default is None
    armor = discover()["armor"]
    assert armor.physics is None
    assert armor.physics_with_options is None


def test_project_physics_field_takes_model_and_params():
    """The hook signature is (model_name, params), so models cannot share one assembly."""
    calls = []

    def hook(model, params):
        calls.append((model, params))
        return None

    project = Project(name="x", params_path=Path("p"), load_params=lambda p: None,
                      models=__import__("projects.armor.models", fromlist=["x"]),
                      physics=hook)
    assert project.physics("m1", object()) is None
    assert calls[0][0] == "m1"


def test_export_unconfigured_project_is_error_not_success(tmp_path):
    r = cad("physics", "export", "armor/demo_cube", "--out", str(tmp_path))
    assert r.returncode == 3, r.stdout + r.stderr
    assert '"status": "ERROR"' in r.stdout
    assert "no physics assembly" in r.stderr
    assert "Traceback" not in r.stderr
    assert not (tmp_path / "scene.xml").exists()


def test_export_unknown_model_is_error(tmp_path):
    r = cad("physics", "export", "no/such_model", "--out", str(tmp_path))
    assert r.returncode == 3, r.stdout + r.stderr
    assert '"status": "ERROR"' in r.stdout


def test_fixture_export_writes_scene_and_assets(tmp_path):
    r = cad("physics", "fixture", "--out", str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert '"status": "PASS"' in r.stdout
    assert (tmp_path / "scene.xml").is_file()
    assets = sorted((tmp_path / "assets").glob("*.stl"))
    assert len(assets) == 3, assets
    text = (tmp_path / "scene.xml").read_text(encoding="utf-8")
    assert '<mesh name="link_ab__arm"' in text
    assert 'contype="0" conaffinity="0"' in text


def test_fixture_export_writes_report_json(tmp_path):
    """The provenance artifact must exist, be strict JSON, and carry the scene identity."""
    r = cad("physics", "fixture", "--out", str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    path = tmp_path / "report.json"
    assert path.is_file()
    assert "wrote report:" in r.stdout
    payload = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject)
    assert payload["scene_hash"]
    assert payload["mujoco_version"]
    assert payload["n_bodies"] == 4
    assert set(payload["assets"]) == {
        "assets/link_ab__arm.stl", "assets/link_ab__tab.stl", "assets/post_free__post.stl"}
    assert len(payload["bodies"]) == 2
    assert payload["solver"]["integrator"] == "RK4"


def _reject(value):
    raise AssertionError(f"non-strict JSON constant {value}")


def test_fixture_export_is_deterministic(tmp_path):
    a = cad("physics", "fixture", "--out", str(tmp_path / "a"))
    b = cad("physics", "fixture", "--out", str(tmp_path / "b"))
    assert a.returncode == b.returncode == 0
    assert (tmp_path / "a" / "scene.xml").read_bytes() == (
        tmp_path / "b" / "scene.xml").read_bytes()
    hash_a = json.loads([ln for ln in a.stdout.splitlines() if ln.startswith("{")][0])["detail"]
    hash_b = json.loads([ln for ln in b.stdout.splitlines() if ln.startswith("{")][0])["detail"]
    assert hash_a == hash_b


def test_export_without_extra_is_actionable(tmp_path):
    """With MuJoCo unimportable, export must be ERROR/3 with a fix, not a traceback."""
    code = """
import sys, builtins
_real = builtins.__import__
def _blocked(name, *a, **k):
    if name == "mujoco" or name.startswith("mujoco."):
        raise ModuleNotFoundError("No module named 'mujoco'")
    return _real(name, *a, **k)
builtins.__import__ = _blocked
sys.argv = ["cad"] + %r
from cadkit.cli import main
main()
""" % (["physics", "fixture", "--out", str(tmp_path)],)
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True,
                       text=True, timeout=240, env=_env())
    assert r.returncode == 3, r.stdout + r.stderr
    assert "uv sync --extra physics" in r.stderr
    assert '"status": "ERROR"' in r.stdout
    assert "Traceback" not in r.stderr


def test_cad_commands_still_work_without_mujoco(tmp_path):
    code = """
import sys, builtins
_real = builtins.__import__
def _blocked(name, *a, **k):
    if name == "mujoco" or name.startswith("mujoco."):
        raise ModuleNotFoundError("No module named 'mujoco'")
    return _real(name, *a, **k)
builtins.__import__ = _blocked
sys.argv = ["cad", "check", "armor/demo_cube", "--out", %r]
from cadkit.cli import main
main()
""" % (str(tmp_path),)
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True,
                       text=True, timeout=240, env=_env())
    assert r.returncode == 0, r.stdout + r.stderr
    assert (tmp_path / "report.json").is_file()
