.PHONY: setup setup-vision demo demo-stop test test-vision test-full e2e train-sensor train-vision build-replay evaluate lint clean \
	generate-api check-api-types train-forecast evaluate-forecast tune-ppe-thresholds guided-demo evaluate-natural-motion \
	prepare-vision-data audit-vision-data check-vision-leakage interview-demo

BACKEND=backend
VENV=$(BACKEND)/.venv
PY=$(VENV)/bin/python
PIP=$(VENV)/bin/pip

setup:
	python3.12 -m venv $(VENV) || python3 -m venv $(VENV)
	$(PIP) install --quiet --upgrade pip
	# Lean application dependencies only (requirements.txt: FastAPI/SQLAlchemy/NumPy/
	# pandas/scikit-learn/XGBoost/Pillow -- no torch/ultralytics/opencv). `make demo`
	# still runs completely on this install alone: the PPE detector and GRU residual
	# forecast degrade honestly to MODEL_UNAVAILABLE/physics-only (CLAUDE.md "safe
	# fallback"), never silently or unsafely. Run `make setup-vision` afterwards for
	# real CV inference and the hybrid GRU forecast.
	$(PIP) install --quiet -r $(BACKEND)/requirements.txt
	cd frontend && npm install --silent
	mkdir -p $(BACKEND)/data
	cd $(BACKEND) && ../$(PY) -m alembic upgrade head
	@echo "Setup complete (lean). Run 'make setup-vision' for real CV/GRU inference, or 'make demo' to start now in degraded/fallback mode."

setup-vision:
	$(PIP) install --quiet -r $(BACKEND)/requirements-vision.txt
	@echo "Vision/GRU dependencies installed (torch/ultralytics/opencv). 'make demo' will now run real CV inference and the hybrid forecast."

demo: demo-stop
	mkdir -p $(BACKEND)/data
	cd $(BACKEND) && .venv/bin/python -m alembic upgrade head
	# Output redirected to log files (not left attached to this shell): a
	# daemonized child inheriting the caller's stdout/stderr keeps those pipes
	# open indefinitely, so `make demo` (and any script driving it) hangs
	# waiting for EOF even though both servers are already up and serving.
	cd $(BACKEND) && nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 \
		> /tmp/sentinel-backend.log 2>&1 & \
	echo $$! > /tmp/sentinel-backend.pid
	cd frontend && nohup npm run dev -- --host 127.0.0.1 --port 5173 --strictPort \
		> /tmp/sentinel-frontend.log 2>&1 & \
	echo $$! > /tmp/sentinel-frontend.pid
	@echo "Backend:  http://127.0.0.1:8000  (log: /tmp/sentinel-backend.log)"
	@echo "Frontend: http://127.0.0.1:5173  (log: /tmp/sentinel-frontend.log)"
	@echo "Stop with: make demo-stop"

demo-stop:
	# `npm run dev &` backgrounds the npm wrapper, not the vite child it spawns --
	# npm doesn't forward signals, so killing the wrapper PID alone leaves the
	# actual server orphaned holding the port (found live during this pass; see
	# docs/README.md §8.1, item 11). Kill by port instead.
	-lsof -ti :8000 | xargs -r kill -9
	-lsof -ti :5173 | xargs -r kill -9
	-rm -f /tmp/sentinel-backend.pid /tmp/sentinel-frontend.pid

test:
	# Runs cleanly in a lean (no torch/ultralytics) install: optional vision/GRU-only
	# tests skip via pytest.importorskip rather than failing. 0 failures is required
	# here regardless of which optional deps happen to be installed.
	cd $(BACKEND) && .venv/bin/python -m pytest -q
	cd frontend && npm test -- --run

test-vision:
	# Vision-dependent tests only, run for real -- fails loudly (not skips) if
	# torch/ultralytics/opencv aren't installed, since this target is explicitly
	# about exercising the real detector/GRU paths. Run 'make setup-vision' first.
	@$(PY) -c "import torch, ultralytics" || \
		(echo "ERROR: vision dependencies not installed. Run 'make setup-vision' first." && exit 1)
	cd $(BACKEND) && .venv/bin/python -m pytest -q tests/test_vision_e2e.py tests/test_vision_model_availability.py tests/test_forecast_gru.py tests/test_gru_train_serve_parity.py -v

test-full:
	# Complete backend + frontend suite with vision deps required (no skips
	# allowed) -- fails loudly if vision deps are missing, since "full" implies
	# everything runs for real. Run 'make setup-vision' first.
	@$(PY) -c "import torch, ultralytics" || \
		(echo "ERROR: vision dependencies not installed. Run 'make setup-vision' first." && exit 1)
	cd $(BACKEND) && .venv/bin/python -m pytest -q
	cd frontend && npm test -- --run

e2e:
	cd frontend && npm run test:e2e

train-sensor:
	cd $(BACKEND) && .venv/bin/python scripts/train_leak_model.py

train-vision:
	cd $(BACKEND) && .venv/bin/python scripts/train_vision_model.py --epochs 60 --patience 12 --batch 8 --amp false
	$(MAKE) build-replay

build-replay:
	cd $(BACKEND) && .venv/bin/python scripts/build_replay_clip.py

evaluate:
	cd $(BACKEND) && .venv/bin/python scripts/evaluate_all.py
	@echo "Evaluation reports written to models/evaluation/ (see full_evaluation_report.json for the combined physics/leak/vision/system sections)"

train-forecast:
	cd $(BACKEND) && .venv/bin/python scripts/train_forecast_gru.py

evaluate-forecast:
	cd $(BACKEND) && .venv/bin/python scripts/evaluate_forecast.py

tune-ppe-thresholds:
	cd $(BACKEND) && .venv/bin/python scripts/tune_ppe_thresholds.py

prepare-vision-data:
	# Prepares manifest(s) for manually-downloaded, already-licensed dataset
	# folders under INPUT_DIR (no network calls). Empty/absent by default in
	# this sandbox -- prints a clear message and exits 0. See
	# docs/adr/0002-vision-v2-roadmap.md.
	cd $(BACKEND) && .venv/bin/python scripts/vision_data/prepare_vision_data.py --input-dir "$(INPUT_DIR)" --output models/training/vision_manifests

audit-vision-data:
	# Exact/near-duplicate detection, class balance, and missing/corrupt
	# annotation checks against a manifest produced by prepare-vision-data.
	cd $(BACKEND) && .venv/bin/python scripts/vision_data/audit_vision_data.py --manifest "$(MANIFEST)" --dataset-root "$(INPUT_DIR)"

check-vision-leakage:
	# Verifies no exact/near-duplicate or same-scene-group image crosses a
	# train/val/test split boundary. Exits non-zero on any leak found.
	cd $(BACKEND) && .venv/bin/python scripts/vision_data/check_vision_leakage.py --manifest "$(MANIFEST)" --splits "$(SPLITS)" --dataset-root "$(INPUT_DIR)"

interview-demo:
	# Guard-only target: no genuinely licensed continuous "interview" video has
	# been acquired in this project (see docs/adr/0002-vision-v2-roadmap.md).
	# Refuses to run rather than faking a slideshow demo as if it were
	# continuous video.
	@$(PY) -c "import torch, ultralytics" || \
		(echo "ERROR: vision dependencies not installed. Run 'make setup-vision' first." && exit 1)
	@test -f demo-assets/interview_compilation_source.mp4 || \
		(echo "ERROR: demo-assets/interview_compilation_source.mp4 not found. See docs/INTERVIEW_DEMO.md for how to add real licensed footage; this target intentionally refuses to run a fake slideshow in its place." && exit 1)
	@echo "Prerequisites present -- see docs/INTERVIEW_DEMO.md for the intended run sequence."

guided-demo:
	cd $(BACKEND) && .venv/bin/python scripts/guided_demo.py

evaluate-natural-motion:
	cd $(BACKEND) && .venv/bin/python scripts/evaluate_natural_motion.py

# Dumps the OpenAPI schema (no running server needed -- app.openapi() is a pure
# function over the declared routes) and regenerates the TypeScript types from
# it. Run this after changing any backend route/contract. Does not touch
# frontend/src/api/types.ts (the hand-written UI/business types) or any
# application logic -- see docs/README.md's "Generated frontend types" section.
generate-api:
	cd $(BACKEND) && .venv/bin/python scripts/dump_openapi.py
	cd frontend && npx openapi-typescript openapi.json -o src/api/generated/schema.ts

# Drift check for CI/make lint: regenerates into a temp file and diffs against
# the committed generated schema. Non-zero exit (and a diff) means the backend
# routes/contracts changed without regenerating -- run `make generate-api` and
# commit the result.
check-api-types:
	cd $(BACKEND) && .venv/bin/python scripts/dump_openapi.py
	cd frontend && npx openapi-typescript openapi.json -o /tmp/schema-check.ts > /dev/null
	diff -u frontend/src/api/generated/schema.ts /tmp/schema-check.ts && echo "OK: generated API types are up to date" || \
		(echo "DRIFT: frontend/src/api/generated/schema.ts is stale -- run 'make generate-api' and commit the result" && exit 1)

lint:
	cd $(BACKEND) && .venv/bin/python -m ruff check app tests scripts || true
	cd frontend && npm run lint || true
	$(MAKE) check-api-types || true

clean:
	rm -f $(BACKEND)/data/sentinel.db
	rm -rf $(BACKEND)/.venv frontend/node_modules
