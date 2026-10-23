"""Pocky validated-numerics tests: option bounds, assembly wiring, frozen S0V/S1 documents.

Run with the optional physics extra:
``uv run --frozen --extra physics pytest tests/test_pocky_physics_valid_numerics.py -q``.
"""
from __future__ import annotations

import math
import subprocess
import tomllib
from pathlib import Path

import pytest

from cadkit.params import REPO_ROOT
from cadkit.physics.scenario import load_acceptance, load_scenario
from projects.pocky.physics.options import AssemblyOptions, load_options

PHYS = REPO_ROOT / "projects" / "pocky" / "physics"
OPTIONS = PHYS / "options"
SCENARIOS = PHYS / "scenarios"
DEFAULT_SCENE_HASH_PREFIX = "2c4bd425c55d9f56"
V_NAMES = ("f000", "f025", "f050", "f075", "f100", "half_dt", "spring_high", "spring_low")


# ------------------------------------------------------------------ options
@pytest.mark.parametrize("key", ["contact_timeconst_s", "stop_timeconst_s"])
@pytest.mark.parametrize("value", [2e-3, 2.5e-4])
def test_timeconst_allowed_values(key, value):
    ts = 6.25e-5 if value == 2.5e-4 else 1e-3
    opts = load_options({key: value, "timestep_s": ts})
    assert getattr(opts, key) == value


@pytest.mark.parametrize("key", ["contact_timeconst_s", "stop_timeconst_s"])
@pytest.mark.parametrize("value", [1e-3, 5e-4, 0.0, -2e-3, 2.5e-3, 1, True, False,
                                   math.nan, math.inf, -math.inf, "0.002", None])
def test_timeconst_rejects_other_values(key, value):
    with pytest.raises(ValueError):
        load_options({key: value, "timestep_s": 6.25e-5})


@pytest.mark.parametrize("ts", [1e-3, 5e-4, 6.25e-5, 3.125e-5])
def test_timestep_allowed_values(ts):
    assert load_options({"timestep_s": ts}).timestep_s == ts


@pytest.mark.parametrize("ts", [2e-3, 1e-4, 0.0, -1e-3, True, math.nan, math.inf, "1e-3"])
def test_timestep_rejects_other_values(ts):
    with pytest.raises(ValueError):
        load_options({"timestep_s": ts})


@pytest.mark.parametrize("key", ["contact_timeconst_s", "stop_timeconst_s"])
def test_timeconst_below_two_timesteps_is_rejected_clearly(key):
    # 2.5e-4 < 2 x 1e-3 and 2.5e-4 < 2 x 5e-4.
    for ts in (1e-3, 5e-4):
        with pytest.raises(ValueError, match="2 x timestep"):
            load_options({key: 2.5e-4, "timestep_s": ts})
    # The default 2 ms timeconst is also too small for no allowed timestep, but the
    # equality edge (tc == 2 dt) must be accepted.
    assert load_options({key: 2.5e-4, "timestep_s": 6.25e-5}).timestep_s == 6.25e-5
    assert load_options({key: 2.5e-4, "timestep_s": 3.125e-5}).timestep_s == 3.125e-5


def test_default_timeconst_is_checked_against_timestep_too():
    # Defaults (2 ms) are fine for every allowed timestep.
    for ts in (1e-3, 5e-4, 6.25e-5, 3.125e-5):
        load_options({"timestep_s": ts})


def test_button_actuator_must_be_bool_default_false():
    assert load_options({}).button_actuator is False
    assert load_options(None).button_actuator is False
    assert load_options({"button_actuator": True}).button_actuator is True
    assert load_options({"button_actuator": False}).button_actuator is False
    for bad in (1, 0, 1.0, "true", None, [True]):
        with pytest.raises(ValueError):
            load_options({"button_actuator": bad})


def test_defaults_unchanged_and_canonical_toml_byte_identical():
    opts = load_options(None)
    assert opts == AssemblyOptions()
    assert (opts.spring_stiffness_n_m, opts.timestep_s) == (500.0, 1e-3)
    assert (opts.contact_timeconst_s, opts.stop_timeconst_s) == (2e-3, 2e-3)
    assert opts.canonical_toml() == "spring_stiffness_n_m = 500.0\ntimestep_s = 0.001\n"
    assert opts.as_dict() == {"spring_stiffness_n_m": 500.0, "timestep_s": 0.001}
    half = load_options({"timestep_s": 5e-4, "spring_stiffness_n_m": 200})
    assert half.canonical_toml() == "spring_stiffness_n_m = 200.0\ntimestep_s = 0.0005\n"
    assert set(half.as_dict()) == {"spring_stiffness_n_m", "timestep_s"}


def test_new_keys_emitted_only_when_non_default():
    valid = load_options({"timestep_s": 6.25e-5, "contact_timeconst_s": 2.5e-4,
                          "stop_timeconst_s": 2.5e-4})
    text = valid.canonical_toml()
    assert "contact_timeconst_s" in text and "stop_timeconst_s" in text
    assert "button_actuator" not in text
    assert tomllib.loads(text)["contact_timeconst_s"] == 2.5e-4
    assert "button_actuator = true" in load_options({"button_actuator": True}).canonical_toml()
    # One non-default time constant is enough to emit both.
    one = load_options({"timestep_s": 6.25e-5, "stop_timeconst_s": 2.5e-4})
    assert "contact_timeconst_s" in one.canonical_toml()


# ------------------------------------------------------------------ assembly
pytest.importorskip("mujoco", reason="optional physics extra not installed")

from cadkit.physics.scene import export_scene  # noqa: E402
from projects.pocky import PROJECT  # noqa: E402
from projects.pocky.params import load_params  # noqa: E402
from projects.pocky.physics import assembly as asm  # noqa: E402
from projects.pocky.physics.assembly import prototype_assembly  # noqa: E402


@pytest.fixture(scope="module")
def params():
    return load_params(PROJECT.params_path)


def _joints(spec):
    return [b.joint for b in spec.bodies if b.joint is not None]


def test_valid_constants():
    assert asm.VALID_CONTACT_TIMECONST_S == 2.5e-4
    assert asm.VALID_TIMESTEP_S == 6.25e-5
    assert asm.CONTACT_TIMECONST_S == 2e-3 and asm.STOP_TIMECONST_S == 2e-3


def test_assembly_defaults_equal_existing_constants(params):
    spec = prototype_assembly(params)
    assert spec.contact_timeconst_s == asm.CONTACT_TIMECONST_S == 2e-3
    joints = _joints(spec)
    assert len(joints) == 3
    assert all(j.stop_timeconst_s == asm.STOP_TIMECONST_S == 2e-3 for j in joints)


def test_assembly_applies_time_constants_to_spec_and_every_joint(params):
    spec = prototype_assembly(
        params, timestep_s=asm.VALID_TIMESTEP_S,
        contact_timeconst_s=asm.VALID_CONTACT_TIMECONST_S, stop_timeconst_s=2.5e-4)
    assert spec.contact_timeconst_s == 2.5e-4
    assert spec.timestep_s == 6.25e-5
    joints = _joints(spec)
    assert {j.joint_id for j in joints} == {"crank_phi", "rod_x", "pusher_x"}
    assert all(j.stop_timeconst_s == 2.5e-4 for j in joints)


def test_contact_and_stop_constants_are_independent(params):
    spec = prototype_assembly(params, timestep_s=6.25e-5, contact_timeconst_s=2.5e-4,
                              stop_timeconst_s=2e-3)
    assert spec.contact_timeconst_s == 2.5e-4
    assert all(j.stop_timeconst_s == 2e-3 for j in _joints(spec))


@pytest.mark.parametrize("bad", [0.0, -1e-3, math.nan, math.inf])
def test_assembly_rejects_non_positive_time_constants(params, bad):
    with pytest.raises(ValueError):
        prototype_assembly(params, contact_timeconst_s=bad)
    with pytest.raises(ValueError):
        prototype_assembly(params, stop_timeconst_s=bad)


def test_button_actuator_adds_exactly_one_force_actuator_on_rod(params):
    assert prototype_assembly(params).actuators == ()
    assert prototype_assembly(params, button_actuator=False).actuators == ()
    acts = prototype_assembly(params, button_actuator=True).actuators
    assert len(acts) == 1
    act = acts[0]
    assert act.joint_id == "rod_x"
    assert act.kind == "force"
    assert act.max_effort == 25.0
    assert act.actuator_id == "button"


def test_default_scene_hash_unchanged_through_project_hook(params, tmp_path):
    spec = PROJECT.physics("prototype", params)
    result = export_scene(spec, tmp_path / "export")
    assert result.scene_hash.startswith(DEFAULT_SCENE_HASH_PREFIX)
    # An explicit empty options table is the same scene.
    spec2 = PROJECT.physics_with_options("prototype", params, {})
    assert export_scene(spec2, tmp_path / "export2").scene_hash == result.scene_hash


# ------------------------------------------------------------------ option files
def _options_toml(name):
    return tomllib.loads((OPTIONS / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["s0v_base", "s0v_half_dt", "s0v_spring_high",
                                  "s0v_spring_low", "s1_press"])
def test_new_options_files_load(name):
    opts = load_options(_options_toml(f"{name}.toml"))
    assert opts.contact_timeconst_s == opts.stop_timeconst_s == 2.5e-4
    assert opts.timestep_s in (6.25e-5, 3.125e-5)
    assert opts.button_actuator is (name == "s1_press")


def test_option_file_values():
    assert load_options(_options_toml("s0v_base.toml")).timestep_s == 6.25e-5
    assert load_options(_options_toml("s0v_half_dt.toml")).timestep_s == 3.125e-5
    assert load_options(_options_toml("s0v_spring_high.toml")).spring_stiffness_n_m == 1000.0
    assert load_options(_options_toml("s0v_spring_low.toml")).spring_stiffness_n_m == 200.0
    assert load_options(_options_toml("s1_press.toml")).spring_stiffness_n_m == 500.0


# ------------------------------------------------------------------ scenarios
def _options_for(name):
    if name.startswith("f"):
        return load_options(_options_toml("s0v_base.toml"))
    return load_options(_options_toml(f"s0v_{name}.toml"))


@pytest.mark.parametrize("name", V_NAMES)
def test_s0v_scenario_matches_options_and_s0_counterpart(name):
    sc = load_scenario(SCENARIOS / f"s0v_{name}.json")
    old = load_scenario(SCENARIOS / f"s0_{name}.json")
    opts = _options_for(name)
    assert sc.timestep_s == opts.timestep_s
    assert sc.sampling_interval_s == sc.timestep_s
    assert sc.fixture == old.fixture
    assert [p.to_dict() for p in sc.phases] == [p.to_dict() for p in old.phases]
    assert sc.reset_phase.to_dict() == old.reset_phase.to_dict()
    total = sum(p.duration_s for p in sc.timed_phases)
    steps = round(total / sc.timestep_s)
    b = sc.budgets
    assert b.max_steps >= steps
    assert b.max_sim_time_s >= total
    assert b.max_state_rows is not None and b.max_state_rows >= steps
    assert b.max_state_bytes is not None and b.max_state_bytes > 0
    assert b.max_trace_rows >= steps


def test_s1_press_scenario_loads_and_budgets_cover_steps():
    sc = load_scenario(SCENARIOS / "s1_press.json")
    opts = load_options(_options_toml("s1_press.toml"))
    assert sc.timestep_s == opts.timestep_s
    total = sum(p.duration_s for p in sc.timed_phases)
    steps = round(total / sc.timestep_s)
    assert sc.budgets.max_steps >= steps
    assert sc.budgets.max_state_rows >= steps
    assert sc.budgets.max_sim_time_s >= total
    assert any(p.kind == "actuate" and p.actuator == "button" for p in sc.timed_phases)


def test_s1_acceptance_loads():
    ac = load_acceptance(PHYS / "s1_acceptance.json")
    assert ac.acceptance_id == "pocky_m5a1_s1_press"
    assert len(ac.checks) > 0


# ------------------------------------------------------------------ frozen S0 documents
def _tracked_s0_paths():
    out = subprocess.run(["git", "ls-files", "projects/pocky/physics"], cwd=REPO_ROOT,
                         capture_output=True, text=True, check=True).stdout.split()
    return [p for p in out if "/s0_" in p or p.endswith("s0_acceptance.json")]


def test_s0_inventory_is_what_we_expect():
    paths = _tracked_s0_paths()
    assert len(paths) >= 12  # 8 scenarios + 3 options + acceptance


@pytest.mark.parametrize("rel", _tracked_s0_paths())
def test_s0_documents_unchanged_versus_head(rel):
    head = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=REPO_ROOT,
                          capture_output=True, check=True).stdout
    assert (REPO_ROOT / rel).read_bytes() == head
