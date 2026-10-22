"""M3 mechanics fixtures: slider statics/dynamics, a stop, and a hinge oscillator.

These are **generic analytic fixtures**, not Pocky models. Each one isolates a physical
relation so a unit error cannot hide, and each one's expected value is computed from declared
inputs rather than read back from the simulation:

* ``slider_frictionless`` — declared carriage mass ``m``, joint spring ``k`` (N/m), a bounded
  force ``F``, no friction and no damping. Statics: ``x_ss = F/k``. Dynamics: the released
  carriage oscillates at ``2π√(m/k)``. Both are checked against closed forms, and the
  displacement is also checked against ``F/k`` derived independently of the runner.
* ``slider_friction`` — the same spring with a declared preload (``k·reference``) and a
  Coulomb ``frictionloss``. The static prediction is a band derived from those two declared
  numbers, and the release residual is bounded by ``frictionloss/k``.
* ``slider_stop`` — a short range and a **declared** stop compliance. A sustained input larger
  than the free deflection drives the carriage onto the stop, where it must rest within a
  penetration budget derived from the declared compliance, not from the compiler default.
* ``hinge_oscillator`` — a hinge with a rotational spring ``k`` (N m/rad) and a known inertia
  ``I``. The undamped period is ``2π√(I/k)``; with damping ratio ``ζ`` it becomes
  ``2π√(I/k)/√(1-ζ²)``. Both the torque unit and the axis/range convention are checked in the
  compiled model.

No ``qpos`` is written after the declared initial state. Collision geometry contributes no
elasticity: every restoring force here comes from the declared joint spring.
"""
from __future__ import annotations

import math

from build123d import Box, Pos

from dataclasses import replace

from .schema import (
    ActuatorSpec,
    AssemblySpec,
    BodySpec,
    ColliderSpec,
    Frame,
    JointSpec,
    PartSpec,
    Source,
    SpringSpec,
)

DENSITY_G_CM3 = 1.24

# ---- shared slider parameters ----------------------------------------------------
#: Declared carriage mass, kg. Assumed analytic-fixture input, NOT a measurement. It is
#: applied through ``PartSpec.mass_kg`` so the compiled body mass is this number rather than
#: the mass of the 8 mm decorative block (which is 6.3e-4 kg and would make every dynamic
#: prediction wrong by ~400x).
SLIDER_KG = 0.25
#: Declared joint spring, N/m.
SLIDER_K_N_PER_M = 50.0
#: Bounded push, N. With the declared spring this gives x_ss = 0.020 m.
SLIDER_FORCE_N = 1.0
#: Declared Coulomb joint friction, N.
SLIDER_FRICTIONLOSS = 0.05
SLIDER_RANGE_M = (-0.05, 0.05)
#: Damping chosen from the declared mass and spring, not inherited from the old light carriage.
#: ζ = 0.7 gives c = 0.7·2√(km) ≈ 4.95 N·s/m and a 4τ settle of ≈ 0.40 s.
SLIDER_DAMPING_RATIO = 0.7
#: Declared spring preload for the friction fixture: the carriage is held off its free
#: position by k·SLIDER_PRELOAD_M. Assumed fixture input, not a measurement.
SLIDER_PRELOAD_M = 0.010

# ---- stop fixture -----------------------------------------------------------------
#: Short travel so a bounded input certainly reaches the stop.
STOP_RANGE_M = (-0.02, 0.02)
#: Declared physical compliance of the stop, as an absolute SI time constant and damping
#: ratio. The MuJoCo default (0.02 s) is soft enough for 2 N to hold a 0.25 kg body ~20 mm
#: past a 20 mm range; this value keeps the steady penetration sub-millimetre.
STOP_TIMECONST_S = 0.002
STOP_DAMPRATIO = 1.0
#: Sustained stop drive, N. Must exceed k·range (1 N) so the stop is genuinely loaded.
STOP_DRIVE_N = 2.0
#: Steady and transient penetration budgets, m. Both are set to **discriminate**, which is the
#: only thing that makes them a test. Measured on this fixture:
#:
#:   declared compliance (tc = 0.002 s): steady 0.0036 mm, transient peak 0.48 mm
#:   MuJoCo default    (tc = 0.020 s): steady 0.3144 mm, transient peak 4.28 mm
#:
#: The budgets sit between those two, so a fixture that inherits the compiler default fails
#: and only the declared compliance passes. A looser budget would accept the default, which is
#: exactly the "range metadata is not a stop test" failure the packet forbids.
#: The steady budget also clears the analytic scale estimate F·tc²/m = 32 µm with 3x margin.
STOP_STEADY_PENETRATION_M = 0.1e-3
STOP_PEAK_PENETRATION_M = 1.0e-3

# ---- hinge oscillator ------------------------------------------------------------
HINGE_K_NM_PER_RAD = 0.02    # declared rotational spring, N m/rad
#: Arm geometry, mm. Declared here so the analytic inertia is derived, never guessed.
ARM_LENGTH_MM = 40.0
ARM_WIDTH_MM = 6.0
ARM_THICK_MM = 4.0
#: The arm's COM sits half its length from the hinge axis, mm.
ARM_LEVER_MM = ARM_LENGTH_MM / 2.0
HINGE_AMP_RAD = math.radians(10.0)
#: Damping ratio for the damped hinge case, declared rather than a raw coefficient: the arm's
#: inertia is ~6.4e-7 kg m², so critical damping is only ~2.3e-4 N·m·s/rad and an
#: innocent-looking 0.02 would be 88x critical (overdamped, no oscillation to measure).
HINGE_DAMPING_RATIO = 0.3


def hinge_damping_nm_s_per_rad(ratio: float = HINGE_DAMPING_RATIO,
                               stiffness: float = HINGE_K_NM_PER_RAD,
                               inertia: float | None = None) -> float:
    """Damping coefficient for a target ratio: ``c = ζ·2√(kI)``, N·m·s/rad."""
    inertia = analytic_hinge_inertia_kg_m2() if inertia is None else inertia
    return ratio * 2.0 * math.sqrt(stiffness * inertia)


def _block(part_id: str, size_mm, pos_mm, collider_half, role="mechanism"):
    return PartSpec(
        part_id,
        Pos(*pos_mm) * Box(*size_mm),
        colliders=(ColliderSpec(f"{part_id}_col", "box", collider_half, pos_mm=pos_mm,
                                role=role,
                                source=Source("derived", f"{part_id} half-extents")),),
        density_g_cm3=DENSITY_G_CM3,
        role=role,
        source=Source("derived", f"{part_id} CAD block"),
    )


def _massed_block(part_id: str, size_mm, pos_mm, collider_half, mass_kg: float,
                  role="mechanism"):
    """A part whose mass is **declared**, not derived from its decorative volume.

    The shape still exists (it is what makes the scene a CAD assembly and gives the visual
    mesh), but ``mass_kg`` wins over density in ``part_inertial``: the solid is treated as a
    uniform body at the implied density, so the mass is exactly the declared value and the
    inertia scales with it consistently.
    """
    part = _block(part_id, size_mm, pos_mm, collider_half, role=role)
    return replace(
        part,
        mass_kg=mass_kg,
        density_g_cm3=None,
        source=Source("assumed", f"{part_id} declared mass {mass_kg} kg (analytic fixture)"),
    )


def slider_analytic_stiffness_damping(mass_kg: float = SLIDER_KG,
                                      stiffness: float = SLIDER_K_N_PER_M,
                                      ratio: float = SLIDER_DAMPING_RATIO) -> float:
    """Damping coefficient for a target ratio: ``c = ζ·2√(km)``, N·s/m."""
    return ratio * 2.0 * math.sqrt(stiffness * mass_kg)


def slider_period_s(mass_kg: float = SLIDER_KG,
                    stiffness: float = SLIDER_K_N_PER_M) -> float:
    """Undamped released period ``2π√(m/k)``, seconds."""
    return 2.0 * math.pi * math.sqrt(mass_kg / stiffness)


def _slider_bodies(*, frictionloss: float, damping: float, range_m, spring: SpringSpec | None,
                   stop_timeconst_s: float | None = None) -> tuple[BodySpec, BodySpec]:
    """Fixed rail plus a carriage with the declared mass, spring, damping and friction.

    ``stop_timeconst_s`` is declared only by a fixture that actually tests a stop. Declaring a
    compliance on a fixture that never reaches its limit would silently bless a stop nobody
    validated, so every non-stop fixture leaves it at the compiler default (which is never
    reached either, because the fixture's range is wide enough that it cannot be).
    """
    rail = BodySpec(
        body_id="rail",
        parts=(_block("rail", (60.0, 20.0, 6.0), (0.0, 0.0, -3.0), (30.0, 10.0, 3.0),
                      role="structure"),),
        fixed_to_world=True,
        fixture="analytic_fixture",
        source=Source("derived", "fixed analytic rail"),
    )
    carriage = BodySpec(
        body_id="carriage",
        parts=(_massed_block("carriage", (8.0, 8.0, 8.0), (0.0, 0.0, 6.0), (4.0, 4.0, 4.0),
                             SLIDER_KG),),
        parent="rail",
        joint=JointSpec(
            joint_id="carriage_slide",
            body_id="carriage",
            kind="slide",
            axis=(1.0, 0.0, 0.0),
            anchor_mm=(0.0, 0.0, 6.0),
            limits=range_m,
            damping=damping,
            frictionloss=frictionloss,
            spring=spring,
            stop_timeconst_s=stop_timeconst_s,
            stop_dampratio=STOP_DAMPRATIO,
            source=Source("derived", "prismatic carriage on the rail"),
        ),
        source=Source("derived", "spring-loaded carriage"),
    )
    return rail, carriage


def slider_frictionless_spec(*, timestep_s: float = 1.0e-3,
                             stiffness: float = SLIDER_K_N_PER_M,
                             with_spring: bool = True,
                             damping: float = 0.0) -> AssemblySpec:
    """Frictionless slider: the clean ``F/k``, ``2π√(m/k)`` and damped-return reference.

    ``damping=0`` leaves a pure oscillator whose released period is ``2π√(m/k)`` and whose
    displacement oscillates about ``F/k``. A nonzero ``damping`` makes the same fixture settle,
    which is what a return-to-home check needs: an undamped carriage never returns, so it
    cannot prove a return.

    Gravity is off. Gravity would add a constant force along Z that the X-axis slide cannot
    feel, but switching it off keeps the fixture a pure one-dimensional oscillator with no
    contact anywhere in the scene.
    """
    rail, carriage = _slider_bodies(
        frictionloss=0.0,
        damping=damping,
        range_m=SLIDER_RANGE_M,
        spring=(SpringSpec(stiffness, 0.0,
                           source=Source("assumed", "declared equivalent spring"))
                if with_spring else None),
    )
    return AssemblySpec(
        name="m3_slider_frictionless",
        bodies=(rail, carriage),
        actuators=(ActuatorSpec("push", "carriage_slide", "force", 2.0,
                                source=Source("assumed", "bounded manual push")),),
        gravity_m_s2=(0.0, 0.0, 0.0),
        timestep_s=timestep_s,
        source=Source("derived", "M3 frictionless slider reference"),
    )


def slider_damped_spec(*, timestep_s: float = 1.0e-3,
                       damping: float | None = None) -> AssemblySpec:
    """Frictionless but damped slider: the release-to-home reference.

    Damping is derived from the declared mass and spring at ``SLIDER_DAMPING_RATIO``, so the
    settle time is chosen analytically (4τ ≈ 0.40 s) rather than inherited from the old light
    carriage.
    """
    if damping is None:
        damping = slider_analytic_stiffness_damping()
    spec = slider_frictionless_spec(timestep_s=timestep_s, damping=damping)
    return replace(spec, name="m3_slider_damped")


def slider_friction_spec(*, frictionloss: float = SLIDER_FRICTIONLOSS,
                         preload_m: float = SLIDER_PRELOAD_M,
                         timestep_s: float = 1.0e-3) -> AssemblySpec:
    """Damped slider with a declared spring preload and Coulomb friction.

    The carriage's spring is declared at reference ``preload_m``, so at ``q = 0`` the spring
    already pushes with ``k·preload_m = 0.5 N``. That force is **not** a dead band: a spring
    reference is a rest coordinate, not a stop, so the carriage moves as soon as the net drive
    exceeds ``frictionloss``, and it settles at ``reference + (F ± frictionloss)/k``. The band
    in :func:`slider_friction_band` is that equilibrium interval, and the release residual is
    measured against ``|q - reference|`` because the reference — not zero — is home.
    """
    rail, carriage = _slider_bodies(
        frictionloss=frictionloss,
        damping=slider_analytic_stiffness_damping(),
        range_m=SLIDER_RANGE_M,
        spring=SpringSpec(SLIDER_K_N_PER_M, preload_m,
                          source=Source("assumed", "declared preload spring")),
    )
    return AssemblySpec(
        name="m3_slider_friction",
        bodies=(rail, carriage),
        actuators=(ActuatorSpec("push", "carriage_slide", "force", 2.0,
                                source=Source("assumed", "bounded manual push")),),
        gravity_m_s2=(0.0, 0.0, 0.0),
        timestep_s=timestep_s,
        source=Source("derived", "M3 preloaded friction slider"),
    )


def slider_stop_spec(*, timestep_s: float = 1.0e-3,
                     stop_timeconst_s: float = STOP_TIMECONST_S) -> AssemblySpec:
    """Short-travel slider whose stop compliance is declared, not inherited."""
    rail, carriage = _slider_bodies(
        frictionloss=0.0,
        damping=0.0,
        range_m=STOP_RANGE_M,
        spring=None,
        stop_timeconst_s=stop_timeconst_s,
    )
    return AssemblySpec(
        name="m3_slider_stop",
        bodies=(rail, carriage),
        actuators=(ActuatorSpec("push", "carriage_slide", "force", STOP_DRIVE_N,
                                source=Source("assumed", "bounded drive into the stop")),),
        gravity_m_s2=(0.0, 0.0, 0.0),
        timestep_s=timestep_s,
        source=Source("derived", "M3 stop-compliance fixture"),
    )


def analytic_slider_deflection(stiffness: float = SLIDER_K_N_PER_M,
                               force: float = SLIDER_FORCE_N) -> float:
    """Quasi-static displacement with no friction: ``F / k``, metres."""
    return force / stiffness


def slider_friction_band(*, frictionloss: float = SLIDER_FRICTIONLOSS,
                         preload_m: float = SLIDER_PRELOAD_M,
                         force: float = SLIDER_FORCE_N,
                         stiffness: float = SLIDER_K_N_PER_M) -> tuple[float, float]:
    """Static displacement band from the declared preload and Coulomb friction, metres.

    At equilibrium the spring force ``k(q - reference)`` balances the drive minus friction,
    so ``q = reference + (F ± frictionloss)/k``. The band width is ``2·frictionloss/k`` and its
    centre is ``reference + F/k`` — both derived from declared numbers only.
    """
    centre = preload_m + force / stiffness
    half = frictionloss / stiffness
    return (centre - half, centre + half)


def slider_release_residual_bound(frictionloss: float = SLIDER_FRICTIONLOSS,
                                  stiffness: float = SLIDER_K_N_PER_M) -> float:
    """Largest residual offset friction can hold: ``frictionloss/k``, metres."""
    return frictionloss / stiffness


def stop_penetration_estimate_m(force: float = STOP_DRIVE_N,
                                timeconst_s: float = STOP_TIMECONST_S,
                                mass_kg: float = SLIDER_KG) -> float:
    """Order-of-magnitude steady penetration of the compliant stop: ``F·tc²/m``, metres.

    MuJoCo's limit constraint behaves as a spring of stiffness ``m/tc²`` against the declared
    stop time constant, so the equilibrium offset for a sustained force ``F`` is ``F·tc²/m``.
    This is a scale estimate used to justify the budget, not a fitted number.
    """
    return force * timeconst_s ** 2 / mass_kg


def analytic_hinge_inertia_kg_m2() -> float:
    """Arm inertia about the hinge axis, from the closed-form box + parallel-axis sum.

    ``I = m (w² + L²)/12 + m d²`` with ``d`` the lever from the hinge to the arm's COM. This
    is computed from declared dimensions and density, independently of the CAD kernel and of
    the compiled model, so the period check cannot be circular.
    """
    from .units import mass_kg

    volume_mm3 = ARM_LENGTH_MM * ARM_WIDTH_MM * ARM_THICK_MM
    m = mass_kg(volume_mm3, DENSITY_G_CM3)
    w, length = ARM_WIDTH_MM / 1000.0, ARM_LENGTH_MM / 1000.0
    i_own = m * (w * w + length * length) / 12.0
    lever = ARM_LEVER_MM / 1000.0
    return i_own + m * lever * lever


def hinge_oscillator_spec(*, damping: float = 0.0,
                          timestep_s: float = 1.0e-3) -> AssemblySpec:
    """A pendulum on a hinge with a rotational spring, released from a small angle."""
    base = BodySpec(
        body_id="post",
        parts=(_block("post", (10.0, 10.0, 10.0), (0.0, 0.0, 5.0), (5.0, 5.0, 5.0),
                      role="structure"),),
        fixed_to_world=True,
        fixture="analytic_fixture",
        source=Source("derived", "fixed analytic post"),
    )
    # The arm's collision geom is filtered off the post: this fixture measures the joint
    # spring and the hinge inertia, and contact between arm and post would add an undeclared
    # torque and contaminate the period. The arm still collides with everything else.
    arm_part = _block("arm", (ARM_WIDTH_MM, ARM_LENGTH_MM, ARM_THICK_MM),
                      (0.0, -ARM_LEVER_MM, 0.0),
                      (ARM_WIDTH_MM / 2, ARM_LEVER_MM, ARM_THICK_MM / 2))
    arm_part = replace(
        arm_part,
        # contype/conaffinity 2/2 shares no bit with the default 1/1 geoms, so the arm
        # collides with nothing: this fixture is a pure torsional oscillator and contact
        # would add an undeclared torque.
        colliders=(replace(arm_part.colliders[0], contype=2, conaffinity=2),),
    )
    arm = BodySpec(
        body_id="arm",
        parts=(arm_part,),
        parent="post",
        joint=JointSpec(
            joint_id="arm_hinge",
            body_id="arm",
            kind="hinge",
            axis=(0.0, 0.0, 1.0),
            anchor_mm=(0.0, 0.0, 10.0),
            limits=(math.radians(-60.0), math.radians(60.0)),
            damping=damping,
            spring=SpringSpec(HINGE_K_NM_PER_RAD, 0.0,
                              source=Source("assumed", "declared rotational spring")),
            source=Source("derived", "hinge at the post top"),
        ),
        source=Source("derived", "spring-restrained arm"),
    )
    return AssemblySpec(
        name="m3_hinge_oscillator",
        bodies=(base, arm),
        gravity_m_s2=(0.0, 0.0, 0.0),  # pure torsional oscillator: gravity would add a bias
        timestep_s=timestep_s,
        source=Source("derived", "M3 hinge oscillator fixture"),
    )


def analytic_period_s(inertia: float | None = None,
                      stiffness: float = HINGE_K_NM_PER_RAD,
                      damping_ratio: float = 0.0) -> float:
    """Damped period ``2π√(I/k)/√(1-ζ²)``, seconds."""
    inertia = analytic_hinge_inertia_kg_m2() if inertia is None else inertia
    omega0 = math.sqrt(stiffness / inertia)
    if damping_ratio >= 1.0:
        raise ValueError("damped period is undefined at or above critical damping")
    return 2.0 * math.pi / (omega0 * math.sqrt(1.0 - damping_ratio ** 2))


def hinge_cad_inertia_kg_m2() -> float:
    """The arm's inertia about the hinge axis, read from the CAD solid.

    Kept alongside :func:`analytic_hinge_inertia_kg_m2` so the two independent routes can be
    compared; neither is used to predict the other.
    """
    from .inertia import part_inertial

    body = next(b for b in hinge_oscillator_spec().bodies if b.body_id == "arm")
    part = body.parts[0]
    _, com_m, tensor = part_inertial(part)
    from .units import mass_kg

    m = mass_kg(float(part.shape.volume), part.density_g_cm3)
    r = math.hypot(com_m[0], com_m[1])
    return float(tensor[2][2]) + m * r * r
