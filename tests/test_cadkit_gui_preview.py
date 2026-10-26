"""`projects/pocky/preview.py` still prints the same dry-run after the playback extraction."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from cadkit.params import REPO_ROOT
from cadkit.physics.runner import run_scenario_files
from projects.pocky import preview

pytest.importorskip("mujoco")

from cadkit.physics.replay import parse_saved_scene  # noqa: E402
from cadkit.physics.state_archive import (  # noqa: E402
    MAX_ARCHIVE_BYTES,
    load_state_meta,
    read_state_archive,
    required_members,
    set_native_state,
)

SCENARIO = {
    "schema_version": "m4a-1", "scenario_id": "drop", "fixture": "drop_box", "seed": 1,
    "timestep_s": 0.001, "sampling_interval_s": 0.05,
    "budgets": {"max_steps": 20000, "max_sim_time_s": 10.0, "max_trace_rows": 20000},
    "phases": [{"name": "reset", "kind": "reset"},
               {"name": "settle", "kind": "settle", "duration_s": 0.6},
               {"name": "hold", "kind": "hold", "duration_s": 0.2}],
}
ACCEPTANCE = {
    "schema_version": "m4a-1", "acceptance_id": "drop_acceptance",
    "validity": {"max_penetration_m": 0.001, "max_speed_m_s": 10.0, "max_energy_j": 1.0},
    "checks": [
        {"name": "contact", "kind": "contact_force_bound", "body_a": "box",
         "body_b": "floor", "max": 100.0, "units": "N"},
        {"name": "penetration", "kind": "penetration_bound", "max": 0.001, "units": "m"},
    ],
}


def _env() -> dict:
    env = {k: v for k, v in os.environ.items() if k != "POCKY_POSE"}
    env["PATH"] = f"{Path.home() / '.local' / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    return env


@pytest.fixture(scope="module")
def drop_run(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("preview_drop")
    scenario = root / "scenario.json"
    acceptance = root / "acceptance.json"
    scenario.write_text(json.dumps(SCENARIO), encoding="utf-8")
    acceptance.write_text(json.dumps(ACCEPTANCE), encoding="utf-8")
    out = root / "run"
    summary = run_scenario_files(scenario, acceptance, out)
    assert summary["status"] == "PASS", summary.get("detail")
    return out


# ----------------------------------------------------------------- pre-refactor Run
# Verbatim copy of the pre-refactor `Run`, pinning the dry-run output.
class _LegacyRun:
    """The saved scene compiled in memory plus the per-step state archive."""

    def __init__(self, run_dir: Path, transparent: list[str], colliders: bool = False):
        import mujoco
        self.mujoco = mujoco
        self.run_dir = run_dir
        scene = run_dir / "scene.xml"
        if not scene.is_file():
            raise SystemExit(f"{run_dir} has no scene.xml; is it a `cad physics run` directory?")
        assets = {f"assets/{p.name}": p.read_bytes()
                  for p in sorted((run_dir / "assets").glob("*.stl"))}
        xml = scene.read_bytes()
        # Inject the key light and a plain skybox (the clear colour) into the in-memory copy only.
        xml = xml.replace(b"</asset>", preview.SKYBOX.encode() + b"</asset>", 1)
        head, sep, tail = xml.rpartition(b"</worldbody>")
        self.model = parse_saved_scene(head + preview.KEY_LIGHT.encode() + sep + tail if sep else xml, assets)
        self.colliders = colliders
        self.data = mujoco.MjData(self.model)
        meta = load_state_meta(run_dir / "state_meta.json")
        npz = run_dir / "states.npz"
        self.state = read_state_archive(
            npz, expected_members=required_members(meta["layout"]),
            max_bytes=max(MAX_ARCHIVE_BYTES, npz.stat().st_size))
        self.times = np.asarray(self.state["time"], dtype=np.float64).reshape(-1)
        self.phase_names = [str(v) for v in self.state["phase_names"]]
        self.phase_index = np.asarray(self.state["phase_index"])
        self.scenario = json.loads((run_dir / "scenario.json").read_text())
        self._style(transparent)

    def _style(self, transparent: list[str]) -> None:
        """Colour every geom per body, set lighting and background, apply --transparent."""
        mj, m = self.mujoco, self.model
        for g in range(m.ngeom):
            body = mj.mj_id2name(m, mj.mjtObj.mjOBJ_BODY, m.geom_bodyid[g])
            gname = mj.mj_id2name(m, mj.mjtObj.mjOBJ_GEOM, g) or ""
            color = preview.BODY_COLORS.get(body, (0.6, 0.6, 0.6))
            if body and body.startswith("packet"):
                color = preview.PACKET_COLOR
            color = next((c for key, c in preview.PART_COLORS.items() if key in gname), color)
            m.geom_matid[g] = -1
            m.geom_rgba[g] = (*color, 1.0)
        m.vis.headlight.ambient[:] = 0.35
        m.vis.headlight.diffuse[:] = 0.45
        m.vis.headlight.specular[:] = 0.1
        for name in transparent:
            body = mj.mj_name2id(m, mj.mjtObj.mjOBJ_BODY, name)
            if body < 0:
                valid = [mj.mj_id2name(m, mj.mjtObj.mjOBJ_BODY, i) for i in range(m.nbody)]
                raise SystemExit(f"--transparent: no body {name!r}; bodies are {valid}")
            m.geom_rgba[m.geom_bodyid == body, 3] = preview.TRANSPARENT_ALPHA

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

    def restore(self, row: int) -> None:
        """Same restore as replay: native integration state, then a forward pass."""
        set_native_state(self.mujoco, self.model, self.data, self.state["integration_state"][row])
        self.mujoco.mj_forward(self.model, self.data)

    def style_contacts(self, rows: np.ndarray, force_scale: float = 1.0) -> None:
        """Shrink contact markers to this model's scale and size force arrows to the peak force."""
        m, d = self.model, self.data
        m.vis.scale.contactwidth = m.vis.scale.contactheight = 0.02
        m.vis.scale.forcewidth = 0.007
        m.vis.rgba.contactpoint[:] = (0.0, 0.0, 0.0, 1.0)
        m.vis.rgba.contactforce[:] = (1.0, 0.0, 0.6, 1.0)
        wrench = np.zeros(6)
        forces: list[float] = []
        for row in rows:
            self.restore(int(row))
            for i in range(d.ncon):
                self.mujoco.mj_contactForce(m, d, i, wrench)
                forces.append(float(np.linalg.norm(wrench[:3])))
        # The strongest sampled contact draws a short arrow, so the scale follows the window.
        if forces:
            m.vis.map.force = force_scale * 0.01 / max(max(forces), 1e-9)

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
                # Skip geoms that leave the assembly (a pulled-away packet), so they cannot zoom the camera out.
                if reach is not None and ((world < reach[0]).any() or (world > reach[1]).any()):
                    continue
                lo, hi = np.minimum(lo, world.min(axis=0)), np.maximum(hi, world.max(axis=0))
            if reach is None:
                # The first row's bounds, grown by their own size on every side, bound later rows.
                size = np.maximum(hi - lo, 1e-3)
                reach = (lo - size, hi + size)
        return lo, hi

    def fit_distance(self, lo, hi, azimuth: float, elevation: float, aspect: float) -> float:
        """Distance at which the bounds' corners fill the frame (with a 15% margin)."""
        az, el = np.radians(azimuth), np.radians(elevation)
        fwd = np.array([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)])
        right = np.cross(fwd, [0, 0, 1.0])
        right /= np.linalg.norm(right)
        up = np.cross(right, fwd)
        t_v = np.tan(np.radians(self.model.vis.global_.fovy) / 2)
        t_h = t_v * aspect
        corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1])
                            for z in (lo[2], hi[2])]) - (lo + hi) / 2
        need = np.maximum(np.abs(corners @ up) / t_v, np.abs(corners @ right) / t_h) + corners @ fwd
        return float(1.15 * need.max())


def _dry_run(run_dir: Path, *extra: str) -> str:
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert preview.main([str(run_dir), "--dry-run", *extra]) == 0
    return buf.getvalue()


@pytest.mark.parametrize("extra", [[], ["--start", "0.05", "--end", "0.4", "--speed", "0.5"]])
def test_preview_dry_run_matches_pre_refactor(drop_run, monkeypatch, extra):
    after = _dry_run(drop_run, *extra)
    monkeypatch.setattr(preview, "Run", _LegacyRun)
    before = _dry_run(drop_run, *extra)
    assert after == before
    assert "states:" in after
    assert "camera: lookat=" in after


def test_preview_script_dry_run(drop_run):
    r = subprocess.run([sys.executable, "projects/pocky/preview.py", str(drop_run), "--dry-run"],
                       cwd=REPO_ROOT, capture_output=True, text=True, timeout=300, env=_env())
    assert r.returncode == 0, r.stderr
    assert r.stdout == _dry_run(drop_run)


def test_preview_missing_scene_message(tmp_path):
    with pytest.raises(SystemExit) as exc:
        preview.Run(tmp_path, [])
    assert "has no scene.xml" in str(exc.value)
