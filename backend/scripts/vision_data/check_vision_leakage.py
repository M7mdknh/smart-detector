#!/usr/bin/env python
"""Verifies that no exact-duplicate, near-duplicate, or same-scene-group image
crosses a train/val/test split boundary in a manifest produced by
prepare_vision_data.py.

Split assignment comes from a separate --splits JSON file (relpath -> split
name) rather than being baked into the manifest, so the same manifest can be
checked against different candidate split assignments without re-running
prepare_vision_data.py.

Exits non-zero (and prints every leak found) if any leakage is detected;
exits 0 if the manifest+splits combination is clean. Only ever exercised
against the synthetic fixtures in this sandbox -- see
backend/tests/test_vision_data_tooling.py, which includes a deliberately
leaky splits file to prove this checker actually catches something, and a
clean one to prove it doesn't false-positive.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from audit_vision_data import find_near_duplicate_pairs, perceptual_hash  # noqa: E402

NEAR_DUP_HAMMING_THRESHOLD = 5


def check_leakage(manifest_path: Path, splits_path: Path, dataset_root: Path) -> list[dict]:
    manifest = json.loads(manifest_path.read_text())
    splits = json.loads(splits_path.read_text())
    images = manifest.get("images", [])

    leaks = []

    # Exact-duplicate cross-split check (sha256 groups).
    by_hash: dict[str, list[str]] = {}
    for rec in images:
        by_hash.setdefault(rec["sha256"], []).append(rec["relpath"])
    for group in by_hash.values():
        if len(group) < 2:
            continue
        assigned_splits = {relpath: splits.get(relpath, "unassigned") for relpath in group}
        distinct_splits = {s for s in assigned_splits.values() if s != "unassigned"}
        if len(distinct_splits) > 1:
            leaks.append({"type": "exact_duplicate_cross_split", "images": assigned_splits})

    # Near-duplicate cross-split check (perceptual hash). Uses the same
    # LSH-banded candidate search as audit_vision_data.py at real dataset
    # scale (see its module docstring for the approximation this implies),
    # then discards same-split and unassigned pairs.
    phashes = {}
    for rec in images:
        try:
            phashes[rec["relpath"]] = perceptual_hash(dataset_root / rec["relpath"])
        except Exception:
            continue
    for p1, p2, dist in find_near_duplicate_pairs(phashes, threshold=NEAR_DUP_HAMMING_THRESHOLD):
        s1, s2 = splits.get(p1, "unassigned"), splits.get(p2, "unassigned")
        if s1 == "unassigned" or s2 == "unassigned" or s1 == s2:
            continue
        leaks.append({"type": "near_duplicate_cross_split", "a": {p1: s1}, "b": {p2: s2}, "hamming_distance": dist})

    # Same-scene-group cross-split check (optional "scene_group" metadata field).
    by_scene: dict[str, list[str]] = {}
    for rec in images:
        group = rec.get("scene_group")
        if group:
            by_scene.setdefault(group, []).append(rec["relpath"])
    for group_name, relpaths in by_scene.items():
        assigned = {r: splits.get(r, "unassigned") for r in relpaths}
        distinct = {s for s in assigned.values() if s != "unassigned"}
        if len(distinct) > 1:
            leaks.append({"type": "scene_group_cross_split", "scene_group": group_name, "images": assigned})

    return leaks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--splits", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    args = parser.parse_args(argv)

    leaks = check_leakage(args.manifest, args.splits, args.dataset_root)
    if leaks:
        print(f"LEAKAGE DETECTED: {len(leaks)} issue(s) found", file=sys.stderr)
        print(json.dumps(leaks, indent=2), file=sys.stderr)
        return 1
    print("No train/val/test leakage detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
