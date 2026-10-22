"""Printable rigid stand-in packet for early bench tests (plan work package D)."""
from build123d import Align, Axis, Box, fillet

from cadkit.model import ModelPart
from projects.pocky.params import Params

CORNER_R = 2.0  # radius of the four vertical edges; top and bottom faces stay flat


def build(p: Params) -> dict[str, ModelPart]:
    k = p.packet
    box = Box(k.length, k.width, k.height, align=(Align.CENTER, Align.CENTER, Align.MIN))
    dummy = fillet(box.edges().filter_by(Axis.Z), CORNER_R)
    return {"dummy": ModelPart(dummy.solid())}
