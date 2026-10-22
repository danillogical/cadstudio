"""Collision fidelity: does the declared primitive recipe leave the CAD's voids open?

M2a proved a collider lands where its part is. This module asks the harder question: does the
recipe *represent* the part? A convex hull over a hollow housing seals every opening, and
MuJoCo would happily collide with that hull while the scene still compiled.

The checks here are analytic geometry over the **declared** primitives — they never consult the
compiled model, and they never trust a mesh AABB:

* **probe occupancy** — for each declared critical probe, no collider may contain it;
* **transit** — a swept test object must travel the declared path without intersecting any
  collider, sampled densely enough to catch a wall across the middle;
* **coverage** — every sample of the CAD solid must lie inside some collider, so a recipe
  cannot silently omit a wall;
* **deviation** — the distance from each declared critical surface to the nearest collider,
  in mm, so an over-thick recipe that narrows a real passage is visible.

Everything is in **body-local millimetres**, matching :class:`ColliderSpec`. World placement is
:func:`to_world_mm`, which applies the body frame once.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .schema import BodySpec, ColliderSpec, Frame

#: Below this many transit samples a wall can slip between steps.
MIN_TRANSIT_SAMPLES = 200
#: A collider may intrude this far into a declared void before it is a defect, mm.
VOID_TOL_MM = 0.05


@dataclass(frozen=True)
class ProbeSpec:
    """A point that must remain free of collision geometry, body-local mm.

    Declared, not inferred: the author states where the passage is, and validation holds the
    recipe to it.
    """

    probe_id: str
    points_mm: tuple[tuple[float, float, float], ...]
    note: str = ""

    def validate(self) -> None:
        if not self.probe_id:
            raise ValueError("probe_id must be non-empty")
        if not self.points_mm:
            raise ValueError(f"probe {self.probe_id!r} has no points")
        for p in self.points_mm:
            if len(p) != 3 or not all(math.isfinite(c) for c in p):
                raise ValueError(f"probe {self.probe_id!r} has a bad point {p!r}")


@dataclass(frozen=True)
class TransitSpec:
    """A swept test object that must travel from ``start_mm`` to ``end_mm`` unobstructed."""

    transit_id: str
    start_mm: tuple[float, float, float]
    end_mm: tuple[float, float, float]
    radius_mm: float
    samples: int = 400

    def validate(self) -> None:
        if not self.transit_id:
            raise ValueError("transit_id must be non-empty")
        if not (math.isfinite(self.radius_mm) and self.radius_mm > 0.0):
            raise ValueError(f"transit {self.transit_id!r} needs a positive radius")
        if self.samples < MIN_TRANSIT_SAMPLES:
            raise ValueError(
                f"transit {self.transit_id!r} needs >= {MIN_TRANSIT_SAMPLES} samples, "
                f"got {self.samples}"
            )
        for point in (self.start_mm, self.end_mm):
            if len(point) != 3 or not all(math.isfinite(c) for c in point):
                raise ValueError(f"transit {self.transit_id!r} has a bad endpoint {point!r}")
        if self.start_mm == self.end_mm:
            raise ValueError(f"transit {self.transit_id!r} has zero length")


@dataclass(frozen=True)
class FidelitySpec:
    """Declared fidelity contract for one body: voids, passage and critical surfaces."""

    probes: tuple[ProbeSpec, ...] = ()
    transits: tuple[TransitSpec, ...] = ()
    #: Sample points on surfaces that must stay close to a collider, body-local mm.
    critical_surfaces_mm: tuple[tuple[float, float, float], ...] = ()
    #: Maximum allowed distance from a critical surface point to the nearest collider, mm.
    max_surface_deviation_mm: float = 0.5
    #: Maximum allowed distance from a CAD solid sample to the nearest collider, mm.
    max_coverage_gap_mm: float = 0.5

    def validate(self) -> None:
        for p in self.probes:
            p.validate()
        for t in self.transits:
            t.validate()
        if not (math.isfinite(self.max_surface_deviation_mm)
                and self.max_surface_deviation_mm > 0.0):
            raise ValueError("max_surface_deviation_mm must be positive")
        if not (math.isfinite(self.max_coverage_gap_mm) and self.max_coverage_gap_mm > 0.0):
            raise ValueError("max_coverage_gap_mm must be positive")


@dataclass
class FidelityResult:
    ok: bool
    violations: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "violations": list(self.violations),
                "metrics": {k: float(v) for k, v in self.metrics.items()}}


# --------------------------------------------------------------------------- primitives
def collider_rotation(collider: ColliderSpec) -> np.ndarray:
    """The collider's 3x3 rotation, taken from the same build123d convention as the CAD."""
    return np.asarray(Frame(rot_deg=collider.rot_deg).rotation_matrix(), dtype=float)


def _local(point_mm, collider: ColliderSpec) -> np.ndarray:
    """A body-local point expressed in the collider's own frame, mm.

    The inverse of a rotation is its **transpose**, applied after subtracting the collider
    position. Negating the XYZ Euler angles is *not* the inverse for compound rotations:
    for rot (25, 35, 45) it maps a known interior point outside the box.
    """
    delta = np.asarray(point_mm, dtype=float) - np.asarray(collider.pos_mm, dtype=float)
    if any(collider.rot_deg):
        return collider_rotation(collider).T @ delta
    return delta


def contains(collider: ColliderSpec, point_mm, margin_mm: float = 0.0) -> bool:
    """Is the body-local point inside this primitive (expanded by ``margin_mm``)?"""
    p = _local(point_mm, collider)
    size = collider.size_mm
    if collider.kind == "box":
        hx, hy, hz = (s + margin_mm for s in size)
        return bool(abs(p[0]) <= hx and abs(p[1]) <= hy and abs(p[2]) <= hz)
    if collider.kind == "sphere":
        return bool(np.linalg.norm(p) <= size[0] + margin_mm)
    if collider.kind in ("cylinder", "capsule"):
        radius, half = size
        radial = float(np.hypot(p[0], p[1]))
        if radial > radius + margin_mm:
            return False
        if collider.kind == "cylinder":
            return bool(abs(p[2]) <= half + margin_mm)
        # capsule: rounded ends
        dz = max(0.0, abs(p[2]) - half)
        return bool(math.hypot(radial, dz) <= radius + margin_mm)
    raise ValueError(f"unsupported collider kind {collider.kind!r}")


def distance_mm(collider: ColliderSpec, point_mm) -> float:
    """Distance from a body-local point to the primitive's surface; 0 inside.

    Used for the deviation metric, so it must be the true distance, not a bounding-box proxy.
    """
    p = _local(point_mm, collider)
    size = collider.size_mm
    if collider.kind == "box":
        h = np.asarray(size, dtype=float)
        d = np.abs(p) - h
        outside = np.maximum(d, 0.0)
        return float(np.linalg.norm(outside))
    if collider.kind == "sphere":
        return float(max(0.0, np.linalg.norm(p) - size[0]))
    if collider.kind in ("cylinder", "capsule"):
        radius, half = size
        radial = float(np.hypot(p[0], p[1]))
        if collider.kind == "cylinder":
            dr = max(0.0, radial - radius)
            dz = max(0.0, abs(p[2]) - half)
            return float(math.hypot(dr, dz))
        dz = max(0.0, abs(p[2]) - half)
        return float(max(0.0, math.hypot(radial, dz) - radius))
    raise ValueError(f"unsupported collider kind {collider.kind!r}")


def signed_distance_mm(collider: ColliderSpec, point_mm) -> float:
    """Signed distance to the primitive boundary: negative inside, positive outside, mm.

    ``distance_mm`` returns 0 for every interior point, so it cannot detect a CAD surface
    *buried* under an over-thick collider. The surface-accuracy metric must use this instead.
    """
    d = distance_mm(collider, point_mm)
    if d > 0.0:
        return d
    # inside: the depth is the smallest distance to any boundary
    p = _local(point_mm, collider)
    size = collider.size_mm
    if collider.kind == "box":
        return -float(np.min(np.asarray(size, dtype=float) - np.abs(p)))
    if collider.kind == "sphere":
        return -float(size[0] - np.linalg.norm(p))
    if collider.kind in ("cylinder", "capsule"):
        radius, half = size
        radial = float(np.hypot(p[0], p[1]))
        if collider.kind == "cylinder":
            return -float(min(radius - radial, half - abs(p[2])))
        dz = max(0.0, abs(p[2]) - half)
        return -float(radius - math.hypot(radial, dz))
    raise ValueError(f"unsupported collider kind {collider.kind!r}")


def collider_aabb_mm(collider: ColliderSpec) -> tuple[np.ndarray, np.ndarray]:
    """Body-local axis-aligned bounds of the primitive (conservative for rotated shapes)."""
    size = collider.size_mm
    if collider.kind == "box":
        half = np.asarray(size, dtype=float)
    elif collider.kind == "sphere":
        half = np.full(3, size[0])
    elif collider.kind == "cylinder":
        half = np.array([size[0], size[0], size[1]])
    elif collider.kind == "capsule":
        half = np.array([size[0], size[0], size[1] + size[0]])
    else:
        raise ValueError(f"unsupported collider kind {collider.kind!r}")
    if any(collider.rot_deg):
        # conservative: the circumscribed sphere of the local box
        r = float(np.linalg.norm(half))
        half = np.full(3, r)
    centre = np.asarray(collider.pos_mm, dtype=float)
    return centre - half, centre + half


# --------------------------------------------------------------------------- validation
def validate_fidelity(body: BodySpec, spec: FidelitySpec,
                      colliders: tuple[ColliderSpec, ...] | None = None) -> FidelityResult:
    """Check one body's recipe against its declared voids and passage."""
    spec.validate()
    body.validate()
    if colliders is None:
        colliders = tuple(c for part in body.parts for c in part.colliders)
    if not colliders:
        return FidelityResult(False, [f"body {body.body_id!r} has no colliders to validate"])

    violations: list[str] = []
    metrics: dict[str, float] = {}

    # 1. Probes: a declared free point must not be inside any collider.
    for probe in spec.probes:
        worst = math.inf
        blocked = None
        for point in probe.points_mm:
            for c in colliders:
                if contains(c, point, margin_mm=VOID_TOL_MM):
                    blocked = (c.collider_id, point)
                    break
            nearest = min(distance_mm(c, point) for c in colliders)
            worst = min(worst, nearest)
            if blocked:
                break
        metrics[f"probe_{probe.probe_id}_min_clearance_mm"] = float(worst)
        if blocked:
            cid, point = blocked
            violations.append(
                f"probe {probe.probe_id!r} is occupied by collider {cid!r} at "
                f"{tuple(round(v, 3) for v in point)} mm: the declared void is filled"
            )

    # 2. Transit: sweep a sphere along the declared path.
    for transit in spec.transits:
        start = np.asarray(transit.start_mm, dtype=float)
        end = np.asarray(transit.end_mm, dtype=float)
        worst = math.inf
        first_hit = None
        swept_start = None
        swept_end = None
        for i in range(transit.samples + 1):
            t = i / transit.samples
            point = start + (end - start) * t
            if swept_start is None:
                # The point actually handed to the primitives, not the declared endpoint.
                # A validator that re-transformed the path would report a different value here.
                swept_start = np.array(point, dtype=float)
            swept_end = np.array(point, dtype=float)
            for c in colliders:
                d = distance_mm(c, tuple(point)) - transit.radius_mm
                worst = min(worst, d)
                if d < 0.0 and first_hit is None:
                    first_hit = (c.collider_id, tuple(float(v) for v in point), float(d))
        metrics[f"transit_{transit.transit_id}_min_clearance_mm"] = float(worst)
        # Record the path actually swept. A validator that silently re-transformed the
        # declared body-local points would report different endpoints here, so this is the
        # observable that catches local/world confusion (a displaced path still "passes").
        for axis, value in zip("xyz", swept_start):
            metrics[f"transit_{transit.transit_id}_swept_start_{axis}_mm"] = float(value)
        for axis, value in zip("xyz", swept_end):
            metrics[f"transit_{transit.transit_id}_swept_end_{axis}_mm"] = float(value)
        if first_hit is not None:
            cid, point, d = first_hit
            violations.append(
                f"transit {transit.transit_id!r} is blocked by collider {cid!r} at "
                f"{tuple(round(v, 3) for v in point)} mm "
                f"(overlap {abs(d):.3f} mm > radius {transit.radius_mm} mm)"
            )

    # 3. Coverage: every sample of the CAD solid must be inside some collider, so a recipe
    #    cannot omit a wall.
    if body.parts:
        gaps = []
        for part in body.parts:
            if part.role == "spare" or part.shape is None:
                continue
            for point in _sample_solid(part.shape, body.frame):
                if not any(contains(c, point, margin_mm=spec.max_coverage_gap_mm)
                           for c in colliders):
                    gaps.append((part.part_id, point))
        metrics["coverage_max_gap_mm"] = _max_gap(body, spec, colliders)
        if gaps:
            pid, point = gaps[0]
            violations.append(
                f"part {pid!r} has CAD material at "
                f"{tuple(round(v, 3) for v in point)} mm outside every collider "
                f"({len(gaps)} uncovered samples); the recipe omits real geometry"
            )

    # 4. Deviation at declared critical surfaces.
    if spec.critical_surfaces_mm:
        # Signed distance: a CAD surface buried inside an over-thick collider must show up as
        # a deviation, not as zero.
        devs = [abs(min((signed_distance_mm(c, p) for c in colliders), key=abs))
                for p in spec.critical_surfaces_mm]
        worst = float(max(devs))
        metrics["critical_surface_max_deviation_mm"] = worst
        if worst > spec.max_surface_deviation_mm:
            violations.append(
                f"critical surface deviates {worst:.3f} mm from the nearest collider "
                f"(limit {spec.max_surface_deviation_mm} mm)"
            )

    return FidelityResult(not violations, violations, metrics)


def _sample_solid(shape, frame: Frame, n: int = 400) -> list[tuple[float, float, float]]:
    """Deterministic sample points on the part surface, in **body-local** mm."""
    from ..mesh import shape_to_mesh
    from .scene import body_local_mesh

    mesh = shape_to_mesh(body_local_mesh(shape, frame))
    # deterministic: take every k-th vertex rather than a random surface sample
    verts = np.asarray(mesh.vertices, dtype=float)
    if len(verts) > n:
        idx = np.linspace(0, len(verts) - 1, n).astype(int)
        verts = verts[idx]
    return [tuple(float(c) for c in v) for v in verts]


def _max_gap(body: BodySpec, spec: FidelitySpec,
             colliders: tuple[ColliderSpec, ...]) -> float:
    worst = 0.0
    for part in body.parts:
        if part.role == "spare" or part.shape is None:
            continue
        for point in _sample_solid(part.shape, body.frame):
            nearest = min(distance_mm(c, point) for c in colliders)
            worst = max(worst, nearest)
    return float(worst)


def to_world_mm(frame: Frame, point_mm) -> tuple[float, float, float]:
    """Body-local -> assembly, applied exactly once."""
    return frame.apply(tuple(point_mm))


def transit_world_mm(body: BodySpec, transit: TransitSpec) -> tuple[np.ndarray, np.ndarray]:
    """The declared body-local transit path, mapped into world space exactly once.

    Exposed so a test can assert the path actually lands inside the body's world volume. A
    validator that confused local and world space would still *pass* its own transit check
    (the displaced path misses every collider), so the path itself must be checked.
    """
    start = np.asarray(to_world_mm(body.frame, transit.start_mm), dtype=float)
    end = np.asarray(to_world_mm(body.frame, transit.end_mm), dtype=float)
    return start, end
