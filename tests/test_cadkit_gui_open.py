"""``cad gui open``: the open-request lifecycle, its HTTP routes, the CLI decisions and the ack wait (packet G5).

Nothing here touches the repo's real ``out/.gui``: services live in temp dirs, and every launcher
(``code``, ``open``, ``xdg-open``) is a fake. Port binding may be blocked by a sandbox (EPERM).
"""
from __future__ import annotations

import http.client
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from cadkit.gui import opener, server
from cadkit.gui.opener import OpenDeps, ServiceRequestError
from cadkit.gui.server import OpenRequestError, OpenRequestStore
from cadkit.params import REPO_ROOT

ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
GOOD_ID = "A" * 24  # well-formed but never issued


class Clock:
    """A settable clock; ``sleep`` advances it so waits finish instantly and are countable."""

    def __init__(self, start: float = 1000.0):
        self.t = start
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


# -- OpenRequestStore ------------------------------------------------------------------


def make_store(**kw):
    clock = Clock()
    kw.setdefault("ttl_s", 60.0)
    kw.setdefault("retain_s", 300.0)
    return OpenRequestStore(clock=clock.now, **kw), clock


def status_of(call, *args) -> int:
    with pytest.raises(OpenRequestError) as info:
        call(*args)
    return info.value.status


def test_store_create_claim_ack():
    store, clock = make_store()
    request = store.create({"model": "pocky/syringe"})
    assert request.state == "pending" and request.target == {"model": "pocky/syringe"}
    assert request.expiresAt == clock.t + 60.0
    assert store.status(request.id)["state"] == "pending"
    claimed = store.claim(request.id)
    assert claimed.state == "claimed" and claimed.target == {"model": "pocky/syringe"}
    assert store.status(request.id)["state"] == "claimed"
    acked = store.ack(request.id)
    assert acked.state == "acked"
    assert store.status(request.id) == {"id": request.id, "state": "acked", "reason": None,
                                        "expiresAt": request.expiresAt}


def test_store_target_none_and_copy():
    store, _ = make_store()
    assert store.create(None).target is None
    target = {"run": "r1"}
    request = store.create(target)
    target["run"] = "mutated"
    assert request.target == {"run": "r1"}


def test_store_claim_is_single_use():
    store, _ = make_store()
    request = store.create(None)
    store.claim(request.id)
    assert status_of(store.claim, request.id) == 404
    store.ack(request.id)
    assert status_of(store.claim, request.id) == 404


def test_store_claim_unknown_is_404():
    store, _ = make_store()
    assert status_of(store.claim, "nope") == 404


def test_store_claim_after_expiry_is_410():
    store, clock = make_store()
    request = store.create(None)
    clock.t += 59.9
    assert store.status(request.id)["state"] == "pending"
    clock.t += 0.2
    assert status_of(store.claim, request.id) == 410
    assert store.status(request.id)["state"] == "expired"


def test_store_ack_without_claim_refused():
    store, _ = make_store()
    request = store.create(None)
    assert status_of(store.ack, request.id) == 409
    assert store.status(request.id)["state"] == "pending"


def test_store_nack_from_pending_and_claimed():
    store, _ = make_store()
    pending = store.create(None)
    done = store.nack(pending.id, "no thanks")
    assert done.state == "nacked" and done.reason == "no thanks"
    claimed = store.create(None)
    store.claim(claimed.id)
    assert store.nack(claimed.id, "untrusted").state == "nacked"
    assert store.status(claimed.id)["reason"] == "untrusted"
    # A nacked request can no longer be claimed.
    assert status_of(store.claim, pending.id) == 404


def test_store_resolved_requests_answer_409():
    store, _ = make_store()
    acked = store.create(None)
    store.claim(acked.id)
    store.ack(acked.id)
    assert status_of(store.ack, acked.id) == 409
    assert status_of(store.nack, acked.id, "late") == 409
    assert store.status(acked.id)["state"] == "acked" and store.status(acked.id)["reason"] is None

    nacked = store.create(None)
    store.nack(nacked.id, "first")
    assert status_of(store.ack, nacked.id) == 409
    assert status_of(store.nack, nacked.id, "second") == 409
    assert store.status(nacked.id)["reason"] == "first"


def test_store_expired_requests_answer_410_to_ack_and_nack():
    store, clock = make_store()
    request = store.create(None)
    store.claim(request.id)
    clock.t += 61
    assert status_of(store.ack, request.id) == 410
    assert status_of(store.nack, request.id, "late") == 410
    assert store.status(request.id)["state"] == "expired"


def test_store_resolved_request_does_not_expire():
    store, clock = make_store()
    request = store.create(None)
    store.claim(request.id)
    store.ack(request.id)
    clock.t += 120
    assert store.status(request.id)["state"] == "acked"


def test_store_retention_cleanup_after_retain_s():
    store, clock = make_store(ttl_s=60.0, retain_s=300.0)
    request = store.create(None)
    clock.t += 60 + 299
    assert store.status(request.id)["state"] == "expired"
    clock.t += 2
    with pytest.raises(OpenRequestError) as info:
        store.status(request.id)
    assert info.value.status == 404
    assert status_of(store.claim, request.id) == 404


def test_store_max_requests_429_and_recovers_after_retention():
    store, clock = make_store(max_requests=3)
    ids = [store.create(None).id for _ in range(3)]
    assert status_of(store.create, None) == 429
    # Expired entries still count until they are forgotten.
    clock.t += 61
    assert status_of(store.create, None) == 429
    clock.t += 300
    fresh = store.create(None)
    assert fresh.id not in ids


def test_store_ids_unique_and_unguessable_looking():
    store, _ = make_store(max_requests=500)
    ids = [store.create(None).id for _ in range(300)]
    assert len(set(ids)) == 300
    for request_id in ids:
        assert ID_RE.fullmatch(request_id)
        assert len(request_id) >= 24  # >= 144 bits of urlsafe base64
    assert len({c for request_id in ids for c in request_id}) > 30  # not a counter


def test_store_duplicate_id_from_source_is_retried():
    produced = iter(["dup-" + "x" * 20, "dup-" + "x" * 20, "uniq-" + "y" * 20])
    clock = Clock()
    store = OpenRequestStore(clock=clock.now, make_id=lambda: next(produced))
    first = store.create(None)
    second = store.create(None)
    assert first.id != second.id


def test_store_server_defaults_match_documented_values():
    assert server.OPEN_TTL_S == 60.0
    assert server.OPEN_RETAIN_S == 300.0
    assert server.MAX_REASON_CHARS == 500
    fresh = OpenRequestStore()
    assert fresh.ttl_s == 60.0 and fresh.retain_s == 300.0


# -- HTTP routes -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def svc(tmp_path_factory):
    service = server.GuiService(out_root=tmp_path_factory.mktemp("open_out"), port=0, quiet=True)
    service.start()
    service.write_discovery()
    try:
        yield service
    finally:
        service.close()


@pytest.fixture()
def clock_store(svc):
    """Swap in a store with an injected clock for one test."""
    clock = Clock(start=time.time())
    saved = svc.open_requests
    svc.open_requests = OpenRequestStore(clock=clock.now)
    try:
        yield svc.open_requests, clock
    finally:
        svc.open_requests = saved


def http_req(svc, method, path, *, token=True, body=None, raw=None):
    conn = http.client.HTTPConnection("127.0.0.1", svc.port, timeout=30)
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {svc.token}"
    data = raw
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    if data is not None:
        headers["Content-Type"] = "application/json"
    try:
        conn.request(method, path, body=data, headers=headers)
        resp = conn.getresponse()
        payload = resp.read()
        return resp.status, (json.loads(payload) if payload else None)
    finally:
        conn.close()


def create(svc, body=None, **kw):
    return http_req(svc, "POST", "/v1/open", body={} if body is None else body, **kw)


@pytest.mark.parametrize("method,path,body", [
    ("POST", "/v1/open", {}),
    ("GET", f"/v1/open/{GOOD_ID}", None),
    ("POST", f"/v1/open/{GOOD_ID}/ack", {}),
    ("POST", f"/v1/open/{GOOD_ID}/nack", {"reason": "x"}),
    ("GET", f"/v1/open/{GOOD_ID}/status", None),
])
def test_routes_require_token(svc, method, path, body):
    status, doc = http_req(svc, method, path, token=False, body=body)
    assert status == 401 and "error" in doc
    # With the token the same request reaches the handler (404 for the unknown id, 201 for create).
    status, _ = http_req(svc, method, path, body=body)
    assert status != 401


def test_routes_wrong_method_405(svc):
    assert http_req(svc, "GET", "/v1/open")[0] == 405
    assert http_req(svc, "POST", f"/v1/open/{GOOD_ID}", body={})[0] == 405
    assert http_req(svc, "GET", f"/v1/open/{GOOD_ID}/ack")[0] == 405
    assert http_req(svc, "POST", f"/v1/open/{GOOD_ID}/status", body={})[0] == 405


def test_create_returns_id_expiry_and_target(svc):
    before = time.time()
    status, doc = create(svc, {"model": "pocky/packet_dummy"})
    assert status == 201
    assert {"id", "expiresAt", "target"} <= set(doc)
    assert ID_RE.fullmatch(doc["id"])
    assert doc["target"] == {"model": "pocky/packet_dummy"}
    assert before + 59 <= doc["expiresAt"] <= time.time() + 61


def test_create_empty_target_and_empty_body(svc):
    status, doc = create(svc, {})
    assert status == 201 and doc["target"] is None
    status, doc = http_req(svc, "POST", "/v1/open", raw=b"")
    assert status == 201 and doc["target"] is None


@pytest.mark.parametrize("body", [
    {"model": "pocky/packet_dummy", "extra": 1},
    {"bogus": True},
    {"model": "pocky/packet_dummy", "run": "r1"},
    {"model": ""},
    {"model": 5},
    {"model": None},
    {"run": ""},
    {"run": ["r1"]},
])
def test_create_bad_bodies_400(svc, body):
    status, doc = create(svc, body)
    assert status == 400 and "error" in doc


def test_create_non_object_and_bad_json_400(svc):
    assert http_req(svc, "POST", "/v1/open", body=["model"])[0] == 400
    assert http_req(svc, "POST", "/v1/open", raw=b"{nope")[0] == 400


@pytest.mark.parametrize("spec", ["pocky/does_not_exist", "nosuchproject/x", "pocky", "a/b/c",
                                  "../etc/passwd", "pocky/.."])
def test_create_unknown_model_404(svc, spec):
    status, doc = create(svc, {"model": spec})
    assert status == 404 and "error" in doc


def test_create_unknown_run_404_and_traversal_403(svc):
    assert create(svc, {"run": "no/such/run"})[0] == 404
    for bad in ("../outside", "/etc", "a/../b", "a//b", "./x", "a\\b"):
        status, doc = create(svc, {"run": bad})
        assert status == 403, (bad, doc)


def test_create_run_must_be_a_run_dir(svc):
    out = svc.out_root
    good = out / "runs" / "r_ok"
    good.mkdir(parents=True)
    (good / "summary.json").write_text("{}")
    (good / "states.npz").write_bytes(b"")
    partial = out / "runs" / "r_partial"
    partial.mkdir(parents=True)
    (partial / "summary.json").write_text("{}")
    link = out / "runs" / "r_link"
    link.symlink_to(good, target_is_directory=True)

    status, doc = create(svc, {"run": "runs/r_ok"})
    assert status == 201 and doc["target"] == {"run": "runs/r_ok"}
    assert create(svc, {"run": "runs/r_partial"})[0] == 404
    assert create(svc, {"run": "runs"})[0] == 404
    assert create(svc, {"run": "runs/r_link"})[0] == 403


def test_claim_returns_target_and_repo_root_once(svc):
    _, made = create(svc, {"model": "pocky/packet_dummy"})
    status, doc = http_req(svc, "GET", f"/v1/open/{made['id']}")
    assert status == 200
    assert {"id": made["id"], "target": {"model": "pocky/packet_dummy"},
            "repoRoot": str(svc.repo_root)}.items() <= doc.items()
    assert doc["repoRoot"] == str(REPO_ROOT.resolve())
    status, doc = http_req(svc, "GET", f"/v1/open/{made['id']}")
    assert status == 404 and "error" in doc


def test_claim_unknown_and_malformed_ids_404(svc):
    assert http_req(svc, "GET", f"/v1/open/{GOOD_ID}")[0] == 404
    for bad in ("short", "x" * 129, "has.dot" + "a" * 16, "a b" + "c" * 20):
        assert http_req(svc, "GET", f"/v1/open/{bad.replace(' ', '%20')}")[0] == 404
        assert http_req(svc, "POST", f"/v1/open/{bad.replace(' ', '%20')}/ack", body={})[0] == 404


def test_claim_expired_410(svc, clock_store):
    store, clock = clock_store
    request = store.create(None)
    clock.t += 61
    assert http_req(svc, "GET", f"/v1/open/{request.id}")[0] == 410
    status, doc = http_req(svc, "GET", f"/v1/open/{request.id}/status")
    assert status == 200 and doc["state"] == "expired"
    clock.t += 301
    assert http_req(svc, "GET", f"/v1/open/{request.id}/status")[0] == 404


def test_ack_flow(svc):
    _, made = create(svc, {})
    rid = made["id"]
    # Not claimed yet: refused.
    assert http_req(svc, "POST", f"/v1/open/{rid}/ack", body={})[0] == 409
    http_req(svc, "GET", f"/v1/open/{rid}")
    status, doc = http_req(svc, "POST", f"/v1/open/{rid}/ack", body={})
    assert status == 200
    assert doc["id"] == rid and doc["state"] == "acked" and doc["reason"] is None
    status, doc = http_req(svc, "GET", f"/v1/open/{rid}/status")
    assert status == 200
    assert {"id", "state", "reason", "expiresAt"} <= set(doc) and doc["state"] == "acked"
    # Resolved: both actions are 409.
    assert http_req(svc, "POST", f"/v1/open/{rid}/ack", body={})[0] == 409
    assert http_req(svc, "POST", f"/v1/open/{rid}/nack", body={"reason": "x"})[0] == 409


def test_ack_body_must_be_empty(svc):
    _, made = create(svc, {})
    rid = made["id"]
    http_req(svc, "GET", f"/v1/open/{rid}")
    assert http_req(svc, "POST", f"/v1/open/{rid}/ack", body={"reason": "x"})[0] == 400
    assert http_req(svc, "POST", f"/v1/open/{rid}/ack", body=["x"])[0] == 400
    # The malformed attempts did not resolve the request.
    assert http_req(svc, "GET", f"/v1/open/{rid}/status")[1]["state"] == "claimed"
    assert http_req(svc, "POST", f"/v1/open/{rid}/ack", body={})[0] == 200


def test_nack_from_pending_and_claimed(svc):
    _, made = create(svc, {})
    status, doc = http_req(svc, "POST", f"/v1/open/{made['id']}/nack", body={"reason": "  wrong repo  "})
    assert status == 200 and doc["state"] == "nacked" and doc["reason"] == "wrong repo"
    assert http_req(svc, "GET", f"/v1/open/{made['id']}")[0] == 404

    _, made = create(svc, {})
    http_req(svc, "GET", f"/v1/open/{made['id']}")
    status, doc = http_req(svc, "POST", f"/v1/open/{made['id']}/nack", body={"reason": "untrusted"})
    assert status == 200 and doc["state"] == "nacked"
    assert http_req(svc, "GET", f"/v1/open/{made['id']}/status")[1]["reason"] == "untrusted"
    assert http_req(svc, "POST", f"/v1/open/{made['id']}/ack", body={})[0] == 409


@pytest.mark.parametrize("body", [
    {}, {"reason": ""}, {"reason": "   "}, {"reason": 5}, {"reason": None}, {"reason": ["x"]},
    {"reason": "x", "extra": 1}, {"why": "x"},
])
def test_nack_bad_bodies_400(svc, body):
    _, made = create(svc, {})
    status, doc = http_req(svc, "POST", f"/v1/open/{made['id']}/nack", body=body)
    assert status == 400 and "error" in doc
    assert http_req(svc, "GET", f"/v1/open/{made['id']}/status")[1]["state"] == "pending"


def test_nack_non_object_400(svc):
    _, made = create(svc, {})
    assert http_req(svc, "POST", f"/v1/open/{made['id']}/nack", body="reason")[0] == 400


def test_nack_oversized_reason_truncated_to_500(svc):
    _, made = create(svc, {})
    status, doc = http_req(svc, "POST", f"/v1/open/{made['id']}/nack", body={"reason": "r" * 5000})
    assert status == 200 and doc["reason"] == "r" * 500
    assert http_req(svc, "GET", f"/v1/open/{made['id']}/status")[1]["reason"] == "r" * 500


def test_nack_unknown_404_and_expired_410(svc, clock_store):
    assert http_req(svc, "POST", f"/v1/open/{GOOD_ID}/nack", body={"reason": "x"})[0] == 404
    store, clock = clock_store
    request = store.create(None)
    clock.t += 61
    assert http_req(svc, "POST", f"/v1/open/{request.id}/nack", body={"reason": "x"})[0] == 410
    assert http_req(svc, "POST", f"/v1/open/{request.id}/ack", body={})[0] == 410


def test_create_429_when_full(svc, clock_store):
    store, _ = clock_store
    store.max_requests = 2
    assert create(svc, {})[0] == 201
    assert create(svc, {})[0] == 201
    status, doc = create(svc, {})
    assert status == 429 and "error" in doc


def test_open_routes_do_not_leak_token(svc):
    _, made = create(svc, {"model": "pocky/packet_dummy"})
    for method, path, body in [("GET", f"/v1/open/{made['id']}", None),
                               ("GET", f"/v1/open/{made['id']}/status", None)]:
        conn = http.client.HTTPConnection("127.0.0.1", svc.port, timeout=30)
        conn.request(method, path, headers={"Authorization": f"Bearer {svc.token}"})
        payload = conn.getresponse().read()
        conn.close()
        assert svc.token.encode() not in payload


# -- CLI decisions ---------------------------------------------------------------------


@pytest.mark.parametrize("requested,code,term,expected", [
    ("vscode", True, "vscode", "vscode"),
    ("vscode", False, None, "vscode"),  # explicit vscode is honoured; failure is reported later
    ("browser", True, "vscode", "browser"),
    ("browser", False, None, "browser"),
    ("auto", True, "vscode", "vscode"),
    ("auto", True, None, "browser"),
    ("auto", True, "iTerm.app", "browser"),
    ("auto", False, "vscode", "browser"),
    ("auto", False, None, "browser"),
])
def test_choose_editor(requested, code, term, expected):
    env = {"TERM_PROGRAM": term} if term else {}
    which = (lambda name: "/usr/bin/code" if name == "code" else None) if code else (lambda name: None)
    editor, reason = opener.choose_editor(requested, env=env, which=which)
    assert editor == expected
    if expected == "browser" and requested == "auto":
        assert reason
        if not code:
            assert "code" in reason
        else:
            assert "TERM_PROGRAM" in reason or "terminal" in reason
    else:
        assert reason is None


def test_vscode_uri_and_gui_url():
    assert opener.vscode_uri("abc_DEF-123") == "vscode://danillogical.cadstudio/open?req=abc_DEF-123"
    record = {"port": 4321, "token": "tok"}
    assert opener.gui_url(record, None) == "http://127.0.0.1:4321/?token=tok"
    assert opener.gui_url(record, {"model": "pocky/syringe"}) == \
        "http://127.0.0.1:4321/?token=tok&model=pocky%2Fsyringe"
    assert opener.gui_url(record, {"run": "a/b"}).endswith("&run=a%2Fb")


def test_redact_hides_token_values():
    assert opener.redact("see http://127.0.0.1:1/?token=SECRET&x=1 now") == \
        "see http://127.0.0.1:1/?token=REDACTED&x=1 now"
    assert "SECRET" not in opener.redact("token=SECRET")


# -- open_gui with injected deps -------------------------------------------------------

TOKEN = "SECRET-TOKEN-xyz"
RECORD = {"pid": 4242, "port": 4555, "token": TOKEN}
REQ_ID = "R" * 24


class FakeApi:
    """Stands in for ``ServiceApi``: scripted status answers, recorded nacks."""

    def __init__(self, status=None, *, create_error=None, nack_error=None):
        self._status = status or (lambda api: {"state": "pending"})
        self._create_error = create_error
        self._nack_error = nack_error
        self.created: list = []
        self.nacks: list[str] = []
        self.status_calls = 0

    def create_open(self, target):
        self.created.append(target)
        if self._create_error:
            raise self._create_error
        return {"id": REQ_ID, "expiresAt": 0, "target": target}

    def open_status(self, request_id):
        assert request_id == REQ_ID
        self.status_calls += 1
        return self._status(self)

    def nack(self, request_id, reason):
        assert request_id == REQ_ID
        self.nacks.append(reason)
        if self._nack_error:
            raise self._nack_error
        return {"id": request_id, "state": "nacked", "reason": reason}


class Harness:
    def __init__(self, api, *, code=True, launchers=None, env=None, platform="darwin",
                 service_error=None, ack_timeout_s=10.0):
        self.api = api
        self.clock = Clock()
        self.cmds: list[list[str]] = []
        self.notes: list[str] = []
        self.api_built = 0
        launchers = launchers or {}
        present = {"open": "/usr/bin/open", "xdg-open": "/usr/bin/xdg-open"}
        if code:
            present["code"] = "/usr/bin/code"

        def runner(cmd, **kwargs):
            self.cmds.append(list(cmd))
            return subprocess.CompletedProcess(cmd, launchers.get(Path(cmd[0]).name, 0), "", "")

        def ensure(deps):
            if service_error:
                raise service_error
            return dict(RECORD), False

        def build_api(record):
            self.api_built += 1
            return api

        self.deps = OpenDeps(
            repo_root=REPO_ROOT, out_root=Path("/nonexistent-out"), env=env or {},
            which=present.get, run=runner, platform=platform, clock=self.clock.now,
            sleep=self.clock.sleep, ack_timeout_s=ack_timeout_s, ensure_service=ensure,
            api=build_api, notify=self.notes.append)

    def open(self, editor="auto", target=None, no_open=False):
        return opener.open_gui(target, editor, no_open=no_open, deps=self.deps)

    @property
    def code_cmds(self):
        return [c for c in self.cmds if Path(c[0]).name == "code"]

    @property
    def browser_cmds(self):
        return [c for c in self.cmds if Path(c[0]).name in ("open", "xdg-open")]


def acked_after(n):
    return lambda api: {"state": "acked" if api.status_calls > n else "pending"}


TARGET = {"model": "pocky/syringe"}


def test_open_vscode_acked():
    h = Harness(FakeApi(acked_after(2)))
    result = h.open("vscode", TARGET)
    assert result.exit_code == 0
    assert result.doc["opened"] == "vscode" and result.doc["reason"] is None
    assert result.doc["requestId"] == REQ_ID and result.doc["target"] == TARGET
    assert h.code_cmds == [["/usr/bin/code", "--open-url",
                            f"vscode://danillogical.cadstudio/open?req={REQ_ID}"]]
    assert h.browser_cmds == []
    assert h.api.nacks == []


def test_open_vscode_nack_is_immediate_exit_3():
    api = FakeApi(lambda api: {"state": "nacked", "reason": "wrong repo root"})
    h = Harness(api)
    result = h.open("vscode", TARGET)
    assert result.exit_code == 3
    assert result.doc["opened"] is None
    assert "wrong repo root" in result.doc["reason"]
    assert h.clock.sleeps == [] and api.status_calls == 1
    assert h.browser_cmds == []
    assert api.nacks == []  # already resolved by the extension


def test_open_auto_nack_falls_back_to_browser_immediately_with_reason():
    api = FakeApi(lambda api: {"state": "nacked", "reason": "workspace is not trusted"})
    h = Harness(api, env={"TERM_PROGRAM": "vscode"})
    result = h.open("auto", TARGET)
    assert result.exit_code == 0
    assert result.doc["opened"] == "browser"
    assert "workspace is not trusted" in result.doc["reason"]
    assert h.clock.sleeps == [] and api.status_calls == 1
    assert h.browser_cmds == [["/usr/bin/open", result.doc["url"]]]
    assert any("browser" in note and "workspace is not trusted" in note for note in h.notes)


def test_open_vscode_silence_times_out_at_10s_and_nacks_own_request():
    api = FakeApi()
    h = Harness(api)
    start = h.clock.t
    result = h.open("vscode", TARGET)
    elapsed = h.clock.t - start
    assert result.exit_code == 3 and result.doc["opened"] is None
    assert 10.0 <= elapsed <= 10.5
    assert 45 <= len(h.clock.sleeps) <= 55  # polled, not one long sleep
    assert "no acknowledgement within 10 s" in result.doc["reason"]
    assert len(api.nacks) == 1 and api.nacks[0]
    assert h.browser_cmds == []


def test_open_auto_silence_falls_back_after_timeout():
    api = FakeApi()
    h = Harness(api, env={"TERM_PROGRAM": "vscode"})
    start = h.clock.t
    result = h.open("auto", TARGET)
    assert 10.0 <= h.clock.t - start <= 10.5
    assert result.exit_code == 0 and result.doc["opened"] == "browser"
    assert "no acknowledgement" in result.doc["reason"]
    assert len(api.nacks) == 1
    assert h.browser_cmds and h.browser_cmds[0][-1].startswith("http://127.0.0.1:4555/?token=")


def test_open_claimed_but_never_acked_is_reported_as_such():
    api = FakeApi(lambda api: {"state": "claimed"})
    h = Harness(api)
    result = h.open("vscode", TARGET)
    assert result.exit_code == 3 and result.doc["opened"] is None
    assert "claimed" in result.doc["reason"] and len(api.nacks) == 1


def test_open_ack_wins_race_counts_as_success():
    def status(api):
        return {"state": "acked" if api.nacks else "pending"}

    api = FakeApi(status, nack_error=ServiceRequestError(409, "open request is acked"))
    h = Harness(api)
    result = h.open("vscode", TARGET)
    assert result.exit_code == 0 and result.doc["opened"] == "vscode"
    assert len(api.nacks) == 1


def test_open_nack_conflict_without_ack_is_still_a_failure():
    api = FakeApi(nack_error=ServiceRequestError(409, "open request is nacked"))
    h = Harness(api)
    result = h.open("vscode", TARGET)
    assert result.exit_code == 3 and result.doc["opened"] is None


@pytest.mark.parametrize("answer", [
    {"state": "nacked", "reason": "r"},
    {"state": "expired"},
])
def test_open_never_claims_success_without_ack(answer):
    h = Harness(FakeApi(lambda api: dict(answer)))
    result = h.open("vscode", TARGET)
    assert result.exit_code == 3 and result.doc["opened"] is None


def test_open_request_vanishing_is_not_success():
    def status(api):
        raise ServiceRequestError(404, "unknown or already claimed open request")

    h = Harness(FakeApi(status))
    result = h.open("vscode", TARGET)
    assert result.exit_code == 3 and result.doc["opened"] is None
    assert "disappeared" in result.doc["reason"]


def test_open_status_errors_other_than_404_are_retried_until_timeout():
    def status(api):
        raise ServiceRequestError(0, "no answer")

    api = FakeApi(status)
    h = Harness(api)
    result = h.open("vscode", TARGET)
    assert result.exit_code == 3 and result.doc["opened"] is None
    assert h.clock.t - 1000.0 >= 10.0


def test_open_code_launch_failure_withdraws_request():
    api = FakeApi()
    h = Harness(api, launchers={"code": 1})
    result = h.open("vscode", TARGET)
    assert result.exit_code == 3 and result.doc["opened"] is None
    assert "code" in result.doc["reason"] and api.status_calls == 0
    assert len(api.nacks) == 1


def test_open_vscode_without_code_on_path_is_exit_3():
    h = Harness(FakeApi(), code=False)
    result = h.open("vscode", TARGET)
    assert result.exit_code == 3 and result.doc["opened"] is None
    assert "PATH" in result.doc["reason"]
    assert h.cmds == []


def test_open_browser_editor_never_creates_a_request():
    api = FakeApi()
    h = Harness(api)
    result = h.open("browser", TARGET)
    assert result.exit_code == 0 and result.doc["opened"] == "browser"
    assert h.api_built == 0 and api.created == []
    assert h.code_cmds == [] and h.browser_cmds == [["/usr/bin/open", result.doc["url"]]]
    assert "model=pocky%2Fsyringe" in result.doc["url"]


def test_open_browser_uses_xdg_open_on_linux():
    h = Harness(FakeApi(), platform="linux")
    result = h.open("browser", TARGET)
    assert result.exit_code == 0 and h.browser_cmds[0][0] == "/usr/bin/xdg-open"


def test_open_browser_launch_failure_exit_3():
    h = Harness(FakeApi(), launchers={"open": 1})
    result = h.open("browser", TARGET)
    assert result.exit_code == 3 and result.doc["opened"] is None
    assert "browser did not open" in result.doc["error"]


def test_open_auto_ack_missing_and_browser_failing_is_exit_3_with_both_reasons():
    h = Harness(FakeApi(), launchers={"open": 1}, env={"TERM_PROGRAM": "vscode"})
    result = h.open("auto", TARGET)
    assert result.exit_code == 3 and result.doc["opened"] is None
    assert "no acknowledgement" in result.doc["reason"] and "open" in result.doc["reason"]


def test_open_auto_outside_vscode_goes_straight_to_browser():
    api = FakeApi()
    h = Harness(api, env={})
    result = h.open("auto", TARGET)
    assert result.exit_code == 0 and result.doc["opened"] == "browser"
    assert result.doc["reason"] and "TERM_PROGRAM" in result.doc["reason"]
    assert h.api_built == 0 and h.code_cmds == []


def test_open_no_open_prints_url_only():
    api = FakeApi()
    h = Harness(api)
    result = h.open("vscode", TARGET, no_open=True)
    assert result.exit_code == 0 and result.doc["opened"] is None
    assert result.doc["url"] == f"http://127.0.0.1:4555/?token={TOKEN}&model=pocky%2Fsyringe"
    assert h.cmds == [] and h.api_built == 0 and api.created == []


def test_open_outdated_service_vscode_is_exit_1():
    api = FakeApi(create_error=ServiceRequestError(404, "not found"))
    h = Harness(api)
    result = h.open("vscode", TARGET)
    assert result.exit_code == 1 and result.doc["opened"] is None
    assert result.doc["reason"] == opener.STALE_SERVICE_REASON
    assert h.cmds == []


def test_open_outdated_service_auto_falls_back_to_browser():
    api = FakeApi(create_error=ServiceRequestError(404, "not found"))
    h = Harness(api, env={"TERM_PROGRAM": "vscode"})
    result = h.open("auto", TARGET)
    assert result.exit_code == 0 and result.doc["opened"] == "browser"
    assert result.doc["reason"] == opener.STALE_SERVICE_REASON
    assert h.code_cmds == []


@pytest.mark.parametrize("status,code", [(400, 2), (403, 2), (404, 2), (500, 1), (0, 1)])
def test_open_create_errors_map_to_exit_codes(status, code):
    # A 404 with a real message is an unknown model/run, not a stale service.
    message = "unknown model x" if status == 404 else "boom"
    h = Harness(FakeApi(create_error=ServiceRequestError(status, message)))
    result = h.open("vscode", TARGET)
    assert result.exit_code == code and result.doc["opened"] is None


def test_open_service_failure_is_exit_1():
    h = Harness(FakeApi(), service_error=opener.OpenError(1, "could not start"))
    result = h.open("vscode", TARGET)
    assert result.exit_code == 1 and result.doc["opened"] is None
    assert result.doc["error"] == "could not start" and h.cmds == []


# -- opener.run: arguments, output --------------------------------------------------


def test_run_rejects_bad_arguments_with_exit_2(tmp_path, capsys):
    deps = Harness(FakeApi()).deps
    deps.out_root = tmp_path
    assert opener.run(model="pocky/syringe", run_dir="x", deps=deps) == 2
    assert opener.run(model=None, run_dir=None, editor="emacs", deps=deps) == 2
    assert opener.run(model="pocky/does_not_exist", run_dir=None, deps=deps) == 2
    assert opener.run(model=None, run_dir="missing", deps=deps) == 2
    capsys.readouterr()
    assert opener.run(model="pocky/does_not_exist", run_dir=None, as_json=True, deps=deps) == 2
    out = capsys.readouterr().out
    assert json.loads(out) == {"opened": None, "error": json.loads(out)["error"], "exit_code": 2}


def test_run_target_rules(tmp_path):
    out = tmp_path / "out"
    run = out / "mj" / "r1"
    run.mkdir(parents=True)
    (run / "summary.json").write_text("{}")
    (run / "states.npz").write_bytes(b"")
    assert opener.run_target("mj/r1", out_root=out) == {"run": "mj/r1"}
    assert opener.run_target(str(run), out_root=out) == {"run": "mj/r1"}
    with pytest.raises(opener.OpenError) as info:
        opener.run_target(str(tmp_path), out_root=out)
    assert info.value.exit_code == 2
    (out / "mj" / "notrun").mkdir()
    with pytest.raises(opener.OpenError):
        opener.run_target("mj/notrun", out_root=out)
    (out / "mj" / "link").symlink_to(run, target_is_directory=True)
    with pytest.raises(opener.OpenError):
        opener.run_target("mj/link", out_root=out)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "summary.json").write_text("{}")
    (elsewhere / "states.npz").write_bytes(b"")
    with pytest.raises(opener.OpenError):
        opener.run_target(str(elsewhere), out_root=out)


def test_run_json_output_shape_and_exit(capsys):
    h = Harness(FakeApi(acked_after(0)))
    code = opener.run(model="pocky/packet_dummy", run_dir=None, editor="vscode", as_json=True,
                      deps=h.deps)
    captured = capsys.readouterr()
    assert code == 0
    doc = json.loads(captured.out)  # stdout is exactly one JSON document
    assert doc["opened"] == "vscode" and doc["exit_code"] == 0
    assert doc["target"] == {"model": "pocky/packet_dummy"} and doc["requestId"] == REQ_ID
    assert {"opened", "editor", "target", "url", "requestId", "reason", "service"} <= set(doc)


def test_run_human_output_never_prints_the_token(capsys):
    ok = Harness(FakeApi(acked_after(0)))
    assert opener.run(model="pocky/packet_dummy", run_dir=None, editor="vscode", deps=ok.deps) == 0
    captured = capsys.readouterr()
    assert "Opened pocky/packet_dummy in VS Code." in captured.out
    assert TOKEN not in captured.out + captured.err

    failed = Harness(FakeApi(lambda api: {"state": "nacked", "reason": "no"}))
    assert opener.run(model="pocky/packet_dummy", run_dir=None, editor="vscode",
                      deps=failed.deps) == 3
    captured = capsys.readouterr()
    assert TOKEN not in captured.out + captured.err and captured.out == ""

    browser = Harness(FakeApi(), env={"TERM_PROGRAM": "vscode"})
    assert opener.run(model="pocky/packet_dummy", run_dir=None, deps=browser.deps) == 0
    captured = capsys.readouterr()
    assert TOKEN not in captured.out + captured.err


def test_run_no_open_prints_the_url(capsys):
    h = Harness(FakeApi())
    assert opener.run(model=None, run_dir=None, no_open=True, deps=h.deps) == 0
    assert capsys.readouterr().out.strip() == f"http://127.0.0.1:4555/?token={TOKEN}"


# -- end to end: the real CLI process against an in-process service ------------------

DRIVER = '''
import sys
from pathlib import Path
from cadkit.gui import opener
# Point the default out dir at the test service's, then run the real `cad` entry point.
opener.REPO_ROOT = Path(sys.argv[1])
from cadkit.cli import main
sys.exit(main(sys.argv[2:]))
'''

FAKE_CODE = f'''#!{sys.executable}
import json, os, sys, urllib.parse, urllib.request

with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write(json.dumps({{"argv": sys.argv[1:]}}) + "\\n")
mode = os.environ.get("FAKE_MODE", "none")
if mode == "none":
    sys.exit(0)
if mode == "exit1":
    sys.stderr.write("boom token=LEAKME\\n")
    sys.exit(1)
rid = urllib.parse.parse_qs(urllib.parse.urlsplit(sys.argv[-1]).query)["req"][0]
opener = urllib.request.build_opener(urllib.request.ProxyHandler({{}}))


def call(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request("http://127.0.0.1:" + os.environ["FAKE_PORT"] + path,
                                     data=data, method=method)
    request.add_header("Authorization", "Bearer " + os.environ["FAKE_TOKEN"])
    request.add_header("Content-Type", "application/json")
    with opener.open(request, timeout=10) as response:
        return json.loads(response.read())


claimed = call("GET", "/v1/open/" + rid)
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write(json.dumps({{"claimed": claimed}}) + "\\n")
if mode == "ack":
    call("POST", "/v1/open/" + rid + "/ack", {{}})
elif mode == "nack":
    call("POST", "/v1/open/" + rid + "/nack", {{"reason": "wrong window"}})
'''

FAKE_OPEN = f'''#!{sys.executable}
import json, os, sys

with open(os.environ["FAKE_OPEN_LOG"], "a") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\\n")
sys.exit(int(os.environ.get("FAKE_OPEN_EXIT", "0")))
'''


class E2E:
    def __init__(self, root: Path, service, bindir: Path):
        self.root = root
        self.service = service
        self.bindir = bindir
        self.code_log = root / "code.log"
        self.open_log = root / "open.log"
        self.driver = root / "driver.py"
        self.driver.write_text(DRIVER)

    def reset(self):
        for log in (self.code_log, self.open_log):
            log.unlink(missing_ok=True)

    def env(self, *, mode="none", term="vscode", open_exit=0):
        env = {k: v for k, v in os.environ.items() if k != "TERM_PROGRAM"}
        env["PATH"] = f"{self.bindir}{os.pathsep}{env.get('PATH', '')}"
        env["PYTHONPATH"] = str(REPO_ROOT)
        env.update(FAKE_LOG=str(self.code_log), FAKE_OPEN_LOG=str(self.open_log), FAKE_MODE=mode,
                   FAKE_PORT=str(self.service.port), FAKE_TOKEN=self.service.token,
                   FAKE_OPEN_EXIT=str(open_exit))
        if term:
            env["TERM_PROGRAM"] = term
        return env

    def cad(self, *args, timeout=90, **env_kw):
        return subprocess.run([sys.executable, str(self.driver), str(self.root), *args],
                              cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout,
                              env=self.env(**env_kw))

    def code_lines(self):
        if not self.code_log.exists():
            return []
        return [json.loads(line) for line in self.code_log.read_text().splitlines()]

    def open_lines(self):
        if not self.open_log.exists():
            return []
        return [json.loads(line) for line in self.open_log.read_text().splitlines()]


@pytest.fixture(scope="module")
def e2e(tmp_path_factory):
    root = tmp_path_factory.mktemp("e2e")
    service = server.GuiService(out_root=root / "out", port=0, quiet=True)
    service.start()
    service.write_discovery()
    bindir = root / "bin"
    bindir.mkdir()
    for name, body in (("code", FAKE_CODE), ("open", FAKE_OPEN), ("xdg-open", FAKE_OPEN)):
        path = bindir / name
        path.write_text(body)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    run = service.out_root / "mj" / "r1"
    run.mkdir(parents=True)
    (run / "summary.json").write_text("{}")
    (run / "states.npz").write_bytes(b"")
    try:
        yield E2E(root, service, bindir)
    finally:
        service.close()


@pytest.fixture()
def fresh(e2e):
    e2e.reset()
    return e2e


def request_state(e2e, request_id):
    return e2e.service.open_requests.status(request_id)


def test_e2e_vscode_acked(fresh):
    r = fresh.cad("gui", "open", "pocky/packet_dummy", "--editor", "vscode", "--json", mode="ack")
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout)
    assert doc["opened"] == "vscode" and doc["exit_code"] == 0 and doc["reason"] is None
    assert doc["target"] == {"model": "pocky/packet_dummy"}
    assert doc["service"]["port"] == fresh.service.port and doc["service"]["started"] is False
    assert doc["url"].startswith(f"http://127.0.0.1:{fresh.service.port}/?token=")
    assert {"opened", "editor", "target", "url", "requestId", "reason", "service"} <= set(doc)
    lines = fresh.code_lines()
    assert lines[0]["argv"] == ["--open-url",
                                f"vscode://danillogical.cadstudio/open?req={doc['requestId']}"]
    assert lines[1]["claimed"]["repoRoot"] == str(REPO_ROOT.resolve())
    assert lines[1]["claimed"]["target"] == {"model": "pocky/packet_dummy"}
    assert request_state(fresh, doc["requestId"])["state"] == "acked"
    assert fresh.open_lines() == []  # no browser was launched


def test_e2e_vscode_acked_human_output_hides_token(fresh):
    r = fresh.cad("gui", "open", "pocky/packet_dummy", "--editor", "vscode", mode="ack")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "Opened pocky/packet_dummy in VS Code."
    assert fresh.service.token not in r.stdout + r.stderr


def test_e2e_run_target_acked(fresh):
    r = fresh.cad("gui", "open", "--run", "mj/r1", "--editor", "vscode", "--json", mode="ack")
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout)
    assert doc["opened"] == "vscode" and doc["target"] == {"run": "mj/r1"}
    assert fresh.code_lines()[1]["claimed"]["target"] == {"run": "mj/r1"}


def test_e2e_vscode_nack_exits_3_quickly(fresh):
    start = time.monotonic()
    r = fresh.cad("gui", "open", "pocky/packet_dummy", "--editor", "vscode", "--json", mode="nack")
    assert time.monotonic() - start < 9.0
    assert r.returncode == 3
    doc = json.loads(r.stdout)
    assert doc["opened"] is None and doc["exit_code"] == 3 and "wrong window" in doc["reason"]
    assert fresh.open_lines() == []
    assert request_state(fresh, doc["requestId"])["state"] == "nacked"


def test_e2e_code_launch_failure_exits_3_and_redacts(fresh):
    r = fresh.cad("gui", "open", "pocky/packet_dummy", "--editor", "vscode", "--json", mode="exit1")
    assert r.returncode == 3
    doc = json.loads(r.stdout)
    assert doc["opened"] is None
    assert "LEAKME" not in r.stdout + r.stderr  # token= values in launcher output are redacted
    assert request_state(fresh, doc["requestId"])["state"] == "nacked"


def test_e2e_vscode_silence_times_out_after_10s_and_withdraws_request(fresh):
    start = time.monotonic()
    r = fresh.cad("gui", "open", "pocky/packet_dummy", "--editor", "vscode", "--json", mode="none")
    elapsed = time.monotonic() - start
    assert r.returncode == 3
    doc = json.loads(r.stdout)
    assert doc["opened"] is None and "no acknowledgement within 10 s" in doc["reason"]
    assert elapsed >= 10.0
    state = request_state(fresh, doc["requestId"])
    assert state["state"] == "nacked"
    # A late claim by the extension now finds nothing, so it cannot open a second view.
    status, _ = http_req(fresh.service, "GET", f"/v1/open/{doc['requestId']}")
    assert status == 404


def test_e2e_auto_in_vscode_terminal_nack_falls_back_to_browser(fresh):
    r = fresh.cad("gui", "open", "pocky/packet_dummy", "--json", mode="nack", term="vscode")
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout)
    assert doc["opened"] == "browser" and "wrong window" in doc["reason"]
    assert fresh.open_lines() == [[doc["url"]]]
    assert "model=pocky%2Fpacket_dummy" in doc["url"]
    assert fresh.service.token not in r.stderr  # stderr explains the fallback without the URL


def test_e2e_auto_outside_vscode_terminal_skips_code(fresh):
    r = fresh.cad("gui", "open", "pocky/packet_dummy", "--json", mode="ack", term=None)
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout)
    assert doc["opened"] == "browser" and doc["requestId"] is None
    assert fresh.code_lines() == []
    assert len(fresh.open_lines()) == 1


def test_e2e_browser_editor_and_launch_failure(fresh):
    r = fresh.cad("gui", "open", "pocky/packet_dummy", "--editor", "browser", "--json")
    assert r.returncode == 0 and json.loads(r.stdout)["opened"] == "browser"
    assert fresh.code_lines() == []
    fresh.reset()
    r = fresh.cad("gui", "open", "pocky/packet_dummy", "--editor", "browser", "--json", open_exit=1)
    assert r.returncode == 3
    assert json.loads(r.stdout)["opened"] is None


def test_e2e_no_open(fresh):
    r = fresh.cad("gui", "open", "pocky/packet_dummy", "--no-open", "--json")
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout)
    assert doc["opened"] is None and f"token={fresh.service.token}" in doc["url"]
    assert fresh.code_lines() == [] and fresh.open_lines() == []
    plain = fresh.cad("gui", "open", "pocky/packet_dummy", "--no-open")
    assert plain.returncode == 0
    assert plain.stdout.strip().startswith("http://127.0.0.1:") and plain.stderr == ""


def test_e2e_usage_errors_exit_2(fresh):
    r = fresh.cad("gui", "open", "pocky/does_not_exist", "--json")
    assert r.returncode == 2
    doc = json.loads(r.stdout)
    assert doc["opened"] is None and doc["exit_code"] == 2 and doc["error"]
    r = fresh.cad("gui", "open", "pocky/packet_dummy", "--run", "mj/r1", "--json")
    assert r.returncode == 2
    r = fresh.cad("gui", "open", "--run", "mj/missing", "--json")
    assert r.returncode == 2
    r = fresh.cad("gui", "open", "pocky/packet_dummy", "--editor", "emacs")
    assert r.returncode == 2
    assert fresh.code_lines() == [] and fresh.open_lines() == []


# -- the cadstudio skills ----------------------------------------------------------------

SKILLS = [REPO_ROOT / ".claude/skills/cadstudio/SKILL.md", REPO_ROOT / ".agents/skills/cadstudio/SKILL.md"]
REQUIRED_COMMANDS = ["cad doctor --json", "cad list --json", "cad gui open", "cad gui trajectory"]


def command_lines(text: str) -> list[str]:
    block = re.search(r"```\n(.*?)```", text, re.S)
    assert block, "no command block"
    return [line.split("#")[0].strip() for line in block.group(1).splitlines() if line.strip()]


def exit_codes(text: str) -> set[int]:
    return {int(m.group(1)) for m in re.finditer(r"^\|\s*(\d+)\s*\|", text, re.M)}


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parts[-4])
def test_skill_documents_commands_and_no_secrets(path):
    text = path.read_text()
    assert text.startswith("---\nname: cadstudio\n")
    for command in REQUIRED_COMMANDS:
        assert command in text, command
    assert "/Users/" not in text and "/home/" not in text
    assert not re.search(r"token=\S", text)
    assert not re.search(r"Bearer\s+\S", text)
    assert not re.search(r"\b[A-Za-z0-9_-]{40,}\b", text)
    assert exit_codes(text) == {opener.EXIT_OK, opener.EXIT_ERROR, opener.EXIT_USAGE,
                                opener.EXIT_NOT_OPENED}


def test_skills_document_the_same_commands_and_exit_codes():
    first, second = (p.read_text() for p in SKILLS)
    assert command_lines(first) == command_lines(second)
    assert exit_codes(first) == exit_codes(second)
    for flag in ("--editor auto|vscode|browser", "--no-open", "--json"):
        assert flag in first and flag in second
    for needle in ("opened", "reason", "requestId", "service", "url"):
        assert f"`{needle}`" in first and f"`{needle}`" in second


def test_skill_exit_code_meanings_match_opener():
    for path in SKILLS:
        rows = dict(re.findall(r"^\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*$", path.read_text(), re.M))
        assert "ack" in rows["3"].lower() or "acknowledg" in rows["3"].lower()
        assert "start" in rows["1"].lower() or "answer" in rows["1"].lower()
        assert "unknown model" in rows["2"].lower() or "bad arguments" in rows["2"].lower()
        assert opener.EXIT_OK == 0 and opener.EXIT_NOT_OPENED == 3


def test_connect_ide_skill_prefers_cad_gui_open():
    text = (REPO_ROOT / ".claude/skills/connect-ide/SKILL.md").read_text()
    assert "cad gui open" in text
    assert "/Users/" not in text
