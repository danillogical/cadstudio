"""M4b adversarial evidence tests: tamper, archive/path safety and budgets."""
from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path

import numpy as np
import pytest

from cadkit.physics import require_mujoco
from cadkit.physics.evidence import EvidenceError, bounded_regular_bytes
from cadkit.physics.replay import ReplayError, parse_saved_scene, replay_run
from cadkit.physics.runner import run_scenario_files
from cadkit.physics.scenario import ScenarioError
from cadkit.physics.state_archive import ArchiveError, read_state_archive

pytest.importorskip("mujoco")

PHASES = [
    {"name": "reset", "kind": "reset", "initial": {"carriage_slide": 0.0}},
    {"name": "push", "kind": "actuate", "duration_s": 0.3, "actuator": "push",
     "effort": 1.0},
    {"name": "hold", "kind": "hold", "duration_s": 0.05},
]
CHECKS = [{"name": "held", "kind": "joint_displacement", "joint": "carriage_slide",
           "to_phase": "push", "expected": 0.02, "tolerance": 0.005, "units": "m"}]


def _scenario(**overrides):
    payload = {
        "schema_version": "m4a-1", "scenario_id": "adv", "fixture": "loaded_slider",
        "seed": 3, "timestep_s": 0.001, "sampling_interval_s": 0.002,
        "budgets": {"max_steps": 20000, "max_sim_time_s": 10.0, "max_trace_rows": 20000},
        "phases": PHASES,
    }
    payload.update(overrides)
    return payload


def _acceptance():
    return {"schema_version": "m4a-1", "acceptance_id": "adv_acc", "validity": {},
            "checks": CHECKS}


def _make_run(tmp_path):
    sp = tmp_path / "s.json"
    ap = tmp_path / "a.json"
    sp.write_text(json.dumps(_scenario()), encoding="utf-8")
    ap.write_text(json.dumps(_acceptance()), encoding="utf-8")
    summary = run_scenario_files(sp, ap, tmp_path / "run")
    assert summary["status"] == "PASS"
    return tmp_path / "run"


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _update_manifest(run_dir, rel):
    manifest = json.loads((run_dir / "manifest.json").read_text())
    manifest["artifacts"][rel] = {"sha256": _sha(run_dir / rel),
                                  "bytes": (run_dir / rel).stat().st_size}
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _rewrite_states(run_dir, mutate):
    with np.load(run_dir / "states.npz", allow_pickle=False) as data:
        arrays = {name: np.array(data[name], copy=True) for name in data.files}
    mutate(arrays)
    with (run_dir / "states.npz").open("wb") as fh:
        np.savez_compressed(fh, **arrays)
    _update_manifest(run_dir, "states.npz")


@pytest.fixture
def run_dir(tmp_path):
    return _make_run(tmp_path)


def test_raw_scene_and_asset_tamper_are_error(run_dir, tmp_path, monkeypatch):
    called = {"step": False}
    real_step = require_mujoco().mj_step

    def spy(model, data):
        called["step"] = True
        return real_step(model, data)

    monkeypatch.setattr(require_mujoco(), "mj_step", spy)
    (run_dir / "scene.xml").write_bytes((run_dir / "scene.xml").read_bytes() + b"\n")
    with pytest.raises((EvidenceError, ReplayError)):
        replay_run(run_dir, tmp_path / "rep1")
    assert called["step"] is False

    asset = next((run_dir / "assets").glob("*.stl"))
    asset.write_bytes(asset.read_bytes() + b"\x00")
    (run_dir / "scene.xml").write_bytes(
        (run_dir / "scene.xml").read_bytes()[:-1])
    with pytest.raises((EvidenceError, ReplayError)):
        replay_run(run_dir, tmp_path / "rep2")
    assert called["step"] is False


def test_scenario_and_acceptance_raw_tamper_are_error(run_dir, tmp_path):
    (run_dir / "scenario.json").write_bytes((run_dir / "scenario.json").read_bytes() + b"\n")
    with pytest.raises((EvidenceError, ReplayError)):
        replay_run(run_dir, tmp_path / "rep-s")
    (run_dir / "scenario.json").write_bytes((run_dir / "scenario.json").read_bytes()[:-1])
    (run_dir / "acceptance.lock.json").write_bytes(
        (run_dir / "acceptance.lock.json").read_bytes() + b"\n")
    with pytest.raises((EvidenceError, ReplayError)):
        replay_run(run_dir, tmp_path / "rep-a")


def test_state_byte_tamper_is_error(run_dir, tmp_path):
    raw = bytearray((run_dir / "states.npz").read_bytes())
    raw[-1] ^= 0xFF
    (run_dir / "states.npz").write_bytes(bytes(raw))
    with pytest.raises((EvidenceError, ReplayError)):
        replay_run(run_dir, tmp_path / "rep")


def test_coordinated_control_tamper_diverges_not_pass(run_dir, tmp_path):
    def mutate(arrays):
        arrays["transition_ctrl"][1] = np.asarray(arrays["transition_ctrl"][1]) + 1.0e-3

    _rewrite_states(run_dir, mutate)
    # The archive mapping cross-check rejects a control row that no longer matches the
    # native CTRL component, before any stepping.
    with pytest.raises((ReplayError, EvidenceError, ArchiveError)):
        replay_run(run_dir, tmp_path / "rep")


def test_coordinated_mask_and_shape_tamper_are_error(run_dir, tmp_path):
    def mask(arrays):
        arrays["integration_mask"] = np.asarray(int(arrays["integration_mask"]) ^ 1)

    _rewrite_states(run_dir, mask)
    with pytest.raises((ArchiveError, ReplayError, EvidenceError)):
        replay_run(run_dir, tmp_path / "rep-mask")


def test_nonfinite_state_is_rejected(run_dir, tmp_path):
    def mutate(arrays):
        arrays["integration_state"][1, 0] = np.nan

    _rewrite_states(run_dir, mutate)
    with pytest.raises((ArchiveError, ReplayError)):
        replay_run(run_dir, tmp_path / "rep-nan")


def test_checkpoint_tamper_is_error(run_dir, tmp_path):
    with np.load(run_dir / "checkpoints.npz", allow_pickle=False) as data:
        arrays = {name: np.array(data[name], copy=True) for name in data.files}
    arrays["post_settle"] = arrays["post_settle"] + 1.0e-3
    with (run_dir / "checkpoints.npz").open("wb") as fh:
        np.savez_compressed(fh, **arrays)
    _update_manifest(run_dir, "checkpoints.npz")
    with pytest.raises((ArchiveError, ReplayError, EvidenceError)):
        replay_run(run_dir, tmp_path / "rep-checkpoint")


def test_runtime_version_tamper_is_error(run_dir, tmp_path):
    manifest = json.loads((run_dir / "manifest.json").read_text())
    manifest["solver"]["runtime_identity"]["mujoco"] = "0.0.0"
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises((ReplayError, EvidenceError)):
        replay_run(run_dir, tmp_path / "rep-runtime")


def test_path_traversal_and_symlink_are_rejected(run_dir, tmp_path):
    with pytest.raises(EvidenceError):
        bounded_regular_bytes(run_dir, "../manifest.json")
    link = run_dir / "assets" / "evil.stl"
    link.symlink_to(run_dir / "scene.xml")
    with pytest.raises(EvidenceError):
        bounded_regular_bytes(run_dir, "assets/evil.stl")


def test_archive_member_safety(tmp_path):
    path = tmp_path / "bad.npz"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("time.npy", b"1234")
        zf.writestr("time.npy", b"5678")
    with pytest.raises(ArchiveError, match="duplicate"):
        read_state_archive(path)

    path2 = tmp_path / "traversal.npz"
    with zipfile.ZipFile(path2, "w") as zf:
        zf.writestr("../evil.npy", b"1234")
    with pytest.raises(ArchiveError, match="unsafe path"):
        read_state_archive(path2)

    path3 = tmp_path / "unexpected.npz"
    np.savez_compressed(path3, time=np.zeros(2), evil=np.zeros(2))
    with pytest.raises(ArchiveError, match="not expected"):
        read_state_archive(path3, expected_members={"time"})

    path4 = tmp_path / "object.npz"
    np.savez_compressed(path4, time=np.array([1.0, 2.0], dtype=object))
    with pytest.raises(ArchiveError, match="(?i)object array|unsupported NPY dtype"):
        read_state_archive(path4)

    path5 = tmp_path / "bomb.npz"
    np.savez_compressed(path5, time=np.zeros(4096))
    with pytest.raises(ArchiveError, match="above"):
        read_state_archive(path5, max_bytes=1024)


def test_scene_xml_includes_and_plugins_are_rejected():
    for payload in (b'<!DOCTYPE x><mujoco/>',
                    b'<mujoco><include file="other.xml"/></mujoco>',
                    b'<mujoco><plugin plugin="evil"/></mujoco>',
                    b'<mujoco><compiler meshdir="/etc"/></mujoco>'):
        with pytest.raises(ReplayError):
            parse_saved_scene(payload, {})


def test_state_budget_rejection_before_large_arrays(tmp_path):
    sp = tmp_path / "s.json"
    ap = tmp_path / "a.json"
    ap.write_text(json.dumps(_acceptance()), encoding="utf-8")
    payload = _scenario()
    payload["budgets"]["max_state_rows"] = 10
    sp.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ScenarioError, match="state archive needs"):
        run_scenario_files(sp, ap, tmp_path / "run-rows")
    assert not (tmp_path / "run-rows").exists()

    payload = _scenario()
    payload["budgets"]["max_state_bytes"] = 1024
    sp.write_text(json.dumps(payload), encoding="utf-8")
    summary = run_scenario_files(sp, ap, tmp_path / "run-bytes")
    assert summary["status"] == "ERROR"
    assert "state archive payload would need" in summary["detail"]
    assert not (tmp_path / "run-bytes" / "states.npz").exists()


def test_replay_output_cannot_overwrite_source(run_dir, tmp_path):
    with pytest.raises(ReplayError, match="inside the source"):
        replay_run(run_dir, run_dir / "nested")
    with pytest.raises(ReplayError, match="existing path"):
        replay_run(run_dir, run_dir)


def _update_manifest_and_summary(run_dir, rel):
    _update_manifest(run_dir, rel)
    summary = json.loads((run_dir / "summary.json").read_text())
    manifest = json.loads((run_dir / "manifest.json").read_text())
    manifest["artifacts"]["summary.json"] = {
        "sha256": _sha(run_dir / "summary.json"),
        "bytes": (run_dir / "summary.json").stat().st_size}
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return summary


def test_truncated_archive_is_error_not_pass(run_dir, tmp_path):
    with np.load(run_dir / "states.npz", allow_pickle=False) as data:
        arrays = {name: np.array(data[name], copy=True) for name in data.files}
    rows = arrays["time"].shape[0]
    keep = rows - 60
    for name, array in list(arrays.items()):
        if array.ndim >= 1 and array.shape[0] == rows:
            arrays[name] = array[:keep]
    with (run_dir / "states.npz").open("wb") as fh:
        np.savez_compressed(fh, **arrays)
    _update_manifest(run_dir, "states.npz")
    summary = json.loads((run_dir / "summary.json").read_text())
    summary["telemetry"]["state_rows"] = keep
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    _update_manifest(run_dir, "summary.json")
    with pytest.raises((ReplayError, EvidenceError, ArchiveError)):
        replay_run(run_dir, tmp_path / "rep-truncated")


def test_scene_comment_tamper_is_error_even_with_updated_hashes(run_dir, tmp_path):
    xml = (run_dir / "scene.xml").read_bytes() + b"\n<!-- tamper -->\n"
    (run_dir / "scene.xml").write_bytes(xml)
    _update_manifest(run_dir, "scene.xml")
    summary = json.loads((run_dir / "summary.json").read_text())
    summary["scene"]["xml_sha256"] = _sha(run_dir / "scene.xml")
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    _update_manifest(run_dir, "summary.json")
    with pytest.raises((ReplayError, EvidenceError)):
        replay_run(run_dir, tmp_path / "rep-comment")


def test_single_quoted_external_asset_is_rejected():
    xml = (b'<mujoco><asset><mesh name="m" file=\'/tmp/evil.stl\'/></asset>'
           b'<worldbody/></mujoco>')
    with pytest.raises(ReplayError, match="unsafe asset path"):
        parse_saved_scene(xml, {})


def test_error_source_is_not_replayable(run_dir, tmp_path):
    summary = json.loads((run_dir / "summary.json").read_text())
    summary["status"] = "ERROR"
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    manifest = json.loads((run_dir / "manifest.json").read_text())
    manifest["status"] = "ERROR"
    manifest["artifacts"]["summary.json"] = {"sha256": _sha(run_dir / "summary.json"),
                                             "bytes": (run_dir / "summary.json").stat().st_size}
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises((ReplayError, EvidenceError)):
        replay_run(run_dir, tmp_path / "rep-error")


def test_missing_archive_member_is_explicit_error(run_dir, tmp_path):
    with np.load(run_dir / "states.npz", allow_pickle=False) as data:
        arrays = {name: np.array(data[name], copy=True) for name in data.files}
    arrays.pop("transition_ctrl")
    with (run_dir / "states.npz").open("wb") as fh:
        np.savez_compressed(fh, **arrays)
    _update_manifest(run_dir, "states.npz")
    with pytest.raises((ReplayError, EvidenceError, ArchiveError)):
        replay_run(run_dir, tmp_path / "rep-member")


def test_one_sided_nan_is_a_mismatch():
    from cadkit.physics.replay import _compare_states

    finite = np.zeros((2, 3))
    one_nan = np.zeros((2, 3))
    one_nan[1, 1] = np.nan
    result = _compare_states(finite, one_nan, 0)
    assert result["ok"] is False
    assert result["first_mismatch"] == [1, 1]


def test_manifest_summary_solver_mismatch_is_error(run_dir, tmp_path):
    summary = json.loads((run_dir / "summary.json").read_text())
    summary["solver"]["runtime_identity"]["mujoco"] = "9.9.9-forged"
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    _update_manifest(run_dir, "summary.json")
    with pytest.raises((ReplayError, EvidenceError)):
        replay_run(run_dir, tmp_path / "rep-solver")


def test_state_meta_and_checkpoints_must_be_manifested(run_dir, tmp_path):
    manifest = json.loads((run_dir / "manifest.json").read_text())
    manifest["artifacts"].pop("state_meta.json", None)
    manifest["artifacts"].pop("checkpoints.npz", None)
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises((ReplayError, EvidenceError)):
        replay_run(run_dir, tmp_path / "rep-meta")


def test_tail_fault_after_full_replay_is_inconclusive(run_dir, tmp_path, monkeypatch):
    import mujoco

    real_step = mujoco.mj_step
    summary = json.loads((run_dir / "summary.json").read_text())
    full_steps = summary["telemetry"]["state_rows"] - 1
    calls = {"n": 0}

    def fault(model, data):
        real_step(model, data)
        calls["n"] += 1
        if calls["n"] == full_steps + 1:
            data.qacc[0] = float("nan")

    monkeypatch.setattr(mujoco, "mj_step", fault)
    result = replay_run(run_dir, tmp_path / "rep-tail-fault")
    assert result["status"] == "INCONCLUSIVE"
    assert result["reproduced"] is False
    assert result["state_comparison"]["ok"] is True
    assert result["post_settle_continuation"]["ok"] is False
    assert result["post_settle_continuation"]["rows"] < 401


def test_forged_shape_rejected_before_allocation(tmp_path, monkeypatch):
    import io
    import numpy.lib.format as fmt

    header = io.BytesIO()
    fmt.write_array_header_1_0(header, {"descr": "<f8", "fortran_order": False,
                                        "shape": (1_000_000_000,)})
    bomb = tmp_path / "forged.npz"
    with zipfile.ZipFile(bomb, "w") as zf:
        zf.writestr("time.npy", header.getvalue())
    import cadkit.physics.state_archive as archive_module

    def forbidden(*args, **kwargs):
        raise AssertionError("np.load must not run before header validation")

    monkeypatch.setattr(archive_module.np, "load", forbidden)
    with pytest.raises(ArchiveError, match="needs"):
        read_state_archive(bomb, max_rows=100, max_bytes=1024)


def test_evidence_read_once_and_mutation_fails(run_dir, tmp_path, monkeypatch):
    import cadkit.physics.replay as replay_module

    real = replay_module.bounded_regular_bytes
    counts: dict[str, int] = {}

    def counting(root, rel, **kwargs):
        counts[rel] = counts.get(rel, 0) + 1
        return real(root, rel, **kwargs)

    monkeypatch.setattr(replay_module, "bounded_regular_bytes", counting)
    source = replay_module.load_verified_run(run_dir)
    assert counts.get("states.npz") == 1
    assert counts.get("state_meta.json") == 1
    # Mutating the archive after verification must fail the end-of-run check.
    raw = bytearray((run_dir / "states.npz").read_bytes())
    raw[-1] ^= 0xFF
    (run_dir / "states.npz").write_bytes(bytes(raw))
    with pytest.raises((ReplayError, EvidenceError)):
        replay_module.replay_run(run_dir, tmp_path / "rep-mutate")


def test_fifo_rejection_does_not_block(tmp_path):
    import subprocess
    import sys

    fifo = tmp_path / "afifo"
    os.mkfifo(fifo)
    code = ("from pathlib import Path; from cadkit.physics.evidence import "
            "bounded_regular_bytes, EvidenceError\n"
            f"try:\n bounded_regular_bytes(Path({str(tmp_path)!r}), 'afifo')\n"
            "except EvidenceError as exc:\n print('rejected', exc)\n")
    proc = subprocess.run([sys.executable, "-c", code], cwd=str(Path(__file__).parents[1]),
                          capture_output=True, text=True, timeout=5)
    assert proc.returncode == 0, proc.stderr
    assert "rejected" in proc.stdout


def test_comparison_rejects_infinity_and_nested_metric_mismatch():
    from cadkit.physics.replay import _compare_evaluations, _compare_states

    assert _compare_states(np.array([[np.inf]]), np.array([[0.0]]), 0)["ok"] is False
    assert _compare_states(np.array([[np.inf]]), np.array([[np.inf]]), 0)["ok"] is True
    source = {"status": "PASS", "checks": [], "metrics": {"peak_effort": {"push": 1.0}},
              "validity": {"ok": True, "reasons": []}}
    replay = {"status": "PASS", "checks": [], "metrics": {"peak_effort": {"push": 2.0}},
              "validity": {"ok": True, "reasons": []}}
    assert _compare_evaluations(source, "PASS", [], replay["metrics"],
                                replay["validity"])["ok"] is False
    source["metrics"]["peak_effort"]["push"] = 2.0
    assert _compare_evaluations(source, "PASS", [], replay["metrics"],
                                replay["validity"])["ok"] is True


def test_wall_budget_stops_and_retains_failure_report(run_dir, tmp_path, monkeypatch):
    import cadkit.physics.replay as replay_module

    monkeypatch.setattr(replay_module, "MAX_REPLAY_WALL_S", 0.0)
    with pytest.raises(ReplayError, match="wall budget"):
        replay_module.replay_run(run_dir, tmp_path / "rep-wall")
    payload = json.loads((tmp_path / "rep-wall" / "replay.json").read_text())
    assert payload["status"] == "ERROR"
    assert "wall budget" in payload["detail"]


def test_phase_count_mismatch_is_error(run_dir, tmp_path):
    with np.load(run_dir / "states.npz", allow_pickle=False) as data:
        arrays = {name: np.array(data[name], copy=True) for name in data.files}
    phase = arrays["phase_index"]
    last = phase[-1]
    keep = np.where(phase != last)[0]
    for name, array in list(arrays.items()):
        if array.ndim >= 1 and array.shape[0] == phase.shape[0]:
            arrays[name] = array[keep]
    with (run_dir / "states.npz").open("wb") as fh:
        np.savez_compressed(fh, **arrays)
    _update_manifest(run_dir, "states.npz")
    summary = json.loads((run_dir / "summary.json").read_text())
    summary["telemetry"]["state_rows"] = int(keep.size)
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    _update_manifest(run_dir, "summary.json")
    with pytest.raises((ReplayError, EvidenceError, ArchiveError)):
        replay_run(run_dir, tmp_path / "rep-phase")


def test_missing_required_member_rejected_before_load(tmp_path, monkeypatch):
    import cadkit.physics.state_archive as archive_module

    path = tmp_path / "only-time.npz"
    np.savez_compressed(path, time=np.zeros(3))
    monkeypatch.setattr(archive_module.np, "load", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("np.load must not run")))
    with pytest.raises(ArchiveError, match="missing required members"):
        read_state_archive(path, expected_members={"time", "integration_state"})


def test_wrong_shape_member_is_error(run_dir, tmp_path):
    with np.load(run_dir / "states.npz", allow_pickle=False) as data:
        arrays = {name: np.array(data[name], copy=True) for name in data.files}
    rows = arrays["time"].shape[0]
    arrays["qpos"] = np.zeros((rows, 3))
    with (run_dir / "states.npz").open("wb") as fh:
        np.savez_compressed(fh, **arrays)
    _update_manifest(run_dir, "states.npz")
    with pytest.raises((ReplayError, EvidenceError, ArchiveError)):
        replay_run(run_dir, tmp_path / "rep-shape")


def test_earlier_phase_truncation_with_later_phase_is_error(run_dir, tmp_path):
    with np.load(run_dir / "states.npz", allow_pickle=False) as data:
        arrays = {name: np.array(data[name], copy=True) for name in data.files}
    phase = arrays["phase_index"]
    first = phase[1]
    keep = np.where((phase != first) | (np.arange(phase.size) < 2))[0]
    for name, array in list(arrays.items()):
        if array.ndim >= 1 and array.shape[0] == phase.shape[0]:
            arrays[name] = array[keep]
    with (run_dir / "states.npz").open("wb") as fh:
        np.savez_compressed(fh, **arrays)
    _update_manifest(run_dir, "states.npz")
    summary = json.loads((run_dir / "summary.json").read_text())
    summary["telemetry"]["state_rows"] = int(keep.size)
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    _update_manifest(run_dir, "summary.json")
    with pytest.raises((ReplayError, EvidenceError, ArchiveError)):
        replay_run(run_dir, tmp_path / "rep-truncate-early")


def test_phase_name_permutation_is_error(run_dir, tmp_path):
    with np.load(run_dir / "states.npz", allow_pickle=False) as data:
        arrays = {name: np.array(data[name], copy=True) for name in data.files}
    names = np.array(list(arrays["phase_names"]))
    if names.size > 2:
        names[1], names[2] = names[2], names[1]
    arrays["phase_names"] = names
    with (run_dir / "states.npz").open("wb") as fh:
        np.savez_compressed(fh, **arrays)
    _update_manifest(run_dir, "states.npz")
    with pytest.raises((ReplayError, EvidenceError, ArchiveError)):
        replay_run(run_dir, tmp_path / "rep-names")


def test_failure_after_steps_is_published_as_error(run_dir, tmp_path, monkeypatch):
    import cadkit.physics.replay as replay_module

    def boom(*args, **kwargs):
        raise replay_module.ReplayError("injected post-pass failure")

    monkeypatch.setattr(replay_module, "_compare_states", boom)
    with pytest.raises(replay_module.ReplayError):
        replay_module.replay_run(run_dir, tmp_path / "rep-post")
    payload = json.loads((tmp_path / "rep-post" / "replay.json").read_text())
    assert payload["status"] == "ERROR"
    assert "injected post-pass failure" in payload["detail"]


def test_source_mutation_during_replay_is_not_published_as_pass(run_dir, tmp_path, monkeypatch):
    import cadkit.physics.replay as replay_module

    real_compare = replay_module._compare_states
    state = {"done": False}

    def mutate_then_compare(*args, **kwargs):
        if not state["done"]:
            state["done"] = True
            (run_dir / "states.npz").write_bytes(
                (run_dir / "states.npz").read_bytes() + b"\x00")
        return real_compare(*args, **kwargs)

    monkeypatch.setattr(replay_module, "_compare_states", mutate_then_compare)
    with pytest.raises((replay_module.ReplayError, EvidenceError)):
        replay_module.replay_run(run_dir, tmp_path / "rep-mutate-live")
    payload = json.loads((tmp_path / "rep-mutate-live" / "replay.json").read_text())
    assert payload["status"] == "ERROR"
