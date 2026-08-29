.PHONY: setup demo demo-stop test e2e train-sensor train-vision build-replay evaluate lint clean \
	generate-api check-api-types train-forecast evaluate-forecast tune-ppe-thresholds guided-demo evaluate-natural-motion

BACKEND=backend
VENV=$(BACKEND)/.venv
PY=$(VENV)/bin/python
PIP=$(VENV)/bin/pip

setup:
	python3.12 -m venv $(VENV) || python3 -m venv $(VENV)
	$(PIP) install --quiet --upgrade pip
	# requirements-vision.txt pulls in requirements.txt plus ultralytics/opencv/torch --
	# without it, `make demo`'s camera and GRU forecast would silently run degraded even
	# on a machine that could run them, failing the Definition of Done's real-CV-inference
	# and hybrid-forecast requirements. Both models still degrade honestly if this install
	# is skipped or fails offline; this is what makes them actually available by default.
	$(PIP) install --quiet -r $(BACKEND)/requirements-vision.txt
	cd frontend && npm install --silent
	mkdir -p $(BACKEND)/data
	cd $(BACKEND) && ../$(PY) -m alembic upgrade head
	@echo "Setup complete. Run 'make demo' to start the application."

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
