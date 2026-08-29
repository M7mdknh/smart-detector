"""Reproduces the fine-tuned PPE YOLO11n artifact (make train-vision).

Requires backend/requirements-vision.txt (ultralytics, opencv, torch) and network
access to download the credential-free Ultralytics Construction-PPE dataset:
https://docs.ultralytics.com/datasets/detect/construction-ppe (AGPL-3.0 licensed
weights/code and dataset; dataset licence recorded in registry.json).

Dataset class map (construction-ppe.yaml, 11 classes total):
  0 helmet, 1 gloves, 2 vest, 3 boots, 4 goggles, 5 none, 6 Person,
  7 no_helmet, 8 no_goggle, 9 no_gloves, 10 no_boots

Training uses the full published label set unmodified (the published test split
is never touched or relabeled). The RUNTIME class filter to {person, helmet,
vest, no_helmet} is applied at inference time only
(app/inference/vision_worker_impl.py), per model-specification.md's "ignore
other classes at runtime; do not relabel them as safe/unsafe".

Epoch count/hardware actually used are recorded in registry.json at the end of
each run (not hardcoded in this docstring) since this script may run on
different hardware across reproductions.
"""

import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

MODELS_DIR = REPO_ROOT / "models"
ARTIFACTS_DIR = MODELS_DIR / "artifacts"
EVAL_DIR = MODELS_DIR / "evaluation"
REGISTRY_PATH = MODELS_DIR / "registry.json"

RUNTIME_CLASSES = ["person", "helmet", "vest", "no_helmet"]
DATASET_CLASSES = ["helmet", "gloves", "vest", "boots", "goggles", "none", "Person", "no_helmet", "no_goggle", "no_gloves", "no_boots"]
DATASET_URL = "https://docs.ultralytics.com/datasets/detect/construction-ppe"
DATASET_DOWNLOAD_URL = "https://github.com/ultralytics/assets/releases/download/v0.0.0/construction-ppe.zip"
DATASET_LICENSE = "AGPL-3.0 (Ultralytics YOLO11 code/weights and Construction-PPE dataset)"
CLASS_MAP_DATASET_TO_RUNTIME = {"Person": "person", "helmet": "helmet", "vest": "vest", "no_helmet": "no_helmet"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--patience", type=int, default=12)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", type=str, default=None, help="'0' for first CUDA GPU, 'cpu' otherwise; auto-detected if omitted")
    parser.add_argument(
        "--amp", type=str, default="false", choices=["true", "false"],
        help="Automatic mixed precision. Default false: an initial run on this project's GPU (GeForce MX450) "
             "produced NaN losses from the very first batch with AMP enabled -- a real numerical-stability "
             "issue on this older/low-VRAM card, not a flag left on by habit. fp32 is the safe default here.",
    )
    parser.add_argument("--data", type=str, default="construction-ppe.yaml", help="Ultralytics data.yaml (relative path or Ultralytics dataset name). Override for continued-fine-tuning experiments on a different dataset.")
    parser.add_argument("--weights", type=str, default="yolo11n.pt", help="Starting weights: 'yolo11n.pt' for COCO-pretrained-from-scratch, or a path to an existing checkpoint (e.g. models/artifacts/ppe-yolo11n.pt) for continued fine-tuning.")
    parser.add_argument("--output-artifact", type=str, default=None, help="Output artifact filename under models/artifacts/. Defaults to ppe-yolo11n.pt (the active v1.1 path) ONLY for full backward compatibility with `make train-vision`; pass an explicit candidate name (e.g. ppe-yolo11n-v1.2-candidate.pt) for any experiment that must not overwrite the active artifact.")
    parser.add_argument("--run-name", type=str, default="ppe-yolo11n", help="Ultralytics run/project subdirectory name under models/evaluation/vision_training_runs/")
    parser.add_argument("--lr0", type=float, default=None, help="Initial learning rate override. Ultralytics default is 0.01; pass a smaller value for continued fine-tuning of an already-trained checkpoint.")
    parser.add_argument("--no-registry-write", action="store_true", help="Skip writing models/registry.json. Use for any run whose result is a CANDIDATE artifact, not a promotion -- registry updates for candidates happen only after the promotion gate passes.")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--cache", type=str, default="false", choices=["true", "false"])
    args = parser.parse_args()
    amp = args.amp == "true"
    cache = args.cache == "true"

    import torch
    import ultralytics
    from ultralytics import YOLO

    device = args.device
    if device is None:
        device = "0" if torch.cuda.is_available() else "cpu"

    hardware = platform.processor() or platform.machine()
    if device != "cpu" and torch.cuda.is_available():
        hardware = torch.cuda.get_device_name(0)

    print(f"Ultralytics {ultralytics.__version__}, torch {torch.__version__}, device={device} ({hardware})")
    print(f"Data: {args.data} | Weights: {args.weights}")

    model = YOLO(args.weights)

    train_kwargs = dict(
        data=args.data,
        epochs=args.epochs,
        patience=args.patience,
        batch=args.batch,
        imgsz=args.imgsz,
        seed=args.seed,
        device=device,
        amp=amp,
        workers=args.workers,
        cache=cache,
        project=str(EVAL_DIR / "vision_training_runs"),
        name=args.run_name,
        exist_ok=True,
    )
    if args.lr0 is not None:
        train_kwargs["lr0"] = args.lr0

    results = model.train(**train_kwargs)

    save_dir = Path(results.save_dir)
    best_weights = save_dir / "weights" / "best.pt"
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    output_name = args.output_artifact or "ppe-yolo11n.pt"
    artifact_path = ARTIFACTS_DIR / output_name
    artifact_path.write_bytes(best_weights.read_bytes())
    sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    artifact_size = artifact_path.stat().st_size

    # Dataset zip checksum (downloaded by ultralytics under its default datasets dir)
    from ultralytics.utils import SETTINGS

    dataset_zip_sha256 = None
    zip_candidates = list(Path(SETTINGS.get("datasets_dir", ".")).glob("construction-ppe*.zip"))
    if zip_candidates:
        dataset_zip_sha256 = hashlib.sha256(zip_candidates[0].read_bytes()).hexdigest()

    # Best-epoch info from Ultralytics' own results.csv
    best_epoch = None
    results_csv = save_dir / "results.csv"
    if results_csv.exists():
        import csv

        with open(results_csv) as f:
            rows = list(csv.DictReader(f))
        if rows:
            best_epoch = int(rows[-1].get("epoch", len(rows) - 1)) + 1  # 0-indexed in file

    if args.no_registry_write:
        print(f"\nArtifact: {artifact_path} ({artifact_size} bytes, sha256={sha256[:16]}...)")
        print(f"Best epoch: {best_epoch} / requested {args.epochs}")
        print(f"Training run dir: {save_dir}")
        print("--no-registry-write set: models/registry.json left untouched. This is a CANDIDATE artifact; "
              "promotion (updating registry.json's active pointer) happens only after the promotion gate passes.")
        return

    registry = json.loads(REGISTRY_PATH.read_text()) if REGISTRY_PATH.exists() else {}
    registry["ppe_detector"] = {
        "name": "ppe_detector",
        "version": "1.0",
        "artifact_path": str(artifact_path.relative_to(REPO_ROOT)),
        "sha256": sha256,
        "artifact_size_bytes": artifact_size,
        "base_checkpoint": "yolo11n.pt (COCO-pretrained)",
        "dataset_url": DATASET_URL,
        "dataset_download_url": DATASET_DOWNLOAD_URL,
        "dataset_license": DATASET_LICENSE,
        "dataset_classes": DATASET_CLASSES,
        "dataset_zip_sha256_locally_computed": dataset_zip_sha256,
        "class_map_dataset_to_runtime": CLASS_MAP_DATASET_TO_RUNTIME,
        "runtime_classes": RUNTIME_CLASSES,
        "runtime_confidence_thresholds": {"person": 0.35, "helmet": 0.25, "vest": 0.30, "no_helmet": 0.25},
        "runtime_nms_iou": 0.50,
        "input_size": args.imgsz,
        "training_config": {
            "epochs_requested": args.epochs, "epochs_completed": best_epoch, "patience": args.patience,
            "batch": args.batch, "seed": args.seed, "amp": amp,
        },
        "ultralytics_version": ultralytics.__version__,
        "torch_version": torch.__version__,
        "training_hardware": hardware,
        "training_device": device,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": "Trained on the full 11-class published label set unmodified; the runtime "
                "adapter filters to person/helmet/vest/no_helmet only and ignores other classes.",
    }
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2))

    print(f"\nArtifact: {artifact_path} ({artifact_size} bytes, sha256={sha256[:16]}...)")
    print(f"Best epoch: {best_epoch} / requested {args.epochs}")
    print(f"Training run dir: {save_dir}")


if __name__ == "__main__":
    main()
