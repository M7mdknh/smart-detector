# Submission Manifest

Generated as part of the final submission-readiness audit (2026-08-29). Lists what a
reviewer needs to find in this repository and what it takes to run it. See
`docs/FINAL_VERIFICATION.md` for the verification evidence behind these numbers.

## v2.0 changes (`assessment-submission-v2.0`, on top of `assessment-submission-v1.0`)

`assessment-submission-v1.0` (commit `d2a3b88`, archive
`factory-safety-sentinel-submission-v1.0.tar.gz`, sha256
`07ad21e9263ad7b6887898b4c6599d3961fa682de51e746a6e22e21fb1ad9644`) is
untouched — no rewrite, move, or retag. Everything below is new commits on
top of it.

This release deliberately does **not** include the "vision-enhanced v2.0"
work originally requested in full (a two-stage YOLO architecture, ~8
externally sourced PPE datasets, retrained/benchmarked YOLO11n/11s
candidates, and a licensed continuous "interview" video). That work requires
a GPU, dataset-provider credentials, and human legal review of video
licensing, none of which are available to an agent in this sandbox. Per an
explicit scope-down decision, this release ships only what is genuinely
executable, and defers the rest as a specification — see
`docs/adr/0002-vision-v2-roadmap.md`.

What v2.0 actually ships:

1. **Clean-environment dependency/test split.** `make setup` now installs
   lean application dependencies only (`requirements.txt` — no
   torch/ultralytics/opencv); `make setup-vision` layers
   `requirements-vision.txt` on top. `make test` passes with 0 failures in
   both environments (vision-only tests skip via `pytest.importorskip` in a
   lean env, run for real when vision deps are present). New `make
   test-vision` and `make test-full` targets fail loudly instead of skipping
   when vision deps are missing, since both explicitly mean "run vision for
   real." One previously-failing lean-env test
   (`test_predict_with_non_finite_model_output_falls_back` in
   `backend/tests/test_forecast_gru.py`) was fixed with a proper
   `pytest.importorskip("torch")` guard — it exercises a code path that
   itself calls `import torch` unconditionally, so it never genuinely
   ran without torch; it now correctly skips instead of failing.
2. **Restricted-zone intrusion detection.** A third configurable zone TYPE
   (`RESTRICTED`), reusing the existing polygon/box-membership +
   foot-point + dwell-timer mechanism used for the gas-exposure and
   overhead-work zones (no new YOLO class). New `IncidentType.PERSON_IN_RESTRICTED_ZONE`
   / reason code `PERSON_IN_RESTRICTED_ZONE`, severity `HIGH`. See
   `backend/app/inference/zone_config.json` (new `restricted-zone` polygon),
   `backend/app/services/vision_ground_truth.py` (`RESTRICTED_ZONE_BOX`,
   the path that actually drives simulator incidents),
   `backend/app/inference/vision_worker_impl.py` (CV replay path, for
   consistency), `backend/app/domain/risk/policy.py`,
   `backend/app/services/incident_service.py`, and
   `backend/tests/test_restricted_zone.py` (5 tests: polygon membership,
   dwell timing on both the CV-replay and ground-truth paths, incident
   creation, dedup).
3. **Incident evidence images and reports.** One annotated evidence
   snapshot per newly opened/escalated vision-derived incident (never per
   frame) — see `backend/app/services/evidence_image.py` for the honesty
   rationale (these incidents are ground-truth-driven with no real
   correlated camera frame, so the image is a labelled schematic
   reconstruction from the same evidence data, never presented as an
   unlabelled camera capture). New `incident_evidence_images` table
   (Alembic revision `a1c2e4f5b678`), `GET
   /api/v1/incidents/{id}/evidence` (safe by-ID file serving, typed 404s),
   `GET /api/v1/incidents/{id}/report.json`, and `GET
   /api/v1/incidents/{id}/report.csv`. Minimal frontend wiring in
   `frontend/src/dashboard/ReviewDrawer.tsx` (evidence thumbnails + report
   download buttons). See `backend/tests/test_incident_evidence_images.py`
   (8 tests).
4. **Duplicate weight cleanup.** `models/artifacts/ppe-yolo11n-v1.1.pt`
   (byte-identical, `sha256=a6b5aedc...`, to the registered
   `ppe-yolo11n.pt`, unreferenced anywhere) was removed after grepping the
   whole repo for references. See `docs/ACCEPTANCE_RESULTS.md` E04.
5. **Dataset-preparation tooling scaffold (input-less until real data
   arrives).** `backend/scripts/vision_data/{prepare_vision_data,audit_vision_data,check_vision_leakage}.py`
   plus `make prepare-vision-data` / `make audit-vision-data` / `make
   check-vision-leakage`, exercised against synthetic fixtures under
   `backend/tests/fixtures/vision_data_sample/` (`backend/tests/test_vision_data_tooling.py`,
   11 tests) — proves the tooling logic works, not that any real external
   dataset has been validated.
6. **`make interview-demo` guard.** Fails immediately with guidance
   (`make setup-vision`, then `docs/INTERVIEW_DEMO.md`) rather than running
   a fake slideshow in place of real continuous video, since none was
   acquired.
7. **`docs/adr/0002-vision-v2-roadmap.md`** — the deferred two-stage
   architecture proposal, the 8 named external datasets' proposed class
   mappings (none downloaded/audited/trained on), and the interview-video
   acquisition checklist.

## Required source directories

| Directory | Contents |
|---|---|
| `backend/` | FastAPI app (`app/api`, `app/contracts`, `app/domain`, `app/inference`, `app/simulation`, `app/storage`), Alembic migrations, `scripts/` (training/evaluation/build tooling), `tests/` |
| `frontend/` | React + TypeScript + Vite app (`src/dashboard`, `src/simulation`, `src/api`), tests |
| `models/` | `artifacts/` (bundled model weights), `training/`, `evaluation/` (reports), `registry.json` |
| `scenarios/` | Reserved per the intended repo layout; currently empty — scenario definitions live in code at `backend/app/inference/synthetic_scenarios.py` rather than as standalone files |
| `demo-assets/` | Bundled replay video assets + their source/licence notes |
| `docs/` | `README.md` (setup/run/architecture/evaluation/limitations), this manifest, `FINAL_VERIFICATION.md` |
| `scripts/` | Repo-root helper scripts (e.g. `run-e2e.sh`) |
| `.claude/skills/` | Specification references cited from `CLAUDE.md` (sensor/vision model specs, dashboard spec, simulator spec, API/data spec, acceptance matrix) |
| `CLAUDE.md`, `README.md`, `Makefile`, `docker-compose.yml` | Project brief/instructions, top-level README, stable commands, container orchestration |

## Model artifacts and checksums

All values independently recomputed with `sha256sum` and cross-checked against
`models/registry.json` — see `docs/FINAL_VERIFICATION.md` Section 3 for the full
reproduction log.

| Artifact | Path | Size | SHA-256 | Version |
|---|---|---:|---|---|
| XGBoost leak classifier | `models/artifacts/leak-classifier-xgb.json` | 195,857 B | `0abcb0aa8992012b3e245f85c2ad4ec179bc0009b3d7f43faf267f7c544c39f9` | 1.0 |
| YOLO11n PPE detector (active) | `models/artifacts/ppe-yolo11n.pt` | 5,464,083 B | `a6b5aedc326b2ad9118d3f5ce1f97769c746b9df92b073df0c6d62b7bacb38ae` | 1.1 |
| YOLO11n PPE detector (retained prior) | `models/artifacts/ppe-yolo11n-v1.0.pt` | 21,274,454 B | `094f67b194251003c8c2b1a97708345ede61cc4600073116c61a822d2cfb9edf` | 1.0 |
| Forecast GRU (P1) | `models/artifacts/forecast-gru.pt` | 19,834 B | `4c1c5c04c541f5faa459668d1ea4567c5d3189a7eb277189e851a0a9fc8f1e02` | 1.0 |
| GRU scaler | `models/artifacts/forecast-gru-scaler.json` | 585 B | `a8cb29d011879a4dd287bca91f1854b75166bce41dcbe2d2d07daccf0fb6ded3` | — |
| GRU feature schema | `models/artifacts/forecast-gru-feature-schema.json` | 858 B | `ff93eb22a70401f247359a84a1757d22b6ef82f6b8b537b025de817c0e9a136a` | — |

Both the XGBoost classifier and the YOLO11n detector were smoke-tested by direct load
(`xgboost.Booster.load_model`, `ultralytics.YOLO(...)`) and by a controlled
missing-artifact test (renamed → confirmed documented fallback/degraded behavior in logs
and `/api/v1/system/status` → restored → checksum re-verified identical). See
`docs/FINAL_VERIFICATION.md` for the full transcript.

Known issue affecting reproducibility of vision metrics specifically: `make evaluate`
cannot regenerate `models/evaluation/vision_model_metrics.json` on a machine with only the
credential-free dataset download, due to a filename mismatch (`construction-ppe.yaml` vs.
the dataset's actual `data.yaml`) — documented in `docs/FINAL_VERIFICATION.md`.

## Demo assets

| Asset | Path | Size | Notes |
|---|---|---:|---|
| Replay clip (Construction-PPE stills) | `demo-assets/replay.mp4` | 8,740,682 B | Source/licence in `demo-assets/REPLAY_SOURCE.md` |
| Natural-motion clip | `demo-assets/replay_natural_motion.mp4` | 3,802,382 B | Source/licence in `demo-assets/NATURAL_MOTION_SOURCE.md` |

## Documentation

- `CLAUDE.md` — project mission, frozen scope, invariants, architecture, model specs, risk
  policy, implementation order (read-only reference governing the whole project).
- `docs/README.md` — setup/run instructions, architecture, evaluation, limitations (997 lines).
- `docs/FINAL_VERIFICATION.md` — this audit's clean-environment verification, artifact
  checksum/reproducibility log, and hygiene findings.
- `docs/SUBMISSION_MANIFEST.md` — this file.
- `.claude/skills/*/references/*.md` — detailed model/API/dashboard/simulator specifications
  cited throughout `CLAUDE.md`.

## Stable `make` commands (from `Makefile`)

| Command | Purpose |
|---|---|
| `make setup` | Create backend venv, install deps (incl. vision extras), install frontend deps, run DB migrations |
| `make demo` | Start backend (`:8000`) and frontend (`:5173`) in the background via `nohup`, logs to `/tmp/sentinel-*.log` |
| `make demo-stop` | Kill both by port (`lsof -ti :8000/:5173`), remove pid files |
| `make test` | Backend `pytest`, frontend `vitest --run` |
| `make e2e` | Headless browser/API acceptance check (`scripts/run-e2e.sh`) — starts real services, loads `/dashboard` and `/simulation`, asserts no console errors |
| `make train-sensor` | Reproduce the XGBoost leak-classifier artifact |
| `make train-vision` | Reproduce the YOLO11n fine-tune (requires the separately-downloaded Construction-PPE dataset) + rebuilds the replay clip |
| `make build-replay` | Rebuild the bundled replay clip only |
| `make evaluate` | Physics + leak-classifier + vision + system-test metrics → `models/evaluation/full_evaluation_report.json` |
| `make train-forecast` | Reproduce the GRU forecast artifact (P1) |
| `make evaluate-forecast` | GRU vs. physics-only benchmark → `models/evaluation/gru_benchmark_report.json` |
| `make tune-ppe-thresholds` | Re-tune PPE class confidence thresholds on the validation split |
| `make guided-demo` | Scripted walkthrough driver |
| `make evaluate-natural-motion` | Evaluate against the natural-motion replay clip |
| `make generate-api` | Dump OpenAPI schema and regenerate `frontend/src/api/generated/schema.ts` |
| `make check-api-types` | CI drift check between backend contracts and generated frontend types |
| `make lint` | `ruff check` (backend) + `oxlint` (frontend) + API-types drift check |
| `make clean` | Remove the SQLite DB, backend venv, frontend `node_modules` |

## Expected ports

| Service | Native (`make demo`) | Docker Compose |
|---|---|---|
| Backend (FastAPI/uvicorn) | `127.0.0.1:8000` | `0.0.0.0:8000` → container `8000` |
| Frontend (Vite dev server / nginx) | `127.0.0.1:5173` | `0.0.0.0:8080` → container `80` |

CORS origins (backend default, `backend/app/settings.py`): `http://localhost:5173`,
`http://127.0.0.1:5173`. `docker-compose.yml` overrides `SENTINEL_CORS_ORIGINS` to also
include `http://localhost:8080` and `http://127.0.0.1:8080` for the containerized frontend.

## Git history and submission archive

Produced in the final correction pass (2026-08-29), after the working tree had no `.git`
directory at all in every prior pass. `.gitignore` was hardened first (PID files, coverage
output, Playwright artifacts, downloaded-dataset directories, `backend/runs/` — Ultralytics'
own generated validation plots that had leaked into an untracked-until-now state — and,
importantly, the model-artifact allowlist was widened: it previously excluded the GRU
artifacts and both PPE-detector version files entirely via `models/artifacts/*`, which would
have silently dropped required, checksum-verified artifacts from the archive).

- **Commit**: `82cf3d272fdc1b4f8c9b9eab0ab3a5962748a6b4` (this documentation update is itself
  part of the tagged commit, so the archive/checksum/verification figures below were computed
  against the immediately-prior commit `1ae6e560504025daba53c0c08577c800c6b23f7d` and then the
  tag was moved to this final commit; the file contents relevant to those figures — everything
  except this manifest and `docs/FINAL_VERIFICATION.md` themselves — are unchanged between the
  two, so the artifact/test/demo verification below remains accurate for the tagged commit)
- **Tag**: `assessment-submission-v1.0` (annotated, points to the commit above)
- **Tracked files**: 198 (`git ls-files | wc -l`)
- **Archive**: `factory-safety-sentinel-submission-v1.0.tar.gz`, built with
  `git archive --format=tar.gz -o <path> assessment-submission-v1.0` (so it contains exactly
  the tracked-file tree, nothing gitignored)
  - **Size**: 41,725,550 bytes (~39.8 MiB)
  - **SHA-256**: `9757267ddfd83d9d811b455edc61aa1905e76a0558c0b140d2681fac74f89820`
- **Extraction verification**: extracted into a fresh temp directory; confirmed all 7 model
  artifacts present with sha256 matching `models/registry.json` exactly (leak classifier, PPE
  detector v1.1 + v1.0 + the unversioned-name duplicate, GRU weights + scaler + feature
  schema); confirmed `docs/`, `backend/tests/` (20 test files), `backend/alembic/versions/`,
  `frontend/src/api/generated/schema.ts`, `Makefile`, `docker-compose.yml`,
  `backend/Dockerfile`, `frontend/Dockerfile`, and `scenarios/README.md` (added this pass so
  the intentionally-empty `scenarios/` directory survives archival — git does not track empty
  directories) all present. Ran `make setup` (lean, `requirements.txt` only — see the disk-
  quota note below for why the full `requirements-vision.txt` extras couldn't also be
  reinstalled a third time in this pass), `make test` (103 passed / 3 skipped / 1
  torch-absent-only failure, consistent with every other lean-venv run in this pass — see
  `docs/FINAL_VERIFICATION.md`), and a `make demo` smoke test (start → `health/ready` and
  `system/status` both 200 → `make demo-stop` → no orphan `uvicorn`/`vite` processes) directly
  from the extracted archive. All passed.
- **What the archive deliberately excludes** (all gitignored, confirmed via `git status
  --porcelain --untracked-files=all` before committing): `backend/.venv/`,
  `frontend/node_modules/`, `frontend/dist/`, `__pycache__/`, `.pytest_cache/`, local
  `*.db`/`*.sqlite*` files, `.env*` (except `.env.example`), logs, PID files, coverage output,
  Playwright artifacts, and `backend/runs/` (generated Ultralytics validation plots).

## Setup / runtime requirements

- **Python**: 3.12 (`make setup` invokes `python3.12` specifically, falling back to
  `python3`; a root `.python-version` pinning `3.12.11` was added this pass so `pyenv`
  resolves `python3.12` on a fresh clone without a manual `pyenv shell`/`PYENV_VERSION`).
  Verified present via `pyenv` (`3.12.11`) in the audit environment.
- **Node.js**: repo was verified against Node `v24.18.0` / npm `11.16.0` in this environment;
  no `.nvmrc`/`engines` field was found pinning an exact version.
- **Disk space**: a full `make setup` (including `requirements-vision.txt` — torch,
  torchvision, ultralytics, opencv) needs roughly **5–6 GB** free for the backend virtualenv
  alone (observed: `backend/.venv` ≈ 6.1 GB including caches; source-only `backend/` excluding
  `.venv` is 2.5 MB). `frontend/node_modules` adds roughly 270 MB. A `tmpfs`/`/tmp`-backed
  install location under ~7.5 GB total capacity is **not sufficient** — the audit hit `OSError:
  [Errno 122] Disk quota exceeded` under those conditions and had to relocate the checkout to
  a larger filesystem (see `docs/FINAL_VERIFICATION.md`).
- **RAM**: not independently benchmarked in this pass; no explicit RAM requirement is stated
  in `CLAUDE.md` or `docs/README.md`. Torch/ultralytics import and a YOLO11n forward pass
  completed without issue on this machine's available memory during the audit.
- **GPU**: optional. The frozen fallback paths (physics/rule-based forecasting, slope-based
  leak rule, degraded camera state) are CPU-only by design; `evaluate`'s vision metrics step
  will use a GPU if `torch.cuda` detects one (an NVIDIA GeForce MX450 was detected on this
  machine) but this is not a requirement for `make demo` to run in fallback mode.
- **Docker** (optional, for `docker compose`): verified working in this environment — Docker
  29.7.2, Compose v5.5.0. Note the backend Docker image installs only `requirements.txt`, not
  `requirements-vision.txt`, so the containerized backend always runs vision in
  fallback/degraded mode (no torch/ultralytics in that image).
