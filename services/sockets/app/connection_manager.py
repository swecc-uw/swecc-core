from fastapi import WebSocket
from typing import Dict, Set
import logging
from .handlers import HandlerKind
from typing import Optional

logger = logging.getLogger(__name__)


class ConnectionManager:

    instance = None

    def __init__(self):
        if not self.initialized:
            self.closing_connections = set()
            self.user_connections: dict[(HandlerKind, int), WebSocket] = {}
            self.ws_connections: dict[int, WebSocket] = {}
            self.initialized = True

    def is_connection_closing(self, websocket: WebSocket) -> bool:
        return id(websocket) in self.closing_connections

    def get_active_user_ids(self) -> Set[int]:
        return set(map(lambda x: x[1], self.user_connections.keys()))

    async def register_connection(
        self, kind: HandlerKind, user_id: int, websocket: WebSocket
    ) -> WebSocket:
        if (kind, user_id) in self.user_connections:
            logger.warning(f"User {user_id} already connected for handler {kind}.")
            return self.user_connections[(kind, user_id)]

        await websocket.accept()

        connection_id = id(websocket)
        self.user_connections[(kind, user_id)] = websocket
        self.ws_connections[connection_id] = websocket

        logger.info(
            f"User {user_id} connected for handler {kind}. Total connections: {len(self.ws_connections)}"
        )
        return websocket

    def get_websocket_connection(
        self, kind: HandlerKind, user_id: int
    ) -> Optional[WebSocket]:
        websocket = self.user_connections.get((kind, user_id))

        if not websocket:
            logger.warning(
                f"No active connection found for user {user_id} and handler {kind}."
            )
            return None

        if self.is_connection_closing(websocket):
            logger.warning(f"Connection for user {user_id} is closing.")
            return None

        return websocket

    def disconnect(self, kind: HandlerKind, user_id: int) -> None:
        websocket = self.user_connections.get((kind, user_id))

        if not websocket:
            logger.warning(
                f"No active connection found for user {user_id} and handler {kind}."
            )
            return

        connection_id = id(websocket)

        self.closing_connections.add(connection_id)

        # Remove from current connection pool
        if connection_id in self.ws_connections:
            del self.ws_connections[connection_id]

        if (kind, user_id) in self.user_connections:
            del self.user_connections[(kind, user_id)]

        logger.info(
            f"WebSocket disconnected. Total connections: {len(self.ws_connections)}"
        )

    def __new__(cls):
        if cls.instance is None:
            cls.instance = super(ConnectionManager, cls).__new__(cls)
            cls.instance.initialized = False
        return cls.instance
