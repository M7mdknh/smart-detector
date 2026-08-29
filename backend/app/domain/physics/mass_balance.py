"""Well-mixed single-zone mass-balance physics for CO2 concentration.

dC/dt = Q/V * (Cin - C) + G/V
tau = V/Q
Css = Cin + G/Q
C(t) = Css + (C0 - Css) * exp(-t/tau)

C, Cin are ppm; V is m3; Q is m3/hour; G is stored as ppm*m3/hour (already a
concentration-equivalent source rate, not a physical mass rate). See
CLAUDE.md "Gas Physics and Exposure" for the unit-layer contract.
"""

import math
from dataclasses import dataclass


class InvalidPhysicsParameters(ValueError):
    pass


@dataclass(frozen=True)
class Segment:
    """Constant-parameter segment: Q, Cin, G held fixed over duration_hours."""

    volume_m3: float
    inlet_ppm: float
    ventilation_m3h: float
    source_ppm_m3h: float
    duration_hours: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.volume_m3) or self.volume_m3 <= 0:
            raise InvalidPhysicsParameters("volume_m3 must be positive and finite")
        if not math.isfinite(self.inlet_ppm) or self.inlet_ppm < 0:
            raise InvalidPhysicsParameters("inlet_ppm must be non-negative and finite")
        if not math.isfinite(self.ventilation_m3h) or self.ventilation_m3h < 0:
            raise InvalidPhysicsParameters("ventilation_m3h must be non-negative and finite")
        if not math.isfinite(self.source_ppm_m3h) or self.source_ppm_m3h < 0:
            raise InvalidPhysicsParameters("source_ppm_m3h must be non-negative and finite")
        if not math.isfinite(self.duration_hours) or self.duration_hours < 0:
            raise InvalidPhysicsParameters("duration_hours must be non-negative and finite")


def steady_state_ppm(seg: Segment) -> float:
    """Css = Cin + G/Q. Zero ventilation degenerates to pure accumulation (no steady state);
    callers must use `concentration_at` which handles Q=0 as an accumulation path."""
    if seg.ventilation_m3h == 0:
        raise InvalidPhysicsParameters("steady state undefined at zero ventilation")
    return seg.inlet_ppm + seg.source_ppm_m3h / seg.ventilation_m3h


def concentration_at(seg: Segment, c0_ppm: float, t_hours: float) -> float:
    """Concentration after t_hours within one constant-parameter segment.

    Handles Q=0 (no ventilation) as a safe pure-accumulation path:
    dC/dt = G/V  =>  C(t) = C0 + (G/V) * t
    """
    if not math.isfinite(c0_ppm) or c0_ppm < 0:
        raise InvalidPhysicsParameters("c0_ppm must be non-negative and finite")
    if not math.isfinite(t_hours) or t_hours < 0:
        raise InvalidPhysicsParameters("t_hours must be non-negative and finite")

    if seg.ventilation_m3h == 0:
        c = c0_ppm + (seg.source_ppm_m3h / seg.volume_m3) * t_hours
        return max(0.0, c)

    tau = seg.volume_m3 / seg.ventilation_m3h
    css = steady_state_ppm(seg)
    c = css + (c0_ppm - css) * math.exp(-t_hours / tau)
    return max(0.0, c)


def integrate_piecewise(
    segments: list[Segment], c0_ppm: float, step_hours: float = 5.0 / 60.0
) -> list[float]:
    """Integrate concentration across possibly-varying segments, sampled at `step_hours`.

    Returns one value per completed step per segment (not including t=0).
    Each segment is itself treated as constant-parameter internally (closed form),
    so this is "piecewise closed-form" rather than raw numerical integration --
    valid because CLAUDE.md only requires numerical integration when parameters
    vary *within* a step; each call segment here is by construction constant.
    """
    out: list[float] = []
    c = c0_ppm
    for seg in segments:
        n_steps = max(1, round(seg.duration_hours / step_hours)) if seg.duration_hours > 0 else 0
        remaining = seg.duration_hours
        for i in range(n_steps):
            dt = min(step_hours, remaining)
            if dt <= 0:
                break
            c = concentration_at(seg, c, dt)
            remaining -= dt
            out.append(c)
    return out


def time_to_threshold_hours(seg: Segment, c0_ppm: float, threshold_ppm: float) -> float | None:
    """Analytic time to cross `threshold_ppm` within this constant-parameter segment.

    Returns None if the segment never reaches the threshold (NO_CROSSING candidate).
    Raises InvalidPhysicsParameters for non-finite/invalid inputs.
    """
    if not math.isfinite(threshold_ppm) or threshold_ppm < 0:
        raise InvalidPhysicsParameters("threshold_ppm must be non-negative and finite")

    if seg.ventilation_m3h == 0:
        rate = seg.source_ppm_m3h / seg.volume_m3
        if rate <= 0:
            return None
        if c0_ppm >= threshold_ppm:
            return 0.0
        return (threshold_ppm - c0_ppm) / rate

    tau = seg.volume_m3 / seg.ventilation_m3h
    css = steady_state_ppm(seg)

    if c0_ppm >= threshold_ppm:
        return 0.0

    # Rising toward css: only reachable if css > threshold.
    if css <= threshold_ppm:
        return None
    if c0_ppm >= css:
        return None

    ratio = (threshold_ppm - css) / (c0_ppm - css)
    if ratio <= 0:
        return None
    t = -tau * math.log(ratio)
    if not math.isfinite(t) or t < 0:
        return None
    return t
