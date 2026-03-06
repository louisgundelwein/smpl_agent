"""OpenAI LLM client wrapper."""

import time
from typing import Any

from openai import OpenAI
from openai.types.chat import ChatCompletion
from httpx import ConnectError, TimeoutException
from openai import APIConnectionError, RateLimitError, APIStatusError


class LLMClient:
    """Wrapper around OpenAI Chat Completions API."""

    _KNOWN_FIELDS = frozenset({"role", "content", "tool_calls", "tool_call_id", "name"})

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout: int = 120,
    ) -> None:
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatCompletion:
        """Send a chat completion request with exponential backoff retry.

        Args:
            messages: The conversation messages list.
            tools: Optional list of tool schemas.

        Raises:
            Exception: After 3 failed attempts with backoff.
        """
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": self._sanitize_messages(messages),
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        max_attempts = 3
        delay = 1  # Start with 1 second
        for attempt in range(max_attempts):
            try:
                return self._client.chat.completions.create(**kwargs)
            except (
                ConnectError,
                TimeoutException,
                APIConnectionError,
                RateLimitError,
                APIStatusError,
            ) as e:
                # Retry on transient errors: network, timeouts, 429, 500, 502, 503
                if isinstance(e, APIStatusError):
                    # Only retry on server errors and rate limit
                    if e.status_code not in (429, 500, 502, 503):
                        raise

                if attempt == max_attempts - 1:
                    raise

                time.sleep(delay)
                delay *= 2  # Exponential backoff

    @staticmethod
    def _sanitize_messages(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Strip unknown fields and ensure every message has content.

        Some providers (e.g. Gemini) reject messages without a content/parts
        field.  The OpenAI SDK's model_dump may include extra fields
        (annotations, refusal, audio) that other providers also reject.
        """
        sanitized: list[dict[str, Any]] = []
        for msg in messages:
            clean = {
                k: v for k, v in msg.items() if k in LLMClient._KNOWN_FIELDS
            }
            if "content" not in clean:
                clean["content"] = ""
            sanitized.append(clean)
        return sanitized
