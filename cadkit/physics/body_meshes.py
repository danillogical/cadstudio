"""Visual bodies of a compiled run scene: which bodies have meshes, and their ``.glb`` payloads.

Shared by the GUI trajectory export (``cadkit/gui/trajectory.py``) and the live sidecar writer
(``cadkit/physics/live.py``), so a live view and a finished trajectory list the same bodies in
the same order with the same mesh files. Everything here is pure: it reads a compiled
``MjModel``, the ``scene.xml`` bytes and the ``assets/*.stl`` bytes, and writes nothing.

A body is exported when it owns at least one mesh geom; bodies come in body-id order. Each
body is ``{"name", "fixed", "meshes", "removedAt"}``: ``fixed`` is true when the body is welded
to the world (``body_weldid == 0``), and each mesh is ``{"geom", "mesh": "meshes/<mesh>.glb",
"pose"}`` with ``pose`` the geom's local ``[x, y, z (mm), qw, qx, qy, qz]`` from ``scene.xml``.
``removedAt`` is the sim time (s) at which a scenario ``remove_body`` took the body out of the
scene, or ``None``; it is ``None`` here and filled in by the trajectory export and the live
writer. A viewer hides the body at every time ``>= removedAt``.
"""
from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET

import numpy as np

_SAFE_MESH = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
_UNSUPPORTED_GEOM_ATTRS = ("euler", "axisangle", "xyaxes", "zaxis", "fromto")


class BodyMeshError(ValueError):
    """The scene's visual bodies could not be mapped or converted."""


def clean(value: float, digits: int) -> float:
    """Round for stable JSON; collapse ``-0.0`` so the text is byte-stable."""
    value = round(float(value), digits)
    return 0.0 if value == 0.0 else value


def _floats(text: str, count: int, what: str) -> list[float]:
    try:
        values = [float(v) for v in text.split()]
    except ValueError:
        values = []
    if len(values) != count:
        raise BodyMeshError(f"{what} must have {count} numbers, got {text!r}")
    return values


def parse_scene_xml(xml: bytes) -> tuple[dict, dict]:
    """``mesh name -> (file, scale)`` and ``geom name -> (pos, quat, unsupported attr)``."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise BodyMeshError(f"scene.xml is not well-formed XML: {exc}") from None
    meshes: dict[str, tuple[str, tuple[float, float, float]]] = {}
    for element in root.iter("mesh"):
        name = element.get("name")
        if not name:
            continue
        scale = _floats(element.get("scale", "1 1 1"), 3, f"mesh {name!r} scale")
        meshes[name] = (element.get("file", ""), (scale[0], scale[1], scale[2]))
    geoms: dict[str, tuple[tuple[float, ...], tuple[float, ...], str | None]] = {}
    for element in root.iter("geom"):
        name = element.get("name")
        if not name:
            continue
        unsupported = next((a for a in _UNSUPPORTED_GEOM_ATTRS if element.get(a) is not None),
                           None)
        geoms[name] = (
            tuple(_floats(element.get("pos", "0 0 0"), 3, f"geom {name!r} pos")),
            tuple(_floats(element.get("quat", "1 0 0 0"), 4, f"geom {name!r} quat")),
            unsupported,
        )
    return meshes, geoms


def body_meshes(mujoco, model, xml: bytes) -> tuple[list[dict], list[tuple[str, str]]]:
    """Bodies with a visual mesh in body-id order, plus ``(mesh name, asset path)`` pairs."""
    meshes_xml, geoms_xml = parse_scene_xml(xml)
    by_body: dict[int, list[dict]] = {}
    references: list[tuple[str, str]] = []
    for g in range(model.ngeom):
        if int(model.geom_type[g]) != int(mujoco.mjtGeom.mjGEOM_MESH):
            continue
        mesh_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_MESH, int(model.geom_dataid[g]))
        geom_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g)
        if not mesh_name or not geom_name:
            raise BodyMeshError(f"mesh geom {g} has no name in the compiled scene")
        if not _SAFE_MESH.fullmatch(mesh_name):
            raise BodyMeshError(f"mesh name {mesh_name!r} is not a safe file name")
        if mesh_name not in meshes_xml:
            raise BodyMeshError(f"mesh {mesh_name!r} is not declared in scene.xml")
        if geom_name not in geoms_xml:
            raise BodyMeshError(f"geom {geom_name!r} is not declared in scene.xml")
        pos, quat, unsupported = geoms_xml[geom_name]
        if unsupported is not None:
            raise BodyMeshError(
                f"mesh geom {geom_name!r} uses {unsupported!r}; only pos/quat local poses "
                "are supported")
        pose = [clean(v * 1000.0, 6) for v in pos] + [clean(v, 9) for v in quat]
        by_body.setdefault(int(model.geom_bodyid[g]), []).append(
            {"geom": geom_name, "mesh": f"meshes/{mesh_name}.glb", "pose": pose})
        references.append((mesh_name, meshes_xml[mesh_name][0]))
    bodies = []
    for body_id in sorted(by_body):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)
        if not name:
            raise BodyMeshError(f"body {body_id} has no name in the compiled scene")
        bodies.append({
            "name": name,
            "fixed": bool(int(model.body_weldid[body_id]) == 0),
            "meshes": by_body[body_id],
            "removedAt": None,
        })
    return bodies, references


def mesh_payloads(xml: bytes, assets: dict[str, bytes],
                  references: list[tuple[str, str]]) -> dict[str, bytes]:
    """Convert every referenced STL to a body-frame millimetre ``.glb``, keyed by its path."""
    import trimesh  # noqa: PLC0415 - heavy; only needed when meshes are converted

    meshes_xml, _ = parse_scene_xml(xml)
    payloads: dict[str, bytes] = {}
    for mesh_name, rel in references:
        key = f"meshes/{mesh_name}.glb"
        if key in payloads:
            continue
        scale = meshes_xml[mesh_name][1]
        if rel not in assets:
            raise BodyMeshError(f"scene.xml references missing asset {rel!r}")
        try:
            mesh = trimesh.load(io.BytesIO(assets[rel]), file_type="stl", force="mesh")
        except Exception as exc:
            raise BodyMeshError(f"cannot read mesh asset {rel!r}: {exc}") from None
        factor = np.array([s * 1000.0 for s in scale])
        # STLs are already body-local mm; the XML scale is 0.001, so this is normally a no-op.
        if not np.allclose(factor, 1.0):
            mesh.vertices = np.asarray(mesh.vertices) * factor
        payloads[key] = mesh.export(file_type="glb")
    return payloads


def body_ids(mujoco, model, bodies: list[dict]) -> np.ndarray:
    """MuJoCo body ids for ``bodies`` (as returned by :func:`body_meshes`), in order."""
    return np.asarray([mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body["name"])
                       for body in bodies], dtype=np.intp)


def pose_frame(data, ids: np.ndarray) -> np.ndarray:
    """One ``[body][x, y, z (mm), qw, qx, qy, qz]`` float32 frame from ``data.xpos``/``xquat``."""
    frame = np.empty((len(ids), 7), dtype="<f4")
    frame[:, 0:3] = np.asarray(data.xpos, dtype=np.float64)[ids] * 1000.0
    frame[:, 3:7] = np.asarray(data.xquat, dtype=np.float64)[ids]
    return frame
