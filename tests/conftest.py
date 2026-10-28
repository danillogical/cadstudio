"""Shared fixtures and helpers for the cadkit test suite (engine tests use the starter project)."""
from pathlib import Path

import pytest
from build123d import Align, Box, Pos

from projects.starter.params import load_params
from projects.starter.part import StarterPart

MINZ = (Align.CENTER, Align.CENTER, Align.MIN)
# Engine tests use frozen starter params, so edits to projects/starter/params.toml cannot move them.
FIXTURE_PARAMS = Path(__file__).parent / "fixtures" / "starter.toml"


def box(x0, x1, y0, y1, z0, z1):
    """Axis-aligned box spanning the given extents (assembly coords)."""
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, z0) * Box(x1 - x0, y1 - y0, z1 - z0, align=MINZ)


def part(shape, **kw):
    return StarterPart(shape, **kw)


@pytest.fixture(scope="session")
def p():
    return load_params(FIXTURE_PARAMS)


def by_name(results):
    """Map check name -> CheckResult."""
    return {r.name: r for r in results}
