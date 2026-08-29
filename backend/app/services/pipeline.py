"""Orchestrates ingestion -> forecast -> exposure -> risk -> incidents for one zone/tick.

Returns a list of (event_type, event_time, payload) tuples for the caller to
publish over WebSocket *after* this function's DB transactions have committed.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.contracts.enums import Severity
from app.services import forecast_service, incident_service
from app.storage.models import SimulationRunRow

SEVERITY_RANK = {Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3, Severity.CRITICAL: 4}


def run_risk_pipeline(session: Session, run: SimulationRunRow, zone_id: str, now: datetime, camera_degraded: bool = False) -> list[tuple[str, datetime, dict]]:
    events: list[tuple[str, datetime, dict]] = []

    forecast = forecast_service.build_forecast(session, run, now)
    if forecast is None:
        return events

    events.append(("forecast.updated", now, {"forecast_id": forecast.forecast_id, "zone_id": forecast.zone_id, "leak_label": forecast.leak_label, "model_status": forecast.model_status}))

    exposure = forecast_service.exposure_snapshot(session, zone_id, now)
    exposure["current_ppm"] = _current_ppm(session, zone_id, now)

    inputs = incident_service.build_risk_inputs(session, forecast, exposure, zone_id, now, camera_degraded)

    # Fixed scope "GAS_RISK" (not the fluctuating incident_type) so one evolving incident
    # tracks the CO2 condition as it escalates/de-escalates, instead of leaving a stale
    # lower-severity incident (e.g. ventilation advisory) open after conditions worsen.
    decision = evaluate_gas_risk_wrapper(inputs)
    if decision is not None:
        row, created = incident_service.upsert_incident(
            session, decision, zone_id, "CO2", forecast.leak_probability, "GAS_RISK", now,
            [("forecast", forecast.forecast_id, "forecast crossing"), ("reading", forecast.based_on_event_time.isoformat(), "latest observed reading")],
        )
        events.append((("incident.created" if created else "incident.updated"), now, {"incident_id": row.incident_id, "severity": row.severity, "type": row.type}))

    for decision in evaluate_ppe_risk_wrapper(inputs):
        row, created = incident_service.upsert_incident(session, decision, zone_id, None, None, decision.incident_type.value, now, [])
        events.append((("incident.created" if created else "incident.updated"), now, {"incident_id": row.incident_id, "severity": row.severity, "type": row.type}))

    camera_decision = evaluate_camera_wrapper(inputs)
    if camera_decision is not None:
        row, created = incident_service.upsert_incident(session, camera_decision, zone_id, None, None, "camera", now, [])
        events.append((("incident.created" if created else "incident.updated"), now, {"incident_id": row.incident_id, "severity": row.severity, "type": row.type}))

    return events


def _current_ppm(session: Session, zone_id: str, now: datetime) -> float:
    from sqlalchemy import select

    from app.storage.models import SensorReadingRow

    stmt = (
        select(SensorReadingRow)
        .where(SensorReadingRow.zone_id == zone_id, SensorReadingRow.gas == "CO2", SensorReadingRow.event_time <= now)
        .order_by(SensorReadingRow.event_time.desc())
        .limit(1)
    )
    row = session.execute(stmt).scalar_one_or_none()
    return row.value if row else 0.0


def evaluate_gas_risk_wrapper(inputs):
    from app.domain.risk.policy import evaluate_gas_risk

    return evaluate_gas_risk(inputs)


def evaluate_ppe_risk_wrapper(inputs):
    from app.domain.risk.policy import evaluate_ppe_risk

    return evaluate_ppe_risk(inputs)


def evaluate_camera_wrapper(inputs):
    from app.domain.risk.policy import evaluate_camera_status

    return evaluate_camera_status(inputs)
