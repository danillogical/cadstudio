"""Synthetic detector edge cases for the generic M4c events.

These tests feed **scripted rigid-body samples** to the pure tracker. They deliberately do not
claim MuJoCo evidence for the trajectories; the real physically driven positive/negative and
replay cases live in ``test_cadkit_physics_m4c_fixture.py``. Every test name is prefixed
``synthetic_`` so the distinction is explicit.
"""
from __future__ import annotations

import math
from dataclasses import replace

import pytest

from cadkit.physics.events import EventTracker, ObservedBody, ObservedContact, StepObservation
from cadkit.physics.scenario import EventSpec, PlaneSpec

MASS_KG = 0.0346
GRAVITY = 9.80665
WEIGHT_N = MASS_KG * GRAVITY


def exit_event(bodies=("packet",), half=(0.05, 0.018, 0.004)) -> EventSpec:
    return EventSpec(
        name="exit", kind="exit_crossing", bodies=tuple(bodies),
        plane=PlaneSpec((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), 1),
        object_half_extents_m=half, window_from="actuate", window_to="hold",
    )


def presentation_event(bodies=("packet",), half=(0.05, 0.018, 0.004),
                       dwell_to="hold") -> EventSpec:
    return EventSpec(
        name="presentation", kind="supported_presentation", bodies=tuple(bodies),
        plane=PlaneSpec((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), 1),
        access_plane=PlaneSpec((0.018, 0.0, 0.0), (1.0, 0.0, 0.0), 1),
        object_half_extents_m=half, window_from="actuate", window_to="hold",
        release_phase="release", dwell_from="release", dwell_to=dwell_to,
        min_protrusion_m=0.030, target_protrusion_m=0.040, min_accessible_m=0.010,
        dwell_min_s=0.5, protrusion_change_max_m=0.001,
        support_bodies=("floor",), min_support_load_fraction=0.6,
        support_hull_margin_m=0.001, support_hull_min_area_m2=1.0e-5,
        support_degeneracy_radius_m=0.002, max_terminal_speed_m_s=0.02,
        bounds_m=((-0.15, 0.15), (-0.05, 0.05), (-0.02, 0.05)),
        fallout_drop_m=0.02,
    )


def body(body_id="packet", x=-0.07, y=0.0, vx=0.1, z=0.004,
         quat=(1.0, 0.0, 0.0, 0.0)):
    return ObservedBody(body_id, (x, y, z), quat, (x, y, z), (vx, 0.0, 0.0),
                        MASS_KG)


def support_contacts(x=0.0, fraction=1.0):
    points = ((-0.02, -0.01), (-0.02, 0.01), (0.02, -0.01), (0.02, 0.01))
    force = WEIGHT_N * fraction / len(points)
    return tuple(ObservedContact("packet", "floor", (x + dx, dy, 0.0), force, (0.0, 0.0, 1.0))
                 for dx, dy in points)


def drive(events, phases, bodies_at, contacts_at, *, dt=0.01, stopped=False,
          gravity=(0.0, 0.0, -GRAVITY), ctrl_zero_at=None, boundary_bodies_at=None):
    tracker = EventTracker(tuple(events), gravity_m_s2=gravity)
    t = 0.0
    step = 0
    for name, kind, duration, ctrl_zero in phases:
        boundary = None
        if boundary_bodies_at is not None:
            boundary_bodies = boundary_bodies_at(name, t)
            if boundary_bodies is not None:
                boundary = StepObservation(
                    time_s=t, step_index=step, phase_name=name, phase_kind=kind,
                    ctrl_zero=True, bodies=boundary_bodies, contacts=(),
                    ctrl_max_abs=0.0)
        tracker.begin_phase(name, kind, t, ctrl_zero, boundary=boundary)
        count = max(1, int(round(duration / dt)))
        for _ in range(count):
            step += 1
            t += dt
            zero = (ctrl_zero if ctrl_zero_at is None
                    else bool(ctrl_zero_at(t, name, kind)))
            tracker.observe(StepObservation(
                time_s=t, step_index=step, phase_name=name, phase_kind=kind,
                ctrl_zero=zero, bodies=bodies_at(t), contacts=contacts_at(t),
                ctrl_max_abs=0.0 if zero else 2.0))
        tracker.end_phase(name, complete=True, end_time_s=t)
    return tracker.finish(stopped=stopped, final_time_s=t)


def test_synthetic_clean_outward_crossing_counts_one_identity():
    results = drive(
        [exit_event()],
        [("actuate", "actuate", 0.4, False), ("release", "release", 0.1, True),
         ("hold", "hold", 0.1, True)],
        lambda t: {"packet": body(x=-0.07 if t < 0.16 else 0.0,
                                  vx=0.1 if t <= 0.16 else 0.0)},
        lambda t: (),
    )
    result = results["exit"]
    assert result.evidence_complete is True
    assert result.distinct_bodies_crossed == 1
    assert result.crossings[0]["time_s"] == pytest.approx(0.16, abs=0.01)
    assert result.bodies["packet"]["repeated_crossings"] == 0


def test_synthetic_touch_only_within_epsilon_is_not_a_crossing():
    epsilon_touch = -0.05 + 0.5e-6
    results = drive(
        [exit_event()],
        [("actuate", "actuate", 0.3, False), ("release", "release", 0.1, True),
         ("hold", "hold", 0.1, True)],
        lambda t: {"packet": body(x=epsilon_touch if 0.1 < t < 0.2 else -0.07,
                                  vx=0.002)},
        lambda t: (),
    )
    result = results["exit"]
    assert result.distinct_bodies_crossed == 0
    assert result.bodies["packet"]["touch_only"] is True
    assert "touch_only" in {d["code"] for d in result.diagnostics}


def test_synthetic_initially_outside_body_is_suppressed():
    results = drive(
        [exit_event()],
        [("actuate", "actuate", 0.3, False), ("release", "release", 0.1, True),
         ("hold", "hold", 0.1, True)],
        lambda t: {"packet": body(x=0.06 if t < 0.2 else 0.08, vx=0.1)},
        lambda t: (),
    )
    result = results["exit"]
    assert result.distinct_bodies_crossed == 0
    assert result.bodies["packet"]["initial_outside"] is True
    assert "initial_outside" in {d["code"] for d in result.diagnostics}


def test_synthetic_slow_outward_leading_edge_is_counted():
    """Rotation or creep can move the leading edge outward with a small/inward COM velocity."""
    results = drive(
        [exit_event()],
        [("actuate", "actuate", 0.3, False), ("release", "release", 0.1, True),
         ("hold", "hold", 0.1, True)],
        lambda t: {"packet": body(x=-0.07 if t < 0.1 else 0.0, vx=-0.1)},
        lambda t: (),
    )
    result = results["exit"]
    assert result.distinct_bodies_crossed == 1
    assert result.bodies["packet"]["wrong_direction_count"] == 0
    assert result.bodies["packet"]["touch_only"] is False


def test_synthetic_inward_crossing_after_outward_is_wrong_direction():
    def position(t):
        if t < 0.1:
            return -0.07
        if t < 0.2:
            return 0.0
        return -0.07

    results = drive(
        [exit_event()],
        [("actuate", "actuate", 0.3, False), ("release", "release", 0.1, True),
         ("hold", "hold", 0.1, True)],
        lambda t: {"packet": body(x=position(t), vx=0.1)},
        lambda t: (),
    )
    result = results["exit"]
    assert result.distinct_bodies_crossed == 1
    assert result.bodies["packet"]["wrong_direction_count"] >= 1


def test_synthetic_same_identity_recrossing_is_not_double_counted():
    def position(t):
        if t < 0.1:
            return -0.07
        if t < 0.2:
            return 0.0
        if t < 0.3:
            return -0.07
        return 0.0

    results = drive(
        [exit_event()],
        [("actuate", "actuate", 0.4, False), ("release", "release", 0.1, True),
         ("hold", "hold", 0.1, True)],
        lambda t: {"packet": body(x=position(t), vx=0.1)},
        lambda t: (),
    )
    result = results["exit"]
    assert result.distinct_bodies_crossed == 1
    assert result.bodies["packet"]["repeated_crossings"] == 1
    assert "re_crossing" in {d["code"] for d in result.diagnostics}


def test_synthetic_two_distinct_bodies_count_twice():
    def bodies_at(t):
        x = -0.07 if t < 0.1 else 0.0
        return {"a": body("a", x=x), "b": body("b", x=x)}

    results = drive(
        [exit_event(bodies=("a", "b"))],
        [("actuate", "actuate", 0.3, False), ("release", "release", 0.1, True),
         ("hold", "hold", 0.1, True)],
        bodies_at, lambda t: (),
    )
    result = results["exit"]
    assert result.distinct_bodies_crossed == 2
    assert result.status == "PASS"  # the event records evidence; event_count decides pass/fail
    assert "double_feed" in {d["code"] for d in result.diagnostics}


def test_synthetic_crossing_before_the_named_window_is_ignored():
    results = drive(
        [exit_event()],
        [("settle", "settle", 0.2, True), ("actuate", "actuate", 0.2, False),
         ("release", "release", 0.1, True), ("hold", "hold", 0.1, True)],
        lambda t: {"packet": body(x=-0.07 if t < 0.15 else -0.04, vx=0.0)},
        lambda t: (),
    )
    assert results["exit"].distinct_bodies_crossed == 0


def _presentation_phases(release=0.4, hold=1.5):
    return [("actuate", "actuate", 0.2, False), ("release", "release", release, True),
            ("hold", "hold", hold, True)]


def _presentation_body(t, x=0.0, z=0.004):
    return {"packet": body(x=-0.07 if t < 0.05 else x,
                           vx=0.1 if t <= 0.05 else 0.0, z=z)}


def test_synthetic_zero_gate_nonzero_at_release_begin():
    def ctrl(t, name, kind):
        return not (name == "release" and abs(t - 0.21) < 1e-9)

    results = drive(
        [presentation_event()], _presentation_phases(),
        lambda t: _presentation_body(t),
        lambda t: support_contacts(0.0) if t >= 0.2 else (),
        ctrl_zero_at=ctrl,
    )
    result = results["presentation"]
    assert result.status == "INCONCLUSIVE"
    assert result.verdict_code == "nonzero_input_after_release"
    assert result.release_zero_ok is False
    assert result.release_zero_checked_samples > 0
    assert result.release_zero_violation["phase"] == "release"
    assert result.release_zero_violation["actual_max_abs_ctrl"] == 2.0
    assert result.invalid_reasons[0]["stage"] == "release_input"
    assert result.bodies["packet"]["success"] is False


def test_synthetic_zero_gate_single_intermediate_release_sample():
    def ctrl(t, name, kind):
        return not (name == "release" and abs(t - 0.31) < 1e-9)

    results = drive(
        [presentation_event()], _presentation_phases(),
        lambda t: _presentation_body(t),
        lambda t: support_contacts(0.0) if t >= 0.2 else (),
        ctrl_zero_at=ctrl,
    )
    result = results["presentation"]
    assert result.status == "INCONCLUSIVE"
    assert result.verdict_code == "nonzero_input_after_release"
    assert result.release_zero_violation["phase"] == "release"
    assert abs(result.release_zero_violation["time_s"] - 0.31) < 1e-9


def test_synthetic_zero_gate_hold_only_nonzero():
    results = drive(
        [presentation_event()], _presentation_phases(),
        lambda t: _presentation_body(t),
        lambda t: support_contacts(0.0) if t >= 0.2 else (),
        ctrl_zero_at=lambda t, name, kind: name != "hold",
    )
    result = results["presentation"]
    assert result.status == "INCONCLUSIVE"
    assert result.verdict_code == "nonzero_input_after_release"
    assert result.release_zero_violation["phase"] == "hold"
    assert result.bodies["packet"]["success"] is False


def test_synthetic_zero_gate_late_violation_revokes_success():
    results = drive(
        [presentation_event()], _presentation_phases(),
        lambda t: _presentation_body(t),
        lambda t: support_contacts(0.0) if t >= 0.2 else (),
        ctrl_zero_at=lambda t, name, kind: not (name == "hold" and t >= 0.81),
    )
    result = results["presentation"]
    assert result.status == "INCONCLUSIVE"
    assert result.verdict_code == "nonzero_input_after_release"
    assert result.bodies["packet"]["success"] is False


def test_synthetic_boundary_command_is_not_release_input():
    phases = [("actuate", "actuate", 0.2, False),
              ("release", "release", 0.4, False),
              ("hold", "hold", 1.5, True)]
    results = drive(
        [presentation_event()], phases,
        lambda t: _presentation_body(t),
        lambda t: support_contacts(0.0) if t >= 0.2 else (),
        ctrl_zero_at=lambda t, name, kind: True,
        boundary_bodies_at=lambda name, t: ({"packet": body(x=-0.07)}
                                            if name == "actuate" else None),
    )
    result = results["presentation"]
    assert result.status == "PASS", result.detail
    assert result.release_zero_ok is True
    assert result.release_zero_violation is None


def test_synthetic_first_step_crossing_is_not_initial_protruding():
    phases = [("settle", "settle", 0.1, True),
              ("actuate", "actuate", 0.2, False),
              ("release", "release", 0.1, True),
              ("hold", "hold", 0.1, True)]
    results = drive(
        [exit_event()], phases,
        lambda t: {"packet": body(x=-0.07 if t <= 0.1 + 1e-9 else 0.0, vx=0.1)},
        lambda t: (),
        boundary_bodies_at=lambda name, t: ({"packet": body(x=-0.07)}
                                            if name == "actuate" else None),
    )
    result = results["exit"]
    assert result.distinct_bodies_crossed == 1
    assert result.bodies["packet"]["initial_protruding"] is False
    crossing = result.crossings[0]
    assert 0.1 < crossing["time_s"] < 0.11


def test_synthetic_first_step_initially_outside_is_suppressed():
    phases = [("settle", "settle", 0.1, True),
              ("actuate", "actuate", 0.2, False),
              ("release", "release", 0.1, True),
              ("hold", "hold", 0.1, True)]
    results = drive(
        [exit_event()], phases,
        lambda t: {"packet": body(x=0.08, vx=0.1)},
        lambda t: (),
        boundary_bodies_at=lambda name, t: ({"packet": body(x=0.06)}
                                            if name == "actuate" else None),
    )
    result = results["exit"]
    assert result.distinct_bodies_crossed == 0
    assert result.bodies["packet"]["initial_outside"] is True


def test_synthetic_prewindow_crossing_is_not_reimported():
    phases = [("settle", "settle", 0.1, True),
              ("actuate", "actuate", 0.2, False),
              ("release", "release", 0.1, True),
              ("hold", "hold", 0.1, True)]
    results = drive(
        [exit_event()], phases,
        lambda t: {"packet": body(x=-0.07 if t <= 0.05 else 0.0, vx=0.1)},
        lambda t: (),
        boundary_bodies_at=lambda name, t: ({"packet": body(x=0.0)}
                                            if name == "actuate" else None),
    )
    result = results["exit"]
    assert result.distinct_bodies_crossed == 0
    assert result.bodies["packet"]["initial_protruding"] is True


def test_synthetic_supported_dwell_at_threshold_passes():
    results = drive(
        [presentation_event()], _presentation_phases(),
        lambda t: _presentation_body(t),
        lambda t: support_contacts(0.0) if t >= 0.2 else (),
    )
    result = results["presentation"]
    assert result.status == "PASS", result.detail
    assert result.dwell["duration_s"] >= 0.5


def test_synthetic_dwell_just_below_threshold_fails():
    results = drive(
        [presentation_event()],
        [("actuate", "actuate", 0.2, False), ("release", "release", 0.3, True),
         ("hold", "hold", 0.1, True)],
        lambda t: _presentation_body(t),
        lambda t: support_contacts(0.0) if t >= 0.2 else (),
    )
    result = results["presentation"]
    assert result.status == "FAIL"
    assert result.verdict_code == "missed_presentation"


def test_synthetic_conditions_before_release_do_not_start_the_dwell():
    results = drive(
        [presentation_event()],
        [("actuate", "actuate", 0.6, False), ("release", "release", 0.05, True),
         ("hold", "hold", 0.1, True)],
        lambda t: _presentation_body(t),
        lambda t: support_contacts(0.0) if t < 0.6 else (),  # supported only before release
    )
    result = results["presentation"]
    assert result.status == "FAIL"
    assert result.dwell is None


def test_synthetic_support_lost_before_dwell_completes_fails():
    results = drive(
        [presentation_event()],
        [("actuate", "actuate", 0.2, False), ("release", "release", 0.4, True),
         ("hold", "hold", 0.3, True)],
        lambda t: _presentation_body(t),
        lambda t: support_contacts(0.0) if t < 0.5 else (),
    )
    result = results["presentation"]
    assert result.status == "FAIL"
    assert result.verdict_code == "support_lost"


def test_synthetic_total_fallout_is_detected():
    results = drive(
        [presentation_event()],
        [("actuate", "actuate", 0.2, False), ("release", "release", 0.4, True),
         ("hold", "hold", 0.4, True)],
        lambda t: _presentation_body(t, z=0.004 if t < 0.2 else -0.018),
        lambda t: (),
    )
    result = results["presentation"]
    assert result.status == "FAIL"
    assert result.verdict_code == "uncontrolled_fallout"


def test_synthetic_degenerate_marginal_support_is_inconclusive():
    def contacts(t):
        if t < 0.2:
            return ()
        return (ObservedContact("packet", "floor", (0.0, 0.003, 0.0), WEIGHT_N,
                                (0.0, 0.0, 1.0)),)

    results = drive(
        [presentation_event()], _presentation_phases(),
        lambda t: _presentation_body(t), contacts,
    )
    result = results["presentation"]
    assert result.status == "INCONCLUSIVE"
    assert result.verdict_code == "support_uncertain"


def test_synthetic_late_presentation_beyond_the_dwell_window_is_not_rescued():
    results = drive(
        [presentation_event(dwell_to="release")],
        [("actuate", "actuate", 0.2, False), ("release", "release", 0.3, True),
         ("hold", "hold", 0.6, True)],
        lambda t: _presentation_body(t),
        lambda t: support_contacts(0.0) if t >= 0.55 else (),
    )
    result = results["presentation"]
    assert result.status == "FAIL"
    assert result.verdict_code == "late_presentation"


def test_synthetic_protrusion_drift_over_one_millimetre_is_recorded():
    def position(t):
        return 0.0 if t < 0.5 else 0.0015

    def contacts(t):
        return support_contacts(position(t)) if t >= 0.2 else ()

    results = drive(
        [presentation_event()],
        [("actuate", "actuate", 0.2, False), ("release", "release", 0.4, True),
         ("hold", "hold", 0.2, True)],
        lambda t: _presentation_body(t, x=position(t)), contacts,
    )
    result = results["presentation"]
    assert result.status == "FAIL"
    assert "drift_exceeded" in {d["code"] for d in result.diagnostics}


def test_synthetic_post_success_drift_revokes_success():
    def position(t):
        return 0.0 if t < 0.9 else 0.002

    def contacts(t):
        return support_contacts(position(t)) if t >= 0.2 else ()

    results = drive(
        [presentation_event()],
        [("actuate", "actuate", 0.2, False), ("release", "release", 0.4, True),
         ("hold", "hold", 0.6, True)],
        lambda t: _presentation_body(t, x=position(t)), contacts,
    )
    result = results["presentation"]
    assert result.status == "FAIL"
    assert result.verdict_code == "post_dwell_failure"
    if result.dwell is not None and result.dwell["duration_s"] is not None:
        assert result.dwell["duration_s"] >= 0.0


def test_synthetic_near_threshold_support_is_inconclusive():
    results = drive(
        [presentation_event()], _presentation_phases(),
        lambda t: _presentation_body(t),
        lambda t: support_contacts(0.0, fraction=0.61) if t >= 0.2 else (),
    )
    result = results["presentation"]
    assert result.status == "INCONCLUSIVE"
    assert result.verdict_code == "support_uncertain"


def test_synthetic_near_threshold_protrusion_is_inconclusive():
    results = drive(
        [presentation_event()], _presentation_phases(),
        lambda t: _presentation_body(t, x=-0.05 + 0.0300001),
        lambda t: support_contacts(-0.05 + 0.0300001) if t >= 0.2 else (),
    )
    result = results["presentation"]
    assert result.status == "INCONCLUSIVE"
    assert result.verdict_code == "near_threshold"


def test_synthetic_pre_release_fallout_is_detected():
    results = drive(
        [presentation_event()],
        [("actuate", "actuate", 0.3, False), ("release", "release", 0.3, True),
         ("hold", "hold", 0.3, True)],
        lambda t: {"packet": body(x=-0.07,
                                  z=0.004 if t < 0.15 else -0.018)},
        lambda t: (),
    )
    result = results["presentation"]
    assert result.status == "FAIL"
    assert result.verdict_code == "uncontrolled_fallout"


def test_synthetic_fallout_uses_the_configured_gravity_axis():
    event = replace(
        presentation_event(),
        bounds_m=((-0.15, 0.15), (-0.02, 0.05), (-0.05, 0.05)),
    )

    def bodies_at(t):
        return {"packet": body(x=-0.07 if t < 0.05 else 0.0,
                               y=0.004 if t < 0.15 else -0.018,
                               vx=0.1 if t <= 0.05 else 0.0)}

    results = drive(
        [event],
        [("actuate", "actuate", 0.3, False), ("release", "release", 0.3, True),
         ("hold", "hold", 0.3, True)],
        bodies_at, lambda t: (), gravity=(0.0, -GRAVITY, 0.0),
    )
    result = results["presentation"]
    assert result.status == "FAIL"
    assert result.verdict_code == "uncontrolled_fallout"


def test_synthetic_support_below_declared_fraction_fails():
    results = drive(
        [presentation_event()], _presentation_phases(),
        lambda t: _presentation_body(t),
        lambda t: support_contacts(0.0, fraction=0.5) if t >= 0.2 else (),
    )
    result = results["presentation"]
    assert result.status == "FAIL"
    assert result.verdict_code == "no_support_load"


def test_synthetic_lone_contact_point_cannot_prove_support():
    def contacts(t):
        if t < 0.2:
            return ()
        return (ObservedContact("packet", "floor", (0.0, 0.0, 0.0), WEIGHT_N,
                                (0.0, 0.0, 1.0)),)

    results = drive(
        [presentation_event()], _presentation_phases(),
        lambda t: _presentation_body(t), contacts,
    )
    result = results["presentation"]
    assert result.status == "INCONCLUSIVE"
    assert result.verdict_code == "support_uncertain"


def test_synthetic_coincident_contacts_are_not_a_support_hull():
    def contacts(t):
        if t < 0.2:
            return ()
        return (
            ObservedContact("packet", "floor", (0.0, 0.0, 0.0), WEIGHT_N / 2,
                            (0.0, 0.0, 1.0)),
            ObservedContact("packet", "floor", (0.0, 0.0, 0.0), WEIGHT_N / 2,
                            (0.0, 0.0, 1.0)),
        )

    results = drive(
        [presentation_event()], _presentation_phases(),
        lambda t: _presentation_body(t), contacts,
    )
    result = results["presentation"]
    assert result.status == "INCONCLUSIVE"
    assert result.verdict_code == "support_uncertain"


def test_synthetic_collinear_line_support_is_accepted_within_radius():
    def contacts(t):
        if t < 0.2:
            return ()
        return (
            ObservedContact("packet", "floor", (-0.02, 0.0015, 0.0), WEIGHT_N / 2,
                            (0.0, 0.0, 1.0)),
            ObservedContact("packet", "floor", (0.02, 0.0015, 0.0), WEIGHT_N / 2,
                            (0.0, 0.0, 1.0)),
        )

    results = drive(
        [presentation_event()], _presentation_phases(),
        lambda t: _presentation_body(t), contacts,
    )
    result = results["presentation"]
    assert result.status == "PASS", result.detail
    assert result.bodies["packet"]["last_support_hull"] == "line"


def test_synthetic_out_of_bounds_is_fail():
    results = drive(
        [presentation_event()], _presentation_phases(),
        lambda t: _presentation_body(t, x=0.0 if t < 0.2 else 0.20),
        lambda t: support_contacts(0.0) if t >= 0.2 else (),
    )
    result = results["presentation"]
    assert result.status == "FAIL"
    assert result.verdict_code == "out_of_bounds"


def test_synthetic_empty_observation_is_inconclusive_never_pass():
    tracker = EventTracker((presentation_event(),),
                           gravity_m_s2=(0.0, 0.0, -GRAVITY))
    tracker.begin_phase("actuate", "actuate", 0.0, False)
    tracker.end_phase("actuate", complete=True, end_time_s=0.2)
    tracker.begin_phase("release", "release", 0.2, True)
    tracker.end_phase("release", complete=True, end_time_s=0.6)
    tracker.begin_phase("hold", "hold", 0.6, True)
    tracker.end_phase("hold", complete=True, end_time_s=1.0)
    result = tracker.finish(stopped=False, final_time_s=1.0)["presentation"]
    assert result.status == "INCONCLUSIVE"
    assert result.evidence_complete is False


def test_synthetic_zero_gravity_is_inconclusive():
    event = presentation_event()
    tracker = EventTracker((event,), gravity_m_s2=(0.0, 0.0, 0.0))
    tracker.begin_phase("actuate", "actuate", 0.0, False)
    tracker.observe(StepObservation(0.01, 1, "actuate", "actuate", False,
                                    {"packet": body(x=-0.07)}, ()))
    tracker.observe(StepObservation(0.02, 2, "actuate", "actuate", False,
                                    {"packet": body(x=0.0)}, ()))
    tracker.end_phase("actuate", complete=True, end_time_s=0.02)
    tracker.begin_phase("release", "release", 0.02, True)
    tracker.observe(StepObservation(0.03, 3, "release", "release", True,
                                    {"packet": body(x=0.0)}, ()))
    tracker.end_phase("release", complete=True, end_time_s=0.42)
    tracker.begin_phase("hold", "hold", 0.42, True)
    tracker.end_phase("hold", complete=True, end_time_s=1.0)
    result = tracker.finish(stopped=False, final_time_s=1.0)["presentation"]
    assert result.status == "INCONCLUSIVE"
    assert result.verdict_code == "gravity_absent"
