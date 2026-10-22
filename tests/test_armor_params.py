import pytest

from projects.armor.params import lid_envelope, load_params, screen_prism


def test_defaults(p):
    assert (p.lid.w, p.lid.h, p.lid.t) == (336, 221, 7.0)
    assert p.fit.slide_clearance == 0.7
    assert p.fit.rear_gap == 0.5
    assert p.fit.front_gap == 0.8
    assert p.structure.back_th == 2.4
    assert p.structure.front_th == 2.4
    assert p.structure.min_wall == 2.4
    assert (p.printer.bed_x, p.printer.bed_y, p.printer.bed_z) == (360, 360, 360)
    assert p.material.density_g_cm3 == 1.27


def test_derived_defaults(p):
    assert p.lid_z0 == pytest.approx(2.9)
    assert p.lid_z1 == pytest.approx(9.9)
    assert p.front_z == pytest.approx(10.7)
    assert p.total_t == pytest.approx(13.1)
    assert p.cavity_w == pytest.approx(337.4)


def test_load_params_explicit_path():
    from projects.armor.params import DEFAULT_PARAMS_PATH
    assert load_params(DEFAULT_PARAMS_PATH) == load_params()


def test_derived_follow_override(p):
    q = p.override({"fit.slide_clearance": 0.4, "lid.t": 6.5})
    assert q.lid_z0 == pytest.approx(2.9)
    assert q.lid_z1 == pytest.approx(9.4)
    assert q.front_z == pytest.approx(10.2)
    assert q.total_t == pytest.approx(12.6)
    assert q.cavity_w == pytest.approx(336.8)


def _bb(s):
    return s.bounding_box()


def test_lid_envelope_bbox(p):
    bb = _bb(lid_envelope(p))
    assert (bb.min.X, bb.max.X) == (pytest.approx(-168), pytest.approx(168))
    assert (bb.min.Y, bb.max.Y) == (pytest.approx(-50), pytest.approx(221))
    assert (bb.min.Z, bb.max.Z) == (pytest.approx(2.9), pytest.approx(9.9))


def test_lid_envelope_inflate(p):
    bb = _bb(lid_envelope(p, inflate=2.0))
    assert (bb.min.X, bb.max.X) == (pytest.approx(-170), pytest.approx(170))
    assert bb.max.Y == pytest.approx(223)
    assert bb.min.Y == pytest.approx(-52)
    assert (bb.min.Z, bb.max.Z) == (pytest.approx(0.9), pytest.approx(11.9))


def test_lid_envelope_follows_override(p):
    bb = _bb(lid_envelope(p.override({"lid.w": 300, "lid.t": 5})))
    assert bb.max.X == pytest.approx(150)
    assert bb.max.Z == pytest.approx(7.9)


def test_screen_prism_bbox(p):
    bb = _bb(screen_prism(p))
    assert (bb.min.X, bb.max.X) == (pytest.approx(-155.25), pytest.approx(155.25))
    assert bb.min.Y == pytest.approx(25.0)
    assert bb.max.Y == pytest.approx(25.0 + 174.8)
    assert bb.min.Z == pytest.approx(p.lid_z1)
    assert bb.max.Z > p.total_t
