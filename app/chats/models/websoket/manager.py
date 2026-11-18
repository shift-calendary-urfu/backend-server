from fastapi import WebSocket

from app.core.logger import get_logger


logger = get_logger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        logger.info("Подключение к WS user_id=%d", user_id)
        self.active_connections.setdefault(user_id, []).append(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        connections = self.active_connections.get(user_id)

        if connections is None:
            logger.warning("Попытка отключиться от несуществующего соединения, user_id=%d", user_id)
            return

        if websocket in connections:
            logger.info("Отключение соединения, user_id=%d", user_id)
            connections.remove(websocket)

        if not connections:
            logger.info("Отключение всех соединений, user_id=%d", user_id)
            del self.active_connections[user_id]

    def is_connected(self, user_id: int) -> bool:
        return bool(self.active_connections.get(user_id))


manager = ConnectionManager()