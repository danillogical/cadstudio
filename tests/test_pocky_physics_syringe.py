"""Pocky syringe dispenser physics: assembly, export, frozen acceptance, scenario, smoke, run evidence.

The syringe acceptance reuses the frozen sources and must not drift from them:

* the packet events and checks equal ``acceptance.toml`` except two declared bindings,
  ``bodies`` (the three packet ids) and presentation ``support_bodies`` (the one-piece housing);
* the housing thresholds equal ``s0_acceptance.json``.

The recorded runs ``out/mujoco-syringe/run`` (free housing) and ``run_clamped`` are optional
generated evidence. An absent run directory skips its tests; one that exists but is
incomplete fails loudly. The clamped run passes; the free run fails with one packet crossed,
a lost presentation support and a shoved housing.

Run with: ``uv run --frozen --extra physics pytest tests/test_pocky_physics_syringe.py -q``.
"""
from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

import pytest

pytest.importorskip("mujoco", reason="optional physics extra not installed")

import mujoco  # noqa: E402

from cadkit import cli  # noqa: E402
from cadkit.params import REPO_ROOT  # noqa: E402
from cadkit.physics.scene import export_scene  # noqa: E402
from cadkit.physics.scenario import (  # noqa: E402
    load_acceptance,
    load_acceptance_toml,
    load_scenario,
)
from cadkit.physics.schema import AssemblySpec  # noqa: E402
from projects.pocky import PROJECT  # noqa: E402
from projects.pocky.geometry.syringe import syringe_layout  # noqa: E402
from projects.pocky.params import load_params  # noqa: E402
from projects.pocky.physics.options import load_options  # noqa: E402

PHYS = REPO_ROOT / "projects" / "pocky" / "physics"
FROZEN_TOML = PHYS / "acceptance.toml"
S0_JSON = PHYS / "s0_acceptance.json"
ACCEPTANCE = PHYS / "syringe_dispense3_acceptance.json"
SCENARIO = PHYS / "scenarios" / "syringe_dispense.json"
OPTIONS = PHYS / "options" / "syringe_dispense3.toml"
OPTIONS_CLAMPED = PHYS / "options" / "syringe_dispense3_clamped.toml"
DEFAULT_SCENE_HASH_PREFIX = "2c4bd425c55d9f56"
PACKET_IDS = ("packet", "packet_02", "packet_03")
TIMED_PHASES = ("actuate", "press_hold", "release", "hold")
RUN_ROOT = REPO_ROOT / "out" / "mujoco-syringe"
RUN_FILES = (
    "summary.json", "manifest.json", "scenario.json", "acceptance.lock.json", "trace.csv",
    "contacts.csv", "states.npz", "state_meta.json", "checkpoints.npz", "report.json",
    "report.md", "scene.xml", "assembly_options.lock.toml",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def params():
    return load_params()


@pytest.fixture(scope="module")
def lay(params):
    return syringe_layout(params)


@pytest.fixture(scope="module")
def acceptance():
    return load_acceptance(ACCEPTANCE)


@pytest.fixture(scope="module")
def scenario():
    return load_scenario(SCENARIO)


def _checks(spec) -> dict:
    return {check.name: check for check in spec.checks}


def _events(spec) -> dict:
    return {event.name: event for event in spec.events}


def _bodies(spec) -> dict:
    return {body.body_id: body for body in spec.bodies}


# --------------------------------------------------------------- assembly
def test_default_assembly_has_housing_slider_and_floor(params):
    spec = PROJECT.physics("syringe", params)
    assert isinstance(spec, AssemblySpec)
    assert {b.body_id for b in spec.bodies} == {"housing", "slider", "floor_world"}
    assert spec.actuators == ()


def test_three_packets_add_packet_bodies(params):
    spec = PROJECT.physics_with_options("syringe", params, {"packets": 3})
    ids = [b.body_id for b in spec.bodies]
    assert set(ids) == {"housing", "slider", "floor_world", *PACKET_IDS}
    assert len(ids) == len(set(ids))


def test_slider_joint_covers_the_stroke(params, lay):
    slider = _bodies(PROJECT.physics("syringe", params))["slider"]
    joint = slider.joint
    assert joint.joint_id == "slider_x" and joint.kind == "slide"
    assert joint.axis == (1.0, 0.0, 0.0)
    assert slider.parent == "housing"
    lo, hi = joint.limits
    assert lo <= 0.0 <= hi
    assert hi >= lay.stroke / 1000.0


def test_equivalent_spring_pushes_the_slider_home(params):
    joint = _bodies(PROJECT.physics("syringe", params))["slider"].joint
    spring = joint.spring
    assert spring.stiffness > 0.0
    # Spring force is -k (q - reference): at q = 0 it must point to -X (home).
    force_at_home = -spring.stiffness * (0.0 - spring.reference)
    assert force_at_home < 0.0


def test_button_actuator_adds_pull_on_slider_x(params):
    spec = PROJECT.physics_with_options("syringe", params, {"button_actuator": True})
    assert [a.actuator_id for a in spec.actuators] == ["pull"]
    assert spec.actuators[0].joint_id == "slider_x"
    assert PROJECT.physics_with_options("syringe", params, {}).actuators == ()


def test_chassis_clamped_fixes_the_housing_as_a_diagnostic_fixture(params):
    free = _bodies(PROJECT.physics_with_options("syringe", params, {}))["housing"]
    assert free.fixed_to_world is False
    clamped = _bodies(
        PROJECT.physics_with_options("syringe", params, {"chassis_clamped": True}))["housing"]
    assert clamped.fixed_to_world is True
    assert clamped.fixture == "diagnostic_fixture"


# --------------------------------------------------------------- export
def test_cad_physics_export_passes_fidelity(tmp_path, capsys):
    out = tmp_path / "export"
    with pytest.raises(SystemExit) as exit_info:  # cli.main always ends in sys.exit(code)
        cli.main(["physics", "export", "pocky/syringe", "--out", str(out)])
    captured = capsys.readouterr()
    assert exit_info.value.code == 0, captured.err
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["fidelity"], "export reported no fidelity results"
    for body, result in report["fidelity"].items():
        assert result["ok"] is True, (body, result)


def test_slider_body_carries_the_handle_colliders_and_mass(params, lay, tmp_path):
    from projects.pocky.geometry.syringe import syringe_solids
    from projects.pocky.physics import syringe_colliders as sc

    spec = PROJECT.physics("syringe", params)
    slider = _bodies(spec)["slider"]
    parts = {part.part_id: part for part in slider.parts}
    assert set(parts) == {"slider", "handle"}
    handle_ids = {c.collider_id for c in parts["handle"].colliders}
    assert handle_ids == {c.collider_id for c in sc.handle_colliders(lay)} and handle_ids
    assert all(i.startswith("handle_") for i in handle_ids)
    solids = syringe_solids(params, 0.0)
    expected_kg = (solids["slider"].volume + solids["handle"].volume) * 1.0e-3 \
        * params.material.density_g_cm3 / 1000.0
    summed = sum(part.shape.volume for part in slider.parts) * 1.0e-3 \
        * params.material.density_g_cm3 / 1000.0
    assert summed == pytest.approx(expected_kg, rel=1e-9)
    # The compiled MuJoCo body mass is what the simulation integrates.
    model = export_scene(spec, tmp_path / "scene").model
    assert float(model.body("slider").mass[0]) == pytest.approx(expected_kg, rel=0.01)


def _housing_collider_zmin_mm(body) -> float:
    """Lowest z of the body's axis-aligned box colliders (the leg feet are unrotated boxes)."""
    lows = []
    for part in body.parts:
        for c in part.colliders:
            if c.kind == "box" and c.rot_deg == (0.0, 0.0, 0.0):
                lows.append(c.pos_mm[2] - c.size_mm[2])
    return min(lows)


def test_housing_body_carries_four_leg_parts_with_colliders_reaching_the_table(params, lay):
    from projects.pocky.geometry.syringe import TABLE_Z

    housing = _bodies(PROJECT.physics("syringe", params))["housing"]
    parts = {part.part_id: part for part in housing.parts}
    assert {"housing", "spring", "leg_1", "leg_2", "leg_3", "leg_4"} <= set(parts)
    for n in range(1, 5):
        ids = {c.collider_id for c in parts[f"leg_{n}"].colliders}
        assert ids and all(i.startswith(f"leg_{n}_") for i in ids)
        zmin = min(c.pos_mm[2] - c.size_mm[2] for c in parts[f"leg_{n}"].colliders)
        assert zmin == pytest.approx(TABLE_Z, abs=1e-6), n
    assert _housing_collider_zmin_mm(housing) == pytest.approx(TABLE_Z, abs=1e-6)


def test_compiled_housing_mass_is_housing_plus_four_legs_at_petg_density(params, tmp_path):
    from projects.pocky.geometry.syringe import syringe_solids

    spec = PROJECT.physics("syringe", params)
    solids = syringe_solids(params, 0.0)
    legs = sum(solids[f"leg_{i}"].volume for i in range(1, 5))
    expected_kg = (solids["housing"].volume + legs) * 1.0e-3 * params.material.density_g_cm3 / 1000.0
    model = export_scene(spec, tmp_path / "scene").model
    assert float(model.body("housing").mass[0]) == pytest.approx(expected_kg, rel=0.01)


def test_wedge_uses_flat_packet_frames_and_blade_uses_tilted_ones(params):
    wedge = _bodies(PROJECT.physics_with_options(
        "syringe", params, {"packets": 3, "separator": "wedge"}))
    blade = _bodies(PROJECT.physics_with_options(
        "syringe", params, {"packets": 3, "separator": "blade"}))
    default = _bodies(PROJECT.physics_with_options("syringe", params, {"packets": 3}))
    pitch_min = params.packet.height
    for name in ("packet_02", "packet_03"):
        assert wedge[name].frame.rot_deg == (0.0, 0.0, 0.0), name
        assert wedge[name].frame.pos_mm[:2] == (0.0, 0.0), name
        assert blade[name].frame.rot_deg[1] != 0.0, name
        assert default[name].frame.rot_deg == wedge[name].frame.rot_deg, name
    # Flat stack: packet i sits one packet height (plus a numerical seat clearance) above i-1.
    z2, z3 = wedge["packet_02"].frame.pos_mm[2], wedge["packet_03"].frame.pos_mm[2]
    assert pitch_min <= z2 < pitch_min + 0.1
    assert z3 - z2 == pytest.approx(z2, abs=1e-9)
    assert wedge["packet"].frame.is_identity and blade["packet"].frame.is_identity


def test_wedge_assembly_exports_and_passes_fidelity(params, tmp_path):
    spec = PROJECT.physics_with_options("syringe", params, {"packets": 3, "separator": "wedge"})
    export_scene(spec, tmp_path / "export")
    report = json.loads((tmp_path / "export" / "report.json").read_text(encoding="utf-8"))
    for body, result in report["fidelity"].items():
        assert result["ok"] is True, (body, result["violations"])


def test_hand_keepout_probes_exist_and_pass_on_export(params, tmp_path):
    spec = PROJECT.physics("syringe", params)
    export_scene(spec, tmp_path / "export")
    for body_id in ("housing", "slider"):
        body = _bodies(spec)[body_id]
        assert "hand_keepout" in {probe.probe_id for probe in body.fidelity.probes}, body_id
    report = json.loads((tmp_path / "export" / "report.json").read_text(encoding="utf-8"))
    for body_id in ("housing", "slider"):
        result = report["fidelity"][body_id]
        assert result["ok"] is True, (body_id, result["violations"])
        assert "probe_hand_keepout_min_clearance_mm" in result["metrics"], body_id
        assert result["metrics"]["probe_hand_keepout_min_clearance_mm"] > 0.0


def test_prototype_default_scene_hash_is_unchanged(params, tmp_path):
    result = export_scene(PROJECT.physics("prototype", params), tmp_path / "export")
    assert result.scene_hash.startswith(DEFAULT_SCENE_HASH_PREFIX)


# --------------------------------------------------------------- frozen acceptance
def test_packet_events_equal_the_frozen_toml_except_the_declared_bindings(acceptance):
    frozen = load_acceptance_toml(FROZEN_TOML)
    assert set(_events(acceptance)) == {"packet_exit", "packet_presentation"}
    for name, event in _events(acceptance).items():
        got, want = event.to_dict(), _events(frozen)[name].to_dict()
        assert got.pop("bodies") == list(PACKET_IDS), name
        want.pop("bodies")
        if name == "packet_presentation":
            assert got.pop("support_bodies") == ["housing"]
            want.pop("support_bodies")
        assert got == want, name


def test_packet_checks_equal_the_frozen_toml(acceptance):
    frozen = load_acceptance_toml(FROZEN_TOML)
    for name in ("exactly_one_packet", "pickup_ready"):
        assert _checks(acceptance)[name].to_dict() == _checks(frozen)[name].to_dict(), name


def test_housing_checks_carry_the_s0_thresholds(acceptance):
    s0 = _checks(load_acceptance(S0_JSON))
    got = _checks(acceptance)
    for phase in TIMED_PHASES:
        pose = got[f"housing_pose_retained_{phase}"].to_dict()
        drop = got[f"housing_drop_{phase}"].to_dict()
        assert pose["window"] == "max_over_phase" and drop["window"] == "max_over_phase"
        assert pose["phase"] == phase and drop["to_phase"] == phase
        want_pose = s0["body_pose_retained"].to_dict()
        want_drop = s0["body_drop"].to_dict()
        for key in ("max", "max_rotation_rad"):
            assert pose[key] == want_pose[key], (phase, key)
        for key in ("lower", "upper", "axis", "frame"):
            assert drop[key] == want_drop[key], (phase, key)
    assert got["penetration"].to_dict() == s0["penetration"].to_dict()
    assert acceptance.validity.to_dict() == load_acceptance(S0_JSON).validity.to_dict()


def test_acceptance_declares_exactly_the_expected_checks(acceptance):
    expected = {"exactly_one_packet", "pickup_ready", "penetration"}
    for phase in TIMED_PHASES:
        expected |= {f"housing_pose_retained_{phase}", f"housing_drop_{phase}"}
    assert [c.name for c in acceptance.checks].count("penetration") == 1
    assert set(_checks(acceptance)) == expected and len(acceptance.checks) == len(expected)


def test_options_files_load_and_match_the_acceptance_bodies(acceptance):
    free = load_options(tomllib.loads(OPTIONS.read_text(encoding="utf-8")))
    clamped = load_options(tomllib.loads(OPTIONS_CLAMPED.read_text(encoding="utf-8")))
    assert free.packets == clamped.packets == len(PACKET_IDS)
    assert free.button_actuator and clamped.button_actuator
    assert clamped.chassis_clamped and not free.chassis_clamped


# --------------------------------------------------------------- scenario
def test_scenario_phases_match_the_event_windows(scenario, acceptance, params):
    order = [phase.name for phase in scenario.phases]
    assert order[0] == "reset"
    assert set(TIMED_PHASES) <= set(order)
    for event in acceptance.events:
        assert order.index(event.window_from) <= order.index(event.window_to), event.name
    presentation = _events(acceptance)["packet_presentation"]
    for field in ("release_phase", "dwell_from", "dwell_to"):
        assert getattr(presentation, field) in order, field
    assert order.index(presentation.window_from) <= order.index(presentation.release_phase)
    assert order.index(presentation.release_phase) <= order.index(presentation.dwell_from)
    assert order.index(presentation.dwell_from) <= order.index(presentation.dwell_to)
    assert order.index(presentation.dwell_to) <= order.index(presentation.window_to)
    for check in acceptance.checks:
        for field in ("phase", "from_phase", "to_phase"):
            value = getattr(check, field)
            if value is not None:
                assert value == "initial" or value in order, (check.name, field)
    hold = next(phase for phase in scenario.phases if phase.name == "hold")
    assert hold.duration_s >= presentation.dwell_min_s


def test_scenario_drives_the_pull_actuator_within_its_bound(scenario, params):
    spec = PROJECT.physics_with_options("syringe", params, {"button_actuator": True})
    pull = spec.actuators[0]
    pulls = [ph for ph in scenario.phases if ph.kind == "actuate"]
    assert pulls and all(ph.actuator == pull.actuator_id for ph in pulls)
    for ph in pulls:
        for effort in (ph.effort, ph.effort_end):
            if effort is not None:
                assert abs(effort) <= pull.max_effort
    assert dict(scenario.reset_phase.initial) == {"slider_x": 0.0}
    assert scenario.timestep_s == pytest.approx(
        load_options(tomllib.loads(OPTIONS.read_text(encoding="utf-8"))).timestep_s)


# --------------------------------------------------------------- smoke
def test_short_smoke_has_no_penetration_and_the_slider_stays_home(params, tmp_path):
    # The run's validated numerics (62.5 us step, 0.25 ms contact compliance), zero input:
    # at the 1 ms / 2 ms defaults the soft contacts alone show ~1.7e-5 m, which is not a fault.
    spec = PROJECT.physics_with_options(
        "syringe", params, tomllib.loads(OPTIONS.read_text(encoding="utf-8")))
    assert PACKET_IDS[-1] in _bodies(spec)
    export = export_scene(spec, tmp_path / "scene")
    model = export.model
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    joint = model.joint("slider_x")
    worst = 0.0
    for _ in range(200):
        mujoco.mj_step(model, data)
        for i in range(data.ncon):
            worst = max(worst, -float(data.contact[i].dist))
    assert worst <= 1.0e-6, f"peak penetration {worst:.3e} m"
    # Home: the preloaded spring holds the slider on the rear stop, 0.5 mm guard below q = 0.
    q = float(data.qpos[joint.qposadr[0]])
    assert q <= 0.0
    assert q == pytest.approx(float(model.jnt_range[joint.id][0]), abs=2.0e-5)
    assert abs(float(data.qvel[joint.dofadr[0]])) < 1.0e-3


# --------------------------------------------------------------- recorded runs (optional)
def _load_run(name: str) -> tuple[Path, dict]:
    """Skip only when the run directory is absent; an incomplete directory fails loudly."""
    run = RUN_ROOT / name
    if not run.is_symlink() and not run.exists():
        pytest.skip(f"optional generated evidence absent: {run} does not exist")
    assert run.is_dir(), f"broken evidence: {run} is not a directory"
    missing = [f for f in RUN_FILES if not (run / f).is_file()]
    assert not missing, f"broken evidence: {run} lacks {missing}"
    return run, json.loads((run / "summary.json").read_text(encoding="utf-8"))


def _by_name(items) -> dict:
    return {item["name"]: item for item in items}


@pytest.mark.parametrize("name", ["run", "run_clamped"])
def test_recorded_run_binds_to_the_current_files_and_is_valid(name, scenario, acceptance):
    _, summary = _load_run(name)
    assert summary["scenario"]["hash"] == scenario.hash()
    assert summary["scenario"]["sha256"] == _sha256(SCENARIO)
    assert summary["acceptance"]["hash"] == acceptance.hash()
    assert summary["acceptance"]["sha256"] == _sha256(ACCEPTANCE)
    assert summary["validity"]["ok"] is True
    assert summary["validity"]["reasons"] == []
    assert summary["metrics"]["peak_penetration_m"] < 2.0e-4
    assert summary["telemetry"]["stopped"] is False


def test_clamped_run_passes_with_one_packet_presented():
    _, summary = _load_run("run_clamped")
    assert summary["status"] == "PASS"
    checks = _by_name(summary["checks"])
    assert checks["exactly_one_packet"]["status"] == "PASS"
    assert checks["pickup_ready"]["status"] == "PASS"
    events = _by_name(summary["events"])
    assert events["packet_exit"]["distinct_bodies_crossed"] == 1
    assert events["packet_presentation"]["verdict_code"] == "supported_presentation"


def test_free_run_fails_with_v2_evidence():
    # v2: the free housing still FAILs, but not by a double feed: exactly one packet crosses
    # and the failures are the lost presentation support and the housing shoved at release.
    _, summary = _load_run("run")
    assert summary["status"] == "FAIL"
    assert summary["validity"]["ok"] is True
    checks = _by_name(summary["checks"])
    assert checks["exactly_one_packet"]["status"] == "PASS"
    assert checks["pickup_ready"]["status"] == "FAIL"
    assert checks["housing_pose_retained_release"]["status"] == "FAIL"
    events = _by_name(summary["events"])
    exit_event = events["packet_exit"]
    assert exit_event["distinct_bodies_crossed"] == 1
    crossed = [b for b, v in exit_event["bodies"].items() if v["crossed"]]
    assert crossed == ["packet"]
    assert events["packet_presentation"]["verdict_code"] == "support_lost"
