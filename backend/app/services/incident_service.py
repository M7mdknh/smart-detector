"""Incident deduplication, state transitions, and audit trail.

Transaction shape: upsert/deduplicate incident -> attach evidence -> append audit
-> commit -> publish (publish happens in the caller, after commit).
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.enums import Actor, CrossingOutcome, IncidentAction, IncidentState, Severity, ZoneMembership
from app.contracts.errors import ApiError
from app.domain.risk.policy import RiskDecision, RiskInputs
from app.logging_config import get_logger
from app.settings import get_settings
from app.storage.models import AuditEventRow, ForecastRow, IncidentEvidenceRow, IncidentRow, VisionEvidenceRow

logger = get_logger(__name__)

_SEVERITY_RANK = {Severity.LOW.value: 1, Severity.MEDIUM.value: 2, Severity.HIGH.value: 3, Severity.CRITICAL.value: 4}

_MEMBERSHIP_FIELD_BY_TYPE = {
    "PERSON_IN_PREDICTED_GAS_RISK": "gas_zone_membership",
    "PPE_HELMET_OVERHEAD_VIOLATION": "overhead_zone_membership",
    "PERSON_IN_RESTRICTED_ZONE": "restricted_zone_membership",
    # PPE_VEST_VIOLATION has no dedicated zone-membership column (vest applies
    # per configured mandatory-vest zone, not tracked as its own membership field).
}


def _primary_vision_row(session: Session, zone_id: str, now: datetime, incident_type: str) -> VisionEvidenceRow | None:
    """Picks the vision-evidence row most relevant to a just-opened/escalated
    incident, for evidence-image capture -- see app/services/evidence_image.py."""
    rows = [v for v in _latest_vision_rows(session, zone_id, now) if v.detected_class == "person"]
    if not rows:
        return None
    field = _MEMBERSHIP_FIELD_BY_TYPE.get(incident_type)
    if field:
        matching = [v for v in rows if getattr(v, field, None) == ZoneMembership.INSIDE.value]
        if matching:
            return matching[0]
    return rows[0]


def _maybe_capture_evidence_image(session: Session, row: IncidentRow, zone_id: str, now: datetime, reason: str) -> None:
    from app.services.evidence_image import EVIDENCE_ELIGIBLE_TYPES, EvidenceContext, save_evidence_image

    if row.type not in EVIDENCE_ELIGIBLE_TYPES:
        return
    try:
        vision_row = _primary_vision_row(session, zone_id, now, row.type)
        save_evidence_image(session, row, EvidenceContext(vision_row=vision_row, reason=reason))
    except Exception:
        # Best-effort: evidence capture must never fail the safety-critical incident write.
        logger.exception("failed to capture incident evidence image", extra={"extra_fields": {"incident_id": row.incident_id}})


ALLOWED_TRANSITIONS = {
    (IncidentState.OPEN, IncidentAction.ACKNOWLEDGE): IncidentState.ACKNOWLEDGED,
    (IncidentState.OPEN, IncidentAction.RESOLVE): IncidentState.RESOLVED,
    (IncidentState.ACKNOWLEDGED, IncidentAction.INVESTIGATE): IncidentState.INVESTIGATING,
    (IncidentState.ACKNOWLEDGED, IncidentAction.RESOLVE): IncidentState.RESOLVED,
    (IncidentState.INVESTIGATING, IncidentAction.RESOLVE): IncidentState.RESOLVED,
}


def _dedup_key(zone_id: str, scope: str) -> str:
    """`scope` alone identifies the deduplication family (e.g. "GAS_RISK", not the
    fluctuating incident_type) so one incident evolves through severities instead of
    a lower-severity incident staying open when a higher one supersedes it."""
    return f"{zone_id}:{scope}"


def _latest_vision_rows(session: Session, zone_id: str, now: datetime, window_seconds: float = 30.0) -> list[VisionEvidenceRow]:
    # Only SIMULATION_GROUND_TRUTH drives incident logic in P0: the bundled CV replay
    # shows an unrelated construction clip, not this simulated worker, so letting it
    # open/clear incidents about "the" worker would be misleading (CLAUDE.md invariant #3).
    # CV_MODEL evidence still populates the camera panel independently, with its own provenance badge.
    since = now - timedelta(seconds=window_seconds)
    stmt = select(VisionEvidenceRow).where(
        VisionEvidenceRow.zone_id == zone_id,
        VisionEvidenceRow.event_time >= since,
        VisionEvidenceRow.event_time <= now,  # exclude rows from a different run whose clock ran ahead of `now`
        VisionEvidenceRow.source == "SIMULATION_GROUND_TRUTH",
    ).order_by(VisionEvidenceRow.event_time.desc())
    return list(session.execute(stmt).scalars())


def build_risk_inputs(session: Session, forecast: ForecastRow, exposure: dict, zone_id: str, now: datetime, camera_degraded: bool) -> RiskInputs:
    settings = get_settings()
    crossings = {c["threshold_name"]: c for c in forecast.crossings_json}
    action = crossings.get("NIOSH_ACTION_5000", {})
    idlh = crossings.get("NIOSH_IDLH_40000", {})
    advisory = crossings.get("INTERNAL_ADVISORY_1000", {})

    current_ppm = forecast.points_json[0]["physics_ppm"] if forecast.points_json else 0.0
    # use the actual last observed reading value stored on forecast.based_on_event_time proxy:
    current_ppm = exposure.get("current_ppm", current_ppm)

    vision_rows = _latest_vision_rows(session, zone_id, now)
    person_rows = [v for v in vision_rows if v.detected_class == "person"]
    person_in_gas_zone = any(v.gas_zone_membership == ZoneMembership.INSIDE.value for v in person_rows)
    person_zone_unknown = camera_degraded or not person_rows

    helmet_violation = any(
        v.overhead_zone_membership == ZoneMembership.INSIDE.value and v.helmet_state == "NON_COMPLIANT" for v in person_rows
    )
    vest_violation = any(v.vest_state == "NON_COMPLIANT" for v in person_rows)
    restricted_zone_violation = any(v.restricted_zone_membership == ZoneMembership.INSIDE.value for v in person_rows)

    return RiskInputs(
        current_co2_ppm=current_ppm,
        short_term_avg_ppm=exposure.get("short_term_avg_ppm"),
        action_crossing_outcome=CrossingOutcome(action.get("outcome", "INSUFFICIENT_DATA")),
        action_crossing_minutes=action.get("minutes_to_cross"),
        idlh_crossing_outcome=CrossingOutcome(idlh.get("outcome", "INSUFFICIENT_DATA")),
        idlh_crossing_minutes=idlh.get("minutes_to_cross"),
        person_in_gas_zone=person_in_gas_zone,
        person_zone_unknown=person_zone_unknown,
        ventilation_advisory=advisory.get("outcome") in ("ALREADY_EXCEEDED", "CROSSING_EXPECTED"),
        niosh_short_term_ppm=settings.niosh_short_term_ppm,
        niosh_idlh_ppm=settings.niosh_idlh_ppm,
        helmet_violation_overhead=helmet_violation,
        vest_violation_mandatory_zone=vest_violation,
        restricted_zone_violation=restricted_zone_violation,
        sensor_unreliable=False,
        camera_degraded=camera_degraded,
    )


def upsert_incident(session: Session, decision: RiskDecision, zone_id: str, gas: str | None, confidence: float | None, scope: str, now: datetime, evidence_refs: list[tuple[str, str, str]]) -> tuple[IncidentRow, bool]:
    dedup_key = _dedup_key(zone_id, scope)
    stmt = select(IncidentRow).where(IncidentRow.dedup_key == dedup_key, IncidentRow.is_active == True)  # noqa: E712
    existing = session.execute(stmt).scalar_one_or_none()

    if existing is not None:
        changed = existing.severity != decision.severity.value or existing.type != decision.incident_type.value
        escalated = changed and _SEVERITY_RANK.get(decision.severity.value, 0) > _SEVERITY_RANK.get(existing.severity, 0)
        existing.type = decision.incident_type.value
        existing.severity = decision.severity.value
        existing.confidence = confidence
        existing.updated_at = now
        existing.reason_codes_json = decision.reason_codes
        existing.explanation = decision.explanation
        existing.recommended_action = decision.recommended_action
        # `version` is optimistic-concurrency protection for the human review workflow
        # (routes.py compares it against the client's expected_version on ACKNOWLEDGE/
        # INVESTIGATE/RESOLVE), not a generic revision counter. This function runs on
        # every sensor/vision re-evaluation cycle -- often every few seconds under an
        # accelerated simulation -- and re-affirms the same severity/type on most of
        # those cycles. Bumping version unconditionally raced a version a human (or
        # scripts/guided_demo.py) had just fetched ahead of them, producing spurious
        # VERSION_CONFLICT 409s on routine actions -- found live running the guided
        # demo. Only bump it when the incident's severity or type actually changed.
        if changed:
            existing.version += 1
        for etype, eid, reason in evidence_refs:
            session.add(IncidentEvidenceRow(incident_id=existing.incident_id, evidence_type=etype, evidence_id=eid, reason=reason, created_at=now))
        if changed:
            session.add(
                AuditEventRow(
                    incident_id=existing.incident_id,
                    actor=Actor.SYSTEM.value,
                    action="SEVERITY_CHANGED",
                    timestamp=now,
                    previous_state=existing.state,
                    new_state=existing.state,
                    comment=f"Severity updated to {decision.severity.value}: {decision.explanation}",
                    correlation_id=None,
                )
            )
        session.commit()
        if escalated:
            _maybe_capture_evidence_image(session, existing, zone_id, now, "SEVERITY_ESCALATED")
            session.commit()
        return existing, False

    row = IncidentRow(
        incident_id=str(uuid.uuid4()),
        type=decision.incident_type.value,
        zone_id=zone_id,
        gas=gas,
        severity=decision.severity.value,
        confidence=confidence,
        state=IncidentState.OPEN.value,
        opened_at=now,
        updated_at=now,
        dedup_key=dedup_key,
        is_active=True,
        reason_codes_json=decision.reason_codes,
        explanation=decision.explanation,
        recommended_action=decision.recommended_action,
        version=1,
    )
    session.add(row)
    session.flush()
    for etype, eid, reason in evidence_refs:
        session.add(IncidentEvidenceRow(incident_id=row.incident_id, evidence_type=etype, evidence_id=eid, reason=reason, created_at=now))
    session.add(
        AuditEventRow(
            incident_id=row.incident_id,
            actor=Actor.SYSTEM.value,
            action="OPENED",
            timestamp=now,
            previous_state=None,
            new_state=row.state,
            comment=decision.explanation,
            correlation_id=None,
        )
    )
    session.commit()
    _maybe_capture_evidence_image(session, row, zone_id, now, "CREATED")
    session.commit()
    return row, True


def apply_action(session: Session, incident_id: str, action: IncidentAction, actor: Actor, comment: str | None, expected_version: int, now: datetime, correlation_id: str) -> IncidentRow:
    row = session.get(IncidentRow, incident_id)
    if row is None:
        raise ApiError("NOT_FOUND", f"incident {incident_id} not found", status_code=404)
    if row.version != expected_version:
        raise ApiError("VERSION_CONFLICT", "incident has been updated since expected_version", status_code=409)

    current_state = IncidentState(row.state)

    if action == IncidentAction.COMMENT:
        new_state = current_state
    else:
        key = (current_state, action)
        if key not in ALLOWED_TRANSITIONS:
            raise ApiError("INVALID_TRANSITION", f"cannot apply {action.value} from {current_state.value}", status_code=409)
        new_state = ALLOWED_TRANSITIONS[key]

    previous_state = row.state
    row.state = new_state.value
    row.updated_at = now
    row.version += 1
    if action == IncidentAction.ACKNOWLEDGE:
        row.acknowledged_at = now
    if new_state == IncidentState.RESOLVED:
        row.resolved_at = now
        row.is_active = False

    session.add(
        AuditEventRow(
            incident_id=row.incident_id,
            actor=actor.value,
            action=action.value,
            timestamp=now,
            previous_state=previous_state,
            new_state=row.state,
            comment=comment,
            correlation_id=correlation_id,
        )
    )
    session.commit()
    return row
