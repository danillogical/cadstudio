"""An open-top tray with rounded corners: the smallest printable model."""
from build123d import Align, Axis, Box, Location, Pos, fillet

from cadkit.model import ModelPart

from ..params import Params
from ..part import StarterPart

MINZ = (Align.CENTER, Align.CENTER, Align.MIN)


def tray(p: Params):
    """Tray resting on z=0, centered on the XY origin."""
    b = p.box
    outer = Box(b.w, b.d, b.h, align=MINZ)
    outer = fillet(outer.edges().filter_by(Axis.Z), b.corner_r)
    pocket = Pos(0, 0, b.wall) * Box(b.w - 2 * b.wall, b.d - 2 * b.wall, b.h, align=MINZ)
    return outer - pocket


def build(p: Params) -> dict[str, ModelPart]:
    # The tray already rests on the bed, so the print pose is the identity.
    return {"tray": StarterPart(tray(p), print_location=Location())}
