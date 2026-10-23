"""Explicit convex collider recipes for the original Pocky prototype.

Every collider is a box, cylinder or capsule in **body-local** millimetres. The recipes are
written feature by feature from the CAD helpers in ``geometry/linkage.py`` and
``geometry/prototype.py``; no part is hulled and no declared void is filled. The fidelity
contracts in this module declare the openings, transit paths and critical planar surfaces the
recipe must preserve, and are checked by ``cadkit.physics.scene.export_scene`` before a scene
can compile.

Bodies use identity frames, so body-local coordinates are the fraction-0 assembly coordinates.
The crank is the one exception in construction only: its recipe is written in the crank's own
pivot frame and then rotated by the actual fraction-0 crank angle, exactly as the CAD builds
it.

Friction: PETG is μ=0.40 priority 0; the analytic floor is μ=0.50 priority 0. The torsional
and rolling terms are the declared assembly values. All values are assumed, not measured.
"""
from __future__ import annotations

import functools
import math
from dataclasses import dataclass

from build123d import Compound, Plane, extrude

from cadkit.physics.collision import FidelitySpec, ProbeSpec, TransitSpec
from cadkit.physics.schema import ColliderSpec, Source

from projects.pocky.geometry.linkage import (
    FACE_W,
    LUG_Y,
    NOSE_R,
    Z_GAP,
    floor_slot_bounds,
    phi_for_button_fraction,
    pose_at_phi,
    pusher_slot_ends,
)
from projects.pocky.geometry.prototype import (
    BAR_Z0,
    BAR_Z1,
    BULLNOSE_Z,
    CHASSIS_Z0,
    DEFAULT_GAP,
    FRONT_WALL_Z,
    HEAD_EXTRA,
    HEAD_UPPER_Y,
    LEDGE_Z,
    PEG_D,
    PROTO_SLOT_W,
    PROTOTYPE_SPRING,
    ROD_PAD_X,
    ROD_PAD_T,
    SPRING_AMPLITUDE,
    SPRING_Y,
    SPRING_Z0,
    _rod_features,
    _spring_web,
    _swept,
    _tube,
    compressed_length,
    moving_solids,
    static_solids,
)
from projects.pocky.params import Params

PETG_FRICTION = (0.40, 0.005, 0.0001)
FLOOR_FRICTION = (0.50, 0.005, 0.0001)
PETG_PRIORITY = 0
#: Fidelity limits from the approved plan: 0.5 mm non-critical coverage, 0.02 mm critical.
COVERAGE_GAP_MM = 0.5
CRITICAL_TOL_MM = 0.02
#: The f=1 pusher-peg head relief: one local circle, not a long strip.
RELIEF_R = PEG_D / 2.0 + HEAD_EXTRA / 2.0 + 0.4
#: The body floor skin left above the relief cut (CAD cut ends at z = -0.01).
RELIEF_CEILING_Z = -0.01
#: Chassis hook and stop constants, read back from the CAD helpers where they are exported.
_STOP_EPS = 0.05
_CHASSIS_WALL = 2.4


# --------------------------------------------------------------------------- primitives
def _src(note: str) -> Source:
    return Source("derived", note)


def _b(cid: str, bounds, note: str, *, role: str = "structure",
       friction: tuple[float, float, float] = PETG_FRICTION,
       priority: int = PETG_PRIORITY) -> ColliderSpec:
    """Axis-aligned box from ``(x0, x1, y0, y1, z0, z1)`` body-local mm."""
    x0, x1, y0, y1, z0, z1 = (float(v) for v in bounds)
    if x1 <= x0 or y1 <= y0 or z1 <= z0:
        raise ValueError(f"empty collider box {cid!r}: {bounds!r}")
    return ColliderSpec(
        collider_id=cid, kind="box",
        size_mm=((x1 - x0) / 2.0, (y1 - y0) / 2.0, (z1 - z0) / 2.0),
        pos_mm=((x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0),
        role=role, source=_src(note), friction=friction, priority=priority,
    )


def _rz(px: float, py: float, phi_deg: float, x: float, y: float) -> tuple[float, float]:
    """Rotate a local point about ``(px, py)`` by ``phi_deg`` (CAD Rot Z convention)."""
    th = math.radians(phi_deg)
    c, s = math.cos(th), math.sin(th)
    return (px + x * c - y * s, py + x * s + y * c)


def _rb(cid: str, bounds, phi_deg: float, pivot, note: str, *, role: str = "structure",
        friction: tuple[float, float, float] = PETG_FRICTION) -> ColliderSpec:
    """Box authored in a local frame, then rotated by the CAD's own Z rotation."""
    x0, x1, y0, y1, z0, z1 = (float(v) for v in bounds)
    if x1 <= x0 or y1 <= y0 or z1 <= z0:
        raise ValueError(f"empty collider box {cid!r}: {bounds!r}")
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    wx, wy = _rz(pivot[0], pivot[1], phi_deg, cx, cy)
    return ColliderSpec(
        collider_id=cid, kind="box",
        size_mm=((x1 - x0) / 2.0, (y1 - y0) / 2.0, (z1 - z0) / 2.0),
        pos_mm=(wx, wy, (z0 + z1) / 2.0),
        rot_deg=(0.0, 0.0, phi_deg),
        role=role, source=_src(note), friction=friction, priority=PETG_PRIORITY,
    )


def _cyl(cid: str, x: float, y: float, z0: float, z1: float, radius: float, note: str,
         *, role: str = "structure", rot_deg=(0.0, 0.0, 0.0),
         friction: tuple[float, float, float] = PETG_FRICTION) -> ColliderSpec:
    if z1 <= z0:
        raise ValueError(f"empty collider cylinder {cid!r}")
    return ColliderSpec(
        collider_id=cid, kind="cylinder", size_mm=(radius, (z1 - z0) / 2.0),
        pos_mm=(x, y, (z0 + z1) / 2.0), rot_deg=rot_deg,
        role=role, source=_src(note), friction=friction, priority=PETG_PRIORITY,
    )


def _ring_sectors(prefix: str, cx: float, cy: float, z0: float, z1: float,
                  ri: float, ro: float, n: int, note: str,
                  *, phi_deg: float = 0.0, pivot=(0.0, 0.0),
                  role: str = "structure") -> list[ColliderSpec]:
    """Approximate an annulus by ``n`` tangent boxes (a declared polygon, not a solid disc).

    The inner boundary is the circumscribed polygon of radius ``ri``: it never enters the
    bore, and the outer boundary under-covers the true cylinder by at most
    ``ro * (1/cos(pi/n) - 1)`` mm. At n=12 and ro=7 that is 0.24 mm, below the 0.5 mm
    non-critical coverage limit. The bore itself is a declared probe exception.
    """
    if n < 6:
        raise ValueError("a ring needs at least 6 sectors")
    half_r = (ro - ri) / 2.0
    rmid = (ri + ro) / 2.0
    half_t = ro * math.tan(math.pi / n)
    out = []
    for k in range(n):
        th = 2.0 * math.pi * k / n
        lx, ly = rmid * math.cos(th), rmid * math.sin(th)
        wx, wy = _rz(pivot[0], pivot[1], phi_deg, lx, ly)
        out.append(ColliderSpec(
            collider_id=f"{prefix}_{k:02d}", kind="box",
            size_mm=(half_r, half_t, (z1 - z0) / 2.0),
            pos_mm=(wx, wy, (z0 + z1) / 2.0),
            rot_deg=(0.0, 0.0, phi_deg + math.degrees(th)),
            role=role, source=_src(note), friction=PETG_FRICTION, priority=PETG_PRIORITY,
        ))
    return out


def _tangent_cap(prefix: str, cx: float, cy: float, radius: float, normals_deg,
                 radial_out: float, tangential_half: float, z0: float, z1: float,
                 note: str, *, role: str = "structure") -> list[ColliderSpec]:
    """Boxes covering the material outside a circular slot end, from tangent planes.

    Each box lies on the outward side of one tangent line to the circle. The union is the
    material outside the circumscribed polygon: the declared void is never entered, and the
    under-covered sliver between the circle and a tangent chord is at most
    ``radius * (1/cos(half-angle) - 1)`` mm.
    """
    half_r = (radial_out - radius) / 2.0
    rmid = (radius + radial_out) / 2.0
    out = []
    for i, deg in enumerate(normals_deg):
        th = math.radians(deg)
        lx, ly = rmid * math.cos(th), rmid * math.sin(th)
        out.append(ColliderSpec(
            collider_id=f"{prefix}_{i:02d}", kind="box",
            size_mm=(half_r, tangential_half, (z1 - z0) / 2.0),
            pos_mm=(cx + lx, cy + ly, (z0 + z1) / 2.0),
            rot_deg=(0.0, 0.0, deg),
            role=role, source=_src(note), friction=PETG_FRICTION, priority=PETG_PRIORITY,
        ))
    return out


def _plate_with_hole(prefix: str, bounds, cx: float, cy: float, radius: float,
                     z0: float, z1: float, note: str,
                     *, role: str = "structure") -> list[ColliderSpec]:
    """A plate split around an octagonal hole of inradius ``radius``.

    Four boxes outside a square of half-size ``square``, plus eight tangent slabs that cover
    the square outside the circumscribed octagon. The hole contains the true circle, so a
    head in the relief never touches a collider; the over-cut is at most
    ``radius * (1/cos(pi/8) - 1)`` mm (0.36 mm at 4.4 mm).
    """
    x0, x1, y0, y1 = (float(v) for v in bounds)
    square = 7.5
    radial_out = square * math.sqrt(2.0) + 0.1
    if not (x0 < cx - square and cx + square < x1 and y0 < cy - square and cy + square < y1):
        raise ValueError("plate_with_hole needs the square inside the plate")
    out = [
        _b(f"{prefix}_east", (cx + square, x1, y0, y1, z0, z1), note, role=role),
        _b(f"{prefix}_west", (x0, cx - square, y0, y1, z0, z1), note, role=role),
        _b(f"{prefix}_north", (cx - square, cx + square, cy + square, y1, z0, z1), note, role=role),
        _b(f"{prefix}_south", (cx - square, cx + square, y0, cy - square, z0, z1), note, role=role),
    ]
    out.extend(_tangent_cap(
        f"{prefix}_slab", cx, cy, radius,
        [45.0 * k for k in range(8)], radial_out, square, z0, z1, note, role=role,
    ))
    return out


# --------------------------------------------------------------------------- void grids
#: The plan's dense probe pitch. Narrow features use a finer pitch, never a coarser one.
VOID_GRID_STEP_MM = 5.0
#: Keep every grid point this far inside the declared region so it cannot sit on a CAD face.
VOID_GRID_INSET_MM = 0.5
#: Clearance demanded from every *other* installed part's exact CAD. ``is_inside`` with a
#: tolerance classifies ON-face points as blocked, so a grid point cannot graze material
#: that a 0.15 mm sphere would intersect. Tangent points (0.15 mm) remain valid.
VOID_GRID_CLEARANCE_MM = 0.15
#: The classifier tolerance, just below the required clearance, so exact tangency survives.
_GRID_CLEARANCE_TOL = VOID_GRID_CLEARANCE_MM - 1.0e-4


@functools.lru_cache(maxsize=8)
def _installed_cad(p: Params, link) -> dict:
    """The fraction-0 installed CAD solids, exactly as the assembly groups them.

    Cached per process: building the body solid dominates the export cost once, and the
    fidelity contracts for all six bodies read the same shapes. The bench ``dummy`` and the
    parked ``shim_08`` are not installed and are omitted.
    """
    static = static_solids(p, link, DEFAULT_GAP)
    pose = pose_at_phi(link, link.phi0)
    moving = moving_solids(p, link, pose, compressed_length(0.0))
    return {**static, **moving}


#: BodySpec part groupings. A welded peg is part of its carrier's group, never empty space.
_WELD_GROUPS = {
    "body": ("body", "shim_04_a", "shim_04_b"),
    "lip": ("lip",),
    "chassis": ("chassis", "spring_seat", "peg_pivot"),
    "crank": ("crank", "peg_pusher"),
    "rod": ("rod", "peg_button", "spring"),
    "pusher": ("pusher",),
}


def _cad_groups(p: Params, link, body_id: str):
    """Own-group solids and every other installed solid, both exact at fraction 0.

    ``others`` is a sequence of ``(part_id, shape)`` pairs so a point of another installed
    part can be attributed to that part rather than silently disappearing.
    """
    cad = _installed_cad(p, link)
    own_ids = _WELD_GROUPS[body_id]
    own = tuple(cad[name] for name in own_ids)
    others = tuple((name, shape) for name, shape in cad.items()
                   if name not in own_ids and name != "dummy")
    return own, others


def _grid(lo: float, hi: float, step: float) -> tuple[float, ...]:
    """Deterministic half-offset coordinates spanning ``[lo, hi]`` with pitch <= ``step``."""
    if not (hi > lo) or not (step > 0.0):
        return ()
    n = max(1, math.ceil((hi - lo) / step - 1e-12))
    return tuple(lo + (i + 0.5) * (hi - lo) / n for i in range(n))


def _box_grid(bounds, steps, keep=None) -> tuple[tuple[float, float, float], ...]:
    xs = _grid(bounds[0], bounds[1], steps[0])
    ys = _grid(bounds[2], bounds[3], steps[1])
    zs = _grid(bounds[4], bounds[5], steps[2])
    points = ((x, y, z) for x in xs for y in ys for z in zs)
    if keep is not None:
        points = (point for point in points if keep(point))
    return tuple(points)


def _inside_any(shapes, point) -> bool:
    return any(shape.is_inside(point) for shape in shapes)


@dataclass(frozen=True)
class VoidOccupancy:
    """How one declared probe grid relates to the installed CAD at fraction 0.

    Two different facts are recorded separately, because they are different guarantees:

    * ``own_void`` — every kept probe point. A point is dropped **only** when it lies inside
      the tested carrier's **own welded group**: that is the carrier's own material, and a
      probe there could never be a legitimate void. Every surviving point is the carrier's
      own-void guarantee, and it survives any other body moving.
    * ``other_occupied`` — the subset of ``own_void`` that is also inside some *independently
      moving* installed part at fraction 0. That is initial assembly occupancy, not a property
      of the carrier's void. It is an **annotation on a kept point**, never a filter: such a
      point stays in ``own_void`` and stays a probe, because another body's CAD sitting there
      at fraction 0 does not shrink the carrier's void and the carrier's collider must still
      not fill it. The accounting identity is therefore ``other_occupied`` ⊆ ``own_void`` and
      ``own_void_count`` equals the declared probe count exactly (no point is ever deleted
      for other-body occupancy).

    The concrete numbers on the current assembly: ``crank:button_slot_grid`` keeps 48 points
    and annotates 28 of them as ``peg_button`` occupancy; ``pusher:y_slot_grid`` keeps 48 and
    annotates 16 as ``peg_pusher``; ``chassis:rod_corridor_grid`` keeps 1455 and annotates 650
    across ``rod`` (572), ``peg_button`` (39), ``spring`` (27) and ``crank`` (12). Those pegs
    are welded to *their own* carriers (``peg_button`` to the rod, ``peg_pusher`` to the
    crank), so from the tested carrier's point of view they are independent bodies, not own
    material. Because they are annotated rather than deleted, the counted points are still
    coverage for the tested carrier.

    ``initial_overlap`` is the separate, additional guarantee that the *compiled* scene has
    no exact overlap at fraction 0 (``clearance_audit.initial_validity_audit``); it is never
    used as proof of the void contract.
    """

    probe_id: str
    body_id: str
    own_void: tuple[tuple[float, float, float], ...]
    other_occupied: tuple[tuple[str, tuple[float, float, float]], ...]

    @property
    def own_void_count(self) -> int:
        return len(self.own_void)

    @property
    def other_occupied_count(self) -> int:
        return len(self.other_occupied)

    def to_dict(self) -> dict:
        return {
            "probe_id": self.probe_id,
            "body_id": self.body_id,
            "own_void_points": self.own_void_count,
            "other_occupied_points": self.other_occupied_count,
            "other_occupied_by_part": _count_by_part(self.other_occupied),
        }


def _count_by_part(rows) -> dict[str, int]:
    out: dict[str, int] = {}
    for name, _point in rows:
        out[name] = out.get(name, 0) + 1
    return out


#: Every declared grid's occupancy classification, keyed ``(body_id, probe_id)``. Filled
#: while the fidelity contracts are built, so the export report and the tests can audit
#: exactly which points were own-void and which were another body's initial occupancy.
_OCCUPANCY: dict[tuple[str, str], VoidOccupancy] = {}


def occupancy_report() -> dict:
    """The recorded own-void / other-occupancy classification for every dense grid."""
    return {f"{body}:{probe}": row.to_dict() for (body, probe), row in sorted(_OCCUPANCY.items())}


def _classify(point, own_shapes, other_shapes):
    """``(own_material, other_part_name)`` for one point against the installed CAD."""
    if _inside_any(own_shapes, point):
        return True, None
    for name, shape in other_shapes:
        if shape.is_inside(point, _GRID_CLEARANCE_TOL):
            return False, name
    return False, None


def _void_grid(points, own_shapes, other_shapes=(), *, body_id="", probe_id=""):
    """Keep every point of the carrier's own void; classify other-body occupancy separately.

    A point inside the tested carrier's **own welded group** is the carrier's own material,
    not a void, so it is dropped. Every other candidate point is kept as a probe: a point
    inside an independently moving part is still the carrier's own void, and the carrier's
    collider must not fill it. Another body's CAD sitting there at fraction 0 does not make
    the carrier's void smaller, and treating it as a reason to delete coverage is exactly the
    silent weakening this contract must not do.

    ``other_shapes`` is a sequence of ``(part_id, shape)`` pairs, used only for the
    classification recorded in :data:`_OCCUPANCY`: which body occupies the point at fraction
    0, and how many points that is. The audit is reported, never subtracted from coverage.
    The separate initial-overlap guarantee comes from the compiled
    ``initial_validity_audit``; it is an additional gate, not proof of this one.
    """
    pairs = tuple(other_shapes)
    boxes = [(name, shape, shape.bounding_box()) for name, shape in pairs]
    margin = VOID_GRID_CLEARANCE_MM
    kept = []
    occupied = []
    for point in points:
        if _inside_any(own_shapes, point):
            continue
        kept.append(point)
        for name, shape, box in boxes:
            if (box.min.X - margin < point[0] < box.max.X + margin
                    and box.min.Y - margin < point[1] < box.max.Y + margin
                    and box.min.Z - margin < point[2] < box.max.Z + margin
                    and shape.is_inside(point, _GRID_CLEARANCE_TOL)):
                occupied.append((name, point))
                break
    if body_id and probe_id:
        _OCCUPANCY[(body_id, probe_id)] = VoidOccupancy(
            probe_id=probe_id, body_id=body_id,
            own_void=tuple(kept), other_occupied=tuple(occupied),
        )
    return tuple(kept)


def _sector_grid(cx, cy, radius, step, z0, z1, zstep):
    """A deterministic square grid clipped to a circle, with a conservative radial inset."""
    inner = radius - VOID_GRID_INSET_MM

    def keep(point):
        return math.hypot(point[0] - cx, point[1] - cy) <= inner

    return _box_grid(
        (cx - radius, cx + radius, cy - radius, cy + radius, z0, z1),
        (step, step, zstep), keep,
    )


def _ring_points(cx, cy, radius, count, z):
    """Evenly spaced points on a circle; used where the void is a narrow annular gap."""
    return tuple(
        (cx + radius * math.cos(2.0 * math.pi * k / count),
         cy + radius * math.sin(2.0 * math.pi * k / count), z)
        for k in range(count)
    )


def _dense_probe(probe_id: str, points, note: str, *, minimum: int = 4) -> ProbeSpec:
    """A grid probe, rejected at build time if it is too sparse to be meaningful."""
    if len(points) < minimum:
        raise ValueError(
            f"dense void probe {probe_id!r} has only {len(points)} points; "
            "the declared region is occupied or the bounds are wrong"
        )
    return ProbeSpec(probe_id, tuple(points), note)


# ------------------------------------------------------------------- swept-rod corridor
#: Target pitch for the swept-corridor lattice. Narrow features adapt down to
#: :data:`CORRIDOR_MIN_PITCH_MM`; nothing is ever coarser than :data:`VOID_GRID_STEP_MM`.
CORRIDOR_PITCH_MM = 2.0
CORRIDOR_MIN_PITCH_MM = 0.6
#: Inset used when clipping corridor lattice points off the corridor's own boundary.
CORRIDOR_INSET_MM = 0.2
#: A corridor probe point must sit this far inside the corridor surface, so the probe cannot
#: graze the swept volume it is supposed to protect.
CORRIDOR_MIN_INSIDE_MM = 0.15


def _x_stations(shape) -> tuple[float, ...]:
    """Every x where the shape's cross-section is piecewise constant, plus the ones where it
    is not, plus the axis of every surface of revolution.

    Three sources, because the shape is a boolean of boxes and pegs:

    * Vertex x values: the corner stations of every planar band.
    * Face bounding-box x values: tangency stations that are not vertices (a cylinder's
      extreme x can lie on a face interior).
    * The x of every **surface of revolution's axis**. A cylinder or cone about Z does not
      have a constant YZ section across its x extent; the section is a circular arc whose
      radius changes continuously with x. Splitting at the axis separates the two sides.

    What the stations alone still do **not** give is a constant section inside a revolution
    band, and the section there is not even monotone or nested (measured: a section 1.0 mm
    from the peg axis is not contained in the section 0.5 mm from it). So the caller both
    subdivides the bands and unions each interval's endpoint sections rather than trusting any
    single section. See :func:`_rod_corridor_prisms`.
    """
    xs = {round(v.X, 7) for v in shape.vertices()}
    for face in shape.faces():
        box = face.bounding_box()
        xs.add(round(box.min.X, 7))
        xs.add(round(box.max.X, 7))
    # Add each revolution axis from the shared helper, so the axis rule exists in one place.
    xs.update(_revolution_axes(shape))
    return tuple(sorted(xs))


#: How many sub-intervals an interval that overlaps a revolution band is split into. Inside a
#: band the section varies continuously with x, so splitting bounds the enclosing-prism excess
#: by the lens between two nearby circular sections instead of the whole peg radius.
CORRIDOR_BAND_SUBDIVISIONS = 4


def _revolution_bands(shape) -> tuple[tuple[float, float], ...]:
    """The x extent of every surface of revolution that is not parallel to the sweep.

    The *extent*, not just the axis position: the Ø7 head is a cylinder spanning
    ``axis ± 3.5`` mm, and the section varies across that whole span, not only at the axis.
    Subdividing only the interval that contains the axis leaves most of the band unsplit.
    """
    bands = []
    for face in shape.faces():
        if str(face.geom_type).split(".")[-1] not in ("CYLINDER", "CONE", "SPHERE", "TORUS"):
            continue
        try:
            axis = face.axis_of_rotation
        except Exception:  # pragma: no cover - a sphere has no axis; its bbox suffices
            continue
        if abs(abs(axis.direction.X) - 1.0) < 1e-9:
            # Revolution about X: the section is constant along x, no band to split.
            continue
        box = face.bounding_box()
        bands.append((round(box.min.X, 7), round(box.max.X, 7)))
    return tuple(sorted(bands))


def _revolution_axes(shape) -> tuple[float, ...]:
    """The x of every surface-of-revolution axis that is not already parallel to X."""
    out = set()
    for face in shape.faces():
        if str(face.geom_type).split(".")[-1] not in ("CYLINDER", "CONE", "SPHERE", "TORUS"):
            continue
        try:
            axis = face.axis_of_rotation
        except Exception:  # pragma: no cover
            continue
        if abs(abs(axis.direction.X) - 1.0) > 1e-9:
            out.add(round(axis.position.X, 7))
    return tuple(sorted(out))


@functools.lru_cache(maxsize=4)
def _rod_corridor_prisms(p: Params, link) -> tuple:
    """The swept rod-group volume over the full stroke, as prism pieces that contain it.

    The rod group (rod + welded button peg) only translates along X by
    ``link.button_stroke``, so its swept volume is the Minkowski sum of the group with that
    segment. The motion is toward **−X**: the group's leftmost x is −70.853 mm at fraction 0
    and −93.947 mm at fraction 1. That sum is **not** the union of the two endpoint copies:
    the rod is not convex, so the flange, shoulder, pad, beam and web each sweep their own x
    interval (measured: the two-copy union is 18,450 mm3 for the rod alone against 27,552.66
    mm3 for the converged sweep of the rod-plus-peg group).

    **Why this is not an exact piecewise-prismatic decomposition, and what it is instead.**
    The group's 34 planar faces are all axis-aligned, so between planar stations the YZ
    section is genuinely constant. But 4 of its faces are surfaces of revolution about Z at
    the button-peg axis (three cylinders: the Ø4 grip, the Ø7 head spanning ``axis ± 3.5``, and
    the Ø4.1 pin bore wall; one cone: the tip chamfer). Inside those bands the section is a
    circular arc whose radius varies continuously with x, so *no* set of x stations makes the
    section constant there, and a single midpoint section is neither the exact section nor
    even a superset. Measured against the 241-copy converged sweep, the construction that
    shipped in the unaccepted partial snapshot (no axis station, no subdivision, one midpoint
    section per interval) missed **3.8391 mm3** of true swept material: unsafe under-coverage,
    exactly the failure mode this contract exists to prevent. Adding the axis station alone
    makes it *worse* (45.5516 mm3), because splitting the band at its widest point leaves each
    half covered only at its midpoint. Band subdivision alone still misses 4.3422 mm3.

    Two separate mechanisms are therefore in play, and they do different jobs:

    * The **multi-section union** is what produces containment. Unioning the interval's three
      sections with no band subdivision at all already misses only 1.6e-9 mm3.
    * **Band subdivision** is what makes the enclosure *tight*. Without it the same union
      encloses 24.195 mm3 of slack; with it, 8.123 mm3. It does not by itself give containment
      (subdivision alone still misses 4.3422 mm3), because a single midpoint section per
      sub-interval is still one section.

    Both are kept because containment without tightness would make the corridor's probes
    reject colliders that are legal in the true swept volume. See
    ``out/mujoco-m5a/fidelity-finalize/worker-review/negatives.json`` for all four variants.

    The construction here is therefore an enclosing one:

    * Split x at the stations from :func:`_x_stations`, which includes the revolution axis.
    * Subdivide every interval that overlaps a revolution band
      (:data:`CORRIDOR_BAND_SUBDIVISIONS`), using the bands' full x extents.
    * Within each interval take the exact CAD section at the interval's two ends **and** its
      midpoint, move all three into one plane, and union them. On the planar intervals the
      three sections are identical, so the union is exactly the section. In a revolution band
      the union covers the interval's variation.
    * Extrude that section along the interval **plus the stroke**.

    **What is proven and what is measured.** On a planar interval the section is provably
    constant, so those prisms are exact. In a revolution band the section is *not* nested and
    *not* monotone: measured on a single plane, the section area is 74.95 mm2 at the peg axis
    and 43.99 mm2 at 3.4 mm out, but a section 1.0 mm out is **not** contained in the section
    0.5 mm out (0.164 mm2 lies outside it), because the Ø4.1 pin bore and the head's z extent
    vary independently. A monotonicity or nesting argument would therefore be false. What *is*
    established is the property the contract needs, by direct measurement against a 241-copy
    converged reference sweep: the corridor contains the true swept volume with **1.1e-8 mm3**
    missing (boolean noise), enclosing **8.123 mm3** of slack, 0.029% of the 27,552.6598 mm3
    sweep, confined to the peg-head band ``x -93.047..-62.953, z -11.6..-4.6``. Containment is
    verified at a sampling density far finer than the construction, and it is re-verified by
    ``test_rod_corridor_contains_the_true_swept_cad_volume``, so a coarser construction fails
    loudly instead of silently under-covering.

    The pieces are returned separately, not fused: a fused solid would lose the per-prism
    cross-section that makes a lattice sample the corridor's thin bands, and sampling one
    bounding box instead is the defect this contract exists to prevent. Cached: about 0.3 s
    once per process.
    """
    rest = pose_at_phi(link, link.phi0)
    moving = moving_solids(p, link, rest, compressed_length(0.0))
    group = (moving["rod"] + moving["peg_button"]).solid()
    stroke = link.button_stroke
    bands = _revolution_bands(group)
    stations = _band_subdivided(_x_stations(group), bands)
    pieces = []
    for a, b in zip(stations, stations[1:]):
        if b - a < 1.0e-7:
            continue
        mid = 0.5 * (a + b)
        sections = []
        for x in (a + _STATION_EPS, mid, b - _STATION_EPS):
            # Take the section on ONE plane. Cutting with a thin box returns both faces of
            # the slab, and near a tangency that doubles the measured area (149.9 mm2 at the
            # peg axis against a true 74.95 mm2). Plane.YZ.offset(x) returns the single face
            # where the plane meets the solid, which is the section.
            faces = (group & Plane.YZ.offset(x)).faces()
            if not faces:
                continue
            section = faces[0]
            for extra in faces[1:]:
                section = section + extra
            if float(section.area) <= 1.0e-9:
                continue
            # The sections come from three different planes, so they must be moved into a
            # common plane *before* being unioned. Unioning faces that sit at different x
            # yields a non-coplanar compound, and extruding that would emit one full-length
            # prism per sample: measured 5,685 mm3 of spurious material.
            sections.append(_shift_x(section, mid - x))
        if not sections:
            continue
        section = sections[0]
        for extra in sections[1:]:
            section = section + extra
        length = (b - a) + stroke
        piece = extrude(section, amount=length, dir=(1.0, 0.0, 0.0))
        pieces.append(_shift_x(piece, (a - stroke) - mid))
    if not pieces:
        raise ValueError("the swept rod corridor has no pieces; the CAD section failed")
    return tuple(pieces)


#: Offset used when sampling a section at an interval end, so the plane does not graze the
#: station's own degenerate tangency.
_STATION_EPS = 1.0e-5


def _band_subdivided(stations, bands) -> tuple[float, ...]:
    """Subdivide every interval that overlaps a revolution band.

    An interval wholly outside every band has a constant section, so it is left alone. An
    interval that overlaps a band has a section varying continuously with x over the overlap,
    so it is split into :data:`CORRIDOR_BAND_SUBDIVISIONS` equal parts. The bands are face
    extents, so this covers the Ø7 head's full ``axis ± 3.5`` span, not only the axis.
    """
    if not bands:
        return tuple(stations)
    out = [stations[0]]
    for a, b in zip(stations, stations[1:]):
        overlaps = any(lo < b - 1e-9 and hi > a + 1e-9 for lo, hi in bands)
        if overlaps and b - a > 1e-7:
            n = CORRIDOR_BAND_SUBDIVISIONS
            out.extend(a + (b - a) * i / n for i in range(1, n))
        out.append(b)
    return tuple(sorted({round(v, 7) for v in out}))


def _rod_corridor(p: Params, link):
    """The swept rod corridor as one shape, for CAD overlap checks and tests.

    The union is returned as a ``Compound`` rather than coerced to a single ``Solid``. The
    enclosing sections make the peg band's prism overlap its neighbours without always
    merging cleanly, and ``.solid()`` raises when the boolean result is more than one solid.
    A compound is the honest type for "this is the region", and every consumer
    (``is_inside``, boolean difference, volume) works on it unchanged.
    """
    prisms = _rod_corridor_prisms(p, link)
    corridor = prisms[0]
    for piece in prisms[1:]:
        corridor = corridor + piece
    return corridor if isinstance(corridor, Compound) else Compound(children=[corridor])


def _shift_x(shape, dx: float):
    from build123d import Pos

    return Pos(dx, 0.0, 0.0) * shape


def _corridor_points(prisms, *, pitch: float = CORRIDOR_PITCH_MM):
    """A lattice strictly inside the corridor, adapted to each prism's local thickness.

    Each prism is sampled over its own bounding box and clipped to itself, so every band of
    the swept volume is covered in three dimensions. The pitch adapts down for thin pieces:
    the 10 x 4 mm shaft needs a z pitch under 4 mm to place more than one plane, and a single
    plane there is exactly how the named 6 mm blocker at (-82, -28, -10.9) used to escape.
    Nothing is coarser than the plan's 5 mm.
    """
    points: list[tuple[float, float, float]] = []
    seen: set[tuple[float, float, float]] = set()
    for piece in prisms:
        box = piece.bounding_box()
        spans = (box.max.X - box.min.X, box.max.Y - box.min.Y, box.max.Z - box.min.Z)
        steps = tuple(min(VOID_GRID_STEP_MM, max(pitch, span / 3.0, CORRIDOR_MIN_PITCH_MM))
                      for span in spans)
        for x in _grid(box.min.X, box.max.X, steps[0]):
            for y in _grid(box.min.Y, box.max.Y, steps[1]):
                for z in _grid(box.min.Z, box.max.Z, steps[2]):
                    if not piece.is_inside((x, y, z), -CORRIDOR_MIN_INSIDE_MM):
                        continue
                    key = (round(x, 6), round(y, 6), round(z, 6))
                    if key in seen:
                        continue
                    seen.add(key)
                    points.append(key)
    return tuple(points)


# --------------------------------------------------------------------------- body
def _tube_values(p: Params, link) -> dict:
    return _tube(p, link)


def body_colliders(p: Params, link, gap: float = DEFAULT_GAP) -> tuple[ColliderSpec, ...]:
    """Housing: floor split around the through-slot and the **local** f=1 peg relief."""
    t = _tube_values(p, link)
    sx0, sx1, sy0, sy1 = floor_slot_bounds(link)
    wall = t["wall"]
    z0, z1 = link.floor_z0, link.floor_z1
    top = t["top"]
    out: list[ColliderSpec] = []

    # Floor. The slot is open through the floor; the back wall bridges it above z=0.
    out.append(_b("floor_rear", (t["floor_x0"], sx0, -t["oy"], t["oy"], z0, z1), "body floor, rear of slot"))
    out.append(_b("floor_front", (sx1, t["ox1"], -t["oy"], t["oy"], z0, z1), "body floor, front of slot"))
    out.append(_b("floor_south", (sx0, sx1, -t["oy"], sy0, z0, z1), "body floor, south of slot"))
    out.append(_b("floor_north_a", (sx0, -56.9, sy1, t["oy"], z0, z1), "body floor, north of slot, west of relief"))
    out.append(_b("floor_north_c", (-49.1, sx1, sy1, t["oy"], z0, z1), "body floor, north of slot, east of relief"))

    # The f=1 relief is a single local circle. Tile the north strip in x bands so the
    # collider follows the circle instead of filling it or cutting a long strip.
    f1 = pose_at_phi(link, phi_for_button_fraction(link, 1.0))
    rcx, rcy = f1.pusher_pin_x, f1.pusher_pin_y
    n_bands = 20
    xa, xb = -56.9, -49.1
    for i in range(n_bands):
        x0 = xa + (xb - xa) * i / n_bands
        x1 = xa + (xb - xa) * (i + 1) / n_bands
        # Use the band's nearest x to the relief centre (0 if the band contains it), so
        # the collider never reaches inside the circle. It under-covers the CAD material on
        # the far side of the band by at most ~0.3 mm, inside the
        # 0.5 mm non-critical coverage limit.
        if x0 <= rcx <= x1:
            dx = 0.0
        else:
            dx = min(abs(x0 - rcx), abs(x1 - rcx))
        if dx >= RELIEF_R:
            y_cut = t["oy"]
        else:
            y_cut = min(t["oy"], rcy - math.sqrt(RELIEF_R * RELIEF_R - dx * dx))
        if y_cut > sy1 + 1e-6:
            out.append(_b(
                f"floor_north_relief_{i:02d}", (x0, x1, sy1, y_cut, z0, RELIEF_CEILING_Z),
                "body floor north strip, local f=1 peg-head relief scallop",
            ))
    # The CAD relief cut stops 0.01 mm below the floor top, leaving a thin skin. Model it
    # explicitly so the relief ceiling is a real collider face, not a filled void.
    out.append(_b("floor_relief_skin", (xa, xb, sy1, t["oy"], RELIEF_CEILING_Z, z1),
                  "body floor skin above the f=1 relief cut"))

    # Side walls. The relief lowers the north wall's underside to the cut ceiling over its
    # x band; elsewhere the wall starts at the CAD's -0.2 mm bridge.
    out.append(_b("side_north_w", (t["ox0"], xa, t["y1"], t["oy"], z1 - 0.2, top), "body north side wall"))
    out.append(_b("side_north_relief", (xa, xb, t["y1"], t["oy"], RELIEF_CEILING_Z, top),
                  "body north side wall above the relief"))
    out.append(_b("side_north_e", (xb, t["ox1"], t["y1"], t["oy"], z1 - 0.2, top), "body north side wall"))
    out.append(_b("side_south", (t["ox0"], t["ox1"], -t["oy"], t["y0"], z1 - 0.2, top), "body south side wall"))

    # Back wall, split around the bullnose notch (x -87.6..-84.95, y +-20.2, z<=4.4).
    out.append(_b("back_lower_n", (t["ox0"], t["x0"], 20.2, t["oy"], z1 - 0.2, BULLNOSE_Z),
                  "body back wall beside the bullnose notch"))
    out.append(_b("back_lower_s", (t["ox0"], t["x0"], -t["oy"], -20.2, z1 - 0.2, BULLNOSE_Z),
                  "body back wall beside the bullnose notch"))
    out.append(_b("back_upper", (t["ox0"], t["x0"], -t["oy"], t["oy"], BULLNOSE_Z, top),
                  "body back wall above the bullnose notch (chamfer approximated)"))

    out.append(_b("front_wall", (t["x1"], t["ox1"], t["y0"] - 0.2, t["y1"] + 0.2,
                                 FRONT_WALL_Z, top),
                  "body front wall above the exit (chamfer approximated)"))

    ledge_y = 6.0
    for sign, tag in ((1.0, "n"), (-1.0, "s")):
        y_in = sign * t["y1"]
        y_out = sign * (t["y1"] + ledge_y)
        lo, hi = sorted((y_in, y_out))
        out.append(_b(f"ledge_{tag}", (t["ox1"] - 1.0, t["ox1"] + 8.0, lo, hi,
                                       LEDGE_Z - wall, LEDGE_Z),
                      "body shim ledge"))

    out.append(_b("rib_n", (60.0, 74.0, t["oy"] - 0.2, t["oy"] + 2.6, z0, z1),
                  "body chassis-hook rib"))
    out.append(_b("rib_s", (-40.0, -26.0, -t["oy"] - 2.6, -t["oy"] + 0.2, z0, z1),
                  "body chassis-hook rib"))

    # Lip-hook bars and ties. The -Y bar stops short of the button head.
    for sign, tag in ((1.0, "n"), (-1.0, "s")):
        inner = sign * (t["oy"] - 0.4)
        outer = sign * (t["oy"] + 3.6)
        if sign < 0:
            outer = max(outer, HEAD_UPPER_Y + 0.8)
        by0, by1 = sorted((inner, outer))
        out.append(_b(f"bar_{tag}", (t["ox1"] - 1.0, t["ox1"] + 4.0, by0, by1, BAR_Z0, BAR_Z1),
                      "body lip-hook bar"))
        tie_inner = by0 if abs(by0) <= abs(by1) else by1
        ty0, ty1 = sorted((tie_inner - sign * 0.8, tie_inner + sign * 1.6))
        out.append(_b(f"tie_{tag}", (t["ox1"] - 4.0, t["ox1"] + 0.2, ty0, ty1, BAR_Z0, BAR_Z1),
                      "body lip-hook tie"))

    # Installed shims are welded to the body; they are separate CAD parts, so they need
    # their own exact boxes for coverage and mass.
    shim_t = gap - LEDGE_Z
    for sign, tag in ((1.0, "a"), (-1.0, "b")):
        y_in = sign * (t["y1"] + 0.4)
        y_out = sign * (t["y1"] + 5.4)
        lo, hi = sorted((y_in, y_out))
        out.append(_b(f"shim_04_{tag}", (t["ox1"] + 0.4, t["ox1"] + 6.6, lo, hi,
                                         LEDGE_Z, LEDGE_Z + shim_t),
                      "installed 0.4 mm shim plate"))
    return tuple(out)


def body_fidelity(p: Params, link) -> FidelitySpec:
    t = _tube_values(p, link)
    f1 = pose_at_phi(link, phi_for_button_fraction(link, 1.0))
    rcx, rcy = f1.pusher_pin_x, f1.pusher_pin_y
    own, others = _cad_groups(p, link, "body")
    sx0, sx1, sy0, sy1 = floor_slot_bounds(link)

    bore_grid = _dense_probe(
        "bore_grid",
        _void_grid(_box_grid(
            (t["x0"], t["x1"], t["y0"], t["y1"], link.floor_z1, t["top"]),
            (VOID_GRID_STEP_MM, VOID_GRID_STEP_MM, VOID_GRID_STEP_MM),
        ), own, others, body_id="body", probe_id="bore_grid"),
        "magazine bore: 5 mm grid over the actual tube interior (x +/-85, y +/-30, z 0..72)",
        minimum=1000,
    )
    exit_grid = _dense_probe(
        "exit_grid",
        _void_grid(_box_grid(
            (t["x1"], t["ox1"], -t["y1"], t["y1"], link.floor_z1, FRONT_WALL_Z - 2.6),
            (1.5, VOID_GRID_STEP_MM, 2.0),
        ), own, others, body_id="body", probe_id="exit_grid"),
        "packet exit: 1.5 mm across the 3 mm front wall, both lateral sides, below the chamfer",
        minimum=30,
    )
    slot_grid = _dense_probe(
        "floor_slot_grid",
        _void_grid(_box_grid(
            (sx0, sx1, sy0, sy1, link.floor_z0, link.floor_z1),
            (VOID_GRID_STEP_MM, 1.75, 1.2),
        ), own, others, body_id="body", probe_id="floor_slot_grid"),
        "through floor slot: 5 mm along the stroke, adapted across the 7 mm width",
        minimum=20,
    )
    relief_grid = _dense_probe(
        "peg_relief_grid",
        _void_grid(_sector_grid(
            rcx, rcy, RELIEF_R, 1.5, link.floor_z0, RELIEF_CEILING_Z, 1.2,
        ), own, others, body_id="body", probe_id="peg_relief_grid"),
        "local f=1 pusher-peg relief: 1.5 mm grid clipped to the actual cut circle",
        minimum=8,
    )
    notch_grid = _dense_probe(
        "back_notch_grid",
        _void_grid(_box_grid(
            (t["ox0"] - 0.2, t["x0"] + 0.05, -FACE_W / 2.0 - 0.2, FACE_W / 2.0 + 0.2,
             -0.02, BULLNOSE_Z),
            (1.3, VOID_GRID_STEP_MM, 1.1),
        ), own, others, body_id="body", probe_id="back_notch_grid"),
        "bullnose back-wall notch: 1.3 mm through the 2.65 mm wall, 5 mm across",
        minimum=12,
    )

    probes = [
        ProbeSpec("floor_slot", (
            (sx0 + 1.1, 0.0, -1.2), (-70.0, 0.0, -1.2),
            (-50.0, 0.0, -1.2), (-36.0, 0.0, -1.2),
        ), "through-slot boundary seeds; the west seed clears the resting pusher neck"),
        slot_grid,
        ProbeSpec("back_notch", (
            (t["ox0"] + 1.4, 0.0, 2.0),
            (t["ox0"] + 1.4, 15.0, 1.0),
            (t["ox0"] + 1.4, -15.0, 1.0),
        ), "bullnose notch through the back wall"),
        notch_grid,
        ProbeSpec("peg_relief", (
            (rcx, rcy - 3.0, -1.2),
            (rcx + 1.0, rcy - 3.5, -1.2),
            (rcx - 1.0, rcy - 3.5, -1.2),
        ), "local f=1 pusher-peg head relief"),
        relief_grid,
        ProbeSpec("bore", (
            (0.0, 0.0, 10.0), (0.0, 20.0, 30.0), (60.0, -20.0, 50.0), (-60.0, 25.0, 40.0),
        ), "magazine bore boundary seeds"),
        bore_grid,
        ProbeSpec("exit", ((86.5, 0.0, 5.0), (86.5, 20.0, 2.0)),
                  "packet exit boundary seeds"),
        exit_grid,
    ]
    transits = [
        TransitSpec("pusher_neck_path", (-89.0, 0.0, -0.4), (-39.0, 0.0, -0.4), 2.5),
    ]
    # The pusher-peg head centre follows a circular arc; four straight chords bound the
    # same corridor with a radius smaller than the head, so the declared path is honest.
    fractions = (0.0, 0.25, 0.5, 0.75, 1.0)
    pts = [pose_at_phi(link, phi_for_button_fraction(link, f)) for f in fractions]
    for i in range(4):
        transits.append(TransitSpec(
            f"peg_head_axis_{i}", (pts[i].pusher_pin_x, pts[i].pusher_pin_y, -1.4),
            (pts[i + 1].pusher_pin_x, pts[i + 1].pusher_pin_y, -1.4), 1.0,
        ))
    sx0, sx1, sy0, sy1 = floor_slot_bounds(link)
    critical = (
        # Floor underside, away from the slot and the relief.
        (0.0, 0.0, link.floor_z0), (50.0, 10.0, link.floor_z0),
        (-20.0, -10.0, link.floor_z0), (-80.0, 10.0, link.floor_z0),
        # Local relief ceiling.
        (rcx, rcy - 3.0, RELIEF_CEILING_Z), (rcx + 0.5, rcy - 3.5, RELIEF_CEILING_Z),
        (rcx - 0.5, rcy - 3.5, RELIEF_CEILING_Z),
        # Floor-slot walls.
        (-60.0, sy1, -1.2), (-60.0, sy0, -1.2), (-50.0, sy1, -1.2),
    )
    return FidelitySpec(
        probes=tuple(probes), transits=tuple(transits),
        critical_surfaces_mm=critical,
        max_surface_deviation_mm=CRITICAL_TOL_MM,
        max_coverage_gap_mm=COVERAGE_GAP_MM,
    )


# --------------------------------------------------------------------------- chassis
def chassis_colliders(p: Params, link) -> tuple[ColliderSpec, ...]:
    """Basement frame: plate with a pivot relief hole, ring-sector boss, stops, guides,
    spring pocket, hooks and artery. No solid boss cylinder and no filled pocket."""
    t = _tube_values(p, link)
    feat = _rod_features(link)
    stroke = link.button_stroke
    out: list[ColliderSpec] = []

    out.extend(_plate_with_hole(
        "base", (-115.0, 110.0, -20.2, 55.0), link.pivot_x, link.pivot_y, 4.4,
        CHASSIS_Z0, -15.6, "chassis plate around the pivot-head relief",
    ))
    # Boss: two declared rings, never a solid disc. The 2.7 mm bore is probe-only.
    out.extend(_ring_sectors(
        "boss", link.pivot_x, link.pivot_y, -15.6, link.crank_z0 - Z_GAP,
        2.7, 7.0, 12, "chassis pivot boss ring (parent-filtered bore)",
        pivot=(link.pivot_x, link.pivot_y),
    ))

    home_x0 = link.home_x + _STOP_EPS
    out.append(_b("home_stop", (home_x0, link.home_x + 3.0, LUG_Y[0], LUG_Y[1],
                                -18.0, -9.0), "chassis home stop"))
    nominal = 40.0 - stroke
    fwd_x1 = nominal - _STOP_EPS
    out.append(_b("forward_stop", (fwd_x1 - 4.0, fwd_x1, LUG_Y[0], LUG_Y[1], -18.0, -12.0),
                  "chassis forward stop"))
    out.append(_b("home_bridge", (home_x0, link.home_x + 3.0, LUG_Y[0], -19.8,
                                  CHASSIS_Z0, -15.75), "chassis home-stop bridge"))
    out.append(_b("fwd_bridge", (fwd_x1 - 4.0, fwd_x1, LUG_Y[0], -19.8,
                                 CHASSIS_Z0, -15.75), "chassis forward-stop bridge"))

    # Spring pocket: floor and walls, with the B insert's steps. The pocket stays open.
    seat = ROD_PAD_X - PROTOTYPE_SPRING.installed()
    back_x = seat - 4.0 - 4.8
    y_near = SPRING_Y + SPRING_AMPLITUDE / 2.0 + 0.5
    y_far = SPRING_Y - SPRING_AMPLITUDE / 2.0 - 0.5
    z_floor = SPRING_Z0 - 0.2
    out.append(_b("spine", (back_x - t["wall"], 20.0, y_far - t["wall"], -16.0,
                            CHASSIS_Z0, z_floor), "chassis spring-pocket spine"))
    out.append(_b("pocket_floor", (back_x - t["wall"], seat + 1.0, y_far - t["wall"],
                                   y_near + t["wall"], CHASSIS_Z0, z_floor),
                  "chassis spring-pocket floor"))
    out.append(_b("pocket_near", (back_x, seat + 1.0, y_near, y_near + t["wall"],
                                  z_floor - 0.2, -2.5), "chassis spring-pocket near wall"))
    out.append(_b("pocket_far", (back_x, seat + 1.0, y_far - t["wall"], y_far,
                                 z_floor - 0.2, -2.5), "chassis spring-pocket far wall"))
    out.append(_b("pocket_back", (back_x - t["wall"], back_x, y_far - t["wall"],
                                  y_near + t["wall"], z_floor - 0.2, -2.5),
                  "chassis spring-pocket back wall"))
    step_x1 = seat - 4.0
    out.append(_b("pocket_step_n", (step_x1 - t["wall"], step_x1, y_near - 1.2,
                                    y_near + 0.2, z_floor, SPRING_Z0 + 5.0),
                  "chassis B-insert step"))
    out.append(_b("pocket_step_s", (step_x1 - t["wall"], step_x1, y_far - 0.2,
                                    y_far + 1.2, z_floor, SPRING_Z0 + 5.0),
                  "chassis B-insert step"))

    # Rod guides. The 0.3 mm per-side guide clearance is a declared joint idealization.
    shaft_y1 = -28.0 + 5.0
    shaft_y0 = -28.0 - 5.0
    north_x0 = feat["x_start"] - stroke - 1.0
    out.append(_b("guide_north", (north_x0, feat["head_outer"], shaft_y1 + 0.3,
                                  shaft_y1 + 0.3 + t["wall"], link.rod_z0, link.rod_z1),
                  "chassis rod guide rail, north"))
    out.append(_b("guide_north_leg", (-20.0, -14.0, shaft_y1 + 0.3, -15.0,
                                      CHASSIS_Z0, link.rod_z1), "chassis guide leg"))
    out.append(_b("guide_north_plinth", (north_x0, feat["head_outer"], shaft_y1 + 0.3,
                                         shaft_y1 + 0.3 + t["wall"], CHASSIS_Z0,
                                         link.rod_z0 + 0.2), "chassis guide plinth"))

    south_y0 = shaft_y0 - 0.3 - t["wall"]
    south_y1 = shaft_y0 - 0.3
    pad_lo, _ = _swept(feat["pad"], stroke)
    sh_lo, sh_hi = _swept(feat["shoulder"], stroke)
    fl_lo, fl_hi = _swept(feat["flange"], stroke)
    hd_lo, _ = _swept((feat["head_inner"], feat["head_outer"]), stroke)
    web_x0, _, _ = _spring_web(link)
    web_swept = web_x0 - stroke
    spans = (
        (north_x0, min(pad_lo, web_swept) - 0.4),
        (sh_hi + 0.4, fl_lo - 0.4),
        (fl_hi + 0.4, hd_lo - 0.4),
    )
    for i, (a, b) in enumerate(spans):
        out.append(_b(f"guide_south_{i}", (a, b, south_y0, south_y1, link.rod_z0, link.rod_z1),
                      "chassis rod guide rail, south"))
        out.append(_b(f"guide_south_plinth_{i}", (a, b, south_y0, south_y1, CHASSIS_Z0,
                                                  link.rod_z0 + 0.2), "chassis guide plinth"))
        mid = 0.5 * (a + b)
        out.append(_b(f"guide_south_drop_{i}", (mid - 1.2, mid + 1.2, LUG_Y[0] - 6.0,
                                                south_y1, CHASSIS_Z0, link.rod_z0 + 0.2),
                      "chassis guide tie"))
    out.append(_b("artery", (spans[0][0], spans[-1][1], LUG_Y[0] - 6.0, LUG_Y[0] - 0.4,
                             CHASSIS_Z0, z_floor), "chassis artery"))

    # Hooks. Tooth underside is 0.05 mm above the body rib top.
    for tag, x0, x1, rib_outer, sign in (
        ("n", 62.0, 72.0, t["oy"] + 2.6, 1.0),
        ("s", -38.0, -28.0, -(t["oy"] + 2.6), -1.0),
    ):
        post_in = rib_outer + sign * 0.3
        post_out = rib_outer + sign * (0.3 + _CHASSIS_WALL)
        tooth_in = rib_outer - sign * 1.0
        py0, py1 = sorted((post_in, post_out))
        ty0, ty1 = sorted((tooth_in, post_in))
        z_catch = 0.05
        z_top = z_catch + _CHASSIS_WALL
        mid = 0.5 * (x0 + x1)
        out.append(_b(f"hook_post_{tag}", (x0, x1, py0, py1, CHASSIS_Z0, z_top),
                      "chassis retention hook post"))
        out.append(_b(f"hook_tooth_{tag}", (mid - 3.0, mid + 3.0, ty0, ty1, z_catch, z_top),
                      "chassis retention hook tooth"))

    # The B insert is welded to the chassis; exact box.
    out.append(_b("spring_seat", (seat - 4.0, seat, SPRING_Y - SPRING_AMPLITUDE / 2.0,
                                  SPRING_Y + SPRING_AMPLITUDE / 2.0, SPRING_Z0,
                                  SPRING_Z0 + 5.0), "chassis B spring insert"))
    return tuple(out)


def chassis_fidelity(p: Params, link) -> FidelitySpec:
    seat = ROD_PAD_X - PROTOTYPE_SPRING.installed()
    back_x = seat - 4.0 - 4.8
    y_near = SPRING_Y + SPRING_AMPLITUDE / 2.0 + 0.5
    y_far = SPRING_Y - SPRING_AMPLITUDE / 2.0 - 0.5
    z_floor = SPRING_Z0 - 0.2
    own, others = _cad_groups(p, link, "chassis")

    pocket_grid = _dense_probe(
        "spring_pocket_grid",
        _void_grid(_box_grid(
            (back_x, seat, y_far, y_near, z_floor, -2.5), (2.0, 3.0, 3.0),
        ), own, others, body_id="chassis", probe_id="spring_pocket_grid"),
        "spring pocket: 2 mm along x, 3 mm across and in z; the B insert is part of the group",
        minimum=20,
    )
    relief_gap_grid = _dense_probe(
        "head_relief_ring",
        _void_grid(
            _ring_points(link.pivot_x, link.pivot_y, 4.2, 16, -17.0), own, others,
            body_id="chassis", probe_id="head_relief_ring",
        ),
        "0.4 mm annular gap around the welded pivot head, 16 adapted station points",
        minimum=12,
    )
    # The rod corridor is a volume, not a line. The previous contract sampled only
    # (x, -28, -16.0), which misses the upper channel: a 6 mm box at (-82, -28, -10.9) has
    # zero installed-CAD overlap, passes the old contract, and still intersects the moving
    # rod by 41.27 mm3 at f=0.5 and 82.8 mm3 at f=1. This grid is the swept rod volume
    # derived from CAD over the full stroke, so the whole corridor is protected. The sweep
    # encloses the true swept volume (it is not an exact piecewise decomposition: the peg's
    # cylindrical and conical faces vary the section continuously, so each interval's prism
    # is the union of its own endpoint sections). The enclosing slack is measured, not
    # assumed: out/mujoco-m5a/fidelity-finalize/probe_validate_corridor.json reports the
    # true swept volume, the corridor volume, the missing volume and the excess bbox.
    corridor = _rod_corridor_prisms(p, link)
    channel_grid = _dense_probe(
        "rod_corridor_grid",
        _void_grid(_corridor_points(corridor), own, others,
                   body_id="chassis", probe_id="rod_corridor_grid"),
        "swept rod corridor: the CAD rod-group sweep over the full button stroke, as "
        "enclosing prisms from real CAD sections (never coarser than 5 mm)",
        minimum=200,
    )

    probes = [
        ProbeSpec("head_relief_gap", (
            (link.pivot_x + 4.2, link.pivot_y, -17.0),
            (link.pivot_x - 4.2, link.pivot_y, -17.0),
            (link.pivot_x, link.pivot_y + 4.2, -17.0),
        ), "0.4 mm ring between the welded pivot head and the plate relief"),
        relief_gap_grid,
        ProbeSpec("spring_pocket", (
            (back_x + 1.5, -74.0, -14.0), (back_x + 1.2, -70.0, -12.0),
            (back_x + 1.7, -78.0, -15.0),
        ), "spring pocket interior"),
        pocket_grid,
        ProbeSpec("rod_channel", (
            (0.0, -28.0, -16.0), (60.0, -28.0, -16.0), (-40.0, -28.0, -16.0),
        ), "rod guide channel"),
        channel_grid,
    ]
    transits = [
        TransitSpec("rod_shaft_path", (-70.0, -28.0, -16.0), (-95.0, -28.0, -16.0), 2.0),
    ]
    critical = (
        (67.0, 35.3, 1.0), (-33.0, -35.3, 1.0),   # hook post inner faces
        (67.0, 34.8, 0.05), (-33.0, -34.8, 0.05),  # tooth undersides
    )
    return FidelitySpec(
        probes=tuple(probes), transits=tuple(transits),
        critical_surfaces_mm=critical,
        max_surface_deviation_mm=CRITICAL_TOL_MM,
        max_coverage_gap_mm=COVERAGE_GAP_MM,
    )


# --------------------------------------------------------------------------- lip
def lip_colliders(p: Params, link, gap: float = DEFAULT_GAP) -> tuple[ColliderSpec, ...]:
    t = _tube_values(p, link)
    out: list[ColliderSpec] = []
    shelf_x0 = t["ox1"] + 0.3
    shelf_x1 = t["ox1"] + 18.0
    nose_r = t["wall"] / 2.0
    out.append(_b("shelf", (shelf_x0, shelf_x1 - nose_r + 0.2, -t["y1"] - 2.0,
                            t["y1"] + 2.0, -t["wall"], 0.0), "lip shelf"))
    out.append(ColliderSpec(
        collider_id="nose", kind="cylinder",
        size_mm=(nose_r, t["y1"] + 2.0),
        pos_mm=(shelf_x1 - nose_r, 0.0, -nose_r), rot_deg=(90.0, 0.0, 0.0),
        source=_src("lip shelf bullnose"), friction=PETG_FRICTION,
    ))
    half = p.packet.width / 2.0
    for sign, tag in ((1.0, "n"), (-1.0, "s")):
        cy0, cy1 = sorted((sign * (half + 0.2), sign * (half + 3.3)))
        out.append(_b(f"cheek_{tag}", (t["ox1"] + 8.3, shelf_x1 - 2.0, cy0, cy1,
                                       -0.2, 4.8), "lip cheek"))
    blade_x0 = p.packet.length / 2.0 - 2.0
    blade_x1 = t["ox1"] + 3.0
    out.append(_b("blade", (blade_x0, blade_x1, -t["y1"] + 0.3, t["y1"] - 0.3,
                            gap, gap + 2.4), "lip separator blade (R0.8 corner approximated)"))
    for sign, tag in ((1.0, "n"), (-1.0, "s")):
        fy0, fy1 = sorted((sign * (t["y1"] - 0.5), sign * (t["y1"] + 5.6)))
        out.append(_b(f"foot_{tag}", (t["ox1"] + 0.4, t["ox1"] + 11.0, fy0, fy1,
                                      gap + _STOP_EPS, gap + _STOP_EPS + t["wall"]),
                      "lip foot"))
    for sign, tag in ((1.0, "n"), (-1.0, "s")):
        inner = sign * (t["oy"] - 0.4)
        outer = sign * (t["oy"] + 3.6)
        if sign < 0:
            outer = max(outer, HEAD_UPPER_Y + 0.8)
        by0, by1 = sorted((inner, outer))
        bar_outer = by0 if abs(by0) >= abs(by1) else by1
        ty0, ty1 = sorted((bar_outer - sign * 1.0, bar_outer + sign * 0.4))
        tooth_x0 = t["ox1"] - 3.4
        tooth_x1 = t["ox1"] - 1.15
        rail_in = bar_outer + sign * 0.2
        rail_out = bar_outer + sign * 2.6
        ry0, ry1 = sorted((rail_in, rail_out))
        riser_x0 = t["ox1"] + 8.4
        riser_x1 = t["ox1"] + 11.0
        shelf_outer = sign * (t["y1"] + 2.0)
        sy0, sy1 = sorted((shelf_outer, shelf_outer - sign * t["wall"]))
        shelf_y = sy0 if abs(sy0) <= abs(sy1) else sy1
        py0, py1 = sorted((shelf_y, rail_out))
        out.append(_b(f"riser_{tag}", (riser_x0, riser_x1, sy0, sy1, -0.2, 14.7),
                      "lip hook riser"))
        out.append(_b(f"plate_{tag}", (riser_x0, riser_x1, py0, py1, 12.3, 14.7),
                      "lip hook plate"))
        out.append(_b(f"rail_{tag}", (tooth_x0, riser_x1, ry0, ry1, 12.3, 14.7),
                      "lip hook rail"))
        out.append(_b(f"tooth_{tag}", (tooth_x0, tooth_x1, ty0, ty1, 12.3, 14.7),
                      "lip hook tooth"))
    return tuple(out)


def lip_fidelity(p: Params, link, gap: float = DEFAULT_GAP) -> FidelitySpec:
    t = _tube_values(p, link)
    blade_x0 = p.packet.length / 2.0 - 2.0
    blade_x1 = t["ox1"] + 3.0
    own, others = _cad_groups(p, link, "lip")
    separator_grid = _dense_probe(
        "separator_gap_grid",
        _void_grid(_box_grid(
            (blade_x0, blade_x1, -t["y1"] + 0.3, t["y1"] - 0.3, 0.0, gap),
            (VOID_GRID_STEP_MM, VOID_GRID_STEP_MM, 2.5),
        ), own, others, body_id="lip", probe_id="separator_gap_grid"),
        "separator gap between the shelf top and the blade underside, 5 mm grid",
        minimum=40,
    )
    probes = [
        ProbeSpec("separator_gap", (
            (82.0, 0.0, 5.5), (86.0, 10.0, 5.5), (86.0, -10.0, 5.5),
        ), "separator gap over the bottom packet"),
        separator_grid,
        ProbeSpec("shelf_clear", ((95.0, 0.0, 1.0), (100.0, 20.0, 2.0)),
                  "open space above the shelf"),
        ProbeSpec("bar_clear", ((t["ox1"] - 1.075, t["oy"] + 2.0, 13.0),),
                  "0.15 mm tooth-to-bar gap"),
    ]
    transits = [
        TransitSpec("packet_exit", (79.0, 0.0, 2.6), (108.0, 0.0, 2.6), 2.0),
    ]
    critical = (
        (blade_x0, 0.0, gap + 2.4), (85.0, 0.0, gap + 2.4), (blade_x0, 20.0, gap + 2.4),
        (85.0, 0.0, gap),
    )
    return FidelitySpec(
        probes=tuple(probes), transits=tuple(transits),
        critical_surfaces_mm=critical,
        max_surface_deviation_mm=CRITICAL_TOL_MM,
        max_coverage_gap_mm=COVERAGE_GAP_MM,
    )


# --------------------------------------------------------------------------- crank
def _crank_phi_deg(link) -> float:
    return math.degrees(link.phi0)


def crank_colliders(p: Params, link) -> tuple[ColliderSpec, ...]:
    """Crank bar split around the button slot, with tangent slot-end caps and a hub ring.

    Authored in the crank's pivot frame and rotated by the actual fraction-0 CAD angle.
    The pusher-peg hole is welded closed by its own peg in the same body.
    """
    phi = _crank_phi_deg(link)
    pivot = (link.pivot_x, link.pivot_y)
    z0, z1 = link.crank_z0, link.crank_z1
    inner, outer = 19.0, 24.094010767585033
    side = PROTO_SLOT_W / 2.0
    reach_button = outer + side + link.min_wall
    reach_pusher = link.radius + PEG_D / 2.0 + link.min_wall
    cap_r = side
    cap_out = 5.0
    out: list[ColliderSpec] = [
        _rb("bar_west", (-reach_button, -outer - cap_r, -5.0, 5.0, z0, z1), phi, pivot,
            "crank bar west of the button slot"),
        _rb("bar_east_w", (-inner + cap_r, -2.7, -5.0, 5.0, z0, z1), phi, pivot,
            "crank bar east of the button slot, west of the pivot bore"),
        _rb("bar_east_e", (2.7, reach_pusher, -5.0, 5.0, z0, z1), phi, pivot,
            "crank bar east of the button slot (peg hole welded)"),
        _rb("bar_north", (-outer - cap_r, -inner + cap_r, side, 5.0, z0, z1), phi, pivot,
            "crank bar north of the button slot"),
        _rb("bar_south", (-outer - cap_r, -inner + cap_r, -5.0, -side, z0, z1), phi, pivot,
            "crank bar south of the button slot"),
    ]
    out.extend(_rotated_cap("cap_west", -outer, 0.0, cap_r, (90, 120, 150, 180, 210, 240, 270),
                            cap_out, 3.0, z0, z1, phi, pivot))
    out.extend(_rotated_cap("cap_east", -inner, 0.0, cap_r, (270, 300, 330, 0, 30, 60, 90),
                            cap_out, 3.0, z0, z1, phi, pivot))
    out.extend(_ring_sectors(
        "hub", 0.0, 0.0, z0, z1, 2.7, 5.5, 12,
        "crank hub ring (parent-filtered pivot bore)", phi_deg=phi, pivot=pivot,
    ))
    return tuple(out)


def _rotated_cap(prefix: str, cx: float, cy: float, radius: float, normals,
                 radial_out: float, tangential_half: float, z0: float, z1: float,
                 phi: float, pivot) -> list[ColliderSpec]:
    """Tangent cap boxes authored in a local frame and rotated with the crank."""
    half_r = (radial_out - radius) / 2.0
    rmid = (radius + radial_out) / 2.0
    out = []
    for i, deg in enumerate(normals):
        th = math.radians(deg)
        lx = cx + rmid * math.cos(th)
        ly = cy + rmid * math.sin(th)
        wx, wy = _rz(pivot[0], pivot[1], phi, lx, ly)
        out.append(ColliderSpec(
            collider_id=f"{prefix}_{i:02d}", kind="box",
            size_mm=(half_r, tangential_half, (z1 - z0) / 2.0),
            pos_mm=(wx, wy, (z0 + z1) / 2.0),
            rot_deg=(0.0, 0.0, phi + deg),
            source=_src("crank button-slot end cap"), friction=PETG_FRICTION,
            priority=PETG_PRIORITY,
        ))
    return out


def crank_fidelity(p: Params, link) -> FidelitySpec:
    phi = _crank_phi_deg(link)
    pivot = (link.pivot_x, link.pivot_y)
    zc = 0.5 * (link.crank_z0 + link.crank_z1)

    def world(x, y, z):
        wx, wy = _rz(pivot[0], pivot[1], phi, x, y)
        return (wx, wy, z)

    side = PROTO_SLOT_W / 2.0
    inner, outer = 19.0, 24.094010767585033
    own, others = _cad_groups(p, link, "crank")
    slot_grid = _dense_probe(
        "button_slot_grid",
        _void_grid(
            tuple(world(x, y, z) for x, y, z in _box_grid(
                (-outer, -inner, -side + 0.3, side - 0.3,
                 link.crank_z0 + 0.5, link.crank_z1 - 0.5),
                (1.0, 1.0, 2.0),
            )),
            own, others, body_id="crank", probe_id="button_slot_grid",
        ),
        "button slot: 1 mm radial/width grid in the crank's own frame; the installed "
        "button peg is an independent body, so its points are kept and annotated in "
        "occupancy_report, not deleted",
        minimum=8,
    )
    probes = [
        ProbeSpec("button_slot", (
            world(-21.0, -1.5, zc), world(-20.0, 0.5, zc), world(-19.5, 1.5, zc),
        ), "button slot void seeds; the button peg belongs to the rod, so the seeds are "
           "chosen clear of its fraction-0 CAD and any peg occupancy is annotated, never "
           "used to exclude slot coverage"),
        slot_grid,
        ProbeSpec("slot_end_voids", (
            world(-25.5, 0.6, zc), world(-17.5, 0.6, zc),
        ), "button-slot end-cap voids"),
        ProbeSpec("pivot_bore", (
            world(0.0, 0.0, zc), world(1.5, 0.0, zc), world(0.0, 1.5, zc),
        ), "parent-filtered pivot bore (declared probe exception; the peg is welded there)"),
    ]
    transits = [
        TransitSpec("button_peg_path", world(-23.094010767585033, 0.0, zc),
                    world(-20.0, 0.0, zc), 2.0),
    ]
    critical = (
        world(-21.0, side, zc), world(-21.0, -side, zc),
    )
    return FidelitySpec(
        probes=tuple(probes), transits=tuple(transits),
        critical_surfaces_mm=critical,
        max_surface_deviation_mm=CRITICAL_TOL_MM,
        max_coverage_gap_mm=COVERAGE_GAP_MM,
    )


# --------------------------------------------------------------------------- rod
def rod_colliders(p: Params, link, pose) -> tuple[ColliderSpec, ...]:
    """Rod at the fraction-0 pose: shaft, two-part head, flange, shoulder, pad, beam, web."""
    feat = _rod_features(link)
    y0 = -28.0 - 5.0
    y1 = -28.0 + 5.0
    z0, z1 = link.rod_z0, link.rod_z1
    head_y1 = min(-p.packet.width / 2.0 - 0.2, -28.0)
    web_x0, web_x1, south_y = _spring_web(link)
    out = [
        _b("shaft", (feat["x_start"], feat["head_outer"], y0, y1, z0, z1), "rod shaft (peg hole welded)"),
        _b("head_lower", (feat["head_inner"], feat["head_outer"], LUG_Y[0], head_y1,
                          z0, -2.6), "rod head, lower"),
        _b("head_upper", (feat["head_inner"], feat["head_outer"], LUG_Y[0], HEAD_UPPER_Y,
                          -2.8, 12.0), "rod head, upper thumb pad"),
        _b("flange", (feat["flange"][0], feat["flange"][1], LUG_Y[0], y0,
                      -18.0, z1), "rod home-stop flange"),
        _b("shoulder", (feat["shoulder"][0], feat["shoulder"][1], LUG_Y[0], y0,
                        z0, -12.0), "rod forward-stop shoulder"),
        _b("pad", (ROD_PAD_X, ROD_PAD_X + ROD_PAD_T, SPRING_Y - SPRING_AMPLITUDE / 2.0,
                   south_y, SPRING_Z0, z1), "rod spring pad"),
        _b("beam", (web_x0, ROD_PAD_X + ROD_PAD_T, south_y - 3.4, south_y,
                    SPRING_Z0, z1), "rod spring-pad beam"),
        _b("web", (web_x0, web_x1, south_y - 0.2, y0 + 0.2, z0, z1), "rod spring-pad web"),
    ]
    return tuple(out)


def rod_fidelity(p: Params, link) -> FidelitySpec:
    feat = _rod_features(link)
    own, others = _cad_groups(p, link, "rod")
    x0 = feat["x_start"] - link.button_stroke - 1.0
    x1 = feat["head_outer"]
    lanes = tuple(
        (x, y, -13.6)
        for y in (-22.85, -33.15)
        for x in _grid(x0, x1, VOID_GRID_STEP_MM)
    )
    guide_grid = _dense_probe(
        "guide_gap_grid",
        _void_grid(lanes, own, others, body_id="rod", probe_id="guide_gap_grid"),
        "0.3 mm rod/guide clearance: 5 mm line grids on both lateral lanes, the declared "
        "joint idealization",
        minimum=20,
    )
    probes = [
        ProbeSpec("guide_gap", ((0.0, -22.85, -16.0), (0.0, -33.15, -16.0)),
                  "0.3 mm rod-to-guide clearance, joint idealization"),
        guide_grid,
    ]
    return FidelitySpec(
        probes=tuple(probes),
        max_surface_deviation_mm=CRITICAL_TOL_MM,
        max_coverage_gap_mm=COVERAGE_GAP_MM,
    )


# --------------------------------------------------------------------------- pusher
def pusher_colliders(p: Params, link, pose) -> tuple[ColliderSpec, ...]:
    """Carriage split around the Y slot, tangent end caps, neck and R2.1 bullnose."""
    pin_x = pose.pusher_pin_x
    y_lo, y_hi = pusher_slot_ends(link)
    side = PROTO_SLOT_W / 2.0
    z0, z1 = link.carriage_z0, link.carriage_z1
    car_y0 = min(-8.0, y_lo - side - link.min_wall)
    car_y1 = max(50.0, y_hi + side + link.min_wall)
    out = [
        _b("carriage_west", (pin_x - 8.0, pin_x - side, car_y0, car_y1, z0, z1),
           "pusher carriage west of the Y slot"),
        _b("carriage_east", (pin_x + side, pin_x + 20.0, car_y0, car_y1, z0, z1),
           "pusher carriage east of the Y slot"),
        _b("carriage_south", (pin_x - side, pin_x + side, car_y0, y_lo - side, z0, z1),
           "pusher carriage south of the Y slot"),
        _b("carriage_north", (pin_x - side, pin_x + side, y_hi + side, car_y1, z0, z1),
           "pusher carriage north of the Y slot"),
    ]
    out.extend(_tangent_cap(
        "pusher_cap_n", pin_x, y_hi, side, (0, 30, 60, 90, 120, 150, 180),
        7.0, 3.0, z0, z1, "pusher Y-slot north end cap",
    ))
    out.extend(_tangent_cap(
        "pusher_cap_s", pin_x, y_lo, side, (180, 210, 240, 270, 300, 330, 360),
        7.0, 3.0, z0, z1, "pusher Y-slot south end cap",
    ))
    cx = pose.face_x - NOSE_R
    # The neck is a 4 x 6 mm column with a 30 degree return wedge cut from its lower rear.
    # Model the material above the wedge instead of the old full-height box: the wedge stays
    # open and no real CAD corner is omitted. The wedge line runs from
    # (rear + 1.2, -0.4) up to (rear - 0.4, z_hi); the neck starts at cx - 2.0.
    wedge_x0 = pose.face_x - 4.2 - 0.4
    wedge_x1 = pose.face_x - 4.2 + 1.2
    z_hi = (wedge_x1 - wedge_x0) * math.tan(math.radians(30.0))
    neck_x0 = cx - 2.0
    out.append(_b("neck_south", (neck_x0, cx + 2.0, -3.0, 3.0, z1 - 0.2, -0.4),
                  "pusher neck below the return chamfer"))
    out.append(_b("neck_east", (wedge_x1, cx + 2.0, -3.0, 3.0, -0.4, 2.0),
                  "pusher neck east of the return chamfer"))
    bands = 8
    for i in range(bands):
        xa = neck_x0 + (wedge_x1 - neck_x0) * i / bands
        xb = neck_x0 + (wedge_x1 - neck_x0) * (i + 1) / bands
        z_lo = -0.4 + (z_hi + 0.4) * (wedge_x1 - xa) / (wedge_x1 - wedge_x0)
        out.append(_b(f"neck_chamfer_{i:02d}", (xa, xb, -3.0, 3.0, z_lo, 2.0),
                      "pusher neck above the 30 degree return chamfer"))
    out.append(ColliderSpec(
        collider_id="bullnose", kind="cylinder", size_mm=(NOSE_R, FACE_W / 2.0),
        pos_mm=(cx, 0.0, NOSE_R), rot_deg=(90.0, 0.0, 0.0),
        source=_src("pusher R2.1 bullnose"), friction=PETG_FRICTION, priority=PETG_PRIORITY,
    ))
    return tuple(out)


def pusher_fidelity(p: Params, link, pose) -> FidelitySpec:
    pin_x = pose.pusher_pin_x
    y_lo, y_hi = pusher_slot_ends(link)
    side = PROTO_SLOT_W / 2.0
    own, others = _cad_groups(p, link, "pusher")
    slot_grid = _dense_probe(
        "y_slot_grid",
        _void_grid(_box_grid(
            (pin_x - side + 0.3, pin_x + side - 0.3, y_lo + 0.3, y_hi - 0.3,
             link.carriage_z0 + 0.5, link.carriage_z1 - 0.5),
            (1.0, 1.5, 2.0),
        ), own, others, body_id="pusher", probe_id="y_slot_grid"),
        "pusher Y slot: 1 mm across the 4.6 mm slot, 1.5 mm along it; the installed "
        "pusher peg is an independent body, so its points are kept and annotated in "
        "occupancy_report, not deleted",
        minimum=8,
    )
    wedge_x0 = pose.face_x - 4.2 - 0.4
    wedge_x1 = pose.face_x - 4.2 + 1.2
    z_hi = (wedge_x1 - wedge_x0) * math.tan(math.radians(30.0))

    def below_wedge(point):
        x, _, z = point
        line = -0.4 + (z_hi + 0.4) * (wedge_x1 - x) / (wedge_x1 - wedge_x0)
        return z <= line - 0.2

    chamfer_grid = _dense_probe(
        "return_chamfer_grid",
        _void_grid(_box_grid(
            (wedge_x0, wedge_x1, -2.5, 2.5, -0.4, z_hi), (0.6, 1.5, 0.5), below_wedge,
        ), own, others, body_id="pusher", probe_id="return_chamfer_grid"),
        "30 degree return-chamfer wedge: 0.6 mm x / 0.5 mm z grid below the exact CAD line",
        minimum=4,
    )
    probes = [
        ProbeSpec("y_slot", (
            (pin_x, 0.5 * (y_lo + y_hi), -4.0),
            (pin_x - 1.5, y_lo + 3.0, -5.0),
            (pin_x + 1.5, y_hi - 3.0, -5.0),
        ), "pusher Y slot void"),
        slot_grid,
        ProbeSpec("y_slot_end_voids", (
            (pin_x + 1.2, y_hi + 1.2, -4.0), (pin_x - 1.2, y_lo - 1.2, -4.0),
        ), "Y-slot end-cap voids"),
        ProbeSpec("return_chamfer", (
            (pose.face_x - 4.1, 0.0, 0.10),
            (pose.face_x - 3.9, 0.0, 0.0),
        ), "30 degree return-chamfer void"),
        chamfer_grid,
    ]
    transits = [
        TransitSpec("peg_slot_path", (pin_x, y_lo + 2.3, -4.8), (pin_x, y_hi - 2.3, -4.8), 2.0),
    ]
    cx = pose.face_x - NOSE_R
    critical = (
        (pin_x - 5.0, 0.0, link.carriage_z1), (pin_x + 8.0, 10.0, link.carriage_z1),
        (pin_x - 6.0, -5.0, link.carriage_z1),
        (cx, 0.0, 2.0 * NOSE_R),
    )
    return FidelitySpec(
        probes=tuple(probes), transits=tuple(transits),
        critical_surfaces_mm=critical,
        max_surface_deviation_mm=CRITICAL_TOL_MM,
        max_coverage_gap_mm=COVERAGE_GAP_MM,
    )


# --------------------------------------------------------------------------- small parts
def peg_pivot_colliders(link) -> tuple[ColliderSpec, ...]:
    boss_bot = link.crank_z0 - Z_GAP - 4.0
    z_tip = link.crank_z1 + 0.2
    z_head1 = boss_bot - _STOP_EPS
    z_head0 = z_head1 - 2.4
    return (
        _cyl("peg_pivot_shaft", link.pivot_x, link.pivot_y, z_head1, z_tip, 2.5,
             "pivot peg shaft"),
        _cyl("peg_pivot_head", link.pivot_x, link.pivot_y, z_head0, z_head1, 4.0,
             "pivot peg head"),
    )


def peg_pusher_colliders(link, pose) -> tuple[ColliderSpec, ...]:
    z_head0 = link.carriage_z1 + 0.2
    return (
        _cyl("peg_pusher_shaft", pose.pusher_pin_x, pose.pusher_pin_y, link.crank_z0,
             z_head0, 2.0, "pusher peg shaft"),
        _cyl("peg_pusher_head", pose.pusher_pin_x, pose.pusher_pin_y, z_head0,
             z_head0 + 2.4, 3.5, "pusher peg head"),
    )


def peg_button_colliders(link, pose) -> tuple[ColliderSpec, ...]:
    z_head0 = link.crank_z1 + 0.2
    return (
        _cyl("peg_button_shaft", pose.button_x, pose.button_y, link.rod_z0, z_head0, 2.0,
             "button peg shaft"),
        _cyl("peg_button_head", pose.button_x, pose.button_y, z_head0, z_head0 + 2.4, 3.5,
             "button peg head"),
    )


def spring_mask_collider(link, pose, spring_shape) -> ColliderSpec:
    """One non-colliding box so the spring visual participates in the schema.

    The equivalent joint spring is the only elasticity; colliding spring beams are not
    enabled. contype/conaffinity 0 means this geom never generates a contact.
    """
    bb = spring_shape.bounding_box()
    return ColliderSpec(
        collider_id="spring_mask", kind="box",
        size_mm=((bb.max.X - bb.min.X) / 2.0, (bb.max.Y - bb.min.Y) / 2.0,
                 (bb.max.Z - bb.min.Z) / 2.0),
        pos_mm=((bb.min.X + bb.max.X) / 2.0, (bb.min.Y + bb.max.Y) / 2.0,
                (bb.min.Z + bb.max.Z) / 2.0),
        contype=0, conaffinity=0, role="mechanism",
        source=_src("spring visual/mass; collision masked"),
        friction=PETG_FRICTION, priority=PETG_PRIORITY,
    )


def floor_collider(p: Params) -> ColliderSpec:
    """The legitimate analytic floor: fixed to the world, top at z = -19.2 mm."""
    return _b("floor_box", (-200.0, 200.0, -200.0, 200.0, CHASSIS_Z0 - 1.0, CHASSIS_Z0),
              "analytic floor fixture, top at -19.2 mm", role="mount",
              friction=FLOOR_FRICTION)
