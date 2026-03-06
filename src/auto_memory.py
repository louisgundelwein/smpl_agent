"""Automatic memory creation: summarize on reset, extract facts after turns."""

import logging
import threading
from queue import Queue
from typing import Any

from src.context import truncate_text
from src.events import AutoMemoryStoredEvent, EventEmitter, MemoryCleanupEvent
from src.llm import LLMClient
from src.memory import MemoryStore

logger = logging.getLogger(__name__)

# Minimum non-system messages to warrant a summary on reset.
MIN_MESSAGES_FOR_SUMMARY = 4

# Similarity threshold above which a memory is considered a duplicate.
DEDUP_THRESHOLD = 0.92

# Max recent messages to send for fact extraction.
MAX_EXTRACTION_MESSAGES = 20

CONVERSATION_SUMMARY_PROMPT = (
    "Summarize this conversation for long-term memory storage. "
    "Focus on:\n"
    "- What the user wanted and what was accomplished\n"
    "- Key decisions made and their rationale\n"
    "- User preferences, opinions, or personal facts revealed\n"
    "- Important technical details, project names, or configuration choices\n"
    "- Any unresolved issues or next steps\n\n"
    "Write a concise summary (3-8 sentences). "
    "Do NOT include greetings, filler, or meta-commentary about the summary itself."
)

MEMORY_MERGE_PROMPT = (
    "You are given a group of very similar memories that overlap in meaning. "
    "Merge them into a single, comprehensive memory that preserves ALL unique "
    "information from each. Be concise but complete — one or two sentences. "
    "Return ONLY the merged memory text, nothing else."
)

FACT_EXTRACTION_PROMPT = (
    "Analyze the following recent conversation messages and extract "
    "discrete, notable facts worth remembering long-term. Focus on:\n"
    "- User preferences (e.g., coding style, tool choices, communication preferences)\n"
    "- Personal facts (e.g., name, role, projects they work on, timezone)\n"
    "- Decisions made (e.g., chose library X over Y, adopted pattern Z)\n"
    "- Important context (e.g., deadlines, constraints, goals)\n\n"
    "Rules:\n"
    "- Skip trivial exchanges (greetings, acknowledgments, simple Q&A about public knowledge)\n"
    "- Skip anything that was ALREADY explicitly stored to memory via a memory tool call "
    "in the messages above\n"
    "- Each fact should be a single, self-contained sentence\n"
    "- If there is nothing worth remembering, respond with exactly: NONE\n\n"
    "Format: One fact per line, no numbering, no bullets."
)


class AutoMemory:
    """Automatic memory creation layer.

    Analogous to ContextManager: injected into Agent as an optional
    dependency, called at specific lifecycle points.

    - on_conversation_end(messages): Called before reset. Summarizes
      and stores the conversation if it's long enough. Runs synchronously.
    - on_turn_end(messages): Called after agent.run() returns.
      Every N turns, spawns a background thread to extract notable facts.
    """

    def __init__(
        self,
        llm: LLMClient,
        memory: MemoryStore,
        emitter: EventEmitter | None = None,
        extract_interval: int = 3,
    ) -> None:
        self._llm = llm
        self._memory = memory
        self._emitter = emitter or EventEmitter()
        self._extract_interval = extract_interval
        self._turn_count = 0
        self._extraction_queue: Queue[list[dict[str, Any]]] = Queue()
        self._bg_thread: threading.Thread | None = None
        self._shutdown_event = threading.Event()
        self._start_worker()

    def on_conversation_end(self, messages: list[dict[str, Any]]) -> None:
        """Summarize and store conversation before reset.

        Runs synchronously. Skips if conversation is too short.
        """
        non_system = [m for m in messages if m.get("role") != "system"]
        if len(non_system) < MIN_MESSAGES_FOR_SUMMARY:
            return

        try:
            summary = self._summarize_conversation(messages)
            if not summary:
                return

            memory_id = self._memory.add(
                content=summary, tags=["auto", "summary"]
            )
            self._emitter.emit(
                AutoMemoryStoredEvent(
                    content=summary[:100],
                    tags=["auto", "summary"],
                    source="conversation_end",
                )
            )
            logger.info("Auto-memory: stored conversation summary (id=%s)", memory_id)
        except Exception:
            logger.exception("Auto-memory: failed to summarize conversation")

        # Run dedup cleanup after storing the summary.
        try:
            self.cleanup_duplicates()
        except Exception:
            logger.exception("Auto-memory: cleanup failed during conversation end")

        # Reset turn counter for the new conversation.
        self._turn_count = 0

    def on_turn_end(self, messages: list[dict[str, Any]]) -> None:
        """Increment turn counter; every N turns, queue facts extraction.

        Extractions are queued and processed sequentially by a worker thread.
        """
        self._turn_count += 1
        if self._turn_count % self._extract_interval != 0:
            return

        # Snapshot recent messages for the worker thread.
        tail_size = min(self._extract_interval * 2 + 2, MAX_EXTRACTION_MESSAGES)
        snapshot = list(messages[-tail_size:])

        self._extraction_queue.put(snapshot)

    def cleanup_duplicates(
        self, threshold: float = 0.90
    ) -> list[dict[str, Any]]:
        """Find and merge near-duplicate memory groups.

        For each group of similar memories (above *threshold*), uses the
        LLM to merge them into a single comprehensive memory, stores the
        merged version, and deletes the originals.

        Returns:
            List of merge result dicts, each with keys:
            merged_id, deleted_ids, content.
        """
        try:
            groups = self._memory.find_duplicate_groups(threshold=threshold)
        except Exception:
            logger.exception("Memory cleanup: failed to find duplicate groups")
            return []

        if not groups:
            return []

        results: list[dict[str, Any]] = []
        total_deleted = 0

        for group in groups:
            try:
                merged_text = self._merge_group(group)
                if not merged_text:
                    continue

                # Collect unique tags from all members.
                all_tags: set[str] = {"auto", "merged"}
                for mem in group:
                    for tag in mem.get("tags", []):
                        all_tags.add(tag)

                merged_id = self._memory.add(
                    content=merged_text, tags=sorted(all_tags)
                )

                # Delete originals.
                deleted_ids = []
                for mem in group:
                    if self._memory.delete(mem["id"]):
                        deleted_ids.append(mem["id"])

                total_deleted += len(deleted_ids)
                results.append({
                    "merged_id": merged_id,
                    "deleted_ids": deleted_ids,
                    "content": merged_text,
                })

                logger.info(
                    "Memory cleanup: merged %d memories into id=%s",
                    len(deleted_ids),
                    merged_id,
                )
            except Exception:
                logger.exception(
                    "Memory cleanup: failed to merge group (ids=%s)",
                    [m["id"] for m in group],
                )

        if results:
            self._emitter.emit(
                MemoryCleanupEvent(
                    groups_merged=len(results),
                    memories_deleted=total_deleted,
                )
            )

        return results

    def _merge_group(self, group: list[dict[str, Any]]) -> str | None:
        """Use LLM to merge a group of similar memories into one."""
        memories_text = "\n".join(
            f"- {mem['content']}" for mem in group
        )
        response = self._llm.chat(
            messages=[
                {"role": "system", "content": MEMORY_MERGE_PROMPT},
                {"role": "user", "content": memories_text},
            ]
        )
        text = (response.choices[0].message.content or "").strip()
        return text if text else None

    def _start_worker(self) -> None:
        """Start the extraction worker thread."""
        self._bg_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
        )
        self._bg_thread.start()

    def _worker_loop(self) -> None:
        """Worker thread: process extraction requests from the queue sequentially."""
        while not self._shutdown_event.is_set():
            try:
                # Get next extraction request with timeout to allow shutdown checks
                messages = self._extraction_queue.get(timeout=1)
                if messages is None:  # Poison pill
                    break
                self._extract_facts(messages)
            except Exception:
                # Queue.Empty is raised on timeout, which is fine
                continue

    def shutdown(self) -> None:
        """Signal worker thread to stop and wait briefly."""
        self._shutdown_event.set()
        if self._bg_thread is not None and self._bg_thread.is_alive():
            self._bg_thread.join(timeout=5)

    def _summarize_conversation(
        self, messages: list[dict[str, Any]]
    ) -> str | None:
        """Use LLM to create a conversation summary. Returns None on failure."""
        formatted = _format_messages_for_llm(messages)
        response = self._llm.chat(
            messages=[
                {"role": "system", "content": CONVERSATION_SUMMARY_PROMPT},
                {"role": "user", "content": formatted},
            ]
        )
        summary = response.choices[0].message.content
        return summary.strip() if summary else None

    def _extract_facts(self, messages: list[dict[str, Any]]) -> None:
        """Background thread target: extract and store facts from recent messages."""
        try:
            if self._shutdown_event.is_set():
                return

            formatted = _format_messages_for_llm(messages)
            response = self._llm.chat(
                messages=[
                    {"role": "system", "content": FACT_EXTRACTION_PROMPT},
                    {"role": "user", "content": formatted},
                ]
            )
            text = (response.choices[0].message.content or "").strip()
            if not text or text.upper() == "NONE":
                return

            facts = [line.strip() for line in text.splitlines() if line.strip()]

            for fact in facts:
                if self._shutdown_event.is_set():
                    return
                self._store_if_not_duplicate(fact, tags=["auto"])
        except Exception:
            logger.exception("Auto-memory: fact extraction failed")

    def _store_if_not_duplicate(
        self, content: str, tags: list[str]
    ) -> int | None:
        """Store a memory only if no near-duplicate exists. Returns memory ID or None."""
        try:
            results = self._memory.search(query=content, top_k=1)
            if results and results[0]["score"] > DEDUP_THRESHOLD:
                logger.debug(
                    "Auto-memory: skipping duplicate (score=%.3f): %s",
                    results[0]["score"],
                    content[:60],
                )
                return None
        except Exception:
            logger.exception("Auto-memory: dedup search failed, storing anyway")

        memory_id = self._memory.add(content=content, tags=tags)
        self._emitter.emit(
            AutoMemoryStoredEvent(
                content=content[:100],
                tags=tags,
                source="turn_extraction",
            )
        )
        logger.info("Auto-memory: stored fact (id=%s): %s", memory_id, content[:60])
        return memory_id


def _format_messages_for_llm(messages: list[dict[str, Any]]) -> str:
    """Convert messages to readable text for LLM prompts."""
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
            # Skip system messages in the formatted output for extraction/summary.
            continue

    return "\n\n".join(parts)
