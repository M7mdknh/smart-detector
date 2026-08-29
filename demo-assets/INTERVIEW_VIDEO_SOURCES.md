# Interview-Demonstration Video Sources

This document tracks every piece of footage considered or used for the
"interview demonstration compilation" (`demo-assets/interview_compilation_source.mp4`
once assembled). Per CLAUDE.md invariant #2 (evidence provenance) and this
project's own explicit sourcing rules, nothing is committed or archived here
unless its license to redistribute is genuinely verified -- footage with
unverified licensing is inspected and disclosed, but kept local-only and
excluded from Git (`.gitignore`) and from any submission archive.

## Clip 1 -- CLEARED for use (own recording, confirmed by the user)

- **Committed path:** `demo-assets/interview_sources/clip1_helmet_alert_own_recording.mp4`
- **Original filename (as supplied):** `Safety Alert_ Worker Found Without Helmet – Immediate Coaching at Construction Site.mp4`
- **SHA-256:** `846d3d97df759ffa121253bcc26b89b00c046578572878c0fbbad7e9a27d6f87`
- **Duration / resolution / fps:** 13.62s, 720x1280 (9:16 portrait), ~29.94 fps, H.264/AAC
- **Container metadata note:** `handler_name: "ISO Media file produced by Google Inc."`,
  `encoder: Lavf59.27.100` -- the filename shape and this metadata initially
  looked consistent with a downloaded/re-muxed video rather than raw camera
  output, so this clip was first treated as license-unverified and kept
  local-only/gitignored. **The user has since explicitly confirmed this is
  their own recording** (or one they can attest to), so it is cleared and now
  committed under the path above.
- **Source:** recorded by the user (own recording, per explicit confirmation).
- **Creator/platform:** the user; not sourced from a third-party platform.
- **License:** own recording -- no third-party license applies; the user has
  the rights to include it in this repository.
- **Redistribution permitted:** yes (own recording).
- **Approximate location/date:** not documented by the source.
- **Download date:** N/A (locally supplied, not downloaded).
- **Content actually verified by inspection** (14 frames sampled at 1 fps,
  visually reviewed -- not assumed from the filename):
  - A man in a yellow/lime hi-vis mesh vest, **no helmet**, disheveled hair
    clearly visible and bare-headed throughout his appearance in-frame
    (~0:00-0:05 and ~0:11-0:13) -- genuinely supports the **missing-helmet**
    scenario.
  - Multiple other workers wearing both a hard hat (yellow) AND a hi-vis vest
    (orange or lime), walking naturally across a real construction site
    (~0:05-0:13) -- genuinely supports the **PPE-compliant** scenario.
  - Every person visible in this clip is wearing a vest of some kind; **no
    frame shows a person with an uncovered torso / no vest.** This clip does
    **NOT** support a missing-vest scenario, despite one worker's vest being
    partly obscured by a black shirt underneath in some frames -- the vest
    itself is always present and visible.
  - Workers walk along a dirt path between temporary barrier rails/rope
    fencing on a real active construction site -- plausibly usable for
    configuring a restricted-zone polygon overlay, though the camera itself
    is handheld and panning/walking with the group (natural but shaky
    motion), which will affect tracking stability more than a fixed camera.
  - Heavy equipment (an excavator, a mobile crane, industrial stacks) is
    visible in the background of several frames, never in close-up or as the
    main subject -- at most a weak/background match for the optional
    near-machinery scenario, not a clear demonstration of it.
  - Real, continuous, single-take footage with correct natural frame order
    (confirmed by 1 fps frame sampling across the full 13.6s duration) -- not
    a slideshow, not stitched from unrelated images.
- **Disposition:** Cleared and committed at the path above. Usable as a
  genuine source clip for the **missing-helmet** and **PPE-compliant**
  scenarios in the interview compilation, and as a weak/secondary source for
  the restricted-zone-walk scenario (see caveats above -- handheld camera,
  short duration). It must **not** be described anywhere as supporting the
  missing-vest scenario, since that event does not occur in it -- a second
  clip is still needed for that scenario (see Status below).

## Other candidates researched (not downloaded, license or content did not clear)

- **mixkit.co** -- 2-3 short (14-25s) PPE-compliant-only construction clips
  from creators `@edgarfernandez` and `@joshjanssen`, whose free tier is the
  genuine Mixkit Free License (commercial use permitted, no attribution
  required, redistribution/resale of the raw clip as stock media prohibited
  -- the compilation use here would be "incorporation into a larger project,"
  which the license permits). Not yet downloaded pending a decision on
  whether PPE-compliant b-roll is still wanted alongside the user-supplied
  clip. Every Mixkit clip found showing a worker walking a corridor/path
  (candidate for the restricted-zone scenario) was uploaded by creator
  `FrameStock` under the **Mixkit Restricted License (personal use only)**
  and is therefore **disqualified** -- commercial/redistributable use would
  require an Envato Elements subscription this project does not have.
- **coverr.co** -- site's own collection page discloses a mix of "authentic
  human-shot video" and "AI-generated stock clips" with no per-clip
  real/AI labelling visible on the page. Individual clip authenticity was not
  verified; **not usable** without per-clip verification not yet performed.
- **pixabay.com**, **pexels.com** -- returned HTTP 403 to automated fetches
  from this environment; not evaluated.

## Compilation: `demo-assets/interview_compilation_source.mp4`

Built from Clip 1 only (the only source cleared for use). Structure (see
`demo-assets/interview_video_manifest.json` for the full machine-readable
breakdown with exact timestamps):

| t (compilation) | Content |
|---|---|
| 0.0 - 2.0s | Title card: "MISSING PPE / Worker without helmet detected" (synthetic, not footage) |
| 2.0 - 3.9s | Real footage: Clip 1, source t=0.0-1.9s -- worker with vest, no helmet |
| 3.9 - 5.9s | Title card: "PPE COMPLIANT / Helmet + vest worn correctly" (synthetic, not footage) |
| 5.9 - 17.6s | Real footage: Clip 1, source t=1.9-13.6s -- multiple workers, all helmet+vest compliant, walking a dirt path between barrier rails (candidate for a restricted-zone polygon overlay during pipeline processing) |

Both real-footage segments are frame-accurate cuts of Clip 1's single
continuous handheld take (confirmed via `ffmpeg` scene-detection at
thresholds down to 0.15 -- no internal cuts detected in the source clip
itself) at **unmodified natural frame timing** -- no speed change, no
frame interpolation. Title cards are synthetic (`drawtext` on black) and are
clearly not footage. Cutting one continuous take into labelled segments at
fixed timestamps is disclosed here, not presented as if 4 separate camera
rolls exist.

- **Total duration:** 17.57s (720x1280, 30fps, H.264, ~6.0MB) -- **well short
  of the 60-120s target** stated in the task, because only one ~13.6s source
  clip has been cleared. This is disclosed rather than padded with fabricated
  or slowed-down footage.
- **No missing-vest scenario is present anywhere in this compilation.**
  Nothing in this document or elsewhere should claim otherwise.
- **No true "restricted zone intrusion" event is baked into this video file**
  -- that requires configuring an actual zone polygon in the running system
  and observing the tracked worker's foot point against it during pipeline
  processing (see the vision pipeline's zone-polygon mechanism), using the
  barrier-rail-path portion of the 5.9-17.6s segment as the source footage.
  It is not a distinct video segment with its own title card.

## Real detector result on this compilation (honest, not curated)

`demo-assets/interview_compilation_annotated.mp4` was produced by
`backend/scripts/build_interview_annotated_video.py`, which runs the exact
registered production model (`ppe-yolo11n-1.1`, `models/registry.json`) at
its real tuned confidence thresholds (`backend/app/inference/ppe_thresholds.json`)
-- no threshold was lowered to make this clip look better than the system
actually performs. Detection summary across all 527 frames: person detected
in 356 frames, `helmet` in 144 frames, `vest` in 402 frames, **`no_helmet` in
0 frames**.

**The real detector never fires `no_helmet` anywhere in this clip, including
during the segment a human reviewer can clearly see is a bare-headed worker.**
Spot-checking one frame from that segment at an unfiltered confidence sweep
(conf=0.001) shows the model's raw `no_helmet` score peaks at **0.0494**,
just under the registered 0.05 threshold -- a genuine near-miss, not a
completely absent signal, but a miss nonetheless at the thresholds the system
actually runs with. This is disclosed here rather than hidden or fixed by
quietly lowering the threshold for this one clip. Consequences:

- The "MISSING PPE" title-carded segment is real, correctly labelled footage
  of a genuinely bare-headed worker -- but the live system, run against this
  clip with its real registered model, will **not** currently raise a
  `PPE_HELMET_OVERHEAD_VIOLATION` incident from it (no `no_helmet` evidence
  ever reaches the assignment/dwell logic in this clip).
  `helmet=UNKNOWN` (never `NON_COMPLIANT`) is the honest state that results.
- This is consistent with the model's own recorded weak point: `no_helmet`
  recall was 0.175-0.45 across held-out evaluations (`models/registry.json`,
  `models/evaluation/vision_v1.2_comparative_evaluation.json`) even on data
  from the training distribution; this real-world Indian construction-site
  clip is further out-of-distribution than either held-out split.
- `helmet` and `vest` detection do fire genuinely and correctly throughout
  the PPE-compliant segment, and the restricted-zone polygon (the existing
  default `restricted-zone` config, unmodified) does visibly overlap the
  walking path in this footage.

## Status

One genuinely licensed clip (Clip 1, own recording) is available and has been
assembled into the compilation above, covering the PPE-compliant and
missing-helmet scenarios, plus a weak restricted-zone-walk candidate.
**No clip covering the missing-vest scenario has been acquired**, and this
project's own sourcing rules forbid fabricating one or reusing footage with
unverified licensing to fill the gap -- see the disqualified Mixkit/Coverr
candidates above. See `docs/adr/0002-vision-v2-roadmap.md` for the standing
project decision to refuse a fabricated/placeholder interview video rather
than misrepresent its provenance.
