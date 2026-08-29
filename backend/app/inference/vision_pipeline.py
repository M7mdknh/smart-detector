"""YOLO11n + ByteTrack replay adapter.

Runs as an in-process background worker started at app startup. Decodes the
bundled replay video, runs detection/tracking, associates PPE/zone evidence,
and writes VisionEvidence rows with source=CV_MODEL. Never blocks ingestion or
the physics/risk pipeline: model/camera failure sets status=UNAVAILABLE and the
dashboard shows a degraded camera panel, not a fabricated safe scene.
"""

import threading
from dataclasses import dataclass, field

from app.logging_config import get_logger
from app.settings import get_settings

logger = get_logger(__name__)

MODEL_VERSION = "unavailable"


@dataclass
class VisionWorker:
    status: str = "UNAVAILABLE"  # combined summary: OK / DEGRADED / UNAVAILABLE
    camera_status: str = "UNAVAILABLE"  # HEALTHY iff the replay/camera stream is decoding frames
    detector_status: str = "UNAVAILABLE"  # ModelStatus value: OK / UNAVAILABLE -- independent of camera_status
    model_version: str | None = None
    observed_fps: float | None = None
    _thread: threading.Thread | None = field(default=None, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)

    def start(self) -> None:
        settings = get_settings()
        if not settings.vision_replay_path.exists():
            logger.warning(
                "vision replay asset missing; camera stays degraded",
                extra={"extra_fields": {"path": str(settings.vision_replay_path)}},
            )
            self.status = "UNAVAILABLE"
            self.camera_status = "UNAVAILABLE"
            self.detector_status = "UNAVAILABLE"
            return
        try:
            import cv2  # noqa: F401
            from ultralytics import YOLO  # noqa: F401
        except ImportError:
            logger.warning("ultralytics/opencv not installed; camera stays degraded (install backend/requirements-vision.txt)")
            self.status = "UNAVAILABLE"
            self.camera_status = "UNAVAILABLE"
            self.detector_status = "UNAVAILABLE"
            return

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        from app.inference.vision_worker_impl import run_replay_loop

        try:
            run_replay_loop(self)
        except Exception:
            logger.exception("vision worker crashed; camera degraded")
            self.status = "UNAVAILABLE"
            self.camera_status = "UNAVAILABLE"
            self.detector_status = "UNAVAILABLE"


_worker: VisionWorker | None = None


def get_vision_worker() -> VisionWorker:
    global _worker
    if _worker is None:
        _worker = VisionWorker()
    return _worker


def reset_vision_worker_for_tests() -> None:
    global _worker
    _worker = None
