"""Pocky syringe3: rear ramp and home window, packet end play, protrusion, and the backstop clips (stop push-back, limit arm spread).

Written from the requirements, with the solids probed (``is_inside`` and boolean overlap), not read
back from the layout numbers.

Run with: ``.venv/bin/python -m pytest tests/test_pocky_syringe3_retention.py -q``.
"""
from __future__ import annotations

import pytest
from build123d import Pos, Vector

from cadkit.checks import overlap_volume, run_checks
from cadkit.project import discover
from projects.pocky.geometry.syringe import syringe_layout as syringe_layout_ref
from projects.pocky.geometry.syringe3 import clip_solids, slider_solid, syringe_layout
from projects.pocky.models import syringe3 as syringe3_model
from projects.pocky.params import load_params

BED_MM = 360.0
STROKES = (0.0, 0.25, 0.5, 0.75, 1.0)
SPREAD_LIMIT = 0.6


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
def clips(lay):
    return clip_solids(lay)


@pytest.fixture(scope="module")
def sliders(lay):
    return {f: slider_solid(lay, lay.travel(f)) for f in STROKES}


@pytest.fixture(scope="module")
def results(p, parts):
    project = discover()["pocky"]
    return {name: run_checks(name, part, p, project) for name, part in parts.items()}


def _in(shape, x, y, z) -> bool:
    return bool(shape.is_inside(Vector(x, y, z)))


def _edge(shape, axis, lo, hi, at, tol=1e-3):
    """Coordinate along ``axis`` where ``shape`` switches state between ``lo`` and ``hi`` (bisection)."""
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


def _edge_abs_y(shape, sign, lo, hi, x, z, tol=1e-3):
    """|y| where ``shape`` switches state between |y| = lo and hi, on the side ``sign``."""
    s_lo = _in(shape, x, sign * lo, z)
    assert _in(shape, x, sign * hi, z) != s_lo, f"no state change between |y|={lo} and {hi}"
    while hi - lo > tol:
        mid = (lo + hi) / 2.0
        if _in(shape, x, sign * mid, z) == s_lo:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _ramp_face_x(housing, lay, z):
    return _edge(housing, 0, lay.bore_x0 - 0.5, lay.ramp_toe_x + 1.0, (0, 0.0, z))


def _rear_inner_x(housing, lay):
    # Well above the ramp, where only the rear wall is left.
    return _edge(housing, 0, lay.rear_x + 0.5, lay.bore_x0 + 3.0, (0, 0.0, lay.top - 1.0))


def _exit_inner_x(housing, lay):
    return _edge(housing, 0, lay.bore_x1 - 3.0, lay.exit_x - 0.5, (0, 0.0, lay.gap + 1.0))


def _plate_face_x(slider, lay, z, travel=0.0):
    x0 = lay.plate_rest_x + travel
    return _edge(slider, 0, x0 - 3.0, x0 + 3.0, (0, 0.0, z))


def _clip_plate_y(lay):
    return 0.5 * (lay.clip_in_y + lay.clip_out_y)


def _clip_mid_x(clip, lay, sign):
    box = clip.bounding_box()
    return 0.5 * (box.min.X + box.max.X)


def _clip_front_x(clip, lay, sign, z=2.0):
    box = clip.bounding_box()
    return _edge(clip, 0, box.min.X + 1.0, box.max.X + 2.0, (0, sign * _clip_plate_y(lay), z))


def _leg_rear_x(slider, lay, sign, z=2.0):
    # Outside the arm, beside the clip plate, the slider is only its leg: its rear face is the first inside point.
    return _edge(slider, 0, 70.0, 99.0, (0, sign * _clip_plate_y(lay), z))


# --------------------------------------------------------------- 1 rear ramp and home window
def test_ramp_is_at_least_7_5_mm_deep(lay, housing):
    # Deepest at the toe's land, probed on y = 0.
    toe = _ramp_face_x(housing, lay, lay.ramp_land_top - 0.5)
    assert toe - _rear_inner_x(housing, lay) >= 7.5


def test_pusher_at_home_is_3_mm_behind_the_ramp_toe(lay, housing, sliders):
    toe = _ramp_face_x(housing, lay, lay.ramp_land_top - 0.5)
    face = _plate_face_x(sliders[0.0], lay, lay.plate_z1 - 0.3)
    assert toe - face >= 3.0


def test_pusher_at_home_is_3_mm_in_front_of_the_rear_wall(lay, housing, sliders):
    face = _plate_face_x(sliders[0.0], lay, lay.plate_z1 - 0.3)
    assert face - _rear_inner_x(housing, lay) >= 3.0


def test_ramp_face_slopes_forward_going_down(lay, housing):
    xs = [_ramp_face_x(housing, lay, z) for z in
          (lay.ramp_land_top + 1.0, (lay.ramp_land_top + lay.ramp_top) / 2.0, lay.ramp_top - 1.0)]
    assert xs[0] > xs[1] > xs[2]


# --------------------------------------------------------------- 2 packet end play
def test_packet_two_has_2_5_mm_of_end_play(p, lay, housing):
    h = p.packet.height
    exit_inner = _exit_inner_x(housing, lay)
    # Across packet 2's band (h .. 2h), the ramp face is narrowest at its lowest.
    for z in (h + 0.3, 1.5 * h, 2.0 * h - 0.3):
        free = exit_inner - _ramp_face_x(housing, lay, z)
        assert free - p.packet.length >= 2.5, (z, free)


# --------------------------------------------------------------- 3 protrusion
def test_bottom_packet_protrudes_75_mm_at_full_stroke(p, lay, housing):
    slider_full = slider_solid(lay, lay.stroke)
    lead = _plate_face_x(slider_full, lay, lay.plate_z1 - 0.3, travel=lay.stroke) + p.packet.length
    exit_face = _edge(housing, 0, lay.bore_x1 + 0.5, lay.shelf_x + 5.0, (0, 0.0, lay.gap + 1.0))
    assert lead - exit_face >= 75.0 - 0.05


# --------------------------------------------------------------- 4 backstop clips
def test_clips_are_separate_parts(parts):
    assert {"clip_n", "clip_s"} <= set(parts)
    for name in ("clip_n", "clip_s"):
        assert overlap_volume(parts[name].shape, parts["housing"].shape) < 1e-6, name
        assert len(parts[name].shape.solids()) == 1, name


@pytest.mark.parametrize("fraction", STROKES)
@pytest.mark.parametrize("name", ("clip_n", "clip_s"))
def test_clip_never_touches_the_slider(clips, sliders, name, fraction):
    assert overlap_volume(clips[name], sliders[fraction]) < 1e-6


@pytest.mark.parametrize("fraction", STROKES)
@pytest.mark.parametrize("name,sign", (("clip_n", 1.0), ("clip_s", -1.0)))
def test_clip_stops_an_arm_spread_of_0_6_mm(clips, sliders, name, sign, fraction):
    spread = Pos(0.0, sign * SPREAD_LIMIT, 0.0) * sliders[fraction]
    assert overlap_volume(clips[name], spread) > 1e-6


@pytest.mark.parametrize("name,sign", (("clip_n", 1.0), ("clip_s", -1.0)))
def test_unhooking_needs_more_travel_than_the_clip_allows(lay, housing, clips, sliders, name, sign):
    # Clip clearance = arm outer face to clip plate inner face, probed mid-clip at plate height.
    x, z = _clip_mid_x(clips[name], lay, sign), 4.0
    arm_out = _edge_abs_y(sliders[0.0], sign, lay.side_y + 1.0, lay.side_y + 5.3, x, z)
    clip_in = _edge_abs_y(clips[name], sign, lay.side_y + 5.3, lay.clip_out_y - 0.5, x, z)
    clearance = clip_in - arm_out
    assert 0.0 < clearance <= SPREAD_LIMIT
    # Engagement = how far the rail stands proud of the wall less the arm's sliding gap to the wall (both probed).
    arm_in = _edge_abs_y(sliders[0.0], sign, lay.side_y + 0.01, lay.side_y + 1.0, x, z)
    rail_tip = _edge_abs_y(housing, sign, lay.side_y + 0.05, lay.side_y + 4.0, 0.0, -1.5)
    engagement = (rail_tip - lay.side_y) - (arm_in - lay.side_y)
    assert engagement > clearance
    assert lay.rail_engagement > clearance


# --------------------------------------------------------------- 4b backstop
def test_slider_at_home_clears_both_clips(clips, sliders):
    for name in ("clip_n", "clip_s"):
        assert overlap_volume(clips[name], sliders[0.0]) < 1e-6, name


@pytest.mark.parametrize("name", ("clip_n", "clip_s"))
def test_slider_cannot_move_back_more_than_half_a_mm(clips, sliders, name):
    behind = Pos(-0.5, 0.0, 0.0) * sliders[0.0]
    assert overlap_volume(clips[name], behind) > 1e-6


def test_pusher_stays_in_the_rear_slot_when_stopped_by_the_clips(lay, housing, sliders):
    behind = Pos(-0.5, 0.0, 0.0) * sliders[0.0]
    face = _plate_face_x(behind, lay, lay.plate_z1 - 0.3, travel=-0.5)
    outer = _edge(housing, 0, lay.rear_x - 3.0, lay.rear_x + 0.5, (0, 0.0, lay.top - 1.0))
    assert face > outer


@pytest.mark.parametrize("name,sign", (("clip_n", 1.0), ("clip_s", -1.0)))
def test_clip_sits_just_behind_its_slider_leg(lay, clips, sliders, name, sign):
    gap = _leg_rear_x(sliders[0.0], lay, sign) - _clip_front_x(clips[name], lay, sign)
    assert 0.0 <= gap <= 0.2, gap


@pytest.mark.parametrize("name", ("clip_n", "clip_s"))
def test_clip_prints_flat(results, name):
    by_name = {r.name: r for r in results[name]}
    assert not [r for r in results[name] if r.status == "fail"], results[name]
    assert by_name["overhangs"].status == "pass", by_name["overhangs"]


# --------------------------------------------------------------- 5 all parts
def test_ten_parts_fit_the_bed(parts):
    assert len(parts) == 10
    for name, part in parts.items():
        box = (part.print_location * part.shape).bounding_box()
        assert max(box.size.X, box.size.Y, box.size.Z) <= BED_MM, (name, box.size)


def test_no_part_has_a_failing_check(results):
    failures = [(n, r) for n, rs in results.items() for r in rs if r.status == "fail"]
    assert not failures, failures


# --------------------------------------------------------------- 6 reference prototype
def test_reference_syringe_is_unchanged(p):
    ref = syringe_layout_ref(p)
    assert ref.bore_x0 == pytest.approx(-85.0)
    assert ref.bore_x1 == pytest.approx(85.0)
    assert ref.stroke == pytest.approx(50.5, abs=0.01)
