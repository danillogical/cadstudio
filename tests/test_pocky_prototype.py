"""Printed prototype: spring B, peg clearance, seat offsets, and the part set."""
import math

import pytest

from cadkit.mesh import posed_shape
from projects.pocky.geometry.linkage import (
    SLOT_END_MARGIN,
    linkage_from,
    phi_for_button_fraction,
    pose_at_phi,
    slot_end_clearance,
)
from projects.pocky.geometry.prototype import (
    PART_ROLES,
    PEG_D,
    PIVOT_BORE,
    PIVOT_PEG_D,
    PROTO_SLOT_W,
    PROTOTYPE_SPRING,
    VARIANTS,
    seat_face_offset,
)
from projects.pocky.models.prototype import build
from projects.pocky.params import load_params

# One printed part, or a set, for each row of the plan's parts table.
ROLE_KEYS = {
    "body": ("body",),
    "chassis": ("chassis",),
    "lip": ("lip",),
    "shim": ("shim_04_a", "shim_04_b", "shim_08"),
    "spring_seat": ("spring_seat",),
    "crank": ("crank",),
    "pusher": ("pusher",),
    "rod": ("rod",),
    "spring": ("spring",),
    "peg": ("peg_pivot", "peg_pusher", "peg_button"),
    "dummy": ("dummy",),
}


@pytest.fixture(scope="module")
def params():
    return load_params()


@pytest.fixture(scope="module")
def parts(params):
    return build(params)


def test_spring_b_lengths():
    spring = PROTOTYPE_SPRING
    assert spring.letter == "B"
    assert spring.thickness == pytest.approx(1.2)
    assert spring.solid_length == pytest.approx(20.4)
    assert spring.free_length == pytest.approx(53.4)
    assert spring.installed() == pytest.approx(50.4)
    assert spring.full_press(40.0 / math.sqrt(3.0)) == pytest.approx(27.306, abs=1e-2)
    assert spring.full_press(40.0 / math.sqrt(3.0)) - spring.solid_length == pytest.approx(6.9, abs=1e-2)


def test_seat_offsets_for_contingencies():
    assert seat_face_offset("A") == pytest.approx(2.4)
    assert seat_face_offset("B") == pytest.approx(0.0)
    assert seat_face_offset("C") == pytest.approx(-4.8)
    assert VARIANTS["A"].free_length == pytest.approx(51.0)
    assert VARIANTS["C"].free_length == pytest.approx(58.2)
    assert VARIANTS["A"].solid_length == pytest.approx(18.0)
    assert VARIANTS["C"].solid_length == pytest.approx(25.2)


def test_peg_clearance(params):
    assert PROTO_SLOT_W - PEG_D == pytest.approx(0.6)
    assert PIVOT_BORE - PIVOT_PEG_D == pytest.approx(0.4)
    link = linkage_from(params)
    for fraction in (0.0, 1.0):
        pose = pose_at_phi(link, phi_for_button_fraction(link, fraction))
        button_clear, pusher_clear = slot_end_clearance(link, pose)
        assert button_clear >= SLOT_END_MARGIN - 1e-9
        assert pusher_clear >= SLOT_END_MARGIN - 1e-9


def test_build_covers_every_part(parts):
    assert set(ROLE_KEYS) == set(PART_ROLES)
    for role, keys in ROLE_KEYS.items():
        missing = [key for key in keys if key not in parts]
        assert not missing, f"{role} missing {missing}"
    for name, part in parts.items():
        assert len(part.shape.solids()) == 1, name
        assert part.shape.is_valid, name
        posed = posed_shape(part)
        assert posed.bounding_box().min.Z == pytest.approx(0.0, abs=1e-6)
        box = posed.bounding_box()
        assert box.max.X - box.min.X <= 360.0
        assert box.max.Y - box.min.Y <= 360.0
        assert box.max.Z - box.min.Z <= 360.0
    spring = parts["spring"].shape.bounding_box()
    assert spring.max.X - spring.min.X == pytest.approx(53.4)
    assert spring.max.Y - spring.min.Y == pytest.approx(14.0)
    assert spring.max.Z - spring.min.Z == pytest.approx(5.0)
    assert parts["spring"].min_wall == pytest.approx(1.2)
    assert parts["shim_04_a"].min_wall == pytest.approx(0.4)
    assert parts["shim_08"].min_wall == pytest.approx(0.8)
    assert parts["body"].min_wall is None
    assert parts["peg_pivot"].min_wall is None
