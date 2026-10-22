"""Shared shape -> trimesh conversion."""
from __future__ import annotations

import numpy as np
import trimesh

from .model import ModelPart


def shape_to_mesh(shape, tolerance: float = 0.02, angular: float = 0.1) -> trimesh.Trimesh:
    """Tessellate a build123d shape into a vertex-merged trimesh."""
    verts, tris = shape.tessellate(tolerance, angular)
    v = np.array([[p.X, p.Y, p.Z] for p in verts], dtype=float)
    f = np.array(tris, dtype=np.int64)
    mesh = trimesh.Trimesh(vertices=v, faces=f, process=False)
    mesh.merge_vertices()
    mesh.update_faces(mesh.nondegenerate_faces())
    return mesh


def posed_shape(mp: ModelPart):
    """The part's shape in print pose (identity if no print_location)."""
    return mp.shape if mp.print_location is None else mp.shape.moved(mp.print_location)
