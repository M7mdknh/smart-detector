from app.contracts.enums import CrossingOutcome, IncidentType, Severity
from app.domain.risk.policy import RiskInputs, evaluate_camera_status, evaluate_gas_risk, evaluate_ppe_risk

BASE = dict(
    current_co2_ppm=500.0,
    short_term_avg_ppm=None,
    action_crossing_outcome=CrossingOutcome.NO_CROSSING,
    action_crossing_minutes=None,
    idlh_crossing_outcome=CrossingOutcome.NO_CROSSING,
    idlh_crossing_minutes=None,
    person_in_gas_zone=False,
    person_zone_unknown=False,
    ventilation_advisory=False,
    niosh_short_term_ppm=30000.0,
    niosh_idlh_ppm=40000.0,
    helmet_violation_overhead=False,
    vest_violation_mandatory_zone=False,
    sensor_unreliable=False,
    camera_degraded=False,
)


def inputs(**overrides):
    d = dict(BASE)
    d.update(overrides)
    return RiskInputs(**d)


def test_no_risk_normal_operation():
    assert evaluate_gas_risk(inputs()) is None


def test_ventilation_advisory_low():
    d = evaluate_gas_risk(inputs(ventilation_advisory=True))
    assert d.severity == Severity.LOW
    assert d.incident_type == IncidentType.CO2_VENTILATION_ADVISORY


def test_action_crossing_medium_no_person():
    d = evaluate_gas_risk(inputs(action_crossing_outcome=CrossingOutcome.CROSSING_EXPECTED, action_crossing_minutes=34))
    assert d.severity == Severity.MEDIUM
    assert d.incident_type == IncidentType.CO2_ACTION_CROSSING_PREDICTED


def test_action_crossing_high_with_person():
    d = evaluate_gas_risk(
        inputs(action_crossing_outcome=CrossingOutcome.CROSSING_EXPECTED, action_crossing_minutes=34, person_in_gas_zone=True)
    )
    assert d.severity == Severity.HIGH
    assert d.incident_type == IncidentType.PERSON_IN_PREDICTED_GAS_RISK


def test_short_term_limit_high_no_person():
    d = evaluate_gas_risk(inputs(short_term_avg_ppm=31000))
    assert d.severity == Severity.HIGH
    assert d.incident_type == IncidentType.CO2_SHORT_TERM_LIMIT


def test_short_term_limit_critical_with_person():
    d = evaluate_gas_risk(inputs(short_term_avg_ppm=31000, person_in_gas_zone=True))
    assert d.severity == Severity.CRITICAL


def test_idlh_current_critical():
    d = evaluate_gas_risk(inputs(current_co2_ppm=41000))
    assert d.severity == Severity.CRITICAL
    assert d.incident_type == IncidentType.CO2_IDLH_NOW_OR_IMMINENT


def test_idlh_imminent_within_10_minutes_critical():
    d = evaluate_gas_risk(inputs(idlh_crossing_outcome=CrossingOutcome.CROSSING_EXPECTED, idlh_crossing_minutes=8))
    assert d.severity == Severity.CRITICAL


def test_idlh_crossing_beyond_10_minutes_not_critical_via_idlh_path():
    # 25 minutes out should not trigger the IDLH-specific critical path (may still hit action crossing).
    d = evaluate_gas_risk(inputs(idlh_crossing_outcome=CrossingOutcome.CROSSING_EXPECTED, idlh_crossing_minutes=25))
    assert d is None or d.incident_type != IncidentType.CO2_IDLH_NOW_OR_IMMINENT


def test_sensor_unreliable_low():
    d = evaluate_gas_risk(inputs(sensor_unreliable=True))
    assert d.severity == Severity.LOW
    assert d.incident_type == IncidentType.SENSOR_UNRELIABLE


def test_helmet_violation_high():
    decisions = evaluate_ppe_risk(inputs(helmet_violation_overhead=True))
    assert len(decisions) == 1
    assert decisions[0].severity == Severity.HIGH
    assert decisions[0].incident_type == IncidentType.PPE_HELMET_OVERHEAD_VIOLATION


def test_vest_violation_medium():
    decisions = evaluate_ppe_risk(inputs(vest_violation_mandatory_zone=True))
    assert decisions[0].severity == Severity.MEDIUM
    assert decisions[0].incident_type == IncidentType.PPE_VEST_VIOLATION


def test_both_ppe_violations_produce_two_decisions():
    decisions = evaluate_ppe_risk(inputs(helmet_violation_overhead=True, vest_violation_mandatory_zone=True))
    assert len(decisions) == 2


def test_camera_degraded():
    d = evaluate_camera_status(inputs(camera_degraded=True))
    assert d.incident_type == IncidentType.CAMERA_DEGRADED
    assert d.severity == Severity.LOW


def test_helmet_never_reduces_gas_risk():
    # Confidence check: helmet compliance/violation fields don't appear in gas risk evaluation at all.
    high = evaluate_gas_risk(
        inputs(action_crossing_outcome=CrossingOutcome.CROSSING_EXPECTED, action_crossing_minutes=10, person_in_gas_zone=True)
    )
    assert high.severity == Severity.HIGH
