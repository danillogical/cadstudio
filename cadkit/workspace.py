"""Where the engine lives and where the user's work lives.

``ENGINE_ROOT`` is the checkout holding ``cadkit/`` (its ``ui/dist`` and extension build).
The *workspace* is the user's tree: the nearest ancestor of the cwd (itself included) that has
a ``projects/`` directory, or ``$CADSTUDIO_WORKSPACE`` when set. Projects are imported from the
workspace's ``projects/`` package. The engine checkout is itself a workspace when run from inside it.

Output layout, for a workspace ``ws``:

- ``ws/projects/<p>/out/<m>/``: everything a model writes (exports, reports, ``renders/``,
  ``scene/``, ``physics/export/``), and its physics runs under ``runs/`` (default
  ``runs/<scenario_id>-<UTC stamp>``, possibly nested deeper), each with its ``<run>.live/`` and
  ``<run>.gui/`` sidecars beside it. A dir under ``out/`` whose name starts with ``_`` (e.g.
  ``_evidence``) is not a model.
- ``ws/.cadstudio/``: hidden engine state that belongs to no project: ``gui/`` (the service's
  discovery record and log, never served) and ``fixtures/`` (engine fixture runs).
- Nothing is written to ``ws/out``.

Ids the GUI service hands out (``runId``, ``liveId``, artifact paths) are POSIX paths relative to
the workspace, and may only name something under an *output root*: ``projects/<p>/out`` or
``.cadstudio/fixtures``. Containment is checked against the root spelled from the workspace's
real path without resolving the root itself, so a symlinked ``projects/<p>``, ``out`` or
``.cadstudio`` never widens what may be served: whatever it points at falls outside the root.
"""
from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

ENGINE_ROOT = Path(__file__).resolve().parent.parent
ENV_VAR = "CADSTUDIO_WORKSPACE"
PROJECTS = "projects"
OUT = "out"
STATE = ".cadstudio"
FIXTURES = "fixtures"
RUNS = "runs"
_RUN_STAMP = "%Y%m%dT%H%M%S%fZ"


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


def _root(root: Path | str | None) -> Path:
    return workspace_root() if root is None else Path(root)


def project_out(project_name: str, root: Path | str | None = None) -> Path:
    """A project's output dir, ``<workspace>/projects/<project>/out``."""
    return _root(root) / PROJECTS / project_name / OUT


def model_out(project_name: str, model: str, root: Path | str | None = None) -> Path:
    """A model's default output dir, ``<workspace>/projects/<project>/out/<model>``."""
    return project_out(project_name, root) / model


def state_root(root: Path | str | None = None) -> Path:
    """The hidden engine-state dir, ``<workspace>/.cadstudio``."""
    return _root(root) / STATE


def fixtures_root(root: Path | str | None = None) -> Path:
    """Where engine fixture runs go by default, ``<workspace>/.cadstudio/fixtures``."""
    return state_root(root) / FIXTURES


def gui_state_dir(root: Path | str | None = None) -> Path:
    """The GUI service's private dir (discovery record and log), ``<workspace>/.cadstudio/gui``."""
    return state_root(root) / "gui"


def default_run_dir(project_name: str, model: str, scenario_id: str,
                    root: Path | str | None = None) -> Path:
    """A fresh default physics run dir, ``<model out>/runs/<scenario_id>-<UTC stamp>``."""
    stamp = datetime.now(timezone.utc).strftime(_RUN_STAMP)
    return model_out(project_name, model, root) / RUNS / f"{scenario_id}-{stamp}"


def output_root_parts(parts: tuple[str, ...] | list[str]) -> tuple[str, ...] | None:
    """The output root a workspace-relative path lies under, as path parts, or None.

    ``projects/<p>/out/...`` -> ``("projects", p, "out")``; ``.cadstudio/fixtures/...`` ->
    ``(".cadstudio", "fixtures")``. Purely lexical: the caller checks ``..`` and symlinks.
    """
    parts = tuple(parts)
    if len(parts) >= 3 and parts[0] == PROJECTS and parts[2] == OUT:
        return parts[:3]
    if len(parts) >= 2 and parts[:2] == (STATE, FIXTURES):
        return parts[:2]
    return None


def output_owner(parts: tuple[str, ...] | list[str]) -> tuple[str | None, str | None]:
    """``(project, "<project>/<model>")`` for a workspace-relative run or live path.

    The model is the first dir below ``projects/<p>/out/`` when the path lies below it; a
    ``_``-prefixed (or dot) dir there is not a model, so its model is None. Fixture runs and
    paths outside every output root have no owner: ``(None, None)``.
    """
    parts = tuple(parts)
    root = output_root_parts(parts)
    if root is None or root[0] != PROJECTS:
        return None, None
    project = parts[1]
    if len(parts) >= 5 and not parts[3].startswith(("_", ".")):
        return project, f"{project}/{parts[3]}"
    return project, None


def output_roots(root: Path | str | None = None) -> list[tuple[Path, tuple[str, ...]]]:
    """Existing output roots of the workspace: ``[(dir, workspace-relative parts)]``, sorted.

    Every ``projects/<p>/out`` plus ``.cadstudio/fixtures``. A root reached through a symlink
    (``projects``, ``<p>``, ``out``, ``.cadstudio`` or ``fixtures``) is left out entirely.
    """
    ws = _root(root)
    found: list[tuple[Path, tuple[str, ...]]] = []
    projects = ws / PROJECTS
    if _real_dir(projects):
        try:
            names = sorted(entry.name for entry in os.scandir(projects)
                           if entry.is_dir(follow_symlinks=False))
        except OSError:
            names = []
        for name in names:
            out = projects / name / OUT
            if _real_dir(out):
                found.append((out, (PROJECTS, name, OUT)))
    fixtures = ws / STATE / FIXTURES
    if _real_dir(ws / STATE) and _real_dir(fixtures):
        found.append((fixtures, (STATE, FIXTURES)))
    return found


class OutputPathError(Exception):
    """A workspace-relative output path that is ``forbidden`` (unsafe or uncontained) or ``missing``."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


def safe_parts(rel: str) -> tuple[str, ...]:
    """The parts of a relative POSIX path with no empty, ``.`` or ``..`` part, no ``\\`` or NUL."""
    if not isinstance(rel, str) or not rel or rel.startswith("/") or "\\" in rel or "\x00" in rel:
        raise OutputPathError("forbidden", f"forbidden path {rel!r}")
    parts = tuple(rel.split("/"))
    if any(part in ("", ".", "..") for part in parts):
        raise OutputPathError("forbidden", f"forbidden path {rel!r}")
    return parts


def resolve_output(rel: str, root: Path | str | None = None) -> tuple[Path, tuple[str, ...]]:
    """``(real path, output-root parts)`` for a workspace-relative path inside an output root.

    ``root`` must be the workspace's real path (``find_workspace`` returns one). Raises
    ``OutputPathError``: ``forbidden`` for an unsafe path, one outside every output root, or one
    whose real path escapes the root it names (a symlink anywhere on the way out of it);
    ``missing`` when nothing exists there. The root is spelled, never resolved, so a symlinked
    root cannot widen access.
    """
    parts = safe_parts(rel)
    base = output_root_parts(parts)
    if base is None:
        raise OutputPathError("forbidden", f"{rel} is not under projects/<project>/out or "
                                           f"{STATE}/{FIXTURES}")
    ws = _root(root)
    try:
        resolved = ws.joinpath(*parts).resolve(strict=True)
    except (OSError, RuntimeError):
        raise OutputPathError("missing", f"no such output {rel}") from None
    if not resolved.is_relative_to(ws.joinpath(*base)):
        raise OutputPathError("forbidden", f"{rel} leaves its output root")
    return resolved, base


def _real_dir(path: Path) -> bool:
    try:
        return stat.S_ISDIR(os.lstat(path).st_mode)
    except OSError:
        return False


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
