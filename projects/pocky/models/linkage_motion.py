"""M1 motion proof: one pose of the straight-line pusher.

``POCKY_POSE`` selects 0, 25, 50, 75, or 100 percent of button travel.
The default is rest. Linkage constants live in ``geometry/linkage.py`` and
are not in ``params.toml``.
"""
from cadkit.model import ModelPart
from projects.pocky.geometry.linkage import (
    button_fraction_from_env,
    linkage_from,
    mechanism_solids,
    on_bed,
    phi_for_button_fraction,
)
from projects.pocky.params import Params


def build(p: Params) -> dict[str, ModelPart]:
    phi = phi_for_button_fraction(linkage_from(p), button_fraction_from_env())
    parts = mechanism_solids(p, phi)
    return {name: ModelPart(shape, print_location=on_bed(shape)) for name, shape in parts.items()}
