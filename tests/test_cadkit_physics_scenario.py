"""M4a strict scenario/acceptance loading, schemas, hashes and budget preflight."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cadkit.params import REPO_ROOT
from cadkit.physics.runner import preflight
from cadkit.physics.scenario import (
    CHECK_KINDS,
    FIXTURE_IDS,
    SCENARIO_SCHEMA_VERSION,
    AcceptanceSpec,
    CheckSpec,
    ScenarioError,
    ValiditySpec,
    build_fixture,
    load_acceptance,
    load_scenario,
)


def scenario_dict(**overrides):
    base = {
        "schema_version": SCENARIO_SCHEMA_VERSION,
        "scenario_id": "loaded_slider",
        "fixture": "loaded_slider",
        "seed": 7,
        "timestep_s": 0.001,
        "sampling_interval_s": 0.002,
        "budgets": {"max_steps": 20000, "max_sim_time_s": 10.0,
                    "max_trace_rows": 20000},
        "phases": [
            {"name": "reset", "kind": "reset", "initial": {"carriage_slide": 0.0}},
            {"name": "settle", "kind": "settle", "duration_s": 0.3},
            {"name": "push", "kind": "actuate", "duration_s": 0.6,
             "actuator": "push", "effort": 1.0},
            {"name": "release", "kind": "release", "duration_s": 0.6},
        ],
    }
    base.update(overrides)
    return base


def acceptance_dict(**overrides):
    base = {
        "schema_version": SCENARIO_SCHEMA_VERSION,
        "acceptance_id": "loaded_slider_acceptance",
        "validity": {"max_penetration_m": 0.001, "max_speed_m_s": 1.0,
                     "max_energy_j": 1.0},
        "checks": [
            {"name": "held", "kind": "joint_displacement", "joint": "carriage_slide",
             "to_phase": "push", "expected": 0.02, "tolerance": 0.001, "units": "m"},
            {"name": "return", "kind": "return_displacement", "joint": "carriage_slide",
             "phase": "release", "reference": 0.0, "max": 0.0002, "units": "m"},
        ],
    }
    base.update(overrides)
    return base


def _write(path: Path, payload) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _raw(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "scenario.json"
    path.write_text(text, encoding="utf-8")
    return path


def test_valid_scenario_loads_with_typed_phases(tmp_path):
    scenario = load_scenario(_write(tmp_path / "s.json", scenario_dict()))
    assert scenario.scenario_id == "loaded_slider"
    assert [p.kind for p in scenario.phases] == ["reset", "settle", "actuate", "release"]
    assert scenario.reset_phase.initial == (("carriage_slide", 0.0),)
    assert scenario.hash() == scenario.hash()


def test_unknown_scenario_field_is_rejected(tmp_path):
    payload = scenario_dict()
    payload["scene_xml"] = "/etc/passwd"
    with pytest.raises(ScenarioError, match="unknown field"):
        load_scenario(_write(tmp_path / "s.json", payload))


def test_unsupported_version_is_rejected(tmp_path):
    with pytest.raises(ScenarioError, match="unsupported scenario schema_version"):
        load_scenario(_write(tmp_path / "s.json", scenario_dict(schema_version="m3-9")))


def test_duplicate_json_key_is_rejected(tmp_path):
    text = """{"schema_version": "m4a-1", "scenario_id": "x", "fixture": "loaded_slider",
    "budgets": {"max_steps": 1, "max_sim_time_s": 1, "max_trace_rows": 1},
    "phases": [{"name": "reset", "kind": "reset"}],
    "scenario_id": "y"}
    """
    with pytest.raises(ScenarioError, match="duplicate JSON key"):
        load_scenario(_raw(tmp_path, text))


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_constants_are_rejected(tmp_path, literal):
    payload = scenario_dict()
    text = json.dumps(payload).replace('"effort": 1.0', f'"effort": {literal}')
    with pytest.raises(ScenarioError, match="non-finite JSON constant"):
        load_scenario(_raw(tmp_path, text))


def test_scenario_cannot_reference_assets_or_paths(tmp_path):
    for field in ("assets", "asset_path", "scene_xml"):
        payload = scenario_dict()
        payload[field] = "/tmp/not-allowed"
        with pytest.raises(ScenarioError, match="unknown field"):
            load_scenario(_write(tmp_path / f"{field}.json", payload))


def test_reserved_state_names_cannot_be_phase_names(tmp_path):
    payload = scenario_dict()
    payload["phases"][1]["name"] = "initial"
    with pytest.raises(ScenarioError, match="reserved"):
        load_scenario(_write(tmp_path / "s.json", payload))


def test_oversized_number_is_rejected_not_overflow(tmp_path):
    text = json.dumps(scenario_dict()).replace(
        '"effort": 1.0', '"effort": 1' + "0" * 400)
    with pytest.raises(ScenarioError, match="representable number"):
        load_scenario(_raw(tmp_path, text))


def test_deeply_nested_json_is_rejected_not_recursion(tmp_path):
    nested = '{"x":' * 20000 + "1" + "}" * 20000
    text = json.dumps(scenario_dict()).replace('"effort": 1.0', '"effort": ' + nested)
    with pytest.raises(ScenarioError, match="nested too deeply"):
        load_scenario(_raw(tmp_path, text))


def test_huge_sampling_interval_is_rejected_at_preflight(tmp_path):
    scenario = load_scenario(_write(tmp_path / "s.json",
                                    scenario_dict(sampling_interval_s=1e308)))
    spec = build_fixture(scenario.fixture, scenario.timestep_s)
    with pytest.raises(ScenarioError, match="not representable"):
        preflight(scenario, spec)


def test_huge_phase_duration_is_rejected_at_preflight(tmp_path):
    payload = scenario_dict()
    payload["phases"][1]["duration_s"] = 1e308
    scenario = load_scenario(_write(tmp_path / "s.json", payload))
    spec = build_fixture(scenario.fixture, scenario.timestep_s)
    with pytest.raises(ScenarioError, match="not representable"):
        preflight(scenario, spec)


def test_unknown_fixture_is_rejected_by_registry_execution(tmp_path):
    scenario = load_scenario(_write(tmp_path / "s.json", scenario_dict(fixture="pocky")))
    with pytest.raises(ScenarioError, match="unknown fixture"):
        build_fixture(scenario.fixture, scenario.timestep_s)


def test_reset_must_be_first_and_unique(tmp_path):
    payload = scenario_dict()
    payload["phases"] = [
        {"name": "settle", "kind": "settle", "duration_s": 0.1},
        {"name": "reset", "kind": "reset"},
    ]
    with pytest.raises(ScenarioError, match="exactly one reset phase"):
        load_scenario(_write(tmp_path / "s.json", payload))


def test_actuate_requires_actuator_and_effort(tmp_path):
    payload = scenario_dict()
    payload["phases"][2].pop("effort")
    with pytest.raises(ScenarioError, match="needs actuator and effort"):
        load_scenario(_write(tmp_path / "s.json", payload))


def test_non_actuate_phase_rejects_effort(tmp_path):
    payload = scenario_dict()
    payload["phases"][1]["effort"] = 1.0
    with pytest.raises(ScenarioError, match="must not declare actuator or effort"):
        load_scenario(_write(tmp_path / "s.json", payload))


def test_acceptance_requires_checks_and_rejects_unknown_fields(tmp_path):
    with pytest.raises(ScenarioError, match="non-empty"):
        load_acceptance(_write(tmp_path / "a.json", acceptance_dict(checks=[])))
    payload = acceptance_dict()
    payload["checks"][0]["window"] = "all"
    with pytest.raises(ScenarioError, match="unknown field"):
        load_acceptance(_write(tmp_path / "a.json", payload))


def test_acceptance_hash_is_separate_and_stable(tmp_path):
    first = load_acceptance(_write(tmp_path / "a.json", acceptance_dict()))
    second = load_acceptance(_write(tmp_path / "b.json", acceptance_dict()))
    assert first.hash() == second.hash()
    payload = acceptance_dict()
    payload["checks"][0]["tolerance"] = 0.002
    changed = load_acceptance(_write(tmp_path / "c.json", payload))
    assert changed.hash() != first.hash()


def test_zero_step_phase_is_rejected_before_stepping(tmp_path):
    payload = scenario_dict()
    payload["phases"][1]["duration_s"] = 0.0004  # rounds to zero at 1 ms
    scenario = load_scenario(_write(tmp_path / "s.json", payload))
    spec = build_fixture(scenario.fixture, scenario.timestep_s)
    with pytest.raises(ScenarioError, match="rounds to zero steps"):
        preflight(scenario, spec)


@pytest.mark.parametrize("budget,value,message", [
    ("max_steps", 100, "step count"),
    ("max_sim_time_s", 0.2, "simulated time"),
    ("max_trace_rows", 5, "trace rows"),
])
def test_preflight_rejects_each_total_budget(tmp_path, budget, value, message):
    payload = scenario_dict()
    payload["budgets"][budget] = value
    scenario = load_scenario(_write(tmp_path / "s.json", payload))
    spec = build_fixture(scenario.fixture, scenario.timestep_s)
    with pytest.raises(ScenarioError, match=message):
        preflight(scenario, spec)


def test_empty_acceptance_cannot_pass():
    """Even if a caller constructs an AcceptanceSpec directly, no checks is no PASS."""
    from cadkit.physics.evaluate import evaluate

    class EmptyTelemetry:
        invalid = []
        stopped = False
        peak_penetration_m = 0.0
        peak_speed = 0.0
        peak_energy_j = 0.0
        trace_rows = []
        contact_rows = []
        contact_pairs = {}

        def metrics(self):
            return {}

        def contacts(self):
            return []

    scenario = load_scenario_stub()
    acceptance = AcceptanceSpec("empty", (), ValiditySpec(), "")
    evaluation = evaluate(scenario, acceptance, EmptyTelemetry())
    assert evaluation.status == "INCONCLUSIVE"
    assert any("no required checks" in r["reason"] for r in evaluation.validity["reasons"])


def load_scenario_stub():
    from cadkit.physics.scenario import BudgetSpec, PhaseSpec, ScenarioSpec

    return ScenarioSpec("stub", "loaded_slider", 0,
                        (PhaseSpec("reset", "reset"),
                         PhaseSpec("settle", "settle", 0.1)),
                        0.001, 0.002, BudgetSpec(100, 1.0, 100))


def test_published_schemas_match_code_allowlists():
    scenario_schema = json.loads(
        (REPO_ROOT / "docs" / "physics-m4a-scenario.schema.json").read_text())
    acceptance_schema = json.loads(
        (REPO_ROOT / "docs" / "physics-m4a-acceptance.schema.json").read_text())
    summary_schema = json.loads(
        (REPO_ROOT / "docs" / "physics-m4a-summary.schema.json").read_text())
    assert scenario_schema["properties"]["schema_version"]["const"] == \
        SCENARIO_SCHEMA_VERSION
    # JSON execution enforces the registry allowlist in ``build_fixture``; the schema
    # publishes the safe-id pattern because typed ``run_assembly`` callers may use their own
    # label.
    assert scenario_schema["properties"]["fixture"]["type"] == "string"
    for fixture_id in FIXTURE_IDS:
        assert build_fixture(fixture_id, 0.001) is not None
    kinds = set()
    for item in acceptance_schema["properties"]["checks"]["items"]["oneOf"]:
        kinds.add(item["properties"]["kind"]["const"])
    assert kinds == set(CHECK_KINDS)
    assert summary_schema["properties"]["status"]["enum"] == \
        ["PASS", "FAIL", "INCONCLUSIVE", "ERROR"]
