"""Scene export: ``scene.json`` plus one binary glTF per part, in assembly coordinates.

**Scene** (`projects/<project>/out/<model>/scene/`, written by `cad gui scene <model>`):
- `scene.json` contains:
  - `schemaVersion: 1`, `project`, `model`, `units: "mm"`;
  - provenance: git commit, a dirty flag, a params-file sha256, `--set` overrides, and the build time;
  - `parts[]`, each with `id` (the `ModelPart` key), `name`, `mesh` (relative `.glb` path), bbox (min/max mm), volume in mm³, and a colour;
  - an optional `printPose` 4×4 per part.
- `parts/<id>.glb` holds the part in **assembly coordinates**, tessellated once.

Fields: ``schemaVersion``, ``project``, ``model``, ``units``, ``provenance``
(``commit``, ``dirty``, ``paramsPath``, ``paramsSha256``, ``overrides``, ``builtAt``) and
``parts`` (``id``, ``name``, ``mesh``, ``bbox``, ``volume``, ``color``, optional
``printPose``). The default output dir is ``projects/<project>/out/<model>/scene/`` in the workspace.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import trimesh

from ..mesh import shape_to_mesh
from ..params import override
from ..project import load_model, resolve
from ..workspace import model_out, workspace_root

SCHEMA_VERSION = 1
# Match build123d Mesher.add_shape defaults used by cadkit/export.py.
LINEAR_DEFLECTION = 0.001
ANGULAR_DEFLECTION = 0.1
_PART_ID = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
_GIT_TIMEOUT_S = 30


class SceneError(ValueError):
    """A user-facing scene export failure: unknown model/param, bad part id, empty mesh."""


def git_provenance(root: Path) -> dict:
    """The HEAD commit and dirty flag of the git repo at ``root``; ``None`` values when git is
    unavailable or ``root`` is not in a git repo."""
    def git(*args: str):
        try:
            return subprocess.run(["git", *args], cwd=root, capture_output=True,
                                  text=True, timeout=_GIT_TIMEOUT_S, check=False)
        except (OSError, subprocess.SubprocessError):
            return None

    head = git("rev-parse", "HEAD")
    status = git("status", "--porcelain")
    commit = head.stdout.strip() if head is not None and head.returncode == 0 else None
    dirty = bool(status.stdout.strip()) if status is not None and status.returncode == 0 else None
    return {"commit": commit, "dirty": dirty}


def _clean(value: float, digits: int) -> float:
    """Round for stable JSON; collapse ``-0.0`` so the text is byte-stable."""
    value = round(float(value), digits)
    return 0.0 if value == 0.0 else value


def location_matrix(loc) -> list[list[float]]:
    """Row-major 4x4 from a build123d ``Location`` (1-based ``Value``), rounded to 9 digits."""
    trsf = loc.wrapped.Transformation()
    rows = [[_clean(trsf.Value(row, col), 9) for col in range(1, 5)] for row in range(1, 4)]
    rows.append([0.0, 0.0, 0.0, 1.0])
    return rows


def part_mesh(shape) -> trimesh.Trimesh:
    """Tessellate a shape in assembly coordinates, never the print pose."""
    return shape_to_mesh(shape, LINEAR_DEFLECTION, ANGULAR_DEFLECTION)


def _colour(name: str, index: int) -> str:
    # Lazy: cadkit.render imports pyvista at module level, which core must not pay for.
    from ..render import _part_color

    return _part_color(name, index)


def _display_path(path: Path, root: Path) -> str:
    """Workspace-relative POSIX path, or the absolute path when the file is outside it."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return str(resolved)


def write_scene(spec, *, params_path=None, sets=None, out=None) -> dict:
    """Write ``scene.json`` and ``parts/<id>.glb`` for ``spec``; returns paths and part ids.

    All meshes are tessellated and encoded before anything is written, so a failing part
    leaves the previous scene untouched. ``scene.json`` is written last, atomically.
    """
    try:
        project, model = resolve(spec)
    except KeyError as exc:
        raise SceneError(str(exc.args[0])) from None

    path = (Path(params_path) if params_path else project.params_path).resolve()
    p = project.load_params(path)
    if sets:
        try:
            p = override(p, sets)
        except KeyError as exc:
            raise SceneError(f"unknown parameter {exc}") from None

    try:
        parts = load_model(project, model).build(p)
    except ValueError as exc:
        raise SceneError(str(exc)) from None

    root = workspace_root()
    outdir = Path(out) if out else model_out(project.name, model, root) / "scene"

    entries: list[dict] = []
    payloads: list[tuple[str, bytes]] = []
    for index, (pid, mp) in enumerate(parts.items()):
        if not _PART_ID.fullmatch(pid):
            raise SceneError(f"invalid part id {pid!r}; use letters, digits, '_', '.' or '-'")
        bb = mp.shape.bounding_box()
        volume = float(mp.shape.volume)
        mesh = part_mesh(mp.shape)
        if len(mesh.faces) == 0:
            raise SceneError(f"part {pid!r} tessellated to no faces")
        data = mesh.export(file_type="glb")
        if not data:
            raise SceneError(f"part {pid!r} produced an empty glb")
        entry = {
            "id": pid,
            "name": pid,
            "mesh": f"parts/{pid}.glb",
            "bbox": {
                "min": [_clean(bb.min.X, 6), _clean(bb.min.Y, 6), _clean(bb.min.Z, 6)],
                "max": [_clean(bb.max.X, 6), _clean(bb.max.Y, 6), _clean(bb.max.Z, 6)],
            },
            "volume": _clean(volume, 6),
            "color": _colour(pid, index),
        }
        if mp.print_location is not None:
            entry["printPose"] = location_matrix(mp.print_location)
        entries.append(entry)
        payloads.append((pid, data))

    doc = {
        "schemaVersion": SCHEMA_VERSION,
        "project": project.name,
        "model": model,
        "units": "mm",
        "provenance": {
            **git_provenance(root),
            "paramsPath": _display_path(path, root),
            "paramsSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "overrides": {key: sets[key] for key in sorted(sets or {})},
            "builtAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "parts": entries,
    }

    outdir.mkdir(parents=True, exist_ok=True)
    parts_dir = outdir / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for pid, data in payloads:
        target = parts_dir / f"{pid}.glb"
        target.write_bytes(data)
        written.append(target)
    ids = {pid for pid, _ in payloads}
    for stale in parts_dir.glob("*.glb"):
        if stale.stem not in ids:
            stale.unlink()

    scene_path = outdir / "scene.json"
    tmp = outdir / "scene.json.tmp"
    tmp.write_text(json.dumps(doc, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(tmp, scene_path)
    written.append(scene_path)

    return {"project": project.name, "model": model, "outdir": outdir, "scene": scene_path,
            "written": written, "parts": [entry["id"] for entry in entries]}
