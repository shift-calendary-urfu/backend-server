import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.chats.websocket.manager import manager

from app.core.database import get_db
from app.core.security import authenticate_user

from app.core.logger import get_logger


logger = get_logger(__name__)

router = APIRouter(prefix="/chats", tags=["Chats WebSocket"])


@router.websocket("/ws")
async def chat_websocket(
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),
) -> None:
    await websocket.accept()

    try:
        data = await asyncio.wait_for(
            websocket.receive_json(),
            timeout=5,
        )

        if (
            not isinstance(data, dict)
            or data.get("type") != "auth"
            or not isinstance(data.get("token"), str)
        ):
            await websocket.close(code=4003)
            return

        user = await authenticate_user(data["token"], db)

    except (asyncio.TimeoutError, HTTPException, ValueError):
        await websocket.close(code=4003)
        return
    except WebSocketDisconnect:
        return

    manager.connect(user.id, websocket)

    try:
        while True:
            await websocket.receive()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(user.id, websocket)