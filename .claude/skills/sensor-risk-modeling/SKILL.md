---
name: sensor-risk-modeling
description: Implement or evaluate gas simulation, sensor quality, leak prediction, concentration forecasting, time-to-action, uncertainty, or physics/ML fusion for Factory Safety Sentinel. Use for sensor and time-series work, not computer vision.
---

# Sensor Risk Modeling

Read the sensor, forecasting, provenance, and evaluation rules in `CLAUDE.md` first. Read [model specification](references/model-specification.md) when implementing features, training, inference, artifacts, exposure windows, or the P1 GRU.

## Model Layers

Maintain distinct layers:

1. sensor validation and quality state;
2. deterministic current-hazard thresholds;
3. well-mixed-zone physics forecast;
4. learned leak probability or residual forecast;
5. calibrated time-to-action and incident evidence.

Never make an ML model the only path for an immediate safety threshold.

## Physics

Use the configured gas profile and zone parameters:

```text
dC/dt = Q/V * (Cin - C) + G/V
tau = V/Q
Css = Cin + G/Q
```

Use the closed-form solution only when its constant-parameter assumptions hold. Otherwise integrate piecewise/numerically. Return typed outcomes for already-crossed, no-crossing, invalid-parameter, and insufficient-data cases.

Test units and boundary conditions. Do not leak ppm, volumetric flow, mass flow, or time-unit conversions across layers.

## Learned Models

- Start with persistence, physics-only, and a simple supervised baseline.
- Implement the calibrated XGBoost configuration and leakage-safe feature schema in the model specification for P0; keep logistic regression as an evaluation baseline.
- Add the specified small residual GRU only as P1 after it beats physics on held-out scenarios.
- Avoid a pretrained foundation model unless it wins a documented comparison and remains cleanly runnable.
- Preserve the physics forecast and learned correction separately in output.

The frozen sequence target is the next 60 minutes at five-minute steps. P0 uses ten hours/120 points for features and warm start; document the relationship to process time constants.

## Data Discipline

- Generate complete seeded scenarios before windowing.
- Split scenario IDs/seeds into train, validation, and test before making overlapping windows.
- Keep normal pump/valve/ventilation transitions in every split so the model must distinguish operations from leaks.
- Include missing, stuck, drifting, noisy, delayed, and duplicate readings in resilience evaluation.
- Store generator version and parameters with each scenario.

## Uncertainty and Safety Labels

- Prefer calibrated probabilities and forecast intervals over raw neural scores.
- Report `NO_CROSSING` rather than an arbitrary large time.
- Keep warning, short-term exposure, and acute thresholds separate.
- Treat time-weighted limits with rolling exposure calculations, not instantaneous crossing.
- Call the UI value `Time-to-Action`; avoid unqualified claims of harm.

## Evaluation

Compare baselines and candidate models on held-out scenarios using MAE/RMSE, threshold-time error, interval coverage, PR-AUC, event precision/recall/F1, false alarms per simulated hour, and warning lead time. Include error analysis by scenario type and severity.

Completion requires reproducible training/evaluation scripts, versioned artifacts, declared hardware/runtime, and tests for physical edge cases.
