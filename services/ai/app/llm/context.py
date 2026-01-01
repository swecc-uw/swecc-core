from dataclasses import dataclass
from collections import deque
from .message import Message
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ContextConfig:
    max_context_length: int
    context_invalidation_time_seconds: int
    system_instruction: str


class ContextManager:
    _instance = None  # Class-level attribute to hold the singleton instance

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ContextManager, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "initialized"):  # Ensure __init__ runs only once
            self.context_configs: dict[str, ContextConfig] = {}
            self.context: dict[str, deque[Message]] = {}
            self.initialized = True  # Mark as initialized

    def add_context_config(self, key: str, **kwargs):
        self.context_configs[key] = ContextConfig(**kwargs)
        if key not in self.context:
            self.context[key] = deque()

    def _update_context(self, key: str, message: Message):
        current_length = sum(map(len, self.context[key])) + len(message)
        max_length = self.context_configs[key].max_context_length
        while len(self.context[key]) > 0 and current_length >= max_length:
            current_length -= len(self.context[key].popleft())

        self.context[key].append(message)
        logger.info(f"Context for key `{key}` updated: {message}")

    def _ensure_relevant_context(self, key: str):
        # Clear context if most recent message is older than context_invalidation_time
        if (
            len(self.context[key]) > 0
            and (datetime.now() - self.context[key][-1].timestamp).total_seconds()
            > self.context_configs[key].context_invalidation_time_seconds
        ):
            logger.info(f"Clearing context for key {key}...")
            self.context[key].clear()

    def add_message_to_context(self, key: str, message: Message):
        if key not in self.context:
            raise ValueError(f"Context key `{key}` not found.")
        self._update_context(key, message)

    def contextualize_prompt(self, key: str, prompt: str):
        if key not in self.context:
            raise ValueError(f"Context key `{key}` not found.")
        self._ensure_relevant_context(key)
        context = self.context[key]
        context_str = "\n".join([str(msg) for msg in context])
        return f"<CONTEXT>\n{context_str}\n</CONTEXT>\n{prompt}"

    def is_registered(self, key: str):
        return key in self.context_configs
