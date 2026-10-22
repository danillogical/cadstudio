"""Project record and discovery.

A project is a package ``projects/<name>/`` whose ``__init__.py`` defines ``PROJECT``.
Its models are the modules in ``PROJECT.models`` (a package) not starting with ``_``,
each exposing ``build(p) -> dict[str, ModelPart]``.
"""
from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, Callable

import projects

if TYPE_CHECKING:
    import trimesh

    from .checks import CheckResult
    from .model import ModelPart


def _no_checks(mp: ModelPart, p: Any) -> list[CheckResult]:
    return []


def _no_ghosts(p: Any) -> list[tuple[trimesh.Trimesh, str, float]]:
    return []


def _no_views(part_meshes: dict[str, trimesh.Trimesh], p: Any, rdir: Path, want: set[str]) -> dict[str, Path]:
    return {}


@dataclass(frozen=True)
class Project:
    """One CAD project plugged into the cadkit engine.

    name: project name, the ``<project>`` in ``<project>/<model>``.
    params_path: default params TOML.
    load_params: ``load_params(path) -> params`` for this project's schema.
    models: package holding the model modules.
    check_hook: ``check_hook(mp, p) -> list[CheckResult]``, run after ``bed_fit``.
    ghost_meshes: ``ghost_meshes(p) -> [(mesh, color, opacity)]`` drawn translucent after
        the parts in standard views; they also widen the camera bounds.
    extra_views: ``extra_views(part_meshes, p, rdir, want) -> {filename: path}`` for the
        view sets in ``want`` beyond ``standard`` (``detail``, ``sections``).
    physics: ``physics(model_name, p) -> AssemblySpec`` for this model, or ``None`` when the
        project has no physics description. Default: no physics. It takes the **model name**
        as well as the params so one project's distinct models are never all assigned one
        assembly by accident. Called only by ``cad physics``; never imported otherwise.
    physics_with_options: ``physics_with_options(model_name, p, options) -> AssemblySpec`` where
        ``options`` is the parsed top-level table of ``cad physics run --options`` (``{}`` when no
        file is given). Default: none. Called only by ``cad physics run``.
    """
    name: str
    params_path: Path
    load_params: Callable[[Path], Any]
    models: ModuleType
    check_hook: Callable[[ModelPart, Any], list[CheckResult]] = _no_checks
    ghost_meshes: Callable[[Any], list[tuple[trimesh.Trimesh, str, float]]] = _no_ghosts
    extra_views: Callable[[dict[str, trimesh.Trimesh], Any, Path, set[str]], dict[str, Path]] = _no_views
    physics: Callable[[str, Any], Any] | None = None
    physics_with_options: Callable[[str, Any, Mapping[str, Any]], Any] | None = None


def discover() -> dict[str, Project]:
    """All projects, keyed and sorted by name: packages under ``projects/`` that define ``PROJECT``."""
    found: dict[str, Project] = {}
    for info in pkgutil.iter_modules(projects.__path__):
        if not info.ispkg:
            continue
        proj = getattr(importlib.import_module(f"projects.{info.name}"), "PROJECT", None)
        if isinstance(proj, Project):
            found[proj.name] = proj
    return dict(sorted(found.items()))


def list_models(project: Project) -> list[str]:
    """Bare names of the project's model modules not starting with ``_``, sorted."""
    return sorted(m.name for m in pkgutil.iter_modules(project.models.__path__) if not m.name.startswith("_"))


def load_model(project: Project, name: str) -> ModuleType:
    """Import model ``name`` of ``project``; raises ``KeyError`` if it is not a listed model."""
    names = list_models(project)
    if name not in names:
        raise KeyError(f"unknown model {name!r} in project {project.name!r}; available: {', '.join(names)}")
    return importlib.import_module(f"{project.models.__name__}.{name}")


def all_models() -> list[str]:
    """Every model as ``<project>/<model>``, sorted by project then model."""
    return [f"{proj.name}/{m}" for proj in discover().values() for m in list_models(proj)]


def resolve(spec: str) -> tuple[Project, str]:
    """Resolve ``<project>/<model>``, or a bare ``<model>`` that is unique across projects.

    Raises ``KeyError`` with a message for an unknown project or model, or an ambiguous bare name.
    """
    projs = discover()
    proj_name, slash, model = spec.rpartition("/")
    if slash:
        if proj_name not in projs:
            raise KeyError(f"unknown project {proj_name!r}; available: {', '.join(projs)}")
        proj = projs[proj_name]
        if model not in list_models(proj):
            raise KeyError(f"unknown model {spec!r}; available: {', '.join(all_models())}")
        return proj, model
    hits = [proj for proj in projs.values() if model in list_models(proj)]
    if not hits:
        raise KeyError(f"unknown model {spec!r}; available: {', '.join(all_models())}")
    if len(hits) > 1:
        raise KeyError(f"model {spec!r} is ambiguous; use one of: "
                       + ", ".join(f"{proj.name}/{model}" for proj in hits))
    return hits[0], model
