"""Armor parameters (single source of truth: ``projects/armor/params.toml``) and shared lid geometry.

Coordinate convention (assembly coordinates, mm)
------------------------------------------------
* X: lid width, centered on 0 (lid spans ``-lid.w/2 .. +lid.w/2``).
* Y: from the lid's hinge edge (``y=0``) up to the top edge (``y=lid.h``).
* Z: from the back face of the rear shell (``z=0``) toward the viewer.
  The lid occupies ``z in [back_th + rear_gap, back_th + rear_gap + lid.t]``.
  The front bezel inner face is at ``front_z = back_th + rear_gap + lid.t + front_gap``.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from build123d import Align, Axis, BuildPart, Box, Locations, Solid, fillet

from cadkit.params import Material, Overridable, Printer, load_sections

DEFAULT_PARAMS_PATH = Path(__file__).resolve().parent / "params.toml"

# How far (mm) the lid envelope extends below the hinge edge (-Y) to model the open bottom.
ENVELOPE_BELOW_HINGE = 50.0
# How far (mm) the screen prism extends past the front of the shell.
SCREEN_PRISM_OVERSHOOT = 50.0


@dataclass(frozen=True)
class Lid:
    """Outer dimensions of the factory lid."""
    w: float
    h: float
    t: float


@dataclass(frozen=True)
class Screen:
    """Active display area; ``bottom`` is measured from the hinge edge."""
    w: float
    h: float
    bottom: float
    corner_r: float


@dataclass(frozen=True)
class Camera:
    """Camera region, centered in X, ``top_offset`` below the lid top edge."""
    w: float
    h: float
    top_offset: float
    notch: bool = True  # False covers the camera with solid bezel instead of cutting a notch


@dataclass(frozen=True)
class Fit:
    """Clearances and extensions around the lid."""
    slide_clearance: float
    rear_gap: float
    front_gap: float
    bottom_hinge_relief: float
    top_extension: float


@dataclass(frozen=True)
class Structure:
    """Wall thicknesses and corner radii."""
    back_th: float
    front_th: float
    min_wall: float
    outer_corner_r: float


@dataclass(frozen=True)
class Fasteners:
    """Screw, counterbore, heat-set insert and boss dimensions."""
    screw_d: float
    counterbore_d: float
    counterbore_depth: float
    insert_d: float
    insert_depth: float
    boss_d: float
    boss_margin: float


@dataclass(frozen=True)
class Params(Overridable):
    """All parameters, one attribute per TOML section, plus derived Z positions."""
    lid: Lid
    screen: Screen
    camera: Camera
    fit: Fit
    structure: Structure
    fasteners: Fasteners
    printer: Printer
    material: Material

    @property
    def lid_z0(self) -> float:
        """Z of the lid back face (``back_th + rear_gap``)."""
        return self.structure.back_th + self.fit.rear_gap

    @property
    def lid_z1(self) -> float:
        """Z of the lid front face."""
        return self.lid_z0 + self.lid.t

    @property
    def front_z(self) -> float:
        """Z of the front bezel inner face."""
        return self.lid_z1 + self.fit.front_gap

    @property
    def total_t(self) -> float:
        """Overall shell thickness (``front_z + front_th``)."""
        return self.front_z + self.structure.front_th

    @property
    def cavity_w(self) -> float:
        """Width of the slide-in cavity (``lid.w + 2*slide_clearance``)."""
        return self.lid.w + 2 * self.fit.slide_clearance


def load_params(path: str | Path | None = None) -> Params:
    """Load parameters from a TOML file (default: ``projects/armor/params.toml``)."""
    return load_sections(Path(path) if path is not None else DEFAULT_PARAMS_PATH, Params)


def _box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> Solid:
    with BuildPart() as bp:
        with Locations(((x0 + x1) / 2, (y0 + y1) / 2, z0)):
            Box(x1 - x0, y1 - y0, z1 - z0, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return bp.part.solid() if hasattr(bp.part, "solid") else bp.part


def lid_envelope(p: Params, inflate: float = 0.0) -> Solid:
    """Box of the lid in assembly coordinates, inflated by ``inflate`` on all sides.

    Extended ``ENVELOPE_BELOW_HINGE`` mm down in -Y past the hinge so the open
    bottom is modeled (the inflation applies to that far end too).
    """
    hw = p.lid.w / 2 + inflate
    return _box(
        -hw, hw,
        -ENVELOPE_BELOW_HINGE - inflate, p.lid.h + inflate,
        p.lid_z0 - inflate, p.lid_z1 + inflate,
    )


def screen_prism(p: Params) -> Solid:
    """Rounded-rect prism of the active screen area, from ``z=lid_z1`` to ``z=total_t+50``."""
    s = p.screen
    z0 = p.lid_z1
    z1 = p.total_t + SCREEN_PRISM_OVERSHOOT
    with BuildPart() as bp:
        with Locations((0, s.bottom + s.h / 2, z0)):
            Box(s.w, s.h, z1 - z0, align=(Align.CENTER, Align.CENTER, Align.MIN))
        if s.corner_r > 0:
            fillet(bp.edges().filter_by(Axis.Z), s.corner_r)
    return bp.part.solid() if hasattr(bp.part, "solid") else bp.part
