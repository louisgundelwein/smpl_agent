"""Agent loop: orchestrates LLM and tool execution."""

import json
import time
from typing import Any

from src.context import ContextManager
from src.history import ConversationHistory
from src.events import (
    ContextCompressedEvent,
    EventEmitter,
    LLMEndEvent,
    LLMStartEvent,
    SubagentResultsCollectedEvent,
    SubagentWaitEvent,
    ToolEndEvent,
    ToolErrorEvent,
    ToolStartEvent,
)
from src.llm import LLMClient
from src.subagent import SubagentManager
from src.tools.registry import ToolRegistry


SYSTEM_PROMPT = (
    "You are a helpful assistant with access to web search and persistent memory.\n\n"
    "Use the brave_web_search tool when you need current information "
    "from the internet. Always cite your sources with URLs.\n\n"
    "Use the memory tool to store important facts, user preferences, and "
    "key information that might be useful in future conversations. "
    "Before answering questions about past interactions, search your memory first."
)

MAX_TOOL_ROUNDS = 10


def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Rough token estimate: total characters / 4."""
    total = 0
    for msg in messages:
        total += len(msg.get("content") or "")
        tc = msg.get("tool_calls")
        if tc:
            total += len(json.dumps(tc))
    return total // 4


class Agent:
    """Agentic loop that alternates between LLM calls and tool execution."""

    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        system_prompt: str = SYSTEM_PROMPT,
        max_tool_rounds: int = MAX_TOOL_ROUNDS,
        emitter: EventEmitter | None = None,
        context_manager: ContextManager | None = None,
        history: ConversationHistory | None = None,
        subagent_manager: SubagentManager | None = None,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._max_tool_rounds = max_tool_rounds
        self._emitter = emitter or EventEmitter()
        self._context_manager = context_manager
        self._history = history
        self._subagent_manager = subagent_manager

        # Load persisted conversation or start fresh.
        # Always replace the system prompt with the current one
        # so edits to SOUL.md take effect immediately.
        loaded = history.load() if history else None
        if loaded:
            loaded[0] = {"role": "system", "content": system_prompt}
            self._messages = loaded
        else:
            self._messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt}
            ]

    @property
    def emitter(self) -> EventEmitter:
        """Access the agent's event emitter."""
        return self._emitter

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

        for round_num in range(1, self._max_tool_rounds + 1):
            if self._context_manager:
                original_count = len(self._messages)
                original_tokens = self._context_manager.estimate_tokens(
                    self._messages
                )
                self._messages = self._context_manager.maybe_compress(
                    self._messages
                )
                if len(self._messages) < original_count:
                    self._emitter.emit(
                        ContextCompressedEvent(
                            original_tokens=original_tokens,
                            compressed_tokens=self._context_manager.estimate_tokens(
                                self._messages
                            ),
                            messages_removed=original_count - len(self._messages),
                        )
                    )

            self._emitter.emit(
                LLMStartEvent(
                    round_number=round_num,
                    message_count=len(self._messages),
                    estimated_tokens=_estimate_tokens(self._messages),
                )
            )

            t0 = time.monotonic()
            response = self._llm.chat(
                messages=self._messages,
                tools=tool_schemas or None,
            )
            llm_ms = int((time.monotonic() - t0) * 1000)

            choice = response.choices[0]
            message = choice.message

            self._emitter.emit(
                LLMEndEvent(
                    round_number=round_num,
                    has_tool_calls=bool(message.tool_calls),
                    duration_ms=llm_ms,
                )
            )

            self._messages.append(message.model_dump(exclude_none=True))

            if not message.tool_calls:
                # If subagents are still running, wait for them and
                # re-enter the loop so the LLM can synthesize results.
                active = (
                    self._subagent_manager.active_count()
                    if self._subagent_manager
                    else 0
                )
                if active > 0:
                    self._emitter.emit(SubagentWaitEvent(active_count=active))

                    t0 = time.monotonic()
                    results = self._subagent_manager.wait_all()
                    wait_ms = int((time.monotonic() - t0) * 1000)

                    self._emitter.emit(
                        SubagentResultsCollectedEvent(
                            count=len(results), duration_ms=wait_ms
                        )
                    )

                    self._messages.append(
                        {
                            "role": "user",
                            "content": self._format_subagent_results(results),
                        }
                    )
                    continue

                self._save_history()
                return message.content or ""

            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)

                self._emitter.emit(ToolStartEvent(tool_name=func_name, arguments=func_args))

                t0 = time.monotonic()
                try:
                    result = self._registry.execute(func_name, **func_args)
                    tool_ms = int((time.monotonic() - t0) * 1000)
                    self._emitter.emit(ToolEndEvent(tool_name=func_name, duration_ms=tool_ms))
                except Exception as exc:
                    tool_ms = int((time.monotonic() - t0) * 1000)
                    result = json.dumps({"error": str(exc)})
                    self._emitter.emit(
                        ToolErrorEvent(tool_name=func_name, error=str(exc), duration_ms=tool_ms)
                    )

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

    @staticmethod
    def _format_subagent_results(results: list[dict[str, Any]]) -> str:
        """Format subagent results into a synthetic user message."""
        lines = [
            "[Subagent results are now available. "
            "Summarize them for the user.]\n"
        ]
        for r in results:
            sid = r["id"]
            task = r["task"]
            status = r["status"]
            if status == "completed":
                lines.append(f"--- Subagent {sid} ({task}) ---\n{r['result']}\n")
            elif status == "failed":
                lines.append(
                    f"--- Subagent {sid} ({task}) ---\nFailed: {r['error']}\n"
                )
            else:
                lines.append(
                    f"--- Subagent {sid} ({task}) ---\nStatus: {status}\n"
                )
        return "\n".join(lines)

    def _save_history(self) -> None:
        """Persist current messages if history is configured."""
        if self._history:
            self._history.save(self._messages)

    def update_system_prompt(self, new_prompt: str) -> None:
        """Replace the system prompt in the current conversation."""
        self._messages[0] = {"role": "system", "content": new_prompt}

    def reset(self) -> None:
        """Clear conversation history, keeping only the system prompt."""
        self._messages = [self._messages[0]]
        if self._history:
            self._history.clear()
