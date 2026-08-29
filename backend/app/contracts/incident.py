from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.contracts.enums import (
    Actor,
    Gas,
    IncidentAction,
    IncidentState,
    IncidentType,
    Severity,
)


class IncidentEvidenceRef(BaseModel):
    evidence_type: str  # "reading" | "forecast" | "vision" | "rule"
    evidence_id: str
    reason: str


class Incident(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: UUID
    type: IncidentType
    zone_id: str
    gas: Gas | None = None
    severity: Severity
    confidence: float | None = None

    state: IncidentState
    opened_at: datetime
    updated_at: datetime
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None

    dedup_key: str
    reason_codes: list[str]
    explanation: str
    recommended_action: str

    evidence: list[IncidentEvidenceRef] = []
    version: int


class IncidentActionRequest(BaseModel):
    action: IncidentAction
    actor: Actor = Actor.HUMAN
    comment: str | None = None
    expected_version: int


class AuditEvent(BaseModel):
    audit_id: UUID
    incident_id: UUID
    actor: Actor
    action: str
    timestamp: datetime
    previous_state: str | None
    new_state: str | None
    comment: str | None
    correlation_id: str | None
