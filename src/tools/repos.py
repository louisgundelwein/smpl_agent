"""Repos tool for managing known repositories."""

import json
from typing import Any

from src.repos import RepoStore
from src.tools.base import Tool


class ReposTool(Tool):
    """Tool that gives the LLM access to the repository registry.

    Supports actions: add, list, remove, get, update.
    """

    def __init__(self, store: RepoStore) -> None:
        self._store = store

    @property
    def name(self) -> str:
        return "repos"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Manage the list of repositories this agent is aware of. "
                    "Use this to add new repos, list known repos, remove repos, "
                    "or get details about a specific repo. When doing coding tasks, "
                    "check this list first to find the right repo URL and details."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["add", "list", "remove", "get", "update"],
                            "description": (
                                "'add' to register a new repo, "
                                "'list' to show all known repos, "
                                "'remove' to unregister a repo, "
                                "'get' to get details of a specific repo, "
                                "'update' to change repo metadata."
                            ),
                        },
                        "name": {
                            "type": "string",
                            "description": "Short unique name for the repo (e.g., 'smpl_agent').",
                        },
                        "owner": {
                            "type": "string",
                            "description": "GitHub owner/org (required for 'add').",
                        },
                        "repo": {
                            "type": "string",
                            "description": "GitHub repo name (required for 'add').",
                        },
                        "url": {
                            "type": "string",
                            "description": "Full clone URL (required for 'add').",
                        },
                        "default_branch": {
                            "type": "string",
                            "description": "Default branch name (default: 'main').",
                        },
                        "description": {
                            "type": "string",
                            "description": "Short description of the repo.",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Tags for categorization.",
                        },
                    },
                    "required": ["action"],
                },
            },
        }

    def execute(self, **kwargs: Any) -> str:
        """Execute a repos action. Returns JSON string with results or error."""
        action = kwargs.get("action")

        try:
            if action == "add":
                return self._add_action(kwargs)
            elif action == "list":
                return self._list_action()
            elif action == "remove":
                return self._remove_action(kwargs)
            elif action == "get":
                return self._get_action(kwargs)
            elif action == "update":
                return self._update_action(kwargs)
            else:
                return json.dumps({"error": f"Unknown action: {action}"})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def _add_action(self, kwargs: dict) -> str:
        name = kwargs.get("name")
        owner = kwargs.get("owner")
        repo = kwargs.get("repo")
        url = kwargs.get("url")

        if not all([name, owner, repo, url]):
            return json.dumps({
                "error": "name, owner, repo, and url are required for 'add' action"
            })

        repo_id = self._store.add(
            name=name,
            owner=owner,
            repo=repo,
            url=url,
            default_branch=kwargs.get("default_branch", "main"),
            description=kwargs.get("description", ""),
            tags=kwargs.get("tags"),
        )
        return json.dumps({
            "added": True,
            "repo_id": repo_id,
            "total_repos": self._store.count(),
        })

    def _list_action(self) -> str:
        repos = self._store.list_all()
        return json.dumps({
            "repos": repos,
            "count": len(repos),
        }, ensure_ascii=False)

    def _remove_action(self, kwargs: dict) -> str:
        name = kwargs.get("name")
        if not name:
            return json.dumps({"error": "name is required for 'remove' action"})
        removed = self._store.remove(name)
        return json.dumps({"removed": removed, "name": name})

    def _get_action(self, kwargs: dict) -> str:
        name = kwargs.get("name")
        if not name:
            return json.dumps({"error": "name is required for 'get' action"})
        repo = self._store.get(name)
        if repo is None:
            return json.dumps({"error": f"Repo '{name}' not found"})
        return json.dumps({"repo": repo}, ensure_ascii=False)

    def _update_action(self, kwargs: dict) -> str:
        name = kwargs.get("name")
        if not name:
            return json.dumps({"error": "name is required for 'update' action"})

        fields = {}
        for key in ("description", "default_branch", "tags"):
            if key in kwargs:
                fields[key] = kwargs[key]

        if not fields:
            return json.dumps({"error": "No fields to update"})

        updated = self._store.update(name, **fields)
        return json.dumps({"updated": updated, "name": name})
