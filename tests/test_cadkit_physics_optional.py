"""Optional-dependency isolation: MuJoCo must never be needed by the CAD commands.

The block is done by making ``import mujoco`` raise inside a subprocess, which is what a
missing extra looks like from the package's point of view. Nothing is uninstalled.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cadkit.params import REPO_ROOT

BLOCKER = """
import sys, builtins
_real = builtins.__import__
def _blocked(name, *a, **k):
    if name == "mujoco" or name.startswith("mujoco."):
        raise ModuleNotFoundError("No module named 'mujoco'")
    return _real(name, *a, **k)
builtins.__import__ = _blocked
sys.argv = ["cad"] + {argv!r}
from cadkit.cli import main
main()
"""


def _env() -> dict:
    env = dict(os.environ)
    env["PATH"] = f"{Path.home() / '.local' / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    return env


def _run_blocked(argv, timeout=240):
    code = BLOCKER.format(argv=argv)
    return subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT,
                          capture_output=True, text=True, timeout=timeout, env=_env())


def test_cad_list_works_without_mujoco():
    r = _run_blocked(["list"])
    assert r.returncode == 0, r.stderr
    assert "starter/box" in r.stdout


def test_cad_check_works_without_mujoco(tmp_path):
    r = _run_blocked(["check", "starter/box", "--out", str(tmp_path)])
    assert r.returncode == 0, r.stdout + r.stderr
    assert (tmp_path / "report.json").is_file()


def test_cad_build_works_without_mujoco(tmp_path):
    r = _run_blocked(["build", "starter/box", "--out", str(tmp_path)])
    assert r.returncode == 0, r.stdout + r.stderr
    assert (tmp_path / "tray.step").is_file()


def test_physics_smoke_without_extra_is_actionable(tmp_path):
    target = tmp_path / "should-not-exist"
    r = _run_blocked(["physics", "smoke", "--out", str(target)])
    assert r.returncode == 3, r.stdout + r.stderr
    assert "uv sync --extra physics" in r.stderr
    assert '"status": "ERROR"' in r.stdout
    assert "Traceback" not in r.stderr
    # no partial artifacts: the run must fail before writing anything
    assert not target.exists()
    payload = json.loads([ln for ln in r.stdout.splitlines() if ln.startswith("{")][-1])
    assert payload["status"] == "ERROR"


def test_physics_module_import_is_lazy():
    """Importing the package and the CLI must not pull MuJoCo in."""
    code = (
        "import sys; import cadkit.cli, cadkit.physics; "
        "print('mujoco' in sys.modules)"
    )
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT,
                       capture_output=True, text=True, timeout=120, env=_env())
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "False"
