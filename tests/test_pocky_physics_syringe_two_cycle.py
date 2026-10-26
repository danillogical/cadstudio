"""Pocky syringe two-cycle dispense: frozen-criteria equality, scenario order, optional run evidence.

Cycle 1 of ``syringe_two_cycle_acceptance.json`` must carry the frozen ``acceptance.toml`` numbers
unchanged (only the ``bodies``/``support_bodies`` bindings differ), and cycle 2 must be a pure
renaming of cycle 1 (names, event links, windows, phases; the cycle-2 identity list), with no
numeric field changed.

The recorded runs ``out/mujoco-two-cycle/<variant>`` are optional generated evidence. An absent
run directory skips its tests; one that exists but is incomplete fails loudly. Expected, recorded
outcome: the wedge separator passes both cycles on the clamped housing; the blade holds packet 2
up (``zero_feed``) so cycle 2 fails.

Run with: ``uv run --frozen --extra physics pytest tests/test_pocky_physics_syringe_two_cycle.py -q``.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

pytest.importorskip("mujoco", reason="optional physics extra not installed")

from cadkit.params import REPO_ROOT  # noqa: E402
from cadkit.physics.scenario import (  # noqa: E402
    load_acceptance,
    load_acceptance_toml,
    load_scenario,
)

PHYS = REPO_ROOT / "projects" / "pocky" / "physics"
FROZEN_TOML = PHYS / "acceptance.toml"
ACCEPTANCE = PHYS / "syringe_two_cycle_acceptance.json"
SCENARIO = PHYS / "scenarios" / "syringe_two_cycle.json"
RUN_ROOT = REPO_ROOT / "out" / "mujoco-two-cycle"
RUN_FILES = (
    "summary.json", "manifest.json", "scenario.json", "acceptance.lock.json", "trace.csv",
    "contacts.csv", "states.npz", "state_meta.json", "checkpoints.npz", "report.json",
    "report.md", "scene.xml", "assembly_options.lock.toml",
)
CYCLE1_BODIES = ["packet", "packet_02", "packet_03"]
CYCLE2_BODIES = ["packet_02", "packet_03"]
EVENT_PAIRS = (("packet_exit", "packet_exit_2"), ("packet_presentation", "packet_presentation_2"))
CHECK_PAIRS = (("exactly_one_packet", "exactly_one_packet_2"),
               ("pickup_ready", "pickup_ready_2"))
# Fields that legitimately differ between a cycle-1 item and its cycle-2 copy.
EVENT_RENAMED = ("name", "window_from", "window_to", "release_phase", "dwell_from", "dwell_to")
EVENT_REBOUND = ("bodies",)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def acceptance():
    return load_acceptance(ACCEPTANCE)


@pytest.fixture(scope="module")
def scenario():
    return load_scenario(SCENARIO)


@pytest.fixture(scope="module")
def frozen():
    return load_acceptance_toml(FROZEN_TOML)


def _events(spec) -> dict:
    return {e.name: e for e in spec.events}


def _checks(spec) -> dict:
    return {c.name: c for c in spec.checks}


# --------------------------------------------------------------- criteria
def test_cycle_1_events_equal_the_frozen_toml_except_the_bindings(acceptance, frozen):
    events, want_events = _events(acceptance), _events(frozen)
    for name, _ in EVENT_PAIRS:
        got, want = events[name].to_dict(), want_events[name].to_dict()
        assert got.pop("bodies") == CYCLE1_BODIES, name
        want.pop("bodies")
        if name == "packet_presentation":
            assert got.pop("support_bodies") == ["housing"]
            want.pop("support_bodies")
        assert got == want, name


def test_cycle_1_checks_equal_the_frozen_toml(acceptance, frozen):
    for name, _ in CHECK_PAIRS:
        assert _checks(acceptance)[name].to_dict() == _checks(frozen)[name].to_dict(), name


def test_cycle_2_events_are_cycle_1_renamed_with_no_numeric_change(acceptance):
    events = _events(acceptance)
    for first, second in EVENT_PAIRS:
        one, two = events[first].to_dict(), events[second].to_dict()
        assert set(one) == set(two), second
        assert two["name"] == first + "_2"
        assert two["bodies"] == CYCLE2_BODIES, second
        for field in EVENT_RENAMED[1:]:
            if field in one:
                assert two[field] == one[field] + "_2", (second, field)
        skipped = set(EVENT_RENAMED) | set(EVENT_REBOUND)
        for field in set(one) - skipped:
            assert two[field] == one[field], (second, field)


def test_cycle_2_checks_are_cycle_1_renamed_and_relinked(acceptance):
    checks = _checks(acceptance)
    for first, second in CHECK_PAIRS:
        one, two = checks[first].to_dict(), checks[second].to_dict()
        assert set(one) == set(two), second
        assert two["name"] == first + "_2"
        assert two["event"] == one["event"] + "_2"
        for field in set(one) - {"name", "event"}:
            assert two[field] == one[field], (second, field)


def test_acceptance_declares_both_cycles_and_the_home_check(acceptance):
    assert [e.name for e in acceptance.events] == [pair[i] for i in (0, 1) for pair in EVENT_PAIRS]
    names = {c.name for c in acceptance.checks}
    assert {n for pair in CHECK_PAIRS for n in pair} <= names
    assert "slider_home_release" in names and "penetration" in names
    for cycle_checks in ("exactly_one_packet", "exactly_one_packet_2"):
        assert _checks(acceptance)[cycle_checks].expected == 1


# --------------------------------------------------------------- scenario
def test_scenario_phase_order_matches_both_cycles_windows(scenario, acceptance):
    order = [phase.name for phase in scenario.phases]
    assert len(order) == len(set(order))
    idx = order.index
    assert order[0] == "reset"
    expected_order = ["reset", "settle", "actuate", "press_hold", "release", "hold", "pickup",
                      "pickup_hold", "settle_2", "actuate_2", "press_hold_2", "release_2", "hold_2"]
    assert order == expected_order
    for event in acceptance.events:
        assert idx(event.window_from) <= idx(event.window_to), event.name
    for event in (e for e in acceptance.events if e.kind == "supported_presentation"):
        chain = [event.window_from, event.release_phase, event.dwell_from, event.dwell_to,
                 event.window_to]
        assert [idx(n) for n in chain] == sorted(idx(n) for n in chain), event.name
    events = _events(acceptance)
    # Cycle 1 completes (hold) before the pickup, which completes before cycle 2 starts.
    assert idx(events["packet_presentation"].window_to) < idx("pickup")
    assert idx("pickup_hold") < idx(events["packet_exit_2"].window_from)
    for check in acceptance.checks:
        for field in ("phase", "from_phase", "to_phase"):
            value = getattr(check, field)
            if value is not None:
                assert value == "initial" or value in order, (check.name, field)


def test_scenario_has_a_pickup_phase_forcing_packet_one(scenario):
    phases = {phase.name: phase for phase in scenario.phases}
    pickup = phases["pickup"]
    assert pickup.body_force is not None
    assert pickup.body_force.body == "packet"
    assert pickup.body_force.force_n[0] == 0.0 and pickup.body_force.force_end_n[0] > 0.0
    hold = phases["pickup_hold"]
    assert hold.body_force is not None and hold.body_force.body == "packet"
    assert hold.body_force.force_n == pickup.body_force.force_end_n
    # No actuator input while the hand pulls the packet out.
    assert pickup.actuator is None and hold.actuator is None


# --------------------------------------------------------------- recorded runs (optional)
def _load_run(variant: str) -> tuple[Path, dict]:
    """Skip only when the run directory is absent; an incomplete directory fails loudly."""
    run = RUN_ROOT / variant
    if not run.is_symlink() and not run.exists():
        pytest.skip(f"optional generated evidence absent: {run} does not exist")
    assert run.is_dir(), f"broken evidence: {run} is not a directory"
    missing = [f for f in RUN_FILES if not (run / f).is_file()]
    assert not missing, f"broken evidence: {run} lacks {missing}"
    return run, json.loads((run / "summary.json").read_text(encoding="utf-8"))


def _by_name(items) -> dict:
    return {item["name"]: item for item in items}


@pytest.mark.parametrize("variant", ["wedge_clamped", "blade_clamped"])
def test_recorded_run_is_valid_and_bound_to_the_current_files(variant, scenario, acceptance):
    _, summary = _load_run(variant)
    assert summary["scenario"]["hash"] == scenario.hash()
    assert summary["scenario"]["sha256"] == _sha256(SCENARIO)
    assert summary["acceptance"]["hash"] == acceptance.hash()
    assert summary["acceptance"]["sha256"] == _sha256(ACCEPTANCE)
    assert summary["validity"]["ok"] is True
    assert summary["validity"]["reasons"] == []
    assert summary["telemetry"]["stopped"] is False


def test_wedge_clamped_run_dispenses_and_presents_both_packets():
    _, summary = _load_run("wedge_clamped")
    assert summary["status"] == "PASS"
    checks = _by_name(summary["checks"])
    for name in ("exactly_one_packet", "exactly_one_packet_2", "pickup_ready", "pickup_ready_2"):
        assert checks[name]["status"] == "PASS", name
    events = _by_name(summary["events"])
    for name in ("packet_presentation", "packet_presentation_2"):
        assert events[name]["verdict_code"] == "supported_presentation", name


def test_blade_clamped_run_holds_packet_two_up_so_cycle_two_fails():
    _, summary = _load_run("blade_clamped")
    assert summary["status"] == "FAIL"
    checks = _by_name(summary["checks"])
    assert checks["pickup_ready_2"]["status"] == "FAIL"
    events = _by_name(summary["events"])
    assert events["packet_presentation_2"]["verdict_code"] == "zero_feed"
    assert "zero_feed" in checks["pickup_ready_2"]["detail"]
