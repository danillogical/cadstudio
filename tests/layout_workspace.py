"""Temp workspaces for tests of the on-disk layout (per-project ``out/``, hidden ``.cadstudio``).

Layout under test, for a workspace ``ws``:
- model outputs: ``ws/projects/<p>/out/<m>/`` (``scene/``, ``runs/``, ``physics/export/``, reports);
- physics runs: ``ws/projects/<p>/out/<m>/runs/<run>`` with ``<run>.live`` / ``<run>.gui`` beside it;
- hidden state: ``ws/.cadstudio/gui/service.json`` and ``ws/.cadstudio/fixtures/``;
- nothing is written to ``ws/out``.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from cadkit.params import REPO_ROOT


def make_starter_workspace(root: Path) -> Path:
    """Workspace at ``root/ws`` holding a copy of the engine's ``projects/`` (the starter project)."""
    ws = root / "ws"
    shutil.copytree(REPO_ROOT / "projects", ws / "projects",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "out"))
    return ws.resolve()


def project_out(ws: Path, project: str = "starter") -> Path:
    return ws / "projects" / project / "out"


def write_fake_run(run_dir: Path, status: str = "PASS") -> Path:
    """The two marker files that make a directory a listed run."""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "summary.json").write_text(json.dumps({"status": status}))
    (run_dir / "states.npz").write_bytes(b"")
    return run_dir


def make_tiny_workspace(root: Path, name: str = "ws", project: str = "tiny") -> Path:
    """A workspace with only ``projects/__init__.py`` and one tiny project (model ``box``)."""
    from gui_tiny_repo import _BOX_MODEL, _INIT, _PARAMS, _PARAMS_TOML

    ws = root / name
    proj = ws / "projects" / project
    (proj / "models").mkdir(parents=True)
    (ws / "projects" / "__init__.py").write_text("")
    (proj / "__init__.py").write_text(_INIT.replace('name="tiny"', f'name="{project}"'))
    (proj / "params.py").write_text(_PARAMS)
    (proj / "params.toml").write_text(_PARAMS_TOML)
    (proj / "models" / "__init__.py").write_text("")
    (proj / "models" / "box.py").write_text(_BOX_MODEL.format(size=10.0))
    return ws.resolve()


def run_cad(cwd: Path, *args: str, timeout: int = 300):
    """The real ``cad`` entry point from ``cwd`` (a workspace with no ``cadkit`` of its own)."""
    import os
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items()
           if k not in ("CADSTUDIO_WORKSPACE", "POCKY_POSE", "PYTHONPATH")}
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["PATH"] = f"{Path.home() / '.local' / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    return subprocess.run([sys.executable, "-m", "cadkit.cli", *args], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=timeout)
