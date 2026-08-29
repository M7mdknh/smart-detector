---
name: vision-worker-safety
description: Implement or evaluate personnel/PPE detection, anonymous tracking, camera/replay adapters, hazard-zone logic, or vision evidence for Factory Safety Sentinel. Use for actual CV and vision-derived events, not simulator rendering or gas forecasting.
---

# Vision Worker Safety

Read `CLAUDE.md`, especially evidence provenance, privacy, scope, and vision rules. Read [model specification](references/model-specification.md) for the frozen dataset/classes, YOLO11n settings, ByteTrack config, association, dwell, and evaluation.

## MVP Outcome

Turn the bundled video or optional webcam into versioned `VisionEvidence` for persons, helmets, vests, anonymous tracks, PPE state, zone membership, and dwell time. Keep safety interpretation in the risk engine.

## Pipeline

1. Decode frames with timestamps.
2. Run the selected detector adapter.
3. Track persons with anonymous session IDs.
4. Associate head/helmet evidence with the correct person.
5. Calculate zone entry using the person's ground-contact point and configured polygons.
6. Apply persistence/dwell logic to reduce single-frame violations.
7. Emit evidence with model version, confidence, frame/camera metadata, and `CV_MODEL` provenance.

## Frozen MVP Model

- Implement fine-tuned YOLO11n with ByteTrack for P0 while keeping the detector API replaceable.
- Use the credential-free Construction-PPE dataset and the reduced runtime class map in the model specification.
- Evaluate on the untouched published test split and a small factory-like replay set when available.
- Select/tune thresholds using person/helmet recall, PPE-event F1, latency, and error analysis rather than vendor COCO mAP.
- Bundle the chosen artifact or provide a credential-free reproducible retrieval step with checksum.

## Safety and Privacy

- Never implement face recognition or persistent identity.
- Do not infer PPE absence from a single missing box.
- Keep `UNKNOWN`, `COMPLIANT`, and `NON_COMPLIANT` distinct.
- A helmet applies to overhead-impact risk; it does not mitigate gas exposure.
- Missing vest is inferred only after persistent failed association in a required-vest zone; begin as `UNKNOWN`.
- Camera/model outage produces degraded evidence, not a claim that the scene is safe.
- Label replay, live camera, and simulation-ground-truth sources accurately.

## Evaluation

Report per-class precision/recall/mAP, PPE-event precision/recall/F1, track fragmentation or ID consistency when meaningful, transient-occlusion errors, and end-to-end inference latency. Include difficult examples such as small helmets, crowding, partial occlusion, lighting change, and out-of-domain footage.

## Do Not

- Attempt falling-tool trajectory prediction in P0.
- Train an abstract `unsafe_worker` class.
- Let CV directly open a critical gas incident without sensor/risk policy.
- Present simulator coordinates as model detections.
