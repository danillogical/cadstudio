"""Pocky parameters (single source of truth: ``projects/pocky/params.toml``).

Coordinate convention (assembly coordinates, mm)
------------------------------------------------
* X: packet long axis (165).
* Y: packet short axis (55).
* Z: vertical; stacked packets occupy increasing Z, and the bottom packet's underside is at ``z=0``.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cadkit.params import Material, Overridable, Printer, load_sections

DEFAULT_PARAMS_PATH = Path(__file__).resolve().parent / "params.toml"


@dataclass(frozen=True)
class Packet:
    """Rigid envelope of one wrapped packet."""
    length: float
    width: float
    height: float


@dataclass(frozen=True)
class Magazine:
    """Magazine interior and test capacity."""
    length_i: float
    width_i: float
    headroom: float
    capacity_test: float


@dataclass(frozen=True)
class Separator:
    """Separator slot at the bottom of the stack."""
    gap: float


@dataclass(frozen=True)
class Structure:
    """Wall thickness."""
    min_wall: float


@dataclass(frozen=True)
class Params(Overridable):
    """All parameters, one attribute per TOML section, plus derived values."""
    packet: Packet
    magazine: Magazine
    separator: Separator
    structure: Structure
    printer: Printer
    material: Material

    @property
    def stack_nominal_height(self) -> float:
        """Uncompressed stack height (``capacity_test * packet.height``)."""
        return self.magazine.capacity_test * self.packet.height


def load_params(path: str | Path | None = None) -> Params:
    """Load parameters from a TOML file (default: ``projects/pocky/params.toml``)."""
    return load_sections(Path(path) if path is not None else DEFAULT_PARAMS_PATH, Params)
