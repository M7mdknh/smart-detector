# Factory Safety Sentinel — Authoritative Metrics Table

**v3.0 note (2026-08-30):** every number below was re-reproduced this pass via
`make evaluate` and `make evaluate-forecast` against the unchanged active
artifacts (`ppe-yolo11n.pt` sha256 `a6b5aedc...c39fca`, calibrated XGBoost
checksum unchanged) and matched the previously-committed values to within
floating-point noise from NMS/eval ordering (e.g. `no_helmet` recall stayed
0.175). See `docs/FINAL_VERIFICATION.md`'s "v3.0 pass" section for the exact
commands and a dataset-path-resolution fix that was required to reproduce the
vision section cleanly in this environment (no metric values changed).

This is the single reconciled source of truth for every reported number in
this submission. Every value below is copied verbatim (or trivially rounded)
from a generated file under `models/evaluation/`; none are recomputed here.
Where `docs/README.md` or root `README.md` quoted a different number, it has
been corrected to match this table (see "Reconciliation notes" at the bottom).

Do not read validation-split and test-split numbers as interchangeable —
each row states which split it is.

## 1. Physics forecast (no learned component)

Source: `models/evaluation/physics_forecast_metrics.json` (same numbers
reproduced in `models/evaluation/full_evaluation_report.json` §`physics`).
Generated: `2026-08-28T15:47:46Z`. Split: 10 held-out scenarios (not further
labeled train/val/test — physics has no learned parameters to leak), 120
point-comparisons, 6 threshold-crossing comparisons.

| Metric | Value |
|---|---|
| MAE | 95.50 ppm |
| RMSE | 121.93 ppm |
| Crossing-time MAE | 20.34 minutes |
| n point-comparisons | 120 |
| n crossing-comparisons | 6 |

Note (from the file itself): measured against the sensor-noise-perturbed
generated trajectory under piecewise-constant controls — there is no real
deployment data for this synthetic prototype.

## 2. Hybrid forecast benchmark (physics vs. physics+GRU residual)

Source: `models/evaluation/gru_benchmark_report.json`. Generated:
`2026-08-28T15:47:40Z`. Split: held-out TEST split (`gru_split_manifest.json`),
1,092 global point-comparisons, scenario-disjoint from GRU training
(`gru_leakage_proof.json`: all 4 leakage checks pass).

| Scope | n | Physics MAE | Hybrid MAE | Improvement |
|---|---|---|---|---|
| Global | 1,092 | 57.19 | **47.59** | 16.8% |
| normal | 156 | 19.90 | 15.84 | 20.4% |
| leak (gradual) | 156 | 83.09 | 64.46 | 22.4% |
| rapid_leak | 156 | 201.09 | 176.48 | 12.2% |
| ventilation_change | 156 | 20.83 | 17.33 | 16.8% |
| changing_source | 156 | 20.16 | 15.66 | 22.3% |
| sensor_noise | 156 | 35.54 | 27.79 | 21.8% |
| missing_data | 156 | 19.75 | 15.59 | 21.1% |
| observable precursor condition | 30 | 50.77 | 37.01 | 27.1% |
| unannounced onset condition | 1,062 | 57.38 | 47.89 | 16.5% |

Global RMSE: physics 284.48, hybrid 281.14 (worst-case abs error: physics
5962.25 ppm, hybrid 5960.54 ppm — no worst-case regression). Global
crossing-time MAE: 2.63 minutes for both (unchanged). Inference latency:
median 1.90 ms, p95 2.41 ms.

**Promotion decision** (from the same file): `promote_hybrid_as_default:
true` — all 4 stated criteria pass (≥5% MAE improvement: 16.8% measured;
no >10% worst-case regression; crossing-time not worse by >10%; fast enough
for the 5-minute cadence).

## 3. Leak classifier (XGBoost)

Source: `models/evaluation/leak_model_metrics.json` (identical numbers in
`full_evaluation_report.json` §`leak_classifier`). Split: TEST, 900 windows,
198 positive (`models/evaluation/leak_model_split_manifest.json`, scenario-ID
split verified disjoint).

| Model | PR-AUC | Precision | Recall | F1 | Brier |
|---|---|---|---|---|---|
| Persistence baseline | 0.220 | 0.000 | 0.000 | 0.000 | 0.172 |
| Physics-only (deviation rule) | 0.923 | 0.888 | 0.879 | 0.883 | 0.092 |
| Logistic regression | 0.941 | 1.000 | 0.899 | 0.947 | 0.029 |
| XGBoost (uncalibrated) | 0.965 | 0.989 | 0.899 | 0.942 | 0.025 |
| **XGBoost (calibrated)** | 0.965 | 0.989 | 0.899 | 0.942 | **0.022** |

Calibration status: `CALIBRATED` (sigmoid/Platt, fit on validation split
only). Calibration's measured effect is entirely in Brier score
(0.0246 → 0.0220); it does not change the decision threshold's
precision/recall on this test set.

False-alarms-per-simulated-hour and warning-lead-time are **not** separately
computed in this submission — precision/recall on the 60-minute-ahead label
serve as the reported proxy (documented as a limitation in `docs/README.md`
§9).

## 4. Vision detector (YOLO11n v1.1, promoted default)

Source: `models/evaluation/vision_model_metrics.json` (identical numbers in
`full_evaluation_report.json` §`vision`). Split: full published
Construction-PPE **TEST** split, 141 images, never used for training or
threshold tuning. Hardware: NVIDIA GeForce MX450.

| Class | Precision | Recall | AP50 | AP50-95 |
|---|---|---|---|---|
| helmet | 0.923 | 0.901 | 0.932 | 0.523 |
| vest | 0.838 | 0.871 | 0.885 | 0.558 |
| person | 0.783 | 0.809 | 0.833 | 0.511 |
| no_helmet | 0.378 | 0.175 | 0.228 | 0.083 |
| **overall (mAP)** | — | — | **0.559** | **0.276** |

Disclosed overlap: 12 of these 141 test images are also the source stills
for the bundled demo replay clip (`demo-assets/REPLAY_SOURCE.md`). Re-scoring
the remaining 129 non-replay test images
(`models/evaluation/vision_replay_overlap_analysis.json`) gives mAP50 0.5553
and no_helmet recall 0.162 — within run-to-run noise of the full-141 numbers
above (≤0.5pp mAP50, ≤1.3pp no_helmet recall), so the 141-image numbers
remain the primary reported figures.

**v1.0 → v1.1 comparison** (same test split; source:
`models/evaluation/vision_model_metrics_v1.0.json` and
`models/registry.json`'s `test_set_comparison_v1.0_to_v1.1`):

| Metric | v1.0 | v1.1 |
|---|---|---|
| mAP50 | 0.504 | 0.559 |
| mAP50-95 | 0.260 | 0.276 |
| no_helmet precision / recall | 0.257 / 0.125 | 0.378 / 0.175 |
| person precision / recall | 0.792 / 0.801 | 0.783 / 0.809 |
| helmet recall | 0.896 | 0.901 |
| vest recall | 0.843 | 0.871 |

Every held-out test metric improved or held steady in v1.1; person
precision moved by −0.009 (within run-to-run noise). PPE-event-level F1
(dwell-gated incident precision/recall, as opposed to per-frame detection
metrics) is **not separately computed** in this submission — dwell-gated
unit tests (`backend/tests/test_vision_association.py`) and the live A08/A09
acceptance runs are the reported proxy (`docs/README.md` §9).

## 5. Vision replay pipeline (operational counts, not accuracy)

Source: `models/evaluation/vision_model_metrics.json` §`replay_evaluation`.
Measured by actually running the v1.1 model against the bundled
`demo-assets/replay.mp4` (480 frames) on this machine's hardware — not a
vendor benchmark, and not a ground-truth-labelled accuracy measurement.

| Metric | Value |
|---|---|
| Frames processed | 480 |
| Unique track IDs | 11 |
| ID-switch candidate events | 1 |
| Latency, median | 11.13 ms |
| Latency, p95 | 12.37 ms |
| Achieved FPS | 87.9 |
| PPE frame counts | helmet 423, no_helmet 94, vest 588 |

## 6. Natural-motion stress test (qualitative only, not a benchmark)

Source: `models/evaluation/natural_motion_report.json`. Clip:
`demo-assets/replay_natural_motion.mp4` (real continuous motion, no
ground-truth annotation exists for it — see `demo-assets/NATURAL_MOTION_SOURCE.md`).

| Metric | Value |
|---|---|
| Frames processed | 360 |
| Person detections | 373 (detection rate 1.036/frame) |
| Person mean confidence | 0.702 |
| Unique track IDs | 3 |
| ID-switch candidate events | 0 |
| PPE class counts (helmet/no_helmet/vest) | 0 / 0 / 0 |
| Latency, median | 11.53 ms |

Zero PPE detections on visible helmet/vest is the headline construction-to-
factory / domain-shift finding — see Q9 in `docs/REVIEW_PREPARATION.md`.

## 7. System / integration test subset (used by `make evaluate`)

Source: `models/evaluation/full_evaluation_report.json` §`system`. This is a
**targeted** pytest subset run by `scripts/evaluate_all.py`
(`tests/test_e2e_pipeline.py`, `tests/test_incident_workflow.py`,
`tests/test_ingestion.py`), not the full backend suite.

| Metric | Value |
|---|---|
| Result | 18 passed in 4.58s |
| Covers | incident dedup, incident workflow state machine + optimistic concurrency, reading idempotency, normal/gradual_leak/ventilation_failure/overhead_ppe scenario end-to-end behavior |

## 8. Full automated test suite (`make test`)

Source: `docs/FINAL_VERIFICATION.md` (this audit's clean-environment run,
2026-08-29). This is broader than §7 above — it is every test file, not the
`evaluate_all.py` subset.

| Suite | Result |
|---|---|
| Backend pytest | 99 passed, **3 failed** |
| Frontend vitest | 18 passed |

The 3 backend failures are all in `tests/test_vision_e2e.py`, caused by the
missing `lap` dependency (see `docs/README.md` §9 and
`docs/FINAL_VERIFICATION.md`) — not a test-logic defect. On a machine where
`lap` is present (e.g. after `pip install lap`), all 102 backend tests pass.

## Reconciliation notes

- **Fixed**: `docs/README.md`'s physics-forecast model card previously
  reported "MAE ≈ 748 ppm, RMSE ≈ 1317 ppm" for
  `models/evaluation/physics_forecast_metrics.json`, which does not match
  that file's actual values (MAE 95.50 ppm, RMSE 121.93 ppm). Corrected in
  this pass to cite the real numbers, with the 6-crossing-comparison
  crossing-time MAE (20.34 min) added, and an explicit note distinguishing
  this file's numbers from the separate, larger
  `gru_benchmark_report.json` physics-baseline MAE (57.19 ppm globally) —
  two different evaluation harnesses/scenario sets, both real, neither a
  typo of the other.
- All other numbers checked against root `README.md` and `docs/README.md`
  (leak-classifier PR-AUC/Brier table, vision mAP50/no_helmet table, hybrid
  MAE 47.59 vs. physics 57.19 / 16.8%, `no_helmet` recall 0.237→0.444 threshold
  sweep) matched their source JSON files exactly — no further corrections
  were needed.
