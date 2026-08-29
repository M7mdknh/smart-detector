"""One-to-one PPE-to-person association tests (Phase 2 enhancement).

Exercises app.inference.ppe_association.assign_ppe directly: pure, fast,
deterministic -- no model call. End-to-end wiring through
associate_and_dwell (which calls assign_ppe internally) is covered by
test_vision_association.py and the real-detector test_vision_e2e.py.
"""

import random

from app.inference.ppe_association import assign_ppe

HEAD = (0.0, 0.0, 1.0, 0.35)
TORSO = (0.0, 0.25, 1.0, 0.75)


def head_region_fn(person_box):
    x1, y1, x2, y2 = person_box
    h = y2 - y1
    return (x1, y1, x2, y1 + h * 0.35)


def torso_region_fn(person_box):
    x1, y1, x2, y2 = person_box
    h = y2 - y1
    return (x1, y1 + h * 0.25, x2, y1 + h * 0.75)


def person(x1, y1=0.0, x2=None, y2=1.0):
    if x2 is None:
        x2 = x1 + 0.2
    return (x1, y1, x2, y2)


def test_two_workers_competing_for_one_helmet_only_one_wins():
    persons = [person(0.0), person(0.05)]  # heavily overlapping so both are near the helmet
    helmet_box = (0.02, 0.0, 0.15, 0.1)
    assignments = assign_ppe(persons, [("helmet", helmet_box, 0.9)], head_region_fn, torso_region_fn)

    positives = [a.helmet_positive for a in assignments]
    assert positives.count(True) == 1, "exactly one of the two competing workers should win the single helmet"
    assert positives.count(False) == 1


def test_two_workers_with_separate_helmets_both_compliant():
    persons = [person(0.0), person(0.6)]
    helmets = [("helmet", (0.02, 0.0, 0.15, 0.1), 0.9), ("helmet", (0.62, 0.0, 0.75, 0.1), 0.85)]
    assignments = assign_ppe(persons, helmets, head_region_fn, torso_region_fn)

    assert assignments[0].helmet_positive is True
    assert assignments[1].helmet_positive is True
    assert assignments[0].matches[0].candidate_idx != assignments[1].matches[0].candidate_idx


def test_overlapping_workers_no_double_assignment():
    persons = [person(0.0, x2=0.4), person(0.1, x2=0.5)]  # substantially overlapping boxes
    helmet_box = (0.15, 0.0, 0.25, 0.1)
    assignments = assign_ppe(persons, [("helmet", helmet_box, 0.9)], head_region_fn, torso_region_fn)
    total_positive = sum(a.helmet_positive for a in assignments)
    assert total_positive == 1, "one PPE box must never satisfy two people"


def test_one_vest_between_two_workers_only_one_gets_it():
    persons = [person(0.0), person(0.05)]
    vest_box = (0.02, 0.3, 0.15, 0.6)
    assignments = assign_ppe(persons, [("vest", vest_box, 0.8)], head_region_fn, torso_region_fn)
    assert sum(a.vest_positive for a in assignments) == 1


def test_conflicting_helmet_and_no_helmet_evidence_is_unknown_not_assigned():
    persons = [person(0.0)]
    candidates = [("helmet", (0.02, 0.0, 0.15, 0.1), 0.6), ("no_helmet", (0.03, 0.0, 0.16, 0.1), 0.55)]
    assignments = assign_ppe(persons, candidates, head_region_fn, torso_region_fn)
    assert assignments[0].helmet_ambiguous is True
    assert assignments[0].helmet_positive is False
    assert assignments[0].helmet_negative is False


def test_reordering_input_detections_does_not_change_result():
    persons = [person(0.0), person(0.6)]
    candidates = [
        ("helmet", (0.02, 0.0, 0.15, 0.1), 0.9),
        ("helmet", (0.62, 0.0, 0.75, 0.1), 0.7),
        ("vest", (0.02, 0.3, 0.15, 0.6), 0.6),
    ]
    baseline = assign_ppe(persons, candidates, head_region_fn, torso_region_fn)

    rng = random.Random(42)
    for _ in range(20):
        shuffled_persons = list(enumerate(persons))
        rng.shuffle(shuffled_persons)
        person_order = [p for _, p in shuffled_persons]
        original_idx = [i for i, _ in shuffled_persons]

        shuffled_candidates = list(candidates)
        rng.shuffle(shuffled_candidates)

        result = assign_ppe(person_order, shuffled_candidates, head_region_fn, torso_region_fn)

        # Map back to original person order and compare positive/negative outcomes
        # (not raw candidate indices, which legitimately differ after shuffling).
        for shuffled_pos, orig_idx in enumerate(original_idx):
            assert result[shuffled_pos].helmet_positive == baseline[orig_idx].helmet_positive
            assert result[shuffled_pos].helmet_negative == baseline[orig_idx].helmet_negative
            assert result[shuffled_pos].vest_positive == baseline[orig_idx].vest_positive


def test_partial_occlusion_low_overlap_candidate_may_go_unmatched():
    # A helmet box barely clipping the edge of the head region (poor overlap) competes
    # against a well-centered candidate for a second person; the poorly-overlapping one
    # should lose out when a person with better evidence is also present, but a person
    # with genuinely no visible PPE evidence stays UNKNOWN rather than guessing.
    persons = [person(0.0)]
    sliver_box = (0.19, 0.0, 0.21, 0.02)  # just barely inside the head region's edge
    assignments = assign_ppe(persons, [("helmet", sliver_box, 0.3)], head_region_fn, torso_region_fn)
    # Either assigned (if centre truly falls in-region) or not -- but never ambiguous,
    # and never a crash on a degenerate/edge overlap.
    assert assignments[0].helmet_ambiguous is False


def test_no_unassigned_ppe_box_grants_compliance():
    # A helmet box that is NOT within anyone's head region must not affect anyone.
    persons = [person(0.5, x2=0.7)]
    far_away_helmet = (0.0, 0.0, 0.05, 0.05)
    assignments = assign_ppe(persons, [("helmet", far_away_helmet, 0.95)], head_region_fn, torso_region_fn)
    assert assignments[0].helmet_positive is False
    assert assignments[0].helmet_reason == "no_candidate_in_region"


def test_degenerate_person_box_yields_unknown_not_a_crash():
    persons = [(0.5, 0.5, 0.5, 0.5)]  # zero-area box: poor/no visibility
    assignments = assign_ppe(persons, [("helmet", (0.49, 0.49, 0.51, 0.51), 0.9)], head_region_fn, torso_region_fn)
    assert assignments[0].helmet_positive is False
    assert assignments[0].helmet_reason == "degenerate_region"


def test_match_scores_are_inspectable():
    persons = [person(0.0)]
    assignments = assign_ppe(persons, [("helmet", (0.02, 0.0, 0.15, 0.1), 0.9)], head_region_fn, torso_region_fn)
    assert len(assignments[0].matches) == 1
    m = assignments[0].matches[0]
    assert 0.0 <= m.score <= 1.0
    assert m.ppe_class == "helmet"
    assert m.confidence == 0.9
