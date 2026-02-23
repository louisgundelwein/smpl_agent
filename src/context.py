"""Automatic context management: compress conversation history when it grows too large."""

import json
from typing import Any

from src.llm import LLMClient


SUMMARIZE_PROMPT = (
    "Summarize the following conversation history concisely. "
    "Preserve: key facts, decisions made, tool results that matter, "
    "and any user preferences or instructions. "
    "Omit: verbose tool outputs, repeated information, and pleasantries. "
    "Format as a concise bulleted list."
)

CHARS_PER_TOKEN = 4


class ContextManager:
    """Monitors message list size and compresses via LLM summarization.

    Called before each LLM call in the agent loop. If the estimated
    token count exceeds max_tokens, older messages are summarized
    into a single system message while preserving recent messages.
    """

    def __init__(
        self,
        llm: LLMClient,
        max_tokens: int = 100_000,
        preserve_recent: int = 10,
    ) -> None:
        self._llm = llm
        self._max_tokens = max_tokens
        self._preserve_recent = preserve_recent

    def estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Estimate total token count across all messages."""
        total_chars = 0
        for msg in messages:
            content = msg.get("content") or ""
            total_chars += len(content)
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                total_chars += len(json.dumps(tool_calls))
        return total_chars // CHARS_PER_TOKEN

    def maybe_compress(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Compress messages if estimated tokens exceed the limit.

        Returns the original list unchanged if no compression is needed,
        or a new compressed list. The input is never mutated.
        """
        if self.estimate_tokens(messages) <= self._max_tokens:
            return messages

        system = messages[0]
        rest = messages[1:]

        # Nothing to compress if fewer messages than preserve_recent
        if len(rest) <= self._preserve_recent:
            return messages

        # Split into compressible zone and preserved zone
        cut = len(rest) - self._preserve_recent
        compressible = rest[:cut]
        preserved = rest[cut:]

        # Adjust cut to a safe boundary (don't split tool-call blocks)
        safe_cut = self._find_safe_cut(compressible)
        if safe_cut <= 0:
            return messages  # can't compress safely

        to_compress = compressible[:safe_cut]
        remaining = compressible[safe_cut:]

        try:
            summary_text = self._summarize(to_compress)
        except Exception:
            return messages  # graceful degradation

        summary_msg = {
            "role": "system",
            "content": (
                "[Conversation Summary]\n"
                "The following is a summary of earlier conversation history "
                "that has been compressed to save context space:\n\n"
                f"{summary_text}\n\n"
                "[End of Summary - Recent conversation follows]"
            ),
        }

        return [system, summary_msg] + remaining + preserved

    def _find_safe_cut(self, messages: list[dict[str, Any]]) -> int:
        """Find the last safe cut point in the message list.

        A safe cut point is after a complete turn (not in the middle
        of an assistant-tool_calls + tool-responses block).
        """
        safe = 0
        i = 0
        while i < len(messages):
            msg = messages[i]
            role = msg.get("role")

            if role == "assistant" and msg.get("tool_calls"):
                # Skip past the assistant + all following tool responses
                i += 1
                while i < len(messages) and messages[i].get("role") == "tool":
                    i += 1
                safe = i
            else:
                i += 1
                safe = i

        return safe

    def _summarize(self, messages: list[dict[str, Any]]) -> str:
        """Use the LLM to summarize a list of messages."""
        formatted = self._format_for_summary(messages)
        response = self._llm.chat(
            messages=[
                {"role": "system", "content": SUMMARIZE_PROMPT},
                {"role": "user", "content": formatted},
            ]
        )
        return response.choices[0].message.content

    def _format_for_summary(self, messages: list[dict[str, Any]]) -> str:
        """Convert messages to readable text for the summarizer."""
        parts: list[str] = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content") or ""

            if role == "tool":
                name = msg.get("name", "unknown")
                if len(content) > 2000:
                    content = content[:1000] + "\n...[truncated]...\n" + content[-500:]
                parts.append(f"[Tool: {name}] {content}")
            elif role == "assistant" and msg.get("tool_calls"):
                calls = msg.get("tool_calls", [])
                call_names = []
                for c in calls:
                    if isinstance(c, dict):
                        call_names.append(c.get("function", {}).get("name", "?"))
                    else:
                        call_names.append(str(c))
                parts.append(f"Assistant called tools: {', '.join(call_names)}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
            elif role == "user":
                parts.append(f"User: {content}")
            elif role == "system":
                parts.append(f"System: {content}")

        return "\n\n".join(parts)
