"""One ejection cycle in the OCP CAD Viewer.

The cycle is the plan's final step: a geometry record, not a bench result.
One button fraction drives every track, through ``phi_for_button_fraction``
and ``pose_at_phi``. Nothing is hand-placed.

Open the OCP CAD Viewer, then run:

    UV_NO_SYNC=1 uv run python projects/pocky/docs/prototype_animation.py

Tracks are offsets from the home pose. The crank's location is the pivot, so
``rz`` spins it about that pivot. The spring beams and folds are the installed
serpentine, each moved in X as the gap closes. A fold's radius is fixed, because
a track cannot change a solid's shape, so the folds crowd together at full press.
The packet drop in the last 10 frames is a scripted translation.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

from build123d import Color, Compound, Pos

from ocp_vscode import Animation, Camera, find_and_set_port, get_port, show

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
    DEFAULT_GAP,
    PROTOTYPE_SPRING,
    ROD_PAD_X,
    SPRING_Y,
    SPRING_Z0,
    _box,
    _half_ring,
    compressed_length,
    moving_solids,
    static_solids,
)
from projects.pocky.params import load_params

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "out" / "pocky" / "prototype" / "animation" / "simulation.json"
HOLD = 10
STEPS = 51
FPS = 15
# Taken off the lip, out the open top. A track cannot hide a solid.
TAKE_X = 40.0
TAKE_Z = 90.0


def _load_sweep():
    path = Path(__file__).with_name("prototype_sweep.py")
    spec = importlib.util.spec_from_file_location("pocky_prototype_sweep", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SWEEP = _load_sweep()


def _paint(shape, label: str, color: str, alpha: float = 1.0):
    shape.label = label
    shape.color = Color(color, alpha)
    return shape


@dataclass(frozen=True)
class Sample:
    phase: str
    step: int
    packet_present: bool
    take: float
    packet2_z: float

    @property
    def fraction(self) -> float:
        return self.step / (STEPS - 1)


def timeline(height: float) -> list[Sample]:
    """10 home, 51 press, 10 presentation, 51 return, 10 home with the drop."""
    frames: list[Sample] = []

    def add(phase: str, step: int, present: bool, take: float, z: float) -> None:
        frames.append(Sample(phase, step, present, take, z))

    for _ in range(HOLD):
        add("hold_home", 0, True, 0.0, height)
    for step in range(STEPS):
        add("press", step, True, 0.0, height)
    for i in range(HOLD):
        # The first of these frames is still the presented packet. Then it is taken.
        add("hold_presentation", STEPS - 1, i == 0, i / (HOLD - 1), height)
    for step in range(STEPS - 1, -1, -1):
        add("return", step, False, 1.0, height)
    for i in range(HOLD):
        z = height * (1.0 - i / (HOLD - 1))
        add("hold_end", 0, False, 1.0, z)
    if len(frames) != 132:
        raise RuntimeError(f"expected 132 frames, built {len(frames)}")
    return frames


def _pose(link, step: int):
    return pose_at_phi(link, phi_for_button_fraction(link, step / (STEPS - 1)))


def spring_pieces():
    """Installed variant B, as separate solids so each can move on its own track.

    Same layout as ``spring_solid`` at the installed length. The seat end stays
    put. Beam ``i`` and fold ``i`` close toward that end as the button travels.
    """
    spec = PROTOTYPE_SPRING
    length = spec.installed()
    x0 = ROD_PAD_X - length
    gaps = spec.beams - 1
    gap = (length - spec.solid_length) / gaps
    pitch = spec.thickness + gap
    t = spec.thickness
    rc = pitch / 2.0
    ri = rc - t / 2.0
    ro = rc + t / 2.0
    y_out = spec.amplitude / 2.0
    fold_y = y_out - ro
    z0, z1 = SPRING_Z0, SPRING_Z0 + spec.height
    y_center = SPRING_Y
    pieces: list[tuple[str, object, float]] = []
    pieces.append((
        "seat_pad",
        _box(x0, x0 + spec.pad + 0.2, y_center - y_out, y_center + y_out, z0, z1),
        0.0,
    ))
    rod_pad_x = x0 + length - spec.pad
    pieces.append((
        "rod_pad",
        _box(rod_pad_x - 0.2, x0 + length, y_center - y_out, y_center + y_out, z0, z1),
        1.0,
    ))
    first = x0 + spec.pad
    for i in range(spec.beams):
        bx = first + i * pitch
        y0b, y1b = -y_out, y_out
        has_pos = (i % 2 == 0 and i < gaps) or (i % 2 == 1 and i > 0)
        has_neg = (i % 2 == 1 and i < gaps) or (i % 2 == 0 and i > 0)
        if has_pos:
            y1b = fold_y + 0.2
        if has_neg:
            y0b = -fold_y - 0.2
        # Index / gaps: the seat beam stays, the rod beam travels with the button.
        pieces.append((
            f"beam_{i:02d}",
            _box(bx, bx + t, y_center + y0b, y_center + y1b, z0, z1),
            i / gaps,
        ))
    for i in range(gaps):
        cx = first + t / 2.0 + i * pitch + rc
        positive = i % 2 == 0
        cy = y_center + (fold_y if positive else -fold_y)
        pieces.append((
            f"fold_{i:02d}",
            _half_ring(cx, cy, z0, z1, ri, ro, positive),
            (i + 0.5) / gaps,
        ))
    return pieces


def assembly(params, link):
    """Home pose. Moving parts are where a zero track leaves them."""
    home = _pose(link, 0)
    housing = {
        name: shape
        for name, shape in static_solids(params, link, DEFAULT_GAP).items()
        if not name.startswith("dummy")
    }
    moving = moving_solids(params, link, home, compressed_length(0.0))
    body = _paint(housing.pop("body"), "body", "#6f9a86", 0.35)
    named = [body]
    palette = {
        "chassis": "#a58f6e",
        "lip": "#8f7aa8",
        "spring_seat": "#a0a266",
        "shim_04_a": "#6e97a8",
        "shim_04_b": "#6e97a8",
        "shim": "#6e97a8",
    }
    for name, shape in housing.items():
        named.append(_paint(shape, name, palette.get(name, "#a58f6e")))
    named.append(_paint(moving["crank"], "crank", "#8f7aa8"))
    named.append(_paint(moving["rod"], "rod", "#a58f6e"))
    named.append(_paint(moving["pusher"], "pusher", "#a0a266"))
    named.append(_paint(moving["peg_pivot"], "peg_pivot", "#a58f6e"))
    named.append(_paint(moving["peg_pusher"], "peg_pusher", "#a58f6e"))
    named.append(_paint(moving["peg_button"], "peg_button", "#a58f6e"))
    named.append(_paint(packet(params), "packet", "#8a8f99"))
    named.append(_paint(Pos(0.0, 0.0, params.packet.height) * packet(params), "packet2", "#5a6270"))
    pieces = []
    factors: dict[str, float] = {}
    for label, shape, factor in spring_pieces():
        pieces.append(_paint(shape, label, "#6e97a8"))
        factors[label] = factor
    named.append(Compound(label="spring", children=pieces))
    return Compound(label="dispenser", children=named), factors


def _check_pose(housing, moving, pose, shift, link, params):
    failures: list[str] = []
    notes: list[str] = []
    paired = {**housing, **moving}
    failures.extend(SWEEP._pairs(paired, pose, None, link))
    packets = packet_solids(params, shift)
    for name, shape in paired.items():
        SWEEP._judge(
            failures, notes, "packet", name, packets["packet"], shape, pose, shift, link,
        )
    second = packets["packet2"]
    pusher = paired["pusher"]
    pushed = 0.0 if SWEEP._separated(pusher, second) else SWEEP.overlap_volume(pusher, second)
    if pushed > SWEEP.OVERLAP_FAIL:
        failures.append(f"pusher∩packet2 overlap {pushed:.6g} mm³")
    if pusher.bounding_box().max.Z > 4.2 + 1e-6:
        failures.append(f"pusher top {pusher.bounding_box().max.Z:.3f} mm")
    button_clear, pusher_clear = slot_end_clearance(link, pose)
    if button_clear < SLOT_END_MARGIN - 1e-9:
        failures.append(f"button slot-end clearance {button_clear:.6f} mm")
    if pusher_clear < SLOT_END_MARGIN - 1e-9:
        failures.append(f"pusher slot-end clearance {pusher_clear:.6f} mm")
    return failures, notes, (button_clear, pusher_clear)


def _drop_extra(lowered, solids, z_bottom: float):
    """Lip contact while the second packet is still above the floor is the scripted transit."""
    failures: list[str] = []
    notes: list[str] = []
    for name, shape in solids.items():
        if SWEEP._separated(lowered, shape):
            continue
        vol = SWEEP.overlap_volume(lowered, shape)
        if vol <= SWEEP.OVERLAP_FAIL:
            continue
        if name == "lip" and z_bottom > 1e-6:
            notes.append(f"packet2∩lip scripted transit {vol:.4g} mm³")
            continue
        if name == "body" and vol <= SWEEP.OVERLAP_NOISE:
            notes.append(f"packet2∩body boolean noise {vol:.4g} mm³")
            continue
        failures.append(f"packet2∩{name} overlap {vol:.6g} mm³")
    return failures, notes


def check_cycle(params, link, frames: list[Sample]):
    housing = {
        name: shape
        for name, shape in static_solids(params, link, DEFAULT_GAP).items()
        if not name.startswith("dummy")
    }
    once: list[str] = []
    SWEEP._solids_once(housing, once)
    SWEEP._hooks(housing, once)
    SWEEP._keepout(link, housing, once)
    SWEEP._spring_block(link, once)
    if once:
        return once, []
    parked = parked_shift(link)
    height = params.packet.height
    moving_at = {}
    cache = {}
    rows = []
    failed = False
    for frame in frames:
        pose = _pose(link, frame.step)
        branch = "forward" if frame.phase in ("hold_home", "press", "hold_presentation") else "return"
        key = (frame.step, branch)
        if key not in cache:
            if frame.step not in moving_at:
                moving_at[frame.step] = moving_solids(
                    params, link, pose, compressed_length(pose.button_travel),
                )
            shift = pose.packet_shift if branch == "forward" else parked
            cache[key] = _check_pose(
                housing, moving_at[frame.step], pose, shift, link, params,
            )
            mark = "PASS" if not cache[key][0] else "FAIL"
            print(f"{mark}  button {frame.fraction:5.2f}  {branch}", flush=True)
        failures, notes, clearance = cache[key]
        failures, notes = list(failures), list(notes)
        if frame.phase == "hold_end" and abs(frame.packet2_z - height) > 1e-9:
            lowered = packet(params) if frame.packet2_z == 0.0 else Pos(0.0, 0.0, frame.packet2_z) * packet(params)
            extra_fail, extra_notes = _drop_extra(
                lowered, {**housing, **moving_at[frame.step]}, frame.packet2_z,
            )
            failures.extend(extra_fail)
            notes.extend(extra_notes)
        if failures:
            failed = True
            for item in failures:
                print(f"      {item}", flush=True)
        if frame.packet_present:
            recorded_shift = pose.packet_shift
        elif frame.phase == "return":
            recorded_shift = parked
        else:
            recorded_shift = None
        rows.append({
            "frame": len(rows),
            "phase": frame.phase,
            "button_fraction": frame.fraction,
            "crank_angle_deg": math.degrees(pose.phi),
            "button_travel": pose.button_travel,
            "pusher_face_x": pose.face_x,
            "bottom_packet_shift": recorded_shift,
            "protrusion": pose.protrusion if frame.packet_present else None,
            "second_packet_z": frame.packet2_z,
            "slot_end_clearance": list(clearance),
            "overlap_status": "fail" if failures else "pass",
            "packet_present": frame.packet_present,
            "packet_drop": "scripted" if frame.phase == "hold_end" else "none",
            "taken": frame.take > 0.0 and not frame.packet_present,
            "failures": failures,
            "notes": notes,
        })
    if failed:
        return ["one or more frames failed"], rows
    return [], rows


def _tracks(link, frames: list[Sample], factors: dict[str, float]):
    """Offsets from the home pose. Times are seconds at 15 fps."""
    home = _pose(link, 0)
    parked = parked_shift(link)
    times = [i / FPS for i in range(len(frames))]
    crank, rod, pusher, button, pin, packet_t, packet2_z = [], [], [], [], [], [], []
    spring = {name: [] for name in factors}
    for frame in frames:
        pose = _pose(link, frame.step)
        travel = pose.button_travel
        crank.append(math.degrees(pose.phi - home.phi))
        rod.append(-travel)
        pusher.append(pose.face_x - home.face_x)
        button.append(pose.button_x - home.button_x)
        pin.append((
            pose.pusher_pin_x - home.pusher_pin_x,
            pose.pusher_pin_y - home.pusher_pin_y,
            0.0,
        ))
        shift = pose.packet_shift if frame.packet_present or frame.phase == "hold_presentation" else parked
        if frame.phase == "hold_home" or frame.phase == "press":
            shift = pose.packet_shift
        packet_t.append((shift + TAKE_X * frame.take, 0.0, TAKE_Z * frame.take))
        packet2_z.append(frame.packet2_z - frames[0].packet2_z)
        for name, factor in factors.items():
            spring[name].append(-travel * factor)
    tracks = [
        ("/dispenser/crank", "rz", times, crank),
        ("/dispenser/rod", "tx", times, rod),
        ("/dispenser/pusher", "tx", times, pusher),
        ("/dispenser/peg_button", "tx", times, button),
        ("/dispenser/peg_pusher", "t", times, pin),
        ("/dispenser/packet", "t", times, packet_t),
        ("/dispenser/packet2", "tz", times, packet2_z),
    ]
    for name, values in spring.items():
        if factors[name] == 0.0:
            continue
        tracks.append((f"/dispenser/spring/{name}", "tx", times, values))
    return tracks


def _write_json(rows, status: str) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "spring": "B",
        "gap": DEFAULT_GAP,
        "frames": len(rows),
        "fps": FPS,
        "duration_s": len(rows) / FPS,
        "packet_drop": "scripted",
        "viewer": "ocp_vscode",
        "command": "UV_NO_SYNC=1 uv run python projects/pocky/docs/prototype_animation.py",
        "rows": rows,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")


def _ocp_paths(node, prefix="") -> list[str]:
    path = f"{prefix}/{node.name}"
    found = [path]
    for child in getattr(node, "objects", []) or []:
        found.extend(_ocp_paths(child, path))
    return found


def _require_paths(model, tracks) -> list[str]:
    from ocp_tessellate.convert import to_ocpgroup

    group, _instances = to_ocpgroup(model)
    paths = set(_ocp_paths(group))
    missing = [path for path, _action, _times, _values in tracks if path not in paths]
    return missing


def main() -> int:
    params = load_params()
    link = linkage_from(params)
    home = _pose(link, 0)
    full = _pose(link, STEPS - 1)
    if abs(full.protrusion - 40.0) > 1e-6:
        print(f"FAIL  full-stroke protrusion is {full.protrusion:.4f} mm", file=sys.stderr)
        return 1
    if abs((full.face_x - home.face_x) - link.stroke) > 1e-6:
        print("FAIL  pusher stroke is not the linkage stroke", file=sys.stderr)
        return 1
    frames = timeline(params.packet.height)
    print("building home assembly", flush=True)
    model, factors = assembly(params, link)
    print("checking poses", flush=True)
    errors, rows = check_cycle(params, link, frames)
    if errors:
        if rows:
            _write_json(rows, "fail")
        for item in errors:
            print(f"FAIL  {item}", flush=True)
        return 1
    _write_json(rows, "pass")
    tracks = _tracks(link, frames, factors)
    missing = _require_paths(model, tracks)
    if missing:
        print("FAIL  animation paths are not in the assembly:", file=sys.stderr)
        for path in missing:
            print(f"      {path}", file=sys.stderr)
        return 1
    find_and_set_port()
    if get_port() is None:
        print(
            "OCP CAD Viewer is not connected. Open it in VS Code, then run this file again.",
            file=sys.stderr,
        )
        print(f"PASS  poses  {OUT}", flush=True)
        return 1
    show(model, reset_camera=Camera.ISO)
    animation = Animation(model)
    for path, action, times, values in tracks:
        animation.add_track(path, action, times, values)
    animation.animate(speed=1)
    print(f"PASS  {len(frames)} frames, {len(frames) / FPS:.1f} s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
