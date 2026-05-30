#!/usr/bin/env python3
"""Minimal LiteLLM Anthropic auth probe — run inside bench-api container or CI."""

from __future__ import annotations

import asyncio
import os
import sys


def _classify(exc: BaseException) -> str:
    text = str(exc).lower()
    if "x-api-key header is required" in text:
        return "missing_header"
    if "authentication" in text or "invalid" in text or "401" in text:
        return "auth_rejected"
    if "not_found" in text or "404" in text:
        return "model_not_found"
    return "other"


async def _try(label: str, **kwargs: object) -> str:
    import litellm

    try:
        await litellm.acompletion(**kwargs)
        print(f"{label}: SUCCESS")
        return "success"
    except Exception as exc:
        kind = _classify(exc)
        print(f"{label}: {type(exc).__name__} [{kind}]: {exc}")
        return kind


async def main() -> int:
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    openai = (os.environ.get("OPENAI_API_KEY") or "").strip()
    print(f"ANTHROPIC_API_KEY set={bool(key)} len={len(key)}")
    if key:
        print(f"ANTHROPIC_API_KEY prefix={key[:12]}...")
    print(f"OPENAI_API_KEY set={bool(openai)} len={len(openai)}")

    model = "anthropic/claude-sonnet-4-6"
    messages = [{"role": "user", "content": "Reply with exactly: ok"}]
    base = dict(model=model, messages=messages, max_tokens=5, temperature=0)

    results: list[str] = []

    print("\n--- Path A: env only, no tools (bench free-text path) ---")
    results.append(await _try("Path A", **base))

    print("\n--- Path B: env only, with tools (bench structured path) ---")
    results.append(
        await _try(
            "Path B",
            **base,
            max_tokens=64,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "submit_action",
                        "description": "Submit action",
                        "parameters": {
                            "type": "object",
                            "properties": {"action": {"type": "string"}},
                            "required": ["action"],
                        },
                    },
                }
            ],
            tool_choice={"type": "function", "function": {"name": "submit_action"}},
        )
    )

    if key:
        print("\n--- Path C: explicit api_key kwarg ---")
        results.append(await _try("Path C", **base, api_key=key))

    # CI exit codes:
    # 0 = anthropic call succeeded on at least one path
    # 1 = key missing in env
    # 2 = key present but header not sent (same prod bug)
    # 3 = key sent but rejected (bad/expired key)
    # 4 = other failure

    if not key:
        print("\nEXIT: no ANTHROPIC_API_KEY in environment")
        return 1

    if "success" in results:
        print("\nEXIT: Anthropic LiteLLM call succeeded")
        return 0

    if "missing_header" in results:
        print("\nEXIT: key in env but LiteLLM did not send x-api-key (matches prod bug)")
        return 2

    if "auth_rejected" in results:
        print("\nEXIT: key sent but Anthropic rejected it (check secret value)")
        return 3

    print("\nEXIT: other LiteLLM/Anthropic failure")
    return 4


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
