"""Unit conversion and the analytic mass/inertia regressions (M1).

Every expected number here is derived from a closed-form formula written in the test, not
read back from the implementation.
"""
import math

import pytest

from cadkit.physics.units import (
    DEG_TO_RAD,
    GRAVITY,
    inertia_kg_m2,
    mass_kg,
    m_to_mm,
    mm_to_m,
)


def test_mm_to_m_roundtrip():
    assert mm_to_m(165.0) == pytest.approx(0.165)
    assert m_to_mm(0.165) == pytest.approx(165.0)


def test_mass_uses_1e6_not_1e3():
    """The regression that M0 got wrong: mm3 * g/cm3 * 1e-6, not /1000."""
    # 8000 mm3 at 1.27 g/cm3 = 10.16 g = 0.01016 kg
    assert mass_kg(8000.0, 1.27) == pytest.approx(0.01016)
    # 20 x 40 x 25 mm box at 1.27 g/cm3, the supervisor's independent check
    assert mass_kg(20.0 * 40.0 * 25.0, 1.27) == pytest.approx(0.0254)
    # and explicitly not the /1000 answer
    assert mass_kg(20000.0, 1.27) != pytest.approx(1.27e-5)


def test_mass_matches_grams_over_1000():
    for volume_mm3, rho in ((109789.2323, 1.27), (1000.0, 1.24), (250.0, 0.95)):
        grams = volume_mm3 * rho / 1000.0  # mm3 * g/cm3 / 1000 == g
        assert mass_kg(volume_mm3, rho) == pytest.approx(grams / 1000.0)


def test_mass_rejects_bad_input():
    with pytest.raises(ValueError):
        mass_kg(0.0, 1.27)
    with pytest.raises(ValueError):
        mass_kg(-5.0, 1.27)
    with pytest.raises(ValueError):
        mass_kg(100.0, 0.0)
    with pytest.raises(ValueError):
        mass_kg(float("nan"), 1.27)
    with pytest.raises(ValueError):
        mass_kg(100.0, float("inf"))


def test_inertia_matches_solid_box_formula():
    """mm5 * g/cm3 * 1e-12 == kg m2, cross-checked against m(a^2+b^2)/12."""
    volume, rho = 20000.0, 1.27
    m = mass_kg(volume, rho)
    for a_mm, b_mm in ((20.0, 40.0), (40.0, 25.0), (20.0, 25.0)):
        # unit-density inertia about the COM for that pair of extents
        inertia_mm5 = volume * (a_mm ** 2 + b_mm ** 2) / 12.0
        expected = m * ((a_mm / 1000.0) ** 2 + (b_mm / 1000.0) ** 2) / 12.0
        assert inertia_kg_m2(inertia_mm5, rho) == pytest.approx(expected)


def test_inertia_is_not_mass_scaled():
    """mm5 -> kg m2 is 1e-12, i.e. a different factor from the mass conversion."""
    assert inertia_kg_m2(1.0e12, 1.27) == pytest.approx(1.27)
    assert mass_kg(1.0e6, 1.27) == pytest.approx(1.27)


def test_gravity_and_degrees():
    assert GRAVITY == pytest.approx(9.80665)
    assert DEG_TO_RAD * 180.0 == pytest.approx(math.pi)
