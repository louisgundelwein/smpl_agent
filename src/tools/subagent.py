"""Subagent tool — lets the LLM spawn and manage concurrent subagents."""

import json
from typing import Any

from src.subagent import SubagentManager
from src.tools.base import Tool


class SubagentTool(Tool):
    """Spawn and manage subagents that work on subtasks concurrently."""

    def __init__(self, manager: SubagentManager) -> None:
        self._manager = manager

    @property
    def name(self) -> str:
        return "subagent"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Spawn and manage subagents that work on subtasks concurrently. "
                    "Use 'spawn' to create a subagent with a task description. "
                    "Use 'status' to check progress of all or specific subagents. "
                    "Use 'result' to get the output of a completed subagent. "
                    "Use 'cancel' to stop a running subagent. "
                    "Subagents have access to web search, shell, and GitHub tools. "
                    "They run independently and cannot spawn further subagents. "
                    "Tasks must be self-contained — subagents have no access to "
                    "the main conversation context."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["spawn", "status", "result", "cancel"],
                            "description": (
                                "'spawn': create a new subagent, "
                                "'status': check all or one subagent, "
                                "'result': get output of a completed subagent, "
                                "'cancel': stop a running subagent."
                            ),
                        },
                        "task": {
                            "type": "string",
                            "description": (
                                "Task description for the subagent (required for 'spawn'). "
                                "Be specific and self-contained."
                            ),
                        },
                        "subagent_id": {
                            "type": "string",
                            "description": (
                                "ID of a specific subagent "
                                "(for 'status', 'result', 'cancel'). "
                                "Optional for 'status' (omit to see all)."
                            ),
                        },
                    },
                    "required": ["action"],
                },
            },
        }

    def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        try:
            if action == "spawn":
                return self._spawn(kwargs)
            elif action == "status":
                return self._status(kwargs)
            elif action == "result":
                return self._result(kwargs)
            elif action == "cancel":
                return self._cancel(kwargs)
            else:
                return json.dumps({"error": f"Unknown action: {action}"})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def _spawn(self, kwargs: dict) -> str:
        task = kwargs.get("task")
        if not task:
            return json.dumps({"error": "task is required for 'spawn' action"})
        state = self._manager.spawn(task)
        return json.dumps({
            "spawned": True,
            "subagent_id": state.id,
            "task": state.task,
            "active_count": self._manager.active_count(),
        })

    def _status(self, kwargs: dict) -> str:
        subagent_id = kwargs.get("subagent_id")
        statuses = self._manager.get_status(subagent_id)
        return json.dumps({"subagents": statuses}, ensure_ascii=False)

    def _result(self, kwargs: dict) -> str:
        subagent_id = kwargs.get("subagent_id")
        if not subagent_id:
            return json.dumps(
                {"error": "subagent_id is required for 'result' action"}
            )
        return json.dumps(
            self._manager.get_result(subagent_id), ensure_ascii=False
        )

    def _cancel(self, kwargs: dict) -> str:
        subagent_id = kwargs.get("subagent_id")
        if not subagent_id:
            return json.dumps(
                {"error": "subagent_id is required for 'cancel' action"}
            )
        return json.dumps(self._manager.cancel(subagent_id))
