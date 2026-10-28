"""Pocky syringe3 dispenser geometry, written from the bench-test requirements.

Requirements (from the printed ``pocky/syringe``): the exit window passes one packet but not two,
the presented packet sticks well out, the rear-wall ramp drops the next packet in front of the
pusher, the pusher cannot slide under a wrapped packet, the side wedges steer an off-centre
packet back, and the return spring stays easy to pull. Every number is a requirement or a
packet dimension; the solids are probed (``is_inside``), not read back from the layout.

Run with: ``.venv/bin/python -m pytest tests/test_pocky_syringe3_geometry.py -q``.
"""
from __future__ import annotations

import math

import pytest
from build123d import Vector

from cadkit.checks import run_checks
from cadkit.project import all_models, discover
from projects.pocky.geometry.syringe import syringe_layout as syringe_layout_ref
from projects.pocky.geometry.syringe3 import SPRING_PRELOAD, syringe_layout, syringe_solids
from projects.pocky.models import syringe3 as syringe3_model
from projects.pocky.params import load_params

BED_MM = 360.0
PARTS = ("housing", "slider", "spring", "handle", "leg_1", "leg_2", "leg_3", "leg_4", "clip_n", "clip_s")


@pytest.fixture(scope="module")
def p():
    return load_params()


@pytest.fixture(scope="module")
def lay(p):
    return syringe_layout(p)


@pytest.fixture(scope="module")
def parts(p):
    return syringe3_model.build(p)


@pytest.fixture(scope="module")
def housing(parts):
    return parts["housing"].shape


@pytest.fixture(scope="module")
def slider_home(p):
    return syringe_solids(p, 0.0)["slider"]


@pytest.fixture(scope="module")
def slider_full(p):
    return syringe_solids(p, 1.0)["slider"]


def _in(shape, x, y, z) -> bool:
    return bool(shape.is_inside(Vector(x, y, z)))


def _edge(shape, axis: int, lo: float, hi: float, at: tuple[float, float, float], tol: float = 1e-3) -> float:
    """Coordinate along ``axis`` where ``shape`` switches state between ``lo`` and ``hi`` (bisection).

    ``at`` holds the other two coordinates (the entry for ``axis`` is ignored).
    """
    def inside(v):
        c = list(at)
        c[axis] = v
        return _in(shape, *c)

    s_lo = inside(lo)
    assert inside(hi) != s_lo, f"no state change between {lo} and {hi} at {at} on axis {axis}"
    while hi - lo > tol:
        mid = (lo + hi) / 2.0
        if inside(mid) == s_lo:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _plate_face_x(slider, lay, z, y=0.0, travel=0.0):
    """Plate face x at height z: slider solid behind it, air ahead (window around the home face + travel)."""
    x0 = lay.plate_rest_x + travel
    return _edge(slider, 0, x0 - 3.0, x0 + 3.0, (0, y, z))


def _plate_top_z(slider, lay):
    return _edge(slider, 2, lay.plate_z1 - 1.5, lay.plate_z1 + 1.5, (lay.plate_rest_x - 3.0, 0.0, 0))


# --------------------------------------------------------------- discovery and parts
def test_cad_discovery_lists_syringe3():
    assert "pocky/syringe3" in all_models()


def test_build_returns_the_ten_parts(parts):
    assert set(parts) == set(PARTS)


# --------------------------------------------------------------- 1 exit gap
def test_exit_gap_passes_one_packet_and_rejects_two(p, lay):
    h = p.packet.height
    assert h == pytest.approx(5.2)
    assert h + 2.0 <= lay.gap <= 2.0 * h - 2.0


def test_exit_wall_lower_edge_sits_at_the_gap(p, lay, housing):
    # Mid exit wall, on the centre line: open window below the gap, wall just above it.
    x = (lay.bore_x1 + lay.exit_x) / 2.0
    assert not _in(housing, x, 0.0, lay.gap - 0.1)
    assert _in(housing, x, 0.0, lay.gap + 0.1)
    assert _edge(housing, 2, lay.gap - 0.5, lay.gap + 0.5, (x, 0.0, 0)) == pytest.approx(lay.gap, abs=0.01)


def test_exit_wall_covers_two_mm_of_packet_two(p, lay):
    assert 2.0 * p.packet.height - lay.gap >= 2.0


# --------------------------------------------------------------- 2 protrusion and bed fit
def test_full_stroke_presents_packet_one_far_past_exit_and_shelf(p, lay, housing, slider_full):
    # Leading edge of the bottom packet = pusher face at full stroke + packet length, from the solids.
    face = _plate_face_x(slider_full, lay, lay.plate_z1 - 0.3, travel=lay.stroke)
    lead = face + p.packet.length
    exit_x = _edge(housing, 0, lay.bore_x1 + 0.5, lay.shelf_x + 5.0, (0, 0.0, lay.gap + 1.0))
    # (the exit wall's front face is where the wall above the gap ends)
    assert exit_x == pytest.approx(lay.exit_x, abs=0.01)
    assert lead - exit_x >= 75.0 - 0.05
    assert lead - lay.shelf_x >= 45.0


def test_every_part_fits_the_bed(parts):
    for name, part in parts.items():
        assert part.print_location is not None, name
        box = (part.print_location * part.shape).bounding_box()
        assert box.size.X <= BED_MM and box.size.Y <= BED_MM and box.size.Z <= BED_MM, (name, box.size)


# --------------------------------------------------------------- 3 rear-wall ramp
def _ramp_face_x(housing, lay, z, y=0.0):
    return _edge(housing, 0, lay.bore_x0 - 0.5, lay.ramp_toe_x + 1.0, (0, y, z))


def test_ramp_is_solid_behind_its_face_and_open_in_front(lay, housing):
    z = (lay.ramp_land_top + lay.ramp_top) / 2.0
    for y in (0.0, 15.0, -15.0):
        x = _ramp_face_x(housing, lay, z, y)
        assert _in(housing, x - 0.2, y, z)
        assert not _in(housing, x + 0.2, y, z)


def test_ramp_toe_is_not_behind_the_pusher_at_home(lay, housing, slider_home):
    toe_x = _ramp_face_x(housing, lay, lay.ramp_land_top - 0.5)
    face_x = _plate_face_x(slider_home, lay, lay.plate_z1 - 0.3)
    assert toe_x >= face_x


def test_ramp_face_slopes_forward_going_down(lay, housing):
    toe_x = _ramp_face_x(housing, lay, lay.ramp_land_top - 0.5)
    top_x = _ramp_face_x(housing, lay, lay.ramp_top - 0.5)
    mid_x = _ramp_face_x(housing, lay, (lay.ramp_land_top + lay.ramp_top) / 2.0)
    assert toe_x > mid_x > top_x


def test_ramp_underside_clears_the_plate_top(lay, housing, slider_home):
    plate_top = _plate_top_z(slider_home, lay)
    x = lay.ramp_toe_x - 1.0  # under the ramp, in the slot
    underside = _edge(housing, 2, plate_top + 0.05, lay.ramp_land_top, (x, 0.0, 0))
    assert underside - plate_top > 0.2


# --------------------------------------------------------------- 4 pusher
def test_plate_floor_gap_is_at_most_a_fifth_of_a_mm(lay, slider_home):
    # Plate underside at y=15 (off the narrow keel); the housing floor top is z=0.
    x = lay.plate_rest_x - 3.0
    bottom = _edge(slider_home, 2, -0.5, 1.5, (x, 15.0, 0))
    assert bottom <= 0.2 + 1e-3


def test_plate_top_stays_under_packet_two(p, lay, slider_home):
    h = p.packet.height
    top = _plate_top_z(slider_home, lay)
    assert h - 0.35 - 1e-3 <= top < h


def test_plate_face_has_an_undercut(lay, slider_home):
    upper = _plate_face_x(slider_home, lay, lay.plate_z1 - 0.3)
    lower = _plate_face_x(slider_home, lay, lay.plate_z0 + 1.8)
    assert upper > lower + 0.1


# --------------------------------------------------------------- 5 wedge lead-in
def _wedge_x(lay):
    return lay.bore_x1 + 2.0  # inside the wedge region, ahead of the funnel ramp


def test_wedge_top_slopes_without_a_ledge(p, lay, housing):
    x = _wedge_x(lay)
    # Guide face top = highest z with a vertical inner face; sample strictly between it and the wedge top.
    foot, top = lay.wedge_foot_z, lay.wedge_top
    levels = [foot + (top - foot) * f for f in (0.15, 0.35, 0.55, 0.75, 0.9)]
    edges = [_edge(housing, 1, 0.0, lay.side_y, (x, 0, z)) for z in levels]
    for e in edges:
        assert e < lay.bore_y  # the slope is inside the bore
    for (z0, e0), (z1, e1) in zip(zip(levels, edges), zip(levels[1:], edges[1:])):
        assert e1 > e0, "lead-in must open outward as it rises (no overhang or flat step)"
        angle = math.degrees(math.atan2(z1 - z0, e1 - e0))
        assert angle >= 55.0 - 0.5, angle  # 0.5 deg for bisection and sample spacing
        assert e1 - e0 <= (z1 - z0) / math.tan(math.radians(55.0)) + 0.01


def test_window_still_guides_packet_one(p, lay, housing):
    x = _wedge_x(lay)
    right = _edge(housing, 1, 0.0, lay.side_y, (x, 0, 0.5))
    left = _edge(housing, 1, 0.0, -lay.side_y, (x, 0, 0.5))
    assert right - left <= p.packet.width + 1.0


# --------------------------------------------------------------- 6 spring
def test_spring_force_bounds(p, lay):
    from projects.pocky.physics.syringe3_assembly import SPRING_STIFFNESS_N_M

    # Same model as the assembly's joint: F = -k (q - reference), reference = -preload, q = travel.
    preload_m = SPRING_PRELOAD / 1000.0
    home = SPRING_STIFFNESS_N_M * preload_m
    peak = SPRING_STIFFNESS_N_M * (lay.stroke / 1000.0 + preload_m)
    assert home >= 1.0, home
    assert peak <= 30.0, peak


# --------------------------------------------------------------- 7 checks
def test_no_check_fails_on_any_part(p, parts):
    project = discover()["pocky"]
    failures = []
    for name, part in parts.items():
        for r in run_checks(name, part, p, project):
            if r.status == "fail":
                failures.append((name, r))
    assert not failures, failures


# --------------------------------------------------------------- 8 reference prototype untouched
def test_reference_syringe_is_unchanged(p):
    ref = syringe_layout_ref(p)
    assert ref.gap == pytest.approx(5.75)
    assert ref.stroke == pytest.approx(50.5, abs=0.01)
