"""GUI watcher and follow: debounced rebuilds, leases and external-write events (from the spec).

The service runs in a subprocess over an isolated tiny repo; builds are stubbed with a process
that logs its start, so the number of builds is the number of lines in ``calls.log``.
"""
from __future__ import annotations

import json
import time

import pytest

from gui_tiny_repo import PROJECT, Sse, TinyService, edit_source, make_repo, write_atomic

DEBOUNCE = 0.5
LEASE = 3.0
LIVE_INTERVAL = 0.3
MODEL = f"{PROJECT}/box"
MODEL2 = f"{PROJECT}/box2"


@pytest.fixture(scope="module")
def tiny(tmp_path_factory):
    root = tmp_path_factory.mktemp("watch")
    repo = make_repo(root)
    out = repo / "out"
    # Pre-existing artifacts: none of these may ever be announced.
    write_atomic(out / PROJECT / "pre" / "scene" / "scene.json", "{}")
    (out / PROJECT / "oldrun").mkdir(parents=True)
    (out / PROJECT / "oldrun" / "summary.json").write_text('{"status": "PASS"}')
    (out / PROJECT / "oldrun" / "states.npz").write_bytes(b"x")
    write_atomic(out / PROJECT / "oldlive.live" / "live.json", '{"frames": 1, "done": true}')
    (out / PROJECT / "oldlive.live" / "poses.bin").write_bytes(b"\0" * 56)
    work = root / "work"
    work.mkdir()
    svc = TinyService(repo, work, stub=True, watch_interval=0.1, watch_debounce=DEBOUNCE,
                      follow_lease=LEASE, live_interval=LIVE_INTERVAL)
    svc.sse = Sse(svc)
    try:
        yield svc
    finally:
        svc.sse.close()
        svc.close()


@pytest.fixture
def quiet(tiny):
    """Start each test with no follows and no pending work."""
    tiny.req("DELETE", "/v1/follow")
    tiny.sleep_file.write_text("0")
    time.sleep(DEBOUNCE + 0.5)
    return tiny


def follow(svc, model=MODEL):
    status, doc, _ = svc.req("POST", "/v1/follow", body={"model": model})
    assert status == 200, doc
    return doc


# --------------------------------------------------------------------------- follow API


def test_follow_requires_auth(tiny):
    assert tiny.req("POST", "/v1/follow", body={"model": MODEL}, token=False)[0] == 401
    assert tiny.req("GET", "/v1/follow", token=False)[0] == 401
    assert tiny.req("DELETE", "/v1/follow", token=False)[0] == 401


def test_follow_unknown_model_is_404(tiny):
    assert tiny.req("POST", "/v1/follow", body={"model": f"{PROJECT}/nope"})[0] == 404
    assert tiny.req("POST", "/v1/follow", body={"model": "nope/box"})[0] == 404


def test_follow_response_list_and_unfollow(quiet):
    doc = follow(quiet)
    assert {"model", "expiresAt", "leaseSeconds", "following"} <= doc.keys()
    assert doc["model"] == MODEL
    assert doc["leaseSeconds"] == pytest.approx(LEASE)
    assert any(f["model"] == MODEL for f in doc["following"])
    assert doc["expiresAt"] > time.time() - 5

    follow(quiet, MODEL2)
    status, listing, _ = quiet.req("GET", "/v1/follow")
    assert status == 200
    assert [f["model"] for f in listing["following"]] == [MODEL, MODEL2]

    status, doc, _ = quiet.req("DELETE", "/v1/follow", body={"model": MODEL})
    assert status == 200
    _, listing, _ = quiet.req("GET", "/v1/follow")
    assert [f["model"] for f in listing["following"]] == [MODEL2]

    follow(quiet)
    status, _, _ = quiet.req("DELETE", "/v1/follow")  # no body: stop everything
    assert status == 200
    _, listing, _ = quiet.req("GET", "/v1/follow")
    assert listing["following"] == []


# --------------------------------------------------------------------------- rebuilds


def test_burst_of_edits_makes_exactly_one_build(quiet):
    n0, e0 = len(quiet.calls()), len(quiet.sse.events)
    follow(quiet)
    for i in range(5):
        edit_source(quiet.repo, i + 1)
        time.sleep(0.05)
    time.sleep(DEBOUNCE + 1.5)
    assert len(quiet.calls()) - n0 == 1
    assert len(quiet.sse.job_ids(e0)) == 1
    time.sleep(1.0)  # nothing else once things settle
    assert len(quiet.calls()) - n0 == 1
    assert len(quiet.sse.job_ids(e0)) == 1


def test_toml_edits_trigger_a_build_too(quiet):
    n0 = len(quiet.calls())
    follow(quiet)
    path = quiet.repo / "projects" / PROJECT / "params.toml"
    path.write_text(path.read_text() + "\n# touched\n")
    time.sleep(DEBOUNCE + 2.0)
    assert len(quiet.calls()) - n0 == 1


def test_edits_while_building_make_at_most_one_follow_up(quiet):
    quiet.sleep_file.write_text("3.0")
    n0 = len(quiet.calls())
    follow(quiet)
    edit_source(quiet.repo, 1)
    deadline = time.monotonic() + 5
    while len(quiet.calls()) - n0 < 1 and time.monotonic() < deadline:
        time.sleep(0.05)
    assert len(quiet.calls()) - n0 == 1, "first build never started"
    # Three separate edit bursts, each past the debounce window, all while the build runs.
    last_edit = 0.0
    for i in range(3):
        time.sleep(0.6)
        follow(quiet)  # keep the lease alive
        last_edit = edit_source(quiet.repo, 10 + i)
    time.sleep(3.0 + 3.0)  # let the first build end and the follow-up run to completion
    calls = quiet.calls()[n0:]
    assert len(calls) - 1 == 1, f"expected exactly one follow-up, got {len(calls) - 1}"
    assert calls[-1] > last_edit, "the follow-up must start after the last edit"
    time.sleep(0.5)
    assert len(quiet.calls()) - n0 == 2


def test_lease_expires_without_renewal(quiet):
    n0 = len(quiet.calls())
    follow(quiet)
    time.sleep(LEASE + 0.8)
    _, listing, _ = quiet.req("GET", "/v1/follow")
    assert listing["following"] == []
    edit_source(quiet.repo, 30)
    time.sleep(DEBOUNCE + 1.5)
    assert len(quiet.calls()) - n0 == 0


def test_renewed_lease_keeps_following(quiet):
    n0 = len(quiet.calls())
    follow(quiet)
    for _ in range(2):
        time.sleep(LEASE * 0.6)
        follow(quiet)
    edit_source(quiet.repo, 31)
    time.sleep(DEBOUNCE + 2.0)
    assert len(quiet.calls()) - n0 == 1


def test_pycache_and_dot_dirs_do_not_trigger_rebuilds(quiet):
    n0 = len(quiet.calls())
    follow(quiet)
    base = quiet.repo / "projects" / PROJECT
    for rel in ("__pycache__/x.py", "models/__pycache__/y.py", ".hidden/z.py", "models/.cache/w.toml"):
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1\n")
        path.write_text("x = 22\n")
    time.sleep(DEBOUNCE + 1.5)
    assert len(quiet.calls()) - n0 == 0
    # The follow is alive: a real edit still builds, so the silence above was not vacuous.
    edit_source(quiet.repo, 40)
    time.sleep(DEBOUNCE + 2.0)
    assert len(quiet.calls()) - n0 == 1


# --------------------------------------------------------------------------- scene events


def test_preexisting_files_are_not_announced(tiny):
    time.sleep(1.5)
    announced = tiny.sse.artifacts()
    stale = [a for a in announced if a.get("model") == f"{PROJECT}/pre"
             or a.get("runId") == f"{PROJECT}/oldrun" or a.get("liveId") == f"{PROJECT}/oldlive"]
    assert stale == []


def test_external_scene_write_is_announced_once(tiny):
    e0 = len(tiny.sse.events)
    write_atomic(tiny.repo / "out" / PROJECT / "ext" / "scene" / "scene.json", '{"a": 1}')
    time.sleep(1.5)
    scenes = [a for a in tiny.sse.artifacts("scene", e0) if a["model"] == f"{PROJECT}/ext"]
    assert len(scenes) == 1
    time.sleep(1.0)
    assert len([a for a in tiny.sse.artifacts("scene", e0) if a["model"] == f"{PROJECT}/ext"]) == 1


def test_service_build_announces_one_scene_event(quiet):
    e0 = len(quiet.sse.events)
    status, doc, _ = quiet.req("POST", f"/v1/models/{MODEL}/build")
    assert status == 202, doc
    assert quiet.wait_job(doc["job"]["id"])["status"] == "succeeded"
    time.sleep(1.5)
    scenes = [a for a in quiet.sse.artifacts("scene", e0) if a["model"] == MODEL]
    assert len(scenes) == 1


# --------------------------------------------------------------------------- run / live events


def test_new_run_dir_is_announced_once_with_listed_run_id(tiny):
    e0 = len(tiny.sse.events)
    run = tiny.repo / "out" / PROJECT / "newrun"
    run.mkdir(parents=True)
    (run / "states.npz").write_bytes(b"x")
    write_atomic(run / "summary.json", '{"status": "PASS"}')
    time.sleep(1.5)
    runs = tiny.sse.artifacts("run", e0)
    assert len(runs) == 1, runs
    status, doc, _ = tiny.req("GET", "/v1/runs")
    assert status == 200
    assert runs[0]["runId"] in [r["runId"] for r in doc["runs"]]
    assert runs[0]["runId"] == f"{PROJECT}/newrun"


def test_live_dir_events_partial_json_and_throttle(tiny):
    live = tiny.repo / "out" / PROJECT / "lv1.live"
    e0 = len(tiny.sse.events)
    write_atomic(live / "live.json", json.dumps({"frames": 3, "done": False}))
    time.sleep(1.0)
    events = [a for a in tiny.sse.artifacts("live", e0) if a["liveId"] == f"{PROJECT}/lv1"]
    assert len(events) == 1 and events[0]["frames"] == 3 and events[0]["done"] is False

    e1 = len(tiny.sse.events)
    (live / "live.json").write_text('{"frames": 4, "do')  # partial, non-atomic write
    time.sleep(1.0)
    assert [a for a in tiny.sse.artifacts("live", e1) if a["liveId"] == f"{PROJECT}/lv1"] == []

    e2 = len(tiny.sse.events)
    write_atomic(live / "live.json", json.dumps({"frames": 9, "done": True}))
    time.sleep(1.0)
    events = [a for a in tiny.sse.artifacts("live", e2) if a["liveId"] == f"{PROJECT}/lv1"]
    assert len(events) == 1 and events[0]["frames"] == 9 and events[0]["done"] is True


def test_live_events_are_throttled(tiny):
    live = tiny.repo / "out" / PROJECT / "lv2.live"
    write_atomic(live / "live.json", json.dumps({"frames": 0, "done": False}))
    time.sleep(1.0)
    e0 = len(tiny.sse.events)
    start = time.monotonic()
    for i in range(50):
        write_atomic(live / "live.json", json.dumps({"frames": i + 1, "done": False}))
        time.sleep(0.02)
    burst = time.monotonic() - start
    time.sleep(1.5)
    events = [a for a in tiny.sse.artifacts("live", e0) if a["liveId"] == f"{PROJECT}/lv2"]
    assert 1 <= len(events) <= 5, (burst, [e["frames"] for e in events])
    assert events[-1]["frames"] == 50, "the final state must still be published after the burst"
