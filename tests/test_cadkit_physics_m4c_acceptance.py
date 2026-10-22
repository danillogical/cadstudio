"""M4c acceptance schema, frozen Pocky configuration and reference validation."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from cadkit.params import REPO_ROOT
from cadkit.physics.evaluate import resolve_references
from cadkit.physics.scenario import (
    BudgetSpec,
    PhaseSpec,
    ScenarioError,
    ScenarioSpec,
    acceptance_from_text,
    acceptance_from_toml_text,
    acceptance_text_matches,
    build_fixture,
    canonical_json,
    load_acceptance_toml,
)

POCKY_ACCEPTANCE = REPO_ROOT / "projects" / "pocky" / "physics" / "acceptance.toml"
POCKY_SEMANTIC_HASH = "5109a0a4cb5ed70c3605ac9b1148eda58cae0a05ba18725807d645e474d216d3"


def test_pocky_acceptance_toml_is_frozen_provisional_and_complete():
    acceptance = load_acceptance_toml(POCKY_ACCEPTANCE)
    assert acceptance.acceptance_id == "pocky_provisional_m4c"
    assert acceptance.hash() == POCKY_SEMANTIC_HASH
    notes = acceptance.notes
    assert "NOT bench measurements" in notes
    assert "165 x 55 x 5.2" in notes
    assert "housing stability" in notes
    assert "0.2 mm" in notes
    assert "candidate identity set" in notes
    assert "undeclared body ID" in notes
    events = {event.name: event for event in acceptance.events}
    exit_event = events["packet_exit"]
    presentation = events["packet_presentation"]
    assert exit_event.kind == "exit_crossing"
    assert exit_event.bodies == ("packet",)
    assert exit_event.plane.point_m == (0.088, 0.0, 0.0)
    assert exit_event.plane.normal == (1.0, 0.0, 0.0)
    assert exit_event.plane.direction == 1
    assert presentation.kind == "supported_presentation"
    assert presentation.bodies == ("packet",)
    assert presentation.access_plane.point_m == (0.106, 0.0, 0.0)
    assert presentation.object_half_extents_m == (0.0825, 0.0275, 0.0026)
    assert presentation.min_protrusion_m == 0.030
    assert presentation.target_protrusion_m == 0.040
    assert presentation.min_accessible_m == 0.010
    assert presentation.min_accessible_m != 0.015  # superseded architecture §16 proposal
    assert presentation.dwell_min_s == 0.5
    assert presentation.protrusion_change_max_m == 0.001
    assert presentation.support_bodies == ("lip", "body")
    assert presentation.min_support_load_fraction == 0.6
    assert presentation.max_terminal_speed_m_s == 0.01
    assert presentation.fallout_drop_m == 0.02
    assert presentation.release_phase == "release"
    assert presentation.window_from == "actuate"
    assert presentation.window_to == "hold"
    checks = {check.name: check for check in acceptance.checks}
    assert checks["exactly_one_packet"].kind == "event_count"
    assert checks["exactly_one_packet"].event == "packet_exit"
    assert checks["exactly_one_packet"].expected == 1
    assert checks["exactly_one_packet"].tolerance == 0
    assert checks["pickup_ready"].kind == "event_verdict"
    assert checks["pickup_ready"].event == "packet_presentation"


def test_toml_source_forces_a_canonical_json_lock_and_keeps_the_same_hash():
    acceptance = load_acceptance_toml(POCKY_ACCEPTANCE)
    assert acceptance_text_matches(acceptance, acceptance.source_text) is False
    canonical = canonical_json(acceptance.to_dict())
    assert acceptance_text_matches(acceptance, canonical) is True
    reparsed = acceptance_from_text(canonical)
    assert reparsed.hash() == acceptance.hash()
    assert reparsed.events[1].min_protrusion_m == 0.030
    assert reparsed.notes == acceptance.notes


def test_toml_loader_rejects_unknown_fields_duplicate_events_and_nonfinite_numbers():
    base = """
schema_version = "m4a-1"
acceptance_id = "a"
[[checks]]
name = "p"
kind = "penetration_bound"
max = 0.01
units = "m"
"""
    with pytest.raises(ScenarioError, match="unknown field"):
        acceptance_from_toml_text(base + "\nunknown = 1\n")
    duplicate = base + """
[[events]]
name = "x"
kind = "exit_crossing"
bodies = ["b"]
object_half_extents_m = [0.1, 0.1, 0.1]
window_from = "a1"
window_to = "a2"
[events.plane]
point_m = [0, 0, 0]
normal = [1, 0, 0]
[[events]]
name = "x"
kind = "exit_crossing"
bodies = ["b"]
object_half_extents_m = [0.1, 0.1, 0.1]
window_from = "a1"
window_to = "a2"
[events.plane]
point_m = [0, 0, 0]
normal = [1, 0, 0]
"""
    with pytest.raises(ScenarioError, match="event names must be unique"):
        acceptance_from_toml_text(duplicate)
    nonfinite = base.replace("max = 0.01", "max = nan")
    with pytest.raises(ScenarioError, match="finite"):
        acceptance_from_toml_text(nonfinite)


def _scenario_and_fixture():
    scenario = ScenarioSpec(
        "schema", "presentation_aperture", 0,
        (PhaseSpec("reset", "reset", initial=(("pusher_slide", 0.0),)),
         PhaseSpec("settle", "settle", duration_s=0.1),
         PhaseSpec("actuate", "actuate", duration_s=0.1,
                   actuator="push", effort=1.0),
         PhaseSpec("release", "release", duration_s=0.1),
         PhaseSpec("hold", "hold", duration_s=0.1)),
        0.001, 0.002, BudgetSpec(1000, 2.0, 1000))
    return scenario, build_fixture("presentation_aperture")


def _acceptance(events, checks):
    doc = {"schema_version": "m4a-1", "acceptance_id": "schema",
           "events": events, "checks": checks}
    return acceptance_from_text(json.dumps(doc))


def _exit_event(**overrides):
    event = {
        "name": "exit", "kind": "exit_crossing", "bodies": ["packet"],
        "plane": {"point_m": [0, 0, 0], "normal": [1, 0, 0], "direction": 1},
        "object_half_extents_m": [0.05, 0.018, 0.004],
        "window_from": "actuate", "window_to": "hold",
    }
    event.update(overrides)
    return event


def _presentation_event(**overrides):
    event = {
        "name": "presentation", "kind": "supported_presentation",
        "bodies": ["packet"],
        "plane": {"point_m": [0, 0, 0], "normal": [1, 0, 0], "direction": 1},
        "access_plane": {"point_m": [0.018, 0, 0], "normal": [1, 0, 0],
                         "direction": 1},
        "object_half_extents_m": [0.05, 0.018, 0.004],
        "window_from": "actuate", "window_to": "hold",
        "release_phase": "release", "dwell_from": "release", "dwell_to": "hold",
        "min_protrusion_m": 0.03, "min_accessible_m": 0.01, "dwell_min_s": 0.5,
        "protrusion_change_max_m": 0.001, "support_bodies": ["housing"],
        "min_support_load_fraction": 0.6, "support_hull_margin_m": 0.001,
        "support_hull_min_area_m2": 0.00001,
        "support_degeneracy_radius_m": 0.002,
        "max_terminal_speed_m_s": 0.02,
        "bounds_m": {"x": [-0.15, 0.15], "y": [-0.05, 0.05],
                     "z": [-0.02, 0.05]},
        "fallout_drop_m": 0.02,
    }
    event.update(overrides)
    return event


def test_event_references_and_phase_ordering_are_rejected_before_a_run():
    scenario, spec = _scenario_and_fixture()
    check = {"name": "n", "kind": "event_count", "event": "exit",
             "expected": 1, "tolerance": 0, "units": "count"}
    resolve_references(scenario, _acceptance([_exit_event()], [check]), spec)

    with pytest.raises(ScenarioError, match="release phase"):
        bad = _presentation_event(release_phase="hold")
        resolve_references(scenario, _acceptance([bad], [
            {"name": "v", "kind": "event_verdict", "event": "presentation",
             "units": "state"}]), spec)

    with pytest.raises(ScenarioError, match="must precede"):
        bad = _exit_event(window_from="hold", window_to="actuate")
        resolve_references(scenario, _acceptance([bad], [check]), spec)

    with pytest.raises(ScenarioError, match="unknown event"):
        resolve_references(scenario, _acceptance([_exit_event()], [
            dict(check, event="missing")]), spec)

    with pytest.raises(ScenarioError, match="requires an exit_crossing"):
        resolve_references(scenario, _acceptance(
            [_presentation_event()], [
                {"name": "n", "kind": "event_count", "event": "presentation",
                 "expected": 1, "tolerance": 0, "units": "count"}]), spec)

    with pytest.raises(ScenarioError, match="fixed to the world"):
        resolve_references(scenario, _acceptance(
            [_exit_event(bodies=["housing"])],
            [dict(check, event="exit")]), spec)


def test_tilted_plane_normal_round_trips_through_the_canonical_lock():
    event = _exit_event(
        plane={"point_m": [0, 0, 0], "normal": [1.0, 1.0, 0.0], "direction": 1})
    acceptance = _acceptance([event], [
        {"name": "n", "kind": "event_count", "event": "exit",
         "expected": 1, "tolerance": 0, "units": "count"}])
    canonical = canonical_json(acceptance.to_dict())
    reparsed = acceptance_from_text(canonical)
    assert reparsed.hash() == acceptance.hash()
    plane = reparsed.events[0].plane
    assert plane.normal == (1.0, 1.0, 0.0)
    assert math.isclose(math.sqrt(sum(v * v for v in plane.unit_normal)), 1.0)


def test_dwell_window_cannot_span_a_later_actuation():
    scenario = ScenarioSpec(
        "schema_actuation", "presentation_aperture", 0,
        (PhaseSpec("reset", "reset", initial=(("pusher_slide", 0.0),)),
         PhaseSpec("settle", "settle", duration_s=0.1),
         PhaseSpec("actuate", "actuate", duration_s=0.1,
                   actuator="push", effort=1.0),
         PhaseSpec("release", "release", duration_s=0.1),
         PhaseSpec("push2", "actuate", duration_s=0.1,
                   actuator="push", effort=1.0),
         PhaseSpec("hold", "hold", duration_s=0.1)),
        0.001, 0.002, BudgetSpec(1000, 2.0, 1000))
    _, spec = _scenario_and_fixture()
    with pytest.raises(ScenarioError, match="spans an actuate phase"):
        resolve_references(scenario, _acceptance([_presentation_event()], [
            {"name": "v", "kind": "event_verdict", "event": "presentation",
             "units": "state"}]), spec)


def test_event_schema_rejects_presentation_fields_on_an_exit_event():
    with pytest.raises(ScenarioError, match="presentation-only"):
        acceptance_from_text(json.dumps({
            "schema_version": "m4a-1", "acceptance_id": "bad",
            "events": [_exit_event(min_protrusion_m=0.03)],
            "checks": [{"name": "n", "kind": "event_count", "event": "exit",
                        "expected": 1, "tolerance": 0, "units": "count"}],
        }))
