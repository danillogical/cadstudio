"""Armor check hook: lid interference, lid gap and screen clearance (run after ``bed_fit``)."""
from __future__ import annotations

from cadkit.checks import VOLUME_TOL_MM3, CheckResult, overlap_volume
from cadkit.model import ModelPart

from .params import Params, lid_envelope, screen_prism


def _lid_checks(mp: ModelPart, p: Params) -> list[CheckResult]:
    custom = getattr(mp, "lid_envelope", None)
    env = custom if custom is not None else lid_envelope(p, inflate=0.0)
    vol = overlap_volume(mp.shape, env)
    out = [CheckResult("lid_interference", "pass" if vol <= VOLUME_TOL_MM3 else "fail",
                       f"overlap with lid envelope {vol:.4g} mm^3", vol)]
    gap = float(mp.shape.distance_to(env))
    need = 0.5 * p.fit.slide_clearance
    ok = gap >= need
    out.append(CheckResult("lid_min_gap", "info" if ok else "fail",
                           f"min gap to lid envelope {gap:.3f} mm (need >= {need:.3f})", gap))
    return out


def _screen_clear(mp: ModelPart, p: Params) -> CheckResult:
    custom = getattr(mp, "screen_prism", None)
    prism = custom if custom is not None else screen_prism(p)
    vol = overlap_volume(mp.shape, prism)
    return CheckResult("screen_clear", "pass" if vol <= VOLUME_TOL_MM3 else "fail",
                       f"overlap with screen prism {vol:.4g} mm^3", vol)


def check_hook(mp: ModelPart, p: Params) -> list[CheckResult]:
    """Lid and screen checks; a plain ModelPart (not an ArmorPart) gets both, with the defaults."""
    results: list[CheckResult] = []
    if getattr(mp, "check_lid", True):
        results.extend(_lid_checks(mp, p))
    if getattr(mp, "check_screen", True):
        results.append(_screen_clear(mp, p))
    return results
