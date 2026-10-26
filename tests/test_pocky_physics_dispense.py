"""Pocky dispense tests: frozen documents, scenario, options, assembly and the recorded run.

The dispense acceptance reuses two frozen sources and must not drift from either:

* the packet events and checks come verbatim from ``acceptance.toml``;
* the housing thresholds come from ``s0_acceptance.json``, with the per-phase pose and drop
  checks evaluated at ``window = "max_over_phase"`` in each timed phase after the settle.

The recorded run ``out/mujoco-dispense/run`` is optional generated evidence. A clean checkout
has no ``out/``, so that absence skips the evidence tests; a run directory that exists but is
incomplete fails loudly. The run is expected to be valid and to FAIL acceptance: the packet
barely touches the exit plane and is not presented.

Run with the optional physics extra:
``uv run --frozen --extra physics pytest tests/test_pocky_physics_dispense.py -q``.
"""
from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

import pytest

pytest.importorskip("mujoco", reason="optional physics extra not installed")

from cadkit.params import REPO_ROOT  # noqa: E402
from cadkit.physics.scene import export_scene  # noqa: E402
from cadkit.physics.scenario import (  # noqa: E402
    load_acceptance,
    load_acceptance_toml,
    load_scenario,
)
from projects.pocky import PROJECT  # noqa: E402
from projects.pocky.params import load_params  # noqa: E402
from projects.pocky.physics.options import load_options  # noqa: E402

PHYS = REPO_ROOT / "projects" / "pocky" / "physics"
FROZEN_TOML = PHYS / "acceptance.toml"
FROZEN_TOML_SHA256 = "518a45ffc4592ca602be4c33c59681038e43dedaa15b688312202c3a57ff6ca2"
S0_JSON = PHYS / "s0_acceptance.json"
S0_JSON_SHA256 = "150c037b2e985dac46b66670c46291872d9e0cc9d287d7946eadf4d9185b5a3a"
DISPENSE_ACCEPTANCE = PHYS / "dispense_acceptance.json"
DISPENSE_SCENARIO = PHYS / "scenarios" / "dispense.json"
DISPENSE_OPTIONS = PHYS / "options" / "dispense.toml"
DEFAULT_SCENE_HASH_PREFIX = "2c4bd425c55d9f56"
RUN_DIR = REPO_ROOT / "out" / "mujoco-dispense" / "run"
RUN_FILES = (
    "summary.json", "manifest.json", "scenario.json", "acceptance.lock.json", "trace.csv",
    "contacts.csv", "states.npz", "state_meta.json", "checkpoints.npz", "report.json",
    "report.md", "scene.xml", "assembly_options.lock.toml",
)
TIMED_PHASES = ("actuate", "press_hold", "release", "hold")
DT_S = 6.25e-5


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def params():
    return load_params()


@pytest.fixture(scope="module")
def dispense():
    return load_acceptance(DISPENSE_ACCEPTANCE)


@pytest.fixture(scope="module")
def scenario():
    return load_scenario(DISPENSE_SCENARIO)


def _checks(spec) -> dict:
    return {check.name: check for check in spec.checks}


def _events(spec) -> dict:
    return {event.name: event for event in spec.events}


# --------------------------------------------------------------- frozen sources
def test_frozen_source_files_are_unchanged():
    assert _sha256(FROZEN_TOML) == FROZEN_TOML_SHA256
    assert _sha256(S0_JSON) == S0_JSON_SHA256


def test_packet_events_equal_the_frozen_acceptance_toml(dispense):
    frozen = load_acceptance_toml(FROZEN_TOML)
    for name in ("packet_exit", "packet_presentation"):
        assert _events(dispense)[name].to_dict() == _events(frozen)[name].to_dict(), name
    assert set(_events(dispense)) == {"packet_exit", "packet_presentation"}


def test_packet_checks_equal_the_frozen_acceptance_toml(dispense):
    frozen = load_acceptance_toml(FROZEN_TOML)
    for name in ("exactly_one_packet", "pickup_ready"):
        assert _checks(dispense)[name].to_dict() == _checks(frozen)[name].to_dict(), name


def test_housing_checks_carry_the_s0_numbers(dispense):
    s0 = load_acceptance(S0_JSON)
    got, ref = _checks(dispense), _checks(s0)
    for phase in TIMED_PHASES:
        pose = got[f"body_pose_retained_{phase}"].to_dict()
        drop = got[f"body_drop_{phase}"].to_dict()
        assert pose["window"] == "max_over_phase" and drop["window"] == "max_over_phase"
        assert pose.pop("phase") == phase
        assert drop.pop("to_phase") == phase
        pose.pop("name"), drop.pop("name")
        want_pose = ref["body_pose_retained"].to_dict()
        want_drop = ref["body_drop"].to_dict()
        for want in (want_pose, want_drop):
            want.pop("name")
        want_pose.pop("phase"), want_drop.pop("to_phase")
        assert pose == want_pose, phase
        assert drop == want_drop, phase
    for name in ("body_on_pusher", "body_on_rod", "body_on_crank", "penetration"):
        assert got[name].to_dict() == ref[name].to_dict(), name


def test_dispense_declares_exactly_the_expected_checks(dispense):
    expected = {"exactly_one_packet", "pickup_ready", "body_on_pusher", "body_on_rod",
                "body_on_crank", "penetration"}
    for phase in TIMED_PHASES:
        expected |= {f"body_pose_retained_{phase}", f"body_drop_{phase}"}
    assert set(_checks(dispense)) == expected
    assert len(dispense.checks) == len(expected)


def test_validity_block_equals_s0(dispense):
    assert dispense.validity.to_dict() == load_acceptance(S0_JSON).validity.to_dict()


# --------------------------------------------------------------- scenario
def test_scenario_loads_and_declares_the_press_sequence(scenario):
    assert scenario.scenario_id == "pocky_dispense"
    names = [phase.name for phase in scenario.phases]
    assert names[0] == "reset"
    timed = names[1:]
    assert timed == ["settle", "actuate", "press_hold", "release", "hold"]
    phases = {phase.name: phase for phase in scenario.phases}
    assert phases["actuate"].kind == "actuate"
    assert phases["actuate"].actuator == "button"
    assert phases["actuate"].effort == 0.0
    assert phases["actuate"].effort_end == -25.0
    assert phases["press_hold"].kind == "actuate"
    assert phases["release"].kind == "release"
    assert phases["hold"].kind == "hold"


def test_scenario_phase_order_is_compatible_with_the_events(scenario, dispense):
    order = [phase.name for phase in scenario.phases]
    for event in dispense.events:
        assert order.index(event.window_from) <= order.index(event.window_to), event.name
        for field in ("release_phase", "dwell_from", "dwell_to"):
            value = getattr(event, field)
            if value is not None:
                assert value in order, (event.name, field)
    presentation = _events(dispense)["packet_presentation"]
    assert order.index(presentation.window_from) <= order.index(presentation.release_phase)
    assert order.index(presentation.dwell_from) <= order.index(presentation.dwell_to)
    assert order.index(presentation.release_phase) <= order.index(presentation.dwell_from)
    assert order.index(presentation.dwell_to) <= order.index(presentation.window_to)
    # Every phase a check names must exist in the scenario.
    for check in dispense.checks:
        for field in ("phase", "from_phase", "to_phase"):
            value = getattr(check, field)
            if value is not None:
                assert value == "initial" or value in order, (check.name, field)


def test_hold_covers_the_presentation_dwell(scenario, dispense):
    hold = next(phase for phase in scenario.phases if phase.name == "hold")
    assert hold.duration_s >= _events(dispense)["packet_presentation"].dwell_min_s


def test_timestep_and_budgets_cover_every_step(scenario):
    assert scenario.timestep_s == DT_S
    steps = sum(round(phase.duration_s / DT_S) for phase in scenario.timed_phases)
    sim_time = steps * DT_S
    budgets = scenario.budgets
    assert budgets.max_steps >= steps
    assert budgets.max_sim_time_s >= sim_time
    every = round(scenario.sampling_interval_s / DT_S)
    assert every * DT_S == pytest.approx(scenario.sampling_interval_s)
    assert budgets.max_trace_rows >= steps // every + len(scenario.phases) + 1
    assert budgets.max_state_rows is not None and budgets.max_state_rows >= steps + 1


# --------------------------------------------------------------- options and assembly
def _options_table() -> dict:
    return tomllib.loads(DISPENSE_OPTIONS.read_text(encoding="utf-8"))


def test_options_load_strictly():
    options = load_options(_options_table())
    assert options.packets == 1
    assert options.button_actuator is True
    assert options.timestep_s == DT_S


def test_assembly_has_one_free_packet_and_the_button_on_rod_x(params):
    default = PROJECT.physics_with_options("prototype", params, {})
    spec = PROJECT.physics_with_options("prototype", params, _options_table())

    def free(assembly) -> set[str]:
        return {b.body_id for b in assembly.bodies if b.parent is None and not b.fixed_to_world}

    assert free(spec) - free(default) == {"packet"}
    assert free(default) - free(spec) == set()
    assert [b.body_id for b in spec.bodies].count("packet") == 1
    assert len(spec.actuators) == 1
    button = spec.actuators[0]
    assert button.actuator_id == "button"
    assert button.joint_id == "rod_x"
    assert button.max_effort == 25.0


def test_packet_identity_matches_the_event_bodies(dispense):
    for event in dispense.events:
        assert event.bodies == ("packet",), event.name


def test_default_scene_hash_is_unchanged(params, tmp_path):
    result = export_scene(PROJECT.physics("prototype", params), tmp_path / "export")
    assert result.scene_hash.startswith(DEFAULT_SCENE_HASH_PREFIX)


# --------------------------------------------------------------- recorded run (optional)
def _require_generated_evidence() -> dict:
    """Skip only when the run directory is absent; an incomplete directory fails loudly."""
    if not RUN_DIR.is_symlink() and not RUN_DIR.exists():
        pytest.skip(f"optional generated evidence absent: {RUN_DIR} does not exist")
    assert RUN_DIR.is_dir(), f"broken evidence: {RUN_DIR} is not a directory"
    missing = [name for name in RUN_FILES if not (RUN_DIR / name).is_file()]
    assert not missing, f"broken evidence: {RUN_DIR} lacks {missing}"
    return json.loads((RUN_DIR / "summary.json").read_text(encoding="utf-8"))


def test_recorded_run_binds_to_the_current_scenario_and_acceptance(scenario, dispense):
    summary = _require_generated_evidence()
    assert summary["scenario"]["hash"] == scenario.hash()
    assert summary["scenario"]["sha256"] == _sha256(DISPENSE_SCENARIO)
    assert summary["acceptance"]["hash"] == dispense.hash()
    assert summary["acceptance"]["sha256"] == _sha256(DISPENSE_ACCEPTANCE)
    assert summary["timestep_s"] == DT_S


def test_recorded_run_is_numerically_valid():
    summary = _require_generated_evidence()
    assert summary["validity"]["ok"] is True
    assert summary["validity"]["reasons"] == []
    assert summary["metrics"]["peak_penetration_m"] < 2.0e-4
    assert summary["metrics"]["initial_rejected"] is False
    assert summary["telemetry"]["stopped"] is False


def test_recorded_run_fails_acceptance_because_the_packet_is_not_presented():
    summary = _require_generated_evidence()
    assert summary["status"] == "FAIL"
    checks = {c["name"]: c for c in summary["checks"]}
    assert checks["pickup_ready"]["status"] == "FAIL"
    events = {e["name"]: e for e in summary["events"]}
    assert events["packet_presentation"]["verdict_code"] == "support_lost"
    for phase in TIMED_PHASES:
        assert checks[f"body_pose_retained_{phase}"]["status"] == "FAIL", phase
        assert checks[f"body_drop_{phase}"]["status"] == "FAIL", phase


def test_recorded_run_counts_one_packet_that_barely_touched_the_exit_plane():
    summary = _require_generated_evidence()
    checks = {c["name"]: c for c in summary["checks"]}
    assert checks["exactly_one_packet"]["status"] == "PASS"
    exit_event = next(e for e in summary["events"] if e["name"] == "packet_exit")
    assert exit_event["distinct_bodies_crossed"] == 1
    crossings = exit_event["crossings"]
    assert [c["body_id"] for c in crossings] == ["packet"]
    # The leading edge crosses by micrometres only, which is why presentation fails.
    assert 0.0 <= crossings[0]["protrusion_m"] < 1.0e-3
