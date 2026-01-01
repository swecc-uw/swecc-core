from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel


class MessageType(str, Enum):
    SYSTEM = "system"
    ERROR = "error"
    ECHO = "echo"
    LOG_LINE = "log_line"
    LOGS_STARTED = "logs_started"
    LOGS_STOPPED = "logs_stopped"
    RESUME_REVIEWED = "resume_reviewed"


class Message(BaseModel):
    type: MessageType
    message: Optional[str] = None
    user_id: Optional[int] = None
    username: Optional[str] = None
    data: Optional[Dict[str, Any]] = None