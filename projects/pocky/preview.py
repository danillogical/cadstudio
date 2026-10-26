"""Watch a saved Pocky physics run as an animation (read-only on the run dir).

A run dir from `cad physics run` holds scene.xml + assets/, states.npz (every integration step),
scenario.json and more. The saved scene is compiled with the replay loader, and each frame
restores the nearest saved integration state (mj_setState) and calls mj_forward, so the contacts
and forces shown are the ones MuJoCo derives from that exact state.

Interactive, loops; keys: space pause, left/right step while paused, [ / ] halve / double speed,
r restart. The macOS viewer needs mjpython, so plain python re-launches itself under it:

    uv run --frozen --extra physics python projects/pocky/preview.py RUN_DIR
    uv run --frozen --extra physics mjpython projects/pocky/preview.py RUN_DIR

Video (H.264 mp4 through ffmpeg, offscreen):

    uv run --frozen --extra physics python projects/pocky/preview.py RUN_DIR --video OUT.mp4 \
        --start 2.9 --end 3.6 --transparent body,lip

`--speed` is sim seconds per playback second (0.25 = 4x slow motion). `--dry-run` loads the run
and prints the frame schedule without opening a window.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from cadkit.physics.replay import parse_saved_scene  # noqa: E402
from cadkit.physics.state_archive import (  # noqa: E402
    MAX_ARCHIVE_BYTES, load_state_meta, read_state_archive, required_members, set_native_state)

DISPLAY_FPS = 60.0       # interactive refresh rate
TRANSPARENT_ALPHA = 0.25
# Per-body colours; geoms whose name contains a PART_COLORS key (pegs, springs, shims) override the body.
BODY_COLORS = {"body": (0.62, 0.72, 0.84), "lip": (0.95, 0.52, 0.12), "chassis": (0.30, 0.31, 0.34),
               "crank": (0.96, 0.82, 0.15), "rod": (0.85, 0.15, 0.15), "pusher": (0.20, 0.68, 0.30),
               "floor_world": (0.42, 0.43, 0.46)}
# Packets (packet, packet_01, ...) are chocolate brown so they stand out from the housing and the red rod.
PACKET_COLOR = (0.42, 0.24, 0.11)
PART_COLORS = {"peg": (0.55, 0.20, 0.75), "spring": (0.10, 0.70, 0.75), "shim": (0.80, 0.80, 0.84)}
SKYBOX = ('<texture type="skybox" builtin="gradient" rgb1="0.97 0.97 0.98" rgb2="0.82 0.84 0.88" '
          'width="16" height="16"/>')
# Directional key light from above and the front; the generated scene has no lights of its own.
KEY_LIGHT = ('<light name="preview_key" directional="true" pos="0 0 1" dir="-0.3 0.5 -1" '
             'diffuse="0.7 0.7 0.7" specular="0.15 0.15 0.15" castshadow="false"/>')


class Run:
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
        xml = xml.replace(b"</asset>", SKYBOX.encode() + b"</asset>", 1)
        head, sep, tail = xml.rpartition(b"</worldbody>")
        self.model = parse_saved_scene(head + KEY_LIGHT.encode() + sep + tail if sep else xml, assets)
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
            color = BODY_COLORS.get(body, (0.6, 0.6, 0.6))
            if body and body.startswith("packet"):
                color = PACKET_COLOR
            color = next((c for key, c in PART_COLORS.items() if key in gname), color)
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
            m.geom_rgba[m.geom_bodyid == body, 3] = TRANSPARENT_ALPHA

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
        for row in rows:
            self.restore(int(row))
            for g in geoms:
                # World-space corners of the geom's local AABB (centre + half-size).
                local = m.geom_aabb[g, :3] + corners * m.geom_aabb[g, 3:]
                world = d.geom_xpos[g] + local @ d.geom_xmat[g].reshape(3, 3).T
                lo, hi = np.minimum(lo, world.min(axis=0)), np.maximum(hi, world.max(axis=0))
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


def schedule(run: Run, t0: float, t1: float, speed: float, fps: float) -> tuple[np.ndarray, np.ndarray]:
    """Frame sim times and the nearest saved row for each, for playback at `speed`."""
    n = int(np.floor((t1 - t0) * fps / speed + 1e-9)) + 1
    times = t0 + np.arange(n) * speed / fps
    return times, np.array([run.row_at(t) for t in times])


def configure_contacts(opt, on: bool, colliders: bool = False) -> None:
    import mujoco
    opt.geomgroup[0] = colliders   # group 0 holds the collision primitives; group 1 the CAD meshes
    opt.flags[mujoco.mjtVisFlag.mjVIS_CONTACTPOINT] = on
    opt.flags[mujoco.mjtVisFlag.mjVIS_CONTACTFORCE] = on


def window(run: Run, args) -> tuple[float, float]:
    t0 = run.t_min if args.start is None else max(args.start, run.t_min)
    t1 = run.t_max if args.end is None else min(args.end, run.t_max)
    if t1 <= t0:
        raise SystemExit(f"empty window: start={t0:.4f} end={t1:.4f} (run spans {run.t_min:.4f}.."
                         f"{run.t_max:.4f} s)")
    return t0, t1


def free_camera(run: Run, args, t0: float, t1: float):
    import mujoco
    rows = np.unique([run.row_at(t) for t in np.linspace(t0, t1, 12)])
    lo, hi = run.framing(rows)
    center = (lo + hi) / 2
    dist = run.fit_distance(lo, hi, args.azimuth, args.elevation, args.width / args.height)
    run.style_contacts(np.unique([run.row_at(t) for t in np.linspace(t0, t1, 40)]), args.force_scale)
    cam = mujoco.MjvCamera()
    cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    cam.lookat[:] = args.lookat if args.lookat is not None else center
    cam.distance = args.distance if args.distance is not None else dist
    cam.azimuth, cam.elevation = args.azimuth, args.elevation
    return cam


def summarize(run: Run, args, t0, t1, times, rows) -> str:
    phases = sorted({run.phase_at(int(r)) for r in rows}, key=run.phase_names.index)
    return (f"run {run.run_dir}\n"
            f"  states: {len(run.times)} rows, dt~{(run.times[1] - run.times[0]) * 1e6:.1f} us, "
            f"sim {run.t_min:.3f}..{run.t_max:.3f} s\n"
            f"  window: {t0:.3f}..{t1:.3f} s at speed {args.speed:g}x -> {len(times)} frames "
            f"at {args.fps:g} fps ({len(times) / args.fps:.1f} s of playback)\n"
            f"  phases in window: {len(phases)} ({phases[0]} .. {phases[-1]})")


# ---------------------------------------------------------------- video

def overlay(frame: np.ndarray, text: str) -> np.ndarray:
    from PIL import Image, ImageDraw, ImageFont
    img = Image.fromarray(frame)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=max(12, frame.shape[0] // 28))
    box = draw.textbbox((8, 8), text, font=font)
    draw.rectangle((box[0] - 6, box[1] - 4, box[2] + 6, box[3] + 4), fill=(0, 0, 0))
    draw.text((8, 8), text, font=font, fill=(255, 255, 255))
    return np.asarray(img)


def write_video(run: Run, args, t0: float, t1: float, times, rows) -> None:
    import mujoco
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit("ffmpeg not found on PATH (macOS: brew install ffmpeg)")
    out = Path(args.video).resolve()
    if run.run_dir.resolve() in out.parents:
        raise SystemExit("refusing to write the video inside the run directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    width, height = args.width // 2 * 2, args.height // 2 * 2   # yuv420p needs even sizes
    run.model.vis.global_.offwidth = max(width, int(run.model.vis.global_.offwidth))
    run.model.vis.global_.offheight = max(height, int(run.model.vis.global_.offheight))
    cam = free_camera(run, args, t0, t1)
    opt = mujoco.MjvOption()
    configure_contacts(opt, not args.no_contacts, run.colliders)
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{width}x{height}", "-r", f"{args.fps:g}", "-i", "-", "-an",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart",
           str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        with mujoco.Renderer(run.model, height=height, width=width) as renderer:
            for k, (t, row) in enumerate(zip(times, rows)):
                run.restore(int(row))
                renderer.update_scene(run.data, camera=cam, scene_option=opt)
                frame = overlay(renderer.render(),
                                f"t = {run.times[row]:.4f} s   {run.phase_at(int(row))}")
                proc.stdin.write(np.ascontiguousarray(frame).tobytes())
                if k % 50 == 0:
                    print(f"\rframe {k + 1}/{len(times)}", end="", flush=True)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    finally:
        rc = proc.wait()
    print()
    if rc != 0:
        raise SystemExit(f"ffmpeg exited with status {rc}")
    print(f"wrote {out}")


# ---------------------------------------------------------------- interactive

class Playback:
    """Shared between the viewer's key thread and the render loop."""

    def __init__(self, t0: float, t1: float, speed: float):
        self.t0, self.t1, self.speed = t0, t1, speed
        self.t = t0
        self.paused = False
        self.step = 0          # pending single-frame steps (+/-) while paused
        self.restart = False
        self.lock = threading.Lock()

    def on_key(self, keycode: int) -> None:
        with self.lock:
            if keycode == 32:
                self.paused = not self.paused
            elif keycode == 262 and self.paused:
                self.step += 1
            elif keycode == 263 and self.paused:
                self.step -= 1
            elif keycode == 91:
                self.speed /= 2
            elif keycode == 93:
                self.speed *= 2
            elif keycode in (82, 114):
                self.restart = True


def run_viewer(run: Run, args, t0: float, t1: float) -> None:
    import mujoco
    import mujoco.viewer
    pb = Playback(t0, t1, args.speed)
    cam = free_camera(run, args, t0, t1)
    try:
        viewer = mujoco.viewer.launch_passive(run.model, run.data, key_callback=pb.on_key)
    except RuntimeError as exc:
        if sys.platform == "darwin" and "mjpython" in str(exc):
            script = Path(sys.argv[0]).as_posix()
            raise SystemExit(
                "launch_passive needs mjpython on macOS. Run:\n  uv run --frozen --extra physics "
                f"mjpython {script} {' '.join(sys.argv[1:])}") from exc
        raise
    with viewer:
        viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        viewer.cam.lookat[:] = cam.lookat
        viewer.cam.distance, viewer.cam.azimuth = cam.distance, cam.azimuth
        viewer.cam.elevation = cam.elevation
        configure_contacts(viewer.opt, not args.no_contacts, run.colliders)
        print("space pause | left/right step (paused) | [ ] speed | r restart | close window to quit")
        last = time.perf_counter()
        last_print = 0.0
        while viewer.is_running():
            now = time.perf_counter()
            dt, last = now - last, now
            with pb.lock:
                frame_dt = pb.speed / DISPLAY_FPS
                if pb.restart:
                    pb.t, pb.restart = pb.t0, False
                if pb.paused:
                    pb.t += pb.step * frame_dt
                    pb.step = 0
                else:
                    pb.t += dt * pb.speed
                if pb.t > pb.t1:
                    pb.t = pb.t0                     # loop
                pb.t = min(max(pb.t, pb.t0), pb.t1)
                t, speed, paused = pb.t, pb.speed, pb.paused
            row = run.row_at(t)
            with viewer.lock():
                run.restore(row)
            viewer.sync()
            if now - last_print > 0.1:
                last_print = now
                print(f"\rt={run.times[row]:8.4f} s  phase={run.phase_at(row):<14} "
                      f"speed={speed:g}x{'  [paused]' if paused else '          '}",
                      end="", flush=True)
            time.sleep(max(0.0, 1 / DISPLAY_FPS - (time.perf_counter() - now)))
    print()


# ---------------------------------------------------------------- mjpython

REEXEC_ENV = "POCKY_PREVIEW_REEXEC"


def ensure_mjpython_libpython() -> None:
    """Link the interpreter's libpython into the MuJoCo mjpython app bundle (macOS only).

    mjpython dlopens `@executable_path/../lib/libpythonX.Y.dylib`, which resolves inside the app
    bundle, so a uv-managed (python-build-standalone) interpreter needs a link there. Reinstalling
    mujoco removes the link, so this runs again whenever interactive mode starts.
    """
    if sys.platform != "darwin":
        return
    import mujoco
    name = f"libpython{sys.version_info[0]}.{sys.version_info[1]}.dylib"
    real = Path(sys.base_prefix) / "lib" / name
    contents = Path(mujoco.__file__).parent / "MuJoCo_(mjpython).app" / "Contents"
    if not real.is_file() or not contents.is_dir():
        return  # framework or Homebrew Python: mjpython finds its own libpython
    link = contents / "lib" / name
    if link.is_symlink():
        if os.readlink(link) == str(real):
            return
        link.unlink()
        action = "repointed"
    elif link.exists():
        print(f"{link} is not a symlink; leaving it alone", file=sys.stderr)
        return
    else:
        action = "created"
    link.parent.mkdir(exist_ok=True)
    link.symlink_to(real)
    print(f"{action} {link} -> {real} (mjpython resolves libpython inside its app bundle)")


def under_mjpython() -> bool:
    import mujoco.viewer
    return mujoco.viewer._MJPYTHON is not None  # set by the mjpython launcher before user code runs


def relaunch_under_mjpython(argv: list[str]) -> None:
    """On macOS, re-exec this script under the venv's mjpython unless it already runs there."""
    if sys.platform != "darwin" or under_mjpython():
        ensure_mjpython_libpython()
        return
    script = Path(sys.argv[0]).as_posix()
    hint = f"uv run --frozen --extra physics mjpython {script} {' '.join(argv)}"
    if os.environ.get(REEXEC_ENV):
        print(f"still not running under mjpython after re-launch; run:\n  {hint}", file=sys.stderr)
        raise SystemExit(2)
    exe = Path(sys.executable).parent / "mjpython"
    if not exe.exists():
        found = shutil.which("mjpython")
        if found is None:
            print(f"mjpython not found next to {sys.executable} or on PATH; run:\n  {hint}",
                  file=sys.stderr)
            raise SystemExit(2)
        exe = Path(found)
    ensure_mjpython_libpython()
    os.environ[REEXEC_ENV] = "1"
    sys.stdout.flush()  # execv discards unflushed buffers
    sys.stderr.flush()
    os.execv(str(exe), [str(exe), str(Path(__file__).resolve()), *argv])


def parse_vec3(text: str) -> list[float]:
    try:
        vals = [float(v) for v in text.split(",")]
    except ValueError:
        vals = []
    if len(vals) != 3:
        raise argparse.ArgumentTypeError("expected x,y,z")
    return vals


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run_dir", type=Path, help="a `cad physics run` output directory")
    ap.add_argument("--video", metavar="OUT.mp4", help="render offscreen to an mp4 instead of opening a viewer")
    ap.add_argument("--dry-run", action="store_true", help="load the run, print the frame schedule, exit")
    ap.add_argument("--check-viewer", action="store_true",
                    help="interactive mode without a window: check the viewer imports under mjpython, exit")
    ap.add_argument("--speed", type=float, default=0.25, help="sim seconds per playback second (default 0.25)")
    ap.add_argument("--start", type=float, help="window start, sim seconds")
    ap.add_argument("--end", type=float, help="window end, sim seconds")
    ap.add_argument("--transparent", default="", metavar="BODY[,BODY]",
                    help="make these bodies' geoms semi-transparent, e.g. body,lip")
    ap.add_argument("--no-contacts", action="store_true", help="hide contact points and forces")
    ap.add_argument("--force-scale", type=float, default=1.0, help="multiply the contact-force arrow length")
    ap.add_argument("--colliders", action="store_true", help="also show the collision primitives")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=float, default=30.0, help="video frame rate (default 30)")
    ap.add_argument("--azimuth", type=float, default=120.0)
    ap.add_argument("--elevation", type=float, default=-20.0)
    ap.add_argument("--distance", type=float, help="default: framed from the model extent")
    ap.add_argument("--lookat", type=parse_vec3, metavar="x,y,z", help="default: assembly centre")
    args = ap.parse_args(argv)
    if args.speed <= 0 or args.fps <= 0:
        ap.error("--speed and --fps must be positive")
    if not (args.video or args.dry_run):
        relaunch_under_mjpython(sys.argv[1:] if argv is None else argv)

    run = Run(args.run_dir, [n for n in args.transparent.split(",") if n], args.colliders)
    t0, t1 = window(run, args)
    fps = args.fps if args.video or args.dry_run else DISPLAY_FPS
    times, rows = schedule(run, t0, t1, args.speed, fps)
    args.fps = fps
    print(summarize(run, args, t0, t1, times, rows))
    if args.dry_run:
        run.restore(int(rows[0]))
        cam = free_camera(run, args, t0, t1)
        print(f"  camera: lookat={np.round(cam.lookat, 4).tolist()} distance={cam.distance:.3f} m")
        return 0
    if args.check_viewer:
        print(f"OK: viewer imports (mjpython={under_mjpython()}, interpreter={sys.executable})")
        return 0
    if args.video:
        write_video(run, args, t0, t1, times, rows)
    else:
        run_viewer(run, args, t0, t1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
