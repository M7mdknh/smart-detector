# Factory Safety Sentinel — Speaker Notes

For a 12–15 minute presentation + Q&A. One slide is roughly 40–50 seconds of talking, leaving room for the review-preparation Q&A appendix at the end. Every "Evidence" line points to a real repository file or a session-verified result — nothing here is invented for the deck.

## 1. Title

**Say:** This is Factory Safety Sentinel — a prototype that predicts gas risk before it becomes dangerous and watches worker PPE/zone compliance in real time, both feeding one incident and review workflow a manager actually uses.

**Evidence:** Hero image is the real, live dashboard captured this session (docs/screenshots/final/01_dashboard_normal_state.png).

**Transition:** Let's start with the problem this solves.

**Likely assessor question:** Is this a finished commercial product?

**Short answer:** No — it's an assessment prototype with a fully working backend/frontend/tests, explicitly not certified for real safety decisions (stated on this slide and throughout).

## 2. Industrial Safety Problem

**Say:** Four real gaps: gradual leaks outrun human attention, PPE violations go unnoticed, restricted zones can't be watched continuously, and today's tools don't unify sensor, camera, and incident data into one place.

**Evidence:** Framed against the actual dashboard screenshot, not a stock photo — this is what the unified view looks like.

**Transition:** Here's how the assessment brief maps onto what was actually built.

**Likely assessor question:** Isn't this solved already by existing SCADA/BMS systems?

**Short answer:** Those systems are usually threshold-only and reactive; this prototype adds predictive forecasting (physics+ML) and vision-based PPE/zone supervision on top, unified in one incident workflow — the gap being addressed, not a claim no monitoring exists at all.

## 3. Scope & Assessment Alignment

**Say:** Everything in the left column is real and working today; the right column is explicitly out of scope for an assessment prototype and reserved for a certified deployment.

**Evidence:** This split is stated directly in the project's own CLAUDE.md scope document, not asserted only in this deck.

**Transition:** Now the architecture that delivers the left column.

**Likely assessor question:** Why defer multi-camera/multi-worker instead of building it?

**Short answer:** The assessment's P0 scope is one workcell/camera/gas-zone end-to-end and fully tested, rather than partial multi-entity support — CLAUDE.md's own frozen-scope decision, to keep the vertical slice complete and defensible.

## 4. Complete Solution Overview

**Say:** Two parallel evidence streams — gas sensors and camera — both terminate in one deterministic risk/incident policy, which writes to the database and pushes live WebSocket updates to the dashboard and simulation UI.

**Evidence:** Matches the actual module layout (backend/app/services/pipeline.py, backend/app/inference/, backend/app/domain/risk/policy.py) — not a conceptual sketch.

**Transition:** Let's look at exactly which of these boxes are trained models versus deterministic logic.

**Likely assessor question:** Is this a microservices architecture?

**Short answer:** No — deliberately a modular monolith (one FastAPI process) with replaceable Python adapters, per CLAUDE.md; simpler to run, test, and reason about for this scope.

## 5. Number and Roles of Models

**Say:** Exactly three trained ML models plus one analytical physics model, confirmed against the model registry — everything else, including ByteTrack and the zone/severity logic, is deterministic by design so the system stays explainable and auditable.

**Evidence:** models/registry.json lists exactly three trained artifacts (leak_classifier, ppe_detector, forecast_gru); CLAUDE.md's Frozen Models table independently confirms the same breakdown.

**Transition:** Here's why each of the three trained models was chosen specifically.

**Likely assessor question:** Why not make the risk policy itself a learned model?

**Short answer:** Explainability and auditability — CLAUDE.md invariant #6 requires severity to be deterministic and separate from raw model confidence, so every incident's reason codes are traceable to a versioned rule, not an opaque score.

## 6. Sensor and Risk Pipeline

**Say:** This is the full sensor path: real readings feed a 10-hour sliding window, the physics model projects forward, the GRU corrects its residual error, the classifier estimates leak probability, and a deterministic policy turns that into a severity with a Time-to-Action estimate.

**Evidence:** Runs every tick against real ingested readings, not a one-shot batch job — backend/app/services/pipeline.py::run_risk_pipeline.

**Transition:** The physics behind that forecast is worth showing explicitly.

**Likely assessor question:** What happens if the GRU model artifact is missing?

**Short answer:** It falls back to physics-only forecasting automatically (CLAUDE.md's safe-fallback invariant) — never crashes, never fabricates a number; shown live in the gru_benchmark_report.json fallback behavior.

## 7. Time-to-Action Physics

**Say:** This is genuine analytical physics, not a black box: a well-mixed mass-balance ODE, solved in closed form for the time a threshold will be crossed given the zone's current ventilation and source rate.

**Evidence:** backend/app/domain/forecast physics module implements exactly these closed-form equations; unit-tested against analytical and numerical cases.

**Transition:** How well does the ML layer improve on physics alone?

**Likely assessor question:** Why is it called Time-to-Action and not time-to-harm?

**Short answer:** The 5000ppm NIOSH reference is an 8-hour occupational action level, not an acute-harm threshold — CLAUDE.md is explicit that conflating the two would be misleading, so the system's own language avoids it.

## 8. Predictive-Model Performance

**Say:** On the exact same held-out points, the GRU residual correction cuts physics-only error by 16.8 percent, from 57.19 to 47.59 ppm MAE. The leak classifier separately reaches 0.965 PR-AUC, well-calibrated after Platt scaling.

**Evidence:** Both numbers pulled and asserted programmatically from gru_benchmark_report.json and leak_model_metrics.json — printed and verified at slide-build time.

**Transition:** Now the vision side: how the system watches PPE and zones.

**Likely assessor question:** Why do you separate the two physics MAE numbers so carefully?

**Short answer:** They're evaluated on different held-out sets (1092 matched points vs. 120 points across 10 scenarios) — comparing them directly would overstate or understate the GRU's real contribution, so the deck keeps them explicitly separate.

## 9. Computer-Vision Design

**Say:** Detection, tracking, PPE dwell, and zone dwell are all real, timestamp-based state machines, not single-frame heuristics — and every burned-in field on this evidence frame, boxes, confidence, model version, is genuinely produced by the pipeline, not composited afterward.

**Evidence:** This exact frame is a real captured evidence image from this session's interview-demo run, is_real_camera_frame=true in the database.

**Transition:** How the detector itself was trained and evaluated comes next.

**Likely assessor question:** Why person-box bottom-center for zone membership instead of the whole box?

**Short answer:** It approximates where the worker is actually standing on the floor plane — using the full bounding box would falsely flag a zone entry as soon as any part of a tall person's box overlapped it.

## 10. Vision Data & Enhancement

**Say:** A genuine second attempt was made to fix the known no_helmet weakness with more data — but the resulting candidate, evaluated honestly against a mechanical promotion gate, failed and was rejected. v1.1 stayed active. That negative result is fully recorded, not hidden.

**Evidence:** models/registry.json's ppe_detector.rejected_experiments entry and models/evaluation/vision_v1.2_comparative_evaluation.json are the source of the table on this slide.

**Transition:** Here's what the currently active model actually achieves.

**Likely assessor question:** If it failed, why show it in the presentation?

**Short answer:** It demonstrates the promotion-gate discipline working as designed — a real engineering process that can say no, which is more credible than only showing successes.

## 11. Vision Performance

**Say:** Helmet and vest detection are strong — over 0.90 and 0.87 AP50. no_helmet remains the honest weak point, both on the held-out benchmark and, more strikingly, on real interview footage where it never fires at the registered threshold — a real domain-gap finding, not swept under the rug.

**Evidence:** Per-class table and mAP figures are read directly from vision_model_metrics.json; the real-clip numbers from this session's interview_video_detection_summary.json.

**Transition:** Here is what all of this looks like assembled into the manager's dashboard.

**Likely assessor question:** Given no_helmet's weakness, does the system ever catch missing helmets at all?

**Short answer:** Yes — via a second, independent policy path: "no positive helmet evidence while a worker is in the overhead-work zone" still triggers a violation, demonstrated live in this session's interview-demo incidents, even when the no_helmet class itself stays silent.

## 12. Manager Dashboard

**Say:** This is the real running dashboard mid-incident: three active alerts, a rising forecast band, and live camera detections all on one screen — every value here comes from the backend, never invented client-side.

**Evidence:** Real screenshot captured this session while a gradual_leak scenario and the interview-demo video were both actually running.

**Transition:** Let's look at three real safety events this system actually caught.

**Likely assessor question:** Does the dashboard poll or use live push updates?

**Short answer:** Both — WebSocket events push live changes, with REST polling (5s) and a fresh REST snapshot on reconnect as the fallback/resync path, so state never silently goes stale.

## 13. Real Safety Incidents

**Say:** Three real, distinct incident types fired from the same interview video during live testing: compliant PPE producing no alert, a helmet violation, and a restricted-zone intrusion — each with its own genuine captured frame.

**Evidence:** All three evidence JPEGs are committed under docs/screenshots/final/evidence_*.jpg, copied from backend/data/incident-evidence/ with is_real_camera_frame=true confirmed in the JSON report.

**Transition:** These all ran without a physical factory — here's the digital twin that makes that possible.

**Likely assessor question:** Could these three incidents have been staged/cherry-picked?

**Short answer:** They were the incidents that genuinely fired during make interview-demo runs this session, verified via the real API before any screenshot was taken — not hand-selected from a larger pool of attempts.

## 14. Simulation / Digital Twin

**Say:** The simulation isn't a toy — it's the same ingestion contract and risk pipeline a real device would use, which is exactly why it's valid engineering testing: every scenario is seeded and reproducible, and the automated tests run against it directly.

**Evidence:** Three real screenshots of the actual Three.js simulation page, captured live this session.

**Transition:** Let's walk the full real sequence end-to-end.

**Likely assessor question:** Isn't a simulator just avoiding the hard problem of real hardware?

**Short answer:** It's the standard approach for testing safety-critical logic before hardware exists — CLAUDE.md invariant #1 (one ingestion path) means swapping in a real device later requires zero backend changes, only a new adapter.

## 15. End-to-End Demonstration

**Say:** This exact seven-step sequence is what ran live this session — real video in, real detection, a real deterministic decision, a real database row, a real evidence frame, a real human review action, and a real downloadable report.

**Evidence:** Every step corresponds 1:1 to a verified API call or database write from this session's interview-demo runs, not a conceptual sequence diagram.

**Transition:** Here's how that's proven by the test suite, not just a demo.

**Likely assessor question:** Is the GitHub link live right now?

**Short answer:** It's the planned repository URL for this submission; a later publication step verifies and updates the final link.

## 16. Testing & Acceptance

**Say:** 173 backend tests and 18 frontend tests pass right now — re-run at the time this deck was built, not copied from an old report — plus both Playwright e2e suites and a documented acceptance matrix with zero failures.

**Evidence:** Test counts were re-executed via pytest and vitest immediately before building this slide; the acceptance matrix is docs/ACCEPTANCE_RESULTS.md, dated and cross-referenced.

**Transition:** No system is without limitations — here they are, stated directly.

**Likely assessor question:** What exactly are the "PASS WITH LIMITATION" items?

**Short answer:** Mainly a sandbox disk-quota constraint that prevented a second from-scratch vision-dependency install in one audit pass, and the intentional schematic-vs-real evidence-image distinction — both disclosed, neither a functional defect.

## 17. Limitations & Responsible Use

**Say:** These are stated plainly because they are true, not because the system failed — a prototype that hides its limitations is less trustworthy than one that measures and discloses them.

**Evidence:** Every point here traces to a specific evaluation finding or an explicit CLAUDE.md invariant, not a generic disclaimer list.

**Transition:** Bringing it together: what this system is actually worth.

**Likely assessor question:** What's the single biggest limitation for real deployment?

**Short answer:** The domain gap — a construction-site-trained detector applied to a real factory floor needs re-evaluation and likely fine-tuning on real factory footage before any safety-relevant claim would be trustworthy.

## 18. Value and Conclusion

**Say:** Factory Safety Sentinel proves the full loop — predict, detect, decide, evidence, review — works end to end, is genuinely tested, and is built so the next step to real hardware is an adapter, not a rewrite. Thank you — happy to take questions.

**Evidence:** Every claim on this slide has been shown with a real screenshot, metric, or test result earlier in the deck.

**Transition:** (End of presentation — open floor for questions.)

**Likely assessor question:** What would you build next with more time?

**Short answer:** Domain-adapted vision fine-tuning on real factory footage and a second gas profile (CO), per the project's own documented P1 roadmap.

---

# Review Preparation — Additional Likely Questions

These are broader than the per-slide Q&A above — the kind of follow-up an assessor asks after the main deck. Each answer is grounded in a real repository decision, not an improvised justification.

**Why GRU instead of LSTM?**
A GRU has fewer parameters and gates than an LSTM, which matters for a small residual-correction model trained on a modest synthetic dataset — less capacity to overfit, faster to train and run (median 1.90ms inference), and residual correction is a simpler target than raw sequence generation, where LSTM's extra gating buys little. The architecture choice is documented in `models/evaluation/gru_training_config.json`.

**Why physics plus ML instead of ML alone?**
Two reasons: safety and interpretability. The physics model is a guaranteed fallback (CLAUDE.md's safe-fallback invariant) — if the GRU artifact is missing or corrupted, the system still forecasts, just without the residual correction, rather than going dark. It's also physically grounded (a real mass-balance ODE), so its output is explainable to a manager in a way a pure black-box forecaster's would not be. The GRU only ever learns the *residual* on top of it, never replaces it.

**Why XGBoost for the leak classifier?**
Tabular, structured sensor features (rolling means/stds, slopes, deviation from physics prediction) are exactly XGBoost's strength — it reliably outperforms plain logistic regression on this kind of engineered feature set (0.965 vs. 0.941 PR-AUC in `leak_model_metrics.json`) while remaining fast enough for real-time use and easy to calibrate (Platt scaling brought Brier score down to 0.022).

**Why YOLO11n specifically?**
It's the newest Ultralytics single-stage detector at the time of this project, tuned for a strong accuracy/speed tradeoff at the "n" (nano) size — appropriate for the target hardware (an NVIDIA MX450, a modest laptop GPU) where the system needs to sustain real-time inference (88 FPS achieved in this project's own evaluation) without a data-center GPU.

**Why not use the hosted Roboflow model instead of self-training?**
A hosted third-party inference endpoint would violate this project's "no fake CV" and reproducibility invariants — the exact model version, weights checksum, and training data must be owned and auditable, and evaluation needs to run against a fixed, versioned artifact under the team's control, not a black-box API that could change without notice. Fine-tuning locally also keeps the system runnable fully offline.

**How do restricted zones work?**
They're configured polygons in normalized camera coordinates (`backend/app/inference/zone_config.json`), not a learned class. Each tracked person's bounding-box bottom-center ("foot point") is tested against the polygon every frame; a 2-second enter/exit debounce prevents flicker from momentary detection noise, and a `PERSON_IN_RESTRICTED_ZONE` incident only opens once that dwell threshold is met.

**How was data leakage prevented?**
Exact-duplicate and near-duplicate (perceptual hash, scene-grouped) checks were run across train/val/test splits before any training (`models/evaluation/vision_v1.2_leakage_check.json`), and the training subset selection explicitly capped near-duplicate video-frame clusters rather than treating augmented/consecutive frames as unique scenes (`vision_v1.2_subset_selection.json`).

**Why is simulation meaningful, not just a toy?**
Because it exercises the identical ingestion → risk → incident pipeline a real device would use (CLAUDE.md invariant #1: one ingestion path for simulator, replay, and future real devices) — it's a deterministic, seeded test harness the automated test suite itself runs against, not a disconnected visualization.

**What happens when a model is missing?**
Every model has a defined, tested degradation path: the leak classifier and GRU forecast fall back to rule-based/physics-only behavior; the PPE detector, if its artifact is missing or its checksum doesn't match the registry, returns `ModelStatus.UNAVAILABLE` and the system reports camera/detector health as degraded — it never fabricates a "safe" reading or silently downloads a substitute model from the network.

**What are the ethical implications of worker monitoring?**
Tracking is anonymous and session-local (ByteTrack IDs reset with the session, no facial recognition, no persistent worker identity). Evidence frames do contain worker imagery, so a real deployment would need an explicit retention and access policy — this is called out directly in the Limitations slide rather than left implicit.

**Is this production-certified?**
No — stated explicitly on the title slide, the scope slide, and the limitations slide. It's an assessment prototype: fully functional and tested within its declared scope, but not validated against any regulatory or industrial safety-certification standard, and not trained on real factory deployment data.
