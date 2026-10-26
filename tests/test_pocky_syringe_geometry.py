"""Pocky syringe dispenser geometry: parts, print poses, separator, slot, stroke, clearance.

Written from the layout spec in ``geometry/syringe.py``, not from the solids' own answers:
the gap, slot and stroke criteria are checked against the frozen numbers (exit face x=88,
shelf end x=106, 30 mm minimum protrusion, 10 mm past the shelf) and probed on the solids.

Run with: ``uv run --frozen --extra physics pytest tests/test_pocky_syringe_geometry.py -q``.
"""
from __future__ import annotations

import pytest
from build123d import Pos, Vector

from cadkit.checks import _overhangs, overlap_volume
from cadkit.project import all_models
from projects.pocky.geometry.packet import packet as packet_solid
from projects.pocky.geometry.syringe import (
    BAR_Z1,
    PULL_DEPTH,
    TABLE_Z,
    hand_keepout,
    syringe_layout,
    syringe_solids,
    wall_shape_for,
)
from projects.pocky.models import syringe as syringe_model
from projects.pocky.params import load_params
from projects.pocky.physics.options import load_options

BED_MM = 360.0
# Frozen presentation criteria (acceptance.toml): exit face, shelf end, protrusions.
EXIT_X = 88.0
SHELF_X = 106.0
MIN_PROTRUSION = 30.0
MIN_PAST_SHELF = 10.0
OVERLAP_NOISE_MM3 = 1.0e-3
LEG_NAMES = ("leg_1", "leg_2", "leg_3", "leg_4")
ALL_PARTS = ("housing", "slider", "spring", "handle", *LEG_NAMES)
# Pre-change measurement: the solid-plinth housing (before the slab and pop-in legs) was 723.68 cm^3.
OLD_PLINTH_HOUSING_CM3 = 723.68


@pytest.fixture(scope="module")
def p():
    return load_params()


@pytest.fixture(scope="module")
def lay(p):
    return syringe_layout(p)


@pytest.fixture(scope="module")
def parts(p):
    return syringe_model.build(p)


def _inside(shape, x, y, z) -> bool:
    return bool(shape.is_inside(Vector(x, y, z)))


# --------------------------------------------------------------- discovery and parts
def test_cad_discovery_lists_the_syringe_model():
    assert "pocky/syringe" in all_models()


def test_build_returns_exactly_housing_slider_spring_handle_and_four_legs(parts):
    # The pull handle is a separate clip-on part and the housing stands on four pop-in legs;
    # no lip, body, chassis or peg parts.
    assert set(parts) == {"housing", "slider", "spring", "handle", "leg_1", "leg_2", "leg_3", "leg_4"}
    for banned in ("lip", "body", "chassis", "peg"):
        assert banned not in parts


@pytest.mark.parametrize("name", ALL_PARTS)
def test_each_part_is_one_valid_solid_resting_on_the_bed(parts, name):
    part = parts[name]
    assert part.shape.is_valid
    assert len(part.shape.solids()) == 1
    assert part.print_location is not None
    posed = part.print_location * part.shape
    assert posed.is_valid
    assert len(posed.solids()) == 1
    box = posed.bounding_box()
    assert box.min.Z == pytest.approx(0.0, abs=1e-6)
    assert box.size.X <= BED_MM and box.size.Y <= BED_MM and box.size.Z <= BED_MM


# --------------------------------------------------------------- separator
def test_separator_gap_is_the_param_and_the_blade_underside(p, lay, parts):
    assert p.separator.gap == pytest.approx(5.75)
    assert lay.gap == pytest.approx(p.separator.gap)
    lay = syringe_layout(p, "blade")
    housing = syringe_solids(p, 0.0, separator="blade")["housing"]
    # Probe mid-blade, away from its rounded lower edge and the exit wall.
    x = lay.blade_x0 + 5.0
    assert _inside(housing, x, 0.0, lay.gap + 0.1)       # blade material just above the gap
    assert not _inside(housing, x, 0.0, lay.gap - 0.1)   # open bore just below it
    # The blade is part of the one-piece housing: fused to the exit wall at its front end.
    assert len(housing.solids()) == 1
    assert _inside(housing, lay.bore_x1 + 0.1, 0.0, lay.gap + 0.1)


# --------------------------------------------------------------- rear slot
def test_rear_slot_passes_the_plate_but_not_a_second_packet(p, lay, parts):
    k = p.packet
    # The pusher plate fits the slot with clearance above and below.
    assert 0.0 < lay.plate_z0 and lay.plate_z1 < lay.slot_h
    assert lay.plate_w < lay.slot_w
    # The slot top is below one packet's thickness, so a packet cannot enter it, and
    # below the separator gap, so it is also under the stack-rejecting clearance.
    assert lay.slot_h < k.height
    assert lay.slot_h < lay.gap
    housing = parts["housing"].shape
    x = lay.rear_x + 1.0  # inside the rear wall
    assert not _inside(housing, x, 0.0, lay.slot_h - 0.1)  # slot is open
    assert _inside(housing, x, 0.0, lay.slot_h + 0.1)      # wall above the slot
    assert _inside(housing, x, 20.0, -0.5)                 # floor slab below it, off the spring channel
    assert _inside(housing, x, lay.slot_w / 2.0 + 0.1, 2.0)  # wall beside it


# --------------------------------------------------------------- stroke
def test_stroke_presents_packet_one_past_the_exit_and_the_shelf(p, lay):
    assert lay.exit_x == pytest.approx(EXIT_X)
    assert lay.shelf_x == pytest.approx(SHELF_X)
    lead_full = lay.plate_rest_x + lay.stroke + p.packet.length
    assert lead_full == pytest.approx(lay.lead_full)
    assert lead_full - EXIT_X >= MIN_PROTRUSION
    assert lead_full - SHELF_X >= MIN_PAST_SHELF
    assert lay.protrusion_full >= MIN_PROTRUSION
    assert lay.past_shelf_full >= MIN_PAST_SHELF
    assert lay.stroke >= lay.stroke_min > 0.0


def test_slider_plate_face_is_where_the_stroke_says(p, lay):
    # The plate face is the trailing edge of the pushed packet, so the leading edge is
    # the plate face plus the packet length. Probe the slider solid at both ends.
    for fraction in (0.0, 1.0):
        slider = syringe_solids(p, fraction)["slider"]
        face = lay.plate_rest_x + lay.travel(fraction)
        mid_z = (lay.plate_z0 + lay.plate_z1) / 2.0
        assert _inside(slider, face - 0.1, 0.0, mid_z), fraction
        assert not _inside(slider, face + 0.1, 0.0, mid_z), fraction


# --------------------------------------------------------------- clearance
@pytest.mark.parametrize("separator", ["blade", "wedge"])
@pytest.mark.parametrize("fraction", [0.0, 0.5, 1.0])
def test_exact_solid_overlap_is_zero(p, fraction, separator):
    solids = syringe_solids(p, fraction, separator=separator)
    assert set(solids) == set(ALL_PARTS)
    for i, a in enumerate(ALL_PARTS):
        for b in ALL_PARTS[i + 1:]:
            common = solids[a].intersect(solids[b])
            volume = common.volume if common is not None else 0.0
            assert volume <= OVERLAP_NOISE_MM3, (a, b, fraction, separator, volume)


# --------------------------------------------------------------- pop-in legs
def test_housing_floor_is_a_slab_with_nothing_solid_below_it(p, lay, parts):
    housing = parts["housing"].shape
    assert lay.slab_z0 == pytest.approx(-13.0)
    assert housing.bounding_box().min.Z == pytest.approx(-13.0, abs=1e-6)
    # Slab material just inside its underside and just under the floor top, off the channel.
    assert _inside(housing, 0.0, 20.0, -12.9)
    assert _inside(housing, 0.0, 20.0, -0.1)
    # No plinth: the region below the slab between the legs is empty, down to the table.
    for x in (-40.0, 0.0, 40.0, 80.0):
        for y in (-30.0, -10.0, 0.0, 10.0, 30.0):
            for z in (-13.5, -20.0, -30.0, -40.0, -50.0):
                assert not _inside(housing, x, y, z), (x, y, z)


def test_four_legs_reach_the_table_plane(p, lay, parts):
    assert len(lay.leg_xy) == 4
    for i, name in enumerate(LEG_NAMES):
        box = parts[name].shape.bounding_box()
        assert box.min.Z == pytest.approx(TABLE_Z, abs=1e-6), name
        x, y = lay.leg_xy[i]
        assert box.min.X < x < box.max.X and box.min.Y < y < box.max.Y, name
        # Column top ends under the slab, so the leg never reaches into the floor above its socket.
        assert box.min.Z < lay.slab_z0 < box.max.Z, name


@pytest.mark.parametrize("name", LEG_NAMES)
def test_leg_is_one_valid_solid_and_prints_foot_down_without_support(parts, name):
    leg = parts[name]
    assert leg.shape.is_valid and len(leg.shape.solids()) == 1
    assert leg.print_location is not None
    posed = leg.print_location * leg.shape
    assert posed.is_valid and len(posed.solids()) == 1
    assert posed.bounding_box().min.Z == pytest.approx(0.0, abs=1e-6)
    result = _overhangs(leg)
    assert result.status == "pass", result.detail
    assert result.value == pytest.approx(0.0, abs=1e-6)


def test_legs_seat_in_their_sockets_with_a_small_gap_and_no_overlap(p):
    solids = syringe_solids(p, 0.0)
    housing = solids["housing"]
    for name in LEG_NAMES:
        assert overlap_volume(housing, solids[name]) <= OVERLAP_NOISE_MM3, name
        gap = housing.distance_to(solids[name])
        # Seated: touching nothing, but within a fraction of a millimetre (0.05 mm designed).
        assert 0.0 < gap <= 0.2, (name, gap)


@pytest.mark.parametrize("fraction", [0.0, 1.0])
def test_legs_are_clear_of_the_hand_keepout(p, fraction):
    solids = syringe_solids(p, fraction)
    keepout = hand_keepout(p)
    for name in LEG_NAMES:
        assert overlap_volume(solids[name], keepout) <= OVERLAP_NOISE_MM3, name


def test_housing_with_legs_is_under_half_the_old_solid_plinth_volume(p):
    solids = syringe_solids(p, 0.0)
    cm3 = (solids["housing"].volume + sum(solids[n].volume for n in LEG_NAMES)) / 1000.0
    assert cm3 < 0.5 * OLD_PLINTH_HOUSING_CM3, cm3


# --------------------------------------------------------------- wedge separator
@pytest.fixture(scope="module")
def wedge_lay(p):
    return syringe_layout(p, "wedge")


@pytest.fixture(scope="module")
def wedge_housing(p):
    return syringe_solids(p, 0.0, separator="wedge")["housing"]


def test_separator_default_is_the_wedge_and_blade_is_selectable(p, lay, parts, wedge_housing):
    assert lay.separator == "wedge"
    assert syringe_layout(p, "wedge").separator == "wedge"
    assert syringe_layout(p, "blade").separator == "blade"
    default = syringe_solids(p, 0.0)["housing"]
    explicit = syringe_solids(p, 0.0, separator="wedge")["housing"]
    blade = syringe_solids(p, 0.0, separator="blade")["housing"]
    assert default.volume == pytest.approx(explicit.volume, rel=1e-12)
    assert parts["housing"].shape.volume == pytest.approx(default.volume, rel=1e-12)
    assert wedge_housing.volume == pytest.approx(default.volume, rel=1e-12)
    assert blade.volume != pytest.approx(default.volume, rel=1e-3)
    # The blade bites over the stack; the default (wedge) housing has no such material.
    x = (lay.blade_x0 + lay.bore_x1) / 2.0  # over the stack, short of the exit wall
    assert x < lay.bore_x1
    assert _inside(blade, x, 0.0, lay.gap + 0.1)
    assert not _inside(default, x, 0.0, lay.gap + 0.1)


def test_unknown_separator_is_rejected(p):
    with pytest.raises(ValueError):
        syringe_layout(p, "comb")
    with pytest.raises(ValueError):
        syringe_solids(p, 0.0, separator="comb")


def test_wedge_housing_has_nothing_over_the_stack_behind_the_exit_wall(wedge_housing):
    xs = [70.0 + 2.0 * i for i in range(8)]       # 70 .. 84
    ys = [-26.0 + 4.0 * i for i in range(14)]     # -26 .. 26
    zs = [6.0 + 2.0 * i for i in range(8)]        # 6 .. 20
    for x in xs:
        for y in ys:
            for z in zs:
                assert not _inside(wedge_housing, x, y, z), (x, y, z)


def test_wedge_exit_window_height_is_the_gap(p, wedge_lay, wedge_housing):
    assert p.separator.gap == pytest.approx(5.75)
    x = (wedge_lay.bore_x1 + wedge_lay.exit_x) / 2.0  # inside the exit wall
    assert not _inside(wedge_housing, x, 0.0, 5.75 - 0.1)  # window open up to the gap
    assert not _inside(wedge_housing, x, 0.0, 0.5)
    assert _inside(wedge_housing, x, 0.0, 5.75 + 0.1)      # exit wall's lower edge sets the gap
    assert _inside(wedge_housing, x, 0.0, 12.0)


def test_wedge_funnel_narrows_the_bore_at_the_exit(p, wedge_lay, wedge_housing):
    width = 2.0 * wedge_lay.wedge_y
    assert width == pytest.approx(55.6, abs=0.05)
    assert width > p.packet.width  # the packet still passes
    x = wedge_lay.exit_x - 1.0
    z = 2.0  # under the wedge top, above the floor
    assert not _inside(wedge_housing, x, wedge_lay.wedge_y - 0.1, z)
    assert not _inside(wedge_housing, x, -(wedge_lay.wedge_y - 0.1), z)
    assert _inside(wedge_housing, x, wedge_lay.wedge_y + 0.1, z)
    assert _inside(wedge_housing, x, -(wedge_lay.wedge_y + 0.1), z)
    # Behind the ramp the bore is its full width.
    x_back = wedge_lay.wedge_x0 - 2.0
    assert not _inside(wedge_housing, x_back, wedge_lay.bore_y - 0.1, z)


def test_wedge_tops_are_below_packet_one_so_a_flat_packet_two_never_touches_them(
        p, wedge_lay, wedge_housing):
    assert wedge_lay.wedge_top < p.packet.height == pytest.approx(5.2)
    # Material up to the wedge top near the exit, none above it inside the bore.
    x = wedge_lay.exit_x - 1.0
    y = wedge_lay.bore_y - 0.05  # the chamfered top peaks at the bore wall's line
    assert _inside(wedge_housing, x, y, wedge_lay.wedge_top - 0.3)
    assert not _inside(wedge_housing, x, y, wedge_lay.wedge_top + 0.1)
    # No point of the exit-side funnel region is solid at packet 1's top height or above,
    # up to the exit wall's lower edge.
    for xi in (70.0, 78.0, 84.0):
        for yi in (-29.0, -28.0, -27.0, 0.0, 27.0, 28.0, 29.0):
            assert not _inside(wedge_housing, xi, yi, 5.3), (xi, yi)
    # Flat packet 2 rests on packet 1: z 5.2 .. 10.4, centred like packet 1.
    packet_2 = Pos(0.0, 0.0, p.packet.height) * packet_solid(p)
    assert packet_2.bounding_box().min.Z == pytest.approx(5.2, abs=1e-6)
    assert overlap_volume(wedge_housing, packet_2) <= OVERLAP_NOISE_MM3


def test_separator_option_is_accepted_for_syringe_and_rejected_elsewhere(p):
    assert load_options({"separator": "wedge"}).separator == "wedge"
    assert load_options({"separator": "blade"}).separator == "blade"
    assert load_options({}).separator == "wedge"
    from projects.pocky import PROJECT

    spec = PROJECT.physics_with_options("syringe", p, {"separator": "wedge"})
    assert spec is not None
    with pytest.raises(ValueError):
        PROJECT.physics_with_options("prototype", p, {"separator": "wedge"})
    for bad in ("comb", "", "Wedge", 3, True, None, ["wedge"]):
        with pytest.raises(ValueError):
            load_options({"separator": bad})


# --------------------------------------------------------------- handle
def test_handle_prints_flat_without_support(parts):
    handle = parts["handle"]
    assert handle.print_location is not None
    posed = handle.print_location * handle.shape
    assert posed.is_valid and len(posed.solids()) == 1
    assert posed.bounding_box().min.Z == pytest.approx(0.0, abs=1e-6)
    # Cadkit overhang check: area of downward faces steeper than 45 deg off the bed.
    result = _overhangs(handle)
    assert result.status == "pass", result.detail
    assert result.value == pytest.approx(0.0, abs=1e-6)


def test_pull_deboss_removes_a_plausible_volume(parts, p):
    handle = parts["handle"]
    assert handle.wall_shape is not None
    removed = handle.wall_shape.volume - handle.shape.volume
    # Four 7 mm capitals, 0.8 mm deep: tens of mm^3, far below the bar's volume.
    assert 15.0 < removed < 200.0, removed
    assert handle.shape.volume < handle.wall_shape.volume
    # The plain base is the same as the helper builds it.
    plain = wall_shape_for("handle", p)
    assert plain.volume == pytest.approx(handle.wall_shape.volume, rel=1e-9)


def test_pull_deboss_is_0p8_mm_deep_on_the_top_face(lay, parts):
    handle, plain = parts["handle"].shape, parts["handle"].wall_shape
    assert PULL_DEPTH == pytest.approx(0.8)
    cx = lay.cross_rest_x + 7.0  # bar centre in X; the text is centred on it
    # Find a point inside a letter stroke: plain bar there, handle empty just below the top face.
    stroke = None
    for ix in range(-14, 15):
        for iy in range(-30, 31):
            x, y = cx + 0.5 * ix, 0.5 * iy
            if _inside(plain, x, y, BAR_Z1 - 0.4) and not _inside(handle, x, y, BAR_Z1 - 0.4):
                stroke = (x, y)
                break
        if stroke:
            break
    assert stroke is not None, "no PULL recess found on the bar top face"
    x, y = stroke
    # Recess spans the top 0.8 mm and no more: empty at 0.7 mm down, solid again at 0.9 mm down.
    assert not _inside(handle, x, y, BAR_Z1 - 0.7)
    assert _inside(handle, x, y, BAR_Z1 - 0.9)
    assert _inside(plain, x, y, BAR_Z1 - 0.1)
    # Away from the letters the top face is intact: a point 0.1 mm below the top is solid.
    assert _inside(handle, cx, 40.0, BAR_Z1 - 0.1)


# --------------------------------------------------------------- hand keep-out and table
def test_presented_packet_lies_in_the_keepout_in_x(lay):
    x0, x1, y0, y1, z0, z1 = lay.keepout
    assert x0 == pytest.approx(SHELF_X)
    assert (x0, x1) == pytest.approx((106.0, 148.0), abs=1.0)
    assert y1 == pytest.approx(47.5) and y0 == pytest.approx(-47.5)
    assert z0 == pytest.approx(-25.0) and z1 == pytest.approx(30.2, abs=0.05)
    # Packet at full stroke: its leading edge is past the shelf with the 20 mm tip margin to spare.
    assert x0 < lay.lead_full < x1
    assert x1 - lay.lead_full == pytest.approx(20.0)


def test_hand_keepout_is_clear_of_slider_and_handle_at_home(p):
    solids = syringe_solids(p, 0.0)
    keepout = hand_keepout(p)
    for name in ("slider", "handle"):
        assert overlap_volume(solids[name], keepout) <= OVERLAP_NOISE_MM3, name


def test_hand_keepout_is_clear_of_housing_beyond_the_shelf(p):
    housing = syringe_solids(p, 0.0)["housing"]
    keepout = hand_keepout(p)
    # The shelf (x <= 106) is the packet's support; everything past it must be clear.
    assert hand_keepout(p).bounding_box().min.X == pytest.approx(SHELF_X)
    assert overlap_volume(housing, keepout) <= OVERLAP_NOISE_MM3
    assert housing.bounding_box().max.X <= SHELF_X + 1.0e-6


@pytest.mark.parametrize("fraction", [0.0, 0.5, 1.0])
def test_nothing_goes_below_the_table_plane(p, fraction):
    assert TABLE_Z == pytest.approx(-52.0)
    for name, shape in syringe_solids(p, fraction).items():
        assert shape.bounding_box().min.Z >= TABLE_Z - 1.0e-6, (name, fraction)
