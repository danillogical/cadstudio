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
def box_runs(tmp_path_factory):
    first = tmp_path_factory.mktemp("scene_box_a")
    second = tmp_path_factory.mktemp("scene_box_b")
    return (_run_scene("starter/box", first), first,
            _run_scene("starter/box", second), second)


@pytest.fixture(scope="module")
def hinge_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("scene_hinge")
    return _run_scene("starter/hinge", out), out


def _scene(out: Path) -> dict:
    return json.loads((out / "scene.json").read_text())


def _params(spec: str):
    project, _ = resolve(spec)
    return project, project.load_params(project.params_path)


@pytest.mark.parametrize("spec", ["starter/box", "starter/hinge"])
def test_scene_json_contract(spec, box_runs, hinge_run):
    doc = box_runs[0] if spec.endswith("box") else hinge_run[0]
    out = box_runs[1] if spec.endswith("box") else hinge_run[1]
    scene = _scene(out)

    assert scene["schemaVersion"] == 1
    assert scene["units"] == "mm"
    assert scene["project"] == "starter"
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


@pytest.mark.parametrize("spec", ["starter/box", "starter/hinge"])
def test_every_part_has_glb(spec, box_runs, hinge_run):
    out = box_runs[1] if spec.endswith("box") else hinge_run[1]
    scene = _scene(out)
    project, p = _params(spec)
    expected = list(load_model(project, spec.split("/")[1]).build(p))
    assert [part["id"] for part in scene["parts"]] == expected
    if spec.endswith("hinge"):
        assert len(scene["parts"]) == 2
    for part in scene["parts"]:
        path = out / part["mesh"]
        assert path.is_file(), part["mesh"]
        assert path.read_bytes()[:4] == b"glTF"


@pytest.mark.parametrize("spec", ["starter/box", "starter/hinge"])
def test_glb_bounds_match_bbox(spec, box_runs, hinge_run):
    out = box_runs[1] if spec.endswith("box") else hinge_run[1]
    scene = _scene(out)
    for part in scene["parts"]:
        mesh = trimesh.load(out / part["mesh"], force="mesh")
        bb = part["bbox"]
        for axis in range(3):
            assert abs(mesh.bounds[0][axis] - bb["min"][axis]) <= TOL_MM, (part["id"], "min", axis)
            assert abs(mesh.bounds[1][axis] - bb["max"][axis]) <= TOL_MM, (part["id"], "max", axis)

    if spec.endswith("box"):
        # Independent of the mesh: the tray is the box envelope in assembly coords, resting on z=0.
        _, p = _params(spec)
        part = scene["parts"][0]
        size = [part["bbox"]["max"][i] - part["bbox"]["min"][i] for i in range(3)]
        want = (p.box.w, p.box.d, p.box.h)
        assert all(abs(got - exp) <= TOL_MM for got, exp in zip(size, want)), (size, want)
        assert abs(part["bbox"]["min"][2]) <= TOL_MM


def test_assembly_not_print_pose(hinge_run):
    _, out = hinge_run
    scene = _scene(out)
    leaf_b = next(part for part in scene["parts"] if part["id"] == "leaf_b")
    pose = leaf_b["printPose"]
    assert pose[3] == [0.0, 0.0, 0.0, 1.0]
    assert pose != [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0],
                    [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]

    project, p = _params("starter/hinge")
    mp = load_model(project, "hinge").build(p)["leaf_b"]
    bb = mp.shape.bounding_box()
    mesh = trimesh.load(out / leaf_b["mesh"], force="mesh")
    for axis, (lo, hi) in enumerate(((bb.min.X, bb.max.X), (bb.min.Y, bb.max.Y), (bb.min.Z, bb.max.Z))):
        assert abs(mesh.bounds[0][axis] - lo) <= TOL_MM
        assert abs(mesh.bounds[1][axis] - hi) <= TOL_MM

    posed = posed_shape(mp).bounding_box()
    assert abs(posed.min.Z - bb.min.Z) > TOL_MM or abs(posed.max.Z - bb.max.Z) > TOL_MM


def test_rerun_byte_identical(box_runs):
    first, second = box_runs[1], box_runs[3]
    a = re.sub(rb'"builtAt": "[^"]*"', b'"builtAt": ""', (first / "scene.json").read_bytes())
    b = re.sub(rb'"builtAt": "[^"]*"', b'"builtAt": ""', (second / "scene.json").read_bytes())
    assert a == b


def test_overrides_recorded(tmp_path):
    r = cad("gui", "scene", "starter/box", "--json", "--set", "box.w=150.0",
            "--out", str(tmp_path))
    assert r.returncode == 0, r.stderr
    scene = _scene(tmp_path)
    assert scene["provenance"]["overrides"] == {"box.w": 150.0}
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
    r = cad("gui", "scene", "starter/box", "--json", "--set", "nope.key=1",
            "--out", str(out))
    assert r.returncode == 1
    doc = json.loads(r.stdout)
    assert "unknown parameter" in doc["error"]
    assert not (out / "scene.json").exists()
