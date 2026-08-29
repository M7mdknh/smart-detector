"""Deterministic sensor-value generator: physical concentration + seeded noise + fault.

Same seed/preset/commands must reproduce equal readings within 1e-6 (see
simulator-specification.md "Determinism Tests").
"""

from dataclasses import dataclass

import numpy as np

from app.domain.physics.mass_balance import Segment, concentration_at

HEALTHY_NOISE_STD_PPM = 20.0
STEP_MINUTES = 5


@dataclass(frozen=True)
class GeneratedReading:
    true_ppm: float
    observed_ppm: float
    quality: str
    fault_code: str | None


def tick_rng(seed: int, tick_index: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([seed, tick_index]))


def generate_tick(
    seed: int,
    tick_index: int,
    seg: Segment,
    last_true_ppm: float,
    fault: str | None,
) -> GeneratedReading:
    step_hours = STEP_MINUTES / 60.0
    true_ppm = concentration_at(seg, last_true_ppm, step_hours)

    rng = tick_rng(seed, tick_index)
    noise = float(rng.normal(0.0, HEALTHY_NOISE_STD_PPM))
    observed = max(0.0, true_ppm + noise)

    quality = "GOOD"
    fault_code = None
    if fault == "STUCK":
        observed = last_true_ppm
        quality = "STUCK"
        fault_code = "STUCK"
    elif fault == "NOISY":
        observed = max(0.0, true_ppm + float(rng.normal(0.0, HEALTHY_NOISE_STD_PPM * 6)))
        quality = "NOISY"
        fault_code = "NOISY"

    return GeneratedReading(true_ppm=true_ppm, observed_ppm=observed, quality=quality, fault_code=fault_code)
