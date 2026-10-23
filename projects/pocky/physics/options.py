"""Strict, bounded assembly options for the Pocky prototype.

The only options this increment supports are the two approved sensitivities: the equivalent
spring rate (200 / 500 / 1000 N/m) and the timestep (1 ms / 0.5 ms). Everything else is
rejected rather than silently ignored: loaded packets, the 25-capacity tube, packet mass,
contact/stop compliance, friction and initial fractions are not run choices here.

The parsed table is the top-level ``cad physics run --options`` document. The generic CLI
already bounds its size and shape; this module enforces the project's semantics before a
scene is built, so an unsupported option can never reach a compiled scene.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

SPRING_RATES_N_M = (200.0, 500.0, 1000.0)
TIMESTEPS_S = (1.0e-3, 5.0e-4)
DEFAULT_SPRING_N_M = 500.0
DEFAULT_TIMESTEP_S = 1.0e-3

SUPPORTED_KEYS = frozenset({"spring_stiffness_n_m", "timestep_s"})
REJECTED_KEYS = {
    "packets": "loaded packets need a later bounded planning approval",
    "capacity": "the 25-capacity tube needs a later bounded planning approval",
    "packet_mass_kg": "packet mass is only meaningful with loaded packets",
    "contact_timeconst_s": "contact compliance is fixed at 2 ms for the timestep studies",
    "stop_timeconst_s": "stop compliance is fixed at 2 ms",
    "friction": "friction is a declared physical input, not a run option",
    "button_fraction": "the runtime scene is always built at fraction 0",
}


@dataclass(frozen=True)
class AssemblyOptions:
    spring_stiffness_n_m: float = DEFAULT_SPRING_N_M
    timestep_s: float = DEFAULT_TIMESTEP_S

    def as_dict(self) -> dict[str, float]:
        return {
            "spring_stiffness_n_m": self.spring_stiffness_n_m,
            "timestep_s": self.timestep_s,
        }

    def canonical_toml(self) -> str:
        return (
            f"spring_stiffness_n_m = {self.spring_stiffness_n_m:.1f}\n"
            f"timestep_s = {self.timestep_s!r}\n"
        )


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
    return AssemblyOptions(spring_stiffness_n_m=spring, timestep_s=timestep)
