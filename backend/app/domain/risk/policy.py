"""Deterministic, versioned severity policy. See CLAUDE.md "Risk and Incident Policy".

Severity is consequence, never a raw model probability. XGBoost/physics outputs
feed `confidence`/evidence only.
"""

from dataclasses import dataclass

from app.contracts.enums import CrossingOutcome, IncidentType, Severity

POLICY_VERSION = "1.0"


@dataclass(frozen=True)
class RiskInputs:
    current_co2_ppm: float
    short_term_avg_ppm: float | None
    action_crossing_outcome: CrossingOutcome
    action_crossing_minutes: float | None
    idlh_crossing_outcome: CrossingOutcome
    idlh_crossing_minutes: float | None
    person_in_gas_zone: bool
    person_zone_unknown: bool
    ventilation_advisory: bool
    niosh_short_term_ppm: float
    niosh_idlh_ppm: float

    helmet_violation_overhead: bool
    vest_violation_mandatory_zone: bool
    sensor_unreliable: bool
    camera_degraded: bool


@dataclass(frozen=True)
class RiskDecision:
    incident_type: IncidentType
    severity: Severity
    reason_codes: list[str]
    explanation: str
    recommended_action: str


DEFAULT_RECOMMENDATION = (
    "Inspect the zone, verify ventilation/source, contact safety personnel, "
    "and follow site procedures. This system never actuates equipment."
)


def evaluate_gas_risk(i: RiskInputs) -> RiskDecision | None:
    """Evaluate CO2-related conditions in descending severity order."""

    # CRITICAL: current or forecast IDLH within 10 minutes
    if i.current_co2_ppm >= i.niosh_idlh_ppm or (
        i.idlh_crossing_outcome == CrossingOutcome.CROSSING_EXPECTED
        and i.idlh_crossing_minutes is not None
        and i.idlh_crossing_minutes <= 10
    ):
        return RiskDecision(
            IncidentType.CO2_IDLH_NOW_OR_IMMINENT,
            Severity.CRITICAL,
            ["CO2_IDLH_NOW_OR_IMMINENT"],
            f"CO2 is at or imminently approaching the IDLH reference of {i.niosh_idlh_ppm:.0f} ppm.",
            DEFAULT_RECOMMENDATION,
        )

    # HIGH/CRITICAL: 15-min short-term average >= 30000
    if i.short_term_avg_ppm is not None and i.short_term_avg_ppm >= i.niosh_short_term_ppm:
        sev = Severity.CRITICAL if i.person_in_gas_zone else Severity.HIGH
        return RiskDecision(
            IncidentType.CO2_SHORT_TERM_LIMIT,
            sev,
            ["CO2_SHORT_TERM_LIMIT"] + (["PERSON_IN_PREDICTED_GAS_RISK"] if i.person_in_gas_zone else []),
            f"15-minute average CO2 ({i.short_term_avg_ppm:.0f} ppm) is at/above the "
            f"short-term reference of {i.niosh_short_term_ppm:.0f} ppm.",
            DEFAULT_RECOMMENDATION,
        )

    # MEDIUM/HIGH: forecast crosses 5000ppm action reference within 60 min
    if i.action_crossing_outcome in (CrossingOutcome.CROSSING_EXPECTED, CrossingOutcome.ALREADY_EXCEEDED):
        if i.person_in_gas_zone:
            return RiskDecision(
                IncidentType.PERSON_IN_PREDICTED_GAS_RISK,
                Severity.HIGH,
                ["CO2_ACTION_CROSSING_PREDICTED", "PERSON_IN_PREDICTED_GAS_RISK"],
                "CO2 forecast crosses the 5000 ppm action reference within the next 60 minutes "
                "and a worker is present in the gas-exposure zone.",
                DEFAULT_RECOMMENDATION,
            )
        return RiskDecision(
            IncidentType.CO2_ACTION_CROSSING_PREDICTED,
            Severity.MEDIUM,
            ["CO2_ACTION_CROSSING_PREDICTED"],
            "CO2 forecast crosses the 5000 ppm action reference within the next 60 minutes.",
            DEFAULT_RECOMMENDATION,
        )

    # LOW: internal ventilation advisory only
    if i.ventilation_advisory:
        return RiskDecision(
            IncidentType.CO2_VENTILATION_ADVISORY,
            Severity.LOW,
            ["CO2_VENTILATION_ADVISORY"],
            "CO2 has crossed the internal 1000 ppm ventilation advisory (not a regulatory limit).",
            DEFAULT_RECOMMENDATION,
        )

    if i.sensor_unreliable:
        return RiskDecision(
            IncidentType.SENSOR_UNRELIABLE,
            Severity.LOW,
            ["SENSOR_UNRELIABLE"],
            "Sensor readings are inconsistent or of degraded quality without corroboration.",
            "Verify sensor calibration and connectivity.",
        )

    return None


def evaluate_ppe_risk(i: RiskInputs) -> list[RiskDecision]:
    decisions: list[RiskDecision] = []
    if i.helmet_violation_overhead:
        decisions.append(
            RiskDecision(
                IncidentType.PPE_HELMET_OVERHEAD_VIOLATION,
                Severity.HIGH,
                ["PPE_HELMET_OVERHEAD_VIOLATION"],
                "Missing helmet compliance persisted while a worker was in the overhead-work zone.",
                DEFAULT_RECOMMENDATION,
            )
        )
    if i.vest_violation_mandatory_zone:
        decisions.append(
            RiskDecision(
                IncidentType.PPE_VEST_VIOLATION,
                Severity.MEDIUM,
                ["PPE_VEST_VIOLATION"],
                "Missing high-visibility vest persisted in a mandatory-PPE zone.",
                DEFAULT_RECOMMENDATION,
            )
        )
    return decisions


def evaluate_camera_status(i: RiskInputs) -> RiskDecision | None:
    if i.camera_degraded:
        return RiskDecision(
            IncidentType.CAMERA_DEGRADED,
            Severity.LOW,
            ["CAMERA_DEGRADED"],
            "Camera/model evidence is unavailable; worker presence cannot be confirmed as safe.",
            "Restore the camera or replay feed to resume worker-safety evidence.",
        )
    return None
