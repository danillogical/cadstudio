"""``cad gui scene``: the scene contract, assembly coordinates, and deterministic JSON (packet G2a)."""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import trimesh

from cadkit.mesh import posed_shape
from cadkit.params import REPO_ROOT
from cadkit.project import load_model, resolve

ROOT = REPO_ROOT
TOL_MM = 0.05


def _env() -> dict:
    env = {k: v for k, v in os.environ.items() if k != "POCKY_POSE"}
    env["PATH"] = f"{Path.home() / '.local' / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    return env


def cad(*args, timeout=300):
    return subprocess.run([sys.executable, "-m", "cadkit.cli", *args], cwd=ROOT,
                          capture_output=True, text=True, timeout=timeout, env=_env())


def _run_scene(spec: str, out: Path) -> dict:
    r = cad("gui", "scene", spec, "--json", "--out", str(out))
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout)  # the whole stdout is one document
    assert doc["exit_code"] == 0
    return doc


@pytest.fixture(scope="module")
def dummy_runs(tmp_path_factory):
    first = tmp_path_factory.mktemp("scene_dummy_a")
    second = tmp_path_factory.mktemp("scene_dummy_b")
    return (_run_scene("pocky/packet_dummy", first), first,
            _run_scene("pocky/packet_dummy", second), second)


@pytest.fixture(scope="module")
def syringe_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("scene_syringe")
    return _run_scene("pocky/syringe", out), out


def _scene(out: Path) -> dict:
    return json.loads((out / "scene.json").read_text())


def _params(spec: str):
    project, _ = resolve(spec)
    return project, project.load_params(project.params_path)


@pytest.mark.parametrize("spec", ["pocky/packet_dummy", "pocky/syringe"])
def test_scene_json_contract(spec, dummy_runs, syringe_run):
    doc = dummy_runs[0] if spec.endswith("packet_dummy") else syringe_run[0]
    out = dummy_runs[1] if spec.endswith("packet_dummy") else syringe_run[1]
    scene = _scene(out)

    assert scene["schemaVersion"] == 1
    assert scene["units"] == "mm"
    assert scene["project"] == "pocky"
    assert scene["model"] == spec.split("/")[1]

    prov = scene["provenance"]
    for key in ("commit", "dirty", "paramsSha256", "overrides", "builtAt"):
        assert key in prov
    project, _ = _params(spec)
    assert prov["paramsSha256"] == hashlib.sha256(project.params_path.read_bytes()).hexdigest()
    assert prov["overrides"] == {}
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", prov["builtAt"])

    assert doc["model"] == spec
    assert Path(doc["scene"]) == out / "scene.json"


@pytest.mark.parametrize("spec", ["pocky/packet_dummy", "pocky/syringe"])
def test_every_part_has_glb(spec, dummy_runs, syringe_run, monkeypatch):
    out = dummy_runs[1] if spec.endswith("packet_dummy") else syringe_run[1]
    scene = _scene(out)
    monkeypatch.delenv("POCKY_POSE", raising=False)
    project, p = _params(spec)
    expected = list(load_model(project, spec.split("/")[1]).build(p))
    assert [part["id"] for part in scene["parts"]] == expected
    if spec.endswith("syringe"):
        assert len(scene["parts"]) == 8
    for part in scene["parts"]:
        path = out / part["mesh"]
        assert path.is_file(), part["mesh"]
        assert path.read_bytes()[:4] == b"glTF"


@pytest.mark.parametrize("spec", ["pocky/packet_dummy", "pocky/syringe"])
def test_glb_bounds_match_bbox(spec, dummy_runs, syringe_run):
    out = dummy_runs[1] if spec.endswith("packet_dummy") else syringe_run[1]
    scene = _scene(out)
    for part in scene["parts"]:
        mesh = trimesh.load(out / part["mesh"], force="mesh")
        bb = part["bbox"]
        for axis in range(3):
            assert abs(mesh.bounds[0][axis] - bb["min"][axis]) <= TOL_MM, (part["id"], "min", axis)
            assert abs(mesh.bounds[1][axis] - bb["max"][axis]) <= TOL_MM, (part["id"], "max", axis)

    if spec.endswith("packet_dummy"):
        # Independent of the mesh: the dummy's box is the packet envelope in assembly coords.
        _, p = _params(spec)
        part = scene["parts"][0]
        size = [part["bbox"]["max"][i] - part["bbox"]["min"][i] for i in range(3)]
        want = (p.packet.length, p.packet.width, p.packet.height)
        assert all(abs(got - exp) <= TOL_MM for got, exp in zip(size, want)), (size, want)
        assert abs(part["bbox"]["min"][2]) <= TOL_MM


def test_assembly_not_print_pose(syringe_run, monkeypatch):
    _, out = syringe_run
    scene = _scene(out)
    slider = next(part for part in scene["parts"] if part["id"] == "slider")
    pose = slider["printPose"]
    assert pose[3] == [0.0, 0.0, 0.0, 1.0]
    assert pose != [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0],
                    [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]

    monkeypatch.delenv("POCKY_POSE", raising=False)
    project, p = _params("pocky/syringe")
    mp = load_model(project, "syringe").build(p)["slider"]
    bb = mp.shape.bounding_box()
    mesh = trimesh.load(out / slider["mesh"], force="mesh")
    for axis, (lo, hi) in enumerate(((bb.min.X, bb.max.X), (bb.min.Y, bb.max.Y), (bb.min.Z, bb.max.Z))):
        assert abs(mesh.bounds[0][axis] - lo) <= TOL_MM
        assert abs(mesh.bounds[1][axis] - hi) <= TOL_MM

    posed = posed_shape(mp).bounding_box()
    assert abs(posed.min.Z - bb.min.Z) > TOL_MM or abs(posed.max.Z - bb.max.Z) > TOL_MM


def test_rerun_byte_identical(dummy_runs):
    first, second = dummy_runs[1], dummy_runs[3]
    a = re.sub(rb'"builtAt": "[^"]*"', b'"builtAt": ""', (first / "scene.json").read_bytes())
    b = re.sub(rb'"builtAt": "[^"]*"', b'"builtAt": ""', (second / "scene.json").read_bytes())
    assert a == b


def test_overrides_recorded(tmp_path, monkeypatch):
    monkeypatch.delenv("POCKY_POSE", raising=False)
    r = cad("gui", "scene", "pocky/packet_dummy", "--json", "--set", "packet.length=150.0",
            "--out", str(tmp_path))
    assert r.returncode == 0, r.stderr
    scene = _scene(tmp_path)
    assert scene["provenance"]["overrides"] == {"packet.length": 150.0}
    part = scene["parts"][0]
    assert abs((part["bbox"]["max"][0] - part["bbox"]["min"][0]) - 150.0) <= TOL_MM


def test_unknown_model_json_error(tmp_path):
    out = tmp_path / "scene"
    r = cad("gui", "scene", "nope", "--json", "--out", str(out))
    assert r.returncode != 0
    doc = json.loads(r.stdout)
    assert "error" in doc and doc["exit_code"] == 1
    assert not (out / "scene.json").exists()


def test_unknown_parameter_json_error(tmp_path):
    out = tmp_path / "scene"
    r = cad("gui", "scene", "pocky/packet_dummy", "--json", "--set", "nope.key=1",
            "--out", str(out))
    assert r.returncode == 1
    doc = json.loads(r.stdout)
    assert "unknown parameter" in doc["error"]
    assert not (out / "scene.json").exists()
