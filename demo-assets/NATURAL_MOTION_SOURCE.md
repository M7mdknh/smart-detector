# Secondary Natural-Motion Tracking Asset

Phase 9 enhancement: a genuinely continuous-motion clip for a qualitative
ByteTrack/domain-gap stress test, **secondary** to the primary deterministic
PPE replay (`demo-assets/replay.mp4`), which remains the default `make demo`
source and the one used for all reported test-set metrics.

- **File:** `demo-assets/replay_natural_motion.mp4`
- **SHA-256:** `75b3cdbb80716337a3ec10abf611d7a66c803aa0d72060d268ae92d5ab1c9490`
- **Source:** Pexels — "Back view of construction worker walking in safety gear on site"
  <https://www.pexels.com/video/back-view-of-workers-walking-in-construction-site-5434220/>
- **Author:** Everett Bumstead
- **Licence:** [Pexels License](https://www.pexels.com/license/) — free for
  commercial and non-commercial use, no attribution required, modification
  explicitly permitted ("You can modify the photos and videos from Pexels.
  Be creative and edit them as you like"). The one relevant restriction is
  not redistributing the *unmodified* file on a competing stock-media
  platform, which does not apply here (a modified, re-encoded, trimmed clip
  bundled inside an open-source assessment repository).
- **Access date:** 2026-08-28
- **Derivation:** original 1920x1080/24fps/~17.5s source, downloaded directly
  and credential-free via `curl` (confirmed no login/API key required),
  trimmed to the first 15 seconds, downscaled to 960x540, re-encoded to H.264
  (`ffmpeg -t 15 -vf scale=960:540 -an -c:v libx264 -crf 23`), audio removed.
- **Content:** two construction workers walking through a jobsite corridor,
  wearing red hard hats and high-visibility red/yellow vests; real camera and
  subject motion (not a still-image slideshow).

## Why this is a secondary asset, not the default replay

This clip shows real workers in real motion — a genuinely different regime
from the still-image-derived primary replay, useful for a qualitative
stress test of tracking continuity and the construction-to-factory domain
gap. It is **not** used for any reported precision/recall/mAP number (those
remain measured on the Construction-PPE dataset's published test split,
never used for training or threshold tuning -- though 12 of those 141 test
images are separately reused as the primary replay's source stills; see
`models/evaluation/vision_replay_overlap_analysis.json` for that disclosure)
and **not** wired into `make demo`'s default startup, to keep the reproducible
P0 demo path unchanged. Run `scripts/evaluate_natural_motion.py` to exercise
it against the registered detector.
