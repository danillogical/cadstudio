"""Headless CAD-vs-collider debug overlay: real surfaces and colliders drawn together.

Uses the repository's existing off-screen PyVista path (``cadkit.render`` already depends on it),
so no GUI and no MuJoCo renderer is involved. The output is a PNG that shows, for one body:

* the CAD visual mesh, translucent;
* every declared collider primitive, solid and in a distinct colour;
* the declared transit path, so a blocked passage is visible at a glance.

This is a diagnostic picture, not evidence on its own: the numeric probe/transit/coverage
results in ``collision.py`` are the actual gate.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .schema import BodySpec, ColliderSpec

VISUAL_COLOR = "#9aa4b2"
COLLIDER_COLORS = ("#d1495b", "#00798c", "#edae49", "#30638e", "#8f7aa8", "#6f9a86")
TRANSIT_COLOR = "#2a9d8f"


def _box_mesh(half_mm, centre_mm, rot_deg=(0.0, 0.0, 0.0)):
    import trimesh

    mesh = trimesh.creation.box(extents=[2 * h * 1e-3 for h in half_mm])
    if any(rot_deg):
        from build123d import Rot

        trsf = Rot(*rot_deg).wrapped.Transformation()
        rot = np.array([[trsf.Value(r, c) for c in range(1, 4)] for r in range(1, 4)])
        mesh.apply_transform(np.block([[rot, np.zeros((3, 1))], [np.zeros((1, 3)), 1.0]]))
    mesh.apply_translation([c * 1e-3 for c in centre_mm])
    return mesh


def _apply_pose(mesh, pos_mm, rot_deg):
    """Apply the collider's exact pose: translation, then the CAD's own rotation."""
    if any(rot_deg):
        from build123d import Rot

        trsf = Rot(*rot_deg).wrapped.Transformation()
        rot = np.array([[trsf.Value(r, c) for c in range(1, 4)] for r in range(1, 4)])
        mesh.apply_transform(np.block([[rot, np.zeros((3, 1))], [np.zeros((1, 3)), 1.0]]))
    mesh.apply_translation([c * 1e-3 for c in pos_mm])
    return mesh


def _cylinder_mesh(radius_mm, half_mm, centre_mm, rot_deg=(0.0, 0.0, 0.0)):
    import trimesh

    mesh = trimesh.creation.cylinder(radius=radius_mm * 1e-3, height=2 * half_mm * 1e-3)
    return _apply_pose(mesh, centre_mm, rot_deg)


def _capsule_mesh(radius_mm, half_mm, centre_mm, rot_deg=(0.0, 0.0, 0.0)):
    """A real capsule: a cylinder with hemispherical ends, matching MuJoCo's capsule geom."""
    import trimesh

    parts = [trimesh.creation.cylinder(radius=radius_mm * 1e-3, height=2 * half_mm * 1e-3)]
    for dz in (-half_mm * 1e-3, half_mm * 1e-3):
        sphere = trimesh.creation.icosphere(radius=radius_mm * 1e-3)
        sphere.apply_translation([0.0, 0.0, dz])
        parts.append(sphere)
    mesh = trimesh.util.concatenate(parts)
    return _apply_pose(mesh, centre_mm, rot_deg)


def _sphere_mesh(radius_mm, centre_mm):
    import trimesh

    mesh = trimesh.creation.icosphere(radius=radius_mm * 1e-3)
    mesh.apply_translation([c * 1e-3 for c in centre_mm])
    return mesh


def collider_mesh(collider: ColliderSpec):
    """A display mesh for a declared primitive, in body-local metres."""
    kind, size, pos = collider.kind, collider.size_mm, collider.pos_mm
    if kind == "box":
        return _box_mesh(size, pos, collider.rot_deg)
    if kind == "sphere":
        return _apply_pose(_sphere_mesh(size[0], (0.0, 0.0, 0.0)), pos, collider.rot_deg)
    if kind == "cylinder":
        return _cylinder_mesh(size[0], size[1], pos, collider.rot_deg)
    if kind == "capsule":
        return _capsule_mesh(size[0], size[1], pos, collider.rot_deg)
    raise ValueError(
        f"overlay cannot draw collider kind {kind!r}; refusing to render a misleading shape"
    )


def render_overlay(body: BodySpec, path: Path, *, transits=(), title: str = "") -> Path:
    """Write a PNG showing the CAD surface with the declared colliders over it."""
    import pyvista as pv

    from ..mesh import shape_to_mesh
    from ..render import to_pv
    from .scene import body_local_mesh

    pl = pv.Plotter(off_screen=True, window_size=(1400, 1000))
    pl.set_background("#f4f4f6")

    for part in body.parts:
        if part.shape is None:
            continue
        mesh = shape_to_mesh(body_local_mesh(part.shape, body.frame))
        # The CAD mesher works in millimetres; colliders and the transit path are in metres.
        # Scale here so one picture cannot compare two different unit systems.
        mesh.apply_scale(1e-3)
        pl.add_mesh(to_pv(mesh), color=VISUAL_COLOR, opacity=0.22, smooth_shading=False,
                    label=f"CAD {part.part_id}")

    for i, collider in enumerate(c for part in body.parts for c in part.colliders):
        mesh = collider_mesh(collider)
        pl.add_mesh(to_pv(mesh), color=COLLIDER_COLORS[i % len(COLLIDER_COLORS)],
                    opacity=0.55, label=collider.collider_id)

    for transit in transits:
        start = np.array(transit.start_mm, dtype=float) * 1e-3
        end = np.array(transit.end_mm, dtype=float) * 1e-3
        line = pv.Line(start, end)
        pl.add_mesh(line.tube(radius=max(transit.radius_mm * 1e-3, 1e-4)), color=TRANSIT_COLOR,
                    opacity=0.9, label="transit path")

    # Lower-centre keeps the legend clear of both the axis triad (lower left) and the
    # geometry, which sits in the middle of the frame.
    pl.add_legend(bcolor=(1, 1, 1, 0.9), size=(0.22, 0.14), loc="lower center")
    pl.show_axes()
    if title:
        pl.add_text(title, position="upper_left", color="#222222")
    # Projection must be set before the camera, otherwise PyVista can reset the view.
    pl.enable_parallel_projection()
    pl.camera_position = "iso"
    pl.camera.azimuth = 35
    pl.camera.elevation = 22
    pl.render()

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.screenshot(str(path))
    pl.close()
    return path
