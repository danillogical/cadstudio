"""Syringe dispenser: housing on four pop-in legs, slider with two arms, clip-on PULL handle, printed spring.

``POCKY_POSE`` selects 0, 25, 50, 75, or 100 percent of the slider stroke.
The handle is exported clipped onto the slider in that pose; it prints flat,
text up. The exported spring is the free (printed) spring, as in the prototype
model, so in this pose it runs the 3 mm preload into the housing seat.
``syringe_solids`` gives the compressed spring for clearance checks.

The four legs are identical. Each is exported as its own part, ``leg_1`` ..
``leg_4``, standing on its foot pad (z=0) at its own assembly XY, so the four
files load onto one plate without overlapping; any one of them with four
copies prints the same set.
"""
from cadkit.model import ModelPart
from projects.pocky.geometry.linkage import button_fraction_from_env
from projects.pocky.geometry.syringe import (
    min_wall_override,
    print_location_for,
    syringe_solids,
    wall_shape_for,
)
from projects.pocky.params import Params


def build(p: Params) -> dict[str, ModelPart]:
    fraction = button_fraction_from_env()
    solids = syringe_solids(p, stroke_fraction=fraction, free_spring=True)
    return {
        name: ModelPart(
            shape,
            print_location=print_location_for(name, shape),
            wall_shape=wall_shape_for(name, p, fraction),
            min_wall=min_wall_override(name, p),
        )
        for name, shape in solids.items()
    }
