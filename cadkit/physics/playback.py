"""Generic playback of a saved physics run: compile the scene and restore any saved state.

This is the run-loading half of the Pocky preview, shared by the interactive viewer and the
GUI trajectory export. It only reads a run directory; nothing here writes or regenerates CAD.
MuJoCo is imported lazily through :func:`cadkit.physics.require_mujoco`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import numpy as np

from . import require_mujoco
from .evidence import EvidenceError, bounded_regular_bytes, raw_sha256
from .replay import ReplayError, parse_saved_scene
from .state_archive import (
    MAX_ARCHIVE_BYTES,
    ArchiveError,
    load_state_meta_bytes,
    read_state_archive,
    required_members,
    set_native_state,
)


class PlaybackError(ValueError):
    """A saved run could not be loaded as a playable scene."""


def frame_times(t0: float, t1: float, fps: float) -> np.ndarray:
    """Frame sim times from ``t0`` to ``t1`` at ``fps``; both ends are sampled."""
    n = int(np.floor((t1 - t0) * fps + 1e-9)) + 1
    return t0 + np.arange(n) / fps


class Playback:
    """The saved scene compiled in memory plus the per-step state archive."""

    def __init__(self, run_dir: Path, *, xml_filter: Callable[[bytes], bytes] | None = None,
                 verify: bool = False):
        self.mujoco = require_mujoco()
        self.run_dir = Path(run_dir)
        scene = self.run_dir / "scene.xml"
        if not scene.is_file():
            raise PlaybackError(
                f"{run_dir} has no scene.xml; is it a `cad physics run` directory?")
        self.manifest: dict | None = None
        self.manifest_sha256: str | None = None
        artifacts: dict = {}
        try:
            if verify:
                manifest_raw = bounded_regular_bytes(self.run_dir, "manifest.json")
                self.manifest = json.loads(manifest_raw.decode("utf-8"))
                if not isinstance(self.manifest, dict):
                    raise PlaybackError("manifest.json is not a JSON object")
                self.manifest_sha256 = raw_sha256(manifest_raw)
                artifacts = self.manifest.get("artifacts")
                if not isinstance(artifacts, dict) or not artifacts:
                    raise PlaybackError("manifest.json has no artifact hashes")
            self.xml = self._read("scene.xml", artifacts, verify)
            self.assets = {
                f"assets/{p.name}": self._read(f"assets/{p.name}", artifacts, verify)
                for p in sorted((self.run_dir / "assets").glob("*.stl"))
            }
            meta_raw = self._read("state_meta.json", artifacts, verify)
            npz_raw = self._read("states.npz", artifacts, verify)
            scenario_raw = self._read("scenario.json", artifacts, verify)
            xml = xml_filter(self.xml) if xml_filter else self.xml
            self.model = parse_saved_scene(xml, self.assets)
            self.data = self.mujoco.MjData(self.model)
            meta = load_state_meta_bytes(meta_raw)
            self.state = read_state_archive(
                npz_raw, expected_members=required_members(meta["layout"]),
                max_bytes=max(MAX_ARCHIVE_BYTES, len(npz_raw)))
            self.times = np.asarray(self.state["time"], dtype=np.float64).reshape(-1)
            self.phase_names = [str(v) for v in self.state["phase_names"]]
            self.phase_index = np.asarray(self.state["phase_index"])
            self.scenario = json.loads(scenario_raw.decode("utf-8"))
            if not len(self.times):
                raise PlaybackError("states.npz has no state rows")
        except PlaybackError:
            raise
        except (ArchiveError, EvidenceError, ReplayError, json.JSONDecodeError,
                OSError, ValueError) as exc:
            raise PlaybackError(str(exc)) from None

    def _read(self, rel: str, artifacts: dict, verify: bool) -> bytes:
        if not verify:
            return (self.run_dir / rel).read_bytes()
        raw = bounded_regular_bytes(self.run_dir, rel, max_bytes=MAX_ARCHIVE_BYTES)
        entry = artifacts.get(rel)
        if not isinstance(entry, dict) or "sha256" not in entry:
            raise PlaybackError(
                f"manifest.json does not hash {rel}; is it a `cad physics run` directory?")
        if entry.get("sha256") != raw_sha256(raw) or entry.get("bytes") != len(raw):
            raise PlaybackError(f"{rel} sha256 does not match manifest.json")
        return raw

    @property
    def t_min(self) -> float:
        return float(self.times[0])

    @property
    def t_max(self) -> float:
        return float(self.times[-1])

    def row_at(self, t: float) -> int:
        """Nearest saved step to sim time `t`."""
        i = int(np.searchsorted(self.times, t))
        if i <= 0:
            return 0
        if i >= len(self.times):
            return len(self.times) - 1
        return i if self.times[i] - t < t - self.times[i - 1] else i - 1

    def phase_at(self, row: int) -> str:
        return self.phase_names[int(self.phase_index[row])]

    def phase_spans(self) -> list[tuple[str, float, float]]:
        """``(name, first row time, last row time)`` for every phase that owns rows."""
        spans = []
        for index, name in enumerate(self.phase_names):
            rows = np.flatnonzero(self.phase_index == index)
            if rows.size:
                spans.append((name, float(self.times[rows[0]]), float(self.times[rows[-1]])))
        return spans

    def restore(self, row: int) -> None:
        """Same restore as replay: native integration state, then a forward pass."""
        set_native_state(self.mujoco, self.model, self.data,
                         self.state["integration_state"][row])
        self.mujoco.mj_forward(self.model, self.data)

    def framing(self, rows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Axis-aligned bounds of the moving assembly over sampled rows."""
        m, d = self.model, self.data
        # Bodies welded to the world (the floor plate) would dominate the extent; skip them.
        moving = m.body_weldid[m.geom_bodyid] != 0
        geoms = np.flatnonzero(moving) if moving.any() else np.arange(m.ngeom)
        corners = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
        lo = np.full(3, np.inf)
        hi = np.full(3, -np.inf)
        reach = None
        for row in rows:
            self.restore(int(row))
            for g in geoms:
                # World-space corners of the geom's local AABB (centre + half-size).
                local = m.geom_aabb[g, :3] + corners * m.geom_aabb[g, 3:]
                world = d.geom_xpos[g] + local @ d.geom_xmat[g].reshape(3, 3).T
                # Skip geoms that leave the assembly (a pulled-away packet), so they cannot
                # zoom the camera out.
                if reach is not None and ((world < reach[0]).any() or (world > reach[1]).any()):
                    continue
                lo, hi = np.minimum(lo, world.min(axis=0)), np.maximum(hi, world.max(axis=0))
            if reach is None:
                # The first row's bounds, grown by their own size on every side, bound later rows.
                size = np.maximum(hi - lo, 1e-3)
                reach = (lo - size, hi + size)
        return lo, hi
