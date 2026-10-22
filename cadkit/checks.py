"""Generic printability checks for a ModelPart, plus report formatting.

Project-specific checks come from the project's ``check_hook``.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import numpy as np
import trimesh

from .mesh import posed_shape, shape_to_mesh
from .model import ModelPart
from .params import CheckParams, default_min_wall

if TYPE_CHECKING:
    from .project import Project

Status = Literal["pass", "fail", "warn", "info"]

VOLUME_TOL_MM3 = 1e-3
MIN_WALL_SAMPLES = 4000
MIN_WALL_SEED = 0
OVERHANG_ANGLE_DEG = 45.0
MIN_FEATURE_MM = 0.8  # two 0.4 mm extrusion widths
DECOR_SURFACE_TOL_MM = 0.05


@dataclass
class CheckResult:
    """Outcome of one check; ``value`` is the headline number, if any."""
    name: str
    status: Status
    detail: str
    value: float | None = None


def overlap_volume(shape, other) -> float:
    """Volume of shape ∩ other (intersect may return None, a Shape or a ShapeList)."""
    common = shape.intersect(other)
    if common is None:
        return 0.0
    if isinstance(common, (list, tuple)):
        return float(sum(c.volume for c in common))
    return float(common.volume)


def _valid_solid(mp: ModelPart) -> CheckResult:
    n = len(mp.shape.solids())
    ok = bool(mp.shape.is_valid) and n == 1
    return CheckResult("valid_solid", "pass" if ok else "fail",
                       f"is_valid={bool(mp.shape.is_valid)}, solids={n}", float(n))


def _watertight(mesh: trimesh.Trimesh) -> CheckResult:
    ok = bool(mesh.is_watertight)
    return CheckResult("watertight", "pass" if ok else "fail",
                       f"watertight={ok}, {len(mesh.faces)} triangles")


def _bed_fit(mp: ModelPart, p: CheckParams) -> CheckResult:
    bb = posed_shape(mp).bounding_box()
    size = (bb.size.X, bb.size.Y, bb.size.Z)
    bed = (p.printer.bed_x, p.printer.bed_y, p.printer.bed_z)
    zmin = bb.min.Z
    fits = all(s <= b + 1e-6 for s, b in zip(size, bed))
    on_bed = abs(zmin) < 1e-3
    ok = fits and on_bed
    detail = (f"size {size[0]:.1f}x{size[1]:.1f}x{size[2]:.1f} vs bed "
              f"{bed[0]:g}x{bed[1]:g}x{bed[2]:g}; z-min={zmin:.4f}")
    if not on_bed:
        detail += " (not resting on z=0; set print_location)"
    return CheckResult("bed_fit", "pass" if ok else "fail", detail, float(zmin))


def _ray_thickness(mesh: trimesh.Trimesh, n: int = MIN_WALL_SAMPLES):
    """Cast rays inward from sampled surface points; returns (points, thickness, hit mask)."""
    points, face_idx = trimesh.sample.sample_surface(mesh, n, seed=MIN_WALL_SEED)
    normals = mesh.face_normals[face_idx]
    origins = points - normals * 1e-3
    locs, ray_idx, _ = mesh.ray.intersects_location(origins, -normals, multiple_hits=False)
    thick = np.full(len(points), np.nan)
    thick[ray_idx] = np.linalg.norm(locs - origins[ray_idx], axis=1)
    return points, thick


def _min_wall(mesh: trimesh.Trimesh, p: CheckParams, req: float | None = None) -> CheckResult:
    """Ray thickness of ``mesh`` against ``req`` (default: the project's ``structure.min_wall``)."""
    _, thick = _ray_thickness(mesh)
    thick = thick[~np.isnan(thick)]
    if len(thick) == 0:
        return CheckResult("min_wall", "warn", "no ray hits; thickness undetermined")
    tmin = float(thick.min())
    p1 = float(np.percentile(thick, 1))
    req = default_min_wall(p) if req is None else req
    if p1 < req * 0.95:
        status: Status = "fail"
    elif tmin < req * 0.5:
        status = "warn"
    else:
        status = "pass"
    return CheckResult("min_wall", status,
                       f"min {tmin:.2f} mm, 1st pct {p1:.2f} mm (required {req:g}); "
                       f"{len(thick)}/{MIN_WALL_SAMPLES} rays hit", p1)


def _min_feature(shape_mesh: trimesh.Trimesh, base_mesh: trimesh.Trimesh) -> CheckResult:
    """Warn-only thickness check of the decoration-only region (never FAIL).

    Decoration is the part of ``shape``'s surface farther than 0.05 mm from the
    ``wall_shape`` surface. FDM features under about 0.8 mm (two 0.4 mm extrusion
    widths) print poorly, so a 1st-percentile ray thickness below that warns.
    """
    points, thick = _ray_thickness(shape_mesh)
    _, dist, _ = trimesh.proximity.closest_point(base_mesh, points)
    keep = (dist > DECOR_SURFACE_TOL_MM) & ~np.isnan(thick)
    t = thick[keep]
    if len(t) == 0:
        return CheckResult("min_feature", "info", "no decoration-only samples with ray hits")
    tmin = float(t.min())
    p1 = float(np.percentile(t, 1))
    status: Status = "warn" if p1 < MIN_FEATURE_MM else "info"
    return CheckResult("min_feature", status,
                       f"decoration min {tmin:.2f} mm, 1st pct {p1:.2f} mm (warn below "
                       f"{MIN_FEATURE_MM:g}); {len(t)}/{MIN_WALL_SAMPLES} decoration samples", p1)


def _overhangs(mp: ModelPart) -> CheckResult:
    """Area of downward faces needing support, in print pose.

    A face is an overhang when its normal points down and its surface is tilted
    more than 45 deg from vertical (normal within 45 deg of straight down),
    excluding faces lying on the bed (z ~ 0).
    """
    mesh = shape_to_mesh(posed_shape(mp))
    nz = mesh.face_normals[:, 2]
    zmax_per_face = mesh.vertices[mesh.faces][:, :, 2].max(axis=1)
    down = nz < -math.sin(math.radians(OVERHANG_ANGLE_DEG))
    off_bed = zmax_per_face > 1e-3
    area = float(mesh.area_faces[down & off_bed].sum())
    return CheckResult("overhangs", "warn" if area > 1e-6 else "pass",
                       f"{area:.1f} mm^2 of faces needing support", area)


def _mass(mp: ModelPart, p: CheckParams) -> CheckResult:
    vol_mm3 = float(mp.shape.volume)
    cm3 = vol_mm3 / 1000.0
    grams = cm3 * p.material.density_g_cm3
    area = math.pi * (p.material.filament_d / 2) ** 2
    meters = vol_mm3 / area / 1000.0
    return CheckResult("mass", "info",
                       f"{cm3:.2f} cm^3, {grams:.1f} g {p.material.name}, {meters:.2f} m filament",
                       grams)


def run_checks(name: str, mp: ModelPart, p: CheckParams, project: Project) -> list[CheckResult]:
    """Run all checks for one part (``name`` is for caller bookkeeping).

    The project's ``check_hook`` results go right after ``bed_fit``.
    """
    results = [_valid_solid(mp)]
    mesh = shape_to_mesh(mp.shape)
    results.append(_watertight(mesh))
    results.append(_bed_fit(mp, p))
    results.extend(project.check_hook(mp, p))
    if mp.wall_shape is not None:
        base = shape_to_mesh(mp.wall_shape)
        results.append(_min_wall(base, p, mp.min_wall))
        results.append(_min_feature(mesh, base))
    else:
        results.append(_min_wall(mesh, p, mp.min_wall))
    results.append(_overhangs(mp))
    results.append(_mass(mp, p))
    return results


def has_failures(results_by_part: dict[str, list[CheckResult]]) -> bool:
    """True if any check has status ``fail``."""
    return any(r.status == "fail" for rs in results_by_part.values() for r in rs)


def format_report(results_by_part: dict[str, list[CheckResult]]) -> str:
    """Markdown table of all results, with a summary line."""
    counts = {s: 0 for s in ("pass", "fail", "warn", "info")}
    for rs in results_by_part.values():
        for r in rs:
            counts[r.status] += 1
    lines = ["# CAD check report", "",
             "Summary: " + ", ".join(f"{n} {s}" for s, n in counts.items()), "",
             "| part | check | status | detail |", "|---|---|---|---|"]
    for part, rs in results_by_part.items():
        for r in rs:
            lines.append(f"| {part} | {r.name} | {r.status.upper()} | {r.detail} |")
    return "\n".join(lines) + "\n"


def write_report(results_by_part: dict[str, list[CheckResult]], outdir) -> dict[str, Path]:
    """Write ``report.json`` and ``report.md`` into ``outdir``."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    jp, mp_ = outdir / "report.json", outdir / "report.md"
    jp.write_text(json.dumps({k: [asdict(r) for r in v] for k, v in results_by_part.items()}, indent=2))
    mp_.write_text(format_report(results_by_part))
    return {"json": jp, "md": mp_}
