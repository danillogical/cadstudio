"""Armor part: a ModelPart with the lid and screen check options."""
from __future__ import annotations

from dataclasses import dataclass

from build123d import Solid

from cadkit.model import ModelPart


@dataclass
class ArmorPart(ModelPart):
    """A ModelPart that sits on the lid.

    check_lid: run lid interference/gap checks.
    lid_envelope: override of the lid envelope (e.g. coupons with swept params).
    screen_prism: override of the screen prism.
    check_screen: run the screen-clearance check.

    A plain ModelPart gets the defaults: both checks, default envelope and prism.
    """
    check_lid: bool = True
    lid_envelope: Solid | None = None
    screen_prism: Solid | None = None
    check_screen: bool = True
