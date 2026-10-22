"""Untrusted-evidence helpers for M4b replay: bounded reads, hashes and relationships.

A run directory is treated as untrusted input. Every file is read through a bounded,
regular-file-only helper, path references are confined to the run root, and JSON is parsed
strictly. Nothing here imports a project, compiles a model, or mutates source evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

from .scenario import ScenarioError, _parse_json_text

MAX_EVIDENCE_BYTES = 64 * 1024 * 1024


class EvidenceError(ValueError):
    """A run directory failed an integrity, path or shape check."""


def _safe_relative(rel: str) -> str:
    if not rel or rel.startswith("/") or rel.startswith("\\"):
        raise EvidenceError(f"absolute path {rel!r} is not allowed")
    if "\x00" in rel:
        raise EvidenceError("path contains a NUL byte")
    parts = Path(rel).parts
    if any(part in ("..", "") for part in parts):
        raise EvidenceError(f"path {rel!r} escapes the run directory")
    return rel


def _open_confined(root: Path, rel: str) -> int:
    """Open a regular file inside ``root`` without following symlinks at any component.

    Every directory component is opened with ``O_NOFOLLOW|O_DIRECTORY`` relative to the
    previous descriptor, so a symlinked component cannot escape the run root. The final
    component is opened nonblocking so a FIFO or device cannot block the caller.
    """
    parts = Path(rel).parts
    dir_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(root, dir_flags | nofollow)
    except OSError as exc:
        raise EvidenceError(f"cannot open run root {root}: {exc}") from exc
    try:
        for part in parts[:-1]:
            try:
                nxt = os.open(part, dir_flags | nofollow, dir_fd=fd)
            except OSError as exc:
                raise EvidenceError(f"cannot open directory component {part!r}: {exc}") from exc
            os.close(fd)
            fd = nxt
        try:
            return os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK | nofollow, dir_fd=fd)
        except OSError as exc:
            raise EvidenceError(f"cannot open {rel!r}: {exc}") from exc
    finally:
        os.close(fd)


def bounded_regular_bytes(root: Path, rel: str, *,
                          max_bytes: int = MAX_EVIDENCE_BYTES) -> bytes:
    """Read a regular file inside ``root`` once, with the size cap before allocation."""
    rel = _safe_relative(rel)
    root = Path(root).resolve()
    fd = _open_confined(root, rel)
    try:
        mode = os.fstat(fd).st_mode
        if not stat.S_ISREG(mode):
            raise EvidenceError(f"{rel!r} is not a regular file ({stat.filemode(mode)})")
        chunks = []
        remaining = max_bytes + 1
        while remaining > 0:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
    finally:
        os.close(fd)
    raw = b"".join(chunks)
    if len(raw) > max_bytes:
        raise EvidenceError(f"{rel!r} exceeds the {max_bytes}-byte evidence budget")
    return raw


def bounded_json(root: Path, rel: str, *, max_bytes: int = MAX_EVIDENCE_BYTES) -> dict:
    raw = bounded_regular_bytes(root, rel, max_bytes=max_bytes)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceError(f"{rel!r} is not valid UTF-8: {exc}") from exc
    try:
        return _parse_json_text(text, rel)
    except ScenarioError as exc:
        raise EvidenceError(str(exc)) from exc


def raw_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha256(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def verify_manifest_relationships(run_dir: Path, manifest: dict, summary: dict,
                                  report: dict, *, raw_files: dict[str, bytes] | None = None,
                                  max_bytes: int = MAX_EVIDENCE_BYTES) -> None:
    """Manifest/summary/report must describe the same run and the same artifacts."""
    require(manifest.get("run_id") == summary.get("run_id"),
            "manifest and summary run_id differ")
    require(manifest.get("status") == summary.get("status"),
            "manifest and summary status differ")
    require(manifest.get("identity") == summary.get("identity"),
            "manifest and summary identity differ")
    require(manifest.get("scenario") == summary.get("scenario"),
            "manifest and summary scenario identity differ")
    require(manifest.get("acceptance") == summary.get("acceptance"),
            "manifest and summary acceptance identity differ")
    require(report.get("scene_hash") == summary["scene"]["scene_hash"],
            "report.json scene_hash differs from the summary")
    artifacts = manifest.get("artifacts")
    require(isinstance(artifacts, dict) and artifacts, "manifest has no artifact hashes")
    require(manifest.get("solver") == summary.get("solver"),
            "manifest and summary solver facts differ")
    for rel, entry in artifacts.items():
        if raw_files is not None and rel in raw_files:
            raw = raw_files[rel]
        else:
            raw = bounded_regular_bytes(run_dir, rel, max_bytes=max_bytes)
        require(raw_sha256(raw) == entry.get("sha256"),
                f"artifact {rel!r} sha256 does not match the manifest")
        require(len(raw) == entry.get("bytes"),
                f"artifact {rel!r} byte count does not match the manifest")
    for rel in ("manifest.json", "summary.json", "scenario.json", "acceptance.lock.json",
                "scene.xml", "states.npz", "report.json", "state_meta.json",
                "checkpoints.npz"):
        require((Path(run_dir) / rel).is_file(), f"required evidence file {rel!r} is missing")
        if rel != "manifest.json":  # the manifest cannot hash itself
            require(rel in artifacts, f"manifest does not hash required evidence {rel!r}")
