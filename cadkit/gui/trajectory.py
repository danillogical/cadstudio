"""Trajectory export: replay a saved physics run into a sibling ``<run-name>.gui/`` directory.

**Trajectory** (`<run>/../<run-name>.gui/`, written by `cad gui trajectory RUN_DIR`; the run dir
itself is never written to):
- `trajectory.json` contains:
  - `schemaVersion: 1`, `units: "mm"`, the run id, and the source `manifest.json` sha256;
  - `bodies[]`, each with `name`, a list of meshes (geom name, `.glb` path, local pose),
    `fixed` (welded to the world) and `removedAt` (sim seconds at which a scenario
    `remove_body` took the body out of the scene, else null; hide it at times >= removedAt);
  - `phases[]` (name, t0, t1);
  - `frameCount`, `times`, and a pointer to the poses.
- `poses.bin` is little-endian float32, `[frame][body][x,y,z,qw,qx,qy,qz]`, positions in mm. It
  is sampled at a fixed fps (default 60 sim-fps) from `states.npz`.
- `contacts.bin` (optional) holds per-frame contact points and normal forces.
- Body meshes come from the run's `assets/*.stl`. The geom-to-body mapping comes from
  compiling the run's `scene.xml`.

Fields: ``schemaVersion``, ``units``, ``runId``, ``manifestSha256``, ``fps``, ``frameCount``,
``times``, ``bodies`` (``name``, ``fixed``, ``removedAt``, ``meshes`` with ``geom``,
``mesh``, ``pose``),
``phases`` (``name``, ``t0``, ``t1``), ``poses`` (``path``, ``dtype``, ``byteOrder``, ``shape``,
``layout``, ``positionUnits``) and ``contacts`` (``path``, ``dtype``, ``byteOrder``, ``count``,
``layout``, ``forceUnits``), which is ``null`` unless ``--contacts`` was passed.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np

from ..physics.body_meshes import (
    BodyMeshError,
    body_ids,
    body_meshes,
    mesh_payloads,
    pose_frame,
)
from ..physics.body_meshes import clean as _clean
from ..physics.playback import Playback, frame_times

SCHEMA_VERSION = 1
DEFAULT_FPS = 60.0
MAX_FPS = 1000.0


class TrajectoryError(ValueError):
    """A run could not be exported as a GUI trajectory."""


def gui_dir_for(run_dir) -> Path:
    """The sibling ``<run-name>.gui/`` directory for ``run_dir``."""
    resolved = Path(run_dir).resolve()
    if not resolved.name:
        raise TrajectoryError(f"{run_dir} has no directory name to derive a .gui dir from")
    if not resolved.is_dir():
        raise TrajectoryError(f"run directory {run_dir} does not exist")
    return resolved.parent / f"{resolved.name}.gui"


def _body_meshes(pb: Playback) -> tuple[list[dict], list[tuple[str, str]]]:
    """Bodies with a visual mesh in body-id order, plus ``(mesh name, asset path)`` pairs."""
    try:
        return body_meshes(pb.mujoco, pb.model, pb.xml)
    except BodyMeshError as exc:
        raise TrajectoryError(str(exc)) from None


def _mesh_payloads(pb: Playback, references: list[tuple[str, str]]) -> dict[str, bytes]:
    """Convert every referenced STL to a body-frame millimetre ``.glb``."""
    try:
        return mesh_payloads(pb.xml, pb.assets, references)
    except BodyMeshError as exc:
        raise TrajectoryError(str(exc)) from None


def _sample(pb: Playback, times: np.ndarray, bodies: list[dict],
            with_contacts: bool) -> tuple[bytes, bytes | None, int]:
    """Restore every frame once and pack the body poses (and optional contacts)."""
    mujoco = pb.mujoco
    model, data = pb.model, pb.data
    ids = body_ids(mujoco, model, bodies)
    frames = np.empty((len(times), len(bodies), 7), dtype="<f4")
    contacts: list[list[float]] = []
    wrench = np.zeros(6)
    for k, t in enumerate(times):
        pb.restore(pb.row_at(float(t)))
        frames[k] = pose_frame(data, ids)
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
    for body in bodies:
        removed_at = pb.removed_at(body["name"])
        body["removedAt"] = None if removed_at is None else _clean(removed_at, 9)
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
