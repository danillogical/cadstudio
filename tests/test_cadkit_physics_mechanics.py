"""M3: jointed assemblies, joint springs, bounded actuators, and the mechanics fixtures."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from build123d import Box, Pos

from cadkit.physics.mechanics import (
    HINGE_DAMPING_RATIO,
    HINGE_K_NM_PER_RAD,
    SLIDER_DAMPING_RATIO,
    SLIDER_FORCE_N,
    SLIDER_FRICTIONLOSS,
    SLIDER_K_N_PER_M,
    SLIDER_KG,
    SLIDER_PRELOAD_M,
    STOP_DRIVE_N,
    STOP_PEAK_PENETRATION_M,
    STOP_RANGE_M,
    STOP_STEADY_PENETRATION_M,
    STOP_TIMECONST_S,
    analytic_hinge_inertia_kg_m2,
    analytic_period_s,
    analytic_slider_deflection,
    hinge_cad_inertia_kg_m2,
    hinge_damping_nm_s_per_rad,
    hinge_oscillator_spec,
    slider_analytic_stiffness_damping,
    slider_damped_spec,
    slider_friction_band,
    slider_friction_spec,
    slider_frictionless_spec,
    slider_period_s,
    slider_release_residual_bound,
    slider_stop_spec,
    stop_penetration_estimate_m,
)
from cadkit.physics.schema import (
    ActuatorSpec,
    AssemblySpec,
    BodySpec,
    ColliderSpec,
    Frame,
    JointSpec,
    PartSpec,
    SpringSpec,
)

pytest.importorskip("mujoco")

import mujoco  # noqa: E402


def _part(part_id="p", size=(4, 4, 4), density=1.24):
    return PartSpec(part_id, Box(*size),
                    colliders=(ColliderSpec(f"{part_id}_c", "box",
                                            tuple(s / 2 for s in size)),),
                    density_g_cm3=density)


def _slide_pair(**joint_kwargs):
    base = BodySpec("base", parts=(_part("b", (20, 20, 4)),), fixed_to_world=True,
                    fixture="analytic_fixture")
    joint_kwargs.setdefault("joint_id", "j")
    joint_kwargs.setdefault("body_id", "slider")
    joint_kwargs.setdefault("kind", "slide")
    joint_kwargs.setdefault("axis", (1, 0, 0))
    slider = BodySpec("slider", parts=(_part("s"),), parent="base",
                      joint=JointSpec(**joint_kwargs))
    return base, slider


# ---- schema contracts -------------------------------------------------------------
# Validation boundary, as implemented: cheap self-contained value objects fail eagerly in
# __post_init__ (SpringSpec, JointSpec, ActuatorSpec). Specs that carry CAD geometry or a
# body graph — Frame, ColliderSpec, PartSpec, BodySpec, AssemblySpec — have no __post_init__
# and validate through validate(), which export_scene always calls before touching the
# filesystem. These tests assert through that boundary instead of expecting construction-time
# errors the schema never promised.
def test_jointed_body_has_no_freejoint():
    base, slider = _slide_pair(limits=(-0.01, 0.01))
    spec = AssemblySpec(name="t", bodies=(base, slider))
    assert spec.bodies[1].joint is not None
    assert spec.bodies[1].joint.kind == "slide"


def test_joint_on_fixed_body_rejected():
    """A fixed body is welded to the world; a joint on it would be silently ignored."""
    base = BodySpec("base", parts=(_part(),), fixed_to_world=True, fixture="analytic_fixture",
                    joint=JointSpec("j", "base", "slide", axis=(1, 0, 0)))
    with pytest.raises(ValueError, match="fixed"):
        AssemblySpec(name="t", bodies=(base,)).validate()


def test_joint_body_id_must_match_owner():
    base = BodySpec("base", parts=(_part(),), fixed_to_world=True, fixture="analytic_fixture")
    bad = BodySpec("slider", parts=(_part("s"),), parent="base",
                   joint=JointSpec("j", "other", "slide", axis=(1, 0, 0)))
    with pytest.raises(ValueError, match="body_id"):
        AssemblySpec(name="t", bodies=(base, bad)).validate()


def test_parent_must_exist():
    orphan = BodySpec("slider", parts=(_part("s"),), parent="nope",
                      joint=JointSpec("j", "slider", "slide", axis=(1, 0, 0)))
    with pytest.raises(ValueError, match="nope"):
        AssemblySpec(name="t", bodies=(orphan,)).validate()


def test_joint_cycle_rejected():
    a = BodySpec("a", parts=(_part("a"),), parent="b",
                 joint=JointSpec("ja", "a", "slide", axis=(1, 0, 0)))
    b = BodySpec("b", parts=(_part("b"),), parent="a",
                 joint=JointSpec("jb", "b", "slide", axis=(1, 0, 0)))
    with pytest.raises(ValueError, match="cycle|parent"):
        AssemblySpec(name="t", bodies=(a, b)).validate()


@pytest.mark.parametrize("axis", [(0, 0, 0), (0, 0, float("nan")), (0, 0, float("inf"))])
def test_joint_axis_must_be_finite_nonzero(axis):
    with pytest.raises(ValueError, match="axis"):
        JointSpec("j", "b", "hinge", axis=axis)


def test_hinge_limits_in_radians_rejects_degrees():
    """Hinge limits are radians. 60 degrees written as 60 rad is caught by the limit check."""
    with pytest.raises(ValueError, match="rad"):
        JointSpec("j", "b", "hinge", axis=(0, 0, 1), limits=(0.0, 60.0))


def test_slide_limits_in_metres_rejects_millimetres():
    with pytest.raises(ValueError, match="m\\b|metre"):
        JointSpec("j", "b", "slide", axis=(1, 0, 0), limits=(0.0, 40.0))


def test_spring_stiffness_must_be_positive():
    with pytest.raises(ValueError, match="stiffness"):
        SpringSpec(0.0, 0.0)


def test_spring_force_at_reference_is_zero():
    """F = -k(q - ref), k = 50 N/m, ref = 0.02 m: at q = 0 the spring pushes +1 N."""
    spring = SpringSpec(50.0, 0.02)
    assert spring.force_at(0.02) == pytest.approx(0.0)
    assert spring.force_at(0.0) == pytest.approx(+1.0)
    assert spring.force_at(0.04) == pytest.approx(-1.0)


def test_actuator_joint_must_exist():
    base, slider = _slide_pair(limits=(-0.01, 0.01))
    spec = AssemblySpec(name="t", bodies=(base, slider),
                        actuators=(ActuatorSpec("a", "missing", "force", 1.0),))
    with pytest.raises(ValueError, match="missing"):
        spec.validate()


def test_actuator_effort_bound_must_be_positive():
    with pytest.raises(ValueError, match="effort"):
        ActuatorSpec("a", "j", "force", 0.0)


def test_actuator_on_free_joint_rejected():
    body = BodySpec("free", parts=(_part(),), fixture="none")
    spec = AssemblySpec(name="t", bodies=(body,),
                        actuators=(ActuatorSpec("a", "free_free", "force", 1.0),))
    with pytest.raises(ValueError, match="free|joint"):
        spec.validate()


# ---- analytic fixtures ------------------------------------------------------------
def test_slider_prediction_is_force_over_stiffness():
    assert analytic_slider_deflection() == pytest.approx(SLIDER_FORCE_N / SLIDER_K_N_PER_M)


def test_slider_band_widens_with_friction():
    narrow = slider_friction_band(frictionloss=0.0)
    wide = slider_friction_band(frictionloss=0.10)
    assert narrow[0] == pytest.approx(narrow[1])
    assert wide[1] - wide[0] == pytest.approx(2 * 0.10 / SLIDER_K_N_PER_M)
    # the band is centred on reference + F/k, not on F/k: the preload shifts it
    assert narrow[0] == pytest.approx(SLIDER_PRELOAD_M + SLIDER_FORCE_N / SLIDER_K_N_PER_M)


def test_friction_band_centre_is_preload_plus_force_over_k():
    lo, hi = slider_friction_band()
    assert (lo + hi) / 2 == pytest.approx(SLIDER_PRELOAD_M + SLIDER_FORCE_N / SLIDER_K_N_PER_M)
    assert slider_release_residual_bound() == pytest.approx(SLIDER_FRICTIONLOSS / SLIDER_K_N_PER_M)


def test_slider_period_is_the_declared_mass_over_stiffness():
    """2*pi*sqrt(m/k) with the declared 0.25 kg and 50 N/m, not the old light carriage."""
    assert slider_period_s() == pytest.approx(2 * math.pi * math.sqrt(SLIDER_KG / SLIDER_K_N_PER_M))
    assert slider_period_s() == pytest.approx(0.4442882938158366, rel=1e-12)


def test_slider_damping_follows_the_declared_mass():
    """c = zeta*2*sqrt(km) is derived, so a change of mass cannot silently detune the settle."""
    c = slider_analytic_stiffness_damping()
    assert c == pytest.approx(SLIDER_DAMPING_RATIO * 2 * math.sqrt(SLIDER_K_N_PER_M * SLIDER_KG))
    # and the 4-tau settle fits inside the declared release window
    omega = math.sqrt(SLIDER_K_N_PER_M / SLIDER_KG)
    assert 4.0 / (SLIDER_DAMPING_RATIO * omega) < 0.6


def test_hinge_analytic_matches_cad_inertia():
    """Two independent routes: closed-form box + parallel axis, versus the CAD solid."""
    analytic = analytic_hinge_inertia_kg_m2()
    cad = hinge_cad_inertia_kg_m2()
    assert analytic == pytest.approx(cad, rel=1e-9)


def test_hinge_period_scales_as_sqrt_inertia_over_k():
    base = analytic_period_s()
    assert analytic_period_s(stiffness=HINGE_K_NM_PER_RAD * 4) == pytest.approx(base / 2)
    assert analytic_period_s(inertia=analytic_hinge_inertia_kg_m2() * 4) == pytest.approx(base * 2)


def test_damped_period_is_undefined_at_critical_damping():
    with pytest.raises(ValueError, match="critical"):
        analytic_period_s(damping_ratio=1.0)


def test_hinge_amplitude_is_small_enough_to_stay_linear():
    """A 10 degree release keeps the small-angle period valid to well under 1%."""
    assert math.radians(10.0) < math.radians(15.0)


# ---- compiled integration: real MJCF, real MuJoCo -----------------------------------
# These tests read the *compiled* model (body_parentid, xpos/xmat/xipos, xanchor/xaxis,
# jnt_range, qpos_spring, qfrc_actuator). A string match on the XML cannot prove the parent
# graph or the SI boundary: the compiler is what interprets both.

def _quat_matrix(wxyz):
    w, x, y, z = wxyz
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def _rot_x(rad):
    c, s = math.cos(rad), math.sin(rad)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def _rot_y(rad):
    c, s = math.cos(rad), math.sin(rad)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def _rot_z(rad):
    c, s = math.cos(rad), math.sin(rad)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def _frame_matrix(frame):
    """Independent R for Frame.rot_deg, as build123d's ``Rot(X, Y, Z)`` composition.

    build123d applies the rotations in the order written, i.e. ``Rx @ Ry @ Rz``. Verified
    against ``Frame.rotation_matrix()`` by ``test_body_euler_matches_build123d...``.
    """
    rx, ry, rz = (math.radians(a) for a in frame.rot_deg)
    return _rot_x(rx) @ _rot_y(ry) @ _rot_z(rz)


def _block(part_id, centre_mm, size_mm):
    return PartSpec(part_id, Pos(*centre_mm) * Box(*size_mm),
                    colliders=(ColliderSpec(f"{part_id}_col", "box",
                                            tuple(s / 2 for s in size_mm),
                                            pos_mm=centre_mm),),
                    density_g_cm3=1.24)


def _three_level_chain():
    """base (fixed) -> l1 (hinge Z) -> l2 (hinge Y) -> l3 (slide X), all rotated.

    Frames are deliberately non-axis-aligned and non-commuting: a parent graph that is flat,
    or a relative pose built with the wrong multiplication order, cannot produce the same
    compiled xpos/xmat as the independent forward-kinematics sum below.
    """
    base = BodySpec(
        "base", parts=(_block("base", (0.0, 0.0, 0.0), (10.0, 10.0, 10.0)),),
        frame=Frame(pos_mm=(5.0, -7.0, 11.0), rot_deg=(12.0, -25.0, 40.0)),
        fixed_to_world=True, fixture="analytic_fixture",
    )
    l1 = BodySpec(
        "l1", parts=(_block("l1", (0.0, 0.0, 0.0), (8.0, 6.0, 4.0)),),
        frame=Frame(pos_mm=(60.0, 10.0, 30.0), rot_deg=(35.0, 10.0, -20.0)),
        parent="base",
        joint=JointSpec("j1", "l1", "hinge", axis=(0.0, 0.0, 1.0),
                        anchor_mm=(10.0, 0.0, 0.0), limits=(-0.5, 0.5)),
    )
    l2 = BodySpec(
        "l2", parts=(_block("l2", (0.0, 0.0, 0.0), (6.0, 5.0, 3.0)),),
        frame=Frame(pos_mm=(95.0, -20.0, 45.0), rot_deg=(-15.0, 50.0, 25.0)),
        parent="l1",
        joint=JointSpec("j2", "l2", "hinge", axis=(0.0, 1.0, 0.0),
                        anchor_mm=(0.0, 0.0, 5.0), limits=(-1.0, 1.0)),
    )
    l3 = BodySpec(
        "l3", parts=(_block("l3", (0.0, 0.0, 0.0), (4.0, 4.0, 4.0)),),
        frame=Frame(pos_mm=(120.0, 5.0, 70.0), rot_deg=(60.0, -30.0, 15.0)),
        parent="l2",
        joint=JointSpec("j3", "l3", "slide", axis=(1.0, 0.0, 0.0),
                        anchor_mm=(0.0, 0.0, 0.0), limits=(-0.02, 0.02)),
    )
    return AssemblySpec(name="m3a_chain", bodies=(base, l1, l2, l3))


def _compile(spec, tmp_path, name="scene"):
    from cadkit.physics.scene import export_scene

    return export_scene(spec, tmp_path / name)


def test_compiled_body_parent_graph_is_nested(tmp_path):
    """The declared parent chain must reach the compiler, not flatten into siblings."""
    ex = _compile(_three_level_chain(), tmp_path)
    model = ex.model

    def bid(name):
        return mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)

    world = 0
    assert model.body_parentid[bid("base")] == world
    assert model.body_parentid[bid("l1")] == bid("base")
    assert model.body_parentid[bid("l2")] == bid("l1")
    assert model.body_parentid[bid("l3")] == bid("l2")
    # and the flat-sibling failure is explicitly excluded
    assert model.body_parentid[bid("l3")] != world


def test_compiled_world_poses_match_independent_forward_kinematics(tmp_path):
    """xpos/xmat at qpos=0 must equal the assembly frame, chain by chain.

    Independent route: each body's world rotation is the product of its ancestors' frame
    rotations (and joint rotations, all zero here), and its world position is the parent
    world position plus the parent rotation applied to the parent-relative translation.
    """
    spec = _three_level_chain()
    ex = _compile(spec, tmp_path)
    model = ex.model
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)

    pose = {}
    for body in spec.bodies:
        frame_rot = _frame_matrix(body.frame)
        frame_pos = np.array(body.frame.pos_mm) * 1e-3
        if body.parent is None:
            expect_pos, expect_rot = frame_pos, frame_rot
        else:
            parent_pos, parent_rot = pose[body.parent]
            expect_pos = parent_pos + parent_rot @ (parent_rot.T @ (frame_pos - parent_pos))
            expect_rot = parent_rot @ (parent_rot.T @ frame_rot)
        pose[body.body_id] = (expect_pos, expect_rot)
        bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body.body_id)
        assert data.xpos[bid] == pytest.approx(expect_pos, abs=1e-12), body.body_id
        assert data.xmat[bid].reshape(3, 3) == pytest.approx(expect_rot, abs=1e-12), body.body_id
        # the assembly frame is the absolute pose; xpos must reproduce it exactly
        assert data.xpos[bid] == pytest.approx(frame_pos, abs=1e-12), body.body_id
        assert data.xmat[bid].reshape(3, 3) == pytest.approx(frame_rot, abs=1e-12)


def test_compiled_chain_moves_correctly_under_nontrivial_joint_angles(tmp_path):
    """With nonzero joint angles, world poses follow the exact anchored FK, not just the frames.

    This is the case a flat hierarchy cannot fake: each joint rotates its subtree about its
    own anchor in the parent's frame, so a wrong anchor or a wrong relative pose moves the
    leaf somewhere measurably different.
    """
    spec = _three_level_chain()
    ex = _compile(spec, tmp_path)
    model = ex.model
    data = mujoco.MjData(model)

    angles = {"j1": 0.3, "j2": -0.45, "j3": 0.011}
    for name, value in angles.items():
        j = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        data.qpos[int(model.jnt_qposadr[j])] = value
    mujoco.mj_forward(model, data)

    declared = {b.body_id: (_frame_matrix(b.frame), np.array(b.frame.pos_mm) * 1e-3)
                for b in spec.bodies}
    # independent FK: walk root to leaf. The parent-relative pose is authored against the
    # parent's *declared* frame; the joint transform then applies inside the child's frame.
    pose = {}

    def rot_about(axis, angle):
        axis = np.asarray(axis, dtype=float)
        axis = axis / np.linalg.norm(axis)
        k = np.array([[0.0, -axis[2], axis[1]],
                      [axis[2], 0.0, -axis[0]],
                      [-axis[1], axis[0], 0.0]])
        return np.eye(3) + math.sin(angle) * k + (1.0 - math.cos(angle)) * (k @ k)

    for body in spec.bodies:
        frame_rot, frame_pos = declared[body.body_id]
        if body.parent is None:
            pose[body.body_id] = (frame_pos, frame_rot)
            continue
        parent_pos, parent_rot = pose[body.parent]
        p_rot, p_pos = declared[body.parent]
        rel_pos = p_rot.T @ (frame_pos - p_pos)
        rel_rot = p_rot.T @ frame_rot
        joint = body.joint
        anchor = np.array(joint.anchor_mm) * 1e-3
        axis = np.array(joint.axis) / np.linalg.norm(joint.axis)
        if joint.kind == "hinge":
            # MJCF: axis and pos are in the child's own frame, so the child rotates about its
            # local axis and the anchor point stays fixed in the parent frame:
            #   rel_R' = rel_R K,  rel_p' = rel_p + rel_R (I - K) a
            k_rot = rot_about(axis, angles[joint.joint_id])
            rel_pos = rel_pos + rel_rot @ ((np.eye(3) - k_rot) @ anchor)
            rel_rot = rel_rot @ k_rot
        else:
            rel_pos = rel_pos + rel_rot @ (axis * angles[joint.joint_id])
        pose[body.body_id] = (parent_pos + parent_rot @ rel_pos, parent_rot @ rel_rot)

    for body in spec.bodies:
        bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body.body_id)
        expect_pos, expect_rot = pose[body.body_id]
        assert data.xpos[bid] == pytest.approx(expect_pos, abs=1e-12), body.body_id
        assert data.xmat[bid].reshape(3, 3) == pytest.approx(expect_rot, abs=1e-12), body.body_id


def test_compiled_joint_anchors_and_axes_follow_the_parent_rotation(tmp_path):
    """xanchor/xaxis are world quantities: they must include every ancestor rotation."""
    spec = _three_level_chain()
    ex = _compile(spec, tmp_path)
    model = ex.model
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)

    pose = {}
    for body in spec.bodies:
        frame_rot, frame_pos = _frame_matrix(body.frame), np.array(body.frame.pos_mm) * 1e-3
        if body.parent is None:
            pose[body.body_id] = (frame_pos, frame_rot)
        else:
            parent_pos, parent_rot = pose[body.parent]
            pose[body.body_id] = (parent_pos + parent_rot @ (parent_rot.T @ (frame_pos - parent_pos)),
                                  parent_rot @ (parent_rot.T @ frame_rot))
    for body in spec.bodies:
        if body.joint is None:
            continue
        body_pos, body_rot = pose[body.body_id]
        anchor = body_pos + body_rot @ (np.array(body.joint.anchor_mm) * 1e-3)
        axis = body_rot @ (np.array(body.joint.axis) / np.linalg.norm(body.joint.axis))
        j = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, body.joint.joint_id)
        assert data.xanchor[j] == pytest.approx(anchor, abs=1e-12), body.joint.joint_id
        assert data.xaxis[j] == pytest.approx(axis, abs=1e-12), body.joint.joint_id


def test_compiled_com_and_inertia_survive_the_nested_placement(tmp_path):
    """xipos and the compiled tensor must match the CAD-derived body inertial, in world terms."""
    spec = _three_level_chain()
    ex = _compile(spec, tmp_path)
    model = ex.model
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)

    from cadkit.physics.inertia import body_inertial

    for body, report in zip(spec.bodies, ex.bodies):
        inertial = body_inertial(body)
        bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body.body_id)
        assert float(model.body_mass[bid]) == pytest.approx(inertial.mass_kg, rel=1e-12)
        assert data.xipos[bid] == pytest.approx(np.array(report.com_world_m), abs=1e-12)
        # body-local COM in the compiled model is the inertial pos, not the body origin
        assert model.body_ipos[bid] == pytest.approx(np.array(inertial.com_m), abs=1e-12)
        # MuJoCo stores principal moments plus an inertial-frame quaternion; rebuild the
        # tensor in body axes and compare it with the CAD-derived one element by element.
        rot = _quat_matrix(model.body_iquat[bid])
        compiled = rot @ np.diag(model.body_inertia[bid]) @ rot.T
        assert compiled == pytest.approx(np.array(inertial.inertia_kg_m2), abs=1e-15)


def test_compiled_hinge_range_and_springref_are_radians(tmp_path):
    """A documented-radian hinge range and nonzero springref must survive as SI values."""
    reference = 0.25           # rad, explicit
    low, high = -0.5, 1.1      # rad, explicit
    spec = AssemblySpec(
        name="m3a_hinge_units",
        bodies=(
            BodySpec("post", parts=(_block("post", (0.0, 0.0, 0.0), (10.0, 10.0, 10.0)),),
                     fixed_to_world=True, fixture="analytic_fixture"),
            BodySpec("arm", parts=(_block("arm", (0.0, 0.0, 0.0), (20.0, 4.0, 2.0)),),
                     frame=Frame(pos_mm=(0.0, 0.0, 10.0), rot_deg=(0.0, 0.0, 20.0)),
                     parent="post",
                     joint=JointSpec("arm_hinge", "arm", "hinge", axis=(0.0, 0.0, 1.0),
                                     limits=(low, high),
                                     spring=SpringSpec(0.02, reference))),
        ),
        gravity_m_s2=(0.0, 0.0, 0.0),
    )
    ex = _compile(spec, tmp_path)
    model = ex.model
    j = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "arm_hinge")
    assert model.jnt_range[j] == pytest.approx([low, high], abs=1e-12)
    assert float(model.qpos_spring[int(model.jnt_qposadr[j])]) == pytest.approx(reference, abs=1e-12)
    assert float(model.jnt_stiffness[j]) == pytest.approx(0.02, rel=1e-12)

    # The compiled spring must actually produce -k(q - ref) at the joint.
    data = mujoco.MjData(model)
    qadr = int(model.jnt_qposadr[j])
    dof = int(model.jnt_dofadr[j])
    for q in (reference, 0.0, reference + 0.4):
        data.qpos[qadr] = q
        mujoco.mj_forward(model, data)
        assert float(data.qfrc_spring[dof]) == pytest.approx(-0.02 * (q - reference), abs=1e-12)


def test_compiled_slide_range_and_springref_are_metres(tmp_path):
    reference, low, high = 0.012, -0.05, 0.05
    spec = AssemblySpec(
        name="m3a_slide_units",
        bodies=(
            BodySpec("rail", parts=(_block("rail", (0.0, 0.0, 0.0), (60.0, 20.0, 6.0)),),
                     fixed_to_world=True, fixture="analytic_fixture"),
            BodySpec("carriage", parts=(_block("carriage", (0.0, 0.0, 6.0), (8.0, 8.0, 8.0)),),
                     frame=Frame(pos_mm=(0.0, 0.0, 6.0)),
                     parent="rail",
                     joint=JointSpec("carriage_slide", "carriage", "slide", axis=(1.0, 0.0, 0.0),
                                     limits=(low, high),
                                     spring=SpringSpec(50.0, reference))),
        ),
        gravity_m_s2=(0.0, 0.0, 0.0),
    )
    ex = _compile(spec, tmp_path)
    model = ex.model
    j = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "carriage_slide")
    assert model.jnt_range[j] == pytest.approx([low, high], abs=1e-12)
    assert float(model.qpos_spring[int(model.jnt_qposadr[j])]) == pytest.approx(reference, abs=1e-12)


def test_compiled_collider_rotation_is_the_declared_rotation(tmp_path):
    """A rotated collider must keep its build123d rotation under the radian compiler."""
    rot_deg = (30.0, 12.0, 55.0)
    spec = AssemblySpec(name="m3a_collider_rot", bodies=(
        BodySpec("b", parts=(PartSpec(
            "p", Box(20.0, 10.0, 6.0),
            colliders=(ColliderSpec("k", "box", (10.0, 5.0, 3.0), rot_deg=rot_deg),),
            density_g_cm3=1.0),),
            frame=Frame(pos_mm=(10.0, 20.0, 30.0), rot_deg=(0.0, 0.0, 0.0)),
        ),
    ))
    ex = _compile(spec, tmp_path)
    model = ex.model
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    g = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "k")
    assert data.geom_xmat[g].reshape(3, 3) == pytest.approx(
        _rot_x(math.radians(rot_deg[0])) @ _rot_y(math.radians(rot_deg[1]))
        @ _rot_z(math.radians(rot_deg[2])), abs=1e-12)


@pytest.mark.parametrize("gear", [1.0, 2.0, -1.5])
def test_compiled_actuator_bounds_generalized_effort(tmp_path, gear):
    """Over-requesting the control must not transmit more than max_effort to the joint.

    ``max_effort`` is the generalized effort (N or N m) after the gear, so the check is on
    ``qfrc_actuator``, not on ``ctrl`` and not on ``actuator_force`` alone.
    """
    bound = 1.5
    spec = AssemblySpec(
        name="m3a_actuator_bound",
        bodies=(
            BodySpec("base", parts=(_block("base", (0.0, 0.0, 0.0), (20.0, 20.0, 4.0)),),
                     fixed_to_world=True, fixture="analytic_fixture"),
            BodySpec("slider", parts=(_block("slider", (0.0, 0.0, 4.0), (4.0, 4.0, 4.0)),),
                     frame=Frame(pos_mm=(0.0, 0.0, 4.0)),
                     parent="base",
                     joint=JointSpec("j", "slider", "slide", axis=(1.0, 0.0, 0.0),
                                     limits=(-0.05, 0.05))),
        ),
        gravity_m_s2=(0.0, 0.0, 0.0),
        actuators=(ActuatorSpec("push", "j", "force", bound, gear=gear),),
    )
    ex = _compile(spec, tmp_path)
    model = ex.model
    data = mujoco.MjData(model)
    a = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, "push")
    dof = int(model.jnt_dofadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "j")])

    for ctrl in (1e6, -1e6, 0.0, 1e-3):
        data.ctrl[:] = 0.0
        data.ctrl[a] = ctrl
        data.qvel[:] = 0.0
        mujoco.mj_forward(model, data)
        transmitted = float(data.qfrc_actuator[dof])
        assert abs(transmitted) <= bound + 1e-12, (ctrl, transmitted)
        assert abs(float(data.actuator_force[a])) <= bound / abs(gear) + 1e-12
    # direction: a positive control with a negative gear must push the joint negative
    data.ctrl[:] = 0.0
    data.ctrl[a] = 1e6
    mujoco.mj_forward(model, data)
    expected_sign = math.copysign(1.0, gear)
    assert math.copysign(1.0, float(data.qfrc_actuator[dof])) == expected_sign
    assert abs(float(data.qfrc_actuator[dof])) == pytest.approx(bound, rel=1e-12)

    # And it must hold while stepping, not only at the first evaluation: the control stays
    # saturated for a full second while the joint runs into its limit.
    data.ctrl[:] = 0.0
    data.ctrl[a] = -1e6 if gear > 0 else 1e6
    peak = 0.0
    for _ in range(1000):
        mujoco.mj_step(model, data)
        peak = max(peak, abs(float(data.qfrc_actuator[dof])))
        assert np.all(np.isfinite(data.qpos)) and np.all(np.isfinite(data.qvel))
    assert peak <= bound + 1e-12, (gear, peak)
    assert peak == pytest.approx(bound, rel=1e-12)


def test_export_enforces_the_graph_boundary_before_writing(tmp_path):
    """The boundary is enforced in production, not just by calling validate() in a test.

    export_scene validates before it creates anything, so an invalid graph must raise and
    leave no output directory behind.
    """
    from cadkit.physics.scene import export_scene

    orphan = BodySpec("slider", parts=(_part("s"),), parent="nope",
                      joint=JointSpec("j", "slider", "slide", axis=(1, 0, 0)))
    out = tmp_path / "never_created"
    with pytest.raises(ValueError, match="nope"):
        export_scene(AssemblySpec(name="t", bodies=(orphan,)), out)
    assert not out.exists()

    cycle_a = BodySpec("a", parts=(_part("a"),), parent="b",
                       joint=JointSpec("ja", "a", "slide", axis=(1, 0, 0)))
    cycle_b = BodySpec("b", parts=(_part("b"),), parent="a",
                       joint=JointSpec("jb", "b", "slide", axis=(1, 0, 0)))
    out2 = tmp_path / "also_never_created"
    with pytest.raises(ValueError, match="cycle|parent"):
        export_scene(AssemblySpec(name="t", bodies=(cycle_a, cycle_b)), out2)
    assert not out2.exists()


# ---- M3b: declared mass, stops, telemetry, convergence, negatives --------------------
def _compiled(spec, tmp_path, name="scene"):
    from cadkit.physics.scene import export_scene

    return export_scene(spec, tmp_path / name)


def test_declared_slider_mass_reaches_the_compiled_model(tmp_path):
    """SLIDER_KG must be the compiled body mass, not the mass of the decorative block."""
    ex = _compiled(slider_frictionless_spec(), tmp_path)
    model = ex.model
    bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "carriage")
    assert float(model.body_mass[bid]) == pytest.approx(SLIDER_KG, rel=1e-12)
    # and the decorative block alone would have been ~400x lighter
    assert float(model.body_mass[bid]) > 100.0 * 6.349e-4


def test_slider_period_from_the_compiled_model(tmp_path):
    """The compiled effective inertia must give 2*pi*sqrt(m/k), read through mj_fullM."""
    ex = _compiled(slider_frictionless_spec(), tmp_path)
    model = ex.model
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    full = np.zeros((model.nv, model.nv))
    mujoco.mj_fullM(model, data, full)
    j = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "carriage_slide")
    inertia = float(full[int(model.jnt_dofadr[j]), int(model.jnt_dofadr[j])])
    assert inertia == pytest.approx(SLIDER_KG, rel=1e-9)
    assert 2 * math.pi * math.sqrt(inertia / SLIDER_K_N_PER_M) == pytest.approx(
        slider_period_s(), rel=1e-9)


def test_stop_compliance_is_declared_in_absolute_si(tmp_path):
    """The stop's solref must reach the compiled model as the declared seconds."""
    ex = _compiled(slider_stop_spec(), tmp_path)
    model = ex.model
    j = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "carriage_slide")
    assert model.jnt_solref[j] == pytest.approx([STOP_TIMECONST_S, 1.0], rel=1e-12)
    assert model.jnt_range[j] == pytest.approx(list(STOP_RANGE_M), rel=1e-12)


def test_stop_compliance_does_not_scale_with_timestep(tmp_path):
    """Refining dt must change integration resolution only, never the stop's stiffness."""
    a = _compiled(slider_stop_spec(timestep_s=1e-3), tmp_path, "a").model
    b = _compiled(slider_stop_spec(timestep_s=5e-4), tmp_path, "b").model
    ja = mujoco.mj_name2id(a, mujoco.mjtObj.mjOBJ_JOINT, "carriage_slide")
    jb = mujoco.mj_name2id(b, mujoco.mjtObj.mjOBJ_JOINT, "carriage_slide")
    assert a.jnt_solref[ja] == pytest.approx(b.jnt_solref[jb], rel=1e-12)
    assert a.opt.timestep == pytest.approx(1e-3)
    assert b.opt.timestep == pytest.approx(5e-4)


def test_stop_rejects_nonpositive_compliance():
    with pytest.raises(ValueError, match="stop_timeconst_s"):
        JointSpec("j", "b", "slide", axis=(1, 0, 0), limits=(-0.01, 0.01),
                  stop_timeconst_s=0.0)
    with pytest.raises(ValueError, match="stop_dampratio"):
        JointSpec("j", "b", "slide", axis=(1, 0, 0), limits=(-0.01, 0.01),
                  stop_dampratio=-1.0)


def test_stop_penetration_estimate_is_the_declared_scale():
    assert stop_penetration_estimate_m() == pytest.approx(
        STOP_DRIVE_N * STOP_TIMECONST_S ** 2 / SLIDER_KG)
    # the declared budgets must be looser than the estimate, or they are not a budget
    assert STOP_STEADY_PENETRATION_M > stop_penetration_estimate_m()
    assert STOP_PEAK_PENETRATION_M > STOP_STEADY_PENETRATION_M


def test_qpos_and_dof_addresses_differ_and_are_used_correctly(tmp_path):
    """jnt_qposadr and jnt_dofadr are not interchangeable once another joint precedes."""
    spec = slider_frictionless_spec()
    rail, carriage = spec.bodies
    free = BodySpec("floater", parts=(_part("f", (2, 2, 2)),), fixture="none")
    spec = type(spec)(**{
        **{f.name: getattr(spec, f.name) for f in spec.__dataclass_fields__.values()},
        "bodies": (free, rail, carriage),
    })
    ex = _compiled(spec, tmp_path)
    model = ex.model
    j = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "carriage_slide")
    qadr, dofadr = int(model.jnt_qposadr[j]), int(model.jnt_dofadr[j])
    assert qadr != dofadr
    assert 0 <= qadr < model.nq and 0 <= dofadr < model.nv
    # the free joint owns qpos[0:7]; the slide coordinate is the last entry, its velocity the
    # last dof. Reading qpos at dofadr would land inside the free body's quaternion.
    data = mujoco.MjData(model)
    data.qpos[qadr] = 0.017
    mujoco.mj_forward(model, data)
    assert float(data.qpos[qadr]) == pytest.approx(0.017)
    assert float(data.qpos[dofadr]) != pytest.approx(0.017)


def test_telemetry_header_matches_every_row():
    """A CSV whose header and rows disagree is not evidence."""
    from cadkit.physics.mechanics_run import TRACE_HEADER, run_damped_return
    import tempfile as _tf

    trial = run_damped_return(Path(_tf.mkdtemp()) / "t")
    assert trial.trace, "the trial produced no telemetry"
    for row in trial.trace:
        assert len(row) == len(TRACE_HEADER)
    for column in ("ctrl_requested", "ctrl_stored", "ctrl_effective", "actuator_force",
                   "qfrc_actuator", "qfrc_spring", "qfrc_damper", "qfrc_constraint",
                   "qpos", "qvel"):
        assert column in TRACE_HEADER


def test_live_frictionless_deflection_and_period(tmp_path):
    from cadkit.physics.mechanics_run import run_frictionless_deflection, run_frictionless_period

    d = run_frictionless_deflection(tmp_path / "d")
    assert d.valid, d.invalid_reasons
    assert d.metrics["relative_error"] <= 0.02
    assert d.metrics["measured_centre_m"] == pytest.approx(
        analytic_slider_deflection(), rel=0.02)

    p = run_frictionless_period(tmp_path / "p")
    assert p.valid, p.invalid_reasons
    assert p.metrics["measured_period_s"] == pytest.approx(slider_period_s(), rel=0.05)


def test_live_damped_return_and_missing_spring(tmp_path):
    from cadkit.physics.mechanics_run import run_damped_return

    ok = run_damped_return(tmp_path / "ok")
    assert ok.valid, ok.invalid_reasons
    assert ok.metrics["residual_m"] <= 1e-4

    neg = run_damped_return(tmp_path / "neg", with_spring=False)
    verdict = {c["name"]: c for c in neg.checks}["returns_to_home"]
    assert verdict["ok"] is False, "a carriage with no spring must not be reported as returned"
    assert neg.valid, "the missing-spring case must be a valid run with a failed check"


def test_live_friction_band_and_missing_input(tmp_path):
    from cadkit.physics.mechanics_run import run_friction_static

    ok = run_friction_static(tmp_path / "ok")
    assert ok.valid, ok.invalid_reasons
    lo, hi = slider_friction_band()
    assert lo <= ok.metrics["x_after_push_m"] <= hi
    assert ok.metrics["release_residual_m"] <= slider_release_residual_bound()

    neg = run_friction_static(tmp_path / "neg", apply_force=False)
    verdict = {c["name"]: c for c in neg.checks}["static_band"]
    assert verdict["ok"] is False, "no input must not reach the driven band"


def test_live_stop_under_sustained_input(tmp_path):
    from cadkit.physics.mechanics_run import run_stop

    trial = run_stop(tmp_path / "s")
    assert trial.valid, trial.invalid_reasons
    m = trial.metrics
    assert m["x_held_m"] > STOP_RANGE_M[1], "the drive must actually reach the stop"
    assert m["steady_penetration_m"] <= STOP_STEADY_PENETRATION_M
    assert m["peak_penetration_m"] <= STOP_PEAK_PENETRATION_M
    assert abs(m["held_constraint_n"]) > 0.0


def test_live_hinge_period_and_damped_case(tmp_path):
    from cadkit.physics.mechanics_run import run_hinge

    a = run_hinge(tmp_path / "a")
    assert a.valid, a.invalid_reasons
    assert a.metrics["measured_period_s"] == pytest.approx(analytic_period_s(), rel=0.05)
    assert a.metrics["compiled_inertia_kg_m2"] == pytest.approx(
        analytic_hinge_inertia_kg_m2(), rel=1e-6)

    c = run_hinge(tmp_path / "c", damping=hinge_damping_nm_s_per_rad())
    assert c.valid, c.invalid_reasons
    assert c.metrics["damping_ratio"] == pytest.approx(HINGE_DAMPING_RATIO, rel=1e-9)
    assert c.metrics["measured_period_s"] == pytest.approx(
        analytic_period_s(damping_ratio=HINGE_DAMPING_RATIO), rel=0.05)


def test_base_and_half_dt_converge(tmp_path):
    """Same physical parameters, two steps: the reported metrics must agree."""
    from cadkit.physics.mechanics_run import _convergence, _run_set

    base = _run_set(tmp_path / "base", 1e-3)
    half = _run_set(tmp_path / "half", 5e-4)
    conv = _convergence(base, half)
    assert conv["base_dt_s"] == pytest.approx(1e-3)
    assert conv["half_dt_s"] == pytest.approx(5e-4)
    bad = [r for r in conv["rows"] if not r["ok"]]
    assert not bad, bad


def test_run_mechanics_status_and_cli_agree(tmp_path):
    from cadkit.physics.mechanics_run import run_mechanics

    summary = run_mechanics(tmp_path / "run")
    assert summary["status"] == "PASS"
    assert all(summary["negatives"][k]["ok"] for k in summary["negatives"])
    assert (tmp_path / "run" / "summary.json").is_file()
    assert (tmp_path / "run" / "report.md").is_file()


def test_guard_rejects_a_speed_beyond_the_declared_bound(tmp_path):
    """A trial whose speed exceeds the fixture's derived bound must be invalid, not PASS."""
    from cadkit.physics.mechanics_run import _Recorder, run_damped_return

    trial = run_damped_return(tmp_path / "t")
    mujoco_ = mujoco
    model = mujoco_.MjModel.from_xml_path(str(tmp_path / "t" / "scene" / "scene.xml"))
    data = mujoco_.MjData(model)
    rec = _Recorder(mujoco_, model, data, "carriage_slide", "push", SLIDER_KG,
                    vmax=1e-9, emax=1e9)
    rec.step(50, SLIDER_FORCE_N)
    assert rec.invalid, "a speed bound of 1e-9 m/s must be violated immediately"
    assert any("speed" in r for r in rec.invalid)
    assert trial.valid


def test_guard_rejects_an_energy_beyond_the_declared_bound(tmp_path):
    from cadkit.physics.mechanics_run import _Recorder, run_damped_return

    trial = run_damped_return(tmp_path / "t")
    model = mujoco.MjModel.from_xml_path(str(tmp_path / "t" / "scene" / "scene.xml"))
    data = mujoco.MjData(model)
    rec = _Recorder(mujoco, model, data, "carriage_slide", "push", SLIDER_KG,
                    vmax=1e9, emax=1e-12)
    rec.step(50, SLIDER_FORCE_N)
    assert rec.invalid
    assert any("energy" in r for r in rec.invalid)
    assert trial.valid


def test_recorder_rejects_out_of_range_addresses():
    from cadkit.physics.mechanics_run import _Recorder

    model = mujoco.MjModel.from_xml_string(
        '<mujoco><worldbody><body name="b"><freejoint name="fj"/>'
        '<inertial pos="0 0 0" mass="1" diaginertia="1e-3 1e-3 1e-3"/>'
        '<geom type="box" size="0.01 0.01 0.01"/></body></worldbody></mujoco>')
    data = mujoco.MjData(model)
    with pytest.raises(ValueError, match="not found"):
        _Recorder(mujoco, model, data, "nosuch", None, 1.0, vmax=1.0, emax=1.0)


def test_summary_is_strict_json(tmp_path):
    """The artifact must never contain NaN/Infinity tokens."""
    import json as _json

    from cadkit.physics.mechanics_run import run_mechanics

    run_mechanics(tmp_path / "run")
    text = (tmp_path / "run" / "summary.json").read_text(encoding="utf-8")
    _json.loads(text, parse_constant=lambda c: (_ for _ in ()).throw(
        AssertionError(f"non-strict JSON constant {c}")))


def test_stop_budget_discriminates_against_the_compiler_default(tmp_path):
    """The stop gate must FAIL a fixture that inherits MuJoCo's soft default compliance.

    This is the regression for the finding that the original 0.5 mm budget passed the
    compiler-default stop (0.3144 mm), i.e. a gate widened past the case it exists to reject.
    """
    import dataclasses

    from cadkit.physics.scene import export_scene

    spec = slider_stop_spec()
    rail, carriage = spec.bodies
    default_spec = dataclasses.replace(
        spec, bodies=(rail, dataclasses.replace(
            carriage, joint=dataclasses.replace(carriage.joint, stop_timeconst_s=None))))
    ex = export_scene(default_spec, tmp_path / "default")
    model = ex.model
    data = mujoco.MjData(model)
    j = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "carriage_slide")
    qadr = int(model.jnt_qposadr[j])
    a = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, "push")
    data.ctrl[a] = STOP_DRIVE_N
    peak = -math.inf
    for _ in range(1000):
        mujoco.mj_step(model, data)
        peak = max(peak, float(data.qpos[qadr]))
    steady = float(data.qpos[qadr]) - STOP_RANGE_M[1]
    peak_pen = peak - STOP_RANGE_M[1]
    assert steady > STOP_STEADY_PENETRATION_M, (
        f"default compliance steady penetration {steady * 1e3:.4f} mm must exceed the "
        f"{STOP_STEADY_PENETRATION_M * 1e3:.2f} mm budget")
    assert peak_pen > STOP_PEAK_PENETRATION_M, (
        f"default compliance peak penetration {peak_pen * 1e3:.4f} mm must exceed the "
        f"{STOP_PEAK_PENETRATION_M * 1e3:.2f} mm budget")


# ---- M3b repair: both sets gated, refsafe, control telemetry, settled statics --------
def _gate(summary):
    """Reproduce the acceptance aggregation from a summary's gating block."""
    gating = summary["gating"]
    valid = (not gating["base_invalid"] and not gating["half_invalid"]
             and summary["convergence"]["ok"]
             and all(v["ok"] for v in summary["negatives"].values()))
    physical = not gating["base_failed_checks"] and not gating["half_failed_checks"]
    return ("INCONCLUSIVE" if not valid else "PASS" if physical else "FAIL")


def test_half_dt_invalidity_cannot_yield_pass(tmp_path, monkeypatch):
    """An invalid half-dt trial must make the run INCONCLUSIVE, not PASS.

    This is the supervisor's fault-injection case: real base/half physics runs, then only the
    half-dt hinge_damped is marked invalid. The comparison metrics are untouched, so any
    change in status comes purely from the gating rule.
    """
    import cadkit.physics.mechanics_run as mr

    real_run_set = mr._run_set

    def poisoned(outdir, dt):
        trials = real_run_set(outdir, dt)
        if dt < 1e-3:                      # the half-dt set only
            trials["hinge_damped"].valid = False
            trials["hinge_damped"].invalid_reasons = ["injected half invalidity"]
        return trials

    monkeypatch.setattr(mr, "_run_set", poisoned)
    summary = mr.run_mechanics(tmp_path / "run")
    assert summary["gating"]["half_invalid"] == ["hinge_damped"]
    assert summary["status"] == "INCONCLUSIVE", summary["status"]
    # The comparison metrics are genuinely untouched: the trial still measured the same period,
    # and every convergence delta equals the clean run's. A status change that came from
    # disturbed physics would not prove the gating rule.
    assert summary["half_trials"]["half/hinge_damped"]["metrics"]["measured_period_s"] > 0
    clean = mr.run_mechanics(tmp_path / "clean")
    assert summary["convergence"]["rows"] == clean["convergence"]["rows"]


def test_half_dt_failed_physical_check_cannot_yield_pass(tmp_path, monkeypatch):
    """A half-dt trial that fails a required check must make the run FAIL, not PASS."""
    import cadkit.physics.mechanics_run as mr

    real_run_set = mr._run_set

    def poisoned(outdir, dt):
        trials = real_run_set(outdir, dt)
        if dt < 1e-3:
            for check in trials["hinge_damped"].checks:
                if check["name"] == "period":
                    check["ok"] = False
                    check["detail"] = "injected physical failure"
        return trials

    monkeypatch.setattr(mr, "_run_set", poisoned)
    summary = mr.run_mechanics(tmp_path / "run")
    assert "hinge_damped:period" in summary["gating"]["half_failed_checks"]
    assert summary["status"] == "FAIL", summary["status"]
    # metrics unchanged: only the verdict was altered, so the FAIL is attributable to gating
    clean = mr.run_mechanics(tmp_path / "clean")
    assert summary["convergence"]["rows"] == clean["convergence"]["rows"]
    assert (summary["half_trials"]["half/hinge_damped"]["metrics"]
            == clean["half_trials"]["half/hinge_damped"]["metrics"])


def test_both_sets_are_persisted_with_traces(tmp_path):
    """Half trials, their checks and their CSVs must survive into the artifact."""
    from cadkit.physics.mechanics_run import run_mechanics

    out = tmp_path / "run"
    summary = run_mechanics(out)
    assert len(summary["half_trials"]) == len(summary["trials"]) == 7
    for key, trial in summary["half_trials"].items():
        assert trial["checks"], key
        assert trial["warnings"], key
        assert trial["solver_dt_s"] == pytest.approx(5e-4), key
        # The half trace must have its OWN file. An unprefixed name would be overwritten by
        # the identically named base trial, silently destroying one set of evidence.
        assert (out / f"trace_half_{key.split('/')[-1]}.csv").is_file(), key
    for key, trial in summary["trials"].items():
        assert trial["solver_dt_s"] == pytest.approx(1e-3), key
        assert (out / f"trace_base_{key.split('/')[-1]}.csv").is_file(), key
    assert len(list(out.glob("trace_*.csv"))) == 16
    assert summary["gating"]["positive_trials_gated"] == sorted(
        list(summary["trials"]) + list(summary["half_trials"]))


def test_half_dt_hinge_is_in_convergence(tmp_path):
    """The damped hinge must be part of the convergence claim, not silently excluded."""
    from cadkit.physics.mechanics_run import _convergence, _run_set

    base = _run_set(tmp_path / "b", 1e-3)
    half = _run_set(tmp_path / "h", 5e-4)
    conv = _convergence(base, half)
    trials = {r["trial"] for r in conv["rows"]}
    # Both hinges must be compared: the supervisor allowed either including the damped hinge
    # or explicitly narrowing the claim, and narrowing it silently was the failure mode.
    assert {"hinge_oscillator", "hinge_damped"} <= trials
    assert len(conv["rows"]) == 8
    assert conv["ok"]


def test_unresolvable_stop_compliance_is_rejected_before_stepping(tmp_path):
    """dt = 2 ms cannot resolve a declared 2 ms stop: refuse it rather than soften it.

    MuJoCo's refsafe floor is 2*dt, so at dt = 2 ms the effective time constant would silently
    become 4 ms while the stored solref still read 2 ms. The supervisor measured the
    consequence: the same state gives a -3.207 N constraint instead of -7.424 N.
    """
    from cadkit.physics.mechanics_run import run_stop

    with pytest.raises(ValueError, match="refsafe"):
        run_stop(tmp_path / "bad", timestep_s=2e-3)
    # and nothing was stepped: the scene directory may exist, but no trial was produced
    assert not (tmp_path / "bad" / "trace").exists()


def test_default_steps_resolve_the_declared_stop_compliance(tmp_path):
    """1 ms and 0.5 ms both clear the 2*dt floor, so the default pair is genuinely valid."""
    from cadkit.physics.mechanics_run import effective_timeconst, run_stop
    import cadkit.physics.scene as scene_mod
    from cadkit.physics.mechanics import STOP_TIMECONST_S, slider_stop_spec

    for dt in (1e-3, 5e-4):
        ex = scene_mod.export_scene(slider_stop_spec(timestep_s=dt), tmp_path / f"s{dt}")
        mujoco_ = __import__("mujoco")
        assert effective_timeconst(mujoco_, ex.model, STOP_TIMECONST_S) == pytest.approx(
            STOP_TIMECONST_S, rel=1e-12)
    trial = run_stop(tmp_path / "ok", timestep_s=1e-3)
    assert trial.metrics["stop_timeconst_resolved"] is True
    assert trial.metrics["stop_timeconst_effective_s"] == pytest.approx(STOP_TIMECONST_S)


def test_same_state_limit_force_agrees_at_the_supported_pair(tmp_path):
    """Identical state must give the same constraint force at 1 ms and 0.5 ms.

    This is the positive counterpart of the rejection test: where the declared compliance is
    resolvable, the effective physics really is step-independent.
    """
    from cadkit.physics.mechanics import slider_stop_spec
    from cadkit.physics.scene import export_scene

    forces = []
    for dt in (1e-3, 5e-4):
        ex = export_scene(slider_stop_spec(timestep_s=dt), tmp_path / f"s{dt}")
        model = ex.model
        data = mujoco.MjData(model)
        j = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "carriage_slide")
        data.qpos[int(model.jnt_qposadr[j])] = 0.0201
        a = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, "push")
        data.ctrl[a] = STOP_DRIVE_N
        mujoco.mj_forward(model, data)
        forces.append(float(data.qfrc_constraint[int(model.jnt_dofadr[j])]))
    assert forces[0] == pytest.approx(forces[1], rel=1e-12), forces


def test_over_request_distinguishes_stored_effective_and_applied(tmp_path):
    """Raw stored control, effective signal and generalized force are three quantities."""
    from cadkit.physics.mechanics_run import TRACE_HEADER, _Recorder
    from cadkit.physics.mechanics import slider_frictionless_spec
    from cadkit.physics.scene import export_scene

    ex = export_scene(slider_frictionless_spec(), tmp_path / "s")
    model = ex.model
    data = mujoco.MjData(model)
    rec = _Recorder(mujoco, model, data, "carriage_slide", "push", SLIDER_KG,
                    vmax=1e9, emax=1e9)
    rec.phase("oversaturation")
    rec.step(5, 1e6)
    row = dict(zip(TRACE_HEADER, rec.trace[-1]))
    # the raw stored control is preserved, not rewritten to look clamped
    assert row["ctrl_requested"] == pytest.approx(1e6)
    assert row["ctrl_stored"] == pytest.approx(1e6)
    # but the applied signal and the generalized force are bounded by the declared effort
    assert abs(row["ctrl_effective"]) <= 2.0 + 1e-9
    assert abs(row["actuator_force"]) <= 2.0 + 1e-9
    assert abs(row["qfrc_actuator"]) <= 2.0 + 1e-9
    assert abs(row["ctrl_effective"] - row["actuator_force"]) <= 1e-12  # gear 1


@pytest.mark.parametrize("gear", [1.0, 2.0, -2.0])
def test_effective_motor_drive_does_not_apply_gear_twice(tmp_path, gear):
    from dataclasses import replace
    from cadkit.physics.mechanics_run import _Recorder, TRACE_HEADER
    from cadkit.physics.scene import export_scene

    spec = slider_damped_spec()
    spec = replace(spec, actuators=(replace(spec.actuators[0], gear=gear),))
    model = export_scene(spec, tmp_path / "scene").model
    for ctrl in (0.25, 1e6):
        data = mujoco.MjData(model)
        rec = _Recorder(mujoco, model, data, "carriage_slide", "push", SLIDER_KG,
                        vmax=1e9, emax=1e9)
        rec.step(1, ctrl)
        row = dict(zip(TRACE_HEADER, rec.trace[0]))
        expected_drive = min(ctrl, 2.0 / abs(gear))
        assert row["ctrl_stored"] == ctrl
        assert row["ctrl_effective"] == pytest.approx(expected_drive)
        assert row["actuator_force"] == pytest.approx(expected_drive)
        assert row["qfrc_actuator"] == pytest.approx(gear * expected_drive)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_invalid_half_metric_still_writes_strict_evidence(tmp_path, monkeypatch, bad):
    import json
    import cadkit.physics.mechanics_run as runner

    original = runner._run_set
    calls = 0

    def corrupt_half(outdir, timestep_s):
        nonlocal calls
        trials = original(outdir, timestep_s)
        calls += 1
        if calls == 2:
            trial = trials["damped_return"]
            trial.valid = False
            trial.invalid_reasons.append("injected nonfinite metric after real physics")
            trial.metrics["residual_m"] = bad
        return trials

    monkeypatch.setattr(runner, "_run_set", corrupt_half)
    summary = runner.run_mechanics(tmp_path / "run")
    assert summary["status"] == "INCONCLUSIVE"
    decoded = json.loads((tmp_path / "run" / "summary.json").read_text(encoding="utf-8"),
                         parse_constant=lambda value: pytest.fail(value))
    row = next(r for r in decoded["convergence"]["rows"]
               if r["trial"] == "damped_return")
    assert row["half"] is None and row["delta"] is None and not row["ok"]
    assert "injected nonfinite metric" in (tmp_path / "run" / "report.md").read_text(
        encoding="utf-8")


def test_generic_export_rejects_unresolvable_declared_joint_stop(tmp_path):
    from dataclasses import replace
    from cadkit.physics.scene import export_scene

    spec = slider_stop_spec()
    rail, carriage = spec.bodies
    spec = replace(spec, bodies=(rail, replace(
        carriage, joint=replace(carriage.joint, stop_timeconst_s=0.001))))
    with pytest.raises(ValueError, match="joint stop.*refsafe"):
        export_scene(spec, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


@pytest.mark.parametrize("quantity", ["qfrc_spring", "qfrc_damper", "qfrc_constraint",
                                     "energy"])
def test_reported_force_and_energy_must_be_finite(tmp_path, monkeypatch, quantity):
    from cadkit.physics.mechanics_run import _Recorder
    from cadkit.physics.scene import export_scene

    model = export_scene(slider_damped_spec(), tmp_path / "scene").model
    data = mujoco.MjData(model)
    rec = _Recorder(mujoco, model, data, "carriage_slide", "push", SLIDER_KG,
                    vmax=1e9, emax=1e9)
    step = mujoco.mj_step

    def corrupt_after_real_step(model, data):
        step(model, data)
        getattr(data, quantity)[rec.dofadr] = float("inf")

    if quantity == "energy":
        monkeypatch.setattr(rec, "energy", lambda: float("nan"))
    else:
        monkeypatch.setattr(mujoco, "mj_step", corrupt_after_real_step)
    rec.step(1, 1.0)
    assert any("non-finite force or energy" in reason for reason in rec.invalid)


def test_damped_trial_reports_settled_statics_within_two_percent(tmp_path):
    """The named settled F/k check the packet requires, with settled-speed evidence."""
    from cadkit.physics.mechanics_run import run_damped_return

    trial = run_damped_return(tmp_path / "d")
    verdict = {c["name"]: c for c in trial.checks}["settled_statics_matches_force_over_k"]
    assert verdict["ok"], verdict["detail"]
    assert trial.metrics["settled_deflection_relative_error"] <= 0.02
    assert trial.metrics["settled_deflection_speed_m_s"] <= 0.02


def test_released_oscillator_is_centred_on_the_spring_reference(tmp_path):
    """Crossings are measured about springref (0), not about F/k."""
    from cadkit.physics.mechanics_run import run_frictionless_period

    trial = run_frictionless_period(tmp_path / "p")
    assert trial.metrics["release_reference_m"] == pytest.approx(0.0)
    assert abs(trial.metrics["release_centre_m"]) < 1e-3
    assert trial.metrics["relative_error"] <= 0.05


def test_undamped_centre_remains_dynamic_evidence(tmp_path):
    """The oscillation centre is kept as dynamic evidence, not presented as steady state."""
    from cadkit.physics.mechanics_run import run_frictionless_deflection

    trial = run_frictionless_deflection(tmp_path / "d")
    assert {c["name"] for c in trial.checks} >= {"deflection_matches_force_over_k"}
    assert trial.metrics["relative_error"] <= 0.02


def test_contact_timeconst_must_clear_the_refsafe_floor():
    """A declared contact stiffer than 2*dt would be silently softened by the solver."""
    with pytest.raises(ValueError, match="refsafe"):
        AssemblySpec(name="t", bodies=(BodySpec("b", parts=(_part(),), fixture="none"),),
                     timestep_s=1.0e-3, contact_timeconst_s=1.0e-3).validate()
    # exactly two timesteps is the boundary and is accepted
    spec = AssemblySpec(name="t", bodies=(BodySpec("b", parts=(_part(),), fixture="none"),),
                        timestep_s=1.0e-3, contact_timeconst_s=2.0e-3)
    spec.validate()


def test_contact_solref_is_not_softened_at_the_default_step(tmp_path):
    """The default scene's contact compliance is the one actually simulated."""
    from cadkit.physics.mechanics_run import effective_timeconst, refsafe_enabled
    from cadkit.physics.mechanics import slider_frictionless_spec
    from cadkit.physics.scene import export_scene

    spec = slider_frictionless_spec()
    ex = export_scene(spec, tmp_path / "s")
    model = ex.model
    assert refsafe_enabled(mujoco, model)
    stored = float(model.geom_solref[0][0])
    assert stored == pytest.approx(spec.contact_timeconst_s, rel=1e-12)
    assert effective_timeconst(mujoco, model, stored) == pytest.approx(stored, rel=1e-12)


def test_report_shows_both_sets_and_negative_trials(tmp_path):
    """report.md must surface half-set evidence, not only base trials."""
    from cadkit.physics.mechanics_run import run_mechanics

    out = tmp_path / "run"
    run_mechanics(out)
    text = (out / "report.md").read_text(encoding="utf-8")
    for key in ("base/damped_return", "half/damped_return", "half/hinge_damped"):
        assert key in text, key
    assert "missing_spring" in text


def test_a_trial_with_no_checks_cannot_pass(tmp_path, monkeypatch):
    """all() over an empty check list is vacuously true; gating must not rely on that."""
    import cadkit.physics.mechanics_run as mr

    real_run_set = mr._run_set

    def poisoned(outdir, dt):
        trials = real_run_set(outdir, dt)
        if dt < 1e-3:
            trials["hinge_damped"].checks = []
        return trials

    monkeypatch.setattr(mr, "_run_set", poisoned)
    summary = mr.run_mechanics(tmp_path / "run")
    assert summary["status"] == "FAIL", summary["status"]


def test_cli_labels_base_and_half_distinctly(tmp_path):
    """Per-trial CLI lines must identify the set, since trial names are shared."""
    import subprocess, sys
    from cadkit.params import REPO_ROOT

    r = subprocess.run([sys.executable, "-m", "cadkit.cli", "physics", "mechanics",
                        "--out", str(tmp_path)],
                       cwd=REPO_ROOT, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "base/damped_return:" in r.stdout
    assert "half/damped_return:" in r.stdout
