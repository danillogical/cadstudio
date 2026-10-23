"""Environment boundary for the independent S0 evidence tests: absent evidence is optional, broken evidence is not.

``out/`` is git-ignored, so a clean checkout has no generated S0 evidence. The independent S0
module must still run its conformance cases there, and must not silently pass or skip when an
evidence tree exists but is incomplete. This module proves that from the outside: it copies
the real independent S0 module into a temporary project root that symlinks the real ``cadkit``
and ``projects`` sources, leaves ``out/`` in a controlled state, and runs pytest as a
subprocess. Nothing here re-implements the module's own prerequisite helper, and no real
evidence or source file is moved, edited or deleted.

The controlled states, each with a single defect so the failure cause is unambiguous. Only
``absent``, ``file`` and ``dangling`` are built from nothing and so run in a clean checkout;
``partial``, ``truncated``, ``missing_compiled`` and ``present`` mirror the real generated
trees and skip (via ``_require_real_evidence``) when those trees are not present:

``absent``          no ``out/`` at all — the clean-checkout case.
``partial``         the adapter/static compiled tree mirrored, the S0 tree empty (needs real trees).
``truncated``       both real generated trees mirrored, one ``summary.json`` cut in half (needs real trees).
``file``            a regular file where the S0 evidence root belongs.
``dangling``        a dangling symlink where the S0 evidence root belongs.
``missing_compiled`` the S0 tree mirrored, the second generated tree absent (needs real trees).
``present``         both real generated trees, via a symlinked ``out/`` (needs real trees).

The mirror states are built by hard-linking the real files, so a failure is caused by the one
injected defect and not by an artifact this fixture forgot to create. ``_mirror`` refuses to
produce an empty mirror, so a missing source tree cannot silently add a second defect.

Outcomes are read from a ``--junitxml`` report written outside the project root, never from
the captured text: pytest echoes source and docstring lines in tracebacks, so a substring such
as ``FileNotFoundError`` appears in the output of any failure. The per-outcome counts come from
the ``<testsuite>`` attributes, and each failure's cause from the ``<failure message=...>``
attribute, whose first line is ``<ExceptionType>: <message>`` for the exception actually raised.

The implementer module ``tests/test_pocky_physics_s0.py`` is out of scope here: it already
handles absent evidence with per-file ``pytest.skip`` guards of its own.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
S0_INDEPENDENT = REPO_ROOT / "tests" / "test_pocky_physics_s0_independent.py"
#: Both generated trees the independent module reads.
S0_TREE = REPO_ROOT / "out" / "mujoco-m5a" / "s0"
COMPILED_TREE = REPO_ROOT / "out" / "mujoco-m5a" / "adapter-static" / "compiled"

#: Pure cases that must run in every environment: plan thresholds and the SI unit table.
PURE_CASES = ("test_zero_point_two_degrees_is_recomputed_in_radians "
              "or test_units_are_si_and_thresholds_are_the_plan_numbers")
#: A case that reads generated run evidence and must not be silently satisfied without it.
EVIDENCE_CASES = "test_invalid_runs_are_inconclusive_and_never_pass"
SELECTION = f"({PURE_CASES} or {EVIDENCE_CASES})"
#: 2 pure cases + 8 parameterised evidence cases.
PURE_COUNT = 2
EVIDENCE_COUNT = 8


@pytest.fixture(scope="module", autouse=True)
def _require_physics():
    pytest.importorskip("mujoco", reason="the S0 evidence modules need the optional physics extra")


def _mirror(tree: Path, root: Path) -> None:
    """Hard-link every file of a generated tree into the temporary root; never mirror nothing."""
    assert tree.is_dir(), f"cannot mirror {tree}: the source tree is not a directory"
    target_root = root / tree.relative_to(REPO_ROOT)
    mirrored = 0
    for source in tree.rglob("*"):
        if not source.is_file():
            continue
        link = target_root / source.relative_to(tree)
        link.parent.mkdir(parents=True, exist_ok=True)
        os.link(source, link)
        mirrored += 1
    assert mirrored > 0, f"cannot mirror {tree}: it contains no files"


def _temporary_root(tmp_path: Path, *, evidence: str) -> Path:
    """Copy the real S0 test module into a temp root with symlinked sources.

    The mirror states hard-link real evidence files, so the caller must tear the root down:
    a surviving hard link is a live handle on the real inode. ``_run_module``'s callers get
    that teardown from ``_teardown_after``; nothing here writes through a link.
    """
    root = tmp_path / "project"
    (root / "tests").mkdir(parents=True)
    shutil.copyfile(S0_INDEPENDENT, root / "tests" / S0_INDEPENDENT.name)
    for name in ("cadkit", "projects"):
        (root / name).symlink_to(REPO_ROOT / name, target_is_directory=True)
    s0_root = root / S0_TREE.relative_to(REPO_ROOT)

    if evidence == "absent":
        pass
    elif evidence == "partial":
        _mirror(COMPILED_TREE, root)
        s0_root.mkdir(parents=True)
    elif evidence == "truncated":
        _mirror(S0_TREE, root)
        _mirror(COMPILED_TREE, root)
        victim = s0_root / "runs" / "s0_f000" / "summary.json"
        data = victim.read_bytes()
        assert len(data) > 1000, "the real summary is too small to truncate meaningfully"
        victim.unlink()
        victim.write_bytes(data[: len(data) // 2])
    elif evidence == "file":
        s0_root.parent.mkdir(parents=True)
        s0_root.write_text("not a directory\n", encoding="utf-8")
    elif evidence == "dangling":
        s0_root.parent.mkdir(parents=True)
        s0_root.symlink_to(tmp_path / "does-not-exist", target_is_directory=True)
    elif evidence == "missing_compiled":
        _mirror(S0_TREE, root)
    elif evidence == "present":
        (root / "out").symlink_to(REPO_ROOT / "out", target_is_directory=True)
    else:
        raise AssertionError(f"unknown evidence state {evidence!r}")
    return root


@pytest.fixture(autouse=True)
def _teardown_after(request, tmp_path: Path):
    """Remove every temporary root after the test, breaking all hard links to real evidence."""
    yield
    for child in tmp_path.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        elif child.is_symlink() or child.is_file():
            child.unlink(missing_ok=True)


@dataclass(frozen=True)
class Outcome:
    """One subprocess run: exit status plus the junit counts and per-case failure messages."""

    returncode: int
    output: str
    tests: int
    failures: int
    errors: int
    skipped: int
    failed: tuple  # of (testcase name, failure message)
    skip_reasons: tuple

    @property
    def passed(self) -> int:
        return self.tests - self.failures - self.errors - self.skipped


def _run_module(root: Path, junit: Path) -> Outcome:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)
    env.pop("PYTEST_ADDOPTS", None)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(root / "tests" / S0_INDEPENDENT.name),
         "-q", "-rs", "-p", "no:cacheprovider", f"--junitxml={junit}", "-k", SELECTION],
        cwd=root, env=env, capture_output=True, text=True, timeout=300,
    )
    output = result.stdout + result.stderr
    assert junit.is_file(), f"pytest wrote no junit report\n{output}"
    tree = ET.parse(junit).getroot()
    suite = tree if tree.tag == "testsuite" else tree.find("testsuite")
    failed, skipped = [], []
    for case in suite.iter("testcase"):
        for kind in ("failure", "error"):
            node = case.find(kind)
            if node is not None:
                failed.append((case.get("name"), node.get("message") or ""))
        node = case.find("skipped")
        if node is not None:
            skipped.append(node.get("message") or "")
    return Outcome(
        returncode=result.returncode, output=output,
        tests=int(suite.get("tests")), failures=int(suite.get("failures")),
        errors=int(suite.get("errors")), skipped=int(suite.get("skipped")),
        failed=tuple(failed), skip_reasons=tuple(skipped),
    )


def _run(tmp_path: Path, evidence: str) -> Outcome:
    root = _temporary_root(tmp_path, evidence=evidence)
    # The report lives beside, not inside, the project root, so it never touches mirrored evidence.
    return _run_module(root, tmp_path / "junit.xml")


def _assert_failures(outcome: Outcome, *, count: int, exc_type: str, fragment: str) -> None:
    """Exactly ``count`` evidence cases failed, each raising ``exc_type`` with ``fragment``."""
    assert outcome.returncode != 0, outcome.output
    assert (outcome.failures, outcome.errors, outcome.skipped) == (count, 0, 0), outcome.output
    assert outcome.passed == outcome.tests - count, outcome.output
    assert len(outcome.failed) == count, outcome.output
    for name, message in outcome.failed:
        assert name.startswith(EVIDENCE_CASES), (name, message)
        first = message.splitlines()[0] if message else ""
        # The crash line is "<ExceptionType>: <text>"; a dotted module prefix is allowed.
        kind, _, text = first.partition(": ")
        assert kind.rsplit(".", 1)[-1] == exc_type, (name, message)
        assert fragment in text, (name, message)


def test_absent_generated_evidence_runs_pure_cases_and_skips_only_evidence(tmp_path: Path):
    """A clean checkout: the conformance cases run and pass; only evidence cases skip."""
    root = _temporary_root(tmp_path, evidence="absent")
    assert not (root / "out").exists()
    outcome = _run_module(root, tmp_path / "junit.xml")

    assert outcome.returncode == 0, outcome.output
    assert (outcome.failures, outcome.errors) == (0, 0), outcome.output
    # The evidence cases skip, and the skip names the optional prerequisite rather than a
    # per-file accident: it must not be reported as a pass.
    assert outcome.skipped == EVIDENCE_COUNT, outcome.output
    assert outcome.passed == PURE_COUNT, outcome.output
    assert len(outcome.skip_reasons) == EVIDENCE_COUNT, outcome.output
    assert all(r.startswith("optional generated evidence absent") for r in outcome.skip_reasons), \
        outcome.skip_reasons


def _require_real_evidence() -> None:
    """Skip the mirror-based states when the real generated trees are absent."""
    if not (S0_TREE.is_dir() and COMPILED_TREE.is_dir()):
        pytest.skip("optional generated evidence absent: the real out/mujoco-m5a trees are "
                    "not present in this checkout")


def test_partial_generated_evidence_fails_loudly_instead_of_skipping(tmp_path: Path):
    """An evidence set that exists but is empty is broken evidence, not an absent prerequisite."""
    _require_real_evidence()
    outcome = _run(tmp_path, "partial")

    _assert_failures(outcome, count=EVIDENCE_COUNT, exc_type="FileNotFoundError",
                     fragment="summary.json")
    assert outcome.passed == PURE_COUNT, outcome.output


def test_truncated_artifact_fails_on_parsing_not_on_absence(tmp_path: Path):
    """A complete mirror with one halved summary fails on corruption, not a missing file."""
    _require_real_evidence()
    outcome = _run(tmp_path, "truncated")

    # Only the case that reads the corrupted run fails; the other seven stems are intact, which
    # proves the failure is caused by the corruption rather than by a missing artifact.
    _assert_failures(outcome, count=1, exc_type="JSONDecodeError", fragment="")
    assert outcome.failed[0][0].endswith("[s0_f000]"), outcome.failed
    assert outcome.passed == PURE_COUNT + EVIDENCE_COUNT - 1, outcome.output


def test_evidence_root_that_is_a_file_fails_instead_of_skipping(tmp_path: Path):
    """A file where the evidence root belongs is broken evidence, not an absent prerequisite."""
    outcome = _run(tmp_path, "file")

    _assert_failures(outcome, count=EVIDENCE_COUNT, exc_type="AssertionError",
                     fragment="exists but is not a directory")
    assert outcome.passed == PURE_COUNT, outcome.output


def test_dangling_evidence_root_fails_instead_of_skipping(tmp_path: Path):
    """A dangling symlink is a broken evidence path, not an absent one."""
    outcome = _run(tmp_path, "dangling")

    _assert_failures(outcome, count=EVIDENCE_COUNT, exc_type="AssertionError",
                     fragment="exists but is not a directory")
    assert outcome.passed == PURE_COUNT, outcome.output


def test_missing_second_evidence_tree_fails_instead_of_skipping(tmp_path: Path):
    """The prerequisite is both generated trees: S0 present with the compiled audits gone fails."""
    _require_real_evidence()
    outcome = _run(tmp_path, "missing_compiled")

    _assert_failures(outcome, count=EVIDENCE_COUNT, exc_type="AssertionError",
                     fragment="adapter-static")
    assert outcome.passed == PURE_COUNT, outcome.output


def test_present_generated_evidence_executes_the_same_cases(tmp_path: Path):
    """With the real evidence trees the identical selection passes, so the skip was environment only."""
    _require_real_evidence()
    outcome = _run(tmp_path, "present")

    assert outcome.returncode == 0, outcome.output
    assert (outcome.failures, outcome.errors, outcome.skipped) == (0, 0, 0), outcome.output
    assert outcome.passed == PURE_COUNT + EVIDENCE_COUNT, outcome.output
