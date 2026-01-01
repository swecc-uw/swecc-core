from enum import Enum
from typing import Union
from dataclasses import dataclass


class Status(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    ERROR = "error"


@dataclass
class PollingRequest:
    request_id: str
    status: Status
    result: Union[str, None]
    error: Union[str, None]


def generate_request_id():
    import uuid

    return str(uuid.uuid4())
