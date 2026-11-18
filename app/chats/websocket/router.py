import asyncio
import time

import jwt
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.chats.websocket.manager import manager
from app.chats.services import ChatServices

from app.config import settings

from app.core.database import get_db
from app.core.security import authenticate_user

from app.exceptions import (
    ChatNotFoundException,
    ChatReadOnlyException,
    InvalidMessageTextException,
)

from app.core.logger import get_logger


logger = get_logger(__name__)

router = APIRouter(prefix="/chats", tags=["Chats WebSocket"])

PING_INTERVAL = 30
PONG_TIMEOUT = 60


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

        token = data["token"]
        user = await authenticate_user(token, db)

        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        token_exp = payload["exp"]

    except (asyncio.TimeoutError, HTTPException, jwt.PyJWTError, ValueError, KeyError):
        await websocket.close(code=4003)
        return
    except WebSocketDisconnect:
        return

    manager.connect(user.id, websocket)

    last_pong = time.monotonic()

    try:
        while True:
            if time.time() >= token_exp:
                await websocket.close(code=4003)
                break

            if time.monotonic() - last_pong >= PONG_TIMEOUT:
                await websocket.close(code=4000)
                break

            try:
                message = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=PING_INTERVAL,
                )
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
                continue

            if not isinstance(message, dict):
                await websocket.send_json({
                    "type": "error",
                    "detail": "Invalid event format",
                })
                continue

            if message.get("type") == "pong":
                last_pong = time.monotonic()

            elif message.get("type") == "message":
                chat_id = message.get("chat_id")
                text = message.get("text")

                if (
                    not isinstance(chat_id, int)
                    or isinstance(chat_id, bool)
                    or not isinstance(text, str)
                ):
                    await websocket.send_json({
                        "type": "error",
                        "detail": "Invalid message format",
                    })
                    continue

                chat_services = ChatServices(db)

                try:
                    saved_message = await chat_services.create_message(
                        chat_id=chat_id,
                        user_id=user.id,
                        text=text,
                    )

                    user_ids = await chat_services.get_chat_member_ids(chat_id)

                    await manager.broadcast_to_users(
                        user_ids=user_ids,
                        message={
                            "type": "new_message",
                            "message": saved_message.model_dump(mode="json"),
                        },
                    )

                except ChatNotFoundException as e:
                    await websocket.send_json({
                        "type": "error",
                        "detail": e.msg,
                    })

                except ChatReadOnlyException as e:
                    await websocket.send_json({
                        "type": "error",
                        "detail": e.msg,
                    })

                except InvalidMessageTextException as e:
                    await websocket.send_json({
                        "type": "error",
                        "detail": e.msg,
                    })

            else:
                await websocket.send_json({
                    "type": "error",
                    "detail": "Неизвестное событие",
                })

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(user.id, websocket)