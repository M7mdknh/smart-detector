#!/usr/bin/env python
"""Converts the Roboflow "Industrial safety" YOLOv11 export's class indices to
this project's canonical runtime class order.

Source dataset (external-data/Industrial safety.v1i.yolov11.zip, data.yaml):
    nc: 4
    names: ['hardhat', 'no_hardhat', 'person', 'safety_vest']
    -> raw index 0=hardhat, 1=no_hardhat, 2=person, 3=safety_vest

Canonical runtime order (models/registry.json "ppe_detector.runtime_classes",
matching the active v1.1 artifact exactly):
    0=person, 1=helmet, 2=vest, 3=no_helmet

This module contains only the pure remap logic (import-safe, no CLI side
effects) plus a CLI that walks a YOLOv11-export-shaped directory
(train/valid/test, each with images/ and labels/) and writes a converted
copy: relabeled .txt files with remapped class ids, images referenced via
symlink (not copied -- the source images are untouched and this keeps the
~1.7GB dataset from being duplicated on disk), and a new data.yaml using the
canonical names in canonical order.

Never introduces a `no_vest` class; the source dataset has none to map.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

# raw dataset class name -> raw index, exactly as declared in data.yaml
RAW_CLASSES = ["hardhat", "no_hardhat", "person", "safety_vest"]

# canonical runtime order, must match models/registry.json's
# ppe_detector.runtime_classes exactly
CANONICAL_CLASSES = ["person", "helmet", "vest", "no_helmet"]

# raw class name -> canonical class name
RAW_NAME_TO_CANONICAL_NAME = {
    "hardhat": "helmet",
    "no_hardhat": "no_helmet",
    "person": "person",
    "safety_vest": "vest",
}

# raw index -> canonical index, derived once at import time so the two name
# tables above are the single source of truth (no separately-hand-maintained
# index table to drift out of sync).
RAW_INDEX_TO_CANONICAL_INDEX = {
    raw_idx: CANONICAL_CLASSES.index(RAW_NAME_TO_CANONICAL_NAME[raw_name])
    for raw_idx, raw_name in enumerate(RAW_CLASSES)
}


class LabelConversionError(ValueError):
    pass


def remap_label_line(line: str) -> str:
    """Remaps a single YOLO label line's leading class index from raw to
    canonical. Preserves the rest of the line (coordinates, and any trailing
    fields such as a segmentation polygon or confidence) byte-for-byte."""
    stripped = line.strip()
    if not stripped:
        return line
    parts = stripped.split()
    try:
        raw_idx = int(parts[0])
    except ValueError as exc:
        raise LabelConversionError(f"non-numeric class id in line: {line!r}") from exc
    if raw_idx not in RAW_INDEX_TO_CANONICAL_INDEX:
        raise LabelConversionError(
            f"unexpected raw class id {raw_idx} (expected one of "
            f"{sorted(RAW_INDEX_TO_CANONICAL_INDEX)}) in line: {line!r}"
        )
    canonical_idx = RAW_INDEX_TO_CANONICAL_INDEX[raw_idx]
    rest = parts[1:]
    return " ".join([str(canonical_idx), *rest])


def remap_label_text(text: str) -> str:
    lines = text.splitlines()
    converted = [remap_label_line(line) for line in lines]
    out = "\n".join(converted)
    if text.endswith("\n"):
        out += "\n"
    return out


def convert_dataset(source_root: Path, dest_root: Path, splits: tuple[str, ...] = ("train", "valid", "test")) -> dict:
    """Walks source_root/{split}/{images,labels} and writes dest_root/{split}/
    {images(symlinks),labels(remapped .txt)} plus a canonical data.yaml.
    Returns a small summary dict (per-split image/label counts)."""
    summary: dict = {"splits": {}}
    dest_root.mkdir(parents=True, exist_ok=True)

    for split in splits:
        src_images = source_root / split / "images"
        src_labels = source_root / split / "labels"
        if not src_images.exists():
            continue
        dst_images = dest_root / split / "images"
        dst_labels = dest_root / split / "labels"
        dst_images.mkdir(parents=True, exist_ok=True)
        dst_labels.mkdir(parents=True, exist_ok=True)

        n_images = 0
        n_labels = 0
        for img_path in sorted(src_images.iterdir()):
            if not img_path.is_file():
                continue
            link_path = dst_images / img_path.name
            if not link_path.exists():
                os.symlink(img_path.resolve(), link_path)
            n_images += 1

            label_path = src_labels / f"{img_path.stem}.txt"
            dst_label_path = dst_labels / f"{img_path.stem}.txt"
            if label_path.exists():
                converted = remap_label_text(label_path.read_text())
                dst_label_path.write_text(converted)
                n_labels += 1
            else:
                dst_label_path.write_text("")

        summary["splits"][split] = {"images": n_images, "labels": n_labels}

    data_yaml = dest_root / "data.yaml"
    data_yaml.write_text(
        "train: ../train/images\n"
        "val: ../valid/images\n"
        "test: ../test/images\n"
        "\n"
        f"nc: {len(CANONICAL_CLASSES)}\n"
        f"names: {CANONICAL_CLASSES!r}\n"
    )
    summary["dest_root"] = str(dest_root)
    summary["canonical_classes"] = CANONICAL_CLASSES
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True, help="Extracted Roboflow export root (contains train/, valid/, test/)")
    parser.add_argument("--dest-root", type=Path, required=True, help="Output directory for the converted (relabeled) dataset")
    args = parser.parse_args(argv)

    summary = convert_dataset(args.source_root, args.dest_root)
    for split, counts in summary["splits"].items():
        print(f"{split}: {counts['images']} images, {counts['labels']} label files converted")
    print(f"Canonical classes: {summary['canonical_classes']}")
    print(f"Wrote {args.dest_root / 'data.yaml'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
