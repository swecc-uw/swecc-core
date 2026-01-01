import logging
import json
from ..connection_manager import ConnectionManager
from ..handlers import HandlerKind
from ..message import Message, MessageType
from . import consumer
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ReviewedResumeMessage(BaseModel):
    feedback: str
    key: str


@consumer(
    queue="sockets.reviewed-resume",
    exchange="swecc-ai-exchange",
    routing_key="reviewed",
    schema=ReviewedResumeMessage,
)
async def reviewed_resume_consumer(body, properties):
    """
    Consumer for the reviewed resume queue.
    """
    user_id, resume_id, file_name = body.key.split("-")

    ws_connection_manager = ConnectionManager()
    websocket = ws_connection_manager.get_websocket_connection(
        HandlerKind.Resume, int(user_id)
    )

    if websocket is None:
        logger.warning(f"No active WebSocket connection for user {user_id}")
        return

    message = Message(
        type=MessageType.RESUME_REVIEWED,
        user_id=int(user_id),
        username=None,
        message=f"Resume reviewed for user {user_id} with feedback: {body.feedback}",
        data={
            "resume_id": resume_id,
            "file_name": file_name,
            "feedback": body.feedback,
        },
    )

    try:
        await websocket.send_text(json.dumps(message.model_dump()))
        logger.info(f"Sent reviewed resume message to user {user_id}")
    except Exception as e:
        logger.error(f"Failed to send message to WebSocket: {e}")
        return
