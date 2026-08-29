"""Restricted zone: a third configurable zone TYPE reusing the exact same
polygon/box-membership + foot-point + dwell-timer mechanism already used for
the gas-exposure and overhead-work zones (CLAUDE.md: restricted areas are not
a YOLO class -- they are configurable polygons evaluated against tracked
worker foot points)."""

from datetime import datetime, timedelta, timezone

from app.contracts.enums import IncidentType, Severity, ZoneMembership
from app.domain.risk.policy import RiskInputs, evaluate_ppe_risk
from app.inference.vision_worker_impl import TrackDwell, associate_and_dwell
from app.inference.zone_config import get_zone_config, point_in_polygon
from app.services import incident_service, vision_ground_truth

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

BASE = dict(
    current_co2_ppm=500.0, short_term_avg_ppm=None, action_crossing_outcome="NO_CROSSING", action_crossing_minutes=None,
    idlh_crossing_outcome="NO_CROSSING", idlh_crossing_minutes=None, person_in_gas_zone=False, person_zone_unknown=False,
    ventilation_advisory=False, niosh_short_term_ppm=30000.0, niosh_idlh_ppm=40000.0, helmet_violation_overhead=False,
    vest_violation_mandatory_zone=False, sensor_unreliable=False, camera_degraded=False,
)


def test_restricted_zone_is_configured():
    zone = get_zone_config().zone_of_type("RESTRICTED")
    assert zone is not None
    assert len(zone.points) >= 3


def test_foot_point_inside_restricted_polygon():
    zone = get_zone_config().zone_of_type("RESTRICTED")
    cx = sum(p[0] for p in zone.points) / len(zone.points)
    cy = sum(p[1] for p in zone.points) / len(zone.points)
    assert point_in_polygon(cx, cy, zone.points) is True
    assert point_in_polygon(0.0, 0.0, zone.points) is False


def test_cv_replay_pipeline_dwell_marks_restricted_membership():
    """Same enter/exit dwell mechanism as gas/overhead: a single frame inside
    the restricted polygon is not enough; persistence past 2s is."""
    zone = get_zone_config().zone_of_type("RESTRICTED")
    cx = sum(p[0] for p in zone.points) / len(zone.points)
    cy = sum(p[1] for p in zone.points) / len(zone.points)
    box = (cx - 0.05, cy - 0.2, cx + 0.05, cy)  # bottom-center lands at (cx, cy)

    tracks: dict[int, TrackDwell] = {}
    rows = associate_and_dwell([(1, box, 0.9)], [], 1, T0, tracks, "test-model")
    assert rows[0].restricted_zone_membership == "OUTSIDE"  # not yet 2s

    rows = associate_and_dwell([(1, box, 0.9)], [], 2, T0 + timedelta(seconds=2.1), tracks, "test-model")
    assert rows[0].restricted_zone_membership == "INSIDE"


def test_ground_truth_restricted_zone_dwell_and_incident_creation(session, now):
    """(Simulator-driven path that actually opens incidents in the demo.)
    Walking the simulated worker into the restricted-zone floor box for long
    enough opens exactly one PERSON_IN_RESTRICTED_ZONE incident; repeated
    ticks update it rather than duplicating."""
    vision_ground_truth.reset_dwell_for_run("run-restricted-test")
    x, y = 5.0, -5.0  # inside RESTRICTED_ZONE_BOX = (3, -8, 8, -3)
    assert vision_ground_truth._in_box(x, y, vision_ground_truth.RESTRICTED_ZONE_BOX)

    rows = []
    for t in (0.0, 1.0, 2.5, 4.0):
        row = vision_ground_truth.emit_ground_truth("run-restricted-test", "zone-1", x, y, True, True, False, T0 + timedelta(seconds=t))
        session.add(row)
        session.commit()
        rows.append(row)

    assert rows[0].restricted_zone_membership == ZoneMembership.OUTSIDE.value
    assert rows[-1].restricted_zone_membership == ZoneMembership.INSIDE.value

    inputs = incident_service.build_risk_inputs(session, _fake_forecast(), {"current_ppm": 500.0}, "zone-1", T0 + timedelta(seconds=4.0), camera_degraded=False)
    assert inputs.restricted_zone_violation is True

    decisions = evaluate_ppe_risk(inputs)
    restricted = [d for d in decisions if d.incident_type == IncidentType.PERSON_IN_RESTRICTED_ZONE]
    assert len(restricted) == 1
    assert restricted[0].severity == Severity.HIGH

    row1, created1 = incident_service.upsert_incident(session, restricted[0], "zone-1", None, None, restricted[0].incident_type.value, now, [])
    assert created1 is True
    row2, created2 = incident_service.upsert_incident(session, restricted[0], "zone-1", None, None, restricted[0].incident_type.value, now, [])
    assert created2 is False
    assert row1.incident_id == row2.incident_id


def test_restricted_zone_risk_decision_severity_high():
    d = dict(BASE)
    d["restricted_zone_violation"] = True
    decisions = evaluate_ppe_risk(RiskInputs(**d))
    assert len(decisions) == 1
    assert decisions[0].incident_type == IncidentType.PERSON_IN_RESTRICTED_ZONE
    assert decisions[0].severity == Severity.HIGH
    assert "PERSON_IN_RESTRICTED_ZONE" in decisions[0].reason_codes


class _FakeForecast:
    crossings_json = [
        {"threshold_name": "NIOSH_ACTION_5000", "outcome": "NO_CROSSING"},
        {"threshold_name": "NIOSH_IDLH_40000", "outcome": "NO_CROSSING"},
        {"threshold_name": "INTERNAL_ADVISORY_1000", "outcome": "NO_CROSSING"},
    ]
    points_json = [{"physics_ppm": 500.0}]
    leak_probability = 0.0


def _fake_forecast():
    return _FakeForecast()
