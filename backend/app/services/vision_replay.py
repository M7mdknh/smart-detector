"""Bundled-replay CV adapter status/query surface for the API layer.

The heavy YOLO11n + ByteTrack pipeline runs as a background worker
(app.inference.vision_pipeline) and writes VisionEvidence rows with
source=CV_MODEL. This module only reads back the latest state for API responses,
so routes stay decoupled from the inference process's lifecycle.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.models import VisionEvidenceRow

CAMERA_ID = "camera-1"


def get_replay_status(session: Session) -> dict:
    from app.inference.vision_pipeline import get_vision_worker

    worker = get_vision_worker()

    stmt = (
        select(VisionEvidenceRow)
        .where(VisionEvidenceRow.camera_id == CAMERA_ID, VisionEvidenceRow.source == "CV_MODEL")
        .order_by(VisionEvidenceRow.event_time.desc())
        .limit(20)
    )
    rows = session.execute(stmt).scalars().all()

    last_frame_age = None
    if rows:
        last_frame_age = (datetime.now(timezone.utc) - rows[0].event_time).total_seconds()

    return {
        "camera_id": CAMERA_ID,
        "status": worker.status,
        "camera_status": worker.camera_status,
        "detector_status": worker.detector_status,
        "model_version": worker.model_version,
        "last_frame_age_seconds": last_frame_age,
        "fps": worker.observed_fps,
        "tracks": [
            {
                "evidence_id": r.evidence_id, "track_id": r.track_id, "detected_class": r.detected_class,
                "confidence": r.confidence, "bbox": [r.bbox_x1, r.bbox_y1, r.bbox_x2, r.bbox_y2],
                "helmet_state": r.helmet_state, "vest_state": r.vest_state,
                "gas_zone_membership": r.gas_zone_membership, "overhead_zone_membership": r.overhead_zone_membership,
                "restricted_zone_membership": r.restricted_zone_membership,
                "event_time": r.event_time,
            }
            for r in rows
        ],
    }
