"""Headless renders (PyVista off-screen VTK): standard views of the assembly and print-pose views."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pyvista as pv
import trimesh

from .mesh import posed_shape, shape_to_mesh
from .model import ModelPart

if TYPE_CHECKING:
    from .project import Project

WIDTH = 1400
HEIGHT = 1000
BG_COLOR = "#f2f2f2"
NAMED_COLORS = {"rear": "#5a6270", "front": "#8a8f99"}
EXTRA_COLORS = ("#6f9a86", "#a58f6e", "#8f7aa8", "#a0a266", "#6e97a8")
EDGE_COLOR = "#1a1a1a"
FEATURE_ANGLE = 30.0
# cadkit renders "standard"; the project's extra_views renders the rest.
VIEW_SETS = ("standard", "detail", "sections", "all")


def to_pv(mesh: trimesh.Trimesh) -> pv.PolyData:
    """Convert a triangle trimesh to PyVista PolyData."""
    faces = np.hstack([np.full((len(mesh.faces), 1), 3), mesh.faces]).ravel()
    return pv.PolyData(np.asarray(mesh.vertices), faces)


def _part_color(name: str, index: int) -> str:
    return NAMED_COLORS.get(name) or EXTRA_COLORS[index % len(EXTRA_COLORS)]


def _light_kit(plotter: pv.Plotter) -> None:
    """Key, fill and back lights so faces at different angles get distinct shades."""
    plotter.remove_all_lights()
    for pos, inten in (((1.0, 1.0, 1.5), 1.0), ((-1.5, 0.3, 1.0), 0.6), ((0.0, -1.0, -1.2), 0.4)):
        light = pv.Light(position=pos, focal_point=(0, 0, 0), light_type="camera light", intensity=inten)
        plotter.add_light(light)


def _add_part(plotter: pv.Plotter, mesh: trimesh.Trimesh, color: str) -> None:
    """Mid-tone flat-shaded part with a thin dark feature-edge overlay."""
    poly = to_pv(mesh)
    plotter.add_mesh(poly, color=color, smooth_shading=False, specular=0.3, specular_power=15,
                     ambient=0.35, show_edges=False)
    add_edges(plotter, poly)


def add_edges(plotter: pv.Plotter, poly: pv.PolyData, width: float = 1.0) -> None:
    """Overlay the dark feature edges of ``poly``."""
    edges = poly.extract_feature_edges(feature_angle=FEATURE_ANGLE)
    if edges.n_points:
        plotter.add_mesh(edges, color=EDGE_COLOR, line_width=width, lighting=False)


def _screenshot(plotter: pv.Plotter, path: Path) -> None:
    plotter.set_background(BG_COLOR)
    plotter.screenshot(str(path))
    plotter.close()


def _camera(plotter: pv.Plotter, bounds, direction, up, zoom: float = 1.0) -> None:
    center = np.array([(bounds[0] + bounds[1]) / 2, (bounds[2] + bounds[3]) / 2, (bounds[4] + bounds[5]) / 2])
    diag = float(np.linalg.norm([bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4]]))
    d = np.asarray(direction, dtype=float)
    d /= np.linalg.norm(d)
    plotter.camera_position = [tuple(center + d * diag * 2), tuple(center), tuple(up)]
    plotter.camera.zoom(zoom)


def render_model(parts: dict[str, ModelPart], p: Any, outdir, project: Project,
                 views: str = "all") -> dict[str, Path]:
    """Write PNGs into ``outdir/renders/`` and return ``{filename: path}``.

    ``views`` selects the set: ``standard`` (iso/front/back/top), ``detail``,
    ``sections`` or ``all``. Standard views draw all parts in assembly coordinates,
    then the project's translucent ghost meshes. Every other set comes from the
    project's ``extra_views``.
    """
    if views not in VIEW_SETS:
        raise ValueError(f"views must be one of {VIEW_SETS}, got {views!r}")
    want = {"standard", "detail", "sections"} if views == "all" else {views}
    rdir = Path(outdir) / "renders"
    rdir.mkdir(parents=True, exist_ok=True)
    part_meshes = {n: shape_to_mesh(mp.shape) for n, mp in parts.items()}
    written: dict[str, Path] = {}

    if "standard" in want:
        ghosts = project.ghost_meshes(p)
        # The camera frames the ghosts and the parts together.
        bounds = None
        for mesh in [g[0] for g in ghosts] + list(part_meshes.values()):
            b = np.array(mesh.bounds).T.ravel()
            bounds = b if bounds is None else [
                min(bounds[0], b[0]), max(bounds[1], b[1]), min(bounds[2], b[2]),
                max(bounds[3], b[3]), min(bounds[4], b[4]), max(bounds[5], b[5])]
        std_views = {
            "iso": ((1.0, -1.2, 1.0), (0, 1, 0), 1.15),
            "front": ((0, 0, 1), (0, 1, 0), 1.0),
            "back": ((0, 0, -1), (0, 1, 0), 1.0),
            "top": ((0, 1, 0), (0, 0, 1), 1.0),
        }
        for vname, (direction, up, zoom) in std_views.items():
            pl = pv.Plotter(off_screen=True, window_size=(WIDTH, HEIGHT))
            _light_kit(pl)
            for i, (n, mesh) in enumerate(part_meshes.items()):
                _add_part(pl, mesh, _part_color(n, i))
            for mesh, color, opacity in ghosts:
                pl.add_mesh(to_pv(mesh), color=color, opacity=opacity)
            pl.show_axes()
            _camera(pl, bounds, direction, up, zoom)
            path = rdir / f"{vname}.png"
            _screenshot(pl, path)
            written[path.name] = path

    written.update(project.extra_views(part_meshes, p, rdir, want - {"standard"}))
    return written


def render_part(name: str, mp: ModelPart, outdir) -> Path:
    """Iso render of one part in print pose to ``outdir/renders/<name>_print.png``."""
    rdir = Path(outdir) / "renders"
    rdir.mkdir(parents=True, exist_ok=True)
    mesh = shape_to_mesh(posed_shape(mp))
    pl = pv.Plotter(off_screen=True, window_size=(WIDTH, HEIGHT))
    _light_kit(pl)
    _add_part(pl, mesh, _part_color(name, 0))
    b = mesh.bounds
    size = float(np.max(b[1] - b[0]))
    cx, cy = (b[0][0] + b[1][0]) / 2, (b[0][1] + b[1][1]) / 2
    bed = pv.Plane(center=(cx, cy, 0), direction=(0, 0, 1), i_size=size * 1.6, j_size=size * 1.6)
    pl.add_mesh(bed, color="#c8c8c8", opacity=0.6)
    pl.show_axes()
    _camera(pl, [b[0][0], b[1][0], b[0][1], b[1][1], b[0][2], b[1][2]], (1, -1.2, 1), (0, 0, 1))
    path = rdir / f"{name}_print.png"
    _screenshot(pl, path)
    return path
