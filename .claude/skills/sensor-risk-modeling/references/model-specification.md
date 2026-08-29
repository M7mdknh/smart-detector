# Sensor Model Specification

Read this reference for physics, feature engineering, training, artifacts, inference, thresholds, or the optional residual GRU.

## P0 Processing Chain

```text
reading validation
  -> canonical units and quality
  -> rolling exposure/features
  -> physics forecast and crossings
  -> calibrated XGBoost leak probability
  -> deterministic risk evidence
```

No learned model blocks immediate threshold/exposure evaluation.

## Sampling and Windows

- Canonical cadence: five simulated minutes.
- Warm-start/lookback: ten hours = 120 points.
- Forecast horizon: one hour = 12 points.
- Interpolate only a single missing interval for feature computation and label it imputed.
- Two or more consecutive missing points produce `INSUFFICIENT_DATA` for learned inference while physics continues from the most recent valid point.
- Split whole scenario IDs/seeds 70%/15%/15% into train/validation/test before creating overlapping windows.
- Keep all windows from a scenario in exactly one split.

## Physics Forecast

Closed form is allowed only for constant `Q`, `Cin`, and `G` over a forecast segment. Otherwise use piecewise integration with a maximum five-minute step. Clamp only physically impossible negative numerical noise to zero; do not hide invalid inputs.

Return for each five-minute horizon point:

- `physics_ppm`;
- optional `residual_ppm`;
- `predicted_ppm = max(0, physics_ppm + residual_ppm)`;
- optional interval bounds;
- assumptions active for that segment.

Calculate each configured crossing independently. If concentration is falling, do not report a future rising crossing. Validate the analytic crossing against numerical evaluation in tests.

## Exposure Calculations

- TWA: time-weighted average over the available rolling eight-hour window; mark `PARTIAL_WINDOW` until eight hours exist.
- Short-term: rolling 15-minute mean from time-weighted samples.
- IDLH: current measurement and physics forecast crossing.
- Optional 1000 ppm: internal ventilation advisory only, not a regulatory or acute threshold.

The default CO2 occupational profile is NIOSH TWA 5000 ppm, ST 30000 ppm, and IDLH 40000 ppm. Store source and profile version.

## XGBoost Leak Classifier

### Target

Binary label `leak_active_within_60m`: positive when the seeded ground-truth emission source is or becomes abnormal within the next 60 simulated minutes. Do not label ordinary ventilation or machine changes as leaks. Store the label-generation version.

### Feature vector at cutoff time

Use only data at or before the cutoff:

1. current CO2 ppm;
2. change over 5, 15, and 30 minutes;
3. robust linear slope over 15, 30, and 60 minutes;
4. rolling mean and standard deviation over 15, 30, and 60 minutes;
5. deviation from the no-leak physics expectation;
6. configured ventilation flow and its 30-minute change;
7. known machine/valve state when available;
8. fraction of missing/imputed readings in 60 minutes;
9. sensor disagreement and quality flags;
10. hour within the simulated scenario only if operational schedules actually exist.

Do not include scenario ID, seed, future control state, future readings, incident severity, or simulator leak flag as a feature.

### Initial reproducible configuration

```text
XGBClassifier(
  n_estimators=200,
  max_depth=3,
  learning_rate=0.05,
  min_child_weight=2,
  subsample=0.8,
  colsample_bytree=0.8,
  reg_lambda=1.0,
  objective="binary:logistic",
  eval_metric="logloss",
  random_state=42,
  n_jobs=1
)
```

Calculate `scale_pos_weight` from the training split only. Use validation-scenario early stopping. Calibrate the final classifier on a disjoint validation subset with sigmoid/Platt calibration; do not calibrate on the test set. If the calibration subset is too small, report the limitation and use uncalibrated probability with a distinct status.

Default interpretation, configurable after validation:

- `< 0.40`: `NO_LEAK_SIGNAL`;
- `0.40–0.69`: `SUSPICIOUS_TREND`;
- `>= 0.70`: `LIKELY_LEAK`.

Probability affects incident confidence/evidence, not severity by itself.

### Rule fallback

Return `SUSPICIOUS_TREND` when a robust 30-minute slope exceeds the configured slope threshold and the observed rise is inconsistent with the known no-leak physics baseline. Require persistence for three readings. Store the exact feature values and rule version.

## Optional P1 Residual GRU

The GRU predicts errors in the physics forecast, never the entire process unconstrained.

- Input: `(batch, 120, feature_count)`.
- Features: normalized CO2, physics one-step expectation, residual, ventilation, source/machine state when known, and missing-quality mask.
- Architecture: one GRU layer, hidden size 32, followed by a linear head producing 12 residual ppm values.
- Dropout: 0 for the single-layer model.
- Loss: Huber loss over valid future points.
- Optimizer: AdamW, learning rate `1e-3`, weight decay `1e-4`.
- Batch size: 64; maximum 100 epochs; early stop after 10 validation epochs without improvement.
- Gradient clipping: norm 1.0; seed 42; deterministic settings documented.
- Standardization statistics come from training scenarios only and are stored with the artifact.
- Prediction bounds: calculate 5th/95th percentiles of validation residual error by horizon; do not invent neural confidence.

Use the GRU only if it improves held-out threshold-time error and RMSE over physics alone without unacceptable worst-scenario regression. Otherwise ship physics-only and document the negative result.

## Artifact Contract

`models/registry.json` contains:

- logical name and semantic version;
- SHA-256 and relative artifact path;
- library versions and Python version;
- feature schema/order and preprocessing version;
- training generator/data version and split manifest;
- calibration version and decision thresholds;
- metric-report path and creation time.

Startup validates the artifact and feature schema. Mismatch or load failure sets `MODEL_UNAVAILABLE`, logs one structured error, and uses fallback.

## Evaluation Gates

Always compare persistence, physics-only, logistic regression, uncalibrated XGBoost, and calibrated XGBoost. Report PR-AUC, precision, recall, F1, Brier score, false alarms/simulated hour, median warning lead time, and confusion by scenario type. Also report physics MAE/RMSE and crossing-time error.

Do not claim universal numeric success targets before observing class balance. The submission must declare chosen operating thresholds and explain the miss/false-alarm tradeoff.
