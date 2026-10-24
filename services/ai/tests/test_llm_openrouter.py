"""Tests for the OpenRouter client used by Discord bot chat."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.llm.openrouter import OpenRouter


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
        assert kwargs["json"]["model"] == "openrouter/free"
        assert "models" not in kwargs["json"]
        assert kwargs["json"]["max_tokens"] == 500
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
    async def test_prompt_model_falls_back_to_reasoning(self, mock_env_vars):
        client = OpenRouter()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": None, "reasoning": "thought it through"}}]
        }

        with patch("app.llm.openrouter.httpx.AsyncClient", return_value=_http(response)):
            result = await client.prompt_model("hi")

        assert result == "thought it through"

    @pytest.mark.asyncio
    async def test_prompt_model_raises_on_http_error(self, mock_env_vars):
        client = OpenRouter()
        response = MagicMock()
        response.status_code = 429
        response.text = "rate limit"

        with patch("app.llm.openrouter.httpx.AsyncClient", return_value=_http(response)):
            with pytest.raises(RuntimeError, match="429"):
                await client.prompt_model("hi")
