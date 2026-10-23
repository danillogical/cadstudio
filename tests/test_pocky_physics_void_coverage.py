"""Independent void-coverage tests for the Pocky M5a-1 collider recipe.

Every expectation here is derived from the exact CAD helpers and the fraction-0 installed
solids, never from the constants in ``projects/pocky/physics/colliders.py``. The recipe's
dense ``ProbeSpec`` grids must:

* lie inside the CAD region they claim to sample (bore, exit, slot, relief, notch, separator,
  spring pocket, swept rod corridor, button slot, guide gap, Y slot, return chamfer,
  head-relief ring);
* have at most the plan's 5 mm pitch on every axis, except where the skipped station is real
  own-group CAD (a probe genuinely cannot be placed in the carrier's own material);
* cover the large regions (bore, exit, floor slot, separator, spring pocket, rod corridor) to
  within one 5 mm step of the CAD extent;
* sit outside the exact fraction-0 CAD of the **carrier's own welded group** (its own part
  plus welded pegs and installed shims), with a 0.15 mm sphere boolean spot check;
* actually catch blockers, in three dimensions and not only along a line.

Two guarantees are deliberately kept apart, because they are different facts:

* **Own void.** A probe point must stay free of the tested carrier's colliders. A point that
  lies inside an *independently moving* part at fraction 0 is still the carrier's own void:
  that part may move away, and the carrier's collider must not fill the space. Such points are
  kept as probes and merely *classified* as other-body initial occupancy
  (``colliders.occupancy_report()``). They are never deleted from coverage.
* **Initial compiled overlap.** ``clearance_audit.initial_validity_audit`` proves the compiled
  scene has no exact overlap at fraction 0. That is an additional gate; it is not proof of the
  own-void contract, and other-body occupancy is never described as "stricter".

Coverage is measured, not counted: :func:`_coverage_audit` samples the CAD void volume in
three dimensions and compares each sample with the nearest declared probe. A half-offset cubic
lattice of pitch ``p`` has worst-case covering radius ``p*sqrt(3)/2``, so a 5 mm pitch justifies
``4.3301 mm``. Per-axis marginal coordinate counts cannot see an interior hole; this can, and
:func:`test_volumetric_audit_catches_the_interior_hole_mutation` proves it on the exact
12-point mutation that used to slip through.

The only declared exception is the crank's ``pivot_bore`` seed probe: it lies in the crank's
own bore void but inside the chassis's welded pivot peg, by design.

Run with the optional physics extra::

    uv run --frozen --extra physics pytest tests/test_pocky_physics_void_coverage.py -q
"""
from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest
import trimesh

pytest.importorskip("mujoco", reason="optional physics extra not installed")

from build123d import Box, Plane, Pos, Rot, Sphere, Vertex, extrude  # noqa: E402

from cadkit.mesh import shape_to_mesh  # noqa: E402
from cadkit.physics import require_mujoco  # noqa: E402
from cadkit.physics.collision import (  # noqa: E402
    ProbeSpec,
    collider_aabb_mm,
    contains,
    validate_fidelity,
)
from cadkit.physics.schema import ColliderSpec, PartSpec  # noqa: E402
from projects.pocky.geometry.linkage import (  # noqa: E402
    BUTTON_Y,
    CHAMFER_DEG,
    CHAMFER_LEG,
    FACE_W,
    NECK_X,
    NOSE_R,
    ROD_W,
    button_slot_radii,
    floor_slot_bounds,
    linkage_from,
    phi_for_button_fraction,
    pose_at_phi,
    pusher_slot_ends,
)
from projects.pocky.geometry.prototype import (  # noqa: E402
    BULLNOSE_Z,
    DEFAULT_GAP,
    FRONT_WALL_Z,
    HEAD_EXTRA,
    INSERT_T,
    PEG_D,
    PIVOT_PEG_D,
    POCKET_RECESS,
    PROTOTYPE_SPRING,
    PROTO_SLOT_W,
    SPRING_AMPLITUDE,
    SPRING_Y,
    SPRING_Z0,
    WALL_CLEAR,
    _rod_features,
    _tube,
    compressed_length,
    moving_solids,
    static_solids,
)
from projects.pocky.params import load_params  # noqa: E402
from projects.pocky.physics.assembly import (  # noqa: E402
    RESET_FRACTIONS,
    prototype_assembly,
)
from projects.pocky.physics.clearance_audit import (  # noqa: E402
    PAIRS,
    compile_scene,
    compiled_reset_audit,
    critical_clearance_audit,
    initial_validity_audit,
    quarter_stroke_negatives,
)
from projects.pocky.physics.colliders import occupancy_report  # noqa: E402

#: The approved plan's dense-grid pitch and the project's critical tolerance.
GRID_STEP_MM = 5.0
PITCH_TOL_MM = 0.01
CRITICAL_TOL_MM = 0.02
#: Exact-CAD boolean noise. A 0.15 mm sphere at a true void point is empty.
VOID_NOISE_MM3 = 1.0e-6
SPHERE_R_MM = 0.15
#: The f=1 relief cut ends 0.01 mm below the floor top (CAD ``_body``).
RELIEF_CEILING_Z = -0.01
#: A material probe is unambiguous well below a 0.05 mm sphere's 5.24e-4 mm^3.
MATERIAL_MM3 = 1.0e-4

#: A half-offset cubic lattice of pitch ``p`` has worst-case covering radius ``p*sqrt(3)/2``:
#: a point anywhere in a cell is at most half a space diagonal from one of its corners. With
#: the plan's 5 mm pitch that is 4.3301 mm, which is the bound every volumetric audit below
#: must hold. The number is pure lattice geometry, not tuned to the current data.
COVERING_RADIUS_MM = GRID_STEP_MM * math.sqrt(3.0) / 2.0

#: The clearance the dense grids declare from *other* installed CAD at fraction 0. A probe
#: point is classified as another body's occupancy when that body's material is this close;
#: the classifier keeps 1e-4 below it so exact tangency survives.
OCCUPANCY_CLEARANCE_MM = 0.15
_CLASSIFIER_TOL_MM = OCCUPANCY_CLEARANCE_MM - 1.0e-4

#: Independent volumetric audit lattices. Deliberately finer than the declared 5 mm pitch and
#: with a phase that is not the production grid's 0.5, so the audit cannot coincide with the
#: probe lattice it is measuring.
BORE_AUDIT_PITCH_MM = 2.5
BORE_AUDIT_PHASE = 0.37
CORRIDOR_AUDIT_PITCH_MM = 2.0
CORRIDOR_AUDIT_PHASE = 0.43

#: The button fractions whose rod-group pose is sampled for the corridor audit. Odd eighths
#: are included so a probe lattice built from the five nominal poses cannot look complete.
CORRIDOR_AUDIT_FRACTIONS = (0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0)

PRODUCT_BODIES = ("body", "lip", "chassis", "crank", "rod", "pusher")

#: The dense grids added for the approved plan's void coverage.
DENSE_GRIDS = {
    "body": ("floor_slot_grid", "back_notch_grid", "peg_relief_grid", "bore_grid", "exit_grid"),
    "lip": ("separator_gap_grid",),
    "chassis": ("head_relief_ring", "spring_pocket_grid", "rod_corridor_grid"),
    "crank": ("button_slot_grid",),
    "rod": ("guide_gap_grid",),
    "pusher": ("y_slot_grid", "return_chamfer_grid"),
}

#: Welded pegs/shims are part of their carrier, never empty space. This is the *assembly's*
#: grouping (``BodySpec.parts``), not a copy of the recipe's own table.
WELDED_PEGS = ("peg_pivot", "peg_pusher", "peg_button", "shim_04_a", "shim_04_b")


# --------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def p():
    return load_params()


@pytest.fixture(scope="module")
def link(p):
    return linkage_from(p)


@pytest.fixture(scope="module")
def rest(link):
    return pose_at_phi(link, link.phi0)


@pytest.fixture(scope="module")
def spec(p):
    return prototype_assembly(p)


@pytest.fixture(scope="module")
def bodies(spec):
    return {body.body_id: body for body in spec.bodies}


@pytest.fixture(scope="module")
def installed(p, link, rest):
    """Every installed solid at fraction 0, minus the bench dummy and parked shim_08."""
    static = static_solids(p, link, DEFAULT_GAP)
    moving = moving_solids(p, link, rest, compressed_length(0.0))
    shapes = {**static, **moving}
    shapes.pop("dummy", None)
    shapes.pop("shim_08", None)
    return shapes


@pytest.fixture(scope="module")
def own_group(bodies):
    """Each carrier's own welded group, taken from the assembly's own part list.

    ``BodySpec.parts`` is where the assembly states which CAD solid belongs to which body, so
    the test never has to copy the recipe's grouping table.
    """
    return {body_id: tuple(part.part_id for part in body.parts)
            for body_id, body in bodies.items()}


@pytest.fixture(scope="module")
def compiled(p, tmp_path_factory):
    mujoco = require_mujoco()
    outdir = tmp_path_factory.mktemp("pocky-void-coverage")
    export = compile_scene(p, outdir)
    assert export.model is not None, "the scene did not compile"
    return mujoco, export.model


# --------------------------------------------------------------------------- helpers
def _probe(bodies, body_id: str, probe_id: str):
    probes = {probe.probe_id: probe for probe in bodies[body_id].fidelity.probes}
    assert probe_id in probes, (body_id, sorted(probes))
    return probes[probe_id]


def _points(bodies, body_id: str, probe_id: str):
    return _probe(bodies, body_id, probe_id).points_mm


def _unique(values) -> list[float]:
    return sorted({round(float(value), 9) for value in values})


def _axis(points, index: int) -> list[float]:
    return _unique(point[index] for point in points)


def _pitch(values: list[float]) -> float:
    return max((b - a for a, b in zip(values, values[1:])), default=0.0)


def _span(values: list[float]) -> float:
    return values[-1] - values[0] if len(values) > 1 else 0.0


def _gaps(values: list[float], limit: float = GRID_STEP_MM + PITCH_TOL_MM):
    return [(a, b) for a, b in zip(values, values[1:]) if b - a > limit]


def _assert_no_pitch_gap(values, label: str) -> None:
    gaps = _gaps(values)
    assert not gaps, f"{label}: pitch above {GRID_STEP_MM} mm at {gaps}"


def _assert_within(point, bounds, label: str, tol: float = 1e-6) -> None:
    low = bounds[0::2]
    high = bounds[1::2]
    for coordinate, lo, hi in zip(point, low, high):
        assert lo - tol <= coordinate <= hi + tol, (
            f"{label}: point {point} is outside {bounds}")


def _overlap_mm3(shape, point, radius: float = SPHERE_R_MM) -> float:
    """Exact volume of ``shape`` inside a sphere at ``point``."""
    common = shape.intersect(Pos(*point) * Sphere(radius))
    if common is None:
        return 0.0
    items = common if isinstance(common, (list, tuple)) else [common]
    return sum(float(item.volume) for item in items if item is not None)


def _aabb_contains(box, point, padding: float = 0.0) -> bool:
    return (box.min.X - padding <= point[0] <= box.max.X + padding
            and box.min.Y - padding <= point[1] <= box.max.Y + padding
            and box.min.Z - padding <= point[2] <= box.max.Z + padding)


def _crank_local(link, point) -> tuple[float, float, float]:
    """World -> crank-local, the inverse of the CAD's ``Rot Z phi0`` placement."""
    phi = link.phi0
    c, s = math.cos(phi), math.sin(phi)
    dx, dy = point[0] - link.pivot_x, point[1] - link.pivot_y
    return (c * dx + s * dy, -s * dx + c * dy, point[2])


def _group_aabb(body) -> tuple[float, float, float, float, float, float]:
    boxes = [part.shape.bounding_box() for part in body.parts if part.shape is not None]
    return (
        min(box.min.X for box in boxes), max(box.max.X for box in boxes),
        min(box.min.Y for box in boxes), max(box.max.Y for box in boxes),
        min(box.min.Z for box in boxes), max(box.max.Z for box in boxes),
    )


# ------------------------------------------------------------------- volumetric audit
def _lattice(lo: float, hi: float, pitch: float, phase: float) -> np.ndarray:
    """Half-offset 1-D lattice spanning ``[lo, hi]`` at no more than ``pitch``."""
    n = max(1, int(math.ceil((hi - lo) / pitch - 1e-12)))
    return lo + (np.arange(n) + phase) * (hi - lo) / n


def _nearest_mm(samples: np.ndarray, probes: np.ndarray, window: float = 12.0) -> np.ndarray:
    """Distance from every sample to the nearest probe, exactly, without a KD-tree.

    ``window`` only bounds the candidate search along x; a probe further than that cannot be
    nearest for these regions (their largest x gap is far under it), and any sample left with
    no candidate keeps ``inf`` so an uncovered region is loud rather than silently zero.
    """
    order = np.argsort(probes[:, 0])
    ordered = probes[order]
    xs = ordered[:, 0]
    low = np.searchsorted(xs, samples[:, 0] - window, "left")
    high = np.searchsorted(xs, samples[:, 0] + window, "right")
    out = np.full(len(samples), np.inf)
    for index in range(len(samples)):
        a, b = low[index], high[index]
        if b > a:
            delta = ordered[a:b] - samples[index]
            out[index] = np.sqrt((delta * delta).sum(1).min())
    return out


def _mesh_of(shape) -> trimesh.Trimesh:
    mesh = shape_to_mesh(shape)
    return trimesh.Trimesh(np.asarray(mesh.vertices), np.asarray(mesh.faces), process=False)


def _rod_group(p, link, fraction: float):
    """The rod group's exact CAD solid at one button fraction: rod plus welded button peg."""
    pose = pose_at_phi(link, phi_for_button_fraction(link, fraction))
    moving = moving_solids(p, link, pose, compressed_length(fraction * link.button_stroke))
    return (moving["rod"] + moving["peg_button"]).solid()


def _assert_covered(samples: np.ndarray, probes, label: str,
                    bound: float = COVERING_RADIUS_MM) -> None:
    """Every sample must be within ``bound`` of a declared probe."""
    distances = _nearest_mm(samples, np.asarray(probes, dtype=float))
    worst = int(distances.argmax())
    assert distances[worst] <= bound, (
        f"{label}: sample {np.round(samples[worst], 3).tolist()} is "
        f"{distances[worst]:.3f} mm from the nearest declared probe, over the "
        f"{bound:.4f} mm covering radius of a {GRID_STEP_MM} mm pitch"
    )


def _blocker(body, position, size: float = 6.0, collider_id: str = "test_block"):
    """Append one ``size`` cube collider to ``body`` and return the mutated body."""
    block = ColliderSpec(collider_id, "box", (size / 2.0,) * 3, pos_mm=position)
    return replace(
        body,
        parts=body.parts + (PartSpec(part_id=f"{collider_id}_part", shape=None,
                                     colliders=(block,)),),
    )


def _void_violations(result) -> list[str]:
    return [v for v in result.violations if "declared void is filled" in v]


def _cube_volume_in(shape, position, size: float = 6.0) -> float:
    common = shape.intersect(Pos(*position) * Box(size, size, size))
    if common is None:
        return 0.0
    items = common if isinstance(common, (list, tuple)) else [common]
    return sum(float(item.volume) for item in items if item is not None)


def _assert_real_void(installed, position, size: float = 6.0,
                      allowed: dict[str, float] | None = None) -> None:
    """A blocker must be in real CAD void: zero overlap with every installed solid.

    ``allowed`` names parts whose overlap is the point of the test (the own-void case), and
    the measured volume is checked against the expected one so a typo cannot pass silently.
    """
    allowed = allowed or {}
    overlaps = {name: _cube_volume_in(shape, position, size)
                for name, shape in installed.items()}
    unexpected = {name: volume for name, volume in overlaps.items()
                  if volume > VOID_NOISE_MM3 and name not in allowed}
    assert not unexpected, (
        f"the {size} mm blocker at {position} is not in real void: {unexpected} mm^3")
    for name, expected in allowed.items():
        assert overlaps[name] > expected * 0.9, (
            f"the blocker at {position} was expected to overlap {name!r} by about "
            f"{expected} mm^3, measured {overlaps[name]:.3f} mm^3")


def _rod_group_overlaps(p, link, position, size: float = 6.0) -> dict[float, float]:
    """Volume of the moving rod group inside the cube, at every audited fraction."""
    return {fraction: _cube_volume_in(_rod_group(p, link, fraction), position, size)
            for fraction in CORRIDOR_AUDIT_FRACTIONS}


# --------------------------------------------------------------------------- exact CAD void
def test_every_dense_grid_point_is_outside_own_group_material(bodies, installed, own_group):
    """No dense-grid point may sit in the carrier's **own** welded-group CAD material.

    The carrier's own group is its own part plus whatever the assembly welds to it (pegs and
    installed shims). That is the only material that can legitimately fill the carrier's own
    void, so a probe inside it would be a real defect.

    A point inside a *different* installed part is not a defect and is not asserted here: that
    part moves independently, the space is still the carrier's own void, and
    :func:`test_occupancy_report_classifies_every_other_body_probe` proves the case is
    classified rather than dropped. ``is_inside`` is exact; the bounding box is only a cheap
    rejection filter, and it returns True on a face, so an on-surface point is rejected too.
    """
    for body_id, probe_ids in DENSE_GRIDS.items():
        own_names = own_group[body_id]
        own = {name: installed[name] for name in own_names}
        boxes = {name: shape.bounding_box() for name, shape in own.items()}
        for probe_id in probe_ids:
            for point in _points(bodies, body_id, probe_id):
                for name, shape in own.items():
                    if not _aabb_contains(boxes[name], point):
                        continue
                    assert not shape.is_inside(point), (
                        f"{body_id} probe {probe_id!r} point {point} is inside its own "
                        f"exact CAD {name!r}")


def test_sphere_sample_has_no_own_group_cad_material(bodies, installed, own_group):
    """Every 97th grid point must have an empty 0.15 mm sphere against its own group's CAD.

    This is not a bounding-box test: the solid is intersected with a real sphere, so a probe
    grazing the carrier's own wall by less than the probe radius is caught even when the
    exact ``is_inside`` test would not see the tangency.
    """
    for body_id, probe_ids in DENSE_GRIDS.items():
        own = {name: installed[name] for name in own_group[body_id]}
        for probe_id in probe_ids:
            sample = _points(bodies, body_id, probe_id)[::97]
            assert sample, (body_id, probe_id)
            for point in sample:
                for name, shape in own.items():
                    volume = _overlap_mm3(shape, point)
                    assert volume <= VOID_NOISE_MM3, (
                        f"{body_id} probe {probe_id!r} point {point} has "
                        f"{volume:.6g} mm^3 of its own {name!r} inside a {SPHERE_R_MM} mm "
                        f"sphere (point is {shape.distance_to(Vertex(*point)):.6g} mm from "
                        f"that solid)")


def test_no_dense_grid_point_is_in_its_own_welded_peg(bodies, installed, own_group):
    """A welded peg is material of its carrier, so no probe of that carrier may sit in it.

    Only the carrier's own pegs are checked. ``peg_pivot`` belongs to the chassis, so the
    crank's ``pivot_bore`` probe is unaffected here and is asserted separately by
    :func:`test_crank_pivot_bore_is_the_documented_peg_exception`.
    """
    for body_id, probe_ids in DENSE_GRIDS.items():
        own_pegs = {name: installed[name] for name in own_group[body_id]
                    if name in WELDED_PEGS}
        for probe_id in probe_ids:
            for point in _points(bodies, body_id, probe_id):
                for name, shape in own_pegs.items():
                    assert not shape.is_inside(point), (
                        f"{body_id} probe {probe_id!r} point {point} is inside its own "
                        f"welded {name!r}")


def test_other_body_occupancy_is_never_own_group_material(bodies, installed, own_group):
    """Every classified other-body point is genuinely outside the carrier's own group.

    ``occupancy_report`` is an audit of *other* bodies. A point attributed to another part
    while also sitting in the carrier's own material would be a misclassification, and it
    would let the report hide an own-void defect behind another part's name.
    """
    report = occupancy_report()
    for body_id, probe_ids in DENSE_GRIDS.items():
        own = {name: installed[name] for name in own_group[body_id]}
        for probe_id in probe_ids:
            row = report[f"{body_id}:{probe_id}"]
            assert set(row["other_occupied_by_part"]) <= set(installed), row
            assert not (set(row["other_occupied_by_part"]) & set(own)), (
                f"{body_id}:{probe_id} attributes occupancy to its own group: {row}")



def test_crank_pivot_bore_is_the_documented_peg_exception(bodies, installed):
    """The crank bore is true crank void, but the chassis's welded pivot peg fills it.

    This is the one declared exception: it is a probe of the *crank* recipe, and the peg is
    parent-filtered out of crank contact. Everywhere else the peg is material.
    """
    probe = _probe(bodies, "crank", "pivot_bore")
    crank = installed["crank"]
    pivot_peg = installed["peg_pivot"]
    for point in probe.points_mm:
        assert not crank.is_inside(point), f"pivot_bore point {point} is crank material"
        assert pivot_peg.is_inside(point), (
            f"pivot_bore point {point} should be inside the welded pivot peg")
        assert _overlap_mm3(installed["peg_pivot"], point) > VOID_NOISE_MM3


# --------------------------------------------------------------------------- body regions
def test_bore_grid_is_dense_and_covers_the_tube(p, link, bodies):
    t = _tube(p, link)
    points = _points(bodies, "body", "bore_grid")
    xs, ys, zs = _axis(points, 0), _axis(points, 1), _axis(points, 2)
    bounds = (t["x0"], t["x1"], t["y0"], t["y1"], link.floor_z1, t["top"])
    for point in points:
        _assert_within(point, bounds, "bore_grid")

    _assert_no_pitch_gap(xs, "bore_grid x")
    _assert_no_pitch_gap(ys, "bore_grid y")
    _assert_no_pitch_gap(zs, "bore_grid z")
    assert _pitch(xs) <= GRID_STEP_MM + PITCH_TOL_MM
    assert _pitch(ys) <= GRID_STEP_MM + PITCH_TOL_MM
    assert _pitch(zs) <= GRID_STEP_MM + PITCH_TOL_MM

    assert _span(xs) >= (t["x1"] - t["x0"]) - GRID_STEP_MM
    assert _span(ys) >= (t["y1"] - t["y0"]) - GRID_STEP_MM
    assert _span(zs) >= (t["top"] - link.floor_z1) - GRID_STEP_MM

    # The plan's independent plane-count floor from the actual bore extents.
    x_planes = math.ceil((t["x1"] - t["x0"]) / GRID_STEP_MM)
    y_planes = math.ceil((t["y1"] - t["y0"]) / GRID_STEP_MM)
    assert len(xs) >= x_planes
    assert len(ys) >= y_planes
    assert len(xs) * len(ys) >= x_planes * y_planes
    assert len(xs) * len(ys) >= 170.0 / GRID_STEP_MM * 60.0 / GRID_STEP_MM - 1e-9


def test_exit_grid_covers_both_lateral_sides(p, link, bodies):
    t = _tube(p, link)
    points = _points(bodies, "body", "exit_grid")
    xs, ys, zs = _axis(points, 0), _axis(points, 1), _axis(points, 2)
    bounds = (t["x1"], t["ox1"], -t["y1"], t["y1"], link.floor_z1, FRONT_WALL_Z - 2.6)
    for point in points:
        _assert_within(point, bounds, "exit_grid")
    _assert_no_pitch_gap(xs, "exit_grid x")
    _assert_no_pitch_gap(ys, "exit_grid y")
    _assert_no_pitch_gap(zs, "exit_grid z")
    assert _span(ys) >= 2.0 * t["y1"] - GRID_STEP_MM
    assert any(value > 20.0 for value in ys), "exit grid has no +Y lateral samples"
    assert any(value < -20.0 for value in ys), "exit grid has no -Y lateral samples"
    # The grid crosses the front-wall band, not just one plane on either face.
    assert _span(xs) >= 1.0


def test_floor_slot_grid_covers_the_slot_and_classifies_the_resting_neck(
        link, rest, bodies, installed, own_group):
    """The floor-slot grid covers the whole through-slot, and the resting neck is *reported*.

    The pusher's neck sits in the west end of the slot at fraction 0. That is another body's
    initial occupancy, not a hole in the body's own void: the pusher moves away, and the
    body's collider must not fill the slot either way. So the grid must still cover the slot
    from end to end, and the points under the neck must appear in ``occupancy_report`` under
    ``pusher`` rather than being deleted.

    The slot is the body's own void: no probe may sit in the body's own material (body plus
    the installed shims), and the grid's x span must reach the CAD slot extents.
    """
    sx0, sx1, sy0, sy1 = floor_slot_bounds(link)
    points = _points(bodies, "body", "floor_slot_grid")
    xs, ys, zs = _axis(points, 0), _axis(points, 1), _axis(points, 2)
    bounds = (sx0, sx1, sy0, sy1, link.floor_z0, link.floor_z1)
    for point in points:
        _assert_within(point, bounds, "floor_slot_grid")
    _assert_no_pitch_gap(xs, "floor_slot_grid x")
    _assert_no_pitch_gap(ys, "floor_slot_grid y")
    _assert_no_pitch_gap(zs, "floor_slot_grid z")

    # Own void: the grid never sits in the body's own welded group.
    for point in points:
        for name in own_group["body"]:
            assert not installed[name].is_inside(point), (
                f"floor_slot_grid point {point} is inside its own {name!r}")

    # The resting neck's east face, from the CAD pose, and the open void beyond it.
    neck_east = (rest.face_x - NOSE_R) + NECK_X / 2.0
    assert neck_east < sx1, "the resting neck is outside the slot"
    assert xs[-1] >= sx1 - GRID_STEP_MM
    assert xs[0] <= sx0 + GRID_STEP_MM, (
        "floor_slot_grid does not reach the west end of the CAD slot")
    assert _span(ys) >= (sy1 - sy0) - 1.75

    # Coverage beyond the neck is the real guarantee: the grid spans the open slot, not just
    # the part of it the resting pusher leaves clear.
    open_extent = sx1 - neck_east
    assert max(_span(xs), _span(ys), _span(zs)) >= open_extent - GRID_STEP_MM

    # The neck is classified, not silently deleted, and it is the pusher that occupies it.
    row = occupancy_report()["body:floor_slot_grid"]
    assert row["other_occupied_by_part"].get("pusher", 0) > 0, row
    neck_points = [point for point in points if point[0] < neck_east - 1e-6]
    assert len(neck_points) >= row["other_occupied_by_part"]["pusher"], (
        f"{len(neck_points)} probe points lie west of the resting neck's east face but only "
        f"{row['other_occupied_by_part']['pusher']} are classified as pusher occupancy")
    # ``own_void`` is the *kept* set, so the pusher points are inside it: they were reported,
    # not deleted. Nothing may be missing from the declared grid.
    assert row["own_void_points"] == len(points), row
    assert sum(row["other_occupied_by_part"].values()) == row["other_occupied_points"], row



def test_peg_relief_grid_is_local_and_inside_the_cut_circle(link, bodies):
    f1 = pose_at_phi(link, phi_for_button_fraction(link, 1.0))
    radius = PEG_D / 2.0 + HEAD_EXTRA / 2.0 + 0.4
    points = _points(bodies, "body", "peg_relief_grid")
    xs, ys, zs = _axis(points, 0), _axis(points, 1), _axis(points, 2)
    for point in points:
        assert math.hypot(point[0] - f1.pusher_pin_x,
                          point[1] - f1.pusher_pin_y) <= radius + 1e-6, (
            f"peg_relief_grid point {point} is outside the actual cut circle")
        assert link.floor_z0 - 0.2 - 1e-6 <= point[2] <= RELIEF_CEILING_Z + 1e-6
    assert _pitch(xs) < GRID_STEP_MM
    assert _pitch(ys) < GRID_STEP_MM
    assert _pitch(zs) < GRID_STEP_MM
    assert _span(xs) >= 2.0 * radius - _pitch(xs) - 1e-6
    assert _span(ys) >= 2.0 * radius - _pitch(ys) - 1e-6
    assert max(math.hypot(point[0] - f1.pusher_pin_x,
                          point[1] - f1.pusher_pin_y) for point in points) >= radius - 1.5


def test_back_notch_grid_is_dense_through_the_wall(p, link, bodies):
    t = _tube(p, link)
    points = _points(bodies, "body", "back_notch_grid")
    xs, ys, zs = _axis(points, 0), _axis(points, 1), _axis(points, 2)
    bounds = (t["ox0"] - 0.2, t["x0"] + 0.05,
              -FACE_W / 2.0 - 0.2, FACE_W / 2.0 + 0.2, -0.02, BULLNOSE_Z)
    for point in points:
        _assert_within(point, bounds, "back_notch_grid")
    _assert_no_pitch_gap(xs, "back_notch_grid x")
    _assert_no_pitch_gap(ys, "back_notch_grid y")
    _assert_no_pitch_gap(zs, "back_notch_grid z")
    assert _span(xs) >= (bounds[1] - bounds[0]) - 1.3
    assert _span(ys) >= (bounds[3] - bounds[2]) - GRID_STEP_MM
    assert _span(zs) >= (bounds[5] - bounds[4]) - 1.1


# --------------------------------------------------------------------------- lip region
def test_separator_gap_grid_is_dense(p, link, bodies):
    t = _tube(p, link)
    points = _points(bodies, "lip", "separator_gap_grid")
    xs, ys, zs = _axis(points, 0), _axis(points, 1), _axis(points, 2)
    blade_x0 = p.packet.length / 2.0 - 2.0
    blade_x1 = t["ox1"] + 3.0
    bounds = (blade_x0, blade_x1, -t["y1"] + 0.3, t["y1"] - 0.3,
              0.0, p.separator.gap)
    for point in points:
        _assert_within(point, bounds, "separator_gap_grid")
    _assert_no_pitch_gap(xs, "separator_gap_grid x")
    _assert_no_pitch_gap(ys, "separator_gap_grid y")
    _assert_no_pitch_gap(zs, "separator_gap_grid z")
    assert _span(ys) >= (bounds[3] - bounds[2]) - GRID_STEP_MM
    assert _span(xs) >= (blade_x1 - blade_x0) - GRID_STEP_MM
    assert _span(zs) >= p.separator.gap - 2.5


# --------------------------------------------------------------------------- chassis regions
def test_chassis_spring_pocket_grid_is_dense(bodies):
    seat = 20.0 - PROTOTYPE_SPRING.installed()
    back_x = seat - INSERT_T - POCKET_RECESS
    y_near = SPRING_Y + SPRING_AMPLITUDE / 2.0 + WALL_CLEAR
    y_far = SPRING_Y - SPRING_AMPLITUDE / 2.0 - WALL_CLEAR
    z_floor = SPRING_Z0 - 0.2
    points = _points(bodies, "chassis", "spring_pocket_grid")
    xs, ys, zs = _axis(points, 0), _axis(points, 1), _axis(points, 2)
    bounds = (back_x, seat, y_far, y_near, z_floor, -2.5)
    for point in points:
        _assert_within(point, bounds, "spring_pocket_grid")
    _assert_no_pitch_gap(xs, "spring_pocket_grid x")
    _assert_no_pitch_gap(ys, "spring_pocket_grid y")
    _assert_no_pitch_gap(zs, "spring_pocket_grid z")
    assert _span(xs) >= (seat - back_x) - GRID_STEP_MM
    assert _span(ys) >= (y_near - y_far) - GRID_STEP_MM
    assert _span(zs) >= (-2.5 - z_floor) - GRID_STEP_MM


def test_chassis_head_relief_ring_is_a_dense_annulus(link, bodies):
    points = _points(bodies, "chassis", "head_relief_ring")
    head_r = PIVOT_PEG_D / 2.0 + HEAD_EXTRA / 2.0
    relief_r = head_r + 0.4
    radii = []
    for point in points:
        radius = math.hypot(point[0] - link.pivot_x, point[1] - link.pivot_y)
        radii.append(radius)
        assert head_r + 1e-6 < radius <= relief_r + 1e-6, (
            f"head_relief_ring point {point} is not in the annular gap")
        assert -19.4 - 1e-6 <= point[2] <= -15.55 + 1e-6
    assert len(points) >= 12
    assert max(radii) - min(radii) <= 1e-6
    chord = 2.0 * radii[0] * math.sin(math.pi / len(points))
    assert chord < GRID_STEP_MM


def test_chassis_rod_corridor_matches_the_cad_sweep_extents(p, link, bodies, installed):
    """The corridor probe must span the rod group's real sweep, not one line through it.

    The extents are taken from the CAD: x runs from the rest ``x_start`` shifted back by the
    full button stroke (the rod at full travel) to ``head_outer`` (the rod at rest); y and z
    come from the rod group's own section bands at each of the audited fractions. The old
    one-line contract sampled ``(x, -28, -16.0)``, which misses the whole upper channel: the
    rod's top face is near z = -11.6, so a corridor lattice that stops at -16.0 cannot protect
    it.
    """
    feat = _rod_features(link)
    x_low = feat["x_start"] - link.button_stroke
    x_high = feat["head_outer"]
    points = np.asarray(_points(bodies, "chassis", "rod_corridor_grid"), dtype=float)
    assert points.ndim == 2 and points.shape[1] == 3

    # x: the lattice starts a probe pitch inside each end, so the spans agree within a pitch.
    assert points[:, 0].min() <= x_low + GRID_STEP_MM, (
        f"corridor starts at {points[:, 0].min():.3f}, not the swept rod's "
        f"{x_low:.3f} mm")
    assert points[:, 0].max() >= x_high - GRID_STEP_MM, (
        f"corridor ends at {points[:, 0].max():.3f}, not the rod head's {x_high:.3f} mm")

    # y and z: the probe bands must lie inside the union of the rod group's own boxes.
    lows, highs = [], []
    for fraction in CORRIDOR_AUDIT_FRACTIONS:
        box = _rod_group(p, link, fraction).bounding_box()
        lows.append((box.min.Y, box.min.Z))
        highs.append((box.max.Y, box.max.Z))
    y_low, z_low = min(v[0] for v in lows), min(v[1] for v in lows)
    y_high, z_high = max(v[0] for v in highs), max(v[1] for v in highs)
    assert y_low - 1e-6 <= points[:, 1].min() and points[:, 1].max() <= y_high + 1e-6, (
        f"corridor y {points[:, 1].min():.3f}..{points[:, 1].max():.3f} is outside the rod "
        f"group's {y_low:.3f}..{y_high:.3f}")
    assert z_low - 1e-6 <= points[:, 2].min() and points[:, 2].max() <= z_high + 1e-6, (
        f"corridor z {points[:, 2].min():.3f}..{points[:, 2].max():.3f} is outside the rod "
        f"group's {z_low:.3f}..{z_high:.3f}")

    # The lattice reaches the rod's upper face band, where the old line could not. The
    # corridor's own top is the head's +Z extent, so the probe must reach within a pitch of
    # it: a lattice that stopped at the shaft's underside would leave the whole head
    # unprotected.
    assert points[:, 2].max() >= link.rod_z1 - GRID_STEP_MM, (
        f"corridor z tops out at {points[:, 2].max():.3f}, below the rod's upper face at "
        f"{link.rod_z1:.3f}")
    assert points[:, 2].max() >= z_high - GRID_STEP_MM, (
        f"corridor z tops out at {points[:, 2].max():.3f}, not the sweep's {z_high:.3f}")

    # The shaft band is genuinely three-dimensional: more than one y and z plane.
    shaft = points[(np.abs(points[:, 1] - BUTTON_Y) <= 5.0) & (points[:, 0] < 0.0)]
    assert len(_unique(shaft[:, 1])) >= 2, _unique(shaft[:, 1])
    assert len(_unique(shaft[:, 2])) >= 2, _unique(shaft[:, 2])

    # And it is the chassis's own void: no probe sits in the chassis group's material.
    for name in ("chassis", "spring_seat", "peg_pivot"):
        assert not any(installed[name].is_inside(tuple(point)) for point in points), name


def test_chassis_rod_corridor_is_the_chassis_own_void(bodies, installed):
    """Every corridor probe is outside the chassis's own welded group, and its x is dense.

    The corridor's y and z pitch is not constant per x station: neighbouring prism pieces of
    the sweep overlap in x, so a station can carry two disjoint z bands. That is why the
    volumetric audit below measures distance to the nearest probe instead of counting
    coordinates along an axis.
    """
    points = np.asarray(_points(bodies, "chassis", "rod_corridor_grid"), dtype=float)
    for name in ("chassis", "spring_seat", "peg_pivot"):
        inside = [tuple(point) for point in points if installed[name].is_inside(tuple(point))]
        assert not inside, f"rod_corridor_grid probe inside its own {name!r}: {inside[:3]}"

    xs = _unique(points[:, 0])
    assert len(xs) >= 20
    assert _pitch(xs) <= GRID_STEP_MM + PITCH_TOL_MM, _pitch(xs)


# ------------------------------------------------------------------- volumetric occupancy
def _bore_audit_samples(p, link, installed, own_group) -> np.ndarray:
    """Independent 3-D samples of the magazine bore, clipped to the body's own material.

    The lattice is the CAD bore extents inset by 0.5 mm and pitched finer than the declared
    grid, at a phase the production grid does not use. Points inside the body's own welded
    group are removed: those are real body material, not bore void.
    """
    t = _tube(p, link)
    low = (t["x0"], t["y0"], link.floor_z1)
    high = (t["x1"], t["y1"], t["top"])
    axes = [_lattice(low[i] + 0.5, high[i] - 0.5, BORE_AUDIT_PITCH_MM, BORE_AUDIT_PHASE)
            for i in range(3)]
    grid = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
    own = [installed[name] for name in own_group["body"]]
    keep = np.ones(len(grid), dtype=bool)
    for shape in own:
        box = shape.bounding_box()
        near = ((grid[:, 0] > box.min.X) & (grid[:, 0] < box.max.X)
                & (grid[:, 1] > box.min.Y) & (grid[:, 1] < box.max.Y)
                & (grid[:, 2] > box.min.Z) & (grid[:, 2] < box.max.Z))
        for index in np.flatnonzero(near):
            keep[index] = keep[index] and not shape.is_inside(tuple(grid[index]))
    return grid[keep]


def _corridor_audit_samples(p, link) -> np.ndarray:
    """Independent 3-D samples of the rod group's sweep over the full stroke.

    The sample volume is the union of the rod group's exact CAD solids at nine fractions,
    including the odd eighths. Each solid is meshed from CAD, and a lattice at
    :data:`CORRIDOR_AUDIT_PITCH_MM` (finer than the declared 5 mm) with a phase the
    production lattice does not use is clipped to the union. This is not the production
    ``_corridor_points`` lattice: it comes from the rod's own meshes at poses the recipe does
    not sample, so a probe grid built from only the five nominal poses shows up as a gap.
    """
    meshes = [_mesh_of(_rod_group(p, link, fraction))
              for fraction in CORRIDOR_AUDIT_FRACTIONS]
    low = np.min([mesh.bounds[0] for mesh in meshes], axis=0)
    high = np.max([mesh.bounds[1] for mesh in meshes], axis=0)
    axes = [_lattice(low[i], high[i], CORRIDOR_AUDIT_PITCH_MM, CORRIDOR_AUDIT_PHASE)
            for i in range(3)]
    grid = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
    inside = np.zeros(len(grid), dtype=bool)
    for mesh in meshes:
        inside |= mesh.contains(grid)
    return grid[inside]


def test_bore_grid_has_volumetric_coverage(p, link, bodies, installed, own_group):
    """Every point of the magazine bore is within the 5 mm lattice's covering radius.

    This is the independent occupancy guarantee. It samples the bore in three dimensions,
    clips to the body's own material, and measures the distance from each sample to the
    nearest declared probe. A half-offset cubic lattice of pitch ``p`` covers every point of
    its cell to ``p*sqrt(3)/2``; at 5 mm that is 4.3301 mm. The measured worst case is
    ~3.73 mm, so the bound is the lattice geometry, not a tuned threshold.

    Marginal per-axis coordinate counts cannot fail here when an interior block of probes is
    removed; :func:`test_volumetric_audit_catches_the_interior_hole_mutation` proves this
    audit does.
    """
    samples = _bore_audit_samples(p, link, installed, own_group)
    assert len(samples) > 10000, len(samples)
    _assert_covered(samples, _points(bodies, "body", "bore_grid"), "bore_grid")


def test_rod_corridor_has_volumetric_coverage(p, link, bodies):
    """Every point of the swept rod corridor is within the covering radius of a probe.

    The sample is the union of the rod group's CAD solids at nine fractions, not the five
    the recipe's poses use, so a lattice that only covers the nominal poses fails. The bound
    is the same 4.3301 mm from the 5 mm pitch; the measured worst case is ~3.70 mm.
    """
    samples = _corridor_audit_samples(p, link)
    assert len(samples) > 2000, len(samples)
    _assert_covered(samples, _points(bodies, "chassis", "rod_corridor_grid"),
                    "rod_corridor_grid")


def test_volumetric_audit_catches_the_interior_hole_mutation(p, link, bodies, installed,
                                                            own_group):
    """Removing the 12 bore probes around (0, 0, 40) must break the audit, and must let a
    6 mm blocker through.

    This is the defect the marginal-axis test missed. The mutation is applied in memory to a
    copy of the probe list; the declared grid is untouched. Three things must all hold:

    1. The audit passes on the real grid, so the bound is not simply too tight.
    2. The audit fails on the mutated grid, with the worst sample inside the hole.
    3. A 6 mm cube at ``(0, 0, 40)`` is rejected by the real contract and accepted by the
       mutated one. That is the concrete consequence of the hole: real void with no probe.

    The mutation also must not be visible to the old marginal count: the removed points are
    all interior, so every axis still spans the same range and still has the same pitch.
    """
    bore = _points(bodies, "body", "bore_grid")
    centre = np.array([0.0, 0.0, 40.0])
    hole = (np.abs(np.asarray(bore, dtype=float) - centre) <= 6.0).all(axis=1)
    assert hole.sum() == 12, f"expected the 12-point interior cube, found {hole.sum()}"
    remaining = [point for point, drop in zip(bore, hole) if not drop]

    samples = _bore_audit_samples(p, link, installed, own_group)
    _assert_covered(samples, bore, "bore_grid")

    distances = _nearest_mm(samples, np.asarray(remaining, dtype=float))
    worst = int(distances.argmax())
    assert distances[worst] > COVERING_RADIUS_MM, (
        "the audit did not notice the interior hole: the worst sample is only "
        f"{distances[worst]:.3f} mm from a surviving probe")
    assert np.abs(samples[worst] - centre).max() <= 6.5, (
        f"the worst sample {np.round(samples[worst], 3).tolist()} is not inside the hole")

    # The mutation is invisible to marginal counts: the axes are unchanged.
    for axis in range(3):
        assert _unique(point[axis] for point in remaining) == _unique(
            point[axis] for point in bore), axis

    # And the concrete consequence: the blocker passes the mutated contract only.
    body = bodies["body"]
    blocker = _blocker(body, tuple(centre), collider_id="interior_hole_block")
    _assert_real_void(installed, tuple(centre))

    real = validate_fidelity(blocker, body.fidelity)
    assert any("bore_grid" in violation for violation in _void_violations(real)), (
        f"the real bore grid does not reject the interior blocker: {real.violations}")

    mutated_probes = tuple(
        ProbeSpec(probe.probe_id,
                  tuple(remaining) if probe.probe_id == "bore_grid" else probe.points_mm,
                  probe.note)
        for probe in body.fidelity.probes
    )
    holed = validate_fidelity(blocker, replace(body.fidelity, probes=mutated_probes))
    assert holed.ok is True, (
        "the mutated grid still rejects the blocker, so the mutation was not the defect "
        f"this test is guarding: {holed.violations}")


# ------------------------------------------------------------------- own void vs occupancy
def test_occupancy_report_is_populated_for_every_dense_grid(bodies):
    """Every dense grid has a record, and the record accounts for every declared point.

    ``own_void`` is the set of points the carrier keeps as its own void, and
    ``other_occupied`` marks which of those points another body also occupies at fraction 0.
    So the accounting identity is: ``own_void_points`` equals the declared count (nothing was
    deleted), ``other_occupied_points`` is a subset of it, and the per-part breakdown sums to
    ``other_occupied_points``. A record that silently dropped a point would break the first
    identity, which is the mechanical check that classification is an audit and not a
    deletion.
    """
    report = occupancy_report()
    for body_id, probe_ids in DENSE_GRIDS.items():
        for probe_id in probe_ids:
            key = f"{body_id}:{probe_id}"
            assert key in report, (key, sorted(report))
            row = report[key]
            declared = len(_points(bodies, body_id, probe_id))
            assert row["probe_id"] == probe_id and row["body_id"] == body_id
            assert row["own_void_points"] == declared, (key, row, declared)
            assert 0 <= row["other_occupied_points"] <= row["own_void_points"], key
            assert sum(row["other_occupied_by_part"].values()) == row[
                "other_occupied_points"], key


def test_occupancy_report_classifies_every_other_body_probe(bodies, installed, own_group):
    """Recount the other-body classification independently, from exact CAD.

    The recount uses the same 0.15 mm clearance the recipe declares, but it is written here
    from the assembly's own part lists, so a change in the recipe's grouping table cannot
    make both sides agree by construction.
    """
    report = occupancy_report()
    for body_id, probe_ids in DENSE_GRIDS.items():
        own = set(own_group[body_id])
        for probe_id in probe_ids:
            expected: dict[str, int] = {}
            for point in _points(bodies, body_id, probe_id):
                for name, shape in installed.items():
                    if name in own:
                        continue
                    if shape.is_inside(point, _CLASSIFIER_TOL_MM):
                        expected[name] = expected.get(name, 0) + 1
                        break
            row = report[f"{body_id}:{probe_id}"]
            assert row["other_occupied_by_part"] == expected, (
                f"{body_id}:{probe_id} report {row['other_occupied_by_part']} != recount "
                f"{expected}")


def test_body_void_blocker_at_the_lip_is_rejected_without_being_called_stricter(
        bodies, installed, own_group):
    """A 6 mm body-void blocker at ``(82, -27, 7)`` overlaps the lip at fraction 0.

    Two different facts, asserted separately:

    * **Own void.** The cube has zero overlap with the body's own welded group (body and its
      shims), so it is real body void. The body's ``bore_grid`` must reject it, and it does.
    * **Other-body occupancy.** The lip's blade fills 60.8 mm^3 of the same cube at fraction
      0. The probe points there are kept and classified under ``lip`` in
      ``occupancy_report``; they are not deleted from coverage and the report does not claim
      the assembly is empty at that spot.

    The test also asserts the negative that matters: the contract must not be described as
    stricter because another body sits in the void. It is not stricter; it is a different
    fact, and the initial compiled overlap audit is the separate gate for assembly overlap.
    """
    position = (82.0, -27.0, 7.0)
    own = {name: installed[name] for name in own_group["body"]}
    own_overlap = sum(_cube_volume_in(shape, position) for shape in own.values())
    assert own_overlap <= VOID_NOISE_MM3, (
        f"the blocker at {position} is inside the body's own material: {own_overlap} mm^3")

    lip_overlap = _cube_volume_in(installed["lip"], position)
    assert 55.0 <= lip_overlap <= 66.0, (
        f"expected about 60.8 mm^3 of lip in the cube at {position}, got {lip_overlap:.3f}")

    body = bodies["body"]
    result = validate_fidelity(_blocker(body, position, collider_id="lip_void_block"),
                               body.fidelity)
    assert result.ok is False
    assert any("bore_grid" in violation for violation in _void_violations(result)), (
        result.violations)

    # The probe next to the blocker is reported as lip occupancy, not deleted.
    row = occupancy_report()["body:bore_grid"]
    assert row["other_occupied_by_part"].get("lip", 0) > 0, row
    near = [point for point in _points(bodies, "body", "bore_grid")
            if max(abs(point[i] - position[i]) for i in range(3)) <= 2.0]
    assert near, "no bore probe near the blocker"
    assert all(installed["lip"].is_inside(point, _CLASSIFIER_TOL_MM) for point in near), (
        f"the probes near the blocker are not classified as lip occupancy: {near}")
    # Nothing was dropped: the record still accounts for every declared bore point, so the
    # lip's presence did not shrink the body's own-void coverage.
    assert row["own_void_points"] == len(_points(bodies, "body", "bore_grid")), row

    # And the contract does not claim the assembly is empty there: the lip's own recipe
    # really does put material at the blocker's centre.
    lip_colliders = [c.collider_id for part in bodies["lip"].parts for c in part.colliders
                     if contains(c, position, margin_mm=0.0)]
    assert lip_colliders, (
        f"the lip recipe has no collider at {position}, so nothing proves the assembly is "
        f"occupied there")


# --------------------------------------------------------------------------- crank region
def test_crank_button_slot_grid_is_dense_in_the_crank_frame(link, bodies):
    inner, outer = button_slot_radii(link)
    half = PROTO_SLOT_W / 2.0
    points = _points(bodies, "crank", "button_slot_grid")
    local = [_crank_local(link, point) for point in points]
    xs, ys, zs = _axis(local, 0), _axis(local, 1), _axis(local, 2)
    for lx, ly, lz in local:
        assert -outer - 1e-6 <= lx <= -inner + 1e-6, (lx, ly, lz)
        assert -half + 0.3 - 1e-6 <= ly <= half - 0.3 + 1e-6, (lx, ly, lz)
        assert link.crank_z0 + 0.5 - 1e-6 <= lz <= link.crank_z1 - 0.5 + 1e-6
    assert _pitch(xs) < GRID_STEP_MM
    assert _pitch(ys) < GRID_STEP_MM
    assert _pitch(zs) < GRID_STEP_MM


# --------------------------------------------------------------------------- rod region
def test_rod_guide_gap_grid_follows_both_cad_lanes(link, bodies, installed):
    feat = _rod_features(link)
    x0 = feat["x_start"] - link.button_stroke - 1.0
    x1 = feat["head_outer"]
    rod_y0 = BUTTON_Y - ROD_W / 2.0
    rod_y1 = BUTTON_Y + ROD_W / 2.0
    lane_north = rod_y1 + 0.3 / 2.0
    lane_south = rod_y0 - 0.3 / 2.0
    z_mid = 0.5 * (link.rod_z0 + link.rod_z1)
    points = _points(bodies, "rod", "guide_gap_grid")

    assert _unique(point[1] for point in points) == pytest.approx([lane_south, lane_north])
    assert _unique(point[2] for point in points) == pytest.approx([z_mid])
    for point in points:
        assert x0 - 1e-6 <= point[0] <= x1 + 1e-6

    # The probe's x axis is contiguous at the plan's pitch. A lane loses a station where
    # the rod's own flange/shoulder/head occupies that exact clearance band, which is real
    # CAD, so the skipped station is justified rather than a sparse sample.
    xs = _axis(points, 0)
    assert _pitch(xs) < GRID_STEP_MM
    assert _span(xs) >= (x1 - x0) - GRID_STEP_MM
    for lane in (lane_south, lane_north):
        lane_xs = _axis([point for point in points if point[1] == pytest.approx(lane)], 0)
        pitch = lane_xs[1] - lane_xs[0]
        for a, b in _gaps(lane_xs):
            assert abs((b - a) - 2.0 * pitch) <= PITCH_TOL_MM + 1e-6, (lane, a, b)
            missing = (a + pitch, lane, z_mid)
            assert any(shape.is_inside(missing) for shape in installed.values()), (
                f"guide lane {lane} gap {a}..{b} is not justified by installed CAD")


# --------------------------------------------------------------------------- pusher regions
def test_pusher_y_slot_grid_is_dense(link, rest, bodies):
    pin_x = rest.pusher_pin_x
    y_lo, y_hi = pusher_slot_ends(link)
    side = PROTO_SLOT_W / 2.0
    points = _points(bodies, "pusher", "y_slot_grid")
    xs, ys, zs = _axis(points, 0), _axis(points, 1), _axis(points, 2)
    bounds = (pin_x - side + 0.3, pin_x + side - 0.3, y_lo + 0.3, y_hi - 0.3,
              link.carriage_z0 + 0.5, link.carriage_z1 - 0.5)
    for point in points:
        _assert_within(point, bounds, "y_slot_grid")
    _assert_no_pitch_gap(xs, "y_slot_grid x")
    _assert_no_pitch_gap(ys, "y_slot_grid y")
    _assert_no_pitch_gap(zs, "y_slot_grid z")
    assert _pitch(xs) < GRID_STEP_MM
    assert _pitch(ys) < GRID_STEP_MM
    assert _pitch(zs) < GRID_STEP_MM
    assert _span(ys) >= (y_hi - y_lo) - GRID_STEP_MM
    assert min(ys) <= y_lo + GRID_STEP_MM
    assert max(ys) >= y_hi - GRID_STEP_MM


def test_pusher_return_chamfer_grid_is_below_the_exact_line(link, rest, bodies):
    rear = rest.face_x - 2.0 * NOSE_R
    x0 = rear - 0.4
    x1 = rear + CHAMFER_LEG
    z_hi = (x1 - x0) * math.tan(math.radians(CHAMFER_DEG))
    slope = math.tan(math.radians(CHAMFER_DEG))
    points = _points(bodies, "pusher", "return_chamfer_grid")
    xs, ys, zs = _axis(points, 0), _axis(points, 1), _axis(points, 2)
    for point in points:
        assert x0 - 1e-6 <= point[0] <= x1 + 1e-6
        assert abs(point[1]) <= FACE_W / 2.0 + 1.0
        assert -0.4 - 1e-6 <= point[2] <= z_hi + 1e-6
        line = -0.4 + (x1 - point[0]) * slope
        assert point[2] <= line - 0.1 + 1e-6, (
            f"return_chamfer_grid point {point} is not below the CAD wedge line")
    assert _pitch(xs) < GRID_STEP_MM
    assert _pitch(ys) < GRID_STEP_MM
    assert _pitch(zs) < GRID_STEP_MM


# --------------------------------------------------------------------------- blockers
def test_bore_blocker_is_real_void_and_fails_the_body_contract(bodies, installed):
    """A 6 mm box deep in the magazine bore must be rejected by ``bore_grid``."""
    body = bodies["body"]
    position = (30.0, 0.0, 20.0)
    _assert_real_void(installed, position)

    result = validate_fidelity(_blocker(body, position, collider_id="bore_block"), body.fidelity)
    assert result.ok is False
    assert any("bore_grid" in violation for violation in _void_violations(result)), (
        result.violations)


def test_exit_blocker_is_real_void_and_fails_the_body_contract(bodies, installed):
    """A 6 mm box in the packet exit must be rejected by ``exit_grid``.

    The exit void is the *body's* own void. At fraction 0 the lip's blade is in the same
    space (measured 81 mm^3 of the cube), which is the lip's initial occupancy: the lip is a
    different body, the space is still the body's own void, and the probe is kept. That is
    exactly the distinction this contract must preserve, so the overlap is asserted rather
    than tolerated.
    """
    body = bodies["body"]
    position = (86.5, -20.0, 5.0)
    _assert_real_void(installed, position, allowed={"lip": 81.0})

    result = validate_fidelity(_blocker(body, position, collider_id="exit_block"), body.fidelity)
    assert result.ok is False
    assert any("exit_grid" in violation for violation in _void_violations(result)), (
        result.violations)


#: The two reproduced channel blockers, and two more in distinct corridor bands. Each is a
#: 6 mm cube in real fraction-0 CAD void that the moving rod group runs through.
CHANNEL_BLOCKERS = (
    # The reviewer's counterexample pair: zero installed CAD, 41.27 mm^3 of rod at f=0.5.
    ("channel_upper_west", (-82.0, -28.0, -10.9)),
    ("channel_upper_far_west", (-88.0, -28.0, -10.9)),
    # The flange sweep: the flange is south of the shaft and reaches z = -18.
    ("flange_sweep", (60.0, -40.0, -13.5)),
    # The head sweep: the head rises to z = +12 as it travels.
    ("head_sweep", (93.0, -40.0, 3.0)),
)


@pytest.mark.parametrize("collider_id, position", CHANNEL_BLOCKERS,
                         ids=[name for name, _ in CHANNEL_BLOCKERS])
def test_channel_blocker_is_real_void_and_fails_the_chassis_corridor(
        p, link, bodies, installed, collider_id, position):
    """Every channel blocker must be zero-CAD, in the rod's path, and rejected.

    Three facts, each derived from CAD rather than from the recipe:

    1. **Zero installed CAD at fraction 0.** The cube overlaps no installed solid at all, so
       no material-coverage or own-void check can be the thing that catches it. This is what
       makes the corridor probe load-bearing.
    2. **The rod group really runs through it.** The overlap with ``rod + peg_button`` is
       measured at each audited fraction and must be substantial at more than one of them.
    3. **The chassis contract rejects it, naming ``rod_corridor_grid``.** A blocker that the
       corridor does not name would be a hole in the sweep, not a fidelity violation.
    """
    _assert_real_void(installed, position)

    overlaps = _rod_group_overlaps(p, link, position)
    hit = {fraction: volume for fraction, volume in overlaps.items()
           if volume > VOID_NOISE_MM3}
    assert len(hit) >= 2, (
        f"{collider_id} at {position} does not intersect the moving rod group at two or more "
        f"audited fractions; overlaps were {overlaps}")
    assert max(hit.values()) >= 10.0, (
        f"{collider_id} at {position} only grazes the rod group: {overlaps}")

    chassis = bodies["chassis"]
    result = validate_fidelity(_blocker(chassis, position, collider_id=collider_id),
                               chassis.fidelity)
    assert result.ok is False, f"{collider_id} passed the chassis contract"
    named = _void_violations(result)
    assert any("rod_corridor_grid" in violation for violation in named), (
        f"{collider_id} was rejected, but not by the rod corridor: {result.violations}")


def test_rod_corridor_contains_the_true_swept_cad_volume(p, link, installed):
    """The corridor must *contain* the rod group's real swept volume, not approximate it.

    This is the test the earlier "exact midpoint sweep" claim could not pass. The rod group's
    34 planar faces are axis-aligned, so between planar stations its YZ section is constant.
    But 4 of its faces are surfaces of revolution about Z at the button-peg axis (the Ø4
    grip, the Ø7 head, the Ø4.1 pin-bore wall and the tip-chamfer cone), and inside that band
    the section is a circular arc whose radius varies continuously with x. A single midpoint
    section there is neither exact nor a superset. Measured against a converged reference, the
    construction that actually shipped (one midpoint section per interval, no axis station, no
    subdivision) missed 3.8391 mm3 of true swept material, and adding only the axis station
    made it worse at 45.5516 mm3. That is unsafe under-coverage of exactly the kind this
    contract exists to prevent.

    Ground truth is a converged reference sweep, the union of the rod group at 121 evenly
    spaced translations over the stroke, built here from CAD rather than from the recipe's
    stations. The assertion is one-sided on purpose: the corridor must cover the reference
    (``reference - corridor`` empty), while the reverse difference is the deliberate
    enclosing slack and is only reported, not required to be zero.
    """
    from projects.pocky.physics import colliders as C

    group = _rod_group(p, link, 0.0)
    stroke = link.button_stroke
    copies = 120
    reference = None
    for index in range(copies + 1):
        copy = Pos(-stroke * index / copies, 0.0, 0.0) * group
        reference = copy if reference is None else reference + copy
    reference = reference.solid()

    prisms = C._rod_corridor_prisms(p, link)
    assert prisms
    corridor = C._rod_corridor(p, link)

    missing = reference - corridor
    missing_volume = float(missing.volume) if missing is not None else 0.0
    assert missing_volume <= VOID_NOISE_MM3, (
        f"the swept-rod corridor misses {missing_volume:.4f} mm3 of the true swept CAD "
        f"volume at {missing.bounding_box().min}..{missing.bounding_box().max}; the probe "
        f"lattice cannot protect material it does not enclose"
    )

    # The enclosure is deliberate but must stay bounded: a corridor that ballooned to the
    # group's whole bounding box would pass containment while making the probes meaningless.
    # Measured on this CAD: 8.123 mm3 excess, 0.029% of the 27552.66 mm3 reference. The bound
    # is 0.5% (about 138 mm3), tight enough to catch a moderate over-enclosure regression
    # rather than only a balloon to the bounding box.
    excess = corridor - reference
    excess_volume = float(excess.volume) if excess is not None else 0.0
    assert excess_volume < 0.005 * float(reference.volume), (
        f"the corridor encloses {excess_volume:.3f} mm3 beyond the true sweep, over 0.5% of "
        f"its {float(reference.volume):.1f} mm3; the enclosing sections are too coarse"
    )

    # And it must still be a real corridor: the pieces are the CAD sections, so the corridor
    # is far smaller than the group's bounding box would suggest.
    box = group.bounding_box()
    hull = (box.max.X - box.min.X + stroke) * (box.max.Y - box.min.Y) * (box.max.Z - box.min.Z)
    assert float(corridor.volume) < 0.6 * hull, (
        f"corridor volume {float(corridor.volume):.0f} mm3 is close to the "
        f"{hull:.0f} mm3 swept bounding box, so it is not section-following"
    )


def test_rod_corridor_band_sections_are_not_nested_so_endpoint_union_is_required(
        p, link):
    """The peg band's sections are NOT nested, which is why a single section cannot work.

    Two facts, both measured from CAD:

    1. The section area falls away from the axis (74.95 mm2 at the axis, 43.99 mm2 at
       3.4 mm out), so the band is where the section varies.
    2. But a section nearer the axis does **not** contain a section further out: the section
       1.0 mm out has 0.164 mm2 outside the section 0.5 mm out. The Ø4.1 pin bore and the
       head's z extent vary independently, so neither nesting nor monotonicity holds. The
       failure is local: 3.0 mm out IS nested inside 2.0 mm out.

    Fact 2 is why the construction must union several sections per interval instead of
    taking one, and it is asserted here so nobody can "simplify" the union away on the
    strength of a false monotonicity argument. The positive coverage claim is
    :func:`test_rod_corridor_contains_the_true_swept_cad_volume`.
    """
    from projects.pocky.physics import colliders as C

    group = _rod_group(p, link, 0.0)
    axes = C._revolution_axes(group)
    assert axes, "the rod group has no surface of revolution; this test would prove nothing"
    axis = axes[0]

    def section_at(x):
        """The single YZ section at ``x``, moved to the x=0 plane so sections are comparable.

        ``Plane.YZ.offset(x)`` returns one face. Cutting with a thin box instead returns both
        faces of the slab, which doubles the measured area near a tangency (149.9 mm2 at the
        peg axis against a true 74.95 mm2) and would corrupt every comparison here.
        """
        faces = (group & Plane.YZ.offset(x)).faces()
        if not faces:
            return None
        out = faces[0]
        for extra in faces[1:]:
            out = out + extra
        # Sections taken at different x lie in different planes; comparing them without
        # moving them into one plane makes the 2-D boolean meaningless.
        return Pos(-x, 0.0, 0.0) * out

    # Fact 1: the section varies strongly across the band. Measured single-plane areas:
    # 74.95 mm2 at the axis, 43.99 mm2 at 3.4 mm out (a 1.70x ratio, not a 3x one).
    at_axis = section_at(axis)
    far = section_at(axis + 3.4)
    assert at_axis is not None and far is not None
    assert float(at_axis.area) > 1.5 * float(far.area), (
        f"section area {float(at_axis.area):.2f} at the axis vs {float(far.area):.2f} at "
        f"3.4 mm out: the band is not where the section varies"
    )

    # Fact 2: the further section is not contained in the nearer one. The direction matters:
    # the nearer section is LARGER (74.18 vs 71.74 mm2), so "nearer outside further" is at
    # least 2.45 mm2 even if the sections were perfectly nested, and would prove nothing. The
    # meaningful quantity is how much of the FURTHER section lies outside the nearer one.
    # Measured by intersection area, not subtraction: a 2-D face difference can return the
    # whole first face for coincident or opposite-orientation operands.
    near = section_at(axis + 0.5)
    further = section_at(axis + 1.0)
    assert near is not None and further is not None
    further_area = float(further.area)
    common = near & further
    common_area = float(common.area) if common is not None else 0.0
    outside_area = further_area - common_area
    assert outside_area > 0.1, (
        f"the section 1.0 mm out has only {outside_area:.6f} mm2 outside the section 0.5 mm "
        f"out, so the band sections look nested after all; if that is really true the "
        f"endpoint-union justification must be re-derived rather than assumed"
    )
    # And the sections really are close variants of one another, not unrelated shapes.
    assert common_area > 0.9 * further_area, (
        f"only {common_area:.3f} of {further_area:.3f} mm2 of the further section is inside "
        f"the nearer one, so these are not sections of one continuous band"
    )
    # Nesting does hold further out: the section 3.0 mm out IS inside the 2.0 mm one. The
    # failure is local to the region near the axis, so no single *section* can represent the
    # band. The construction therefore applies the same rule everywhere -- union the
    # interval's endpoint and midpoint sections -- rather than trying to pick one section.
    near_outer = section_at(axis + 2.0)
    far_outer = section_at(axis + 3.0)
    assert near_outer is not None and far_outer is not None
    outer_common = near_outer & far_outer
    outer_outside = float(far_outer.area) - (float(outer_common.area)
                                             if outer_common is not None else 0.0)
    assert outer_outside <= 0.01, (
        f"the section 3.0 mm out has {outer_outside:.4f} mm2 outside the 2.0 mm one; the "
        f"nesting failure is supposed to be local to the axis, so re-check the band model"
    )


def test_rod_corridor_band_subdivision_keeps_the_enclosure_tight(p, link):
    """The union gives containment; the band subdivision is what keeps the enclosure tight.

    The independent test worker found that variant D (endpoint union with **no** band
    subdivision) already contains the true sweep, so no existing test pinned what subdivision
    buys. It buys tightness: 24.195 mm3 of slack without it, 8.123 mm3 with it. This test
    measures both and requires the subdivided corridor to be materially tighter, so removing
    `_band_subdivided` from the construction fails here even though containment alone would
    still hold.

    Tightness matters for a concrete reason: slack is corridor volume that is not real swept
    volume, and a collider that sits in the slack is legal in the true sweep but would be
    rejected by the corridor's probes.
    """
    from projects.pocky.physics import colliders as C

    group = _rod_group(p, link, 0.0)
    stroke = link.button_stroke
    copies = 120
    reference = None
    for index in range(copies + 1):
        copy = Pos(-stroke * index / copies, 0.0, 0.0) * group
        reference = copy if reference is None else reference + copy
    reference = reference.solid()

    def corridor_excess(with_subdivision: bool) -> tuple[float, int]:
        """Enclosure of a locally built corridor variant, and its piece count.

        ``with_subdivision=False`` is the mutant: the same three-section union with
        :func:`_band_subdivided` removed. The test compares **production** against this
        mutant, so deleting the subdivision from production cannot pass.
        """
        stations = C._x_stations(group)
        if with_subdivision:
            stations = C._band_subdivided(stations, C._revolution_bands(group))
        pieces = []
        for a, b in zip(stations, stations[1:]):
            if b - a < 1.0e-7:
                continue
            mid = 0.5 * (a + b)
            sections = []
            for x in (a + C._STATION_EPS, mid, b - C._STATION_EPS):
                faces = (group & Plane.YZ.offset(x)).faces()
                if not faces:
                    continue
                section = faces[0]
                for extra in faces[1:]:
                    section = section + extra
                if float(section.area) <= 1.0e-9:
                    continue
                sections.append(Pos(mid - x, 0.0, 0.0) * section)
            if not sections:
                continue
            section = sections[0]
            for extra in sections[1:]:
                section = section + extra
            piece = extrude(section, amount=(b - a) + stroke, dir=(1.0, 0.0, 0.0))
            pieces.append(Pos((a - stroke) - mid, 0.0, 0.0) * piece)
        corridor = pieces[0]
        for piece in pieces[1:]:
            corridor = corridor + piece
        excess = corridor - reference
        return (float(excess.volume) if excess is not None else 0.0), len(pieces)

    coarse, coarse_pieces = corridor_excess(False)

    # The production corridor, straight from the shipped code.
    production = C._rod_corridor(p, link)
    production_excess = production - reference
    tight = (float(production_excess.volume)
             if production_excess is not None else 0.0)
    production_pieces = len(C._rod_corridor_prisms(p, link))

    assert production_pieces > coarse_pieces, (
        f"production builds {production_pieces} prisms and the unsubdivided variant "
        f"{coarse_pieces}; production is not subdividing the revolution bands"
    )
    assert tight <= coarse, (
        f"production encloses {tight:.3f} mm3 and the unsubdivided variant {coarse:.3f} mm3, "
        f"so the subdivision is not reducing the enclosure"
    )
    # Measured 24.355 -> 8.283 mm3 on this CAD (ratio 2.94). Require at least a 2x reduction
    # so the test fails if subdivision is dropped from production, without pinning the value.
    assert coarse > 2.0 * tight, (
        f"production encloses {tight:.3f} mm3 and the unsubdivided variant {coarse:.3f} mm3; "
        f"band subdivision is supposed to cut the slack roughly threefold, so it is not "
        f"effective in production"
    )
    # And the production corridor must still be tight in absolute terms.
    assert tight < 0.005 * float(reference.volume), (
        f"the production corridor encloses {tight:.3f} mm3, over 0.5% of the "
        f"{float(reference.volume):.1f} mm3 sweep"
    )


def test_rod_corridor_does_not_fire_on_real_chassis_material(bodies, installed):
    """A 6 mm cube in real chassis material must be *material*, not a void violation.

    This is the positive control that keeps the corridor from being trivially rejecting:
    the same contract that rejects a blocker in the swept corridor must accept a blocker
    that is simply more of the chassis. The point is chosen where the cube is fully inside
    the chassis CAD (measured 80.6 mm^3 of the 216 mm^3 cube) and away from every probe.

    Removing the collider that covers that material must then be caught by the ordinary
    material-coverage check, so the control also proves the coverage check still works.
    """
    chassis = bodies["chassis"]
    position = (117.0, -21.9, -14.2)
    cube_volume = 216.0
    inside = _cube_volume_in(installed["chassis"], position)
    assert inside >= 0.3 * cube_volume, (
        f"the control point {position} is not inside real chassis material: {inside} mm^3")

    result = validate_fidelity(_blocker(chassis, position, collider_id="material_control"),
                               chassis.fidelity)
    assert result.ok is True, (
        f"a blocker inside real chassis material was treated as void: {result.violations}")

    # The material is covered by a collider; dropping that collider is a coverage failure.
    covering = [c.collider_id for part in chassis.parts for c in part.colliders
                if contains(c, position, margin_mm=0.0)]
    assert covering, f"no chassis collider covers the material at {position}"
    for collider_id in covering:
        thinned = tuple(
            replace(part, colliders=tuple(c for c in part.colliders
                                          if c.collider_id != collider_id))
            for part in chassis.parts)
        broken = validate_fidelity(replace(chassis, parts=thinned), chassis.fidelity)
        coverage = [v for v in broken.violations if "outside every collider" in v]
        assert coverage, (
            f"dropping {collider_id!r} did not trip the material-coverage check: "
            f"{broken.violations}")


def test_channel_blockers_cover_the_rod_at_every_late_fraction(p, link, installed):
    """Across the channel blockers, the rod group is intersected at f=0.5, 0.75 and 1.0.

    Individually the blockers sit in different x bands: the near-west cube is in the shaft's
    travel at mid stroke, the far-west cube only reaches the rod as the shaft arrives. Each is
    real void, and each is rejected on its own; this test asserts the stronger collective
    property the corridor has to provide -- no audited late fraction leaves the rod
    unprotected. Overlaps are measured from the rod group's CAD at each fraction, never from
    the recipe's probe list.
    """
    per_fraction = {fraction: {} for fraction in (0.5, 0.75, 1.0)}
    for name, position in CHANNEL_BLOCKERS:
        _assert_real_void(installed, position)
        overlaps = _rod_group_overlaps(p, link, position)
        for fraction in per_fraction:
            per_fraction[fraction][name] = overlaps[fraction]

    for fraction, rows in per_fraction.items():
        best = max(rows.values())
        assert best >= 10.0, (
            f"no channel blocker intersects the rod group at f={fraction}: {rows}")


def test_rod_corridor_probes_are_outside_every_non_moving_installed_solid(
        bodies, installed):
    """Positive control: the corridor is chassis void, so it is empty of every static part.

    The corridor is sampled inside the space the *rod* sweeps. That space must be free of the
    static assembly -- the housing, the lip, the chassis and its welded seat and pivot peg,
    and the installed shims -- or the corridor would be protecting a region that is really
    material. The moving mechanism is deliberately excluded: the rod group itself, the crank,
    the spring and the welded pegs occupy the corridor at fraction 0, which is exactly the
    other-body occupancy the audit reports. See
    :func:`test_corridor_occupancy_is_classified_not_deleted`.
    """
    moving_parts = {"rod", "peg_button", "spring", "crank", "peg_pusher"}
    static = {name: shape for name, shape in installed.items() if name not in moving_parts}
    points = _points(bodies, "chassis", "rod_corridor_grid")
    for name, shape in static.items():
        inside = [tuple(point) for point in points if shape.is_inside(tuple(point))]
        assert not inside, (
            f"{len(inside)} rod_corridor_grid points are inside static CAD {name!r}: "
            f"{inside[:3]}")


def test_corridor_occupancy_is_classified_not_deleted(bodies, installed):
    """The corridor's own-void count keeps every point, and the rod's occupancy is reported.

    The rod, the button peg, the crank and the spring all sit in the corridor at fraction 0.
    Under the corrected contract that is initial assembly occupancy, not a reason to delete
    coverage: every declared point is still the chassis's own void, and the report names the
    parts that occupy it. Deleting those points would be the silent weakening the contract
    exists to prevent, and it would leave the corridor empty of probes exactly where the rod
    is about to travel.
    """
    points = _points(bodies, "chassis", "rod_corridor_grid")
    row = occupancy_report()["chassis:rod_corridor_grid"]
    assert row["own_void_points"] == len(points)
    assert row["other_occupied_points"] > 0, row
    assert row["other_occupied_by_part"].get("rod", 0) > 0, row

    recounted: dict[str, int] = {}
    for point in points:
        for name in ("rod", "peg_button", "spring", "crank", "peg_pusher"):
            if installed[name].is_inside(point, _CLASSIFIER_TOL_MM):
                recounted[name] = recounted.get(name, 0) + 1
                break
    assert row["other_occupied_by_part"] == recounted, (
        f"report {row['other_occupied_by_part']} != recount {recounted}")


def test_volumetric_audit_rejects_the_old_line_only_corridor(p, link, installed):
    """The removed one-line channel probe cannot pass the volumetric corridor audit.

    The old contract declared ``(x, -28, -16.0)`` along the guide. That line is real void and
    would satisfy every point-based check, but it is one-dimensional: it never reaches the
    rod's upper face near z = -11.6, and it says nothing about the flange and head sweeps
    south of the shaft. Rebuilding it here from CAD and running the same audit must fail, so
    the audit is what stops a regression back to a line.
    """
    feat = _rod_features(link)
    xs = _lattice(feat["x_start"] - link.button_stroke, feat["head_outer"],
                  GRID_STEP_MM, 0.5)
    line = np.stack([xs, np.full(len(xs), BUTTON_Y), np.full(len(xs), link.rod_z0 - 0.4)],
                    axis=-1)

    # The old grid skipped the stations that fell in real chassis material (stop bridges).
    # Reconstruct that too, so the comparison is against the contract that actually existed
    # rather than a strawman that a material check would reject.
    static = {name: shape for name, shape in installed.items()
              if name not in {"rod", "peg_button", "spring", "crank", "peg_pusher"}}
    keep = np.array([
        not any(shape.is_inside(tuple(point)) for shape in static.values())
        for point in line
    ])
    assert keep.sum() >= 10, int(keep.sum())
    line = line[keep]

    samples = _corridor_audit_samples(p, link)
    distances = _nearest_mm(samples, line)
    assert distances.max() > COVERING_RADIUS_MM, (
        "the volumetric audit accepted a one-line corridor probe: worst sample is only "
        f"{distances.max():.3f} mm away")

    # The specific thing the line misses is the upper channel: samples above the rod's own
    # top face are tens of millimetres from a probe sitting at ``rod_z0 - 0.4``.
    upper = samples[:, 2] > link.rod_z1
    assert upper.sum() > 500, int(upper.sum())
    assert distances[upper].max() > COVERING_RADIUS_MM, (
        "the line covered the upper channel, so this negative proves nothing: worst upper "
        f"sample is {distances[upper].max():.3f} mm away")


# --------------------------------------------------------------------------- retained contract
def test_every_product_fidelity_contract_still_passes(bodies):
    for body_id in PRODUCT_BODIES:
        body = bodies[body_id]
        result = validate_fidelity(body, body.fidelity)
        assert result.ok, (body_id, result.violations)
        assert result.metrics["coverage_max_gap_mm"] <= 0.5


def test_whole_body_hull_negative_still_names_the_floor_slot(bodies, installed):
    body = bodies["body"]
    assert validate_fidelity(body, body.fidelity).ok is True

    shapes = [installed["body"], installed["shim_04_a"], installed["shim_04_b"]]
    boxes = [shape.bounding_box() for shape in shapes]
    x0 = min(box.min.X for box in boxes)
    x1 = max(box.max.X for box in boxes)
    y0 = min(box.min.Y for box in boxes)
    y1 = max(box.max.Y for box in boxes)
    z0 = min(box.min.Z for box in boxes)
    z1 = max(box.max.Z for box in boxes)
    hull = ColliderSpec(
        "hull_box", "box",
        ((x1 - x0) / 2.0, (y1 - y0) / 2.0, (z1 - z0) / 2.0),
        pos_mm=((x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0),
    )
    hulled = replace(
        body,
        parts=body.parts + (PartSpec(part_id="hull_part", shape=None,
                                     colliders=(hull,)),),
    )
    result = validate_fidelity(hulled, body.fidelity)
    assert result.ok is False
    assert any("floor_slot" in violation and "declared void is filled" in violation
               for violation in result.violations), result.violations


def test_filled_crank_slot_negative_still_names_the_button_slot(link, bodies, installed):
    crank = bodies["crank"]
    assert validate_fidelity(crank, crank.fidelity).ok is True

    inner, outer = button_slot_radii(link)
    half_x = (outer - inner) / 2.0
    center_local = (-0.5 * (inner + outer), 0.0)
    phi_deg = math.degrees(link.phi0)
    cx = link.pivot_x + center_local[0] * math.cos(link.phi0)
    cy = link.pivot_y + center_local[0] * math.sin(link.phi0)
    zc = 0.5 * (link.crank_z0 + link.crank_z1)
    fill = ColliderSpec(
        "slot_fill", "box",
        (half_x, PROTO_SLOT_W / 2.0 - 0.15, 2.0),
        pos_mm=(cx, cy, zc), rot_deg=(0.0, 0.0, phi_deg),
    )
    # The box really is in the crank's own slot void.
    fill_box = (Pos(cx, cy, zc) * Rot(0.0, 0.0, phi_deg)
                * Box(2.0 * half_x, 2.0 * (PROTO_SLOT_W / 2.0 - 0.15), 4.0))
    overlap = installed["crank"].intersect(fill_box)
    volume = 0.0 if overlap is None else sum(float(item.volume) for item in overlap)
    assert volume <= VOID_NOISE_MM3, f"the slot fill is in crank material: {volume} mm^3"
    filled = replace(
        crank,
        parts=crank.parts + (PartSpec(part_id="slot_fill_part", shape=None,
                                      colliders=(fill,)),),
    )
    result = validate_fidelity(filled, crank.fidelity)
    assert result.ok is False
    assert any("button_slot" in violation and "declared void is filled" in violation
               for violation in result.violations), result.violations


def test_floor_slot_and_local_relief_and_no_hull_still_hold(link, bodies, installed):
    body = bodies["body"]
    colliders = tuple(c for part in body.parts for c in part.colliders)
    sx0, sx1, sy0, sy1 = floor_slot_bounds(link)
    body_shape = installed["body"]

    for point in ((0.5 * (sx0 + sx1), 0.0, -1.2), (sx0 + 0.5, 0.0, -1.2),
                  (sx1 - 0.5, 0.0, -1.2)):
        assert _overlap_mm3(body_shape, point, 0.05) <= VOID_NOISE_MM3
        assert not any(contains(collider, point, margin_mm=0.05) for collider in colliders)

    for point in ((sx0 - 1.0, 0.0, -1.2), (sx1 + 1.0, 0.0, -1.2),
                  (-60.0, sy0 - 1.0, -1.2), (-60.0, sy1 + 1.0, -1.2)):
        assert _overlap_mm3(body_shape, point, 0.05) > MATERIAL_MM3
        assert any(contains(collider, point, margin_mm=0.5) for collider in colliders)

    f1 = pose_at_phi(link, phi_for_button_fraction(link, 1.0))
    radius = PEG_D / 2.0 + HEAD_EXTRA / 2.0 + 0.4
    relief_centre = (f1.pusher_pin_x, f1.pusher_pin_y - 3.0, -1.2)
    assert _overlap_mm3(body_shape, relief_centre) <= VOID_NOISE_MM3
    assert not any(contains(collider, relief_centre, margin_mm=0.05)
                   for collider in colliders)

    # The cut is local in x: material just outside the f1 circle is real and covered.
    # y=32.0 stays inside the CAD floor while clearing the f1 circle in x.
    for x in (f1.pusher_pin_x - radius - 1.0, f1.pusher_pin_x + radius + 1.0):
        point = (x, 32.0, -1.2)
        assert _overlap_mm3(body_shape, point, 0.05) > MATERIAL_MM3
        assert any(contains(collider, point, margin_mm=0.5) for collider in colliders)

    # No collider may be the whole body group's AABB hull, and the relief stays local.
    x0, x1, y0, y1, z0, z1 = _group_aabb(body)
    for collider in colliders:
        low, high = collider_aabb_mm(collider)
        assert not (low[0] <= x0 + 1e-9 and low[1] <= y0 + 1e-9
                    and low[2] <= z0 + 1e-9 and high[0] >= x1 - 1e-9
                    and high[1] >= y1 - 1e-9 and high[2] >= z1 - 1e-9), (
            collider.collider_id)
    relief = [
        collider for collider in colliders
        if collider.collider_id.startswith("floor_north_relief_")
        or collider.collider_id in ("floor_relief_skin", "side_north_relief")
    ]
    assert relief
    band = (f1.pusher_pin_x - radius, f1.pusher_pin_x + radius)
    for collider in relief:
        low, high = collider_aabb_mm(collider)
        assert low[0] >= band[0] - 1e-6
        assert high[0] <= band[1] + 1e-6


# --------------------------------------------------------------------------- compiled scene
def test_compiled_reset_audit_passes_at_all_five_fractions(p, compiled):
    mujoco, model = compiled
    audit = compiled_reset_audit(mujoco, model, p)
    assert audit["ok"], [
        (row["fraction"], row["exceeded"], row["sign_bad"])
        for row in audit["fractions"] if not row["ok"]
    ]
    assert [row["fraction"] for row in audit["fractions"]] == list(RESET_FRACTIONS)
    for row in audit["fractions"]:
        assert row["ok"] is True, (row["fraction"], row["errors"])


def test_quarter_stroke_linear_and_sign_flip_are_both_rejected(p, compiled):
    mujoco, model = compiled
    negatives = quarter_stroke_negatives(mujoco, model, p)
    linear = negatives["linear"]
    assert linear["rejected"] is True
    assert linear["audit_ok"] is False
    assert linear["min_pusher_error_m"] >= linear["required_min_m"]
    assert negatives["sign_flip"]["rejected"] is True
    assert negatives["sign_flip"]["audit_ok"] is False


def test_critical_clearance_matches_cad_at_all_five_fractions(p, compiled):
    mujoco, model = compiled
    audit = critical_clearance_audit(mujoco, model, p)
    assert audit["ok"], [
        (fraction["fraction"], row["pair"], row["difference_mm"])
        for fraction in audit["fractions"] for row in fraction["pairs"] if not row["ok"]
    ]
    assert audit["tolerance_mm"] == pytest.approx(CRITICAL_TOL_MM)
    rows = {
        (fraction["fraction"], row["pair"]): row
        for fraction in audit["fractions"] for row in fraction["pairs"]
    }
    expected = {(fraction, pair.pair_id) for pair in PAIRS for fraction in pair.fractions}
    assert set(rows) == expected
    for (fraction, pair), row in rows.items():
        assert row["ok"] is True, (fraction, pair, row)
        assert row["cad_distance_mm"] is not None
        assert row["collider_distance_mm"] is not None
        assert row["difference_mm"] <= CRITICAL_TOL_MM


def test_initial_validity_is_scene_valid_at_all_five_fractions(p, compiled):
    mujoco, model = compiled
    audit = initial_validity_audit(mujoco, model, p)
    assert audit["ok"] is True
    assert audit["verdict"] == "SCENE_VALID"
    assert audit["exact_overlap"]["ok"] is True
    noise = audit["exact_overlap"]["noise_threshold_mm3"]
    rows = {fraction["fraction"]: fraction for fraction in audit["fractions"]}
    assert set(rows) == set(RESET_FRACTIONS)
    for fraction, row in rows.items():
        exact = row["exact_overlap"]
        penetration = row["collider_penetration"]
        assert exact["ok"] is True, (fraction, exact["overlaps"])
        assert exact["overlaps"] == []
        assert exact["worst_overlap_mm3"] <= noise
        assert penetration["ok"] is True, (fraction, penetration["penetrations"])
        assert penetration["penetrations"] == []
        assert penetration["worst_m"] > -1e-6
