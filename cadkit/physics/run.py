"""Evaluation, artifacts and the minimal report for a physics run.

Kept deliberately small: M1 needs one scenario, a manifest, a trace and a readable report.
M4 will generalise the phase/telemetry layer; nothing here pre-implements it.
"""
from __future__ import annotations

import csv
import json
import math
import platform
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import CheckResult, PhysicsUnavailable, RunResult, Status
from .gravity_drop import (
    CONTACT_TIMECONST_S,
    MAX_GEOM_SIZE_M,
    MAX_MASS_KG,
    MIN_GEOM_SIZE_M,
    MIN_MASS_KG,
    FREEFALL_REL_TOL,
    REST_PENETRATION_MM,
    REST_TOL_MM,
    SCENARIO,
    TERMINAL_SPEED_TOL,
    DropSpec,
    Simulation,
    cross_check_solid,
    scene_hash,
    scene_xml,
    simulate,
)
from .units import m_to_mm

#: Fraction of the free-fall window used for the analytic comparison. 0.8 keeps several
#: trace samples of headroom before the analytic contact time, so a sample landing after
#: contact can never clip the displacement and cause a spurious failure.
FREEFALL_CHECK_FRACTION = 0.8


def _status_from(checks: list[CheckResult]) -> Status:
    if any(c.status == "ERROR" for c in checks):
        return "ERROR"
    if any(c.status == "FAIL" for c in checks):
        return "FAIL"
    if any(c.status == "INCONCLUSIVE" for c in checks):
        return "INCONCLUSIVE"
    return "PASS"


def evaluate(spec: DropSpec, sim: Simulation) -> list[CheckResult]:
    """All M1 acceptance checks, each against an independent analytic reference."""
    checks: list[CheckResult] = []

    # 0. The compiled scene must honour the declared gravity and stay in a plausible SI
    # envelope. This is what catches a mm/m or g/kg mix-up before any dynamics are read.
    # Signed: a scene that emits +g instead of -g must fail here, not be absolved by abs().
    expected_gz = -spec.gravity_m_s2
    g_ok = abs(sim.gravity_z_m_s2 - expected_gz) <= 1e-9 * max(1.0, spec.gravity_m_s2)
    checks.append(CheckResult(
        "declared_gravity", "PASS" if g_ok else "FAIL",
        f"compiled gravity_z {sim.gravity_z_m_s2:.9g} m/s2 vs declared {expected_gz:.9g}",
        abs(sim.gravity_z_m_s2 - expected_gz), "m/s2 delta"))

    # The compiled SI values must equal the declared mm/kg values. This is the check that
    # catches a wrong conversion factor; a fixed plausible-range test would not, because the
    # box size and mass scale together.
    expected_half = spec.edge_mm / 2000.0
    # Absolute SI window as well as self-consistency. Self-consistency alone cannot catch a
    # unit mix-up: a scene compiled from a wrongly-scaled spec agrees with that spec.
    in_window = (MIN_GEOM_SIZE_M <= sim.max_geom_size_m <= MAX_GEOM_SIZE_M
                 and MIN_MASS_KG <= sim.mass_kg <= MAX_MASS_KG)
    size_rel = abs(sim.max_geom_size_m - expected_half) / expected_half
    mass_rel = abs(sim.mass_kg - spec.mass_kg) / spec.mass_kg

    def _excursion(value: float, lo: float, hi: float) -> float:
        """Relative distance outside [lo, hi]; 0.0 when inside."""
        if value < lo:
            return (lo - value) / lo
        if value > hi:
            return (value - hi) / hi
        return 0.0

    # A FAIL must never carry a 0.0 metric: a sweep comparing values numerically would read
    # that as perfect agreement. The value is the largest relative violation, so it is
    # positive exactly when the check fails.
    window_violation = max(
        _excursion(sim.max_geom_size_m, MIN_GEOM_SIZE_M, MAX_GEOM_SIZE_M),
        _excursion(sim.mass_kg, MIN_MASS_KG, MAX_MASS_KG),
    )
    plausible = size_rel <= 1e-9 and mass_rel <= 1e-6 and in_window
    window_note = "" if in_window else " (OUTSIDE the absolute SI window)"
    checks.append(CheckResult(
        "si_plausibility", "PASS" if plausible else "FAIL",
        f"compiled half-size {sim.max_geom_size_m:.9g} m vs declared {expected_half:.9g} m; "
        f"compiled mass {sim.mass_kg:.9g} kg vs declared {spec.mass_kg:.9g} kg; "
        f"within the absolute window {MIN_GEOM_SIZE_M:g}..{MAX_GEOM_SIZE_M:g} m / "
        f"{MIN_MASS_KG:g}..{MAX_MASS_KG:g} kg{window_note}",
        max(size_rel, mass_rel, window_violation), "relative"))

    # 1. Free fall: displacement vs 1/2 g t^2, before contact. With no gravity there is no
    # free-fall window to compare against, so this cannot be a PASS.
    window = spec.contact_time_s * FREEFALL_CHECK_FRACTION
    mask = (sim.times > 0.0) & (sim.times <= window) if math.isfinite(window) else np.zeros(0, bool)
    if not math.isfinite(window):
        checks.append(CheckResult("freefall", "INCONCLUSIVE",
                                  "zero or negative gravity: no free-fall window to check"))
    elif not mask.any():
        checks.append(CheckResult("freefall", "ERROR", "no trace samples before contact"))
    else:
        t = sim.times[mask]
        measured = spec.com_z0_m - sim.com_z[mask]
        expected = 0.5 * spec.gravity_m_s2 * t * t
        rel = float(np.max(np.abs(measured - expected) / np.maximum(expected, 1e-12)))
        checks.append(CheckResult(
            "freefall", "PASS" if rel <= FREEFALL_REL_TOL else "FAIL",
            f"max relative displacement error {rel:.4%} over t<= {window:.4f} s "
            f"(tolerance {FREEFALL_REL_TOL:.0%}; continuum 1/2 g t^2 reference, "
            f"integrator RK4, dt={spec.timestep_s:g} s)",
            rel, "relative"))

    # 2. Contact timing vs sqrt(2h/g).
    if math.isfinite(spec.contact_time_s):
        after = sim.times[sim.contact_count > 0]
        if after.size == 0:
            checks.append(CheckResult("contact_detected", "FAIL",
                                      "no contact in the run; box never reached the floor"))
        else:
            t_contact = float(after[0])
            rel = abs(t_contact - spec.contact_time_s) / spec.contact_time_s
            # Sampling granularity dominates here, so allow one trace interval plus 5%.
            tolerance = 0.05 + 0.005 / spec.contact_time_s
            checks.append(CheckResult(
                "contact_detected", "PASS" if rel <= tolerance else "FAIL",
                f"first contact at {t_contact:.4f} s, analytic {spec.contact_time_s:.4f} s "
                f"(relative {rel:.2%}, tolerance {tolerance:.2%}; trace resolution is "
                f"{spec.timestep_s * max(1, int(round(0.005 / spec.timestep_s))):g} s, so this "
                f"is a coarse sanity check, not the 1% gate)",
                rel, "relative"))
    else:
        checks.append(CheckResult("contact_detected", "INCONCLUSIVE",
                                  "zero or negative gravity: contact is never reached"))

    # 3. Rest: bottom on the floor.
    bottom_mm = m_to_mm(float(sim.com_z[-1])) - spec.edge_mm / 2.0
    rest_ok = abs(bottom_mm) <= REST_TOL_MM
    checks.append(CheckResult(
        "rest_on_floor", "PASS" if rest_ok else "FAIL",
        f"final box bottom {bottom_mm:+.4f} mm from the floor "
        f"(tolerance {REST_TOL_MM} mm)", bottom_mm, "mm"))

    # 4. Terminal speed: settled, not bouncing or diverging.
    speed = abs(float(sim.com_vz[-1]))
    checks.append(CheckResult(
        "terminal_speed", "PASS" if speed <= TERMINAL_SPEED_TOL else "FAIL",
        f"final abs(vz) {speed:.5f} m/s (tolerance {TERMINAL_SPEED_TOL} m/s)", speed, "m/s"))

    # 5. Finite values everywhere.
    finite = bool(np.all(np.isfinite(sim.com_z)) and np.all(np.isfinite(sim.com_vz)))
    checks.append(CheckResult("finite_state", "PASS" if finite else "FAIL",
                              "all sampled positions and velocities finite" if finite
                              else "non-finite value in the trace"))

    # 6. Penetration. Two separate numbers: the settled state must be inside a tight
    # tolerance, while the impact transient is bounded by the contact model's own scale
    # (impact speed x solref time constant), which is a scale estimate, not a closed-form
    # limit: the settled-penetration check is the real acceptance criterion.
    settled_pen_mm = -bottom_mm if bottom_mm < 0.0 else 0.0
    settled_ok = settled_pen_mm <= REST_PENETRATION_MM
    checks.append(CheckResult(
        "settled_penetration", "PASS" if settled_ok else "FAIL",
        f"settled penetration {settled_pen_mm:.4f} mm "
        f"(limit {REST_PENETRATION_MM} mm)", settled_pen_mm, "mm"))

    peak_pen_mm = max(0.0, -(m_to_mm(float(sim.com_z.min())) - spec.edge_mm / 2.0))
    bound_mm = spec.transient_penetration_mm
    checks.append(CheckResult(
        "transient_penetration", "PASS" if peak_pen_mm <= bound_mm else "FAIL",
        f"peak impact penetration {peak_pen_mm:.4f} mm vs order-of-magnitude envelope "
        f"{bound_mm:.4f} mm (impact {spec.impact_speed_m_s:.3f} m/s x solref time constant "
        f"{CONTACT_TIMECONST_S:g} s); the settled-penetration limit is the real criterion",
        peak_pen_mm, "mm"))

    # 7. Mass and inertia must be positive and match the analytic values.
    analytic_i = spec.inertia_kg_m2
    if not (analytic_i > 0.0) or not (spec.mass_kg > 0.0):
        checks.append(CheckResult(
            "mass_inertia", "FAIL",
            f"analytic mass/inertia not positive (mass {spec.mass_kg!r}, inertia {analytic_i!r})"))
    else:
        i_err = max(abs(v - analytic_i) / analytic_i for v in sim.inertia_diag)
        mass_err = abs(sim.mass_kg - spec.mass_kg) / spec.mass_kg
        ok = sim.mass_kg > 0 and min(sim.inertia_diag) > 0 and mass_err < 1e-6 and i_err < 1e-6
        checks.append(CheckResult(
            "mass_inertia", "PASS" if ok else "FAIL",
            f"compiled mass {sim.mass_kg:.9g} kg (analytic {spec.mass_kg:.9g}); "
            f"inertia {sim.inertia_diag[0]:.6g} kg m2 (analytic {analytic_i:.6g})",
            max(mass_err, i_err), "relative"))

    # 8. Analytic-vs-build123d cross-check of volume, mass and inertia.
    x = cross_check_solid(spec)
    v_err = abs(x["volume_mm3"] - x["analytic_volume_mm3"]) / x["analytic_volume_mm3"]
    i_solid_err = abs(x["inertia_diag_kg_m2"] - x["analytic_inertia_kg_m2"]) / x["analytic_inertia_kg_m2"]
    ok = v_err < 1e-9 and i_solid_err < 1e-6
    checks.append(CheckResult(
        "cad_analytic_crosscheck", "PASS" if ok else "FAIL",
        f"build123d volume {x['volume_mm3']:.6f} mm3 vs analytic "
        f"{x['analytic_volume_mm3']:.6f}; inertia {x['inertia_diag_kg_m2']:.9g} vs "
        f"{x['analytic_inertia_kg_m2']:.9g} kg m2",
        max(v_err, i_solid_err), "relative"))
    return checks


def _now_utc() -> str:
    """Single timestamp source, so a run's id and manifest agree."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def default_outdir(run_id: str) -> Path:
    from ..workspace import fixtures_root

    return fixtures_root() / "gravity_drop" / "physics" / run_id


def run_smoke(out: Path | None = None, spec: DropSpec | None = None) -> RunResult:
    """Run the fixture once, write its artifacts, and return the evaluated result."""
    spec = spec or DropSpec()
    spec.validate()
    xml = scene_xml(spec)
    try:
        sim = simulate(spec)
    except PhysicsUnavailable as exc:
        return RunResult(status="ERROR", scenario=SCENARIO, detail=str(exc))

    digest = scene_hash(xml, spec, sim.mujoco_version)
    run_id = f"{_now_utc()}-{digest[:8]}"
    outdir = Path(out) if out is not None else default_outdir(run_id)
    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return RunResult(status="ERROR", scenario=SCENARIO,
                         detail=f"could not create output dir {outdir}: {exc}")

    checks = evaluate(spec, sim)
    status = _status_from(checks)

    try:
        return _write_artifacts(outdir, xml, sim, spec, checks, status, digest, run_id)
    except OSError as exc:
        return RunResult(status="ERROR", scenario=SCENARIO,
                         detail=f"could not write artifacts to {outdir}: {exc}")


def _write_artifacts(outdir, xml, sim, spec, checks, status, digest, run_id) -> RunResult:
    (outdir / "scene.xml").write_text(xml, encoding="utf-8")
    trace = outdir / "trace.csv"
    with trace.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["time_s", "com_z_m", "com_vz_m_s", "contact_count"])
        for row in zip(sim.times, sim.com_z, sim.com_vz, sim.contact_count):
            writer.writerow([f"{v:.9g}" for v in row])

    manifest = {
        "run_id": run_id,
        "scenario": SCENARIO,
        "scene_hash": digest,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": status,
        "versions": {
            "mujoco": sim.mujoco_version,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "solver": {
            "integrator": "RK4", "timestep_s": spec.timestep_s,
            "duration_s": spec.duration_s, "n_steps": sim.n_steps,
            "cone": "elliptic", "solver": "Newton", "iterations": 100,
            "gravity_m_s2": [0.0, 0.0, -spec.gravity_m_s2],
        },
        "seed": spec.seed,
        "inputs": asdict(spec),
        "analytic": {
            "mass_kg": spec.mass_kg,
            "inertia_kg_m2": spec.inertia_kg_m2,
            "contact_time_s": (spec.contact_time_s if math.isfinite(spec.contact_time_s)
                               else None),
            "fall_distance_m": spec.fall_distance_m,
        },
        "runtime_wall_s": sim.wall_time_s,
        "artifacts": {"scene": "scene.xml", "trace": "trace.csv",
                      "summary": "summary.json", "report": "report.md"},
    }
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n",
                                              encoding="utf-8")

    result = RunResult(
        status=status,
        scenario=SCENARIO,
        # Strict-JSON safe: None, never NaN/Infinity, so non-Python consumers can parse this.
        metrics={c.name: (c.value if c.value is not None and math.isfinite(c.value) else None)
                 for c in checks},
        checks=checks,
        scene_hash=digest,
        run_id=run_id,
        artifacts={
            "manifest": str(outdir / "manifest.json"),
            "scene": str(outdir / "scene.xml"),
            "trace": str(trace),
            "summary": str(outdir / "summary.json"),
            "report": str(outdir / "report.md"),
        },
    )
    (outdir / "summary.json").write_text(json.dumps(result.to_dict(), indent=2) + "\n",
                                            encoding="utf-8")
    (outdir / "report.md").write_text(render_report(result, sim, spec), encoding="utf-8")
    return result


def render_report(result: RunResult, sim: Simulation, spec: DropSpec) -> str:
    lines = [
        "# Physics smoke: gravity drop", "",
        f"Status: **{result.status}**  ",
        f"Scenario: `{result.scenario}`  ",
        f"Run: `{result.run_id}`  ",
        f"Scene hash: `{result.scene_hash}`  ",
        f"MuJoCo {sim.mujoco_version} | Python {sys.version.split()[0]} | {platform.platform()}",
        "",
        "Fixed floor is an intentional analytic fixture, not a product restraint.",
        "",
        "| check | status | value | detail |", "|---|---|---|---|",
    ]
    for c in result.checks:
        value = "" if c.value is None else f"{c.value:.6g} {c.units}".strip()
        lines.append(f"| {c.name} | {c.status} | {value} | {c.detail} |")
    lines += [
        "",
        f"Steps: {sim.n_steps} at {spec.timestep_s:g} s | wall time {sim.wall_time_s:.3f} s",
        f"Analytic contact time: {spec.contact_time_s:.4f} s | "
        f"analytic mass: {spec.mass_kg:.9g} kg",
        "",
    ]
    return "\n".join(lines)
