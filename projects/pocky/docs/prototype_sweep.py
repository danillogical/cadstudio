"""Gate A and Gate B for the printed prototype.

Headless. Does not edit ``m1_sweep.py`` or the M1 solids.

    UV_NO_SYNC=1 uv run python projects/pocky/docs/prototype_sweep.py

Writes ``out/pocky/prototype/gate_a.json``. Exit code is 1 when a sample fails.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from build123d import Pos

from cadkit.checks import overlap_volume
from projects.pocky.geometry.linkage import (
    SLOT_END_MARGIN,
    linkage_from,
    packet_solids,
    parked_shift,
    phi_for_button_fraction,
    pose_at_phi,
    slot_end_clearance,
)
from projects.pocky.geometry.packet import packet
from projects.pocky.geometry.prototype import (
    PROTOTYPE_SPRING,
    _lip,
    button_keepout,
    compressed_length,
    moving_solids,
    spring_solid,
    static_solids,
)
from projects.pocky.params import load_params

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "out" / "pocky" / "prototype" / "gate_a.json"
OVERLAP_FAIL = 1e-3
OVERLAP_NOISE = 1.0
ANALYTIC_TOL = 1e-6
GAPS = (5.35, 5.75, 6.15, 6.55)
# Faces that are supposed to meet. A boolean sliver there is noise.
NEAR = {
    ("packet", "pusher"),
    ("body", "packet"),
    ("body", "pusher"),
    ("chassis", "rod"),
    ("lip", "packet"),
    ("rod", "spring"),
    ("spring", "spring_seat"),
    ("chassis", "spring_seat"),
}
# The peg sits in these holes on purpose. Slot-end clearance is checked apart.
PEG_SEAT = {
    ("crank", "peg_pivot"),
    ("chassis", "peg_pivot"),
    ("crank", "peg_pusher"),
    ("peg_pusher", "pusher"),
    ("crank", "peg_button"),
    ("peg_button", "rod"),
}


def main() -> int:
    params = load_params()
    link = linkage_from(params)
    parked = parked_shift(link)
    static = static_solids(params, link, 5.75)
    # The dummy is a print part parked beside the machine. It is not a collision partner.
    housing = {k: v for k, v in static.items() if not k.startswith("dummy")}
    failures: list[str] = []
    notes: list[str] = []
    _solids_once(housing, failures)
    _hooks(housing, failures)
    _keepout(link, housing, failures)
    _spring_block(link, failures)
    gate_b = _gate_b(params, link, failures)
    samples = []
    poses = [(i / 20.0, phi_for_button_fraction(link, i / 20.0)) for i in range(21)]
    poses.append(("neck", math.radians(109.5)))
    for fraction, phi in poses:
        pose = pose_at_phi(link, phi)
        moving = moving_solids(params, link, pose, compressed_length(pose.button_travel))
        paired = dict(housing)
        paired.update(moving)
        base = _pairs(paired, pose, None, link)
        for branch, shift in (("forward", pose.packet_shift), ("return", parked)):
            posed = dict(paired)
            posed.update(packet_solids(params, shift))
            # The second packet is the one the separator holds. Only the pusher may not hit it.
            second = posed.pop("packet2")
            sample_fail = list(base)
            sample_notes: list[str] = []
            for name, shape in posed.items():
                if name == "packet":
                    continue
                _judge(sample_fail, sample_notes, "packet", name, posed["packet"], shape, pose, shift, link)
            pushed = overlap_volume(posed["pusher"], second) if not _separated(posed["pusher"], second) else 0.0
            if pushed > OVERLAP_FAIL:
                sample_fail.append(f"pusher∩packet2 overlap {pushed:.6g} mm³")
            if posed["pusher"].bounding_box().max.Z > 4.2 + 1e-6:
                sample_fail.append(f"pusher top {posed['pusher'].bounding_box().max.Z:.3f} mm")
            button_clear, pusher_clear = slot_end_clearance(link, pose)
            if button_clear < SLOT_END_MARGIN - 1e-9:
                sample_fail.append(f"button slot-end clearance {button_clear:.6f} mm")
            if pusher_clear < SLOT_END_MARGIN - 1e-9:
                sample_fail.append(f"pusher slot-end clearance {pusher_clear:.6f} mm")
            label = fraction if isinstance(fraction, str) else f"{fraction:.2f}"
            mark = "PASS" if not sample_fail else "FAIL"
            print(f"{mark}  button {label:>5}  {branch:7}  phi {math.degrees(pose.phi):7.3f}")
            for item in sample_fail:
                print(f"      {item}")
            samples.append({
                "fraction": fraction,
                "branch": branch,
                "phi_deg": math.degrees(pose.phi),
                "button_travel": pose.button_travel,
                "face_x": pose.face_x,
                "packet_shift": shift,
                "spring_length": compressed_length(pose.button_travel),
                "slot_end_clearance": [button_clear, pusher_clear],
                "status": "fail" if sample_fail else "pass",
                "failures": sample_fail,
                "notes": sample_notes,
            })
            failures.extend(f"{label}/{branch}: {item}" for item in sample_fail)
            notes.extend(sample_notes)
    status = "pass" if not failures else "fail"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "gate": "A",
        "status": status,
        "spring": "B",
        "gap": 5.75,
        "gate_b": gate_b,
        "notes": notes,
        "failures": failures,
        "samples": samples,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"{status.upper()}  {OUT}")
    return 0 if status == "pass" else 1


def _solids_once(housing: dict, failures: list[str]) -> None:
    free = spring_solid(PROTOTYPE_SPRING, PROTOTYPE_SPRING.free_length, 0.0, 0.0, 0.0)
    box = free.bounding_box()
    size = (box.max.X - box.min.X, box.max.Y - box.min.Y, box.max.Z - box.min.Z)
    if any(abs(a - b) > 1e-6 for a, b in zip(size, (53.4, 14.0, 5.0))):
        failures.append(f"free spring bbox {size}")
    if len(free.solids()) != 1 or not free.is_valid:
        failures.append("free spring is not one valid solid")
    for name, shape in housing.items():
        if len(shape.solids()) != 1 or not shape.is_valid:
            failures.append(f"{name} is not one valid solid")


def _hooks(housing: dict, failures: list[str]) -> None:
    body, chassis, lip = housing["body"], housing["chassis"], housing["lip"]
    if overlap_volume(chassis, body) > OVERLAP_FAIL:
        failures.append("chassis hook intersects the body while seated")
    dropped = overlap_volume(Pos(0, 0, -1.0) * chassis, body)
    if dropped <= OVERLAP_FAIL:
        failures.append("chassis can drop 1 mm in -Z without a hook meeting the body")
    if overlap_volume(lip, body) > OVERLAP_FAIL:
        failures.append("lip intersects the body while seated")
    pulled = overlap_volume(Pos(1.0, 0, 0) * lip, body)
    if pulled <= OVERLAP_FAIL:
        failures.append("lip can slide 1 mm in +X without the tooth meeting the bar")


def _keepout(link, housing: dict, failures: list[str]) -> None:
    keep = button_keepout(link)
    for name in ("body", "chassis"):
        vol = overlap_volume(keep, housing[name])
        if vol > OVERLAP_FAIL:
            failures.append(f"button keepout intersects {name} ({vol:.4g} mm³)")


def _spring_block(link, failures: list[str]) -> None:
    full = compressed_length(link.button_stroke)
    margin = full - PROTOTYPE_SPRING.solid_length
    if margin < 6.0 - 1e-6:
        failures.append(f"full-press margin {margin:.3f} mm is under 6 mm")


def _gate_b(params, link, failures: list[str]) -> list[dict]:
    """A 5.2 mm packet passes every shim. Two rigid packets do not."""
    rows = []
    one = packet(params)
    upper = Pos(0, 0, params.packet.height) * packet(params)
    for gap in GAPS:
        lip = _lip(params, link, gap)
        one_hit = overlap_volume(lip, one)
        two_hit = overlap_volume(lip, upper)
        row = {"gap": gap, "one": one_hit, "two": two_hit}
        rows.append(row)
        if one_hit > OVERLAP_FAIL:
            failures.append(f"gate B: 5.2 mm packet hits the lip at gap {gap}")
        if two_hit <= OVERLAP_FAIL:
            failures.append(f"gate B: 10.4 mm stack misses the lip at gap {gap}")
    return rows


def _pairs(solids: dict, pose, shift, link) -> list[str]:
    failures: list[str] = []
    names = list(solids)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            _judge(failures, [], a, b, solids[a], solids[b], pose, shift, link)
    return failures


def _judge(failures, notes, a, b, shape_a, shape_b, pose, shift, link) -> None:
    key = tuple(sorted((a, b)))
    if key in PEG_SEAT:
        return
    if _separated(shape_a, shape_b):
        return
    vol = overlap_volume(shape_a, shape_b)
    if key in NEAR:
        err = _analytic(key, pose, shift, link)
        if err > ANALYTIC_TOL:
            failures.append(f"{a}∩{b} analytic penetration {err:.6g} mm")
        elif vol > OVERLAP_NOISE:
            failures.append(f"{a}∩{b} overlap {vol:.6g} mm³")
        elif vol > OVERLAP_FAIL:
            notes.append(f"{a}∩{b} boolean noise {vol:.6g} mm³")
    elif vol > OVERLAP_FAIL:
        failures.append(f"{a}∩{b} overlap {vol:.6g} mm³")


def _analytic(key, pose, shift, link) -> float:
    if key == ("packet", "pusher") and shift is not None:
        packet_back = -link.packet_length / 2.0 + shift
        return max(0.0, pose.face_x - packet_back)
    if key == ("chassis", "rod"):
        home = max(0.0, -pose.button_travel)
        forward = max(0.0, pose.button_travel - link.button_stroke)
        return max(home, forward)
    return 0.0


def _separated(a, b) -> bool:
    aa, bb = a.bounding_box(), b.bounding_box()
    gap = max(
        max(aa.min.X, bb.min.X) - min(aa.max.X, bb.max.X),
        max(aa.min.Y, bb.min.Y) - min(aa.max.Y, bb.max.Y),
        max(aa.min.Z, bb.min.Z) - min(aa.max.Z, bb.max.Z),
    )
    return gap > 0.02


if __name__ == "__main__":
    sys.exit(main())
