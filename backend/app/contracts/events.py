from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class WsEvent(BaseModel):
    schema_version: str = "1.0"
    event_id: UUID
    sequence: int
    type: str
    event_time: datetime
    published_at: datetime
    correlation_id: str
    payload: dict[str, Any]
