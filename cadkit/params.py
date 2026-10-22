"""Generic parameter loading: TOML sections into frozen dataclasses, plus dotted overrides.

A project defines its own params schema: a frozen dataclass whose fields are section
dataclasses, one per TOML table. ``load_sections`` fills it from a TOML file and
``override`` returns a copy with dotted keys replaced. Every project schema carries
the shared ``printer`` and ``material`` sections and a ``structure`` section with a
``min_wall`` field, which the generic checks read.
"""
from __future__ import annotations

import dataclasses
import tomllib
import typing
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeVar

REPO_ROOT = Path(__file__).resolve().parent.parent

T = TypeVar("T")


@dataclass(frozen=True)
class Printer:
    """Printer bed volume."""
    bed_x: float
    bed_y: float
    bed_z: float


@dataclass(frozen=True)
class Material:
    """Filament properties."""
    name: str
    density_g_cm3: float
    filament_d: float


class HasMinWall(Protocol):
    """Minimal ``structure`` section the generic checks need: the default wall thickness (mm)."""
    min_wall: float


class CheckParams(Protocol):
    """What the generic checks read from a project's params."""
    printer: Printer
    material: Material
    structure: HasMinWall


def default_min_wall(p: CheckParams) -> float:
    """The project's default ``min_wall`` requirement (mm)."""
    return p.structure.min_wall


def load_sections(path: str | Path, schema: type[T]) -> T:
    """Load the TOML file at ``path`` into ``schema``, one section dataclass per field."""
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    hints = typing.get_type_hints(schema)
    return schema(**{f.name: hints[f.name](**data[f.name]) for f in dataclasses.fields(schema)})


def override(params: T, mapping: dict[str, float]) -> T:
    """Return a copy of ``params`` with dotted keys replaced, e.g. ``{"structure.min_wall": 2.0}``.

    Raises ``KeyError`` for an unknown section or field. Numeric values are
    coerced to float (string fields such as ``material.name`` stay strings).
    """
    sections = {f.name: getattr(params, f.name) for f in dataclasses.fields(params)}
    for key, value in mapping.items():
        sec, dot, field = key.partition(".")
        if not dot or sec not in sections:
            raise KeyError(key)
        names = {f.name for f in dataclasses.fields(sections[sec])}
        if field not in names:
            raise KeyError(key)
        current = getattr(sections[sec], field)
        new = str(value) if isinstance(current, str) else float(value)
        sections[sec] = dataclasses.replace(sections[sec], **{field: new})
    return type(params)(**sections)


class Overridable:
    """Mixin for a params schema: adds ``p.override(mapping)`` (see ``override``)."""

    def override(self, mapping: dict[str, float]):
        return override(self, mapping)
