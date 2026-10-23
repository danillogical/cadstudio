"""Static preflight for the Pocky prototype: no MuJoCo, exact CAD geometry.

Reports the load path that the approved plan pre-recorded:

* the clip teeth are a **retention-only** bearing: the tooth underside is 0.05 mm above the
  body rib top, so gravity separates them and cannot be carried downward;
* the support margin of the body alone and of the hanging group (body + lip + shims), using
  the measured clip patches;
* exact-solid overlap for every body group at all five button fractions;
* the derived tilted packet seat inventory (10 and 25 packets), against the installed
  assembly.

The 0.02 mm collider/CAD clearance audit lives in ``clearance_audit.py`` because it needs the
compiled scene. This module is importable without MuJoCo.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from build123d import Box, CenterOf, Pos, Rot

from cadkit.checks import overlap_volume
from cadkit.physics.support import SupportMargin, bearing_carries, support_margin

from projects.pocky.geometry.linkage import (
    linkage_from,
    phi_for_button_fraction,
    pose_at_phi,
)
from projects.pocky.geometry.packet import packet
from projects.pocky.geometry.prototype import (
    DEFAULT_GAP,
    LEDGE_Z,
    _tube,
    static_solids,
    moving_solids,
    compressed_length,
)
from projects.pocky.params import Params
from projects.pocky.physics.assembly import RESET_FRACTIONS, reset_state

#: Exact-solid overlap volumes at or below this are boolean noise (prototype_sweep.py).
OVERLAP_NOISE_MM3 = 1.0e-3
#: M0 measured clip bearing patches, corners in mm (x, y).
CLIP_PATCHES_MM = (
    ((64.0, 34.0), (70.0, 34.0), (70.0, 35.0), (64.0, 35.0)),
    ((-36.0, -35.0), (-30.0, -35.0), (-30.0, -34.0), (-36.0, -34.0)),
)
CLIP_TOOTH_UNDERSIDE_Z = 0.05
CLIP_RIB_TOP_Z = 0.0
#: Derived tilted seat: bottom packet rear top to the blade rear edge (plan section 5.1).
SEAT_CLEARANCE_MM = 0.001


def assembly_solids(p: Params, fraction: float) -> dict[str, object]:
    """Every installed CAD solid at one button fraction, grouped by simulated body.

    Excludes the bench ``dummy`` and the parked ``shim_08``, which are print parts, not
    installed assembly parts. The spring uses its compressed length so it sits on its seat.
    """
    link = linkage_from(p)
    pose = pose_at_phi(link, phi_for_button_fraction(link, fraction))
    static = static_solids(p, link, DEFAULT_GAP)
    moving = moving_solids(p, link, pose, compressed_length(pose.button_travel))
    return {
        "body": [static["body"], static["shim_04_a"], static["shim_04_b"]],
        "lip": [static["lip"]],
        "chassis": [static["chassis"], static["spring_seat"], moving["peg_pivot"]],
        "crank": [moving["crank"], moving["peg_pusher"]],
        "rod": [moving["rod"], moving["peg_button"], moving["spring"]],
        "pusher": [moving["pusher"]],
    }


def _fuse(shapes):
    acc = shapes[0]
    for shape in shapes[1:]:
        acc = acc + shape
    return acc.solid()


def _body_shapes(p: Params, fraction: float) -> dict[str, object]:
    return {name: _fuse(parts) for name, parts in assembly_solids(p, fraction).items()}


def _separated(a, b, tol: float = 0.02) -> bool:
    aa, bb = a.bounding_box(), b.bounding_box()
    gap = max(
        max(aa.min.X, bb.min.X) - min(aa.max.X, bb.max.X),
        max(aa.min.Y, bb.min.Y) - min(aa.max.Y, bb.max.Y),
        max(aa.min.Z, bb.min.Z) - min(aa.max.Z, bb.max.Z),
    )
    return gap > tol


def exact_overlap_inventory(p: Params) -> dict:
    """Pairwise exact-solid overlap of the installed groups at all five fractions."""
    fractions = {}
    ok = True
    for fraction in RESET_FRACTIONS:
        shapes = _body_shapes(p, fraction)
        names = sorted(shapes)
        rows = []
        worst = 0.0
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                if _separated(shapes[a], shapes[b]):
                    continue
                volume = overlap_volume(shapes[a], shapes[b])
                worst = max(worst, volume)
                if volume > OVERLAP_NOISE_MM3:
                    rows.append({"a": a, "b": b, "volume_mm3": volume})
        if rows:
            ok = False
        fractions[f"{fraction:.2f}"] = {
            "worst_overlap_mm3": worst,
            "overlaps": rows,
            "ok": not rows,
        }
    return {
        "ok": ok,
        "noise_threshold_mm3": OVERLAP_NOISE_MM3,
        "fractions": fractions,
    }


def _mass_com(shape, density_g_cm3: float) -> tuple[float, tuple[float, float, float]]:
    volume_mm3 = float(shape.volume)
    mass_kg = volume_mm3 * density_g_cm3 * 1e-6
    com = shape.center(CenterOf.MASS)
    return mass_kg, (com.X, com.Y, com.Z)


def _group_mass_com(shapes, density_g_cm3: float) -> tuple[float, tuple[float, float, float]]:
    total = 0.0
    moment = [0.0, 0.0, 0.0]
    for shape in shapes:
        mass, com = _mass_com(shape, density_g_cm3)
        total += mass
        for i in range(3):
            moment[i] += mass * com[i]
    return total, tuple(m / total for m in moment)


def bearing_direction() -> dict:
    """The clip tooth pushes down; gravity also pulls down, so it carries no downward load."""
    tooth_normal = (0.0, 0.0, -1.0)  # the tooth sits above the rib and pushes down
    gravity_load = (0.0, 0.0, -1.0)
    return {
        "tooth_underside_z_mm": CLIP_TOOTH_UNDERSIDE_Z,
        "rib_top_z_mm": CLIP_RIB_TOP_Z,
        "gap_mm": CLIP_TOOTH_UNDERSIDE_Z - CLIP_RIB_TOP_Z,
        "retention_normal_z": -1.0,
        "carries_gravity_downward": bearing_carries(gravity_load, tooth_normal),
        "conclusion": "retention_only_+Z; a downward load separates the rib from the tooth",
        "limitation": "a support polygon cannot convert upward retention into downward bearing",
    }


def support_margins(p: Params) -> dict:
    density = p.material.density_g_cm3
    g = 9.80665
    static = static_solids(p, linkage_from(p), DEFAULT_GAP)
    body_shapes = [static["body"], static["shim_04_a"], static["shim_04_b"]]
    body_mass, body_com = _group_mass_com(body_shapes, density)
    hanging_mass, hanging_com = _group_mass_com(body_shapes + [static["lip"]], density)
    rows = {}
    for name, mass, com in (("body", body_mass, body_com), ("hanging_group", hanging_mass, hanging_com)):
        margin: SupportMargin = support_margin(
            (com[0], com[1]), CLIP_PATCHES_MM, mass * g,
        )
        rows[name] = {
            "mass_kg": mass,
            "weight_n": mass * g,
            "com_mm": com,
            "hull_area_mm2": margin.hull_area_mm2,
            "strip_width_mm": margin.strip_width_mm,
            "com_inside": margin.com_inside,
            "com_margin_mm": margin.com_margin_mm,
            "gravity_moment_nm": margin.gravity_moment_nm,
        }
    return {
        "patches_mm": [[list(pt) for pt in patch] for patch in CLIP_PATCHES_MM],
        "groups": rows,
        "limitation": "static bearing only; the support polygon is not a downward seat",
    }


def _tilted_packets(p: Params, n: int) -> list:
    """Packets 1..n at the derived 1.0368 degree seat, with the 1 um seating clearance."""
    blade_front_z = p.separator.gap + 2.4   # lip blade top (z=8.15)
    blade_rear_x = p.packet.length / 2.0 - 2.0  # blade rear edge (x=80.5)
    rear_x = -p.packet.length / 2.0
    rear_z = p.packet.height
    angle = math.atan2(blade_front_z - rear_z, blade_rear_x - rear_x)
    deg = math.degrees(angle)
    base = Pos(0.0, 0.0, 0.0) * packet(p)
    bottom = base
    tilt = Pos(rear_x, 0.0, rear_z) * Rot(0.0, -deg, 0.0) * Pos(-rear_x, 0.0, 0.0) * base
    normal = (-math.sin(angle), 0.0, math.cos(angle))
    clearance = Pos(
        normal[0] * SEAT_CLEARANCE_MM, 0.0, normal[2] * SEAT_CLEARANCE_MM,
    )
    packets = [bottom]
    second = clearance * tilt
    packets.append(second)
    for k in range(1, n - 1):
        packets.append(Pos(k * p.packet.height * normal[0], 0.0,
                           k * p.packet.height * normal[2]) * second)
    return packets


def tilted_seat_inventory(p: Params, counts=(10, 25)) -> dict:
    link = linkage_from(p)
    tube = _tube(p, link)
    static = static_solids(p, link, DEFAULT_GAP)
    installed = [static["body"], static["lip"], static["chassis"], static["spring_seat"],
                 static["shim_04_a"], static["shim_04_b"]]
    rows = {}
    for n in counts:
        packets = _tilted_packets(p, n)
        max_z = max(pk.bounding_box().max.Z for pk in packets)
        top = packets[-1].bounding_box()
        overlaps = []
        for index, pk in enumerate(packets[1:], start=2):
            for name, shape in zip(
                ("body", "lip", "chassis", "spring_seat", "shim_04_a", "shim_04_b"),
                installed,
            ):
                if _separated(pk, shape):
                    continue
                volume = overlap_volume(pk, shape)
                if volume > OVERLAP_NOISE_MM3:
                    overlaps.append({"packet": index, "part": name, "volume_mm3": volume})
        angle = math.atan2(
            (p.separator.gap + 2.4) - p.packet.height,
            (p.packet.length / 2.0 - 2.0) + p.packet.length / 2.0,
        )
        rows[str(n)] = {
            "tilt_deg": math.degrees(angle),
            "max_z_mm": max_z,
            "top_rear_x_mm": top.min.X,
            "back_wall_gap_mm": top.min.X - tube["x0"],
            "overlaps": overlaps,
            "ok": not overlaps,
        }
    return {
        "ok": all(row["ok"] for row in rows.values()),
        "seating_clearance_mm": SEAT_CLEARANCE_MM,
        "counts": rows,
        "note": "read-only static reproduction; it authorizes no loaded scene or run",
    }


def static_preflight(p: Params) -> dict:
    """Everything in this module, in one JSON-safe record."""
    return {
        "bearing": bearing_direction(),
        "support": support_margins(p),
        "exact_overlap": exact_overlap_inventory(p),
        "tilted_seat": tilted_seat_inventory(p),
        "resets": [
            {
                "fraction": state.fraction,
                "crank_phi_rad": state.crank_phi_rad,
                "rod_x_m": state.rod_x_m,
                "pusher_x_m": state.pusher_x_m,
                "pusher_displacement_mm": state.pusher_x_m * 1000.0,
                "button_travel_mm": state.button_travel_mm,
                "face_x_mm": state.face_x_mm,
            }
            for state in (reset_state(p, f) for f in RESET_FRACTIONS)
        ],
    }
