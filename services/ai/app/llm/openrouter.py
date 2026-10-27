import logging
import os
import random
import re
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"
DEFAULT_MODEL = "openrouter/free"
# OpenRouter rejects a models array longer than this.
MAX_ROUTED_MODELS = 3
# openrouter/free also routes to guard models. Their entire reply is a verdict
# such as "User Safety: safe", so they are left out of the chat pool.
_EXCLUDED_MODEL_PARTS = ("content-safety", "safety-guard", "llama-guard", "safeguard")
_SAFETY_VERDICT = re.compile(r"^(?:User|Response)\s+Safety:\s*\S+\s*$", re.IGNORECASE)
_FREE_MODEL_TTL_SECONDS = 10 * 60
_free_model_cache: list[str] = []
_free_model_cached_at = 0.0
# Reasoning tokens count toward max_tokens. Leave room for the visible reply.
COMPLETION_MAX_TOKENS = 2000
REASONING_MAX_TOKENS = 1000
REQUEST_TIMEOUT_SECONDS = 45.0
_THINK_BLOCK = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)


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
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as http:
                return await self._complete(http, messages)
        except Exception as e:
            detail = str(e).strip() or type(e).__name__
            logger.exception(
                "OpenRouter prompt failed model=%s error_type=%s detail=%s",
                self.model_name,
                type(e).__name__,
                detail,
            )
            if not str(e).strip():
                raise RuntimeError(f"OpenRouter request failed: {type(e).__name__}") from e
            raise

    async def _complete(self, http: httpx.AsyncClient, messages: list[dict]) -> str:
        pool = None
        if self.model_name == DEFAULT_MODEL:
            pool = await load_free_chat_models(self.api_key, http)

        excluded: set[str] = set()
        last_safety_model = ""
        for _ in range(2):
            body = {
                "messages": messages,
                "max_tokens": COMPLETION_MAX_TOKENS,
                "temperature": 0.7,
                "reasoning": {
                    "exclude": True,
                    "max_tokens": REASONING_MAX_TOKENS,
                },
            }
            if pool:
                choices = [model_id for model_id in pool if model_id not in excluded]
                if not choices:
                    break
                random.shuffle(choices)
                # A random slice of the free chat pool. The content-safety model is not in it.
                body["models"] = choices[:MAX_ROUTED_MODELS]
            else:
                body["model"] = self.model_name

            response = await http.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            if response.status_code >= 400:
                raise RuntimeError(_http_error_message(response))

            payload = response.json()
            served = str(payload.get("model") or "")
            text = _message_text(payload)
            if _is_excluded_model(served) or _is_safety_verdict(text):
                last_safety_model = served or last_safety_model
                logger.warning(
                    "Skipping content-safety response from model=%s", served or "unknown"
                )
                if served:
                    excluded.add(served)
                if pool:
                    continue
                break
            logger.info("OpenRouter served model=%s", served or self.model_name)
            return text

        raise RuntimeError(
            "OpenRouter returned a content-safety verdict"
            + (f" from {last_safety_model}" if last_safety_model else "")
        )


def _is_excluded_model(model_id: str) -> bool:
    lowered = model_id.lower()
    return any(part in lowered for part in _EXCLUDED_MODEL_PARTS)


def _is_safety_verdict(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return bool(lines) and all(_SAFETY_VERDICT.match(line) for line in lines)


def chat_model_ids(catalog: list) -> list[str]:
    """Free text-chat models, without content-safety classifiers."""
    ids = []
    for item in catalog:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "")
        if not model_id.endswith(":free"):
            continue
        if _is_excluded_model(model_id):
            continue
        outputs = (item.get("architecture") or {}).get("output_modalities") or ["text"]
        if "text" not in outputs:
            continue
        ids.append(model_id)
    return ids


async def load_free_chat_models(api_key: str, http: httpx.AsyncClient) -> list[str]:
    global _free_model_cache, _free_model_cached_at

    now = time.monotonic()
    if _free_model_cache and now - _free_model_cached_at < _FREE_MODEL_TTL_SECONDS:
        return list(_free_model_cache)

    try:
        response = await http.get(
            MODELS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        ids = chat_model_ids(response.json().get("data") or [])
    except Exception as exc:
        logger.warning("Could not load the free model list: %s", exc)
        return list(_free_model_cache)

    if ids:
        _free_model_cache = ids
        _free_model_cached_at = now
        logger.info("Free chat pool has %s models; content-safety models are excluded", len(ids))
    return list(ids)


def _is_reasoning_part(part: dict) -> bool:
    part_type = str(part.get("type") or "")
    return part_type == "reasoning" or part_type.startswith("reasoning.")


def _visible_text(content) -> str:
    return _THINK_BLOCK.sub("", _coerce_text(content)).strip()


def _coerce_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("text") and not _is_reasoning_part(part):
                parts.append(str(part["text"]))
        return "".join(parts).strip()
    return ""


def _http_error_message(response: httpx.Response) -> str:
    fallback = (response.text or "")[:500]
    try:
        payload = response.json()
    except Exception:
        return f"OpenRouter request failed ({response.status_code}): {fallback}"

    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        message = error.get("message") or fallback
        code = error.get("code", response.status_code)
        return f"OpenRouter request failed ({response.status_code}, code={code}): {message}"
    if isinstance(error, str) and error:
        return f"OpenRouter request failed ({response.status_code}): {error[:500]}"
    return f"OpenRouter request failed ({response.status_code}): {fallback}"


def _message_text(payload: dict) -> str:
    error = payload.get("error")
    choices = payload.get("choices") or []
    if error and not choices:
        if isinstance(error, dict):
            message = error.get("message") or error
            code = error.get("code")
            raise ValueError(f"OpenRouter error (code={code}): {message}")
        raise ValueError(f"OpenRouter error: {error}")

    if not choices:
        raise ValueError("OpenRouter response did not include choices")

    choice = choices[0]
    message = choice.get("message") or {}
    finish_reason = choice.get("finish_reason")
    # A truncated completion is usually reasoning that ran out of room.
    # Drop it so the partial plan is neither posted nor stored as context.
    if finish_reason == "length":
        raise ValueError("OpenRouter response was cut off (finish_reason=length)")

    text = _visible_text(message.get("content"))
    if not text:
        suffix = f" (finish_reason={finish_reason})" if finish_reason else ""
        raise ValueError(f"OpenRouter response did not include message text{suffix}")
    return text
