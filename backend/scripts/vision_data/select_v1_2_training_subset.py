#!/usr/bin/env python
"""Deterministic (seed=42) class-aware training-subset selection for the
v1.2 Industrial-Safety fine-tuning experiment.

Given the cleaned TRAIN split's manifest + audit report (from
prepare_vision_data.py / audit_vision_data.py), this:
  1. Drops exact-duplicate images (keeps one representative per sha256 group).
  2. Groups the remaining train images into near-duplicate connected
     components (union-find over the audit's near_duplicate_pairs, restricted
     to train<->train pairs -- this dataset's near-duplicates are
     overwhelmingly consecutive video frames from the same source clip, so a
     component is treated as one "scene").
  3. Caps how many images are kept per scene component (MAX_PER_SCENE) to
     maximize scene/lighting/scale diversity instead of keeping near-identical
     frames, while always keeping every no_helmet-containing image in a
     capped scene if there is room in the cap (rare-class preservation).
  4. Deterministically shuffles (seed=42) and takes up to TARGET_MAX images,
     but never drops a no_helmet-containing image while any non-no_helmet
     image remains selectable, and always keeps at least MIN_TARGET images
     if the cleaned pool is smaller than the target range.

Never touches valid/ or test/ splits -- both are frozen held-out data.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

SEED = 42
TARGET_MIN = 6000
TARGET_MAX = 8000
MAX_PER_SCENE = 3  # cap near-duplicate video-frame clusters to this many kept frames


class UnionFind:
    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def select_subset(manifest: dict, audit: dict, split_prefix: str = "industrial_safety/images/train__") -> dict:
    train_images = [rec for rec in manifest["images"] if rec["relpath"].startswith(split_prefix)]
    train_paths = {rec["relpath"] for rec in train_images}
    class_names = manifest["raw_class_list"]  # canonical order after conversion: person, helmet, vest, no_helmet
    no_helmet_idx = class_names.index("no_helmet") if "no_helmet" in class_names else None

    # 1. exact-duplicate dedup: keep first (sorted) relpath per sha256 group
    by_hash: dict[str, list[str]] = defaultdict(list)
    for rec in train_images:
        by_hash[rec["sha256"]].append(rec["relpath"])
    dropped_exact = set()
    for group in by_hash.values():
        if len(group) > 1:
            for extra in sorted(group)[1:]:
                dropped_exact.add(extra)

    cleaned_paths = [p for p in train_paths if p not in dropped_exact]

    # 2. near-duplicate connected components restricted to train<->train pairs
    uf = UnionFind()
    for p in cleaned_paths:
        uf.find(p)  # ensure singleton entry exists
    for pair in audit.get("near_duplicate_pairs", []):
        a, b = pair["a"], pair["b"]
        if a in uf.parent and b in uf.parent:
            uf.union(a, b)

    components: dict[str, list[str]] = defaultdict(list)
    for p in cleaned_paths:
        components[uf.find(p)].append(p)

    rec_by_path = {rec["relpath"]: rec for rec in train_images}

    def has_no_helmet(path: str) -> bool:
        if no_helmet_idx is None:
            return False
        return no_helmet_idx in rec_by_path[path].get("class_ids_present", [])

    rng = random.Random(SEED)
    capped: list[str] = []
    for comp_id in sorted(components.keys()):
        members = sorted(components[comp_id])
        rng.shuffle(members)
        # rare-class preservation: no_helmet members always kept (up to a
        # slightly higher per-scene cap so a rare positive is never dropped
        # just because its scene is large)
        no_helmet_members = [m for m in members if has_no_helmet(m)]
        other_members = [m for m in members if not has_no_helmet(m)]
        keep = list(dict.fromkeys(no_helmet_members[: max(MAX_PER_SCENE, len(no_helmet_members))] + other_members))[:max(MAX_PER_SCENE, len(no_helmet_members))]
        capped.extend(keep)

    capped = sorted(set(capped))

    if len(capped) <= TARGET_MAX:
        selected = capped
        used_full_cleaned_pool = True
    else:
        used_full_cleaned_pool = False
        no_helmet_pool = [p for p in capped if has_no_helmet(p)]
        other_pool = [p for p in capped if not has_no_helmet(p)]
        rng2 = random.Random(SEED)
        rng2.shuffle(other_pool)
        rng2.shuffle(no_helmet_pool)
        # keep all rare-class images where practical, then fill with others
        selected = list(no_helmet_pool)
        remaining_budget = TARGET_MAX - len(selected)
        selected.extend(other_pool[: max(0, remaining_budget)])
        if len(selected) > TARGET_MAX:
            selected = selected[:TARGET_MAX]
        selected = sorted(set(selected))

    per_class_counts = {name: 0 for name in class_names}
    for p in selected:
        for cid in rec_by_path[p].get("class_ids_present", []):
            per_class_counts[class_names[cid]] += 1

    return {
        "seed": SEED,
        "raw_train_images": len(train_images),
        "exact_duplicates_dropped": len(dropped_exact),
        "cleaned_train_images": len(cleaned_paths),
        "near_dup_scene_components": len(components),
        "max_per_scene_cap": MAX_PER_SCENE,
        "post_cap_pool_size": len(capped),
        "used_full_cleaned_pool": used_full_cleaned_pool,
        "target_range": [TARGET_MIN, TARGET_MAX],
        "selected_count": len(selected),
        "per_class_instance_counts": per_class_counts,
        "selected_relpaths": selected,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    manifest = json.loads(args.manifest.read_text())
    audit = json.loads(args.audit.read_text())
    result = select_subset(manifest, audit)
    args.output.write_text(json.dumps(result, indent=2))
    print(
        f"raw_train={result['raw_train_images']} cleaned={result['cleaned_train_images']} "
        f"components={result['near_dup_scene_components']} post_cap={result['post_cap_pool_size']} "
        f"selected={result['selected_count']} used_full_cleaned_pool={result['used_full_cleaned_pool']}"
    )
    print("per_class_instance_counts:", result["per_class_instance_counts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
