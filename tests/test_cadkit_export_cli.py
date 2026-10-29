import json
import subprocess
from pathlib import Path

import pytest
import trimesh
from build123d import Location

from cadkit.export import export_part
from cadkit.params import REPO_ROOT
from conftest import box, part

ROOT = REPO_ROOT


def test_export_part(tmp_path):
    shape = box(300, 320, 50, 90, 5, 30)  # 20 x 40 x 25 = 20000 mm^3
    mp = part(shape, print_location=Location((-300, -50, -5)))
    paths = export_part("thing", mp, tmp_path)
    assert set(paths) == {"step", "stl", "3mf"}
    for ext, pth in paths.items():
        assert pth.exists() and pth.stat().st_size > 0, ext
        assert pth.name == f"thing.{ext}"
    mesh = trimesh.load(paths["stl"])
    assert mesh.bounds[0][2] == pytest.approx(0.0, abs=1e-3)
    assert mesh.volume == pytest.approx(20000.0, rel=0.01)
    assert mesh.volume == pytest.approx(shape.volume, rel=0.01)


def cad(*args):
    return subprocess.run(["uv", "run", "cad", *args], cwd=ROOT, capture_output=True,
                          text=True, timeout=120)


def test_cli_list():
    r = cad("list")
    assert r.returncode == 0, r.stderr
    assert {"starter/box", "starter/hinge"} <= set(r.stdout.split())


def test_cli_build_check(tmp_path):
    r = cad("build", "box", "--check", "--out", str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    rep = json.loads((tmp_path / "report.json").read_text())
    assert "tray" in rep
    assert all(c["status"] != "fail" for c in rep["tray"])
    for f in ("tray.step", "tray.stl", "tray.3mf", "assembly.step"):
        assert (tmp_path / f).exists(), f


def test_cli_unknown_model(tmp_path):
    r = cad("build", "nope", "--out", str(tmp_path))
    assert r.returncode != 0


def test_cli_unknown_set_key(tmp_path):
    r = cad("build", "box", "--set", "fit.bogus=1", "--out", str(tmp_path))
    assert r.returncode != 0


def test_cli_set_reflected_in_report(tmp_path):
    r = cad("build", "hinge", "--check", "--set", "fit.clearance=0.5",
            "--out", str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    rep = json.loads((tmp_path / "report.json").read_text())
    gap = {c["name"]: c for c in rep["leaf_a"]}["clearance"]
    assert "need >= 0.250" in gap["detail"]  # 0.5 * 0.5


def test_cli_check_command_failing_exit(tmp_path):
    # A huge min_wall makes the tray's walls too thin -> exit 1.
    r = cad("check", "box", "--set", "structure.min_wall=100", "--out", str(tmp_path))
    assert r.returncode == 1


def test_render_model_smoke(tmp_path, p):
    from cadkit.render import render_model
    from projects.starter import PROJECT
    from projects.starter.models import box as box_model
    parts = box_model.build(p)
    written = render_model(parts, p, tmp_path, PROJECT)
    iso = tmp_path / "renders" / "iso.png"
    assert written["iso.png"] == iso
    assert iso.exists() and iso.stat().st_size > 0
