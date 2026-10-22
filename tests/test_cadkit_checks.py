import math
import re

import pytest
from build123d import Box, Compound, Location, Pos

from cadkit.checks import run_checks
from conftest import MINZ, box, by_name, part
from projects.armor import PROJECT

OUTSIDE_X = 168 + 30


def far_box():
    return box(OUTSIDE_X, OUTSIDE_X + 20, 100, 120, 0, 20)


def run(shape, p, **kw):
    return by_name(run_checks("t", part(shape, **kw), p, PROJECT))


def test_statuses_valid(p):
    for r in run_checks("t", part(far_box()), p, PROJECT):
        assert r.status in {"pass", "fail", "warn", "info"}


def test_bed_fit_too_long(p):
    shape = box(-185, 185, 0, 10, 0, 10)
    assert run(shape, p, check_lid=False)["bed_fit"].status == "fail"


def test_bed_fit_ok_350(p):
    shape = box(-175, 175, 0, 10, 0, 10)
    assert run(shape, p, check_lid=False)["bed_fit"].status == "pass"


def test_bed_fit_not_on_bed(p):
    shape = box(300, 320, 0, 10, 5, 15)
    assert run(shape, p, check_lid=False)["bed_fit"].status == "fail"


def test_bed_fit_print_location_fixes_pose(p):
    shape = box(300, 320, 0, 10, 5, 15)
    r = run(shape, p, check_lid=False, print_location=Location((0, 0, -5)))
    assert r["bed_fit"].status == "pass"


def test_min_wall_thin_plate_fails(p):
    r = run(box(200, 260, 0, 60, 0, 1.6), p, check_lid=False)
    assert r["min_wall"].status == "fail"


def test_min_wall_thick_plate_passes(p):
    r = run(box(200, 260, 0, 60, 0, 3.0), p, check_lid=False)
    assert r["min_wall"].status == "pass"


def test_two_solids_fail_valid_solid(p):
    shape = Compound([box(200, 220, 0, 20, 0, 20), box(250, 270, 0, 20, 0, 20)])
    assert run(shape, p, check_lid=False)["valid_solid"].status == "fail"


def test_mass_20mm_cube(p):
    r = run(Box(20, 20, 20, align=MINZ), p, check_lid=False, check_screen=False)["mass"]
    assert r.status == "info"
    assert r.value == pytest.approx(8.0 * 1.27, rel=0.01)  # 10.16 g
    vol = float(re.search(r"([\d.]+) cm\^3", r.detail).group(1))
    assert vol == pytest.approx(8.0, rel=0.01)
    expect_m = 8000 / (math.pi * (1.75 / 2) ** 2) / 1000  # ~3.33 m
    m = float(re.search(r"([\d.]+) m filament", r.detail).group(1))
    assert m == pytest.approx(expect_m, rel=0.01)


def test_overhang_box_passes(p):
    r = run(far_box(), p)["overhangs"]
    assert r.status == "pass"
    assert r.value == pytest.approx(0.0, abs=1e-6)


def test_overhang_t_shape_warns(p):
    post = box(-5, 5, -5, 5, 0, 20)
    plate = box(-30, 30, -30, 30, 20, 25)
    shape = (post + plate)
    # Place well outside the lid; print pose already rests at z=0.
    shape = Pos(250, 100, 0) * shape
    r = run(shape, p)["overhangs"]
    assert r.status == "warn"
    assert r.value == pytest.approx(60 * 60 - 10 * 10, rel=0.10)
