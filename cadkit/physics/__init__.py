"""Optional rigid-body physics: lazy MuJoCo access and the shared result vocabulary.

Nothing here imports ``mujoco`` at module import time. ``cad list``, ``cad build``,
``cad render`` and ``cad check`` must keep working with the extra absent, so every MuJoCo
symbol is reached through :func:`require_mujoco` or a function-local import.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

#: The status vocabulary is fixed by the M1 contract. A scene that cannot be simulated as
#: declared is an ERROR; the *reason* ("scene invalid: initial overlap") is carried in the
#: detail and in each trial's ``scene_valid`` flag, so no new status is invented.
Status = Literal["PASS", "FAIL", "INCONCLUSIVE", "ERROR"]

#: Exit code per status. ``cad check`` already uses 1 for FAIL; physics extends it.
EXIT_CODES: dict[str, int] = {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2, "ERROR": 3}

MISSING_EXTRA_MESSAGE = (
    "physics needs the optional solver extra, which is not installed: "
    "run `uv sync --extra physics` (mujoco 3.16.0), then retry. "
    "The CAD commands (list/build/render/check) do not need it."
)


class PhysicsUnavailable(RuntimeError):
    """The optional MuJoCo dependency is missing or unimportable."""


def require_mujoco():
    """Import and return ``mujoco``, or raise :class:`PhysicsUnavailable` with a fix."""
    try:
        import mujoco  # noqa: PLC0415 - deliberately lazy
    except Exception as exc:  # ImportError, OSError from a broken binary wheel, ...
        raise PhysicsUnavailable(MISSING_EXTRA_MESSAGE) from exc
    return mujoco


@dataclass
class CheckResult:
    """One named measurement and its verdict."""

    name: str
    status: Status
    detail: str
    value: float | None = None
    units: str = ""


@dataclass
class RunResult:
    """Outcome of one scenario run; ``artifacts`` maps names to files on disk."""

    status: Status
    scenario: str
    metrics: dict[str, float] = field(default_factory=dict)
    checks: list[CheckResult] = field(default_factory=list)
    scene_hash: str = ""
    run_id: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)
    detail: str = ""

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.status]

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "scenario": self.scenario,
            "scene_hash": self.scene_hash,
            "run_id": self.run_id,
            "metrics": self.metrics,
            "checks": [
                {"name": c.name, "status": c.status, "detail": c.detail,
                 "value": c.value, "units": c.units}
                for c in self.checks
            ],
            "artifacts": self.artifacts,
            "detail": self.detail,
        }
