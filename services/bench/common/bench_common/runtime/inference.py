"""
Inference router wrapping LiteLLM.
Builds messages from observation + binding vow context, calls the model,
and parses the response into an action dict.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
from typing import Any, NamedTuple

import litellm
import structlog
from bench_common.config import settings
from bench_common.core.binding_vow import BindingVow, CompositeSpace, SpaceSpec, SpaceType
from bench_common.core.run import AgentConfig
from bench_common.runtime.env_client import Observation

log = structlog.get_logger()


def _safe_usage_field(usage: Any, name: str) -> int | None:
    """Read a token count from a LiteLLM `Usage` object, dict, or None."""
    if usage is None:
        return None
    if isinstance(usage, dict):
        val = usage.get(name)
    else:
        val = getattr(usage, name, None)
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


class StructuredOutputError(RuntimeError):
    """Raised when a provider's structured-output response can't be parsed.

    Distinct from transient network/rate-limit errors: a malformed structured
    response means the model gave us garbage, not that the call failed. The
    agent loop should mark the episode failed with a clear reason instead of
    feeding reasoning text into the env as if it were a real action.
    """


# Disable LiteLLM's default internal retries — we own retry policy below so
# 429/5xx counts are predictable and bounded.
litellm.num_retries = 0

# Retry policy for transient provider errors. Kept short so a stuck provider
# doesn't tie up an episode's wall-clock budget; the agent_loop deadline still
# wraps the whole call.
_MAX_INFERENCE_RETRIES = 2
_BASE_BACKOFF_SECONDS = 1.0


def _is_transient_error(exc: BaseException) -> bool:
    """True for errors worth a bounded retry: rate-limit, 5xx, transport blips."""
    # LiteLLM normalises provider exceptions to subclasses of these.
    rate_limit = getattr(litellm, "RateLimitError", None)
    api_conn = getattr(litellm, "APIConnectionError", None)
    timeout_err = getattr(litellm, "Timeout", None)
    internal = getattr(litellm, "InternalServerError", None)
    service_unavail = getattr(litellm, "ServiceUnavailableError", None)
    transient_types = tuple(
        t for t in (rate_limit, api_conn, timeout_err, internal, service_unavail) if t is not None
    )
    if transient_types and isinstance(exc, transient_types):
        return True
    # Fallback: many providers expose `.status_code` on their error classes.
    status = getattr(exc, "status_code", None)
    return isinstance(status, int) and (status == 429 or 500 <= status < 600)


async def _acompletion_with_retry(**kwargs: Any) -> Any:
    """Wrap litellm.acompletion with bounded retry on transient errors."""
    attempt = 0
    while True:
        try:
            return await litellm.acompletion(**kwargs)
        except Exception as exc:
            if attempt >= _MAX_INFERENCE_RETRIES or not _is_transient_error(exc):
                raise
            # Exponential backoff with jitter; total worst-case ≈ 3s + 6s = 9s.
            delay = _BASE_BACKOFF_SECONDS * (2**attempt) + random.uniform(0, 0.5)
            log.warning(
                "inference_transient_error_retry",
                attempt=attempt + 1,
                max_attempts=_MAX_INFERENCE_RETRIES,
                delay_s=round(delay, 2),
                error=type(exc).__name__,
                detail=str(exc)[:200],
            )
            await asyncio.sleep(delay)
            attempt += 1


# Values that must not be sent to LiteLLM as real provider keys.
_PLACEHOLDER_API_KEYS = frozenset(
    {
        "placeholder",
        "changeme",
        "your_api_key_here",
        "sk-placeholder",
    }
)


def _resolve_google_api_key() -> str | None:
    """Prefer a real Google AI Studio key from GOOGLE_API_KEY or GEMINI_API_KEY."""
    for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
        val = (os.environ.get(name) or "").strip()
        if not val:
            continue
        low = val.lower()
        if low in _PLACEHOLDER_API_KEYS or low.startswith("your_"):
            continue
        return val
    return None


def normalize_model_id(model: str) -> str:
    """Map legacy ``google/gemini-*`` IDs to LiteLLM's ``gemini/*`` provider."""
    if model.startswith("google/gemini-"):
        return "gemini/" + model.removeprefix("google/")
    return model


# ── Structured-output helpers ─────────────────────────────────────────────────

# Space types for which we can derive a JSON Schema and use provider-native
# structured output.  TEXT / IMAGE / MULTI_MODAL stay on the free-text path.
_STRUCTURED_SPACE_TYPES = frozenset(
    {SpaceType.DISCRETE, SpaceType.JSON, SpaceType.CONTINUOUS, SpaceType.COMPOSITE}
)


def _provider_key(model: str) -> str:
    """Return a short provider tag for a normalised model ID."""
    for prefix in ("openai/", "anthropic/", "gemini/", "ollama/"):
        if model.startswith(prefix):
            return prefix.rstrip("/")
    return "unknown"


def _space_to_json_schema(space: SpaceSpec | CompositeSpace) -> dict[str, Any]:
    """Convert a BindingVow SpaceSpec or CompositeSpace to a JSON Schema dict.

    The returned schema describes the *action value* itself (not wrapped).
    Pass the result through ``_wrap_action_schema`` before sending to any API.
    """
    if isinstance(space, CompositeSpace):
        props = {k: _space_to_json_schema(v) for k, v in space.fields.items()}
        return {
            "type": "object",
            "properties": props,
            "required": list(space.fields.keys()),
        }
    if space.type == SpaceType.DISCRETE:
        schema: dict[str, Any] = {"type": "string"}
        if space.enum_values:
            schema["enum"] = space.enum_values
        return schema
    if space.type == SpaceType.JSON:
        # schema_ref holds a raw JSON Schema string authored by the env developer.
        if space.schema_ref:
            try:
                return json.loads(space.schema_ref)
            except (json.JSONDecodeError, TypeError):
                pass
        return {"type": "object"}
    if space.type == SpaceType.CONTINUOUS:
        schema = {"type": "number"}
        if space.bounds:
            if "low" in space.bounds:
                schema["minimum"] = space.bounds["low"]
            if "high" in space.bounds:
                schema["maximum"] = space.bounds["high"]
        return schema
    # TEXT, IMAGE, MULTI_MODAL — callers should not reach here for structured paths
    return {"type": "string"}


def _wrap_action_schema(inner: dict[str, Any]) -> dict[str, Any]:
    """Wrap the action schema in a top-level object.

    All three providers (OpenAI, Anthropic, Gemini) require the outermost JSON
    Schema type to be ``object``.  We consistently wrap the value under an
    ``action`` key and unwrap it after parsing, so provider-specific extraction
    logic is uniform.
    """
    return {
        "type": "object",
        "properties": {"action": inner},
        "required": ["action"],
    }


class DecideResult(NamedTuple):
    """Parsed env action plus raw model text for traces / showcase export."""

    action: Any
    reasoning_text: str
    # Token usage from the provider response — used by the agent loop to
    # enforce a per-episode budget and stop a runaway agent before it burns
    # through inference credits. 0 when the provider doesn't surface usage.
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class InferenceRouter:
    """Model-agnostic inference via LiteLLM."""

    _THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

    def __init__(self, *, allow_any_model: bool = False) -> None:
        self._allow_any_model = allow_any_model

    async def decide(
        self,
        observation: Observation,
        binding_vow: BindingVow,
        agent_config: AgentConfig,
        extra_context: dict[str, Any],
        step: int,
        env_system_prompt: str | None = None,
    ) -> DecideResult:
        model_name = normalize_model_id(agent_config.model)
        if not self._allow_any_model:
            allowed_models = settings.supported_models + settings.accepted_model_aliases
            if model_name not in allowed_models:
                raise ValueError(
                    f"Model {model_name!r} is not supported. " f"Allowed: {allowed_models}"
                )

        provider = _provider_key(model_name)
        use_structured = self._supports_structured_output(binding_vow.action_space, provider)

        messages = self._build_messages(
            observation,
            binding_vow,
            agent_config,
            extra_context,
            step,
            env_system_prompt,
            use_structured=use_structured,
            provider=provider,
        )

        kwargs: dict[str, Any] = dict(
            model=model_name,
            messages=messages,
            temperature=agent_config.temperature,
            max_tokens=agent_config.max_tokens,
        )
        # ── provider-specific base kwargs ─────────────────────────────────────
        if provider == "ollama":
            kwargs["max_tokens"] = max(agent_config.max_tokens, 512)
            kwargs["api_base"] = kwargs.get("api_base", "http://localhost:11434")
            kwargs["extra_body"] = {"think": False}
        elif provider == "gemini":
            api_key = _resolve_google_api_key()
            if not api_key:
                raise ValueError(
                    "Gemini model requested but no Google AI Studio API key is configured. "
                    "Set GOOGLE_API_KEY or GEMINI_API_KEY in the bench-api environment "
                    "(see .env.example), then recreate the bench-api container."
                )
            kwargs["api_key"] = api_key

        # ── structured-output kwargs ──────────────────────────────────────────
        if use_structured:
            action_schema = _wrap_action_schema(_space_to_json_schema(binding_vow.action_space))
            if provider == "anthropic":
                # Claude: force a single tool call so the response is always a
                # validated JSON object — no free-text parsing needed.
                kwargs["tools"] = [
                    {
                        "type": "function",
                        "function": {
                            "name": "submit_action",
                            "description": (
                                "Submit your chosen action for this step. "
                                "Call this exactly once per turn."
                            ),
                            "parameters": action_schema,
                        },
                    }
                ]
                kwargs["tool_choice"] = {
                    "type": "function",
                    "function": {"name": "submit_action"},
                }
            else:
                # OpenAI and Gemini: JSON Schema response_format (LiteLLM
                # translates to each provider's native wire format).
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "action",
                        "schema": action_schema,
                    },
                }

        response = await _acompletion_with_retry(**kwargs)

        if use_structured:
            action, reasoning_text = self._extract_structured_action(response, provider)
        else:
            raw = response.choices[0].message.content or ""
            reasoning_text = self._strip_thinking(raw)
            log.debug("inference_raw", step=step, model=model_name, raw=reasoning_text[:200])
            action = self._parse_action(reasoning_text, binding_vow)

        usage = getattr(response, "usage", None) or {}
        # LiteLLM normalises usage to an OpenAI-shaped object across providers,
        # but on some custom endpoints it's a dict or None. Be defensive.
        prompt_tokens = int(_safe_usage_field(usage, "prompt_tokens") or 0)
        completion_tokens = int(_safe_usage_field(usage, "completion_tokens") or 0)
        total_tokens = int(
            _safe_usage_field(usage, "total_tokens") or (prompt_tokens + completion_tokens)
        )

        log.debug(
            "inference_decision",
            step=step,
            model=model_name,
            structured=use_structured,
            action=str(action)[:120],
            total_tokens=total_tokens,
        )
        return DecideResult(
            action=action,
            reasoning_text=reasoning_text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    # ── structured-output helpers ─────────────────────────────────────────────

    def _supports_structured_output(self, space: SpaceSpec | CompositeSpace, provider: str) -> bool:
        """Return True when provider-native structured output can be applied.

        Requires a known provider (OpenAI, Anthropic, or Gemini) *and* a space
        type for which we can derive a JSON Schema.  Unknown / custom endpoints
        (``allow_any_model=True``) always use the free-text fallback path.
        """
        if self._allow_any_model:
            return False
        if provider not in ("openai", "anthropic", "gemini"):
            return False
        if isinstance(space, CompositeSpace):
            return True
        return space.type in _STRUCTURED_SPACE_TYPES

    def _extract_structured_action(self, response: Any, provider: str) -> tuple[Any, str]:
        """Unpack the action value from a structured-output API response.

        Returns ``(action, reasoning_text)``.

        *   **Anthropic** responses carry a tool call; any text emitted before
            the call is captured as ``reasoning_text``.
        *   **OpenAI / Gemini** responses have the JSON object directly in
            ``message.content``; ``reasoning_text`` is empty.
        """
        if provider == "anthropic":
            message = response.choices[0].message

            # Collect any pre-tool reasoning text from the content blocks.
            reasoning_text = ""
            content = message.content
            if isinstance(content, str):
                reasoning_text = content.strip()
            elif isinstance(content, list):
                reasoning_text = " ".join(
                    (b.get("text", "") if isinstance(b, dict) else getattr(b, "text", ""))
                    for b in content
                    if (isinstance(b, dict) and b.get("type") == "text")
                    or (hasattr(b, "type") and b.type == "text")
                ).strip()

            tool_calls = message.tool_calls or []
            if len(tool_calls) > 1:
                # tool_choice is forced to submit_action but Claude can still emit
                # extra calls on prefill/streaming edges — surface the drop so we
                # can debug if it ever happens, instead of silently picking [0].
                log.warning(
                    "structured_tool_call_multiple",
                    provider=provider,
                    count=len(tool_calls),
                )
            if tool_calls:
                args = tool_calls[0].function.arguments
                try:
                    parsed = json.loads(args) if isinstance(args, str) else args
                except json.JSONDecodeError as exc:
                    raise StructuredOutputError(
                        f"Anthropic tool args were not valid JSON: {exc}. "
                        f"Raw args: {str(args)[:200]}"
                    ) from exc
                if not isinstance(parsed, dict):
                    raise StructuredOutputError(
                        f"Anthropic tool args parsed to {type(parsed).__name__}, "
                        f"expected an object with an 'action' field."
                    )
                if "action" not in parsed:
                    raise StructuredOutputError(
                        "Anthropic tool args did not contain required 'action' field."
                    )
                return parsed["action"], reasoning_text

            # Model did not call the tool (should not happen with tool_choice forced).
            raise StructuredOutputError(
                "Anthropic response contained no tool call despite forced "
                "tool_choice — feeding reasoning text as action would corrupt "
                "the episode. Provider may have refused or hit max_tokens."
            )

        # OpenAI / Gemini — message.content is the JSON object string.
        raw = response.choices[0].message.content or ""
        if not raw.strip():
            raise StructuredOutputError(
                f"{provider} returned empty content — likely a content-filter "
                f"refusal or max_tokens too small."
            )
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise StructuredOutputError(
                f"{provider} returned non-JSON content despite response_format: "
                f"{exc}. Raw: {raw[:200]}"
            ) from exc
        if not isinstance(parsed, dict):
            raise StructuredOutputError(
                f"{provider} structured content parsed to {type(parsed).__name__}, "
                "expected an object with an 'action' field."
            )
        if "action" not in parsed:
            raise StructuredOutputError(
                f"{provider} structured content did not contain required 'action' field."
            )
        return parsed["action"], ""

    def _strip_thinking(self, text: str) -> str:
        """Remove <think>...</think> blocks that some reasoning models emit."""
        return self._THINK_TAG_RE.sub("", text).strip()

    # ── message construction ──────────────────────────────────────────────────

    def _build_messages(
        self,
        observation: Observation,
        vow: BindingVow,
        config: AgentConfig,
        extra_context: dict[str, Any],
        step: int,
        env_system_prompt: str | None = None,
        *,
        use_structured: bool = False,
        provider: str = "unknown",
    ) -> list[dict[str, Any]]:
        system = self._build_system_prompt(
            vow,
            config,
            extra_context,
            env_system_prompt,
            use_structured=use_structured,
            provider=provider,
        )
        user_content = self._build_user_content(observation, step, provider)
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        messages.append({"role": "user", "content": user_content})
        return messages

    def _build_system_prompt(
        self,
        vow: BindingVow,
        config: AgentConfig,
        extra_context: dict[str, Any],
        env_system_prompt: str | None = None,
        *,
        use_structured: bool = False,
        provider: str = "unknown",
    ) -> str:
        parts: list[str] = []
        if env_system_prompt:
            parts.append(env_system_prompt)
        if config.system_prompt:
            parts.append(config.system_prompt)

        if vow.description:
            parts.append(f"## Domain\n{vow.description}")

        parts.append(f"## Action Space\n{self._describe_space(vow.action_space)}")

        if extra_context:
            for key, value in extra_context.items():
                parts.append(f"## {key}\n{value}")

        if use_structured:
            if provider == "anthropic":
                parts.append(
                    "Call the submit_action tool with your chosen action. "
                    "You may reason briefly before calling the tool; "
                    "the platform records your full reply."
                )
            else:
                # OpenAI / Gemini — response_format enforces the JSON Schema
                parts.append(
                    "Respond with a JSON object containing your chosen action "
                    "in the required schema. "
                    "You may include a brief reasoning field if the schema allows it; "
                    "the platform records your full reply."
                )
        else:
            parts.append(
                "Respond with your action. You may include one or two sentences of reasoning first; "
                "the platform records your full reply. "
                "If the action space is discrete, include exactly one allowed value in your response. "
                "If the action space is JSON, end with valid JSON only."
            )
        return "\n\n".join(parts)

    def _describe_space(self, space: SpaceSpec | CompositeSpace) -> str:
        if isinstance(space, CompositeSpace):
            inner = ", ".join(f"{k}: {self._describe_space(v)}" for k, v in space.fields.items())
            return f"composite({inner})"
        if space.enum_values:
            return f"one of {space.enum_values}"
        if space.description:
            return space.description
        return space.type.value

    def _build_user_content(
        self,
        observation: Observation,
        step: int,
        provider: str,
    ) -> str | list[dict[str, Any]]:
        """Build the user-turn content for the model message.

        Returns a plain string for text/JSON observations and a multipart
        content list (per each provider's vision API spec) for image
        observations.  Unknown or ``application/*`` content types fall back
        to text serialisation.

        Image data in ``observation.data`` may be:
        - ``bytes`` — raw binary, encoded to base64 here.
        - ``str``   — assumed already base64-encoded.
        - ``dict``  with key ``"url"`` — treated as a remote URL (OpenAI-style
          only; Anthropic requires base64 for now).
        """
        ct = (observation.content_type or "application/json").lower()
        step_prefix = f"[Step {step}]"

        if ct.startswith("image/"):
            return self._build_image_content(observation.data, ct, step_prefix, provider)

        # Text / JSON path
        data = observation.data
        if isinstance(data, (dict, list)):
            data_str = json.dumps(data, ensure_ascii=False)
        else:
            data_str = str(data)
        return f"{step_prefix}\n{data_str}"

    def _build_image_content(
        self,
        data: Any,
        media_type: str,
        step_prefix: str,
        provider: str,
    ) -> list[dict[str, Any]]:
        """Build a provider-appropriate multipart content list for image observations.

        Supports bytes (raw binary), str (base64), and dict{"url": ...} (remote URL).
        Anthropic requires base64; OpenAI/Gemini accept either base64 data-URLs or
        remote https:// URLs.
        """
        import base64

        # Resolve data to either a base64 string or a URL string.
        if isinstance(data, bytes):
            b64 = base64.b64encode(data).decode("ascii")
            url = None
        elif isinstance(data, dict) and "url" in data:
            b64 = None
            url = str(data["url"])
        elif isinstance(data, str) and data.startswith("data:"):
            header, _, encoded = data.partition(",")
            b64 = encoded if ";base64" in header else data
            url = data
        elif isinstance(data, str) and data.startswith(("http://", "https://")):
            b64 = None
            url = data
        else:
            # Assume already base64-encoded string
            b64 = str(data)
            url = None

        text_block: dict[str, Any] = {"type": "text", "text": step_prefix}

        if provider == "anthropic":
            # Anthropic requires base64; fall back gracefully if only a URL was given.
            if b64 is None:
                log.warning(
                    "image_obs_url_not_supported_for_anthropic",
                    hint="Return bytes or a base64 string from step(); URLs are not accepted.",
                )
                return [
                    {
                        "type": "text",
                        "text": f"{step_prefix}\n[image — URL not supported for Anthropic provider]",
                    }
                ]
            image_block: dict[str, Any] = {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64,
                },
            }
        else:
            # OpenAI / Gemini — data-URL for base64, plain URL otherwise.
            img_url = url if url is not None else f"data:{media_type};base64,{b64}"
            image_block = {
                "type": "image_url",
                "image_url": {"url": img_url, "detail": "auto"},
            }

        return [text_block, image_block]

    # ── response parsing ──────────────────────────────────────────────────────

    def _parse_action(self, raw: str, vow: BindingVow) -> Any:
        action_space = vow.action_space
        if isinstance(action_space, CompositeSpace):
            return self._extract_json(raw)
        if isinstance(action_space, SpaceSpec):
            if action_space.type == SpaceType.DISCRETE and action_space.enum_values:
                stripped = raw.strip()
                # 1) Exact match (case-insensitive)
                for val in action_space.enum_values:
                    if stripped.upper() == val.upper():
                        return val
                # 2) Scan for first occurrence of any allowed value as a word boundary
                lower = stripped.lower()
                for val in action_space.enum_values:
                    if re.search(rf"\b{re.escape(val.lower())}\b", lower):
                        return val
                log.warning(
                    "action_parse_fallback", raw=raw[:200], allowed=action_space.enum_values
                )
                return stripped
            if action_space.type == SpaceType.JSON:
                return self._extract_json(raw)
            if action_space.type == SpaceType.CONTINUOUS:
                return self._extract_number(raw)
        return raw.strip()

    def _extract_json(self, raw: str) -> Any:
        # Strip markdown code fences if present
        text = raw.strip()
        for fence in ("```json", "```"):
            if text.startswith(fence):
                text = text.removeprefix(fence)
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
                break
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        decoder = json.JSONDecoder()
        candidates = [i for i, char in enumerate(text) if char in "[{"]
        for start in reversed(candidates):
            try:
                parsed, end = decoder.raw_decode(text[start:])
            except json.JSONDecodeError:
                continue
            if text[start + end :].strip():  # noqa: E203  # black-formatted slice
                continue
            return parsed
        return text

    def _extract_number(self, raw: str) -> float | str:
        text = raw.strip()
        try:
            return float(text)
        except ValueError:
            pass
        matches = re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", text)
        if len(matches) == 1:
            return float(matches[0])
        return text
