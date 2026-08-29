import uuid
from datetime import datetime, timezone

import pytest

from app.storage import db as db_module
from app.storage.db import Base


@pytest.fixture
def session(tmp_path, monkeypatch):
    db_path = tmp_path / f"test-{uuid.uuid4().hex}.db"
    url = f"sqlite:///{db_path}"
    db_module.reset_engine_for_tests(url)
    Base.metadata.create_all(db_module.get_engine())

    from app.inference import leak_model, vision_pipeline

    leak_model.reset_leak_model_for_tests()
    vision_pipeline.reset_vision_worker_for_tests()

    s = db_module.get_session()
    yield s
    s.close()


@pytest.fixture
def now():
    return datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
