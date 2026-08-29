"""Builds the bundled camera replay asset from the Construction-PPE dataset's
own TEST split (never touched for training/evaluation numbers -- this only
*copies* a handful of test images into a short derived video for the demo UI).

Source: https://docs.ultralytics.com/datasets/detect/construction-ppe
Licence: AGPL-3.0 (same as the dataset/training artifact). The derived video
is a straightforward re-encoding (still-image pans) of a subset of the
dataset's own licensed images -- no third-party or unlicensed footage is used.

Selects a handful of test-split images labeled with a person + at least one of
helmet/no_helmet/vest, verified by reading the corresponding YOLO label files
(not by inspecting filenames), and renders each as a few seconds of a slow pan
("Ken Burns" motion) so the bundled clip has multiple frames per subject for
ByteTrack continuity, at demo-assets/replay.mp4.
"""

import json
import sys
from pathlib import Path

import cv2

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

DEMO_ASSETS = REPO_ROOT / "demo-assets"
OUT_PATH = DEMO_ASSETS / "replay.mp4"
SOURCE_DOC_PATH = DEMO_ASSETS / "REPLAY_SOURCE.md"

DATASET_CLASS_NAMES = ["helmet", "gloves", "vest", "boots", "goggles", "none", "Person", "no_helmet", "no_goggle", "no_gloves", "no_boots"]
PERSON_ID = 6
HELMET_ID = 0
NO_HELMET_ID = 7
VEST_ID = 2

SECONDS_PER_IMAGE = 4.0
FPS = 10
OUT_SIZE = (960, 540)


def find_dataset_root() -> Path:
    from ultralytics.utils import SETTINGS

    root = Path(SETTINGS.get("datasets_dir", ".")) / "construction-ppe"
    if not root.exists():
        raise SystemExit(f"Dataset not found at {root}. Run scripts/train_vision_model.py (or a short --epochs 1 dry run) first to trigger the dataset download.")
    return root


def label_classes(label_path: Path) -> set[int]:
    if not label_path.exists():
        return set()
    classes = set()
    for line in label_path.read_text().splitlines():
        parts = line.split()
        if parts:
            classes.add(int(parts[0]))
    return classes


def select_images(dataset_root: Path, n: int = 12) -> tuple[list[Path], dict]:
    test_images_dir = dataset_root / "images" / "test"
    test_labels_dir = dataset_root / "labels" / "test"
    candidates = []
    for img_path in sorted(test_images_dir.glob("*")):
        if img_path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue
        label_path = test_labels_dir / (img_path.stem + ".txt")
        classes = label_classes(label_path)
        if PERSON_ID in classes and (HELMET_ID in classes or NO_HELMET_ID in classes or VEST_ID in classes):
            candidates.append((img_path, classes))

    # Prefer clean single-signal examples so the bundled clip demonstrates each
    # PPE state unambiguously: helmet-positive (and no no_helmet in the same
    # frame), no_helmet-only (missing-helmet evidence), and vest-positive.
    helmet_only = [p for p, c in candidates if HELMET_ID in c and NO_HELMET_ID not in c]
    no_helmet_only = [p for p, c in candidates if NO_HELMET_ID in c and HELMET_ID not in c]
    vest_imgs = [p for p, c in candidates if VEST_ID in c]

    # Guarantee real representation of all three signals by reserving slots per
    # category first (previously this filled all `n` slots from one category --
    # found and fixed after inspecting the first build's output).
    selected: list[Path] = []
    per_category_quota = max(2, n // 4)
    for pool in (no_helmet_only, helmet_only, vest_imgs):
        added = 0
        for p in pool:
            if p not in selected:
                selected.append(p)
                added += 1
            if added >= per_category_quota:
                break

    # Fill any remaining slots from the general candidate pool for variety.
    for p, _ in candidates:
        if len(selected) >= n:
            break
        if p not in selected:
            selected.append(p)

    return selected[:n], {str(p): sorted(c) for p, c in candidates if p in selected}


def ken_burns_frames(img, n_frames: int, out_size):
    h, w = img.shape[:2]
    frames = []
    zoom_start, zoom_end = 1.0, 1.12
    for i in range(n_frames):
        t = i / max(1, n_frames - 1)
        zoom = zoom_start + (zoom_end - zoom_start) * t
        crop_w, crop_h = int(w / zoom), int(h / zoom)
        x0 = (w - crop_w) // 2
        y0 = (h - crop_h) // 2
        crop = img[y0 : y0 + crop_h, x0 : x0 + crop_w]
        resized = cv2.resize(crop, out_size, interpolation=cv2.INTER_LINEAR)
        frames.append(resized)
    return frames


def main():
    dataset_root = find_dataset_root()
    selected, class_map = select_images(dataset_root, n=12)
    if not selected:
        raise SystemExit("No suitable test-split images found (person + helmet/no_helmet/vest label).")

    DEMO_ASSETS.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(OUT_PATH), fourcc, FPS, OUT_SIZE)

    n_frames_per_image = int(SECONDS_PER_IMAGE * FPS)
    used = []
    for img_path in selected:
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        for frame in ken_burns_frames(img, n_frames_per_image, OUT_SIZE):
            writer.write(frame)
        used.append(img_path.name)

    writer.release()

    doc = f"""# Bundled Replay Source

- **Source dataset:** Ultralytics Construction-PPE, https://docs.ultralytics.com/datasets/detect/construction-ppe
- **Licence:** AGPL-3.0 (same licence as the dataset and the YOLO11 code/weights trained on it)
- **Split used:** `test` (published test split; these images are read-only source material, not used for training or reported as evaluation numbers)
- **Derivation:** each source still image is rendered as a {SECONDS_PER_IMAGE:.0f}s slow-zoom ("Ken Burns") pan at {FPS} fps and concatenated into `replay.mp4`, so the bundled clip is a straightforward re-encoding of licensed source images plus synthetic camera motion -- no external or unlicensed footage.
- **Selection:** images verified (by reading their YOLO label files, not filenames) to contain at least a `Person` box and one of `helmet` / `no_helmet` / `vest`.

## Source images used

```json
{json.dumps(class_map, indent=2)}
```

Class IDs: {json.dumps({i: n for i, n in enumerate(DATASET_CLASS_NAMES)})}
"""
    SOURCE_DOC_PATH.write_text(doc)

    print(f"Wrote {OUT_PATH} from {len(used)} source images: {used}")
    print(f"Documented at {SOURCE_DOC_PATH}")


if __name__ == "__main__":
    main()
