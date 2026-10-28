"""Live sidecar for a running ``cad physics run``: poses you can watch while the run steps.

``cad physics run`` (unless ``--no-live``) writes ``<out-parent>/<run-name>.live/``, a SIBLING
of the run dir. Nothing is ever written inside the run dir, so its listing and
``manifest.json`` are the same with live on or off. The sidecar is created right after the run
dir is claimed (a stale ``.live`` dir of the same name is removed first) and is never cleaned
up; it stays as a record of the last live view.

Contents (written in this order):

- ``meshes/<mesh>.glb``: every visual mesh, converted once from the run's ``assets/*.stl``
  after the scene compiles (the same conversion and file names as the trajectory export).
- ``poses.bin``: append-only little-endian float32 ``[frame][body][x,y,z,qw,qx,qy,qz]``,
  positions in mm, the same layout as a trajectory's ``poses.bin`` (``frameBytes`` per frame).
- ``live.json``: replaced atomically (temp file + ``os.replace``) after each flush.

``live.json`` keys:

- ``schemaVersion`` (1), ``units`` (``"mm"``), ``liveId`` (null when the dir is not under
  ``out/``; otherwise the dir's path relative to ``out/`` without ``.live``).
- ``fps``, ``t0``: frame ``k`` is the accepted state nearest sim time ``t0 + k / fps`` (ties
  to the earlier state), the rule ``Playback.row_at`` uses, and frames run up to the last
  state exactly as ``frame_times`` counts them. So a finished live ``poses.bin`` equals the
  trajectory export of the same run at the same fps (the trajectory default is 60, live 30).
  There is no ``times`` list. ``t0`` is the initial state's time (null until the first frame).
- ``frames``: the number of complete frames in ``poses.bin``. Readers must trust only this:
  the pose bytes are written and flushed before ``live.json`` is replaced, so ``frames`` never
  exceeds the bytes on disk (the file may already hold more).
- ``simTime``: the latest accepted state's sim time (null before the first). ``plannedTime``:
  the run plan's end time (``t0`` plus every timed phase's steps × timestep), null if unknown.
- ``bodies[]``: ``{name, fixed, removedAt, meshes: [{geom, mesh, pose}]}`` exactly as in
  ``trajectory.json``; ``mesh`` is relative to the ``.live`` dir. Empty until the scene has
  compiled and every mesh file is written, so a listed mesh always exists. ``removedAt`` is
  null until the run removes that body (a scenario ``remove_body``); ``live.json`` is
  rewritten at that moment with the removal's sim time, the same value the trajectory export
  reports. A viewer hides the body at every time ``>= removedAt``.
- ``phases[]``: ``{name, t0, t1}`` for every phase that has states so far (first and last
  state time, as in a trajectory); ``t1`` is null for the current phase until the run is done.
- ``poses``: ``{path, dtype, byteOrder, layout, positionUnits, frameBytes}``.
- ``done``: true once no more frames will be written. ``status``: null while running; on
  completion the run summary's status (``"PASS"``, ``"FAIL"``, ``"INCONCLUSIVE"``), or
  ``"error"`` when the run errored (summary ``ERROR`` or an exception). ``runId``: on
  completion, the run's id as ``GET /v1/runs`` spells it (path relative to ``out/``) when the
  run dir holds ``summary.json`` and ``states.npz`` and lies under ``out/``; else null.
- ``error``: null, or why the live writer stopped early (``done`` is then true and ``status``
  null: the run itself carries on unaffected).

Flushing happens at most every ``flush_s`` seconds of wall time (default 0.5), checked only
when a frame is sampled, plus once at the end. Poses are appended with a plain ``write`` +
``flush`` (no ``fsync``). The writer can never fail a run: every error is caught, logged once
to stderr, and the writer stops (best-effort ``live.json`` with ``done: true``).
"""
from __future__ import annotations

import json
import math
import os
import shutil
import sys
import time
from pathlib import Path

import numpy as np

from .body_meshes import body_ids, body_meshes, clean, mesh_payloads, pose_frame

SCHEMA_VERSION = 1
DEFAULT_FPS = 30.0
MAX_FPS = 1000.0
DEFAULT_FLUSH_S = 0.5
_EPS = 1e-9


def live_dir_for(run_dir) -> Path:
    """The sibling ``<run-name>.live/`` directory for ``run_dir``."""
    run_dir = Path(run_dir).absolute()
    return run_dir.parent / f"{run_dir.name}.live"


def _out_relative(path: Path, out_root: Path) -> str | None:
    try:
        return path.resolve().relative_to(Path(out_root).resolve()).as_posix()
    except (OSError, ValueError):
        return None


class LiveWriter:
    """Writes one run's ``.live`` sidecar; see the module docstring for the contract.

    The runner calls :meth:`open` once the run dir is claimed, :meth:`attach` once the scene
    compiles, :meth:`observe` for every accepted state (as the recorder's observer) and
    :meth:`finish` at the end. Every method swallows its own errors.
    """

    def __init__(self, *, fps: float = DEFAULT_FPS, flush_s: float = DEFAULT_FLUSH_S,
                 out_root=None, clock=time.monotonic, stream=None) -> None:
        fps = float(fps)
        if not math.isfinite(fps) or not 0.0 < fps <= MAX_FPS:
            raise ValueError(f"live fps must be a finite number in (0, {MAX_FPS:g}], got {fps!r}")
        if out_root is None:
            from ..workspace import workspace_root

            out_root = workspace_root() / "out"
        self.fps = fps
        self.flush_s = float(flush_s)
        self.out_root = Path(out_root)
        self._clock = clock
        self._stream = stream
        self.run_dir: Path | None = None
        self.dir: Path | None = None
        self.active = False
        self.done = False
        self.error: str | None = None
        self.status: str | None = None
        self.run_id: str | None = None
        self.live_id: str | None = None
        self.bodies: list[dict] = []
        self._ids = np.zeros(0, dtype=np.intp)
        self._attached = False
        self._poses = None
        self._pending: list[bytes] = []
        self._pending_frames = 0
        self.frames = 0
        self.t0: float | None = None
        self.planned_s: float | None = None
        self._next_t = 0.0
        self._window = 0.0
        self._prev: tuple[float, bytes] | None = None
        self._last_t: float | None = None
        self._phases: list[dict] = []
        self._phase: str | None = None
        self._dirty = False
        self._last_flush = 0.0
        # Timing of the writer's own work (seconds), for overhead measurement.
        self.attach_s = 0.0
        self.observe_s = 0.0
        self.flush_count = 0

    # -- lifecycle -----------------------------------------------------------------------

    def open(self, run_dir) -> None:
        """Replace any stale sidecar and write the first ``live.json`` (no bodies yet)."""
        try:
            self.run_dir = Path(run_dir)
            self.dir = live_dir_for(self.run_dir)
            self.live_id = _out_relative(self.run_dir, self.out_root)
            if self.dir.is_symlink() or self.dir.is_file():
                self.dir.unlink()
            elif self.dir.exists():
                shutil.rmtree(self.dir)
            self.dir.mkdir(parents=True)
            self._poses = open(self.dir / "poses.bin", "wb")
            self.active = True
            self._write_doc()
            self._last_flush = self._clock()
        except Exception as exc:
            self._fail(exc)

    def attach(self, mujoco, model, *, planned_s: float | None = None) -> None:
        """Map the visual bodies, write their ``.glb`` files, then publish them."""
        if not self.active:
            return
        started = time.perf_counter()
        try:
            xml = (self.run_dir / "scene.xml").read_bytes()
            assets = {f"assets/{p.name}": p.read_bytes()
                      for p in sorted((self.run_dir / "assets").glob("*.stl"))}
            bodies, references = body_meshes(mujoco, model, xml)
            for rel, blob in sorted(mesh_payloads(xml, assets, references).items()):
                target = self.dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(blob)
            self.bodies = bodies
            self._ids = body_ids(mujoco, model, bodies)
            self.planned_s = planned_s
            # Poses are packed only for states within two timesteps of the next frame time.
            self._window = 2.0 * float(model.opt.timestep)
            self._attached = True
            self._write_doc()
        except Exception as exc:
            self._fail(exc)
        finally:
            self.attach_s += time.perf_counter() - started

    def observe(self, data, phase: str) -> None:
        """Recorder observer: sample frames at ``fps`` and flush on the wall-clock cadence."""
        if not self.active:
            return
        started = time.perf_counter()
        try:
            t = float(data.time)
            self._last_t = t
            if phase != self._phase:
                if self._phases:
                    self._phases[-1]["t1"] = self._phases[-1]["_last"]
                self._phases.append({"name": phase, "t0": t, "t1": None, "_last": t})
                self._phase = phase
                self._dirty = True
            else:
                self._phases[-1]["_last"] = t
            if not self._attached:
                return
            if self.t0 is None:
                self.t0 = t
                self._next_t = t
                if self.planned_s is not None:
                    self.planned_s = t + self.planned_s
            if t < self._next_t - self._window:
                self._prev = None
                return
            blob = pose_frame(data, self._ids).tobytes()
            prev = self._prev
            crossed = False
            while t >= self._next_t:
                # The state nearest the frame time, ties to the earlier one (Playback.row_at).
                at = self._next_t
                near = blob if prev is None or t - at < at - prev[0] else prev[1]
                self._pending.append(near)
                self._pending_frames += 1
                self._next_t = self.t0 + (self.frames + self._pending_frames) / self.fps
                crossed = True
            self._prev = (t, blob)
            if crossed and self._clock() - self._last_flush >= self.flush_s:
                self._flush()
        except Exception as exc:
            self._fail(exc)
        finally:
            self.observe_s += time.perf_counter() - started

    def removed(self, name: str, t: float) -> None:
        """Recorder removal observer: stamp ``removedAt`` on the body and republish now."""
        if not self.active:
            return
        try:
            for body in self.bodies:
                if body["name"] == name:
                    body["removedAt"] = clean(t, 9)
            self._dirty = True
            self._flush()
        except Exception as exc:
            self._fail(exc)

    def finish(self, summary: dict | None) -> None:
        """Flush what is left and mark the sidecar done; ``None`` means the run raised."""
        if not self.active:
            return
        try:
            if self._phases:
                self._phases[-1]["t1"] = self._phases[-1]["_last"]
            self._trailing_frames()
            raw = summary.get("status") if isinstance(summary, dict) else None
            self.status = "error" if raw in (None, "ERROR") else str(raw)
            self.run_id = self._finished_run_id()
            self.done = True
            self._flush(force=True)
        except Exception as exc:
            self._fail(exc)
        finally:
            self._close()

    # -- internals -----------------------------------------------------------------------

    def _trailing_frames(self) -> None:
        """Frames up to the last state, as ``frame_times`` counts them, use the last state."""
        if self.t0 is None or self._prev is None or self._last_t is None:
            return
        total = int(math.floor((self._last_t - self.t0) * self.fps + _EPS)) + 1
        while self.frames + self._pending_frames < total:
            self._pending.append(self._prev[1])
            self._pending_frames += 1

    def _finished_run_id(self) -> str | None:
        run_dir = self.run_dir
        for name in ("summary.json", "states.npz"):
            path = run_dir / name
            if path.is_symlink() or not path.is_file():
                return None
        return _out_relative(run_dir, self.out_root)

    def _flush(self, *, force: bool = False) -> None:
        if not (self._pending or self._dirty or force):
            return
        if self._pending:
            self._poses.write(b"".join(self._pending))
            self._poses.flush()
            self.frames += self._pending_frames
            self._pending.clear()
            self._pending_frames = 0
        self._write_doc()
        self._dirty = False
        self._last_flush = self._clock()
        self.flush_count += 1

    def _doc(self) -> dict:
        nbody = len(self.bodies)
        return {
            "schemaVersion": SCHEMA_VERSION,
            "units": "mm",
            "liveId": self.live_id,
            "fps": self.fps,
            "t0": None if self.t0 is None else clean(self.t0, 9),
            "frames": int(self.frames),
            "simTime": None if self._last_t is None else clean(self._last_t, 9),
            "plannedTime": None if self.planned_s is None else clean(self.planned_s, 9),
            "bodies": self.bodies,
            "phases": [{"name": p["name"], "t0": clean(p["t0"], 9),
                        "t1": None if p["t1"] is None else clean(p["t1"], 9)}
                       for p in self._phases],
            "poses": {
                "path": "poses.bin",
                "dtype": "float32",
                "byteOrder": "little",
                "layout": "[frame][body][x,y,z,qw,qx,qy,qz]",
                "positionUnits": "mm",
                "frameBytes": nbody * 7 * 4,
            },
            "done": self.done,
            "status": self.status,
            "runId": self.run_id,
            "error": self.error,
        }

    def _write_doc(self) -> None:
        path = self.dir / "live.json"
        tmp = self.dir / f".live.json.{os.getpid()}.tmp"
        tmp.write_text(json.dumps(self._doc(), indent=2, allow_nan=False) + "\n",
                       encoding="utf-8")
        os.replace(tmp, path)

    def _fail(self, exc: Exception) -> None:
        """Log once, stop writing, and leave a best-effort ``done`` record."""
        if not self.active and self.error is not None:
            return
        self.error = f"live writer stopped: {type(exc).__name__}: {exc}"
        stream = self._stream if self._stream is not None else sys.stderr
        try:
            stream.write(f"physics run: {self.error}\n")
            stream.flush()
        except Exception:
            pass
        was_active = self.active
        self.active = False
        self.done = True
        self.status = None
        if was_active and self.dir is not None:
            try:
                self._write_doc()
            except Exception:
                pass
        self._close()

    def _close(self) -> None:
        self.active = False
        poses, self._poses = self._poses, None
        if poses is not None:
            try:
                poses.close()
            except Exception:
                pass
