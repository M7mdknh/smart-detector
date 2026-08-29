import uuid
from datetime import datetime

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.db import Base, UTCDateTime


def _uuid() -> str:
    return str(uuid.uuid4())


class SensorReadingRow(Base):
    __tablename__ = "sensor_readings"

    reading_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sensor_id: Mapped[str] = mapped_column(String(64), index=True)
    zone_id: Mapped[str] = mapped_column(String(64), index=True)
    scenario_id: Mapped[str] = mapped_column(String(64), index=True)
    gas: Mapped[str] = mapped_column(String(16))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16))
    event_time: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    ingested_at: Mapped[datetime] = mapped_column(UTCDateTime)
    source: Mapped[str] = mapped_column(String(16))
    quality: Mapped[str] = mapped_column(String(16))
    sequence_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    fault_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload_hash: Mapped[str] = mapped_column(String(64))

    __table_args__ = (UniqueConstraint("reading_id", name="uq_reading_id"),)


class ForecastRow(Base):
    __tablename__ = "forecasts"

    forecast_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    zone_id: Mapped[str] = mapped_column(String(64), index=True)
    gas: Mapped[str] = mapped_column(String(16))
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    based_on_event_time: Mapped[datetime] = mapped_column(UTCDateTime)
    physics_model_version: Mapped[str] = mapped_column(String(32))
    ml_model_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model_status: Mapped[str] = mapped_column(String(16))
    gru_model_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gru_status: Mapped[str] = mapped_column(String(16), default="UNAVAILABLE")
    horizon_minutes: Mapped[int] = mapped_column(Integer, default=60)
    step_minutes: Mapped[int] = mapped_column(Integer, default=5)
    points_json: Mapped[dict] = mapped_column(JSON)
    leak_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    leak_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    calibration_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    feature_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    crossings_json: Mapped[dict] = mapped_column(JSON)


class VisionEvidenceRow(Base):
    __tablename__ = "vision_evidence"

    evidence_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    camera_id: Mapped[str] = mapped_column(String(64), index=True)
    zone_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    frame_id: Mapped[int] = mapped_column(Integer)
    event_time: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    ingested_at: Mapped[datetime] = mapped_column(UTCDateTime)
    source: Mapped[str] = mapped_column(String(32))
    model_version: Mapped[str] = mapped_column(String(32))
    track_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    detected_class: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[float] = mapped_column(Float)
    bbox_x1: Mapped[float] = mapped_column(Float)
    bbox_y1: Mapped[float] = mapped_column(Float)
    bbox_x2: Mapped[float] = mapped_column(Float)
    bbox_y2: Mapped[float] = mapped_column(Float)
    helmet_state: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    vest_state: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    gas_zone_membership: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    overhead_zone_membership: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    dwell_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)


class IncidentRow(Base):
    __tablename__ = "incidents"

    incident_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    type: Mapped[str] = mapped_column(String(64))
    zone_id: Mapped[str] = mapped_column(String(64), index=True)
    gas: Mapped[str | None] = mapped_column(String(16), nullable=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    state: Mapped[str] = mapped_column(String(16), index=True)
    opened_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    dedup_key: Mapped[str] = mapped_column(String(128), index=True)
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    reason_codes_json: Mapped[list] = mapped_column(JSON)
    explanation: Mapped[str] = mapped_column(String(1024))
    recommended_action: Mapped[str] = mapped_column(String(512))
    version: Mapped[int] = mapped_column(Integer, default=1)

    evidence: Mapped[list["IncidentEvidenceRow"]] = relationship(back_populates="incident")
    audit_events: Mapped[list["AuditEventRow"]] = relationship(back_populates="incident", order_by="AuditEventRow.sequence")

    __table_args__ = (UniqueConstraint("dedup_key", "is_active", name="uq_active_dedup"),)


class IncidentEvidenceRow(Base):
    __tablename__ = "incident_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    incident_id: Mapped[str] = mapped_column(String(36), ForeignKey("incidents.incident_id"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(16))
    evidence_id: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)

    incident: Mapped["IncidentRow"] = relationship(back_populates="evidence")


class AuditEventRow(Base):
    __tablename__ = "audit_events"

    # Server-generated, globally monotonically increasing INTEGER PRIMARY KEY -- the
    # audit trail's TRUE causal/insertion order (SQLAlchemy autoincrement requires the
    # actual primary key; a separate non-PK "sequence" column would not auto-populate).
    # `timestamp` alone is not reliable for ordering: SYSTEM events are stamped with
    # the simulated event_time while HUMAN actions are stamped with real wall-clock
    # time, and an accelerated simulation (up to 300x) can put the simulated clock
    # hours ahead of real time within seconds, so a human's real-time action can sort
    # BEFORE a system event that actually happened first. Found live via the guided
    # demo script (Phase 6): ACKNOWLEDGE/RESOLVE appeared before the OPENED event they
    # followed. `sequence` is what the API orders by; `audit_id` remains the stable
    # business-key UUID exposed over the API; `timestamp` remains informational.
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_id: Mapped[str] = mapped_column(String(36), unique=True, index=True, default=_uuid)
    incident_id: Mapped[str] = mapped_column(String(36), ForeignKey("incidents.incident_id"), index=True)
    actor: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(32))
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    previous_state: Mapped[str | None] = mapped_column(String(16), nullable=True)
    new_state: Mapped[str | None] = mapped_column(String(16), nullable=True)
    comment: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    incident: Mapped["IncidentRow"] = relationship(back_populates="audit_events")


class SimulationRunRow(Base):
    __tablename__ = "simulation_runs"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    scenario_id: Mapped[str] = mapped_column(String(64), index=True)
    preset: Mapped[str] = mapped_column(String(64))
    seed: Mapped[int] = mapped_column(Integer)
    generator_version: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(16))
    speed: Mapped[int] = mapped_column(Integer, default=1)
    state_version: Mapped[int] = mapped_column(Integer, default=1)
    event_time: Mapped[datetime] = mapped_column(UTCDateTime)
    zone_volume_m3: Mapped[float] = mapped_column(Float)
    inlet_co2_ppm: Mapped[float] = mapped_column(Float)
    source_ppm_m3_per_h: Mapped[float] = mapped_column(Float)
    ventilation_m3_per_h: Mapped[float] = mapped_column(Float)
    last_true_ppm: Mapped[float] = mapped_column(Float, default=450.0)
    worker_x: Mapped[float] = mapped_column(Float, default=0.0)
    worker_y: Mapped[float] = mapped_column(Float, default=0.0)
    worker_helmet: Mapped[bool] = mapped_column(default=True)
    worker_vest: Mapped[bool] = mapped_column(default=True)
    overhead_zone_active: Mapped[bool] = mapped_column(default=False)
    camera_status: Mapped[str] = mapped_column(String(16), default="HEALTHY")
    sensor_fault: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_current: Mapped[bool] = mapped_column(default=True, index=True)


class SimulationCommandRow(Base):
    __tablename__ = "simulation_commands"

    command_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    command: Mapped[str] = mapped_column(String(32))
    payload_json: Mapped[dict] = mapped_column(JSON)
    expected_state_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resulting_state_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor: Mapped[str] = mapped_column(String(16), default="HUMAN")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class ModelRegistryRow(Base):
    __tablename__ = "model_registry"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(32))
    artifact_path: Mapped[str] = mapped_column(String(256))
    sha256: Mapped[str] = mapped_column(String(64))
    training_data_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metrics_path: Mapped[str | None] = mapped_column(String(256), nullable=True)
    load_status: Mapped[str] = mapped_column(String(16), default="UNAVAILABLE")
    loaded_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
