from ..events import Event
from ..message import Message, MessageType
from .base_handler import BaseHandler


class EchoHandler(BaseHandler):
    def __init__(self, event_emitter):
        super().__init__(event_emitter, "Echo")

    async def handle_message(self, event: Event) -> None:
        try:
            content = event.data.get("content", "")
            self.logger.info(
                f"Echo service: Message from {event.username} (ID: {event.user_id}): {content}"
            )

            response = Message(
                type=MessageType.ECHO,
                user_id=event.user_id,
                username=event.username,
                message=content,
            )

            await self.safe_send(event.websocket, response.dict())
        except Exception as e:
            self.logger.error(f"Error in handle_message: {str(e)}", exc_info=True)
