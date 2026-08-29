# Submission Manifest

Generated as part of the final submission-readiness audit (2026-08-29). Lists what a
reviewer needs to find in this repository and what it takes to run it. See
`docs/FINAL_VERIFICATION.md` for the verification evidence behind these numbers.

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

## Setup / runtime requirements

- **Python**: 3.12 (`make setup` invokes `python3.12` specifically, falling back to
  `python3`). Verified present via `pyenv` (`3.12.11`) in the audit environment.
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
