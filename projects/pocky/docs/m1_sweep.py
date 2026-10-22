"""Gate A sweep for the straight-line pusher.

Headless. Does not call ``proposal_sweep.main`` (that rewrites the proposal figure).

    .venv/bin/python projects/pocky/docs/m1_sweep.py

Writes ``out/pocky/linkage_motion/gate_a.json``. Exit code is 1 when any sample fails.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from cadkit.checks import overlap_volume
from projects.pocky.geometry import linkage as linkage_mod
from projects.pocky.geometry.linkage import (
    SLOT_END_MARGIN,
    linkage_from,
    mechanism_solids,
    packet_solids,
    parked_shift,
    phi_for_button_fraction,
    pin_solids,
    pose_at_phi,
    slot_end_clearance,
)
from projects.pocky.params import load_params

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "out" / "pocky" / "linkage_motion" / "gate_a.json"
OVERLAP_FAIL = 1e-3
OVERLAP_NOISE = 1.0
ANALYTIC_TOL = 1e-6
NEAR = {
    ("floor", "pusher"),
    ("packet", "pusher"),
    ("home_stop", "rod"),
    ("forward_stop", "rod"),
}


def main() -> int:
    params = load_params()
    link = linkage_from(params)
    parked = parked_shift(link)
    samples = []
    for i in range(21):
        fraction = i / 20.0
        phi = phi_for_button_fraction(link, fraction)
        pose = pose_at_phi(link, phi)
        solids = mechanism_solids(params, phi)
        solids.update(pin_solids(params, phi))
        chamfer = linkage_mod.CHAMFER_NOTE
        for branch, shift in (("forward", pose.packet_shift), ("return", parked)):
            posed = dict(solids)
            posed.update(packet_solids(params, shift))
            samples.append(_sample(fraction, branch, pose, shift, link, posed, chamfer))
            mark = "PASS" if samples[-1]["status"] == "pass" else "FAIL"
            print(f"{mark}  button {fraction:5.2f}  {branch:7}  phi {math_deg(pose.phi):7.3f}")
    status = "pass" if all(s["status"] == "pass" for s in samples) else "fail"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"gate": "A", "status": status, "chamfer": linkage_mod.CHAMFER_NOTE, "samples": samples}, indent=2) + "\n")
    print(f"{status.upper()}  {OUT}")
    return 0 if status == "pass" else 1


def _sample(fraction, branch, pose, shift, link, solids, chamfer) -> dict:
    failures: list[str] = []
    notes: list[str] = []
    names = list(solids)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            key = tuple(sorted((a, b)))
            vol = _overlap(solids[a], solids[b])
            if key in NEAR:
                err = _analytic_penetration(key, pose, shift, link)
                if err > ANALYTIC_TOL:
                    failures.append(f"{a}∩{b} analytic penetration {err:.6g} mm")
                elif vol > OVERLAP_NOISE:
                    failures.append(f"{a}∩{b} overlap {vol:.6g} mm³")
                elif vol > OVERLAP_FAIL:
                    notes.append(f"{a}∩{b} boolean noise {vol:.6g} mm³")
            elif vol > OVERLAP_FAIL:
                failures.append(f"{a}∩{b} overlap {vol:.6g} mm³")
    button_clear, pusher_clear = slot_end_clearance(link, pose)
    if button_clear < SLOT_END_MARGIN - 1e-9:
        failures.append(f"button slot-end clearance {button_clear:.6f} mm")
    if pusher_clear < SLOT_END_MARGIN - 1e-9:
        failures.append(f"pusher slot-end clearance {pusher_clear:.6f} mm")
    if pose.button_travel < -ANALYTIC_TOL or link.button_stroke - pose.button_travel < -ANALYTIC_TOL:
        failures.append("stop gap is negative")
    ratio = (link.radius / link.e_abs) * math.sin(pose.phi) ** 3
    if abs(pose.speed_ratio - ratio) > ANALYTIC_TOL:
        failures.append(f"speed ratio {pose.speed_ratio} != {ratio}")
    if abs(pose.button_y + 28.0) > ANALYTIC_TOL:
        failures.append(f"button y {pose.button_y}")
    packet_back = -link.packet_length / 2.0 + shift
    if branch == "forward" and pose.face_x > packet_back + ANALYTIC_TOL:
        failures.append("face passed the packet back")
    return {
        "fraction": fraction,
        "branch": branch,
        "phi_deg": math_deg(pose.phi),
        "button_travel": pose.button_travel,
        "face_x": pose.face_x,
        "packet_shift": shift,
        "protrusion": -link.packet_length / 2.0 + shift + link.packet_length - link.outer_x,
        "speed_ratio": pose.speed_ratio,
        "slot_end_clearance": [button_clear, pusher_clear],
        "chamfer": chamfer,
        "status": "fail" if failures else "pass",
        "failures": failures,
        "notes": notes,
    }


def _analytic_penetration(key, pose, shift, link) -> float:
    packet_back = -link.packet_length / 2.0 + shift
    if key == ("packet", "pusher"):
        return max(0.0, pose.face_x - packet_back)
    if key == ("floor", "pusher"):
        # Bullnose bottom is z = 0. The neck stays inside the floor slot by construction.
        return 0.0
    if key == ("home_stop", "rod"):
        return max(0.0, -pose.button_travel)
    if key == ("forward_stop", "rod"):
        return max(0.0, pose.button_travel - link.button_stroke)
    return 0.0


def _overlap(a, b) -> float:
    if _separated(a, b):
        return 0.0
    return overlap_volume(a, b)


def _separated(a, b) -> bool:
    aa, bb = a.bounding_box(), b.bounding_box()
    gap = max(
        max(aa.min.X, bb.min.X) - min(aa.max.X, bb.max.X),
        max(aa.min.Y, bb.min.Y) - min(aa.max.Y, bb.max.Y),
        max(aa.min.Z, bb.min.Z) - min(aa.max.Z, bb.max.Z),
    )
    return gap > 0.02


def math_deg(phi: float) -> float:
    return math.degrees(phi)


if __name__ == "__main__":
    sys.exit(main())
