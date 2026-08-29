"""Renders and saves one annotated evidence image per logical incident event
(creation, or a meaningful severity escalation) -- never one per frame.

Honesty note (CLAUDE.md invariant #3, "no fake CV"): by default, incidents
this system opens for worker-safety conditions are driven by
SIMULATION_GROUND_TRUTH vision evidence (the bundled CV replay shows an
unrelated construction clip, never correlated with the simulated worker --
see app/services/incident_service.py's `_latest_vision_rows`). There is
therefore no real captured camera frame to attach to a ground-truth-driven
incident in that mode. Rather than fabricate a "camera frame" that never
existed, this module renders a labelled schematic snapshot (zone outline,
worker marker/box, burned-in text: incident type, severity, zone, track ID,
timestamp, PPE state, confidence, model/source, alert description) from the
same evidence data that drove the incident decision.

When settings.interview_demo_mode is on (see docs/INTERVIEW_DEMO.md) and the
triggering evidence row's source is CV_MODEL, a real captured frame DOES
exist -- the vision worker caches its own already-annotated frame
(app/inference/frame_cache.py) for exactly this purpose -- so that genuine
frame is saved instead of a schematic. If no cached frame is available near
the incident's timestamp (a genuine gap, e.g. the worker restarted), this
degrades honestly to the schematic rather than fabricating a capture; the
schematic image itself makes this fallback explicit in its burned-in text.
The image and every burned-in field are always clearly attributed to their
real source (SIMULATION_GROUND_TRUTH or CV_MODEL, whichever produced the
evidence row) -- never presented as an unlabelled camera capture.
"""

import hashlib
import io
import uuid
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from app.settings import get_settings
from app.storage.models import IncidentEvidenceImageRow, IncidentRow, VisionEvidenceRow

IMG_W, IMG_H = 640, 480

# Incident types for which an evidence image is meaningful: all require a
# person/track association (vision-derived). Pure sensor conditions (e.g.
# CO2_VENTILATION_ADVISORY with no person present) have no track to depict.
EVIDENCE_ELIGIBLE_TYPES = {
    "PERSON_IN_PREDICTED_GAS_RISK",
    "PPE_HELMET_OVERHEAD_VIOLATION",
    "PPE_VEST_VIOLATION",
    "PERSON_IN_RESTRICTED_ZONE",
}


@dataclass
class EvidenceContext:
    vision_row: VisionEvidenceRow | None
    reason: str  # "CREATED" | "SEVERITY_ESCALATED"


def _font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _draw_zone_box(draw: ImageDraw.ImageDraw, membership: str | None, label: str, box_norm: tuple[float, float, float, float], color):
    x1, y1, x2, y2 = (box_norm[0] * IMG_W, box_norm[1] * IMG_H, box_norm[2] * IMG_W, box_norm[3] * IMG_H)
    draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
    draw.text((x1 + 4, y1 + 4), label, fill=color, font=_font(14))


def render_evidence_image(incident: IncidentRow, ctx: EvidenceContext) -> Image.Image:
    img = Image.new("RGB", (IMG_W, IMG_H), color=(24, 26, 30))
    draw = ImageDraw.Draw(img)

    row = ctx.vision_row
    # Approximate normalized zone regions for the schematic (matches the demo
    # left/right split documented in zone_config.json); purely illustrative.
    if incident.type == "PERSON_IN_PREDICTED_GAS_RISK":
        zone_box, zone_color, zone_label = (0.5, 0.0, 1.0, 1.0), (220, 90, 40), "GAS EXPOSURE ZONE"
    elif incident.type == "PPE_HELMET_OVERHEAD_VIOLATION":
        zone_box, zone_color, zone_label = (0.0, 0.0, 0.5, 1.0), (220, 170, 30), "OVERHEAD WORK ZONE"
    elif incident.type == "PERSON_IN_RESTRICTED_ZONE":
        zone_box, zone_color, zone_label = (0.3, 0.6, 0.7, 1.0), (200, 40, 200), "RESTRICTED ZONE"
    else:
        zone_box, zone_color, zone_label = (0.0, 0.0, 1.0, 1.0), (60, 140, 220), "MANDATORY-PPE ZONE"

    _draw_zone_box(draw, None, zone_label, zone_box, zone_color)

    cx = (zone_box[0] + zone_box[2]) / 2 * IMG_W
    cy = (zone_box[1] + zone_box[3]) / 2 * IMG_H
    box_half = 60
    person_box = [cx - box_half, cy - box_half * 1.4, cx + box_half, cy + box_half * 1.4]
    draw.rectangle(person_box, outline=(80, 220, 120), width=3)
    track_label = f"track_id={row.track_id}" if row and row.track_id is not None else "track_id=unknown"
    draw.text((person_box[0], person_box[1] - 18), track_label, fill=(80, 220, 120), font=_font(14))

    lines = [
        f"ALERT: {incident.type}",
        f"Severity: {incident.severity}   Reason: {ctx.reason}",
        f"Zone: {incident.zone_id}",
        f"Timestamp (event_time): {incident.updated_at.isoformat()}",
        f"Helmet: {row.helmet_state if row else 'UNKNOWN'}   Vest: {row.vest_state if row else 'UNKNOWN'}",
        f"Confidence: {row.confidence:.2f}" if row else "Confidence: n/a",
        f"Source: {row.source if row else 'n/a'} (model_version={row.model_version if row else 'n/a'})",
        incident.explanation[:90],
        "NOTE: schematic reconstruction from evidence data, not a raw camera capture.",
    ]
    y = IMG_H - 18 * len(lines) - 8
    for line in lines:
        draw.text((8, y), line, fill=(230, 230, 230), font=_font(13))
        y += 18

    return img


def _try_real_frame_bytes(row: VisionEvidenceRow | None, incident: IncidentRow) -> bytes | None:
    """Returns real annotated-frame JPEG bytes captured by the vision worker
    (app/inference/frame_cache.py) if interview_demo_mode is on, the triggering
    row is genuinely CV_MODEL, and a recent-enough frame was cached -- else
    None (never fabricated).

    Staleness is anchored on REAL wall-clock time, not `incident.updated_at`
    (the simulation clock, which the caller advances by whole simulated
    minutes per tick -- see app/simulation/engine.py::tick). The vision worker
    always caches frames with real wall-clock timestamps
    (app/inference/frame_cache.py), so anchoring on the simulation clock would
    make every cached frame look stale within seconds of a scenario running,
    even one genuinely captured a moment ago -- found live via
    `make interview-demo` reporting real incidents but zero real evidence
    frames despite a healthy, actively-processing vision worker."""
    if row is None or row.source != "CV_MODEL":
        return None
    if not get_settings().interview_demo_mode:
        return None
    try:
        from datetime import datetime, timezone

        from app.inference.frame_cache import get_latest_frame

        cached = get_latest_frame(row.camera_id, datetime.now(timezone.utc))
        if cached is None:
            return None
        jpeg_bytes, _frame_id, _event_time = cached
        return jpeg_bytes
    except Exception:
        return None


def save_evidence_image(session, incident: IncidentRow, ctx: EvidenceContext) -> IncidentEvidenceImageRow:
    """Renders (or, when a genuine CV_MODEL-sourced frame is available in
    interview_demo_mode, uses the real captured frame verbatim), writes to disk
    under settings.incident_evidence_dir, and records a row in
    incident_evidence_images. Never raises on a rendering hiccup in a way that
    would fail the surrounding incident transaction -- callers should treat
    this as best-effort and log failures, since evidence capture must never
    block the safety-critical incident write itself."""
    settings = get_settings()
    settings.incident_evidence_dir.mkdir(parents=True, exist_ok=True)

    file_id = uuid.uuid4().hex[:8]
    filename = f"{incident.incident_id}-{file_id}.jpg"
    path = settings.incident_evidence_dir / filename

    real_frame = _try_real_frame_bytes(ctx.vision_row, incident)
    is_real_frame = real_frame is not None
    if is_real_frame:
        path.write_bytes(real_frame)
    else:
        img = render_evidence_image(incident, ctx)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        path.write_bytes(buf.getvalue())

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    row = ctx.vision_row
    image_row = IncidentEvidenceImageRow(
        id=str(uuid.uuid4()),
        incident_id=incident.incident_id,
        created_at=incident.updated_at,
        reason=ctx.reason,
        incident_type=incident.type,
        severity=incident.severity,
        zone_id=incident.zone_id,
        track_id=row.track_id if row else None,
        ppe_helmet_state=row.helmet_state if row else None,
        ppe_vest_state=row.vest_state if row else None,
        confidence=row.confidence if row else None,
        model_version=row.model_version if row else "n/a",
        source=row.source if row else "n/a",
        source_frame_id=row.frame_id if row else None,
        file_path=f"data/incident-evidence/{filename}",
        sha256=digest,
        is_real_camera_frame=is_real_frame,
    )
    session.add(image_row)
    return image_row
