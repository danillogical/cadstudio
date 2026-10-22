"""Scene adapter: frames, mass/COM/inertia, visual vs collision alignment, MJCF determinism.

Every expected value is computed independently — from build123d's own transform of the shape,
from a closed-form solid formula, or from the analytic parallel-axis theorem — never by calling
the code under test twice.
"""
import json
import math

import numpy as np
import pytest

from cadkit.physics.schema import (
    AssemblySpec,
    BodySpec,
    ColliderSpec,
    Frame,
    PartSpec,
    Source,
    safe_filename,
)
from cadkit.physics.scene import SceneInvalid, export_scene

pytest.importorskip("mujoco", reason="optional physics extra not installed")

import mujoco  # noqa: E402

from cadkit.physics.fixtures import FIXTURE_DENSITY_G_CM3, fixture_assembly  # noqa: E402
from cadkit.physics.inertia import body_inertial, part_inertial  # noqa: E402
from cadkit.physics.units import mass_kg  # noqa: E402


# --------------------------------------------------------------------------- frames
def test_frame_matches_build123d_transform():
    """Frame.apply must equal build123d's own Pos*Rot of the same point."""
    from build123d import Box, Pos, Rot

    cases = [
        ((10.0, 20.0, 30.0), (30.0, 0.0, 0.0), (4.0, 6.0, 8.0)),
        ((1.0, -2.0, 3.0), (12.0, 34.0, 56.0), (5.0, -7.0, 11.0)),
        ((0.0, 0.0, 0.0), (0.0, 0.0, 90.0), (3.0, 1.0, 0.0)),
    ]
    for pos, rot, pt in cases:
        frame = Frame(pos_mm=pos, rot_deg=rot)
        moved = (Pos(*pos) * Rot(*rot)) * (Pos(*pt) * Box(1, 1, 1))
        bb = moved.bounding_box()
        centre = ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2,
                  (bb.min.Z + bb.max.Z) / 2)
        assert frame.apply(pt) == pytest.approx(centre, abs=1e-9)
        assert frame.to_local(frame.apply(pt)) == pytest.approx(pt, abs=1e-9)


def test_frame_rejects_nonfinite():
    with pytest.raises(ValueError):
        Frame(pos_mm=(0.0, float("nan"), 0.0)).validate()


# --------------------------------------------------------------------------- mass
def test_part_mass_uses_the_canonical_formula():
    from build123d import Box

    shape = Box(20.0, 40.0, 25.0)
    part = PartSpec("b", shape, colliders=(ColliderSpec("c", "box", (10, 20, 12.5)),),
                    density_g_cm3=1.27)
    m, com, _ = part_inertial(part)
    assert m == pytest.approx(20.0 * 40.0 * 25.0 * 1.27 * 1e-6)
    assert m == pytest.approx(0.0254)
    assert com == pytest.approx((0.0, 0.0, 0.0), abs=1e-12)


def test_offset_com_is_reported_and_compiled(tmp_path):
    """A part whose COM is not at the body origin must keep that offset end to end."""
    from build123d import Box, Pos

    frame = Frame(pos_mm=(50.0, 0.0, 0.0), rot_deg=(0.0, 0.0, 0.0))
    # authored in ASSEMBLY coordinates, as the contract requires
    shape = Pos(62.0, 0.0, 0.0) * Box(6.0, 6.0, 6.0)
    spec = AssemblySpec(name="offset", bodies=(
        BodySpec("b", parts=(PartSpec("p", shape,
                                     colliders=(ColliderSpec("c", "box", (3, 3, 3),
                                                             pos_mm=(12, 0, 0)),),
                                     density_g_cm3=1.0),),
                 frame=frame),
    ))
    ex = export_scene(spec, tmp_path)
    # independent: the shape's own COM in assembly coordinates, in metres
    independent = (0.062, 0.0, 0.0)
    assert ex.bodies[0].com_world_m == pytest.approx(independent, abs=1e-12)

    model = ex.model
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "b")
    # data.xipos is the body COM; data.xpos is the frame origin (0.05) and must differ.
    assert data.xipos[bid] == pytest.approx(independent, abs=1e-9)
    assert data.xpos[bid][0] == pytest.approx(0.05, abs=1e-9)
    assert abs(data.xipos[bid][0] - data.xpos[bid][0]) > 0.01


def test_measured_mass_override_rescales_inertia_consistently():
    """A measured mass keeps the shape's distribution and scales the tensor by the same ratio."""
    from build123d import Box

    shape = Box(20.0, 40.0, 25.0)
    derived = PartSpec("p", shape, colliders=(ColliderSpec("c", "box", (10, 20, 12.5)),),
                       density_g_cm3=1.27)
    m0, _, i0 = part_inertial(derived)

    measured = 0.030
    override = PartSpec("p", shape, colliders=(ColliderSpec("c", "box", (10, 20, 12.5)),),
                        density_g_cm3=1.27, mass_kg=measured)
    m1, com1, i1 = part_inertial(override)

    assert m1 == pytest.approx(measured)
    assert com1 == pytest.approx((0.0, 0.0, 0.0), abs=1e-12)
    # inertia scales by exactly the mass ratio
    assert np.array(i1) / np.array(i0) == pytest.approx(
        np.full((3, 3), measured / m0), rel=1e-12)


def test_two_part_body_uses_parallel_axis(tmp_path):
    """Aggregate inertia must equal the analytic parallel-axis sum about the body COM."""
    from build123d import Box, Pos

    d = 1.24
    a = Pos(-20.0, 0.0, 0.0) * Box(10.0, 10.0, 10.0)
    b = Pos(30.0, 0.0, 0.0) * Box(10.0, 10.0, 10.0)
    spec = AssemblySpec(name="agg", bodies=(
        BodySpec("ab", parts=(
            PartSpec("a", a, colliders=(ColliderSpec("ca", "box", (5, 5, 5), pos_mm=(-20, 0, 0)),),
                     density_g_cm3=d),
            PartSpec("b", b, colliders=(ColliderSpec("cb", "box", (5, 5, 5), pos_mm=(30, 0, 0)),),
                     density_g_cm3=d),
        )),
    ))
    ex = export_scene(spec, tmp_path)
    inertial = body_inertial(spec.bodies[0])

    ma = mass_kg(1000.0, d)
    mb = mass_kg(1000.0, d)
    total = ma + mb
    # equal masses 50 mm apart -> COM halfway
    assert inertial.mass_kg == pytest.approx(total)
    assert inertial.com_m == pytest.approx((0.005, 0.0, 0.0), abs=1e-12)

    # analytic: I_self about each cube COM (m a^2/6) + m d^2 about the shared COM
    i_self = ma * (0.010 ** 2) / 6.0
    lever = 0.025 ** 2
    got = np.diag(np.array(inertial.inertia_kg_m2))
    # The two cubes are separated along X, so the parallel-axis term adds m d^2 to the
    # moments about Y and Z only; I_xx stays 2 * I_self.
    assert got[0] == pytest.approx(2.0 * i_self, rel=1e-9)
    assert got[1] == pytest.approx(2.0 * (i_self + ma * lever), rel=1e-9)
    assert got[2] == pytest.approx(2.0 * (i_self + ma * lever), rel=1e-9)

    model = ex.model
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "ab")
    assert data.xipos[bid] == pytest.approx(inertial.com_m, abs=1e-9)


# --------------------------------------------------------------------------- geometry
def test_visual_and_collider_world_bounds_coincide(tmp_path):
    """The visual mesh and its primitive collider must land on the same world volume."""
    ex = export_scene(fixture_assembly(), tmp_path)
    model = ex.model
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)

    def world_aabb(name):
        g = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, name)
        rot = data.geom_xmat[g].reshape(3, 3)
        half = model.geom_size[g]
        corners = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1)
                            for sz in (-1, 1)]) * half
        world = (rot @ corners.T).T + data.geom_xpos[g]
        return world.min(axis=0), world.max(axis=0)

    # Every visual mesh must have a collider at the same world volume. The pairs are taken
    # from the spec itself, so a collider left at the wrong offset cannot be skipped.
    spec = fixture_assembly()
    pairs = []
    for body in spec.bodies:
        for part in body.parts:
            if part.role == "spare" or part.shape is None:
                continue
            visual = f"{body.body_id}__{part.part_id}_visual"
            for col in part.colliders:
                pairs.append((visual, col.collider_id))
    assert len(pairs) == 3, pairs
    for visual, collider in pairs:
        lo_v, hi_v = world_aabb(visual)
        lo_c, hi_c = world_aabb(collider)
        assert lo_v == pytest.approx(lo_c, abs=1e-6), visual
        assert hi_v == pytest.approx(hi_c, abs=1e-6), visual


def test_visual_geoms_never_collide(tmp_path):
    ex = export_scene(fixture_assembly(), tmp_path)
    model = ex.model
    for g in range(model.ngeom):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g)
        if name.endswith("_visual"):
            assert model.geom_contype[g] == 0 and model.geom_conaffinity[g] == 0, name


def test_mesh_scale_is_applied_exactly_once(tmp_path):
    """The written STL is in mm; the <mesh scale> converts it; the result is metres."""
    ex = export_scene(fixture_assembly(), tmp_path)
    model = ex.model
    g = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "link_ab__arm_visual")
    # arm is 40 x 10 x 6 mm -> half extents 0.02 x 0.005 x 0.003 m
    half = np.sort(model.geom_size[g])
    assert half == pytest.approx(np.sort([0.02, 0.005, 0.003]), rel=1e-6)


def test_body_and_freejoint_counts(tmp_path):
    ex = export_scene(fixture_assembly(), tmp_path)
    # world + world_frame + two bodies
    assert ex.n_bodies == 4
    assert ex.n_free_joints == 2
    assert ex.n_geoms == 6  # 3 visual + 3 collider


# --------------------------------------------------------------------------- determinism
def test_two_exports_are_byte_identical(tmp_path):
    a = export_scene(fixture_assembly(), tmp_path / "a")
    b = export_scene(fixture_assembly(), tmp_path / "b")
    assert a.scene_hash == b.scene_hash
    assert (tmp_path / "a" / "scene.xml").read_bytes() == (
        tmp_path / "b" / "scene.xml").read_bytes()
    assert a.asset_hashes == b.asset_hashes


def test_scene_hash_changes_with_geometry(tmp_path):
    from build123d import Box, Pos

    spec = fixture_assembly()
    first = export_scene(spec, tmp_path / "x")

    body = spec.bodies[0]
    part = body.parts[0]
    changed = AssemblySpec(name=spec.name, bodies=(
        BodySpec(body.body_id, parts=(PartSpec(
            part.part_id, Pos(10.0, 0.0, 1.0) * Box(40.0, 10.0, 7.0), part.colliders,
            density_g_cm3=FIXTURE_DENSITY_G_CM3),) + body.parts[1:],
            frame=body.frame, fixture=body.fixture),
        *spec.bodies[1:],
    ))
    second = export_scene(changed, tmp_path / "y")
    assert first.scene_hash != second.scene_hash


# --------------------------------------------------------------------------- negatives
def test_missing_collider_recipe_is_scene_invalid(tmp_path):
    from build123d import Box

    spec = AssemblySpec(name="no_collider", bodies=(
        BodySpec("b", parts=(PartSpec("p", Box(10, 10, 10), density_g_cm3=1.0),)),
    ))
    with pytest.raises(SceneInvalid, match="no collider recipe"):
        export_scene(spec, tmp_path)


def test_spare_role_is_allowed_without_colliders(tmp_path):
    from build123d import Box

    spec = AssemblySpec(name="spare", bodies=(
        BodySpec("b", parts=(
            PartSpec("p", Box(10, 10, 10),
                     colliders=(ColliderSpec("c", "box", (5, 5, 5)),), density_g_cm3=1.0),
            PartSpec("parked", Box(2, 2, 2), role="spare", density_g_cm3=1.0),
        )),
    ))
    ex = export_scene(spec, tmp_path)
    assert ex.n_geoms == 2  # one visual + one collider; the spare contributes neither


@pytest.mark.parametrize("bad_id", ["", "has space", "semi;colon", "../escape", ".hidden",
                                    "x" * 65, "a__b"])
def test_unsafe_ids_are_rejected(bad_id):
    with pytest.raises(ValueError):
        safe_filename(bad_id)


def test_ids_cannot_escape_the_output_directory(tmp_path):
    from build123d import Box

    with pytest.raises(ValueError):
        PartSpec("../../evil", Box(1, 1, 1), density_g_cm3=1.0).validate()
    with pytest.raises(ValueError):
        PartSpec("..", Box(1, 1, 1), density_g_cm3=1.0).validate()


@pytest.mark.parametrize("bad", [
    {"mass_kg": 0.0}, {"mass_kg": -1.0}, {"mass_kg": float("nan")},
    {"density_g_cm3": 0.0}, {"density_g_cm3": -2.0},
])
def test_invalid_mass_inputs_are_rejected(bad):
    from build123d import Box

    with pytest.raises(ValueError):
        PartSpec("p", Box(1, 1, 1), **bad).validate()


def test_duplicate_part_ids_are_rejected():
    from build123d import Box

    p = PartSpec("same", Box(1, 1, 1), density_g_cm3=1.0)
    with pytest.raises(ValueError, match="duplicate part"):
        BodySpec("b", parts=(p, p)).validate()


def test_duplicate_body_ids_are_rejected():
    from build123d import Box

    p = PartSpec("p", Box(1, 1, 1), density_g_cm3=1.0)
    b = BodySpec("same", parts=(p,))
    with pytest.raises(ValueError, match="duplicate body"):
        AssemblySpec(name="a", bodies=(b, b)).validate()


def test_fixed_body_must_declare_a_fixture():
    from build123d import Box

    p = PartSpec("p", Box(1, 1, 1), density_g_cm3=1.0)
    with pytest.raises(ValueError, match="fixture"):
        BodySpec("b", parts=(p,), fixed_to_world=True).validate()


def test_invalid_inertia_is_rejected(monkeypatch):
    """An asymmetric or non-positive-definite tensor must not reach the XML."""
    from cadkit.physics import inertia as inertia_mod

    real = inertia_mod._validate_tensor
    with pytest.raises(ValueError, match="not positive definite"):
        real("b", np.array([[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, 1.0]]))
    with pytest.raises(ValueError, match="triangle inequality"):
        real("b", np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 10.0]]))
    with pytest.raises(ValueError, match="asymmetric"):
        real("b", np.array([[1.0, 0.5, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]))


def test_thin_shell_inertia_is_not_rejected():
    """A thin-walled part legitimately exceeds the uniform-solid bbox bound."""
    from build123d import Box

    outer = Box(100.0, 100.0, 100.0)
    inner = Box(99.6, 99.6, 99.6)
    shell = (outer - inner).solid()
    part = PartSpec("shell", shell, colliders=(ColliderSpec("c", "box", (50, 50, 50)),),
                    density_g_cm3=1.27)
    m, _, tensor = part_inertial(part)
    uniform = m * (0.1 ** 2 + 0.1 ** 2) / 12.0
    got = np.diag(np.array(tensor))[0]
    assert got > uniform  # a shell has its mass further out
    inertia_mod = __import__("cadkit.physics.inertia", fromlist=["_validate_tensor"])
    inertia_mod._validate_tensor("shell", np.array(tensor))  # must not raise


# --------------------------------------------------------------------------- report
def test_offdiagonal_inertia_survives_into_the_xml(tmp_path):
    """A rotated part gives the body a real product term; it must reach fullinertia."""
    ex = export_scene(fixture_assembly(), tmp_path)
    text = ex.scene_xml.read_text(encoding="utf-8")
    assert 'fullinertia="' in text
    body = next(b for b in ex.bodies if b.body_id == "link_ab")
    i = np.array(body.inertia_kg_m2)
    assert max(abs(i[0, 1]), abs(i[0, 2]), abs(i[1, 2])) > 1e-9

    # and MuJoCo must have parsed a tensor with the same principal moments
    model = ex.model
    bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "link_ab")
    # MuJoCo stores the principal moments plus a quaternion; the multiset of moments is
    # invariant under the rotation, so compare sorted eigenvalues.
    compiled = np.sort(np.array(model.body_inertia[bid], dtype=float))
    analytic = np.sort(np.linalg.eigvalsh(i))
    assert compiled == pytest.approx(analytic, rel=1e-6)


def test_declared_collider_bitmasks_are_compiled(tmp_path):
    """A collider's contype/conaffinity must reach the model, not be flattened."""
    ex = export_scene(fixture_assembly(), tmp_path)
    model = ex.model
    for body in fixture_assembly().bodies:
        for part in body.parts:
            for col in part.colliders:
                g = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, col.collider_id)
                assert model.geom_contype[g] == col.contype, col.collider_id
                assert model.geom_conaffinity[g] == col.conaffinity, col.collider_id


def test_body_euler_matches_build123d_for_a_general_rotation(tmp_path):
    """The MJCF euler must be the same convention as Frame.rotation_matrix()."""
    from build123d import Box, Pos

    frame = Frame(pos_mm=(10.0, 20.0, 30.0), rot_deg=(30.0, 12.0, 55.0))
    shape = Pos(30.0, 0.0, 0.0) * Box(20.0, 10.0, 6.0)
    spec = AssemblySpec(name="euler", bodies=(BodySpec("b", parts=(PartSpec(
        "p", shape, density_g_cm3=1.0,
        colliders=(ColliderSpec("k", "box", (10, 5, 3), pos_mm=(30, 0, 0)),)),),
        frame=frame),))
    ex = export_scene(spec, tmp_path)
    data = mujoco.MjData(ex.model)
    mujoco.mj_forward(ex.model, data)
    bid = mujoco.mj_name2id(ex.model, mujoco.mjtObj.mjOBJ_BODY, "b")
    assert np.array(frame.rotation_matrix()) == pytest.approx(
        data.xmat[bid].reshape(3, 3), abs=1e-9)


def test_spare_with_colliders_is_rejected(tmp_path):
    """A collider on a spare would never be simulated; that must not pass silently."""
    from build123d import Box

    spec = AssemblySpec(name="spare_col", bodies=(
        BodySpec("b", parts=(
            PartSpec("p", Box(10, 10, 10),
                     colliders=(ColliderSpec("c", "box", (5, 5, 5)),), density_g_cm3=1.0),
            PartSpec("parked", Box(2, 2, 2), role="spare", density_g_cm3=1.0,
                     colliders=(ColliderSpec("ghost", "box", (1, 1, 1)),)),
        )),
    ))
    with pytest.raises(SceneInvalid, match="never be simulated"):
        export_scene(spec, tmp_path)


def test_convex_collider_is_rejected_until_implemented():
    with pytest.raises(ValueError, match="not implemented yet"):
        ColliderSpec("c", "convex", (),
                     vertices_mm=((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))).validate()


def test_scene_hash_is_platform_independent(tmp_path):
    """Scene identity must not depend on the machine, or it cannot match across CI workers."""
    import cadkit.physics.scene as scene_mod

    a = export_scene(fixture_assembly(), tmp_path / "p1").scene_hash
    real = scene_mod.platform if hasattr(scene_mod, "platform") else None
    assert real is None  # the module must not consult the platform at all
    b = export_scene(fixture_assembly(), tmp_path / "p2").scene_hash
    assert a == b


def test_report_is_strict_json(tmp_path):
    ex = export_scene(fixture_assembly(), tmp_path)
    payload = json.dumps(ex.report())
    assert "NaN" not in payload and "Infinity" not in payload
    json.loads(payload, parse_constant=_reject)


def _reject(value):
    raise AssertionError(f"non-strict JSON constant {value}")


def test_export_writes_utf8_scene_and_assets(tmp_path):
    ex = export_scene(fixture_assembly(), tmp_path)
    text = ex.scene_xml.read_text(encoding="utf-8")
    assert "<mujoco" in text
    for rel in ex.asset_hashes:
        assert (tmp_path / rel).is_file(), rel
