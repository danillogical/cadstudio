"""A temp workspace whose project has a ``physics/`` tree, for tests of the GUI's physics-input rules.

The listing and path rules only look at files, so the project needs no physics assembly.
Projects: ``rig`` (physics files, model ``box``) and ``bare`` (no ``physics/`` at all).
"""
from __future__ import annotations

import contextlib
from pathlib import Path

import pytest

from gui_tiny_repo import _BOX_MODEL, _INIT, _PARAMS, _PARAMS_TOML

# Project-relative paths under ``projects/rig``.
SCENARIO = "physics/scenarios/two_cycle.json"
ACCEPTANCE = "physics/two_cycle_acceptance.json"
OPTIONS = "physics/options/clamped.toml"
NOT_LISTED = "physics/acceptance.toml"  # exists, but is not a scenario, acceptance or options file
PY_FILE = "physics/options.py"  # likewise, and a code file


def _write_project(ws: Path, name: str) -> Path:
    proj = ws / "projects" / name
    (proj / "models").mkdir(parents=True)
    (proj / "__init__.py").write_text(_INIT.replace('name="tiny"', f'name="{name}"'))
    (proj / "params.py").write_text(_PARAMS)
    (proj / "params.toml").write_text(_PARAMS_TOML)
    (proj / "models" / "__init__.py").write_text("")
    (proj / "models" / "box.py").write_text(_BOX_MODEL.format(size=10.0))
    return proj


def make_physics_workspace(root: Path) -> Path:
    """Workspace at ``root/ws`` with the ``rig`` and ``bare`` projects and a ``pyproject.toml``."""
    ws = root / "ws"
    (ws / "projects").mkdir(parents=True)
    (ws / "projects" / "__init__.py").write_text("")
    (ws / "pyproject.toml").write_text("")  # a workspace file outside any project
    rig = _write_project(ws, "rig")
    _write_project(ws, "bare")
    for rel in (SCENARIO, ACCEPTANCE, OPTIONS, NOT_LISTED, PY_FILE):
        path = rig / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}" if rel.endswith(".json") else "")
    return ws.resolve()


@contextlib.contextmanager
def workspace_env(ws: Path):
    """Point ``$CADSTUDIO_WORKSPACE`` at ``ws`` for the block (in-process project discovery)."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("CADSTUDIO_WORKSPACE", str(ws))
        yield
