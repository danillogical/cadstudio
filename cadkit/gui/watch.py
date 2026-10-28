"""Disk watcher for the GUI service: follow-mode rebuilds and events for external writes.

One daemon thread polls by ``mtime``/size every ``interval`` seconds (default 1.0; stdlib only,
no file hashing). ``GuiService.start()`` runs the first scan synchronously as the baseline, so
anything already on disk at start is never announced; ``GuiService.close()`` stops the thread.

**Follow and source rebuilds.** ``POST /v1/follow {"model": "<project>/<model>"}`` registers
(or renews) a follow with a lease that expires ``lease`` seconds (default 60) after the last
POST; ``DELETE /v1/follow`` drops one model (``{"model"}``) or all of them (no body or ``{}``).
While a project has a live follow, every ``*.py`` and ``*.toml`` under ``projects/<project>/``
is tracked (``__pycache__``, dot dirs and symlinked dirs are skipped). An add, remove, or
``mtime``/size change starts a debounce; after ``debounce`` seconds (default 1.5) with no further
change, each followed model of that project gets ONE build job through the normal job queue.
A build is not queued when a build job for that model is already ``queued``; when one is
``running``, at most one follow-up is queued. So a burst of edits yields exactly one build,
plus one follow-up if edits land while it runs.

**External scenes.** ``out/<project>/<model>/scene/scene.json`` (``<project>`` a known project,
checked only when announcing so the baseline scan never imports the projects) is announced as
``artifact {kind: "scene", model}`` whenever its ``mtime`` differs from the last one announced
(a newly appearing scene counts; a deleted one is forgotten silently).
``write_scene`` replaces ``scene.json`` atomically, so a changed ``mtime`` is always a complete
file. While a service build job for the model runs, the scene is not considered; the job
records the ``mtime`` it produced before publishing its own event, so it is never announced twice.

**External runs.** A directory under ``out/`` that newly qualifies as a run (``is_run_dir``,
the rule ``GET /v1/runs`` uses), or whose ``summary.json`` ``mtime`` changes, is announced as
``artifact {kind: "run", runId}`` with ``runId`` relative to ``out/`` as in ``GET /v1/runs``.
A service physics job's own run dir is skipped while the job runs, and recorded when the job
announces it.

**Live runs.** A non-symlink directory ``<run-name>.live/`` under ``out/`` whose ``live.json``
or ``poses.bin`` changes (``mtime``/size) is announced as ``artifact {kind: "live", liveId,
frames, done}``. ``liveId`` is the ``.live`` dir's path relative to ``out/`` without the
``.live`` suffix (the ``runId`` the finished run will have; its files are
``<liveId>.live/...``, as trajectories are ``<runId>.gui/...``). ``frames`` is ``live.json``'s
integer ``frames`` (else null) and ``done`` is true only when ``live.json`` has ``done: true``.
A ``live.json`` that is missing, unreadable or not a JSON object is skipped for that tick and
retried on the next. Events are throttled to one per ``live_interval`` seconds (default 0.5)
per live dir; a change inside the window is published once the window has passed.

**Scan pruning.** The ``out/`` walk uses ``os.scandir`` and never follows symlinks. It skips dot
dirs and ``*.gui`` dirs (as ``GET /v1/runs`` does), and also ``renders/`` dirs, the ``parts/``
dir inside any ``scene/`` dir, and the inside of ``*.live`` dirs.

**Locking.** All shared watcher state (follows, records, in-flight job keys) is guarded by
``Watcher._lock``; file I/O for a scan happens outside it, and changed files are re-stat'ed
under the lock before deciding, so a job's freshly recorded ``mtime`` always wins over a stale
observation. Events are published and build jobs submitted only after ``_lock`` is released.
"""
from __future__ import annotations

import json
import os
import stat
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_INTERVAL_S = 1.0
DEFAULT_DEBOUNCE_S = 1.5
DEFAULT_LEASE_S = 60.0
DEFAULT_LIVE_INTERVAL_S = 0.5
_SOURCE_SUFFIXES = (".py", ".toml")
_STOP_JOIN_S = 5.0


def project_dir(project) -> Path:
    """The directory of a project package (``projects/<name>/``)."""
    return Path(project.models.__file__).resolve().parent.parent


# -- the out/ walk and the run rule, shared with GET /v1/runs --------------------------


def walk_out(root: Path):
    """Yield ``(path, rel_parts, files, subdirs)`` for every dir under ``root``, top-down.

    ``files`` maps name to ``os.DirEntry`` for every entry that is not a real directory
    (symlinks included); ``subdirs`` lists real child dirs that are not dot or ``*.gui`` dirs,
    sorted, and the caller may remove names from it to prune the walk. Symlinked dirs are
    never entered and unreadable dirs are skipped.
    """
    stack: list[tuple[Path, tuple[str, ...]]] = [(Path(root), ())]
    while stack:
        path, rel = stack.pop()
        files: dict[str, os.DirEntry] = {}
        subdirs: list[str] = []
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    try:
                        real_dir = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        continue
                    if real_dir:
                        if not entry.name.startswith(".") and not entry.name.endswith(".gui"):
                            subdirs.append(entry.name)
                    else:
                        files[entry.name] = entry
        except OSError:
            continue
        subdirs.sort()
        yield path, rel, files, subdirs
        for name in reversed(subdirs):
            stack.append((path / name, rel + (name,)))


def is_run_dir(rel: tuple[str, ...], files: dict) -> bool:
    """A physics run dir: below ``out/`` with real ``summary.json`` and ``states.npz`` files."""
    if not rel:
        return False
    for name in ("summary.json", "states.npz"):
        entry = files.get(name)
        if entry is None or entry.is_symlink():
            return False
    return True


def _stat_sig(path: Path) -> tuple[int, int] | None:
    """``(mtime_ns, size)`` of a regular non-symlink file, else None."""
    try:
        st = os.lstat(path)
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode):
        return None
    return st.st_mtime_ns, st.st_size


def _entry_sig(entry: os.DirEntry) -> tuple[int, int] | None:
    try:
        if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
            return None
        st = entry.stat(follow_symlinks=False)
    except OSError:
        return None
    return st.st_mtime_ns, st.st_size


# -- state ----------------------------------------------------------------------------


@dataclass
class _Follow:
    project: object
    model: str
    expires_at: float


@dataclass
class _SourceState:
    """Tracked sources of one followed project."""

    root: Path
    generation: int
    files: dict[str, tuple[int, int]] = field(default_factory=dict)
    changed_at: float | None = None
    changed: list[str] = field(default_factory=list)


@dataclass
class _LiveState:
    sig: tuple | None = None
    last_publish: float = float("-inf")


class Watcher:
    """Polls project sources and ``out/`` for ``GuiService``; see the module docstring."""

    def __init__(self, service, *, interval: float = DEFAULT_INTERVAL_S,
                 debounce: float = DEFAULT_DEBOUNCE_S, lease: float = DEFAULT_LEASE_S,
                 live_interval: float = DEFAULT_LIVE_INTERVAL_S, clock=time.time,
                 monotonic=time.monotonic) -> None:
        self.service = service
        self.interval = interval
        self.debounce = debounce
        self.lease = lease
        self.live_interval = live_interval
        self._clock = clock
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._tick_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._generation = 0
        self._follows: dict[str, _Follow] = {}
        self._sources: dict[str, _SourceState] = {}
        self._baselined = False
        self._scenes: dict[str, tuple[int, int]] = {}
        self._runs: dict[str, tuple[int, int] | None] = {}
        self._lives: dict[str, _LiveState] = {}
        self._own_scenes: dict[str, int] = {}
        self._own_runs: dict[str, int] = {}
        self.last_scan_s: float | None = None

    # -- lifecycle -----------------------------------------------------------------------

    def start(self) -> None:
        """Take the baseline scan now, then poll on a daemon thread."""
        if self._thread is not None:
            return
        self._stop.clear()
        self.scan_once()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="cadgui-watch")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(_STOP_JOIN_S, 2 * self.interval))

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.scan_once()
            except Exception as exc:  # the watcher must never die
                if not getattr(self.service, "quiet", False):
                    sys.stderr.write(f"cadgui watch: scan failed: {exc}\n")

    # -- follows -------------------------------------------------------------------------

    def follow(self, project, model: str) -> dict:
        """Register or renew a follow of ``<project>/<model>``; returns ``{model, expiresAt}``."""
        key = f"{project.name}/{model}"
        with self._lock:
            tracked = project.name in self._sources
        # Baseline a newly followed project before it is tracked, so an edit made right after
        # the POST is already a change and the first tick never sees an empty file list.
        files = None if tracked else _scan_sources(project_dir(project))
        now = self._clock()
        with self._lock:
            self._expire(now)
            self._follows[key] = _Follow(project=project, model=model,
                                         expires_at=now + self.lease)
            if project.name not in self._sources:
                if files is None:  # unfollowed between the two lock sections; rare
                    files = _scan_sources(project_dir(project))
                self._generation += 1
                self._sources[project.name] = _SourceState(
                    root=project_dir(project), generation=self._generation, files=files)
        return {"model": key, "expiresAt": now + self.lease}

    def unfollow(self, key: str | None = None) -> None:
        """Drop one follow (``<project>/<model>``), or all of them when ``key`` is None."""
        with self._lock:
            if key is None:
                self._follows.clear()
            else:
                self._follows.pop(key, None)
            self._prune_sources()

    def following(self) -> list[dict]:
        with self._lock:
            self._expire(self._clock())
            return [{"model": key, "expiresAt": follow.expires_at}
                    for key, follow in sorted(self._follows.items())]

    def _expire(self, now: float) -> None:
        """Drop lapsed follows and the source state of projects nobody follows (lock held)."""
        for key in [key for key, follow in self._follows.items() if follow.expires_at <= now]:
            del self._follows[key]
        self._prune_sources()

    def _prune_sources(self) -> None:
        followed = {follow.project.name for follow in self._follows.values()}
        for name in [name for name in self._sources if name not in followed]:
            del self._sources[name]

    # -- service job hooks ---------------------------------------------------------------

    def begin_job(self, kind: str, key: str) -> None:
        """A service job is about to write ``key`` (a model for builds, a runId for runs)."""
        own = self._own_scenes if kind == "build" else self._own_runs
        with self._lock:
            own[key] = own.get(key, 0) + 1

    def end_job(self, kind: str, key: str) -> None:
        own = self._own_scenes if kind == "build" else self._own_runs
        with self._lock:
            count = own.get(key, 0) - 1
            if count > 0:
                own[key] = count
            else:
                own.pop(key, None)

    def note_scene(self, key: str) -> None:
        """Record the scene ``mtime`` a service job is about to announce itself."""
        sig = _stat_sig(self._scene_path(key))
        with self._lock:
            if sig is None:
                self._scenes.pop(key, None)
            else:
                self._scenes[key] = sig

    def note_run(self, run_id: str) -> None:
        """Record the run a service job is about to announce itself."""
        sig = _stat_sig(self.service.out_root / run_id / "summary.json")
        with self._lock:
            self._runs[run_id] = sig

    def _scene_path(self, key: str) -> Path:
        project, _, model = key.partition("/")
        return self.service.out_root / project / model / "scene" / "scene.json"

    # -- scanning ------------------------------------------------------------------------

    def scan_once(self) -> None:
        """One poll: expire follows, check sources, check ``out/``, then submit and publish."""
        with self._tick_lock:
            started = time.perf_counter()
            builds = self._check_sources()
            events = self._check_out()
            self.last_scan_s = time.perf_counter() - started
        for project, model, reason in builds:
            self.service.submit_follow_build(project, model, reason)
        for data in events:
            self.service.publish("artifact", data)

    def _check_sources(self) -> list[tuple[object, str, str]]:
        with self._lock:
            self._expire(self._clock())
            snapshot = [(name, state.root, state.generation)
                        for name, state in self._sources.items()]
        observed = {name: (generation, _scan_sources(root))
                    for name, root, generation in snapshot}
        now = self._monotonic()
        builds = []
        with self._lock:
            for name, (generation, files) in observed.items():
                state = self._sources.get(name)
                if state is None or state.generation != generation:
                    continue
                changed = _diff(state.files, files)
                state.files = files
                if changed:
                    state.changed_at = now
                    state.changed.extend(path for path in changed if path not in state.changed)
                if state.changed_at is not None and now - state.changed_at >= self.debounce:
                    reason = _describe(state.changed, state.root)
                    state.changed_at = None
                    state.changed = []
                    for follow in self._follows.values():
                        if follow.project.name == name:
                            builds.append((follow.project, follow.model, reason))
        return builds

    def _check_out(self) -> list[dict]:
        root = self.service.out_root
        scenes: dict[str, tuple[int, int]] = {}
        runs: dict[str, tuple[int, int] | None] = {}
        lives: dict[str, tuple] = {}
        if root.is_dir():
            for path, rel, files, subdirs in walk_out(root):
                if "renders" in subdirs:
                    subdirs.remove("renders")
                if rel and rel[-1] == "scene" and "parts" in subdirs:
                    subdirs.remove("parts")
                for name in [name for name in subdirs if name.endswith(".live")]:
                    subdirs.remove(name)
                    live_rel = "/".join(rel + (name,))
                    lives[live_rel] = (_stat_sig(path / name / "live.json"),
                                       _stat_sig(path / name / "poses.bin"))
                if len(rel) == 3 and rel[2] == "scene" and "scene.json" in files:
                    sig = _entry_sig(files["scene.json"])
                    if sig is not None:
                        scenes[f"{rel[0]}/{rel[1]}"] = sig
                if is_run_dir(rel, files):
                    runs["/".join(rel)] = _entry_sig(files["summary.json"])
        events: list[dict] = []
        now = self._monotonic()
        with self._lock:
            baseline = not self._baselined
            self._baselined = True
            self._diff_scenes(scenes, baseline, events)
            self._diff_runs(runs, baseline, events)
            self._diff_lives(lives, baseline, now, events)
        if any(data["kind"] == "scene" for data in events):
            # Only known projects' scenes; checked after the lock since the first call imports them.
            projects = self.service.project_names()
            events = [data for data in events if data["kind"] != "scene"
                      or data["model"].partition("/")[0] in projects]
        return events

    def _diff_scenes(self, scenes: dict, baseline: bool, events: list[dict]) -> None:
        for key in [key for key in self._scenes if key not in scenes]:
            if key not in self._own_scenes:
                del self._scenes[key]
        for key, sig in sorted(scenes.items()):
            if key in self._own_scenes or self._scenes.get(key) == sig:
                continue
            if baseline:
                self._scenes[key] = sig
                continue
            fresh = _stat_sig(self._scene_path(key))
            if fresh is None or self._scenes.get(key) == fresh:
                continue
            self._scenes[key] = fresh
            events.append({"kind": "scene", "model": key})

    def _diff_runs(self, runs: dict, baseline: bool, events: list[dict]) -> None:
        for run_id in [run_id for run_id in self._runs if run_id not in runs]:
            if run_id not in self._own_runs:
                del self._runs[run_id]
        for run_id, sig in sorted(runs.items()):
            if run_id in self._own_runs:
                continue
            if run_id in self._runs and self._runs[run_id] == sig:
                continue
            if baseline:
                self._runs[run_id] = sig
                continue
            fresh = _stat_sig(self.service.out_root / run_id / "summary.json")
            if run_id in self._runs and self._runs[run_id] == fresh:
                continue
            self._runs[run_id] = fresh
            events.append({"kind": "run", "runId": run_id})

    def _diff_lives(self, lives: dict, baseline: bool, now: float, events: list[dict]) -> None:
        for live_rel in [live_rel for live_rel in self._lives if live_rel not in lives]:
            del self._lives[live_rel]
        for live_rel, sig in sorted(lives.items()):
            state = self._lives.setdefault(live_rel, _LiveState())
            if state.sig == sig:
                continue
            if baseline:
                state.sig = sig
                continue
            if now - state.last_publish < self.live_interval:
                continue  # throttled; the change is still pending on the next tick
            doc = _read_live(self.service.out_root / live_rel / "live.json")
            if doc is None:
                continue  # missing or partial live.json: retry next tick
            state.sig = sig
            state.last_publish = now
            frames = doc.get("frames")
            if isinstance(frames, bool) or not isinstance(frames, int):
                frames = None
            events.append({"kind": "live", "liveId": live_rel[:-len(".live")],
                           "frames": frames, "done": doc.get("done") is True})


def _scan_sources(root: Path) -> dict[str, tuple[int, int]]:
    """``{relative path: (mtime_ns, size)}`` of the ``*.py``/``*.toml`` files under ``root``."""
    out: dict[str, tuple[int, int]] = {}
    stack = [root]
    while stack:
        path = stack.pop()
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    name = entry.name
                    if name.startswith("."):
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if name != "__pycache__":
                                stack.append(Path(entry.path))
                            continue
                        if not name.endswith(_SOURCE_SUFFIXES):
                            continue
                        st = entry.stat()
                    except OSError:
                        continue
                    out[os.path.relpath(entry.path, root)] = (st.st_mtime_ns, st.st_size)
        except OSError:
            continue
    return out


def _diff(before: dict, after: dict) -> list[str]:
    changed = [path for path, sig in after.items() if before.get(path) != sig]
    changed += [path for path in before if path not in after]
    return sorted(changed)


def _describe(changed: list[str], root: Path) -> str:
    names = [f"{root.name}/{Path(path).as_posix()}" for path in changed[:3]]
    more = f" (+{len(changed) - 3} more)" if len(changed) > 3 else ""
    return f"source changed: {', '.join(names)}{more}"


def _read_live(path: Path) -> dict | None:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None
