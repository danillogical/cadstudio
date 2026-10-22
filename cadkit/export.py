"""STEP / STL / 3MF export."""
from __future__ import annotations

from pathlib import Path

from build123d import Compound, Mesher, export_step

from .mesh import posed_shape
from .model import ModelPart


def export_part(name: str, mp: ModelPart, outdir) -> dict[str, Path]:
    """Write ``<name>.step`` (assembly coords) and ``.stl``/``.3mf`` (print pose).

    Returns a dict with keys ``step``, ``stl``, ``3mf``.
    """
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    paths = {ext: outdir / f"{name}.{ext}" for ext in ("step", "stl", "3mf")}
    export_step(mp.shape, str(paths["step"]))
    posed = posed_shape(mp)
    for ext in ("stl", "3mf"):
        mesher = Mesher()
        mesher.add_shape(posed)
        mesher.write(str(paths[ext]))
    return paths


def export_assembly(parts: dict[str, ModelPart], outdir) -> Path:
    """Write all parts together in assembly coordinates to ``assembly.step``."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / "assembly.step"
    export_step(Compound([mp.shape for mp in parts.values()]), str(path))
    return path
