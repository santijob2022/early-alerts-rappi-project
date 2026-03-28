"""Telegram message sender — plain HTTP call to the Bot API sendMessage endpoint."""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(15.0)
_MAX_MESSAGE_LENGTH = 4096  # Telegram hard limit


def _truncate(text: str) -> str:
    if len(text) > _MAX_MESSAGE_LENGTH:
        suffix = "\n[mensaje truncado por longitud máxima]"
        return text[: _MAX_MESSAGE_LENGTH - len(suffix)] + suffix
    return text


async def send_message(bot_token: str, chat_id: str, text: str) -> bool:
    """Send a plain-text message via the Telegram Bot API.

    Returns True on success, False on failure (after logging the error).
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": _truncate(text)}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                return True
            logger.error(
                "Telegram sendMessage failed: HTTP %s — %s",
                response.status_code,
                response.text,
            )
            return False
        except httpx.RequestError as exc:
            logger.exception("Telegram sendMessage request error: %s", exc)
            return False
