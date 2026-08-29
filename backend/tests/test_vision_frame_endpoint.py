"""GET /api/v1/vision/frame.jpg: serves the latest real annotated replay frame
(app/inference/frame_cache.py) for the dashboard camera panel's live image.
Route function called directly, matching this suite's existing convention
(see tests/test_dashboard_snapshot_scoping.py) -- no GPU/video needed since
the cache is populated directly, same technique as
tests/test_interview_demo_wiring.py's frame_cache round-trip tests.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.api.routes import vision_frame
from app.contracts.errors import ApiError
from app.inference import frame_cache


@pytest.fixture(autouse=True)
def _reset_frame_cache():
    frame_cache.reset_for_tests()
    yield
    frame_cache.reset_for_tests()


def test_vision_frame_returns_cached_jpeg_bytes():
    now = datetime.now(timezone.utc)
    real_bytes = b"\xff\xd8\xff\xe0fake-but-nontrivial-jpeg-payload" * 10
    frame_cache.set_latest_frame("camera-1", real_bytes, 42, now)

    response = vision_frame()

    assert response.media_type == "image/jpeg"
    assert response.body == real_bytes
    assert len(response.body) > 100
    assert response.headers["X-Frame-Id"] == "42"
    assert response.headers["Cache-Control"] == "no-store"


def test_vision_frame_404_when_no_frame_cached():
    with pytest.raises(ApiError) as exc_info:
        vision_frame()

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "CAMERA_DEGRADED"


def test_vision_frame_404_when_cached_frame_stale():
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=120)
    frame_cache.set_latest_frame("camera-1", b"stale-jpeg-bytes", 1, stale_time)

    with pytest.raises(ApiError) as exc_info:
        vision_frame()

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "CAMERA_DEGRADED"


def test_vision_frame_never_serves_a_different_camera():
    frame_cache.set_latest_frame("camera-other", b"unrelated-jpeg-bytes", 1, datetime.now(timezone.utc))

    with pytest.raises(ApiError) as exc_info:
        vision_frame()

    assert exc_info.value.status_code == 404
