"""Memory tool for the agent to store and search semantic memories."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from src.memory import MemoryStore
from src.tools.base import Tool

if TYPE_CHECKING:
    from src.auto_memory import AutoMemory


class MemoryTool(Tool):
    """Tool that gives the LLM access to persistent semantic memory.

    Supports four actions: store, search, delete, and cleanup.
    """

    def __init__(
        self,
        memory_store: MemoryStore,
        auto_memory: AutoMemory | None = None,
    ) -> None:
        self._store = memory_store
        self._auto_memory = auto_memory

    @property
    def name(self) -> str:
        return "memory"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Persistent semantic memory. Use this to store important "
                    "information for later retrieval, search past memories by "
                    "meaning, delete memories that are no longer needed, or "
                    "clean up near-duplicate memories."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["store", "search", "delete", "cleanup"],
                            "description": (
                                "The action to perform: "
                                "'store' to save new information, "
                                "'search' to find relevant memories, "
                                "'delete' to remove a memory by ID, "
                                "'cleanup' to find and merge near-duplicate memories."
                            ),
                        },
                        "content": {
                            "type": "string",
                            "description": (
                                "For 'store': the information to remember. "
                                "For 'search': the query to search for."
                            ),
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Optional tags for categorization (only for 'store')."
                            ),
                        },
                        "memory_id": {
                            "type": "integer",
                            "description": "The memory ID to delete (only for 'delete').",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of results for 'search' (default 5).",
                        },
                        "threshold": {
                            "type": "number",
                            "description": (
                                "Similarity threshold for 'cleanup' (default 0.90). "
                                "Memories above this threshold are considered duplicates."
                            ),
                        },
                    },
                    "required": ["action"],
                },
            },
        }

    def execute(self, **kwargs: Any) -> str:
        """Execute a memory action. Returns JSON string with results or error."""
        action = kwargs.get("action")

        try:
            if action == "store":
                return self._store_action(kwargs)
            elif action == "search":
                return self._search_action(kwargs)
            elif action == "delete":
                return self._delete_action(kwargs)
            elif action == "cleanup":
                return self._cleanup_action(kwargs)
            else:
                return json.dumps({"error": f"Unknown action: {action}"})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def _store_action(self, kwargs: dict) -> str:
        content = kwargs.get("content")
        if not content:
            return json.dumps({"error": "content is required for 'store' action"})

        tags = kwargs.get("tags")
        memory_id = self._store.add(content=content, tags=tags)
        total = self._store.count()
        return json.dumps({
            "stored": True,
            "memory_id": memory_id,
            "total_memories": total,
        })

    def _search_action(self, kwargs: dict) -> str:
        content = kwargs.get("content")
        if not content:
            return json.dumps({"error": "content is required for 'search' action"})

        top_k = kwargs.get("top_k", 5)
        results = self._store.search(query=content, top_k=top_k)
        return json.dumps({
            "results": results,
            "count": len(results),
        }, ensure_ascii=False)

    def _delete_action(self, kwargs: dict) -> str:
        memory_id = kwargs.get("memory_id")
        if memory_id is None:
            return json.dumps({"error": "memory_id is required for 'delete' action"})

        deleted = self._store.delete(memory_id=int(memory_id))
        return json.dumps({"deleted": deleted, "memory_id": memory_id})

    def _cleanup_action(self, kwargs: dict) -> str:
        if self._auto_memory is None:
            return json.dumps({"error": "cleanup requires auto_memory to be configured"})

        threshold = kwargs.get("threshold", 0.90)
        results = self._auto_memory.cleanup_duplicates(threshold=threshold)
        return json.dumps({
            "groups_merged": len(results),
            "total_deleted": sum(len(r["deleted_ids"]) for r in results),
            "merges": [
                {
                    "merged_id": r["merged_id"],
                    "deleted_ids": r["deleted_ids"],
                    "content": r["content"][:200],
                }
                for r in results
            ],
        }, ensure_ascii=False)
