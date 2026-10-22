"""Generic per-step named events: exit crossings and supported presentations.

The tracker is deliberately independent of MuJoCo and of any product project. The runner
feeds it one coherent post-state sample per integration step; it never reads a sparse trace
and never writes simulation state. All geometry is declared in SI metres, and the rigid body
extent is the declared half-extent of the object in its own body frame.

Semantics that matter for evidence:

* a crossing is the **leading point** of the rigid box passing the plane in the configured
  direction, not the centre merely touching it;
* a body already outside (or partly outside) when the cycle starts cannot produce a crossing
  in that cycle;
* one body can produce at most one crossing record per cycle; re-crossings are diagnostics;
* a presentation requires actual contact support whose gravity-normal load carries a declared
  fraction of the body's weight, with the projected COM inside the contact support hull (or
  within a declared degeneracy radius for line/point support), followed by a continuous
  post-release dwell with bounded protrusion change;
* empty or truncated observation is INCONCLUSIVE, never PASS; numerical invalidity is handled
  by the caller's validity gate and dominates any physical event verdict.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping

from .scenario import EventSpec, PlaneSpec

Vec3 = tuple[float, float, float]
Quat = tuple[float, float, float, float]

#: Plane and velocity tolerances. 1 um is three orders of magnitude above float noise at
#: metre scale and far below the smallest declared feature (0.8 mm). 1 mm/s is a quiescent
#: velocity: at a 1 ms step it is 1 um/step, while commanded motion is tens of mm/s.
DEFAULT_PLANE_EPS_M = 1.0e-6
DEFAULT_VELOCITY_EPS_M_S = 1.0e-3
#: Diagnostics are evidence, not a trace. One per (body, code) is enough; repeated
#: occurrences are counted.
MAX_DIAGNOSTIC_KEYS = 64


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a: Vec3, s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


def _norm(a: Vec3) -> float:
    return math.sqrt(_dot(a, a))


def _normalize(a: Vec3) -> Vec3 | None:
    n = _norm(a)
    if not (math.isfinite(n) and n > 1e-15):
        return None
    return _mul(a, 1.0 / n)


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _quat_matrix(q: Quat) -> tuple[Vec3, Vec3, Vec3]:
    """Rotation matrix columns (body axes in world) from a w,x,y,z quaternion."""
    w, x, y, z = q
    n = math.sqrt(w * w + x * x + y * y + z * z)
    if not (math.isfinite(n) and n > 1e-15):
        return (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
    w, x, y, z = w / n, x / n, y / n, z / n
    return (
        (1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y + w * z), 2.0 * (x * z - w * y)),
        (2.0 * (x * y - w * z), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z + w * x)),
        (2.0 * (x * z + w * y), 2.0 * (y * z - w * x), 1.0 - 2.0 * (x * x + y * y)),
    )


def _extent_along(normal: Vec3, quat: Quat, half_m: Vec3) -> float:
    cols = _quat_matrix(quat)
    return sum(abs(_dot(normal, cols[j])) * half_m[j] for j in range(3))


@dataclass(frozen=True)
class ObservedBody:
    """One body's post-state sample, in SI metres and seconds."""

    body_id: str
    pos_m: Vec3
    quat_wxyz: Quat
    com_m: Vec3
    linear_velocity_m_s: Vec3
    mass_kg: float


@dataclass(frozen=True)
class ObservedContact:
    """One contact at the observed state. ``normal_world`` is a unit vector."""

    body_a: str
    body_b: str
    position_m: Vec3
    normal_force_n: float
    normal_world: Vec3


@dataclass(frozen=True)
class StepObservation:
    time_s: float
    step_index: int
    phase_name: str
    phase_kind: str
    ctrl_zero: bool
    bodies: Mapping[str, ObservedBody]
    contacts: tuple[ObservedContact, ...]
    ctrl_max_abs: float = 0.0


@dataclass(frozen=True)
class SupportMetrics:
    load_n: float
    fraction: float
    hull_state: str
    point_count: int
    margin_m: float | None
    uncertain: bool
    ok: bool


@dataclass
class _CrossingState:
    seen: bool = False
    prev_far_m: float | None = None
    prev_time_s: float | None = None
    suppressed: bool = False
    suppress_code: str | None = None
    crossed: bool = False
    crossing_time_s: float | None = None
    crossing_signed_m: float | None = None
    crossing_protrusion_m: float | None = None
    repeated_crossings: int = 0
    wrong_direction_count: int = 0
    touch_only: bool = False
    max_far_m: float = -math.inf
    last_far_m: float | None = None
    last_protrusion_m: float | None = None


@dataclass
class _PresentationState:
    support_seen: bool = False
    support_lost: bool = False
    support_uncertain: bool = False
    max_up_m: float | None = None
    out_of_bounds: bool = False
    last_support_fraction: float = 0.0
    last_support_load_n: float = 0.0
    last_hull_state: str = "none"
    last_protrusion_m: float | None = None
    last_accessible_m: float | None = None
    dwell_active: bool = False
    dwell_start_s: float | None = None
    dwell_start_protrusion_m: float | None = None
    dwell_min_protrusion_m: float | None = None
    dwell_max_protrusion_m: float | None = None
    dwell_min_support_fraction: float | None = None
    dwell_interruptions: int = 0
    success: bool = False
    success_time_s: float | None = None
    success_protrusion_m: float | None = None
    success_revoked: bool = False
    dwell_sustained_end_s: float | None = None
    dwell_uncertain: bool = False


@dataclass
class _EventRuntime:
    spec: EventSpec
    active: bool = False
    start_time_s: float | None = None
    release_time_s: float | None = None
    release_seen: bool = False
    release_zero_ok: bool = True
    zero_input_required: bool = False
    zero_input_ok: bool = True
    zero_checked_samples: int = 0
    zero_violation: dict | None = None
    zero_violation_count: int = 0
    dwell_open: bool = False
    dwell_closed: bool = False
    window_closed: bool = False
    window_complete: bool = False
    phase_incomplete: bool = False
    observations: int = 0
    missing_body: bool = False
    duplicated_observation: int = 0
    late_candidate: bool = False
    fatal_codes: set[str] = field(default_factory=set)
    failure_codes: set[str] = field(default_factory=set)
    diagnostic_counts: dict[tuple[str, str], int] = field(default_factory=dict)
    diagnostics: list[dict] = field(default_factory=list)
    crossing: dict[str, _CrossingState] = field(default_factory=dict)
    presentation: dict[str, _PresentationState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for body_id in self.spec.bodies:
            self.crossing[body_id] = _CrossingState()
            if self.spec.kind == "supported_presentation":
                self.presentation[body_id] = _PresentationState()


@dataclass(frozen=True)
class EventResult:
    name: str
    kind: str
    status: str
    ok: bool | None
    verdict_code: str
    detail: str
    distinct_bodies_crossed: int
    evidence_complete: bool
    crossings: tuple[dict, ...]
    bodies: dict[str, dict]
    dwell: dict | None
    diagnostics: tuple[dict, ...]
    release_time_s: float | None = None
    release_zero_ok: bool | None = None
    release_zero_checked_samples: int = 0
    release_zero_violation: dict | None = None
    invalid_reasons: tuple[dict, ...] = ()

    def to_dict(self) -> dict:
        return {
            "name": self.name, "kind": self.kind, "status": self.status,
            "ok": self.ok, "verdict_code": self.verdict_code, "detail": self.detail,
            "distinct_bodies_crossed": self.distinct_bodies_crossed,
            "evidence_complete": self.evidence_complete,
            "crossings": [dict(c) for c in self.crossings],
            "bodies": {k: dict(v) for k, v in self.bodies.items()},
            "dwell": dict(self.dwell) if self.dwell is not None else None,
            "diagnostics": [dict(d) for d in self.diagnostics],
            "release_time_s": self.release_time_s,
            "release_zero_ok": self.release_zero_ok,
            "release_zero_checked_samples": self.release_zero_checked_samples,
            "release_zero_violation": (dict(self.release_zero_violation)
                                       if self.release_zero_violation is not None
                                       else None),
            "invalid_reasons": [dict(r) for r in self.invalid_reasons],
        }


def _plane_signed(plane: PlaneSpec, point_m: Vec3) -> float:
    return plane.direction * _dot(plane.unit_normal, _sub(point_m, plane.point_m))


def _point_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Monotone-chain convex hull, CCW, with near-duplicate removal."""
    pts = sorted(set((round(x, 12), round(y, 12)) for x, y in points))
    if len(pts) <= 1:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0.0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0.0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _polygon_area(hull: list[tuple[float, float]]) -> float:
    if len(hull) < 3:
        return 0.0
    area = 0.0
    for i, a in enumerate(hull):
        b = hull[(i + 1) % len(hull)]
        area += a[0] * b[1] - b[0] * a[1]
    return 0.5 * abs(area)


def _hull_margin(hull: list[tuple[float, float]], point: tuple[float, float]) -> float:
    """Signed distance to the nearest CCW hull edge; positive inside."""
    best = math.inf
    for i, a in enumerate(hull):
        b = hull[(i + 1) % len(hull)]
        ex, ey = b[0] - a[0], b[1] - a[1]
        length = math.hypot(ex, ey)
        if length <= 0.0:
            continue
        cross = ex * (point[1] - a[1]) - ey * (point[0] - a[0])
        best = min(best, cross / length)
    return best


def _line_metrics(points: list[tuple[float, float]],
                  point: tuple[float, float]) -> tuple[float, float, float, float]:
    """Perpendicular distance and projection interval for a degenerate support set."""
    if len(points) == 1:
        return math.hypot(point[0] - points[0][0], point[1] - points[0][1]), 0.0, 0.0, 0.0
    p0 = points[0]
    far = max(points, key=lambda p: (p[0] - p0[0]) ** 2 + (p[1] - p0[1]) ** 2)
    dx, dy = far[0] - p0[0], far[1] - p0[1]
    length = math.hypot(dx, dy)
    if length <= 1e-12:
        return _line_metrics([p0], point)
    ux, uy = dx / length, dy / length
    rel = (point[0] - p0[0], point[1] - p0[1])
    along = rel[0] * ux + rel[1] * uy
    perpendicular = abs(-rel[0] * uy + rel[1] * ux)
    projections = [((p[0] - p0[0]) * ux + (p[1] - p0[1]) * uy) for p in points]
    return perpendicular, along, min(projections), max(projections)


def _hull_state(points: list[tuple[float, float]], point: tuple[float, float],
                spec: EventSpec) -> tuple[str, float | None]:
    """Classify the projected COM against the actual contact support set.

    Returns one of ``inside``, ``line``, ``marginal``, ``outside`` or ``none``.
    A degenerate line support hull is accepted only within the declared degeneracy radius;
    a lone contact point is ``marginal`` (INCONCLUSIVE), and a nearly marginal 2-D hull is
    ``marginal`` rather than a silent PASS.
    """
    if not points:
        return "none", None
    hull = _point_hull(points)
    area = _polygon_area(hull)
    if len(hull) >= 3 and area >= spec.support_hull_min_area_m2:
        margin = _hull_margin(hull, point)
        if margin >= spec.support_hull_margin_m:
            return "inside", margin
        if margin >= 0.0:
            return "marginal", margin
        if -margin <= spec.support_hull_margin_m:
            return "marginal", margin
        return "outside", margin
    # Collinear or coincident contacts: a flat packet on a narrow shelf is a legitimate
    # line support. Accept it only within the declared radius of the line and segment.
    radius = spec.support_degeneracy_radius_m
    distance, along, low, high = _line_metrics(points, point)
    if len(hull) <= 1:
        # Coincident contacts are still a lone point; they cannot establish a hull.
        return "marginal", distance
    if distance <= radius and low - radius <= along <= high + radius:
        return "line", distance
    if distance <= 2.0 * radius and low - 2.0 * radius <= along <= high + 2.0 * radius:
        return "marginal", distance
    return "outside", distance


class EventTracker:
    """Feed one :class:`StepObservation` per integration step; read results after finish."""

    def __init__(self, events: tuple[EventSpec, ...], *, gravity_m_s2: Vec3,
                 plane_eps_m: float = DEFAULT_PLANE_EPS_M,
                 velocity_eps_m_s: float = DEFAULT_VELOCITY_EPS_M_S):
        if not math.isfinite(plane_eps_m) or plane_eps_m <= 0.0:
            raise ValueError("plane_eps_m must be positive and finite")
        if not math.isfinite(velocity_eps_m_s) or velocity_eps_m_s < 0.0:
            raise ValueError("velocity_eps_m_s must be non-negative and finite")
        self.events = tuple(events)
        self.names = [e.name for e in self.events]
        if len(set(self.names)) != len(self.names):
            raise ValueError("event names must be unique")
        self.gravity = tuple(float(v) for v in gravity_m_s2)
        self.gravity_magnitude = _norm(self.gravity)
        self.up = (_normalize(_mul(self.gravity, -1.0))
                   if self.gravity_magnitude > 0.0 else None)
        self.plane_eps_m = float(plane_eps_m)
        self.velocity_eps_m_s = float(velocity_eps_m_s)
        self._runtimes = {e.name: _EventRuntime(e) for e in self.events}
        self._results: dict[str, EventResult] | None = None
        self._basis: tuple[Vec3, Vec3] | None = None
        if self.up is not None:
            self._basis = self._make_basis(self.up)

    @staticmethod
    def _make_basis(up: Vec3) -> tuple[Vec3, Vec3]:
        ref = (1.0, 0.0, 0.0) if abs(up[0]) < 0.9 else (0.0, 1.0, 0.0)
        e1 = _normalize(_cross(up, ref))
        assert e1 is not None
        e2 = _cross(up, e1)
        return e1, e2

    def _project(self, point_m: Vec3) -> tuple[float, float]:
        assert self._basis is not None
        e1, e2 = self._basis
        return (_dot(point_m, e1), _dot(point_m, e2))

    def _diag(self, rt: _EventRuntime, code: str, body_id: str, t: float,
              step: int, detail: str) -> None:
        key = (body_id, code)
        if key in rt.diagnostic_counts:
            rt.diagnostic_counts[key] += 1
            return
        if len(rt.diagnostics) >= MAX_DIAGNOSTIC_KEYS:
            return
        rt.diagnostic_counts[key] = 1
        rt.diagnostics.append({"code": code, "body_id": body_id,
                               "time_s": float(t), "step": int(step),
                               "detail": detail})

    # ------------------------------------------------------------------ phases
    def begin_phase(self, name: str, kind: str, start_time_s: float,
                    ctrl_zero: bool, *, boundary: StepObservation | None = None) -> None:
        for rt in self._runtimes.values():
            spec = rt.spec
            if name == spec.window_from:
                rt.active = True
                rt.start_time_s = float(start_time_s)
                rt.window_closed = False
                rt.window_complete = False
                rt.phase_incomplete = False
                rt.observations = 0
                rt.missing_body = False
                rt.late_candidate = False
                rt.release_seen = False
                rt.release_time_s = None
                rt.release_zero_ok = True
                rt.zero_input_required = False
                rt.zero_input_ok = True
                rt.zero_checked_samples = 0
                rt.zero_violation = None
                rt.zero_violation_count = 0
                rt.dwell_open = False
                rt.dwell_closed = False
                rt.fatal_codes.clear()
                rt.failure_codes.clear()
                rt.diagnostic_counts.clear()
                rt.diagnostics.clear()
                rt.crossing = {b: _CrossingState() for b in spec.bodies}
                if spec.kind == "supported_presentation":
                    rt.presentation = {b: _PresentationState() for b in spec.bodies}
                if boundary is not None:
                    self._seed_boundary(rt, boundary)
            if name == spec.release_phase:
                rt.release_seen = True
                rt.release_time_s = float(start_time_s)
                # Actual zero input is checked per required post-step sample, not from the
                # pre-step boundary command (which may still be the prior actuation).
                rt.zero_input_required = True
            if name == spec.dwell_from:
                rt.dwell_open = True

    def _seed_boundary(self, rt: _EventRuntime, boundary: StepObservation) -> None:
        """Seed crossing geometry from the coherent pre-step window state.

        The boundary is never a crossing sample and is never release-input evidence. It only
        establishes the previous geometry so a crossing in the first integration step of the
        window is detected rather than mistaken for an initially protruding body.
        """
        spec = rt.spec
        for body_id in spec.bodies:
            body = boundary.bodies.get(body_id)
            if body is None:
                continue
            extent = _extent_along(spec.plane.unit_normal, body.quat_wxyz,
                                   spec.object_half_extents_m)
            signed = _plane_signed(spec.plane, body.pos_m)
            far = signed + extent
            state = rt.crossing[body_id]
            state.seen = True
            state.prev_far_m = far
            state.prev_time_s = boundary.time_s
            state.last_far_m = far
            state.max_far_m = far
            if far > self.plane_eps_m:
                state.suppressed = True
                near = signed - extent
                state.suppress_code = ("initial_outside" if near > self.plane_eps_m
                                       else "initial_protruding")
                self._diag(rt, state.suppress_code, body_id, boundary.time_s,
                           boundary.step_index,
                           "body was already outside the plane at the window boundary")

    def end_phase(self, name: str, *, complete: bool, end_time_s: float,
                  stopped: bool = False) -> None:
        for rt in self._runtimes.values():
            spec = rt.spec
            relevant = (name in (spec.window_from, spec.window_to, spec.release_phase,
                                 spec.dwell_from, spec.dwell_to)
                        or rt.active)
            if relevant and (not complete or stopped):
                rt.phase_incomplete = True
            if name == spec.dwell_to:
                rt.dwell_closed = True
                rt.zero_input_required = False
                self._close_dwell(rt, float(end_time_s))
            if name == spec.window_to:
                rt.window_closed = True
                rt.window_complete = bool(complete and not stopped)

    # ------------------------------------------------------------------ observation
    def observe(self, obs: StepObservation) -> None:
        if self._results is not None:
            raise RuntimeError("observe() after finish()")
        for rt in self._runtimes.values():
            if not rt.active or rt.window_closed:
                continue
            if rt.zero_input_required:
                rt.zero_checked_samples += 1
                if not obs.ctrl_zero:
                    rt.zero_input_ok = False
                    rt.release_zero_ok = False
                    rt.zero_violation_count += 1
                    if rt.zero_violation is None:
                        actual = max(0.0, float(obs.ctrl_max_abs))
                        rt.zero_violation = {
                            "phase": obs.phase_name,
                            "time_s": float(obs.time_s),
                            "step": int(obs.step_index),
                            "actual_max_abs_ctrl": actual,
                        }
                        self._diag(
                            rt, "nonzero_input_after_release", rt.spec.bodies[0],
                            obs.time_s, obs.step_index,
                            f"nonzero actual control during required zero-input "
                            f"interval ({obs.phase_name}, max |ctrl| = {actual:.9g})")
                    for pres in rt.presentation.values():
                        if pres.success:
                            pres.success_revoked = True
            rt.observations += 1
            for body_id in rt.spec.bodies:
                body = obs.bodies.get(body_id)
                if body is None:
                    rt.missing_body = True
                    self._diag(rt, "missing_body", body_id, obs.time_s,
                               obs.step_index, "no body sample for a declared identity")
                    continue
                self._observe_body(rt, body, obs)

    def _observe_body(self, rt: _EventRuntime, body: ObservedBody,
                      obs: StepObservation) -> None:
        spec = rt.spec
        state = rt.crossing[body.body_id]
        extent = _extent_along(spec.plane.unit_normal, body.quat_wxyz,
                               spec.object_half_extents_m)
        signed = _plane_signed(spec.plane, body.pos_m)
        far = signed + extent
        if not state.seen:
            state.seen = True
            state.prev_far_m = far
            state.prev_time_s = obs.time_s
            state.last_far_m = far
            state.max_far_m = far
            if far > self.plane_eps_m:
                state.suppressed = True
                near = signed - extent
                if near > self.plane_eps_m:
                    state.suppress_code = "initial_outside"
                else:
                    state.suppress_code = "initial_protruding"
                self._diag(rt, state.suppress_code, body.body_id, obs.time_s,
                           obs.step_index,
                           "body was already outside the plane at cycle start")
            return
        prev_far = state.prev_far_m
        assert prev_far is not None and state.prev_time_s is not None
        if far > state.max_far_m:
            state.max_far_m = far
        if prev_far <= self.plane_eps_m and far > self.plane_eps_m:
            if state.suppressed:
                self._diag(rt, state.suppress_code or "initial_outside", body.body_id,
                           obs.time_s, obs.step_index,
                           "crossing suppressed because the body started outside")
            elif state.crossed:
                state.repeated_crossings += 1
                self._diag(rt, "re_crossing", body.body_id, obs.time_s,
                           obs.step_index,
                           "same identity crossed outward again in one cycle")
            else:
                # The leading-edge displacement is the crossing criterion. The COM
                # velocity is deliberately not a gate: rotation and slow creep can move
                # the leading edge outward while the COM velocity is small or inward.
                span = far - prev_far
                fraction = (-prev_far / span) if span > 0.0 else 0.0
                fraction = min(max(fraction, 0.0), 1.0)
                state.crossed = True
                state.touch_only = False
                state.crossing_time_s = (state.prev_time_s
                                         + (obs.time_s - state.prev_time_s) * fraction)
                state.crossing_signed_m = signed
                state.crossing_protrusion_m = far
        elif prev_far > self.plane_eps_m and far <= -self.plane_eps_m:
            state.wrong_direction_count += 1
            self._diag(rt, "wrong_direction", body.body_id, obs.time_s,
                       obs.step_index, "body crossed back inward against the configured exit")
        if (not state.crossed and state.max_far_m > 0.0
                and state.max_far_m <= self.plane_eps_m):
            state.touch_only = True
        state.prev_far_m = far
        state.prev_time_s = obs.time_s
        state.last_far_m = far
        state.last_protrusion_m = max(0.0, far)
        if spec.kind == "supported_presentation" and self.up is not None:
            self._observe_presentation(rt, body, obs, state, far)

    def _support_metrics(self, rt: _EventRuntime, body: ObservedBody,
                         obs: StepObservation) -> SupportMetrics:
        spec = rt.spec
        assert self.up is not None
        points: list[tuple[float, float]] = []
        load = 0.0
        for contact in obs.contacts:
            if body.body_id == contact.body_a:
                other = contact.body_b
            elif body.body_id == contact.body_b:
                other = contact.body_a
            else:
                continue
            if other not in spec.support_bodies:
                continue
            normal = contact.normal_world
            toward_com = _sub(body.com_m, contact.position_m)
            if _dot(normal, toward_com) < 0.0:
                normal = _mul(normal, -1.0)
            vertical = _dot(normal, self.up)
            if vertical <= 0.0:
                continue
            force = abs(float(contact.normal_force_n))
            if not math.isfinite(force) or force <= 0.0:
                continue
            load += force * vertical
            if len(points) < 256:
                points.append(self._project(contact.position_m))
        weight = max(0.0, float(body.mass_kg)) * self.gravity_magnitude
        fraction = (load / weight) if weight > 0.0 else 0.0
        if not math.isfinite(fraction):
            fraction = 0.0
        hull_state, margin = _hull_state(points, self._project(body.com_m), spec)
        near_fraction = (spec.min_support_load_fraction > 0.0
                         and abs(fraction - spec.min_support_load_fraction)
                         <= 0.05 * spec.min_support_load_fraction)
        uncertain = hull_state == "marginal" or near_fraction
        ok = (fraction + 1e-12 >= spec.min_support_load_fraction
              and hull_state in ("inside", "line") and not near_fraction)
        return SupportMetrics(load, fraction, hull_state, len(points), margin,
                              uncertain, ok)

    def _presentation_metrics(self, rt: _EventRuntime, body: ObservedBody,
                              obs: StepObservation) -> tuple[bool, dict] | None:
        spec = rt.spec
        if self.up is None:
            return None
        extent_outer = _extent_along(spec.plane.unit_normal, body.quat_wxyz,
                                     spec.object_half_extents_m)
        outer_far = _plane_signed(spec.plane, body.pos_m) + extent_outer
        protrusion = max(0.0, outer_far)
        accessible = 0.0
        if spec.access_plane is not None:
            extent_access = _extent_along(spec.access_plane.unit_normal, body.quat_wxyz,
                                          spec.object_half_extents_m)
            accessible = max(0.0, _plane_signed(spec.access_plane, body.pos_m)
                             + extent_access)
        support = self._support_metrics(rt, body, obs)
        speed = _norm(body.linear_velocity_m_s)
        out_of_bounds = False
        if spec.bounds_m is not None:
            for axis, value in enumerate(body.com_m):
                low, high = spec.bounds_m[axis]
                if value < low - 1e-12 or value > high + 1e-12:
                    out_of_bounds = True
        conditions = (not out_of_bounds
                      and protrusion + 1e-12 >= spec.min_protrusion_m
                      and accessible + 1e-12 >= spec.min_accessible_m
                      and support.ok
                      and speed <= spec.max_terminal_speed_m_s + 1e-12)
        return conditions, {
            "protrusion_m": protrusion, "accessible_m": accessible,
            "support": support, "speed_m_s": speed, "out_of_bounds": out_of_bounds,
        }

    def _observe_presentation(self, rt: _EventRuntime, body: ObservedBody,
                              obs: StepObservation,
                              crossing: _CrossingState, far: float) -> None:
        assert self.up is not None
        spec = rt.spec
        state = rt.presentation[body.body_id]
        state.last_protrusion_m = max(0.0, far)
        up_coord = _dot(body.com_m, self.up)
        state.max_up_m = (up_coord if state.max_up_m is None
                          else max(state.max_up_m, up_coord))
        metrics = self._presentation_metrics(rt, body, obs)
        if metrics is None:
            return
        conditions, values = metrics
        support: SupportMetrics = values["support"]
        state.last_support_load_n = support.load_n
        state.last_support_fraction = support.fraction
        state.last_hull_state = support.hull_state
        state.last_accessible_m = values["accessible_m"]
        if support.fraction + 1e-12 >= spec.min_support_load_fraction:
            state.support_seen = True
        if values["out_of_bounds"]:
            state.out_of_bounds = True
            rt.failure_codes.add("out_of_bounds")
            rt.fatal_codes.add("out_of_bounds")
            self._diag(rt, "out_of_bounds", body.body_id, obs.time_s,
                       obs.step_index, "COM left the declared bounds")
        if support.uncertain:
            state.support_uncertain = True
            self._diag(rt, "support_uncertain", body.body_id, obs.time_s,
                       obs.step_index,
                       f"support state {support.hull_state} with margin "
                       f"{support.margin_m}")
        if (state.max_up_m is not None
                and up_coord < state.max_up_m - spec.fallout_drop_m
                and support.fraction + 1e-12 < spec.min_support_load_fraction):
            rt.failure_codes.add("uncontrolled_fallout")
            rt.fatal_codes.add("uncontrolled_fallout")
            self._diag(rt, "uncontrolled_fallout", body.body_id, obs.time_s,
                       obs.step_index, "unsupported COM fell beyond the declared drop")
        if not rt.zero_input_ok:
            # The run is already invalid for a release-zero violation; do not manufacture a
            # new successful dwell from later samples.
            return
        if not crossing.crossed:
            return
        if rt.release_time_s is None:
            return
        if obs.time_s + 1e-12 < rt.release_time_s:
            return
        if rt.dwell_closed:
            # Conditions first holding after the bounded dwell window cannot rescue the run.
            if conditions and not state.success and not rt.late_candidate:
                rt.late_candidate = True
                self._diag(rt, "late_presentation", body.body_id, obs.time_s,
                           obs.step_index,
                           "presentation conditions first held after the dwell window")
            if not conditions and state.success:
                state.success_revoked = True
                rt.failure_codes.add("post_dwell_failure")
                rt.fatal_codes.add("post_dwell_failure")
                self._diag(rt, "post_dwell_failure", body.body_id, obs.time_s,
                           obs.step_index, "support or stability failed after the dwell")
            return
        if not rt.dwell_open:
            return
        if conditions:
            if not state.dwell_active:
                self._start_dwell(state, obs.time_s, values, spec)
            else:
                self._update_dwell(rt, state, obs.time_s, values, body.body_id)
        else:
            if state.dwell_active:
                rt.failure_codes.add("dwell_interrupted")
                state.dwell_interruptions += 1
                self._diag(rt, "dwell_interrupted", body.body_id, obs.time_s,
                           obs.step_index, "a required dwell condition failed")
                if support.fraction + 1e-12 < spec.min_support_load_fraction:
                    state.support_lost = True
                    rt.failure_codes.add("support_lost")
                    rt.fatal_codes.add("support_lost")
                    self._diag(rt, "support_lost", body.body_id, obs.time_s,
                               obs.step_index, "support load fell below the declared fraction")
                if state.success:
                    state.success_revoked = True
                    rt.failure_codes.add("post_dwell_failure")
                    rt.fatal_codes.add("post_dwell_failure")
                    self._diag(rt, "post_dwell_failure", body.body_id, obs.time_s,
                               obs.step_index, "support or stability failed after the dwell")
                self._reset_dwell(state)
            else:
                if (state.support_seen
                        and support.fraction + 1e-12 < spec.min_support_load_fraction):
                    state.support_lost = True
                    rt.failure_codes.add("support_lost")
                    rt.fatal_codes.add("support_lost")
                    self._diag(rt, "support_lost", body.body_id, obs.time_s,
                               obs.step_index, "support load below the declared fraction")
                if support.hull_state == "outside":
                    rt.failure_codes.add("unsupported_com")
                    self._diag(rt, "unsupported_com", body.body_id, obs.time_s,
                               obs.step_index, "projected COM is outside the support hull")
                if values["protrusion_m"] + 1e-12 < spec.min_protrusion_m:
                    rt.failure_codes.add("protrusion_below_min")
                if values["accessible_m"] + 1e-12 < spec.min_accessible_m:
                    rt.failure_codes.add("accessibility_below_min")
                if values["speed_m_s"] > spec.max_terminal_speed_m_s + 1e-12:
                    rt.failure_codes.add("motion_unstable")

    @staticmethod
    def _near_threshold(spec: EventSpec, values: dict, elapsed: float | None) -> bool:
        support: SupportMetrics = values["support"]
        protrusion_band = max(0.01 * spec.min_protrusion_m, 1e-4)
        access_band = max(0.01 * spec.min_accessible_m, 1e-4)
        # Duration uncertainty is assessed once from the sustained dwell length, not from
        # every sample that happens to cross the minimum on its way to a longer hold.
        _ = elapsed
        return (support.uncertain
                or abs(values["protrusion_m"] - spec.min_protrusion_m) <= protrusion_band
                or abs(values["accessible_m"] - spec.min_accessible_m) <= access_band)

    @classmethod
    def _start_dwell(cls, state: _PresentationState, t: float, values: dict,
                     spec: EventSpec) -> None:
        protrusion = values["protrusion_m"]
        state.dwell_active = True
        state.dwell_start_s = float(t)
        state.dwell_start_protrusion_m = protrusion
        state.dwell_min_protrusion_m = protrusion
        state.dwell_max_protrusion_m = protrusion
        state.dwell_min_support_fraction = values["support"].fraction
        state.dwell_sustained_end_s = float(t)
        state.dwell_uncertain = cls._near_threshold(spec, values, 0.0)

    def _update_dwell(self, rt: _EventRuntime, state: _PresentationState, t: float,
                      values: dict, body_id: str) -> None:
        spec = rt.spec
        assert state.dwell_active and state.dwell_start_s is not None
        protrusion = values["protrusion_m"]
        state.dwell_min_protrusion_m = min(state.dwell_min_protrusion_m, protrusion)
        state.dwell_max_protrusion_m = max(state.dwell_max_protrusion_m, protrusion)
        state.dwell_min_support_fraction = min(state.dwell_min_support_fraction,
                                               values["support"].fraction)
        state.dwell_sustained_end_s = float(t)
        drift = state.dwell_max_protrusion_m - state.dwell_min_protrusion_m
        if drift > spec.protrusion_change_max_m + 1e-12:
            rt.failure_codes.add("drift_exceeded")
            rt.failure_codes.add("dwell_interrupted")
            state.dwell_interruptions += 1
            self._diag(rt, "drift_exceeded", body_id, t, -1,
                       f"protrusion changed {drift:.6g} m during the dwell")
            if state.success:
                state.success_revoked = True
                rt.failure_codes.add("post_dwell_failure")
                rt.fatal_codes.add("post_dwell_failure")
                self._diag(rt, "post_dwell_failure", body_id, t, -1,
                           "protrusion drifted after the dwell had succeeded")
                self._reset_dwell(state)
                return
            self._reset_dwell(state)
            self._start_dwell(state, t, values, spec)
            return
        elapsed = max(0.0, t - state.dwell_start_s)
        state.dwell_uncertain = state.dwell_uncertain or self._near_threshold(
            spec, values, elapsed)
        if not state.success and elapsed + 1e-12 >= spec.dwell_min_s:
            state.success = True
            state.success_time_s = float(t)
            state.success_protrusion_m = protrusion

    @staticmethod
    def _reset_dwell(state: _PresentationState) -> None:
        state.dwell_active = False
        state.dwell_start_s = None
        state.dwell_start_protrusion_m = None
        state.dwell_min_protrusion_m = None
        state.dwell_max_protrusion_m = None
        state.dwell_min_support_fraction = None
        state.dwell_sustained_end_s = None
        state.dwell_uncertain = False

    def _close_dwell(self, rt: _EventRuntime, end_time_s: float) -> None:
        for body_id, state in rt.presentation.items():
            if state.success and not state.success_revoked:
                # The dwell completed; it must remain supported through the bounded window.
                continue
            if state.dwell_active:
                elapsed = (end_time_s - state.dwell_start_s
                           if state.dwell_start_s is not None else 0.0)
                if elapsed + 1e-12 < rt.spec.dwell_min_s:
                    rt.failure_codes.add("dwell_too_short")
                    self._diag(rt, "dwell_too_short", body_id, end_time_s, -1,
                               f"dwell window closed after {elapsed:.6g} s")
                else:
                    rt.failure_codes.add("dwell_incomplete")
                state.dwell_active = False

    # ------------------------------------------------------------------ results
    def finish(self, *, stopped: bool, final_time_s: float) -> dict[str, EventResult]:
        if self._results is not None:
            return self._results
        results: dict[str, EventResult] = {}
        for rt in self._runtimes.values():
            results[rt.spec.name] = self._result(rt, stopped=stopped,
                                                 final_time_s=final_time_s)
        self._results = results
        return results

    def _result(self, rt: _EventRuntime, *, stopped: bool,
                final_time_s: float) -> EventResult:
        spec = rt.spec
        crossed = [b for b, s in rt.crossing.items() if s.crossed]
        count = len(crossed)
        if spec.kind == "supported_presentation":
            rt.release_zero_ok = bool(rt.zero_input_ok
                                      and rt.zero_checked_samples > 0)
        invalid_reasons: tuple[dict, ...] = ()
        if rt.zero_violation is not None:
            violation = rt.zero_violation
            reason = (
                "nonzero actual control during required zero-input interval "
                f"({violation['phase']}, step {violation['step']}, "
                f"t={violation['time_s']:.9g} s, "
                f"max |ctrl|={violation['actual_max_abs_ctrl']:.9g}); "
                "a commanded zero is not proof of actual zero")
            invalid_reasons = ({"stage": "release_input", "reason": reason,
                                "time_s": violation["time_s"]},)
        complete = bool(rt.active and rt.window_closed and rt.window_complete
                        and not stopped and not rt.phase_incomplete
                        and not rt.missing_body and rt.observations > 0)
        bodies: dict[str, dict] = {}
        for body_id, state in rt.crossing.items():
            pres = rt.presentation.get(body_id)
            entry = {
                "initial_outside": state.suppress_code == "initial_outside",
                "initial_protruding": state.suppress_code == "initial_protruding",
                "crossed": state.crossed,
                "crossing_time_s": state.crossing_time_s,
                "crossing_protrusion_m": state.crossing_protrusion_m,
                "repeated_crossings": state.repeated_crossings,
                "wrong_direction_count": state.wrong_direction_count,
                "touch_only": state.touch_only,
                "last_protrusion_m": state.last_protrusion_m,
            }
            if pres is not None:
                entry.update({
                    "support_seen": pres.support_seen,
                    "support_lost": pres.support_lost,
                    "support_uncertain": pres.support_uncertain,
                    "out_of_bounds": pres.out_of_bounds,
                    "last_support_fraction": pres.last_support_fraction,
                    "last_support_load_n": pres.last_support_load_n,
                    "last_support_hull": pres.last_hull_state,
                    "success": pres.success and not pres.success_revoked,
                    "dwell_start_s": pres.dwell_start_s,
                    "success_time_s": pres.success_time_s,
                    "dwell_interruptions": pres.dwell_interruptions,
                })
            bodies[body_id] = entry
        crossings = []
        for body_id in crossed:
            state = rt.crossing[body_id]
            crossings.append({
                "body_id": body_id,
                "time_s": state.crossing_time_s,
                "direction": ("+" if spec.plane.direction > 0 else "-") + "normal",
                "signed_m": state.crossing_signed_m,
                "protrusion_m": state.crossing_protrusion_m,
            })
        for body_id, state in rt.crossing.items():
            if state.touch_only:
                self._diag(rt, "touch_only", body_id, final_time_s, -1,
                           "max leading-edge excursion stayed inside the tolerance band")
            if state.wrong_direction_count and (body_id, "wrong_direction") not in \
                    rt.diagnostic_counts:
                self._diag(rt, "wrong_direction", body_id, final_time_s, -1,
                           "wrong-direction crossing was observed")
            if state.suppress_code and (body_id, state.suppress_code) not in \
                    rt.diagnostic_counts:
                self._diag(rt, state.suppress_code, body_id, final_time_s, -1,
                           "body started outside the exit plane in this cycle")
        if count == 0:
            self._diag(rt, "zero_feed", rt.spec.bodies[0], final_time_s, -1,
                       "no declared identity crossed outward in the window")
        elif count > 1:
            self._diag(rt, "double_feed", rt.spec.bodies[0], final_time_s, -1,
                       f"{count} distinct identities crossed outward in one cycle")
        codes = set(rt.failure_codes)
        for state in rt.crossing.values():
            if state.suppress_code:
                codes.add(state.suppress_code)
            if state.wrong_direction_count:
                codes.add("wrong_direction")
            if state.touch_only:
                codes.add("touch_only")
        if count == 0:
            codes.add("zero_feed")
        elif count > 1:
            codes.add("double_feed")

        dwell = None
        if spec.kind == "supported_presentation":
            winner = next((b for b in crossed
                           if rt.presentation[b].success
                           and not rt.presentation[b].success_revoked), None)
            if winner is None:
                winner = crossed[0] if crossed else None
            if winner is not None:
                pres = rt.presentation[winner]
                if pres.dwell_start_s is not None:
                    end = (pres.dwell_sustained_end_s
                           if pres.dwell_sustained_end_s is not None
                           else pres.success_time_s)
                    duration = (end - pres.dwell_start_s) if end is not None else None
                    dwell = {
                        "body_id": winner,
                        "start_s": pres.dwell_start_s,
                        "end_s": end,
                        "duration_s": duration,
                        "protrusion_min_m": pres.dwell_min_protrusion_m,
                        "protrusion_max_m": pres.dwell_max_protrusion_m,
                        "change_m": ((pres.dwell_max_protrusion_m
                                      - pres.dwell_min_protrusion_m)
                                     if pres.dwell_min_protrusion_m is not None else None),
                        "support_fraction_min": pres.dwell_min_support_fraction,
                        "uncertain": pres.dwell_uncertain,
                    }

        if spec.kind == "exit_crossing":
            status = "PASS" if complete else "INCONCLUSIVE"
            code = "crossings_recorded" if complete else "insufficient_observation"
            detail = (f"{count} distinct body identity(ies) crossed the configured plane; "
                      f"repeated crossings are diagnostics, not additional identities")
            ok = None
        else:
            ok = None
            if rt.zero_violation is not None:
                status, code = "INCONCLUSIVE", "nonzero_input_after_release"
                codes.add("nonzero_input_after_release")
            elif not complete:
                status, code = "INCONCLUSIVE", "insufficient_observation"
                if rt.missing_body:
                    code = "missing_body"
                elif not rt.release_seen:
                    code = "release_not_observed"
                elif stopped or rt.phase_incomplete:
                    code = "evidence_truncated"
            elif rt.zero_checked_samples == 0:
                status, code = "INCONCLUSIVE", "release_input_not_observed"
            elif self.gravity_magnitude <= 0.0:
                status, code = "INCONCLUSIVE", "gravity_absent"
            elif count == 0:
                if "out_of_bounds" in rt.fatal_codes:
                    status, code = "FAIL", "out_of_bounds"
                elif "uncontrolled_fallout" in rt.fatal_codes:
                    status, code = "FAIL", "uncontrolled_fallout"
                else:
                    status, code = "FAIL", "zero_feed"
            elif count > 1:
                status, code = "FAIL", "double_feed"
            elif "out_of_bounds" in rt.fatal_codes:
                status, code = "FAIL", "out_of_bounds"
            elif "uncontrolled_fallout" in rt.fatal_codes:
                status, code = "FAIL", "uncontrolled_fallout"
            elif "support_lost" in rt.fatal_codes:
                status, code = "FAIL", "support_lost"
            elif "post_dwell_failure" in rt.fatal_codes:
                status, code = "FAIL", "post_dwell_failure"
            elif any(pres.success and not pres.success_revoked
                     for pres in rt.presentation.values()):
                success_body, success_pres = next(
                    (body_id, pres) for body_id, pres in rt.presentation.items()
                    if pres.success and not pres.success_revoked)
                duration = (None if success_pres.dwell_sustained_end_s is None
                            or success_pres.dwell_start_s is None
                            else success_pres.dwell_sustained_end_s
                            - success_pres.dwell_start_s)
                band = 0.01 * spec.dwell_min_s
                if (success_pres.dwell_uncertain
                        or (duration is not None
                            and duration < spec.dwell_min_s + band)):
                    status, code = "INCONCLUSIVE", "near_threshold"
                    codes.add("near_threshold")
                    self._diag(rt, "near_threshold", success_body, final_time_s, -1,
                               "a successful dwell was within the declared near-threshold band")
                else:
                    status, code = "PASS", "supported_presentation"
            elif rt.late_candidate:
                status, code = "FAIL", "late_presentation"
            elif any(pres.support_uncertain for pres in rt.presentation.values()):
                status, code = "INCONCLUSIVE", "support_uncertain"
            elif "unsupported_com" in codes:
                status, code = "FAIL", "unsupported_com"
            elif "no_support_load" in codes or not any(
                    pres.support_seen for pres in rt.presentation.values()):
                status, code = "FAIL", "no_support_load"
            else:
                status, code = "FAIL", "missed_presentation"
            ok = status == "PASS"
            detail = (f"crossed by {count} distinct identity(ies); verdict {code}; "
                      f"codes {sorted(codes)}")
        diagnostics = tuple(dict(d, occurrences=rt.diagnostic_counts.get(
            (d["body_id"], d["code"]), 1)) for d in rt.diagnostics)
        return EventResult(
            name=spec.name, kind=spec.kind, status=status, ok=ok,
            verdict_code=code, detail=detail, distinct_bodies_crossed=count,
            evidence_complete=complete, crossings=tuple(crossings), bodies=bodies,
            dwell=dwell, diagnostics=diagnostics,
            release_time_s=rt.release_time_s,
            release_zero_ok=(rt.release_zero_ok
                             if spec.kind == "supported_presentation" else None),
            release_zero_checked_samples=rt.zero_checked_samples,
            release_zero_violation=(dict(rt.zero_violation)
                                    if rt.zero_violation is not None else None),
            invalid_reasons=invalid_reasons,
        )
