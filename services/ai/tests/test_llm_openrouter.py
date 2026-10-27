"""Tests for the OpenRouter client used by Discord bot chat."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.llm.openrouter import (
    COMPLETION_MAX_TOKENS,
    REASONING_MAX_TOKENS,
    OpenRouter,
    chat_model_ids,
)


@pytest.fixture(autouse=True)
def free_chat_pool(monkeypatch):
    async def _pool(api_key, http):
        return ["poolside/laguna-xs-2.1:free", "google/gemma-4-26b-a4b-it:free"]

    monkeypatch.setattr("app.llm.openrouter.load_free_chat_models", _pool)


def _http(response):
    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=response)
    mock_http.__aenter__.return_value = mock_http
    mock_http.__aexit__.return_value = False
    return mock_http


def _ok(content):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"choices": [{"message": {"content": content}}]}
    return response


class TestOpenRouter:
    def test_initialization_missing_api_key(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        with pytest.raises(ValueError, match="OPENROUTER_API_KEY environment variable not set"):
            OpenRouter()

    def test_initialization_default_model(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test_openrouter_key")
        monkeypatch.delenv("OPENROUTER_MODEL", raising=False)

        client = OpenRouter()

        assert client.model_name == "openrouter/free"

    @pytest.mark.asyncio
    async def test_prompt_model_posts_free_router(self, mock_env_vars):
        client = OpenRouter()
        mock_http = _http(_ok("hello"))

        with patch("app.llm.openrouter.httpx.AsyncClient", return_value=mock_http):
            result = await client.prompt_model("hi", system_instruction="sys")

        assert result == "hello"
        _, kwargs = mock_http.post.call_args
        assert "model" not in kwargs["json"]
        assert set(kwargs["json"]["models"]) == {
            "poolside/laguna-xs-2.1:free",
            "google/gemma-4-26b-a4b-it:free",
        }
        assert "nvidia/nemotron-3.5-content-safety:free" not in kwargs["json"]["models"]
        assert kwargs["json"]["max_tokens"] == COMPLETION_MAX_TOKENS
        assert kwargs["json"]["reasoning"] == {
            "exclude": True,
            "max_tokens": REASONING_MAX_TOKENS,
        }
        assert kwargs["json"]["messages"] == [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
        assert kwargs["headers"]["Authorization"] == "Bearer test_openrouter_key"

    @pytest.mark.asyncio
    async def test_prompt_model_reads_multipart_content(self, mock_env_vars):
        client = OpenRouter()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": [{"type": "text", "text": "from parts"}]}}]
        }

        with patch("app.llm.openrouter.httpx.AsyncClient", return_value=_http(response)):
            result = await client.prompt_model("hi")

        assert result == "from parts"

    @pytest.mark.asyncio
    async def test_prompt_model_hides_classified_reasoning(self, mock_env_vars):
        client = OpenRouter()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"type": "reasoning.text", "text": "think in private"},
                            {"type": "text", "text": "visible answer"},
                        ],
                        "reasoning": "also private",
                    }
                }
            ]
        }

        with patch("app.llm.openrouter.httpx.AsyncClient", return_value=_http(response)):
            result = await client.prompt_model("hi")

        assert result == "visible answer"

    @pytest.mark.asyncio
    async def test_prompt_model_rejects_reasoning_only_response(self, mock_env_vars):
        client = OpenRouter()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": None, "reasoning": "thought it through"}}]
        }

        with patch("app.llm.openrouter.httpx.AsyncClient", return_value=_http(response)):
            with pytest.raises(ValueError, match="did not include message text"):
                await client.prompt_model("hi")

    @pytest.mark.asyncio
    async def test_prompt_model_drops_think_blocks(self, mock_env_vars):
        client = OpenRouter()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": "<think>plan the reply</think>The meeting is at 6."},
                }
            ]
        }

        with patch("app.llm.openrouter.httpx.AsyncClient", return_value=_http(response)):
            result = await client.prompt_model("hi")

        assert result == "The meeting is at 6."

    @pytest.mark.asyncio
    async def test_prompt_model_rejects_truncated_response(self, mock_env_vars):
        client = OpenRouter()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {"content": "Here's a thinking process:"},
                }
            ]
        }

        with patch("app.llm.openrouter.httpx.AsyncClient", return_value=_http(response)):
            with pytest.raises(ValueError, match="finish_reason=length"):
                await client.prompt_model("hi")

    @pytest.mark.asyncio
    async def test_prompt_model_raises_on_http_error(self, mock_env_vars):
        client = OpenRouter()
        response = MagicMock()
        response.status_code = 429
        response.text = "rate limit"

        with patch("app.llm.openrouter.httpx.AsyncClient", return_value=_http(response)):
            with pytest.raises(RuntimeError, match="429"):
                await client.prompt_model("hi")

    @pytest.mark.asyncio
    async def test_prompt_model_uses_explicit_model(self, mock_env_vars, monkeypatch):
        monkeypatch.setenv("OPENROUTER_MODEL", "poolside/laguna-xs-2.1:free")
        client = OpenRouter()
        mock_http = _http(_ok("hello"))

        with patch("app.llm.openrouter.httpx.AsyncClient", return_value=mock_http):
            await client.prompt_model("hi")

        _, kwargs = mock_http.post.call_args
        assert kwargs["json"]["model"] == "poolside/laguna-xs-2.1:free"
        assert "models" not in kwargs["json"]

    @pytest.mark.asyncio
    async def test_prompt_model_routes_at_most_three_free_models(self, mock_env_vars, monkeypatch):
        pool = [f"example/chat-{i}:free" for i in range(5)]

        async def _pool(api_key, http):
            return pool

        monkeypatch.setattr("app.llm.openrouter.load_free_chat_models", _pool)
        client = OpenRouter()
        mock_http = _http(_ok("hello"))

        with patch("app.llm.openrouter.httpx.AsyncClient", return_value=mock_http):
            await client.prompt_model("hi")

        routed = mock_http.post.call_args.kwargs["json"]["models"]
        assert len(routed) == 3
        assert set(routed) <= set(pool)
        assert "nvidia/nemotron-3.5-content-safety:free" not in routed

    @pytest.mark.asyncio
    async def test_prompt_model_retries_after_safety_verdict(self, mock_env_vars):
        client = OpenRouter()
        verdict = MagicMock()
        verdict.status_code = 200
        verdict.json.return_value = {
            "model": "nvidia/nemotron-3.5-content-safety:free",
            "choices": [{"finish_reason": "stop", "message": {"content": "User Safety: safe"}}],
        }
        answer = _ok("Paris")
        answer.json.return_value["model"] = "poolside/laguna-xs-2.1:free"
        mock_http = _http(verdict)
        mock_http.post = AsyncMock(side_effect=[verdict, answer])

        with patch("app.llm.openrouter.httpx.AsyncClient", return_value=mock_http):
            result = await client.prompt_model("capital of France")

        assert result == "Paris"
        second_models = mock_http.post.call_args_list[1].kwargs["json"]["models"]
        assert "nvidia/nemotron-3.5-content-safety:free" not in second_models


def test_chat_model_ids_skip_content_safety_models():
    catalog = [
        {"id": "poolside/laguna-xs-2.1:free", "architecture": {"output_modalities": ["text"]}},
        {"id": "nvidia/nemotron-3.5-content-safety:free"},
        {"id": "meta-llama/llama-guard-4-12b:free"},
        {"id": "openai/gpt-oss-safeguard-20b"},
        {"id": "google/lyria-3-pro-preview:free", "architecture": {"output_modalities": ["audio"]}},
        {"id": "openrouter/free"},
    ]

    assert chat_model_ids(catalog) == ["poolside/laguna-xs-2.1:free"]
