"""Unit tests for app/agent/llm/client.py."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.llm.client import LLMClient
from app.config import Settings


def _make_settings(**kwargs) -> Settings:
    base = dict(
        telegram_bot_token="tok",
        telegram_chat_id="123",
        llm_api_key="test_key",
        llm_model="gpt-4o-mini",
        motor_rules_path="data/historical_context/Motor_Reglas_y_Alertas.md",
        motor_docs_path="data/historical_context/Documentacion_Motor_Alertas_Tempranas.md",
    )
    base.update(kwargs)
    return Settings(**base)


def _make_llm_response(content: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


class TestLLMClient:
    async def test_generate_returns_content(self):
        settings = _make_settings()
        client = LLMClient(settings)
        mock_response = _make_llm_response("respuesta generada")

        with patch("app.agent.llm.client.litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            result = await client.generate("system prompt", "user message")

        assert result == "respuesta generada"

    async def test_generate_passes_system_and_user_messages(self):
        settings = _make_settings()
        client = LLMClient(settings)
        mock_response = _make_llm_response("ok")

        with patch("app.agent.llm.client.litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            await client.generate("sys", "usr")

        call_kwargs = mock_call.call_args.kwargs
        messages = call_kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "sys"}
        assert messages[1] == {"role": "user", "content": "usr"}

    async def test_generate_uses_configured_model(self):
        settings = _make_settings(llm_model="anthropic/claude-3-haiku-20240307")
        client = LLMClient(settings)
        mock_response = _make_llm_response("ok")

        with patch("app.agent.llm.client.litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            await client.generate("s", "u")

        assert mock_call.call_args.kwargs["model"] == "anthropic/claude-3-haiku-20240307"

    async def test_generate_includes_api_base_when_set(self):
        settings = _make_settings(llm_api_base="http://localhost:11434")
        client = LLMClient(settings)
        mock_response = _make_llm_response("ok")

        with patch("app.agent.llm.client.litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            await client.generate("s", "u")

        assert mock_call.call_args.kwargs.get("api_base") == "http://localhost:11434"

    async def test_generate_omits_api_base_when_none(self):
        settings = _make_settings(llm_api_base=None)
        client = LLMClient(settings)
        mock_response = _make_llm_response("ok")

        with patch("app.agent.llm.client.litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            await client.generate("s", "u")

        assert "api_base" not in mock_call.call_args.kwargs

    async def test_generate_raises_runtime_error_on_exception(self):
        settings = _make_settings()
        client = LLMClient(settings)

        with patch(
            "app.agent.llm.client.litellm.acompletion",
            new=AsyncMock(side_effect=Exception("network error")),
        ):
            with pytest.raises(RuntimeError, match="LLM generation failed"):
                await client.generate("s", "u")

    async def test_generate_runtime_error_chains_original(self):
        settings = _make_settings()
        client = LLMClient(settings)
        original = ValueError("bad response")

        with patch(
            "app.agent.llm.client.litellm.acompletion",
            new=AsyncMock(side_effect=original),
        ):
            with pytest.raises(RuntimeError) as exc_info:
                await client.generate("s", "u")

        assert exc_info.value.__cause__ is original

    async def test_generate_passes_timeout(self):
        settings = _make_settings()
        client = LLMClient(settings)
        mock_response = _make_llm_response("ok")

        with patch("app.agent.llm.client.litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            await client.generate("s", "u")

        assert mock_call.call_args.kwargs.get("timeout") == 30
