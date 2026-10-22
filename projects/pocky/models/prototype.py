"""Printed 10-packet dispenser.

``POCKY_POSE`` selects 0, 25, 50, 75, or 100 percent of button travel.
The spring in the assembly is the free spring, 53.4 mm. It overlaps the
seat by the 3 mm preload. The sweep uses the compressed length instead.
"""
from cadkit.model import ModelPart
from projects.pocky.geometry.linkage import button_fraction_from_env
from projects.pocky.geometry.prototype import (
    min_wall_override,
    print_location_for,
    prototype_solids,
)
from projects.pocky.params import Params


def build(p: Params) -> dict[str, ModelPart]:
    solids = prototype_solids(p, fraction=button_fraction_from_env())
    return {
        name: ModelPart(
            shape,
            print_location=print_location_for(name, shape),
            min_wall=min_wall_override(name),
        )
        for name, shape in solids.items()
    }
