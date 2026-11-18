
import asyncio
import time

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.exceptions import HTTPException

from app.chats.websocket.manager import manager
from app.chats.services import ChatServices

from app.config import settings

from app.core.database import AsyncSessionLocal
from app.core.security import authenticate_user

from app.exceptions import (
    ChatNotFoundException,
    ChatReadOnlyException,
    InvalidMessageTextException,
)

from app.core.logger import get_logger


logger = get_logger(__name__)

router = APIRouter(prefix="/chats", tags=["Chats WebSocket"])

AUTH_TIMEOUT = 5
PING_INTERVAL = 30
PONG_TIMEOUT = 60

MESSAGE_RATE_LIMIT = 1.0

last_message_at: dict[int, float] = {}


@router.websocket("/ws")
async def chat_websocket(
    websocket: WebSocket,
) -> None:
    await websocket.accept()

    try:
        data = await asyncio.wait_for(
            websocket.receive_json(),
            timeout=AUTH_TIMEOUT,
        )

        if (
            not isinstance(data, dict)
            or data.get("type") != "auth"
            or not isinstance(data.get("token"), str)
        ):
            await websocket.close(code=4003)
            return

        token = data["token"]
        async with AsyncSessionLocal() as db:
            user = await authenticate_user(token, db)

        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        token_exp = payload["exp"]

    except (
        asyncio.TimeoutError,
        HTTPException,
        jwt.PyJWTError,
        ValueError,
        KeyError,
        TypeError,
    ):
        await websocket.close(code=4003)
        return

    except WebSocketDisconnect:
        return

    manager.connect(user.id, websocket)

    next_ping_at = time.monotonic() + PING_INTERVAL
    pending_ping_at: float | None = None

    try:
        while True:
            now = time.monotonic()

            if time.time() >= token_exp:
                await websocket.close(code=4003)
                break

            if (
                pending_ping_at is not None
                and now - pending_ping_at >= PONG_TIMEOUT
            ):
                await websocket.close(code=4000)
                break

            if (
                pending_ping_at is None
                and now >= next_ping_at
            ):
                await websocket.send_json({"type": "ping"})

                pending_ping_at = now
                continue

            if pending_ping_at is not None:
                timeout = min(
                    PONG_TIMEOUT - (now - pending_ping_at),
                    token_exp - time.time(),
                )
            else:
                timeout = min(
                    next_ping_at - now,
                    token_exp - time.time(),
                )

            try:
                message = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=max(timeout, 0.001),
                )

            except asyncio.TimeoutError:
                continue

            except ValueError:
                await websocket.send_json({
                    "type": "error",
                    "detail": "Invalid JSON",
                })
                continue

            if not isinstance(message, dict):
                await websocket.send_json({
                    "type": "error",
                    "detail": "Invalid event format",
                })
                continue

            if message.get("type") == "pong":
                if pending_ping_at is not None:
                    pending_ping_at = None
                    next_ping_at = time.monotonic() + PING_INTERVAL

            elif message.get("type") == "message":
                chat_id = message.get("chat_id")
                text = message.get("text")

                if (
                    not isinstance(chat_id, int)
                    or isinstance(chat_id, bool)
                    or chat_id <= 0
                    or not isinstance(text, str)
                ):
                    await websocket.send_json({
                        "type": "error",
                        "detail": "Invalid message format",
                    })
                    continue

                now = time.monotonic()
                last_sent = last_message_at.get(user.id, 0.0)

                if now - last_sent < MESSAGE_RATE_LIMIT:
                    await websocket.send_json({
                        "type": "error",
                        "detail": "rate_limit",
                    })
                    continue

                last_message_at[user.id] = now

                try:
                    async with AsyncSessionLocal() as db:
                        chat_services = ChatServices(db)

                        saved_message = await chat_services.create_message(
                            chat_id=chat_id,
                            user_id=user.id,
                            text=text,
                        )

                        user_ids = await chat_services.get_chat_member_ids(chat_id)

                    await manager.broadcast_to_users(
                        user_ids,
                        {
                            "type": "new_message",
                            "data": saved_message.model_dump(mode="json"),
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
