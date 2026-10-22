"""Pocky packet dispenser: a manual spring-return mechanism that ejects one packet from a stack."""
from __future__ import annotations

from cadkit.project import Project

from . import models
from .params import DEFAULT_PARAMS_PATH, load_params


def _ghost_meshes(p):
    from cadkit.mesh import shape_to_mesh

    from .geometry.linkage import ghost_packet_shapes

    bottom, second = ghost_packet_shapes(p)
    return [
        (shape_to_mesh(bottom), "#1f4e79", 0.35),
        (shape_to_mesh(second), "#c45911", 0.28),
    ]


PROJECT = Project(
    name="pocky",
    params_path=DEFAULT_PARAMS_PATH,
    load_params=load_params,
    models=models,
    ghost_meshes=_ghost_meshes,
)
