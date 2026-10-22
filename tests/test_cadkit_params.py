import dataclasses

import pytest

from projects.armor.params import Params


def test_override_returns_new_and_leaves_original(p):
    q = p.override({"fit.slide_clearance": 0.4, "lid.t": 6.5})
    assert isinstance(q, Params) and q is not p
    assert q.fit.slide_clearance == 0.4
    assert q.lid.t == 6.5
    assert p.fit.slide_clearance == 0.7 and p.lid.t == 7.0


def test_frozen(p):
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.lid = None
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.lid.w = 1.0


@pytest.mark.parametrize("key", ["fit.nope", "nosuch.w", "lid", "lid.", "w"])
def test_override_unknown_key(p, key):
    with pytest.raises(KeyError):
        p.override({key: 1.0})
