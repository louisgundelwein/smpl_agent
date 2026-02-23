"""Agent loop: orchestrates LLM and tool execution."""

import json
from typing import Any

from src.llm import LLMClient
from src.tools.registry import ToolRegistry


SYSTEM_PROMPT = (
    "You are a helpful assistant with access to web search. "
    "Use the brave_web_search tool when you need current information "
    "from the internet. Always cite your sources with URLs."
)

MAX_TOOL_ROUNDS = 10


class Agent:
    """Agentic loop that alternates between LLM calls and tool execution."""

    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        system_prompt: str = SYSTEM_PROMPT,
        max_tool_rounds: int = MAX_TOOL_ROUNDS,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._max_tool_rounds = max_tool_rounds
        self._messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]

    @property
    def messages(self) -> list[dict[str, Any]]:
        """Current conversation history (read-only copy)."""
        return list(self._messages)

    def run(self, user_input: str) -> str:
        """Process a user message through the agent loop.

        Returns the agent's final text response.

        Raises:
            RuntimeError: If tool execution exceeds max_tool_rounds.
        """
        self._messages.append({"role": "user", "content": user_input})

        tool_schemas = self._registry.get_schemas()

        for _ in range(self._max_tool_rounds):
            response = self._llm.chat(
                messages=self._messages,
                tools=tool_schemas or None,
            )
            choice = response.choices[0]
            message = choice.message

            self._messages.append(message.model_dump())

            if not message.tool_calls:
                return message.content or ""

            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)

                try:
                    result = self._registry.execute(func_name, **func_args)
                except Exception as exc:
                    result = json.dumps({"error": str(exc)})

                self._messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": func_name,
                        "content": result,
                    }
                )

        raise RuntimeError(
            f"Agent exceeded maximum tool rounds ({self._max_tool_rounds})"
        )

    def reset(self) -> None:
        """Clear conversation history, keeping only the system prompt."""
        self._messages = [self._messages[0]]
