"""Compiled-scene audits: CAD-derived resets, critical clearances and initial validity.

Two independent measurements are kept apart, as the approved plan requires:

* **exact CAD overlap** of the installed solids at each button fraction (``support.py``);
* **collider penetration** of the compiled scene after the same reset.

The reset audit derives every coordinate from ``linkage_from``/``phi_for_button_fraction``/
``pose_at_phi`` and compares the compiled body transforms with the same CAD pose. The
clearance audit compares a collider-to-collider distance with the exact-CAD distance for the
same declared feature pair, on the compiled ``data.geom_xpos``/``geom_xmat`` after each
reset. A critical mismatch over 0.02 mm is ``SCENE_INVALID``; it is never a product FAIL.

This module imports MuJoCo lazily through the accepted ``require_mujoco`` helper.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from build123d import Box, Pos

from cadkit.physics import require_mujoco

from projects.pocky.geometry.linkage import (
    BUTTON_Y,
    linkage_from,
    phi_for_button_fraction,
    pose_at_phi,
)
from projects.pocky.geometry.prototype import (
    DEFAULT_GAP,
    compressed_length,
    moving_solids,
    static_solids,
)
from projects.pocky.params import Params
from projects.pocky.physics.assembly import RESET_FRACTIONS, reset_state
from projects.pocky.physics.support import exact_overlap_inventory

CRITICAL_TOL_MM = 0.02
#: Compiled reset tolerances from the approved plan.
CRANK_TOL_RAD = 1.0e-9
TRANSLATION_TOL_M = 1.0e-6
STATION_TOL_M = 1.0e-6
#: The linear-reset negative must miss the CAD pusher station by at least this much.
QUARTER_STROKE_NEGATIVE_M = 1.367e-3
#: A collider intrusion below this is contact noise, not a scene defect.
PENETRATION_TOL_M = 1.0e-6

RESET_JOINTS = ("crank_phi", "rod_x", "pusher_x")


@dataclass(frozen=True)
class CriticalPair:
    pair_id: str
    part_a: str
    part_b: str
    body_a: str
    body_b: str
    prefixes_a: tuple[str, ...]
    prefixes_b: tuple[str, ...]
    window: tuple[float, float, float, float, float, float] | str
    expected_cad_mm: float | None
    fractions: tuple[float, ...] = RESET_FRACTIONS
    note: str = ""


PAIRS: tuple[CriticalPair, ...] = (
    CriticalPair(
        "body_pusher_floor", "body", "pusher", "body", "pusher",
        ("floor_",), ("carriage_", "pusher_cap_"), "pusher_carriage",
        0.40, note="body floor underside to pusher carriage top",
    ),
    CriticalPair(
        "body_chassis_base", "body", "chassis", "body", "chassis",
        ("floor_",), ("boss_",), (-85.0, -71.0, -15.0, -1.0, -12.0, -2.0),
        9.20, note="body floor underside to the chassis pivot boss top (highest surface under the body)",
    ),
    CriticalPair(
        "body_chassis_clip", "body", "chassis", "body", "chassis",
        ("rib_n",), ("hook_tooth_n", "hook_post_n"), (60.0, 74.0, 32.0, 38.0, -1.0, 1.0),
        0.05, note="clip tooth underside to body rib top",
    ),
    CriticalPair(
        "lip_body_tooth_n", "lip", "body", "lip", "body",
        ("tooth_n",), ("bar_n",), (83.0, 93.0, 30.0, 37.0, 10.0, 17.0),
        0.15, note="lip hook tooth to body bar",
    ),
    CriticalPair(
        "lip_body_tooth_s", "lip", "body", "lip", "body",
        ("tooth_s",), ("bar_s",), (83.0, 93.0, -37.0, -30.0, 10.0, 17.0),
        0.15, note="lip hook tooth to body bar",
    ),
    CriticalPair(
        "lip_shim_n", "lip", "shim_04_a", "lip", "body",
        ("foot_n",), ("shim_04_a",), (87.0, 96.0, 29.0, 36.0, 4.8, 9.0),
        0.05, note="lip foot to installed shim",
    ),
    CriticalPair(
        "lip_shim_s", "lip", "shim_04_b", "lip", "body",
        ("foot_s",), ("shim_04_b",), (87.0, 96.0, -36.0, -29.0, 4.8, 9.0),
        0.05, note="lip foot to installed shim",
    ),
    CriticalPair(
        "crank_pusher_peg", "peg_pusher", "pusher", "crank", "pusher",
        ("peg_pusher_",), ("carriage_", "pusher_cap_"), "peg_pusher_head",
        0.20, note="pusher peg head to carriage top",
    ),
    CriticalPair(
        "rod_crank_slot", "peg_button", "crank", "rod", "crank",
        ("peg_button_shaft",), ("bar_n", "bar_s"), "peg_button_window",
        0.30, note="button peg shaft to crank slot wall",
    ),
    CriticalPair(
        "body_pusher_bullnose_contact", "body", "pusher", "body", "pusher",
        ("floor_",), ("bullnose",), "bullnose_contact",
        None, note=("bullnose underside to body floor top: the plan's 0.027 mm is this "
                    "tangency; the measured CAD distance is the reference"),
    ),
    CriticalPair(
        "body_pusher_backwall_notch", "body", "pusher", "body", "pusher",
        ("back_upper",), ("bullnose", "neck_"), (-88.0, -84.0, -3.0, 3.0, 3.0, 5.0),
        None, fractions=(0.0,), note=("informational: back wall above the notch, not the "
                                      "plan's bullnose/floor tangency"),
    ),
    CriticalPair(
        "body_crank_relief", "body", "peg_pusher", "body", "crank",
        ("floor_north_relief_", "floor_relief_skin"), ("peg_pusher_head",), "peg_pusher_head",
        0.19, fractions=(1.0,), note="f=1 pusher peg head to local floor relief ceiling",
    ),
    CriticalPair(
        "lip_rod_head", "lip", "rod", "lip", "rod",
        ("rail_s",), ("head_upper",), (88.0, 107.0, -40.0, -34.0, 11.0, 15.0),
        0.30, fractions=(1.0,), note="f=1 lip rail to rod thumb-pad head",
    ),
)


def _joint_index(mujoco, model, name: str) -> int:
    joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
    if joint_id < 0:
        raise KeyError(f"compiled scene has no joint {name!r}")
    return joint_id


def apply_reset(mujoco, model, data, coordinates: dict[str, float]) -> None:
    """Reset every coordinate, then write only the declared joint positions."""
    mujoco.mj_resetData(model, data)
    for name, value in coordinates.items():
        joint_id = _joint_index(mujoco, model, name)
        qadr = int(model.jnt_qposadr[joint_id])
        data.qpos[qadr] = float(value)
    mujoco.mj_forward(model, data)


def _quat_matrix(quat) -> np.ndarray:
    w, x, y, z = (float(v) for v in quat)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def _world_point(data, body_id: int, local_m) -> np.ndarray:
    rot = _quat_matrix(data.xquat[body_id])
    return np.asarray(data.xpos[body_id], dtype=float) + rot @ np.asarray(local_m, dtype=float)


def _z_angle(quat) -> float:
    w, _, _, z = (float(v) for v in quat)
    return 2.0 * math.atan2(z, w)


def _part_shapes(p: Params, fraction: float) -> dict[str, object]:
    link = linkage_from(p)
    pose = pose_at_phi(link, phi_for_button_fraction(link, fraction))
    shapes = dict(static_solids(p, link, DEFAULT_GAP))
    shapes.update(moving_solids(p, link, pose, compressed_length(pose.button_travel)))
    shapes.pop("dummy", None)
    return shapes


def _pusher_window(state) -> tuple[float, float, float, float, float, float]:
    pin = state.pusher_pin_x_mm
    return (pin - 9.0, pin + 21.0, -9.0, 33.0, -3.5, -2.0)


def _peg_window(p, state, z0: float, z1: float,
                peg: str = "pusher") -> tuple[float, float, float, float, float, float]:
    link = linkage_from(p)
    pose = pose_at_phi(link, phi_for_button_fraction(link, state.fraction))
    if peg == "button":
        cx, cy = pose.button_x, pose.button_y
    else:
        cx, cy = pose.pusher_pin_x, pose.pusher_pin_y
    return (cx - 5.0, cx + 5.0, cy - 5.0, cy + 5.0, z0, z1)


def _window_for(pair: CriticalPair, p: Params, state) -> tuple[float, ...]:
    if pair.window == "pusher_carriage":
        return _pusher_window(state)
    if pair.window == "bullnose_contact":
        return (state.face_x_mm - 4.2, state.face_x_mm, 3.5, 20.0, -0.2, 0.2)
    if pair.window == "peg_pusher_head":
        return _peg_window(p, state, -3.2, 0.0)
    if pair.window == "peg_button_window":
        return _peg_window(p, state, -11.0, -7.3, peg="button")
    return pair.window


def _crop(shape, window):
    x0, x1, y0, y1, z0, z1 = (float(v) for v in window)
    box = Pos((x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0) * Box(
        x1 - x0, y1 - y0, z1 - z0)
    common = shape.intersect(box)
    if common is None:
        return None
    shapes = common if isinstance(common, (list, tuple)) else [common]
    shapes = [s for s in shapes if float(getattr(s, "volume", 0.0)) > 0.0]
    if not shapes:
        return None
    if len(shapes) == 1:
        return shapes[0]
    acc = shapes[0]
    for other in shapes[1:]:
        acc = acc + other
    return acc


def _cad_distance(shape_a, shape_b, window):
    crop_a = _crop(shape_a, window)
    crop_b = _crop(shape_b, window)
    if crop_a is None or crop_b is None:
        return None
    try:
        return float(crop_a.distance_to(crop_b))
    except Exception:
        return None


def _geom_ids(mujoco, model, body_name: str, prefixes: tuple[str, ...]) -> list[int]:
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name)
    if body_id < 0:
        raise KeyError(f"compiled scene has no body {body_name!r}")
    out = []
    for gid in range(model.ngeom):
        if int(model.geom_bodyid[gid]) != body_id:
            continue
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, gid) or ""
        if any(name.startswith(prefix) for prefix in prefixes):
            out.append(gid)
    return out


def _collider_distance(mujoco, model, data, ids_a: list[int], ids_b: list[int],
                       max_m: float = 1.0) -> float | None:
    best = None
    fromto = np.zeros(6, dtype=float)
    for g1 in ids_a:
        for g2 in ids_b:
            try:
                d = float(mujoco.mj_geomDistance(model, data, g1, g2, max_m,
                                                 fromto))
            except Exception:
                continue
            if not math.isfinite(d):
                continue
            if best is None or d < best:
                best = d
    return best


def _contact_penetration(mujoco, model, data) -> dict:
    worst = 0.0
    pairs = []
    geom_name = {
        gid: (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, gid) or "")
        for gid in range(model.ngeom)
    }
    for contact in data.contact[:data.ncon]:
        dist = float(contact.dist)
        if dist < worst:
            worst = dist
        if dist < -PENETRATION_TOL_M:
            pairs.append({
                "geom1": geom_name.get(int(contact.geom1), "?"),
                "geom2": geom_name.get(int(contact.geom2), "?"),
                "dist_m": dist,
            })
    pairs.sort(key=lambda row: row["dist_m"])
    return {"worst_m": worst, "penetrations": pairs, "ok": not pairs}


# --------------------------------------------------------------------------- compiled reset
def compiled_reset_audit(mujoco, model, p: Params,
                         injections: dict[float, dict[str, float]] | None = None) -> dict:
    """Compile/reset at all five fractions and compare the transforms with the CAD helpers.

    ``injections`` overrides a joint coordinate for a named fraction (negative tests). The
    reported ``errors`` are always against the CAD helper pose, never against the injected
    value, so a wrong reset is visible by construction.
    """
    data = mujoco.MjData(model)
    model.opt.timestep = float(model.opt.timestep)
    body_ids = {
        name: mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
        for name in ("body", "lip", "chassis", "crank", "rod", "pusher", "floor_world")
    }
    for name, bid in body_ids.items():
        if bid < 0:
            raise KeyError(f"compiled scene has no body {name!r}")

    injections = injections or {}
    base = {"crank_phi": 0.0, "rod_x": 0.0, "pusher_x": 0.0}
    apply_reset(mujoco, model, data, base)
    x0 = {name: np.array(data.xpos[bid], dtype=float) for name, bid in body_ids.items()}

    link = linkage_from(p)
    rest = pose_at_phi(link, link.phi0)
    peg_local = np.array([rest.pusher_pin_x / 1000.0, rest.pusher_pin_y / 1000.0,
                          0.5 * (link.crank_z0 + link.crank_z1) / 1000.0])
    button_local = np.array([rest.button_x / 1000.0, BUTTON_Y / 1000.0,
                             0.5 * (link.rod_z0 + link.rod_z1) / 1000.0])
    face_local = np.array([rest.face_x / 1000.0, 0.0, 1.0e-3])

    rows = []
    ok = True
    for fraction in RESET_FRACTIONS:
        state = reset_state(p, fraction)
        coordinates = state.joint_coordinates()
        coordinates.update(injections.get(fraction, {}))
        apply_reset(mujoco, model, data, coordinates)

        crank_angle = _z_angle(data.xquat[body_ids["crank"]])
        rod_dx = np.array(data.xpos[body_ids["rod"]], dtype=float) - x0["rod"]
        pusher_dx = np.array(data.xpos[body_ids["pusher"]], dtype=float) - x0["pusher"]

        peg_world = _world_point(data, body_ids["crank"], peg_local)
        button_world = _world_point(data, body_ids["rod"], button_local)
        face_world = _world_point(data, body_ids["pusher"], face_local)

        errors = {
            "crank_rad": abs(crank_angle - state.crank_phi_rad),
            "rod_dx_m": abs(float(rod_dx[0]) - state.rod_x_m),
            "rod_offaxis_m": float(np.max(np.abs(rod_dx[1:]))),
            "pusher_dx_m": abs(float(pusher_dx[0]) - state.pusher_x_m),
            "pusher_offaxis_m": float(np.max(np.abs(pusher_dx[1:]))),
            "peg_station_m": float(np.max(np.abs(
                peg_world - np.array([state.pusher_pin_x_mm, state.pusher_pin_y_mm,
                                      0.5 * (link.crank_z0 + link.crank_z1)]) / 1000.0))),
            "button_station_m": float(np.max(np.abs(
                button_world - np.array([state.button_x_mm, state.button_y_mm,
                                         0.5 * (link.rod_z0 + link.rod_z1)]) / 1000.0))),
            "face_station_m": abs(float(face_world[0]) - state.face_x_mm / 1000.0),
            "pusher_sign_m": abs(float(pusher_dx[0])) if fraction == 0.0 else (
                float(pusher_dx[0]) if state.pusher_x_m > 0 else -float(pusher_dx[0])),
        }
        limits = {
            "crank_rad": CRANK_TOL_RAD,
            "rod_dx_m": TRANSLATION_TOL_M,
            "rod_offaxis_m": TRANSLATION_TOL_M,
            "pusher_dx_m": TRANSLATION_TOL_M,
            "pusher_offaxis_m": TRANSLATION_TOL_M,
            "peg_station_m": STATION_TOL_M,
            "button_station_m": STATION_TOL_M,
            "face_station_m": STATION_TOL_M,
        }
        exceeded = {name: value for name, value in errors.items()
                    if name in limits and value > limits[name]}
        # The sign check is only meaningful for fractions with a nonzero pusher reset.
        sign_bad = fraction > 0.0 and errors["pusher_sign_m"] < 0.0
        row_ok = not exceeded and not sign_bad
        ok = ok and row_ok
        rows.append({
            "fraction": fraction,
            "joint_coordinates": coordinates,
            "crank_phi_rad": crank_angle,
            "crank_phi_expected_rad": state.crank_phi_rad,
            "rod_dx_m": float(rod_dx[0]),
            "rod_x_expected_m": state.rod_x_m,
            "pusher_dx_m": float(pusher_dx[0]),
            "pusher_x_expected_m": state.pusher_x_m,
            "pusher_peg_world_m": peg_world.tolist(),
            "button_peg_world_m": button_world.tolist(),
            "pusher_face_x_m": float(face_world[0]),
            "pusher_face_expected_m": state.face_x_mm / 1000.0,
            "errors": errors,
            "exceeded": exceeded,
            "sign_bad": sign_bad,
            "ok": row_ok,
        })
    return {"ok": ok, "fractions": rows}


def quarter_stroke_negatives(mujoco, model, p: Params) -> dict:
    """Inject the wrong linear pusher resets and the sign flip; both must be rejected."""
    linear = {0.25: {"pusher_x": 0.0125}, 0.75: {"pusher_x": 0.0375}}
    sign_flip = {0.25: {"pusher_x": -0.011132495}, 0.5: {"pusher_x": -0.025},
                 0.75: {"pusher_x": -0.038867505}}
    linear_audit = compiled_reset_audit(mujoco, model, p, injections=linear)
    flips = compiled_reset_audit(mujoco, model, p, injections=sign_flip)
    linear_rows = {row["fraction"]: row for row in linear_audit["fractions"]}
    quarter_error = min(
        linear_rows[0.25]["errors"]["pusher_dx_m"],
        linear_rows[0.75]["errors"]["pusher_dx_m"],
    )
    flip_rows = {row["fraction"]: row for row in flips["fractions"]}
    flip_error = max(row["errors"]["pusher_dx_m"] for row in flip_rows.values())
    return {
        "linear": {
            "audit_ok": linear_audit["ok"],
            "min_pusher_error_m": quarter_error,
            "required_min_m": QUARTER_STROKE_NEGATIVE_M,
            "rejected": not linear_audit["ok"] and quarter_error >= QUARTER_STROKE_NEGATIVE_M,
            "rows": linear_rows,
        },
        "sign_flip": {
            "audit_ok": flips["ok"],
            "max_pusher_error_m": flip_error,
            "rejected": not flips["ok"],
            "rows": flip_rows,
        },
    }


# --------------------------------------------------------------------------- clearance audit
def critical_clearance_audit(mujoco, model, p: Params) -> dict:
    """Collider-vs-CAD clearance for the declared critical pairs at each reset."""
    data = mujoco.MjData(model)
    link = linkage_from(p)
    rows = []
    ok = True
    for fraction in RESET_FRACTIONS:
        state = reset_state(p, fraction)
        apply_reset(mujoco, model, data, state.joint_coordinates())
        shapes = _part_shapes(p, fraction)
        fraction_rows = []
        for pair in PAIRS:
            if fraction not in pair.fractions:
                continue
            window = _window_for(pair, p, state)
            cad = _cad_distance(shapes[pair.part_a], shapes[pair.part_b], window)
            ids_a = _geom_ids(mujoco, model, pair.body_a, pair.prefixes_a)
            ids_b = _geom_ids(mujoco, model, pair.body_b, pair.prefixes_b)
            collider = _collider_distance(mujoco, model, data, ids_a, ids_b)
            difference = None
            pair_ok = True
            if cad is not None and collider is not None:
                difference = abs(collider * 1000.0 - cad)
                pair_ok = difference <= CRITICAL_TOL_MM
            elif collider is None or cad is None:
                pair_ok = False
            ok = ok and pair_ok
            fraction_rows.append({
                "pair": pair.pair_id,
                "part_a": pair.part_a,
                "part_b": pair.part_b,
                "window_mm": list(window),
                "cad_distance_mm": None if cad is None else cad,
                "collider_distance_mm": None if collider is None else collider * 1000.0,
                "difference_mm": difference,
                "expected_cad_mm": pair.expected_cad_mm,
                "tolerance_mm": CRITICAL_TOL_MM,
                "ok": pair_ok,
                "note": pair.note,
            })
        rows.append({
            "fraction": fraction,
            "reset": state.joint_coordinates(),
            "transforms": {
                name: {
                    "xpos_m": np.asarray(data.xpos[mujoco.mj_name2id(
                        model, mujoco.mjtObj.mjOBJ_BODY, name)], dtype=float).tolist(),
                    "xquat": np.asarray(data.xquat[mujoco.mj_name2id(
                        model, mujoco.mjtObj.mjOBJ_BODY, name)], dtype=float).tolist(),
                }
                for name in ("body", "lip", "chassis", "crank", "rod", "pusher")
            },
            "pairs": fraction_rows,
            "ok": all(row["ok"] for row in fraction_rows),
        })
    return {"ok": ok, "tolerance_mm": CRITICAL_TOL_MM, "fractions": rows}


def initial_validity_audit(mujoco, model, p: Params) -> dict:
    """Exact CAD overlap (five fractions) plus compiled collider penetration at each reset."""
    exact = exact_overlap_inventory(p)
    data = mujoco.MjData(model)
    fractions = []
    ok = exact["ok"]
    for fraction in RESET_FRACTIONS:
        state = reset_state(p, fraction)
        apply_reset(mujoco, model, data, state.joint_coordinates())
        penetration = _contact_penetration(mujoco, model, data)
        ok = ok and penetration["ok"]
        fractions.append({
            "fraction": fraction,
            "collider_penetration": penetration,
            "exact_overlap": exact["fractions"][f"{fraction:.2f}"],
        })
    return {
        "ok": ok,
        "verdict": "SCENE_VALID" if ok else "SCENE_INVALID",
        "exact_overlap": exact,
        "fractions": fractions,
        "note": "an initial overlap or critical mismatch is SCENE_INVALID, never a product FAIL",
    }


def compile_scene(p: Params, outdir):
    """Export and compile through the accepted generic exporter."""
    from cadkit.physics.scene import export_scene

    from projects.pocky.physics.assembly import prototype_assembly

    return export_scene(prototype_assembly(p), outdir)
