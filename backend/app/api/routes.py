from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import correlation_id, db_session
from app.contracts.enums import ComponentStatus, Gas
from app.contracts.errors import ApiError
from app.contracts.incident import IncidentActionRequest
from app.contracts.sensor import SensorHistoryResponse, SensorReadingIn, SensorReadingOut
from app.contracts.simulation import ScenarioLoadResponse, SimulationCommand, SimulationState
from app.inference.leak_model import get_leak_model
from app.services import incident_service
from app.services.ws_hub import hub
from app.simulation import engine
from app.simulation.presets import PRESETS, ZONE_ID
from app.storage.models import AuditEventRow, ForecastRow, IncidentRow, SensorReadingRow, SimulationCommandRow, SimulationRunRow

router = APIRouter(prefix="/api/v1")


@router.get("/health/live")
def health_live():
    return {"status": "ok"}


@router.get("/health/ready")
def health_ready(session: Annotated[Session, Depends(db_session)]):
    session.execute(select(1))
    return {"status": "ok"}


@router.get("/system/status")
def system_status(session: Annotated[Session, Depends(db_session)]):
    from app.inference.vision_pipeline import get_vision_worker

    run = engine._get_current_run(session)
    leak_model = get_leak_model()
    vision_worker = get_vision_worker()
    # "camera" reports the REAL CV pipeline's operational status (model loaded, replay
    # decoding), not run.camera_status -- that field is the simulator's fault-injection
    # control input and is unrelated to whether the actual detector is running. Conflating
    # the two previously made /system/status falsely report "camera": "HEALTHY" while the
    # real vision worker was UNAVAILABLE (caught during the Docker acceptance pass).
    # Camera (replay stream decoding) and the PPE detector (fine-tuned model loaded
    # and verified) are independent health signals -- the stream can be healthy while
    # the detector is MODEL_UNAVAILABLE (missing/corrupt artifact). "vision" is the
    # combined capability the dashboard should key off for PPE-evidence trust;
    # "camera"/"detector" are kept for finer-grained/legacy consumers.
    camera_status = ComponentStatus.HEALTHY.value if vision_worker.camera_status == "HEALTHY" else ComponentStatus.UNAVAILABLE.value
    detector_status = ComponentStatus.HEALTHY.value if vision_worker.detector_status == "OK" else ComponentStatus.UNAVAILABLE.value
    if camera_status == ComponentStatus.HEALTHY.value and detector_status == ComponentStatus.HEALTHY.value:
        vision_status = ComponentStatus.HEALTHY.value
    elif camera_status == ComponentStatus.HEALTHY.value:
        vision_status = ComponentStatus.DEGRADED.value
    else:
        vision_status = ComponentStatus.UNAVAILABLE.value
    vision_message = None
    if vision_status == ComponentStatus.DEGRADED.value:
        vision_message = "PPE model unavailable; camera stream is active but compliance cannot be determined."
    elif vision_status == ComponentStatus.UNAVAILABLE.value:
        vision_message = "Camera/replay stream unavailable; no vision evidence is being produced."
    return {
        "database": ComponentStatus.HEALTHY.value,
        "simulator": ComponentStatus.HEALTHY.value if run else ComponentStatus.UNAVAILABLE.value,
        "camera": camera_status,
        "detector": detector_status,
        "vision": vision_status,
        "vision_message": vision_message,
        "leak_model": ComponentStatus.HEALTHY.value if leak_model.status.value == "OK" else ComponentStatus.DEGRADED.value,
        "leak_model_status": leak_model.status.value,
    }


@router.post("/sensor-readings", status_code=201)
async def post_sensor_reading(
    reading: SensorReadingIn,
    session: Annotated[Session, Depends(db_session)],
    cid: Annotated[str, Depends(correlation_id)],
):
    from app.services import ingestion

    out, is_new = ingestion.ingest_reading(session, reading)
    if is_new:
        await hub.publish("sensor.reading.created", reading.event_time, {"zone_id": reading.zone_id, "value": reading.value}, cid)
    return out


@router.get("/zones/{zone_id}/readings", response_model=SensorHistoryResponse)
def zone_readings(
    zone_id: str,
    session: Annotated[Session, Depends(db_session)],
    gas: Gas,
    from_: Annotated[datetime, Query(alias="from")],
    to: datetime,
    limit: int = Query(default=500, le=2000),
    scenario_id: str | None = None,
):
    # Optional scenario_id (additive, backward-compatible): without it, two scenario
    # loads close together in real wall-clock time can have overlapping event_time
    # windows, so a from/to range alone can pull a few readings from the WRONG run into
    # the chart -- visible live as two anomalous spikes near "Now" after reloading a
    # scenario shortly after an accelerated run. The dashboard passes the current run's
    # scenario_id; direct API callers may omit it for the prior unscoped behavior.
    filters = [SensorReadingRow.zone_id == zone_id, SensorReadingRow.gas == gas.value, SensorReadingRow.event_time >= from_, SensorReadingRow.event_time <= to]
    if scenario_id:
        filters.append(SensorReadingRow.scenario_id == scenario_id)
    stmt = select(SensorReadingRow).where(*filters).order_by(SensorReadingRow.event_time).limit(limit)
    rows = session.execute(stmt).scalars().all()
    readings = [
        SensorReadingOut(
            reading_id=r.reading_id, sensor_id=r.sensor_id, zone_id=r.zone_id, scenario_id=r.scenario_id,
            gas=r.gas, value=r.value, unit=r.unit, event_time=r.event_time, ingested_at=r.ingested_at,
            source=r.source, quality=r.quality, sequence_number=r.sequence_number,
            correlation_id=r.correlation_id, fault_code=r.fault_code,
        )
        for r in rows
    ]
    return SensorHistoryResponse(zone_id=zone_id, gas=gas, readings=readings)


@router.get("/zones/{zone_id}/forecast/latest")
def zone_forecast_latest(zone_id: str, session: Annotated[Session, Depends(db_session)]):
    stmt = select(ForecastRow).where(ForecastRow.zone_id == zone_id).order_by(ForecastRow.generated_at.desc()).limit(1)
    row = session.execute(stmt).scalar_one_or_none()
    if row is None:
        raise ApiError("INSUFFICIENT_DATA", "no forecast available yet", status_code=404)
    return _forecast_row_to_dict(row)


def _forecast_row_to_dict(row: ForecastRow) -> dict:
    return {
        "forecast_id": row.forecast_id,
        "zone_id": row.zone_id,
        "gas": row.gas,
        "generated_at": row.generated_at,
        "based_on_event_time": row.based_on_event_time,
        "physics_model_version": row.physics_model_version,
        "ml_model_version": row.ml_model_version,
        "model_status": row.model_status,
        "gru_model_version": row.gru_model_version,
        "gru_status": row.gru_status,
        "horizon_minutes": row.horizon_minutes,
        "step_minutes": row.step_minutes,
        "points": row.points_json,
        "leak_probability": row.leak_probability,
        "leak_label": row.leak_label,
        "calibration_version": row.calibration_version,
        "crossings": row.crossings_json,
    }


@router.get("/vision/latest")
def vision_latest(session: Annotated[Session, Depends(db_session)]):
    from app.services.vision_replay import get_replay_status

    return get_replay_status(session)


@router.get("/vision/zones")
def vision_zones():
    """Authoritative, versioned camera-zone polygons (Phase 8) so the frontend
    can render the exact configured geometry rather than a hardcoded shape."""
    from app.inference.zone_config import get_zone_config

    config = get_zone_config()
    return {
        "version": config.version,
        "camera_id": config.camera_id,
        "zones": [{"id": z.id, "type": z.type, "label": z.label, "points": [list(p) for p in z.points]} for z in config.zones],
    }


@router.get("/incidents")
def list_incidents(
    session: Annotated[Session, Depends(db_session)],
    state: str | None = None,
    severity: str | None = None,
    zone_id: str | None = None,
):
    stmt = select(IncidentRow)
    if state:
        stmt = stmt.where(IncidentRow.state == state)
    if severity:
        stmt = stmt.where(IncidentRow.severity == severity)
    if zone_id:
        stmt = stmt.where(IncidentRow.zone_id == zone_id)
    stmt = stmt.order_by(IncidentRow.updated_at.desc()).limit(100)
    rows = session.execute(stmt).scalars().all()
    return [_incident_row_to_dict(r) for r in rows]


def _incident_row_to_dict(row: IncidentRow) -> dict:
    return {
        "incident_id": row.incident_id,
        "type": row.type,
        "zone_id": row.zone_id,
        "gas": row.gas,
        "severity": row.severity,
        "confidence": row.confidence,
        "state": row.state,
        "opened_at": row.opened_at,
        "updated_at": row.updated_at,
        "acknowledged_at": row.acknowledged_at,
        "resolved_at": row.resolved_at,
        "dedup_key": row.dedup_key,
        "reason_codes": row.reason_codes_json,
        "explanation": row.explanation,
        "recommended_action": row.recommended_action,
        "version": row.version,
    }


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str, session: Annotated[Session, Depends(db_session)]):
    row = session.get(IncidentRow, incident_id)
    if row is None:
        raise ApiError("NOT_FOUND", "incident not found", status_code=404)
    d = _incident_row_to_dict(row)
    d["evidence"] = [{"evidence_type": e.evidence_type, "evidence_id": e.evidence_id, "reason": e.reason} for e in row.evidence]
    d["evidence_images"] = [_evidence_image_to_dict(img) for img in row.evidence_images]
    allowed = [a.value for (s, a), _ in incident_service.ALLOWED_TRANSITIONS.items() if s.value == row.state]
    d["allowed_actions"] = allowed + ["COMMENT"]
    return d


def _evidence_image_to_dict(img) -> dict:
    return {
        "id": img.id,
        "incident_id": img.incident_id,
        "created_at": img.created_at,
        "reason": img.reason,
        "track_id": img.track_id,
        "ppe_helmet_state": img.ppe_helmet_state,
        "ppe_vest_state": img.ppe_vest_state,
        "confidence": img.confidence,
        "model_version": img.model_version,
        "source": img.source,
        "source_frame_id": img.source_frame_id,
        "sha256": img.sha256,
        "is_real_camera_frame": img.is_real_camera_frame,
        # Relative to API_BASE (frontend/src/api/client.ts), which already
        # includes the /api/v1 prefix -- a leading /api/v1 here doubled it
        # (frontend/tests/e2e/interview-demo.e2e.mjs caught this: the review
        # drawer's evidence <img> requested /api/v1/api/v1/... and silently
        # failed to load in every environment; no prior test ever opened the
        # drawer and checked the image actually loaded).
        "url": f"/incidents/{img.incident_id}/evidence",
    }


@router.get("/incidents/{incident_id}/evidence")
def get_incident_evidence(incident_id: str, session: Annotated[Session, Depends(db_session)]):
    """Serves the most recent annotated evidence image for this incident, looked
    up strictly by incident ID -- never a client-supplied filesystem path. 404 if
    the incident has no captured evidence, or if the file is missing on disk."""
    from fastapi.responses import FileResponse

    from app.settings import BACKEND_ROOT

    row = session.get(IncidentRow, incident_id)
    if row is None:
        raise ApiError("NOT_FOUND", "incident not found", status_code=404)
    if not row.evidence_images:
        raise ApiError("NOT_FOUND", "no evidence image captured for this incident", status_code=404)

    latest = row.evidence_images[-1]
    # file_path is stored relative to backend/ (e.g. "data/incident-evidence/<id>.jpg");
    # resolve it against the backend root, never against a client-controlled value.
    resolved = BACKEND_ROOT / latest.file_path
    if not resolved.exists():
        raise ApiError("EVIDENCE_FILE_MISSING", "evidence record exists but the image file is missing on disk", status_code=404)
    return FileResponse(str(resolved), media_type="image/jpeg", filename=f"{incident_id}-evidence.jpg")


@router.get("/incidents/{incident_id}/report.json")
def get_incident_report_json(incident_id: str, session: Annotated[Session, Depends(db_session)]):
    row = session.get(IncidentRow, incident_id)
    if row is None:
        raise ApiError("NOT_FOUND", "incident not found", status_code=404)
    d = _incident_row_to_dict(row)
    d["evidence"] = [{"evidence_type": e.evidence_type, "evidence_id": e.evidence_id, "reason": e.reason, "created_at": e.created_at} for e in row.evidence]
    d["evidence_images"] = [_evidence_image_to_dict(img) for img in row.evidence_images]
    audit_stmt = select(AuditEventRow).where(AuditEventRow.incident_id == incident_id).order_by(AuditEventRow.sequence)
    d["audit_trail"] = [
        {"audit_id": a.audit_id, "actor": a.actor, "action": a.action, "timestamp": a.timestamp, "previous_state": a.previous_state, "new_state": a.new_state, "comment": a.comment}
        for a in session.execute(audit_stmt).scalars()
    ]
    return d


@router.get("/incidents/{incident_id}/report.csv")
def get_incident_report_csv(incident_id: str, session: Annotated[Session, Depends(db_session)]):
    import csv
    import io

    from fastapi.responses import Response

    row = session.get(IncidentRow, incident_id)
    if row is None:
        raise ApiError("NOT_FOUND", "incident not found", status_code=404)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "incident_id", "type", "zone_id", "gas", "severity", "confidence", "state",
        "opened_at", "updated_at", "acknowledged_at", "resolved_at", "reason_codes",
        "explanation", "recommended_action", "version",
        "evidence_image_id", "evidence_image_reason", "evidence_image_track_id",
        "evidence_image_helmet_state", "evidence_image_vest_state", "evidence_image_model_version",
        "evidence_image_source", "evidence_image_sha256", "evidence_image_is_real_camera_frame",
    ])
    base = [
        row.incident_id, row.type, row.zone_id, row.gas, row.severity, row.confidence, row.state,
        row.opened_at.isoformat(), row.updated_at.isoformat(),
        row.acknowledged_at.isoformat() if row.acknowledged_at else "",
        row.resolved_at.isoformat() if row.resolved_at else "",
        ";".join(row.reason_codes_json or []), row.explanation, row.recommended_action, row.version,
    ]
    if row.evidence_images:
        for img in row.evidence_images:
            writer.writerow(base + [img.id, img.reason, img.track_id, img.ppe_helmet_state, img.ppe_vest_state, img.model_version, img.source, img.sha256, img.is_real_camera_frame])
    else:
        writer.writerow(base + ["", "", "", "", "", "", "", "", ""])

    return Response(content=buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={incident_id}-report.csv"})


@router.post("/incidents/{incident_id}/actions")
async def incident_action(
    incident_id: str,
    body: IncidentActionRequest,
    session: Annotated[Session, Depends(db_session)],
    cid: Annotated[str, Depends(correlation_id)],
):
    now = datetime.now(timezone.utc)
    row = incident_service.apply_action(session, incident_id, body.action, body.actor, body.comment, body.expected_version, now, cid)
    await hub.publish("incident.updated", now, {"incident_id": row.incident_id, "state": row.state, "version": row.version}, cid)
    await hub.publish("incident.audit.created", now, {"incident_id": row.incident_id, "action": body.action.value}, cid)
    return _incident_row_to_dict(row)


@router.get("/incidents/{incident_id}/audit")
def incident_audit(incident_id: str, session: Annotated[Session, Depends(db_session)]):
    stmt = select(AuditEventRow).where(AuditEventRow.incident_id == incident_id).order_by(AuditEventRow.sequence)
    rows = session.execute(stmt).scalars().all()
    return [
        {
            "audit_id": r.audit_id, "incident_id": r.incident_id, "actor": r.actor, "action": r.action,
            "timestamp": r.timestamp, "previous_state": r.previous_state, "new_state": r.new_state,
            "comment": r.comment, "correlation_id": r.correlation_id,
        }
        for r in rows
    ]


@router.get("/dashboard/snapshot")
def dashboard_snapshot(session: Annotated[Session, Depends(db_session)]):
    run = engine._get_current_run(session)

    # Scoped to the CURRENT run's scenario_id AND event_time <= run.event_time: without
    # both, "latest by event_time" can return data from a PREVIOUS run whose simulated
    # clock had been accelerated further into the future than the newly-reloaded run's
    # clock, silently showing stale readings/forecast after a scenario reload. scenario_id
    # alone is not enough -- reloading the SAME preset/seed (the common case: the default
    # demo always uses seed 42) produces the SAME scenario_id, so a second load's early
    # warm-start rows can still be shadowed by the first load's later, far-future-dated
    # rows sharing that scenario_id. Found live during the A05 acceptance pass twice:
    # first reloading a different preset, then again reloading the identical preset/seed.
    scenario_filter = (SensorReadingRow.scenario_id == run.scenario_id) if run else True
    time_filter = (SensorReadingRow.event_time <= run.event_time) if run else True

    forecast_stmt = select(ForecastRow).where(ForecastRow.zone_id == ZONE_ID).order_by(ForecastRow.generated_at.desc()).limit(1)
    if run:
        forecast_stmt = forecast_stmt.where(ForecastRow.generated_at <= run.event_time)
    forecast = session.execute(forecast_stmt).scalar_one_or_none()

    readings_stmt = (
        select(SensorReadingRow)
        .where(SensorReadingRow.zone_id == ZONE_ID, SensorReadingRow.gas == "CO2", scenario_filter, time_filter)
        .order_by(SensorReadingRow.event_time.desc())
        .limit(1)
    )
    latest_reading = session.execute(readings_stmt).scalar_one_or_none()

    incidents_stmt = select(IncidentRow).where(IncidentRow.is_active == True).order_by(IncidentRow.severity.desc(), IncidentRow.updated_at.desc())  # noqa: E712
    active_incidents = session.execute(incidents_stmt).scalars().all()

    from app.services.vision_replay import get_replay_status

    vision_status = get_replay_status(session)

    return {
        "server_time": datetime.now(timezone.utc),
        "simulation": _sim_state_dict(run) if run else None,
        "latest_reading": {
            "value": latest_reading.value, "event_time": latest_reading.event_time, "quality": latest_reading.quality, "source": latest_reading.source,
        } if latest_reading else None,
        "forecast": _forecast_row_to_dict(forecast) if forecast else None,
        "active_incidents": [_incident_row_to_dict(r) for r in active_incidents],
        "vision": vision_status,
        "model_versions": {
            "physics": "1.0",
            "risk_policy": "1.0",
            "leak_model_status": get_leak_model().status.value,
        },
    }


def _sim_state_dict(run: SimulationRunRow) -> dict:
    return {
        "run_id": run.run_id, "scenario_id": run.scenario_id, "preset": run.preset, "seed": run.seed,
        "generator_version": run.generator_version, "state": run.state, "speed": run.speed,
        "state_version": run.state_version, "event_time": run.event_time,
        "zone_volume_m3": run.zone_volume_m3, "inlet_co2_ppm": run.inlet_co2_ppm,
        "source_ppm_m3_per_h": run.source_ppm_m3_per_h, "ventilation_m3_per_h": run.ventilation_m3_per_h,
        "worker_x": run.worker_x, "worker_y": run.worker_y, "worker_helmet": run.worker_helmet,
        "worker_vest": run.worker_vest, "overhead_zone_active": run.overhead_zone_active,
        "camera_status": run.camera_status, "sensor_fault": run.sensor_fault,
    }


@router.get("/simulation/state")
def simulation_state(session: Annotated[Session, Depends(db_session)]):
    run = engine._get_current_run(session)
    if run is None:
        raise ApiError("VALIDATION_ERROR", "no scenario loaded", status_code=404)
    return _sim_state_dict(run)


@router.get("/simulation/presets")
def simulation_presets():
    return {"presets": list(PRESETS.keys())}


@router.post("/simulation/scenarios/{preset_id}/load")
async def load_scenario(preset_id: str, session: Annotated[Session, Depends(db_session)], cid: Annotated[str, Depends(correlation_id)], seed: int | None = None):
    run = engine.load_scenario(session, preset_id, seed)
    await hub.publish("simulation.state.updated", run.event_time, {"run_id": run.run_id, "state": run.state}, cid)
    return ScenarioLoadResponse(accepted=True, state=SimulationState(**_sim_state_dict(run)))


@router.post("/simulation/commands")
async def simulation_command(cmd: SimulationCommand, session: Annotated[Session, Depends(db_session)], cid: Annotated[str, Depends(correlation_id)]):
    run = engine._get_current_run(session)
    if run is None:
        raise ApiError("SIMULATION_STATE_CONFLICT", "no scenario loaded", status_code=409)

    # Idempotent by command_id, per api-and-data-specification.md: "A repeated identical
    # reading_id or command_id returns the original success." SimulationCommandRow existed
    # in the schema from the start but was never written to or checked -- found during the
    # A10 acceptance pass that a duplicate command_id silently re-executed (harmless for
    # most commands here since they're idempotent-by-nature, but not for the contract, and
    # not safe in general for a future non-idempotent command).
    existing_command = session.get(SimulationCommandRow, str(cmd.command_id))
    if existing_command is not None:
        return _sim_state_dict(run)

    if cmd.expected_state_version is not None and cmd.expected_state_version != run.state_version:
        raise ApiError("SIMULATION_STATE_CONFLICT", "stale state_version", status_code=409)

    if cmd.command == "start":
        engine.start(session, run)
    elif cmd.command == "pause":
        engine.pause(session, run)
    elif cmd.command == "reset":
        run = engine.reset(session, run)
    elif cmd.command == "set_speed":
        engine.set_speed(session, run, cmd.payload["speed"])
    elif cmd.command == "set_controls":
        engine.set_controls(session, run, cmd.payload.get("source_ppm_m3h"), cmd.payload.get("ventilation_m3h"))
    elif cmd.command == "set_worker":
        engine.set_worker(
            session, run, cmd.payload.get("x"), cmd.payload.get("y"), cmd.payload.get("helmet"), cmd.payload.get("vest"), cmd.payload.get("overhead_active")
        )
    else:
        raise ApiError("VALIDATION_ERROR", f"unknown command {cmd.command}", status_code=422)

    session.add(
        SimulationCommandRow(
            command_id=str(cmd.command_id), run_id=run.run_id, command=cmd.command, payload_json=cmd.payload,
            expected_state_version=cmd.expected_state_version, resulting_state_version=run.state_version,
            actor="HUMAN", created_at=run.event_time,
        )
    )
    session.commit()

    await hub.publish("simulation.state.updated", run.event_time, {"run_id": run.run_id, "state": run.state, "state_version": run.state_version}, cid)
    return _sim_state_dict(run)
