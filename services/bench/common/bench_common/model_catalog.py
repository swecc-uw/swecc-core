"""
Canonical LiteLLM model IDs for BenchAnything.

Google AI Studio models use the ``gemini/`` prefix (GEMINI_API_KEY / GOOGLE_API_KEY).
The legacy ``google/gemini-*`` strings are not valid LiteLLM providers.
"""

from __future__ import annotations

# Exactly five models for full-bench / worker runs and mesocosm picker parity.
FULL_BENCH_MODELS: tuple[str, ...] = (
    "anthropic/claude-sonnet-4-6",
    "openai/gpt-4o",
    "gemini/gemini-3.1-flash-lite",
    "deepseek/deepseek-chat",
    "xai/grok-2",
)

# Additional models accepted for dev test bench and gallery runs.
EXTRA_MODEL_ALIASES: tuple[str, ...] = (
    "gemini/gemini-2.5-flash",
    "gemini/gemini-2.5-flash-lite",
    "gemini/gemini-3.1-flash-lite-preview",
    "gemini/gemini-3.5-flash",
    "gemini/gemini-flash-latest",
    "gemini/gemini-flash-lite-latest",
)

ALLOWED_MODELS: tuple[str, ...] = FULL_BENCH_MODELS + EXTRA_MODEL_ALIASES

# Human-readable labels for API docs / optional clients (id → label).
MODEL_LABELS: dict[str, str] = {
    "anthropic/claude-sonnet-4-6": "Claude Sonnet 4.6",
    "openai/gpt-4o": "GPT-4o",
    "gemini/gemini-3.1-flash-lite": "Gemini 3.1 Flash Lite",
    "deepseek/deepseek-chat": "DeepSeek Chat",
    "xai/grok-2": "Grok 2",
    "gemini/gemini-2.5-flash": "Gemini 2.5 Flash",
    "gemini/gemini-2.5-flash-lite": "Gemini 2.5 Flash Lite",
    "gemini/gemini-3.1-flash-lite-preview": "Gemini 3.1 Flash Lite (preview)",
    "gemini/gemini-3.5-flash": "Gemini 3.5 Flash",
    "gemini/gemini-flash-latest": "Gemini Flash (latest)",
    "gemini/gemini-flash-lite-latest": "Gemini Flash Lite (latest)",
}
