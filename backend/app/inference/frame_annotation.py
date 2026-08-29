"""Renders a real annotated video frame (boxes/labels/zones burned into the
actual pixels of a genuinely decoded camera/replay frame) -- as opposed to
app/services/evidence_image.py's schematic reconstruction, which is used only
when no real source frame exists (the simulator-driven `/dashboard` demo).

Pure function, no I/O: given one already-decoded BGR frame plus the same
detection/dwell state `vision_worker_impl.py` already computes, it draws:
  - a box + track ID + foot-point marker per detected person
  - a labelled, confidence-scored box per detected PPE item (helmet/vest/no_helmet)
  - each configured zone polygon, with its label
  - per-person PPE state (helmet/vest COMPLIANT/NON_COMPLIANT/UNKNOWN) and zone
    dwell seconds, near that person's box
  - a fixed top-left readout: model name/version and the frame's own event_time
  - an optional severity badge per track, when an incident is currently open
    for that track (never presented as if severity were a raw detector output)

Reused by both the offline interview-compilation renderer
(scripts/build_interview_annotated_video.py) and the live evidence-capture
path (app/services/evidence_image.py), so the two never drift apart.
"""

from __future__ import annotations

from datetime import datetime

import cv2
import numpy as np

from app.inference.vision_worker_impl import TrackDwell
from app.inference.zone_config import ZoneConfig

_PERSON_COLOR = (0, 220, 0)  # BGR
_PPE_COLORS = {"helmet": (255, 200, 0), "vest": (0, 165, 255), "no_helmet": (0, 0, 255)}
_ZONE_COLOR = (255, 0, 255)
_TEXT_COLOR = (255, 255, 255)
_TEXT_BG = (0, 0, 0)
_SEVERITY_COLORS = {"LOW": (0, 200, 200), "MEDIUM": (0, 140, 255), "HIGH": (0, 60, 255), "CRITICAL": (0, 0, 220)}

_FONT = cv2.FONT_HERSHEY_SIMPLEX


def _put_label(img, text: str, x: int, y: int, color=_TEXT_COLOR, scale: float = 0.45, thickness: int = 1) -> None:
    (tw, th), baseline = cv2.getTextSize(text, _FONT, scale, thickness)
    cv2.rectangle(img, (x, y - th - baseline - 2), (x + tw + 4, y + baseline), _TEXT_BG, -1)
    cv2.putText(img, text, (x + 2, y - baseline), _FONT, scale, color, thickness, cv2.LINE_AA)


def render_annotated_frame(
    frame_bgr: np.ndarray,
    persons: list[tuple[int | None, tuple[float, float, float, float], float]],
    ppe_candidates: list[tuple[str, tuple[float, float, float, float], float]],
    tracks: dict[int, TrackDwell],
    zone_config: ZoneConfig,
    model_version: str,
    event_time: datetime,
    frame_id: int,
    incident_severity_by_track: dict[int, str] | None = None,
) -> np.ndarray:
    img = frame_bgr.copy()
    h, w = img.shape[:2]
    incident_severity_by_track = incident_severity_by_track or {}

    for zone in zone_config.zones:
        pts = np.array([[int(x * w), int(y * h)] for x, y in zone.points], dtype=np.int32)
        cv2.polylines(img, [pts], isClosed=True, color=_ZONE_COLOR, thickness=2, lineType=cv2.LINE_AA)
        anchor = pts[0]
        _put_label(img, zone.label, int(anchor[0]) + 4, max(16, int(anchor[1]) + 16), color=_ZONE_COLOR)

    for name, box, conf in ppe_candidates:
        x1, y1, x2, y2 = int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)
        color = _PPE_COLORS.get(name, (200, 200, 200))
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        _put_label(img, f"{name} {conf:.2f}", x1, max(14, y1 - 4), color=color)

    for track_id, box, conf in persons:
        x1, y1, x2, y2 = int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)
        cv2.rectangle(img, (x1, y1), (x2, y2), _PERSON_COLOR, 2)

        foot_x, foot_y = (x1 + x2) // 2, y2
        cv2.circle(img, (foot_x, foot_y), 5, (255, 255, 255), -1)
        cv2.circle(img, (foot_x, foot_y), 5, (0, 0, 0), 1)

        id_label = f"ID {track_id}" if track_id is not None else "ID unknown"
        _put_label(img, f"person {conf:.2f}  {id_label}", x1, max(14, y1 - 4))

        info_lines = []
        dwell = tracks.get(track_id) if track_id is not None else None
        if dwell is not None:
            info_lines.append(f"helmet={dwell.helmet_state.value}  vest={dwell.vest_state.value}")
            zone_bits = []
            if dwell.gas_membership.value == "INSIDE":
                zone_bits.append("gas-zone")
            if dwell.overhead_membership.value == "INSIDE":
                zone_bits.append("overhead-zone")
            if dwell.restricted_membership.value == "INSIDE":
                since = dwell.restricted_in_since
                dwell_s = (event_time - since).total_seconds() if since else 0.0
                zone_bits.append(f"restricted-zone (dwell {dwell_s:.1f}s)")
            if zone_bits:
                info_lines.append(", ".join(zone_bits))
        else:
            info_lines.append("helmet=UNKNOWN  vest=UNKNOWN (tracker id unavailable)")

        severity = incident_severity_by_track.get(track_id) if track_id is not None else None
        if severity:
            info_lines.append(f"INCIDENT SEVERITY: {severity}")

        ty = y2 + 16
        for line in info_lines:
            color = _SEVERITY_COLORS.get(severity, _TEXT_COLOR) if line.startswith("INCIDENT") else _TEXT_COLOR
            _put_label(img, line, x1, ty, color=color)
            ty += 18

    header = f"{model_version}  |  {event_time.isoformat()}  |  frame {frame_id}"
    _put_label(img, header, 6, 20, scale=0.5)

    return img
