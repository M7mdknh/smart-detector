# Factory Safety Sentinel — Review Preparation

Concise, defensible answers to expected review questions, grounded in this
repository's actual code and evaluation artifacts (not generic ML
boilerplate). Cite files where useful so the author can re-derive each
answer under questioning.

## 1. Why physics+ML (not physics-only or ML-only) for forecasting?

Physics alone (`models/evaluation/physics_forecast_metrics.json`) is
transparent and always available but assumes constant `(Q, Cin, G)` over the
60-minute horizon, so it cannot anticipate a mid-window step-change and its
crossing-time error is structurally large on sudden-onset leaks. A pure ML
model with no physics prior would need far more training data to relearn
mass-balance dynamics the equations already give for free, and would degrade
less gracefully when its artifact is missing. The hybrid design
(`models/evaluation/gru_benchmark_report.json`) keeps physics as the always-
available baseline and floor for behavior, and adds a GRU **residual**
correction that measurably improves MAE by 16.8% globally with no worst-case
regression (5960.5 vs 5962.3 ppm) — while `forecast_gru.py` degrades to
physics-only, not a crash, whenever the artifact is unavailable
(`gru_status: "FALLBACK"`).

## 2. Why XGBoost for leak likelihood (not another model)?

`models/evaluation/full_evaluation_report.json`'s `leak_classifier` section
directly compares four candidates on the same held-out test set: persistence
(PR-AUC 0.22), physics-only rule (0.923), logistic regression (0.941), and
XGBoost (0.965, calibrated Brier 0.022 vs. logistic regression's 0.029).
XGBoost's actual measured edge here is calibration quality, not raw
discrimination — the synthetic scenarios are physics-driven and clearly
separable, so all learned models score well. XGBoost was chosen over a
larger model (e.g. a neural net) because it is fast enough for the 5-minute
ingestion cadence, trains in seconds without a GPU, and its explainable
feature importances (17 leakage-safe engineered features,
`app/inference/features.py`) support the explainability requirement that a
raw neural score would not.

## 3. Why GRU residuals, not absolute concentration prediction?

Predicting an absolute concentration directly would let the learned model
silently override the physics baseline even where physics is already
correct, and would remove the interpretable
`physics_ppm`/`residual_ppm`/`predicted_ppm` decomposition CLAUDE.md's
`Forecast` contract requires. Residual learning bounds what the GRU can
change — it can only correct the physics baseline, never replace it — which
is also why the safe fallback (physics-only when `gru_status != OK`) is a
one-line drop of the residual term rather than a separate code path
(`models/registry.json`'s `forecast_gru.note`: "Predicts the residual
against a cutoff-anchored physics forecast... never an unconstrained
absolute concentration").

## 4. Why is severity kept separate from model confidence?

CLAUDE.md invariant #6 states severity is consequence, not confidence.
`backend/app/domain/risk/policy.py` computes severity from current/rolling
exposure, forecast crossings, and person/PPE presence — a 99%-confident
leak-probability score with nobody in the zone and no threshold crossing
imminent is still `LOW`/no incident, while a lower-confidence detection with
a confirmed worker in the gas zone and an imminent crossing is `HIGH`
(`PERSON_IN_PREDICTED_GAS_RISK`). Conflating the two would let a
well-calibrated-but-irrelevant model score drive an alarm, or let a
genuinely dangerous but lower-confidence read get under-prioritized —
exactly the failure mode the separation is designed to prevent.

## 5. How was train/validation/test window leakage prevented?

Both learned models split by **whole scenario ID**, never by overlapping
time window, before any windowing happens. The leak classifier's split is
verified disjoint by assertion in `scripts/train_leak_model.py::split_scenarios`
(manifest: `models/evaluation/leak_model_split_manifest.json`). The GRU's
split is proven by an automated pre-training check
(`models/evaluation/gru_leakage_proof.json`), asserting: no scenario appears
in two splits, no window's feature timestamps exceed its cutoff, no
forbidden feature (`scenario_id`, `seed`, future-controls) is present, and
normalization statistics are fit on the train split only. Both artifacts'
reproducibility was independently checked by re-running training twice and
diffing the resulting SHA-256 checksums (bit-identical after fixing a
`hash()`-seeding bug — `docs/README.md` §8.1 item 7).

## 6. Behavior on sensor failure, model failure, and camera failure

- **Sensor failure** (missing/stuck/noisy readings): quality flags propagate
  into `missing_fraction_60m`/robust-slope features rather than being
  silently imputed as normal; a corroboration-less disagreement raises a
  `LOW` `SENSOR_UNRELIABLE` data-quality incident, never a fabricated safe
  reading (CLAUDE.md invariant #12).
- **Model failure** (leak classifier or GRU artifact missing/corrupt):
  `app/inference/leak_model.py` and `app/inference/forecast_gru.py` catch
  the load/inference failure, set a typed `UNAVAILABLE`/`FALLBACK` status
  surfaced on `/system/status` and the forecast payload's `model_status`/
  `gru_status`, and fall back to the rule-based / physics-only path — the
  UI shows the degraded state, not a healthy one.
- **Camera failure**: `/system/status`'s `camera` field reports the real
  vision worker's operational status (fixed bug, `docs/README.md` §8.1 item
  2 — it used to read the simulator's fault-injection input instead), and
  the dashboard's camera panel renders "Camera/model unavailable... Worker
  presence cannot be confirmed as safe from this feed" rather than a stale
  or fabricated frame — matching the `CAMERA_DEGRADED` reason code in
  CLAUDE.md's severity table.

## 7. Why doesn't the system predict an arbitrary leak with no precursor signal?

This is a structural information limit, not a tuning gap. The
`unannounced_onset_condition` row in `models/evaluation/gru_benchmark_report.json`
(1,062 of 1,092 test comparisons) covers cases where the 10-hour input
window contains no signal indicating what is about to happen — no function
of that window, physics or learned, can be expected to anticipate a genuinely
unannounced step-change. The report distinguishes this from the 30
`observable_precursor_condition` cases (residual already ≥150 ppm visible in
the last 30 minutes of input), where the hybrid model shows a larger, more
meaningful improvement (27% vs. 16.5%) — the honest reading is that the
system detects and forecasts developing conditions, not clairvoyant leaks.

## 8. Why is no_helmet detection performance weak?

`no_helmet` is the rarest class in the published Construction-PPE dataset. A
validation-split threshold sweep on the interrupted v1.0 checkpoint
(`models/evaluation/ppe_threshold_sweep_v1.0.json`) showed recall plateaued
at 0.237 across every tested confidence threshold (0.05–0.40) — a model-
capacity ceiling, not a threshold problem. Resuming training to the full 60
epochs (v1.1) improved held-out test recall from 0.125 to 0.175 and
precision from 0.257 to 0.378 (`models/registry.json`), a real but partial
improvement; the class remains the weakest in the model (0.175 recall vs.
0.81–0.90 for the other three classes) because there simply isn't enough
labeled `no_helmet` data in this dataset to fully resolve it, and this
submission does not claim otherwise (`docs/README.md` §9).

## 9. Why did the natural-motion (Pexels) clip get zero PPE detections?

`models/evaluation/natural_motion_report.json`: person detection worked well
(373 detections over 360 frames, mean confidence 0.70, 3 stable track IDs),
but all three PPE classes (helmet/no_helmet/vest) came back at zero, despite
the clip showing visible PPE. This is the construction-to-factory /
domain-shift gap made concrete: the model was trained and evaluated
exclusively on the Construction-PPE dataset's framing, lighting, camera
angle, and worker clothing style; a real continuous clip from a different
source (camera distance, resolution, motion blur, PPE style) falls outside
that learned distribution for the PPE classes specifically, even though the
coarser `person` class — closer to COCO's original pretraining — generalized
fine. `docs/README.md` §9 and §7.6 report this directly rather than omitting
the stress test because it was unflattering.

## 10. How would real sensors replace the simulator in production?

The ingestion contract is the seam: `POST /api/v1/sensor-readings` accepts a
versioned `SensorReadingIn` payload (`schema_version`, `sensor_id`,
`zone_id`, `gas`, `value`, `unit`, `event_time`, `source`, `quality`) and is
idempotent by `reading_id` (`app/services/ingestion.py::ingest_reading`).
CLAUDE.md invariant #1 requires the simulator, replay, and any future device
to use this **same** path — a real CO2 sensor's driver would just need to
POST to this endpoint with `source` set to something other than
`SIMULATOR`/`REPLAY`. No downstream code (physics, ML, risk policy)
branches on where a reading came from.

## 11. What would need to change to support another gas or another camera?

**Another gas**: CLAUDE.md invariant #9 requires thresholds/units/exposure
windows/actions to come from a versioned gas profile — currently the NIOSH
CO2 profile lives as named fields on `Settings`
(`backend/app/settings.py`: `niosh_twa_ppm`, `niosh_short_term_ppm`,
`niosh_idlh_ppm`, `internal_ventilation_advisory_ppm`,
`niosh_profile_version`). Adding CO (the specified P1 gas) means adding a
second profile object keyed by gas type rather than more scalar settings,
plus extending `risk/policy.py`'s severity table and the leak-classifier's
per-gas feature engineering — the physics equation itself
(`dC/dt = Q/V*(Cin-C) + G/V`) is already gas-agnostic. **Another camera**:
`backend/app/inference/zone_config.py` already loads versioned,
independent-of-resolution normalized zone polygons from `zone_config.json`
keyed by `camera_id` — adding a camera means adding a `ZoneConfig` entry and
a `VisionWorker` instance pointed at the new feed; the association/dwell
logic (`vision_worker_impl.py`) is not camera-specific.

## 12. What are the production deployment requirements?

Per `docs/README.md` §10: (1) fine-tune/evaluate vision on real or licensed
factory-representative footage, not just Construction-PPE; (2) resolve the
GRU/torch-vs-Docker-image-size tradeoff deliberately (the current Docker
image excludes torch/ultralytics entirely, running physics-fallback only);
(3) validate the mass-balance physics model against real sensor data; (4)
add horizontal scaling for the currently single-process, in-memory
WebSocket hub and background workers; (5) replace SQLite with a managed
RDBMS with connection pooling/backup; (6) add authentication/authorization
to the incident-action endpoints (currently open, appropriate only for a
credential-free demo); (7) persist per-reading historical
ventilation/source controls so the GRU's live feature window matches its
training windows exactly (currently a documented train/serve
simplification).

## 13. What is the largest security/privacy risk in this system?

The incident-action endpoints (`POST /api/v1/incidents/{id}/actions`) have
no authentication — anyone who can reach the bound host/port can
acknowledge, comment on, resolve, or reopen a safety incident. This is
explicitly scoped as acceptable for a credential-free local demo (the
server binds to `127.0.0.1` by default and CORS is an explicit allow-list,
`backend/app/settings.py`), but it is the single largest gap between this
prototype and anything handling a real facility — item 6 in the production
deployment list above. On the privacy side the design is comparatively
strong: worker identity is a session-local anonymous `track_id` reset on
tracker restart, no facial recognition, and raw camera frames are never
persisted to SQLite (only structured `VisionEvidence` rows) — so the
residual privacy risk is smaller than the access-control gap.

## 14. What is the estimated operational cost/capacity of this system?

Per `docs/README.md` §10's approximate cost profile: one small CPU-only VM
for the backend, plus one CPU or small-GPU instance if sustained ~10fps
YOLO inference is required for a live camera (the bundled replay pipeline
itself achieves ~88 fps on a laptop-class NVIDIA GeForce MX450 per
`models/evaluation/vision_model_metrics.json`'s `replay_evaluation`, so
real-time single-camera inference is not compute-heavy). SQLite is adequate
at this data volume — a few hundred MB per year of readings and events for
one workcell — but would need migration to a managed RDBMS beyond a
handful of concurrent zones/cameras, since the WebSocket hub and inference
workers are currently single-process (production requirement #4 above).

## 15. Which single design decision would you change with more time?

Persisting per-reading historical ventilation/source control values, so the
GRU's live feature window at inference time matches its training windows
exactly. Right now `forecast_service.py::_build_gru_feature_window` holds
the current run's controls constant across the full 120-step lookback
because per-tick historical control values aren't stored per reading, while
training windows use the actual historical controls — a real, acknowledged
train/serve skew (`docs/README.md` §9). It's a narrow, well-isolated fix
(add columns, backfill the window builder) that would remove the last
documented discrepancy in the forecast path, rather than a fundamental
architecture change.

---

## Live-change exercise 1: adjusting PPE dwell duration

**What to change**: the PPE-violation and zone-entry dwell thresholds are
currently plain module-level constants, not yet an externally versioned
config file:
- `backend/app/services/vision_ground_truth.py` (lines ~22–25):
  `ZONE_ENTER_SECONDS = 2.0`, `ZONE_EXIT_SECONDS = 2.0`,
  `PPE_VIOLATION_SECONDS = 3.0`, `PPE_CLEAR_SECONDS = 5.0` — used by the
  `SIMULATION_GROUND_TRUTH` evidence path.
- `backend/app/inference/vision_worker_impl.py` (lines ~81–84): the same
  four constants, used by the real `CV_MODEL` replay path.

Both must change together (or be refactored into one shared, versioned
config) since they currently duplicate the same values independently — a
genuine "versioned config" per CLAUDE.md's spirit would hoist these into
`Settings` with a `dwell_config_version` field, which has not been done yet.

**Focused test that must pass afterward**:
`backend/tests/test_vision_association.py::test_helmet_violation_requires_three_seconds_in_overhead_zone`
(and its siblings in the same file —
`test_zone_entry_requires_two_seconds_persistence`,
`test_vest_violation_after_three_seconds_no_vest_detected`,
`test_violation_clears_after_five_seconds_compliant` — all encode the exact
current threshold values and would need updating alongside the constants).

## Live-change exercise 2: adjusting the internal CO2 advisory (without touching sourced NIOSH thresholds)

**What to change**: `backend/app/settings.py`'s
`internal_ventilation_advisory_ppm: float = 1000.0` — a `Settings` field
kept explicitly separate from the sourced NIOSH fields
(`niosh_twa_ppm`, `niosh_short_term_ppm`, `niosh_idlh_ppm`,
`niosh_source_url`, `niosh_profile_version`) on the same class. Changing
only this field does not touch the CDC-sourced values or their citation.
The consuming logic is `backend/app/domain/risk/policy.py` (~line 98:
`if i.ventilation_advisory:` → `LOW` / `CO2_VENTILATION_ADVISORY`).

**Focused test that must pass afterward**:
`backend/tests/test_risk_policy.py::test_ventilation_advisory_low`.

## Diagnosis exercise (a): GRU artifact unavailable

Inspection order: (1) `models/registry.json`'s `forecast_gru` entry — confirm
`artifact_path`, `sha256`, `scaler_path`/`scaler_sha256`, and
`feature_schema_path` all point at files that actually exist and match
checksum; (2) `backend/app/inference/forecast_gru.py` — the adapter's load
path catches a missing/corrupt artifact and sets `self._status =
ModelStatus.UNAVAILABLE` (never raises past the caller); (3)
`backend/app/services/forecast_service.py` — confirms `gru_status` is set
from the adapter's status and that `combined_forecast` correctly degrades to
physics-only when it isn't `OK`; (4) the `/api/v1/system/status` and
`/api/v1/zones/{zone_id}/forecast/latest` routes
(`backend/app/api/routes.py`) — the forecast response's own `model_status`/
`gru_status` fields are the fastest live confirmation, no log-diving
required. Physics-fallback correctness itself is asserted by
`backend/tests/test_gru_train_serve_parity.py` and the promotion-criteria
checks baked into `models/evaluation/gru_benchmark_report.json`.

## Diagnosis exercise (b): dashboard stale after scenario reset

Inspection order: (1) `frontend/src/lib/useWebSocket.ts` — events are
applied strictly by `sequence` number; a gap (or first connection) triggers
`queryClient.invalidateQueries({queryKey: ["dashboard-snapshot"]})` before
trusting further events (the comment there cites "dashboard-specification.md's
reconnect rule"); (2) `frontend/src/dashboard/hooks.ts` — the
`dashboard-snapshot` query's `refetchInterval: 5000` REST poll is the
fallback if the WebSocket path misses something; (3) backend side,
`backend/app/api/routes.py`'s `/dashboard/snapshot` and
`/zones/{zone_id}/readings` handlers, and
`incident_service._latest_vision_rows` — all three were previously fixed
(`docs/README.md` §8.1 item 3) to scope by `scenario_id` **and** an
`event_time <= run.event_time` upper bound, because reloading the same
seeded preset reuses the same `scenario_id`; a regression here is the first
place to check with
`backend/tests/test_dashboard_snapshot_scoping.py`'s two tests as the
executable spec of correct behavior.
