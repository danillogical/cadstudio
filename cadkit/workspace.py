"""Where the engine lives and where the user's work lives.

``ENGINE_ROOT`` is the checkout holding ``cadkit/`` (its ``ui/dist`` and extension build).
The *workspace* is the user's tree: the nearest ancestor of the cwd (itself included) that has
a ``projects/`` directory, or ``$CADSTUDIO_WORKSPACE`` when set. Projects are imported from the
workspace's ``projects/`` package and every default output goes to ``<workspace>/out``.
The engine checkout is itself a workspace when run from inside it.
"""
from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

ENGINE_ROOT = Path(__file__).resolve().parent.parent
ENV_VAR = "CADSTUDIO_WORKSPACE"
PROJECTS = "projects"


class WorkspaceError(Exception):
    """No workspace could be found, or its ``projects`` package could not be loaded."""


def find_workspace(cwd: Path | str | None = None, env: dict | None = None) -> Path:
    """The workspace for ``cwd`` (default: the process cwd), as a resolved real path.

    ``$CADSTUDIO_WORKSPACE`` wins over the search; raises ``WorkspaceError`` when neither applies.
    """
    env = os.environ if env is None else env
    override = env.get(ENV_VAR)
    if override:
        root = Path(override).expanduser().resolve()
        if not root.is_dir():
            raise WorkspaceError(f"{ENV_VAR}={override} is not a directory")
        return root
    start = Path.cwd() if cwd is None else Path(cwd)
    start = start.resolve()
    for candidate in (start, *start.parents):
        if (candidate / PROJECTS).is_dir():
            return candidate
    raise WorkspaceError(
        f"no cadstudio workspace: no {PROJECTS}/ directory in {start} or any parent; "
        f"run from inside a workspace or set {ENV_VAR}=<dir containing {PROJECTS}/>")


def workspace_root() -> Path:
    """The current workspace; read from the env and cwd on every call, so it is never stale."""
    return find_workspace()


def out_root() -> Path:
    """The workspace's default output directory, ``<workspace>/out``."""
    return workspace_root() / "out"


def _loaded_from(module: ModuleType, pkg_dir: Path) -> bool:
    paths = list(getattr(module, "__path__", None) or [])
    return len(paths) == 1 and Path(paths[0]).resolve() == pkg_dir


def projects_package(root: Path | None = None) -> ModuleType:
    """The workspace's ``projects`` package, imported from ``<root>/projects`` and nowhere else.

    A ``projects`` already in ``sys.modules`` from another tree (the engine's own, or a previous
    workspace) is dropped with its submodules, so nothing stale is reused. The workspace also goes
    first on ``sys.path`` so project code that imports ``projects.*`` resolves the same way.
    """
    root = (workspace_root() if root is None else Path(root)).resolve()
    pkg_dir = root / PROJECTS
    if not pkg_dir.is_dir():
        raise WorkspaceError(f"workspace {root} has no {PROJECTS}/ directory")
    current = sys.modules.get(PROJECTS)
    if current is not None and _loaded_from(current, pkg_dir):
        return current
    for name in [n for n in sys.modules if n == PROJECTS or n.startswith(PROJECTS + ".")]:
        del sys.modules[name]
    entry = str(root)
    if entry in sys.path:
        sys.path.remove(entry)
    sys.path.insert(0, entry)
    importlib.invalidate_caches()
    # Load by location rather than by sys.path search, so an installed or namespace
    # ``projects`` elsewhere on the path can never shadow the workspace's.
    init = pkg_dir / "__init__.py"
    if init.is_file():
        spec = importlib.util.spec_from_file_location(
            PROJECTS, init, submodule_search_locations=[str(pkg_dir)])
    else:
        spec = importlib.machinery.ModuleSpec(PROJECTS, None, is_package=True)
        spec.submodule_search_locations = [str(pkg_dir)]
    if spec is None:
        raise WorkspaceError(f"cannot import {pkg_dir} as the {PROJECTS} package")
    module = importlib.util.module_from_spec(spec)
    sys.modules[PROJECTS] = module
    try:
        if spec.loader is not None:
            spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(PROJECTS, None)
        raise
    return module
