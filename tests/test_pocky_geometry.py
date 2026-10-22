import itertools
import json
import subprocess

import pytest

from cadkit.checks import overlap_volume, run_checks
from cadkit.params import REPO_ROOT
from cadkit.project import discover, load_model
from conftest import by_name
from projects.pocky.geometry.packet import packet, packet_stack
from projects.pocky.params import load_params

ROOT = REPO_ROOT


@pytest.fixture(scope="module")
def pp():
    return load_params()


def cad(*args):
    return subprocess.run(["uv", "run", "cad", *args], cwd=ROOT, capture_output=True,
                          text=True, timeout=120)


def test_packet_bbox(pp):
    s = packet(pp)
    bb = s.bounding_box()
    assert len(s.solids()) == 1
    assert (bb.size.X, bb.size.Y, bb.size.Z) == pytest.approx((165.0, 55.0, 5.2), abs=1e-6)
    assert (bb.min.X, bb.max.X) == pytest.approx((-82.5, 82.5), abs=1e-6)
    assert (bb.min.Y, bb.max.Y) == pytest.approx((-27.5, 27.5), abs=1e-6)
    assert (bb.min.Z, bb.max.Z) == pytest.approx((0.0, 5.2), abs=1e-6)
    assert s.volume == pytest.approx(165.0 * 55.0 * 5.2, rel=1e-6)


def test_packet_follows_override(pp):
    q = pp.override({"packet.length": 150.0, "packet.width": 40.0, "packet.height": 3.0})
    bb = packet(q).bounding_box()
    assert (bb.size.X, bb.size.Y, bb.size.Z) == pytest.approx((150.0, 40.0, 3.0), abs=1e-6)
    assert (bb.min.Z, bb.max.Z) == pytest.approx((0.0, 3.0), abs=1e-6)


@pytest.mark.parametrize("n", [1, 2, 10, 25])
def test_packet_stack_no_gap(pp, n):
    stack = packet_stack(pp, n)
    h = pp.packet.height
    assert len(stack) == n
    for i, s in enumerate(stack):
        bb = s.bounding_box()
        assert bb.min.Z == pytest.approx(i * h, abs=1e-6)
        assert bb.max.Z == pytest.approx(i * h + h, abs=1e-6)
    assert max(s.bounding_box().max.Z for s in stack) == pytest.approx(n * h, abs=1e-6)
    for a, b in itertools.combinations(stack, 2):
        assert overlap_volume(a, b) <= 1e-3


def test_packet_stack_top_values(pp):
    top = lambda n: max(s.bounding_box().max.Z for s in packet_stack(pp, n))
    assert top(10) == pytest.approx(52.0, abs=1e-6)
    assert top(25) == pytest.approx(130.0, abs=1e-6)


@pytest.mark.parametrize("n", [1, 2, 10, 25])
def test_packet_stack_with_gap(pp, n):
    gap = pp.separator.gap - pp.packet.height  # nonzero
    h = pp.packet.height
    stack = packet_stack(pp, n, gap=gap)
    assert len(stack) == n
    for i, s in enumerate(stack):
        bb = s.bounding_box()
        assert bb.min.Z == pytest.approx(i * (h + gap), abs=1e-6)
        assert bb.max.Z == pytest.approx(i * (h + gap) + h, abs=1e-6)
    for a, b in itertools.combinations(stack, 2):
        assert overlap_volume(a, b) <= 1e-3


@pytest.mark.parametrize("n,gap", [(0, 0.0), (-1, 0.0), (3, -0.1)])
def test_packet_stack_invalid(pp, n, gap):
    with pytest.raises(ValueError):
        packet_stack(pp, n, gap=gap)


def test_dummy_model_discovered():
    assert "pocky" in discover()


def _dummy(pp):
    project = discover()["pocky"]
    return project, load_model(project, "packet_dummy").build(pp)


def test_dummy_build_parts(pp):
    _, parts = _dummy(pp)
    assert set(parts) == {"dummy"}
    bb = parts["dummy"].shape.bounding_box()
    assert (bb.size.X, bb.size.Y, bb.size.Z) == pytest.approx((165.0, 55.0, 5.2), abs=1e-6)


def test_dummy_checks(pp):
    project, parts = _dummy(pp)
    res = by_name(run_checks("dummy", parts["dummy"], pp, project))
    for name in ("valid_solid", "watertight", "bed_fit"):
        assert res[name].status == "pass", res[name]
    assert all(r.status != "fail" for r in res.values())


def test_cli_list():
    r = cad("list")
    assert r.returncode == 0, r.stderr
    assert "pocky/packet_dummy" in r.stdout.split()


def test_cli_check_set_reflected(tmp_path):
    r = cad("check", "pocky/packet_dummy", "--set", "packet.length=150", "--out", str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    rep = json.loads((tmp_path / "report.json").read_text())
    bed = {c["name"]: c for c in rep["dummy"]}["bed_fit"]
    assert bed["status"] == "pass"
    assert "150" in bed["detail"]
