from typing import Dict, List, Callable
import logging
import asyncio
from .events import Event, EventType

logger = logging.getLogger(__name__)

class EventEmitter:
    def __init__(self):
        self.listeners = {}
    
    def on(self, event_type: EventType, listener: Callable) -> None:
        if event_type not in self.listeners:
            self.listeners[event_type] = []
        self.listeners[event_type].append(listener)
    
    def off(self, event_type: EventType, listener: Callable) -> None:
        if event_type in self.listeners and listener in self.listeners[event_type]:
            self.listeners[event_type].remove(listener)
    
    async def emit(self, event: Event) -> None:
        if event.type not in self.listeners:
            return
            
        tasks = []
        for listener in self.listeners[event.type]:
            tasks.append(self._safe_execute(listener, event))
            
        if tasks:
            # Use return_exceptions=True to prevent one listener error from affecting others
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _safe_execute(self, listener: Callable, event: Event) -> None:
        try:
            await listener(event)
        except asyncio.CancelledError:
            # Don't log cancelled errors, just propagate them
            raise
        except Exception as e:
            listener_name = getattr(listener, "__name__", str(listener))
            logger.error(
                f"Error in listener {listener_name} for event {event.type}: {str(e)}",
                exc_info=True
            )