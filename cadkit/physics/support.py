"""Support geometry: does a bearing footprint hold a body's centre of mass?

Pure planar geometry in millimetres, with no MuJoCo import, so scenario authors and tests can
call it without the physics stack. Given the contact patches a body rests on, it reports the
convex hull of those patches, how far the centre of mass sits inside or outside it, and the
gravity moment that tends to tip the body off the support.

Degenerate supports are handled explicitly rather than by a tolerance on the area: collinear
patches are a line segment and a lone point is a point, both with zero area and zero width.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

#: Relative tolerance for treating hull points as collinear (scaled by the point spread squared).
COLLINEAR_REL_TOL = 1e-12
#: A COM this close to a line support counts as lying on it, mm.
ON_SEGMENT_TOL_MM = 1e-9


@dataclass(frozen=True)
class SupportMargin:
    """Result of :func:`support_margin`; lengths in mm, area in mm^2, moment in N*m."""

    hull_area_mm2: float
    strip_width_mm: float
    com_inside: bool
    #: Signed distance from the COM (xy) to the hull boundary: positive inside, negative outside.
    com_margin_mm: float
    #: weight_n * max(0, -com_margin_mm) / 1000, the moment tending to tip off the support.
    gravity_moment_nm: float


def _hull(points: np.ndarray) -> np.ndarray:
    """Convex hull by monotone chain, counter-clockwise, collinear points dropped."""
    pts = np.unique(points, axis=0)
    if len(pts) <= 2:
        return pts
    spread = float(np.ptp(pts, axis=0).max())
    eps = COLLINEAR_REL_TOL * spread * spread

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    chains = []
    for seq in (pts, pts[::-1]):
        chain: list[np.ndarray] = []
        for p in seq:
            while len(chain) >= 2 and cross(chain[-2], chain[-1], p) <= eps:
                chain.pop()
            chain.append(p)
        chains.append(chain[:-1])
    hull = chains[0] + chains[1]
    # A collinear set collapses both chains onto the two extremes.
    return np.array(hull if len(hull) >= 3 else [pts[0], pts[-1]])


def _dist_to_segment(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    ab = b - a
    denom = float(ab @ ab)
    t = 0.0 if denom == 0.0 else min(1.0, max(0.0, float((p - a) @ ab) / denom))
    return float(np.linalg.norm(p - (a + t * ab)))


def _min_width(hull: np.ndarray) -> float:
    """Minimum hull width: over hull edges, the largest point distance to that edge's line."""
    best = math.inf
    n = len(hull)
    for i in range(n):
        a, b = hull[i], hull[(i + 1) % n]
        edge = b - a
        normal = np.array([-edge[1], edge[0]]) / np.linalg.norm(edge)
        best = min(best, float(np.max(np.abs((hull - a) @ normal))))
    return best


def support_margin(com_xy_mm, patches_xy_mm, weight_n) -> SupportMargin:
    """Hull, strip width and COM margin for patches (each a sequence of (x, y) corners), mm."""
    com = np.asarray(com_xy_mm, dtype=float).reshape(-1)
    if com.shape != (2,) or not np.all(np.isfinite(com)):
        raise ValueError(f"com_xy_mm must be two finite numbers, got {com_xy_mm!r}")
    weight = float(weight_n)
    if not math.isfinite(weight) or weight < 0.0:
        raise ValueError(f"weight_n must be finite and non-negative, got {weight_n!r}")
    rows = [np.asarray(p, dtype=float).reshape(-1, 2) for p in patches_xy_mm]
    rows = [r for r in rows if len(r)]
    if not rows:
        raise ValueError("support_margin needs at least one patch with at least one point")
    points = np.vstack(rows)
    if not np.all(np.isfinite(points)):
        raise ValueError("patch points must be finite")

    hull = _hull(points)
    if len(hull) == 1:
        # Degenerate: every point coincident.
        dist = float(np.linalg.norm(com - hull[0]))
        margin, inside, area, width = -dist, dist <= ON_SEGMENT_TOL_MM, 0.0, 0.0
        if inside:
            margin = 0.0
    elif len(hull) == 2:
        # Degenerate: a line segment has no interior, so only "on it" counts as inside.
        dist = _dist_to_segment(com, hull[0], hull[1])
        inside = dist <= ON_SEGMENT_TOL_MM
        margin, area, width = (0.0 if inside else -dist), 0.0, 0.0
    else:
        x, y = hull[:, 0], hull[:, 1]
        area = 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))
        width = _min_width(hull)
        edges = [(hull[i], hull[(i + 1) % len(hull)]) for i in range(len(hull))]
        edge_dist = min(_dist_to_segment(com, a, b) for a, b in edges)
        # Hull is counter-clockwise, so inside means left of (or on) every edge.
        inside = all(
            (b[0] - a[0]) * (com[1] - a[1]) - (b[1] - a[1]) * (com[0] - a[0]) >= 0.0
            for a, b in edges
        )
        margin = edge_dist if inside else -edge_dist
    return SupportMargin(
        hull_area_mm2=float(area),
        strip_width_mm=float(width),
        com_inside=bool(inside),
        com_margin_mm=float(margin),
        gravity_moment_nm=weight * max(0.0, -margin) / 1000.0,
    )


def bearing_carries(load_direction, contact_normal) -> bool:
    """True if the contact pushes against the load; normal points from support into the body."""
    load = np.asarray(load_direction, dtype=float).reshape(-1)
    normal = np.asarray(contact_normal, dtype=float).reshape(-1)
    for name, v in (("load_direction", load), ("contact_normal", normal)):
        if v.shape != (3,) or not np.all(np.isfinite(v)):
            raise ValueError(f"{name} must be three finite numbers")
        if np.linalg.norm(v) == 0.0:
            raise ValueError(f"{name} must be non-zero")
    return bool(float(load @ normal) < 0.0)
