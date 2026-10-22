"""Per-collider friction and priority: validation, XML, recorded inputs, effective contacts."""
from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest

from cadkit.physics.schema import ColliderSpec

pytest.importorskip("mujoco", reason="optional physics extra not installed")

import mujoco  # noqa: E402

from cadkit.physics.replay import replay_run  # noqa: E402
from cadkit.physics.runner import _verify_compiled, run_assembly  # noqa: E402
from cadkit.physics.scenario import (  # noqa: E402
    AcceptanceSpec,
    BudgetSpec,
    CheckSpec,
    PhaseSpec,
    ScenarioError,
    ScenarioSpec,
    ValiditySpec,
    build_fixture,
)
from cadkit.physics.scene import export_scene  # noqa: E402


def _collider(**kw):
    return ColliderSpec("c", "box", (1.0, 1.0, 1.0), **kw)


def _with_colliders(box=None, floor=None, **spec_kw):
    """The drop_box fixture with replacement friction/priority on its two colliders."""
    spec = build_fixture("drop_box", 0.001)
    bodies = []
    for body in spec.bodies:
        kw = floor if body.body_id == "floor" else box
        parts = tuple(replace(part, colliders=tuple(replace(c, **(kw or {}))
                                                    for c in part.colliders))
                      for part in body.parts)
        bodies.append(replace(body, parts=parts))
    return replace(spec, bodies=tuple(bodies), **spec_kw)


def _scenario(hold_s=0.4):
    return ScenarioSpec(
        "fp_drop", "drop_box", 0,
        (PhaseSpec("reset", "reset"), PhaseSpec("settle", "settle", hold_s)),
        0.001, 0.01, BudgetSpec(20000, 10.0, 20000))


def _acceptance():
    return AcceptanceSpec("fp_acc", (
        CheckSpec(name="pen", kind="penetration_bound", maximum=0.005, units="m"),),
        ValiditySpec())


# --------------------------------------------------------------------------- validation
@pytest.mark.parametrize("friction", [
    (0.3, 0.005), (0.3, 0.005, 0.0001, 0.1), (),
    (-0.1, 0.005, 0.0001), (0.3, -1e-9, 0.0001),
    (float("nan"), 0.0, 0.0), (0.3, float("inf"), 0.0), (0.3, 0.0, float("-inf")),
])
def test_bad_friction_is_rejected(friction):
    with pytest.raises(ValueError, match="friction"):
        _collider(friction=friction).validate()


@pytest.mark.parametrize("priority", [-1, 1.0, "1", None, True])
def test_bad_priority_is_rejected(priority):
    with pytest.raises(ValueError, match="priority"):
        _collider(priority=priority).validate()


def test_valid_friction_and_priority_accepted():
    _collider(friction=(0.3, 0.0, 0.0), priority=1).validate()
    _collider(friction=(0.0, 0.0, 0.0), priority=0).validate()
    _collider().validate()


def test_defaults_are_inherit_and_zero():
    c = _collider()
    assert c.friction is None and c.priority == 0


def test_assembly_validate_rejects_bad_collider_friction():
    spec = _with_colliders(box={"friction": (math.nan, 0.0, 0.0)})
    with pytest.raises(ValueError, match="friction"):
        spec.validate()


# --------------------------------------------------------------------------- XML
def _geom_lines(xml: str, *names):
    return {n: next(line for line in xml.splitlines() if f'name="{n}"' in line and "<geom" in line)
            for n in names}


def test_xml_emits_attributes_only_when_set(tmp_path):
    base = export_scene(_with_colliders(), tmp_path / "base")
    xml = base.scene_xml.read_text(encoding="utf-8")
    lines = _geom_lines(xml, "box_col", "floor_col")
    for line in lines.values():
        assert "friction=" not in line and "priority=" not in line

    set_ = export_scene(
        _with_colliders(box={"friction": (0.3, 0.005, 0.0001), "priority": 1}),
        tmp_path / "set")
    lines = _geom_lines(set_.scene_xml.read_text(encoding="utf-8"), "box_col", "floor_col")
    assert 'friction="0.3 0.005 0.0001"' in lines["box_col"]
    assert 'priority="1"' in lines["box_col"]
    assert "friction=" not in lines["floor_col"] and "priority=" not in lines["floor_col"]
    assert set_.scene_hash != base.scene_hash


def test_default_colliders_scene_is_unchanged_by_the_new_fields(tmp_path):
    """A spec that spells out the defaults emits byte-identical XML and the same hash."""
    a = export_scene(_with_colliders(), tmp_path / "a")
    b = export_scene(_with_colliders(box={"friction": None, "priority": 0},
                                     floor={"friction": None, "priority": 0}),
                     tmp_path / "b")
    assert a.scene_xml.read_bytes() == b.scene_xml.read_bytes()
    assert a.scene_hash == b.scene_hash


def test_priority_zero_is_not_emitted_but_friction_equal_to_default_is(tmp_path):
    """An explicit friction is emitted even when it equals the default, so it is declared."""
    spec = build_fixture("drop_box", 0.001)
    ex = export_scene(_with_colliders(box={"friction": spec.friction}), tmp_path)
    lines = _geom_lines(ex.scene_xml.read_text(encoding="utf-8"), "box_col")
    assert "friction=" in lines["box_col"] and "priority=" not in lines["box_col"]


# --------------------------------------------------------------------------- physical_inputs
def test_physical_inputs_record_resolved_friction_and_priority(tmp_path):
    spec = _with_colliders(box={"friction": (0.3, 0.005, 0.0001), "priority": 1})
    summary = run_assembly(spec, _scenario(0.1), _acceptance(), tmp_path / "run")
    assert summary["status"] == "PASS", summary.get("detail")
    cols = {c["collider_id"]: c
            for body in summary["physical_inputs"]["bodies"]
            for part in body["parts"] for c in part["colliders"]}
    assert cols["box_col"]["friction"] == [0.3, 0.005, 0.0001]
    assert cols["box_col"]["priority"] == 1
    # The floor inherits the assembly default and records it resolved, not as null.
    assert cols["floor_col"]["friction"] == list(spec.friction)
    assert cols["floor_col"]["priority"] == 0


# --------------------------------------------------------------------------- effective friction
def _settled_contact_friction(tmp_path, spec):
    ex = export_scene(spec, tmp_path)
    model = mujoco.MjModel.from_xml_path(str(ex.scene_xml))
    data = mujoco.MjData(model)
    for _ in range(600):
        mujoco.mj_step(model, data)
    box = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "box_col")
    floor = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "floor_col")
    rows = [i for i in range(data.ncon)
            if {int(data.contact[i].geom1), int(data.contact[i].geom2)} == {box, floor}]
    assert rows, "the box never touched the floor"
    return model, [float(data.contact[i].friction[0]) for i in rows], (box, floor)


def test_higher_priority_collider_sets_effective_contact_friction(tmp_path):
    spec = _with_colliders(box={"friction": (0.30, 0.005, 0.0001), "priority": 1},
                           floor={"friction": (0.50, 0.005, 0.0001), "priority": 0})
    model, effective, (box, floor) = _settled_contact_friction(tmp_path, spec)
    assert model.geom_friction[box][0] == pytest.approx(0.30)
    assert model.geom_friction[floor][0] == pytest.approx(0.50)
    assert effective == pytest.approx([0.30] * len(effective), abs=1e-9)


def test_equal_priority_uses_the_max_friction(tmp_path):
    """Contrast: without a priority difference MuJoCo takes the larger friction."""
    spec = _with_colliders(box={"friction": (0.30, 0.005, 0.0001)},
                           floor={"friction": (0.50, 0.005, 0.0001)})
    _, effective, _ = _settled_contact_friction(tmp_path, spec)
    assert effective == pytest.approx([0.50] * len(effective), abs=1e-9)


# --------------------------------------------------------------------------- compiled check
def _compiled(tmp_path, spec):
    ex = export_scene(spec, tmp_path)
    return mujoco.MjModel.from_xml_path(str(ex.scene_xml)), ex


def test_verify_compiled_accepts_matching_model(tmp_path):
    spec = _with_colliders(box={"friction": (0.3, 0.005, 0.0001), "priority": 1})
    model, ex = _compiled(tmp_path, spec)
    facts, _ = _verify_compiled(mujoco, model, spec, ex)
    assert facts["collider_geoms"]["box_col"]["priority"] == 1
    assert facts["collider_geoms"]["box_col"]["friction"][0] == pytest.approx(0.3)


def test_verify_compiled_detects_friction_mismatch(tmp_path):
    spec = _with_colliders(box={"friction": (0.3, 0.005, 0.0001), "priority": 1})
    model, ex = _compiled(tmp_path, spec)
    gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "box_col")
    model.geom_friction[gid][0] = 0.9
    with pytest.raises(ScenarioError, match="friction"):
        _verify_compiled(mujoco, model, spec, ex)


def test_verify_compiled_detects_inherited_friction_mismatch(tmp_path):
    """A collider with no friction must still equal the assembly default, wherever it is."""
    spec = _with_colliders()
    model, ex = _compiled(tmp_path, spec)
    gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "floor_col")
    model.geom_friction[gid][0] = 0.1
    with pytest.raises(ScenarioError, match="friction"):
        _verify_compiled(mujoco, model, spec, ex)


def test_verify_compiled_detects_priority_mismatch(tmp_path):
    spec = _with_colliders(box={"priority": 1})
    model, ex = _compiled(tmp_path, spec)
    gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "box_col")
    model.geom_priority[gid] = 0
    with pytest.raises(ScenarioError, match="priority"):
        _verify_compiled(mujoco, model, spec, ex)


def test_run_assembly_reports_a_declared_vs_compiled_mismatch_as_error(tmp_path, monkeypatch):
    """End to end: tamper with the compiled model and the run must not report PASS."""
    import cadkit.physics.runner as runner

    real = runner._verify_compiled

    def tampered(mj, model, spec, export):
        gid = mj.mj_name2id(model, mj.mjtObj.mjOBJ_GEOM, "box_col")
        model.geom_friction[gid][0] += 0.2
        return real(mj, model, spec, export)

    monkeypatch.setattr(runner, "_verify_compiled", tampered)
    spec = _with_colliders(box={"friction": (0.3, 0.005, 0.0001), "priority": 1})
    summary = run_assembly(spec, _scenario(0.1), _acceptance(), tmp_path / "run")
    assert summary["status"] == "ERROR"
    assert "friction" in summary["detail"]


# --------------------------------------------------------------------------- replay
def test_replay_reproduces_a_run_with_per_collider_friction(tmp_path):
    spec = _with_colliders(box={"friction": (0.30, 0.005, 0.0001), "priority": 1},
                           floor={"friction": (0.50, 0.005, 0.0001)})
    summary = run_assembly(spec, _scenario(0.3), _acceptance(), tmp_path / "run")
    assert summary["status"] == "PASS", summary.get("detail")
    assert summary["solver"]["collider_geoms"]["box_col"]["priority"] == 1
    result = replay_run(tmp_path / "run", tmp_path / "rep")
    assert result["status"] == "PASS" and result["reproduced"] is True


def test_replay_rejects_a_recorded_friction_that_disagrees_with_the_scene(tmp_path):
    """Editing a recorded per-collider friction must break replay, not pass silently."""
    import json

    from cadkit.physics.replay import ReplayError

    spec = _with_colliders(box={"friction": (0.30, 0.005, 0.0001), "priority": 1})
    run = tmp_path / "run"
    run_assembly(spec, _scenario(0.1), _acceptance(), run)
    path = run / "summary.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["solver"]["collider_geoms"]["box_col"]["friction"][0] = 0.9
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ReplayError):
        replay_run(run, tmp_path / "rep")
