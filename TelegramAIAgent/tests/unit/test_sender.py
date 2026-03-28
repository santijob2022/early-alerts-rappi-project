"""Unit tests for app/services/telegram/sender.py."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.services.telegram.sender import _MAX_MESSAGE_LENGTH, _truncate, send_message

BOT_TOKEN = "123456:TEST_TOKEN"
CHAT_ID = "987654"
SEND_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


# ── _truncate ─────────────────────────────────────────────────────────────────

class TestTruncate:
    def test_short_message_unchanged(self):
        msg = "hello"
        assert _truncate(msg) == msg

    def test_exact_limit_unchanged(self):
        msg = "x" * _MAX_MESSAGE_LENGTH
        assert _truncate(msg) == msg

    def test_long_message_truncated(self):
        msg = "x" * (_MAX_MESSAGE_LENGTH + 100)
        result = _truncate(msg)
        assert len(result) == _MAX_MESSAGE_LENGTH

    def test_truncated_message_ends_with_suffix(self):
        msg = "x" * (_MAX_MESSAGE_LENGTH + 100)
        result = _truncate(msg)
        assert result.endswith("[mensaje truncado por longitud máxima]")

    def test_truncate_preserves_beginning(self):
        prefix = "IMPORTANT_START "
        msg = prefix + "x" * (_MAX_MESSAGE_LENGTH + 100)
        result = _truncate(msg)
        assert result.startswith("IMPORTANT_START")

    def test_empty_string_unchanged(self):
        assert _truncate("") == ""


# ── send_message ──────────────────────────────────────────────────────────────

class TestSendMessage:
    @respx.mock
    async def test_success_returns_true(self):
        respx.post(SEND_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
        result = await send_message(BOT_TOKEN, CHAT_ID, "hello")
        assert result is True

    @respx.mock
    async def test_http_400_returns_false(self):
        respx.post(SEND_URL).mock(return_value=httpx.Response(400, json={"ok": False}))
        result = await send_message(BOT_TOKEN, CHAT_ID, "hello")
        assert result is False

    @respx.mock
    async def test_http_500_returns_false(self):
        respx.post(SEND_URL).mock(return_value=httpx.Response(500, text="Internal Server Error"))
        result = await send_message(BOT_TOKEN, CHAT_ID, "hello")
        assert result is False

    @respx.mock
    async def test_sends_correct_payload(self):
        route = respx.post(SEND_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
        await send_message(BOT_TOKEN, CHAT_ID, "test message")
        sent_json = route.calls.last.request.read()
        import json
        payload = json.loads(sent_json)
        assert payload["chat_id"] == CHAT_ID
        assert payload["text"] == "test message"

    @respx.mock
    async def test_long_message_is_truncated_before_send(self):
        route = respx.post(SEND_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
        long_text = "z" * (_MAX_MESSAGE_LENGTH + 500)
        await send_message(BOT_TOKEN, CHAT_ID, long_text)
        import json
        payload = json.loads(route.calls.last.request.read())
        assert len(payload["text"]) == _MAX_MESSAGE_LENGTH

    @respx.mock
    async def test_request_error_returns_false(self):
        respx.post(SEND_URL).mock(side_effect=httpx.ConnectError("refused"))
        result = await send_message(BOT_TOKEN, CHAT_ID, "hello")
        assert result is False

    @respx.mock
    async def test_timeout_error_returns_false(self):
        respx.post(SEND_URL).mock(side_effect=httpx.TimeoutException("timed out"))
        result = await send_message(BOT_TOKEN, CHAT_ID, "hello")
        assert result is False
