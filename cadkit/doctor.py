"""``cad doctor``: report the local toolchain without importing the heavy packages.

Stdlib only. ``build123d`` and ``mujoco`` are located and versioned through
``importlib`` metadata, never imported, so doctor stays fast and works without the
optional physics extra.
"""
from __future__ import annotations

import importlib.metadata
import importlib.util
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .workspace import ENGINE_ROOT, WorkspaceError, state_root, workspace_root

MIN_PYTHON = (3, 11)
MIN_NODE_MAJOR = 22
VERSION_TIMEOUT_S = 10
VERSION_RE = re.compile(r"\d+(?:\.\d+)+")


def _parse_version(text: str) -> str | None:
    """First dotted version in the output (``uv 0.13.0 (… darwin)`` -> ``0.13.0``)."""
    match = VERSION_RE.search(text)
    return match.group(0) if match else None


def _major(version: str | None) -> int:
    try:
        return int((version or "").split(".")[0])
    except ValueError:
        return 0


def _tool(name: str, *, required: bool = False, min_major: int | None = None) -> dict:
    """Locate ``name`` and run ``--version`` with captured output (nothing reaches stdout)."""
    path = shutil.which(name)
    entry = {"available": False, "version": None, "path": path, "required": required, "ok": False}
    if path is None:
        return entry
    try:
        proc = subprocess.run([path, "--version"], capture_output=True, text=True,
                              timeout=VERSION_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        return entry
    if proc.returncode != 0:
        return entry
    version = _parse_version(proc.stdout or proc.stderr)
    entry["available"] = True
    entry["version"] = version
    entry["ok"] = min_major is None or _major(version) >= min_major
    return entry


def _package(name: str, *, required: bool = False) -> dict:
    """Whether a package is installed and its metadata version, without importing it."""
    available = importlib.util.find_spec(name) is not None
    version = None
    if available:
        try:
            version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    return {"available": available, "version": version, "required": required, "ok": available}


def _python() -> dict:
    return {
        "available": True,
        "version": platform.python_version(),
        "path": sys.executable,
        "required": True,
        "ok": sys.version_info[:2] >= MIN_PYTHON,
    }


def _output_dir(workspace: Path | None, error: str | None = None) -> dict:
    if workspace is None:
        return {"path": None, "writable": False, "required": True, "ok": False, "error": error}
    path = state_root(workspace)
    writable = False
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path):
            writable = True
    except OSError:
        pass
    return {"path": str(path), "writable": writable, "required": True, "ok": writable}


def _presence(path: Path, kind: str, *, required: bool = False) -> dict:
    present = path.is_dir() if kind == "dir" else path.is_file()
    return {"path": str(path), "present": present, "required": required, "ok": present}


def collect(workspace: Path | None = None, engine_root: Path = ENGINE_ROOT) -> dict:
    """Build the doctor report; ``ok`` covers only the required checks.

    ``output_dir`` is the workspace's hidden state dir ``.cadstudio/`` (default: the current
    workspace), which must be writable; model outputs go to each project's own ``out/``. The UI
    and extension builds belong to the engine checkout.
    """
    error = None
    if workspace is None:
        try:
            workspace = workspace_root()
        except WorkspaceError as exc:
            error = str(exc)
    engine = Path(engine_root)
    checks = {
        "python": _python(),
        "uv": _tool("uv"),
        "build123d": _package("build123d", required=True),
        "mujoco": _package("mujoco"),
        "node": _tool("node", min_major=MIN_NODE_MAJOR),
        "npm": _tool("npm"),
        "output_dir": _output_dir(Path(workspace) if workspace is not None else None, error),
        "ui_dist": _presence(engine / "ui" / "dist", "dir"),
        "extension_build": _presence(
            engine / ".vscode" / "extensions" / "cadstudio" / "dist" / "extension.js", "file"),
    }
    return {"ok": all(c["ok"] for c in checks.values() if c["required"]), "checks": checks}


def format_text(report: dict) -> str:
    """One line per check plus a summary; the JSON form carries the same data."""
    lines = []
    for name, check in report["checks"].items():
        flag = "ok" if check["ok"] else ("FAIL" if check["required"] else "warn")
        if "version" in check:
            detail = check["version"] or "not found"
            if check.get("path"):
                detail += f" ({check['path']})"
        elif "writable" in check:
            detail = check.get("error") or ("writable" if check["writable"] else "not writable")
            if check.get("path"):
                detail += f" ({check['path']})"
        else:
            detail = "present" if check["present"] else "absent"
        lines.append(f"{name:<16} {flag:<4} {detail}")
    lines.append("")
    lines.append("cad doctor: " + ("ok" if report["ok"] else "required check failed"))
    return "\n".join(lines)
