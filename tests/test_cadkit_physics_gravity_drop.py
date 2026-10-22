"""The primitive gravity fixture: analytic free fall, settle, determinism, negatives."""
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cadkit.params import REPO_ROOT
from cadkit.physics import EXIT_CODES, PhysicsUnavailable

pytest.importorskip("mujoco", reason="optional physics extra not installed")

from cadkit.physics.gravity_drop import (  # noqa: E402
    DropSpec,
    cross_check_solid,
    scene_hash,
    scene_xml,
    simulate,
)
from cadkit.physics.run import evaluate, run_smoke  # noqa: E402
from cadkit.physics.units import GRAVITY, m_to_mm  # noqa: E402


@pytest.fixture(scope="module")
def spec():
    return DropSpec()


@pytest.fixture(scope="module")
def sim(spec):
    return simulate(spec)


def test_box_is_20mm_and_100mm_above_floor(spec):
    assert spec.edge_mm == 20.0
    # bottom at z=0.1 m, so the COM is one half-edge above that
    assert spec.com_z0_m == pytest.approx(0.1 + 0.01)
    assert spec.fall_distance_m == pytest.approx(0.1)


def test_mass_and_inertia_match_closed_form(spec, sim):
    analytic_mass = 8000.0 * 1.27 * 1e-6  # mm3 * g/cm3 * 1e-6
    analytic_inertia = analytic_mass * 0.02 ** 2 / 6.0  # m a^2 / 6 for a cube
    assert spec.mass_kg == pytest.approx(analytic_mass)
    assert sim.mass_kg == pytest.approx(analytic_mass, rel=1e-9)
    for value in sim.inertia_diag:
        assert value == pytest.approx(analytic_inertia, rel=1e-6)


def test_build123d_crosscheck_matches_analytic(spec):
    x = cross_check_solid(spec)
    assert x["volume_mm3"] == pytest.approx(8000.0, rel=1e-12)
    assert x["mass_kg"] == pytest.approx(8000.0 * 1.27 * 1e-6, rel=1e-12)
    assert x["inertia_diag_kg_m2"] == pytest.approx(x["analytic_inertia_kg_m2"], rel=1e-9)


def test_freefall_matches_half_g_t_squared(spec, sim):
    """Independent analytic reference, computed here rather than read from the report."""
    for t in (0.02, 0.05, 0.10, 0.12):
        idx = int(abs(sim.times - t).argmin())
        measured = spec.com_z0_m - sim.com_z[idx]
        expected = 0.5 * GRAVITY * sim.times[idx] ** 2
        assert measured == pytest.approx(expected, rel=1e-6)


def test_contact_time_matches_sqrt_2h_over_g(spec, sim):
    expected = math.sqrt(2.0 * 0.1 / GRAVITY)
    assert expected == pytest.approx(0.1428, abs=1e-4)
    first = sim.times[sim.contact_count > 0]
    assert first.size > 0
    assert first[0] == pytest.approx(expected, abs=0.005)


def test_settles_on_floor(spec, sim):
    bottom_mm = m_to_mm(float(sim.com_z[-1])) - spec.edge_mm / 2.0
    assert abs(bottom_mm) <= 0.1
    assert abs(float(sim.com_vz[-1])) <= 0.01


def test_all_checks_pass(spec, sim):
    checks = evaluate(spec, sim)
    failed = [c.name for c in checks if c.status not in ("PASS",)]
    assert failed == [], failed


def test_scene_hash_is_identity(spec, sim):
    xml = scene_xml(spec)
    assert scene_hash(xml, spec, sim.mujoco_version) == scene_hash(
        scene_xml(DropSpec()), DropSpec(), sim.mujoco_version)
    assert scene_hash(xml, spec, sim.mujoco_version) != scene_hash(
        xml, DropSpec(timestep_s=5e-4), sim.mujoco_version)


def test_two_runs_are_identical(spec, sim):
    """Same input, same compiled scene, same numbers to the last sampled digit."""
    again = simulate(spec)
    assert again.mujoco_version == sim.mujoco_version
    assert scene_hash(scene_xml(spec), spec, again.mujoco_version) == scene_hash(
        scene_xml(spec), spec, sim.mujoco_version)
    assert again.n_steps == sim.n_steps
    assert (again.times == sim.times).all()
    assert (again.com_z == sim.com_z).all()
    assert (again.com_vz == sim.com_vz).all()


def test_wrong_gravity_is_detected():
    """3.71 m/s2 (Mars) must change the trajectory, so the analytic check still passes but
    the declared-gravity check is what proves the scene honoured the input."""
    mars = DropSpec(gravity_m_s2=3.71)
    s = simulate(mars)
    assert s.gravity_z_m_s2 == pytest.approx(-3.71)
    # a slower fall than Earth for the same clearance
    assert s.times[s.contact_count > 0][0] > math.sqrt(2.0 * 0.1 / GRAVITY)


def test_gravity_sign_error_is_caught(monkeypatch):
    """A scene that emits +g instead of -g must fail declared_gravity, not be absolved by abs()."""
    from cadkit.physics import gravity_drop as gd

    spec = DropSpec()
    good = {c.name: c.status for c in evaluate(spec, simulate(spec))}
    assert good["declared_gravity"] == "PASS"

    real = gd.Simulation

    def flipped(**kwargs):
        kwargs["gravity_z_m_s2"] = -kwargs["gravity_z_m_s2"]
        return real(**kwargs)

    monkeypatch.setattr(gd, "Simulation", flipped)
    checks = {c.name: c.status for c in evaluate(spec, simulate(spec))}
    assert checks["declared_gravity"] == "FAIL", checks


def test_zero_gravity_never_passes():
    zero = DropSpec(gravity_m_s2=0.0)
    s = simulate(zero)
    checks = evaluate(zero, s)
    by_name = {c.name: c.status for c in checks}
    assert by_name["freefall"] == "INCONCLUSIVE"
    assert by_name["contact_detected"] == "INCONCLUSIVE"
    assert by_name["rest_on_floor"] == "FAIL"
    assert "PASS" != _overall(checks)


def test_unit_mixup_is_detected():
    """A metres/millimetres mix-up must fail, and the verdict must be the whole run's.

    A 200 mm box is a legitimate fixture: it compiles self-consistently and passes. A 20 m
    box cannot be anything but a unit error, and it must not pass.
    """
    huge = DropSpec(edge_mm=20_000.0)
    sim = simulate(huge)
    checks = {c.name: c.status for c in evaluate(huge, sim)}
    assert checks["si_plausibility"] == "FAIL", checks
    assert _overall(list(evaluate(huge, sim))) != "PASS"


def test_a_failing_check_never_reports_a_zero_metric():
    """A numeric sweep must never read a FAIL as perfect agreement."""
    for bad_spec in (DropSpec(edge_mm=20_000.0), DropSpec(gravity_m_s2=0.0)):
        sim = simulate(bad_spec)
        for c in evaluate(bad_spec, sim):
            if c.status == "FAIL" and c.value is not None:
                assert c.value > 0.0, (c.name, c.status, c.value, c.detail)


def test_plausible_box_passes_self_consistently():
    """Scale changes the physics, not the verdict, for an in-window box."""
    big = DropSpec(edge_mm=200.0)
    sim = simulate(big)
    checks = {c.name: c.status for c in evaluate(big, sim)}
    assert checks["si_plausibility"] == "PASS"
    assert checks["cad_analytic_crosscheck"] == "PASS"
    # 200 mm box: COM rests half the edge above the floor
    assert m_to_mm(float(sim.com_z[-1])) == pytest.approx(100.0, abs=0.5)


@pytest.mark.parametrize("bad", [
    {"edge_mm": 0.0}, {"edge_mm": -20.0}, {"density_g_cm3": 0.0},
    {"density_g_cm3": -1.0}, {"clearance_mm": 0.0}, {"timestep_s": 0.0},
    {"timestep_s": 0.05}, {"duration_s": -1.0}, {"gravity_m_s2": float("nan")},
    {"gravity_m_s2": -9.80665},
    {"duration_s": 1.0e6},          # would preallocate a multi-GB trace
    {"duration_s": 1.0, "timestep_s": 1.0e-6},  # 1e6 steps, over the budget
])
def test_invalid_spec_is_rejected(bad):
    with pytest.raises(ValueError):
        DropSpec(**bad).validate()


def _overall(checks):
    statuses = {c.status for c in checks}
    for status in ("ERROR", "FAIL", "INCONCLUSIVE"):
        if status in statuses:
            return status
    return "PASS"


def test_run_smoke_writes_artifacts(tmp_path):
    result = run_smoke(tmp_path, DropSpec())
    assert result.status == "PASS"
    assert result.exit_code == 0
    for name in ("manifest", "scene", "trace", "summary", "report"):
        assert Path(result.artifacts[name]).is_file(), name
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["scene_hash"] == result.scene_hash
    assert manifest["solver"]["timestep_s"] == 1e-3
    assert manifest["solver"]["integrator"] == "RK4"
    assert manifest["seed"] == 0
    assert manifest["versions"]["mujoco"]
    assert manifest["runtime_wall_s"] >= 0.0
    # trace has a header plus one row per sample
    rows = (tmp_path / "trace.csv").read_text().splitlines()
    assert rows[0].startswith("time_s,com_z_m")
    assert len(rows) > 10


def test_summary_json_is_strictly_parsable(tmp_path):
    """No NaN/Infinity tokens: a strict (non-Python) JSON parser must accept every artifact."""
    zero = DropSpec(gravity_m_s2=0.0)
    result = run_smoke(tmp_path, zero)
    assert result.status == "FAIL"
    for name in ("summary.json", "manifest.json"):
        text = (tmp_path / name).read_text()
        for token in ("NaN", "Infinity", "-Infinity"):
            assert token not in text, f"{name} contains {token}"
        json.loads(text, parse_constant=_reject_constant)


def _reject_constant(value):
    raise AssertionError(f"non-strict JSON constant {value}")


def test_si_plausibility_catches_a_broken_length_conversion(monkeypatch, spec):
    """Mutate the mm->m factor and confirm the check actually fails.

    A self-consistency check that can never fail is worse than no check, so this pins that
    the factor is load-bearing.
    """
    from cadkit.physics import gravity_drop as gd
    from cadkit.physics import units

    good = {c.name: c.status for c in evaluate(spec, simulate(spec))}
    assert good["si_plausibility"] == "PASS"

    monkeypatch.setattr(units, "MM_TO_M", units.MM_TO_M * 10.0)
    monkeypatch.setattr(gd, "mm_to_m", lambda v: v * units.MM_TO_M)
    sim = simulate(spec)
    checks = {c.name: c.status for c in evaluate(spec, sim)}
    assert checks["si_plausibility"] == "FAIL", checks


def test_mass_factor_is_pinned_to_an_independent_constant(monkeypatch):
    """A uniform wrong mass factor is self-consistent, so it must be pinned absolutely.

    ``mass_kg`` is the only place the factor exists; the fixture's mass at 1.27 g/cm3 is a
    physical fact (8000 mm3 -> 10.16 g -> 0.01016 kg), written here independently of the
    implementation.
    """
    from cadkit.physics import units

    assert units.mass_kg(8000.0, 1.27) == pytest.approx(0.01016, rel=1e-12)

    monkeypatch.setattr(units, "MASS_FACTOR", 1e-3)
    assert units.mass_kg(8000.0, 1.27) != pytest.approx(0.01016, rel=1e-3)


def test_unwritable_out_is_error_not_traceback(tmp_path):
    """A write failure must still emit the machine-readable status and exit 3."""
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")  # a file where a directory is needed
    result = run_smoke(blocker, DropSpec())
    assert result.status == "ERROR"  # a file where a directory is needed
    assert "could not" in result.detail
    env = _env()
    r = subprocess.run([sys.executable, "-m", "cadkit.cli", "physics", "smoke",
                        "--out", str(blocker)], cwd=REPO_ROOT, capture_output=True,
                       text=True, timeout=180, env=env)
    assert r.returncode == EXIT_CODES["ERROR"], r.stdout + r.stderr
    assert '"status": "ERROR"' in r.stdout
    assert "Traceback" not in r.stderr


def test_physics_usage_error_is_not_inconclusive():
    """argparse exits 2 on a usage error; that must not look like INCONCLUSIVE."""
    env = _env()
    for argv in (["physics"], ["physics", "smoke", "--bogus"]):
        r = subprocess.run([sys.executable, "-m", "cadkit.cli", *argv], cwd=REPO_ROOT,
                           capture_output=True, text=True, timeout=120, env=env)
        assert r.returncode == EXIT_CODES["ERROR"], (argv, r.returncode)
        assert '"status": "ERROR"' in r.stdout, argv


def test_non_default_timestep_keeps_the_penetration_envelope_consistent():
    """The envelope uses the solref time constant, not 2*dt; they coincide at dt=1 ms."""
    spec = DropSpec(timestep_s=5e-4)
    sim = simulate(spec)
    checks = {c.name: c for c in evaluate(spec, sim)}
    assert checks["transient_penetration"].status == "PASS"
    assert "0.002 s" in checks["transient_penetration"].detail


def test_report_markdown_has_uniform_columns(tmp_path):
    """A detail containing a pipe would split the table cell."""
    result = run_smoke(tmp_path, DropSpec())
    rows = [ln for ln in (tmp_path / "report.md").read_text().splitlines() if ln.startswith("| ")]
    widths = {ln.count("|") for ln in rows}
    assert widths == {5}, sorted(widths)


def test_discrete_freefall_residual_is_recorded(tmp_path):
    """RK4 at 1 ms keeps the continuum residual tiny; the value must be in summary.json.

    The gate compares against the continuum 1/2 g t^2, so the residual is the convergence
    evidence. A first-order integrator at 1 ms would sit near 1% and this asserts it does not.
    """
    result = run_smoke(tmp_path, DropSpec())
    residual = result.metrics["freefall"]
    assert residual is not None
    assert residual < 1e-6, residual


def test_exit_codes_are_distinct():
    assert EXIT_CODES == {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2, "ERROR": 3}


def test_cli_smoke_returns_zero_and_reports(tmp_path):
    env = _env()
    r = subprocess.run([sys.executable, "-m", "cadkit.cli", "physics", "smoke",
                        "--out", str(tmp_path)], cwd=REPO_ROOT, capture_output=True,
                       text=True, timeout=180, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert '"status": "PASS"' in r.stdout
    assert (tmp_path / "summary.json").is_file()


def test_cli_zero_gravity_exits_nonzero(tmp_path):
    env = _env()
    r = subprocess.run([sys.executable, "-m", "cadkit.cli", "physics", "smoke",
                        "--out", str(tmp_path), "--gravity", "0"],
                       cwd=REPO_ROOT, capture_output=True, text=True, timeout=180, env=env)
    assert r.returncode == EXIT_CODES["FAIL"], r.stdout + r.stderr
    assert '"status": "FAIL"' in r.stdout


def test_cli_invalid_density_exits_error(tmp_path):
    env = _env()
    r = subprocess.run([sys.executable, "-m", "cadkit.cli", "physics", "smoke",
                        "--out", str(tmp_path), "--density", "0"],
                       cwd=REPO_ROOT, capture_output=True, text=True, timeout=180, env=env)
    assert r.returncode == EXIT_CODES["ERROR"], r.stdout + r.stderr
    assert '"status": "ERROR"' in r.stdout
    assert "Traceback" not in r.stderr


def _env() -> dict[str, str]:
    """Subprocess env with ~/.local/bin on PATH so a bare `uv` would also resolve."""
    env = dict(os.environ)
    env["PATH"] = f"{Path.home() / '.local' / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    return env
