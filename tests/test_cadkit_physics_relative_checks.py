"""Independent tests for the generic bound relative checks (M5a S0).

The contract under test:

* ``relative_pose`` / ``relative_translation`` use the bodies' **current** attached axes,
  never a frozen initial frame and never the reversed ``T_b . T_a^-1`` order.
* ``window="max_over_phase"`` evaluates every recorded integration state and reports the
  worst one (plus its time and the terminal value).
* ``contact_duration`` measures the whole run at integration-step resolution on the summed
  normal force of a body pair, strictly greater than the threshold.
* ``near_threshold_fraction`` is opt-in and only widens a PASS into INCONCLUSIVE.
* Replay recomputes every derived value from the verified acceptance lock; recorded values
  are never trusted.

Live fixture runs use the registered ``drop_box`` scene (a 20 mm box released 40 mm above
a fixed floor). ``sampling_interval_s`` equals the 1 ms timestep so ``trace.csv`` contains
every integration state. Synthetic snapshot telemetry is used only where an exact value is
needed to isolate evaluator semantics (near-threshold bands, world-frame signed drops,
missing/incomplete watches).
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
from dataclasses import replace

import numpy as np
import pytest

from cadkit.physics.evaluate import evaluate, resolve_references
from cadkit.physics.replay import replay_run
from cadkit.physics.runner import run_assembly, run_scenario
from cadkit.physics.scenario import (
    AcceptanceSpec,
    BudgetSpec,
    CheckSpec,
    PhaseSpec,
    ScenarioError,
    ScenarioSpec,
    ValiditySpec,
    acceptance_from_text,
    build_fixture,
    canonical_json,
)
from cadkit.physics.telemetry import (
    PhaseTelemetry,
    Snapshot,
    Telemetry,
    matrix_to_quaternion,
    pose_delta,
    quat_to_matrix,
    relative_transform,
)

pytest.importorskip("mujoco")

DT = 1.0e-3
BODIES = ("floor", "box")

# --------------------------------------------------------------------------- math helpers


def _yaw(angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    return np.asarray([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)


def _quat_yaw(angle: float) -> tuple[float, float, float, float]:
    return (math.cos(angle / 2.0), 0.0, 0.0, math.sin(angle / 2.0))


def _quat_x(angle: float) -> tuple[float, float, float, float]:
    return (math.cos(angle / 2.0), math.sin(angle / 2.0), 0.0, 0.0)


def _rigid(rotation: np.ndarray, translation: np.ndarray, pos, quat):
    """Apply a common world rigid transform ``G`` to one body-to-world pose."""
    new_pos = rotation @ np.asarray(pos, dtype=np.float64) + translation
    new_quat = matrix_to_quaternion(rotation @ quat_to_matrix(quat))
    return new_pos, new_quat


def _norm(value) -> float:
    return float(np.linalg.norm(np.asarray(value, dtype=np.float64)))


# --------------------------------------------------------------------------- synthetic telemetry


def _snapshot(time_s: float, bodies: dict) -> Snapshot:
    """A boundary snapshot carrying only the body poses the relative checks read."""
    return Snapshot(
        time_s=time_s,
        qpos={},
        qvel={},
        hash="",
        bodies={
            name: {"xpos": [float(v) for v in pos],
                   "xquat": [float(v) for v in quat]}
            for name, (pos, quat) in bodies.items()
        },
    )


def _synthetic_telemetry(initial: dict, end: dict, *, phase: str = "settle",
                         time_s: float = 0.1) -> Telemetry:
    return Telemetry(boundaries={
        "initial": _snapshot(0.0, initial),
        phase: _snapshot(time_s, end),
    })


def _identity_bodies(pos_b=(0.1, 0.0, 0.0)) -> dict:
    return {"floor": ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)),
            "box": (tuple(float(v) for v in pos_b), (1.0, 0.0, 0.0, 0.0))}


def _acceptance(checks: list[dict], *, near: float | None = None) -> AcceptanceSpec:
    doc: dict = {
        "schema_version": "m4a-1",
        "acceptance_id": "synthetic",
        "checks": checks,
    }
    if near is not None:
        doc["near_threshold_fraction"] = near
    return acceptance_from_text(json.dumps(doc))


def _outcome(acceptance: AcceptanceSpec, telemetry: Telemetry):
    scenario = _scenario("synthetic", _DROP_PHASES)
    evaluation = evaluate(scenario, acceptance, telemetry)
    return evaluation, {outcome.name: outcome for outcome in evaluation.checks}


# --------------------------------------------------------------------------- loader helpers


def _pose_doc(**overrides) -> dict:
    doc = {
        "name": "pose", "kind": "relative_pose", "body_a": "floor",
        "body_b": "box", "phase": "settle", "max": 0.01,
        "max_rotation_rad": 0.01, "units": "m",
    }
    doc.update(overrides)
    return doc


def _translation_doc(**overrides) -> dict:
    doc = {
        "name": "trans", "kind": "relative_translation", "body_a": "floor",
        "body_b": "box", "from_phase": "initial", "to_phase": "settle",
        "axis": "z", "lower": -0.01, "upper": 0.01, "units": "m",
    }
    doc.update(overrides)
    return doc


def _contact_doc(**overrides) -> dict:
    doc = {
        "name": "contact", "kind": "contact_duration", "body_a": "floor",
        "body_b": "box", "force_threshold_n": 0.05, "max": 0.1, "units": "s",
    }
    doc.update(overrides)
    return doc


def _load_doc(*checks: dict) -> AcceptanceSpec:
    return acceptance_from_text(json.dumps({
        "schema_version": "m4a-1", "acceptance_id": "loader", "checks": list(checks)}))


def _loader_scenario() -> ScenarioSpec:
    return _scenario("loader", _LOADER_PHASES)


def _loader_spec():
    return build_fixture("drop_box", DT)


# --------------------------------------------------------------------------- run helpers


def _scenario(scenario_id: str, phases) -> ScenarioSpec:
    return ScenarioSpec(scenario_id, "drop_box", 0, tuple(phases), DT, DT,
                        BudgetSpec(20000, 10.0, 20000))


_DROP_PHASES = (
    PhaseSpec("reset", "reset"),
    # The 0.10 s phase boundary is exactly a below-threshold (zero-force) interruption;
    # the sustained rest episode begins at 0.11 s, in the next phase.
    PhaseSpec("settle", "settle", 0.10),
    PhaseSpec("hold", "hold", 0.30),
)
_LOADER_PHASES = (
    PhaseSpec("reset", "reset"),
    PhaseSpec("settle", "settle", 0.05),
    PhaseSpec("hold", "hold", 0.05),
)


def _phase_steps(summary: dict) -> dict[str, int]:
    return {phase["name"]: int(phase["actual_steps"])
            for phase in summary["phases"]}


def _checks_by_name(summary: dict) -> dict[str, dict]:
    return {check["name"]: check for check in summary["checks"]}


def _read_trace(run_dir):
    with (run_dir / "trace.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_contacts(run_dir):
    with (run_dir / "contacts.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _trace_pose_columns(rows) -> tuple[dict, dict]:
    header = list(rows[0])
    pos, quat = {}, {}
    for body in BODIES:
        pos[body] = {}
        quat[body] = {}
        for axis in ("x", "y", "z"):
            match = next(key for key in header
                         if key.startswith(f"body_pos:{body}.{axis}"))
            pos[body][axis] = match
        for component in ("w", "x", "y", "z"):
            match = next(key for key in header
                         if key.startswith(f"body_quat:{body}.{component}"))
            quat[body][component] = match
    return pos, quat


def _trace_pose(row, pos, quat, body):
    return ([float(row[pos[body][axis]]) for axis in ("x", "y", "z")],
            [float(row[quat[body][component]]) for component in ("w", "x", "y", "z")])


def _independent_relative(rows, phase: str):
    """Recompute attached-local relative pose/translation from raw trace rows.

    Reference is the reset/initial trace row. Every declared-phase row contributes one
    sample, exactly as the acceptance contract requires.
    """
    pos, quat = _trace_pose_columns(rows)
    initial = next(row for row in rows if row["phase"] == "reset")
    p_ref, r_ref = relative_transform(
        *_trace_pose(initial, pos, quat, "floor"),
        *_trace_pose(initial, pos, quat, "box"))
    samples = []
    for row in rows:
        if row["phase"] != phase:
            continue
        p_rel, r_rel = relative_transform(
            *_trace_pose(row, pos, quat, "floor"),
            *_trace_pose(row, pos, quat, "box"))
        delta, angle = pose_delta(p_ref, r_ref, p_rel, r_rel)
        samples.append({
            "time_s": float(row["state_time_s"]),
            "translation_m": _norm(delta),
            "rotation_rad": float(angle),
            "delta": np.asarray(delta, dtype=np.float64),
            "box_z": float(row[pos["box"]["z"]]),
        })
    return samples


def _independent_speed(samples, dt: float):
    """Central-difference body speed from trace body positions (1 ms samples)."""
    best = (0.0, None)
    for index in range(1, len(samples) - 1):
        previous = samples[index - 1]
        following = samples[index + 1]
        speed = abs(following["box_z"] - previous["box_z"]) / (2.0 * dt)
        if speed > best[0]:
            best = (speed, samples[index]["time_s"])
    return best


def _state_force_series(run_dir, body_a="floor", body_b="box"):
    """Sum every contact-point normal force per integration state, zero when no contact."""
    rows = _read_trace(run_dir)
    by_time: dict[float, list[float]] = {}
    for row in _read_contacts(run_dir):
        if {row["body_a"], row["body_b"]} != {body_a, body_b}:
            continue
        by_time.setdefault(float(row["state_time_s"]), []).append(
            float(row["normal_force_n"]))
    return [(float(row["state_time_s"]),
             sum(by_time.get(float(row["state_time_s"]), ())))
            for row in rows], by_time


def _episodes(series, threshold: float):
    episodes: list[dict] = []
    start = None
    last = None
    count = 0
    for time_s, force in series:
        if force > threshold:
            if start is None:
                start, count = time_s, 0
            last = time_s
            count += 1
        elif start is not None:
            episodes.append({"start_s": start, "end_s": last, "run_samples": count,
                             "longest_s": last - start})
            start = None
    if start is not None:
        episodes.append({"start_s": start, "end_s": last, "run_samples": count,
                         "longest_s": last - start})
    return episodes


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- module fixtures


@pytest.fixture(scope="module")
def drop_pass_run(tmp_path_factory):
    """One real drop_box run shared by the replay, trace-recompute and contact tests."""
    run_dir = tmp_path_factory.mktemp("drop-pass") / "run"
    acceptance = AcceptanceSpec("drop_pass", (
        CheckSpec(name="pose_end", kind="relative_pose", body_a="floor",
                  body_b="box", phase="settle", maximum=0.2,
                  max_rotation_rad=0.1, units="m"),
        CheckSpec(name="pose_max", kind="relative_pose", body_a="floor",
                  body_b="box", phase="settle", maximum=0.2,
                  max_rotation_rad=0.1, window="max_over_phase", units="m"),
        CheckSpec(name="trans_max", kind="relative_translation", body_a="floor",
                  body_b="box", from_phase="initial", to_phase="settle",
                  axis="z", frame="body_a", lower=-0.2, upper=0.0,
                  window="max_over_phase", units="m"),
        CheckSpec(name="trans_world_max", kind="relative_translation",
                  body_a="floor", body_b="box", from_phase="initial",
                  to_phase="settle", axis="z", frame="world", lower=-0.2,
                  upper=0.0, window="max_over_phase", units="m"),
        CheckSpec(name="speed_end", kind="body_speed", body="box", phase="hold",
                  maximum=1.0, units="m/s"),
        CheckSpec(name="speed_max", kind="body_speed", body="box", phase="settle",
                  maximum=10.0, window="max_over_phase", units="m/s"),
        CheckSpec(name="contact", kind="contact_duration", body_a="floor",
                  body_b="box", force_threshold_n=0.06, maximum=0.35, units="s"),
        CheckSpec(name="contact_rev", kind="contact_duration", body_a="box",
                  body_b="floor", force_threshold_n=0.06, maximum=0.35, units="s"),
        CheckSpec(name="contact_isolated", kind="contact_duration", body_a="floor",
                  body_b="box", force_threshold_n=3.0, maximum=0.0, units="s"),
    ), ValiditySpec())
    scenario = _scenario("drop_pass", _DROP_PHASES)
    summary = run_scenario(scenario, acceptance, run_dir)
    assert summary["status"] == "PASS", summary["checks"]
    return {"summary": summary, "run_dir": run_dir, "scenario": scenario,
            "acceptance": acceptance}


@pytest.fixture(scope="module")
def drop_fail_run(tmp_path_factory, drop_pass_run):
    """A real run with failing max-over-phase bounds and an equality-threshold contact."""
    peak = _checks_by_name(drop_pass_run["summary"])["contact"]["evidence"]["peak_force_n"]
    run_dir = tmp_path_factory.mktemp("drop-fail") / "run"
    acceptance = AcceptanceSpec("drop_fail", (
        CheckSpec(name="pose_fail", kind="relative_pose", body_a="floor",
                  body_b="box", phase="settle", maximum=0.01,
                  max_rotation_rad=0.1, window="max_over_phase", units="m"),
        CheckSpec(name="trans_fail", kind="relative_translation", body_a="floor",
                  body_b="box", from_phase="initial", to_phase="settle",
                  axis="z", frame="body_a", lower=-0.001, upper=0.0,
                  window="max_over_phase", units="m"),
        CheckSpec(name="speed_pass", kind="body_speed", body="box", phase="settle",
                  maximum=10.0, window="max_over_phase", units="m/s"),
        CheckSpec(name="contact_eq", kind="contact_duration", body_a="floor",
                  body_b="box", force_threshold_n=peak, maximum=1.0, units="s"),
        CheckSpec(name="hold_from_settle", kind="relative_translation",
                  body_a="floor", body_b="box", from_phase="settle",
                  to_phase="hold", axis="z", lower=-0.001, upper=0.001,
                  units="m"),
        CheckSpec(name="hold_from_initial", kind="relative_translation",
                  body_a="floor", body_b="box", from_phase="initial",
                  to_phase="hold", axis="z", lower=-0.001, upper=0.001,
                  units="m"),
    ), ValiditySpec())
    scenario = _scenario("drop_fail", _DROP_PHASES)
    summary = run_scenario(scenario, acceptance, run_dir)
    assert summary["status"] == "FAIL", summary["checks"]
    return {"summary": summary, "run_dir": run_dir, "peak_threshold": peak}


@pytest.fixture(scope="module")
def near_run(tmp_path_factory):
    """A live run whose opt-in near bands leave it INCONCLUSIVE and replayable."""
    run_dir = tmp_path_factory.mktemp("near-band") / "run"
    acceptance = AcceptanceSpec("near_band", (
        CheckSpec(name="pose_near", kind="relative_pose", body_a="floor",
                  body_b="box", phase="settle", maximum=0.049,
                  max_rotation_rad=0.1, units="m"),
        CheckSpec(name="trans_near", kind="relative_translation",
                  body_a="floor", body_b="box", from_phase="initial",
                  to_phase="settle", axis="z", frame="body_a",
                  lower=-0.049, upper=0.0, units="m"),
    ), ValiditySpec(), near_threshold_fraction=0.2)
    scenario = _scenario("near_band", _DROP_PHASES)
    summary = run_scenario(scenario, acceptance, run_dir)
    assert summary["status"] == "INCONCLUSIVE", summary["checks"]
    return {"summary": summary, "run_dir": run_dir}


@pytest.fixture(scope="module")
def speed_contact_near_runs(tmp_path_factory, drop_pass_run):
    """Live speed/contact runs at the supervisor's measured/0.9 near-band pattern."""
    checks = _checks_by_name(drop_pass_run["summary"])
    speed = float(checks["speed_max"]["value"])
    duration = float(checks["contact"]["value"])
    scenario = _scenario("speed_contact_band", _DROP_PHASES)

    def criteria(speed_bound, duration_bound):
        return (
            CheckSpec(name="speed_band", kind="body_speed", body="box",
                      phase="settle", maximum=speed_bound,
                      window="max_over_phase", units="m/s"),
            CheckSpec(name="contact_band", kind="contact_duration", body_a="floor",
                      body_b="box", force_threshold_n=0.06, maximum=duration_bound,
                      units="s"),
        )

    def run(name, speed_bound, duration_bound, near):
        run_dir = tmp_path_factory.mktemp(name) / "run"
        acceptance = AcceptanceSpec(
            name, criteria(speed_bound, duration_bound), ValiditySpec(),
            near_threshold_fraction=near)
        summary = run_scenario(scenario, acceptance, run_dir)
        return {"summary": summary, "run_dir": run_dir, "acceptance": acceptance}

    near = run("speed_contact_near", speed / 0.9, duration / 0.9, 0.2)
    plain = run("speed_contact_plain", speed / 0.9, duration / 0.9, 0.0)
    breach = run("speed_contact_breach", speed * 0.5, duration * 0.5, 0.2)
    assert near["summary"]["status"] == "INCONCLUSIVE"
    assert plain["summary"]["status"] == "PASS"
    assert breach["summary"]["status"] == "FAIL"
    return {"near": near, "plain": plain, "breach": breach,
            "measured_speed": speed, "measured_duration": duration}


@pytest.fixture(scope="module")
def lift_run(tmp_path_factory):
    """A real no-contact scene: gravity is reversed so the box rises away from the floor."""
    spec = replace(build_fixture("drop_box", DT), gravity_m_s2=(0.0, 0.0, 9.80665),
                   name="m4a_drop_box_lift")
    phases = (PhaseSpec("reset", "reset"), PhaseSpec("rise", "settle", 0.009))
    scenario = _scenario("lift", phases)
    acceptance = AcceptanceSpec("lift", (
        CheckSpec(name="no_contact", kind="contact_duration", body_a="floor",
                  body_b="box", force_threshold_n=0.0, maximum=0.0, units="s"),
        CheckSpec(name="world_lift", kind="relative_translation", body_a="floor",
                  body_b="box", from_phase="initial", to_phase="rise", axis="z",
                  frame="world", lower=-0.0001, upper=0.0001, units="m"),
    ), ValiditySpec(), near_threshold_fraction=0.2)
    run_dir = tmp_path_factory.mktemp("lift") / "run"
    summary = run_assembly(spec, scenario, acceptance, run_dir,
                           fixture_label="drop_box_lift")
    return {"summary": summary, "run_dir": run_dir}


# --------------------------------------------------------------------------- 1. wrong frame/order


def test_yaw_90_counterexample_uses_current_attached_axes_and_correct_order():
    """A=(1,0,0) mm, B=(1,1,0) mm, both yawed 90 deg: p_rel must be (1,0,0) mm."""
    pos_a, quat_a = (1.0, 0.0, 0.0), _quat_yaw(math.pi / 2.0)
    pos_b, quat_b = (1.0, 1.0, 0.0), _quat_yaw(math.pi / 2.0)

    p_rel, rotation_rel = relative_transform(pos_a, quat_a, pos_b, quat_b)
    np.testing.assert_allclose(p_rel, [1.0, 0.0, 0.0], atol=1e-12)
    np.testing.assert_allclose(rotation_rel, np.eye(3), atol=1e-12)

    # Frozen initial axes / plain world separation gives (0,1,0) and is wrong.
    frozen = np.asarray(pos_b) - np.asarray(pos_a)
    np.testing.assert_allclose(frozen, [0.0, 1.0, 0.0], atol=1e-12)
    assert _norm(p_rel - frozen) > 0.5

    # The reversed order T_b . T_a^-1 gives (-1,0,0) and is wrong.
    reversed_p, _ = relative_transform(pos_b, quat_b, pos_a, quat_a)
    np.testing.assert_allclose(reversed_p, [-1.0, 0.0, 0.0], atol=1e-12)
    assert _norm(p_rel - reversed_p) > 0.5


# --------------------------------------------------------------------------- 2. common rotation


def test_common_rotation_leaves_attached_local_delta_zero_and_rejects_old_formula():
    quat_identity = (1.0, 0.0, 0.0, 0.0)
    pos_a0, pos_b0 = (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)
    p_ref, r_ref = relative_transform(pos_a0, quat_identity, pos_b0, quat_identity)
    np.testing.assert_allclose(p_ref, [1.0, 0.0, 0.0], atol=1e-12)

    yaw = math.pi / 2.0
    pos_a1 = (0.0, 0.0, 0.0)
    pos_b1 = tuple(_yaw(yaw) @ np.asarray(pos_b0))
    quat1 = _quat_yaw(yaw)
    p_end, r_end = relative_transform(pos_a1, quat1, pos_b1, quat1)

    delta_p, delta_rotation = pose_delta(p_ref, r_ref, p_end, r_end)
    assert _norm(delta_p) < 1e-12
    assert abs(delta_rotation) < 1e-12

    # The old frozen-frame/world-separation formula reports sqrt(2) mm of "motion".
    old_delta = (np.asarray(pos_b1) - np.asarray(pos_a1)
                 - (np.asarray(pos_b0) - np.asarray(pos_a0)))
    assert _norm(old_delta) == pytest.approx(1.4142135623730951, rel=1e-12)
    assert _norm(delta_p) < 1e-6
    assert not math.isclose(_norm(delta_p), _norm(old_delta), abs_tol=1e-3)


# --------------------------------------------------------------------------- 3. invariance


def test_constant_rigid_transform_preserves_relative_pose_delta_and_angle():
    quat_identity = (1.0, 0.0, 0.0, 0.0)
    poses = [
        ((0.10, -0.20, 0.30), quat_identity),
        ((0.35, -0.15, 0.28), _quat_yaw(0.4)),
        ((0.12, -0.18, 0.31), _quat_yaw(0.1)),
        ((0.30, -0.16, 0.27), _quat_yaw(0.45)),
    ]
    # Two bodies at initial and final times.
    p0, r0 = relative_transform(*poses[0], *poses[1])
    p1, r1 = relative_transform(*poses[2], *poses[3])
    baseline_delta, baseline_angle = pose_delta(p0, r0, p1, r1)

    common_rotation = _yaw(0.7)
    common_translation = np.asarray([0.4, -0.9, 1.3])
    moved = [_rigid(common_rotation, common_translation, pos, quat)
             for pos, quat in poses]
    q0, s0 = relative_transform(*moved[0], *moved[1])
    q1, s1 = relative_transform(*moved[2], *moved[3])
    moved_delta, moved_angle = pose_delta(q0, s0, q1, s1)

    np.testing.assert_allclose(q0, p0, atol=1e-12)
    np.testing.assert_allclose(q1, p1, atol=1e-12)
    np.testing.assert_allclose(moved_delta, baseline_delta, atol=1e-12)
    np.testing.assert_allclose(moved_angle, baseline_angle, atol=1e-12)

    # Explicit limitation: world-frame separation is *not* invariant under a common
    # rotation (it is only invariant under a common translation).
    world_before = np.asarray(poses[1][0]) - np.asarray(poses[0][0])
    world_after = np.asarray(moved[1][0]) - np.asarray(moved[0][0])
    assert _norm(world_after - world_before) > 0.1
    assert _norm(world_after) == pytest.approx(_norm(world_before), rel=1e-12)


# --------------------------------------------------------------------------- 4. true relative motion


def test_true_relative_motion_survives_common_motion_and_no_motion_gives_zero():
    quat_identity = (1.0, 0.0, 0.0, 0.0)
    pos_a0 = (0.2, -0.1, 0.05)
    pos_b0 = (0.3, -0.1, 0.05)
    p0, r0 = relative_transform(pos_a0, quat_identity, pos_b0, quat_identity)

    common_rotation = _yaw(0.35)
    common_translation = np.asarray([-0.7, 0.2, 0.4])
    rot_a = common_rotation  # A starts at identity, so R_a' = G_R
    pos_a1 = rot_a @ np.asarray(pos_a0) + common_translation
    # B has moved +0.02 m in A's local +x and yawed 0.3 rad relative to A.
    pos_b1 = pos_a1 + rot_a @ np.asarray([0.12, 0.0, 0.0])
    quat_a1 = matrix_to_quaternion(rot_a)
    quat_b1 = matrix_to_quaternion(rot_a @ _yaw(0.3))

    p1, r1 = relative_transform(pos_a1, quat_a1, pos_b1, quat_b1)
    delta_p, angle = pose_delta(p0, r0, p1, r1)
    np.testing.assert_allclose(delta_p, [0.02, 0.0, 0.0], atol=1e-12)
    assert angle == pytest.approx(0.3, abs=1e-12)

    # No relative motion at all: exactly zero, not a small fabricated value.
    p_same, r_same = relative_transform(pos_a1, quat_a1, pos_b1, quat_b1)
    zero_delta, zero_angle = pose_delta(p1, r1, p_same, r_same)
    assert _norm(zero_delta) == 0.0
    assert zero_angle == 0.0


# --------------------------------------------------------------------------- 5. component isolation


def test_rotation_only_breach_fails_while_translation_component_passes():
    initial = _identity_bodies()
    endpoint = _identity_bodies()
    endpoint["box"] = ((0.1, 0.0, 0.0), _quat_yaw(0.5))
    telemetry = _synthetic_telemetry(initial, endpoint)
    acceptance = _acceptance([_pose_doc(max=0.001, max_rotation_rad=0.01)])
    evaluation, outcomes = _outcome(acceptance, telemetry)

    outcome = outcomes["pose"]
    assert evaluation.status == "FAIL"
    assert outcome.status == "FAIL"
    assert outcome.evidence["translation_m"] == pytest.approx(0.0, abs=1e-12)
    assert outcome.evidence["rotation_rad"] == pytest.approx(0.5, abs=1e-12)


def test_both_pose_bounds_breached_fails_and_keeps_both_components():
    initial = _identity_bodies()
    endpoint = _identity_bodies(pos_b=(0.15, 0.0, 0.0))
    endpoint["box"] = ((0.15, 0.0, 0.0), _quat_yaw(0.5))
    telemetry = _synthetic_telemetry(initial, endpoint)
    acceptance = _acceptance([_pose_doc(max=0.01, max_rotation_rad=0.1)])
    evaluation, outcomes = _outcome(acceptance, telemetry)

    outcome = outcomes["pose"]
    assert evaluation.status == "FAIL"
    assert outcome.status == "FAIL"
    assert outcome.evidence["translation_m"] == pytest.approx(0.05, abs=1e-12)
    assert outcome.evidence["rotation_rad"] == pytest.approx(0.5, abs=1e-12)


def test_translation_only_breach_fails_while_rotation_component_passes():
    initial = _identity_bodies()
    endpoint = _identity_bodies(pos_b=(0.15, 0.0, 0.0))
    telemetry = _synthetic_telemetry(initial, endpoint)
    acceptance = _acceptance([_pose_doc(max=0.01, max_rotation_rad=1.0)])
    evaluation, outcomes = _outcome(acceptance, telemetry)

    outcome = outcomes["pose"]
    assert evaluation.status == "FAIL"
    assert outcome.status == "FAIL"
    assert outcome.evidence["translation_m"] == pytest.approx(0.05, abs=1e-12)
    assert outcome.evidence["rotation_rad"] == pytest.approx(0.0, abs=1e-12)


# --------------------------------------------------------------------------- 6. world-z signed


def test_world_z_signed_drop_and_lift_reject_the_wrong_sign_and_report_drop():
    # Rotate the reference body 90 deg about x so a local-axis implementation would read
    # zero while the world-frame z separation is unambiguous.
    rotated = _quat_x(math.pi / 2.0)
    initial = {"floor": ((0.0, 0.0, 0.0), rotated),
               "box": ((0.0, 0.0, 0.1000), (1.0, 0.0, 0.0, 0.0))}
    fall = {"floor": ((0.0, 0.0, 0.0), rotated),
            "box": ((0.0, 0.0, 0.0996), (1.0, 0.0, 0.0, 0.0))}
    lift = {"floor": ((0.0, 0.0, 0.0), rotated),
            "box": ((0.0, 0.0, 0.1004), (1.0, 0.0, 0.0, 0.0))}
    acceptance = _acceptance([_translation_doc(
        frame="world", from_phase="initial", to_phase="settle",
        lower=-0.0001, upper=0.0001)])

    fall_eval, fall_out = _outcome(acceptance, _synthetic_telemetry(initial, fall))
    fall_check = fall_out["trans"]
    assert fall_eval.status == "FAIL"
    assert fall_check.status == "FAIL"
    assert fall_check.value == pytest.approx(-0.0004, abs=1e-12)
    assert fall_check.evidence["drop_m"] == pytest.approx(0.0004, abs=1e-12)
    assert fall_check.evidence["terminal_m"] < 0.0

    # The same rotated reference reads exactly zero on local z, so the FAIL above proves the
    # world-separation branch (not body_a) produced the signed value.
    local_acceptance = _acceptance([_translation_doc(
        frame="body_a", from_phase="initial", to_phase="settle",
        lower=-0.0001, upper=0.0001)])
    local_eval, local_out = _outcome(
        local_acceptance, _synthetic_telemetry(initial, fall))
    assert local_eval.status == "PASS"
    assert local_out["trans"].value == pytest.approx(0.0, abs=1e-12)

    lift_eval, lift_out = _outcome(acceptance, _synthetic_telemetry(initial, lift))
    lift_check = lift_out["trans"]
    assert lift_eval.status == "FAIL"
    assert lift_check.status == "FAIL"
    assert lift_check.value == pytest.approx(0.0004, abs=1e-12)
    assert lift_check.evidence["drop_m"] == 0.0
    assert lift_check.evidence["terminal_m"] > 0.0


# --------------------------------------------------------------------------- 7. strict loader


def test_loader_rejects_unknown_bodies_phases_and_ordering():
    spec = _loader_spec()
    scenario = _loader_scenario()

    def reject(match: str, *checks: dict, **top):
        doc = {"schema_version": "m4a-1", "acceptance_id": "loader",
               "checks": list(checks), **top}
        acceptance = acceptance_from_text(json.dumps(doc))
        with pytest.raises(ScenarioError, match=match):
            resolve_references(scenario, acceptance, spec)

    reject("unknown body", _pose_doc(body_a="ghost"))
    reject("unknown body", _translation_doc(body_b="ghost"))
    reject("unknown phase", _pose_doc(phase="nope"))
    reject("unknown phase", _translation_doc(to_phase="nope"))
    reject("timed scenario phase", _pose_doc(phase="reset"))
    reject("timed scenario phase", _translation_doc(to_phase="reset"))
    reject("'initial' or a timed phase", _translation_doc(from_phase="reset"))
    reject("must precede", _translation_doc(from_phase="hold", to_phase="settle"))
    reject("must precede", _translation_doc(from_phase="settle", to_phase="settle"))


@pytest.mark.parametrize("check,match", [
    (_pose_doc(body_a="floor", body_b="floor"), "must differ"),
    (_translation_doc(body_a="box", body_b="box"), "must differ"),
    (_contact_doc(body_a="box", body_b="box"), "must differ"),
    (_translation_doc(frame="world", axis="x"), "only defined for axis='z'"),
    (_translation_doc(frame="world", axis="y"), "only defined for axis='z'"),
    (_contact_doc(window="max_over_phase"), "not defined for it"),
])
def test_loader_rejects_invalid_documents(check, match):
    with pytest.raises(ScenarioError, match=match):
        _load_doc(check)


def test_loader_rejects_missing_bounds_ordering_extra_fields_and_nonfinite():
    missing_lower = _translation_doc()
    del missing_lower["lower"]
    with pytest.raises(ScenarioError, match="missing required field"):
        _load_doc(missing_lower)
    missing_upper = _translation_doc()
    del missing_upper["upper"]
    with pytest.raises(ScenarioError, match="missing required field"):
        _load_doc(missing_upper)
    with pytest.raises(ScenarioError, match="must not exceed"):
        _load_doc(_translation_doc(lower=0.01, upper=-0.01))
    with pytest.raises(ScenarioError, match="unknown field"):
        _load_doc(_pose_doc(extra=1))

    nonfinite = json.dumps({"schema_version": "m4a-1", "acceptance_id": "loader",
                            "checks": [_pose_doc(max=float("nan"))]})
    with pytest.raises(ScenarioError, match="non-finite"):
        acceptance_from_text(nonfinite)
    overflow = json.dumps({"schema_version": "m4a-1", "acceptance_id": "loader",
                           "checks": [_pose_doc()]}).replace('"max": 0.01',
                                                              '"max": 1e999')
    with pytest.raises(ScenarioError, match="finite"):
        acceptance_from_text(overflow)


def test_canonical_round_trip_omits_defaults_and_preserves_hash():
    pose_default = _pose_doc()  # default window "end", units "m"
    pose_max = _pose_doc(name="pose_max", window="max_over_phase")
    trans = _translation_doc(frame="body_a")
    contact = _contact_doc()
    speed_end = {"name": "speed", "kind": "body_speed", "body": "box",
                 "phase": "settle", "max": 1.0, "units": "m/s"}
    acceptance = _load_doc(pose_default, pose_max, trans, contact, speed_end)

    by_name = {check.name: check for check in acceptance.checks}
    assert "window" not in by_name["pose"].to_dict()
    assert by_name["pose"].window == "end"
    assert by_name["pose_max"].to_dict()["window"] == "max_over_phase"
    assert "window" not in by_name["speed"].to_dict()

    canonical = canonical_json(acceptance.to_dict())
    reparsed = acceptance_from_text(canonical)
    assert reparsed.hash() == acceptance.hash()
    assert [check.to_dict() for check in reparsed.checks] == \
        [check.to_dict() for check in acceptance.checks]

    # Removing an explicit max_over_phase window changes the semantics and the hash back to
    # the default end window; a document without the field loads cleanly.
    document = acceptance.to_dict()
    pose_dict = next(item for item in document["checks"] if item["name"] == "pose_max")
    del pose_dict["window"]
    downgraded = acceptance_from_text(json.dumps(document))
    downgraded_pose = {c.name: c for c in downgraded.checks}["pose_max"]
    assert downgraded_pose.window == "end"
    assert downgraded.hash() != acceptance.hash()

    # Default-window checks already omit the field and still round-trip.
    document = acceptance.to_dict()
    stripped = next(item for item in document["checks"] if item["name"] == "pose")
    assert "window" not in stripped
    assert acceptance_from_text(json.dumps(document)).hash() == acceptance.hash()

    # near_threshold_fraction is opt-in and omitted when zero.
    assert acceptance.near_threshold_fraction == 0.0
    assert "near_threshold_fraction" not in acceptance.to_dict()
    opt_in = acceptance_from_text(json.dumps({
        "schema_version": "m4a-1", "acceptance_id": "synthetic",
        "near_threshold_fraction": 0.2, "checks": [_pose_doc()]}))
    assert opt_in.to_dict()["near_threshold_fraction"] == 0.2
    assert acceptance_from_text(canonical_json(opt_in.to_dict())).hash() == opt_in.hash()


def test_typed_relative_translation_default_frame_round_trips():
    """A typed CheckSpec leaving the optional body_a frame at its default must round-trip.

    Contract item 7: ``CheckSpec.to_dict()`` round-trips through
    ``acceptance_from_text`` with the same hash. Omitting ``frame`` means body_a, so the
    canonical document must not gain a field that changes the acceptance hash (which would
    also make the run's own acceptance lock unreplayable).
    """
    typed = AcceptanceSpec("typed", (
        CheckSpec(name="trans", kind="relative_translation", body_a="floor",
                  body_b="box", from_phase="initial", to_phase="settle",
                  axis="z", lower=-0.1, upper=0.1, units="m"),
    ), ValiditySpec())
    document = typed.to_dict()
    assert "frame" not in document["checks"][0]
    reloaded = acceptance_from_text(canonical_json(document))
    assert reloaded.hash() == typed.hash()


# --------------------------------------------------------------------------- 8. every-step maxima


def test_max_over_phase_matches_independent_trace_recomputation(drop_pass_run):
    summary = drop_pass_run["summary"]
    run_dir = drop_pass_run["run_dir"]
    checks = _checks_by_name(summary)
    steps = _phase_steps(summary)
    rows = _read_trace(run_dir)
    samples = _independent_relative(rows, "settle")
    assert len(samples) == steps["settle"]

    # relative_pose: worst translation is interior (t=0.092 s), terminal is smaller.
    pose = checks["pose_max"]
    worst = max(samples, key=lambda item: item["translation_m"])
    assert pose["evidence"]["samples"] == steps["settle"]
    assert pose["evidence"]["translation_m"] == pytest.approx(
        worst["translation_m"], rel=1e-12, abs=1e-12)
    assert pose["evidence"]["translation_time_s"] == pytest.approx(
        worst["time_s"], abs=1e-9)
    assert worst["time_s"] < samples[-1]["time_s"] - 1e-9
    assert pose["evidence"]["end_translation_m"] == pytest.approx(
        samples[-1]["translation_m"], rel=1e-12, abs=1e-12)
    assert pose["evidence"]["rotation_rad"] == pytest.approx(
        max(item["rotation_rad"] for item in samples), abs=1e-12)
    assert pose["status"] == "PASS"

    # relative_translation: the minimum signed z is also interior.
    trans = checks["trans_max"]
    lowest = min(samples, key=lambda item: item["delta"][2])
    assert trans["evidence"]["samples"] == steps["settle"]
    assert trans["evidence"]["min_m"] == pytest.approx(
        float(lowest["delta"][2]), rel=1e-12, abs=1e-12)
    assert trans["evidence"]["min_time_s"] == pytest.approx(
        lowest["time_s"], abs=1e-9)
    assert lowest["time_s"] < samples[-1]["time_s"] - 1e-9
    assert trans["evidence"]["terminal_m"] == pytest.approx(
        float(samples[-1]["delta"][2]), rel=1e-12, abs=1e-12)
    assert trans["status"] == "PASS"

    # body_speed: central-difference positions find an interior worst speed.
    speed = checks["speed_max"]
    independent_speed, independent_time = _independent_speed(samples, DT)
    assert speed["evidence"]["samples"] == steps["settle"]
    assert independent_time == pytest.approx(speed["evidence"]["time_s"], abs=1.5 * DT)
    assert independent_speed == pytest.approx(
        speed["evidence"]["speed_m_s"], rel=0.03)
    assert speed["evidence"]["time_s"] < samples[-1]["time_s"] - 1e-9
    assert speed["evidence"]["terminal_time_s"] == pytest.approx(
        samples[-1]["time_s"], abs=1e-9)
    assert 0.0 <= speed["evidence"]["terminal_speed_m_s"] < independent_speed
    assert speed["status"] == "PASS"

    # The default "end" window keeps its old terminal-only shape and no evidence block.
    assert checks["pose_end"]["evidence"]["samples"] == 1
    assert checks["pose_end"]["evidence"]["window"] == "end"
    assert "evidence" not in checks["speed_end"]


def test_missing_and_incomplete_every_step_watches_are_inconclusive():
    initial = _snapshot(0.0, _identity_bodies())
    phase = PhaseTelemetry(name="settle", kind="settle", requested_duration_s=0.1,
                           actual_steps=10, complete=True, start_time_s=0.0,
                           end_time_s=0.1)
    telemetry = Telemetry(boundaries={"initial": initial}, phases=[phase])
    acceptance = _acceptance([_pose_doc(window="max_over_phase")])

    evaluation, outcomes = _outcome(acceptance, telemetry)
    outcome = outcomes["pose"]
    assert evaluation.status == "INCONCLUSIVE"
    assert outcome.status == "INCONCLUSIVE"
    assert "no every-step pose watch" in outcome.detail

    # A watch that saw fewer states than the phase is not evidence of coverage.
    telemetry.watch_evidence["pose"] = {
        "kind": "relative_pose", "window": "max_over_phase", "phase": "settle",
        "samples": 9, "translation_m": 0.0, "translation_time_s": 0.0,
        "rotation_rad": 0.0, "rotation_time_s": 0.0,
        "end_translation_m": 0.0, "end_rotation_rad": 0.0, "end_time_s": 0.1,
    }
    evaluation, outcomes = _outcome(acceptance, telemetry)
    assert evaluation.status == "INCONCLUSIVE"
    assert "took 10 steps but the watch saw 9" in outcomes["pose"].detail

    # An incomplete phase is partial evidence, never a verdict.
    phase.complete = False
    telemetry.watch_evidence["pose"]["samples"] = 10
    evaluation, outcomes = _outcome(acceptance, telemetry)
    assert evaluation.status == "INCONCLUSIVE"
    assert "did not complete" in outcomes["pose"].detail


# --------------------------------------------------------------------------- 9. contact duration


def test_contact_duration_sums_multiple_points_and_ignores_body_order(drop_pass_run):
    summary = drop_pass_run["summary"]
    run_dir = drop_pass_run["run_dir"]
    checks = _checks_by_name(summary)
    steps = _phase_steps(summary)
    series, by_time = _state_force_series(run_dir)
    threshold = checks["contact"]["evidence"]["threshold_n"]
    episodes = _episodes(series, threshold)

    contract = checks["contact"]
    reverse = checks["contact_rev"]
    evidence = contract["evidence"]
    assert contract["status"] == "PASS"
    assert reverse["status"] == "PASS"
    for key in ("longest_s", "start_s", "end_s", "run_samples", "samples_above",
                "peak_force_n", "terminal_force_n", "samples"):
        assert reverse["evidence"][key] == pytest.approx(evidence[key], abs=1e-15), key

    # Coverage: reset state plus every integration step of the whole run.
    assert evidence["samples"] == 1 + sum(steps.values())
    assert len(episodes) >= 2
    longest = max(episodes, key=lambda item: item["longest_s"])
    assert evidence["longest_s"] == pytest.approx(longest["longest_s"], abs=1e-12)
    assert evidence["start_s"] == pytest.approx(longest["start_s"], abs=1e-12)
    assert evidence["end_s"] == pytest.approx(longest["end_s"], abs=1e-12)
    assert evidence["run_samples"] == longest["run_samples"]
    assert evidence["longest_s"] == pytest.approx(
        (evidence["run_samples"] - 1) * DT, abs=1e-12)
    # Two separated episodes: the brief impact excursion is not merged into the rest run.
    first_end = min(episode["end_s"] for episode in episodes
                    if episode is not longest)
    assert evidence["start_s"] > first_end
    first_above = min(time_s for time_s, force in series if force > threshold)
    last_above = max(time_s for time_s, force in series if force > threshold)
    assert evidence["start_s"] - first_end > 0.01
    assert evidence["longest_s"] < last_above - first_above
    # The 0.10 s phase boundary itself is a below-threshold interruption. It must not join
    # the impact episode to the rest episode nor add a step to either run.
    boundary_s = summary["phases"][1]["end_time_s"]
    boundary_force = next(force for time_s, force in series
                          if time_s == pytest.approx(boundary_s, abs=1e-12))
    assert boundary_force == 0.0
    assert evidence["start_s"] > boundary_s

    # Multi-point sum: at rest four points each sit below the threshold, their sum above it.
    terminal_time = max(by_time)
    individual = by_time[terminal_time]
    assert len(individual) == 4
    assert max(individual) < threshold
    assert sum(individual) > threshold
    assert evidence["terminal_force_n"] == pytest.approx(sum(individual), abs=1e-12)

    # The summed semantics is what produces the long run: a max-per-point reading would end
    # the sustained rest episode because every individual point is below the threshold.
    per_point = [(time_s, max(by_time[time_s]) if time_s in by_time else 0.0)
                 for time_s, _ in series]
    per_point_longest = max(episode["longest_s"]
                            for episode in _episodes(per_point, threshold))
    assert per_point_longest < 0.01
    assert evidence["longest_s"] > per_point_longest + 0.2

    # An isolated one-state excursion is 0.0 s.
    isolated = checks["contact_isolated"]
    assert isolated["status"] == "PASS"
    assert isolated["evidence"]["samples_above"] == 1
    assert isolated["evidence"]["longest_s"] == 0.0
    # contacts.csv rounds each point force; compare the sum at recorded precision.
    assert evidence["peak_force_n"] == pytest.approx(
        max(sum(forces) for forces in by_time.values()), rel=1e-9)


def test_contact_threshold_equality_does_not_count(drop_fail_run):
    summary = drop_fail_run["summary"]
    run_dir = drop_fail_run["run_dir"]
    threshold = drop_fail_run["peak_threshold"]
    check = _checks_by_name(summary)["contact_eq"]
    series, _ = _state_force_series(run_dir)
    strict_episodes = _episodes(series, threshold)

    assert check["status"] == "PASS"
    assert check["evidence"]["terminal_force_n"] < threshold
    # The threshold is exactly the recorded peak. If equality counted, at least that peak
    # state would be above; strict comparison leaves the run empty.
    assert check["evidence"]["peak_force_n"] == pytest.approx(
        threshold, rel=1e-15, abs=0.0)
    assert check["evidence"]["samples_above"] == 0
    assert check["evidence"]["run_samples"] == 0
    assert check["evidence"]["longest_s"] == 0.0
    # The raw contact rows agree with the peak within their recorded float precision.
    assert max(force for _, force in series) == pytest.approx(
        threshold, rel=1e-9)
    # The CSV's 12-digit rendering can exceed the exact peak by a few 1e-12 N; allow that
    # recorded precision, and still require no run once the rounding is excluded.
    assert _episodes(series, threshold + 1e-9) == []


def test_contact_duration_zero_contact_passes_and_missing_watch_is_inconclusive(lift_run):
    summary = lift_run["summary"]
    check = _checks_by_name(summary)["no_contact"]
    evidence = check["evidence"]
    steps = _phase_steps(summary)
    assert check["status"] == "PASS"
    assert evidence["longest_s"] == 0.0
    assert evidence["peak_force_n"] == 0.0
    assert evidence["terminal_force_n"] == 0.0
    assert evidence["samples"] == 1 + sum(steps.values())
    assert evidence["samples_above"] == 0

    # A missing watch must not be reported as a fabricated zero.
    acceptance = _acceptance([_contact_doc()])
    telemetry = Telemetry(boundaries={}, phases=[])
    evaluation, outcomes = _outcome(acceptance, telemetry)
    assert evaluation.status == "INCONCLUSIVE"
    assert outcomes["contact"].status == "INCONCLUSIVE"
    assert "fabricated" in outcomes["contact"].detail

    # Incomplete run coverage is also INCONCLUSIVE.
    telemetry = Telemetry(
        boundaries={},
        phases=[PhaseTelemetry(name="settle", kind="settle",
                               requested_duration_s=0.1, actual_steps=10,
                               complete=False)],
        watch_evidence={"contact": {"samples": 11}},
    )
    evaluation, outcomes = _outcome(acceptance, telemetry)
    assert evaluation.status == "INCONCLUSIVE"
    assert "did not complete" in outcomes["contact"].detail


# --------------------------------------------------------------------------- 10. near threshold


def test_near_threshold_band_is_opt_in_and_only_downgrades_a_pass():
    initial = _identity_bodies()
    endpoint = _identity_bodies(pos_b=(0.1004, 0.0, 0.0))
    telemetry = _synthetic_telemetry(initial, endpoint)
    pose = _pose_doc(max=0.00045, max_rotation_rad=1.0)

    # 0.0004 m is within 20% of the 0.00045 m bound: a PASS becomes INCONCLUSIVE.
    evaluation, outcomes = _outcome(_acceptance([pose], near=0.2), telemetry)
    assert evaluation.status == "INCONCLUSIVE"
    assert outcomes["pose"].status == "INCONCLUSIVE"
    assert outcomes["pose"].evidence["translation_near_threshold"] is True
    assert outcomes["pose"].evidence["near_threshold_fraction"] == 0.2
    assert outcomes["pose"].value == pytest.approx(0.0004, abs=1e-12)

    # Without the opt-in field the same value is a plain PASS.
    evaluation, outcomes = _outcome(_acceptance([pose]), telemetry)
    assert evaluation.status == "PASS"
    assert outcomes["pose"].status == "PASS"
    assert outcomes["pose"].evidence["translation_near_threshold"] is False

    # A real breach stays FAIL even with the band enabled.
    evaluation, outcomes = _outcome(
        _acceptance([_pose_doc(max=0.0002, max_rotation_rad=1.0)], near=0.2),
        telemetry)
    assert evaluation.status == "FAIL"
    assert outcomes["pose"].status == "FAIL"


def test_zero_bound_has_no_near_threshold_band():
    initial = _identity_bodies()
    endpoint = _identity_bodies()  # no motion at all
    telemetry = _synthetic_telemetry(initial, endpoint)
    acceptance = _acceptance([
        _pose_doc(max=0.0, max_rotation_rad=0.0),
        _translation_doc(lower=0.0, upper=0.0),
    ], near=0.2)
    evaluation, outcomes = _outcome(acceptance, telemetry)

    assert evaluation.status == "PASS"
    assert outcomes["pose"].status == "PASS"
    assert outcomes["trans"].status == "PASS"
    assert outcomes["pose"].evidence["translation_near_threshold"] is False
    assert outcomes["pose"].evidence["rotation_near_threshold"] is False
    assert outcomes["trans"].evidence["near_lower"] is False
    assert outcomes["trans"].evidence["near_upper"] is False


# --------------------------------------------------------------------------- 11. replay / tamper


def test_real_run_replays_and_matches_every_derived_value(drop_pass_run, tmp_path):
    summary = drop_pass_run["summary"]
    result = replay_run(drop_pass_run["run_dir"], tmp_path / "replay")
    assert summary["status"] == "PASS"
    assert result["status"] == "PASS"
    assert result["reproduced"] is True
    assert result["replay_status"] == "PASS"
    assert result["evaluation_comparison"]["ok"] is True
    assert result["evaluation_comparison"]["differences"] == []


def test_tampered_derived_record_is_not_trusted(drop_pass_run, tmp_path):
    source = tmp_path / "tampered"
    shutil.copytree(drop_pass_run["run_dir"], source)
    summary = json.loads((source / "summary.json").read_text(encoding="utf-8"))
    check = next(item for item in summary["checks"] if item["name"] == "pose_max")
    assert check["evidence"]["translation_m"] > 0.0
    check["evidence"]["translation_m"] = 0.0
    check["value"] = 0.0
    (source / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

    # Update the manifest entry exactly as the existing adversarial replay tests do.
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    manifest["artifacts"]["summary.json"] = {
        "sha256": _sha256(source / "summary.json"),
        "bytes": (source / "summary.json").stat().st_size,
    }
    (source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = replay_run(source, tmp_path / "tampered-replay")
    assert result["status"] != "PASS"
    assert result["reproduced"] is False
    assert result["evaluation_comparison"]["ok"] is False
    differences = result["evaluation_comparison"]["differences"]
    assert differences
    assert any("pose_max" in difference for difference in differences)
    assert any("translation_m" in difference for difference in differences)


# --------------------------------------------------------------------------- 12. live PASS/FAIL


def test_live_max_over_phase_bounds_fail_and_pass_on_the_real_run(drop_fail_run):
    summary = drop_fail_run["summary"]
    checks = _checks_by_name(summary)
    assert summary["status"] == "FAIL"

    pose = checks["pose_fail"]
    assert pose["kind"] == "relative_pose"
    assert pose["status"] == "FAIL"
    assert pose["evidence"]["translation_m"] > 0.01
    assert pose["evidence"]["translation_time_s"] < 0.11 - 1e-9
    assert pose["value"] == pytest.approx(
        pose["evidence"]["translation_m"], rel=1e-12)

    trans = checks["trans_fail"]
    assert trans["kind"] == "relative_translation"
    assert trans["status"] == "FAIL"
    assert trans["evidence"]["min_m"] < -0.001
    assert trans["evidence"]["min_time_s"] < 0.11 - 1e-9
    assert trans["value"] == pytest.approx(trans["evidence"]["min_m"], rel=1e-12)

    # At least one live PASS alongside the two real breaches.
    assert checks["speed_pass"]["status"] == "PASS"
    assert checks["speed_pass"]["evidence"]["samples"] == _phase_steps(
        summary)["settle"]


def test_live_reversed_gravity_lift_is_signed_up_and_drop_m_is_zero(lift_run):
    summary = lift_run["summary"]
    check = _checks_by_name(summary)["world_lift"]
    assert summary["status"] == "FAIL"
    assert check["status"] == "FAIL"
    assert check["evidence"]["terminal_m"] > 0.0003
    assert check["evidence"]["terminal_m"] < 0.0005
    assert check["evidence"]["drop_m"] == 0.0
    assert check["value"] == pytest.approx(
        check["evidence"]["terminal_m"], rel=1e-12)


# --------------------------------------------------------------------------- review-fix regressions


def test_body_speed_max_over_phase_rejects_reset_and_initial_phases():
    """A reset/initial phase has no post-step state to watch; reject before the run."""
    spec = _loader_spec()
    scenario = _loader_scenario()
    for phase in ("reset", "initial"):
        check = CheckSpec(name=f"speed_{phase}", kind="body_speed", body="box",
                          phase=phase, maximum=1.0, window="max_over_phase",
                          units="m/s")
        acceptance = AcceptanceSpec("reset_speed", (check,), ValiditySpec())
        with pytest.raises(ScenarioError, match="timed scenario phase"):
            resolve_references(scenario, acceptance, spec)


def test_zero_sample_phase_watch_is_inconclusive_not_a_format_error():
    """samples == 0 with None terminal/time fields must be a clean INCONCLUSIVE."""
    initial = _snapshot(0.0, _identity_bodies())
    phase = PhaseTelemetry(name="settle", kind="settle", requested_duration_s=0.1,
                           actual_steps=10, complete=True)
    telemetry = Telemetry(
        boundaries={"initial": initial},
        phases=[phase],
        watch_evidence={
            "pose": {
                "samples": 0, "translation_m": None, "translation_time_s": None,
                "rotation_rad": None, "rotation_time_s": None,
                "end_translation_m": None, "end_rotation_rad": None,
                "end_time_s": None,
            },
            "trans": {
                "samples": 0, "min_m": None, "min_time_s": None,
                "max_m": None, "max_time_s": None,
                "terminal_m": None, "terminal_time_s": None,
            },
            "speed": {
                "samples": 0, "speed_m_s": None, "time_s": None,
                "terminal_speed_m_s": None, "terminal_time_s": None,
            },
        },
    )
    acceptance = _acceptance([
        _pose_doc(name="pose", window="max_over_phase"),
        _translation_doc(name="trans", window="max_over_phase"),
        {"name": "speed", "kind": "body_speed", "body": "box",
         "phase": "settle", "max": 1.0, "units": "m/s",
         "window": "max_over_phase"},
    ])

    evaluation, outcomes = _outcome(acceptance, telemetry)
    assert evaluation.status == "INCONCLUSIVE"
    for name in ("pose", "trans", "speed"):
        assert outcomes[name].status == "INCONCLUSIVE"
        assert outcomes[name].value is None
        assert "recorded no integration state" in outcomes[name].detail


def test_rotation_only_fail_reports_radians_and_rotation_time():
    initial = _identity_bodies()
    endpoint = _identity_bodies()
    endpoint["box"] = ((0.1, 0.0, 0.0), _quat_yaw(0.5))
    telemetry = _synthetic_telemetry(initial, endpoint)
    acceptance = _acceptance([
        _pose_doc(name="rotation", max=0.001, max_rotation_rad=0.01)])

    evaluation, outcomes = _outcome(acceptance, telemetry)
    outcome = outcomes["rotation"]
    assert evaluation.status == "FAIL"
    assert outcome.status == "FAIL"
    assert outcome.value == pytest.approx(outcome.evidence["rotation_rad"], abs=1e-12)
    assert outcome.value == pytest.approx(0.5, abs=1e-12)
    assert outcome.units == "rad"
    assert outcome.time_s == outcome.evidence["rotation_time_s"]
    assert outcome.evidence["translation_m"] == pytest.approx(0.0, abs=1e-12)
    assert outcome.evidence["rotation_rad"] == pytest.approx(0.5, abs=1e-12)


def test_translation_only_fail_still_reports_metres_and_translation_time():
    initial = _identity_bodies()
    endpoint = _identity_bodies(pos_b=(0.15, 0.0, 0.0))
    telemetry = _synthetic_telemetry(initial, endpoint)
    acceptance = _acceptance([
        _pose_doc(name="translation", max=0.01, max_rotation_rad=1.0)])

    evaluation, outcomes = _outcome(acceptance, telemetry)
    outcome = outcomes["translation"]
    assert evaluation.status == "FAIL"
    assert outcome.status == "FAIL"
    assert outcome.value == pytest.approx(
        outcome.evidence["translation_m"], abs=1e-12)
    assert outcome.value == pytest.approx(0.05, abs=1e-12)
    assert outcome.units == "m"
    assert outcome.time_s == outcome.evidence["translation_time_s"]
    assert outcome.evidence["rotation_rad"] == pytest.approx(0.0, abs=1e-12)


def test_near_threshold_detail_names_the_upper_bound_not_the_lower():
    initial = _identity_bodies()
    endpoint = _identity_bodies(pos_b=(0.1003, 0.0, 0.0))
    telemetry = _synthetic_telemetry(initial, endpoint)
    acceptance = _acceptance([
        _translation_doc(name="band", axis="x", frame="body_a",
                         lower=0.0, upper=0.00035)], near=0.2)

    evaluation, outcomes = _outcome(acceptance, telemetry)
    outcome = outcomes["band"]
    assert evaluation.status == "INCONCLUSIVE"
    assert outcome.status == "INCONCLUSIVE"
    assert outcome.value == pytest.approx(0.0003, abs=1e-12)
    assert outcome.evidence["near_upper"] is True
    assert outcome.evidence["near_lower"] is False
    assert "upper bound" in outcome.detail
    assert "lower bound" not in outcome.detail


def test_world_z_drop_evidence_tracks_reported_worst_not_terminal():
    initial = _snapshot(0.0, _identity_bodies())
    phase = PhaseTelemetry(name="settle", kind="settle", requested_duration_s=0.1,
                           actual_steps=10, complete=True)
    watch = {
        "samples": 10,
        "min_m": -0.08, "min_time_s": 0.06,
        "max_m": -0.06, "max_time_s": 0.02,
        "terminal_m": -0.07, "terminal_time_s": 0.10,
    }
    telemetry = Telemetry(
        boundaries={"initial": initial}, phases=[phase],
        watch_evidence={"drop": dict(watch)})
    acceptance = _acceptance([
        _translation_doc(name="drop", axis="z", frame="world",
                         lower=-0.085, upper=-0.05, window="max_over_phase")])

    evaluation, outcomes = _outcome(acceptance, telemetry)
    outcome = outcomes["drop"]
    assert evaluation.status == "PASS"
    assert outcome.status == "PASS"
    # The reported worst is the lower sample, and the terminal differs from it.
    assert outcome.value == pytest.approx(-0.08, abs=1e-12)
    assert outcome.time_s == outcome.evidence["min_time_s"]
    assert outcome.evidence["terminal_m"] == pytest.approx(-0.07, abs=1e-12)
    assert outcome.value != outcome.evidence["terminal_m"]
    assert outcome.evidence["drop_m"] == pytest.approx(
        max(0.0, -outcome.value), abs=1e-12)
    assert f"{outcome.evidence['drop_m']:.9g}" in outcome.detail
    assert "positive downward drop" in outcome.detail

    # The same numbers on a non-world frame retain no downward-drop claim.
    local_acceptance = _acceptance([
        _translation_doc(name="drop", axis="z", frame="body_a",
                         lower=-0.085, upper=-0.05, window="max_over_phase")])
    local_eval, local_out = _outcome(local_acceptance, telemetry)
    local = local_out["drop"]
    assert local_eval.status == "PASS"
    assert local.status == "PASS"
    assert local.value == pytest.approx(-0.08, abs=1e-12)
    assert local.evidence["drop_m"] is None
    assert "positive downward drop" not in local.detail


def test_nonfinite_assembly_options_are_rejected_before_a_run():
    spec = build_fixture("drop_box", DT)
    scenario = _scenario("options", (
        PhaseSpec("reset", "reset"), PhaseSpec("settle", "settle", 0.01)))
    acceptance = AcceptanceSpec("options", (
        CheckSpec(name="speed", kind="body_speed", body="box", phase="settle",
                  maximum=10.0, units="m/s"),), ValiditySpec())
    for options_text in ("gain = inf\n", "gain = nan\n",
                         "gains = [1.0, inf]\n"):
        with pytest.raises(ScenarioError, match="must be finite"):
            run_assembly(spec, scenario, acceptance, None,
                         options_text=options_text)


def test_live_world_frame_max_over_phase_watch_and_replay(drop_pass_run, tmp_path):
    summary = drop_pass_run["summary"]
    run_dir = drop_pass_run["run_dir"]
    check = _checks_by_name(summary)["trans_world_max"]
    evidence = check["evidence"]
    steps = _phase_steps(summary)

    assert check["status"] == "PASS"
    assert check["kind"] == "relative_translation"
    assert evidence["frame"] == "world"
    assert evidence["window"] == "max_over_phase"
    assert evidence["samples"] == steps["settle"]
    assert evidence["min_m"] == pytest.approx(-0.040548039844, rel=1e-9)
    assert evidence["min_time_s"] == pytest.approx(0.092, abs=1e-9)
    assert evidence["min_time_s"] < 0.10 - 1e-9
    assert evidence["max_m"] == pytest.approx(-4.9e-06, rel=0.05)
    assert evidence["max_time_s"] == pytest.approx(0.001, abs=1e-9)
    assert evidence["terminal_m"] == pytest.approx(-0.039986469174, rel=1e-9)
    assert evidence["terminal_m"] != evidence["min_m"]
    assert evidence["drop_m"] == pytest.approx(
        max(0.0, -check["value"]), abs=1e-12)

    result = replay_run(run_dir, tmp_path / "world-replay")
    assert result["status"] == "PASS"
    assert result["reproduced"] is True
    assert result["evaluation_comparison"]["differences"] == []


def test_timed_from_phase_reference_uses_the_phase_end_boundary(drop_fail_run):
    checks = _checks_by_name(drop_fail_run["summary"])
    from_settle = checks["hold_from_settle"]
    from_initial = checks["hold_from_initial"]

    assert from_settle["status"] == "PASS"
    assert from_settle["evidence"]["from_phase"] == "settle"
    assert from_settle["evidence"]["to_phase"] == "hold"
    assert abs(from_settle["value"]) <= 0.001
    assert from_settle["evidence"]["samples"] == 1

    assert from_initial["status"] == "FAIL"
    assert from_initial["evidence"]["from_phase"] == "initial"
    assert from_initial["value"] == pytest.approx(-0.0400005325, rel=1e-6)
    assert from_initial["value"] < -0.03
    assert from_initial["evidence"]["samples"] == 1


def test_inconclusive_near_band_run_replays_without_differences(near_run, tmp_path):
    summary = near_run["summary"]
    checks = _checks_by_name(summary)
    assert summary["status"] == "INCONCLUSIVE"
    assert checks["pose_near"]["status"] == "INCONCLUSIVE"
    assert checks["pose_near"]["evidence"]["translation_near_threshold"] is True
    assert checks["trans_near"]["status"] == "INCONCLUSIVE"
    assert checks["trans_near"]["evidence"]["near_lower"] is True

    result = replay_run(near_run["run_dir"], tmp_path / "near-replay")
    assert result["status"] == "INCONCLUSIVE"
    assert result["replay_status"] == "INCONCLUSIVE"
    assert result["reproduced"] is True
    assert result["evaluation_comparison"]["ok"] is True
    assert result["evaluation_comparison"]["differences"] == []


def test_rotation_near_band_is_opt_in():
    initial = _identity_bodies()
    endpoint = _identity_bodies()
    endpoint["box"] = ((0.1, 0.0, 0.0), _quat_yaw(0.4))
    telemetry = _synthetic_telemetry(initial, endpoint)
    # Rotation 0.4 rad against a 0.45 rad bound: inside 20% (0.09 rad).
    check = _pose_doc(name="rotation", max=0.0, max_rotation_rad=0.45)

    evaluation, outcomes = _outcome(_acceptance([check], near=0.2), telemetry)
    outcome = outcomes["rotation"]
    assert evaluation.status == "INCONCLUSIVE"
    assert outcome.status == "INCONCLUSIVE"
    assert outcome.evidence["rotation_near_threshold"] is True
    assert outcome.evidence["translation_near_threshold"] is False
    assert outcome.units == "rad"
    assert outcome.value == pytest.approx(0.4, abs=1e-12)

    evaluation, outcomes = _outcome(_acceptance([check]), telemetry)
    assert evaluation.status == "PASS"
    assert outcomes["rotation"].status == "PASS"


def test_translation_near_band_with_symmetric_nonzero_bounds_names_upper():
    initial = _identity_bodies()
    endpoint = _identity_bodies(pos_b=(0.1009, 0.0, 0.0))
    telemetry = _synthetic_telemetry(initial, endpoint)
    acceptance = _acceptance([
        _translation_doc(name="band", axis="x", frame="body_a",
                         lower=-0.001, upper=0.001)], near=0.2)

    evaluation, outcomes = _outcome(acceptance, telemetry)
    outcome = outcomes["band"]
    assert evaluation.status == "INCONCLUSIVE"
    assert outcome.status == "INCONCLUSIVE"
    assert outcome.value == pytest.approx(0.0009, abs=1e-12)
    assert outcome.evidence["near_upper"] is True
    assert outcome.evidence["near_lower"] is False
    assert "upper bound" in outcome.detail
    assert "lower bound" not in outcome.detail


# --------------------------------------------------------------------------- remediation R1-R3


def _rewrite_summary(path, mutate) -> None:
    """Apply ``mutate`` to summary.json and refresh its manifest hash/bytes."""
    summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
    mutate(summary)
    text = json.dumps(summary)
    text = text.replace("-Infinity", "-1e999").replace("Infinity", "1e999")
    (path / "summary.json").write_text(text, encoding="utf-8")
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    manifest["artifacts"]["summary.json"] = {
        "sha256": _sha256(path / "summary.json"),
        "bytes": (path / "summary.json").stat().st_size,
    }
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _watch_check(summary: dict, name: str = "pose_max") -> dict:
    return next(check for check in summary["checks"] if check["name"] == name)


def test_nonfinite_summary_evidence_is_not_trusted_by_replay(drop_pass_run, tmp_path):
    variants = {
        "value_positive": lambda check: (
            check.__setitem__("value", float("inf")),
            check["evidence"].__setitem__("translation_m", float("inf"))),
        "value_negative": lambda check: (
            check.__setitem__("value", float("-inf")),
            check["evidence"].__setitem__("translation_m", float("-inf"))),
        "time_positive": lambda check: (
            check.__setitem__("time_s", float("inf")),
            check["evidence"].__setitem__("translation_time_s", float("inf"))),
    }
    for label, mutate in variants.items():
        source = tmp_path / label
        shutil.copytree(drop_pass_run["run_dir"], source)
        _rewrite_summary(source, lambda summary: mutate(_watch_check(summary)))
        assert "1e999" in (source / "summary.json").read_text(encoding="utf-8")

        result = replay_run(source, tmp_path / f"{label}-replay")
        assert result["status"] != "PASS"
        assert result["reproduced"] is False
        assert result["evaluation_comparison"]["ok"] is False
        differences = result["evaluation_comparison"]["differences"]
        assert differences
        assert any("non-finite" in difference for difference in differences), differences


def test_compare_watch_number_rejects_nonfinite_and_huge_values():
    # Private replay comparator is imported explicitly: this pins the R1 numeric guard.
    from cadkit.physics.replay import _compare_watch_number

    cases = [
        (float("inf"), 1.0),
        (1.0, float("inf")),
        (float("-inf"), 1.0),
        (float("nan"), float("nan")),
        (10 ** 400, 1.0),
        (float("inf"), float("inf")),
    ]
    for left, right in cases:
        differences: list[str] = []
        _compare_watch_number(left, right, "path", differences,
                              time_like=False, time_atol=0.0)
        assert differences, (left, right)
        assert any("non-finite" in difference or "unrepresentable" in difference
                   for difference in differences), (left, right, differences)

    differences = []
    _compare_watch_number(1.0, 1.0 + 1e-12, "path", differences,
                          time_like=False, time_atol=0.0)
    assert differences == []


def test_speed_and_contact_near_bands_are_opt_in_and_replay(
        speed_contact_near_runs, tmp_path):
    near = speed_contact_near_runs["near"]
    plain = speed_contact_near_runs["plain"]
    breach = speed_contact_near_runs["breach"]
    measured_speed = speed_contact_near_runs["measured_speed"]
    measured_duration = speed_contact_near_runs["measured_duration"]

    near_checks = _checks_by_name(near["summary"])
    assert near["summary"]["status"] == "INCONCLUSIVE"
    assert near_checks["speed_band"]["status"] == "INCONCLUSIVE"
    assert near_checks["contact_band"]["status"] == "INCONCLUSIVE"
    assert near_checks["speed_band"]["evidence"]["near_threshold"] is True
    assert near_checks["contact_band"]["evidence"]["near_threshold"] is True
    assert near_checks["speed_band"]["evidence"]["bound_m_s"] == pytest.approx(
        measured_speed / 0.9, rel=1e-12)
    assert near_checks["contact_band"]["evidence"]["bound_s"] == pytest.approx(
        measured_duration / 0.9, rel=1e-12)
    assert near_checks["speed_band"]["value"] == pytest.approx(
        measured_speed, rel=1e-9)
    assert near_checks["contact_band"]["value"] == pytest.approx(
        measured_duration, rel=1e-9)

    result = replay_run(near["run_dir"], tmp_path / "speed-contact-near-replay")
    assert result["status"] == "INCONCLUSIVE"
    assert result["replay_status"] == "INCONCLUSIVE"
    assert result["reproduced"] is True
    assert result["evaluation_comparison"]["differences"] == []

    plain_checks = _checks_by_name(plain["summary"])
    assert plain["summary"]["status"] == "PASS"
    assert plain_checks["speed_band"]["status"] == "PASS"
    assert plain_checks["contact_band"]["status"] == "PASS"
    assert plain_checks["speed_band"]["evidence"]["near_threshold"] is False
    assert plain_checks["contact_band"]["evidence"]["near_threshold"] is False

    breach_checks = _checks_by_name(breach["summary"])
    assert breach["summary"]["status"] == "FAIL"
    assert breach_checks["speed_band"]["status"] == "FAIL"
    assert breach_checks["contact_band"]["status"] == "FAIL"


def test_zero_contact_bound_has_no_band(lift_run):
    check = _checks_by_name(lift_run["summary"])["no_contact"]
    assert lift_run["summary"]["status"] == "FAIL"  # world_lift is a deliberate breach
    assert check["status"] == "PASS"
    assert check["evidence"]["bound_s"] == 0.0
    assert check["evidence"]["near_threshold"] is False


def _bad_r3_checks():
    pose_ok = dict(kind="relative_pose", body_a="floor", body_b="box",
                   phase="settle", maximum=0.01, max_rotation_rad=0.01, units="m")
    trans_ok = dict(kind="relative_translation", body_a="floor", body_b="box",
                    from_phase="initial", to_phase="settle", axis="z",
                    lower=-0.01, upper=0.01, units="m")
    return [
        ("world_x", CheckSpec(name="bad", **{**trans_ok, "frame": "world",
                                              "axis": "x"}),
         "only defined for axis='z'"),
        ("world_y", CheckSpec(name="bad", **{**trans_ok, "frame": "world",
                                              "axis": "y"}),
         "only defined for axis='z'"),
        ("contact_window", CheckSpec(name="bad", kind="contact_duration",
                                     body_a="floor", body_b="box",
                                     force_threshold_n=0.01, maximum=0.1,
                                     window="max_over_phase", units="s"),
         "window must be 'end'"),
        ("pose_missing_rotation", CheckSpec(name="bad", **{**pose_ok,
                                                            "max_rotation_rad": None}),
         "max_rotation_rad must be a number"),
        ("trans_lower_upper", CheckSpec(name="bad", **{**trans_ok,
                                                       "lower": 0.01, "upper": -0.01}),
         "lower must not exceed upper"),
        ("trans_missing_lower", CheckSpec(name="bad", **{**trans_ok, "lower": None}),
         "lower must be a number"),
        ("trans_missing_upper", CheckSpec(name="bad", **{**trans_ok, "upper": None}),
         "upper must be a number"),
        ("pose_wrong_units", CheckSpec(name="bad", **{**pose_ok, "units": "rad"}),
         "units must be 'm'"),
        ("contact_wrong_units", CheckSpec(name="bad", kind="contact_duration",
                                          body_a="floor", body_b="box",
                                          force_threshold_n=0.01, maximum=0.1,
                                          units="m"), "units must be 's'"),
        ("pose_nonfinite", CheckSpec(name="bad", **{**pose_ok,
                                                    "maximum": float("inf")}),
         "max must be finite"),
        ("same_body", CheckSpec(name="bad", **{**pose_ok, "body_a": "box"}),
         "must differ"),
        ("legacy_window", CheckSpec(name="bad", kind="penetration_bound",
                                    maximum=0.01, units="m",
                                    window="max_over_phase"),
         "window is only valid"),
    ]


@pytest.mark.parametrize("label,check,match", _bad_r3_checks(),
                         ids=[item[0] for item in _bad_r3_checks()])
def test_typed_malformed_criteria_are_rejected_before_a_run(
        label, check, match, tmp_path):
    # Construction is intentionally permissive; rejection happens at admission.
    scenario = _scenario(f"r3_{label}", _DROP_PHASES)
    acceptance = AcceptanceSpec(f"r3_{label}", (check,), ValiditySpec())
    outdir = tmp_path / f"rejected-{label}"
    with pytest.raises(ScenarioError, match=match):
        run_scenario(scenario, acceptance, outdir)
    assert not outdir.exists()


def test_tampered_plan_timestep_cannot_widen_replay_time_tolerance(
        drop_pass_run, tmp_path):
    """Replay time tolerance must come from the verified model, not summary["plan"]."""

    def tamper(summary, timestep):
        summary["plan"]["timestep_s"] = timestep
        check = _watch_check(summary)
        check["time_s"] = 123.0
        check["evidence"]["translation_time_s"] = -77.0
        check["evidence"]["rotation_time_s"] = 5000.0
        check["evidence"]["end_time_s"] = 123.0

    for label, timestep in (("infinite", float("inf")), ("huge", 1.0e6)):
        source = tmp_path / label
        shutil.copytree(drop_pass_run["run_dir"], source)
        _rewrite_summary(source, lambda summary, value=timestep:
                         tamper(summary, value))
        result = replay_run(source, tmp_path / f"{label}-replay")
        assert result["status"] != "PASS"
        assert result["reproduced"] is False
        differences = result["evaluation_comparison"]["differences"]
        assert differences
        assert any("time_s" in difference for difference in differences), differences

    control = replay_run(drop_pass_run["run_dir"], tmp_path / "control-replay")
    assert control["status"] == "PASS"
    assert control["reproduced"] is True
    assert control["evaluation_comparison"]["differences"] == []
