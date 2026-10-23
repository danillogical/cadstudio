"""Independent S0 verification for M5a-1: plan clauses 5.2-5.4 and 6.1, not the implementation.

This module is deliberately written from ``docs/mujoco-m5a-plan.md`` sections 5.2-5.4 (and the
S0 evidence packet), and from the actual CAD helpers. It does not import the implementer's
tests, does not trust the numbers already written in the frozen JSON, and never calls
``reset_state`` for anything except a cross-check of its own derivation.

Covered clauses, in the order of the ticket:

1. Thresholds, body ordering, sign and units (plan 5.3 table and its sign rules; 5.4 near
   threshold): ``0.20 deg`` is recomputed in radians here; ``body_drop`` must be
   ``body_a=chassis, body_b=body`` so a fall is negative; contact checks must use
   ``window="end"`` with no phase fields; every bound is a metre/second value, never mm/deg.
2. All-five resets from ``linkage_from``/``phi_for_button_fraction``/``pose_at_phi``, plus the
   naive linear quarter-stroke negative of plan 5.2 (>= 1.3 mm wrong at f=0.25 and f=0.75).
3. No actuation in the eight scenarios: phase kinds/durations, zero effort/ctrl, empty
   actuator sets and zero ``qfrc_applied`` in the archived states.
4. Every-step and full-hold retention at the declared timestep, including the terminal hold
   state (plan 5.4: ``sampling_interval_s = timestep_s``, full 0.5 s hold retained).
5. Budgets derived from each scenario's own dt, and no truncation (declared vs actual rows,
   ``stopped``/``initial_rejected`` false).
6. Worst-over-hold vs end-boundary distinction for ``relative_pose``/``relative_translation``,
   recomputed from ``trace.csv`` with the plan's attached-local formula.
7. Valid FAIL preserved, invalid run INCONCLUSIVE and never PASS (plan 5.3 validity row, 5.4
   "near-threshold/validity" rules), on real evidence and on synthetic summaries in ``tmp_path``.
8. Replay identity for ``replay_s0_f000``: reproduced, zero state difference, empty evaluation
   differences, source status preserved, and never reported as PASS.
9. Evidence completeness: the per-run artifact set and hashes, finite checkpoints bound to the
   state archive, and the preflight's all-five audits.

Generated evidence is an optional prerequisite, not a source file: ``out/`` is git-ignored and
absent from a clean checkout. The prerequisite is the whole generated evidence set — the S0
runs/replay/preflight tree and the accepted adapter/static compiled audits the preflight
cross-checks. Clauses 1-3 (thresholds, resets, scenario declarations) and the synthetic
``tmp_path`` cases need no generated evidence and always run. Every clause that reads a run,
replay or preflight artifact first calls ``_require_generated_evidence``, which skips **only**
when the whole set is absent. A set that exists but is incomplete, truncated, unreadable, or a
dangling symlink is not an optional prerequisite: those tests fail loudly, and nothing here
catches ``FileNotFoundError`` or ``Exception`` to hide it.

Run with the optional physics extra::

    uv run --frozen --extra physics pytest tests/test_pocky_physics_s0_independent.py -q
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
import pytest

from cadkit.physics.scenario import load_acceptance, load_scenario
from projects.pocky.geometry.linkage import (
    linkage_from,
    phi_for_button_fraction,
    pose_at_phi,
)
from projects.pocky.params import load_params
from projects.pocky.physics import report
from projects.pocky.physics.assembly import reset_state

REPO_ROOT = Path(__file__).resolve().parents[1]
S0_ROOT = REPO_ROOT / "out" / "mujoco-m5a" / "s0"
#: The S0 preflight cross-checks the accepted adapter/static compiled audits, a second
#: git-ignored generated tree. Both are part of the same optional prerequisite.
COMPILED_ROOT = REPO_ROOT / "out" / "mujoco-m5a" / "adapter-static" / "compiled"
RUNS_ROOT = S0_ROOT / "runs"
REPLAY_ROOT = S0_ROOT / "replay_s0_f000"
PREFLIGHT_PATH = S0_ROOT / "preflight" / "preflight.json"
SCENARIO_DIR = REPO_ROOT / "projects" / "pocky" / "physics" / "scenarios"
ACCEPTANCE_PATH = REPO_ROOT / "projects" / "pocky" / "physics" / "s0_acceptance.json"

#: Plan 5.2 case table: five initial fractions plus spring low/high and half dt.
RUN_STEMS = (
    "s0_f000", "s0_f025", "s0_f050", "s0_f075", "s0_f100",
    "s0_spring_low", "s0_spring_high", "s0_half_dt",
)
FRACTION_STEMS = ("s0_f000", "s0_f025", "s0_f050", "s0_f075", "s0_f100")

#: Plan 5.2 reset table, transcribed to nine decimals (fraction -> crank rad, rod m, pusher m).
PLAN_RESET_TABLE = {
    0.00: (0.000000000, 0.000000000, 0.000000000),
    0.25: (-0.242563874, -0.005773503, 0.011132495),
    0.50: (-0.523598776, -0.011547005, 0.025000000),
    0.75: (-0.804633677, -0.017320508, 0.038867505),
    1.00: (-1.047197551, -0.023094011, 0.050000000),
}
#: Plan 5.2: the linear pusher quarter stroke misses by at least 1.367 mm.
LINEAR_QUARTER_ERROR_MM = 1.3675049056307252
LINEAR_NEGATIVE_FLOOR_MM = 1.3

#: Plan 5.3: the frozen S0 thresholds, as the plan states them (not read from the JSON).
PLAN_MAX_TRANSLATION_M = 0.00020
#: Plan 5.3: "chassis/floor 1 mm and 0.20 deg bound the analytic floor contact".
PLAN_GROUNDED_MAX_M = 0.001
#: Plan 5.3: each bound relative check's own translation bound, in metres.
PLAN_POSE_BOUNDS_M = {
    "body_pose_retained": PLAN_MAX_TRANSLATION_M,
    "chassis_grounded": PLAN_GROUNDED_MAX_M,
}
PLAN_MAX_ROTATION_RAD = 0.20 * math.pi / 180.0
PLAN_DROP_BOUND_M = 0.00010
PLAN_CONTACT_THRESHOLD_N = 0.0715
PLAN_CONTACT_MAX_S = 0.20
PLAN_GROUNDED_MAX_M = 0.001
PLAN_SPEED_MAX_M_S = 0.001
PLAN_PENETRATION_MAX_M = 0.0002
PLAN_NEAR_THRESHOLD_FRACTION = 0.2
#: Plan 5.3: 5% of the 145.89 g body+lip hanging group, versus 0.0684 N for the body alone.
HANGING_GROUP_KG = 0.14589
GRAVITY_M_S2 = 9.80665
BODY_ONLY_FIVE_PERCENT_N = 0.0684
#: Plan 5.2/5.4: settle 3.0 s then a 0.5 s zero-input hold.
SETTLE_S = 3.0
HOLD_S = 0.5
TOTAL_S = SETTLE_S + HOLD_S
BASE_DT_S = 1.0e-3
HALF_DT_S = 5.0e-4
#: Generic runner contact-row allowance per declared trace row (cadkit/physics/runner.py:958).
CONTACT_ROWS_PER_TRACE_ROW = 16
#: Contact pairs frozen by plan 5.3 (body and lip against each moving part).
CONTACT_PAIRS = (
    ("body", "pusher"), ("body", "rod"), ("body", "crank"),
    ("lip", "pusher"), ("lip", "rod"), ("lip", "crank"),
)
#: Plan 5.3: S0 check name -> SI units the plan assigns.
CHECK_UNITS = {
    "body_pose_retained": "m",
    "body_drop": "m",
    "chassis_grounded": "m",
    "settled_body": "m/s",
    "settled_lip": "m/s",
    "penetration": "m",
    **{f"{a}_on_{b}": "s" for a, b in CONTACT_PAIRS},
}


# ----------------------------------------------------------------------------- helpers
def _expected_dt(stem: str) -> float:
    return HALF_DT_S if stem.endswith("half_dt") else BASE_DT_S


def _required_steps(stem: str) -> int:
    return int(round(TOTAL_S / _expected_dt(stem)))


def _run(stem: str) -> Path:
    return RUNS_ROOT / stem


def _require_generated_evidence(root: Path = S0_ROOT) -> None:
    """Skip only when the entire generated evidence set is absent.

    ``out/`` is git-ignored, so a clean checkout has no evidence to read. That absence is the
    one optional prerequisite this module recognises, and it covers both generated trees the
    module reads: the S0 runs/replay/preflight under ``S0_ROOT`` and the accepted
    adapter/static compiled audits the preflight cross-checks under ``COMPILED_ROOT``. A tree
    that exists but lacks an artifact is a broken set, not an absent one, so it is left to
    fail: no broad ``FileNotFoundError``/``Exception`` handling and no per-file skip. A
    non-directory, or a dangling symlink, where the evidence root belongs is broken evidence
    too, not absence.
    """
    if not root.is_symlink() and not root.exists():
        pytest.skip(
            f"optional generated evidence absent: {root} does not exist. The S0 runs are "
            "git-ignored build output, not source; generate them with the S0 packet's "
            "out/mujoco-m5a/s0/scripts/run_s0.sh, or run only the conformance cases."
        )
    assert root.is_dir(), f"broken evidence: {root} exists but is not a directory"
    assert COMPILED_ROOT.is_dir(), (
        f"broken evidence: {COMPILED_ROOT} is missing; the S0 preflight cross-checks the "
        "accepted adapter/static compiled audits"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@lru_cache(maxsize=None)
def _summary(stem: str) -> dict:
    return json.loads((_run(stem) / "summary.json").read_text(encoding="utf-8"))


def _evidence(summary: dict, name: str) -> dict:
    for check in summary["checks"]:
        if check["name"] == name:
            assert isinstance(check.get("evidence"), dict), f"{name} carries no evidence"
            return check["evidence"]
    raise AssertionError(f"summary has no check named {name!r}")


def _check(summary: dict, name: str) -> dict:
    for check in summary["checks"]:
        if check["name"] == name:
            return check
    raise AssertionError(f"summary has no check named {name!r}")


@lru_cache(maxsize=None)
def _states(stem: str) -> dict:
    with np.load(_run(stem) / "states.npz", allow_pickle=False) as archive:
        return {
            "time": np.array(archive["time"]),
            "step_index": np.array(archive["step_index"]),
            "phase_index": np.array(archive["phase_index"]),
            "phase_names": [str(name) for name in archive["phase_names"]],
            "qfrc_applied": np.array(archive["qfrc_applied"]),
            "transition_qfrc_applied": np.array(archive["transition_qfrc_applied"]),
            "transition_xfrc_applied": np.array(archive["transition_xfrc_applied"]),
            "transition_ctrl": np.array(archive["transition_ctrl"]),
            "qpos": np.array(archive["qpos"]),
            "ctrl_shape": tuple(archive["ctrl"].shape),
            "act_shape": tuple(archive["act"].shape),
            "timestep_s": float(archive["timestep_s"]),
            "integration_state": np.array(archive["integration_state"]),
        }


@lru_cache(maxsize=None)
def _trace(stem: str) -> dict:
    """Parse only the columns this module needs, from the run's own ``trace.csv``."""
    bodies = ("body", "chassis", "floor_world")
    wanted = ["state_time_s", "phase", "step", "ncon"]
    for body in bodies:
        wanted += [f"body_pos:{body}.{axis} (m)" for axis in "xyz"]
        wanted += [f"body_quat:{body}.{axis}" for axis in "wxyz"]
    with (_run(stem) / "trace.csv").open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        index = {name: position for position, name in enumerate(header)}
        missing = [name for name in wanted if name not in index]
        assert not missing, f"{stem}: trace.csv lacks {missing}"
        rows = list(reader)
    columns = {name: [row[index[name]] for row in rows] for name in wanted}

    def numeric(name: str) -> np.ndarray:
        return np.array([float(value) for value in columns[name]], dtype=float)

    out = {
        "time": numeric("state_time_s"),
        "step": np.array([int(value) for value in columns["step"]], dtype=int),
        "ncon": np.array([int(value) for value in columns["ncon"]], dtype=int),
        "phase": np.array(columns["phase"], dtype=object),
        "pos": {body: np.stack([numeric(f"body_pos:{body}.{axis} (m)") for axis in "xyz"], 1)
                for body in bodies},
        "quat": {body: np.stack([numeric(f"body_quat:{body}.{axis}") for axis in "wxyz"], 1)
                 for body in bodies},
        "rows": len(rows),
        "header": tuple(header),
    }
    assert out["rows"] == len(out["time"])
    return out


def _rotation_matrix(quat: np.ndarray) -> np.ndarray:
    """Body-to-world rotation matrices (wxyz), normalized row-wise."""
    q = np.asarray(quat, dtype=float)
    q = q / np.linalg.norm(q, axis=1)[:, None]
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    return np.stack([
        np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], 1),
        np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], 1),
        np.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], 1),
    ], 1)


def _attached_local_delta(trace: dict, body_a: str, body_b: str,
                          mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Plan 5.3: p_rel = R_a^T (p_b - p_a); Δp against the initial row; ΔR likewise."""
    ra = _rotation_matrix(trace["quat"][body_a])
    rb = _rotation_matrix(trace["quat"][body_b])
    p_rel = np.einsum("nij,nj->ni", np.transpose(ra, (0, 2, 1)),
                      trace["pos"][body_b] - trace["pos"][body_a])
    r_rel = np.einsum("nij,njk->nik", np.transpose(ra, (0, 2, 1)), rb)
    delta_p = np.linalg.norm(p_rel[mask] - p_rel[0], axis=1)
    rotation = r_rel[mask] @ r_rel[0].T
    scalar = np.sqrt(np.maximum(0.0, (np.trace(rotation, axis1=1, axis2=2) + 1.0) / 4.0))
    theta = 2.0 * np.arccos(np.clip(np.abs(scalar), 0.0, 1.0))
    return delta_p, theta


def _hold_mask(trace: dict) -> np.ndarray:
    return trace["phase"] == "hold"


def _cad_reset(fraction: float) -> dict[str, float]:
    """Plan 5.2 reset formulas, derived here from the CAD helpers (not from reset_state)."""
    params = load_params()
    link = linkage_from(params)
    rest = pose_at_phi(link, link.phi0)
    pose = pose_at_phi(link, phi_for_button_fraction(link, fraction))
    return {
        "crank_phi": pose.phi - link.phi0,
        "rod_x": -pose.button_travel / 1000.0,
        "pusher_x": (pose.face_x - rest.face_x) / 1000.0,
    }


def _scenario_paths() -> list[Path]:
    return sorted(SCENARIO_DIR.glob("s0_*.json"))


def _status_from_evidence(validity_ok: bool, statuses: list[str]) -> str:
    """Plan 5.3/5.4 precedence, restated independently of the evaluator's code."""
    if not validity_ok:
        return "INCONCLUSIVE"
    if any(status == "INCONCLUSIVE" for status in statuses):
        return "INCONCLUSIVE"
    if any(status == "FAIL" for status in statuses):
        return "FAIL"
    if statuses and all(status == "PASS" for status in statuses):
        return "PASS"
    return "INCONCLUSIVE"


def _drop_fails(delta_z: float, lower: float, upper: float) -> bool:
    """Plan 5.3: the signed world-z change must lie inside [lower, upper]; both sides fail."""
    return delta_z < lower or delta_z > upper


def _write_synthetic_run(directory: Path, *, status: str, validity_ok: bool,
                         checks: list[dict]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    summary = {
        "status": status,
        "validity": {
            "ok": validity_ok,
            "reasons": [] if validity_ok else [{
                "stage": "validity",
                "reason": "peak penetration 0.0003 m exceeds declared bound 0.0002 m",
                "time_s": None,
            }],
        },
        "checks": checks,
        "phases": [],
        "solver": {"bodies": {}},
        "physical_inputs": {"gravity_m_s2": [0.0, 0.0, -GRAVITY_M_S2]},
        "telemetry": {},
        "plan": {},
        "state_archive": {},
        "metrics": {},
        "scenario": {"id": "synthetic"},
    }
    (directory / "summary.json").write_text(json.dumps(summary), encoding="utf-8")


def _synthetic_drop_check(status: str, value: float, drop: float) -> dict:
    return {
        "name": "body_drop", "kind": "relative_translation", "status": status,
        "value": value, "units": "m", "time_s": 3.2,
        "evidence": {
            "kind": "relative_translation", "window": "max_over_phase", "frame": "world",
            "axis": "z", "from_phase": "initial", "to_phase": "hold",
            "min_m": value, "min_time_s": 3.2, "max_m": value, "max_time_s": 3.2,
            "terminal_m": value, "terminal_time_s": 3.2,
            "lower_m": -PLAN_DROP_BOUND_M, "upper_m": PLAN_DROP_BOUND_M,
            "drop_m": drop, "samples": 500,
        },
    }


# ------------------------------------------------------------------ 1. plan thresholds
def test_zero_point_two_degrees_is_recomputed_in_radians():
    """Plan 5.3: the rotation bound is 0.20 deg, i.e. 0.20*pi/180 rad, not 0.20 rad."""
    radians = 0.20 * math.pi / 180.0
    assert radians == pytest.approx(0.003490658503988659, abs=1e-18)
    assert 0.20 / radians == pytest.approx(57.29577951308232, rel=1e-15)
    acceptance = load_acceptance(ACCEPTANCE_PATH)
    by_name = {check.name: check for check in acceptance.checks}
    for name in ("body_pose_retained", "chassis_grounded"):
        bound = by_name[name].max_rotation_rad
        assert bound == pytest.approx(radians, abs=1e-15), f"{name} is not 0.20 deg in rad"
        assert bound != pytest.approx(0.20, abs=1e-6), f"{name} stored degrees as radians"


def test_body_drop_is_chassis_then_body_so_a_fall_is_negative():
    """Plan 5.3: body_a=chassis, body_b=body, world z, and a fall must read negative."""
    acceptance = load_acceptance(ACCEPTANCE_PATH)
    drop = {check.name: check for check in acceptance.checks}["body_drop"]
    assert drop.kind == "relative_translation"
    assert (drop.body_a, drop.body_b) == ("chassis", "body")
    assert (drop.frame, drop.axis) == ("world", "z")
    assert (drop.from_phase, drop.to_phase, drop.window) == ("initial", "hold",
                                                            "max_over_phase")
    assert drop.lower == pytest.approx(-PLAN_DROP_BOUND_M, abs=1e-15)
    assert drop.upper == pytest.approx(PLAN_DROP_BOUND_M, abs=1e-15)
    assert drop.units == "m"

    # Δrel_z = (z_body1 - z_chassis1) - (z_body0 - z_chassis0) with body_b=body, body_a=chassis.
    z_chassis0, z_body0, z_chassis1, z_body1 = 0.0, 0.0, 0.0, -0.0004
    delta = (z_body1 - z_chassis1) - (z_body0 - z_chassis0)
    assert delta == pytest.approx(-0.0004, abs=1e-18)
    assert delta < 0, "a 0.4 mm fall must be a negative signed change"
    assert _drop_fails(delta, drop.lower, drop.upper), "a fall must fail the lower bound"
    assert max(0.0, -delta) == pytest.approx(0.0004, abs=1e-18)

    # The same 0.4 mm motion upward must fail the upper bound (both directions fail).
    lift = +0.0004
    assert _drop_fails(lift, drop.lower, drop.upper), "a lift must fail the upper bound"
    assert max(0.0, -lift) == 0.0

    # Swapping the bodies flips the sign, so the reported downward drop would read zero:
    # the ordering is load-bearing, not cosmetic.
    swapped = (z_chassis1 - z_body1) - (z_chassis0 - z_body0)
    assert swapped == pytest.approx(-delta, abs=1e-18)
    assert swapped > 0 and max(0.0, -swapped) == 0.0
    assert _drop_fails(0.0, drop.lower, drop.upper) is False


@pytest.mark.parametrize("pair", CONTACT_PAIRS, ids=lambda pair: f"{pair[0]}_on_{pair[1]}")
def test_contact_checks_use_end_window_without_phase_fields(pair: tuple[str, str]):
    """Plan 5.3 and the S0 packet: whole-run ``window=end``, no phase/from/to fields."""
    acceptance = load_acceptance(ACCEPTANCE_PATH)
    check = {item.name: item for item in acceptance.checks}[f"{pair[0]}_on_{pair[1]}"]
    assert check.kind == "contact_duration"
    assert (check.body_a, check.body_b) == pair
    assert check.window == "end", "S0 contact duration must not use max_over_phase"
    assert check.phase is None and check.from_phase is None and check.to_phase is None
    assert check.force_threshold_n == pytest.approx(PLAN_CONTACT_THRESHOLD_N, abs=1e-15)
    assert check.maximum == pytest.approx(PLAN_CONTACT_MAX_S, abs=1e-15)
    assert check.units == "s"


def test_units_are_si_and_thresholds_are_the_plan_numbers():
    """Plan 5.3: SI units throughout, and every frozen bound is the plan's own number."""
    acceptance = load_acceptance(ACCEPTANCE_PATH)
    by_name = {check.name: check for check in acceptance.checks}
    assert set(by_name) == set(CHECK_UNITS)
    for name, units in CHECK_UNITS.items():
        assert by_name[name].units == units, f"{name} units"
        assert units not in ("mm", "deg", "ms", "rad")
    for check in acceptance.checks:
        assert not check.units.startswith("m") or check.units in ("m", "m/s")

    assert by_name["body_pose_retained"].maximum == pytest.approx(PLAN_MAX_TRANSLATION_M,
                                                                  abs=1e-15)
    assert by_name["body_pose_retained"].max_rotation_rad == pytest.approx(
        PLAN_MAX_ROTATION_RAD, abs=1e-15)
    assert by_name["chassis_grounded"].maximum == pytest.approx(PLAN_GROUNDED_MAX_M,
                                                                abs=1e-15)
    assert by_name["chassis_grounded"].max_rotation_rad == pytest.approx(
        PLAN_MAX_ROTATION_RAD, abs=1e-15)
    for name in ("settled_body", "settled_lip"):
        assert by_name[name].maximum == pytest.approx(PLAN_SPEED_MAX_M_S, abs=1e-15)
        assert by_name[name].phase == "hold"
        assert by_name[name].window == "max_over_phase"
    assert by_name["penetration"].kind == "penetration_bound"
    assert by_name["penetration"].maximum == pytest.approx(PLAN_PENETRATION_MAX_M, abs=1e-15)

    # 0.0715 N is 5% of the 145.89 g hanging group, not 5% of the body alone (0.0684 N).
    expected = 0.05 * HANGING_GROUP_KG * GRAVITY_M_S2
    assert expected == pytest.approx(PLAN_CONTACT_THRESHOLD_N, abs=1e-4)
    assert abs(PLAN_CONTACT_THRESHOLD_N - BODY_ONLY_FIVE_PERCENT_N) > 3e-3
    thresholds = {by_name[f"{a}_on_{b}"].force_threshold_n for a, b in CONTACT_PAIRS}
    assert thresholds == {PLAN_CONTACT_THRESHOLD_N}

    # Validity declares the penetration bound and nothing that would smuggle in another gate.
    assert acceptance.validity.max_penetration_m == pytest.approx(PLAN_PENETRATION_MAX_M,
                                                                  abs=1e-15)
    assert acceptance.validity.max_speed_m_s is None
    assert acceptance.validity.max_angular_speed_rad_s is None
    assert acceptance.validity.max_energy_j is None
    assert acceptance.near_threshold_fraction == pytest.approx(PLAN_NEAR_THRESHOLD_FRACTION,
                                                               abs=1e-15)
    assert acceptance.events == ()


# --------------------------------------------------------------- 2. all-five reset derivation
def test_all_five_resets_derive_from_the_cad_helpers():
    """Plan 5.2: every reset is the helper pose, and the plan table is its rounded result."""
    by_fraction = {round(fraction, 2): stem for fraction, stem in zip(
        (0.0, 0.25, 0.5, 0.75, 1.0), FRACTION_STEMS)}
    assert len(by_fraction) == 5
    for fraction, stem in by_fraction.items():
        derived = _cad_reset(fraction)
        scenario = load_scenario(SCENARIO_DIR / f"{stem}.json")
        written = {name: value for name, value in scenario.reset_phase.initial}
        assert set(written) == {"crank_phi", "rod_x", "pusher_x"}
        for joint, value in derived.items():
            assert written[joint] == pytest.approx(value, abs=1e-15), f"{stem}.{joint}"

        # Cross-check only: the production helper must agree with this independent derivation.
        cross = reset_state(load_params(), fraction)
        assert cross.crank_phi_rad == pytest.approx(derived["crank_phi"], abs=1e-15)
        assert cross.rod_x_m == pytest.approx(derived["rod_x"], abs=1e-15)
        assert cross.pusher_x_m == pytest.approx(derived["pusher_x"], abs=1e-15)

        # Plan 5.2's table is the helpers rounded to nine decimals.
        crank, rod, pusher = PLAN_RESET_TABLE[fraction]
        assert derived["crank_phi"] == pytest.approx(crank, abs=1e-9)
        assert derived["rod_x"] == pytest.approx(rod, abs=1e-9)
        assert derived["pusher_x"] == pytest.approx(pusher, abs=1e-9)
        assert derived["pusher_x"] * 1000.0 == pytest.approx(pusher * 1000.0, abs=1e-6)

        # Plan 5.2: the pusher translation equals the pin x displacement.
        link = linkage_from(load_params())
        rest = pose_at_phi(link, link.phi0)
        pose = pose_at_phi(link, phi_for_button_fraction(link, fraction))
        assert (pose.pusher_pin_x - rest.pusher_pin_x) / 1000.0 == pytest.approx(
            derived["pusher_x"], abs=1e-15)


def test_compiled_reset_audit_agrees_with_the_helper_derivation():
    """Plan 5.2 cross-check: the compiled reset audit matches this module's own derivation."""
    _require_generated_evidence()
    preflight = json.loads(PREFLIGHT_PATH.read_text(encoding="utf-8"))
    for row in preflight["compiled"]["resets"]:
        derived = _cad_reset(float(row["fraction"]))
        assert row["ok"] is True
        assert row["sign_bad"] is False
        assert row["worst_translation_error_m"] <= 1e-9
        assert row["worst_angular_error_rad"] <= 1e-9
        for joint, value in derived.items():
            assert float(row["joint_coordinates"][joint]) == pytest.approx(value, abs=1e-12)


def test_naive_linear_quarter_stroke_is_rejected():
    """Plan 5.2: linear quarter stroke is a negative, wrong by >= 1.3 mm at f=0.25/0.75."""
    full_stroke_m = _cad_reset(1.0)["pusher_x"]
    assert full_stroke_m == pytest.approx(0.05, abs=1e-15)
    for fraction in (0.25, 0.75):
        exact = _cad_reset(fraction)["pusher_x"]
        naive = fraction * full_stroke_m
        error_mm = abs(exact - naive) * 1000.0
        assert error_mm == pytest.approx(LINEAR_QUARTER_ERROR_MM, abs=1e-9)
        assert error_mm >= LINEAR_NEGATIVE_FLOOR_MM, f"f={fraction}: only {error_mm} mm"
        assert error_mm > 0.3, "the error must exceed the 0.3 mm pin/slot side clearance"


@pytest.mark.parametrize("stem", FRACTION_STEMS)
def test_compiled_run_starts_at_the_helper_reset(stem: str):
    """Plan 5.2: the runtime reset is the helper pose, applied at the declared joint addresses."""
    _require_generated_evidence()
    fraction = int(stem.split("_f")[1]) / 100.0
    derived = _cad_reset(fraction)
    summary = _summary(stem)
    states = _states(stem)
    joints = summary["solver"]["joints"]
    assert set(joints) == {"crank_phi", "rod_x", "pusher_x"}
    for joint, value in derived.items():
        address = joints[joint]["qposadr"]
        assert states["qpos"][0][address] == pytest.approx(value, abs=1e-15)
    # Only initial states are written: the reset phase has no duration and no actuator.
    assert summary["phases"][0]["kind"] == "reset"
    assert summary["phases"][0]["actual_steps"] == 0
    assert summary["phases"][0]["actuator"] is None


@pytest.mark.parametrize("stem", ("s0_f000", "s0_spring_low", "s0_half_dt"))
def test_non_fraction_scenarios_declare_the_rest_pose(stem: str):
    """Plan 5.2: the spring and half-dt variants are the f=0 rest pose with other options."""
    derived = _cad_reset(0.0)
    assert derived == {"crank_phi": 0.0, "rod_x": 0.0, "pusher_x": 0.0}
    scenario = load_scenario(SCENARIO_DIR / f"{stem}.json")
    assert dict(scenario.reset_phase.initial) == pytest.approx(derived, abs=1e-15)


@pytest.mark.parametrize("stem", ("s0_f000", "s0_spring_low", "s0_half_dt"))
def test_non_fraction_runs_start_at_the_rest_pose(stem: str):
    """Plan 5.2: the compiled run of each variant is reset to that same rest pose."""
    _require_generated_evidence()
    derived = _cad_reset(0.0)
    summary = _summary(stem)
    joints = summary["solver"]["joints"]
    qpos = _states(stem)["qpos"][0]
    for joint, value in derived.items():
        assert qpos[joints[joint]["qposadr"]] == pytest.approx(value, abs=1e-15)


# ---------------------------------------------------------- 3. no actuation, plan durations
@pytest.mark.parametrize("stem", RUN_STEMS)
def test_scenarios_declare_plan_phases_and_no_actuation(stem: str):
    """Plan 5.2: reset, settle 3.0 s, hold 0.5 s of real zero input; no actuator anywhere."""
    scenario = load_scenario(SCENARIO_DIR / f"{stem}.json")
    assert scenario.scenario_id == f"m5a1_{stem}"
    assert scenario.fixture == "pocky_prototype"
    assert scenario.seed == 0
    assert scenario.timestep_s == pytest.approx(_expected_dt(stem), abs=1e-15)
    assert scenario.sampling_interval_s == pytest.approx(_expected_dt(stem), abs=1e-15)
    assert tuple(phase.kind for phase in scenario.phases) == ("reset", "settle", "hold")
    assert scenario.phases[1].duration_s == pytest.approx(SETTLE_S, abs=1e-15)
    assert scenario.phases[2].duration_s == pytest.approx(HOLD_S, abs=1e-15)
    assert scenario.reset_phase.name == "reset"
    for phase in scenario.timed_phases:
        assert phase.actuator is None, f"{stem}.{phase.name} declares an actuator"
        assert phase.effort is None, f"{stem}.{phase.name} declares an effort"


@pytest.mark.parametrize("stem", RUN_STEMS)
def test_runs_apply_zero_effort_every_step(stem: str):
    """Plan 5.2/5.4: the hold is real zero input, so no actuator, ctrl or applied force."""
    _require_generated_evidence()
    summary = _summary(stem)
    states = _states(stem)
    assert summary["control_names"] == []
    assert summary["solver"]["actuators"] == {}
    assert summary["metrics"]["commanded_actuators"] == []
    assert summary["metrics"]["peak_ctrl_stored"] == {}
    assert summary["metrics"]["peak_effort"] == {}
    assert states["ctrl_shape"][1] == 0
    assert states["act_shape"][1] == 0
    assert float(np.max(np.abs(states["qfrc_applied"]))) == 0.0
    assert float(np.max(np.abs(states["transition_qfrc_applied"]))) == 0.0
    assert float(np.max(np.abs(states["transition_xfrc_applied"]))) == 0.0
    assert states["transition_ctrl"].size == 0

    phases = {phase["name"]: phase for phase in summary["phases"]}
    assert phases["settle"]["requested_effort"] in (None, 0.0)
    assert phases["settle"]["ctrl_requested"] in (None, 0.0)
    assert phases["hold"]["requested_effort"] == 0.0
    assert phases["hold"]["ctrl_requested"] == 0.0
    for name in ("settle", "hold"):
        assert phases[name]["actuator"] is None
        assert phases[name]["ctrl_effective_peak"] is None
        assert phases[name]["complete"] is True
    assert phases["settle"]["actual_duration_s"] == pytest.approx(SETTLE_S, abs=1e-9)
    assert phases["hold"]["actual_duration_s"] == pytest.approx(HOLD_S, abs=1e-9)
    assert phases["settle"]["actual_steps"] == int(round(SETTLE_S / _expected_dt(stem)))
    assert phases["hold"]["actual_steps"] == int(round(HOLD_S / _expected_dt(stem)))


# ------------------------------------------------- 4. every-step retention and the full hold
@pytest.mark.parametrize("stem", RUN_STEMS)
def test_retained_states_cover_the_whole_run_at_the_declared_timestep(stem: str):
    """Plan 5.4: sampling == timestep, so every integration state of 3.5 s is retained."""
    _require_generated_evidence()
    summary = _summary(stem)
    states = _states(stem)
    dt = _expected_dt(stem)
    steps = _required_steps(stem)
    assert summary["plan"]["sample_every_steps"] == 1, "the run was downsampled"
    assert states["timestep_s"] == pytest.approx(dt, abs=1e-15)
    assert len(states["time"]) == steps + 1
    assert states["step_index"][0] == 0 and states["step_index"][-1] == steps
    np.testing.assert_allclose(np.diff(states["time"]), dt, atol=1e-12, rtol=0.0)
    assert states["time"][0] == 0.0
    assert states["time"][-1] == pytest.approx(TOTAL_S, abs=1e-9)
    assert np.all(np.diff(states["step_index"]) == 1)


@pytest.mark.parametrize("stem", RUN_STEMS)
def test_hold_rows_are_retained_and_its_final_state_is_present(stem: str):
    """Plan 5.4: the full 0.5 s hold is retained, terminal hold state included."""
    _require_generated_evidence()
    summary = _summary(stem)
    states = _states(stem)
    trace = _trace(stem)
    dt = _expected_dt(stem)
    hold_rows = int(round(HOLD_S / dt))

    assert states["phase_names"] == ["reset", "settle", "hold"]
    counts = np.bincount(states["phase_index"], minlength=3)
    assert counts[0] == 1, "the reset row must be the single initial state"
    assert counts[1] == int(round(SETTLE_S / dt))
    assert counts[2] == hold_rows
    assert states["phase_index"][-1] == 2
    assert states["phase_names"][states["phase_index"][-1]] == "hold"

    assert trace["rows"] == len(states["time"])
    assert trace["rows"] == summary["telemetry"]["state_rows"]
    np.testing.assert_allclose(trace["time"], states["time"], atol=1e-12, rtol=0.0)
    assert trace["phase"][-1] == "hold"
    assert int(trace["step"][-1]) == _required_steps(stem)
    assert int(np.count_nonzero(trace["phase"] == "hold")) == hold_rows
    assert trace["time"][-1] == pytest.approx(TOTAL_S, abs=1e-9)

    # The hold's final state is archived, not only reported: the last checkpoint is the row.
    archive = summary["state_archive"]["checkpoints"]
    assert archive["terminal_row"] == _required_steps(stem)
    assert states["time"][archive["terminal_row"]] == pytest.approx(states["time"][-1],
                                                                    abs=1e-12)


# ----------------------------------------------------------------------- 5. budget handling
@pytest.mark.parametrize("stem", RUN_STEMS)
def test_declared_budgets_cover_the_required_samples(stem: str):
    """Plan 5.4: budgets are sized from this scenario's own dt, and cover every sample."""
    scenario = load_scenario(SCENARIO_DIR / f"{stem}.json")
    dt = _expected_dt(stem)
    steps = _required_steps(stem)
    budgets = scenario.budgets
    assert scenario.sampling_interval_s == dt
    assert budgets.max_steps >= steps
    assert budgets.max_trace_rows >= steps + 1, "trace budget cannot hold every state"
    assert budgets.max_state_rows is not None and budgets.max_state_rows >= steps + 1
    assert budgets.max_sim_time_s >= TOTAL_S
    assert budgets.max_state_bytes is not None and budgets.max_state_bytes > 0


@pytest.mark.parametrize("stem", RUN_STEMS)
def test_declared_budgets_cover_the_observed_payload(stem: str):
    """Plan 5.4: the declared byte budget covers the archived payload actually written."""
    _require_generated_evidence()
    scenario = load_scenario(SCENARIO_DIR / f"{stem}.json")
    summary = _summary(stem)
    assert summary["state_archive"]["payload_estimate_bytes"] <= scenario.budgets.max_state_bytes
    assert summary["state_archive"]["rows"] == _required_steps(stem) + 1


@pytest.mark.parametrize("stem", RUN_STEMS)
def test_no_run_truncated_or_silently_sampled_less(stem: str):
    """Plan 5.4: an overflow invalidates; a completed run shows declared == actual rows."""
    _require_generated_evidence()
    summary = _summary(stem)
    states = _states(stem)
    trace = _trace(stem)
    steps = _required_steps(stem)
    telemetry = summary["telemetry"]

    assert summary["status"] in ("PASS", "FAIL", "INCONCLUSIVE")
    assert summary["detail"] == ""
    assert telemetry["stopped"] is False, f"{stem} stopped early"
    assert telemetry["initial_rejected"] is False
    assert all(count == 0 for count in telemetry["warnings"].values()), telemetry["warnings"]
    assert summary["validity"]["reasons"] != []
    assert summary["plan"]["total_steps"] == steps
    assert summary["plan"]["total_time_s"] == pytest.approx(TOTAL_S, abs=1e-12)
    assert telemetry["trace_rows"] == steps + 1
    assert telemetry["state_rows"] == steps + 1
    assert trace["rows"] == steps + 1
    assert len(states["time"]) == steps + 1
    assert summary["state_archive"]["rows"] == steps + 1
    assert summary["state_archive"]["checkpoints"]["rows"] == steps + 1
    assert summary["state_archive"]["checkpoints"]["post_settle_row"] == int(
        round(SETTLE_S / _expected_dt(stem)))
    # Contact rows stay inside the scenario's own declared allowance: the runner caps them at
    # 16 per declared trace row, so no contact overflow happened and none was dropped.
    scenario = load_scenario(SCENARIO_DIR / f"{stem}.json")
    assert summary["state_archive"]["payload_budget_bytes"] > 0
    assert telemetry["contact_rows"] <= scenario.budgets.max_trace_rows * (
        CONTACT_ROWS_PER_TRACE_ROW)


# ----------------------------------------------------------- 6. worst sample vs end boundary
@pytest.mark.parametrize("stem", RUN_STEMS)
def test_worst_over_hold_is_reported_separately_from_the_end_boundary(stem: str):
    """Plan 5.3/5.4: max_over_phase reports the worst hold sample, and the end value too."""
    _require_generated_evidence()
    summary = _summary(stem)
    trace = _trace(stem)
    mask = _hold_mask(trace)
    hold_times = trace["time"][mask]
    assert len(hold_times) == int(round(HOLD_S / _expected_dt(stem)))

    for name, bodies in (("body_pose_retained", ("body", "chassis")),
                         ("chassis_grounded", ("chassis", "floor_world"))):
        evidence = _evidence(summary, name)
        check = _check(summary, name)
        assert evidence["window"] == "max_over_phase"
        assert evidence["phase"] == "hold"
        assert evidence["samples"] == len(hold_times)
        assert evidence["bound_translation_m"] == pytest.approx(
            PLAN_POSE_BOUNDS_M[name], abs=1e-15)
        assert evidence["bound_rotation_rad"] == pytest.approx(PLAN_MAX_ROTATION_RAD,
                                                               abs=1e-15)
        assert evidence["near_threshold_fraction"] == pytest.approx(
            PLAN_NEAR_THRESHOLD_FRACTION, abs=1e-15)

        # Recompute the plan 5.3 attached-local pose independently, from the trace.
        delta_p, theta = _attached_local_delta(trace, bodies[0], bodies[1], mask)
        # The archived quaternions are printed to 12 significant digits in trace.csv, so the
        # independent recompute agrees with the evaluator's own arrays to ~5e-12, not to 0.
        assert evidence["translation_m"] == pytest.approx(float(delta_p.max()), abs=5e-12)
        assert evidence["rotation_rad"] == pytest.approx(float(theta.max()), abs=5e-12)

        # The reported worst sample attains the reported value at the reported time. Ties
        # keep the last sample, so the index is found from the reported time, not by argmax.
        for value_key, time_key, series in (("translation_m", "translation_time_s", delta_p),
                                            ("rotation_rad", "rotation_time_s", theta)):
            reported_time = evidence[time_key]
            index = int(np.argmin(np.abs(hold_times - reported_time)))
            assert abs(hold_times[index] - reported_time) <= 1e-9
            assert series[index] == pytest.approx(evidence[value_key], abs=5e-12)
            assert evidence[value_key] == pytest.approx(float(series.max()), abs=5e-12)

        # The end boundary is a separate, explicitly reported sample of the same hold.
        assert evidence["end_time_s"] == pytest.approx(hold_times[-1], abs=1e-9)
        assert evidence["end_translation_m"] == pytest.approx(float(delta_p[-1]), abs=5e-12)
        assert evidence["end_rotation_rad"] == pytest.approx(float(theta[-1]), abs=5e-12)
        assert evidence["end_translation_m"] <= evidence["translation_m"] + 5e-12
        assert evidence["end_rotation_rad"] <= evidence["rotation_rad"] + 5e-12
        if evidence["translation_time_s"] != evidence["end_time_s"]:
            assert evidence["end_translation_m"] < evidence["translation_m"], name
        if evidence["rotation_time_s"] != evidence["end_time_s"]:
            assert evidence["end_rotation_rad"] < evidence["rotation_rad"], name

        # The check's single reported value/time is one of those two distinct quantities.
        if check["value"] == pytest.approx(evidence["translation_m"], abs=5e-12):
            assert check["time_s"] == pytest.approx(evidence["translation_time_s"], abs=1e-12)
        else:
            assert check["value"] == pytest.approx(evidence["rotation_rad"], abs=5e-12)
            assert check["time_s"] == pytest.approx(evidence["rotation_time_s"], abs=1e-12)

    drop = _evidence(summary, "body_drop")
    z_body = trace["pos"]["body"][:, 2]
    z_chassis = trace["pos"]["chassis"][:, 2]
    relative = (z_body - z_chassis)[mask] - (z_body - z_chassis)[0]
    assert drop["samples"] == len(hold_times)
    assert drop["min_m"] == pytest.approx(float(relative.min()), abs=1e-12)
    assert drop["max_m"] == pytest.approx(float(relative.max()), abs=1e-12)
    assert drop["terminal_m"] == pytest.approx(float(relative[-1]), abs=1e-12)
    assert drop["drop_m"] == pytest.approx(max(0.0, -float(relative.min())), abs=1e-12)
    for time_key, series, pick in (("min_time_s", relative, np.argmin),
                                   ("max_time_s", relative, np.argmax),
                                   ("terminal_time_s", relative, lambda values: -1)):
        reported_time = drop[time_key]
        assert hold_times[pick(series)] == pytest.approx(reported_time, abs=1e-9)
    assert (drop["lower_m"], drop["upper_m"]) == pytest.approx(
        (-PLAN_DROP_BOUND_M, PLAN_DROP_BOUND_M), abs=1e-15)
    assert drop["terminal_m"] >= drop["min_m"]
    if drop["min_time_s"] != drop["terminal_time_s"]:
        assert drop["terminal_m"] > drop["min_m"]
    # These runs are a fall: the signed change is negative and the drop positive.
    assert drop["min_m"] < 0.0
    assert drop["drop_m"] > 0.0
    assert _drop_fails(drop["min_m"], drop["lower_m"], drop["upper_m"])


@pytest.mark.parametrize("stem", RUN_STEMS)
def test_contact_duration_evidence_is_per_step_and_consistent(stem: str):
    """Plan 5.3: contact duration is a whole-run per-step summed-force interval."""
    _require_generated_evidence()
    summary = _summary(stem)
    steps = _required_steps(stem)
    dt = _expected_dt(stem)
    for pair in CONTACT_PAIRS:
        name = f"{pair[0]}_on_{pair[1]}"
        evidence = _evidence(summary, name)
        assert evidence["window"] == "end"
        assert evidence["samples"] == steps + 1, "the watch must cover every step"
        assert evidence["threshold_n"] == pytest.approx(PLAN_CONTACT_THRESHOLD_N, abs=1e-15)
        assert evidence["bound_s"] == pytest.approx(PLAN_CONTACT_MAX_S, abs=1e-15)
        assert 0 <= evidence["samples_above"] <= evidence["samples"]
        assert 0 <= evidence["run_samples"] <= evidence["samples_above"]
        if evidence["run_samples"] == 0:
            # No uninterrupted run: at most isolated one-state excursions, which count 0.0 s.
            assert evidence["longest_s"] == 0.0
            assert evidence["start_s"] is None and evidence["end_s"] is None
        else:
            assert evidence["longest_s"] == pytest.approx(
                (evidence["run_samples"] - 1) * dt, abs=1e-9)
            assert evidence["end_s"] - evidence["start_s"] == pytest.approx(
                evidence["longest_s"], abs=1e-9)
            assert evidence["start_s"] >= 0.0
            assert evidence["end_s"] <= _states(stem)["time"][-1] + 1e-9
        # The peak force is a raw maximum, so it is at least the threshold whenever any
        # state crossed it, and non-negative otherwise.
        assert evidence["peak_force_n"] >= 0.0
        if evidence["samples_above"]:
            assert evidence["peak_force_n"] > evidence["threshold_n"]
        assert evidence["terminal_force_n"] is not None
        assert evidence["terminal_time_s"] == pytest.approx(
            _states(stem)["time"][-1], abs=1e-9)


# ------------------------------------------------- 7. valid FAIL versus invalid INCONCLUSIVE
@pytest.mark.parametrize("stem", RUN_STEMS)
def test_invalid_runs_are_inconclusive_and_never_pass(stem: str):
    """Plan 5.3/5.4: a validity breach makes the conclusion INCONCLUSIVE, never PASS."""
    _require_generated_evidence()
    summary = _summary(stem)
    validity = summary["validity"]
    statuses = [check["status"] for check in summary["checks"]]
    assert validity["ok"] is False, f"{stem} is expected to breach numerical validity"
    assert validity["reasons"], "an invalid run must state its reasons"
    assert any("penetration" in reason["reason"] for reason in validity["reasons"])
    assert summary["status"] == "INCONCLUSIVE"
    assert summary["status"] != "PASS"
    assert _status_from_evidence(validity["ok"], statuses) == summary["status"]

    # Individual product verdicts are preserved, not rewritten to INCONCLUSIVE.
    assert "FAIL" in statuses and "PASS" in statuses
    assert _check(summary, "penetration")["status"] == "FAIL"
    assert _check(summary, "penetration")["value"] > PLAN_PENETRATION_MAX_M
    assert _check(summary, "body_drop")["status"] == "FAIL"
    assert summary["metrics"]["checks_failed"] >= 1
    assert summary["metrics"]["checks_passed"] >= 1

    # The diagnostic report copies the evaluator's status and never invents a PASS verdict.
    diagnostics = report.diagnostics(_run(stem))
    assert diagnostics["status"] == summary["status"]
    assert diagnostics["validity"]["ok"] is False
    markdown = report.render_markdown(diagnostics)
    assert "**PASS**" not in markdown
    assert "**INCONCLUSIVE**" in markdown


def test_valid_fail_summary_is_preserved_by_the_diagnostics(tmp_path: Path):
    """Plan 5.3: a hash-bound structural FAIL stays FAIL when the run is numerically valid."""
    run = tmp_path / "valid_fail"
    _write_synthetic_run(run, status="FAIL", validity_ok=True,
                         checks=[_synthetic_drop_check("FAIL", -0.0004, 0.0004)])
    before = _sha256(run / "summary.json")
    listing = sorted(path.name for path in run.iterdir())

    diagnostics = report.diagnostics(run)
    assert diagnostics["status"] == "FAIL"
    assert diagnostics["validity"]["ok"] is True
    assert [check["status"] for check in diagnostics["checks"]] == ["FAIL"]
    markdown = report.render_markdown(diagnostics)
    assert "**FAIL**" in markdown
    assert "**PASS**" not in markdown

    assert _sha256(run / "summary.json") == before, "diagnostics rewrote the summary"
    assert sorted(path.name for path in run.iterdir()) == listing


def test_invalid_run_with_passing_checks_is_inconclusive(tmp_path: Path):
    """Plan 5.3: validity short-circuits PASS even when every predicate happens to read true."""
    run = tmp_path / "invalid_pass"
    _write_synthetic_run(run, status="INCONCLUSIVE", validity_ok=False,
                         checks=[_synthetic_drop_check("PASS", -0.00005, 0.00005)])
    diagnostics = report.diagnostics(run)
    assert diagnostics["status"] == "INCONCLUSIVE"
    assert diagnostics["validity"]["ok"] is False
    # The individual PASS is preserved as evidence, but the run is not a PASS.
    assert [check["status"] for check in diagnostics["checks"]] == ["PASS"]
    markdown = report.render_markdown(diagnostics)
    assert "**PASS**" not in markdown
    assert "**INCONCLUSIVE**" in markdown
    # The same precedence, restated here, agrees with the copied status.
    assert _status_from_evidence(False, ["PASS"]) == "INCONCLUSIVE"
    assert _status_from_evidence(True, ["PASS"]) == "PASS"
    assert _status_from_evidence(True, ["FAIL"]) == "FAIL"


# ----------------------------------------------------------------------- 8. replay identity
def test_replay_reproduces_the_source_run_exactly_and_never_reports_pass():
    """Plan 5.4: replay re-steps from the verified state and must reproduce, never PASS."""
    _require_generated_evidence()
    replay = json.loads((REPLAY_ROOT / "replay.json").read_text(encoding="utf-8"))
    source = _summary("s0_f000")

    assert replay["reproduced"] is True
    assert replay["source_status"] == source["status"] == "INCONCLUSIVE"
    assert replay["replay_status"] == replay["source_status"]
    assert replay["replay_status"] != "PASS"
    assert replay["source_run"] == "out/mujoco-m5a/s0/runs/s0_f000"

    states = replay["state_comparison"]
    assert states["ok"] is True
    assert states["max_abs_diff"] == 0.0
    assert states["nonfinite_mismatches"] == 0
    assert states["first_mismatch"] is None
    assert states["rows"] == len(_states("s0_f000")["time"]) == 3501
    assert states["expected_rows"] == states["rows"]

    continuation = replay["post_settle_continuation"]
    assert continuation["ok"] is True
    assert continuation["max_abs_diff"] == 0.0
    assert continuation["start_row"] == 3000
    assert continuation["rows"] == int(round(HOLD_S / BASE_DT_S)) + 1
    assert continuation["expected_rows"] == continuation["rows"]

    assert replay["evaluation_comparison"] == {"ok": True, "differences": []}
    assert replay["event_comparison"]["ok"] is True
    assert replay["event_comparison"]["differences"] == []
    assert replay["replayed_state_rows"] == states["rows"]

    # Every bound source file still hashes to what the replay verified.
    for name, digest in replay["source_hashes"].items():
        path = _run("s0_f000") / name
        assert path.exists(), f"replay binds a missing file {name}"
        assert _sha256(path) == digest, f"replay hash mismatch for {name}"
    assert replay["source_hashes"]["scene.xml"] == source["scene"]["xml_sha256"]
    manifest = json.loads((_run("s0_f000") / "manifest.json").read_text(encoding="utf-8"))
    for name, entry in manifest["artifacts"].items():
        assert replay["source_hashes"][name] == entry["sha256"], f"replay binds a stale {name}"

    with np.load(REPLAY_ROOT / "replayed_states.npz", allow_pickle=False) as archive:
        replayed = np.array(archive["integration_state"])
        start_row = int(archive["start_row"])
    # The archive holds the whole re-stepped run; the post-settle continuation is its tail.
    assert start_row == states["start_row"] == 0
    assert replayed.shape[0] == states["rows"]
    np.testing.assert_array_equal(replayed, _states("s0_f000")["integration_state"])
    np.testing.assert_array_equal(
        replayed[continuation["start_row"]:],
        _states("s0_f000")["integration_state"][continuation["start_row"]:])

    comparison = report.compare(_run("s0_f000"), REPLAY_ROOT)
    assert comparison["reproduced"] is True
    assert comparison["inconclusive"] == []
    assert comparison["replay_status"] == "INCONCLUSIVE"
    assert comparison["source_status"] == "INCONCLUSIVE"
    assert comparison["evaluation_comparison"]["ok"] is True
    assert comparison["evaluation_comparison"]["differences"] == []
    assert comparison["state_comparison"]["max_abs_diff"] == 0.0
    text = report.render_comparison(comparison)
    assert "PASS" not in text
    assert "INCONCLUSIVE" in text


# ------------------------------------------------------------------ 9. evidence completeness
@pytest.mark.parametrize("stem", RUN_STEMS)
def test_each_run_carries_the_required_evidence(stem: str):
    """Evidence packet: summary/report/trace/contacts/states/checkpoints/locks per run."""
    _require_generated_evidence()
    run = _run(stem)
    required = (
        "summary.json", "report.md", "report.json", "manifest.json", "trace.csv",
        "contacts.csv", "states.npz", "state_meta.json", "checkpoints.npz",
        "scenario.json", "acceptance.lock.json", "assembly_options.lock.toml", "scene.xml",
    )
    for name in required:
        assert (run / name).is_file(), f"{stem} is missing {name}"
    summary = _summary(stem)
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    assert summary["status"] == manifest["status"]
    assert summary["run_id"] == manifest["run_id"] == stem
    assert summary["artifacts"]["trace"] == "trace.csv"
    assert summary["artifacts"]["contacts"] == "contacts.csv"
    assert summary["artifacts"]["states"] == "states.npz"
    assert summary["artifacts"]["checkpoints"] == "checkpoints.npz"
    assert summary["artifacts"]["acceptance_lock"] == "acceptance.lock.json"
    assert summary["artifacts"]["assembly_options_lock"] == "assembly_options.lock.toml"

    # The per-run locks are the frozen project files, byte for byte.
    assert (run / "scenario.json").read_bytes() == (
        SCENARIO_DIR / f"{stem}.json").read_bytes()
    assert (run / "acceptance.lock.json").read_bytes() == ACCEPTANCE_PATH.read_bytes()
    assert summary["scenario"]["sha256"] == _sha256(run / "scenario.json")
    assert summary["acceptance"]["sha256"] == _sha256(run / "acceptance.lock.json")

    # The manifest's artifact hashes still match the files on disk.
    for name, entry in manifest["artifacts"].items():
        path = run / name
        assert path.is_file(), f"{stem}: manifest names a missing {name}"
        assert path.stat().st_size == entry["bytes"], f"{stem}: {name} size changed"
        assert _sha256(path) == entry["sha256"], f"{stem}: {name} hash changed"
    assert _sha256(run / "scene.xml") == summary["scene"]["xml_sha256"]


@pytest.mark.parametrize("stem", RUN_STEMS)
def test_checkpoints_are_finite_and_bound_to_the_state_archive(stem: str):
    """Evidence packet: saved checkpoints must be complete and bound, never claimed settled."""
    _require_generated_evidence()
    summary = _summary(stem)
    states = _states(stem)
    archive = summary["state_archive"]["checkpoints"]
    with np.load(_run(stem) / "checkpoints.npz", allow_pickle=False) as checkpoints:
        names = set(checkpoints.files)
        assert {"initial", "initial_row", "post_settle", "post_settle_row",
                "terminal", "terminal_row"} <= names
        for name in ("initial", "post_settle", "terminal"):
            values = np.array(checkpoints[name])
            assert values.ndim == 1
            assert values.size == states["integration_state"].shape[1]
            assert np.all(np.isfinite(values)), f"{stem}.{name} has non-finite entries"
        rows = {name: int(checkpoints[f"{name}_row"])
                for name in ("initial", "post_settle", "terminal")}
        stored = {name: np.array(checkpoints[name]) for name in
                  ("initial", "post_settle", "terminal")}

    assert rows == {"initial": archive["initial_row"], "post_settle": archive["post_settle_row"],
                    "terminal": archive["terminal_row"]}
    assert rows["initial"] == 0
    assert rows["post_settle"] == int(round(SETTLE_S / _expected_dt(stem)))
    assert rows["terminal"] == _required_steps(stem)
    for name, row in rows.items():
        np.testing.assert_array_equal(stored[name], states["integration_state"][row])


def test_preflight_reports_ok_and_covers_all_five_fractions():
    """Evidence packet: the all-five compiled reset/clearance/validity audit must be ok."""
    _require_generated_evidence()
    preflight = json.loads(PREFLIGHT_PATH.read_text(encoding="utf-8"))
    assert preflight["kind"] == "m5a1_s0_preflight"
    assert preflight["ok"] is True
    assert preflight["problems"] == []
    compiled = preflight["compiled"]
    assert compiled["ok"] is True
    assert compiled["problems"] == []
    assert compiled["scenarios_match_audit"] is True
    assert [row["fraction"] for row in compiled["resets"]] == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert all(row["ok"] for row in compiled["resets"])
    assert all(row["sign_bad"] is False for row in compiled["resets"])
    assert all(row["worst_translation_error_m"] <= 1e-9 for row in compiled["resets"])
    assert all(row["worst_angular_error_rad"] <= 1e-9 for row in compiled["resets"])
    assert [row["fraction"] for row in compiled["validity"]] == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert all(row["ok"] for row in compiled["validity"])
    assert all(row["worst_exact_overlap_mm3"] == 0.0 for row in compiled["validity"])
    assert compiled["clearance"]["ok"] is True
    assert compiled["clearance"]["tolerance_mm"] == pytest.approx(0.02, abs=1e-12)
    assert compiled["clearance"]["fractions"] == 5

    # The linear and sign-flip negatives are rejected. The preflight converts the audit's
    # metre-valued fields to millimetres, so the converted fields must carry a ``_mm`` suffix:
    # a millimetre number under an ``_m`` name is wrong by 1000x and is asserted against here.
    negatives = compiled["negatives"]
    raw = json.loads((REPO_ROOT / "out" / "mujoco-m5a" / "adapter-static" / "compiled"
                      / "negative_resets.json").read_text(encoding="utf-8"))
    assert raw["linear"]["min_pusher_error_m"] == pytest.approx(
        LINEAR_QUARTER_ERROR_MM / 1000.0, abs=1e-12)
    assert raw["linear"]["min_pusher_error_m"] >= raw["linear"]["required_min_m"]
    assert negatives["linear"]["rejected"] is True
    assert negatives["linear"]["audit_ok"] is False
    assert not any(key.endswith("_m") for key in negatives["linear"]), negatives["linear"]
    assert negatives["linear"]["min_pusher_error_mm"] == pytest.approx(
        raw["linear"]["min_pusher_error_m"] * 1000.0, abs=1e-9)
    assert negatives["linear"]["min_pusher_error_mm"] >= LINEAR_NEGATIVE_FLOOR_MM
    assert negatives["linear"]["required_min_mm"] == pytest.approx(
        raw["linear"]["required_min_m"] * 1000.0, abs=1e-9)
    assert negatives["sign_flip"]["rejected"] is True
    assert negatives["sign_flip"]["audit_ok"] is False
    assert not any(key.endswith("_m") for key in negatives["sign_flip"]), negatives["sign_flip"]
    assert negatives["sign_flip"]["max_pusher_error_mm"] == pytest.approx(
        raw["sign_flip"]["max_pusher_error_m"] * 1000.0, abs=1e-9)


@pytest.mark.parametrize("stem", RUN_STEMS)
def test_preflight_budgets_cover_each_scenario_and_its_observed_rows(stem: str):
    """Plan 5.4: the derived budget table covers every sample and the observed contact rows."""
    _require_generated_evidence()
    preflight = json.loads(PREFLIGHT_PATH.read_text(encoding="utf-8"))
    budgets = preflight["budgets"]
    assert budgets["ok"] is True and budgets["problems"] == []
    rows = {row["scenario"]: row for row in budgets["scenarios"]}
    assert set(rows) == set(RUN_STEMS)
    row = rows[stem]
    steps = _required_steps(stem)
    assert row["timestep_s"] == pytest.approx(_expected_dt(stem), abs=1e-15)
    assert row["sampling_interval_s"] == row["timestep_s"]
    assert row["steps"] == steps
    assert row["required_trace_rows"] == steps + 1
    assert row["required_state_rows"] == steps + 1
    assert row["declared_trace_rows"] >= steps + 1
    assert row["declared_state_rows"] >= steps + 1
    assert row["declared_steps"] >= steps
    assert row["contact_row_cap"] == row["declared_trace_rows"] * CONTACT_ROWS_PER_TRACE_ROW
    assert row["observed_contact_rows"] <= row["contact_row_cap"]
    assert row["observed_contact_rows"] == _summary(stem)["telemetry"]["contact_rows"]
    assert budgets["contact_rows_per_trace_row"] == CONTACT_ROWS_PER_TRACE_ROW
    assert budgets["worst_observed_contact_rows_per_state"] <= row["contact_row_cap"] / max(
        row["required_state_rows"], 1)
