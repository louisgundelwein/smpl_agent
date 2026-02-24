"""Scheduler tool for managing scheduled/recurring tasks."""

import json
from typing import Any

from src.scheduler import SchedulerStore
from src.tools.base import Tool


class SchedulerTool(Tool):
    """Tool that gives the LLM access to scheduled task management.

    Supports actions: create, list, delete, enable, disable.
    """

    def __init__(self, store: SchedulerStore) -> None:
        self._store = store

    @property
    def name(self) -> str:
        return "scheduler"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Manage scheduled/recurring tasks. Tasks run automatically "
                    "on a cron schedule. Use this to create, list, delete, "
                    "enable, or disable scheduled tasks. Results are delivered "
                    "to memory and/or Telegram."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["create", "list", "delete", "enable", "disable"],
                            "description": (
                                "'create' to add a new scheduled task, "
                                "'list' to show all tasks, "
                                "'delete' to remove a task, "
                                "'enable'/'disable' to toggle a task."
                            ),
                        },
                        "name": {
                            "type": "string",
                            "description": "Unique name for the task.",
                        },
                        "prompt": {
                            "type": "string",
                            "description": "The instruction to execute on schedule (for 'create').",
                        },
                        "schedule": {
                            "type": "string",
                            "description": (
                                "Cron expression (e.g., '0 9 * * *' for daily at 9am UTC, "
                                "'0 */6 * * *' for every 6 hours) or simple interval "
                                "(e.g., 'every 6h', 'every 30m'). All times are UTC."
                            ),
                        },
                        "deliver_to": {
                            "type": "string",
                            "enum": ["memory", "telegram", "both"],
                            "description": "Where to deliver results (default: 'memory').",
                        },
                        "telegram_chat_id": {
                            "type": "integer",
                            "description": (
                                "Telegram chat ID for delivery "
                                "(required when deliver_to is 'telegram' or 'both')."
                            ),
                        },
                    },
                    "required": ["action"],
                },
            },
        }

    def execute(self, **kwargs: Any) -> str:
        """Execute a scheduler action. Returns JSON string with results or error."""
        action = kwargs.get("action")

        try:
            if action == "create":
                return self._create_action(kwargs)
            elif action == "list":
                return self._list_action()
            elif action == "delete":
                return self._delete_action(kwargs)
            elif action == "enable":
                return self._toggle_action(kwargs, enabled=True)
            elif action == "disable":
                return self._toggle_action(kwargs, enabled=False)
            else:
                return json.dumps({"error": f"Unknown action: {action}"})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def _create_action(self, kwargs: dict) -> str:
        name = kwargs.get("name")
        prompt = kwargs.get("prompt")
        schedule = kwargs.get("schedule")

        if not all([name, prompt, schedule]):
            return json.dumps({
                "error": "name, prompt, and schedule are required for 'create' action"
            })

        deliver_to = kwargs.get("deliver_to", "memory")
        telegram_chat_id = kwargs.get("telegram_chat_id")

        task_id = self._store.add(
            name=name,
            prompt=prompt,
            cron_expression=schedule,
            deliver_to=deliver_to,
            telegram_chat_id=telegram_chat_id,
        )

        task = self._store.get(name)
        return json.dumps({
            "created": True,
            "task_id": task_id,
            "next_run_at": task["next_run_at"] if task else None,
            "total_tasks": self._store.count(),
        })

    def _list_action(self) -> str:
        tasks = self._store.list_all()
        return json.dumps({
            "tasks": tasks,
            "count": len(tasks),
        }, ensure_ascii=False)

    def _delete_action(self, kwargs: dict) -> str:
        name = kwargs.get("name")
        if not name:
            return json.dumps({"error": "name is required for 'delete' action"})
        deleted = self._store.delete(name)
        return json.dumps({"deleted": deleted, "name": name})

    def _toggle_action(self, kwargs: dict, enabled: bool) -> str:
        name = kwargs.get("name")
        if not name:
            action = "enable" if enabled else "disable"
            return json.dumps({"error": f"name is required for '{action}' action"})
        toggled = self._store.toggle(name, enabled=enabled)
        return json.dumps({
            "toggled": toggled,
            "name": name,
            "enabled": enabled,
        })
