"""``cad gui open``: start or reuse the GUI service, then show a model or run in VS Code or a browser.

Flow: reuse a healthy registered service (the same rule as ``cad gui serve``) or spawn a detached
``cad gui serve --port 0 --no-browser --json`` that outlives this command (log in
``<workspace>/.cadstudio/gui/service.log``). For VS Code, create a one-time open request (``POST /v1/open``), run
``code --open-url vscode://danillogical.cadstudio/open?req=<id>`` and wait up to
``ACK_TIMEOUT_S`` for the extension's ack. ``--editor auto`` falls back to the browser when there is
no ack; ``--editor vscode`` exits 3 instead. Success is claimed only after an ack or a browser
launch that exited 0.

A ``--run`` target is a run dir given as an absolute path, a path relative to the cwd, or a
workspace-relative id; it must lie under ``projects/<project>/out/`` or ``.cadstudio/fixtures/``
(the service's output roots) and is sent as its workspace-relative id.

Exit codes: 0 opened (or ``--no-open``), 1 the service failed to start or answer, 2 bad
arguments or an unknown model or run, 3 not opened (no ack, or the browser launch failed).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from ..workspace import OutputPathError, resolve_output, workspace_root
from .server import MAX_BODY_BYTES, _pid_alive, discovery_path, existing_service, read_discovery

EXTENSION_URI = "vscode://danillogical.cadstudio/open"
EDITORS = ("auto", "vscode", "browser")
ACK_TIMEOUT_S = 10.0
ACK_POLL_S = 0.2
START_TIMEOUT_S = 30.0
START_POLL_S = 0.25
HEALTH_RETRIES = 3
HEALTH_RETRY_S = 0.5
LAUNCH_TIMEOUT_S = 10.0
REQUEST_TIMEOUT_S = 5.0
LOG_TAIL_LINES = 8

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_NOT_OPENED = 3

STALE_SERVICE_REASON = ("the running GUI service has no open-request route (it predates "
                        "`cad gui open`); stop it and rerun")

_TOKEN_IN_TEXT = re.compile(r"(token=)[^&\s\"']+")


def no_ack_reason(timeout_s: float = ACK_TIMEOUT_S) -> str:
    """The fallback reason when nothing acknowledged the request in time."""
    return (f"no acknowledgement within {timeout_s:g} s (extension missing, untrusted workspace, "
            "or another window received it)")


class OpenError(Exception):
    """A failure that ends ``cad gui open`` with ``exit_code``."""

    def __init__(self, exit_code: int, message: str):
        super().__init__(message)
        self.exit_code = exit_code
        self.message = message


class ServiceRequestError(Exception):
    """A service call without a 2xx answer; ``status`` 0 means no HTTP answer at all."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def redact(text: str) -> str:
    """Hide any ``token=`` value, e.g. in a service log tail or a launcher's error output."""
    # ASCII only: consumers may decode CLI output under the C locale.
    return _TOKEN_IN_TEXT.sub(r"\1REDACTED", text)


# -- pure decisions --------------------------------------------------------------------


def choose_editor(requested: str, *, env: Mapping[str, str],
                  which: Callable[[str], str | None]) -> tuple[str, str | None]:
    """``(editor, reason)``: auto picks vscode only with ``code`` on PATH inside a VS Code terminal."""
    if requested == "vscode":
        return "vscode", None
    if requested == "browser":
        return "browser", None
    if which("code") is None:
        return "browser", "`code` is not on PATH"
    if env.get("TERM_PROGRAM") != "vscode":
        return "browser", "not running in a VS Code terminal (TERM_PROGRAM is not vscode)"
    return "vscode", None


def gui_url(record: Mapping, target: Mapping | None) -> str:
    """The tokened browser URL; ``model=`` or ``run=`` makes the GUI open on that target."""
    query = {"token": record["token"]}
    if target:
        query.update(target)
    return f"http://127.0.0.1:{record['port']}/?{urllib.parse.urlencode(query)}"


def vscode_uri(request_id: str) -> str:
    return f"{EXTENSION_URI}?{urllib.parse.urlencode({'req': request_id})}"


def describe_target(target: Mapping | None) -> str:
    if not target:
        return "the GUI"
    if "model" in target:
        return target["model"]
    return f"run {target['run']}"


def model_target(spec: str) -> dict:
    """``{"model": "<project>/<model>"}`` for a spec ``cad`` resolves; else exit 2."""
    from ..project import resolve

    try:
        project, model = resolve(spec)
    except KeyError as exc:
        raise OpenError(EXIT_USAGE, str(exc.args[0]) if exc.args else f"unknown model {spec}") from None
    return {"model": f"{project.name}/{model}"}


def run_target(run_dir: str, *, ws: Path, cwd: Path | None = None) -> dict:
    """``{"run": <runId>}`` for a run dir inside the workspace's output roots; else exit 2.

    ``run_dir`` is an absolute path, a cwd-relative path or a workspace-relative id (tried in that
    order); the id returned is the run's real path relative to the workspace.
    """
    given = Path(run_dir)
    root = Path(ws).resolve()
    candidates = [given] if given.is_absolute() else [Path(cwd or Path.cwd()) / given, root / given]
    path = next((c for c in candidates if c.exists() or c.is_symlink()), None)
    if path is None:
        raise OpenError(EXIT_USAGE, f"no run directory {run_dir}")
    if path.is_symlink():
        raise OpenError(EXIT_USAGE, f"run directory {run_dir} is a symlink")
    resolved = path.resolve()
    outside = (f"run directory {run_dir} is not under {root}/projects/<project>/out or "
               f"{root}/.cadstudio/fixtures")
    if not resolved.is_relative_to(root):
        raise OpenError(EXIT_USAGE, outside)
    rel = resolved.relative_to(root).as_posix()
    try:
        contained, base = resolve_output(rel, root)
    except OutputPathError:
        raise OpenError(EXIT_USAGE, outside) from None
    if contained != resolved or contained == root.joinpath(*base):
        raise OpenError(EXIT_USAGE, outside)
    if not resolved.is_dir() or not (resolved / "summary.json").is_file() \
            or not (resolved / "states.npz").is_file():
        raise OpenError(EXIT_USAGE,
                        f"{run_dir} is not a run directory (needs summary.json and states.npz)")
    return {"run": rel}


# -- service ---------------------------------------------------------------------------


class ServiceApi:
    """Token-authenticated calls to the registered service; never goes through a proxy."""

    def __init__(self, record: Mapping, *, timeout_s: float = REQUEST_TIMEOUT_S):
        self.port = int(record["port"])
        self.token = str(record["token"])
        self.timeout_s = timeout_s
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data,
                                         method=method)
        request.add_header("Authorization", f"Bearer {self.token}")
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with self._opener.open(request, timeout=self.timeout_s) as response:
                raw = response.read(MAX_BODY_BYTES)
        except urllib.error.HTTPError as exc:
            message = exc.reason
            try:
                doc = json.loads(exc.read(MAX_BODY_BYTES).decode("utf-8"))
                if isinstance(doc, dict) and isinstance(doc.get("error"), str):
                    message = doc["error"]
            except (OSError, ValueError):
                pass
            raise ServiceRequestError(exc.code, str(message)) from None
        except (OSError, urllib.error.URLError) as exc:
            raise ServiceRequestError(0, f"no answer from the GUI service: {exc}") from None
        try:
            doc = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ServiceRequestError(0, "the GUI service answered with invalid JSON") from None
        if not isinstance(doc, dict):
            raise ServiceRequestError(0, "the GUI service answered with a non-object")
        return doc

    def create_open(self, target: Mapping | None) -> dict:
        return self.call("POST", "/v1/open", dict(target or {}))

    def open_status(self, request_id: str) -> dict:
        return self.call("GET", f"/v1/open/{urllib.parse.quote(request_id)}/status")

    def nack(self, request_id: str, reason: str) -> dict:
        return self.call("POST", f"/v1/open/{urllib.parse.quote(request_id)}/nack",
                         {"reason": reason})


def service_log_path(repo_root: Path) -> Path:
    """The log of a service ``cad gui open`` started, ``<workspace>/.cadstudio/gui/service.log``."""
    return discovery_path(repo_root).parent / "service.log"


def spawn_service(repo_root: Path) -> subprocess.Popen:
    """Start ``cad gui serve`` detached (own session, no stdin), logging to ``service_log_path``."""
    log = service_log_path(repo_root)
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        log.parent.chmod(0o700)
    except OSError:
        pass
    # The serve log holds the tokened URL, so it is private like service.json.
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        return subprocess.Popen(
            [sys.executable, "-m", "cadkit.cli", "gui", "serve", "--port", "0", "--no-browser",
             "--json"],
            cwd=repo_root, stdin=subprocess.DEVNULL, stdout=fd, stderr=fd,
            start_new_session=True, close_fds=True)
    finally:
        os.close(fd)


def _log_tail(log: Path) -> str:
    try:
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return redact("\n".join(lines[-LOG_TAIL_LINES:]))


def registered_alive(repo_root: Path) -> bool:
    """Whether ``service.json`` names this repo and a live pid (it may just be slow to answer)."""
    doc = read_discovery(repo_root)
    return bool(doc) and doc.get("repoRoot") == str(Path(repo_root).resolve()) \
        and _pid_alive(doc.get("pid"))


def ensure_service(repo_root: Path, *, timeout_s: float = START_TIMEOUT_S,
                   find=existing_service, spawn=spawn_service, alive=registered_alive,
                   clock=time.monotonic, sleep=time.sleep) -> tuple[dict, bool]:
    """``(record, started)``: a healthy registered service, spawning and awaiting one if needed."""
    found = find(repo_root)
    # One failed health check must not replace a live service, so retry before spawning.
    retries = HEALTH_RETRIES if found is None and alive(repo_root) else 0
    for _ in range(retries):
        sleep(HEALTH_RETRY_S)
        found = find(repo_root)
        if found is not None:
            break
    if found is not None:
        return found, False
    log = service_log_path(repo_root)
    try:
        proc = spawn(repo_root)
    except OSError as exc:
        raise OpenError(EXIT_ERROR, f"could not start `cad gui serve`: {exc}") from None
    deadline = clock() + timeout_s
    while True:
        found = find(repo_root)
        if found is not None:
            return found, True
        code = proc.poll()
        if code is not None:
            # A serve that found a service started meanwhile exits 0; look once more.
            found = find(repo_root)
            if found is not None:
                return found, False
            tail = _log_tail(log)
            raise OpenError(EXIT_ERROR, f"`cad gui serve` exited with code {code} before it was "
                                        f"healthy; see {log}" + (f"\n{tail}" if tail else ""))
        if clock() >= deadline:
            raise OpenError(EXIT_ERROR, f"the GUI service did not become healthy within "
                                        f"{timeout_s:.0f} s; see {log}")
        sleep(START_POLL_S)


# -- launching -------------------------------------------------------------------------


def _run_launcher(cmd: list[str], run) -> tuple[bool, str | None]:
    try:
        proc = run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                   timeout=LAUNCH_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return False, f"`{Path(cmd[0]).name}` did not finish within {LAUNCH_TIMEOUT_S:.0f} s"
    except OSError as exc:
        return False, f"`{Path(cmd[0]).name}` could not run: {redact(str(exc))}"
    if proc.returncode != 0:
        detail = redact((proc.stderr or proc.stdout or "").strip())[-300:]
        return False, (f"`{Path(cmd[0]).name}` exited with code {proc.returncode}"
                       + (f": {detail}" if detail else ""))
    return True, None


def launch_browser(url: str, *, platform: str, which: Callable[[str], str | None],
                   run, open_web=webbrowser.open) -> tuple[bool, str | None]:
    """``open`` (macOS) or ``xdg-open`` (Linux/BSD) the URL; ``(launched, failure)``."""
    if platform == "darwin":
        launcher = "open"
    elif platform.startswith(("linux", "freebsd", "openbsd", "netbsd")):
        launcher = "xdg-open"
    else:
        try:
            return (True, None) if open_web(url) else (False, "no browser could be launched")
        except Exception as exc:  # webbrowser raises a variety of errors per platform
            return False, f"browser launch failed: {redact(str(exc))}"
    exe = which(launcher)
    if exe is None:
        return False, f"`{launcher}` is not on PATH"
    return _run_launcher([exe, url], run)


def wait_for_ack(status: Callable[[], dict], *, timeout_s: float = ACK_TIMEOUT_S,
                 poll_s: float = ACK_POLL_S, clock=time.monotonic, sleep=time.sleep) -> dict:
    """Poll until acked, nacked or expired; ``{"state": "timeout", "last": ...}`` at the deadline."""
    deadline = clock() + timeout_s
    last: str | None = None
    while True:
        try:
            doc = status()
            last = doc.get("state")
            if last in ("acked", "nacked", "expired"):
                return doc
        except ServiceRequestError as exc:
            if exc.status == 404:
                return {"state": "unknown", "reason": exc.message}
        if clock() >= deadline:
            return {"state": "timeout", "last": last}
        sleep(poll_s)


@dataclass
class OpenDeps:
    """Everything ``open_gui`` touches outside its arguments; tests replace fields."""

    repo_root: Path = field(default_factory=workspace_root)
    env: Mapping[str, str] = field(default_factory=lambda: os.environ)
    which: Callable[[str], str | None] = shutil.which
    run: Callable = subprocess.run
    platform: str = sys.platform
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    ack_timeout_s: float = ACK_TIMEOUT_S
    ensure_service: Callable[["OpenDeps"], tuple[dict, bool]] = (
        lambda deps: ensure_service(deps.repo_root))
    api: Callable[[Mapping], ServiceApi] = ServiceApi
    notify: Callable[[str], None] = lambda text: print(text, file=sys.stderr, flush=True)


def _open_in_vscode(api: ServiceApi, request_id: str, deps: OpenDeps) -> tuple[bool, str | None]:
    """Hand the request to VS Code and wait for the extension's verdict."""
    code = deps.which("code")
    if code is None:
        return False, "`code` is not on PATH"
    launched, failure = _run_launcher([code, "--open-url", vscode_uri(request_id)], deps.run)
    if launched:
        result = wait_for_ack(lambda: api.open_status(request_id), timeout_s=deps.ack_timeout_s,
                              clock=deps.clock, sleep=deps.sleep)
        state = result.get("state")
        if state == "acked":
            return True, None
        if state == "nacked":
            return False, f"the VS Code extension refused: {result.get('reason') or 'no reason'}"
        if state == "expired":
            return False, "the open request expired before VS Code acknowledged it"
        if state == "unknown":
            return False, f"the open request disappeared: {result.get('reason')}"
        failure = (f"the VS Code extension claimed the request but did not acknowledge within "
                   f"{deps.ack_timeout_s:g} s" if result.get("last") == "claimed"
                   else no_ack_reason(deps.ack_timeout_s))
    # Withdraw the request so a late claim cannot open a second view; an ack that raced in wins.
    try:
        api.nack(request_id, "cad gui open stopped waiting")
    except ServiceRequestError as exc:
        if exc.status == 409:
            try:
                if api.open_status(request_id).get("state") == "acked":
                    return True, None
            except ServiceRequestError:
                pass
    return False, failure


@dataclass
class OpenResult:
    exit_code: int
    doc: dict


def open_gui(target: Mapping | None, editor: str = "auto", *, no_open: bool = False,
             deps: OpenDeps | None = None) -> OpenResult:
    """Run ``cad gui open`` for a validated target; never raises ``OpenError``."""
    deps = deps or OpenDeps()
    doc: dict = {"opened": None, "editor": editor, "target": dict(target) if target else None,
                 "url": None, "requestId": None, "reason": None, "service": None}
    try:
        record, started = deps.ensure_service(deps)
    except OpenError as exc:
        return OpenResult(exc.exit_code, {**doc, "error": exc.message, "exit_code": exc.exit_code})
    doc["service"] = {"pid": record.get("pid"), "port": record.get("port"), "started": started,
                      "log": str(service_log_path(deps.repo_root)) if started else None}
    doc["url"] = gui_url(record, target)
    if started:
        deps.notify(f"cad gui open: started the GUI service (pid {record.get('pid')}); it keeps "
                    f"running, log in {service_log_path(deps.repo_root)}")
    if no_open:
        return OpenResult(EXIT_OK, {**doc, "exit_code": EXIT_OK})

    choice, reason = choose_editor(editor, env=deps.env, which=deps.which)
    if choice == "vscode":
        api = deps.api(record)
        try:
            request = api.create_open(target)
        except ServiceRequestError as exc:
            if not (exc.status == 404 and exc.message == "not found"):
                code = EXIT_USAGE if exc.status in (400, 403, 404) else EXIT_ERROR
                return OpenResult(code, {**doc, "error": f"could not create an open request: "
                                                         f"{exc.message}", "exit_code": code})
            # The route itself is missing: a service started before `cad gui open` existed.
            request = None
            failure = STALE_SERVICE_REASON
            if editor == "vscode":
                return OpenResult(EXIT_ERROR, {**doc, "reason": failure, "error": failure,
                                               "exit_code": EXIT_ERROR})
        if request is not None:
            doc["requestId"] = request.get("id")
            opened, failure = _open_in_vscode(api, doc["requestId"], deps)
            if opened:
                return OpenResult(EXIT_OK, {**doc, "opened": "vscode", "exit_code": EXIT_OK})
        if editor == "vscode":
            return OpenResult(EXIT_NOT_OPENED, {**doc, "reason": failure,
                                                "error": f"not opened in VS Code: {failure}",
                                                "exit_code": EXIT_NOT_OPENED})
        reason = failure
    if reason:
        deps.notify(f"cad gui open: using the browser: {reason}")
    launched, failure = launch_browser(doc["url"], platform=deps.platform, which=deps.which,
                                       run=deps.run)
    if launched:
        return OpenResult(EXIT_OK, {**doc, "opened": "browser", "reason": reason,
                                    "exit_code": EXIT_OK})
    reason = f"{reason}; {failure}" if reason else failure
    return OpenResult(EXIT_NOT_OPENED, {**doc, "reason": reason,
                                        "error": f"the browser did not open: {failure}",
                                        "exit_code": EXIT_NOT_OPENED})


# -- command ---------------------------------------------------------------------------


def run(*, model: str | None, run_dir: str | None, editor: str = "auto", no_open: bool = False,
        as_json: bool = False, deps: OpenDeps | None = None) -> int:
    """``cad gui open``: resolve the target, open it, and report on stdout (JSON) and stderr."""
    deps = deps or OpenDeps()
    try:
        if model and run_dir:
            raise OpenError(EXIT_USAGE, "give a model or --run, not both")
        if editor not in EDITORS:
            raise OpenError(EXIT_USAGE, f"--editor must be one of {', '.join(EDITORS)}")
        target = (model_target(model) if model
                  else run_target(run_dir, ws=deps.repo_root) if run_dir else None)
    except OpenError as exc:
        print(f"cad gui open: {exc.message}", file=sys.stderr)
        if as_json:
            print(json.dumps({"opened": None, "error": exc.message, "exit_code": exc.exit_code},
                             indent=2))
        return exc.exit_code

    result = open_gui(target, editor, no_open=no_open, deps=deps)
    doc = result.doc
    if as_json:
        if "error" in doc:
            print(f"cad gui open: {doc['error']}", file=sys.stderr)
        print(json.dumps(doc, indent=2))
        return result.exit_code
    what = describe_target(target)
    if no_open and result.exit_code == EXIT_OK:
        print(doc["url"])  # --no-open is the explicit way to get the tokened URL
    elif doc["opened"] == "vscode":
        print(f"Opened {what} in VS Code.")
    elif doc["opened"] == "browser":
        print(f"Opened {what} in the browser.")
    else:
        print(f"cad gui open: {doc.get('error', 'not opened')}", file=sys.stderr)
        if result.exit_code == EXIT_NOT_OPENED:
            print("cad gui open: try --editor browser, or --no-open to print the URL.",
                  file=sys.stderr)
    return result.exit_code
