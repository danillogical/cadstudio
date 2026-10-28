"""M4c acceptance schema and reference validation."""
from __future__ import annotations

import json
import math

import pytest

from cadkit.physics.evaluate import resolve_references
from cadkit.physics.scenario import (
    BudgetSpec,
    PhaseSpec,
    ScenarioError,
    ScenarioSpec,
    acceptance_from_text,
    acceptance_from_toml_text,
    build_fixture,
    canonical_json,
)


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
