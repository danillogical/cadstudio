"""Joint coupling (gear train / rack and pinion) as a MuJoCo joint equality constraint.

Assumptions, limited to what already exists:
- Joints are named by ``JointSpec.joint_id`` and the MJCF joint name is that id unchanged
  (ids used here are already filename-safe).
- ``JointCouplingSpec`` and ``AssemblySpec.couplings`` are new; everything else is existing API.
- The scene is written to ``<outdir>/scene.xml`` by ``export_scene``.
- Simulation scenes use zero gravity, a world-fixed base, two sibling jointed bodies placed
  far apart so they cannot touch, and joint armature so the small torque gives a measurable
  but modest rotation.
"""
from __future__ import annotations

import dataclasses
import math
import xml.etree.ElementTree as ET

import pytest
from build123d import Box

from cadkit.physics.schema import (
    ActuatorSpec,
    AssemblySpec,
    BodySpec,
    ColliderSpec,
    Frame,
    JointCouplingSpec,
    JointSpec,
    PartSpec,
)

pytest.importorskip("mujoco")

import mujoco  # noqa: E402

TORQUE = 1.0e-3
SIM_S = 0.5


def _part(part_id, size=(4, 4, 4), collides=True):
    bits = {} if collides else {"contype": 0, "conaffinity": 0}
    return PartSpec(part_id, Box(*size),
                    colliders=(ColliderSpec(f"{part_id}_c", "box",
                                            tuple(s / 2 for s in size), **bits),),
                    density_g_cm3=1.24)


def _spec(couplings=(), follower_kind="hinge", extra_joint=False):
    base = BodySpec("base", parts=(_part("b", (20, 20, 4), collides=False),), fixed_to_world=True,
                    fixture="analytic_fixture")
    driver = BodySpec(
        "drv", parts=(_part("pd"),), parent="base", frame=Frame(),
        joint=JointSpec("jd", "drv", "hinge", axis=(0, 1, 0), armature=1e-3))
    follower = BodySpec(
        "fol", parts=(_part("pf"),), parent="base",
        frame=Frame(pos_mm=(100.0, 0.0, 0.0)),
        joint=JointSpec("jf", "fol", follower_kind,
                        axis=(0, 1, 0) if follower_kind == "hinge" else (1, 0, 0),
                        armature=1e-3))
    bodies = [base, driver, follower]
    if extra_joint:
        bodies.append(BodySpec(
            "fol2", parts=(_part("pf2"),), parent="base",
            joint=JointSpec("jg", "fol2", "hinge", axis=(0, 1, 0), armature=1e-3)))
    return AssemblySpec(
        name="coupled", bodies=tuple(bodies), gravity_m_s2=(0.0, 0.0, 0.0),
        actuators=(ActuatorSpec("motor", "jd", "torque", 1.0),),
        couplings=tuple(couplings))


def _coupling(**kw):
    args = dict(name="c", driver="jd", follower="jf", ratio=2.0)
    args.update(kw)
    return JointCouplingSpec(**args)


# ---- schema -----------------------------------------------------------------------
def test_coupling_spec_is_frozen_and_defaults_empty():
    c = _coupling()
    assert (c.name, c.driver, c.follower, c.ratio) == ("c", "jd", "jf", 2.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.ratio = 3.0  # type: ignore[misc]
    assert _spec().couplings == ()


def test_valid_coupling_validates():
    _spec([_coupling()]).validate()


@pytest.mark.parametrize("coupling,match", [
    (dict(driver="nope"), "nope"),
    (dict(follower="nope"), "nope"),
    (dict(follower="jd"), "jd"),
    (dict(ratio=0.0), "ratio"),
    (dict(ratio=math.inf), "ratio"),
    (dict(ratio=math.nan), "ratio"),
])
def test_invalid_coupling_rejected(coupling, match):
    with pytest.raises(ValueError, match=match):
        _spec([_coupling(**coupling)]).validate()


def test_duplicate_coupling_names_rejected():
    spec = _spec([_coupling(), _coupling(follower="jg")], extra_joint=True)
    with pytest.raises(ValueError):
        spec.validate()


def test_follower_coupled_twice_rejected():
    spec = _spec([_coupling(name="a"), _coupling(name="b", ratio=3.0)])
    with pytest.raises(ValueError):
        spec.validate()


# ---- export -----------------------------------------------------------------------
def test_export_emits_joint_equality(tmp_path):
    from cadkit.physics.scene import export_scene

    ex = export_scene(_spec([_coupling(ratio=-0.5)]), tmp_path / "out")
    root = ET.parse(ex.scene_xml).getroot()
    eqs = root.findall("./equality/joint")
    assert len(eqs) == 1
    eq = eqs[0]
    assert eq.get("joint1") == "jf" and eq.get("joint2") == "jd"
    coef = [float(v) for v in eq.get("polycoef").split()]
    assert len(coef) == 5
    assert coef[0] == pytest.approx(0.0)
    assert coef[1] == pytest.approx(-0.5)
    assert coef[2:] == pytest.approx([0.0, 0.0, 0.0])


def test_no_coupling_emits_no_equality(tmp_path):
    from cadkit.physics.scene import export_scene

    ex = export_scene(_spec(), tmp_path / "out")
    assert ET.parse(ex.scene_xml).getroot().find("equality") is None


def test_scene_hash_changes_with_ratio(tmp_path):
    from cadkit.physics.scene import export_scene

    a = export_scene(_spec([_coupling(ratio=2.0)]), tmp_path / "a")
    b = export_scene(_spec([_coupling(ratio=3.0)]), tmp_path / "b")
    assert a.scene_hash != b.scene_hash


def test_scene_identity_changes_with_ratio(tmp_path):
    from cadkit.physics.scene import compute_scene_hash, export_scene, scene_identity

    ex = export_scene(_spec([_coupling(ratio=2.0)]), tmp_path / "a")
    xml = ex.scene_xml.read_text(encoding="utf-8")
    other = _spec([_coupling(ratio=3.0)])
    h1 = compute_scene_hash(scene_identity(xml, ex.asset_hashes, _spec([_coupling(ratio=2.0)])))
    h2 = compute_scene_hash(scene_identity(xml, ex.asset_hashes, other))
    assert h1 != h2


# ---- simulation -------------------------------------------------------------------
def _drive(tmp_path, spec):
    from cadkit.physics.scene import export_scene

    ex = export_scene(spec, tmp_path / "sim")
    model = mujoco.MjModel.from_xml_path(str(ex.scene_xml))
    data = mujoco.MjData(model)
    act = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, "motor")
    jd = model.joint("jd").qposadr[0]
    jf = model.joint("jf").qposadr[0]
    data.ctrl[act] = TORQUE
    for _ in range(int(round(SIM_S / model.opt.timestep))):
        mujoco.mj_step(model, data)
    return float(data.qpos[jd]), float(data.qpos[jf])


@pytest.mark.parametrize("ratio", [-0.5, 2.0])
def test_hinge_follower_tracks_ratio_times_driver(tmp_path, ratio):
    q_d, q_f = _drive(tmp_path, _spec([_coupling(ratio=ratio)]))
    assert abs(q_d) > 1e-2 and abs(q_f) > 1e-3, (q_d, q_f)
    assert q_f == pytest.approx(ratio * q_d, rel=0.01)


def test_rack_follower_slides_radius_times_angle(tmp_path):
    r = 0.01  # pinion radius in metres: slide travel = r * theta
    q_d, q_f = _drive(tmp_path, _spec([_coupling(ratio=r)], follower_kind="slide"))
    assert abs(q_d) > 1e-2 and abs(q_f) > 1e-5, (q_d, q_f)
    assert q_f == pytest.approx(r * q_d, rel=0.01)


# ---- runner verification ----------------------------------------------------------
def _compile(tmp_path, spec):
    from cadkit.physics.scene import export_scene

    ex = export_scene(spec, tmp_path / "verify")
    return mujoco.MjModel.from_xml_path(str(ex.scene_xml)), ex


@pytest.mark.parametrize("kind,ratio", [("hinge", 2.0), ("slide", 0.01)])
def test_verify_compiled_records_coupling_facts(tmp_path, kind, ratio):
    from cadkit.physics.runner import _verify_compiled

    spec = _spec([_coupling(ratio=ratio)], follower_kind=kind)
    model, ex = _compile(tmp_path, spec)
    facts, _ = _verify_compiled(mujoco, model, spec, ex)
    rec = facts["couplings"]["c"]
    assert rec["driver"] == "jd" and rec["follower"] == "jf"
    assert rec["polycoef"] == pytest.approx([0.0, ratio, 0.0, 0.0, 0.0])
    assert rec["solref"] == pytest.approx([2.0e-3, 1.0])


def _tamper_ratio(model, eid):
    model.eq_data[eid][1] = 3.0


def _tamper_solref(model, eid):
    model.eq_solref[eid][0] = 0.05


def _tamper_swap(model, eid):
    a, b = int(model.eq_obj1id[eid]), int(model.eq_obj2id[eid])
    model.eq_obj1id[eid], model.eq_obj2id[eid] = b, a


@pytest.mark.parametrize("tamper", [_tamper_ratio, _tamper_solref, _tamper_swap])
def test_verify_couplings_rejects_tampered_model(tmp_path, tamper):
    from cadkit.physics.runner import ScenarioError, _verify_couplings

    spec = _spec([_coupling(name="gear")])
    model, _ = _compile(tmp_path, spec)
    assert "gear" in _verify_couplings(mujoco, model, spec)
    tamper(model, mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_EQUALITY, "gear"))
    with pytest.raises(ScenarioError, match="gear"):
        _verify_couplings(mujoco, model, spec)


def test_uncoupled_assembly_records_no_couplings(tmp_path):
    from cadkit.physics.runner import _resolved_inputs, _verify_compiled

    spec = _spec()
    model, ex = _compile(tmp_path, spec)
    facts, _ = _verify_compiled(mujoco, model, spec, ex)
    assert "couplings" not in facts
    assert "couplings" not in _resolved_inputs(spec)


def test_coupled_assembly_lists_couplings_in_resolved_inputs():
    from cadkit.physics.runner import _resolved_inputs

    assert len(_resolved_inputs(_spec([_coupling()]))["couplings"]) == 1
