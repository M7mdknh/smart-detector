#!/usr/bin/env python
"""Audits one or more manifest JSON files produced by prepare_vision_data.py:
exact-duplicate (sha256) and near-duplicate (perceptual average-hash)
detection, class balance, missing-annotation counts, and corrupt-image checks.

Uses the `imagehash` package for perceptual hashing if it's installed;
otherwise falls back to a small self-contained average-hash implementation
(8x8 grayscale average hash, Hamming-distance comparison) so this tool has no
hard dependency beyond Pillow.

This only validates whatever manifest(s) it's pointed at -- see
docs/adr/0002-vision-v2-roadmap.md for the explicit statement that no real
external dataset has been audited this way; only the synthetic fixtures under
backend/tests/fixtures/vision_data_sample/ have been (see
backend/tests/test_vision_data_tooling.py).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

NEAR_DUP_HAMMING_THRESHOLD = 5  # out of 64 bits; small enough to avoid false positives on distinct scenes


def _ahash_fallback(image_path: Path) -> int:
    from PIL import Image

    img = Image.open(image_path).convert("L").resize((8, 8))
    pixels = list(img.getdata())
    avg = sum(pixels) / len(pixels)
    bits = 0
    for p in pixels:
        bits = (bits << 1) | (1 if p >= avg else 0)
    return bits


def perceptual_hash(image_path: Path) -> int:
    try:
        import imagehash
        from PIL import Image

        return int(str(imagehash.average_hash(Image.open(image_path))), 16)
    except ImportError:
        return _ahash_fallback(image_path)


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def audit_manifest(manifest_path: Path, dataset_root: Path) -> dict:
    manifest = json.loads(manifest_path.read_text())
    images = manifest.get("images", [])

    exact_dup_groups: dict[str, list[str]] = defaultdict(list)
    corrupt: list[str] = []
    phashes: dict[str, int] = {}

    for rec in images:
        relpath = rec["relpath"]
        exact_dup_groups[rec["sha256"]].append(relpath)
        img_path = dataset_root / relpath
        try:
            phashes[relpath] = perceptual_hash(img_path)
        except Exception as exc:
            corrupt.append(f"{relpath}: {exc}")

    exact_duplicates = [group for group in exact_dup_groups.values() if len(group) > 1]

    near_duplicates = []
    paths = list(phashes.keys())
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            p1, p2 = paths[i], paths[j]
            dist = hamming_distance(phashes[p1], phashes[p2])
            if dist <= NEAR_DUP_HAMMING_THRESHOLD:
                near_duplicates.append({"a": p1, "b": p2, "hamming_distance": dist})

    class_balance = Counter()
    for rec in images:
        for cid in rec.get("class_ids_present", []):
            raw_name = manifest["raw_class_list"][cid] if cid < len(manifest.get("raw_class_list", [])) else f"class_{cid}"
            canonical = manifest.get("class_mapping_applied", {}).get(raw_name, raw_name)
            class_balance[canonical] += 1

    missing_annotations = [rec["relpath"] for rec in images if rec["num_boxes"] == 0]
    invalid_annotations = [
        {"relpath": rec["relpath"], "invalid_lines": rec["invalid_annotation_lines"]}
        for rec in images
        if rec.get("invalid_annotation_lines")
    ]

    return {
        "dataset": manifest.get("name"),
        "image_count": len(images),
        "exact_duplicate_groups": exact_duplicates,
        "near_duplicate_pairs": near_duplicates,
        "class_balance": dict(class_balance),
        "images_missing_annotations": missing_annotations,
        "images_with_invalid_annotations": invalid_annotations,
        "corrupt_images": corrupt,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="Path to a manifest JSON produced by prepare_vision_data.py")
    parser.add_argument("--dataset-root", type=Path, default=None, help="Root directory the manifest's relpaths are relative to (defaults to the manifest's own directory's parent)")
    parser.add_argument("--output", type=Path, default=None, help="Where to write the audit report JSON (defaults to stdout only)")
    args = parser.parse_args(argv)

    dataset_root = args.dataset_root or args.manifest.parent
    report = audit_manifest(args.manifest, dataset_root)

    print(json.dumps(report, indent=2))
    if args.output:
        args.output.write_text(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
