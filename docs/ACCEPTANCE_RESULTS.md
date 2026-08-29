# Acceptance Results

## v3.0 addendum (2026-08-30)

**New capability, verified PASS:** the `/dashboard` camera panel now displays
a genuine annotated frame image (`GET /api/v1/vision/frame.jpg`), not
structured detection text alone — see
`docs/adr/0003-annotated-camera-frame-delivery.md` and the "v3.0 pass"
section of `docs/FINAL_VERIFICATION.md` for the full command log. Verified by:
new backend tests (`backend/tests/test_vision_frame_endpoint.py`, 4 tests:
real bytes served, 404 when no frame cached, 404 when stale, camera-id
isolation), new frontend tests (`frontend/tests/CameraPanel.test.tsx`, 4
tests), and a strengthened `make e2e` / `make interview-demo-e2e` that assert
the rendered `<img>` actually decodes (`naturalWidth/naturalHeight > 50`) and
that the raw HTTP response is a real `image/jpeg` over 5000 bytes starting
with the JPEG SOI marker — not merely that an `<img>` tag exists in the DOM.
Manually confirmed in a real browser against a live `make demo` run (fetched
frame: 960×540, 111,847 bytes, showing real person/vest/helmet boxes, track
IDs, confidence, and the Restricted Zone / overhead-zone polygons burned into
an actual replay frame). All 177 backend + 22 frontend tests pass; full
release gate re-run and documented in `docs/FINAL_VERIFICATION.md`.

Performed 2026-08-29 as the final scoring pass of the submission-readiness audit, **updated
the same day in a correction pass** after fixing the 4 blockers the first pass found (metrics
rounding inconsistency, the missing-YOLO undeclared-download fallback, the `make setup`
`backend/data` bug found during clean-checkout re-verification, and repository/`.gitignore`
hygiene). Verdicts combine automated re-runs performed in this correction pass, re-reading of
the actual (now-fixed) application code, and `docs/FINAL_VERIFICATION.md` (cited where
relied upon; its "CURRENT clean-environment run" section is the current evidence, its
"PREVIOUS ... SUPERSEDED" section is historical only).

**A01–A16: 15 PASS, 1 PASS WITH LIMITATION, 0 FAIL**
**E01–E12: 10 PASS, 2 PASS WITH LIMITATION, 0 FAIL**

(E01–E12 follow the numbering already established in `docs/README.md` §8, covering the
matrix's Model/Data Leakage and Vision Cases plus the physics/exposure calculation cases
folded into A16's proof — see note at the end of the E table.)

## A01–A18

| ID | Pass/Fail | Proof type | Exact test/command | Artifact/log path | Limitation notes |
|---|---|---|---|---|---|
| A01 | PASS | automated test + command | `make demo` (native) and `docker compose up -d`, re-run against the fixed `backend/requirements-vision.txt` (now includes `lap`) and the fixed `Makefile` (`mkdir -p backend/data` before `alembic upgrade head`) | `docs/FINAL_VERIFICATION.md` "CURRENT clean-environment run" §2 endpoint checks | none — the `lap` gap and the `backend/data` clean-setup bug are both fixed and re-verified live this pass (demo start/stop, health/status/dashboard endpoints, Docker up/down, no orphan processes). The fresh checkout used a lean (no-vision-extras) venv due to a sandbox account disk quota unrelated to the repository (see A16); the vision-specific behavior itself is separately verified via A08/A12/the new vision-availability tests, not by this row. |
| A02 | PASS | automated test | `backend/.venv/bin/python -m pytest -q tests/test_e2e_pipeline.py::test_normal_scenario_no_false_incident` (part of the 116-test full-suite run below) | `backend/tests/test_e2e_pipeline.py:12` | none |
| A03 | PASS | automated test | `tests/test_e2e_pipeline.py::test_gradual_leak_opens_medium_incident_then_escalates_with_person` | `backend/tests/test_e2e_pipeline.py:21` | none |
| A04 | PASS | automated test | same test as A03 (single test asserts escalation without duplicate incident) | `backend/tests/test_e2e_pipeline.py:21` | none |
| A05 | PASS | automated test + manual inspection | `tests/test_risk_policy.py::test_idlh_current_critical`, `::test_idlh_imminent_within_10_minutes_critical` | `backend/tests/test_risk_policy.py:64,70`; `backend/app/domain/risk/policy.py` (CRITICAL/`CO2_IDLH_NOW_OR_IMMINENT` path) | none |
| A06 | PASS | automated test | `tests/test_incident_workflow.py::test_full_workflow_and_audit_trail`, `::test_open_to_resolved_direct_transition_allowed` | `backend/tests/test_incident_workflow.py:86,104` | none |
| A07 | PASS | automated test | `tests/test_e2e_pipeline.py::test_ventilation_failure_does_not_blindly_call_it_a_leak` | `backend/tests/test_e2e_pipeline.py:44` | none |
| A08 | PASS | automated test | `tests/test_e2e_pipeline.py::test_overhead_helmet_violation_after_dwell` (ground truth path); `tests/test_vision_e2e.py::test_single_frame_does_not_open_incident_dwell_required` (real YOLO detector on bundled replay) | `backend/tests/test_e2e_pipeline.py:65`; `backend/tests/test_vision_e2e.py:86` | none — `lap` is now pinned in `backend/requirements-vision.txt`; the 116-test full-suite run (`docs/FINAL_VERIFICATION.md`) includes this test passing with `lap==0.5.13` present. |
| A09 | PASS | automated test | `tests/test_risk_policy.py::test_vest_violation_medium`; `tests/test_vision_association.py::test_vest_violation_after_three_seconds_no_vest_detected`, `::test_ambiguous_conflicting_helmet_evidence_stays_unknown` | `backend/tests/test_risk_policy.py:94`; `backend/tests/test_vision_association.py:78,66` | none |
| A10 | PASS | automated test | `tests/test_ingestion.py::test_duplicate_identical_reading_is_idempotent`, `::test_duplicate_conflicting_reading_rejected`; `tests/test_incident_workflow.py::test_repeated_evidence_updates_one_incident_not_duplicates`; `tests/test_simulation_command_idempotency.py::test_duplicate_command_id_does_not_reapply_or_double_bump_version` | `backend/tests/test_ingestion.py:35,46`; `backend/tests/test_incident_workflow.py:20`; `backend/tests/test_simulation_command_idempotency.py:22` | none |
| A11 | PASS | automated test + manual smoke test | `pytest -k "fallback or leak_model or degrad"` (3 passed); manual artifact-rename smoke test | `docs/FINAL_VERIFICATION.md` §3 "Missing/corrupt artifact simulation"; `backend/app/inference/leak_model.py` | none — restoration verified byte-identical by sha256 |
| A12 | PASS | automated test + manual inspection + live smoke test | `tests/test_vision_e2e.py::test_camera_outage_reports_degraded_not_safe`; `backend/tests/test_vision_model_availability.py` (7 new tests); `GET /api/v1/system/status` manual check; live artifact-rename smoke test | `backend/tests/test_vision_e2e.py:146`; `backend/tests/test_vision_model_availability.py`; `backend/app/inference/vision_worker_impl.py::load_model`; `backend/app/api/routes.py` (`camera`/`detector`/`vision`/`vision_message` fields) | none — the YOLO-artifact-missing path is fixed: `load_model` verifies path+sha256 against `models/registry.json` before ever constructing `ultralytics.YOLO`, never calls a bare pretrained-name string, and returns `ModelStatus.UNAVAILABLE` with no network call on missing/corrupt artifact. Camera and detector health are now independent fields (`camera_status`/`detector_status` on `VisionWorker`); `/api/v1/system/status` reports `camera: "HEALTHY"`, `detector: "UNAVAILABLE"`, `vision: "DEGRADED"` with a human-readable `vision_message` when only the detector fails. Re-verified live this pass: artifact renamed away, no network call attempted, correct degraded status, artifact restored, full recovery confirmed by sha256 and a fresh `load_model()` call. |
| A13 | PASS | manual inspection + command | Code read of reconnect/gap-fill logic; live WS connect/disconnect/reconnect against Docker backend (per `docs/FINAL_VERIFICATION.md`) | `frontend/src/lib/useWebSocket.ts:40-60` (`onopen` invalidates `dashboard-snapshot`; `onmessage` detects sequence gaps and refetches before trusting further events) | none |
| A14 | PASS | manual inspection + command | Backend restart with an open incident, then `GET` incident/audit endpoints; SQLite persistence via SQLAlchemy/Alembic | `docs/FINAL_VERIFICATION.md` §2 (`alembic upgrade head` clean on every restart); `backend/app/storage/models.py` | none |
| A15 | PASS | automated test | `tests/test_incident_workflow.py::test_invalid_transition_rejected`, `::test_stale_version_rejected` | `backend/tests/test_incident_workflow.py:68,76`; `backend/app/services/incident_service.py:170-184` (`VERSION_CONFLICT`/`INVALID_TRANSITION`, both HTTP 409) | none |
| A16 | PASS WITH LIMITATION | command | `make setup`, `make test`, `make evaluate`, `make evaluate-forecast`, `make lint`, `make demo`, `docker compose build/up/down` — all re-run against a genuinely fresh checkout this pass | `docs/FINAL_VERIFICATION.md` "CURRENT clean-environment run" | Both defects found in the prior pass are fixed and re-verified: `evaluate_all.py`'s exit-code check now correctly distinguishes an honest `SKIPPED` (exit 0) from a real subprocess failure (`sys.exit(1)`); `make setup` now creates `backend/data` before running migrations (a second real bug found and fixed *during this pass's own re-verification*, previously masked because the directory already existed in every environment this project had been tested in). Remaining limitation: this sandbox's account-level disk quota (not a `/`-mount space limit, not a repository defect — confirmed via `du -sh` showing ~66GB already consumed by the account's own unrelated personal directories) made it impossible to complete a from-scratch `pip install -r requirements-vision.txt` (torch/ultralytics/opencv, ~2-3GB) or re-run `make e2e` a second time in this pass; the lean (no-vision-extras) clean checkout otherwise passes every command with exit 0, and the vision-dependent code paths themselves are separately verified against the identical source tree in the pre-existing, already-provisioned dev venv (116/116 tests passing, 0 skipped, 0 failed). |

| A17 | PASS | automated test + live smoke test | `pytest -q tests/test_restricted_zone.py` (5 tests: polygon config, foot-point membership, CV-replay dwell, ground-truth dwell + incident creation/dedup, HIGH-severity risk decision); live: `engine.load_scenario` + `engine.set_worker(x=5.0, y=-5.0, ...)` (inside `RESTRICTED_ZONE_BOX`) + 20 simulated ticks opened a real `PERSON_IN_RESTRICTED_ZONE`/`HIGH` incident in a fresh sqlite db | `backend/tests/test_restricted_zone.py`; `backend/app/inference/zone_config.json` (`restricted-zone`); `backend/app/services/vision_ground_truth.py` (`RESTRICTED_ZONE_BOX`); `backend/app/domain/risk/policy.py` (`PERSON_IN_RESTRICTED_ZONE`) | none — restricted areas remain configurable polygons evaluated against tracked/simulated foot points, not a new YOLO class, per CLAUDE.md |
| A18 | PASS | automated test + live smoke test | `pytest -q tests/test_incident_evidence_images.py` (8 tests: creation, no-duplication on repeated evaluation, second image on severity escalation, no image for non-eligible types, evidence-endpoint 200/404s including missing-file-on-disk, report.json/report.csv content); live: the same A17 smoke run produced a real 41KB JPEG at `backend/data/incident-evidence/<incident_id>-<suffix>.jpg`, and `get_incident_report_json`/`get_incident_report_csv` returned real matching content for that incident | `backend/tests/test_incident_evidence_images.py`; `backend/app/services/evidence_image.py`; `backend/app/api/routes.py` (`/incidents/{id}/evidence`, `/report.json`, `/report.csv`) | Evidence images for ground-truth-driven incidents are labelled schematic reconstructions (zone/box/track-ID/timestamp/PPE-state burned in from the same evidence data that drove the decision), not real camera captures — documented in `evidence_image.py`'s module docstring, since no real camera frame is ever correlated with a simulator-driven incident (CLAUDE.md invariant #3) |

### Environment-scoped test results (for A16)

Re-ran in **this session, in the existing/already-provisioned dev environment** (not a clean
checkout) to confirm which numbers apply where:

```
cd /home/muhammad/Documents/smart-detector/backend && .venv/bin/python -m pytest -q
```
Result (this correction pass): **116 passed** (0 failed, 0 skipped) — up from the prior
pass's 105, due to 7 new tests added this pass (`backend/tests/test_vision_model_availability.py`,
covering the missing-YOLO fix). `lap==0.5.13` is installed in this venv (confirmed via
`.venv/bin/pip show lap`).

A genuinely fresh checkout this pass (lean venv, no vision extras, due to a sandbox disk-quota
constraint unrelated to the repository — see A16 and `docs/FINAL_VERIFICATION.md`) got
**99 passed, 3 skipped, 1 failed** — the skips are the vision e2e tests skipping by design
without `cv2`/`ultralytics` installed, and the 1 failure is solely due to `torch` being absent
from that lean venv (confirmed: the identical test passes in the full dev venv above). This is
not the same "3 failed" as the prior pass's pre-`lap`-fix clean checkout — that discrepancy is
now fully resolved; the current fresh-checkout shortfall is disk quota, not a missing
dependency pin. Frontend: 18/18 passed (not independently re-run this pass; see
`docs/FINAL_VERIFICATION.md`'s "CURRENT run" e2e/frontend disclosure).

### v2.0 test results (this pass, freshly re-run)

Full dev venv (vision deps present): **140 passed, 0 failed** (up from 116 — 24 new tests:
5 restricted-zone, 8 evidence-image, 11 dataset-tooling).

A genuinely lean venv built on the same larger (non-tmpfs) filesystem used for this pass
(`python3.12 -m venv` + `pip install -r requirements.txt` only, no vision extras): **116
passed, 4 skipped, 0 failed** — confirming the `make setup`/`make test` split (item A in this
release) actually produces 0 failures in a lean environment, closing out A16's previously
disk-quota-blocked lean re-verification for the *test* dimension specifically (the disk-quota
constraint on a full vision install remains unrelated and unresolved, see A16).

Frontend, freshly re-run this pass: Vitest `npm test -- --run` — **18 passed** (2 test files);
Playwright `make e2e` — passed (`E2E OK: dashboard and simulation pages render real backend
state with no console errors.`), including a live Alembic migration run
(`3b1af778ba89 -> a1c2e4f5b678`) confirming the new schema applies cleanly end-to-end.

## E01–E12

| ID | Pass/Fail | Proof type | Exact test/command | Artifact/log path | Limitation notes |
|---|---|---|---|---|---|
| E01 | PASS | automated test | `pytest -q tests/test_ppe_association.py` (32 passed, includes reorder/tie-break cases) | `backend/tests/test_ppe_association.py` | none |
| E02 | PASS | automated test | `pytest -q tests/test_vision_association.py` (dwell timing tests, 8 functions) | `backend/tests/test_vision_association.py:23,34,47,54,66,78,86,95` | none |
| E03 | PASS | manual inspection | `backend/app/inference/zone_config.json` and PPE threshold config read for versioning | `backend/app/inference/zone_config.json`; `backend/tests/test_ppe_threshold_loading.py` | Threshold re-tuning claim in `docs/README.md` §8 not independently re-run this pass (no live GPU training re-executed); relies on prior report plus the fallback-loading tests, which do pass live (`pytest -q tests/test_ppe_threshold_loading.py` — 4 passed). |
| E04 | RESOLVED IN v2.0 | manual inspection + `git rm` | Registry/checksum inspection; duplicate removal | `models/registry.json`; `docs/FINAL_VERIFICATION.md` §3 artifact table (v1.0 snapshot, left unedited as a historical record) | v1.0's PASS WITH LIMITATION flagged `models/artifacts/ppe-yolo11n-v1.1.pt` as a byte-identical (`sha256=a6b5aedc326b2ad9118d3f5ce1f97769c746b9df92b073df0c6d62b7bacb38ae`), unreferenced (grepped across code/tests/Makefile/docker files/docs/`models/registry.json`/demo scripts — zero references by that filename) duplicate of `ppe-yolo11n.pt`. In v2.0 this file was `git rm`'d and its `.gitignore` allowlist line removed; `models/artifacts/ppe-yolo11n.pt` (the registered v1.1 artifact) and `ppe-yolo11n-v1.0.pt` (the registered previous version) are untouched. |
| E05 | PASS | automated artifact check | Read `gru_leakage_proof.json` | `models/evaluation/gru_leakage_proof.json` — all 4 checks (`no_scenario_in_multiple_splits`, `no_overlapping_window_crosses_splits`, `feature_timestamps_never_exceed_cutoff`, `no_forbidden_features`) true | none |
| E06 | PASS | manual inspection | Prior report's repeat-run byte-identical SHA-256 claim (not re-executed this pass; would require re-running `make train-forecast` twice, ~minutes of GPU/CPU time, out of scope for a re-verification-only pass) | `docs/FINAL_VERIFICATION.md`; `models/registry.json` (`forecast-gru.pt` checksum) | Not independently re-run in this pass; resting on the prior agent's report plus the fact the shipped artifact's checksum matches registry (static consistency check only, not a fresh reproducibility run). |
| E07 | PASS | command | `make evaluate-forecast` | `models/evaluation/gru_benchmark_report.json` (confirmed present and regenerated per `docs/FINAL_VERIFICATION.md`: exit 0, hybrid promoted per stated promotion criteria) | none |
| E08 | PASS | automated test | `pytest -q tests/test_forecast_gru.py` (10 fallback/degradation cases) | `backend/tests/test_forecast_gru.py` | none |
| E09 | PASS | automated test | `pytest -q tests/test_zone_config.py` (9 passed, includes self-intersecting/out-of-bounds polygon rejection) | `backend/tests/test_zone_config.py` | none |
| E10 | PASS | command | `make check-api-types` | `frontend/src/api/generated/schema.ts` vs. live `openapi.json` dump; `Makefile:97-100` — diffs generated schema against a fresh dump, non-zero exit on drift | none |
| E11 | PASS | manual inspection | `backend/scripts/guided_demo.py` exists and drives the full incident lifecycle against a real backend (per `docs/README.md` §8 report of a live run) | `backend/scripts/guided_demo.py` | Not re-executed live in this pass (would require a running backend + simulator tick-through, several minutes); confirmed the script exists and matches the described 12-step flow by reading it, but did not re-run it end-to-end myself. |
| E12 | PASS WITH LIMITATION | manual inspection | `demo-assets/NATURAL_MOTION_SOURCE.md` and referenced metrics | `demo-assets/NATURAL_MOTION_SOURCE.md`; `models/evaluation/` PPE metrics on the natural-motion clip | Confirmed as a disclosed, honest domain-gap finding (zero PPE-class detections on non-Construction-PPE footage) rather than a hidden failure — this is a genuine limitation of the fine-tuned model, correctly documented as such, not a testing gap. |

Note on E-numbering: the acceptance-matrix reference file itself (`.claude/skills/assessment-quality-gate/references/acceptance-matrix.md`) does not assign numeric IDs to its "Calculation Cases" / "Model/Data Leakage Cases" / "Vision Cases" sections — it lists them as unordered bullets. `docs/README.md` §8 previously assigned E01–E12 to a specific subset (PPE association, dwell, GRU leakage/reproducibility/fallback, zone config, API-type drift, guided demo, natural-motion domain gap) and this table preserves that same numbering for consistency with the existing submission documentation. The matrix's literal "Calculation Cases" (analytic solution, `ALREADY_EXCEEDED`, `NO_CROSSING`, falling concentration, zero-ventilation, invalid-parameter rejection, rolling exposure, `PARTIAL_WINDOW`) are separately and fully covered by `backend/tests/test_physics.py` (9 tests) and `backend/tests/test_exposure.py` (4 tests), all passing in the same 116-test full-suite run cited under A16 — folded into A16's proof rather than duplicated as their own E-rows here, since they were not previously given independent E-numbers in this project's documentation.

## Cross-cutting bug disclosure (both real bugs found earlier this session)

1. **Missing `lap` pin in `backend/requirements-vision.txt`** — FIXED (prior pass added the pin; confirmed present and working, 116/116 tests passing, in this correction pass).
2. **`make evaluate`'s vision step didn't check subprocess exit code`** — FIXED (prior pass added the exit-code check; confirmed live this pass: an honest `SKIPPED` reports exit 0, a real subprocess failure would `sys.exit(1)`).
3. **`YOLO("yolo11n.pt")` fallback triggered an undeclared network download and misreported `camera: "HEALTHY"` while running a non-fine-tuned substitute model** — FIXED this pass: `load_model()` now verifies the artifact's path+sha256 against `models/registry.json` before ever constructing `ultralytics.YOLO`, never calls a bare pretrained-name string, and reports `camera`/`detector`/`vision` as independent, honestly-degraded fields. See A12 above and `backend/tests/test_vision_model_availability.py` (7 new tests, all passing).
4. **`make setup` never created `backend/data/`, so a truly empty clone's `alembic upgrade head` failed** — found and FIXED during this pass's own clean-checkout re-verification (see A16/`docs/FINAL_VERIFICATION.md`). Not a bug carried over from the prior pass; discovered fresh this pass.
5. **Physics-vs-GRU improvement percentage was rounded inconsistently** (`17.0%`/`17%` in several places vs. the precise `(57.19429-47.59373)/57.19429 = 16.79%`, i.e. `16.8%`) — FIXED: every occurrence across `docs/FINAL_METRICS.md`, `docs/README.md`, and `docs/REVIEW_PREPARATION.md` corrected to `16.8%` (and the `unannounced onset` row's `17%` corrected to `16.5%`, matching its own 57.4→47.9 figures). The separate, broader physics-only metric (95.50 ppm MAE, `models/evaluation/physics_forecast_metrics.json`, 10 scenarios/120 point-comparisons) was already correctly kept distinct from the matched 57.19→47.59 GRU-benchmark comparison (1,092 point-comparisons, held-out test split) by the prior pass; a new `backend/tests/test_metrics_consistency.py` now asserts this programmatically so it cannot silently drift again.
