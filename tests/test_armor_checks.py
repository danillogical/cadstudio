import pytest

from cadkit.checks import run_checks
from conftest import box, by_name, part
from projects.armor import PROJECT

OUTSIDE_X = 168 + 30


def far_box():
    return box(OUTSIDE_X, OUTSIDE_X + 20, 100, 120, 0, 20)


def run(shape, p, **kw):
    return by_name(run_checks("t", part(shape, **kw), p, PROJECT))


def test_clean_part_passes(p):
    r = run(far_box(), p)
    for n in ("valid_solid", "watertight", "bed_fit", "lid_interference",
              "screen_clear", "min_wall"):
        assert r[n].status == "pass", (n, r[n])
    assert r["lid_min_gap"].status != "fail"


def test_lid_intrusion_fails(p):
    r = run(box(167, 187, 100, 120, 0, 20), p)
    assert r["lid_interference"].status == "fail"
    assert r["lid_min_gap"].status == "fail"


def test_gap_below_threshold(p):
    r = run(box(168.2, 188.2, 100, 120, 0, 20), p)
    assert r["lid_interference"].status == "pass"
    assert r["lid_min_gap"].status == "fail"
    assert r["lid_min_gap"].value == pytest.approx(0.2, abs=1e-3)


def test_gap_adequate(p):
    r = run(box(169, 189, 100, 120, 0, 20), p)
    assert r["lid_interference"].status == "pass"
    assert r["lid_min_gap"].status != "fail"


def test_gap_threshold_follows_clearance(p):
    # need = 0.5*clearance: 1.0 mm gap fails once clearance is 2.5 (need 1.25).
    r = run(box(169, 189, 100, 120, 0, 20), p.override({"fit.slide_clearance": 2.5}))
    assert r["lid_min_gap"].status == "fail"


def test_check_lid_false_skips(p):
    # Part intrudes into the lid, but lid checks are documented as skipped.
    r = run(box(167, 187, 100, 120, 0, 20), p, check_lid=False)
    assert "lid_interference" not in r and "lid_min_gap" not in r
    assert "screen_clear" in r


def test_screen_intrusion(p):
    shape = box(-10, 10, 100, 120, 12, 20)
    assert run(shape, p)["screen_clear"].status == "fail"
    r = run(shape, p, check_screen=False)
    assert "screen_clear" not in r


def test_screen_clear_beside_screen(p):
    # Same z, but outside the 310.5 mm wide screen footprint.
    assert run(box(160, 180, 100, 120, 12, 20), p, check_lid=False)["screen_clear"].status == "pass"


def test_custom_lid_envelope_used(p):
    shape = box(OUTSIDE_X, OUTSIDE_X + 20, 100, 120, 0, 20)
    # Params envelope does not touch this part; custom envelope swallows it.
    env = box(OUTSIDE_X - 5, OUTSIDE_X + 30, 90, 130, -5, 30)
    r = run(shape, p, lid_envelope=env)
    assert r["lid_interference"].status == "fail"


def test_custom_lid_envelope_replaces_default(p):
    # Part sits inside the default lid envelope but far from the custom one.
    shape = box(-10, 10, 100, 120, 3, 9)
    assert run(shape, p)["lid_interference"].status == "fail"
    env = box(1000, 1010, 0, 10, 0, 10)
    assert run(shape, p, lid_envelope=env)["lid_interference"].status == "pass"
