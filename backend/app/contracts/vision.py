from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.enums import DetectionClass, EvidenceSource, PpeState, ZoneMembership


class VisionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    evidence_id: UUID
    camera_id: str
    zone_id: str | None = None

    frame_id: int
    event_time: datetime
    ingested_at: datetime
    source: EvidenceSource
    model_version: str

    track_id: int | None = None
    detected_class: DetectionClass
    confidence: float = Field(ge=0.0, le=1.0)
    bbox_x1: float
    bbox_y1: float
    bbox_x2: float
    bbox_y2: float

    helmet_state: PpeState = PpeState.UNKNOWN
    vest_state: PpeState = PpeState.UNKNOWN
    gas_zone_membership: ZoneMembership = ZoneMembership.UNKNOWN
    overhead_zone_membership: ZoneMembership = ZoneMembership.UNKNOWN
    dwell_seconds: float | None = None


class VisionLatestResponse(BaseModel):
    camera_id: str
    status: str
    model_version: str | None
    last_frame_age_seconds: float | None
    fps: float | None
    tracks: list[VisionEvidence]
