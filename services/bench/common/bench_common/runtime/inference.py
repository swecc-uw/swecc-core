"""
Inference router wrapping LiteLLM.
Builds messages from observation + binding vow context, calls the model,
and parses the response into an action dict.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import litellm
import structlog
from bench_common.config import settings
from bench_common.core.binding_vow import BindingVow, CompositeSpace, SpaceSpec, SpaceType
from bench_common.core.run import AgentConfig
from bench_common.runtime.env_client import Observation

log = structlog.get_logger()

# Disable LiteLLM's default internal retries on rate-limit errors. The default
# (3 retries with exponential backoff) burns through free-tier per-minute quotas
# in seconds when a 429 surfaces, turning a single failed call into ~3-10 wasted
# calls against the daily cap. We surface the 429 immediately instead, and let
# the orchestrator / worker decide what to do (e.g. mark the episode failed,
# back off the run, etc).
litellm.num_retries = 0

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


class InferenceRouter:
    """Model-agnostic inference via LiteLLM."""

    _THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

    async def decide(
        self,
        observation: Observation,
        binding_vow: BindingVow,
        agent_config: AgentConfig,
        extra_context: dict[str, Any],
        step: int,
        env_system_prompt: str | None = None,
    ) -> Any:
        messages = self._build_messages(
            observation, binding_vow, agent_config, extra_context, step, env_system_prompt
        )

        model_name = normalize_model_id(agent_config.model)
        allowed_models = settings.supported_models + settings.accepted_model_aliases
        if model_name not in allowed_models:
            raise ValueError(
                f"Model {model_name!r} is not supported. " f"Allowed: {allowed_models}"
            )
        is_ollama = model_name.startswith("ollama/")
        is_gemini = model_name.startswith("gemini/")

        kwargs: dict[str, Any] = dict(
            model=model_name,
            messages=messages,
            temperature=agent_config.temperature,
            max_tokens=agent_config.max_tokens,
        )
        if is_ollama:
            kwargs["max_tokens"] = max(agent_config.max_tokens, 512)
            kwargs["api_base"] = kwargs.get("api_base", "http://localhost:11434")
            kwargs["extra_body"] = {"think": False}
        elif is_gemini:
            api_key = _resolve_google_api_key()
            if not api_key:
                raise ValueError(
                    "Gemini model requested but no Google AI Studio API key is configured. "
                    "Set GOOGLE_API_KEY or GEMINI_API_KEY in the bench-api environment "
                    "(see .env.example), then recreate the bench-api container."
                )
            kwargs["api_key"] = api_key

        response = await litellm.acompletion(**kwargs)

        raw = response.choices[0].message.content or ""
        raw = self._strip_thinking(raw)
        log.debug("inference_raw", step=step, model=model_name, raw=raw[:200])
        return self._parse_action(raw, binding_vow)

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
    ) -> list[dict[str, Any]]:
        system = self._build_system_prompt(vow, config, extra_context, env_system_prompt)
        user = self._serialize_observation(observation, vow, step)
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        messages.append({"role": "user", "content": user})
        return messages

    def _build_system_prompt(
        self,
        vow: BindingVow,
        config: AgentConfig,
        extra_context: dict[str, Any],
        env_system_prompt: str | None = None,
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

        parts.append(
            "Respond with only your action. "
            "If the action space is discrete, reply with exactly one of the allowed values. "
            "If the action space is JSON, reply with valid JSON only."
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

    def _serialize_observation(self, observation: Observation, vow: BindingVow, step: int) -> str:
        data = observation.data
        if isinstance(data, (dict, list)):
            data_str = json.dumps(data, ensure_ascii=False)
        else:
            data_str = str(data)
        return f"[Step {step}]\n{data_str}"

    # ── response parsing ──────────────────────────────────────────────────────

    def _parse_action(self, raw: str, vow: BindingVow) -> Any:
        action_space = vow.action_space
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
            return text
