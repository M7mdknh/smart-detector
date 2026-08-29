"""Deterministic-adapter unit tests for vision association/dwell/zone logic
(no model call -- see CLAUDE.md's allowance for deterministic adapters in unit
tests; the real detector is exercised in tests/test_vision_e2e.py instead).
"""

from datetime import datetime, timedelta, timezone

from app.inference.vision_worker_impl import (
    TrackDwell,
    associate_and_dwell,
)
from app.inference.zone_config import get_zone_config

OVERHEAD_ZONE_POLY_X = [p[0] for p in get_zone_config().zone_of_type("OVERHEAD_WORK").points]

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def person_box(x1=0.55, y1=0.2, x2=0.75, y2=0.9):
    return (x1, y1, x2, y2)


def test_zone_entry_requires_two_seconds_persistence():
    tracks: dict[int, TrackDwell] = {}
    box = person_box()  # bottom-center at x=0.65 -> inside GAS_ZONE_POLY (x>=0.5)

    rows = associate_and_dwell([(1, box, 0.9)], [], 1, T0, tracks, "test-model")
    assert rows[0].gas_zone_membership == "OUTSIDE"  # not yet 2s

    rows = associate_and_dwell([(1, box, 0.9)], [], 2, T0 + timedelta(seconds=2.1), tracks, "test-model")
    assert rows[0].gas_zone_membership == "INSIDE"


def test_helmet_violation_requires_three_seconds_in_overhead_zone():
    tracks: dict[int, TrackDwell] = {}
    # bottom-center in the overhead (left) zone, no helmet/no_helmet detection at all
    box = (0.1, 0.1, 0.3, 0.8)
    assert min(OVERHEAD_ZONE_POLY_X) <= (box[0] + box[2]) / 2 <= max(OVERHEAD_ZONE_POLY_X)

    for t in (0.0, 2.1, 4.5):  # first tick establishes zone entry, then PPE dwell accrues
        rows = associate_and_dwell([(1, box, 0.9)], [], int(t), T0 + timedelta(seconds=t), tracks, "test-model")

    assert rows[0].overhead_zone_membership == "INSIDE"
    assert rows[0].helmet_state == "NON_COMPLIANT"


def test_single_frame_missing_helmet_does_not_immediately_violate():
    tracks: dict[int, TrackDwell] = {}
    box = (0.1, 0.1, 0.3, 0.8)
    rows = associate_and_dwell([(1, box, 0.9)], [], 1, T0, tracks, "test-model")
    assert rows[0].helmet_state == "UNKNOWN"


def test_positive_helmet_evidence_becomes_compliant_after_one_second():
    tracks: dict[int, TrackDwell] = {}
    box = person_box()
    helmet_box = (0.58, 0.18, 0.7, 0.35)  # inside head region of box

    rows = associate_and_dwell([(1, box, 0.9)], [("helmet", helmet_box, 0.8)], 1, T0, tracks, "test-model")
    assert rows[0].helmet_state == "UNKNOWN"  # not yet 1s

    rows = associate_and_dwell([(1, box, 0.9)], [("helmet", helmet_box, 0.8)], 2, T0 + timedelta(seconds=1.1), tracks, "test-model")
    assert rows[0].helmet_state == "COMPLIANT"


def test_ambiguous_conflicting_helmet_evidence_stays_unknown():
    tracks: dict[int, TrackDwell] = {}
    box = person_box()
    helmet_box = (0.58, 0.18, 0.7, 0.35)
    no_helmet_box = (0.6, 0.19, 0.72, 0.34)  # overlapping detection, both classes fire

    rows = associate_and_dwell(
        [(1, box, 0.9)], [("helmet", helmet_box, 0.6), ("no_helmet", no_helmet_box, 0.55)], 1, T0, tracks, "test-model"
    )
    assert rows[0].helmet_state == "UNKNOWN"


def test_vest_violation_after_three_seconds_no_vest_detected():
    tracks: dict[int, TrackDwell] = {}
    box = person_box()
    for t in (0.0, 3.1):
        rows = associate_and_dwell([(1, box, 0.9)], [], int(t), T0 + timedelta(seconds=t), tracks, "test-model")
    assert rows[0].vest_state == "NON_COMPLIANT"


def test_tracker_loss_emits_evidence_without_track_id_and_no_dwell():
    tracks: dict[int, TrackDwell] = {}
    box = person_box()
    rows = associate_and_dwell([(None, box, 0.9)], [], 1, T0, tracks, "test-model")
    assert rows[0].track_id is None
    assert rows[0].gas_zone_membership == "UNKNOWN"
    assert tracks == {}  # no per-track dwell state was opened


def test_violation_clears_after_five_seconds_compliant():
    tracks: dict[int, TrackDwell] = {}
    box = (0.1, 0.1, 0.3, 0.8)
    # establish violation
    for t in (0.0, 2.1, 4.5):
        associate_and_dwell([(1, box, 0.9)], [], int(t), T0 + timedelta(seconds=t), tracks, "test-model")
    assert tracks[1].helmet_state.value == "NON_COMPLIANT"

    # now provide positive helmet evidence and wait out the 5s clear window
    helmet_box = (0.13, 0.11, 0.27, 0.3)
    for t in (4.6, 10.0):
        rows = associate_and_dwell([(1, box, 0.9)], [("helmet", helmet_box, 0.8)], int(t), T0 + timedelta(seconds=t), tracks, "test-model")
    assert rows[0].helmet_state == "COMPLIANT"
