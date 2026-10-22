"""Unit conversion: the single SI boundary for ``cadkit.physics``.

Everything authored for physics is in the CAD's units — **mm, g/cm3, N, degrees** — and is
converted to SI exactly here. MuJoCo does not define units ("Units are unspecified — MuJoCo
does not specify basic physical units", https://mujoco.readthedocs.io/en/stable/overview.html),
so a second, ad-hoc conversion anywhere else is a bug.

Canonical formulas (Codex supervisor review §21.1):

    mass_kg  = volume_mm3 * rho_g_cm3 * 1e-6
    I_kg_m2  = I_mm5     * rho_g_cm3 * 1e-12

``build123d`` reports ``Shape.volume`` in mm3 and ``Shape.matrix_of_inertia`` in mm5 about the
centre of mass (unit density), established empirically in M0: a 20 x 40 x 25 box returns
3.708333e6, 1.708333e6, 3.333333e6, which is ``m(b^2+c^2)/12`` with ``m = volume``.
"""
from __future__ import annotations

import math

MM_TO_M = 1e-3
G_CM3_TO_KG_M3 = 1e3
DEG_TO_RAD = math.pi / 180.0

#: mm3 * g/cm3 -> kg
MASS_FACTOR = 1e-6
#: mm5 * g/cm3 -> kg m2
INERTIA_FACTOR = 1e-12

GRAVITY = 9.80665  # m/s2, standard gravity


def mm_to_m(value_mm: float) -> float:
    return float(value_mm) * MM_TO_M


def m_to_mm(value_m: float) -> float:
    return float(value_m) / MM_TO_M


def mass_kg(volume_mm3: float, density_g_cm3: float) -> float:
    """Mass of a solid of ``volume_mm3`` at ``density_g_cm3``.

    ``8000 mm3`` at ``1.27 g/cm3`` -> ``0.01016 kg``. Note the factor is ``1e-6``:
    dividing by 1000 instead is wrong by 1000.
    """
    _require_finite(volume_mm3, "volume_mm3")
    _require_finite(density_g_cm3, "density_g_cm3")
    if volume_mm3 <= 0.0:
        raise ValueError(f"volume_mm3 must be positive, got {volume_mm3}")
    if density_g_cm3 <= 0.0:
        raise ValueError(f"density_g_cm3 must be positive, got {density_g_cm3}")
    return volume_mm3 * density_g_cm3 * MASS_FACTOR


def inertia_kg_m2(inertia_mm5: float, density_g_cm3: float) -> float:
    """One component of the inertia tensor: mm5 at ``density_g_cm3`` -> kg m2."""
    _require_finite(inertia_mm5, "inertia_mm5")
    _require_finite(density_g_cm3, "density_g_cm3")
    return inertia_mm5 * density_g_cm3 * INERTIA_FACTOR


def density_kg_m3(density_g_cm3: float) -> float:
    return float(density_g_cm3) * G_CM3_TO_KG_M3


def _require_finite(value: float, name: str) -> None:
    if not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite, got {value!r}")
