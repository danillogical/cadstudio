"""Mass, centre of mass and full inertia tensor, derived from CAD and validated.

Formulas (Codex supervisor review §21.1, established in M0):

    mass_kg      = volume_mm3 * rho_g_cm3 * 1e-6
    I_kg_m2      = I_mm5     * rho_g_cm3 * 1e-12

``build123d`` gives ``volume`` in mm3 and ``matrix_of_inertia`` in mm5 **about the part's own
centre of mass**, with unit density.

A body is an aggregate of parts welded together, so its tensor is the parallel-axis sum about
the body centre of mass — never an average of the parts' matrices.

Important MuJoCo distinction, per the M1 supervisor review: ``data.xipos`` is the body centre
of mass and ``data.xpos`` is the body frame origin. ``data.subtree_com`` includes descendants
and must never be used as a body's COM.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .schema import BodySpec, PartSpec
from .units import inertia_kg_m2, mass_kg, mm_to_m

#: Relative tolerance for the principal-moment triangle inequality.
TRIANGLE_RTOL = 1e-6


@dataclass(frozen=True)
class Inertial:
    """A body's mass properties in **body-local** metres, about its centre of mass."""

    mass_kg: float
    com_m: tuple[float, float, float]
    #: Full symmetric tensor in kg m2, in body axes, about the COM.
    inertia_kg_m2: tuple[tuple[float, float, float], ...]
    source: str

    def principal_moments(self) -> tuple[float, float, float]:
        vals = np.linalg.eigvalsh(np.array(self.inertia_kg_m2, dtype=float))
        return tuple(float(v) for v in vals)  # type: ignore[return-value]


def part_inertial(part: PartSpec) -> tuple[float, np.ndarray, np.ndarray]:
    """Mass (kg), assembly COM (m), and the tensor in **assembly** axes about that COM.

    ``PartSpec.shape`` is already authored in assembly coordinates, and build123d reports
    ``center(CenterOf.MASS)`` and ``matrix_of_inertia`` in the shape's own axes about its own
    COM. So **no frame transform belongs here**: applying the body frame again would
    double-transform any part in a rotated body. The single assembly -> body-local step is
    done once, in :func:`body_inertial`.
    """
    if part.shape is None:
        raise ValueError(f"part {part.part_id!r} has no shape; cannot derive inertia")

    volume_mm3 = float(part.shape.volume)
    density = part.density_g_cm3
    if part.mass_kg is not None:
        if density is None:
            # Measured mass with no density: treat the solid as uniform at the implied density
            # so the mass *distribution* is preserved and the inertia is rescaled consistently.
            density = part.mass_kg * 1e6 / volume_mm3
        shape_mass = mass_kg(volume_mm3, density)
        scale = part.mass_kg / shape_mass
        mass = part.mass_kg
    else:
        scale = 1.0
        mass = mass_kg(volume_mm3, density)

    com_mm = part.shape.center(_center_of_mass())
    com_assembly_mm = np.array([com_mm.X, com_mm.Y, com_mm.Z], dtype=float)

    tensor_mm5 = np.array(part.shape.matrix_of_inertia, dtype=float)

    # unit-density mm5 -> kg m2, then rescale for a measured-mass override
    tensor_kg_m2 = tensor_mm5 * density * scale * 1e-12
    return mass, com_assembly_mm * 1e-3, tensor_kg_m2


def _center_of_mass():
    from build123d import CenterOf

    return CenterOf.MASS


def body_inertial(body: BodySpec) -> Inertial:
    """Aggregate a body's parts into one inertial record in body-local axes.

    Parallel-axis theorem, applied per part about the **body** COM:

        I_body = sum( I_part + m_part * (|d|^2 * Identity - d outer d) ),  d = com_part - com_body
    """
    body.validate()
    masses: list[float] = []
    coms: list[np.ndarray] = []
    tensors: list[np.ndarray] = []

    for part in body.parts:
        if part.role == "spare":
            continue  # not part of the rigid body
        m, com_asm, tensor_asm = part_inertial(part)
        masses.append(m)
        coms.append(com_asm)
        tensors.append(tensor_asm)

    total = float(sum(masses))
    if not math.isfinite(total) or total <= 0.0:
        raise ValueError(f"body {body.body_id!r} has non-positive total mass {total!r}")
    com = sum((m * c for m, c in zip(masses, coms)), start=np.zeros(3)) / total

    aggregate = np.zeros((3, 3), dtype=float)
    for m, c, t in zip(masses, coms, tensors):
        d = c - com
        aggregate += t + m * (float(d @ d) * np.eye(3) - np.outer(d, d))

    # rotate into body-local axes: R^T I_asm R
    r = np.array(body.frame.rotation_matrix(), dtype=float)
    local = r.T @ aggregate @ r
    local = 0.5 * (local + local.T)  # remove numerical asymmetry

    _validate_tensor(body.body_id, local)
    com_local_m = r.T @ (com - np.array(body.frame.pos_mm) * 1e-3)

    return Inertial(
        mass_kg=total,
        com_m=tuple(float(v) for v in com_local_m),  # type: ignore[arg-type]
        inertia_kg_m2=tuple(tuple(float(v) for v in row) for row in local),  # type: ignore[arg-type]
        source="; ".join(sorted({p.source.kind for p in body.parts})),
    )


def _validate_tensor(name: str, tensor: np.ndarray) -> None:
    if not np.all(np.isfinite(tensor)):
        raise ValueError(f"body {name!r} inertia contains a non-finite value")
    asym = float(np.max(np.abs(tensor - tensor.T)))
    if asym > 1e-12 * max(1.0, float(np.max(np.abs(tensor)))):
        raise ValueError(f"body {name!r} inertia is asymmetric by {asym:g}")
    vals = np.linalg.eigvalsh(tensor)
    if not np.all(vals > 0.0):
        raise ValueError(f"body {name!r} inertia is not positive definite: {vals}")
    i1, i2, i3 = float(vals[0]), float(vals[1]), float(vals[2])
    # principal moments of any real body satisfy I1 + I2 >= I3
    if i1 + i2 < i3 * (1.0 - TRIANGLE_RTOL):
        raise ValueError(
            f"body {name!r} principal moments violate the triangle inequality: "
            f"{i1:.6g} + {i2:.6g} < {i3:.6g}"
        )


def assembly_point_to_m(point_mm: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(mm_to_m(v) for v in point_mm)  # type: ignore[return-value]
