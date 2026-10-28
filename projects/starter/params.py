"""Starter parameters (single source of truth: ``projects/starter/params.toml``)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cadkit.params import Material, Overridable, Printer, load_sections

DEFAULT_PARAMS_PATH = Path(__file__).resolve().parent / "params.toml"


@dataclass(frozen=True)
class Box:
    """Outer size of the open-top tray."""
    w: float
    d: float
    h: float
    wall: float
    corner_r: float


@dataclass(frozen=True)
class Hinge:
    """Two-leaf hinge: each leaf is a plate with one knuckle, joined by a pin."""
    leaf_w: float
    leaf_t: float
    knuckle_len: float
    knuckle_r: float
    pin_r: float
    open_deg: float


@dataclass(frozen=True)
class Fit:
    """Clearance between parts that must move or fit together."""
    clearance: float


@dataclass(frozen=True)
class Structure:
    """The generic ``min_wall`` check reads ``min_wall`` from here."""
    min_wall: float


@dataclass(frozen=True)
class Params(Overridable):
    """All parameters, one attribute per TOML section."""
    box: Box
    hinge: Hinge
    fit: Fit
    structure: Structure
    printer: Printer
    material: Material


def load_params(path: str | Path | None = None) -> Params:
    """Load parameters from a TOML file (default: ``projects/starter/params.toml``)."""
    return load_sections(Path(path) if path is not None else DEFAULT_PARAMS_PATH, Params)
