"""Generic primitive gravity fixture: a box dropped onto a fixed floor.

Analytic reference, independent of the solver:

    free fall   z(t) = z0 - g t^2 / 2          (until contact)
    contact     t_c  = sqrt(2 h / g)
    rest        bottom_z = 0
    box inertia I    = m a^2 / 6               (cube, about the centre of mass)

The floor is a fixed analytic fixture. Supervisor review §21.9: an intentionally fixed
analytic fixture is legitimate and is not a product-acceptance restraint.

The box is authored with ``build123d`` so the mm -> m, mm3 -> kg and mm5 -> kg m2
conversions are exercised by the same code path a CAD part will use in M2.
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import require_mujoco
from .units import GRAVITY, inertia_kg_m2, mass_kg, mm_to_m

SCENARIO = "gravity_drop"

#: Free-fall analytic tolerance, relative. The plan asks for 1%.
FREEFALL_REL_TOL = 0.01
#: Rest height tolerance, mm.
REST_TOL_MM = 0.1
#: Terminal speed tolerance, m/s.
TERMINAL_SPEED_TOL = 0.01
#: Allowed penetration in the settled state, mm.
REST_PENETRATION_MM = 0.1
#: Contact-model time constant, s. MuJoCo recommends >= 2 timesteps for stability.
CONTACT_TIMECONST_S = 2.0e-3
#: Absolute SI plausibility window for a fixture box, metres and kilograms. A self-consistent
#: scene cannot detect its own unit error, so these absolute bounds are kept alongside the
#: declared-vs-compiled comparison.
MIN_GEOM_SIZE_M = 1.0e-5
MAX_GEOM_SIZE_M = 2.0
MIN_MASS_KG = 1.0e-4
#: 1000 kg, deliberately loose: this window exists to catch a metres/millimetres mix-up (a
#: 20 m box), not to constrain design. A 200 mm PETG block legitimately weighs 10 kg.
MAX_MASS_KG = 1.0e3
#: Hard step budget. duration/timestep above this is rejected, not attempted: the trace
#: arrays are preallocated, so an unbounded duration is a MemoryError, not a slow run.
MAX_SIM_STEPS = 200_000


@dataclass(frozen=True)
class DropSpec:
    """A box dropped onto a floor. Every length is mm, every mass kg, angles unused."""

    edge_mm: float = 20.0
    density_g_cm3: float = 1.27
    clearance_mm: float = 100.0          # gap between the box bottom and the floor at t=0
    timestep_s: float = 1.0e-3
    duration_s: float = 0.6
    seed: int = 0
    gravity_m_s2: float = GRAVITY

    def validate(self) -> None:
        for name in ("edge_mm", "density_g_cm3", "clearance_mm", "timestep_s", "duration_s"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive, got {value!r}")
        if not math.isfinite(self.gravity_m_s2):
            raise ValueError(f"gravity_m_s2 must be finite, got {self.gravity_m_s2!r}")
        if self.gravity_m_s2 < 0.0:
            # A negative magnitude would emit +g and quietly invert the scene.
            raise ValueError(f"gravity_m_s2 must be >= 0, got {self.gravity_m_s2!r}")
        if self.timestep_s > 1.0e-2:
            raise ValueError(f"timestep_s must be <= 0.01, got {self.timestep_s}")
        n_steps = self.duration_s / self.timestep_s
        if n_steps > MAX_SIM_STEPS:
            raise ValueError(
                f"duration_s/timestep_s = {n_steps:.0f} steps exceeds the {MAX_SIM_STEPS} "
                f"step budget; shorten duration_s or coarsen timestep_s"
            )
        mass_kg(self.edge_mm ** 3, self.density_g_cm3)  # rejects bad density

    # -- derived, SI -------------------------------------------------------
    @property
    def half_height_m(self) -> float:
        return mm_to_m(self.edge_mm) / 2.0

    @property
    def com_z0_m(self) -> float:
        return mm_to_m(self.clearance_mm) + self.half_height_m

    @property
    def mass_kg(self) -> float:
        return mass_kg(self.edge_mm ** 3, self.density_g_cm3)

    @property
    def inertia_kg_m2(self) -> float:
        """Cube about its centre of mass: ``m a^2 / 6``."""
        edge_m = mm_to_m(self.edge_mm)
        return self.mass_kg * edge_m * edge_m / 6.0

    @property
    def impact_speed_m_s(self) -> float:
        """Speed at first contact: ``sqrt(2 g h)``."""
        if self.gravity_m_s2 <= 0.0:
            return 0.0
        return math.sqrt(2.0 * self.gravity_m_s2 * self.fall_distance_m)

    @property
    def transient_penetration_mm(self) -> float:
        """Analytic soft-contact overshoot bound, mm.

        A compliant contact with time constant ``tau`` compressed at ``v`` settles after
        roughly ``v * tau`` of travel. This is the documented contact-model artifact, not a
        geometry error, so it is bounded rather than zero.
        """
        return self.impact_speed_m_s * CONTACT_TIMECONST_S * 1e3

    @property
    def fall_distance_m(self) -> float:
        """Bottom travels exactly ``clearance_mm`` before touching the floor."""
        return mm_to_m(self.clearance_mm)

    @property
    def contact_time_s(self) -> float:
        if self.gravity_m_s2 <= 0.0:
            return math.inf
        return math.sqrt(2.0 * self.fall_distance_m / self.gravity_m_s2)

    def analytic_z(self, t_s: float) -> float:
        """COM height at ``t_s`` while still in free fall."""
        return self.com_z0_m - 0.5 * self.gravity_m_s2 * t_s * t_s

    def analytic_displacement(self, t_s: float) -> float:
        return 0.5 * self.gravity_m_s2 * t_s * t_s


def build_box_solid(spec: DropSpec):
    """The fixture box as a build123d solid, centred on the origin."""
    from build123d import Box

    spec.validate()
    return Box(spec.edge_mm, spec.edge_mm, spec.edge_mm)


def cross_check_solid(spec: DropSpec) -> dict[str, float]:
    """Compare build123d's volume and inertia with the analytic values."""
    solid = build_box_solid(spec)
    volume_mm3 = float(solid.volume)
    mi = np.array(solid.matrix_of_inertia, dtype=float)
    diag = np.diag(mi)
    return {
        "volume_mm3": volume_mm3,
        "analytic_volume_mm3": spec.edge_mm ** 3,
        "mass_kg": mass_kg(volume_mm3, spec.density_g_cm3),
        "analytic_mass_kg": spec.mass_kg,
        "inertia_diag_kg_m2": float(np.mean([inertia_kg_m2(v, spec.density_g_cm3) for v in diag])),
        "analytic_inertia_kg_m2": spec.inertia_kg_m2,
    }


def scene_xml(spec: DropSpec) -> str:
    """Deterministic MJCF. Numbers are formatted with ``%.9g`` for a stable hash."""
    spec.validate()
    e = spec.edge_mm
    half = spec.half_height_m

    def f(value: float) -> str:
        return f"{value:.9g}"

    # Inertia is isotropic for a cube; emit the diagonal explicitly.
    i = spec.inertia_kg_m2
    return f"""<mujoco model="{SCENARIO}">
  <!-- Generated by cadkit.physics.gravity_drop. Do not edit: regenerate instead. -->
  <compiler angle="radian" coordinate="local"/>
  <option timestep="{f(spec.timestep_s)}" integrator="RK4" cone="elliptic"
          solver="Newton" iterations="100" gravity="0 0 {f(-spec.gravity_m_s2)}"/>
  <default>
    <geom condim="3" solref="{f(CONTACT_TIMECONST_S)} 1" solimp="0.95 0.99 0.001"/>
  </default>
  <worldbody>
    <!-- Intentionally fixed analytic floor fixture (supervisor review 21.9). -->
    <geom name="floor" type="plane" size="1 1 0.1" pos="0 0 0" rgba="0.6 0.6 0.6 1"/>
    <body name="box" pos="0 0 {f(spec.com_z0_m)}">
      <freejoint name="box_free"/>
      <inertial pos="0 0 0" mass="{f(spec.mass_kg)}"
                diaginertia="{f(i)} {f(i)} {f(i)}"/>
      <geom name="box_geom" type="box" size="{f(mm_to_m(e) / 2)} {f(mm_to_m(e) / 2)} {f(half)}"
            rgba="0.85 0.35 0.25 1"/>
    </body>
  </worldbody>
</mujoco>
"""


def scene_hash(xml: str, spec: DropSpec, mujoco_version: str) -> str:
    payload = {
        "xml": xml,
        "spec": {
            "edge_mm": spec.edge_mm,
            "density_g_cm3": spec.density_g_cm3,
            "clearance_mm": spec.clearance_mm,
            "timestep_s": spec.timestep_s,
            "duration_s": spec.duration_s,
            "seed": spec.seed,
            "gravity_m_s2": spec.gravity_m_s2,
        },
        "mujoco": mujoco_version,
        "platform": platform.platform(),
    }
    blob = json.dumps(payload, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


@dataclass
class Simulation:
    """Raw arrays from one run, plus the compile-time facts needed for the report."""

    #: ``com_z`` is ``data.xpos`` for the box body, i.e. the body *frame origin*. It equals
    #: the centre of mass only because this fixture declares ``inertial pos="0 0 0"``. A CAD
    #: part with an offset COM must use ``data.subtree_com`` instead; do not copy this.
    times: np.ndarray
    com_z: np.ndarray
    com_vz: np.ndarray
    contact_count: np.ndarray
    mass_kg: float
    inertia_diag: tuple[float, float, float]
    wall_time_s: float
    n_steps: int
    mujoco_version: str
    gravity_z_m_s2: float          # signed, as compiled: negative for downward gravity
    max_geom_size_m: float


def simulate(spec: DropSpec) -> Simulation:
    """Run the fixture headless. No viewer, no rendering, no GPU."""
    mujoco = require_mujoco()
    spec.validate()
    xml = scene_xml(spec)
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)

    n_steps = max(1, int(round(spec.duration_s / spec.timestep_s)))
    sample_every = max(1, int(round(0.005 / spec.timestep_s)))  # 5 ms trace

    times = np.empty(n_steps // sample_every + 2, dtype=float)
    com_z = np.empty_like(times)
    com_vz = np.empty_like(times)
    contacts = np.empty_like(times)

    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "box")
    mujoco.mj_forward(model, data)

    k = 0

    def record() -> None:
        nonlocal k
        times[k] = data.time
        com_z[k] = float(data.xpos[body_id][2])
        com_vz[k] = float(data.qvel[2])  # free joint: qvel[0:3] is linear velocity
        contacts[k] = float(data.ncon)
        k += 1

    record()
    start = time.perf_counter()
    for step in range(1, n_steps + 1):
        mujoco.mj_step(model, data)
        if step % sample_every == 0 or step == n_steps:
            record()
    wall = time.perf_counter() - start

    return Simulation(
        times=times[:k],
        com_z=com_z[:k],
        com_vz=com_vz[:k],
        contact_count=contacts[:k],
        mass_kg=float(model.body_mass[body_id]),
        inertia_diag=tuple(float(v) for v in model.body_inertia[body_id]),
        wall_time_s=wall,
        n_steps=n_steps,
        mujoco_version=mujoco.__version__,
        gravity_z_m_s2=float(model.opt.gravity[2]),
        # Largest half-size of the simulated body's own geoms (the floor plane is a fixture).
        max_geom_size_m=float(np.max(model.geom_size[
            [g for g in range(model.ngeom) if model.geom_bodyid[g] == body_id]
        ])),
    )
