#!/usr/bin/env python
"""Dataset-manifest preparation tool for future PPE-dataset acquisition.

This does NOT download anything. It accepts a directory of already-downloaded,
already-licensed dataset folders (YOLO-format: images/, labels/, classes.txt,
optionally dataset_info.json) and produces one manifest.json per dataset
under --output, plus a canonical class-name normalization pass driven by a
small JSON/YAML mapping config (raw dataset class name -> one of this
project's runtime classes: person/helmet/vest/no_helmet, or any other string
if the dataset genuinely has an out-of-scope class you want tracked but not
mapped).

Real inputs are not present in this sandbox (see docs/adr/0002-vision-v2-roadmap.md):
running with no --input-dir (or an empty one) prints a clear message and
exits 0 rather than failing, since there is genuinely nothing to prepare yet.

Self-test / --dry-run mode runs this same logic against the tiny synthetic
fixture set committed at backend/tests/fixtures/vision_data_sample/, so the
tool's logic is exercised by a real test without needing any external dataset
-- see backend/tests/test_vision_data_tooling.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "vision_data_sample"

YOLO_LABEL_LINE_MIN_FIELDS = 5


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def aggregate_folder_sha256(files: list[Path], root: Path) -> str:
    """Deterministic hash over sorted (relative_path, content_sha256) pairs --
    stands in for "archive sha256" when the input is a directory rather than
    a single zip file (a real zip is hashed directly, see main())."""
    h = hashlib.sha256()
    for f in sorted(files, key=lambda p: str(p.relative_to(root))):
        h.update(str(f.relative_to(root)).encode("utf-8"))
        h.update(sha256_file(f).encode("utf-8"))
    return h.hexdigest()


def load_class_mapping(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    text = path.read_text()
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml  # optional; only needed for YAML mapping files

            return yaml.safe_load(text) or {}
        except ImportError:
            print(f"WARNING: pyyaml not installed, cannot read {path}; treating mapping as empty", file=sys.stderr)
            return {}
    return json.loads(text) or {}


def parse_yolo_label_file(path: Path, num_classes: int) -> dict:
    """Returns {"boxes": [...], "invalid_lines": [...]}. A line is invalid if
    it doesn't have 5 whitespace-separated fields, the class id is out of the
    known range, or any coordinate falls outside [0, 1]."""
    boxes = []
    invalid = []
    if not path.exists():
        return {"boxes": boxes, "invalid_lines": invalid, "missing": True}
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < YOLO_LABEL_LINE_MIN_FIELDS:
            invalid.append({"line": lineno, "reason": "wrong_field_count", "raw": line})
            continue
        try:
            cls_id = int(parts[0])
            coords = [float(x) for x in parts[1:5]]
        except ValueError:
            invalid.append({"line": lineno, "reason": "non_numeric", "raw": line})
            continue
        if not (0 <= cls_id < num_classes):
            invalid.append({"line": lineno, "reason": "unknown_class_id", "raw": line})
            continue
        if any(c < 0.0 or c > 1.0 for c in coords):
            invalid.append({"line": lineno, "reason": "coordinate_out_of_range", "raw": line})
            continue
        boxes.append({"class_id": cls_id, "cx": coords[0], "cy": coords[1], "w": coords[2], "h": coords[3]})
    return {"boxes": boxes, "invalid_lines": invalid, "missing": False}


def prepare_dataset(dataset_dir: Path, class_mapping: dict[str, str], splits: dict[str, str] | None, splits_root: Path | None) -> dict:
    images_dir = dataset_dir / "images"
    labels_dir = dataset_dir / "labels"
    classes_path = dataset_dir / "classes.txt"
    info_path = dataset_dir / "dataset_info.json"

    classes = classes_path.read_text().splitlines() if classes_path.exists() else []
    classes = [c.strip() for c in classes if c.strip()]
    canonical_classes = sorted({class_mapping.get(c, c) for c in classes})

    info = {}
    if info_path.exists():
        try:
            info = json.loads(info_path.read_text())
        except Exception:
            info = {}

    image_files = sorted(images_dir.glob("*")) if images_dir.exists() else []
    records = []
    total_boxes = 0
    total_invalid = 0
    missing_annotations = 0

    for img_path in image_files:
        label_path = labels_dir / f"{img_path.stem}.txt"
        parsed = parse_yolo_label_file(label_path, len(classes))
        total_boxes += len(parsed["boxes"])
        total_invalid += len(parsed["invalid_lines"])
        if parsed["missing"] or not parsed["boxes"]:
            missing_annotations += 1

        rel = img_path
        if splits_root is not None:
            rel = img_path.relative_to(splits_root)
        split = (splits or {}).get(str(rel), "unassigned")

        records.append(
            {
                "relpath": str(rel),
                "sha256": sha256_file(img_path),
                "split": split,
                "num_boxes": len(parsed["boxes"]),
                "class_ids_present": sorted({b["class_id"] for b in parsed["boxes"]}),
                "invalid_annotation_lines": parsed["invalid_lines"],
            }
        )

    manifest = {
        "name": info.get("name", dataset_dir.name),
        "owner": info.get("owner", "unknown"),
        "url": info.get("url", "unknown"),
        "license": info.get("license", "unknown"),
        "version": info.get("version", "unknown"),
        "raw_class_list": classes,
        "canonical_class_list": canonical_classes,
        "class_mapping_applied": {c: class_mapping.get(c, c) for c in classes},
        "image_count": len(image_files),
        "annotation_box_count": total_boxes,
        "invalid_annotation_count": total_invalid,
        "images_missing_annotations": missing_annotations,
        "archive_sha256": aggregate_folder_sha256(image_files + [p for p in labels_dir.glob("*") if labels_dir.exists()], dataset_dir) if image_files else None,
        "images": records,
    }
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=None, help="Directory containing one or more dataset subfolders (images/, labels/, classes.txt)")
    parser.add_argument("--class-mapping", type=Path, default=None, help="JSON or YAML file mapping raw dataset class names to canonical runtime names")
    parser.add_argument("--splits", type=Path, default=None, help="Optional JSON file mapping relative image paths to a split name (train/val/test)")
    parser.add_argument("--output", type=Path, default=Path("models/training/vision_manifests"), help="Directory to write one manifest JSON per dataset")
    parser.add_argument("--dry-run", action="store_true", help="Self-test mode: run against the checked-in synthetic fixtures instead of --input-dir")
    args = parser.parse_args(argv)

    if args.dry_run:
        input_dir = FIXTURE_DIR
        class_mapping = load_class_mapping(FIXTURE_DIR / "class_mapping.json")
        splits = json.loads((FIXTURE_DIR / "splits_clean.json").read_text())
    else:
        input_dir = args.input_dir
        class_mapping = load_class_mapping(args.class_mapping)
        splits = json.loads(args.splits.read_text()) if args.splits else None

    if input_dir is None or not input_dir.exists():
        print("No --input-dir given (or it does not exist); nothing to prepare. "
              "See docs/adr/0002-vision-v2-roadmap.md for how to acquire real datasets first.")
        return 0

    dataset_dirs = [d for d in sorted(input_dir.iterdir()) if d.is_dir() and (d / "images").exists()]
    if not dataset_dirs:
        print(f"No dataset subfolders (with an images/ directory) found under {input_dir}; nothing to prepare.")
        return 0

    args.output.mkdir(parents=True, exist_ok=True)
    for dataset_dir in dataset_dirs:
        manifest = prepare_dataset(dataset_dir, class_mapping, splits, input_dir)
        out_path = args.output / f"{dataset_dir.name}_manifest.json"
        out_path.write_text(json.dumps(manifest, indent=2))
        print(f"Wrote manifest for '{dataset_dir.name}': {manifest['image_count']} images, "
              f"{manifest['annotation_box_count']} boxes, {manifest['invalid_annotation_count']} invalid annotation lines "
              f"-> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
