"""A two-leaf hinge: leaf A holds the pin, leaf B turns on it; printed flat, shown open.

Assembly coordinates: the hinge axis runs along X through (y=0, z=knuckle_r). Leaf A lies flat
on y<0. Leaf B is built flat on y>0, then turned about the axis to ``hinge.open_deg``.
"""
from build123d import Align, Axis, Box, Cylinder, Location, Pos, Rot

from cadkit.model import ModelPart

from ..params import Params
from ..part import StarterPart

# How far the pin reaches back into its own knuckle so the two fuse into one solid.
PIN_ANCHOR = 2.0


def _axis_cylinder(r: float, x0: float, x1: float, axis_z: float):
    """Cylinder of radius ``r`` along X from ``x0`` to ``x1`` on the hinge axis."""
    return Pos((x0 + x1) / 2, 0, axis_z) * Rot(Y=90) * Cylinder(r, x1 - x0)


def _plate(h, x0: float, x1: float, side: int):
    """Leaf plate on the +Y (``side`` 1) or -Y (``side`` -1) side of the axis, resting on z=0."""
    return Pos((x0 + x1) / 2, side * h.leaf_w / 2, 0) * Box(
        x1 - x0, h.leaf_w, h.leaf_t, align=(Align.CENTER, Align.CENTER, Align.MIN))


def leaf_a(p: Params):
    """Fixed leaf: plate, knuckle and the pin that reaches through leaf B's knuckle."""
    h, gap = p.hinge, p.fit.clearance
    r = h.knuckle_r
    k = h.knuckle_len
    body = _plate(h, 0, k, -1) + _axis_cylinder(r, 0, k, r)
    pin = _axis_cylinder(h.pin_r, k - PIN_ANCHOR, 2 * k + gap, r)
    return body + pin


def leaf_b_flat(p: Params):
    """Moving leaf, flat: plate and a knuckle bored for the pin, one gap past leaf A's knuckle."""
    h, gap = p.hinge, p.fit.clearance
    r = h.knuckle_r
    x0, x1 = h.knuckle_len + gap, 2 * h.knuckle_len + gap
    body = _plate(h, x0, x1, 1) + _axis_cylinder(r, x0, x1, r)
    return body - _axis_cylinder(h.pin_r + gap, x0 - 1, x1 + 1, r)


def build(p: Params) -> dict[str, ModelPart]:
    h = p.hinge
    # Turn leaf B up from flat (180 deg) to the open angle, about the hinge axis.
    turn = Location((0, 0, h.knuckle_r)) * Rot(X=180 - h.open_deg) * Location((0, 0, -h.knuckle_r))
    a = leaf_a(p)
    b = turn * leaf_b_flat(p)
    return {
        "leaf_a": StarterPart(a, print_location=Location(), mate=b),
        # Printing B flat is the inverse of the assembly turn.
        "leaf_b": StarterPart(b, print_location=turn.inverse(), mate=a),
    }
