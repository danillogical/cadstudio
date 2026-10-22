import dataclasses

import pytest

from projects.pocky.params import DEFAULT_PARAMS_PATH, load_params


@pytest.fixture(scope="module")
def pp():
    return load_params()


def test_default_path_exists():
    assert DEFAULT_PARAMS_PATH.exists()
    assert DEFAULT_PARAMS_PATH.name == "params.toml"


def test_packet_defaults(pp):
    assert (pp.packet.length, pp.packet.width, pp.packet.height) == (165.0, 55.0, 5.2)


def test_magazine_defaults(pp):
    m = pp.magazine
    assert (m.length_i, m.width_i, m.headroom, m.capacity_test) == (170.0, 60.0, 20.0, 10)


def test_other_defaults(pp):
    assert pp.separator.gap == 5.75
    assert pp.structure.min_wall == 2.4
    assert (pp.printer.bed_x, pp.printer.bed_y, pp.printer.bed_z) == (360, 360, 360)
    assert pp.material.name == "PETG"


def test_stack_nominal_height_default(pp):
    assert pp.stack_nominal_height == pytest.approx(52.0)


def test_stack_nominal_height_follows_override(pp):
    assert pp.override({"magazine.capacity_test": 25}).stack_nominal_height == pytest.approx(130.0)
    q = pp.override({"packet.height": 6.0})
    assert q.stack_nominal_height == pytest.approx(60.0)


def test_design_invariants(pp):
    assert pp.magazine.length_i > pp.packet.length
    assert pp.magazine.width_i > pp.packet.width
    assert pp.packet.height < pp.separator.gap < 2 * pp.packet.height


def test_override_returns_new_and_leaves_original(pp):
    q = pp.override({"packet.length": 150.0, "separator.gap": 6.0})
    assert q is not pp and type(q) is type(pp)
    assert q.packet.length == 150.0 and q.separator.gap == 6.0
    assert pp.packet.length == 165.0 and pp.separator.gap == 5.75


def test_frozen(pp):
    with pytest.raises(dataclasses.FrozenInstanceError):
        pp.packet = None
    with pytest.raises(dataclasses.FrozenInstanceError):
        pp.packet.length = 1.0


@pytest.mark.parametrize("key", ["packet.nope", "nosuch.length", "packet", "packet.", "length"])
def test_override_unknown_key(pp, key):
    with pytest.raises(KeyError):
        pp.override({key: 1.0})
