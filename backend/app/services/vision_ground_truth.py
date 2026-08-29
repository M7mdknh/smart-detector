"""Converts simulator worker/PPE floor state into VisionEvidence rows.

Tagged SIMULATION_GROUND_TRUTH -- never presented as CV_MODEL output (CLAUDE.md
invariant #3). May drive incident logic for deterministic scenario tests while
the camera panel independently runs actual CV replay (simulator-specification.md).

Dwell is timestamp-based, matching the vision model spec's dwell semantics:
zone entry/exit after 2s persistence, PPE violation after 3s persistence,
clear after 5s of compliant/outside evidence.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.contracts.enums import DetectionClass, EvidenceSource, PpeState, ZoneMembership
from app.storage.models import VisionEvidenceRow

GAS_ZONE_BOX = (3.0, 3.0, 8.0, 8.0)  # x1, y1, x2, y2 in floor meters
OVERHEAD_ZONE_BOX = (-8.0, -8.0, -3.0, -3.0)

ZONE_ENTER_SECONDS = 2.0
ZONE_EXIT_SECONDS = 2.0
PPE_VIOLATION_SECONDS = 3.0
PPE_CLEAR_SECONDS = 5.0

GROUND_TRUTH_MODEL_VERSION = "sim-ground-truth-1.0"


def _in_box(x: float, y: float, box: tuple[float, float, float, float]) -> bool:
    x1, y1, x2, y2 = box
    return x1 <= x <= x2 and y1 <= y <= y2


@dataclass
class _TrackDwellState:
    gas_inside_since: datetime | None = None
    gas_outside_since: datetime | None = None
    gas_membership: ZoneMembership = ZoneMembership.OUTSIDE

    overhead_inside_since: datetime | None = None
    overhead_outside_since: datetime | None = None
    overhead_membership: ZoneMembership = ZoneMembership.OUTSIDE

    helmet_noncompliant_since: datetime | None = None
    helmet_compliant_since: datetime | None = None
    helmet_state: PpeState = PpeState.UNKNOWN

    vest_noncompliant_since: datetime | None = None
    vest_compliant_since: datetime | None = None
    vest_state: PpeState = PpeState.UNKNOWN


_dwell_by_run: dict[str, _TrackDwellState] = {}


def reset_dwell_for_run(run_id: str) -> None:
    _dwell_by_run.pop(run_id, None)


def _apply_dwell(now: datetime, currently_true: bool, since_true: datetime | None, since_false: datetime | None, enter_seconds: float, exit_seconds: float, current_state, true_state, false_state):
    if currently_true:
        since_false = None
        since_true = since_true or now
        if (now - since_true).total_seconds() >= enter_seconds:
            current_state = true_state
    else:
        since_true = None
        since_false = since_false or now
        if (now - since_false).total_seconds() >= exit_seconds:
            current_state = false_state
    return current_state, since_true, since_false


def emit_ground_truth(run_id: str, zone_id: str, worker_x: float, worker_y: float, helmet_on: bool, vest_on: bool, overhead_zone_active: bool, now: datetime) -> VisionEvidenceRow:
    state = _dwell_by_run.setdefault(run_id, _TrackDwellState())

    in_gas = _in_box(worker_x, worker_y, GAS_ZONE_BOX)
    state.gas_membership, state.gas_inside_since, state.gas_outside_since = _apply_dwell(
        now, in_gas, state.gas_inside_since, state.gas_outside_since, ZONE_ENTER_SECONDS, ZONE_EXIT_SECONDS,
        state.gas_membership, ZoneMembership.INSIDE, ZoneMembership.OUTSIDE,
    )

    in_overhead = overhead_zone_active and _in_box(worker_x, worker_y, OVERHEAD_ZONE_BOX)
    state.overhead_membership, state.overhead_inside_since, state.overhead_outside_since = _apply_dwell(
        now, in_overhead, state.overhead_inside_since, state.overhead_outside_since, ZONE_ENTER_SECONDS, ZONE_EXIT_SECONDS,
        state.overhead_membership, ZoneMembership.INSIDE, ZoneMembership.OUTSIDE,
    )

    helmet_missing = in_overhead and not helmet_on
    state.helmet_state, state.helmet_noncompliant_since, state.helmet_compliant_since = _apply_dwell(
        now, helmet_missing, state.helmet_noncompliant_since, state.helmet_compliant_since, PPE_VIOLATION_SECONDS, PPE_CLEAR_SECONDS,
        state.helmet_state, PpeState.NON_COMPLIANT, PpeState.COMPLIANT if helmet_on else PpeState.UNKNOWN,
    )

    vest_missing = not vest_on
    state.vest_state, state.vest_noncompliant_since, state.vest_compliant_since = _apply_dwell(
        now, vest_missing, state.vest_noncompliant_since, state.vest_compliant_since, PPE_VIOLATION_SECONDS, PPE_CLEAR_SECONDS,
        state.vest_state, PpeState.NON_COMPLIANT, PpeState.COMPLIANT if vest_on else PpeState.UNKNOWN,
    )

    dwell_seconds = None
    if state.gas_membership == ZoneMembership.INSIDE and state.gas_inside_since:
        dwell_seconds = (now - state.gas_inside_since).total_seconds()

    row = VisionEvidenceRow(
        evidence_id=str(uuid.uuid4()),
        camera_id="ground-truth",
        zone_id=zone_id,
        frame_id=0,
        event_time=now,
        ingested_at=now,
        source=EvidenceSource.SIMULATION_GROUND_TRUTH.value,
        model_version=GROUND_TRUTH_MODEL_VERSION,
        track_id=0,
        detected_class=DetectionClass.PERSON.value,
        confidence=1.0,
        bbox_x1=0.0,
        bbox_y1=0.0,
        bbox_x2=0.0,
        bbox_y2=0.0,
        helmet_state=state.helmet_state.value,
        vest_state=state.vest_state.value,
        gas_zone_membership=state.gas_membership.value,
        overhead_zone_membership=state.overhead_membership.value,
        dwell_seconds=dwell_seconds,
    )
    return row
