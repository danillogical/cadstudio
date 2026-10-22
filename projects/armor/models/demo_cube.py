"""Demo model: a 20 mm cube placed well outside the lid, to exercise the toolchain."""
from build123d import Align, Box, Location, Pos

from cadkit.model import ModelPart
from projects.armor.params import Params

SIZE = 20.0


def build(p: Params) -> dict[str, ModelPart]:
    x = p.lid.w / 2 + 30
    y = p.lid.h / 2
    z = p.lid_z0
    cube = Pos(x, y, z) * Box(SIZE, SIZE, SIZE, align=(Align.CENTER, Align.CENTER, Align.MIN))
    # Print pose: move to the origin and rest on the bed (z=0).
    return {"cube": ModelPart(cube, print_location=Location((-x, -y, -z)))}
