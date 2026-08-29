# Bundled Replay Source

- **Source dataset:** Ultralytics Construction-PPE, https://docs.ultralytics.com/datasets/detect/construction-ppe
- **Licence:** AGPL-3.0 (same licence as the dataset and the YOLO11 code/weights trained on it)
- **Split used:** `test` (published test split; these images are read-only source material, never used for training or threshold tuning). **Disclosure:** these same 12 images are part of the 141-image test split that IS scored for the reported detection metrics (`models/evaluation/vision_model_metrics.json`) -- they are not a disjoint holdout from that report. See `models/evaluation/vision_replay_overlap_analysis.json` for the full accounting of what touched training/tuning/replay/final-eval, and for a re-scored check on the remaining 129 non-replay test images showing the overlap changes no metric materially.
- **Derivation:** each source still image is rendered as a 4s slow-zoom ("Ken Burns") pan at 10 fps and concatenated into `replay.mp4`, so the bundled clip is a straightforward re-encoding of licensed source images plus synthetic camera motion -- no external or unlicensed footage.
- **Selection:** images verified (by reading their YOLO label files, not filenames) to contain at least a `Person` box and one of `helmet` / `no_helmet` / `vest`.

## Source images used

```json
{
  "<local-dataset-root>/construction-ppe/images/test/image1.jpeg": [
    0,
    1,
    2,
    6
  ],
  "<local-dataset-root>/construction-ppe/images/test/image10.jpeg": [
    2,
    6
  ],
  "<local-dataset-root>/construction-ppe/images/test/image1003.jpg": [
    0,
    1,
    2,
    3,
    6
  ],
  "<local-dataset-root>/construction-ppe/images/test/image1007.jpg": [
    0,
    1,
    2,
    3,
    4,
    6
  ],
  "<local-dataset-root>/construction-ppe/images/test/image1009.jpg": [
    0,
    1,
    2,
    6
  ],
  "<local-dataset-root>/construction-ppe/images/test/image1014.jpg": [
    0,
    1,
    2,
    3,
    4,
    6
  ],
  "<local-dataset-root>/construction-ppe/images/test/image1019.jpg": [
    0,
    1,
    2,
    3,
    6
  ],
  "<local-dataset-root>/construction-ppe/images/test/image1023.jpg": [
    0,
    1,
    2,
    3,
    4,
    6
  ],
  "<local-dataset-root>/construction-ppe/images/test/image1037.jpeg": [
    0,
    1,
    2,
    3,
    6
  ],
  "<local-dataset-root>/construction-ppe/images/test/image1120.jpg": [
    5,
    6,
    7,
    8
  ],
  "<local-dataset-root>/construction-ppe/images/test/image1132.jpg": [
    3,
    5,
    6,
    7,
    8,
    9
  ],
  "<local-dataset-root>/construction-ppe/images/test/image1133.jpg": [
    5,
    6,
    7,
    8,
    9
  ]
}
```

Class IDs: {"0": "helmet", "1": "gloves", "2": "vest", "3": "boots", "4": "goggles", "5": "none", "6": "Person", "7": "no_helmet", "8": "no_goggle", "9": "no_gloves", "10": "no_boots"}
