"""Geometric invariant tests for the armor models.

Expectations come from the design spec and ``projects/armor/params.toml`` (via ``projects.armor.params``), probed with
thin boxes/cylinders in assembly coordinates. Nothing here reads the model's private ``Frame`` numbers;
the only model helper used is the public ``screw_positions``.
"""
from __future__ import annotations

import functools

import pytest
from build123d import Align, Compound, Cylinder, Pos

from cadkit.checks import run_checks
from cadkit.project import list_models, load_model
from conftest import box
from projects.armor import PROJECT
from projects.armor.models._armor_base import screw_positions
from projects.armor.params import load_params, lid_envelope, screen_prism

ARMOR = [n for n in list_models(PROJECT) if n.startswith("armor_")]
P = load_params()
TOL = 0.05
# Y bands for side/rear probes: near the hinge, mid-lid and near the top, relative to lid.h and clear of screw axes.
YS = [(20, 30), (round(P.lid.h * 0.4), round(P.lid.h * 0.4) + 10), (round(P.lid.h) - 20, round(P.lid.h) - 14)]
FULL = 0.99  # fraction of a probe that must be solid to count as "hits solid"
EMPTY = 1e-3  # mm^3 of overlap tolerated for "empty"


# ---------------------------------------------------------------- helpers

@functools.lru_cache(maxsize=None)
def build(name: str, overrides: tuple = ()):
    """Build a model once per (name, overrides); cached for the whole session."""
    return load_model(PROJECT, name).build(P.override(dict(overrides)))


@functools.lru_cache(maxsize=None)
def checks(name: str):
    return {k: run_checks(k, mp, P, PROJECT) for k, mp in build(name).items()}


def vol(shape, probe) -> float:
    """Volume of shape ∩ probe (intersect may return None, a Shape or a ShapeList)."""
    common = shape.intersect(probe)
    if common is None:
        return 0.0
    if isinstance(common, (list, tuple)):
        return float(sum(c.volume for c in common))
    return float(common.volume)


def isect(shape, probe) -> Compound:
    """shape ∩ probe as a single Compound (intersect may return None, a Shape or a ShapeList)."""
    common = shape.intersect(probe)
    if common is None:
        return Compound([])
    if isinstance(common, (list, tuple)):
        return Compound(list(common))
    return common


def frac(shape, probe) -> float:
    return vol(shape, probe) / probe.volume


def assert_empty(shape, probe, what=""):
    v = vol(shape, probe)
    assert v <= EMPTY, f"{what}: expected empty probe, overlap {v:.4g} mm^3"


def assert_solid(shape, probe, what=""):
    f = frac(shape, probe)
    assert f >= FULL, f"{what}: expected solid probe, only {f:.3f} of it is solid"


def cyl(x, y, r, z0, z1):
    return Pos(x, y, z0) * Cylinder(r, z1 - z0, align=(Align.CENTER, Align.CENTER, Align.MIN))


def ring(x, y, r0, r1, z0, z1):
    return cyl(x, y, r1, z0, z1) - cyl(x, y, r0, z0 - 1, z1 + 1)


def parts_of(name):
    m = build(name)
    return m["rear"].shape, m["front"].shape


def solids_sorted_x(shape):
    return sorted(shape.solids(), key=lambda s: s.center().X)


HW = P.lid.w / 2
SC = P.fit.slide_clearance
Z0, Z1 = P.lid_z0, P.lid_z1
FRONT_Z = Z1 + P.fit.front_gap  # spec: lid front face + front_gap
TOTAL_T = FRONT_Z + P.structure.front_th


# ---------------------------------------------------------------- 0. spec self-consistency

def test_derived_z_matches_spec():
    assert Z0 == pytest.approx(P.structure.back_th + P.fit.rear_gap)
    assert P.front_z == pytest.approx(FRONT_Z)
    assert P.total_t == pytest.approx(TOTAL_T)


# ---------------------------------------------------------------- 1. parts and checks

@pytest.mark.parametrize("name", ARMOR)
def test_has_rear_and_front(name):
    assert {"rear", "front"} <= set(build(name))


@pytest.mark.parametrize("name", ARMOR)
def test_run_checks_no_fail(name):
    bad = [(part, r.name, r.detail) for part, rs in checks(name).items() for r in rs if r.status == "fail"]
    assert not bad, f"failing checks: {bad}"


# ---------------------------------------------------------------- 2. clearances

@pytest.mark.parametrize("name", ARMOR)
@pytest.mark.parametrize("y0,y1", YS)
@pytest.mark.parametrize("side", [-1, 1])
def test_side_clearance(name, y0, y1, side):
    rear, front = parts_of(name)

    def xs(a, b):
        return tuple(sorted((side * a, side * b)))

    gap = box(*xs(HW, HW + SC - TOL), y0, y1, Z0, Z1)
    for nm, s in (("rear", rear), ("front", front)):
        assert_empty(s, gap, f"{nm} side gap probe (gap-0.05) side={side} y={y0}-{y1}")
    wall = box(*xs(HW + SC + TOL + 0.01, HW + SC + 0.3), y0, y1, Z0, Z1)
    assert_solid(rear, wall, f"rear side wall just beyond slide_clearance side={side} y={y0}-{y1}")


@pytest.mark.parametrize("name", ARMOR)
@pytest.mark.parametrize("y0,y1", YS)
def test_rear_clearance(name, y0, y1):
    rear, front = parts_of(name)
    gap = box(-HW, HW, y0, y1, Z0 - P.fit.rear_gap + TOL, Z0)
    for nm, s in (("rear", rear), ("front", front)):
        assert_empty(s, gap, f"{nm} rear gap probe (gap-0.05) y={y0}-{y1}")
    plate = box(-HW, HW, y0, y1, Z0 - P.fit.rear_gap - 0.3, Z0 - P.fit.rear_gap - TOL - 0.01)
    assert_solid(rear, plate, f"back plate just behind rear_gap y={y0}-{y1}")


@pytest.mark.parametrize("name", ARMOR)
def test_front_clearance(name):
    rear, front = parts_of(name)
    hs, vs = P.screen.w / 2, P.screen.bottom + P.screen.h
    # border regions outside the screen opening, inside the lid outline
    regions = {
        "right border": (hs + 3, HW - 3, 100, 110),
        "left border": (-(HW - 3), -(hs + 3), 100, 110),
        "top border": (40, 100, vs + 1.5, vs + 4),
        "bottom border": (-100, 100, P.fit.bottom_hinge_relief + 2, P.screen.bottom - 2),
    }
    for label, (x0, x1, y0, y1) in regions.items():
        x0, x1 = sorted((x0, x1))
        gap = box(x0, x1, y0, y1, Z1, Z1 + P.fit.front_gap - TOL)
        for nm, s in (("rear", rear), ("front", front)):
            assert_empty(s, gap, f"{nm} front gap probe (gap-0.05), {label}")
        plate = box(x0, x1, y0, y1, FRONT_Z + TOL + 0.01, FRONT_Z + 0.3)
        assert_solid(front, plate, f"bezel plate just past front_gap, {label}")


@pytest.mark.parametrize("name", ARMOR)
@pytest.mark.parametrize("x0,x1", [(-100, -20), (20, 100)])
def test_top_clearance(name, x0, x1):
    rear, front = parts_of(name)
    gap = box(x0, x1, P.lid.h, P.lid.h + SC - TOL, Z0, Z1)
    for nm, s in (("rear", rear), ("front", front)):
        assert_empty(s, gap, f"{nm} top gap probe (slide_clearance-0.05)")
    cap = box(x0, x1, P.lid.h + SC + TOL + 0.01, P.lid.h + SC + 0.3, Z0, Z1)
    assert_solid(rear, cap, "rear cap just above slide_clearance")


# ---------------------------------------------------------------- 3. hinge edge open

@pytest.mark.parametrize("name", ARMOR)
def test_hinge_edge_open(name):
    rear, front = parts_of(name)
    relief = P.fit.bottom_hinge_relief
    probe = box(-HW, HW, -50, relief - 0.01, Z0, Z1)
    for nm, s in (("rear", rear), ("front", front)):
        assert_empty(s, probe, f"{nm} below bottom_hinge_relief")
        assert s.bounding_box().min.Y >= relief - TOL, f"{nm} extends below hinge relief"


@pytest.mark.parametrize("name", ARMOR)
def test_lid_slides_out(name):
    rear, front = parts_of(name)
    env = lid_envelope(P)
    step = 10.0
    n = int(P.lid.h // step) + 1
    for i in range(n + 1):
        d = min(i * step, P.lid.h)
        moved = Pos(0, -d, 0) * env
        for nm, s in (("rear", rear), ("front", front)):
            assert vol(s, moved) <= EMPTY, f"lid blocked by {nm} after sliding -{d} in Y"


# ---------------------------------------------------------------- 4. top cap closed

@pytest.mark.parametrize("name", ARMOR)
def test_top_cap_closed(name):
    rear, _ = parts_of(name)
    probe = box(-(HW + SC), HW + SC, P.lid.h + SC + 0.1, P.lid.h + P.fit.top_extension - 0.1,
                P.structure.back_th, FRONT_Z)
    assert_solid(rear, probe, "top cap across cavity in X and Z")


# ---------------------------------------------------------------- 5. screen opening and camera notch

@pytest.mark.parametrize("name", ARMOR)
def test_screen_opening_empty(name):
    _, front = parts_of(name)
    assert vol(front, screen_prism(P)) <= EMPTY


@pytest.mark.parametrize("name", ARMOR)
@pytest.mark.parametrize("edge", ["left", "right", "bottom", "top"])
def test_screen_opening_not_oversized(name, edge):
    _, front = parts_of(name)
    s = P.screen
    x0, x1 = -s.w / 2, s.w / 2
    y0, y1 = s.bottom, s.bottom + s.h
    m = 10.0  # stay clear of the rounded corners
    cam_x = P.camera.w / 2 + 1  # and of the camera notch
    d0, d1 = 0.2, 0.4  # 0.3 mm outside the edge (+-0.1)
    zz = (FRONT_Z, TOTAL_T)
    if edge == "left":
        probes = [box(x0 - d1, x0 - d0, y0 + m, y1 - m, *zz)]
    elif edge == "right":
        probes = [box(x1 + d0, x1 + d1, y0 + m, y1 - m, *zz)]
    elif edge == "bottom":
        probes = [box(x0 + m, x1 - m, y0 - d1, y0 - d0, *zz)]
    else:
        probes = [box(x0 + m, -cam_x, y1 + d0, y1 + d1, *zz), box(cam_x, x1 - m, y1 + d0, y1 + d1, *zz)]
    for pr in probes:
        assert_solid(front, pr, f"bezel 0.3 mm outside screen {edge} edge")


@pytest.mark.parametrize("name", ARMOR)
def test_camera_notch(name):
    _, front = parts_of(name)
    c = P.camera
    top = P.lid.h - c.top_offset
    bot = top - c.h
    hw = c.w / 2
    zz = (FRONT_Z, TOTAL_T)
    if not c.notch:
        assert_solid(front, box(-hw, hw, bot, top, *zz), "camera covered by bezel")
        return
    assert_empty(front, box(-hw + TOL, hw - TOL, bot + TOL, top - TOL, *zz), "inside camera notch")
    for label, pr in {
        "left": box(-hw - 0.4, -hw - 0.2, bot + 1, top - 1, *zz),
        "right": box(hw + 0.2, hw + 0.4, bot + 1, top - 1, *zz),
        "above": box(-hw + 1, hw - 1, top + 0.2, top + 0.4, *zz),
        "below": box(-hw + 1, hw - 1, bot - 0.4, bot - 0.2, *zz),
    }.items():
        assert_solid(front, pr, f"bezel just outside camera notch ({label})")


# ---------------------------------------------------------------- 6. fasteners

SCREWS = screw_positions(P)


@pytest.mark.parametrize("name", ARMOR)
def test_six_screws_symmetric(name):
    assert len(SCREWS) == 6
    assert sorted((-x, y) for x, y in SCREWS) == sorted(SCREWS)


@pytest.mark.parametrize("name", ARMOR)
@pytest.mark.parametrize("x,y", SCREWS)
def test_rear_insert_bore(name, x, y):
    rear, _ = parts_of(name)
    f = P.fasteners
    r = f.insert_d / 2
    top = FRONT_Z
    bottom = top - f.insert_depth
    # bore exists, with bottom and depth as specified
    assert_empty(rear, cyl(x, y, (f.insert_d - 0.2) / 2, bottom + TOL, top - TOL), "insert bore")
    assert_solid(rear, cyl(x, y, r - 0.1, bottom - 0.4, bottom - TOL - 0.01), "material under bore bottom")
    # boss ring around the bore, over the full insert depth
    assert_solid(rear, ring(x, y, r + 0.1, r + f.boss_margin - 0.1, bottom + 0.1, top - 0.1),
                 "boss ring around insert bore")
    # bore entirely outside the lid cavity (lid inflated by slide_clearance)
    assert vol(cyl(x, y, r, bottom, top), lid_envelope(P, inflate=SC)) <= EMPTY
    # >= boss_margin of material on the cavity side and on the outer side
    cavity_edge = HW + SC
    outer_edge = rear.bounding_box().max.X
    s = 1 if x > 0 else -1
    assert abs(x) - r - cavity_edge >= f.boss_margin - 1e-6, "cavity-side material < boss_margin"
    assert outer_edge - (abs(x) + r) >= f.boss_margin - 1e-6, "outer-side material < boss_margin"
    assert s * x > 0


@pytest.mark.parametrize("name", ARMOR)
@pytest.mark.parametrize("x,y", SCREWS)
def test_front_screw_hole_and_counterbore(name, x, y):
    _, front = parts_of(name)
    f = P.fasteners
    rh, rc = f.screw_d / 2, f.counterbore_d / 2
    cb_floor = TOTAL_T - f.counterbore_depth
    assert_empty(front, cyl(x, y, rh - 0.1, FRONT_Z, TOTAL_T), "M3 clearance hole through bezel")
    assert_solid(front, ring(x, y, rh + 0.1, rh + 0.4, FRONT_Z + 0.05, cb_floor - TOL),
                 "material just outside the M3 hole below the counterbore (hole not oversized)")
    # counterbore on the visible face
    assert_empty(front, cyl(x, y, rc - 0.1, cb_floor + TOL, TOTAL_T), "counterbore")
    assert_solid(front, ring(x, y, rh + 0.1, rc - 0.1, FRONT_Z + 0.05, cb_floor - TOL), "counterbore floor")
    assert_solid(front, ring(x, y, rc + 0.1, rc + 0.4, cb_floor + 0.05, TOTAL_T - 0.05),
                 "material just outside counterbore (not oversized)")


# ---------------------------------------------------------------- 7. parametric response

def _zmin(shape):
    return shape.bounding_box().min.Z


def _cavity_depth(rear):
    """Rear shell max Z minus the back-plate top at the cavity center (no cavity-lid assumptions)."""
    col = isect(rear, box(-1, 1, 100, 102, -1, 100))
    plate_top = col.bounding_box().max.Z
    return rear.bounding_box().max.Z - plate_top


def _inner_width(rear):
    zmid = (Z0 + Z1) / 2
    row = isect(rear, box(-300, 300, 100, 101, zmid - 0.5, zmid + 0.5))
    solids = solids_sorted_x(row)
    assert len(solids) == 2, f"expected two side walls on the probe row, got {len(solids)}"
    return solids[1].bounding_box().min.X - solids[0].bounding_box().max.X


@pytest.mark.parametrize("name", ARMOR)
def test_lid_thickness_shifts_front_and_cavity(name):
    base, thick = build(name), build(name, (("lid.t", 8.0),))
    dz = _zmin(thick["front"].shape) - _zmin(base["front"].shape)
    assert dz == pytest.approx(1.0, abs=0.01), f"front z-min shift {dz}"
    dc = _cavity_depth(thick["rear"].shape) - _cavity_depth(base["rear"].shape)
    assert dc == pytest.approx(1.0, abs=0.01), f"cavity depth change {dc}"


@pytest.mark.parametrize("name", ARMOR)
def test_slide_clearance_widens_cavity(name):
    base, wide = build(name), build(name, (("fit.slide_clearance", 1.0),))
    w0, w1 = _inner_width(base["rear"].shape), _inner_width(wide["rear"].shape)
    assert w0 == pytest.approx(P.lid.w + 2 * SC, abs=0.02)
    assert w1 - w0 == pytest.approx(0.6, abs=0.02), f"cavity widened by {w1 - w0}"


# ---------------------------------------------------------------- 8. bed fit and print pose

@pytest.mark.parametrize("name", ARMOR)
@pytest.mark.parametrize("part_name", ["rear", "front"])
def test_bed_fit_print_pose(name, part_name):
    mp = build(name)[part_name]
    assert mp.print_location is not None
    bb = mp.shape.moved(mp.print_location).bounding_box()
    assert bb.min.Z == pytest.approx(0, abs=0.01)
    assert bb.size.X <= P.printer.bed_x and bb.size.Y <= P.printer.bed_y and bb.size.Z <= P.printer.bed_z


@pytest.mark.parametrize("name", ARMOR)
def test_front_visible_face_is_top(name):
    mp = build(name)["front"]
    asm = mp.shape.bounding_box()
    posed = mp.shape.moved(mp.print_location).bounding_box()
    # The inner face (assembly z = front_z) is flat on the bed; raised decoration may only grow upward.
    assert asm.min.Z == pytest.approx(FRONT_Z, abs=0.01)
    inner = isect(mp.shape, box(-300, 300, 0, 400, FRONT_Z - 0.01, FRONT_Z + 0.1))
    assert inner.moved(mp.print_location).bounding_box().min.Z == pytest.approx(0, abs=0.01)
    assert posed.size.Z == pytest.approx(asm.size.Z, abs=0.01)  # not flipped: visible side faces up


# ---------------------------------------------------------------- 9. fit_test coupons

def _coupons():
    return {k: mp for k, mp in build("fit_test").items() if k != "insert_test"}


def _coupon_params(mp):
    """(clearance, lid_t) recovered from the part's own geometry/envelope, not from names."""
    env = mp.lid_envelope.bounding_box()
    lid_t = env.size.Z
    zmid = (env.min.Z + env.max.Z) / 2
    row = isect(mp.shape, box(-300, 0, P.lid.h - 12, P.lid.h - 11, zmid - 0.5, zmid + 0.5))
    wall_inner = max(s.bounding_box().max.X for s in row.solids())
    clearance = -HW - wall_inner
    return clearance, lid_t


def test_fit_test_has_nine_coupons_and_insert_test():
    m = build("fit_test")
    assert "insert_test" in m
    assert len(_coupons()) == 9


def test_fit_test_coupon_combos():
    combos = {(round(c, 2), round(t, 2)) for c, t in map(_coupon_params, _coupons().values())}
    want = {(c, t) for c in (0.4, 0.7, 1.0) for t in (6.5, 7.0, 7.5)}
    assert combos == want


COUPON_KEYS = [f"c{round(c * 100):03d}_t{round(t * 10):02d}" for c in (0.4, 0.7, 1.0) for t in (6.5, 7.0, 7.5)]


@pytest.mark.parametrize("key", COUPON_KEYS)
def test_fit_test_coupon_matches_own_envelope(key):
    # Keys only select a coupon; its swept values are recovered geometrically and checked against the key.
    mp = build("fit_test")[key]
    clearance, lid_t = _coupon_params(mp)
    assert clearance == pytest.approx(int(key[1:4]) / 100, abs=TOL)
    assert lid_t == pytest.approx(int(key[6:]) / 10, abs=TOL)
    assert mp.lid_envelope is not None
    assert vol(mp.shape, mp.lid_envelope) <= EMPTY, "coupon interferes with its own lid envelope"
    # The spec's "0.6 mm thicker" cannot collide: fit.front_gap (0.8) absorbs it. So bracket the front
    # gap instead: a lid thicker by front_gap-0.05 still clears, one thicker by front_gap+0.1 collides.
    gap = P.fit.front_gap
    ok = P.override({"fit.slide_clearance": clearance, "lid.t": lid_t + gap - TOL})
    hit = P.override({"fit.slide_clearance": clearance, "lid.t": lid_t + gap + 0.1})
    assert vol(mp.shape, lid_envelope(ok)) <= EMPTY, "coupon front gap smaller than fit.front_gap"
    assert vol(mp.shape, lid_envelope(hit)) > EMPTY, "coupon front gap larger than fit.front_gap"
