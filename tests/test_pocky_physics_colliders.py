"""Pocky M5a-1 collider tests: fidelity contracts, real voids, negatives and clearances.

The recipe is checked against the **exact CAD solids** as well as the adapter's declared
probes/transits. Every declared probe point and transit sample must be empty in the exact CAD
part (a 0.15 mm sphere booleans to nothing) and free of colliders; the R2.1 bullnose crest is
measured by an exact-CAD distance. Two deliberate wrong recipes (a whole-body AABB hull and a
box filling the crank button slot) must fail the declared contract and name the probe.

Compiled-scene checks use the real exported scene under ``tmp_path``:
``critical_clearance_audit`` and ``initial_validity_audit``.

Run with the optional physics extra:
``uv run --frozen --extra physics pytest tests/test_pocky_physics_colliders.py -q``.
"""
from __future__ import annotations

import math
from dataclasses import replace

import pytest

pytest.importorskip("mujoco", reason="optional physics extra not installed")

from build123d import Pos, Rot, Sphere, Vertex  # noqa: E402

from cadkit.physics import require_mujoco  # noqa: E402
from cadkit.physics.collision import (  # noqa: E402
    collider_aabb_mm,
    contains,
    signed_distance_mm,
    validate_fidelity,
)
from cadkit.physics.schema import ColliderSpec, PartSpec  # noqa: E402
from projects.pocky.geometry.linkage import (  # noqa: E402
    NOSE_R,
    floor_slot_bounds,
    linkage_from,
    phi_for_button_fraction,
    pose_at_phi,
    pusher_slot_ends,
)
from projects.pocky.geometry.prototype import (  # noqa: E402
    DEFAULT_GAP,
    compressed_length,
    moving_solids,
    static_solids,
)
from projects.pocky.params import load_params  # noqa: E402
from projects.pocky.physics.assembly import (  # noqa: E402
    RESET_FRACTIONS,
    prototype_assembly,
    reset_state,
)
from projects.pocky.physics.clearance_audit import (  # noqa: E402
    PAIRS,
    compile_scene,
    critical_clearance_audit,
    initial_validity_audit,
)

#: Approved plan limits: 0.5 mm non-critical coverage, 0.02 mm critical surfaces.
COVERAGE_GAP_MM = 0.5
CRITICAL_TOL_MM = 0.02
#: Boolean-noise threshold for the exact-CAD sphere probes, mm^3.
VOID_NOISE_MM3 = 1.0e-3
#: A 0.05 mm material probe holds 5.24e-4 mm^3; half of that is unambiguous material.
MATERIAL_MM3 = 1.0e-4
#: The plan's local f=1 relief band, mm.
RELIEF_X_BAND = (-56.9, -49.1)

PRODUCT_BODIES = ("body", "lip", "chassis", "crank", "rod", "pusher")

#: Declared probes, checked against the exact CAD.
PROBE_IDS = [
    ("body", "floor_slot"),
    ("body", "back_notch"),
    ("body", "peg_relief"),
    ("body", "bore"),
    ("body", "exit"),
    ("lip", "separator_gap"),
    ("lip", "shelf_clear"),
    ("lip", "bar_clear"),
    ("chassis", "head_relief_gap"),
    ("chassis", "spring_pocket"),
    ("chassis", "rod_channel"),
    ("crank", "button_slot"),
    ("crank", "slot_end_voids"),
    ("crank", "pivot_bore"),
    ("rod", "guide_gap"),
    ("pusher", "y_slot"),
    ("pusher", "y_slot_end_voids"),
    ("pusher", "return_chamfer"),
]

TRANSIT_IDS = [
    ("body", "pusher_neck_path"),
    ("body", "peg_head_axis_0"),
    ("body", "peg_head_axis_1"),
    ("body", "peg_head_axis_2"),
    ("body", "peg_head_axis_3"),
    ("lip", "packet_exit"),
    ("chassis", "rod_shaft_path"),
    ("crank", "button_peg_path"),
    ("pusher", "peg_slot_path"),
]


# --------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def p():
    return load_params()


@pytest.fixture(scope="module")
def spec(p):
    return prototype_assembly(p)


@pytest.fixture(scope="module")
def bodies(spec):
    return {body.body_id: body for body in spec.bodies}


@pytest.fixture(scope="module")
def cad_shapes(p):
    """Exact CAD solids at fraction 0, taken from the geometry helpers, not the adapter."""
    link = linkage_from(p)
    rest = pose_at_phi(link, link.phi0)
    static = static_solids(p, link, DEFAULT_GAP)
    moving = moving_solids(p, link, rest, compressed_length(0.0))
    return {
        "body": static["body"],
        "lip": static["lip"],
        "chassis": static["chassis"],
        "crank": moving["crank"],
        "rod": moving["rod"],
        "pusher": moving["pusher"],
    }


@pytest.fixture(scope="module")
def compiled(p, tmp_path_factory):
    mujoco = require_mujoco()
    outdir = tmp_path_factory.mktemp("pocky-collider-scene")
    export = compile_scene(p, outdir)
    assert export.model is not None, "the scene did not compile"
    return mujoco, export.model


# --------------------------------------------------------------------------- helpers
def _colliders(body) -> tuple[ColliderSpec, ...]:
    return tuple(c for part in body.parts for c in part.colliders)


def _overlap_mm3(shape, point, radius: float = 0.15) -> float:
    """Volume of the exact CAD solid inside a small sphere at ``point``."""
    common = shape.intersect(Pos(*point) * Sphere(radius))
    if common is None:
        return 0.0
    items = common if isinstance(common, (list, tuple)) else [common]
    return sum(float(item.volume) for item in items if item is not None)


def _group_aabb(body) -> tuple[float, float, float, float, float, float]:
    boxes = [part.shape.bounding_box() for part in body.parts if part.shape is not None]
    return (
        min(box.min.X for box in boxes), max(box.max.X for box in boxes),
        min(box.min.Y for box in boxes), max(box.max.Y for box in boxes),
        min(box.min.Z for box in boxes), max(box.max.Z for box in boxes),
    )


def _world_xy(link, x: float, y: float) -> tuple[float, float]:
    """A crank-local point rotated by the CAD's own fraction-0 crank angle."""
    location = Pos(link.pivot_x, link.pivot_y, 0.0) * Rot(
        0.0, 0.0, math.degrees(link.phi0)) * Pos(x, y, 0.0)
    return location.position.X, location.position.Y


# --------------------------------------------------------------------------- contracts
def test_every_declared_fidelity_contract_passes(bodies):
    for body_id in PRODUCT_BODIES:
        body = bodies[body_id]
        assert body.fidelity is not None
        assert body.fidelity.max_coverage_gap_mm <= COVERAGE_GAP_MM
        assert body.fidelity.max_surface_deviation_mm <= CRITICAL_TOL_MM

        result = validate_fidelity(body, body.fidelity)
        assert result.ok, (body_id, result.violations)
        assert result.metrics["coverage_max_gap_mm"] <= COVERAGE_GAP_MM
        deviation = result.metrics.get("critical_surface_max_deviation_mm")
        if deviation is not None:
            assert deviation <= CRITICAL_TOL_MM


@pytest.mark.parametrize("body_id,probe_id", PROBE_IDS)
def test_declared_probes_are_exact_cad_voids(body_id, probe_id, bodies, cad_shapes):
    body = bodies[body_id]
    probe = next(p for p in body.fidelity.probes if p.probe_id == probe_id)
    colliders = _colliders(body)
    shape = cad_shapes[body_id]
    for point in probe.points_mm:
        assert _overlap_mm3(shape, point) <= VOID_NOISE_MM3, (
            f"{body_id} probe {probe_id!r} point {point} is exact-CAD material")
        assert not any(contains(c, point, margin_mm=0.05) for c in colliders), (
            f"{body_id} probe {probe_id!r} point {point} is inside a collider")


@pytest.mark.parametrize("body_id,transit_id", TRANSIT_IDS)
def test_declared_transits_are_exact_cad_voids(body_id, transit_id, bodies, cad_shapes):
    body = bodies[body_id]
    transit = next(t for t in body.fidelity.transits if t.transit_id == transit_id)
    shape = cad_shapes[body_id]
    start = transit.start_mm
    end = transit.end_mm
    for index in range(5):
        t = index / 4.0
        point = tuple(start[i] + (end[i] - start[i]) * t for i in range(3))
        assert _overlap_mm3(shape, point, transit.radius_mm) <= VOID_NOISE_MM3, (
            f"{body_id} transit {transit_id!r} is blocked by exact-CAD material at {point}")


# --------------------------------------------------------------------------- features
def test_f1_peg_relief_is_local(p, bodies, cad_shapes):
    link = linkage_from(p)
    f1 = pose_at_phi(link, phi_for_button_fraction(link, 1.0))
    shape = cad_shapes["body"]
    colliders = _colliders(bodies["body"])

    centre = (f1.pusher_pin_x, f1.pusher_pin_y - 3.0, -1.2)
    assert _overlap_mm3(shape, centre) <= VOID_NOISE_MM3
    assert not any(contains(c, centre, margin_mm=0.05) for c in colliders)

    # The cut circle reaches y = 31.401 mm at this x: void just inside, material just out.
    assert _overlap_mm3(shape, (f1.pusher_pin_x, 31.45, -1.2), 0.05) <= VOID_NOISE_MM3
    assert _overlap_mm3(shape, (f1.pusher_pin_x, 31.30, -1.2), 0.05) > MATERIAL_MM3

    # Local in x: the CAD has material just outside the band and the colliders cover it,
    # so the relief is not a long strip.
    for x in (-57.5, -48.5):
        point = (x, 32.0, -1.2)
        assert _overlap_mm3(shape, point, 0.05) > MATERIAL_MM3
        assert any(contains(c, point, margin_mm=0.5) for c in colliders)

    relief = [
        c for c in colliders
        if c.collider_id.startswith("floor_north_relief_")
        or c.collider_id in ("floor_relief_skin", "side_north_relief")
    ]
    assert relief
    for collider in relief:
        low, high = collider_aabb_mm(collider)
        assert low[0] >= RELIEF_X_BAND[0] - 1e-6
        assert high[0] <= RELIEF_X_BAND[1] + 1e-6


def test_through_floor_slot_is_open(p, bodies, cad_shapes):
    link = linkage_from(p)
    sx0, sx1, sy0, sy1 = floor_slot_bounds(link)
    shape = cad_shapes["body"]
    colliders = _colliders(bodies["body"])

    for point in (
        (0.5 * (sx0 + sx1), 0.0, -1.2),
        (sx0 + 0.5, 0.0, -1.2),
        (sx1 - 0.5, 0.0, -1.2),
    ):
        assert _overlap_mm3(shape, point, 0.05) <= VOID_NOISE_MM3
        assert not any(contains(c, point, margin_mm=0.05) for c in colliders)

    for point in (
        (sx0 - 1.0, 0.0, -1.2),
        (sx1 + 1.0, 0.0, -1.2),
        (-60.0, sy0 - 1.0, -1.2),
        (-60.0, sy1 + 1.0, -1.2),
    ):
        assert _overlap_mm3(shape, point, 0.05) > MATERIAL_MM3
        assert any(contains(c, point, margin_mm=0.5) for c in colliders)


def test_boss_bore_and_head_relief_are_open(p, bodies, cad_shapes):
    link = linkage_from(p)
    chassis_shape = cad_shapes["chassis"]
    chassis_colliders = _colliders(bodies["chassis"])
    for sign in (-1.0, 1.0):
        point = (link.pivot_x + sign * 4.2, link.pivot_y, -17.0)
        assert _overlap_mm3(chassis_shape, point, 0.05) <= VOID_NOISE_MM3
        assert not any(contains(c, point, margin_mm=0.05) for c in chassis_colliders)
    point = (link.pivot_x, link.pivot_y + 4.2, -17.0)
    assert _overlap_mm3(chassis_shape, point, 0.05) <= VOID_NOISE_MM3
    assert not any(contains(c, point, margin_mm=0.05) for c in chassis_colliders)

    material = (link.pivot_x + 8.0, link.pivot_y, -17.0)
    assert _overlap_mm3(chassis_shape, material, 0.05) > MATERIAL_MM3

    # The crank's own pivot bore is the declared probe exception: void in the CAD and
    # free of crank geometry, not a solid boss.
    crank = bodies["crank"]
    bore = next(probe for probe in crank.fidelity.probes if probe.probe_id == "pivot_bore")
    crank_colliders = _colliders(crank)
    for point in bore.points_mm:
        assert _overlap_mm3(cad_shapes["crank"], point, 0.05) <= VOID_NOISE_MM3
        assert not any(contains(c, point, margin_mm=0.05) for c in crank_colliders)


def test_crank_button_slot_and_both_end_caps_are_open(p, bodies, cad_shapes):
    link = linkage_from(p)
    zc = 0.5 * (link.crank_z0 + link.crank_z1)
    shape = cad_shapes["crank"]
    colliders = _colliders(bodies["crank"])

    for local in ((-21.5, 0.0), (-20.0, 0.5), (-23.0, -0.5), (-25.5, 0.6), (-17.5, 0.6)):
        wx, wy = _world_xy(link, *local)
        point = (wx, wy, zc)
        assert _overlap_mm3(shape, point, 0.05) <= VOID_NOISE_MM3
        assert not any(contains(c, point, margin_mm=0.05) for c in colliders)

    wx, wy = _world_xy(link, -21.5, 2.5)
    assert _overlap_mm3(shape, (wx, wy, zc), 0.05) > MATERIAL_MM3


def test_pusher_y_slot_and_both_end_caps_are_open(p, bodies, cad_shapes):
    link = linkage_from(p)
    rest = pose_at_phi(link, link.phi0)
    pin_x = rest.pusher_pin_x
    y_lo, y_hi = pusher_slot_ends(link)
    shape = cad_shapes["pusher"]
    colliders = _colliders(bodies["pusher"])

    for point in (
        (pin_x, 0.5 * (y_lo + y_hi), -4.0),
        (pin_x, y_lo + 2.0, -5.0),
        (pin_x, y_hi - 2.0, -5.0),
        (pin_x + 1.2, y_hi + 1.2, -4.0),
        (pin_x - 1.2, y_lo - 1.2, -4.0),
    ):
        assert _overlap_mm3(shape, point, 0.05) <= VOID_NOISE_MM3
        assert not any(contains(c, point, margin_mm=0.05) for c in colliders)

    for x in (pin_x - 3.0, pin_x + 3.0):
        assert _overlap_mm3(shape, (x, 0.5 * (y_lo + y_hi), -5.0), 0.05) > MATERIAL_MM3


def test_bullnose_crest_is_r2_1_and_matches_the_cad(p, bodies, cad_shapes):
    assert NOSE_R == pytest.approx(2.1)
    link = linkage_from(p)
    rest = pose_at_phi(link, link.phi0)
    cx = rest.face_x - NOSE_R
    crest = (cx, 0.0, 2.0 * NOSE_R)
    shape = cad_shapes["pusher"]

    assert float(shape.distance_to(Vertex(*crest))) == pytest.approx(0.0, abs=1e-6)
    assert _overlap_mm3(shape, (cx, 0.0, 2.0 * NOSE_R + 0.2), 0.05) <= VOID_NOISE_MM3
    assert _overlap_mm3(shape, (cx, 0.0, 2.0 * NOSE_R - 0.2), 0.05) > MATERIAL_MM3

    bullnose = next(c for c in _colliders(bodies["pusher"])
                    if c.collider_id == "bullnose")
    assert bullnose.kind == "cylinder"
    assert bullnose.size_mm[0] == pytest.approx(NOSE_R, abs=1e-9)
    assert abs(signed_distance_mm(bullnose, crest)) <= CRITICAL_TOL_MM


def test_separator_gap_and_packet_exit_are_open(p, bodies, cad_shapes):
    gap = p.separator.gap
    shape = cad_shapes["lip"]
    colliders = _colliders(bodies["lip"])

    for point in (
        (82.0, 0.0, gap - 0.25),
        (86.0, 10.0, gap - 0.25),
        (86.0, -10.0, gap - 0.25),
    ):
        assert _overlap_mm3(shape, point) <= VOID_NOISE_MM3
        assert not any(contains(c, point, margin_mm=0.05) for c in colliders)

    assert _overlap_mm3(shape, (82.0, 0.0, gap + 1.2), 0.05) > MATERIAL_MM3
    assert _overlap_mm3(shape, (82.0, 0.0, gap - 1.0), 0.05) <= VOID_NOISE_MM3

    for x in (79.0, 90.0, 100.0, 108.0):
        point = (x, 0.0, 2.6)
        assert _overlap_mm3(shape, point, 1.0) <= VOID_NOISE_MM3
        assert not any(contains(c, point, margin_mm=0.05) for c in colliders)


# --------------------------------------------------------------------------- negatives
def test_whole_body_hull_fails_the_body_contract(bodies):
    body = bodies["body"]
    assert validate_fidelity(body, body.fidelity).ok is True

    x0, x1, y0, y1, z0, z1 = _group_aabb(body)
    hull = ColliderSpec(
        collider_id="hull_box", kind="box",
        size_mm=((x1 - x0) / 2.0, (y1 - y0) / 2.0, (z1 - z0) / 2.0),
        pos_mm=((x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0),
    )
    hulled = replace(
        body,
        parts=body.parts + (
            PartSpec(part_id="hull_part", shape=None, colliders=(hull,)),
        ),
    )
    result = validate_fidelity(hulled, body.fidelity)
    assert result.ok is False
    assert any(
        "floor_slot" in violation and "declared void is filled" in violation
        for violation in result.violations
    ), result.violations


def test_filled_crank_slot_fails_the_crank_contract(p, bodies):
    link = linkage_from(p)
    crank = bodies["crank"]
    assert validate_fidelity(crank, crank.fidelity).ok is True

    phi_deg = math.degrees(link.phi0)
    wx, wy = _world_xy(link, -21.5, 0.0)
    fill = ColliderSpec(
        collider_id="slot_fill", kind="box", size_mm=(3.547, 2.15, 2.0),
        pos_mm=(wx, wy, 0.5 * (link.crank_z0 + link.crank_z1)),
        rot_deg=(0.0, 0.0, phi_deg),
    )
    filled = replace(
        crank,
        parts=crank.parts + (
            PartSpec(part_id="slot_fill_part", shape=None, colliders=(fill,)),
        ),
    )
    result = validate_fidelity(filled, crank.fidelity)
    assert result.ok is False
    assert any(
        "button_slot" in violation and "declared void is filled" in violation
        for violation in result.violations
    ), result.violations


# --------------------------------------------------------------------------- compiled
def test_critical_clearances_match_cad_at_all_five_fractions(p, compiled):
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
    assert rows
    # Every declared pair at every declared fraction is in the audit, including the
    # bullnose/floor contact pair; nothing is silently dropped.
    expected = {
        (fraction, pair.pair_id) for pair in PAIRS for fraction in pair.fractions
    }
    assert set(rows) == expected
    for (fraction, pair), row in rows.items():
        assert row["ok"] is True, (fraction, pair, row)
        assert row["cad_distance_mm"] is not None
        assert row["collider_distance_mm"] is not None
        assert row["difference_mm"] is not None
        assert row["difference_mm"] <= CRITICAL_TOL_MM

    # The reported transforms are the real compiled ones: the pusher xpos is the CAD
    # reset at every fraction, not a reused fraction-0 pose.
    pusher_x = {
        fraction["fraction"]: fraction["transforms"]["pusher"]["xpos_m"][0]
        for fraction in audit["fractions"]
    }
    for fraction in RESET_FRACTIONS:
        expected = reset_state(p, fraction).pusher_x_m
        assert pusher_x[fraction] - pusher_x[0.0] == pytest.approx(expected, abs=1e-6)

    relief = rows[(1.0, "body_crank_relief")]
    assert relief["collider_distance_mm"] == pytest.approx(0.19, abs=CRITICAL_TOL_MM)
    assert relief["cad_distance_mm"] == pytest.approx(0.19, abs=CRITICAL_TOL_MM)

    lip_rod = rows[(1.0, "lip_rod_head")]
    assert lip_rod["collider_distance_mm"] == pytest.approx(0.30, abs=CRITICAL_TOL_MM)
    assert lip_rod["cad_distance_mm"] == pytest.approx(0.30, abs=CRITICAL_TOL_MM)

    # The bullnose/floor tangency is a measured contact, not a clearance: a positive
    # gap would hide the 0.027 mm plan value behind a cropped face pair.
    contact = rows[(0.0, "body_pusher_bullnose_contact")]
    assert contact["cad_distance_mm"] == pytest.approx(0.0, abs=CRITICAL_TOL_MM)
    assert abs(contact["collider_distance_mm"]) <= CRITICAL_TOL_MM


def test_compiled_scene_has_no_equality_constraints_or_actuators(compiled):
    """Contacts and joints only: no equality weld and no hidden input."""
    _, model = compiled
    assert int(model.neq) == 0
    assert int(model.nu) == 0


def test_initial_validity_is_scene_valid_at_all_five_fractions(p, compiled):
    mujoco, model = compiled
    audit = initial_validity_audit(mujoco, model, p)
    assert audit["ok"] is True
    assert audit["verdict"] == "SCENE_VALID"
    assert audit["exact_overlap"]["ok"] is True
    noise = audit["exact_overlap"]["noise_threshold_mm3"]

    fractions = {fraction["fraction"]: fraction for fraction in audit["fractions"]}
    assert set(fractions) == set(RESET_FRACTIONS)
    for fraction, row in fractions.items():
        exact = row["exact_overlap"]
        penetration = row["collider_penetration"]
        assert exact is not penetration, "exact overlap and collider penetration differ"
        assert exact["ok"] is True, (fraction, exact["overlaps"])
        assert exact["overlaps"] == []
        assert exact["worst_overlap_mm3"] <= noise
        assert penetration["ok"] is True, (fraction, penetration["penetrations"])
        assert penetration["penetrations"] == []
        assert penetration["worst_m"] > -1e-6


def test_no_hull_no_filled_slot_and_a_local_relief_band(p, bodies, cad_shapes):
    for body_id in PRODUCT_BODIES:
        body = bodies[body_id]
        colliders = _colliders(body)
        assert len(colliders) > 1
        assert not any(c.kind == "convex" for c in colliders)

        x0, x1, y0, y1, z0, z1 = _group_aabb(body)
        for collider in colliders:
            low, high = collider_aabb_mm(collider)
            contains_body = (
                low[0] <= x0 + 1e-9 and low[1] <= y0 + 1e-9 and low[2] <= z0 + 1e-9
                and high[0] >= x1 - 1e-9 and high[1] >= y1 - 1e-9
                and high[2] >= z1 - 1e-9
            )
            assert not contains_body, (body_id, collider.collider_id)

    link = linkage_from(p)
    sx0, sx1, _, _ = floor_slot_bounds(link)
    body_colliders = _colliders(bodies["body"])
    slot_centre = (0.5 * (sx0 + sx1), 0.0, -1.2)
    assert not any(contains(c, slot_centre, margin_mm=0.05) for c in body_colliders)

    f1 = pose_at_phi(link, phi_for_button_fraction(link, 1.0))
    relief_centre = (f1.pusher_pin_x, f1.pusher_pin_y - 3.0, -1.2)
    assert not any(contains(c, relief_centre, margin_mm=0.05) for c in body_colliders)

    relief = [
        c for c in body_colliders
        if c.collider_id.startswith("floor_north_relief_")
        or c.collider_id in ("floor_relief_skin", "side_north_relief")
    ]
    assert relief
    spans = []
    for collider in relief:
        low, high = collider_aabb_mm(collider)
        spans.append(high[0] - low[0])
        assert low[0] >= RELIEF_X_BAND[0] - 1e-6
        assert high[0] <= RELIEF_X_BAND[1] + 1e-6
    assert max(spans) <= (RELIEF_X_BAND[1] - RELIEF_X_BAND[0]) + 1e-6

    body_box = cad_shapes["body"].bounding_box()
    body_length = body_box.max.X - body_box.min.X
    assert max(spans) < body_length / 10.0
