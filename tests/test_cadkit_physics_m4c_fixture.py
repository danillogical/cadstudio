"""Real MuJoCo presentation-aperture fixture, negatives and replay (M4c).

The fixture is independent of the Pocky project: a fixed multipart channel with an open mouth
and a shelf, one or two free rigid boxes, and a bounded damped pusher. The positive run is a
real supported partial presentation after zero-input release, not a scripted trajectory.
"""
from __future__ import annotations

import json
import math
from dataclasses import replace
from unittest.mock import patch

import numpy as np
import pytest

from cadkit.physics.events import EventTracker
from cadkit.physics.replay import replay_run
from cadkit.physics.runner import run_assembly
from cadkit.physics.scenario import (
    BudgetSpec,
    PhaseSpec,
    ScenarioError,
    ScenarioSpec,
    acceptance_from_text,
    build_fixture,
)
from cadkit.physics.telemetry import TelemetryRecorder

pytest.importorskip("mujoco")
import mujoco  # noqa: E402


def scenario(effort=2.0):
    return ScenarioSpec(
        "m4c_presentation_positive", "presentation_aperture", 11,
        (PhaseSpec("reset", "reset", initial=(("pusher_slide", 0.0),)),
         PhaseSpec("settle", "settle", duration_s=0.5),
         PhaseSpec("actuate", "actuate", duration_s=2.0,
                   actuator="push", effort=effort),
         PhaseSpec("release", "release", duration_s=0.4),
         PhaseSpec("hold", "hold", duration_s=1.5)),
        0.001, 0.002, BudgetSpec(7000, 8.0, 7000))


def acceptance_doc(bodies=("packet",), extents=(0.05, 0.018, 0.004),
                   max_speed=2.0):
    return {
        "schema_version": "m4a-1",
        "acceptance_id": "m4c_presentation_acceptance",
        "notes": "Provisional generic fixture acceptance for M4c; not a product criterion.",
        "validity": {"max_penetration_m": 0.002, "max_speed_m_s": max_speed},
        "events": [
            {"name": "packet_exit", "kind": "exit_crossing",
             "bodies": list(bodies),
             "plane": {"point_m": [0.0, 0.0, 0.0],
                       "normal": [1.0, 0.0, 0.0], "direction": 1},
             "object_half_extents_m": list(extents),
             "window_from": "actuate", "window_to": "hold"},
            {"name": "packet_presentation", "kind": "supported_presentation",
             "bodies": list(bodies),
             "plane": {"point_m": [0.0, 0.0, 0.0],
                       "normal": [1.0, 0.0, 0.0], "direction": 1},
             "access_plane": {"point_m": [0.018, 0.0, 0.0],
                              "normal": [1.0, 0.0, 0.0], "direction": 1},
             "object_half_extents_m": list(extents),
             "window_from": "actuate", "window_to": "hold",
             "release_phase": "release", "dwell_from": "release",
             "dwell_to": "hold",
             "min_protrusion_m": 0.030, "target_protrusion_m": 0.040,
             "min_accessible_m": 0.010, "dwell_min_s": 0.5,
             "protrusion_change_max_m": 0.001,
             "support_bodies": ["housing"],
             "min_support_load_fraction": 0.6,
             "support_hull_margin_m": 0.001,
             "support_hull_min_area_m2": 1.0e-5,
             "support_degeneracy_radius_m": 0.002,
             "max_terminal_speed_m_s": 0.02,
             "bounds_m": {"x": [-0.15, 0.15], "y": [-0.05, 0.05],
                          "z": [-0.02, 0.05]},
             "fallout_drop_m": 0.02},
        ],
        "checks": [
            {"name": "exactly_one", "kind": "event_count",
             "event": "packet_exit", "expected": 1, "tolerance": 0,
             "units": "count"},
            {"name": "supported_pickup", "kind": "event_verdict",
             "event": "packet_presentation", "units": "state"},
        ],
    }


def acceptance(bodies=("packet",), extents=(0.05, 0.018, 0.004), max_speed=2.0):
    return acceptance_from_text(
        json.dumps(acceptance_doc(bodies, extents, max_speed)))


def run_case(tmp_path, name, spec, *, effort=2.0, bodies=("packet",),
             extents=(0.05, 0.018, 0.004), max_speed=2.0):
    out = tmp_path / name
    summary = run_assembly(spec, scenario(effort),
                           acceptance(bodies, extents, max_speed), out)
    return summary, out


def test_real_positive_is_supported_partial_presentation(tmp_path):
    summary, out = run_case(tmp_path, "positive", build_fixture("presentation_aperture"))
    assert summary["status"] == "PASS", summary.get("detail")
    assert summary["validity"]["ok"] is True
    exit_event = next(e for e in summary["events"] if e["name"] == "packet_exit")
    presentation = next(e for e in summary["events"]
                        if e["name"] == "packet_presentation")
    assert exit_event["distinct_bodies_crossed"] == 1
    assert exit_event["crossings"][0]["body_id"] == "packet"
    assert presentation["status"] == "PASS"
    assert presentation["verdict_code"] == "supported_presentation"
    assert presentation["evidence_complete"] is True
    assert presentation["release_zero_ok"] is True
    assert presentation["release_zero_checked_samples"] > 0
    assert presentation["release_zero_violation"] is None
    dwell = presentation["dwell"]
    assert dwell["duration_s"] >= 0.5
    assert dwell["change_m"] <= 0.001
    assert dwell["protrusion_min_m"] >= 0.030
    assert dwell["support_fraction_min"] >= 0.6
    body = presentation["bodies"]["packet"]
    assert body["last_support_hull"] == "inside"
    assert body["support_seen"] is True
    checks = {c["name"]: c["status"] for c in summary["checks"]}
    assert checks == {"exactly_one": "PASS", "supported_pickup": "PASS"}
    assert (out / "states.npz").is_file()
    assert json.loads((out / "manifest.json").read_text())["events"]


def test_real_missing_force_is_zero_feed_fail(tmp_path):
    summary, _ = run_case(tmp_path, "missing_force",
                          build_fixture("presentation_aperture"), effort=0.0)
    assert summary["status"] == "FAIL"
    presentation = next(e for e in summary["events"]
                        if e["name"] == "packet_presentation")
    assert presentation["verdict_code"] == "zero_feed"
    assert presentation["distinct_bodies_crossed"] == 0
    assert summary["validity"]["ok"] is True


def test_real_blocked_aperture_is_zero_feed_fail(tmp_path):
    summary, _ = run_case(tmp_path, "blocked",
                          build_fixture("presentation_aperture_blocked"))
    assert summary["status"] == "FAIL"
    presentation = next(e for e in summary["events"]
                        if e["name"] == "packet_presentation")
    assert presentation["verdict_code"] == "zero_feed"
    assert presentation["distinct_bodies_crossed"] == 0
    assert summary["validity"]["ok"] is True


def test_real_two_packets_are_a_double_feed_fail(tmp_path):
    summary, _ = run_case(
        tmp_path, "double", build_fixture("presentation_aperture_double"),
        bodies=("packet_a", "packet_b"), extents=(0.05, 0.0085, 0.004))
    assert summary["status"] == "FAIL"
    exit_event = next(e for e in summary["events"] if e["name"] == "packet_exit")
    presentation = next(e for e in summary["events"]
                        if e["name"] == "packet_presentation")
    assert exit_event["distinct_bodies_crossed"] == 2
    assert presentation["verdict_code"] == "double_feed"
    check = next(c for c in summary["checks"] if c["name"] == "exactly_one")
    assert check["status"] == "FAIL" and check["value"] == 2.0


def test_real_no_gravity_is_inconclusive_not_pass(tmp_path):
    spec = replace(build_fixture("presentation_aperture"),
                   gravity_m_s2=(0.0, 0.0, 0.0))
    summary, _ = run_case(tmp_path, "no_gravity", spec)
    assert summary["status"] == "INCONCLUSIVE"
    presentation = next(e for e in summary["events"]
                        if e["name"] == "packet_presentation")
    assert presentation["verdict_code"] == "gravity_absent"


def test_wrong_unit_scale_is_error_before_a_run_directory(tmp_path):
    spec = replace(build_fixture("presentation_aperture"),
                   gravity_m_s2=(0.0, 0.0, -0.00980665))
    out = tmp_path / "wrong_unit"
    with pytest.raises(ValueError, match="unit-scale error"):
        run_assembly(spec, scenario(), acceptance(), out)
    assert not out.exists()


def test_numerical_invalidity_dominates_a_physical_event_pass(tmp_path):
    summary, _ = run_case(tmp_path, "invalid",
                          build_fixture("presentation_aperture"), max_speed=0.001)
    assert summary["status"] == "INCONCLUSIVE"
    assert summary["validity"]["ok"] is False
    presentation = next(e for e in summary["events"]
                        if e["name"] == "packet_presentation")
    # The event logic may see a supported presentation; invalidity still dominates overall.
    assert presentation["status"] == "PASS"


def test_real_positive_and_real_failure_replay_identically(tmp_path):
    positive, positive_dir = run_case(tmp_path, "positive_replay",
                                      build_fixture("presentation_aperture"))
    replay_positive = replay_run(positive_dir, tmp_path / "positive_replay_out")
    assert replay_positive["status"] == positive["status"] == "PASS"
    assert replay_positive["reproduced"] is True
    assert replay_positive["event_comparison"]["ok"] is True

    blocked, blocked_dir = run_case(tmp_path, "blocked_replay",
                                    build_fixture("presentation_aperture_blocked"))
    replay_blocked = replay_run(blocked_dir, tmp_path / "blocked_replay_out")
    assert replay_blocked["status"] == blocked["status"] == "FAIL"
    assert replay_blocked["reproduced"] is True
    assert replay_blocked["event_comparison"]["ok"] is True


def _run_powered(tmp_path, name, start_time_s):
    real_step = mujoco.mj_step
    calls = 0

    def powered(model, data):
        nonlocal calls
        if float(data.time) >= start_time_s - 1e-9:
            data.ctrl[0] = 2.0
            calls += 1
        real_step(model, data)

    with patch.object(mujoco, "mj_step", powered):
        summary, out = run_case(tmp_path, name,
                                build_fixture("presentation_aperture"))
    return summary, out, calls


def _assert_powered_inconclusive(summary, out, calls, phase):
    assert calls > 0
    assert summary["status"] == "INCONCLUSIVE"
    assert summary["validity"]["ok"] is False
    assert any(reason["stage"] == "release_input"
               for reason in summary["validity"]["reasons"])
    presentation = next(e for e in summary["events"]
                        if e["name"] == "packet_presentation")
    assert presentation["status"] == "INCONCLUSIVE"
    assert presentation["verdict_code"] == "nonzero_input_after_release"
    assert presentation["evidence_complete"] is True
    assert presentation["release_zero_ok"] is False
    assert presentation["release_zero_violation"]["phase"] == phase
    assert presentation["release_zero_violation"]["actual_max_abs_ctrl"] == 2.0
    assert presentation["bodies"]["packet"]["success"] is False
    assert presentation["invalid_reasons"][0]["stage"] == "release_input"
    check = next(c for c in summary["checks"] if c["name"] == "supported_pickup")
    assert check["status"] == "INCONCLUSIVE"
    with np.load(out / "states.npz", allow_pickle=False) as archive:
        controls = np.asarray(archive["ctrl"])
        times = np.asarray(archive["time"])
    assert int(np.count_nonzero(np.any(np.abs(controls) > 1e-12, axis=1))) > 0
    assert times.size > 0


@pytest.mark.parametrize("phase,start_time", [("release", 2.5), ("hold", 2.9)])
def test_real_powered_release_and_hold_are_inconclusive(tmp_path, phase, start_time):
    summary, out, calls = _run_powered(tmp_path, f"powered_{phase}", start_time)
    _assert_powered_inconclusive(summary, out, calls, phase)
    replay = replay_run(out, tmp_path / f"powered_{phase}_replay")
    assert replay["status"] == "INCONCLUSIVE"
    assert replay["reproduced"] is True
    assert replay["event_comparison"]["ok"] is True


def test_real_recorder_passes_prestep_boundary_seed(tmp_path):
    seen = []
    original = EventTracker.begin_phase

    def wrapper(self, name, kind, start_time_s, ctrl_zero, *, boundary=None):
        seen.append((name, boundary))
        return original(self, name, kind, start_time_s, ctrl_zero,
                        boundary=boundary)

    with patch.object(EventTracker, "begin_phase", wrapper):
        summary, _ = run_case(tmp_path, "boundary_seed",
                              build_fixture("presentation_aperture"))
    assert summary["status"] == "PASS"
    actuate = [boundary for name, boundary in seen if name == "actuate"]
    assert actuate and actuate[0] is not None
    boundary = actuate[0]
    assert boundary.phase_name == "actuate"
    assert boundary.time_s == pytest.approx(0.5)
    assert boundary.step_index == 500
    assert "packet" in boundary.bodies


def _scenario_with_actuation(actuation_s):
    return ScenarioSpec(
        "m4c_boundary", "presentation_aperture", 11,
        (PhaseSpec("reset", "reset", initial=(("pusher_slide", 0.0),)),
         PhaseSpec("settle", "settle", duration_s=0.5),
         PhaseSpec("actuate", "actuate", duration_s=actuation_s,
                   actuator="push", effort=2.0),
         PhaseSpec("release", "release", duration_s=0.4),
         PhaseSpec("hold", "hold", duration_s=1.5)),
        0.001, 0.002, BudgetSpec(7000, 8.0, 7000))


def test_real_boundary_seed_uses_forwarded_state_and_suppresses_prewindow_crossing(
        tmp_path):
    spec = replace(build_fixture("presentation_aperture"), integrator="Euler")
    base = run_assembly(spec, scenario(), acceptance(), tmp_path / "euler_base")
    crossing = next(e for e in base["events"]
                    if e["name"] == "packet_exit")["crossings"][0]["time_s"]
    end_t = math.ceil(crossing * 1000.0 - 1e-9) / 1000.0
    actuation_s = round(end_t - 0.5, 3)
    doc = acceptance_doc()
    for event in doc["events"]:
        event["window_from"] = "release"
    doc_acceptance = acceptance_from_text(json.dumps(doc))

    seen = {}
    original = TelemetryRecorder._event_boundary_observation

    def spy(self, phase):
        observation = original(self, phase)
        if phase.name == "release":
            body_id = dict(self.bodies)["packet"]
            coherent = self._observe()
            seen["seed_pos"] = observation.bodies["packet"].pos_m
            seen["coherent_pos"] = tuple(float(v) for v in coherent.xpos[body_id])
            seen["seed_time"] = observation.time_s
            seen["coherent_time"] = float(coherent.time)
        return observation

    with patch.object(TelemetryRecorder, "_event_boundary_observation", spy):
        summary = run_assembly(spec, _scenario_with_actuation(actuation_s),
                               doc_acceptance, tmp_path / "prewindow")
    assert seen
    assert seen["seed_pos"] == pytest.approx(seen["coherent_pos"], abs=1e-12)
    assert seen["seed_time"] == pytest.approx(seen["coherent_time"], abs=1e-12)
    exit_event = next(e for e in summary["events"] if e["name"] == "packet_exit")
    assert exit_event["distinct_bodies_crossed"] == 0
    assert exit_event["bodies"]["packet"]["initial_protruding"] is True
    replay = replay_run(tmp_path / "prewindow", tmp_path / "prewindow_replay")
    assert replay["reproduced"] is True
    assert replay["event_comparison"]["ok"] is True


def test_real_window_from_first_timed_phase_replays(tmp_path):
    doc = acceptance_doc()
    for event in doc["events"]:
        event["window_from"] = "settle"
    doc_acceptance = acceptance_from_text(json.dumps(doc))
    summary = run_assembly(build_fixture("presentation_aperture"), scenario(),
                           doc_acceptance, tmp_path / "first_phase")
    assert summary["status"] == "PASS", summary.get("detail")
    replay = replay_run(tmp_path / "first_phase", tmp_path / "first_phase_replay")
    assert replay["status"] == "PASS"
    assert replay["reproduced"] is True
    assert replay["event_comparison"]["ok"] is True


def test_malformed_event_schema_is_a_loader_error_not_a_dynamics_negative(tmp_path):
    doc = acceptance_doc()
    doc["events"][0]["unexpected"] = 1
    with pytest.raises(ScenarioError, match="unknown field"):
        acceptance_from_text(json.dumps(doc))
