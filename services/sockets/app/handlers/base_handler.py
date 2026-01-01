from ..event_emitter import EventEmitter
from ..events import Event, EventType
from ..message import Message, MessageType
import logging
import json

class BaseHandler:
    def __init__(self, event_emitter: EventEmitter, service_name: str):
        self.event_emitter = event_emitter
        self.service_name = service_name

        self.event_emitter.on(EventType.CONNECTION, self.handle_connect)
        self.event_emitter.on(EventType.MESSAGE, self.handle_message)
        self.event_emitter.on(EventType.DISCONNECT, self.handle_disconnect)

        self.logger = logging.getLogger(f"{self.service_name}Handler")

    
    async def handle_connect(self, event: Event) -> None:
        try:
            message = Message(
                type=MessageType.SYSTEM,
                message=f"{self.service_name} service: Connected as {event.username}",
            )
            await self.safe_send(event.websocket, message.dict())
            self.logger.info(
                f"{self.service_name} service: User {event.username} (ID: {event.user_id}) connected"
            )
        except Exception as e:
            self.logger.error(f"Error in handle_connect for {self.service_name} service: {str(e)}", exc_info=True)

    async def handle_message(self, event: Event) -> None:
        self.logger.info(
            f"{self.service_name} service: Message from {event.username} (ID: {event.user_id}): {event.data}"
        )

    async def handle_disconnect(self, event: Event) -> None:
        try:
            user_id = event.user_id
            self.logger.info(
                f"{self.service_name} service: User {event.username} (ID: {user_id}) disconnected"
            )
        except Exception as e:
            self.logger.error(f"Error in handle_disconnect for {self.service_name} service: {str(e)}", exc_info=True)

    async def safe_send(self, websocket, data):
        """Safely send a message, handling potential disconnection gracefully"""
        try:
            await websocket.send_text(json.dumps(data))
        except Exception as e:
            # Just log the error
            self.logger.debug(f"Could not send message, websocket may be closed: {str(e)}")
