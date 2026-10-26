"""Pocky M5a-1 assembly tests: inventory, masses, CAD resets and compiled transforms.

Written from the ticket and the CAD helpers, not from the adapter's own answers:

* the five reset states are recomputed from ``linkage_from``/``phi_for_button_fraction``/
  ``pose_at_phi`` and compared with ``reset_state``;
* the compiled scene is exported with ``clearance_audit.compile_scene``, and the crank
  rotation, the rod/pusher translations and the pusher peg station are read from
  ``data.xpos``/``data.xquat`` and rotated in this file;
* the negative resets are the wrong linear 12.5/37.5 mm injection and the sign-flipped
  pusher injection, both of which must fail the cross-check.

Run with the optional physics extra:
``uv run --frozen --extra physics pytest tests/test_pocky_physics_assembly.py -q``.
"""
from __future__ import annotations

import math

import pytest

pytest.importorskip("mujoco", reason="optional physics extra not installed")

from cadkit.physics import require_mujoco  # noqa: E402
from cadkit.physics.schema import AssemblySpec  # noqa: E402
from projects.pocky import PROJECT  # noqa: E402
from projects.pocky.geometry.linkage import (  # noqa: E402
    linkage_from,
    phi_for_button_fraction,
    pose_at_phi,
)
from projects.pocky.geometry.prototype import (  # noqa: E402
    DEFAULT_GAP,
    compressed_length,
    moving_solids,
    static_solids,
)
from projects.pocky.params import load_params  # noqa: E402
from projects.pocky.physics.assembly import (  # noqa: E402
    RESET_FRACTIONS,
    expected_quarter_stroke_mm,
    prototype_assembly,
    reset_state,
)
from projects.pocky.physics.clearance_audit import (  # noqa: E402
    compile_scene,
    compiled_reset_audit,
    quarter_stroke_negatives,
)
from projects.pocky.physics.options import load_options  # noqa: E402
from projects.pocky.physics.support import exact_overlap_inventory  # noqa: E402

#: PETG datasheet density used for every CAD-derived mass (``params.toml``).
DENSITY_G_CM3 = 1.27
#: The approved compiled-reset tolerances.
CRANK_TOL_RAD = 1.0e-9
TRANSLATION_TOL_M = 1.0e-6
STATION_TOL_M = 1.0e-6
#: The ticket's quarter-stroke pusher travel, mm. Not 12.5 / 37.5.
QUARTER_PUSHER_MM = (11.132495, 38.867505)

#: The plan's reset table, at the printed precision. Recomputed below from the helpers.
RESET_TABLE = {
    0.0: (0.0, 0.0, 0.0, 0.0),
    0.25: (-0.242563874, -0.005773503, 0.011132495, 11.132495),
    0.5: (-0.523598776, -0.011547005, 0.025000000, 25.000000),
    0.75: (-0.804633677, -0.017320508, 0.038867505, 38.867505),
    1.0: (-1.047197551, -0.023094011, 0.050000000, 50.000000),
}


# --------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def p():
    return load_params()


@pytest.fixture(scope="module")
def spec(p):
    return prototype_assembly(p)


@pytest.fixture(scope="module")
def compiled(p, tmp_path_factory):
    """The real exported scene: ``compile_scene`` writes and compiles under ``tmp_path``."""
    mujoco = require_mujoco()
    outdir = tmp_path_factory.mktemp("pocky-assembly-scene")
    export = compile_scene(p, outdir)
    assert export.model is not None, "the scene did not compile"
    assert export.scene_xml.is_file()
    return mujoco, export.model, export


# --------------------------------------------------------------------------- helpers
def _part_mass_kg(spec: AssemblySpec, *part_ids: str) -> float:
    wanted = set(part_ids)
    total = 0.0
    seen: set[str] = set()
    for body in spec.bodies:
        for part in body.parts:
            if part.part_id in wanted:
                assert part.shape is not None
                total += float(part.shape.volume) * DENSITY_G_CM3 * 1e-6
                seen.add(part.part_id)
    assert seen == wanted, f"missing parts {sorted(wanted - seen)}"
    return total


def _body_id(mujoco, model, name: str) -> int:
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
    assert body_id >= 0, f"compiled scene has no body {name!r}"
    return body_id


def _joint_id(mujoco, model, name: str) -> int:
    joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
    assert joint_id >= 0, f"compiled scene has no joint {name!r}"
    return joint_id


def _write_joints(mujoco, model, data, coordinates: dict[str, float]) -> None:
    """Write initial joint coordinates; the test's own copy of the reset mechanism."""
    mujoco.mj_resetData(model, data)
    for name, value in coordinates.items():
        joint_id = _joint_id(mujoco, model, name)
        data.qpos[int(model.jnt_qposadr[joint_id])] = float(value)
    mujoco.mj_forward(model, data)


def _rotate(quat, vector) -> tuple[float, float, float]:
    """Rotate ``vector`` by the ``w x y z`` unit quaternion, without cadkit's matrix."""
    w, x, y, z = (float(v) for v in quat)
    vx, vy, vz = (float(v) for v in vector)
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (
        vx + w * tx + (y * tz - z * ty),
        vy + w * ty + (z * tx - x * tz),
        vz + w * tz + (x * ty - y * tx),
    )


def _angle_about_z(quat) -> float:
    """Rotation angle about +Z from the compiled quaternion (zero for the CAD crank)."""
    return 2.0 * math.atan2(float(quat[3]), float(quat[0]))


# --------------------------------------------------------------------------- inventory
def test_assembly_builds_and_inventory_is_each_installed_part_once(p, spec):
    link = linkage_from(p)
    rest = pose_at_phi(link, link.phi0)
    expected_static = set(static_solids(p, link, DEFAULT_GAP)) - {"dummy"}
    expected_moving = set(moving_solids(p, link, rest, compressed_length(0.0)))

    part_ids = spec.part_ids()
    assert len(part_ids) == len(set(part_ids)), "a part appears in more than one body"
    assert "dummy" not in part_ids, "the bench print dummy is not an installed part"
    assert "shim_08" not in part_ids, "the parked 0.8 mm shim is not installed"
    assert set(part_ids) - {"floor"} == expected_static | expected_moving

    assert [body.body_id for body in spec.bodies] == [
        "body", "lip", "chassis", "crank", "rod", "pusher", "floor_world",
    ]
    owned = {body.body_id: {part.part_id for part in body.parts} for body in spec.bodies}
    assert owned["body"] == {"body", "shim_04_a", "shim_04_b"}
    assert owned["lip"] == {"lip"}
    assert owned["chassis"] == {"chassis", "spring_seat", "peg_pivot"}
    assert owned["crank"] == {"crank", "peg_pusher"}
    assert owned["rod"] == {"rod", "peg_button", "spring"}
    assert owned["pusher"] == {"pusher"}
    assert owned["floor_world"] == {"floor"}

    # The welded ownership is declared in the plan: the body owns both installed shims,
    # the chassis owns the seat and the pivot peg, the crank its pusher peg, the rod its
    # button peg and the spring visual/mass.
    body = next(b for b in spec.bodies if b.body_id == "body")
    assert body.fixed_to_world is False
    for body_id in ("chassis", "crank", "rod", "pusher"):
        assert next(b for b in spec.bodies if b.body_id == body_id).fixed_to_world is False


def test_masses_come_from_cad_volume_times_petg_density(p, spec):
    assert p.material.density_g_cm3 == pytest.approx(DENSITY_G_CM3)

    # Individual CAD parts, kg. The rod and crank figures include their welded pegs and
    # the rod its spring visual/mass.
    assert _part_mass_kg(spec, "body") == pytest.approx(0.13943, abs=1e-4)
    assert _part_mass_kg(spec, "chassis") == pytest.approx(0.10257, abs=1e-4)
    assert _part_mass_kg(spec, "lip") == pytest.approx(0.00643, abs=1e-4)
    assert _part_mass_kg(spec, "rod", "peg_button", "spring") == pytest.approx(
        0.01831, abs=1e-4)
    assert _part_mass_kg(spec, "crank", "peg_pusher") == pytest.approx(0.00411, abs=1e-4)
    assert _part_mass_kg(spec, "pusher") == pytest.approx(0.00876, abs=1e-4)

    # The ticket's 0.00087 kg figure is the plan's "pegs" line: the pivot, pusher and
    # button pegs together. The pivot peg alone is 0.00037 kg (reported, not a defect:
    # the plan table's 0.873 g is the three-peg total).
    assert _part_mass_kg(spec, "peg_pivot", "peg_pusher", "peg_button") == pytest.approx(
        0.00087, abs=1e-4)
    assert _part_mass_kg(spec, "peg_pivot") == pytest.approx(0.00037, abs=1e-4)

    floor = next(body for body in spec.bodies if body.body_id == "floor_world")
    assert floor.fixed_to_world is True
    assert floor.fixture == "analytic_fixture"
    floor_mass = _part_mass_kg(spec, "floor")
    assert floor_mass == pytest.approx(0.2032, abs=1e-6)

    product = sum(
        float(part.shape.volume)
        for body in spec.bodies if body.body_id != "floor_world"
        for part in body.parts
    ) * DENSITY_G_CM3 * 1e-6
    assert product * 1000.0 == pytest.approx(280.36, abs=0.1)


# --------------------------------------------------------------------------- CAD resets
def test_reset_states_are_derived_from_the_cad_helpers(p):
    link = linkage_from(p)
    rest = pose_at_phi(link, link.phi0)
    assert tuple(RESET_FRACTIONS) == (0.0, 0.25, 0.5, 0.75, 1.0)

    for fraction in RESET_FRACTIONS:
        phi = phi_for_button_fraction(link, fraction)
        pose = pose_at_phi(link, phi)
        state = reset_state(p, fraction)

        assert state.fraction == fraction
        assert state.phi_rad == pytest.approx(phi, abs=1e-12)
        assert state.crank_phi_rad == pytest.approx(pose.phi - link.phi0, abs=1e-12)
        assert state.rod_x_m == pytest.approx(-pose.button_travel / 1000.0, abs=1e-12)
        assert state.pusher_x_m == pytest.approx(
            (pose.face_x - rest.face_x) / 1000.0, abs=1e-12)
        assert state.button_travel_mm == pytest.approx(pose.button_travel, abs=1e-12)
        assert state.face_x_mm == pytest.approx(pose.face_x, abs=1e-12)
        assert state.pusher_pin_x_mm == pytest.approx(pose.pusher_pin_x, abs=1e-12)
        assert state.pusher_pin_y_mm == pytest.approx(pose.pusher_pin_y, abs=1e-12)

        crank_phi, rod_x, pusher_x, pusher_mm = RESET_TABLE[fraction]
        assert state.crank_phi_rad == pytest.approx(crank_phi, abs=1e-9)
        assert state.rod_x_m == pytest.approx(rod_x, abs=1e-9)
        assert state.pusher_x_m == pytest.approx(pusher_x, abs=1e-9)
        # The table's mm column is printed to six decimals, unlike the rad/m columns.
        assert state.pusher_x_m * 1000.0 == pytest.approx(pusher_mm, abs=1e-6)

        assert set(state.joint_coordinates()) == {"crank_phi", "rod_x", "pusher_x"}

    # Endpoints are the CAD stroke and the installed preload, not an interpolation.
    full = reset_state(p, 1.0)
    assert full.rod_x_m == pytest.approx(-link.button_stroke / 1000.0, abs=1e-12)
    assert full.pusher_x_m == pytest.approx(link.stroke / 1000.0, abs=1e-12)
    assert reset_state(p, 0.0).crank_phi_rad == 0.0


def test_quarter_stroke_pusher_travel_is_not_linear(p):
    quarter, three_quarter = expected_quarter_stroke_mm(p)
    assert quarter == pytest.approx(QUARTER_PUSHER_MM[0], abs=1e-6)
    assert three_quarter == pytest.approx(QUARTER_PUSHER_MM[1], abs=1e-6)
    assert reset_state(p, 0.25).pusher_x_m * 1000.0 == pytest.approx(quarter, abs=1e-12)
    assert reset_state(p, 0.75).pusher_x_m * 1000.0 == pytest.approx(
        three_quarter, abs=1e-12)

    # The wrong linear reset is 12.5 / 37.5 mm. Its exact quarter-stroke error is
    # 1.367504905... mm, which is 9.4e-8 mm below the printed 1.367505: keep 1.3675.
    linear_error_25 = abs(12.5 - quarter)
    linear_error_75 = abs(37.5 - three_quarter)
    assert linear_error_25 >= 1.3675
    assert linear_error_75 >= 1.3675
    assert linear_error_25 / 1000.0 == pytest.approx(
        0.0125 - 0.011132495094369276, abs=1e-12)
    assert linear_error_75 / 1000.0 == pytest.approx(
        0.03886750490563074 - 0.0375, abs=1e-12)


# --------------------------------------------------------------------------- compiled
def test_compiled_transforms_match_the_cad_pose_at_all_five_fractions(p, compiled):
    mujoco, model, _ = compiled
    data = mujoco.MjData(model)
    link = linkage_from(p)
    rest = pose_at_phi(link, link.phi0)

    crank = _body_id(mujoco, model, "crank")
    rod = _body_id(mujoco, model, "rod")
    pusher = _body_id(mujoco, model, "pusher")
    _write_joints(mujoco, model, data, {"crank_phi": 0.0, "rod_x": 0.0, "pusher_x": 0.0})
    base = {
        "rod": [float(v) for v in data.xpos[rod]],
        "pusher": [float(v) for v in data.xpos[pusher]],
    }

    peg_local = (
        rest.pusher_pin_x / 1000.0,
        rest.pusher_pin_y / 1000.0,
        0.5 * (link.crank_z0 + link.crank_z1) / 1000.0,
    )
    face_local = (rest.face_x / 1000.0, 0.0, 1.0e-3)

    for fraction in RESET_FRACTIONS:
        phi = phi_for_button_fraction(link, fraction)
        pose = pose_at_phi(link, phi)
        crank_phi = pose.phi - link.phi0
        rod_x = -pose.button_travel / 1000.0
        pusher_x = (pose.face_x - rest.face_x) / 1000.0

        _write_joints(mujoco, model, data, {
            "crank_phi": crank_phi, "rod_x": rod_x, "pusher_x": pusher_x,
        })

        assert _angle_about_z(data.xquat[crank]) == pytest.approx(
            crank_phi, abs=CRANK_TOL_RAD)

        rod_delta = [float(data.xpos[rod][i]) - base["rod"][i] for i in range(3)]
        assert rod_delta[0] == pytest.approx(rod_x, abs=TRANSLATION_TOL_M)
        assert max(abs(v) for v in rod_delta[1:]) <= TRANSLATION_TOL_M

        pusher_delta = [float(data.xpos[pusher][i]) - base["pusher"][i] for i in range(3)]
        assert pusher_delta[0] == pytest.approx(pusher_x, abs=TRANSLATION_TOL_M)
        assert max(abs(v) for v in pusher_delta[1:]) <= TRANSLATION_TOL_M
        if fraction > 0.0:
            assert pusher_delta[0] > 0.0, "the pusher reset must travel +X"

        peg_offset = _rotate(data.xquat[crank], peg_local)
        peg_world = [float(data.xpos[crank][i]) + peg_offset[i] for i in range(3)]
        assert peg_world[0] == pytest.approx(pose.pusher_pin_x / 1000.0, abs=STATION_TOL_M)
        assert peg_world[1] == pytest.approx(pose.pusher_pin_y / 1000.0, abs=STATION_TOL_M)
        assert peg_world[2] == pytest.approx(peg_local[2], abs=STATION_TOL_M)

        face_offset = _rotate(data.xquat[pusher], face_local)
        face_x = float(data.xpos[pusher][0]) + face_offset[0]
        assert face_x == pytest.approx(pose.face_x / 1000.0, abs=STATION_TOL_M)


def test_compiled_reset_audit_passes_at_all_five_fractions(p, compiled):
    mujoco, model, _ = compiled
    audit = compiled_reset_audit(mujoco, model, p)
    assert audit["ok"], [row for row in audit["fractions"] if not row["ok"]]
    rows = {row["fraction"]: row for row in audit["fractions"]}
    assert set(rows) == set(RESET_FRACTIONS)

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
    for fraction, row in rows.items():
        assert row["ok"], (fraction, row["errors"], row["exceeded"])
        assert row["exceeded"] == {}
        assert row["sign_bad"] is False
        state = reset_state(p, fraction)
        assert row["joint_coordinates"] == pytest.approx(
            state.joint_coordinates(), abs=1e-12)
        for key, limit in limits.items():
            assert row["errors"][key] <= limit, (fraction, key, row["errors"][key])
        assert row["pusher_x_expected_m"] == pytest.approx(state.pusher_x_m, abs=1e-12)


def test_linear_and_sign_flipped_resets_are_rejected(p, compiled):
    mujoco, model, _ = compiled
    negatives = quarter_stroke_negatives(mujoco, model, p)

    linear = negatives["linear"]
    assert linear["rejected"] is True
    assert linear["audit_ok"] is False
    exact_error = 0.0125 - 0.011132495094369276
    assert linear["min_pusher_error_m"] == pytest.approx(exact_error, abs=1e-12)
    assert linear["min_pusher_error_m"] >= 1.367e-3
    for fraction in (0.25, 0.75):
        row = linear["rows"][fraction]
        assert row["errors"]["pusher_dx_m"] == pytest.approx(exact_error, abs=1e-12)
        assert row["ok"] is False
    # Only the injected fractions fail: the rejection is the wrong reset, not the scene.
    for fraction in (0.0, 0.5, 1.0):
        assert linear["rows"][fraction]["ok"] is True

    sign_flip = negatives["sign_flip"]
    assert sign_flip["rejected"] is True
    assert sign_flip["audit_ok"] is False
    worst = 2.0 * 0.03886750490563074
    assert sign_flip["max_pusher_error_m"] == pytest.approx(worst, abs=1e-9)
    for fraction in (0.25, 0.5, 0.75):
        row = sign_flip["rows"][fraction]
        assert row["errors"]["pusher_dx_m"] > 0.02
        assert row["ok"] is False


# --------------------------------------------------------------------------- restraint
def test_only_the_analytic_floor_is_fixed_and_there_are_no_actuators(spec, compiled):
    mujoco, model, _ = compiled
    fixed = [body.body_id for body in spec.bodies if body.fixed_to_world]
    assert fixed == ["floor_world"]
    floor = next(body for body in spec.bodies if body.body_id == "floor_world")
    assert floor.fixture == "analytic_fixture"

    floor_part = floor.parts[0]
    assert float(floor_part.shape.bounding_box().max.Z) == pytest.approx(-19.2, abs=1e-9)
    collider = floor_part.colliders[0]
    assert collider.pos_mm[2] + collider.size_mm[2] == pytest.approx(-19.2, abs=1e-9)

    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "floor_box")
    assert geom_id >= 0
    top_m = float(data.geom_xpos[geom_id][2]) + float(model.geom_size[geom_id][2])
    assert top_m == pytest.approx(-0.0192, abs=1e-9)

    names = [body.body_id for body in spec.bodies]
    compiled_ids = {name: _body_id(mujoco, model, name) for name in names}
    fixed_compiled = [
        name for name, body_id in compiled_ids.items()
        if int(model.body_jntnum[body_id]) == 0 and int(model.body_parentid[body_id]) == 0
    ]
    assert fixed_compiled == ["floor_world"]

    assert spec.actuators == ()
    assert int(model.nu) == 0


def test_reset_writes_only_the_three_declared_joints(p, compiled):
    mujoco, model, _ = compiled
    kinds = {
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, joint): int(model.jnt_type[joint])
        for joint in range(model.njnt)
    }
    # MuJoCo joint type 0 is a free joint; 2 is slide, 3 is hinge.
    non_free = {name for name, kind in kinds.items() if kind != 0}
    free = {name for name, kind in kinds.items() if kind == 0}
    assert non_free == {"crank_phi", "rod_x", "pusher_x"}
    assert free == {"body_free", "lip_free", "chassis_free"}

    for fraction in RESET_FRACTIONS:
        assert set(reset_state(p, fraction).joint_coordinates()) == non_free


# --------------------------------------------------------------------------- spring/options
def test_spring_is_the_declared_rod_slide(p, spec):
    rod = next(body for body in spec.bodies if body.body_id == "rod")
    assert rod.parent == "chassis"
    assert rod.joint is not None
    assert rod.joint.joint_id == "rod_x"
    assert rod.joint.kind == "slide"
    assert rod.joint.axis == (1.0, 0.0, 0.0)
    assert rod.joint.spring is not None
    assert rod.joint.spring.stiffness == pytest.approx(500.0)
    assert rod.joint.spring.reference == pytest.approx(0.003)
    lo, hi = rod.joint.limits
    assert lo <= reset_state(p, 1.0).rod_x_m <= hi


@pytest.mark.parametrize("rate", [200.0, 500.0, 1000.0])
def test_options_accept_the_approved_spring_rates(p, rate):
    options = load_options({"spring_stiffness_n_m": rate})
    assert options.spring_stiffness_n_m == pytest.approx(rate)
    spec = prototype_assembly(p, spring_stiffness_n_m=rate)
    rod = next(body for body in spec.bodies if body.body_id == "rod")
    assert rod.joint.spring.stiffness == pytest.approx(rate)


@pytest.mark.parametrize("timestep_s", [1.0e-3, 5.0e-4])
def test_options_accept_the_approved_timesteps(p, timestep_s):
    options = load_options({"timestep_s": timestep_s})
    assert options.timestep_s == pytest.approx(timestep_s)
    spec = prototype_assembly(p, timestep_s=timestep_s)
    assert spec.timestep_s == pytest.approx(timestep_s)


@pytest.mark.parametrize("key", [
    "capacity",
    "contact_timeconst_s",
    "stop_timeconst_s",
    "friction",
    "button_fraction",
    "unknown_option",
])
def test_options_reject_unsupported_keys(key):
    with pytest.raises(ValueError):
        load_options({key: 1})


@pytest.mark.parametrize("count", range(11))
def test_options_accept_zero_to_capacity_packets(count):
    assert load_options({"packets": count}).packets == count


@pytest.mark.parametrize("table", [
    {"packets": 11},
    {"packets": 25},
    {"packets": -1},
    {"packets": True},
    {"packets": 1.0},
    {"packet_mass_kg": 0.007},
    {"packets": 0, "packet_mass_kg": 0.007},
    {"packets": 1, "packet_mass_kg": 0.0039},
    {"packets": 1, "packet_mass_kg": 0.0101},
    {"packets": 1, "packet_mass_kg": float("nan")},
])
def test_options_reject_unsupported_packet_choices(table):
    with pytest.raises(ValueError):
        load_options(table)


@pytest.mark.parametrize("mass", [0.004, 0.007, 0.010])
def test_options_accept_packet_mass_within_range_with_one_packet(mass):
    assert load_options({"packets": 1, "packet_mass_kg": mass}).packet_mass_kg == mass


@pytest.mark.parametrize("table", [
    {"spring_stiffness_n_m": 0.0},
    {"spring_stiffness_n_m": -200.0},
    {"spring_stiffness_n_m": 300.0},
    {"timestep_s": 0.0},
    {"timestep_s": 2.0e-3},
    {"timestep_s": 1.0},
])
def test_options_reject_out_of_range_values(table):
    with pytest.raises(ValueError):
        load_options(table)


@pytest.mark.parametrize("table", [
    {"spring_stiffness_n_m": [200.0]},
    {"spring_stiffness_n_m": "200"},
    {"spring_stiffness_n_m": True},
    {"spring_stiffness_n_m": float("nan")},
    {"spring_stiffness_n_m": float("inf")},
    {"timestep_s": [0.001]},
    {"timestep_s": "fast"},
    [],
])
def test_options_reject_non_scalar_values(table):
    with pytest.raises(ValueError):
        load_options(table)


@pytest.mark.parametrize("kwargs, match", [
    ({"packets": 11}, "tube capacity"),
    ({"packets": -1}, "tube capacity"),
    ({"capacity": 25}, "capacity"),
    ({"button_fraction": 0.25}, "fraction 0"),
])
def test_prototype_assembly_rejects_loaded_and_capacity_variants(p, kwargs, match):
    with pytest.raises(ValueError, match=match):
        prototype_assembly(p, **kwargs)


# --------------------------------------------------------------------------- lazy hooks
def test_lazy_physics_hooks(p):
    assert PROJECT.physics is not None
    assert PROJECT.physics_with_options is not None

    spec = PROJECT.physics("prototype", p)
    assert isinstance(spec, AssemblySpec)
    assert spec.name == "pocky_prototype"
    assert spec.timestep_s == pytest.approx(1.0e-3)

    for other in ("linkage_motion", "packet_dummy", "not_a_model"):
        assert PROJECT.physics(other, p) is None
        assert PROJECT.physics_with_options(other, p, {}) is None

    optioned = PROJECT.physics_with_options(
        "prototype", p, {"spring_stiffness_n_m": 200.0, "timestep_s": 5.0e-4})
    assert isinstance(optioned, AssemblySpec)
    assert optioned.timestep_s == pytest.approx(5.0e-4)
    rod = next(body for body in optioned.bodies if body.body_id == "rod")
    assert rod.joint.spring.stiffness == pytest.approx(200.0)

    loaded = PROJECT.physics_with_options("prototype", p, {"packets": 2})
    assert isinstance(loaded, AssemblySpec)
    assert {b.body_id for b in loaded.bodies} >= {"packet", "packet_02"}

    with pytest.raises(ValueError):
        PROJECT.physics_with_options("prototype", p, {"packets": 11})


# --------------------------------------------------------------------------- static
def test_exact_solid_overlap_is_zero_at_all_five_fractions(p):
    inventory = exact_overlap_inventory(p)
    assert inventory["ok"] is True
    assert inventory["noise_threshold_mm3"] == pytest.approx(1.0e-3)
    assert set(inventory["fractions"]) == {f"{fraction:.2f}" for fraction in RESET_FRACTIONS}
    for key, row in inventory["fractions"].items():
        assert row["ok"] is True, (key, row["overlaps"])
        assert row["overlaps"] == []
        assert row["worst_overlap_mm3"] <= 1.0e-3
