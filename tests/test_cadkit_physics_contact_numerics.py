"""Optional contact numerics: validation, XML, recorded inputs, compiled check, replay, effect."""
from __future__ import annotations

import json
import math
from dataclasses import replace

import pytest

from cadkit.physics.schema import ColliderSpec

pytest.importorskip("mujoco", reason="optional physics extra not installed")

import mujoco  # noqa: E402

from cadkit.physics.evidence import raw_sha256  # noqa: E402
from cadkit.physics.replay import ReplayError, replay_run  # noqa: E402
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

NAN, INF = float("nan"), float("inf")


def _spec(box=None, **kw):
    """The drop_box fixture with assembly-level numerics and optional box collider overrides."""
    spec = build_fixture("drop_box", 0.001)
    if box:
        bodies = []
        for body in spec.bodies:
            if body.body_id == "floor":
                bodies.append(body)
                continue
            parts = tuple(replace(p, colliders=tuple(replace(c, **box) for c in p.colliders))
                          for p in body.parts)
            bodies.append(replace(body, parts=parts))
        spec = replace(spec, bodies=tuple(bodies))
    return replace(spec, **kw)


def _scenario(hold_s=0.1):
    return ScenarioSpec(
        "cn_drop", "drop_box", 0,
        (PhaseSpec("reset", "reset"), PhaseSpec("settle", "settle", hold_s)),
        0.001, 0.01, BudgetSpec(20000, 10.0, 20000))


def _acceptance():
    return AcceptanceSpec("cn_acc", (
        CheckSpec(name="pen", kind="penetration_bound", maximum=0.005, units="m"),),
        ValiditySpec())


_FULL = dict(contact_solimp=(0.9, 0.99, 0.002, 0.4, 3.0), contact_margin_m=0.002,
             contact_gap_m=0.001, noslip_iterations=3, impratio=2.0)


# --------------------------------------------------------------------------- validation
@pytest.mark.parametrize("solimp", [
    (), (0.9, 0.99), (0.9, 0.99, 0.001, 0.5), (0.9, 0.99, 0.001, 0.5, 2.0, 1.0),
    (0.0, 0.99, 0.001), (-0.1, 0.99, 0.001), (0.995, 0.99, 0.001), (0.9, 1.0, 0.001),
    (0.9, 0.99, 0.0), (0.9, 0.99, -0.001),
    (0.9, 0.99, 0.001, 0.0, 2.0), (0.9, 0.99, 0.001, 1.0, 2.0), (0.9, 0.99, 0.001, 0.5, 0.9),
    (NAN, 0.99, 0.001), (0.9, INF, 0.001), (0.9, 0.99, NAN), (0.9, 0.99, 0.001, NAN, 2.0),
    (0.9, 0.99, 0.001, 0.5, INF), (True, 0.99, 0.001), (0.9, 0.99, True),
])
def test_bad_contact_solimp_is_rejected(solimp):
    with pytest.raises(ValueError, match="solimp"):
        _spec(contact_solimp=solimp).validate()


@pytest.mark.parametrize("solimp", [(0.9, 0.9, 0.001), (0.9, 0.99, 0.001),
                                    (0.9, 0.99, 0.001, 0.5, 1.0), (0.99, 0.999, 0.0001)])
def test_valid_contact_solimp_is_accepted(solimp):
    _spec(contact_solimp=solimp).validate()


@pytest.mark.parametrize("field,value", [
    ("contact_margin_m", -1e-9), ("contact_margin_m", NAN), ("contact_margin_m", INF),
    ("contact_margin_m", True),
    ("contact_gap_m", -1e-9), ("contact_gap_m", NAN), ("contact_gap_m", INF),
    ("contact_gap_m", True),
])
def test_bad_margin_or_gap_is_rejected(field, value):
    kw = {field: value}
    if field == "contact_gap_m":
        kw["contact_margin_m"] = 0.01
    with pytest.raises(ValueError, match=field):
        _spec(**kw).validate()


def test_gap_above_margin_is_rejected():
    with pytest.raises(ValueError, match="contact_gap_m"):
        _spec(contact_margin_m=0.001, contact_gap_m=0.002).validate()
    with pytest.raises(ValueError, match="contact_gap_m"):
        _spec(contact_gap_m=0.001).validate()  # unset margin means 0


def test_gap_equal_to_margin_and_zero_values_are_accepted():
    _spec(contact_margin_m=0.002, contact_gap_m=0.002).validate()
    _spec(contact_margin_m=0.0, contact_gap_m=0.0).validate()


@pytest.mark.parametrize("value", [-1, 1.0, "1", None, True, False])
def test_bad_noslip_iterations_is_rejected(value):
    with pytest.raises(ValueError, match="noslip_iterations"):
        _spec(noslip_iterations=value).validate()


@pytest.mark.parametrize("value", [0.0, -1.0, NAN, INF, True, "2"])
def test_bad_impratio_is_rejected(value):
    with pytest.raises(ValueError, match="impratio"):
        _spec(impratio=value).validate()


def test_valid_numerics_are_accepted_and_default_to_unset():
    _spec(**_FULL).validate()
    spec = build_fixture("drop_box", 0.001)
    assert spec.contact_solimp is None and spec.contact_margin_m is None
    assert spec.contact_gap_m is None and spec.impratio is None
    assert spec.noslip_iterations == 0


def _collider(**kw):
    return ColliderSpec("c", "box", (1.0, 1.0, 1.0), **kw)


@pytest.mark.parametrize("kw,match", [
    ({"solimp": (0.9, 0.99)}, "solimp"), ({"solimp": (0.99, 0.9, 0.001)}, "solimp"),
    ({"solimp": (0.9, 0.99, 0.001, 0.5, 0.5)}, "solimp"), ({"solimp": (NAN, 0.99, 0.001)}, "solimp"),
    ({"solref": (0.01,)}, "solref"), ({"solref": (0.01, 1.0, 1.0)}, "solref"),
    ({"solref": (0.0, 1.0)}, "solref"), ({"solref": (0.01, -1.0)}, "solref"),
    ({"solref": (NAN, 1.0)}, "solref"), ({"solref": (True, 1.0)}, "solref"),
    ({"margin": -0.001}, "margin"), ({"margin": NAN}, "margin"),
    ({"margin": INF}, "margin"), ({"margin": True}, "margin"),
])
def test_bad_collider_numerics_are_rejected(kw, match):
    with pytest.raises(ValueError, match=match):
        _collider(**kw).validate()


def test_valid_collider_numerics_are_accepted_and_default_to_none():
    _collider(solimp=(0.9, 0.99, 0.001), solref=(0.01, 1.0), margin=0.0).validate()
    c = _collider()
    assert c.solimp is None and c.solref is None and c.margin is None


def test_refsafe_guard_still_enforced():
    # Assembly time constant below 2*dt.
    with pytest.raises(ValueError, match="2"):
        _spec(contact_timeconst_s=0.0015).validate()
    # Per-collider solref below 2*dt (dt = 0.001).
    with pytest.raises(ValueError, match="solref"):
        _spec(box={"solref": (0.0015, 1.0)}).validate()
    _spec(box={"solref": (0.002, 1.0)}).validate()


# --------------------------------------------------------------------------- XML
def _line(xml: str, marker: str) -> str:
    """The whole `<geom .../>` or `<option .../>` element containing the marker (may wrap)."""
    at = xml.index(marker)
    start = xml.rfind("<", 0, at)
    return xml[start:xml.index("/>", at)]


def test_unset_numerics_leave_xml_and_hash_byte_identical(tmp_path):
    a = export_scene(build_fixture("drop_box", 0.001), tmp_path / "a")
    b = export_scene(_spec(contact_solimp=None, contact_margin_m=None, contact_gap_m=None,
                           noslip_iterations=0, impratio=None), tmp_path / "b")
    assert a.scene_xml.read_bytes() == b.scene_xml.read_bytes()
    assert a.scene_hash == b.scene_hash
    xml = a.scene_xml.read_text(encoding="utf-8")
    assert 'solimp="0.95 0.99 0.001"' in _line(xml, "<geom condim")
    for token in ("margin=", "gap=", "noslip_iterations", "impratio"):
        assert token not in xml


def test_set_numerics_are_emitted(tmp_path):
    base = export_scene(build_fixture("drop_box", 0.001), tmp_path / "base")
    ex = export_scene(_spec(**_FULL), tmp_path / "set")
    xml = ex.scene_xml.read_text(encoding="utf-8")
    default_geom = xml[xml.index("<default>"):xml.index("</default>")]
    assert 'solimp="0.9 0.99 0.002 0.4 3.0"' in default_geom
    assert "0.95 0.99 0.001" not in default_geom
    assert 'margin="0.002"' in default_geom and 'gap="0.001"' in default_geom
    option = _line(xml, "<option")
    assert 'noslip_iterations="3"' in option and 'impratio="2.0"' in option
    assert ex.scene_hash != base.scene_hash


@pytest.mark.parametrize("kw,present,absent", [
    ({"contact_solimp": (0.99, 0.999, 0.0001)}, ['solimp="0.99 0.999 0.0001"'],
     ["margin=", "gap=", "noslip", "impratio"]),
    ({"contact_margin_m": 0.003}, ['margin="0.003"'], ["gap=", "noslip", "impratio"]),
    ({"noslip_iterations": 2}, ['noslip_iterations="2"'], ["impratio", "margin=", "gap="]),
    ({"impratio": 3.0}, ['impratio="3.0"'], ["noslip", "margin=", "gap="]),
])
def test_each_numeric_is_emitted_only_when_set(tmp_path, kw, present, absent):
    xml = export_scene(_spec(**kw), tmp_path).scene_xml.read_text(encoding="utf-8")
    for token in present:
        assert token in xml
    for token in absent:
        assert token not in xml


def test_per_collider_numerics_are_emitted_only_on_that_geom(tmp_path):
    ex = export_scene(_spec(box={"solimp": (0.9, 0.95, 0.002), "solref": (0.01, 0.8),
                                 "margin": 0.004}), tmp_path)
    xml = ex.scene_xml.read_text(encoding="utf-8")
    box = _line(xml, 'name="box_col"')
    floor = _line(xml, 'name="floor_col"')
    assert 'solimp="0.9 0.95 0.002"' in box and 'solref="0.01 0.8"' in box
    assert 'margin="0.004"' in box
    for token in ("solimp=", "solref=", "margin="):
        assert token not in floor


# --------------------------------------------------------------------------- physical inputs
def test_physical_inputs_and_solver_facts_record_the_numerics(tmp_path):
    spec = _spec(box={"solimp": (0.9, 0.95, 0.002, 0.5, 2.0), "solref": (0.01, 0.8),
                      "margin": 0.004}, **_FULL)
    summary = run_assembly(spec, _scenario(), _acceptance(), tmp_path / "run")
    assert summary["status"] == "PASS", summary.get("detail")
    inputs = summary["physical_inputs"]
    assert inputs["contact_solimp"] == [0.9, 0.99, 0.002, 0.4, 3.0]
    assert inputs["contact_margin_m"] == 0.002 and inputs["contact_gap_m"] == 0.001
    assert inputs["noslip_iterations"] == 3 and inputs["impratio"] == 2.0
    cols = {c["collider_id"]: c for b in inputs["bodies"] for p in b["parts"]
            for c in p["colliders"]}
    assert cols["box_col"]["solimp"] == [0.9, 0.95, 0.002, 0.5, 2.0]
    assert cols["box_col"]["solref"] == [0.01, 0.8] and cols["box_col"]["margin"] == 0.004
    assert cols["floor_col"]["solimp"] is None and cols["floor_col"]["margin"] is None
    solver = summary["solver"]
    assert solver["solver_settings"]["noslip_iterations"] == 3
    assert solver["solver_settings"]["impratio"] == pytest.approx(2.0)
    box = solver["collider_geoms"]["box_col"]
    assert box["solimp"] == pytest.approx([0.9, 0.95, 0.002, 0.5, 2.0])
    assert box["solref"] == pytest.approx([0.01, 0.8]) and box["margin"] == pytest.approx(0.004)
    floor = solver["collider_geoms"]["floor_col"]
    assert floor["solimp"] == pytest.approx([0.9, 0.99, 0.002, 0.4, 3.0])
    assert floor["margin"] == pytest.approx(0.002) and floor["gap"] == pytest.approx(0.001)


def test_unset_inputs_are_recorded_as_unset(tmp_path):
    summary = run_assembly(build_fixture("drop_box", 0.001), _scenario(), _acceptance(),
                           tmp_path / "run")
    assert summary["status"] == "PASS", summary.get("detail")
    inputs = summary["physical_inputs"]
    assert inputs["contact_solimp"] is None and inputs["contact_margin_m"] is None
    assert inputs["contact_gap_m"] is None and inputs["impratio"] is None
    assert inputs["noslip_iterations"] == 0


# --------------------------------------------------------------------------- compiled check
def _compiled(tmp_path, spec):
    ex = export_scene(spec, tmp_path)
    return mujoco.MjModel.from_xml_path(str(ex.scene_xml)), ex


def _gid(model, name="box_col"):
    return mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, name)


def test_verify_compiled_accepts_matching_numerics(tmp_path):
    spec = _spec(box={"solimp": (0.9, 0.95, 0.002, 0.5, 2.0), "solref": (0.01, 0.8),
                      "margin": 0.004}, **_FULL)
    model, ex = _compiled(tmp_path, spec)
    facts, _ = _verify_compiled(mujoco, model, spec, ex)
    assert facts["solver_settings"]["noslip_iterations"] == 3
    assert facts["collider_geoms"]["box_col"]["margin"] == pytest.approx(0.004)


def _tamper_geom(array, value):
    def apply(model, gid):
        getattr(model, array)[gid] = value
    return apply


def _tamper_opt(attr, value):
    def apply(model, gid):
        setattr(model.opt, attr, value)
    return apply


@pytest.mark.parametrize("label,tamper", [
    ("solimp", _tamper_geom("geom_solimp", [0.5, 0.6, 0.01, 0.5, 2.0])),
    ("solref", _tamper_geom("geom_solref", [0.05, 1.0])),
    ("margin", _tamper_geom("geom_margin", 0.01)),
    ("gap", _tamper_geom("geom_gap", 0.0)),
    ("noslip_iterations", _tamper_opt("noslip_iterations", 0)),
    ("impratio", _tamper_opt("impratio", 7.0)),
])
def test_verify_compiled_detects_tampered_numerics(tmp_path, label, tamper):
    spec = _spec(box={"solimp": (0.9, 0.95, 0.002, 0.5, 2.0), "solref": (0.01, 0.8),
                      "margin": 0.004}, **{**_FULL, "contact_margin_m": 0.004})
    model, ex = _compiled(tmp_path, spec)
    tamper(model, _gid(model))
    with pytest.raises(ScenarioError, match=label):
        _verify_compiled(mujoco, model, spec, ex)


def test_verify_compiled_detects_tampered_inherited_default(tmp_path):
    """A collider without overrides must equal the assembly default, wherever it is."""
    spec = _spec()
    model, ex = _compiled(tmp_path, spec)
    model.geom_solimp[_gid(model, "floor_col")][0] = 0.5
    with pytest.raises(ScenarioError, match="solimp"):
        _verify_compiled(mujoco, model, spec, ex)


def test_three_value_collider_solimp_under_a_five_value_default_verifies(tmp_path):
    """A declared 3-value collider solimp must verify whatever tail the compiler resolves."""
    spec = _spec(box={"solimp": (0.9, 0.95, 0.002)}, contact_solimp=(0.9, 0.99, 0.002, 0.4, 3.0))
    model, ex = _compiled(tmp_path, spec)
    _verify_compiled(mujoco, model, spec, ex)


# --------------------------------------------------------------------------- replay
def test_replay_reproduces_a_run_with_contact_numerics(tmp_path):
    spec = _spec(box={"solimp": (0.9, 0.95, 0.002, 0.5, 2.0), "margin": 0.004},
                 **{**_FULL, "contact_margin_m": 0.004})
    summary = run_assembly(spec, _scenario(0.2), _acceptance(), tmp_path / "run")
    assert summary["status"] == "PASS", summary.get("detail")
    result = replay_run(tmp_path / "run", tmp_path / "rep")
    assert result["status"] == "PASS" and result["reproduced"] is True


def _edit_summary(run, edit):
    path = run / "summary.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    edit(data)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


@pytest.mark.parametrize("name,edit", [
    ("noslip", lambda d: d["solver"]["solver_settings"].__setitem__("noslip_iterations", 9)),
    ("impratio", lambda d: d["solver"]["solver_settings"].__setitem__("impratio", 9.0)),
    ("geom_solimp", lambda d: d["solver"]["collider_geoms"]["box_col"]["solimp"].__setitem__(0, 0.5)),
    ("geom_solref", lambda d: d["solver"]["collider_geoms"]["box_col"]["solref"].__setitem__(0, 0.05)),
    ("geom_margin", lambda d: d["solver"]["collider_geoms"]["box_col"].__setitem__("margin", 0.02)),
    ("geom_gap", lambda d: d["solver"]["collider_geoms"]["box_col"].__setitem__("gap", 0.0)),
])
def test_replay_fails_when_recorded_numerics_are_edited(tmp_path, name, edit):
    run = tmp_path / "run"
    summary = run_assembly(_spec(**_FULL), _scenario(), _acceptance(), run)
    assert summary["status"] == "PASS", summary.get("detail")
    _edit_summary(run, edit)
    with pytest.raises(ReplayError):
        replay_run(run, tmp_path / "rep")


def test_replay_of_a_summary_without_the_new_keys_still_works(tmp_path):
    """Backward compatibility: a default run whose record predates the new keys replays."""
    run = tmp_path / "run"
    summary = run_assembly(build_fixture("drop_box", 0.001), _scenario(), _acceptance(), run)
    assert summary["status"] == "PASS", summary.get("detail")

    def strip_solver(data):
        for key in ("noslip_iterations", "impratio"):
            data["solver"]["solver_settings"].pop(key, None)
        for geom in data["solver"]["collider_geoms"].values():
            for key in ("solimp", "solref", "margin", "gap"):
                geom.pop(key, None)

    def strip(data):
        strip_solver(data)
        inputs = data["physical_inputs"]
        for key in ("contact_solimp", "contact_margin_m", "contact_gap_m",
                    "noslip_iterations", "impratio"):
            inputs.pop(key, None)
        for body in inputs["bodies"]:
            for part in body["parts"]:
                for c in part["colliders"]:
                    for key in ("solimp", "solref", "margin"):
                        c.pop(key, None)

    _edit_summary(run, strip)
    # The manifest carries a copy of the solver facts that must agree with the summary.
    manifest = run / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    strip_solver(data)
    entry = data["artifacts"]["summary.json"]
    entry["sha256"] = raw_sha256((run / "summary.json").read_bytes())
    if "bytes" in entry:
        entry["bytes"] = (run / "summary.json").stat().st_size
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    result = replay_run(run, tmp_path / "rep")
    assert result["status"] == "PASS" and result["reproduced"] is True


# --------------------------------------------------------------------------- physical effect
def _steady_penetration(tmp_path, spec):
    ex = export_scene(spec, tmp_path)
    model = mujoco.MjModel.from_xml_path(str(ex.scene_xml))
    data = mujoco.MjData(model)
    for _ in range(1500):
        mujoco.mj_step(model, data)
    box, floor = _gid(model, "box_col"), _gid(model, "floor_col")
    dists = [float(data.contact[i].dist) for i in range(data.ncon)
             if {int(data.contact[i].geom1), int(data.contact[i].geom2)} == {box, floor}]
    assert dists, "the box never touched the floor"
    return -min(dists)


def test_stiffer_solimp_reduces_steady_penetration(tmp_path):
    default = _steady_penetration(tmp_path / "d", _spec())
    stiff = _steady_penetration(tmp_path / "s", _spec(contact_solimp=(0.99, 0.999, 0.0001)))
    assert math.isfinite(default) and math.isfinite(stiff)
    assert default > 0.0
    assert stiff < default
