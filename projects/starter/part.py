"""Starter part: a ModelPart that can name the part it must keep clear of."""
from __future__ import annotations

from dataclasses import dataclass

from cadkit.model import ModelPart


@dataclass
class StarterPart(ModelPart):
    """A ModelPart with an optional mating part.

    mate: the other part's shape in assembly coordinates; the ``clearance`` check measures against it.
    """
    mate: object | None = None
