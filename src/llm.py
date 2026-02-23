"""OpenAI LLM client wrapper."""

from typing import Any

from openai import OpenAI
from openai.types.chat import ChatCompletion


class LLMClient:
    """Wrapper around OpenAI Chat Completions API."""

    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatCompletion:
        """Send a chat completion request.

        Args:
            messages: The conversation messages list.
            tools: Optional list of tool schemas.
        """
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        return self._client.chat.completions.create(**kwargs)
