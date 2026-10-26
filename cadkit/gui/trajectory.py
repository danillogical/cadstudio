"""Trajectory export: replay a saved physics run into a sibling ``<run-name>.gui/`` directory.

**Trajectory** (`<run>/../<run-name>.gui/`, written by `cad gui trajectory RUN_DIR`; the run dir
itself is never written to):
- `trajectory.json` contains:
  - `schemaVersion: 1`, `units: "mm"`, the run id, and the source `manifest.json` sha256;
  - `bodies[]`, each with `name`, a list of meshes (geom name, `.glb` path, local pose) and
    `fixed` (welded to the world);
  - `phases[]` (name, t0, t1);
  - `frameCount`, `times`, and a pointer to the poses.
- `poses.bin` is little-endian float32, `[frame][body][x,y,z,qw,qx,qy,qz]`, positions in mm. It
  is sampled at a fixed fps (default 60 sim-fps) from `states.npz`.
- `contacts.bin` (optional) holds per-frame contact points and normal forces.
- Body meshes come from the run's `assets/*.stl`. The geom-to-body mapping comes from
  compiling the run's `scene.xml`.

Fields: ``schemaVersion``, ``units``, ``runId``, ``manifestSha256``, ``fps``, ``frameCount``,
``times``, ``bodies`` (``name``, ``fixed``, ``meshes`` with ``geom``, ``mesh``, ``pose``),
``phases`` (``name``, ``t0``, ``t1``), ``poses`` (``path``, ``dtype``, ``byteOrder``, ``shape``,
``layout``, ``positionUnits``) and ``contacts`` (``path``, ``dtype``, ``byteOrder``, ``count``,
``layout``, ``forceUnits``), which is ``null`` unless ``--contacts`` was passed.
"""
from __future__ import annotations

import io
import json
import math
import os
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import trimesh

from ..physics.playback import Playback, frame_times

SCHEMA_VERSION = 1
DEFAULT_FPS = 60.0
MAX_FPS = 1000.0
_SAFE_MESH = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
_UNSUPPORTED_GEOM_ATTRS = ("euler", "axisangle", "xyaxes", "zaxis", "fromto")


class TrajectoryError(ValueError):
    """A run could not be exported as a GUI trajectory."""


def _clean(value: float, digits: int) -> float:
    """Round for stable JSON; collapse ``-0.0`` so the text is byte-stable."""
    value = round(float(value), digits)
    return 0.0 if value == 0.0 else value


def gui_dir_for(run_dir) -> Path:
    """The sibling ``<run-name>.gui/`` directory for ``run_dir``."""
    resolved = Path(run_dir).resolve()
    if not resolved.name:
        raise TrajectoryError(f"{run_dir} has no directory name to derive a .gui dir from")
    if not resolved.is_dir():
        raise TrajectoryError(f"run directory {run_dir} does not exist")
    return resolved.parent / f"{resolved.name}.gui"


def _floats(text: str, count: int, what: str) -> list[float]:
    try:
        values = [float(v) for v in text.split()]
    except ValueError:
        values = []
    if len(values) != count:
        raise TrajectoryError(f"{what} must have {count} numbers, got {text!r}")
    return values


def _parse_scene_xml(xml: bytes) -> tuple[dict, dict]:
    """``mesh name -> (file, scale)`` and ``geom name -> (pos, quat, unsupported attr)``."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise TrajectoryError(f"scene.xml is not well-formed XML: {exc}") from None
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


def _body_meshes(pb: Playback) -> tuple[list[dict], list[tuple[str, str]]]:
    """Bodies with a visual mesh in body-id order, plus ``(mesh name, asset path)`` pairs."""
    mujoco = pb.mujoco
    model = pb.model
    meshes_xml, geoms_xml = _parse_scene_xml(pb.xml)
    by_body: dict[int, list[dict]] = {}
    references: list[tuple[str, str]] = []
    for g in range(model.ngeom):
        if int(model.geom_type[g]) != int(mujoco.mjtGeom.mjGEOM_MESH):
            continue
        mesh_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_MESH, int(model.geom_dataid[g]))
        geom_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g)
        if not mesh_name or not geom_name:
            raise TrajectoryError(f"mesh geom {g} has no name in the compiled scene")
        if not _SAFE_MESH.fullmatch(mesh_name):
            raise TrajectoryError(f"mesh name {mesh_name!r} is not a safe file name")
        if mesh_name not in meshes_xml:
            raise TrajectoryError(f"mesh {mesh_name!r} is not declared in scene.xml")
        if geom_name not in geoms_xml:
            raise TrajectoryError(f"geom {geom_name!r} is not declared in scene.xml")
        pos, quat, unsupported = geoms_xml[geom_name]
        if unsupported is not None:
            raise TrajectoryError(
                f"mesh geom {geom_name!r} uses {unsupported!r}; only pos/quat local poses "
                "are supported")
        pose = [_clean(v * 1000.0, 6) for v in pos] + [_clean(v, 9) for v in quat]
        by_body.setdefault(int(model.geom_bodyid[g]), []).append(
            {"geom": geom_name, "mesh": f"meshes/{mesh_name}.glb", "pose": pose})
        references.append((mesh_name, meshes_xml[mesh_name][0]))
    bodies = []
    for body_id in sorted(by_body):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)
        if not name:
            raise TrajectoryError(f"body {body_id} has no name in the compiled scene")
        bodies.append({
            "name": name,
            "fixed": bool(int(model.body_weldid[body_id]) == 0),
            "meshes": by_body[body_id],
        })
    return bodies, references


def _mesh_payloads(pb: Playback, references: list[tuple[str, str]]) -> dict[str, bytes]:
    """Convert every referenced STL to a body-frame millimetre ``.glb``."""
    meshes_xml, _ = _parse_scene_xml(pb.xml)
    payloads: dict[str, bytes] = {}
    for mesh_name, rel in references:
        scale = meshes_xml[mesh_name][1]
        if rel not in pb.assets:
            raise TrajectoryError(f"scene.xml references missing asset {rel!r}")
        try:
            mesh = trimesh.load(io.BytesIO(pb.assets[rel]), file_type="stl", force="mesh")
        except Exception as exc:
            raise TrajectoryError(f"cannot read mesh asset {rel!r}: {exc}") from None
        factor = np.array([s * 1000.0 for s in scale])
        # STLs are already body-local mm; the XML scale is 0.001, so this is normally a no-op.
        if not np.allclose(factor, 1.0):
            mesh.vertices = np.asarray(mesh.vertices) * factor
        payloads[f"meshes/{mesh_name}.glb"] = mesh.export(file_type="glb")
    return payloads


def _sample(pb: Playback, times: np.ndarray, bodies: list[dict],
            with_contacts: bool) -> tuple[bytes, bytes | None, int]:
    """Restore every frame once and pack the body poses (and optional contacts)."""
    mujoco = pb.mujoco
    model, data = pb.model, pb.data
    body_ids = [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body["name"])
                for body in bodies]
    frames = np.empty((len(times), len(bodies), 7), dtype="<f4")
    contacts: list[list[float]] = []
    wrench = np.zeros(6)
    for k, t in enumerate(times):
        pb.restore(pb.row_at(float(t)))
        for b, body_id in enumerate(body_ids):
            frames[k, b, 0:3] = np.asarray(data.xpos[body_id], dtype=np.float64) * 1000.0
            frames[k, b, 3:7] = np.asarray(data.xquat[body_id], dtype=np.float64)
        if with_contacts:
            for i in range(data.ncon):
                contact = data.contact[i]
                mujoco.mj_contactForce(model, data, i, wrench)
                pos = np.asarray(contact.pos, dtype=np.float64) * 1000.0
                normal = np.asarray(contact.frame[:3], dtype=np.float64)
                contacts.append([float(k), *pos.tolist(), *normal.tolist(), float(wrench[0])])
    blob = None
    if with_contacts:
        blob = np.asarray(contacts, dtype="<f4").reshape(-1, 8).tobytes()
    return frames.astype("<f4").tobytes(), blob, len(contacts)


def write_trajectory(run_dir, *, fps: float = DEFAULT_FPS, contacts: bool = False) -> dict:
    """Export ``<run-name>.gui/`` next to ``run_dir`` and return the written paths.

    Everything is built in memory first, then staged in a temp dir beside the run and moved
    into place, so a failed export leaves the previous ``.gui/`` and the run dir untouched.
    """
    try:
        fps = float(fps)
    except (TypeError, ValueError):
        raise TrajectoryError(f"fps must be a number in (0, {MAX_FPS:g}], got {fps!r}") from None
    if not math.isfinite(fps) or not 0.0 < fps <= MAX_FPS:
        raise TrajectoryError(f"fps must be a finite number in (0, {MAX_FPS:g}], got {fps!r}")
    run_path = Path(run_dir)
    if run_path.is_symlink():
        raise TrajectoryError(f"run directory {run_dir} is a symlink; refusing")
    if not run_path.is_dir():
        raise TrajectoryError(f"run directory {run_dir} does not exist")
    final = gui_dir_for(run_path)
    resolved = run_path.resolve()
    if final == resolved or resolved in final.parents:
        raise TrajectoryError(f"refusing to write the trajectory inside the run dir {run_dir}")
    if final.is_symlink():
        raise TrajectoryError(f"{final} is a symlink; refusing to replace it")

    pb = Playback(run_path, verify=True)
    if pb.t_max < pb.t_min:
        raise TrajectoryError(f"the run's states end before they start ({pb.t_min}..{pb.t_max})")
    bodies, references = _body_meshes(pb)
    if not bodies:
        raise TrajectoryError("the scene has no visual mesh bodies to export")
    meshes = _mesh_payloads(pb, references)
    times = frame_times(pb.t_min, pb.t_max, fps)
    poses_blob, contacts_blob, contact_count = _sample(pb, times, bodies, contacts)
    phases = [{"name": name, "t0": _clean(t0, 9), "t1": _clean(t1, 9)}
              for name, t0, t1 in pb.phase_spans()]

    run_id = pb.manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise TrajectoryError("manifest.json has no run_id")
    doc = {
        "schemaVersion": SCHEMA_VERSION,
        "units": "mm",
        "runId": run_id,
        "manifestSha256": pb.manifest_sha256,
        "fps": fps,
        "frameCount": int(len(times)),
        "times": [_clean(t, 9) for t in times],
        "bodies": bodies,
        "phases": phases,
        "poses": {
            "path": "poses.bin",
            "dtype": "float32",
            "byteOrder": "little",
            "shape": [int(len(times)), len(bodies), 7],
            "layout": "[frame][body][x,y,z,qw,qx,qy,qz]",
            "positionUnits": "mm",
        },
        "contacts": None if not contacts else {
            "path": "contacts.bin",
            "dtype": "float32",
            "byteOrder": "little",
            "count": int(contact_count),
            "layout": "[contact][frame,x,y,z,nx,ny,nz,normalForce]",
            "forceUnits": "N",
        },
    }
    doc_bytes = (json.dumps(doc, indent=2, allow_nan=False) + "\n").encode("utf-8")

    payloads: list[tuple[str, bytes]] = [("poses.bin", poses_blob)]
    if contacts_blob is not None:
        payloads.append(("contacts.bin", contacts_blob))
    payloads.extend(sorted(meshes.items()))
    payloads.append(("trajectory.json", doc_bytes))

    parent = final.parent
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=parent))
    try:
        stage.chmod(0o755)
        for rel, data in payloads:
            target = stage / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        backup = None
        if final.exists():
            backup = Path(tempfile.mkdtemp(prefix=f".{final.name}.old.", dir=parent))
            backup.rmdir()
            os.replace(final, backup)
        try:
            os.replace(stage, final)
        except OSError:
            if backup is not None:
                os.replace(backup, final)
            raise
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)
    finally:
        shutil.rmtree(stage, ignore_errors=True)

    written = [final / rel for rel, _ in payloads]
    return {"run": str(run_path.resolve()), "outdir": final,
            "trajectory": final / "trajectory.json",
            "frameCount": int(len(times)), "bodies": [b["name"] for b in bodies],
            "written": written}
