"""Strict, bounded assembly options for the Pocky prototype.

Supported options are the equivalent spring rate (200 / 500 / 1000 N/m), the timestep
(1 ms / 0.5 ms at the original 2 ms compliance; 62.5 us / 31.25 us at the validated 0.25 ms
compliance) and the contact / stop time constants, each restricted to {2 ms, 0.25 ms}. Both
time constants must be at least twice the timestep. Everything else is rejected rather than
silently ignored: loaded packets, the 25-capacity tube, packet mass, friction and initial
fractions are not run choices here. The validated numerics come from
``out/mujoco-sim-valid/sweep/results.md``; the 2 ms defaults keep the M5a-1 evidence
reproducible.

The parsed table is the top-level ``cad physics run --options`` document. The generic CLI
already bounds its size and shape; this module enforces the project's semantics before a
scene is built, so an unsupported option can never reach a compiled scene.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

SPRING_RATES_N_M = (200.0, 500.0, 1000.0)
TIMESTEPS_S = (1.0e-3, 5.0e-4, 6.25e-5, 3.125e-5)
TIMECONSTS_S = (2.0e-3, 2.5e-4)
DEFAULT_SPRING_N_M = 500.0
DEFAULT_TIMESTEP_S = 1.0e-3
DEFAULT_TIMECONST_S = 2.0e-3
#: MuJoCo needs solref timeconst >= 2*dt for the soft constraint to be resolved.
MIN_TIMECONST_PER_TIMESTEP = 2.0

SUPPORTED_KEYS = frozenset({
    "spring_stiffness_n_m", "timestep_s", "contact_timeconst_s", "stop_timeconst_s",
    "button_actuator",
})
REJECTED_KEYS = {
    "packets": "loaded packets need a later bounded planning approval",
    "capacity": "the 25-capacity tube needs a later bounded planning approval",
    "packet_mass_kg": "packet mass is only meaningful with loaded packets",
    "friction": "friction is a declared physical input, not a run option",
    "button_fraction": "the runtime scene is always built at fraction 0",
}


@dataclass(frozen=True)
class AssemblyOptions:
    spring_stiffness_n_m: float = DEFAULT_SPRING_N_M
    timestep_s: float = DEFAULT_TIMESTEP_S
    contact_timeconst_s: float = DEFAULT_TIMECONST_S
    stop_timeconst_s: float = DEFAULT_TIMECONST_S
    #: Opt-in bounded force actuator on the rod slide (the button); off keeps the scene identical.
    button_actuator: bool = False

    def _compliance_is_default(self) -> bool:
        return (self.contact_timeconst_s == DEFAULT_TIMECONST_S
                and self.stop_timeconst_s == DEFAULT_TIMECONST_S)

    def as_dict(self) -> dict[str, float]:
        out = {
            "spring_stiffness_n_m": self.spring_stiffness_n_m,
            "timestep_s": self.timestep_s,
        }
        # The compliance keys appear only when non-default, so the original base-case
        # document (and its hash) is unchanged.
        if not self._compliance_is_default():
            out["contact_timeconst_s"] = self.contact_timeconst_s
            out["stop_timeconst_s"] = self.stop_timeconst_s
        if self.button_actuator:
            out["button_actuator"] = True
        return out

    def canonical_toml(self) -> str:
        text = (
            f"spring_stiffness_n_m = {self.spring_stiffness_n_m:.1f}\n"
            f"timestep_s = {self.timestep_s!r}\n"
        )
        if not self._compliance_is_default():
            text += (
                f"contact_timeconst_s = {self.contact_timeconst_s!r}\n"
                f"stop_timeconst_s = {self.stop_timeconst_s!r}\n"
            )
        if self.button_actuator:
            text += "button_actuator = true\n"
        return text


def _number(key: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"assembly option {key!r} must be a number, got {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"assembly option {key!r} must be finite, got {value!r}")
    return number


def load_options(table: Mapping[str, Any] | None) -> AssemblyOptions:
    """Validate one parsed options table and return the typed choices.

    Unknown keys, rejected keys, out-of-range values and non-scalar values all raise
    ``ValueError``. A rejected option never falls back to a default silently.
    """
    if table is None:
        return AssemblyOptions()
    if not isinstance(table, Mapping):
        raise ValueError(f"assembly options must be a table, got {type(table).__name__}")
    unknown = sorted(set(table) - SUPPORTED_KEYS)
    for key in unknown:
        if key in REJECTED_KEYS:
            raise ValueError(f"assembly option {key!r} is not supported: {REJECTED_KEYS[key]}")
    if unknown:
        raise ValueError(
            f"unknown assembly option(s) {unknown}; supported: {sorted(SUPPORTED_KEYS)}"
        )
    spring = DEFAULT_SPRING_N_M
    timestep = DEFAULT_TIMESTEP_S
    if "spring_stiffness_n_m" in table:
        spring = _number("spring_stiffness_n_m", table["spring_stiffness_n_m"])
        if spring not in SPRING_RATES_N_M:
            raise ValueError(
                f"spring_stiffness_n_m {spring!r} is outside the approved sensitivity set "
                f"{SPRING_RATES_N_M}"
            )
    if "timestep_s" in table:
        timestep = _number("timestep_s", table["timestep_s"])
        if timestep not in TIMESTEPS_S:
            raise ValueError(
                f"timestep_s {timestep!r} is outside the approved set {TIMESTEPS_S}"
            )
    timeconsts = {}
    for key in ("contact_timeconst_s", "stop_timeconst_s"):
        value = DEFAULT_TIMECONST_S
        if key in table:
            value = _number(key, table[key])
            if value not in TIMECONSTS_S:
                raise ValueError(f"{key} {value!r} is outside the approved set {TIMECONSTS_S}")
        if value < MIN_TIMECONST_PER_TIMESTEP * timestep:
            raise ValueError(
                f"{key} {value!r} s is below 2 x timestep_s ({2.0 * timestep!r} s); MuJoCo "
                f"cannot resolve a soft constraint faster than two steps"
            )
        timeconsts[key] = value
    button_actuator = False
    if "button_actuator" in table:
        button_actuator = table["button_actuator"]
        if not isinstance(button_actuator, bool):
            raise ValueError(
                f"assembly option 'button_actuator' must be true or false, got {button_actuator!r}"
            )
    return AssemblyOptions(spring_stiffness_n_m=spring, timestep_s=timestep,
                           button_actuator=button_actuator, **timeconsts)
