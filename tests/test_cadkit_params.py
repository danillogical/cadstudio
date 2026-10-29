import dataclasses

import pytest

from projects.starter.params import Params


def test_override_returns_new_and_leaves_original(p):
    q = p.override({"fit.clearance": 0.2, "box.h": 30.0})
    assert isinstance(q, Params) and q is not p
    assert q.fit.clearance == 0.2
    assert q.box.h == 30.0
    assert p.fit.clearance == 0.4 and p.box.h == 25.0


def test_frozen(p):
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.box = None
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.box.w = 1.0


@pytest.mark.parametrize("key", ["fit.nope", "nosuch.w", "box", "box.", "w"])
def test_override_unknown_key(p, key):
    with pytest.raises(KeyError):
        p.override({key: 1.0})
