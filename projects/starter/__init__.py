"""Starter: a small example project with a rounded tray and a two-leaf hinge, for the quickstart."""
from __future__ import annotations

from cadkit.project import Project

from . import models
from .checks import check_hook
from .params import DEFAULT_PARAMS_PATH, load_params

PROJECT = Project(
    name="starter",
    params_path=DEFAULT_PARAMS_PATH,
    load_params=load_params,
    models=models,
    check_hook=check_hook,
)
