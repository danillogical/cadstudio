"""``cad physics run`` through a fake project: hooks, options lock, guards and replay.

No project-specific names: the project is a stand-in whose hooks return the registered
drop-box assembly, injected by patching the CLI's ``resolve``.
"""
from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("mujoco", reason="optional physics extra not installed")

import cadkit.cli as cli  # noqa: E402
from cadkit.physics.scenario import build_fixture  # noqa: E402
from cadkit.project import Project  # noqa: E402

MODEL = "drop"
OPTIONS_LOCK = "assembly_options.lock.toml"


def _scenario(timestep=0.001, **overrides):
    payload = {
        "schema_version": "m4a-1", "scenario_id": "fake_drop", "fixture": "drop_box",
        "seed": 3, "sampling_interval_s": 0.01,
        "budgets": {"max_steps": 20000, "max_sim_time_s": 10.0, "max_trace_rows": 20000},
        "phases": [{"name": "reset", "kind": "reset"},
                   {"name": "settle", "kind": "settle", "duration_s": 0.3}],
    }
    if timestep is not None:
        payload["timestep_s"] = timestep
    payload.update(overrides)
    return payload


ACCEPTANCE = {
    "schema_version": "m4a-1", "acceptance_id": "fake_drop_acc",
    "validity": {"max_penetration_m": 0.005},
    "checks": [{"name": "pen", "kind": "penetration_bound", "max": 0.005, "units": "m"}],
}


def _main(argv):
    """``cli.main`` ends in ``sys.exit``; return the exit code instead."""
    try:
        return cli.main(argv)
    except SystemExit as exc:
        return exc.code


class Harness:
    def __init__(self, tmp_path, monkeypatch, capsys):
        self.tmp, self.capsys = tmp_path, capsys
        self.calls: list = []
        self.monkeypatch = monkeypatch

    def project(self, *, physics=True, with_options=True, none_for_model=False):
        def plain(model, p):
            self.calls.append(("physics", model))
            return None if none_for_model else build_fixture("drop_box", 0.001)

        def opts(model, p, options):
            self.calls.append(("physics_with_options", model, dict(options)))
            if none_for_model:
                return None
            spec = build_fixture("drop_box", 0.001)
            if "friction" in options:
                spec = replace(spec, friction=(float(options["friction"]), 0.005, 0.0001))
            return spec

        project = Project(name="fakeproj", params_path=Path("unused.toml"),
                          load_params=lambda path: None, models=cli,
                          physics=plain if physics else None,
                          physics_with_options=opts if with_options else None)

        def fake_resolve(spec):
            if spec != f"fakeproj/{MODEL}":
                raise KeyError(f"unknown model {spec!r}")
            return project, MODEL

        self.monkeypatch.setattr(cli, "resolve", fake_resolve)
        return project

    def write(self, name, payload):
        path = self.tmp / name
        path.write_text(payload if isinstance(payload, str) else json.dumps(payload),
                        encoding="utf-8")
        return path

    def run(self, *, scenario=None, options=None, out=None, model=f"fakeproj/{MODEL}",
            extra=()):
        scenario_path = self.write("scenario.json", scenario or _scenario())
        acceptance_path = self.write("acceptance.json", ACCEPTANCE)
        out = out or self.tmp / "run"
        argv = ["physics", "run", model, "--scenario", str(scenario_path),
                "--acceptance", str(acceptance_path), "--out", str(out), *extra]
        if options is not None:
            argv += ["--options", str(options)]
        self.capsys.readouterr()
        code = _main(argv)
        captured = self.capsys.readouterr()
        return code, captured.out, captured.err, Path(out)


@pytest.fixture
def h(tmp_path, monkeypatch, capsys):
    return Harness(tmp_path, monkeypatch, capsys)


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- success
def test_run_with_options_writes_lock_and_records_sha_everywhere(h):
    h.project()
    raw = 'friction = 0.35  # keep this comment byte-exact\nlabel = "a"\nvalues = [1, 2]\n'
    options = h.write("options.toml", raw)
    code, out, err, run = h.run(options=options)
    assert code == 0, out + err
    assert '"status": "PASS"' in out
    lock = run / OPTIONS_LOCK
    assert lock.read_bytes() == raw.encode("utf-8")
    sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    summary, manifest = _json(run / "summary.json"), _json(run / "manifest.json")
    assert summary["assembly_options_sha256"] == sha
    assert manifest["assembly_options_sha256"] == sha
    assert summary["assembly_options"] == tomllib.loads(raw) == manifest["assembly_options"]
    assert sha in out
    assert h.calls == [("physics_with_options", MODEL, tomllib.loads(raw))]
    # The explicit run choice reached the physics, and the identity depends on it.
    cols = [c for b in summary["physical_inputs"]["bodies"] for p in b["parts"]
            for c in p["colliders"]]
    assert all(c["friction"][0] == pytest.approx(0.35) for c in cols)

    other = h.write("options2.toml", "friction = 0.36\n")
    code2, out2, err2, run2 = h.run(options=other, out=h.tmp / "run2")
    assert code2 == 0, out2 + err2
    assert _json(run2 / "summary.json")["identity"] != summary["identity"]


def test_options_sha_is_part_of_the_run_identity(h):
    """Same scene, only a comment differs in the options: the options hash still changes identity."""
    h.project()
    a = h.run(options=h.write("a.toml", "friction = 0.4\n"), out=h.tmp / "a")
    b = h.run(options=h.write("b.toml", "friction = 0.4 # same value\n"), out=h.tmp / "b")
    assert a[0] == 0 and b[0] == 0
    sa, sb = _json(a[3] / "summary.json"), _json(b[3] / "summary.json")
    assert sa["scene"]["scene_hash"] == sb["scene"]["scene_hash"]
    assert sa["assembly_options_sha256"] != sb["assembly_options_sha256"]
    assert sa["identity"] != sb["identity"]


def test_replay_reproduces_a_cli_run_with_options(h):
    h.project()
    code, out, err, run = h.run(options=h.write("options.toml", "friction = 0.35\n"))
    assert code == 0, out + err
    rep = h.tmp / "rep"
    rc = _main(["physics", "replay", str(run), "--out", str(rep)])
    captured = h.capsys.readouterr()
    assert rc == 0, captured.out + captured.err
    assert '"status": "PASS"' in captured.out
    assert "reproduced True" in captured.out


def test_exit_code_follows_status_fail(h):
    h.project()
    scenario = _scenario(phases=[{"name": "reset", "kind": "reset"},
                                 {"name": "settle", "kind": "settle", "duration_s": 0.3}])
    path = h.write("scenario.json", scenario)
    acceptance = dict(ACCEPTANCE, checks=[{"name": "pen", "kind": "penetration_bound",
                                           "max": 1e-12, "units": "m"}], validity={})
    acc = h.write("acceptance.json", acceptance)
    code = _main(["physics", "run", f"fakeproj/{MODEL}", "--scenario", str(path),
                     "--acceptance", str(acc), "--out", str(h.tmp / "failrun")])
    out = h.capsys.readouterr().out
    assert code == 1, out
    assert '"status": "FAIL"' in out


def test_no_options_with_only_physics_hook_runs_and_replays(h):
    h.project(with_options=False)
    code, out, err, run = h.run()
    assert code == 0, out + err
    assert h.calls == [("physics", MODEL)]
    lock = run / OPTIONS_LOCK
    summary = _json(run / "summary.json")
    if lock.exists():  # an empty-options lock must still be a valid, hash-recorded document
        assert tomllib.loads(lock.read_text(encoding="utf-8")) == {}
        assert summary["assembly_options_sha256"] == hashlib.sha256(
            lock.read_bytes()).hexdigest()
    rc = _main(["physics", "replay", str(run), "--out", str(h.tmp / "rep")])
    assert rc == 0, h.capsys.readouterr()


def test_no_options_prefers_physics_with_options_with_empty_mapping(h):
    h.project()
    code, out, err, _ = h.run()
    assert code == 0, out + err
    assert h.calls == [("physics_with_options", MODEL, {})]


# --------------------------------------------------------------------------- error paths
def _assert_error(result, fragment=None):
    code, out, err, run = result
    assert code == 3, out + err
    assert '"status": "ERROR"' in out
    assert "Traceback" not in err
    if fragment:
        assert fragment in out + err
    return run


def test_options_without_physics_with_options_hook_is_error(h):
    h.project(with_options=False)
    result = h.run(options=h.write("options.toml", "friction = 0.4\n"))
    run = _assert_error(result, "physics_with_options")
    assert not run.exists()
    assert h.calls == []


def test_missing_hooks_is_error(h):
    h.project(physics=False, with_options=False)
    _assert_error(h.run(), "no physics assembly")


def test_hook_returning_none_is_error(h):
    h.project(none_for_model=True)
    _assert_error(h.run(), "no physics assembly")


def test_unknown_model_is_error(h):
    h.project()
    _assert_error(h.run(model="fakeproj/no_such_model"))
    _assert_error(h.run(model="nope/drop", out=h.tmp / "other"))


def test_unknown_model_with_real_resolve_is_error(tmp_path, capsys):
    scenario = tmp_path / "s.json"
    scenario.write_text(json.dumps(_scenario()), encoding="utf-8")
    acceptance = tmp_path / "a.json"
    acceptance.write_text(json.dumps(ACCEPTANCE), encoding="utf-8")
    code = _main(["physics", "run", "no/such_model", "--scenario", str(scenario),
                     "--acceptance", str(acceptance), "--out", str(tmp_path / "r")])
    captured = capsys.readouterr()
    assert code == 3, captured.out + captured.err
    assert '"status": "ERROR"' in captured.out
    assert not (tmp_path / "r").exists()


def test_scenario_timestep_mismatch_is_error(h):
    h.project()
    run = _assert_error(h.run(scenario=_scenario(timestep=0.002)), "timestep")
    assert not (run / "summary.json").exists()


def test_scenario_without_timestep_is_error(h):
    h.project()
    run = _assert_error(h.run(scenario=_scenario(timestep=None)), "timestep_s")
    assert not (run / "summary.json").exists()


@pytest.mark.parametrize("text", [
    "[nested]\nvalue = 1\n",
    "key = { inner = 1 }\n",
    "[[rows]]\nvalue = 1\n",
    "mixed = [1, [2]]\n",
    "this is = = not toml\n",
])
def test_bad_options_toml_is_error(h, text):
    h.project()
    result = h.run(options=h.write("options.toml", text))
    run = _assert_error(result)
    assert not (run / OPTIONS_LOCK).exists()


def test_oversize_options_is_error(h):
    h.project()
    big = "note = \"" + "x" * (cli.MAX_OPTIONS_BYTES + 10) + "\"\n"
    _assert_error(h.run(options=h.write("options.toml", big)), "exceeds")


def test_missing_options_file_is_error(h):
    h.project()
    _assert_error(h.run(options=h.tmp / "absent.toml"))


def test_existing_out_directory_is_refused_and_untouched(h):
    h.project()
    out = h.tmp / "taken"
    out.mkdir()
    (out / "keep.txt").write_text("precious", encoding="utf-8")
    code, stdout, stderr, _ = h.run(out=out)
    assert code == 3, stdout + stderr
    assert '"status": "ERROR"' in stdout
    assert sorted(p.name for p in out.iterdir()) == ["keep.txt"]


# --------------------------------------------------------------------------- tamper
def _good_run(h, options="friction = 0.35\n"):
    h.project()
    code, out, err, run = h.run(options=h.write("options.toml", options))
    assert code == 0, out + err
    return run


def _replay_code(h, run, name):
    code = _main(["physics", "replay", str(run), "--out", str(h.tmp / name)])
    captured = h.capsys.readouterr()
    return code, captured.out + captured.err


def test_tampered_lock_file_fails_replay(h):
    run = _good_run(h)
    lock = run / OPTIONS_LOCK
    lock.write_text("friction = 0.99\n", encoding="utf-8")
    code, text = _replay_code(h, run, "rep")
    assert code == 3, text
    assert "Traceback" not in text


def test_lock_file_with_only_whitespace_change_fails_replay(h):
    """The hash is over raw bytes, so even a semantically equal rewrite is rejected."""
    run = _good_run(h)
    lock = run / OPTIONS_LOCK
    lock.write_bytes(lock.read_bytes() + b"\n")
    code, text = _replay_code(h, run, "rep")
    assert code == 3, text


def test_deleted_lock_file_fails_replay(h):
    run = _good_run(h)
    (run / OPTIONS_LOCK).unlink()
    code, text = _replay_code(h, run, "rep")
    assert code == 3, text


def test_stripping_options_record_from_summary_fails_replay(h):
    run = _good_run(h)
    path = run / "summary.json"
    data = _json(path)
    data.pop("assembly_options_sha256")
    data.pop("assembly_options")
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    code, text = _replay_code(h, run, "rep")
    assert code == 3, text
