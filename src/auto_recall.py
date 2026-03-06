"""Automatic memory recall: inject relevant memories before each LLM call."""

import logging
import time
from typing import Any

from src.events import EventEmitter, MemoryRecallEvent
from src.memory import MemoryStore

logger = logging.getLogger(__name__)

# Default relevance threshold (cosine similarity + fts bonus).
DEFAULT_THRESHOLD = 0.55
DEFAULT_TOP_K = 5


class AutoRecall:
    """Proactive memory search injected into the agent loop.

    Before each LLM call, searches memory with the user's message and
    returns formatted context if relevant matches are found.  Analogous
    to ContextManager — an optional dependency injected into Agent.
    """

    def __init__(
        self,
        memory: MemoryStore,
        emitter: EventEmitter | None = None,
        threshold: float = DEFAULT_THRESHOLD,
        top_k: int = DEFAULT_TOP_K,
    ) -> None:
        self._memory = memory
        self._emitter = emitter or EventEmitter()
        self._threshold = threshold
        self._top_k = top_k

    def recall(self, user_input: str) -> dict[str, str] | None:
        """Search memory for relevant context given the user's message.

        Returns a dict with 'role' and 'content' keys to inject into messages,
        or None if no relevant memories are found.
        """
        try:
            if self._memory.count() == 0:
                return None

            t0 = time.monotonic()
            results = self._memory.search(query=user_input, top_k=self._top_k)
            duration_ms = int((time.monotonic() - t0) * 1000)

            # Filter by relevance threshold.
            relevant = [r for r in results if r["score"] >= self._threshold]
            if not relevant:
                return None

            self._emitter.emit(
                MemoryRecallEvent(
                    count=len(relevant),
                    top_score=relevant[0]["score"],
                    duration_ms=duration_ms,
                )
            )

            formatted = _format_recall(relevant)
            return {"role": "user", "content": formatted}

        except Exception:
            logger.exception("Auto-recall: search failed")
            return None


def _format_recall(memories: list[dict[str, Any]]) -> str:
    """Format recalled memories into a context message."""
    lines = [
        "[Memory context — automatically recalled, may or may not be relevant]"
    ]
    for mem in memories:
        score = mem["score"]
        content = mem["content"].replace("\n", " ")
        lines.append(f"- (score {score:.2f}) {content}")
    lines.append("[End memory context]")
    return "\n".join(lines)
