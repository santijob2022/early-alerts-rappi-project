"""LiteLLM wrapper — provider-agnostic LLM client.

Model and provider are determined entirely by settings.llm_model.
Switching from OpenAI to Anthropic / Ollama / Azure requires only an env var
change — no code modifications.
"""
from __future__ import annotations

import logging

import litellm

from app.config import Settings

logger = logging.getLogger(__name__)

# Suppress noisy litellm success logs
litellm.success_callback = []
litellm.set_verbose = False


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self._model = settings.llm_model
        self._api_key = settings.llm_api_key
        self._api_base = settings.llm_api_base

    async def generate(self, system_prompt: str, user_message: str) -> str:
        """Call the LLM and return the generated text.

        Raises RuntimeError on failure after logging the error.
        """
        kwargs: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "api_key": self._api_key,
            "timeout": 30,
        }
        if self._api_base:
            kwargs["api_base"] = self._api_base

        try:
            response = await litellm.acompletion(**kwargs)
            return response.choices[0].message.content
        except Exception as exc:
            logger.exception("LLM call failed: %s", exc)
            raise RuntimeError(f"LLM generation failed: {exc}") from exc
