"""Lid armor: a two-piece slide-on shell for the Lenovo IdeaPad 3 Chromebook 11AST5 display lid."""
from __future__ import annotations

from cadkit.project import Project

from . import models
from .checks import check_hook
from .params import DEFAULT_PARAMS_PATH, load_params


def _ghost_meshes(p):
    from .render import ghost_meshes  # lazy: keeps pyvista/matplotlib out of `cad list`
    return ghost_meshes(p)


def _extra_views(part_meshes, p, rdir, want):
    from .render import extra_views
    return extra_views(part_meshes, p, rdir, want)


PROJECT = Project(
    name="armor",
    params_path=DEFAULT_PARAMS_PATH,
    load_params=load_params,
    models=models,
    check_hook=check_hook,
    ghost_meshes=_ghost_meshes,
    extra_views=_extra_views,
)
