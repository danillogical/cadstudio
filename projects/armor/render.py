"""Armor renders: lid/screen ghosts for the standard views, plus the detail and section views.

Detail views cover parts named ``front`` and ``rear``; sections cut through the lid at fixed
heights and draw the lid (red) and screen (blue) outlines.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pyvista as pv
import trimesh
from matplotlib.patches import PathPatch, Rectangle
from matplotlib.path import Path as MplPath

from cadkit.mesh import shape_to_mesh
from cadkit.render import BG_COLOR, HEIGHT, WIDTH, add_edges, to_pv

from .params import Params, lid_envelope, screen_prism

PART_COLOR = "#444444"  # section fill
SIDE_WALL_HALF_SPAN = 25.0
HEIGHT_CMAP = "turbo"
DETAIL_WINDOW = (90.0, 60.0)  # mm, corner close-up size
SCALE_BAR_STEPS = (1, 2, 5, 10, 20, 50, 100, 200)
LID_GHOST = ("#6fa8dc", 0.22)
SCREEN_GHOST = ("#3d85c6", 0.35)


def ghost_meshes(p: Params) -> list[tuple[trimesh.Trimesh, str, float]]:
    """Translucent lid envelope, then the screen area as a thin slab on the lid face."""
    lid_mesh = shape_to_mesh(lid_envelope(p))
    # Draw the screen as a thin slab on the lid face; the full prism would hide the bezel.
    screen_mesh = shape_to_mesh(screen_prism(p)).slice_plane([0, 0, p.lid_z1 + 0.3], [0, 0, -1], cap=True)
    return [(lid_mesh, *LID_GHOST), (screen_mesh, *SCREEN_GHOST)]


def extra_views(part_meshes: dict[str, trimesh.Trimesh], p: Params, rdir: Path, want: set[str]) -> dict[str, Path]:
    """``detail`` close-ups of front/rear and ``sections`` through the lid, for the sets in ``want``."""
    written: dict[str, Path] = {}
    if "detail" in want:
        written.update(_render_details(part_meshes, rdir))

    if "sections" in want:
        for yv in (p.lid.h * 0.5, p.lid.h - 10):
            path = rdir / f"section_y{yv:g}.png"
            _section_xz(part_meshes, p, yv, path)
            written[path.name] = path
        xv = p.lid.w / 2 - 5
        path = rdir / f"section_x{xv:g}.png"
        _section_yz(part_meshes, p, xv, path)
        written[path.name] = path
    return written


# ----------------------------------------------------------------- detail views

def _nice_bar_mm(width_mm: float) -> float:
    """Largest round scale-bar length not exceeding ~25% of the view width."""
    ok = [b for b in SCALE_BAR_STEPS if b <= width_mm * 0.25]
    return float(ok[-1]) if ok else float(SCALE_BAR_STEPS[0])


def _detail_view(mesh: trimesh.Trimesh, path: Path, title: str, cbar_label: str, *, view_dir: int,
                 window: tuple[float, float, float, float] | None = None, mirror: bool = False,
                 depth: bool = False) -> Path:
    """Orthographic height/depth-coloured render of ``mesh`` with edges, title and mm scale bar.

    ``view_dir`` is -1 to look down -Z from z>0 or +1 to look along +Z from z<0.
    ``window`` is (x0, x1, y0, y1) in mm, default the whole mesh. ``mirror`` flips
    the image horizontally so back-face text reads correctly.
    """
    b = mesh.bounds
    x0, x1, y0, y1 = window if window else (b[0][0], b[1][0], b[0][1], b[1][1])
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    aspect = WIDTH / HEIGHT
    half_h = max((y1 - y0) / 2, (x1 - x0) / 2 / aspect) * 1.04
    half_w = half_h * aspect
    zmin, zmax = float(b[0][2]), float(b[1][2])

    poly = to_pv(mesh)
    z = np.asarray(mesh.vertices)[:, 2]
    poly["h"] = (z - zmin) if depth else z
    clim = (0.0, zmax - zmin) if depth else (zmin, zmax)
    pl = pv.Plotter(off_screen=True, window_size=(WIDTH, HEIGHT))
    pl.set_background(BG_COLOR)
    pl.add_mesh(poly, scalars="h", cmap=HEIGHT_CMAP, clim=clim, lighting=False, show_scalar_bar=False)
    add_edges(pl, poly, width=1.0)
    span = max(zmax - zmin, 1.0) * 4 + 100
    cam_z = zmax + span if view_dir < 0 else zmin - span
    pl.camera_position = [(cx, cy, cam_z), (cx, cy, (zmin + zmax) / 2), (0, 1, 0)]
    pl.camera.parallel_projection = True
    pl.camera.parallel_scale = half_h
    pl.reset_camera_clipping_range()
    img = pl.screenshot(return_img=True)
    pl.close()
    if mirror:
        img = img[:, ::-1]

    fig, ax = plt.subplots(figsize=(WIDTH / 100, HEIGHT / 100 + 0.6))
    ax.imshow(img, extent=(cx - half_w, cx + half_w, cy - half_h, cy + half_h), origin="upper")
    ax.set_title(title, fontsize=11)
    ax.set_xlabel("X (mm)" + (" (mirrored view)" if mirror else ""))
    ax.set_ylabel("Y (mm)")
    sm = plt.cm.ScalarMappable(cmap=HEIGHT_CMAP, norm=plt.Normalize(*clim))
    fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.02, label=cbar_label)
    bar = _nice_bar_mm(2 * half_w)
    bx = cx - half_w + 0.04 * 2 * half_w
    by = cy - half_h + 0.05 * 2 * half_h
    ax.plot([bx, bx + bar], [by, by], color="black", lw=4, solid_capstyle="butt")
    ax.text(bx + bar / 2, by + 0.015 * 2 * half_h, f"{bar:g} mm", ha="center", va="bottom", fontsize=10,
            bbox=dict(facecolor="white", alpha=0.7, edgecolor="none", pad=1.5))
    fig.tight_layout()
    _save(fig, path)
    return path


def _render_details(part_meshes: dict[str, trimesh.Trimesh], rdir: Path) -> dict[str, Path]:
    """detail_front_{full,tl,br}.png and detail_rear_full.png for parts named front/rear."""
    out: dict[str, Path] = {}
    if "front" in part_meshes:
        m = part_meshes["front"]
        b = m.bounds
        ww, wh = DETAIL_WINDOW
        zr = f"z {b[0][2]:.1f}..{b[1][2]:.1f} mm"
        label = "height Z (mm)"
        jobs = {
            "detail_front_full.png": (None, f"Front part, view -Z, colour = height ({zr})"),
            "detail_front_tl.png": ((b[0][0], b[0][0] + ww, b[1][1] - wh, b[1][1]),
                                    f"Front part, top-left {ww:g}x{wh:g} mm, colour = height ({zr})"),
            "detail_front_br.png": ((b[1][0] - ww, b[1][0], b[0][1], b[0][1] + wh),
                                    f"Front part, bottom-right {ww:g}x{wh:g} mm, colour = height ({zr})"),
        }
        for fname, (window, title) in jobs.items():
            out[fname] = _detail_view(m, rdir / fname, title, label, view_dir=-1, window=window)
    if "rear" in part_meshes:
        m = part_meshes["rear"]
        out["detail_rear_full.png"] = _detail_view(
            m, rdir / "detail_rear_full.png",
            "Rear part, seen from back (view +Z from z<0), mirrored horizontally so back text reads; colour = depth",
            "depth from rear face (mm)", view_dir=1, mirror=True, depth=True)
    return out


# ---------------------------------------------------------------- sections

def _section_rings(mesh: trimesh.Trimesh, axis: int, value: float, cols: tuple[int, int]):
    normal = np.zeros(3)
    normal[axis] = 1.0
    origin = np.zeros(3)
    origin[axis] = value
    sec = mesh.section(plane_normal=normal, plane_origin=origin)
    if sec is None:
        return []
    return [np.asarray(d)[:, list(cols)] for d in sec.discrete if len(d) >= 3]


def _signed_area(r: np.ndarray) -> float:
    x, y = r[:, 0], r[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _fill_patch(rings: list[np.ndarray]) -> PathPatch | None:
    """Compound path with orientation set by nesting depth so holes render as holes."""
    if not rings:
        return None
    verts, codes = [], []
    for i, r in enumerate(rings):
        depth = sum(1 for j, o in enumerate(rings)
                    if j != i and MplPath(o).contains_point(r[0]))
        want_ccw = depth % 2 == 0
        if (_signed_area(r) > 0) != want_ccw:
            r = r[::-1]
        verts.extend(r.tolist() + [r[0].tolist()])
        codes.extend([MplPath.MOVETO] + [MplPath.LINETO] * (len(r) - 1) + [MplPath.CLOSEPOLY])
    return PathPatch(MplPath(verts, codes), facecolor=PART_COLOR, edgecolor="black", lw=0.6)


def _draw_inset(ax, rings_all, rects_red, rects_blue, xlim, ylim, xlabel, ylabel, title):
    for rings in rings_all:
        patch = _fill_patch(rings)
        if patch is not None:
            ax.add_patch(patch)
    for (x0, x1, y0, y1) in rects_red:
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, edgecolor="red", lw=1.5))
    for (x0, x1, y0, y1) in rects_blue:
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, edgecolor="blue", lw=1.5, ls="--"))
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_aspect("equal")
    ax.grid(True, color="#cccccc", lw=0.5)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=10)


def _save(fig, path: Path) -> None:
    fig.savefig(path, dpi=100, facecolor="#fafafa")
    plt.close(fig)


def _section_xz(meshes, p: Params, y: float, path: Path) -> None:
    """XZ plane at height ``y``: left and right side-wall insets side by side."""
    rings = [_section_rings(m, 1, y, (0, 2)) for m in meshes.values()]
    hw = p.lid.w / 2
    zlim = (-3.0, p.total_t + 3.0)
    red = [(-hw, hw, p.lid_z0, p.lid_z1)]
    in_screen = p.screen.bottom <= y <= p.screen.bottom + p.screen.h
    blue = [(-p.screen.w / 2, p.screen.w / 2, p.lid_z1, p.total_t + 50.0)] if in_screen else []
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH / 100, 4.2))
    for ax, edge, side in zip(axes, (-hw, hw), ("left edge", "right edge")):
        _draw_inset(ax, rings, red, blue, (edge - SIDE_WALL_HALF_SPAN, edge + SIDE_WALL_HALF_SPAN),
                    zlim, "X (mm)", "Z (mm)", f"XZ section at y={y:g} mm, {side}")
    fig.tight_layout()
    _save(fig, path)


def _section_yz(meshes, p: Params, x: float, path: Path) -> None:
    """YZ plane at ``x``: insets at the hinge edge and the top edge."""
    rings = [_section_rings(m, 0, x, (1, 2)) for m in meshes.values()]
    zlim = (-3.0, p.total_t + 3.0)
    red = [(-50.0, p.lid.h, p.lid_z0, p.lid_z1)]
    in_screen = abs(x) <= p.screen.w / 2
    blue = [(p.screen.bottom, p.screen.bottom + p.screen.h, p.lid_z1, p.total_t + 50.0)] if in_screen else []
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH / 100, 4.2))
    for ax, centre, side in zip(axes, (0.0, p.lid.h), ("hinge edge", "top edge")):
        _draw_inset(ax, rings, red, blue, (centre - SIDE_WALL_HALF_SPAN - 10, centre + SIDE_WALL_HALF_SPAN + 10),
                    zlim, "Y (mm)", "Z (mm)", f"YZ section at x={x:g} mm, {side}")
    fig.tight_layout()
    _save(fig, path)
