"""Authenticated local GUI service: ``cad gui serve`` on 127.0.0.1.

Artifact contracts (plan-gui.md section 3.1)

**Scene** (``out/<project>/<model>/scene/``, written by ``cad gui scene <model>``):
- ``scene.json`` contains:
  - ``schemaVersion: 1``, ``project``, ``model``, ``units: "mm"``;
  - provenance: git commit, a dirty flag, a params-file sha256, ``--set`` overrides, and the build time;
  - ``parts[]``, each with ``id`` (the ``ModelPart`` key), ``name``, ``mesh`` (relative ``.glb`` path), bbox (min/max mm), volume in mm³, and a colour;
  - an optional ``printPose`` 4×4 per part.
- ``parts/<id>.glb`` holds the part in **assembly coordinates**, tessellated once.

**Trajectory** (``<run>/../<run-name>.gui/``, written by ``cad gui trajectory RUN_DIR``; the run dir itself is never written to):
- ``trajectory.json`` contains:
  - ``schemaVersion: 1``, ``units: "mm"``, the run id, and the source ``manifest.json`` sha256;
  - ``bodies[]``, each with ``name``, a list of meshes (geom name, ``.glb`` path, local pose) and ``fixed`` (welded to the world);
  - ``phases[]`` (name, t0, t1);
  - ``frameCount``, ``times``, and a pointer to the poses.
- ``poses.bin`` is little-endian float32, ``[frame][body][x,y,z,qw,qx,qy,qz]``, positions in mm. It is sampled at a fixed fps (default 60 sim-fps) from ``states.npz``.
- ``contacts.bin`` (optional) holds per-frame contact points and normal forces.
- Body meshes come from the run's ``assets/*.stl``. The geom-to-body mapping comes from compiling the run's ``scene.xml``.

**Service discovery:** ``out/.gui/service.json`` with pid, port, token, protocol version, repo root, start time and mode ``0600``.

Service surface (plan-gui.md section 3.2; ``schemaVersion`` on every response)

| Endpoint | Purpose |
|---|---|
| ``GET /v1/health`` | identity, protocol version, repo root (no token needed; no secrets) |
| ``GET /v1/models`` | ``cad list`` as JSON |
| ``GET /v1/models/{project}/{model}/scene`` | latest scene manifest, or 404 with the command that would build it |
| ``POST /v1/models/{project}/{model}/build`` | job: build, check, then scene export |
| ``GET /v1/runs`` | physics run dirs found under ``out/`` (has ``summary.json`` and ``states.npz``), newest first |
| ``GET /v1/runs/{runId}/trajectory`` | trajectory manifest (exports on first request) |
| ``POST /v1/runs`` | job: ``cad physics run`` with a scenario, acceptance and options chosen from files already in the project |
| ``GET /v1/jobs/{id}``, ``POST /v1/jobs/{id}/cancel`` | job state, log tail, artifacts |
| ``GET /v1/artifacts/{path}`` | stream a file **only** from ``out/<project>/…/scene/`` or a ``.gui/`` trajectory dir, after canonicalising the path |
| ``GET /v1/events`` | SSE stream of job and artifact changes |
| ``POST /v1/open`` | create a one-time open request for ``{model}``, ``{run}`` or ``{}`` (``cad gui open``) |
| ``GET /v1/open/{id}`` | claim an open request (single use): its target and the repo root |
| ``POST /v1/open/{id}/ack``, ``POST /v1/open/{id}/nack`` | the editor opened the target, or refused with ``{reason}`` |
| ``GET /v1/open/{id}/status`` | ``pending``, ``claimed``, ``acked``, ``nacked`` (with reason) or ``expired`` |
| ``GET /`` | the built ``ui/dist`` |

Rules:
- Every non-health route requires ``Authorization: Bearer <token>``, or the ``?token=`` query the server gives the browser on open.
- Requests whose ``Host`` isn't ``127.0.0.1:<port>`` or ``localhost:<port>`` are rejected.
- Requests with an ``Origin`` other than the server's own are rejected.
- Jobs on the same model or run queue one at a time, and read-only viewers are unlimited.
- A failed job never replaces the last good scene or trajectory; the old one is returned marked ``stale: true``.

Deviations and response details

- ``GET /`` and the ``ui/dist`` static files skip the token check: browser subresource loads cannot
  carry a bearer token, and the built bundle is public build output. They still get the Host and
  Origin checks, and every ``/v1/*`` route except health still requires the token.
- JSON bodies carry ``schemaVersion: 1`` plus the keys documented per route below. Errors are
  ``{"schemaVersion": 1, "error": "<message>"}`` (plus extra keys where noted).
- ``runId`` is a POSIX path relative to ``out/``. Trajectory artifacts live beside the run in
  ``<run>.gui/``, so their artifact path is ``<runId>.gui/<file>``.
- A build job with a failing check leaves the previous scene in place and marks it ``stale``.
  In-process OCCT work cannot be interrupted, so only physics jobs can be cancelled.
- ``GET /v1/models/{project}/{model}/physics-inputs`` (token required) lists the files a run may
  use: ``scenarios`` (``physics/scenarios/*.json``), ``acceptance`` (``physics/*_acceptance.json``)
  and ``options`` (``physics/options/*.toml``), each entry ``{"name", "path"}`` with ``path``
  relative to the repo root. Only regular, non-symlink files inside the project are listed.
- ``POST /v1/runs`` accepts a scenario, acceptance or options path only when it is in that
  listing, spelled repo-relative (as listed) or project-relative. Traversal, absolute and
  outside-project paths are 403, a missing file is 400, and an existing unlisted file is 403.

Open requests (``cad gui open``; all token-protected, held in memory only)

- ``POST /v1/open`` takes at most one of ``{"model": "<project>/<model>"}`` (must resolve, else
  404) or ``{"run": "<runId>"}`` (validated like the trajectory route: 403 for unsafe paths, 404
  unless it is a run dir under ``out/``); ``{}`` opens the GUI with no target. 201
  ``{id, expiresAt, target}``, where ``target`` is ``{"model"}``, ``{"run"}`` or ``null`` and
  ``expiresAt`` is epoch seconds. Ids are random, single use, and expire ``OPEN_TTL_S`` (60 s)
  after creation.
- ``GET /v1/open/{id}`` claims a pending request: 200 ``{id, target, repoRoot}``. Unknown,
  already claimed or resolved ids are 404; an expired one is 410.
- ``POST /v1/open/{id}/ack`` (empty body) is accepted only for a claimed request;
  ``POST /v1/open/{id}/nack`` with ``{"reason": str}`` for a pending or claimed one (the CLI nacks
  its own request when it stops waiting, so a late claim cannot open a second view). Either
  answers 200 ``{id, state, reason}``; a resolved request is 409, expired 410, unknown 404.
- ``GET /v1/open/{id}/status`` answers 200 ``{id, state, reason, expiresAt}``; resolved requests
  stay queryable for ``OPEN_RETAIN_S`` after expiry, then answer 404.
"""
from __future__ import annotations

import collections
import contextlib
import hashlib
import hmac
import http.server
import json
import math
import os
import queue
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..params import REPO_ROOT
from ..project import Project, all_models, discover, list_models, load_model, resolve

PROTOCOL_VERSION = 1
SCHEMA_VERSION = 1
LOG_TAIL = 200
MAX_BODY_BYTES = 64 * 1024
ARTIFACT_CHUNK = 64 * 1024
KEEPALIVE_S = 15.0
_HEALTH_TIMEOUT_S = 2.0
_KILL_GRACE_S = 5.0

_SEGMENT = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
_MODEL_SCENE = re.compile(r"^/v1/models/([^/]+)/([^/]+)/scene$")
_MODEL_BUILD = re.compile(r"^/v1/models/([^/]+)/([^/]+)/build$")
_MODEL_INPUTS = re.compile(r"^/v1/models/([^/]+)/([^/]+)/physics-inputs$")
_RUN_TRAJECTORY = re.compile(r"^/v1/runs/(.+)/trajectory$")
_JOB = re.compile(r"^/v1/jobs/([^/]+)$")
_JOB_CANCEL = re.compile(r"^/v1/jobs/([^/]+)/cancel$")
_ARTIFACT = re.compile(r"^/v1/artifacts/(.*)$")
_OPEN = re.compile(r"^/v1/open/([^/]+)$")
_OPEN_ACTION = re.compile(r"^/v1/open/([^/]+)/(ack|nack|status)$")
_OPEN_ID = re.compile(r"^[A-Za-z0-9_-]{16,128}$")

OPEN_TTL_S = 60.0
OPEN_RETAIN_S = 300.0
MAX_OPEN_REQUESTS = 256
MAX_REASON_CHARS = 500

_CAD_LOCK = threading.Lock()

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".map": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".wasm": "application/wasm",
    ".woff2": "font/woff2",
}

_FALLBACK_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>CADStudio GUI</title></head>
<body><h1>CADStudio GUI</h1>
<p>The GUI is not built. Run:</p>
<pre>cd ui &amp;&amp; npm ci &amp;&amp; npm run build</pre>
</body></html>
"""


class _HttpError(Exception):
    """A request failure that becomes a JSON error response."""

    def __init__(self, status: int, message: str, **extra):
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra


@dataclass
class Job:
    """One queued build or physics run; the log keeps only the last ``LOG_TAIL`` lines."""

    kind: str
    key: str
    model: str
    status: str = "queued"
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    createdAt: float = field(default_factory=time.time)
    startedAt: float | None = None
    finishedAt: float | None = None
    error: str | None = None
    exitCode: int | None = None
    log: collections.deque = field(default_factory=lambda: collections.deque(maxlen=LOG_TAIL))
    artifacts: dict = field(default_factory=dict)
    payload: dict = field(default_factory=dict, repr=False)
    _proc: subprocess.Popen | None = field(default=None, repr=False)
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)
    _proc_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _terminating: bool = field(default=False, repr=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "key": self.key,
            "model": self.model,
            "status": self.status,
            "createdAt": self.createdAt,
            "startedAt": self.startedAt,
            "finishedAt": self.finishedAt,
            "error": self.error,
            "exitCode": self.exitCode,
            "log": list(self.log),
            "artifacts": dict(self.artifacts),
        }


class EventBus:
    """Fan-out of job and artifact events to SSE subscribers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: set[queue.Queue] = set()
        self._next = 0

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._subscribers.add(q)
        return q

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def publish(self, event: str, data: dict) -> None:
        with self._lock:
            self._next += 1
            message = {"id": self._next, "event": event, "data": data}
            subscribers = list(self._subscribers)
        for q in subscribers:
            q.put_nowait(message)


class JobQueue:
    """FIFO jobs per model key; one worker thread drains a key at a time."""

    def __init__(self, service: GuiService) -> None:
        self.service = service
        self._lock = threading.Lock()
        self._pending: dict[str, collections.deque[Job]] = {}
        self._active: set[str] = set()

    def submit(self, job: Job) -> None:
        self.service.jobs[job.id] = job
        with self._lock:
            self._pending.setdefault(job.key, collections.deque()).append(job)
            if job.key in self._active:
                start = False
            else:
                self._active.add(job.key)
                start = True
        self.service.publish("job", {"job": job.to_dict()})
        if start:
            threading.Thread(target=self._drain, args=(job.key,), daemon=True,
                             name=f"cadgui-{job.key}").start()

    def _drain(self, key: str) -> None:
        while True:
            with self._lock:
                pending = self._pending.get(key)
                if not pending:
                    self._pending.pop(key, None)
                    self._active.discard(key)
                    return
                job = pending.popleft()
            self.service.run_job(job)


class OpenRequestError(Exception):
    """An open-request operation refused with an HTTP status (404, 409, 410 or 429)."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class OpenRequest:
    """One ``cad gui open`` request; ``target`` is ``{"model": ...}``, ``{"run": ...}`` or None."""

    id: str
    target: dict | None
    createdAt: float
    expiresAt: float
    state: str = "pending"
    reason: str | None = None

    def to_status(self) -> dict:
        return {"id": self.id, "state": self.state, "reason": self.reason,
                "expiresAt": self.expiresAt}


class OpenRequestStore:
    """In-memory, single-use open requests with an injectable clock and id source.

    ``pending`` -> ``claimed`` (``claim``) -> ``acked`` (``ack``) or ``nacked`` (``nack``, also
    from ``pending``). An unresolved request becomes ``expired`` at ``expiresAt``; every entry is
    forgotten ``retain_s`` after that.
    """

    def __init__(self, *, ttl_s: float = OPEN_TTL_S, retain_s: float = OPEN_RETAIN_S,
                 max_requests: int = MAX_OPEN_REQUESTS, clock=time.time,
                 make_id=lambda: secrets.token_urlsafe(18)) -> None:
        self.ttl_s = ttl_s
        self.retain_s = retain_s
        self.max_requests = max_requests
        self._clock = clock
        self._make_id = make_id
        self._lock = threading.Lock()
        self._requests: dict[str, OpenRequest] = {}

    def create(self, target: dict | None) -> OpenRequest:
        with self._lock:
            now = self._prune()
            if len(self._requests) >= self.max_requests:
                raise OpenRequestError(429, "too many open requests")
            request_id = self._make_id()
            while request_id in self._requests:
                request_id = self._make_id()
            request = OpenRequest(id=request_id, target=dict(target) if target else None,
                                  createdAt=now, expiresAt=now + self.ttl_s)
            self._requests[request_id] = request
            return request

    def claim(self, request_id: str) -> OpenRequest:
        """Hand the request out once; any later claim is refused."""
        with self._lock:
            request = self._get(request_id)
            if request.state == "expired":
                raise OpenRequestError(410, "open request expired")
            if request.state != "pending":
                raise OpenRequestError(404, "unknown or already claimed open request")
            request.state = "claimed"
            return request

    def ack(self, request_id: str) -> OpenRequest:
        with self._lock:
            request = self._resolvable(request_id, ("claimed",))
            request.state = "acked"
            return request

    def nack(self, request_id: str, reason: str) -> OpenRequest:
        with self._lock:
            request = self._resolvable(request_id, ("pending", "claimed"))
            request.state = "nacked"
            request.reason = reason
            return request

    def status(self, request_id: str) -> dict:
        with self._lock:
            return self._get(request_id).to_status()

    def _resolvable(self, request_id: str, states: tuple[str, ...]) -> OpenRequest:
        request = self._get(request_id)
        if request.state == "expired":
            raise OpenRequestError(410, "open request expired")
        if request.state not in states:
            raise OpenRequestError(409, f"open request is {request.state}")
        return request

    def _get(self, request_id: str) -> OpenRequest:
        self._prune()
        request = self._requests.get(request_id)
        if request is None:
            raise OpenRequestError(404, "unknown or already claimed open request")
        return request

    def _prune(self) -> float:
        """Expire overdue unresolved requests and forget old ones; returns the clock reading."""
        now = self._clock()
        for request_id, request in list(self._requests.items()):
            if request.state in ("pending", "claimed") and now >= request.expiresAt:
                request.state = "expired"
            if now >= request.expiresAt + self.retain_s:
                del self._requests[request_id]
        return now


class GuiService:
    """The loopback HTTP service, its job table and its discovery record."""

    def __init__(self, *, repo_root=REPO_ROOT, out_root=None, port: int = 0,
                 quiet: bool = False) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.out_root = Path(out_root) if out_root is not None else self.repo_root / "out"
        self.out_root = self.out_root.resolve()
        self.token = secrets.token_urlsafe(32)
        self.quiet = quiet
        self.stop_event = threading.Event()
        self.jobs: dict[str, Job] = {}
        self.scene_state: dict[tuple[str, str], dict] = {}
        self.run_locks: dict[str, threading.Lock] = {}
        self._run_locks_lock = threading.Lock()
        self._project_names: set[str] | None = None
        self._started = False
        self._thread: threading.Thread | None = None
        self.discovery: dict | None = None

        self.events = EventBus()
        self.queue = JobQueue(self)
        self.open_requests = OpenRequestStore()
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", port), _Handler)
        self.server.daemon_threads = True
        self.server.service = self
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/?token={self.token}"

    # -- lifecycle ---------------------------------------------------------------------

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True,
                                        name="cadgui-server")
        self._thread.start()

    def close(self) -> None:
        self.stop_event.set()
        for job in list(self.jobs.values()):
            if job.status == "queued":
                job.status = "cancelled"
                job.finishedAt = time.time()
            elif job.kind == "run" and job.status == "running":
                _kill(job)
        if self._started:
            self.server.shutdown()
        self.server.server_close()
        self._started = False
        self._remove_discovery()

    # -- discovery ---------------------------------------------------------------------

    @property
    def discovery_path(self) -> Path:
        return discovery_path(self.out_root)

    def write_discovery(self) -> dict:
        doc = {
            "schemaVersion": SCHEMA_VERSION,
            "pid": os.getpid(),
            "port": self.port,
            "token": self.token,
            "protocolVersion": PROTOCOL_VERSION,
            "repoRoot": str(self.repo_root),
            "startedAt": _utc_now(),
            "url": self.url,
        }
        gui_dir = self.discovery_path.parent
        gui_dir.mkdir(parents=True, exist_ok=True)
        try:
            gui_dir.chmod(0o700)
        except OSError:
            pass
        tmp = gui_dir / f".service.json.{os.getpid()}.{secrets.token_hex(4)}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.chmod(tmp, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(doc, indent=2) + "\n")
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
        os.replace(tmp, self.discovery_path)
        self.discovery = doc
        return doc

    def _remove_discovery(self) -> None:
        current = read_discovery(self.out_root)
        if not current:
            return
        if current.get("pid") != os.getpid() or current.get("token") != self.token:
            return
        with contextlib.suppress(OSError):
            self.discovery_path.unlink()

    # -- events and jobs ---------------------------------------------------------------

    def publish(self, event: str, data: dict) -> None:
        self.events.publish(event, data)

    def run_job(self, job: Job) -> None:
        if job.status == "cancelled":
            job.finishedAt = time.time()
            self.publish("job", {"job": job.to_dict()})
            return
        job.status = "running"
        job.startedAt = time.time()
        self.publish("job", {"job": job.to_dict()})
        try:
            if job.kind == "build":
                project = job.payload["project"]
                _build_model(self, job, project, job.payload["model"], job.payload["sets"])
                job.artifacts = {"scene": f"{job.key}/scene/scene.json"}
                self.scene_state[(project.name, job.payload["model"])] = {
                    "stale": False, "error": None, "job": job.id}
                self.publish("artifact", {"kind": "scene", "model": job.key})
            else:
                _run_physics(self, job, job.payload["cmd"], job.payload["out"])
        except Exception as exc:  # a worker must never die
            job.status = "failed"
            job.error = str(exc)
            if job.kind == "build":
                project = job.payload["project"]
                self.scene_state[(project.name, job.payload["model"])] = {
                    "stale": True, "error": str(exc), "job": job.id}
        finally:
            if job.status == "running":
                job.status = "succeeded"
            job.finishedAt = time.time()
            self.publish("job", {"job": job.to_dict()})

    def cancel(self, job: Job) -> None:
        if job.status == "queued":
            job.status = "cancelled"
            job.finishedAt = time.time()
            self.publish("job", {"job": job.to_dict()})
            return
        if job.status != "running":
            raise _HttpError(409, f"job {job.id} is already {job.status}")
        if job.kind != "run":
            raise _HttpError(409, "running build jobs cannot be cancelled")
        job._cancel.set()
        job.status = "cancelled"
        _kill(job)
        self.publish("job", {"job": job.to_dict()})

    def project_names(self) -> set[str]:
        if self._project_names is None:
            self._project_names = set(discover())
        return self._project_names

    def run_lock(self, run_id: str) -> threading.Lock:
        with self._run_locks_lock:
            return self.run_locks.setdefault(run_id, threading.Lock())


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# -- discovery helpers -----------------------------------------------------------------


def discovery_path(out_root) -> Path:
    return Path(out_root) / ".gui" / "service.json"


def read_discovery(out_root) -> dict | None:
    """The discovery record, or ``None`` when it is missing or not a JSON object."""
    try:
        doc = json.loads(discovery_path(out_root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def _pid_alive(pid) -> bool:
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def existing_service(out_root, repo_root=REPO_ROOT) -> dict | None:
    """A registered service that is alive, for this repo, and answers its own health check."""
    doc = read_discovery(out_root)
    if not doc:
        return None
    if not _pid_alive(doc.get("pid")):
        return None
    root = str(Path(repo_root).resolve())
    if doc.get("repoRoot") != root:
        return None
    port = doc.get("port")
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/v1/health",
                         timeout=_HEALTH_TIMEOUT_S) as response:
            if response.status != 200:
                return None
            body = json.loads(response.read(MAX_BODY_BYTES).decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return None
    if not isinstance(body, dict) or body.get("repoRoot") != root:
        return None
    if body.get("pid") != doc.get("pid"):
        return None
    return doc


def start_service(*, repo_root=REPO_ROOT, out_root=None, port: int = 0,
                  quiet: bool = False) -> tuple[GuiService | None, dict]:
    """Reuse a healthy registered service, else start one and register it."""
    root = Path(repo_root).resolve()
    out = Path(out_root) if out_root is not None else root / "out"
    existing = existing_service(out, root)
    if existing is not None:
        return None, existing
    service = GuiService(repo_root=root, out_root=out, port=port, quiet=quiet)
    service.start()
    return service, service.write_discovery()


def run(*, port: int = 0, open_browser: bool = True, as_json: bool = False,
        repo_root=REPO_ROOT, out_root=None) -> int:
    """``cad gui serve``: print the URL, then serve until SIGINT/SIGTERM."""
    root = Path(repo_root).resolve()
    out = Path(out_root) if out_root is not None else root / "out"
    stop = threading.Event()

    def _handle(signum, frame) -> None:
        stop.set()

    previous = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            previous[sig] = signal.signal(sig, _handle)
        except (ValueError, OSError):
            pass
    try:
        return _run_service(root, out, port, open_browser, as_json, stop)
    finally:
        for sig, handler in previous.items():
            with contextlib.suppress(ValueError, OSError):
                signal.signal(sig, handler)


def _run_service(root: Path, out: Path, port: int, open_browser: bool, as_json: bool,
                 stop: threading.Event) -> int:
    service, record = start_service(repo_root=root, out_root=out, port=port)
    reused = service is None
    if service is None:
        service_url = record.get("url") or (
            f"http://127.0.0.1:{record['port']}/?token={record['token']}")
    else:
        service_url = service.url
    if as_json:
        print(json.dumps({
            "url": service_url,
            "port": record["port"],
            "pid": record["pid"],
            "repoRoot": record["repoRoot"],
            "discovery": str(discovery_path(out)),
            "reused": reused,
        }), flush=True)
    elif reused:
        print(f"cadstudio GUI already running: {service_url}", flush=True)
    else:
        print(f"cadstudio GUI: {service_url}", flush=True)
    if reused:
        return 0
    if open_browser:
        with contextlib.suppress(Exception):
            webbrowser.open(service_url)
    try:
        while not stop.wait(0.25):
            pass
    finally:
        service.close()
    return 0


# -- workers ---------------------------------------------------------------------------


def _coerce_sets(doc) -> dict:
    """``{"set": {key: number|string}}`` -> override mapping; anything else is a 400."""
    if doc is None:
        return {}
    if not isinstance(doc, dict):
        raise _HttpError(400, "body must be a JSON object")
    extra = set(doc) - {"set"}
    if extra:
        raise _HttpError(400, f"unexpected key(s): {', '.join(sorted(extra))}")
    sets = doc.get("set", {})
    if not isinstance(sets, dict):
        raise _HttpError(400, "set must be a JSON object")
    out: dict = {}
    for key, value in sets.items():
        if not isinstance(key, str) or not key:
            raise _HttpError(400, "set keys must be non-empty strings")
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise _HttpError(400, f"set value for {key!r} must be a number or string")
        if isinstance(value, str):
            try:
                out[key] = float(value)
            except ValueError:
                out[key] = value
        else:
            number = float(value)
            if not math.isfinite(number):
                raise _HttpError(400, f"set value for {key!r} must be finite")
            out[key] = number
    return out


def _build_model(service: GuiService, job: Job, project: Project, model: str,
                 sets: dict) -> None:
    """Build, export, check, then write the scene; raise on any failure."""
    from ..checks import has_failures, run_checks, write_report
    from ..export import export_assembly, export_part
    from ..params import override
    from .scene import write_scene

    with _CAD_LOCK:
        outdir = service.out_root / project.name / model
        outdir.mkdir(parents=True, exist_ok=True)
        p = project.load_params(project.params_path)
        if sets:
            try:
                p = override(p, sets)
            except KeyError as exc:
                raise RuntimeError(f"unknown parameter {exc}") from None
        parts = load_model(project, model).build(p)
        job.log.append(f"built {len(parts)} part(s)")
        for name, part in parts.items():
            for path in export_part(name, part, outdir).values():
                job.log.append(f"wrote {path.name}")
        assembly = export_assembly(parts, outdir)
        job.log.append(f"wrote {assembly.name}")
        results = {name: run_checks(name, part, p, project) for name, part in parts.items()}
        write_report(results, outdir)
        for name, checks in results.items():
            for result in checks:
                job.log.append(f"check {name} {result.name}: {result.status}")
        if has_failures(results):
            failures = ", ".join(f"{name}:{result.name}" for name, checks in results.items()
                                 for result in checks if result.status == "fail")
            raise RuntimeError(f"checks failed: {failures}")
        state = write_scene(f"{project.name}/{model}", sets=sets, out=outdir / "scene")
        job.log.append(f"wrote {state['scene'].name}")


def _physics_command(spec: str, scenario: str, acceptance: str, options: str | None,
                     out: str) -> list[str]:
    """The ``cad physics run`` command line for one job (tests stub this)."""
    cmd = [sys.executable, "-m", "cadkit.cli", "physics", "run", spec,
           "--scenario", str(scenario), "--acceptance", str(acceptance)]
    if options:
        cmd += ["--options", str(options)]
    return cmd + ["--out", str(out)]


def _terminate(proc: subprocess.Popen) -> None:
    """SIGTERM the job's process group, then SIGKILL after the grace period."""
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=_KILL_GRACE_S)
        return
    except subprocess.TimeoutExpired:
        pass
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        os.killpg(proc.pid, signal.SIGKILL)
    with contextlib.suppress(subprocess.TimeoutExpired, OSError):
        proc.wait(timeout=_KILL_GRACE_S)


def _kill(job: Job) -> None:
    """Terminate the job's process group once, whichever thread asks first."""
    with job._proc_lock:
        proc = job._proc
        if proc is None or job._terminating:
            return
        job._terminating = True
    _terminate(proc)


def _run_physics(service: GuiService, job: Job, cmd: list[str], out: Path) -> None:
    if job._cancel.is_set():
        job.status = "cancelled"
        return
    proc = subprocess.Popen(cmd, cwd=service.repo_root, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, start_new_session=True)
    with job._proc_lock:
        job._proc = proc
    if job._cancel.is_set():
        # Cancel arrived between the check above and the Popen: kill the fresh process.
        _kill(job)
    try:
        if proc.stdout is not None:
            for line in proc.stdout:
                job.log.append(line.rstrip("\n"))
        code = proc.wait()
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
        with job._proc_lock:
            job._proc = None
    job.exitCode = code
    if out.exists():
        job.artifacts = {"runId": _relative_to(out, service.out_root)}
        service.publish("artifact", {"kind": "run", "runId": job.artifacts["runId"]})
    if job.status == "cancelled" or job._cancel.is_set():
        job.status = "cancelled"
        return
    if code == 0:
        job.status = "succeeded"
    else:
        job.status = "failed"
        job.error = f"cad physics run exited with code {code}"


def _relative_to(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return path.as_posix()


# -- request handler -------------------------------------------------------------------


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "cadstudio-gui"
    sys_version = ""

    @property
    def service(self) -> GuiService:
        return self.server.service

    def log_message(self, fmt, *args) -> None:
        if self.service.quiet:
            return
        text = re.sub(r"\?[^\s\"]*", "", fmt % args)
        sys.stderr.write(f"{self.address_string()} - {text}\n")

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")

    def do_HEAD(self) -> None:
        self._handle("HEAD")

    def do_PUT(self) -> None:
        self._handle("PUT")

    def do_PATCH(self) -> None:
        self._handle("PATCH")

    def do_DELETE(self) -> None:
        self._handle("DELETE")

    def _handle(self, method: str) -> None:
        self._responded = False
        try:
            self._serve(method)
        except _HttpError as exc:
            self._error(exc.status, exc.message, **exc.extra)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # never leak a traceback to the client
            self._error(500, f"internal error: {exc}")

    def _error(self, status: int, message: str, **extra) -> None:
        if self._responded:  # headers already went out; closing the connection is all we can do
            return
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            self._send_error(status, message, **extra)

    def _serve(self, method: str) -> None:
        split = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(split.path)
        query = urllib.parse.parse_qs(split.query)
        self._check_host()
        self._check_origin()
        if path == "/v1/health":
            if method != "GET":
                raise _HttpError(405, "method not allowed")
            return self._health()
        if not path.startswith("/v1/"):
            if method != "GET":
                raise _HttpError(405, "method not allowed")
            return self._static(path)
        self._check_auth(query)

        match = _MODEL_SCENE.fullmatch(path)
        if match:
            return self._require(method, "GET") or self._model_scene(*match.groups())
        match = _MODEL_BUILD.fullmatch(path)
        if match:
            return self._require(method, "POST") or self._model_build(*match.groups())
        match = _MODEL_INPUTS.fullmatch(path)
        if match:
            return self._require(method, "GET") or self._model_inputs(*match.groups())
        match = _RUN_TRAJECTORY.fullmatch(path)
        if match:
            return self._require(method, "GET") or self._run_trajectory(match.group(1))
        match = _JOB_CANCEL.fullmatch(path)
        if match:
            return self._require(method, "POST") or self._job_cancel(match.group(1))
        match = _JOB.fullmatch(path)
        if match:
            return self._require(method, "GET") or self._job(match.group(1))
        match = _ARTIFACT.fullmatch(path)
        if match:
            return self._require(method, "GET") or self._artifact(match.group(1))
        if path == "/v1/models":
            return self._require(method, "GET") or self._models()
        if path == "/v1/runs":
            if method == "GET":
                return self._runs()
            if method == "POST":
                return self._start_run()
            raise _HttpError(405, "method not allowed")
        if path == "/v1/events":
            return self._require(method, "GET") or self._events()
        if path == "/v1/open":
            return self._require(method, "POST") or self._open_create()
        match = _OPEN_ACTION.fullmatch(path)
        if match:
            request_id, action = match.groups()
            return (self._require(method, "GET" if action == "status" else "POST")
                    or self._open_action(request_id, action))
        match = _OPEN.fullmatch(path)
        if match:
            return self._require(method, "GET") or self._open_claim(match.group(1))
        raise _HttpError(404, "not found")

    def _require(self, method: str, wanted: str) -> None:
        if method != wanted:
            raise _HttpError(405, "method not allowed")

    # -- checks and responses ----------------------------------------------------------

    def _check_host(self) -> None:
        allowed = {f"127.0.0.1:{self.service.port}", f"localhost:{self.service.port}"}
        if self.headers.get("Host") not in allowed:
            raise _HttpError(403, "bad Host header")

    def _check_origin(self) -> None:
        origin = self.headers.get("Origin")
        if origin is None:
            return
        allowed = {f"http://127.0.0.1:{self.service.port}",
                   f"http://localhost:{self.service.port}"}
        if origin not in allowed:
            raise _HttpError(403, "bad Origin header")

    def _check_auth(self, query: dict) -> None:
        token = None
        header = self.headers.get("Authorization") or ""
        scheme, _, value = header.partition(" ")
        if scheme.lower() == "bearer" and value:
            token = value.strip()
        if token is None:
            values = query.get("token") or []
            token = values[0] if values else None
        if not self._token_matches(token):
            raise _HttpError(401, "missing or invalid token")

    def _token_matches(self, candidate) -> bool:
        if not isinstance(candidate, str):
            return False
        try:
            return hmac.compare_digest(candidate.encode("utf-8"),
                                       self.service.token.encode("utf-8"))
        except (UnicodeError, TypeError):
            return False

    def _send_json(self, status: int, doc: dict, *, headers: dict | None = None) -> None:
        body = json.dumps({"schemaVersion": SCHEMA_VERSION, **doc},
                          allow_nan=False).encode("utf-8")
        self._responded = True
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_error(self, status: int, message: str, **extra) -> None:
        self._send_json(status, {"error": message, **extra})

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise _HttpError(400, "bad Content-Length") from None
        if length < 0 or length > MAX_BODY_BYTES:
            raise _HttpError(400, f"body exceeds {MAX_BODY_BYTES} bytes")
        raw = self.rfile.read(length) if length else b""
        if not raw.strip():
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise _HttpError(400, "body is not valid JSON") from None

    # -- routes ------------------------------------------------------------------------

    def _health(self) -> None:
        self._send_json(200, {
            "service": "cadstudio",
            "protocolVersion": PROTOCOL_VERSION,
            "repoRoot": str(self.service.repo_root),
            "pid": os.getpid(),
        })

    def _models(self) -> None:
        projects = [{"name": proj.name, "params_path": str(proj.params_path),
                     "models": list_models(proj)} for proj in discover().values()]
        self._send_json(200, {"projects": projects, "models": all_models()})

    def _model_scene(self, project_name: str, model: str) -> None:
        if not _SEGMENT.fullmatch(project_name) or not _SEGMENT.fullmatch(model):
            raise _HttpError(404, f"unknown model {project_name}/{model}")
        _resolve_or_404(f"{project_name}/{model}")
        scene_path = self.service.out_root / project_name / model / "scene" / "scene.json"
        if not scene_path.is_file():
            raise _HttpError(404, "no scene",
                             command=f"cad gui scene {project_name}/{model}")
        try:
            scene = json.loads(scene_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise _HttpError(500, f"scene.json is unreadable: {exc}") from None
        state = self.service.scene_state.get((project_name, model), {})
        self._send_json(200, {
            "project": project_name,
            "model": model,
            "stale": bool(state.get("stale", False)),
            "error": state.get("error"),
            "job": state.get("job"),
            "artifactBase": f"{project_name}/{model}/scene",
            "scene": scene,
        })

    def _model_build(self, project_name: str, model: str) -> None:
        if not _SEGMENT.fullmatch(project_name) or not _SEGMENT.fullmatch(model):
            raise _HttpError(404, f"unknown model {project_name}/{model}")
        project = _resolve_or_404(f"{project_name}/{model}")
        sets = _coerce_sets(self._read_body())
        job = Job(kind="build", key=f"{project.name}/{model}", model=f"{project.name}/{model}")
        job.payload = {"project": project, "model": model, "sets": sets}
        self.service.queue.submit(job)
        self._send_json(202, {"job": job.to_dict()})

    def _model_inputs(self, project_name: str, model: str) -> None:
        if not _SEGMENT.fullmatch(project_name) or not _SEGMENT.fullmatch(model):
            raise _HttpError(404, f"unknown model {project_name}/{model}")
        project = _resolve_or_404(f"{project_name}/{model}")
        listing = _physics_inputs(project, self.service.repo_root)
        self._send_json(200, {
            "project": project.name,
            "model": model,
            **{key: [{"name": entry.name, "path": entry.path} for entry in entries]
               for key, entries in listing.items()},
        })

    def _job(self, job_id: str) -> None:
        job = self.service.jobs.get(job_id)
        if job is None:
            raise _HttpError(404, f"unknown job {job_id}")
        self._send_json(200, {"job": job.to_dict()})

    def _job_cancel(self, job_id: str) -> None:
        job = self.service.jobs.get(job_id)
        if job is None:
            raise _HttpError(404, f"unknown job {job_id}")
        self.service.cancel(job)
        self._send_json(200, {"job": job.to_dict()})

    def _runs(self) -> None:
        root = self.service.out_root
        runs = []
        if root.is_dir():
            for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
                dirnames[:] = sorted(d for d in dirnames
                                     if not d.startswith(".") and not d.endswith(".gui")
                                     and not (Path(dirpath) / d).is_symlink())
                current = Path(dirpath)
                if current == root or current.is_symlink():
                    continue
                if "summary.json" not in filenames or "states.npz" not in filenames:
                    continue
                if (current / "summary.json").is_symlink() or (current / "states.npz").is_symlink():
                    continue
                status = None
                with contextlib.suppress(OSError, ValueError):
                    status = json.loads((current / "summary.json").read_text(
                        encoding="utf-8")).get("status")
                modified = None
                with contextlib.suppress(OSError):
                    modified = (current / "summary.json").stat().st_mtime
                runs.append({"runId": current.relative_to(root).as_posix(),
                             "path": str(current), "status": status, "modified": modified})
        # Most recent first (by summary.json mtime); ties and unreadable times fall back to runId.
        runs.sort(key=lambda run: run["runId"])
        runs.sort(key=lambda run: run["modified"] or 0.0, reverse=True)
        self._send_json(200, {"runs": runs})

    def _run_trajectory(self, run_id: str) -> None:
        resolved = _resolve_run_dir(self.service, run_id)

        with self.service.run_lock(run_id):
            manifest = resolved / "manifest.json"
            if not manifest.is_file():
                raise _HttpError(404, f"unknown run {run_id}")
            digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
            gui_dir = resolved.parent / f"{resolved.name}.gui"
            trajectory_path = gui_dir / "trajectory.json"
            stale = False
            error = None
            doc = None
            if trajectory_path.is_file() and not trajectory_path.is_symlink():
                with contextlib.suppress(OSError, ValueError):
                    cached = json.loads(trajectory_path.read_text(encoding="utf-8"))
                    if isinstance(cached, dict) and cached.get("manifestSha256") == digest:
                        doc = cached
            if doc is None:
                try:
                    from .trajectory import write_trajectory

                    write_trajectory(resolved)
                    doc = json.loads(trajectory_path.read_text(encoding="utf-8"))
                except Exception as exc:
                    stale = True
                    error = str(exc)
                    if trajectory_path.is_file():
                        with contextlib.suppress(OSError, ValueError):
                            doc = json.loads(trajectory_path.read_text(encoding="utf-8"))
                    if doc is None:
                        raise _HttpError(422, error) from None
        self._send_json(200, {
            "runId": run_id,
            "stale": stale,
            "error": error,
            "artifactBase": f"{run_id}.gui",
            "trajectory": doc,
        })

    def _start_run(self) -> None:
        doc = self._read_body()
        if not isinstance(doc, dict):
            raise _HttpError(400, "body must be a JSON object")
        extra = set(doc) - {"model", "scenario", "acceptance", "options"}
        if extra:
            raise _HttpError(400, f"unexpected key(s): {', '.join(sorted(extra))}")
        spec = doc.get("model")
        if not isinstance(spec, str) or not spec:
            raise _HttpError(400, "model must be a non-empty string")
        project = _resolve_or_404(spec)
        model = spec.rpartition("/")[2]
        listing = _physics_inputs(project, self.service.repo_root)
        paths = {}
        for key, group in (("scenario", "scenarios"), ("acceptance", "acceptance"),
                           ("options", "options")):
            value = doc.get(key)
            if value is None and key == "options":
                continue
            if not isinstance(value, str) or not value:
                raise _HttpError(400, f"{key} must be a non-empty string")
            paths[key] = _listed_input(project, self.service.repo_root, listing[group],
                                       value, key)
        scenario = paths["scenario"]
        out_dir = (self.service.out_root / project.name / model / "physics"
                   / Path(scenario).stem / _stamp())
        command = _physics_command(f"{project.name}/{model}", str(scenario),
                                   str(paths["acceptance"]),
                                   str(paths["options"]) if "options" in paths else None,
                                   str(out_dir))
        job = Job(kind="run", key=f"{project.name}/{model}", model=f"{project.name}/{model}")
        job.payload = {"cmd": command, "out": out_dir}
        self.service.queue.submit(job)
        self._send_json(202, {"job": job.to_dict()})

    def _open_create(self) -> None:
        target = _open_target(self.service, self._read_body())
        try:
            request = self.service.open_requests.create(target)
        except OpenRequestError as exc:
            raise _open_error(exc) from None
        self._send_json(201, {"id": request.id, "expiresAt": request.expiresAt,
                              "target": request.target})

    def _open_claim(self, request_id: str) -> None:
        if not _OPEN_ID.fullmatch(request_id):
            raise _HttpError(404, "unknown or already claimed open request")
        try:
            request = self.service.open_requests.claim(request_id)
        except OpenRequestError as exc:
            raise _open_error(exc) from None
        self._send_json(200, {"id": request.id, "target": request.target,
                              "repoRoot": str(self.service.repo_root)})

    def _open_action(self, request_id: str, action: str) -> None:
        if not _OPEN_ID.fullmatch(request_id):
            raise _HttpError(404, "unknown or already claimed open request")
        store = self.service.open_requests
        try:
            if action == "status":
                return self._send_json(200, store.status(request_id))
            doc = self._read_body()
            if not isinstance(doc, dict):
                raise _HttpError(400, "body must be a JSON object")
            if action == "ack":
                if doc:
                    raise _HttpError(400, "ack takes no fields")
                request = store.ack(request_id)
            else:
                if set(doc) != {"reason"}:
                    raise _HttpError(400, "nack takes exactly {\"reason\"}")
                reason = doc["reason"]
                if not isinstance(reason, str) or not reason.strip():
                    raise _HttpError(400, "reason must be a non-empty string")
                request = store.nack(request_id, reason.strip()[:MAX_REASON_CHARS])
        except OpenRequestError as exc:
            raise _open_error(exc) from None
        self._send_json(200, request.to_status())

    def _artifact(self, rel: str) -> None:
        if not rel or rel.startswith("/") or "\\" in rel or "\x00" in rel:
            raise _HttpError(403, "forbidden artifact path")
        parts = rel.split("/")
        if any(part in ("", ".", "..") for part in parts):
            raise _HttpError(403, "forbidden artifact path")
        target = self.service.out_root / rel
        try:
            resolved = target.resolve(strict=True)
        except (OSError, RuntimeError):
            raise _HttpError(404, "artifact not found") from None
        root = self.service.out_root.resolve()
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise _HttpError(403, "artifact is outside out/")
        if not _artifact_allowed(self.service, resolved.relative_to(root).parts):
            raise _HttpError(403, "artifact path is not served")
        size = resolved.stat().st_size
        content_type = _CONTENT_TYPES.get(resolved.suffix.lower(), "application/octet-stream")
        self._responded = True
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(resolved, "rb") as fh:
            while True:
                chunk = fh.read(ARTIFACT_CHUNK)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def _events(self) -> None:
        q = self.service.events.subscribe()
        try:
            self._responded = True
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.flush()
            last = time.monotonic()
            while not self.service.stop_event.is_set():
                try:
                    message = q.get(timeout=1.0)
                except queue.Empty:
                    if time.monotonic() - last >= KEEPALIVE_S:
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                        last = time.monotonic()
                    continue
                payload = json.dumps(message["data"], allow_nan=False)
                chunk = (f"id: {message['id']}\nevent: {message['event']}\n"
                         f"data: {payload}\n\n")
                self.wfile.write(chunk.encode("utf-8"))
                self.wfile.flush()
                last = time.monotonic()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.service.events.unsubscribe(q)

    def _static(self, path: str) -> None:
        dist = self.service.repo_root / "ui" / "dist"
        index = dist / "index.html"
        if not index.is_file():
            if path in ("/", "/index.html"):
                return self._send_html(200, _FALLBACK_PAGE)
            raise _HttpError(404, "not found")
        rel = path.lstrip("/") or "index.html"
        if "\\" in rel or "\x00" in rel:
            raise _HttpError(404, "not found")
        parts = rel.split("/")
        if any(part in ("", ".", "..") for part in parts):
            raise _HttpError(404, "not found")
        try:
            resolved = (dist / rel).resolve(strict=True)
        except (OSError, RuntimeError):
            raise _HttpError(404, "not found") from None
        if not resolved.is_relative_to(dist.resolve()) or not resolved.is_file():
            raise _HttpError(404, "not found")
        body = resolved.read_bytes()
        content_type = _CONTENT_TYPES.get(resolved.suffix.lower(), "application/octet-stream")
        self._responded = True
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_html(self, status: int, html: str) -> None:
        body = html.encode("utf-8")
        self._responded = True
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)


# -- small helpers ---------------------------------------------------------------------


def _resolve_run_dir(service: GuiService, run_id: str) -> Path:
    """The run dir ``run_id`` names under ``out/``: 403 for unsafe paths, 404 unless it is a run."""
    root = service.out_root.resolve()
    parts = run_id.split("/")
    if (not run_id or run_id.startswith("/") or "\\" in run_id or "\x00" in run_id
            or any(part in ("", ".", "..") for part in parts)):
        raise _HttpError(403, "forbidden run path")
    candidate = service.out_root / run_id
    if candidate.is_symlink():
        raise _HttpError(403, "run directory is a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        raise _HttpError(404, f"unknown run {run_id}") from None
    if not resolved.is_relative_to(root):
        raise _HttpError(403, "run is outside out/")
    if not resolved.is_dir() or not (resolved / "summary.json").is_file() \
            or not (resolved / "states.npz").is_file():
        raise _HttpError(404, f"unknown run {run_id}")
    return resolved


def _open_target(service: GuiService, doc) -> dict | None:
    """Validate a ``POST /v1/open`` body into ``{"model"}``, ``{"run"}`` or None."""
    if not isinstance(doc, dict):
        raise _HttpError(400, "body must be a JSON object")
    extra = set(doc) - {"model", "run"}
    if extra:
        raise _HttpError(400, f"unexpected key(s): {', '.join(sorted(extra))}")
    if "model" in doc and "run" in doc:
        raise _HttpError(400, "give model or run, not both")
    if "model" in doc:
        spec = doc["model"]
        if not isinstance(spec, str) or not spec:
            raise _HttpError(400, "model must be a non-empty string")
        project_name, _, model = spec.partition("/")
        if not _SEGMENT.fullmatch(project_name) or not _SEGMENT.fullmatch(model):
            raise _HttpError(404, f"unknown model {spec}")
        _resolve_or_404(spec)
        return {"model": spec}
    if "run" in doc:
        run_id = doc["run"]
        if not isinstance(run_id, str) or not run_id:
            raise _HttpError(400, "run must be a non-empty string")
        _resolve_run_dir(service, run_id)
        return {"run": run_id}
    return None


def _open_error(exc: OpenRequestError) -> _HttpError:
    return _HttpError(exc.status, exc.message)


def _resolve_or_404(spec: str) -> Project:
    try:
        project, _ = resolve(spec)
    except KeyError as exc:
        raise _HttpError(404, str(exc.args[0]) if exc.args else f"unknown model {spec}") from None
    return project


@dataclass(frozen=True)
class _InputFile:
    """One listed physics input: display name, repo-relative and project-relative spellings."""

    name: str
    path: str
    project_path: str
    resolved: Path


# Listing key -> (subdirectory of the project, glob) for the physics-inputs route.
_INPUT_GLOBS = {
    "scenarios": ("physics/scenarios", "*.json"),
    "acceptance": ("physics", "*_acceptance.json"),
    "options": ("physics/options", "*.toml"),
}


def _project_dir(project: Project) -> Path:
    return Path(project.models.__file__).resolve().parent.parent


def _physics_inputs(project: Project, repo_root: Path) -> dict[str, list[_InputFile]]:
    """Existing scenario, acceptance and options files of ``project``, sorted by path."""
    project_dir = _project_dir(project)
    root = Path(repo_root).resolve()
    listing: dict[str, list[_InputFile]] = {}
    for key, (subdir, pattern) in _INPUT_GLOBS.items():
        entries = []
        folder = project_dir / subdir
        if folder.is_dir() and not folder.is_symlink():
            for candidate in folder.glob(pattern):
                if candidate.is_symlink() or not candidate.is_file():
                    continue
                resolved = candidate.resolve()
                if not resolved.is_relative_to(project_dir) or not resolved.is_relative_to(root):
                    continue
                entries.append(_InputFile(
                    name=resolved.name,
                    path=resolved.relative_to(root).as_posix(),
                    project_path=resolved.relative_to(project_dir).as_posix(),
                    resolved=resolved,
                ))
        listing[key] = sorted(entries, key=lambda entry: entry.path)
    return listing


def _listed_input(project: Project, repo_root: Path, entries: list[_InputFile], value: str,
                  key: str) -> Path:
    """The listed file ``value`` names: 403 for unsafe or unlisted paths, 400 when missing."""
    if "\\" in value or "\x00" in value:
        raise _HttpError(403, f"{key} path is not allowed")
    path = Path(value)
    if path.is_absolute():
        raise _HttpError(403, f"{key} must be relative to the project")
    if any(part in ("", ".", "..") for part in value.split("/")):
        raise _HttpError(403, f"{key} must not contain '..'")
    for entry in entries:
        if value in (entry.path, entry.project_path):
            return entry.resolved
    if not any((base / path).exists() for base in (Path(repo_root), _project_dir(project))):
        raise _HttpError(400, f"{key} file not found: {value}")
    raise _HttpError(403, f"{key} is not a listed {key} file: {value}")


def _artifact_allowed(service: GuiService, parts: tuple[str, ...]) -> bool:
    if len(parts) >= 4 and parts[0] in service.project_names() and parts[2] == "scene":
        return True
    for part in parts[:-1]:
        if part.endswith(".gui") and part != ".gui":
            return True
    return False


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
