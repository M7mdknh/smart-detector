"""Targeted continuation-training experiment (Phase 3), justified by validation
evidence: the confidence-threshold sweep (scripts/tune_ppe_thresholds.py) showed
no_helmet recall plateaus at ~24% across the ENTIRE tested threshold range on the
validation split -- a model-capacity/training-completeness limit, not a threshold
problem. This is exactly the condition the task's rules require before attempting
more training: "only if validation analysis shows threshold tuning cannot provide
a usable operating point."

This resumes the SAME interrupted run (not a new experiment with different
hyperparameters) from its last checkpoint toward its ORIGINAL target of 60
epochs -- Ultralytics' `resume=True` continues from the exact saved optimizer/
scheduler state in the existing run directory, seed/config unchanged.

Does NOT overwrite the registered v1.0 artifact. Produces a new checkpoint that
is evaluated on validation (never test) before any promotion decision; promotion
to v1.1 happens in a separate, explicit step only if justified.
"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

RUN_DIR = REPO_ROOT / "models" / "evaluation" / "vision_training_runs" / "ppe-yolo11n"


def main():
    from ultralytics import YOLO

    last = RUN_DIR / "weights" / "last.pt"
    if not last.exists():
        raise SystemExit(f"no checkpoint to resume from at {last}")

    model = YOLO(str(last))
    model.train(resume=True)

    best = RUN_DIR / "weights" / "best.pt"
    print(f"Continuation run complete. Best checkpoint: {best}")


if __name__ == "__main__":
    main()
