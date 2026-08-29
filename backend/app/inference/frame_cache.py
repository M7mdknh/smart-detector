"""Tiny in-process cache of the most recent REAL annotated camera/replay frame
per camera_id, JPEG-encoded. Lets app/services/evidence_image.py attach a
genuine captured frame to a CV_MODEL-driven incident instead of a schematic
reconstruction, without threading frame bytes through the DB row itself.

Process-local only (no persistence, no cross-process sharing) -- correct for
this project's single-process backend. Bounded to one entry per camera_id, so
memory use does not grow with runtime.
"""

from datetime import datetime

_LATEST: dict[str, tuple[bytes, int, datetime]] = {}


def set_latest_frame(camera_id: str, jpeg_bytes: bytes, frame_id: int, event_time: datetime) -> None:
    _LATEST[camera_id] = (jpeg_bytes, frame_id, event_time)


def get_latest_frame(camera_id: str, now: datetime, max_age_seconds: float = 30.0) -> tuple[bytes, int, datetime] | None:
    """Returns (jpeg_bytes, frame_id, event_time) if a frame was cached for this
    camera within max_age_seconds of `now`, else None -- never a stale frame
    silently presented as current."""
    entry = _LATEST.get(camera_id)
    if entry is None:
        return None
    jpeg_bytes, frame_id, event_time = entry
    if (now - event_time).total_seconds() > max_age_seconds:
        return None
    return jpeg_bytes, frame_id, event_time


def reset_for_tests() -> None:
    _LATEST.clear()
