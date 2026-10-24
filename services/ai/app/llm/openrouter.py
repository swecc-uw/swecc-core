import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openrouter/free"


class OpenRouter:
    """Text chat client for the Discord bot. Defaults to the free-model router."""

    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.model_name = os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)

        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable not set")

    async def prompt_model(self, prompt: str, system_instruction: Optional[str] = None):
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        try:
            async with httpx.AsyncClient(timeout=30.0) as http:
                response = await http.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model_name,
                        "messages": messages,
                        "max_tokens": 500,
                        "temperature": 0.7,
                    },
                )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"OpenRouter request failed ({response.status_code}): {response.text}"
                )
            return _message_text(response.json())
        except Exception as e:
            logger.error(f"Error in prompt_model: {e}")
            raise


def _coerce_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("text"):
                parts.append(str(part["text"]))
        return "".join(parts).strip()
    return ""


def _message_text(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise ValueError("OpenRouter response did not include choices")

    message = choices[0].get("message") or {}
    text = _coerce_text(message.get("content")) or _coerce_text(message.get("reasoning"))
    if not text:
        raise ValueError("OpenRouter response did not include message text")
    return text
