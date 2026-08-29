from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.logging_config import get_logger
from app.services.ws_hub import hub

router = APIRouter()
logger = get_logger(__name__)


@router.websocket("/api/v1/ws")
async def ws_endpoint(websocket: WebSocket):
    await hub.connect(websocket)
    try:
        while True:
            # Client is not required to send anything; read to detect disconnect.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(websocket)
