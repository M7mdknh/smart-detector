"""In-process WebSocket hub. Publishes projections only after DB commit."""

import asyncio
import itertools
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

from app.contracts.events import WsEvent
from app.logging_config import get_logger

logger = get_logger(__name__)


class WsHub:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._seq = itertools.count(1)
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)

    async def publish(self, event_type: str, event_time: datetime, payload: dict[str, Any], correlation_id: str) -> None:
        event = WsEvent(
            event_id=uuid.uuid4(),
            sequence=next(self._seq),
            type=event_type,
            event_time=event_time,
            published_at=datetime.now(timezone.utc),
            correlation_id=correlation_id,
            payload=payload,
        )
        data = event.model_dump_json()
        dead: list[WebSocket] = []
        async with self._lock:
            targets = list(self._connections)
        for ws in targets:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)


hub = WsHub()
