"""Model part container shared by models, checks, export and render."""
from __future__ import annotations

from dataclasses import dataclass

from build123d import Location


@dataclass
class ModelPart:
    """One printable part, defined in assembly coordinates.

    shape: build123d Part/Solid/Compound in assembly coordinates.
    print_location: transform from assembly coords to the print-bed pose
        (part resting on z=0); None means identity.
    wall_shape: undecorated structural base; if set, min_wall probes it instead of ``shape``.
    min_wall: per-part override of the project's ``structure.min_wall`` (mm).

    Projects subclass this to add their own per-part check options.
    """
    shape: object
    print_location: Location | None = None
    wall_shape: object | None = None
    min_wall: float | None = None
