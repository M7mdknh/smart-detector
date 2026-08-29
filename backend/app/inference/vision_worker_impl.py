"""Real YOLO11n + ByteTrack replay loop. Imported lazily by VisionWorker._run()
only when ultralytics/opencv are installed and a replay asset exists, so the
core demo never needs the heavy vision dependencies (requirements-vision.txt).

Pipeline (per vision-worker-safety/references/model-specification.md):
  decode frames -> detect -> ByteTrack -> per-person PPE/zone association
  -> timestamp dwell -> emit VisionEvidence(source=CV_MODEL)

`process_frame` is the testable core: given a loaded model, one decoded frame,
and per-track dwell state, it runs real detection+tracking and returns
VisionEvidenceRow objects (not yet added/committed) plus the updated dwell
state. `run_replay_loop` is a thin infinite-loop wrapper around it for the
background worker thread. The principal end-to-end test calls `process_frame`
directly against real frames and the real model -- no mocked detector.
"""

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.contracts.enums import DetectionClass, EvidenceSource, ModelStatus, PpeState, ZoneMembership
from app.inference.ppe_association import assign_ppe
from app.inference.zone_config import get_zone_config, point_in_polygon
from app.logging_config import get_logger
from app.settings import get_settings
from app.storage.db import get_session
from app.storage.models import VisionEvidenceRow

logger = get_logger(__name__)

_SPEC_DEFAULT_THRESHOLDS = {"person": 0.35, "helmet": 0.25, "vest": 0.30, "no_helmet": 0.25}
_THRESHOLDS_PATH = Path(__file__).parent / "ppe_thresholds.json"


def _load_class_conf_thresholds() -> dict[str, float]:
    """Loads validation-derived thresholds (Phase 3, scripts/tune_ppe_thresholds.py)
    if present and well-formed; otherwise falls back to the P0 spec's initial values.
    A malformed/missing file is not a hard failure -- it degrades to the documented
    default, same as every other model-adjacent config in this system."""
    if not _THRESHOLDS_PATH.exists():
        return dict(_SPEC_DEFAULT_THRESHOLDS)
    try:
        config = json.loads(_THRESHOLDS_PATH.read_text())
        thresholds = config["thresholds"]
        if set(thresholds) != set(_SPEC_DEFAULT_THRESHOLDS):
            logger.error("ppe_thresholds.json has an unexpected class set; using spec defaults")
            return dict(_SPEC_DEFAULT_THRESHOLDS)
        return {k: float(v) for k, v in thresholds.items()}
    except Exception:
        logger.exception("failed to load ppe_thresholds.json; using spec defaults")
        return dict(_SPEC_DEFAULT_THRESHOLDS)


CLASS_CONF_THRESHOLDS = _load_class_conf_thresholds()
BASE_TRACK_CONF = 0.20  # floor passed to model.track(); per-class thresholds above are applied after
NMS_IOU = 0.50
TARGET_FPS = 10.0

# Explicit path, not just the string "bytetrack.yaml": ultralytics silently returns
# boxes.id=None (is_track=False) if the tracker isn't passed explicitly alongside
# other kwargs like conf/iou on this version -- found live via a failing e2e test
# ("expected ByteTrack to assign at least one anonymous track_id"). Using our own
# checked-in config (not ultralytics' bundled default) also gets us the spec's exact
# threshold values instead of the vendor defaults.
TRACKER_CONFIG_PATH = str(Path(__file__).parent / "bytetrack.yaml")

# Dataset label names differ from runtime names only for "Person" -> "person".
DATASET_TO_RUNTIME_CLASS = {"Person": "person", "helmet": "helmet", "vest": "vest", "no_helmet": "no_helmet"}

HEAD_REGION_TOP = 0.0
HEAD_REGION_BOTTOM = 0.35
HEAD_REGION_EXPAND_X = 0.10
TORSO_TOP = 0.25
TORSO_BOTTOM = 0.75
TORSO_LEFT = 0.10
TORSO_RIGHT = 0.90

ZONE_ENTER_SECONDS = 2.0
ZONE_EXIT_SECONDS = 2.0
PPE_VIOLATION_SECONDS = 3.0
PPE_CLEAR_SECONDS = 5.0

# Zone geometry now comes from the versioned, backend-owned config
# (app/inference/zone_config.py / zone_config.json) instead of hardcoded
# bounding-box constants -- real polygons (>=3 points), validated, normalized
# to [0,1] camera coordinates independent of source resolution. The bundled
# replay is a slideshow of distinct licensed still images (see
# demo-assets/REPLAY_SOURCE.md), not one continuous factory floor shot, so the
# default demo geometry is still a left/right split -- but it is now data, not code.


def _head_region(box):
    x1, y1, x2, y2 = box
    h = y2 - y1
    w = x2 - x1
    expand = w * HEAD_REGION_EXPAND_X
    return (x1 - expand, y1 + h * HEAD_REGION_TOP, x2 + expand, y1 + h * HEAD_REGION_BOTTOM)


def _torso_region(box):
    x1, y1, x2, y2 = box
    h = y2 - y1
    w = x2 - x1
    return (x1 + w * TORSO_LEFT, y1 + h * TORSO_TOP, x1 + w * TORSO_RIGHT, y1 + h * TORSO_BOTTOM)


@dataclass
class TrackDwell:
    gas_membership: ZoneMembership = ZoneMembership.OUTSIDE
    gas_in_since: datetime | None = None
    gas_out_since: datetime | None = None
    overhead_membership: ZoneMembership = ZoneMembership.OUTSIDE
    overhead_in_since: datetime | None = None
    overhead_out_since: datetime | None = None
    restricted_membership: ZoneMembership = ZoneMembership.OUTSIDE
    restricted_in_since: datetime | None = None
    restricted_out_since: datetime | None = None
    helmet_state: PpeState = PpeState.UNKNOWN
    helmet_positive_since: datetime | None = None
    helmet_negative_since: datetime | None = None
    vest_state: PpeState = PpeState.UNKNOWN
    vest_positive_since: datetime | None = None
    vest_negative_since: datetime | None = None


def _apply_dwell(now, is_true, since_true, since_false, enter_s, exit_s, current, true_state, false_state):
    """Binary debounce for zone membership (single enter/exit timer)."""
    if is_true:
        since_false = None
        since_true = since_true or now
        if (now - since_true).total_seconds() >= enter_s:
            current = true_state
    else:
        since_true = None
        since_false = since_false or now
        if (now - since_false).total_seconds() >= exit_s:
            current = false_state
    return current, since_true, since_false


def _apply_ppe_dwell(now, positive, negative, state, positive_since, negative_since):
    """Three-tier PPE state machine, per model-specification.md's "Temporal State":
    positive evidence -> COMPLIANT after 1s (or after 5s if clearing an existing
    violation); negative/missing evidence -> NON_COMPLIANT after 3s persistence.
    Neither continuously true resets its own timer but does not flip the state
    (single-frame flicker doesn't cause a transition either way)."""
    positive_since = positive_since if positive else None
    negative_since = negative_since if negative else None

    if positive:
        positive_since = positive_since or now
        held = (now - positive_since).total_seconds()
        required = PPE_CLEAR_SECONDS if state == PpeState.NON_COMPLIANT else 1.0
        if held >= required:
            state = PpeState.COMPLIANT
    elif negative:
        negative_since = negative_since or now
        if (now - negative_since).total_seconds() >= PPE_VIOLATION_SECONDS:
            state = PpeState.NON_COMPLIANT

    return state, positive_since, negative_since


def load_model(model_path=None):
    """Returns (model, model_version, person_only, status).

    Verifies the configured artifact's path AND sha256 (models/registry.json,
    "ppe_detector") BEFORE ever constructing ultralytics.YOLO. This never loads a
    bare pretrained-name string (e.g. "yolo11n.pt") -- that form triggers an
    automatic network download and would silently swap in a non-fine-tuned,
    non-PPE model, which is exactly the "fake CV" / dishonest-degradation failure
    mode CLAUDE.md forbids. On a missing artifact or checksum mismatch this
    returns (None, None, True, ModelStatus.UNAVAILABLE) and makes no network call
    and constructs no model object; the caller (run_replay_loop) must keep the
    camera/replay stream running and report detector health separately, without
    fabricating PPE compliance.

    The DEFAULT artifact filename (used when model_path is not given) is read
    from models/registry.json's "ppe_detector.artifact_path" field, not
    hardcoded -- this is what lets a promotion switch the active model by
    editing the registry pointer alone, without overwriting any artifact file
    on disk. If the registry is missing/unreadable, this falls back to the
    v1.1 filename "ppe-yolo11n.pt" (the only artifact ever bundled before this
    field existed)."""
    settings = get_settings()

    ppe_detector_meta: dict = {}
    registry_path = settings.model_registry_path
    if registry_path.exists():
        try:
            registry = json.loads(registry_path.read_text())
            ppe_detector_meta = registry.get("ppe_detector", {})
        except Exception:
            logger.exception("failed to read model registry for ppe_detector")

    expected_sha256 = ppe_detector_meta.get("sha256")
    registry_artifact_path = ppe_detector_meta.get("artifact_path")
    default_filename = Path(registry_artifact_path).name if registry_artifact_path else "ppe-yolo11n.pt"
    registry_version = ppe_detector_meta.get("version", "1.1")

    path = model_path or (settings.models_dir / "artifacts" / default_filename)
    relative_path = f"models/artifacts/{path.name}"  # logged instead of the absolute path
    # Checksum verification gates any path that CLAIMS to be the registry's
    # currently active artifact -- whether resolved as the default or passed
    # explicitly with the same filename (e.g. a corrupted/tampered copy of
    # the active weights). A path with a DIFFERENT filename (e.g. an
    # unpromoted candidate under its own name) is never checked against the
    # active registry's expected hash -- it never claimed to be that artifact.
    claims_to_be_registry_default = path.name == default_filename

    if not path.exists():
        logger.error(
            "PPE model artifact missing; detector unavailable, no fallback download attempted",
            extra={"extra_fields": {"artifact_path": relative_path}},
        )
        return None, None, True, ModelStatus.UNAVAILABLE

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if claims_to_be_registry_default and expected_sha256:
        if digest != expected_sha256:
            logger.error(
                "PPE model artifact checksum mismatch; detector unavailable, no fallback download attempted",
                extra={
                    "extra_fields": {
                        "artifact_path": relative_path,
                        "expected_sha256": expected_sha256,
                        "actual_sha256": digest,
                    }
                },
            )
            return None, None, True, ModelStatus.UNAVAILABLE
    elif claims_to_be_registry_default and not expected_sha256:
        logger.warning("model registry missing ppe_detector sha256; loading artifact without checksum verification")

    from ultralytics import YOLO

    # Only label the model with the registry's active version when this really
    # is the registry-verified artifact (sha256 matches, whether resolved as
    # the default or passed explicitly); a mismatched override (e.g.
    # evaluating an unpromoted candidate) is labelled from its own filename
    # instead of borrowing the active version's name.
    if expected_sha256 and digest == expected_sha256:
        model_version = f"ppe-yolo11n-{registry_version}"
    else:
        model_version = path.stem

    # The checksum gate above only protects the registry-verified default
    # path; an explicit override skips it deliberately (candidate evaluation).
    # Either way, never let a corrupt/unreadable checkpoint crash the caller --
    # a file that merely LOOKS present but isn't a real checkpoint must still
    # degrade honestly instead of raising out of this function.
    try:
        model = YOLO(str(path))
    except Exception:
        logger.exception(
            "PPE model artifact failed to load; detector unavailable",
            extra={"extra_fields": {"artifact_path": relative_path}},
        )
        return None, None, True, ModelStatus.UNAVAILABLE
    return model, model_version, False, ModelStatus.OK


def parse_detections(model, results, person_only: bool):
    """Extracts (persons, ppe_candidates) from one ultralytics Results object,
    applying the runtime class filter and per-class confidence thresholds.
    Split out from process_frame so it's exercised by the real-detector e2e
    test, while `associate_and_dwell` below covers edge cases deterministically."""
    boxes = results[0].boxes
    persons: list[tuple[int | None, tuple[float, float, float, float], float]] = []
    ppe_candidates: list[tuple[str, tuple[float, float, float, float], float]] = []

    for i in range(len(boxes)):
        cls_id = int(boxes.cls[i])
        raw_name = model.names[cls_id]
        name = DATASET_TO_RUNTIME_CLASS.get(raw_name, raw_name)
        if name not in CLASS_CONF_THRESHOLDS:
            continue  # ignore dataset classes outside the runtime set (gloves, boots, goggles, ...)
        conf = float(boxes.conf[i])
        if conf < CLASS_CONF_THRESHOLDS[name]:
            continue
        x1, y1, x2, y2 = (float(v) for v in boxes.xyxyn[i])
        box = (x1, y1, x2, y2)
        track_id = int(boxes.id[i]) if boxes.id is not None else None

        if name == "person":
            persons.append((track_id, box, conf))
        elif not person_only and name in ("helmet", "vest", "no_helmet"):
            ppe_candidates.append((name, box, conf))

    return persons, ppe_candidates


def associate_and_dwell(
    persons: list[tuple[int | None, tuple[float, float, float, float], float]],
    ppe_candidates: list[tuple[str, tuple[float, float, float, float], float]],
    frame_id: int,
    event_time: datetime,
    tracks: dict[int, TrackDwell],
    model_version: str,
    camera_id: str = "camera-1",
    zone_id: str = "zone-1",
) -> list[VisionEvidenceRow]:
    """Pure association/dwell/zone logic, deterministic given its inputs -- no
    model call. This is what edge-case unit tests (ambiguous PPE, tracker loss)
    exercise directly with synthetic (persons, ppe_candidates) lists, per
    CLAUDE.md's "unit tests may use deterministic adapters" allowance."""
    rows: list[VisionEvidenceRow] = []

    # Global one-to-one assignment across ALL detected persons in this frame
    # (tracked or not) so a PPE box's fate is decided fairly regardless of
    # tracker state, before any per-person dwell/state logic runs. See
    # app/inference/ppe_association.py for the algorithm.
    person_boxes = [box for _, box, _ in persons]
    assignments = assign_ppe(person_boxes, ppe_candidates, _head_region, _torso_region)

    for person_idx, (track_id, box, conf) in enumerate(persons):
        assignment = assignments[person_idx]
        if track_id is None:
            # Tracker failure: emit the box but do not open per-track dwell incidents.
            # Fields are set explicitly (not left to the ORM column default, which only
            # applies at flush/insert time -- an in-memory-only row would otherwise read
            # back as None rather than the intended "UNKNOWN").
            rows.append(
                VisionEvidenceRow(
                    evidence_id=str(uuid.uuid4()), camera_id=camera_id, zone_id=zone_id, frame_id=frame_id,
                    event_time=event_time, ingested_at=event_time, source=EvidenceSource.CV_MODEL.value,
                    model_version=model_version, track_id=None, detected_class=DetectionClass.PERSON.value,
                    confidence=conf, bbox_x1=box[0], bbox_y1=box[1], bbox_x2=box[2], bbox_y2=box[3],
                    helmet_state=PpeState.UNKNOWN.value, vest_state=PpeState.UNKNOWN.value,
                    gas_zone_membership=ZoneMembership.UNKNOWN.value, overhead_zone_membership=ZoneMembership.UNKNOWN.value,
                    restricted_zone_membership=ZoneMembership.UNKNOWN.value,
                )
            )
            continue

        dwell = tracks.setdefault(track_id, TrackDwell())
        bottom_center = ((box[0] + box[2]) / 2, box[3])

        zone_config = get_zone_config()
        gas_zone = zone_config.zone_of_type("GAS_EXPOSURE")
        overhead_zone = zone_config.zone_of_type("OVERHEAD_WORK")
        vest_zone = zone_config.zone_of_type("MANDATORY_VEST")
        restricted_zone = zone_config.zone_of_type("RESTRICTED")

        in_gas = bool(gas_zone) and point_in_polygon(bottom_center[0], bottom_center[1], gas_zone.points)
        dwell.gas_membership, dwell.gas_in_since, dwell.gas_out_since = _apply_dwell(
            event_time, in_gas, dwell.gas_in_since, dwell.gas_out_since, ZONE_ENTER_SECONDS, ZONE_EXIT_SECONDS,
            dwell.gas_membership, ZoneMembership.INSIDE, ZoneMembership.OUTSIDE,
        )
        in_overhead = bool(overhead_zone) and point_in_polygon(bottom_center[0], bottom_center[1], overhead_zone.points)
        dwell.overhead_membership, dwell.overhead_in_since, dwell.overhead_out_since = _apply_dwell(
            event_time, in_overhead, dwell.overhead_in_since, dwell.overhead_out_since, ZONE_ENTER_SECONDS, ZONE_EXIT_SECONDS,
            dwell.overhead_membership, ZoneMembership.INSIDE, ZoneMembership.OUTSIDE,
        )
        in_vest_zone = bool(vest_zone) and point_in_polygon(bottom_center[0], bottom_center[1], vest_zone.points)
        in_restricted = bool(restricted_zone) and point_in_polygon(bottom_center[0], bottom_center[1], restricted_zone.points)
        dwell.restricted_membership, dwell.restricted_in_since, dwell.restricted_out_since = _apply_dwell(
            event_time, in_restricted, dwell.restricted_in_since, dwell.restricted_out_since, ZONE_ENTER_SECONDS, ZONE_EXIT_SECONDS,
            dwell.restricted_membership, ZoneMembership.INSIDE, ZoneMembership.OUTSIDE,
        )

        # PPE evidence for this specific person comes from the global one-to-one
        # assignment computed above -- a helmet/vest box already claimed by
        # another competing person cannot also make this one look compliant.
        if assignment.helmet_ambiguous:
            dwell.helmet_state = PpeState.UNKNOWN
            dwell.helmet_positive_since = None
            dwell.helmet_negative_since = None
        else:
            helmet_negative = assignment.helmet_negative or (in_overhead and not assignment.helmet_positive and not assignment.helmet_negative)
            dwell.helmet_state, dwell.helmet_positive_since, dwell.helmet_negative_since = _apply_ppe_dwell(
                event_time, assignment.helmet_positive, helmet_negative, dwell.helmet_state,
                dwell.helmet_positive_since, dwell.helmet_negative_since,
            )

        # No "no_vest" class exists in the dataset (model-specification.md): absence of
        # an *assigned* vest, while inside the configured mandatory-vest zone, is the
        # negative signal; outside that zone a missing vest stays UNKNOWN rather than
        # a violation.
        vest_negative = in_vest_zone and not assignment.vest_positive
        dwell.vest_state, dwell.vest_positive_since, dwell.vest_negative_since = _apply_ppe_dwell(
            event_time, assignment.vest_positive, vest_negative, dwell.vest_state,
            dwell.vest_positive_since, dwell.vest_negative_since,
        )

        rows.append(
            VisionEvidenceRow(
                evidence_id=str(uuid.uuid4()), camera_id=camera_id, zone_id=zone_id, frame_id=frame_id,
                event_time=event_time, ingested_at=event_time, source=EvidenceSource.CV_MODEL.value,
                model_version=model_version, track_id=track_id, detected_class=DetectionClass.PERSON.value,
                confidence=conf, bbox_x1=box[0], bbox_y1=box[1], bbox_x2=box[2], bbox_y2=box[3],
                helmet_state=dwell.helmet_state.value, vest_state=dwell.vest_state.value,
                gas_zone_membership=dwell.gas_membership.value, overhead_zone_membership=dwell.overhead_membership.value,
                restricted_zone_membership=dwell.restricted_membership.value,
                dwell_seconds=(event_time - dwell.gas_in_since).total_seconds() if dwell.gas_in_since else None,
            )
        )

    return rows


def process_frame_full(
    model,
    frame,
    frame_id: int,
    event_time: datetime,
    tracks: dict[int, TrackDwell],
    person_only: bool,
    model_version: str,
    camera_id: str = "camera-1",
    zone_id: str = "zone-1",
):
    """Like process_frame, but also returns the raw (persons, ppe_candidates)
    the evidence rows were built from, so a caller that needs to render an
    annotated frame (app/inference/frame_annotation.py) doesn't have to re-run
    detection. process_frame() below is the thin, signature-stable wrapper
    used by process_frame's existing callers/tests."""
    results = model.track(frame, persist=True, verbose=False, conf=BASE_TRACK_CONF, iou=NMS_IOU, tracker=TRACKER_CONFIG_PATH)
    persons, ppe_candidates = parse_detections(model, results, person_only)
    rows = associate_and_dwell(persons, ppe_candidates, frame_id, event_time, tracks, model_version, camera_id, zone_id)
    return rows, persons, ppe_candidates


def process_frame(
    model,
    frame,
    frame_id: int,
    event_time: datetime,
    tracks: dict[int, TrackDwell],
    person_only: bool,
    model_version: str,
    camera_id: str = "camera-1",
    zone_id: str = "zone-1",
) -> list[VisionEvidenceRow]:
    """Runs the REAL detector+tracker on one frame and applies association/dwell.
    This is the function the principal end-to-end test calls -- no mocked detector."""
    rows, _persons, _ppe_candidates = process_frame_full(
        model, frame, frame_id, event_time, tracks, person_only, model_version, camera_id, zone_id
    )
    return rows


def run_replay_loop(worker) -> None:
    import cv2

    settings = get_settings()
    model, model_version, person_only, detector_status = load_model()
    worker.model_version = model_version
    worker.detector_status = detector_status.value

    cap = cv2.VideoCapture(str(settings.vision_replay_path))
    if not cap.isOpened():
        logger.error("failed to open replay video")
        worker.camera_status = "UNAVAILABLE"
        worker.status = "UNAVAILABLE"
        return

    # Camera/replay stream and the PPE detector are independent health signals
    # (CLAUDE.md "honest degradation"): the bundled video can decode fine while
    # the fine-tuned model artifact is missing/corrupt, and that must show as
    # camera=HEALTHY, detector=MODEL_UNAVAILABLE, combined vision=DEGRADED --
    # never a fabricated "0 people at risk" or a silently swapped-in model.
    worker.camera_status = "HEALTHY"
    worker.status = "OK" if detector_status == ModelStatus.OK else "DEGRADED"
    frame_id = 0
    tracks: dict[int, TrackDwell] = {}
    min_interval = 1.0 / TARGET_FPS
    last_frame_time = 0.0

    while True:
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # loop the bundled replay
            continue

        now_wall = time.monotonic()
        if now_wall - last_frame_time < min_interval:
            continue
        last_frame_time = now_wall
        frame_id += 1

        if model is None:
            # Detector unavailable: keep decoding frames (camera stays HEALTHY)
            # but emit no CV_MODEL evidence at all rather than fabricate
            # PPE/zone compliance. Callers must treat "no recent evidence" plus
            # detector_status=MODEL_UNAVAILABLE as UNKNOWN, not as a safe scene.
            worker.observed_fps = 1.0 / max(1e-6, time.monotonic() - now_wall + min_interval)
            continue

        session = get_session()
        try:
            event_time = datetime.now(timezone.utc)
            rows, persons, ppe_candidates = process_frame_full(model, frame, frame_id, event_time, tracks, person_only, model_version)
            for row in rows:
                session.add(row)
            worker.observed_fps = 1.0 / max(1e-6, time.monotonic() - now_wall + min_interval)
            session.commit()

            _cache_annotated_frame(frame, persons, ppe_candidates, tracks, model_version, event_time, frame_id)
        finally:
            session.close()


def _cache_annotated_frame(frame, persons, ppe_candidates, tracks, model_version, event_time, frame_id, camera_id: str = "camera-1") -> None:
    """Renders the real annotated frame and caches it (app/inference/frame_cache.py).

    Two independent consumers read this cache: app/services/evidence_image.py
    (interview_demo_mode only, to attach a genuine captured frame to a
    CV_MODEL-driven incident) and GET /api/v1/vision/frame.jpg (always, so the
    live /dashboard camera panel can display real annotated pixels -- boxes,
    labels, track IDs, and zone polygons burned into an actual decoded replay
    frame -- rather than structured detection text alone). Always run, not
    gated to interview_demo_mode: the default simulator-driven dashboard demo
    still benefits from seeing genuine CV output, even though its incidents
    remain SIMULATION_GROUND_TRUTH-driven. The render cost (OpenCV drawing on
    one frame at TARGET_FPS=10) is negligible on CPU. Best-effort: a rendering
    failure must never break frame ingestion."""
    try:
        import cv2

        from app.inference.frame_annotation import render_annotated_frame
        from app.inference.frame_cache import set_latest_frame

        annotated = render_annotated_frame(frame, persons, ppe_candidates, tracks, get_zone_config(), model_version, event_time, frame_id)
        ok, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if ok:
            set_latest_frame(camera_id, buf.tobytes(), frame_id, event_time)
    except Exception:
        logger.exception("failed to render/cache annotated frame for interview-demo evidence capture")
