"""Helpers for GUI service tests that need an isolated repo: a copy of ``cadkit`` plus a tiny project.

The service runs in a subprocess whose repo root is the copy, so its project discovery, its
watcher and its build subprocesses all see only the tiny project that the test is free to edit.
"""
from __future__ import annotations

import http.client
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from cadkit.params import REPO_ROOT

PROJECT = "tiny"

_BOX_MODEL = '''\
from build123d import Align, Box

from cadkit.model import ModelPart

SIZE = {size}


def build(p):
    shape = Box(SIZE, 20, 30, align=(Align.MIN, Align.MIN, Align.MIN))
    return {{"box": ModelPart(shape)}}
'''

_PARAMS = '''\
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cadkit.params import Material, Overridable, Printer, load_sections

DEFAULT_PARAMS_PATH = Path(__file__).resolve().parent / "params.toml"


@dataclass(frozen=True)
class Structure:
    min_wall: float


@dataclass(frozen=True)
class Params(Overridable):
    structure: Structure
    printer: Printer
    material: Material


def load_params(path=DEFAULT_PARAMS_PATH):
    return load_sections(path, Params)
'''

_PARAMS_TOML = '''\
[structure]
min_wall = 1.0

[printer]
bed_x = 360
bed_y = 360
bed_z = 360

[material]
name = "PETG"
density_g_cm3 = 1.27
filament_d = 1.75
'''

_INIT = '''\
from cadkit.project import Project

from . import models
from .params import DEFAULT_PARAMS_PATH, load_params

PROJECT = Project(name="tiny", params_path=DEFAULT_PARAMS_PATH, load_params=load_params,
                  models=models)
'''

# Replaces the build subprocess: logs the start, optionally sleeps, then publishes a scene.
STUB_BUILD = '''\
import json, os, sys, time

args = sys.argv
out = args[args.index("--out") + 1]
with open(os.environ["STUB_LOG"], "a") as fh:
    fh.write(f"{time.time()} {args[1]}\\n")
try:
    delay = float(open(os.environ["STUB_SLEEP"]).read())
except (OSError, ValueError):
    delay = 0.0
time.sleep(delay)
scene = os.path.join(out, "scene")
os.makedirs(scene, exist_ok=True)
tmp = os.path.join(scene, ".scene.tmp")
with open(tmp, "w") as fh:
    json.dump({"stub": time.time()}, fh)
os.replace(tmp, os.path.join(scene, "scene.json"))
print(json.dumps({"scene": os.path.join(scene, "scene.json"), "checks": {}, "written": []}))
'''

LAUNCHER = '''\
import json, os, sys, time
from pathlib import Path

repo = Path(sys.argv[1])
opts = json.loads(sys.argv[2])
sys.path.insert(0, str(repo))
os.chdir(repo)
from cadkit.gui import server

if opts.pop("stub", False):
    server._build_command = lambda spec, sets: [sys.executable, os.environ["STUB_BUILD"], spec]
svc = server.GuiService(repo_root=repo, out_root=repo / "out", port=0, quiet=True, **opts)
svc.start()
print(json.dumps({"port": svc.port, "token": svc.token}), flush=True)
while True:
    time.sleep(1)
'''


def make_repo(root: Path, size: float = 10.0) -> Path:
    """Copy ``cadkit`` into ``root/repo`` and add the ``tiny`` project with models ``box``/``box2``."""
    repo = root / "repo"
    shutil.copytree(REPO_ROOT / "cadkit", repo / "cadkit",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "node_modules"))
    proj = repo / "projects"
    (proj / PROJECT / "models").mkdir(parents=True)
    (proj / "__init__.py").write_text("")
    (proj / PROJECT / "__init__.py").write_text(_INIT)
    (proj / PROJECT / "params.py").write_text(_PARAMS)
    (proj / PROJECT / "params.toml").write_text(_PARAMS_TOML)
    (proj / PROJECT / "models" / "__init__.py").write_text("")
    for name in ("box", "box2"):
        (proj / PROJECT / "models" / f"{name}.py").write_text(_BOX_MODEL.format(size=size))
    return repo


def child_env(**extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("POCKY_POSE", "PYTHONPATH")}
    env["PATH"] = f"{Path.home() / '.local' / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    env.update(extra)
    return env


class Sse:
    """Collects ``/v1/events`` into ``self.events`` (each with a ``t`` receive time)."""

    def __init__(self, svc: "TinyService") -> None:
        self.events: list[dict] = []
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._conn = http.client.HTTPConnection("127.0.0.1", svc.port, timeout=60)
        self._svc = svc
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()
        assert self._ready.wait(10), "SSE did not connect"

    def _read(self) -> None:
        self._conn.request("GET", f"/v1/events?token={self._svc.token}")
        resp = self._conn.getresponse()
        assert resp.status == 200
        self._ready.set()
        current: dict = {}
        try:
            while not self._stop.is_set():
                line = resp.fp.readline()
                if not line:
                    break
                text = line.decode("utf-8").rstrip("\n")
                if not text:
                    if current:
                        current["t"] = time.monotonic()
                        self.events.append(current)
                    current = {}
                    continue
                key, _, value = text.partition(": ")
                if key == "event":
                    current["event"] = value
                elif key == "data":
                    current["data"] = json.loads(value)
        except (OSError, ValueError, http.client.HTTPException):
            pass

    def artifacts(self, kind: str | None = None, since: int = 0) -> list[dict]:
        out = [e["data"] for e in self.events[since:] if e.get("event") == "artifact"]
        return [d for d in out if kind is None or d.get("kind") == kind]

    def job_ids(self, since: int = 0) -> set[str]:
        return {e["data"]["job"]["id"] for e in self.events[since:] if e.get("event") == "job"}

    def close(self) -> None:
        self._stop.set()
        try:
            self._conn.sock.shutdown(2)  # type: ignore[union-attr]
        except (OSError, AttributeError):
            pass
        self._conn.close()


class TinyService:
    """A ``GuiService`` subprocess rooted at an isolated tiny repo."""

    def __init__(self, repo: Path, work: Path, *, stub: bool, **opts) -> None:
        self.repo, self.work = repo, work
        self.calls_log = work / "calls.log"
        self.sleep_file = work / "stub_sleep"
        (work / "stub_build.py").write_text(STUB_BUILD)
        (work / "launcher.py").write_text(LAUNCHER)
        env = child_env(STUB_LOG=str(self.calls_log), STUB_SLEEP=str(self.sleep_file),
                        STUB_BUILD=str(work / "stub_build.py"))
        self.stderr = open(work / "service.stderr", "w")
        self.proc = subprocess.Popen(
            [sys.executable, str(work / "launcher.py"), str(repo),
             json.dumps({"stub": stub, **opts})],
            cwd=repo, env=env, stdout=subprocess.PIPE, stderr=self.stderr, text=True)
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("service did not start: " + (work / "service.stderr").read_text())
        doc = json.loads(line)
        self.port, self.token = doc["port"], doc["token"]

    def req(self, method, path, *, body=None, token=True, raw_body=None, timeout=60):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = raw_body
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        try:
            conn.request(method, path, body=data, headers=headers)
            resp = conn.getresponse()
            payload = resp.read()
            try:
                doc = json.loads(payload) if payload else None
            except ValueError:
                doc = None
            return resp.status, doc, dict(resp.getheaders())
        finally:
            conn.close()

    def wait_job(self, job_id, timeout=120):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status, doc, _ = self.req("GET", f"/v1/jobs/{job_id}")
            assert status == 200, doc
            if doc["job"]["status"] in ("succeeded", "failed", "cancelled"):
                return doc["job"]
            time.sleep(0.05)
        raise AssertionError(f"job {job_id} did not finish")

    def calls(self) -> list[float]:
        try:
            lines = self.calls_log.read_text().splitlines()
        except OSError:
            return []
        return [float(line.split()[0]) for line in lines if line.strip()]

    def close(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.stderr.close()


def edit_source(repo: Path, n: int, model: str = "box") -> float:
    """Append a distinct comment to a model file (changes mtime and size); returns ``time.time()``."""
    path = repo / "projects" / PROJECT / "models" / f"{model}.py"
    with open(path, "a") as fh:
        fh.write(f"# edit {n} {'x' * n}\n")
    return time.time()


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)
