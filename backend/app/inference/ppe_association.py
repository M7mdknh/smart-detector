"""One-to-one PPE-to-person association.

Replaces the earlier "any(...) matches" approach (each person checked
independently against the full candidate pool, so one helmet box could make
multiple nearby people appear compliant -- a real gap found and documented
during the P0 acceptance pass). This module computes a deterministic global
assignment: each PPE detection is used at most once, each person receives at
most one final item per class group ("head" = helmet/no_helmet, "torso" =
vest).

Algorithm (greedy, score-sorted -- deterministic, no external dependency;
Hungarian matching would be exact-optimal but isn't justified at this scale,
typically a handful of people per frame):

1. For each person, compute head/torso regions (model-specification.md's
   geometry). Degenerate regions (near-zero area -- a corrupt/tiny box) never
   produce a match: that person's slot stays UNKNOWN ("poor head/torso
   visibility").
2. For each (person, candidate) pair where the candidate's centre falls
   inside the relevant region, compute a match score from normalized overlap
   (IoU of the candidate box against the region box), inverse centre
   distance, and detector confidence.
3. Ambiguity pre-check: if a person has BOTH a valid `helmet` and a valid
   `no_helmet` candidate in their head region simultaneously, that person's
   head slot is immediately UNKNOWN (conflicting evidence) and is removed
   from the assignable pool for that person -- but the two candidates remain
   available to match *other* people.
4. Greedy assignment: remaining candidate matches are sorted by score
   descending, with an input-order-independent tie-break (rounded box
   coordinates, not list index -- reordering the input never changes the
   result). Each pass consumes one person-slot and one candidate; a person or
   candidate already claimed is skipped.

Every match carries its score and the reason it did or didn't win, so the
assignment is inspectable (`PersonPpeAssignment.head_reason` /
`.torso_reason`).
"""

from dataclasses import dataclass, field

HEAD_CLASSES = ("helmet", "no_helmet")
TORSO_CLASSES = ("vest",)

# Score weights: overlap and confidence matter roughly equally; centre distance
# is a tie-breaker among otherwise-similar candidates.
W_OVERLAP = 0.45
W_DISTANCE = 0.25
W_CONFIDENCE = 0.30

MIN_REGION_AREA = 1e-6


def _region_iou(candidate_box: tuple[float, float, float, float], region: tuple[float, float, float, float]) -> float:
    cx1, cy1, cx2, cy2 = candidate_box
    rx1, ry1, rx2, ry2 = region
    ix1, iy1 = max(cx1, rx1), max(cy1, ry1)
    ix2, iy2 = min(cx2, rx2), min(cy2, ry2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    cand_area = max(0.0, (cx2 - cx1)) * max(0.0, (cy2 - cy1))
    region_area = max(0.0, (rx2 - rx1)) * max(0.0, (ry2 - ry1))
    union = cand_area + region_area - inter
    if union <= 0:
        return 0.0
    return inter / union


def _center_distance_normalized(candidate_box, region) -> float:
    cx = (candidate_box[0] + candidate_box[2]) / 2
    cy = (candidate_box[1] + candidate_box[3]) / 2
    rx = (region[0] + region[2]) / 2
    ry = (region[1] + region[3]) / 2
    diag = ((region[2] - region[0]) ** 2 + (region[3] - region[1]) ** 2) ** 0.5
    if diag <= 0:
        return 1.0
    dist = ((cx - rx) ** 2 + (cy - ry) ** 2) ** 0.5
    return min(1.0, dist / diag)


def _region_area(region: tuple[float, float, float, float]) -> float:
    return max(0.0, region[2] - region[0]) * max(0.0, region[3] - region[1])


def _center_in(box, region) -> bool:
    cx = (box[0] + box[2]) / 2
    cy = (box[1] + box[3]) / 2
    return region[0] <= cx <= region[2] and region[1] <= cy <= region[3]


@dataclass(frozen=True)
class PpeMatch:
    person_idx: int
    candidate_idx: int
    ppe_class: str
    score: float
    overlap: float
    distance: float
    confidence: float


@dataclass
class PersonPpeAssignment:
    helmet_positive: bool = False
    helmet_negative: bool = False
    helmet_ambiguous: bool = False
    helmet_reason: str = "no_candidate_in_region"
    vest_positive: bool = False
    vest_reason: str = "no_candidate_in_region"
    matches: list[PpeMatch] = field(default_factory=list)


def _score(candidate_box, region, confidence) -> tuple[float, float, float]:
    overlap = _region_iou(candidate_box, region)
    distance = _center_distance_normalized(candidate_box, region)
    score = W_OVERLAP * overlap + W_DISTANCE * (1.0 - distance) + W_CONFIDENCE * confidence
    return score, overlap, distance


def _tiebreak_key(m: PpeMatch, person_box, candidate_box):
    # Deterministic regardless of input list order: sorts on the score first,
    # then on rounded geometry/class -- never on list index.
    return (
        -m.score,
        tuple(round(v, 6) for v in person_box),
        tuple(round(v, 6) for v in candidate_box),
        m.ppe_class,
    )


def assign_ppe(
    persons: list[tuple[float, float, float, float]],
    ppe_candidates: list[tuple[str, tuple[float, float, float, float], float]],
    head_region_fn,
    torso_region_fn,
) -> list[PersonPpeAssignment]:
    """persons: list of person boxes (already filtered to real detections).
    ppe_candidates: list of (class_name, box, confidence).
    Returns one PersonPpeAssignment per person, in input order."""
    assignments = [PersonPpeAssignment() for _ in persons]

    head_regions = [head_region_fn(p) for p in persons]
    torso_regions = [torso_region_fn(p) for p in persons]

    # --- Ambiguity pre-check: both helmet and no_helmet valid for one person ---
    ambiguous_person_idx: set[int] = set()
    for pi, region in enumerate(head_regions):
        if _region_area(region) < MIN_REGION_AREA:
            assignments[pi].helmet_reason = "degenerate_region"
            continue
        classes_present = {
            c for c, box, _ in ppe_candidates if c in HEAD_CLASSES and _center_in(box, region)
        }
        if len(classes_present) > 1:
            ambiguous_person_idx.add(pi)
            assignments[pi].helmet_ambiguous = True
            assignments[pi].helmet_reason = "conflicting_helmet_and_no_helmet_evidence"

    # --- Build candidate match list for head slot (excluding ambiguous persons) ---
    head_matches: list[tuple[PpeMatch, tuple, tuple]] = []
    for pi, region in enumerate(head_regions):
        if pi in ambiguous_person_idx or _region_area(region) < MIN_REGION_AREA:
            continue
        for ci, (cls, box, conf) in enumerate(ppe_candidates):
            if cls not in HEAD_CLASSES or not _center_in(box, region):
                continue
            score, overlap, distance = _score(box, region, conf)
            head_matches.append((PpeMatch(pi, ci, cls, score, overlap, distance, conf), persons[pi], box))

    # --- Torso slot ---
    torso_matches: list[tuple[PpeMatch, tuple, tuple]] = []
    for pi, region in enumerate(torso_regions):
        if _region_area(region) < MIN_REGION_AREA:
            assignments[pi].vest_reason = "degenerate_region"
            continue
        for ci, (cls, box, conf) in enumerate(ppe_candidates):
            if cls not in TORSO_CLASSES or not _center_in(box, region):
                continue
            score, overlap, distance = _score(box, region, conf)
            torso_matches.append((PpeMatch(pi, ci, cls, score, overlap, distance, conf), persons[pi], box))

    def greedy_assign(matches: list[tuple[PpeMatch, tuple, tuple]]) -> list[PpeMatch]:
        ordered = sorted(matches, key=lambda t: _tiebreak_key(t[0], t[1], t[2]))
        claimed_person_slots: set[int] = set()
        claimed_candidates: set[int] = set()
        winners: list[PpeMatch] = []
        for m, _, _ in ordered:
            if m.person_idx in claimed_person_slots or m.candidate_idx in claimed_candidates:
                continue
            claimed_person_slots.add(m.person_idx)
            claimed_candidates.add(m.candidate_idx)
            winners.append(m)
        return winners

    for m in greedy_assign(head_matches):
        a = assignments[m.person_idx]
        a.matches.append(m)
        if m.ppe_class == "helmet":
            a.helmet_positive = True
            a.helmet_reason = f"assigned helmet score={m.score:.3f} overlap={m.overlap:.3f}"
        else:
            a.helmet_negative = True
            a.helmet_reason = f"assigned no_helmet score={m.score:.3f} overlap={m.overlap:.3f}"

    for m in greedy_assign(torso_matches):
        a = assignments[m.person_idx]
        a.matches.append(m)
        a.vest_positive = True
        a.vest_reason = f"assigned vest score={m.score:.3f} overlap={m.overlap:.3f}"

    return assignments
