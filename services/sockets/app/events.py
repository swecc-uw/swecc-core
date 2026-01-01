from enum import Enum
from typing import Dict, Any, Optional


class EventType(str, Enum):
    CONNECTION = "connection"
    MESSAGE = "message"
    DISCONNECT = "disconnect"


class Event:
    def __init__(
        self,
        type: EventType,
        user_id: int,
        username: str,
        data: Optional[Dict[str, Any]] = None,
        websocket=None,
    ):
        self.type = type
        self.user_id = user_id
        self.username = username
        self.data = data or {}
        self.websocket = websocket