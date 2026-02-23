"""Memory tool for the agent to store and search semantic memories."""

import json
from typing import Any

from src.memory import MemoryStore
from src.tools.base import Tool


class MemoryTool(Tool):
    """Tool that gives the LLM access to persistent semantic memory.

    Supports three actions: store, search, and delete.
    """

    def __init__(self, memory_store: MemoryStore) -> None:
        self._store = memory_store

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
                    "meaning, or delete memories that are no longer needed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["store", "search", "delete"],
                            "description": (
                                "The action to perform: "
                                "'store' to save new information, "
                                "'search' to find relevant memories, "
                                "'delete' to remove a memory by ID."
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
