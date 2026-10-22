"""Versioned, declarative M4a scenarios and acceptance criteria.

The scenario file is deliberately **data**, never code. It may select one of a small registry
of generic analytic fixtures, declare reset coordinates and timed phases, and set runtime
budgets. It cannot import modules, execute shell commands, name files outside the run
directory, or carry arbitrary Python objects. Acceptance thresholds live in a separate file
so a candidate scenario cannot relax the criteria it is measured against.

Both files are strict JSON:

* duplicate object keys are rejected, not last-one-wins;
* ``NaN``/``Infinity`` literals are rejected;
* unknown fields are rejected at every level;
* every numeric field must be finite and in its documented range;
* references (joints, actuators, bodies, phases) are resolved against the assembled scene
  before a step is taken.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "m4a-1"
SCENARIO_SCHEMA_VERSION = SCHEMA_VERSION
ACCEPTANCE_SCHEMA_VERSION = SCHEMA_VERSION

PHASE_KINDS = ("reset", "settle", "actuate", "release", "hold")
TIMED_PHASE_KINDS = ("settle", "actuate", "release", "hold")
CHECK_KINDS = (
    "joint_displacement",
    "return_displacement",
    "terminal_speed",
    "body_speed",
    "effort_bound",
    "contact_force_bound",
    "penetration_bound",
    "event_count",
    "event_verdict",
)
EVENT_KINDS = ("exit_crossing", "supported_presentation")
FIXTURE_IDS = ("loaded_slider", "loaded_slider_no_spring",
               "loaded_slider_negative_gear", "drop_box",
               "presentation_aperture", "presentation_aperture_blocked",
               "presentation_aperture_double")

#: A scenario/acceptance file is small configuration. The cap prevents a malformed or
#: hostile file from consuming memory before any validation can run.
MAX_CONFIG_BYTES = 1 << 20


class ScenarioError(ValueError):
    """A scenario or acceptance file cannot be admitted as declared."""


# --------------------------------------------------------------------------- strict JSON
def _reject_constant(value: str):
    raise ScenarioError(f"non-finite JSON constant {value!r} is not allowed")


def _reject_duplicate_keys(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ScenarioError(f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def _read_bounded_text(path: Path, what: str) -> str:
    """Read a regular UTF-8 file with a hard allocation bound.

    The cap is enforced **before** the whole file is materialized: at most
    ``MAX_CONFIG_BYTES + 1`` bytes are requested, and the descriptor is checked to be a
    regular file first, so a directory, FIFO, device or socket is rejected instead of read.
    The exact bytes are retained for the frozen lock/hash.
    """
    path = Path(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ScenarioError(f"cannot read {what} {path}: {exc}") from exc
    try:
        try:
            mode = os.fstat(fd).st_mode
        except OSError as exc:
            raise ScenarioError(f"cannot stat {what} {path}: {exc}") from exc
        if not stat.S_ISREG(mode):
            raise ScenarioError(
                f"{what} {path} is not a regular file (mode {stat.filemode(mode)}); "
                f"only regular files are accepted")
        chunks = []
        remaining = MAX_CONFIG_BYTES + 1
        while remaining > 0:
            try:
                chunk = os.read(fd, remaining)
            except OSError as exc:
                raise ScenarioError(f"cannot read {what} {path}: {exc}") from exc
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
    finally:
        os.close(fd)
    if len(raw) > MAX_CONFIG_BYTES:
        raise ScenarioError(
            f"{what} {path} is at least {len(raw)} bytes, above the {MAX_CONFIG_BYTES} cap")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ScenarioError(f"cannot read {what} {path} as UTF-8: {exc}") from exc


def _read_json(path: Path, what: str) -> tuple[dict, str]:
    text = _read_bounded_text(Path(path), what)
    value = _parse_json_text(text, f"{what} {path}")
    return value, text


def _parse_json_text(text: str, where: str) -> dict:
    try:
        value = json.loads(text, parse_constant=_reject_constant,
                           object_pairs_hook=_reject_duplicate_keys)
    except ScenarioError:
        raise
    except json.JSONDecodeError as exc:
        raise ScenarioError(f"{where} is not valid JSON: {exc}") from exc
    except RecursionError as exc:
        raise ScenarioError(f"{where} is nested too deeply to parse") from exc
    if not isinstance(value, dict):
        raise ScenarioError(f"{where} must contain a JSON object")
    return value


def _check_keys(obj: dict, where: str, *, required=(), optional=()) -> None:
    allowed = set(required) | set(optional)
    unknown = sorted(set(obj) - allowed)
    if unknown:
        raise ScenarioError(f"{where} has unknown field(s) {unknown}")
    missing = sorted(set(required) - set(obj))
    if missing:
        raise ScenarioError(f"{where} is missing required field(s) {missing}")


def _number(obj: dict, key: str, where: str, *, positive: bool = False,
            nonnegative: bool = False) -> float:
    value = obj[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScenarioError(f"{where}.{key} must be a number, got {value!r}")
    try:
        value = float(value)
    except (OverflowError, ValueError, TypeError) as exc:
        raise ScenarioError(f"{where}.{key} is not a representable number: {value!r}") from exc
    if not math.isfinite(value):
        raise ScenarioError(f"{where}.{key} must be finite, got {value!r}")
    if positive and value <= 0.0:
        raise ScenarioError(f"{where}.{key} must be positive, got {value!r}")
    if nonnegative and value < 0.0:
        raise ScenarioError(f"{where}.{key} must be non-negative, got {value!r}")
    return value


def _integer(obj: dict, key: str, where: str, *, positive: bool = False) -> int:
    value = obj[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ScenarioError(f"{where}.{key} must be an integer, got {value!r}")
    if positive and value <= 0:
        raise ScenarioError(f"{where}.{key} must be positive, got {value!r}")
    return value


def _string(obj: dict, key: str, where: str, *, choices=None) -> str:
    value = obj[key]
    if not isinstance(value, str) or not value:
        raise ScenarioError(f"{where}.{key} must be a non-empty string, got {value!r}")
    if choices is not None and value not in choices:
        raise ScenarioError(f"{where}.{key} must be one of {list(choices)}, got {value!r}")
    return value


def _safe_id(value: str, what: str) -> str:
    from .schema import safe_filename

    try:
        return safe_filename(value)
    except ValueError as exc:
        raise ScenarioError(f"{what}: {exc}") from exc


def scenario_from_text(text: str) -> ScenarioSpec:
    """Parse a scenario document that was already read (no second filesystem read)."""
    return _scenario_from_obj(_parse_json_text(text, "scenario text"), text)


def acceptance_from_text(text: str) -> AcceptanceSpec:
    return _acceptance_from_obj(_parse_json_text(text, "acceptance text"), text)


def scenario_text_matches(spec: ScenarioSpec, text: str) -> bool:
    """Whether ``text`` parses to the same scenario as ``spec``.

    Used before copying a source document into a run: a typed spec mutated after loading keeps
    its old ``source_text``, and copying that unrelated document as the lock would attest
    criteria that were not evaluated.
    """
    try:
        return _scenario_from_obj(_parse_json_text(text, "scenario text"), text).hash() \
            == spec.hash()
    except ScenarioError:
        return False


def acceptance_text_matches(spec: AcceptanceSpec, text: str) -> bool:
    try:
        return _acceptance_from_obj(_parse_json_text(text, "acceptance text"), text).hash() \
            == spec.hash()
    except ScenarioError:
        return False


def canonical_json(value: Any) -> str:
    """Canonical UTF-8 text for hashing and identity, never containing NaN/inf."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- scenario types
@dataclass(frozen=True)
class BudgetSpec:
    max_steps: int
    max_sim_time_s: float
    max_trace_rows: int
    max_state_rows: int | None = None
    max_state_bytes: int | None = None

    def to_dict(self) -> dict:
        out = {
            "max_steps": self.max_steps,
            "max_sim_time_s": self.max_sim_time_s,
            "max_trace_rows": self.max_trace_rows,
        }
        if self.max_state_rows is not None:
            out["max_state_rows"] = self.max_state_rows
        if self.max_state_bytes is not None:
            out["max_state_bytes"] = self.max_state_bytes
        return out


@dataclass(frozen=True)
class PhaseSpec:
    """One declared phase.

    A ``reset`` phase carries the only positions this runner may ever write; it must be first
    and unique. Every other phase is timed and its duration must resolve to at least one
    whole step at the scenario timestep.
    """

    name: str
    kind: str
    duration_s: float | None = None
    initial: tuple[tuple[str, float], ...] = ()
    actuator: str | None = None
    effort: float | None = None

    @property
    def is_reset(self) -> bool:
        return self.kind == "reset"

    def to_dict(self) -> dict:
        out: dict[str, Any] = {"name": self.name, "kind": self.kind}
        if self.initial:
            out["initial"] = {k: v for k, v in self.initial}
        if self.duration_s is not None:
            out["duration_s"] = self.duration_s
        if self.actuator is not None:
            out["actuator"] = self.actuator
        if self.effort is not None:
            out["effort"] = self.effort
        return out


@dataclass(frozen=True)
class ScenarioSpec:
    scenario_id: str
    fixture: str
    seed: int
    phases: tuple[PhaseSpec, ...]
    timestep_s: float | None
    sampling_interval_s: float
    budgets: BudgetSpec
    source_text: str = field(default="", compare=False, repr=False)

    def to_dict(self) -> dict:
        out: dict[str, Any] = {
            "schema_version": SCENARIO_SCHEMA_VERSION,
            "scenario_id": self.scenario_id,
            "fixture": self.fixture,
            "seed": self.seed,
            "sampling_interval_s": self.sampling_interval_s,
            "budgets": self.budgets.to_dict(),
            "phases": [p.to_dict() for p in self.phases],
        }
        if self.timestep_s is not None:
            out["timestep_s"] = self.timestep_s
        return out

    @property
    def reset_phase(self) -> PhaseSpec:
        return self.phases[0]

    @property
    def timed_phases(self) -> tuple[PhaseSpec, ...]:
        return tuple(p for p in self.phases if not p.is_reset)

    def hash(self) -> str:
        return content_hash(self.to_dict())


@dataclass(frozen=True)
class ValiditySpec:
    max_penetration_m: float | None = None
    max_speed_m_s: float | None = None
    max_angular_speed_rad_s: float | None = None
    max_energy_j: float | None = None

    def to_dict(self) -> dict:
        # Unset optional bounds are omitted, never emitted as null: the loader rejects a
        # null numeric field, so a canonical document must round-trip through it.
        return {key: value for key, value in {
            "max_penetration_m": self.max_penetration_m,
            "max_speed_m_s": self.max_speed_m_s,
            "max_angular_speed_rad_s": self.max_angular_speed_rad_s,
            "max_energy_j": self.max_energy_j,
        }.items() if value is not None}


@dataclass(frozen=True)
class CheckSpec:
    """One declarative predicate. Only the fields valid for ``kind`` are populated."""

    name: str
    kind: str
    joint: str | None = None
    actuator: str | None = None
    phase: str | None = None
    from_phase: str | None = None
    to_phase: str | None = None
    body: str | None = None
    body_a: str | None = None
    body_b: str | None = None
    event: str | None = None
    expected: float | None = None
    tolerance: float | None = None
    reference: float | None = None
    maximum: float | None = None
    units: str = ""

    def __post_init__(self) -> None:
        if self.kind not in CHECK_KINDS:
            raise ValueError(f"unknown check kind {self.kind!r}")
        if not self.units:
            raise ValueError(
                f"check {self.name!r} ({self.kind}) needs explicit non-empty units")

    def to_dict(self) -> dict:
        return {key: value for key, value in {
            "name": self.name, "kind": self.kind, "joint": self.joint,
            "actuator": self.actuator, "phase": self.phase,
            "from_phase": self.from_phase, "to_phase": self.to_phase,
            "body": self.body, "body_a": self.body_a, "body_b": self.body_b,
            "event": self.event,
            "expected": self.expected, "tolerance": self.tolerance,
            "reference": self.reference, "max": self.maximum, "units": self.units,
        }.items() if value is not None}


@dataclass(frozen=True)
class PlaneSpec:
    """An oriented plane in SI metres. ``direction`` selects the outward side.

    ``normal`` is stored **as authored** so the semantic hash is stable across a
    canonical-JSON lock round-trip; :attr:`unit_normal` is the normalized vector used for
    geometry. Normalizing at construction made normalization non-idempotent for tilted
    normals and could make replay reject its own lock.
    """

    point_m: tuple[float, float, float]
    normal: tuple[float, float, float]
    direction: int = 1

    def __post_init__(self) -> None:
        if len(self.point_m) != 3 or not all(math.isfinite(v) for v in self.point_m):
            raise ValueError(f"plane point_m must be 3 finite numbers, got {self.point_m!r}")
        if len(self.normal) != 3 or not all(math.isfinite(v) for v in self.normal):
            raise ValueError(f"plane normal must be 3 finite numbers, got {self.normal!r}")
        if isinstance(self.direction, bool) or self.direction not in (-1, 1):
            raise ValueError(f"plane direction must be +1 or -1, got {self.direction!r}")
        norm = math.sqrt(sum(v * v for v in self.normal))
        if not (math.isfinite(norm) and norm > 1e-12):
            raise ValueError("plane normal must be nonzero")

    @property
    def unit_normal(self) -> tuple[float, float, float]:
        norm = math.sqrt(sum(v * v for v in self.normal))
        return tuple(v / norm for v in self.normal)  # type: ignore[return-value]

    def to_dict(self) -> dict:
        return {"point_m": list(self.point_m), "normal": list(self.normal),
                "direction": int(self.direction)}


@dataclass(frozen=True)
class EventSpec:
    """One typed, named event window and its criteria.

    Lengths are SI metres; the rigid object's half-extents are in its body frame. Phase
    names bind the event to a bounded scenario window. ``target_protrusion_m`` is recorded
    for information only and is never a pass threshold.
    """

    name: str
    kind: str
    bodies: tuple[str, ...]
    plane: PlaneSpec
    object_half_extents_m: tuple[float, float, float]
    window_from: str
    window_to: str
    access_plane: PlaneSpec | None = None
    release_phase: str | None = None
    dwell_from: str | None = None
    dwell_to: str | None = None
    min_protrusion_m: float | None = None
    target_protrusion_m: float | None = None
    min_accessible_m: float | None = None
    dwell_min_s: float | None = None
    protrusion_change_max_m: float | None = None
    support_bodies: tuple[str, ...] = ()
    min_support_load_fraction: float = 0.6
    support_hull_margin_m: float = 0.001
    support_hull_min_area_m2: float = 1.0e-5
    support_degeneracy_radius_m: float = 0.002
    max_terminal_speed_m_s: float | None = None
    bounds_m: tuple[tuple[float, float], tuple[float, float],
                    tuple[float, float]] | None = None
    fallout_drop_m: float | None = None

    def __post_init__(self) -> None:
        if self.kind not in EVENT_KINDS:
            raise ValueError(f"unknown event kind {self.kind!r}")
        if not self.name:
            raise ValueError("event name must be non-empty")
        if not self.bodies or len(set(self.bodies)) != len(self.bodies) or not all(
                isinstance(b, str) and b for b in self.bodies):
            raise ValueError(f"event {self.name!r} needs unique non-empty body ids")
        if not isinstance(self.plane, PlaneSpec):
            raise ValueError(f"event {self.name!r} needs a PlaneSpec")
        if (len(self.object_half_extents_m) != 3
                or not all(math.isfinite(v) and v > 0.0
                           for v in self.object_half_extents_m)):
            raise ValueError(f"event {self.name!r} needs 3 positive half-extents")
        if not self.window_from or not self.window_to:
            raise ValueError(f"event {self.name!r} needs window_from and window_to phases")
        if self.kind == "exit_crossing":
            forbidden = {
                "access_plane": self.access_plane,
                "release_phase": self.release_phase,
                "dwell_from": self.dwell_from,
                "dwell_to": self.dwell_to,
                "min_protrusion_m": self.min_protrusion_m,
                "target_protrusion_m": self.target_protrusion_m,
                "min_accessible_m": self.min_accessible_m,
                "dwell_min_s": self.dwell_min_s,
                "protrusion_change_max_m": self.protrusion_change_max_m,
                "support_bodies": self.support_bodies or None,
                "max_terminal_speed_m_s": self.max_terminal_speed_m_s,
                "bounds_m": self.bounds_m,
                "fallout_drop_m": self.fallout_drop_m,
            }
            present = [k for k, v in forbidden.items() if v is not None]
            if present:
                raise ValueError(
                    f"exit_crossing event {self.name!r} has presentation-only field(s) "
                    f"{present}")
            if (self.min_support_load_fraction != 0.6
                    or self.support_hull_margin_m != 0.001
                    or self.support_hull_min_area_m2 != 1.0e-5
                    or self.support_degeneracy_radius_m != 0.002):
                raise ValueError(
                    f"exit_crossing event {self.name!r} cannot carry support-hull criteria")
            return
        # supported_presentation
        required = {
            "access_plane": self.access_plane,
            "release_phase": self.release_phase,
            "dwell_from": self.dwell_from,
            "dwell_to": self.dwell_to,
            "min_protrusion_m": self.min_protrusion_m,
            "min_accessible_m": self.min_accessible_m,
            "dwell_min_s": self.dwell_min_s,
            "protrusion_change_max_m": self.protrusion_change_max_m,
            "max_terminal_speed_m_s": self.max_terminal_speed_m_s,
            "bounds_m": self.bounds_m,
            "fallout_drop_m": self.fallout_drop_m,
        }
        missing = [k for k, v in required.items() if v is None]
        if missing:
            raise ValueError(
                f"supported_presentation event {self.name!r} is missing {missing}")
        if not self.support_bodies:
            raise ValueError(f"event {self.name!r} needs declared support_bodies")
        if not isinstance(self.access_plane, PlaneSpec):
            raise ValueError(f"event {self.name!r} access_plane must be a PlaneSpec")
        for key, value, positive in (
            ("min_protrusion_m", self.min_protrusion_m, True),
            ("min_accessible_m", self.min_accessible_m, False),
            ("dwell_min_s", self.dwell_min_s, True),
            ("protrusion_change_max_m", self.protrusion_change_max_m, False),
            ("support_hull_margin_m", self.support_hull_margin_m, False),
            ("support_hull_min_area_m2", self.support_hull_min_area_m2, True),
            ("support_degeneracy_radius_m", self.support_degeneracy_radius_m, False),
            ("max_terminal_speed_m_s", self.max_terminal_speed_m_s, True),
            ("fallout_drop_m", self.fallout_drop_m, True),
        ):
            if not math.isfinite(value) or (value <= 0.0 if positive else value < 0.0):
                raise ValueError(f"event {self.name!r} {key} is out of range: {value!r}")
        if (not math.isfinite(self.min_support_load_fraction)
                or not 0.0 < self.min_support_load_fraction <= 1.0):
            raise ValueError(
                f"event {self.name!r} min_support_load_fraction must be in (0, 1]")
        if self.target_protrusion_m is not None and (
                not math.isfinite(self.target_protrusion_m)
                or self.target_protrusion_m <= 0.0):
            raise ValueError(f"event {self.name!r} target_protrusion_m is out of range")
        if len(self.bounds_m) != 3:
            raise ValueError(f"event {self.name!r} bounds_m must have x, y and z")
        for low, high in self.bounds_m:
            if not (math.isfinite(low) and math.isfinite(high) and low < high):
                raise ValueError(f"event {self.name!r} bounds_m range is invalid")

    def to_dict(self) -> dict:
        out: dict[str, Any] = {
            "name": self.name, "kind": self.kind, "bodies": list(self.bodies),
            "plane": self.plane.to_dict(),
            "object_half_extents_m": list(self.object_half_extents_m),
            "window_from": self.window_from, "window_to": self.window_to,
        }
        if self.kind == "exit_crossing":
            return out
        out.update({
            "min_support_load_fraction": self.min_support_load_fraction,
            "support_hull_margin_m": self.support_hull_margin_m,
            "support_hull_min_area_m2": self.support_hull_min_area_m2,
            "support_degeneracy_radius_m": self.support_degeneracy_radius_m,
        })
        for key, value in (
            ("access_plane", self.access_plane.to_dict() if self.access_plane else None),
            ("release_phase", self.release_phase),
            ("dwell_from", self.dwell_from), ("dwell_to", self.dwell_to),
            ("min_protrusion_m", self.min_protrusion_m),
            ("target_protrusion_m", self.target_protrusion_m),
            ("min_accessible_m", self.min_accessible_m),
            ("dwell_min_s", self.dwell_min_s),
            ("protrusion_change_max_m", self.protrusion_change_max_m),
            ("support_bodies", list(self.support_bodies) if self.support_bodies else None),
            ("max_terminal_speed_m_s", self.max_terminal_speed_m_s),
            ("bounds_m", ({"x": list(self.bounds_m[0]),
                           "y": list(self.bounds_m[1]),
                           "z": list(self.bounds_m[2])}
                          if self.bounds_m is not None else None)),
            ("fallout_drop_m", self.fallout_drop_m),
        ):
            if value is not None:
                out[key] = value
        return out


@dataclass(frozen=True)
class AcceptanceSpec:
    acceptance_id: str
    checks: tuple[CheckSpec, ...]
    validity: ValiditySpec
    source_text: str = field(default="", compare=False, repr=False)
    notes: str = ""
    events: tuple[EventSpec, ...] = ()

    def to_dict(self) -> dict:
        out = {
            "schema_version": ACCEPTANCE_SCHEMA_VERSION,
            "acceptance_id": self.acceptance_id,
            "checks": [c.to_dict() for c in self.checks],
            "validity": self.validity.to_dict(),
        }
        if self.notes:
            out["notes"] = self.notes
        if self.events:
            out["events"] = [e.to_dict() for e in self.events]
        return out

    def hash(self) -> str:
        return content_hash(self.to_dict())


# --------------------------------------------------------------------------- loaders
def load_scenario(path: str | Path) -> ScenarioSpec:
    obj, raw_text = _read_json(Path(path), "scenario")
    return _scenario_from_obj(obj, raw_text)


def _scenario_from_obj(obj: dict, raw_text: str) -> ScenarioSpec:
    where = "scenario"
    _check_keys(obj, where,
                required=("schema_version", "scenario_id", "fixture", "phases"),
                optional=("seed", "timestep_s", "sampling_interval_s", "budgets"))
    version = _string(obj, "schema_version", where)
    if version != SCENARIO_SCHEMA_VERSION:
        raise ScenarioError(
            f"unsupported scenario schema_version {version!r}; this build accepts "
            f"{SCENARIO_SCHEMA_VERSION!r}")
    scenario_id = _safe_id(_string(obj, "scenario_id", where), "scenario_id")
    # A typed ``run_assembly`` caller may use a non-registry label; the registry allowlist
    # is enforced when a JSON scenario is executed through ``run_scenario``/``build_fixture``.
    fixture = _safe_id(_string(obj, "fixture", where), "fixture")
    seed = _integer(obj, "seed", where) if "seed" in obj else 0
    if not 0 <= seed <= 2**31 - 1:
        raise ScenarioError(f"scenario.seed must be in [0, 2**31-1], got {seed}")
    timestep = _number(obj, "timestep_s", where, positive=True) if "timestep_s" in obj else None
    if timestep is not None and timestep > 1.0e-2:
        raise ScenarioError(f"scenario.timestep_s must be <= 0.01, got {timestep}")
    interval = (_number(obj, "sampling_interval_s", where, positive=True)
                if "sampling_interval_s" in obj else 0.002)
    budgets_obj = obj.get("budgets")
    if not isinstance(budgets_obj, dict):
        raise ScenarioError("scenario.budgets must be an object")
    _check_keys(budgets_obj, "scenario.budgets",
                required=("max_steps", "max_sim_time_s", "max_trace_rows"),
                optional=("max_state_rows", "max_state_bytes"))
    budgets = BudgetSpec(
        max_steps=_integer(budgets_obj, "max_steps", "scenario.budgets", positive=True),
        max_sim_time_s=_number(budgets_obj, "max_sim_time_s", "scenario.budgets",
                               positive=True),
        max_trace_rows=_integer(budgets_obj, "max_trace_rows", "scenario.budgets",
                                positive=True),
        max_state_rows=(_integer(budgets_obj, "max_state_rows", "scenario.budgets",
                                 positive=True)
                        if "max_state_rows" in budgets_obj else None),
        max_state_bytes=(_integer(budgets_obj, "max_state_bytes", "scenario.budgets",
                                  positive=True)
                         if "max_state_bytes" in budgets_obj else None),
    )
    phases_raw = obj["phases"]
    if not isinstance(phases_raw, list) or not phases_raw:
        raise ScenarioError("scenario.phases must be a non-empty list")
    phases = tuple(_load_phase(item, i) for i, item in enumerate(phases_raw))
    names = [p.name for p in phases]
    if len(set(names)) != len(names):
        raise ScenarioError(f"scenario phase names must be unique, got {names}")
    reserved = {"initial", "post_settle", "terminal"}
    clash = sorted(reserved & set(names))
    if clash:
        raise ScenarioError(
            f"scenario phase name(s) {clash} are reserved for recorded state boundaries")
    resets = [i for i, p in enumerate(phases) if p.is_reset]
    if resets != [0]:
        raise ScenarioError(
            "scenario.phases must contain exactly one reset phase and it must be first; "
            f"found reset indices {resets}")
    if len(phases) < 2:
        raise ScenarioError("scenario.phases needs a reset phase and at least one timed phase")
    return ScenarioSpec(scenario_id, fixture, seed, phases, timestep, interval, budgets,
                        raw_text)


def _load_phase(item, index: int) -> PhaseSpec:
    where = f"scenario.phases[{index}]"
    if not isinstance(item, dict):
        raise ScenarioError(f"{where} must be an object")
    kind_required = ("name", "kind")
    _check_keys(item, where, required=kind_required,
                optional=("duration_s", "initial", "actuator", "effort"))
    name = _safe_id(_string(item, "name", where), f"{where}.name")
    kind = _string(item, "kind", where, choices=PHASE_KINDS)
    initial: dict[str, float] = {}
    if "initial" in item:
        raw = item["initial"]
        if not isinstance(raw, dict):
            raise ScenarioError(f"{where}.initial must be an object")
        for key, value in raw.items():
            joint = _safe_id(key, f"{where}.initial key")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ScenarioError(f"{where}.initial[{key!r}] must be a number")
            try:
                value = float(value)
            except (OverflowError, ValueError, TypeError) as exc:
                raise ScenarioError(
                    f"{where}.initial[{key!r}] is not a representable number") from exc
            if not math.isfinite(value):
                raise ScenarioError(f"{where}.initial[{key!r}] must be finite")
            initial[joint] = value
    if kind == "reset":
        if "duration_s" in item or "actuator" in item or "effort" in item:
            raise ScenarioError(f"{where}: a reset phase has no duration, actuator or effort")
        return PhaseSpec(name=name, kind=kind, initial=tuple(sorted(initial.items())))
    if "initial" in item:
        raise ScenarioError(f"{where}: only a reset phase may declare initial coordinates")
    if "duration_s" not in item:
        raise ScenarioError(f"{where}: timed phase {kind!r} needs duration_s")
    duration = _number(item, "duration_s", where, positive=True)
    actuator = effort = None
    if kind == "actuate":
        if "actuator" not in item or "effort" not in item:
            raise ScenarioError(f"{where}: an actuate phase needs actuator and effort")
        actuator = _safe_id(_string(item, "actuator", where), f"{where}.actuator")
        effort = _number(item, "effort", where)
    elif "actuator" in item or "effort" in item:
        raise ScenarioError(f"{where}: {kind!r} phases must not declare actuator or effort")
    return PhaseSpec(name=name, kind=kind, duration_s=duration, initial=(),
                     actuator=actuator, effort=effort)


def load_acceptance(path: str | Path) -> AcceptanceSpec:
    obj, raw_text = _read_json(Path(path), "acceptance")
    return _acceptance_from_obj(obj, raw_text)


def acceptance_from_toml_text(text: str) -> AcceptanceSpec:
    """Parse a strict TOML acceptance document with the same typed schema as JSON.

    TOML is a convenience for frozen project criteria; the evaluated document is still the
    typed :class:`AcceptanceSpec`, and a run lock is written as canonical JSON. ``tomllib``
    rejects duplicate keys. Non-finite TOML floats are rejected by the numeric validators.
    """
    import tomllib

    try:
        obj = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ScenarioError(f"acceptance TOML is not valid: {exc}") from exc
    except RecursionError as exc:
        raise ScenarioError("acceptance TOML is nested too deeply to parse") from exc
    if not isinstance(obj, dict):
        raise ScenarioError("acceptance TOML must contain a table")
    return _acceptance_from_obj(obj, text)


def load_acceptance_toml(path: str | Path) -> AcceptanceSpec:
    text = _read_bounded_text(Path(path), "acceptance")
    return acceptance_from_toml_text(text)


def _acceptance_from_obj(obj: dict, raw_text: str) -> AcceptanceSpec:
    where = "acceptance"
    _check_keys(obj, where, required=("schema_version", "acceptance_id", "checks"),
                optional=("validity", "notes", "events"))
    version = _string(obj, "schema_version", where)
    if version != ACCEPTANCE_SCHEMA_VERSION:
        raise ScenarioError(
            f"unsupported acceptance schema_version {version!r}; this build accepts "
            f"{ACCEPTANCE_SCHEMA_VERSION!r}")
    acceptance_id = _safe_id(_string(obj, "acceptance_id", where), "acceptance_id")
    notes = obj.get("notes", "")
    if not isinstance(notes, str):
        raise ScenarioError("acceptance.notes must be a string")
    raw_checks = obj["checks"]
    if not isinstance(raw_checks, list) or not raw_checks:
        raise ScenarioError("acceptance.checks must be a non-empty list")
    checks = tuple(_load_check(item, i) for i, item in enumerate(raw_checks))
    names = [c.name for c in checks]
    if len(set(names)) != len(names):
        raise ScenarioError(f"acceptance check names must be unique, got {names}")
    raw_events = obj.get("events", [])
    if not isinstance(raw_events, list):
        raise ScenarioError("acceptance.events must be a list")
    events = tuple(_load_event(item, i) for i, item in enumerate(raw_events))
    event_names = [e.name for e in events]
    if len(set(event_names)) != len(event_names):
        raise ScenarioError(f"acceptance event names must be unique, got {event_names}")
    validity_obj = obj.get("validity", {})
    if not isinstance(validity_obj, dict):
        raise ScenarioError("acceptance.validity must be an object")
    _check_keys(validity_obj, "acceptance.validity",
                optional=("max_penetration_m", "max_speed_m_s",
                          "max_angular_speed_rad_s", "max_energy_j"))
    validity = ValiditySpec(
        max_penetration_m=(_number(validity_obj, "max_penetration_m",
                                   "acceptance.validity", nonnegative=True)
                           if "max_penetration_m" in validity_obj else None),
        max_speed_m_s=(_number(validity_obj, "max_speed_m_s", "acceptance.validity",
                               nonnegative=True)
                       if "max_speed_m_s" in validity_obj else None),
        max_angular_speed_rad_s=(
            _number(validity_obj, "max_angular_speed_rad_s", "acceptance.validity",
                    nonnegative=True)
            if "max_angular_speed_rad_s" in validity_obj else None),
        max_energy_j=(_number(validity_obj, "max_energy_j", "acceptance.validity",
                              nonnegative=True)
                      if "max_energy_j" in validity_obj else None),
    )
    return AcceptanceSpec(acceptance_id, checks, validity, raw_text,
                          notes=notes, events=events)


def _numbers(obj: dict, key: str, where: str, length: int, *,
             positive: bool = False, nonnegative: bool = False) -> tuple[float, ...]:
    value = obj[key]
    if not isinstance(value, list) or len(value) != length:
        raise ScenarioError(f"{where}.{key} must be a list of {length} numbers")
    out = []
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ScenarioError(f"{where}.{key}[{index}] must be a number")
        try:
            number = float(item)
        except (OverflowError, ValueError, TypeError) as exc:
            raise ScenarioError(f"{where}.{key}[{index}] is not representable") from exc
        if not math.isfinite(number):
            raise ScenarioError(f"{where}.{key}[{index}] must be finite")
        if positive and number <= 0.0:
            raise ScenarioError(f"{where}.{key}[{index}] must be positive")
        if nonnegative and number < 0.0:
            raise ScenarioError(f"{where}.{key}[{index}] must be non-negative")
        out.append(number)
    return tuple(out)


def _load_plane(item, where: str) -> PlaneSpec:
    if not isinstance(item, dict):
        raise ScenarioError(f"{where} must be an object")
    _check_keys(item, where, required=("point_m", "normal"), optional=("direction",))
    direction = _integer(item, "direction", where) if "direction" in item else 1
    try:
        return PlaneSpec(_numbers(item, "point_m", where, 3),
                         _numbers(item, "normal", where, 3), direction)
    except ValueError as exc:
        raise ScenarioError(f"{where}: {exc}") from exc


_EVENT_FIELDS = ("name", "kind", "bodies", "plane", "object_half_extents_m",
                 "window_from", "window_to")
_EVENT_OPTIONAL = ("access_plane", "release_phase", "dwell_from", "dwell_to",
                   "min_protrusion_m", "target_protrusion_m", "min_accessible_m",
                   "dwell_min_s", "protrusion_change_max_m", "support_bodies",
                   "min_support_load_fraction", "support_hull_margin_m",
                   "support_hull_min_area_m2", "support_degeneracy_radius_m",
                   "max_terminal_speed_m_s", "bounds_m", "fallout_drop_m")


def _load_event(item, index: int) -> EventSpec:
    where = f"acceptance.events[{index}]"
    if not isinstance(item, dict):
        raise ScenarioError(f"{where} must be an object")
    _check_keys(item, where, required=_EVENT_FIELDS, optional=_EVENT_OPTIONAL)
    name = _safe_id(_string(item, "name", where), f"{where}.name")
    kind = _string(item, "kind", where, choices=EVENT_KINDS)
    raw_bodies = item["bodies"]
    if not isinstance(raw_bodies, list) or not raw_bodies:
        raise ScenarioError(f"{where}.bodies must be a non-empty list")
    bodies = tuple(_safe_id(_string({"body": b}, "body", where),
                            f"{where}.bodies") for b in raw_bodies)
    support_bodies: tuple[str, ...] = ()
    if "support_bodies" in item:
        raw_support = item["support_bodies"]
        if not isinstance(raw_support, list) or not raw_support:
            raise ScenarioError(f"{where}.support_bodies must be a non-empty list")
        support_bodies = tuple(_safe_id(_string({"body": b}, "body", where),
                                        f"{where}.support_bodies")
                               for b in raw_support)
    bounds = None
    if "bounds_m" in item:
        raw_bounds = item["bounds_m"]
        if not isinstance(raw_bounds, dict):
            raise ScenarioError(f"{where}.bounds_m must be an object")
        _check_keys(raw_bounds, f"{where}.bounds_m", required=("x", "y", "z"))
        bounds = tuple(_numbers(raw_bounds, axis, f"{where}.bounds_m", 2)
                       for axis in ("x", "y", "z"))
    kwargs: dict[str, Any] = {
        "name": name, "kind": kind, "bodies": bodies,
        "plane": _load_plane(item["plane"], f"{where}.plane"),
        "object_half_extents_m": _numbers(item, "object_half_extents_m", where, 3,
                                          positive=True),
        "window_from": _safe_id(_string(item, "window_from", where),
                                f"{where}.window_from"),
        "window_to": _safe_id(_string(item, "window_to", where), f"{where}.window_to"),
        "support_bodies": support_bodies,
    }
    if "access_plane" in item:
        kwargs["access_plane"] = _load_plane(item["access_plane"], f"{where}.access_plane")
    for key in ("release_phase", "dwell_from", "dwell_to"):
        if key in item:
            kwargs[key] = _safe_id(_string(item, key, where), f"{where}.{key}")
    for key, positive, nonnegative in (
        ("min_protrusion_m", True, False),
        ("target_protrusion_m", True, False),
        ("min_accessible_m", False, True),
        ("dwell_min_s", True, False),
        ("protrusion_change_max_m", False, True),
        ("min_support_load_fraction", True, False),
        ("support_hull_margin_m", False, True),
        ("support_hull_min_area_m2", True, False),
        ("support_degeneracy_radius_m", False, True),
        ("max_terminal_speed_m_s", True, False),
        ("fallout_drop_m", True, False),
    ):
        if key in item:
            kwargs[key] = _number(item, key, where, positive=positive,
                                  nonnegative=nonnegative)
    if "min_accessible_m" not in kwargs and kind == "supported_presentation":
        raise ScenarioError(f"{where}: supported_presentation needs min_accessible_m")
    if bounds is not None:
        kwargs["bounds_m"] = bounds
    try:
        return EventSpec(**kwargs)
    except ValueError as exc:
        raise ScenarioError(f"{where}: {exc}") from exc


_CHECK_FIELDS = {
    "joint_displacement": (("joint", "to_phase", "expected", "tolerance", "units"),
                           ("from_phase",)),
    "return_displacement": (("joint", "phase", "reference", "max", "units"), ()),
    "terminal_speed": (("joint", "phase", "max", "units"), ()),
    "body_speed": (("body", "phase", "max", "units"), ()),
    "effort_bound": (("actuator", "max", "units"), ()),
    "contact_force_bound": (("body_a", "body_b", "max", "units"), ()),
    "penetration_bound": (("max", "units"), ()),
    "event_count": (("event", "expected", "tolerance", "units"), ()),
    "event_verdict": (("event", "units"), ()),
}


def _load_check(item, index: int) -> CheckSpec:
    where = f"acceptance.checks[{index}]"
    if not isinstance(item, dict):
        raise ScenarioError(f"{where} must be an object")
    if "kind" not in item:
        raise ScenarioError(f"{where} is missing kind")
    kind = _string(item, "kind", where, choices=CHECK_KINDS)
    required, optional = _CHECK_FIELDS[kind]
    _check_keys(item, where, required=("name", "kind", *required),
                optional=(*optional, "kind", "name"))
    name = _safe_id(_string(item, "name", where), f"{where}.name")
    kwargs: dict[str, Any] = {"name": name, "kind": kind}

    def text(key):
        return _safe_id(_string(item, key, where), f"{where}.{key}")

    if kind == "joint_displacement":
        kwargs.update(
            joint=text("joint"), to_phase=text("to_phase"),
            from_phase=text("from_phase") if "from_phase" in item else None,
            expected=_number(item, "expected", where),
            tolerance=_number(item, "tolerance", where, nonnegative=True),
            units=_string(item, "units", where, choices=("m", "rad")),
        )
    elif kind == "return_displacement":
        kwargs.update(
            joint=text("joint"), phase=text("phase"),
            reference=_number(item, "reference", where),
            maximum=_number(item, "max", where, nonnegative=True),
            units=_string(item, "units", where, choices=("m", "rad")),
        )
    elif kind == "terminal_speed":
        kwargs.update(
            joint=text("joint"), phase=text("phase"),
            maximum=_number(item, "max", where, nonnegative=True),
            units=_string(item, "units", where, choices=("m/s", "rad/s")),
        )
    elif kind == "body_speed":
        kwargs.update(
            body=text("body"), phase=text("phase"),
            maximum=_number(item, "max", where, nonnegative=True),
            units=_string(item, "units", where, choices=("m/s",)),
        )
    elif kind == "effort_bound":
        units = _string(item, "units", where)
        if units not in ("N", "N m", "Nm", "N.m"):
            raise ScenarioError(f"{where}.units must be N or N m, got {units!r}")
        kwargs.update(
            actuator=text("actuator"),
            maximum=_number(item, "max", where, positive=True),
            units=units,
        )
    elif kind == "contact_force_bound":
        kwargs.update(
            body_a=text("body_a"), body_b=text("body_b"),
            maximum=_number(item, "max", where, positive=True),
            units=_string(item, "units", where, choices=("N",)),
        )
    elif kind == "event_count":
        units = _string(item, "units", where)
        if units != "count":
            raise ScenarioError(f"{where}.units must be 'count', got {units!r}")
        kwargs.update(
            event=text("event"),
            expected=_integer(item, "expected", where),
            tolerance=_integer(item, "tolerance", where),
            units=units,
        )
        if kwargs["expected"] < 0 or kwargs["tolerance"] < 0:
            raise ScenarioError(f"{where}: expected and tolerance must be non-negative")
    elif kind == "event_verdict":
        units = _string(item, "units", where)
        if units != "state":
            raise ScenarioError(f"{where}.units must be 'state', got {units!r}")
        kwargs.update(event=text("event"), units=units)
    else:  # penetration_bound
        kwargs.update(
            maximum=_number(item, "max", where, positive=True),
            units=_string(item, "units", where, choices=("m",)),
        )
    return CheckSpec(**kwargs)


# --------------------------------------------------------------------------- fixtures
def _loaded_slider(timestep_s: float):
    from dataclasses import replace

    from .mechanics import slider_damped_spec

    return replace(slider_damped_spec(timestep_s=timestep_s), name="m4a_loaded_slider")


def _loaded_slider_negative_gear(timestep_s: float):
    from dataclasses import replace

    from .mechanics import slider_damped_spec

    spec = slider_damped_spec(timestep_s=timestep_s)
    actuator = replace(spec.actuators[0], gear=-2.0)
    return replace(spec, name="m4a_loaded_slider_negative_gear",
                   actuators=(actuator,))


def _loaded_slider_no_spring(timestep_s: float):
    from dataclasses import replace

    from .mechanics import slider_analytic_stiffness_damping, slider_frictionless_spec

    spec = slider_frictionless_spec(
        timestep_s=timestep_s, damping=slider_analytic_stiffness_damping(),
        with_spring=False)
    return replace(spec, name="m4a_loaded_slider_no_spring")


def _drop_box(timestep_s: float):
    from build123d import Box, Pos

    from .schema import AssemblySpec, BodySpec, ColliderSpec, Frame, PartSpec, Source
    from .units import mass_kg

    edge_mm = 20.0
    density = 1.27
    floor = BodySpec(
        body_id="floor",
        parts=(PartSpec(
            part_id="floor",
            shape=Pos(0.0, 0.0, -5.0) * Box(120.0, 120.0, 10.0),
            colliders=(ColliderSpec("floor_col", "box", (60.0, 60.0, 5.0),
                                    pos_mm=(0.0, 0.0, -5.0),
                                    source=Source("derived", "fixed analytic floor")),),
            role="structure",
            density_g_cm3=1.24,
            source=Source("derived", "M4a drop fixture floor"),
        ),),
        fixed_to_world=True,
        fixture="analytic_fixture",
        source=Source("derived", "fixed floor, intentionally analytic"),
    )
    box = BodySpec(
        body_id="box",
        parts=(PartSpec(
            part_id="box",
            shape=Pos(0.0, 0.0, 50.0) * Box(edge_mm, edge_mm, edge_mm),
            colliders=(ColliderSpec("box_col", "box",
                                    (edge_mm / 2, edge_mm / 2, edge_mm / 2),
                                    pos_mm=(0.0, 0.0, 50.0),
                                    source=Source("derived", "box half-extents")),),
            mass_kg=mass_kg(edge_mm ** 3, density),
            role="packet",
            source=Source("assumed", "20 mm cube at 1.27 g/cm3, analytic fixture"),
        ),),
        frame=Frame(),
        source=Source("derived", "free box released from 40 mm above the floor"),
    )
    return AssemblySpec(
        name="m4a_drop_box",
        bodies=(floor, box),
        gravity_m_s2=(0.0, 0.0, -9.80665),
        timestep_s=timestep_s,
        contact_timeconst_s=2.0e-3,
        source=Source("derived", "generic contact-telemetry fixture"),
    )


def _presentation_aperture(timestep_s: float):
    from .presentation_aperture import presentation_aperture_spec

    return presentation_aperture_spec(timestep_s=timestep_s)


def _presentation_aperture_blocked(timestep_s: float):
    from .presentation_aperture import blocked_presentation_aperture_spec

    return blocked_presentation_aperture_spec(timestep_s=timestep_s)


def _presentation_aperture_double(timestep_s: float):
    from .presentation_aperture import double_presentation_aperture_spec

    return double_presentation_aperture_spec(timestep_s=timestep_s)


_FIXTURES = {
    "loaded_slider": _loaded_slider,
    "loaded_slider_no_spring": _loaded_slider_no_spring,
    "loaded_slider_negative_gear": _loaded_slider_negative_gear,
    "drop_box": _drop_box,
    "presentation_aperture": _presentation_aperture,
    "presentation_aperture_blocked": _presentation_aperture_blocked,
    "presentation_aperture_double": _presentation_aperture_double,
}


def build_fixture(fixture_id: str, timestep_s: float | None = None):
    """Build a registered generic assembly. No scenario-supplied code or paths."""
    if fixture_id not in _FIXTURES:
        raise ScenarioError(f"unknown fixture {fixture_id!r}; registered: {sorted(_FIXTURES)}")
    if timestep_s is None:
        timestep_s = 1.0e-3
    spec = _FIXTURES[fixture_id](float(timestep_s))
    spec.validate()
    return spec
