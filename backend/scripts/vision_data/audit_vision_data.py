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

# Full O(n^2) pairwise Hamming comparison is only tractable up to a few
# thousand images. Above this, near-duplicate candidates are pre-filtered
# with LSH banding (split the 64-bit hash into BANDS equal-width bands;
# only compare pairs that share at least one band exactly) before the exact
# Hamming distance is computed on the surviving candidate pairs. This is the
# standard LSH approximation for Hamming-space near-duplicate search: any
# pair differing by at most NEAR_DUP_HAMMING_THRESHOLD=5 bits over 4 bands of
# 16 bits each has, on average, a high chance of leaving at least one band
# untouched, but (being an approximation) can in principle miss a pair whose
# 5 differing bits are spread one-per-band across all 4 bands. Real-world
# scale (tens of thousands of images) makes this the only tractable option;
# documented here rather than silently applied.
NEAR_DUP_LSH_THRESHOLD_IMAGES = 3000
NEAR_DUP_LSH_BANDS = 4
NEAR_DUP_LSH_BAND_BITS = 16  # 4 bands * 16 bits = 64-bit hash


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


def _lsh_bands(value: int) -> list[int]:
    mask = (1 << NEAR_DUP_LSH_BAND_BITS) - 1
    return [(value >> (i * NEAR_DUP_LSH_BAND_BITS)) & mask for i in range(NEAR_DUP_LSH_BANDS)]


def find_near_duplicate_pairs(phashes: dict[str, int], threshold: int = NEAR_DUP_HAMMING_THRESHOLD) -> list[tuple[str, str, int]]:
    """Returns (path_a, path_b, hamming_distance) for every pair whose
    perceptual hashes differ by <= threshold bits. Uses full O(n^2) pairwise
    comparison for small inputs and LSH banding (see module docstring) above
    NEAR_DUP_LSH_THRESHOLD_IMAGES to stay tractable at real dataset scale."""
    paths = list(phashes.keys())
    pairs_checked: set[tuple[str, str]] = set()
    results: list[tuple[str, str, int]] = []

    if len(paths) <= NEAR_DUP_LSH_THRESHOLD_IMAGES:
        candidate_pairs = ((paths[i], paths[j]) for i in range(len(paths)) for j in range(i + 1, len(paths)))
    else:
        buckets: dict[tuple[int, int], list[str]] = defaultdict(list)
        for p in paths:
            for band_idx, band_val in enumerate(_lsh_bands(phashes[p])):
                buckets[(band_idx, band_val)].append(p)

        def _gen():
            for bucket_paths in buckets.values():
                if len(bucket_paths) < 2:
                    continue
                for i in range(len(bucket_paths)):
                    for j in range(i + 1, len(bucket_paths)):
                        a, b = bucket_paths[i], bucket_paths[j]
                        yield (a, b) if a < b else (b, a)

        candidate_pairs = _gen()

    for a, b in candidate_pairs:
        key = (a, b) if a < b else (b, a)
        if key in pairs_checked:
            continue
        pairs_checked.add(key)
        dist = hamming_distance(phashes[a], phashes[b])
        if dist <= threshold:
            results.append((key[0], key[1], dist))
    return results


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

    near_duplicates = [
        {"a": p1, "b": p2, "hamming_distance": dist}
        for p1, p2, dist in find_near_duplicate_pairs(phashes)
    ]

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
