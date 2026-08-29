"""`make evaluate` entry point. Runs physics, leak-classifier, and vision
evaluation as clearly separated sections, plus a system-metrics section
summarizing the automated end-to-end/integration test results (incident
dedup, restart-recovery-shaped tests, workflow correctness) -- not the same
thing as live manual acceptance verification, which is reported separately
in docs/README.md's acceptance matrix.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
EVAL_DIR = REPO_ROOT / "models" / "evaluation"
PY = sys.executable


def run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def main():
    report = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "sections": {}}

    print("=" * 70)
    print("PHYSICS FORECAST METRICS")
    print("=" * 70)
    code, out = run([PY, "scripts/evaluate_physics.py"], BACKEND_ROOT)
    print(out)
    physics_path = EVAL_DIR / "physics_forecast_metrics.json"
    report["sections"]["physics"] = json.loads(physics_path.read_text()) if physics_path.exists() else {"status": "FAILED", "log": out}
    report["sections"]["physics"]["exit_code"] = code

    print("=" * 70)
    print("LEAK CLASSIFIER METRICS (reproduces the calibrated XGBoost artifact)")
    print("=" * 70)
    code, out = run([PY, "scripts/train_leak_model.py"], BACKEND_ROOT)
    print(out)
    leak_path = EVAL_DIR / "leak_model_metrics.json"
    report["sections"]["leak_classifier"] = json.loads(leak_path.read_text()) if leak_path.exists() else {"status": "FAILED", "log": out}
    report["sections"]["leak_classifier"]["exit_code"] = code

    print("=" * 70)
    print("VISION MODEL METRICS")
    print("=" * 70)
    try:
        import ultralytics  # noqa: F401

        code, out = run([PY, "scripts/evaluate_vision_model.py"], BACKEND_ROOT)
        print(out)
        vision_path = EVAL_DIR / "vision_model_metrics.json"
        report["sections"]["vision"] = json.loads(vision_path.read_text()) if vision_path.exists() else {"status": "FAILED", "log": out}
        report["sections"]["vision"]["exit_code"] = code
    except ImportError:
        msg = "SKIPPED: ultralytics not installed (pip install -r requirements-vision.txt)"
        print(msg)
        report["sections"]["vision"] = {"status": "SKIPPED", "reason": msg}

    print("=" * 70)
    print("END-TO-END SYSTEM METRICS (automated integration test summary)")
    print("=" * 70)
    code, out = run([PY, "-m", "pytest", "-q", "tests/test_e2e_pipeline.py", "tests/test_incident_workflow.py", "tests/test_ingestion.py"], BACKEND_ROOT)
    print(out)
    nonblank_lines = [line for line in out.strip().splitlines() if line.strip()]
    last_line = nonblank_lines[-1] if nonblank_lines else ""
    report["sections"]["system"] = {
        "exit_code": code,
        "summary_line": last_line,
        "covers": [
            "incident dedup (repeated evidence updates one incident, not duplicates)",
            "incident workflow state machine + optimistic concurrency",
            "reading idempotency (duplicate reading_id)",
            "normal/gradual_leak/ventilation_failure/overhead_ppe scenario end-to-end behavior",
        ],
        "note": "Automated coverage, not a substitute for the live manual verification recorded in docs/README.md's acceptance matrix.",
    }

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EVAL_DIR / "full_evaluation_report.json"
    out_path.write_text(json.dumps(report, indent=2, default=str))
    print("=" * 70)
    print(f"Full report written to {out_path}")

    failed_sections = [
        name
        for name, section in report["sections"].items()
        if section.get("exit_code", 0) not in (0, None)
    ]
    if failed_sections:
        print(f"FAILED sections (non-zero exit code): {', '.join(failed_sections)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
