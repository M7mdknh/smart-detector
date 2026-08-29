"""Generates labeled synthetic scenarios for XGBoost leak-classifier training.

Uses the same physics/generator code as the live simulator (no separate training
simulator), split by scenario ID/seed before windowing per CLAUDE.md's data
discipline. Labels come from the seeded ground-truth source schedule, not from
simulator internals leaking into the model (see model-specification.md).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.domain.physics.mass_balance import Segment
from app.simulation.generator import generate_tick

STEP_MINUTES = 5
ZONE_VOLUME_M3 = 1000.0
INLET_PPM = 450.0


@dataclass(frozen=True)
class ScenarioSpec:
    scenario_id: str
    seed: int
    kind: str  # "normal" | "leak" | "ventilation_change"
    duration_hours: float = 16.0


def _control_schedule(spec: ScenarioSpec, rng: np.random.Generator) -> list[tuple[float, float, float]]:
    """Returns list of (start_minute, source_ppm_m3h, ventilation_m3h) segments."""
    n_minutes = spec.duration_hours * 60
    segments = []
    ventilation = 500.0

    if spec.kind == "normal":
        # occasional benign ventilation adjustments, no leak
        t = 0.0
        source = 0.0
        while t < n_minutes:
            dur = rng.uniform(60, 180)
            ventilation = float(rng.choice([400.0, 500.0, 600.0]))
            segments.append((t, source, ventilation))
            t += dur

    elif spec.kind == "ventilation_change":
        t = 0.0
        source = float(rng.uniform(0, 150_000))
        segments.append((t, source, 500.0))
        change_at = rng.uniform(n_minutes * 0.3, n_minutes * 0.7)
        segments.append((change_at, source, float(rng.choice([100.0, 150.0, 200.0]))))

    elif spec.kind == "leak":
        t = 0.0
        source = 0.0
        segments.append((t, source, 500.0))
        leak_start = rng.uniform(n_minutes * 0.2, n_minutes * 0.6)
        leak_rate = float(rng.uniform(1_500_000, 6_000_000))
        segments.append((leak_start, leak_rate, 500.0))

    elif spec.kind == "rapid_leak":
        # Additive kind (GRU-only; does not alter "leak"'s behavior/determinism):
        # a much later, sharper onset so a forecast cutoff can land squarely in the
        # "no precursor yet" regime -- the structural unannounced-onset case Phase 5
        # must report honestly rather than claim the GRU can predict.
        t = 0.0
        segments.append((t, 0.0, 500.0))
        leak_start = rng.uniform(n_minutes * 0.75, n_minutes * 0.9)
        leak_rate = float(rng.uniform(5_000_000, 8_000_000))
        segments.append((leak_start, leak_rate, 500.0))

    elif spec.kind == "changing_source":
        # Additive kind: several benign step changes in source (below leak-labeling
        # magnitude) so the GRU sees genuine multi-segment piecewise dynamics without
        # ever being mislabeled as a leak.
        t = 0.0
        source = float(rng.uniform(0, 50_000))
        segments.append((t, source, 500.0))
        n_changes = int(rng.integers(2, 4))
        for _ in range(n_changes):
            t += rng.uniform(n_minutes * 0.15, n_minutes * 0.25)
            if t >= n_minutes:
                break
            source = float(rng.uniform(0, 150_000))
            segments.append((t, source, 500.0))

    else:  # sensor_noise / missing_data: normal operational schedule, fault injected
        # separately in generate_scenario_dataframe via spec.kind.
        t = 0.0
        source = 0.0
        while t < n_minutes:
            dur = rng.uniform(60, 180)
            ventilation = float(rng.choice([450.0, 500.0, 550.0]))
            segments.append((t, source, ventilation))
            t += dur

    return segments


def _source_at(segments: list[tuple[float, float, float]], minute: float) -> tuple[float, float]:
    active = segments[0]
    for seg in segments:
        if seg[0] <= minute:
            active = seg
        else:
            break
    return active[1], active[2]


_KIND_SALT = {
    "normal": 1, "leak": 2, "ventilation_change": 3,
    # Additive kinds (GRU dataset only): new salts, existing ones untouched so the
    # XGBoost leak classifier's data/artifact reproducibility is unaffected.
    "rapid_leak": 4, "changing_source": 5, "sensor_noise": 6, "missing_data": 7,
}
_LEAK_LABEL_KINDS = ("leak", "rapid_leak")


def generate_scenario_dataframe(spec: ScenarioSpec) -> pd.DataFrame:
    """Returns a DataFrame with columns: minute, ppm, source_ppm_m3h, ventilation_m3h,
    leak_active_within_60m (label)."""
    # NOTE: must not use Python's built-in hash() on a string here -- it's randomized
    # per-process (PYTHONHASHSEED) unless explicitly disabled, which silently broke
    # exact run-to-run reproducibility of the generated training data.
    rng = np.random.default_rng(np.random.SeedSequence([spec.seed, _KIND_SALT[spec.kind]]))
    segments = _control_schedule(spec, rng)

    n_points = int(spec.duration_hours * 60 / STEP_MINUTES)

    # sensor_noise / missing_data inject a fault on a deterministic subset of ticks
    # (never on "leak"-family kinds, so the leak classifier's data is unaffected).
    fault_ticks: set[int] = set()
    fault_kind = None
    if spec.kind == "sensor_noise":
        fault_kind = "NOISY"
        fault_ticks = set(rng.choice(n_points, size=int(n_points * 0.15), replace=False).tolist())
    elif spec.kind == "missing_data":
        fault_kind = "STUCK"  # generator has no "drop the reading" fault; STUCK is the
        # closest existing primitive (a stale/frozen reading) -- the resulting rows are
        # marked missing=1 below so the GRU still sees them as an imputed/low-quality tick.
        fault_ticks = set(rng.choice(n_points, size=int(n_points * 0.08), replace=False).tolist())

    rows = []
    true_ppm = INLET_PPM
    for i in range(n_points):
        minute = i * STEP_MINUTES
        source, ventilation = _source_at(segments, minute)
        seg = Segment(volume_m3=ZONE_VOLUME_M3, inlet_ppm=INLET_PPM, ventilation_m3h=ventilation, source_ppm_m3h=source, duration_hours=STEP_MINUTES / 60.0)
        fault = fault_kind if i in fault_ticks else None
        result = generate_tick(spec.seed, i, seg, true_ppm, fault)
        true_ppm = result.true_ppm
        rows.append({
            "minute": minute, "ppm": result.observed_ppm, "source_ppm_m3h": source, "ventilation_m3h": ventilation,
            "missing": 1 if i in fault_ticks else 0,
        })

    df = pd.DataFrame(rows)

    # Label: leak_active_within_60m -- positive if source becomes/is abnormal for
    # "leak"-family scenarios; every other kind is always negative, since those are
    # exactly the operational transients/faults the classifier must NOT flag.
    df["leak_active_within_60m"] = 0
    if spec.kind in _LEAK_LABEL_KINDS:
        future_minutes = 60
        leak_minutes = [m for m, s, _ in segments if s > 0]
        if leak_minutes:
            leak_start_minute = min(leak_minutes)
            df.loc[df["minute"] >= leak_start_minute - future_minutes, "leak_active_within_60m"] = 1
            df.loc[df["minute"] >= leak_start_minute, "leak_active_within_60m"] = 1
            df.loc[df["minute"] < leak_start_minute - future_minutes, "leak_active_within_60m"] = 0

    df["scenario_id"] = spec.scenario_id
    df["seed"] = spec.seed
    df["kind"] = spec.kind
    return df


def default_scenario_specs(n_per_kind: int = 40, base_seed: int = 1000) -> list[ScenarioSpec]:
    specs = []
    idx = 0
    for kind in ("normal", "leak", "ventilation_change"):
        for i in range(n_per_kind):
            specs.append(ScenarioSpec(scenario_id=f"{kind}-{i:03d}", seed=base_seed + idx, kind=kind))
            idx += 1
    return specs


def gru_scenario_specs(n_per_kind: int = 30, base_seed: int = 5000) -> list[ScenarioSpec]:
    """Broader kind mix for the GRU forecast dataset (Phase 4): adds rapid-onset
    leaks, multi-step source changes, sensor noise, and missing readings on top of
    the leak-classifier's normal/leak/ventilation_change kinds. A longer duration
    gives more windows per scenario at the 120-in/12-out cadence."""
    specs = []
    idx = 0
    kinds = ("normal", "leak", "rapid_leak", "ventilation_change", "changing_source", "sensor_noise", "missing_data")
    for kind in kinds:
        for i in range(n_per_kind):
            specs.append(ScenarioSpec(scenario_id=f"gru-{kind}-{i:03d}", seed=base_seed + idx, kind=kind, duration_hours=24.0))
            idx += 1
    return specs
