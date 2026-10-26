"""Machine-readable ``cad`` output and the core/GUI import boundary (packet G1)."""
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from cadkit.params import REPO_ROOT
from cadkit.project import all_models, discover, list_models

ROOT = REPO_ROOT


def _env() -> dict:
    env = dict(os.environ)
    env["PATH"] = f"{Path.home() / '.local' / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    return env


def cad(*args, timeout=240):
    return subprocess.run([sys.executable, "-m", "cadkit.cli", *args], cwd=ROOT,
                          capture_output=True, text=True, timeout=timeout, env=_env())


def test_list_human_unchanged():
    r = cad("list")
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == all_models()


def test_list_json():
    r = cad("list", "--json")
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout)  # the whole stdout is one document
    assert doc["models"] == all_models()
    projects = {p["name"]: p for p in doc["projects"]}
    assert {"armor", "pocky"} <= set(projects)
    for name, proj in discover().items():
        entry = projects[name]
        assert entry["models"] == list_models(proj)
        params = Path(entry["params_path"])
        assert params.is_absolute() and params.is_file()


def test_build_json_check(tmp_path):
    r = cad("build", "pocky/packet_dummy", "--check", "--json", "--out", str(tmp_path))
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout)
    assert doc["exit_code"] == r.returncode
    assert doc["model"] == "pocky/packet_dummy"
    assert doc["outdir"] == str(tmp_path)
    for name in ("dummy.step", "dummy.stl", "dummy.3mf", "assembly.step"):
        path = tmp_path / name
        assert path.exists(), name
        assert str(path) in doc["written"]
    checks = doc["checks"]["dummy"]
    assert checks
    for check in checks:
        assert isinstance(check["name"], str) and check["name"]
        assert check["status"] in {"pass", "fail", "warn", "info"}
        assert isinstance(check["detail"], str)
    on_disk = json.loads((tmp_path / "report.json").read_text())
    assert {n: [{k: c[k] for k in ("name", "status", "detail", "value")} for c in cs]
            for n, cs in on_disk.items()} == doc["checks"]
    assert doc["report"]["json"] == str(tmp_path / "report.json")
    assert doc["report"]["md"] == str(tmp_path / "report.md")
    assert "wrote" in r.stderr


def test_build_json_failing_exit_unchanged(tmp_path):
    # Large slide_clearance makes the demo cube's 30 mm gap insufficient -> exit 1.
    r = cad("build", "armor/demo_cube", "--check", "--json",
            "--set", "fit.slide_clearance=100", "--out", str(tmp_path))
    assert r.returncode == 1, r.stdout + r.stderr
    doc = json.loads(r.stdout)
    assert doc["exit_code"] == 1
    assert any(c["status"] == "fail" for c in doc["checks"]["cube"])


def test_build_json_without_check(tmp_path):
    r = cad("build", "armor/demo_cube", "--json", "--out", str(tmp_path))
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout)
    assert doc["checks"] is None and doc["report"] is None
    assert doc["exit_code"] == 0


def test_build_json_unknown_model(tmp_path):
    r = cad("build", "nope", "--json", "--out", str(tmp_path))
    assert r.returncode == 1
    doc = json.loads(r.stdout)
    assert "error" in doc and doc["exit_code"] == 1


def test_doctor_json():
    r = cad("doctor", "--json")
    doc = json.loads(r.stdout)
    checks = doc["checks"]
    assert set(checks) == {"python", "uv", "build123d", "mujoco", "node", "npm",
                           "output_dir", "ui_dist", "extension_build"}
    assert checks["python"]["version"] == platform.python_version()
    assert checks["python"]["ok"] is True
    assert checks["build123d"]["available"] is True
    assert isinstance(checks["mujoco"]["available"], bool)
    assert isinstance(checks["output_dir"]["writable"], bool)
    assert r.returncode == (0 if doc["ok"] else 1)


def test_doctor_human():
    r = cad("doctor")
    assert r.returncode in (0, 1)
    assert r.stdout.strip()
    try:
        json.loads(r.stdout)
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError("human doctor output must not be JSON")


def test_gui_package_exists():
    assert (ROOT / "cadkit" / "gui" / "__init__.py").is_file()


CORE_IMPORT_CHECK = """
import importlib, json, sys
from pathlib import Path
import cadkit
root = Path(cadkit.__file__).parent
names = []
for path in sorted(root.rglob("*.py")):
    rel = path.relative_to(root)
    if rel.parts[0] == "gui":
        continue
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if parts:
        names.append("cadkit." + ".".join(parts))
for name in names:
    importlib.import_module(name)
bad = sorted(m for m in sys.modules
             if m == "cadkit.gui" or m.startswith("cadkit.gui.") or m == "http.server")
print(json.dumps({"modules": names, "bad": bad}))
"""


def test_core_does_not_import_gui():
    # A fresh process: the pytest process may already have loaded GUI or server modules.
    r = subprocess.run([sys.executable, "-c", CORE_IMPORT_CHECK], cwd=ROOT,
                       capture_output=True, text=True, timeout=240, env=_env())
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout)
    assert doc["bad"] == []
    for name in ("cadkit.cli", "cadkit.checks", "cadkit.physics.runner"):
        assert name in doc["modules"]
