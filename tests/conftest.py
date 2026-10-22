"""Shared fixtures and helpers for the cadkit test suite."""
from pathlib import Path

import pytest
from build123d import Align, Box, Pos

from projects.armor.params import load_params
from projects.armor.part import ArmorPart

MINZ = (Align.CENTER, Align.CENTER, Align.MIN)
# cadkit unit tests use frozen 14" params; model tests use the live projects/armor/params.toml.
FIXTURE_PARAMS = Path(__file__).parent / "fixtures" / "lid_14in.toml"


def box(x0, x1, y0, y1, z0, z1):
    """Axis-aligned box spanning the given extents (assembly coords)."""
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, z0) * Box(x1 - x0, y1 - y0, z1 - z0, align=MINZ)


def part(shape, **kw):
    return ArmorPart(shape, **kw)


@pytest.fixture(scope="session")
def p():
    return load_params(FIXTURE_PARAMS)


def by_name(results):
    """Map check name -> CheckResult."""
    return {r.name: r for r in results}
