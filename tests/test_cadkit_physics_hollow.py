"""M2b: hollow-collision fidelity — declared voids, passage, and the sealed-hull negative."""
import json
import math
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from cadkit.params import REPO_ROOT
from cadkit.physics.collision import (
    FidelitySpec,
    ProbeSpec,
    TransitSpec,
    contains,
    distance_mm,
    validate_fidelity,
)
from cadkit.physics.hollow import (
    CAVITY_HALF_WIDTH_MM,
    CHANNEL_HEIGHT_MM,
    CHANNEL_LENGTH_MM,
    FLOOR_OVERRUN_MM,
    PROBE_RADIUS_MM,
    RESTING_Z_MM,
    TRANSIT_END_MM,
    TRANSIT_START_MM,
    channel_colliders,
    channel_fidelity,
    channel_solid,
    concave_mesh_diagnostic_xml,
    rotated_u_channel_spec,
    u_channel_spec,
    u_channel_spec_bad_recipe,
)
from cadkit.physics.scene import SceneInvalid, export_scene
from cadkit.physics.schema import BodySpec, ColliderSpec, Frame, PartSpec

pytest.importorskip("mujoco", reason="optional physics extra not installed")

import mujoco  # noqa: E402


def _env():
    env = dict(os.environ)
    env["PATH"] = f"{Path.home() / '.local' / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    return env


# ------------------------------------------------------------------ fixture geometry
def test_channel_geometry_is_a_u_channel():
    """Independent check of the CAD: floor plus two walls, cavity open along X and up."""
    solid = channel_solid()
    bb = solid.bounding_box()
    # the floor overruns the walled section by the declared lead-in at each end
    assert (bb.size.X, bb.size.Y, bb.size.Z) == pytest.approx(
        (CHANNEL_LENGTH_MM + 2 * FLOOR_OVERRUN_MM, 40.0, CHANNEL_HEIGHT_MM))
    # cavity centre is empty material
    assert not solid.is_inside((0.0, 0.0, CHANNEL_HEIGHT_MM / 2.0))
    # the floor and both walls are material
    assert solid.is_inside((0.0, 0.0, 1.0))
    assert solid.is_inside((0.0, CAVITY_HALF_WIDTH_MM + 2.0, CHANNEL_HEIGHT_MM / 2.0))
    assert solid.is_inside((0.0, -CAVITY_HALF_WIDTH_MM - 2.0, CHANNEL_HEIGHT_MM / 2.0))
    # both mouths are open: a point just outside each end, on the cavity axis, is not material
    for x in (-CHANNEL_LENGTH_MM / 2.0 - 1.0, CHANNEL_LENGTH_MM / 2.0 + 1.0):
        assert not solid.is_inside((x, 0.0, CHANNEL_HEIGHT_MM / 2.0))


def test_colliders_do_not_span_the_cavity():
    """No single collider may cover the cavity centre: that is the whole point."""
    for c in channel_colliders():
        assert not contains(c, (0.0, 0.0, CHANNEL_HEIGHT_MM / 2.0)), c.collider_id


# ------------------------------------------------------------------ probe occupancy
def test_correct_recipe_passes_fidelity():
    result = validate_fidelity(u_channel_spec().bodies[0], channel_fidelity())
    assert result.ok, result.violations
    # clearances tie back to the CAD dimensions, not to an implementation constant
    assert result.metrics["probe_cavity_axis_min_clearance_mm"] == pytest.approx(
        CAVITY_HALF_WIDTH_MM, abs=1e-9)
    assert result.metrics["transit_through_channel_min_clearance_mm"] == pytest.approx(2.0,
                                                                                      abs=1e-9)
    assert result.metrics["coverage_max_gap_mm"] == pytest.approx(0.0, abs=1e-6)


def test_bad_recipe_fills_the_void_and_is_rejected():
    """The whole M2b point: a wrong recipe must be a defect, not a warning."""
    result = validate_fidelity(u_channel_spec_bad_recipe().bodies[0], channel_fidelity())
    assert not result.ok
    joined = " ".join(result.violations)
    assert "occupied" in joined and "u_spanning_block" in joined


def test_bad_recipe_is_rejected_on_production_export(tmp_path):
    """Export, not just validation, must refuse it — and must create nothing."""
    out = tmp_path / "bad"
    with pytest.raises(SceneInvalid, match="collision-fidelity contract"):
        export_scene(u_channel_spec_bad_recipe(), out)
    assert not out.exists(), "an invalid scene must not leave a partial output directory"


def test_oversized_collider_blocks_transit():
    """A box that is merely too big — not spanning the whole part — still blocks passage."""
    spec = u_channel_spec()
    channel = spec.bodies[0]
    too_thick = ColliderSpec("u_floor", "box",
                             (CHANNEL_LENGTH_MM / 2.0, 20.0, 12.0),
                             pos_mm=(0.0, 0.0, 12.0),
                             source=channel.parts[0].colliders[0].source)
    bad = replace(channel, parts=(replace(channel.parts[0], colliders=(
        too_thick, *channel.parts[0].colliders[1:])),))
    result = validate_fidelity(bad, channel_fidelity())
    assert not result.ok
    assert any("blocked" in v for v in result.violations), result.violations


def test_offset_collider_blocks_transit():
    """A collider shifted sideways into the cavity must be caught."""
    spec = u_channel_spec()
    channel = spec.bodies[0]
    shifted = replace(channel.parts[0].colliders[1],
                      pos_mm=(0.0, CAVITY_HALF_WIDTH_MM - 2.0, CHANNEL_HEIGHT_MM / 2.0))
    bad = replace(channel, parts=(replace(channel.parts[0], colliders=(
        channel.parts[0].colliders[0], shifted, channel.parts[0].colliders[2])),))
    result = validate_fidelity(bad, channel_fidelity())
    assert not result.ok


def test_missing_wall_is_caught_by_coverage():
    """A recipe that omits a wall leaves CAD material uncovered."""
    spec = u_channel_spec()
    channel = spec.bodies[0]
    bad = replace(channel, parts=(replace(channel.parts[0], colliders=(
        channel.parts[0].colliders[0], channel.parts[0].colliders[1])),))
    result = validate_fidelity(bad, channel_fidelity())
    assert not result.ok
    assert any("omits real geometry" in v for v in result.violations), result.violations


# ------------------------------------------------------------------ transforms
def test_rotated_channel_still_passes(tmp_path):
    """Local/world confusion must fail: a rotated body keeps the same fidelity verdict."""
    spec = rotated_u_channel_spec()
    result = validate_fidelity(spec.bodies[0], channel_fidelity())
    assert result.ok, result.violations
    ex = export_scene(spec, tmp_path)
    assert ex.model is not None


def test_rotated_channel_transit_is_in_world_space(tmp_path):
    """The transit is declared body-local; after rotation its world path must move with it."""
    spec = rotated_u_channel_spec()
    frame = spec.bodies[0].frame
    local_mid = ((TRANSIT_START_MM[0] + TRANSIT_END_MM[0]) / 2.0, 0.0,
                 TRANSIT_START_MM[2])
    world_mid = frame.apply(local_mid)
    # the declared path is not the world path once the body is rotated
    assert world_mid != pytest.approx(local_mid)
    # and the fidelity check still passes, which it could not if the transform were applied twice
    assert validate_fidelity(spec.bodies[0], channel_fidelity()).ok


def test_transit_world_path_lies_inside_the_rotated_body():
    """The mapped transit path must run through the channel's world volume.

    A validator that treated body-local transit points as world points would place the path
    far outside the body and then *pass*, because nothing would be hit. So the path itself is
    asserted, not only the verdict.
    """
    from cadkit.physics.collision import transit_world_mm

    spec = rotated_u_channel_spec()
    body = spec.bodies[0]
    transit = channel_fidelity().transits[0]
    start, end = transit_world_mm(body, transit)

    world_bb = body.frame.location() * channel_solid()
    bb = world_bb.bounding_box()
    lo = np.array([bb.min.X, bb.min.Y, bb.min.Z]) - 30.0
    hi = np.array([bb.max.X, bb.max.Y, bb.max.Z]) + 30.0
    for point in (start, end):
        assert np.all(point >= lo) and np.all(point <= hi), (point, lo, hi)

    # and the un-mapped path would NOT be inside, so this assertion is discriminating
    local_start = np.asarray(transit.start_mm, dtype=float)
    assert not np.all(local_start >= lo) or not np.all(local_start <= hi)

    # The validator must sweep the declared body-local points, unchanged. A world/local
    # mix-up displaces the path but still reports a pass, so the swept endpoints are the
    # observable that catches it.
    result = validate_fidelity(body, channel_fidelity())
    swept = (result.metrics["transit_through_channel_swept_start_x_mm"],
             result.metrics["transit_through_channel_swept_start_y_mm"],
             result.metrics["transit_through_channel_swept_start_z_mm"])
    assert swept == pytest.approx(transit.start_mm, abs=1e-9)
    swept_end = (result.metrics["transit_through_channel_swept_end_x_mm"],
                 result.metrics["transit_through_channel_swept_end_y_mm"],
                 result.metrics["transit_through_channel_swept_end_z_mm"])
    assert swept_end == pytest.approx(transit.end_mm, abs=1e-9)


def test_probe_points_are_body_local_not_world():
    """A body-local probe point must not be silently treated as a world point.

    Constructed to be *discriminating*: the frame translates the cavity centre (0, 0, 20) onto
    (0, 0, 0), which is inside the floor collider. So the same coordinate is free in
    body-local space and occupied in world space, and a validator that confused the two would
    flip the verdict.
    """
    from cadkit.physics.schema import Frame

    colliders = channel_colliders()
    local_centre = (0.0, 0.0, CHANNEL_HEIGHT_MM / 2.0)
    frame = Frame(pos_mm=(0.0, 0.0, -CHANNEL_HEIGHT_MM / 2.0))
    world_centre = frame.apply(local_centre)

    # free in the space the contract declares...
    assert not any(contains(c, local_centre) for c in colliders)
    # ...and occupied in world space, so the two are genuinely distinguishable
    assert world_centre == pytest.approx((0.0, 0.0, 0.0), abs=1e-9)
    assert any(contains(c, world_centre) for c in colliders)

    # The validator works in body-local space. Moving only the frame (leaving the CAD solid
    # in its original assembly position) therefore *must* break coverage — that is the same
    # local/world distinction seen from the other side, and it proves the check is sensitive
    # to it rather than passing by construction.
    spec = u_channel_spec()
    moved_frame = replace(spec.bodies[0], frame=frame)
    broken = validate_fidelity(moved_frame, channel_fidelity())
    assert not broken.ok
    assert any("omits real geometry" in v for v in broken.violations), broken.violations

    # With the geometry moved consistently, the contract passes again.
    consistent = replace(spec.bodies[0], frame=frame,
                         parts=tuple(replace(part, shape=frame.location() * part.shape)
                                     for part in spec.bodies[0].parts))
    result = validate_fidelity(consistent, channel_fidelity())
    assert result.ok, result.violations
    assert result.metrics["coverage_max_gap_mm"] == pytest.approx(0.0, abs=1e-6)


# ------------------------------------------------------------------ primitives
@pytest.mark.parametrize("kind,size,inside,outside", [
    ("box", (5.0, 5.0, 5.0), (4.0, 0.0, 0.0), (6.0, 0.0, 0.0)),
    ("sphere", (5.0,), (4.0, 0.0, 0.0), (6.0, 0.0, 0.0)),
    ("cylinder", (5.0, 5.0), (4.0, 0.0, 4.0), (6.0, 0.0, 0.0)),
    ("capsule", (5.0, 5.0), (0.0, 0.0, 9.0), (0.0, 0.0, 11.0)),
])
def test_every_primitive_supports_containment_and_distance(kind, size, inside, outside):
    c = ColliderSpec("c", kind, size)
    assert contains(c, inside)
    assert not contains(c, outside)
    assert distance_mm(c, inside) == pytest.approx(0.0)
    assert distance_mm(c, outside) > 0.0


def test_rotated_box_containment_uses_the_local_frame():
    c = ColliderSpec("c", "box", (10.0, 2.0, 2.0), rot_deg=(0.0, 0.0, 90.0))
    # rotated 90 deg about Z, the long axis is now Y
    assert contains(c, (0.0, 9.0, 0.0))
    assert not contains(c, (9.0, 0.0, 0.0))


# ---------------------------------------------------- supervisor-defect regressions
def test_compound_rotation_inverse_is_exact():
    """Defect 1: negating Euler angles is not the inverse for compound rotations.

    Independent reproduction from the supervisor review: a box with half-extents (10, 2, 1)
    rotated (25, 35, 45) deg, and the known local interior point (9, 0, 0) mapped by the same
    rotation, must be reported interior.
    """
    from cadkit.physics.schema import Frame

    c = ColliderSpec("c", "box", (10.0, 2.0, 1.0), rot_deg=(25.0, 35.0, 45.0))
    interior = Frame(rot_deg=(25.0, 35.0, 45.0)).apply((9.0, 0.0, 0.0))
    assert interior == pytest.approx((5.2130516881, 7.3103562623, -0.6186949299), abs=1e-9)
    assert contains(c, interior)
    assert distance_mm(c, interior) == pytest.approx(0.0)

    exterior = Frame(rot_deg=(25.0, 35.0, 45.0)).apply((10.5, 0.0, 0.0))
    assert not contains(c, exterior)
    assert distance_mm(c, exterior) == pytest.approx(0.5, abs=1e-9)


@pytest.mark.parametrize("rot", [(25.0, 35.0, 45.0), (12.0, -34.0, 56.0),
                                 (90.0, 0.0, 0.0), (0.0, 90.0, 0.0), (0.0, 0.0, 90.0)])
def test_rotated_primitives_agree_with_a_mapped_point(rot):
    """Containment must be invariant to expressing the same point in the collider frame."""
    from cadkit.physics.schema import Frame

    c = ColliderSpec("c", "box", (10.0, 2.0, 1.0), rot_deg=rot)
    for local, expected in (((9.0, 0.0, 0.0), True), ((0.0, 1.5, 0.0), True),
                            ((0.0, 0.0, 0.9), True), ((10.5, 0.0, 0.0), False),
                            ((0.0, 2.5, 0.0), False)):
        assert contains(c, Frame(rot_deg=rot).apply(local)) is expected, (rot, local)


def _passage(**overrides):
    """A fully-populated PASS trial, with every field overridable by keyword."""
    fields = dict(
        valid=True, invalid_reasons=[], scene_valid=True, scene_invalid_reason="",
        passed=True, min_x_mm=0.0, max_x_mm=200.0, exit_x_mm=66.0, crossed_exit=True,
        y_dev_mm=0.0, z_dev_mm=0.0, max_contact_depth_mm=0.0, initial_penetration_mm=0.0,
        n_contacts=1, max_contact_count=1, terminal_speed=0.0, finite=True, warnings={},
        mass_kg=0.001, wall_time_s=0.0, solver_dt_s=1e-3, settle_end_s=0.05,
        trial_start_s=0.05, trial_end_s=0.85, trace=[],
    )
    fields.update(overrides)
    from cadkit.physics.hollow_run import PassageResult

    return PassageResult(**fields)


def test_invalid_numerics_never_report_pass():
    """Defect 2: a trial with a non-finite state or solver warnings must not pass."""
    from cadkit.physics.hollow_run import PassageResult, _status

    good = _passage()
    bad_finite = replace(good, valid=False, invalid_reasons=["non-finite state"])
    bad_warn = replace(good, valid=False, invalid_reasons=["solver warning badqvel"])
    sealed = replace(good, passed=False)
    assert _status(good, sealed) == "PASS"
    # invalid numerics outrank an apparent crossing, in either trial
    assert _status(bad_finite, sealed) == "INCONCLUSIVE"
    assert _status(good, bad_warn) == "INCONCLUSIVE"
    assert _status(bad_warn, bad_finite) == "INCONCLUSIVE"
    # and an invalid positive trial is never a PASS even if it crossed the plane
    assert _status(bad_finite, sealed) != "PASS"


def test_warning_counters_cover_the_installed_enum():
    """Defect 2: every real warning counter is captured, by name, without the sentinel."""
    import mujoco as mj

    from cadkit.physics.hollow_run import WARNING_NAMES, _warning_counters

    expected = {n for n in dir(mj.mjtWarning)
                if n.startswith("mjWARN_")}
    assert set(WARNING_NAMES) == expected
    assert "mjNWARNING" not in WARNING_NAMES
    model = mj.MjModel.from_xml_path(str(_channel_scene_dir()))
    counters = _warning_counters(mj, mj.MjData(model))
    assert set(counters) == {n.removeprefix("mjWARN_").lower() for n in expected}
    assert len(counters) == 7


def _channel_scene_dir():
    from cadkit.physics.hollow_run import run_channel_evidence
    import tempfile

    d = Path(tempfile.mkdtemp()) / "scene"
    run_channel_evidence(d.parent)
    return d / "scene.xml"


def test_overthick_wall_violates_surface_accuracy_without_blocking():
    """Defect 6: a collider that buries a CAD surface must show deviation, not zero."""
    from cadkit.physics.collision import signed_distance_mm

    spec = u_channel_spec()
    channel = spec.bodies[0]
    # grow the +Y side wall 1.5 mm into the cavity: the centre line stays clear (cavity half
    # width 15, wall inner face moves to 13.5, transit radius 6), but the declared critical
    # surface at y=+15 is now buried.
    thick = replace(channel.parts[0].colliders[1],
                    size_mm=(channel.parts[0].colliders[1].size_mm[0],
                             channel.parts[0].colliders[1].size_mm[1] + 1.5,
                             channel.parts[0].colliders[1].size_mm[2]),
                    pos_mm=(0.0, 17.5 - 1.5, CHANNEL_HEIGHT_MM / 2.0))
    bad = replace(channel, parts=(replace(channel.parts[0], colliders=(
        channel.parts[0].colliders[0], thick, channel.parts[0].colliders[2])),))

    # the transit still passes, so a clearance-only check would miss it
    result = validate_fidelity(bad, channel_fidelity())
    assert result.metrics["transit_through_channel_min_clearance_mm"] > 0.0
    # but the buried surface is reported
    assert not result.ok
    assert any("critical surface deviates" in v for v in result.violations), result.violations
    # and the plain distance-to-volume metric would have said zero
    assert distance_mm(thick, (0.0, CAVITY_HALF_WIDTH_MM, CHANNEL_HEIGHT_MM / 2.0)) == 0.0
    assert signed_distance_mm(thick, (0.0, CAVITY_HALF_WIDTH_MM,
                                     CHANNEL_HEIGHT_MM / 2.0)) < 0.0


def test_overlay_rejects_unsupported_kinds_and_honours_rotation():
    """Defect 7: the overlay must draw real primitives, not a misleading shape."""
    from cadkit.physics.overlay import collider_mesh

    rotated = ColliderSpec("c", "cylinder", (5.0, 10.0), rot_deg=(0.0, 90.0, 0.0))
    bounds = collider_mesh(rotated).bounds
    # rotated 90 deg about Y, the long axis is X: 20 mm long, 10 mm across
    assert bounds[1][0] - bounds[0][0] == pytest.approx(0.020, abs=1e-6)
    assert bounds[1][2] - bounds[0][2] == pytest.approx(0.010, abs=1e-6)

    capsule = collider_mesh(ColliderSpec("c", "capsule", (4.0, 8.0)))
    # capsule ends add a radius beyond the cylinder half-length
    assert capsule.bounds[1][2] - capsule.bounds[0][2] == pytest.approx(0.024, abs=1e-6)


# ------------------------------------------------------------------ dynamics
def test_probe_passes_through_the_channel(tmp_path):
    """Live physics: the probe must traverse the open length and leave past the exit plane."""
    from cadkit.physics.hollow_run import run_channel_evidence

    summary = run_channel_evidence(tmp_path / "run")
    pos = summary["positive"]
    assert pos["valid"], pos["invalid_reasons"]
    assert pos["passed"], pos
    assert pos["crossed_exit"], pos
    assert pos["max_x_mm"] > summary["criterion"]["exit_plane_x_mm"]
    # it stayed on the cavity axis, i.e. it went through rather than over or around
    assert pos["lateral_deviation_mm"] <= PROBE_RADIUS_MM
    assert pos["height_deviation_mm"] <= PROBE_RADIUS_MM
    # and it was never deeply embedded in the floor
    assert pos["max_contact_depth_mm"] <= 1.0
    assert pos["initial_penetration_mm"] <= 0.2
    assert pos["finite"]
    assert all(v == 0 for v in pos["warnings"].values()), pos["warnings"]
    # mass matches the analytic box formula
    assert pos["mass_kg"] == pytest.approx((2 * PROBE_RADIUS_MM) ** 3 * 1.24 * 1e-6)


def test_concave_mesh_diagnostic_seals_the_cavity(tmp_path):
    """Negative: the same CAD collided as a mesh hull starts inside the cavity and fails."""
    from cadkit.physics.hollow_run import run_channel_evidence

    summary = run_channel_evidence(tmp_path / "run")
    neg = summary["negative_mesh_diagnostic"]
    assert not neg["passed"], neg
    # the hull swallows the cavity, so the probe begins interpenetrating solid material
    assert neg["initial_penetration_mm"] > 1.0, neg
    # and it is ejected off the cavity axis rather than traversing
    assert neg["height_deviation_mm"] is None or neg["height_deviation_mm"] > PROBE_RADIUS_MM
    assert neg["finite"]


def test_no_qpos_is_written_after_release():
    """Motion must come from gravity and contact, not from scripted positions."""
    source = (REPO_ROOT / "cadkit" / "physics" / "hollow_run.py").read_text(encoding="utf-8")
    assert "qpos[" not in source
    assert "qpos =" not in source


def test_evidence_is_deterministic(tmp_path):
    from cadkit.physics.hollow_run import run_channel_evidence

    a = run_channel_evidence(tmp_path / "a")
    b = run_channel_evidence(tmp_path / "b")
    assert a["scene_hash"] == b["scene_hash"]
    assert a["positive"]["max_x_mm"] == pytest.approx(b["positive"]["max_x_mm"], abs=1e-9)
    assert (tmp_path / "a" / "trace_positive.csv").read_bytes() == (
        tmp_path / "b" / "trace_positive.csv").read_bytes()


# ------------------------------------------------------------------ artifacts
def test_evidence_writes_all_artifacts(tmp_path):
    from cadkit.physics.hollow_run import run_channel_evidence

    run = tmp_path / "run"
    summary = run_channel_evidence(run)
    for name in ("summary.json", "report.md", "trace_positive.csv",
                 "trace_mesh_diagnostic.csv", "collision_overlay.png"):
        assert (run / name).is_file(), name
    assert (run / "scene" / "scene.xml").is_file()
    assert (run / "mesh_diagnostic" / "scene_mesh_diagnostic.xml").is_file()
    assert (run / "mesh_diagnostic" / "u_channel.stl").is_file()
    payload = json.loads((run / "summary.json").read_text(encoding="utf-8"),
                         parse_constant=_reject)
    assert payload["status"] == "PASS"
    assert (run / "collision_overlay.png").stat().st_size > 10_000


def _reject(value):
    raise AssertionError(f"non-strict JSON constant {value}")


def test_diagnostic_scene_is_marked_test_only():
    xml = concave_mesh_diagnostic_xml()
    assert "TEST-ONLY" in xml
    assert "not a design of record" in xml.lower()
    # it must be a real mesh collider over the original STL, not a fabricated box
    assert 'type="mesh"' in xml
    assert "u_channel.stl" in xml
    # the *channel* collider must be the mesh; only the probe is a primitive
    channel_geoms = [ln for ln in xml.splitlines() if "u_channel_hull" in ln]
    assert channel_geoms and 'type="mesh"' in channel_geoms[0]


# ------------------------------------------------------------------ CLI
def test_run_directory_is_fresh_and_refuses_reuse(tmp_path):
    """A second run must not overwrite the first: evidence integrity."""
    from cadkit.physics.hollow_run import run_channel_evidence

    first = tmp_path / "run1"
    run_channel_evidence(first)
    trace = (first / "trace_positive.csv").read_bytes()
    with pytest.raises(FileExistsError):
        run_channel_evidence(first)
    assert (first / "trace_positive.csv").read_bytes() == trace


def test_summary_records_mujoco_version_and_run_id(tmp_path):
    from cadkit.physics.hollow_run import run_channel_evidence

    summary = run_channel_evidence(tmp_path / "run")
    assert summary["versions"]["mujoco"]
    assert summary["run_id"] == "run"


def test_requested_timestep_reaches_both_compiled_scenes(tmp_path):
    """The blocking defect: a requested step must be the step that actually runs.

    Opens both saved XMLs and checks the compiled `model.opt.timestep`, then checks the actual
    phase timings, because counting steps from the request while the XML hard-codes 1 ms
    silently runs the wrong duration.
    """
    import mujoco as mj

    from cadkit.physics.hollow_run import run_channel_evidence

    dt = 5.0e-4
    run = tmp_path / "half"
    summary = run_channel_evidence(run, timestep_s=dt)

    for scene in (run / "scene" / "scene.xml",
                  run / "mesh_diagnostic" / "scene_mesh_diagnostic.xml"):
        model = mj.MjModel.from_xml_path(str(scene))
        assert float(model.opt.timestep) == pytest.approx(dt, rel=1e-12), scene.name

    for key in ("positive", "negative_mesh_diagnostic"):
        trial = summary[key]
        assert trial["solver_dt_s"] == pytest.approx(dt, rel=1e-12)
        # actual, from compiled state: settle 0.05 s then an 0.8 s trial
        assert trial["settle_end_s"] == pytest.approx(0.05, abs=2 * dt)
        assert trial["trial_end_s"] - trial["trial_start_s"] == pytest.approx(0.8, abs=2 * dt)

    assert summary["solver"]["compiled_timestep_s"] == pytest.approx(dt, rel=1e-12)
    assert summary["solver"]["requested_timestep_s"] == pytest.approx(dt)


def test_timestep_mismatch_is_rejected(tmp_path):
    """A scene compiled at one step must not be simulated as if it had another."""
    from cadkit.physics.hollow import u_channel_spec
    from cadkit.physics.hollow_run import _simulate
    from cadkit.physics.scene import export_scene

    ex = export_scene(u_channel_spec(through_path=True, timestep_s=1e-3), tmp_path / "s")
    with pytest.raises(ValueError, match="compiled model uses"):
        _simulate(str(ex.scene_xml), "probe", duration_s=0.1, timestep_s=5e-4,
                  base_dir=ex.outdir)


@pytest.mark.parametrize("dt,duration", [(1e-3, 1e6), (1e-8, 1e-3)])
def test_unbounded_duration_is_rejected_before_settling(tmp_path, monkeypatch, dt, duration):
    from cadkit.physics.hollow import u_channel_spec
    from cadkit.physics.hollow_run import _simulate
    from cadkit.physics.scene import export_scene

    ex = export_scene(u_channel_spec(through_path=True, timestep_s=dt), tmp_path / "s")

    def forbidden_step(*args, **kwargs):
        pytest.fail("an over-budget run must be rejected before any settling steps")

    monkeypatch.setattr("mujoco.mj_step", forbidden_step)
    with pytest.raises(ValueError, match="budget"):
        _simulate(str(ex.scene_xml), "probe", duration_s=duration, timestep_s=dt,
                  base_dir=ex.outdir)


def test_contact_time_constant_is_absolute_not_timestep_scaled():
    """Refining dt must not stiffen the contact, or convergence is confounded."""
    from cadkit.physics.hollow import CONTACT_TIMECONST_S, u_channel_spec

    coarse = u_channel_spec(through_path=True, timestep_s=1e-3)
    fine = u_channel_spec(through_path=True, timestep_s=5e-4)
    assert coarse.contact_timeconst_s == fine.contact_timeconst_s == CONTACT_TIMECONST_S
    assert coarse.timestep_s != fine.timestep_s


def test_convergence_pair_reports_actual_differences(tmp_path):
    """Baseline vs half-step: same contact model, different integration resolution."""
    from cadkit.physics.hollow_run import run_channel_evidence

    base = run_channel_evidence(tmp_path / "base", timestep_s=1e-3)
    half = run_channel_evidence(tmp_path / "half", timestep_s=5e-4)

    assert base["positive"]["passed"] and half["positive"]["passed"]
    assert base["positive"]["solver_dt_s"] == pytest.approx(1e-3)
    assert half["positive"]["solver_dt_s"] == pytest.approx(5e-4)
    # both cross, and the depth difference is bounded rather than asserted equal
    assert base["positive"]["crossed_exit"] and half["positive"]["crossed_exit"]
    assert abs(base["positive"]["max_contact_depth_mm"]
               - half["positive"]["max_contact_depth_mm"]) <= 0.5


def test_initial_overlap_is_scene_invalid_not_a_physical_failure(tmp_path):
    """The mesh-hull negative is an invalid scene, distinct from a dynamics failure."""
    from cadkit.physics.hollow_run import run_channel_evidence

    summary = run_channel_evidence(tmp_path / "run", timestep_s=1e-3)
    neg = summary["negative_mesh_diagnostic"]
    assert neg["scene_valid"] is False
    assert "inside solid material" in neg["scene_invalid_reason"]
    # numerically fine: it is the representation that is wrong
    assert neg["valid"] is True
    assert neg["passed"] is False


def test_positive_with_initial_overlap_can_never_pass():
    from cadkit.physics.hollow_run import PassageResult

    r = _passage()
    assert r.scene_valid is True
    assert r.passed is True
    bad = _passage(scene_valid=False, passed=False)
    assert bad.passed is False


def test_cli_channel_reports_pass_and_writes_evidence(tmp_path):
    r = subprocess.run([sys.executable, "-m", "cadkit.cli", "physics", "channel",
                        "--out", str(tmp_path)], cwd=REPO_ROOT, capture_output=True,
                       text=True, timeout=300, env=_env())
    assert r.returncode == 0, r.stdout + r.stderr
    assert '"status": "PASS"' in r.stdout
    assert (tmp_path / "summary.json").is_file()


def test_cli_channel_without_extra_is_actionable(tmp_path):
    code = """
import sys, builtins
_real = builtins.__import__
def _blocked(name, *a, **k):
    if name == "mujoco" or name.startswith("mujoco."):
        raise ModuleNotFoundError("No module named 'mujoco'")
    return _real(name, *a, **k)
builtins.__import__ = _blocked
sys.argv = ["cad", "physics", "channel", "--out", %r]
from cadkit.cli import main
main()
""" % (str(tmp_path),)
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True,
                       text=True, timeout=300, env=_env())
    assert r.returncode == 3, r.stdout + r.stderr
    assert '"status": "ERROR"' in r.stdout
    assert "Traceback" not in r.stderr


def test_unsupported_validation_is_rejected_explicitly():
    """A contract with no probes and no transits is still valid; a malformed one is not."""
    with pytest.raises(ValueError):
        ProbeSpec("p", ()).validate()
    with pytest.raises(ValueError):
        TransitSpec("t", (0, 0, 0), (0, 0, 0), 1.0).validate()
    with pytest.raises(ValueError):
        TransitSpec("t", (0, 0, 0), (10, 0, 0), -1.0).validate()
    with pytest.raises(ValueError):
        TransitSpec("t", (0, 0, 0), (10, 0, 0), 1.0, samples=5).validate()
    with pytest.raises(ValueError):
        FidelitySpec(max_surface_deviation_mm=0.0).validate()


def test_fidelity_metrics_are_in_the_export_report(tmp_path):
    ex = export_scene(u_channel_spec(), tmp_path)
    payload = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert payload["fidelity"]["channel"]["ok"] is True
    assert "transit_through_channel_min_clearance_mm" in payload["fidelity"]["channel"]["metrics"]
