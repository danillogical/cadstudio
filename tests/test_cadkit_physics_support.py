"""Support-margin geometry and bearing direction (pure planar maths, no MuJoCo)."""
from __future__ import annotations

import math
import subprocess
import sys

import pytest

from cadkit.params import REPO_ROOT
from cadkit.physics.support import SupportMargin, bearing_carries, support_margin

SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


def test_square_interior_margin_is_distance_to_nearest_edge():
    m = support_margin((4.0, 5.0), [SQUARE], 2.0)
    assert isinstance(m, SupportMargin)
    assert m.hull_area_mm2 == pytest.approx(100.0)
    assert m.strip_width_mm == pytest.approx(10.0)
    assert m.com_inside is True
    assert m.com_margin_mm == pytest.approx(4.0)
    assert m.gravity_moment_nm == 0.0


def test_square_centre_margin_is_half_width():
    assert support_margin((5.0, 5.0), [SQUARE], 1.0).com_margin_mm == pytest.approx(5.0)


def test_square_exterior_margin_is_negative_distance():
    m = support_margin((13.0, 5.0), [SQUARE], 2.0)
    assert m.com_inside is False
    assert m.com_margin_mm == pytest.approx(-3.0)
    # Diagonal exterior: nearest feature is the corner.
    m = support_margin((13.0, 14.0), [SQUARE], 2.0)
    assert m.com_margin_mm == pytest.approx(-5.0)


def test_gravity_moment_is_weight_times_overhang_when_outside():
    m = support_margin((13.0, 5.0), [SQUARE], 2.0)
    assert m.gravity_moment_nm == pytest.approx(2.0 * 3.0 / 1000.0)


def test_com_on_boundary_is_inside_with_zero_margin_and_moment():
    m = support_margin((10.0, 5.0), [SQUARE], 2.0)
    assert m.com_inside is True
    assert m.com_margin_mm == pytest.approx(0.0, abs=1e-9)
    assert m.gravity_moment_nm == 0.0


def test_two_patch_strip_reference_case():
    patches = [
        [(64.0, 34.0), (70.0, 34.0), (70.0, 35.0), (64.0, 35.0)],
        [(-36.0, -35.0), (-30.0, -35.0), (-30.0, -34.0), (-36.0, -34.0)],
    ]
    m = support_margin((5.28, 0.0), patches, 1.0)
    assert m.strip_width_mm == pytest.approx(4.23, abs=0.01)
    assert m.com_margin_mm == pytest.approx(-4.54, abs=0.01)
    assert m.com_inside is False
    assert m.gravity_moment_nm == pytest.approx(1.0 * 4.54 / 1000.0, abs=1e-5)


def test_patches_are_unioned_into_one_hull():
    """Two separate squares: a COM in the gap between them is inside their joint hull."""
    a = [(0.0, 0.0), (2.0, 0.0), (2.0, 10.0), (0.0, 10.0)]
    b = [(8.0, 0.0), (10.0, 0.0), (10.0, 10.0), (8.0, 10.0)]
    m = support_margin((5.0, 5.0), [a, b], 1.0)
    assert m.com_inside is True
    assert m.hull_area_mm2 == pytest.approx(100.0)


def test_collinear_patches_are_a_line_with_no_area_or_width():
    patches = [[(0.0, 0.0), (1.0, 1.0)], [(2.0, 2.0), (5.0, 5.0)]]
    m = support_margin((2.0, 3.0), patches, 4.0)
    assert m.hull_area_mm2 == 0.0
    assert m.strip_width_mm == 0.0
    assert m.com_inside is False
    assert m.com_margin_mm == pytest.approx(-math.sqrt(2.0) / 2.0)
    assert m.gravity_moment_nm == pytest.approx(4.0 * (math.sqrt(2.0) / 2.0) / 1000.0)


def test_com_on_a_line_support_is_inside_with_zero_margin():
    m = support_margin((2.5, 2.5), [[(0.0, 0.0), (5.0, 5.0)]], 1.0)
    assert m.hull_area_mm2 == 0.0 and m.strip_width_mm == 0.0
    assert m.com_inside is True
    assert m.com_margin_mm == pytest.approx(0.0, abs=1e-9)


def test_lone_point_is_degenerate():
    m = support_margin((3.0, 4.0), [[(0.0, 0.0)]], 1.0)
    assert m.hull_area_mm2 == 0.0 and m.strip_width_mm == 0.0
    assert m.com_inside is False
    assert m.com_margin_mm == pytest.approx(-5.0)
    assert m.gravity_moment_nm == pytest.approx(5.0 / 1000.0)


def test_lone_point_under_the_com_is_inside_with_zero_margin():
    m = support_margin((0.0, 0.0), [[(0.0, 0.0)]], 1.0)
    assert m.com_inside is True
    assert m.com_margin_mm == 0.0


@pytest.mark.parametrize("patches", [[], [[]]])
def test_empty_patches_raise(patches):
    with pytest.raises(ValueError):
        support_margin((0.0, 0.0), patches, 1.0)


@pytest.mark.parametrize("bad", [
    {"com": (float("nan"), 0.0)}, {"com": (0.0, float("inf"))}, {"com": (0.0, 0.0, 0.0)},
    {"patches": [[(0.0, float("nan"))]]}, {"patches": [[(float("inf"), 0.0)]]},
    {"weight": -1.0}, {"weight": float("nan")}, {"weight": float("inf")},
])
def test_non_finite_or_negative_inputs_raise(bad):
    with pytest.raises(ValueError):
        support_margin(bad.get("com", (0.0, 0.0)), bad.get("patches", [SQUARE]),
                       bad.get("weight", 1.0))


def test_zero_weight_is_allowed_and_has_no_moment():
    assert support_margin((20.0, 0.0), [SQUARE], 0.0).gravity_moment_nm == 0.0


# --------------------------------------------------------------------------- bearing
def test_bearing_carries_when_normal_opposes_load():
    assert bearing_carries((0, 0, -1), (0, 0, 1)) is True


def test_retention_only_clip_does_not_carry():
    assert bearing_carries((0, 0, -1), (0, 0, -1)) is False


def test_perpendicular_normal_does_not_carry():
    assert bearing_carries((0, 0, -1), (1, 0, 0)) is False


def test_oblique_opposing_normal_carries_and_scale_is_irrelevant():
    assert bearing_carries((0, 0, -3), (0.5, 0, 0.2)) is True


@pytest.mark.parametrize("load,normal", [((0, 0, 0), (0, 0, 1)), ((0, 0, -1), (0, 0, 0)),
                                         ((0, 0, -1), (0, 0)), ((0, 0, -1), (0, float("nan"), 1))])
def test_bearing_rejects_bad_vectors(load, normal):
    with pytest.raises(ValueError):
        bearing_carries(load, normal)


# --------------------------------------------------------------------------- import hygiene
def test_support_module_imports_without_mujoco():
    code = ("import sys\n"
            "import cadkit.physics.support as s\n"
            "assert 'mujoco' not in sys.modules, 'mujoco was imported'\n"
            "print(s.support_margin((1, 1), [[(0, 0), (2, 0), (2, 2), (0, 2)]], 1).com_inside)\n")
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == "True"
