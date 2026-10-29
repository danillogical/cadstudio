"""Starter check hook: the gap to the mating part (runs after ``bed_fit``)."""
from __future__ import annotations

from cadkit.checks import CheckResult
from cadkit.model import ModelPart

from .params import Params


def check_hook(mp: ModelPart, p: Params) -> list[CheckResult]:
    """FAIL if the part is closer to its mate than half of ``fit.clearance``; no mate, no check."""
    mate = getattr(mp, "mate", None)
    if mate is None:
        return []
    gap = float(mp.shape.distance_to(mate))
    need = 0.5 * p.fit.clearance
    return [CheckResult("clearance", "pass" if gap >= need else "fail",
                        f"min gap to mating part {gap:.3f} mm (need >= {need:.3f})", gap)]
