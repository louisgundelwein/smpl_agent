"""Automatic context management: compress conversation history when it grows too large."""

import json
from typing import Any

from src.llm import LLMClient

# Try to import tiktoken for accurate token counting
try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False


SUMMARIZE_PROMPT = (
    "Summarize the following conversation history concisely. "
    "Preserve: key facts, decisions made, tool results that matter, "
    "and any user preferences or instructions. "
    "Omit: verbose tool outputs, repeated information, and pleasantries. "
    "Format as a concise bulleted list."
)

CHARS_PER_TOKEN = 4


def truncate_text(text: str, max_len: int = 2000) -> str:
    """Truncate text longer than max_len, preserving start and end.

    Format: first 1000 chars + "...[truncated]..." + last 500 chars
    """
    if len(text) <= max_len:
        return text
    return text[:1000] + "\n...[truncated]...\n" + text[-500:]


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
        self._tiktoken_enc = None

        # Initialize tiktoken encoder for OpenAI models if available
        if _TIKTOKEN_AVAILABLE and self._is_openai_model(llm.model):
            try:
                self._tiktoken_enc = tiktoken.encoding_for_model(llm.model)
            except (KeyError, Exception):
                # Model not in tiktoken db or other error, fall back to char counting
                pass

    def estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Estimate total token count using tiktoken if available, else fallback."""
        if self._tiktoken_enc:
            return self._count_tokens_tiktoken(messages)
        return self._count_tokens_fallback(messages)

    def _count_tokens_tiktoken(self, messages: list[dict[str, Any]]) -> int:
        """Count tokens using tiktoken."""
        total = 0
        for msg in messages:
            content = msg.get("content") or ""
            if content:
                total += len(self._tiktoken_enc.encode(content))
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                tool_json = json.dumps(tool_calls)
                total += len(self._tiktoken_enc.encode(tool_json))
        return total

    def _count_tokens_fallback(self, messages: list[dict[str, Any]]) -> int:
        """Fallback token count using character estimation."""
        total_chars = 0
        for msg in messages:
            content = msg.get("content") or ""
            total_chars += len(content)
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                total_chars += len(json.dumps(tool_calls))
        return total_chars // CHARS_PER_TOKEN

    @staticmethod
    def _is_openai_model(model: str) -> bool:
        """Check if the model is an OpenAI model (gpt-*, o1-*, etc)."""
        return model.startswith(("gpt-", "o1-"))

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
        summary = response.choices[0].message.content
        if not summary:
            raise ValueError("LLM returned empty summary")
        return summary

    def _format_for_summary(self, messages: list[dict[str, Any]]) -> str:
        """Convert messages to readable text for the summarizer."""
        parts: list[str] = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content") or ""

            if role == "tool":
                name = msg.get("name", "unknown")
                content = truncate_text(content)
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
