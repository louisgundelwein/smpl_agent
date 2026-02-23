"""Brave Web Search API tool."""

import json
import time
from typing import Any

import httpx

from src.tools.base import Tool


class BraveSearchTool(Tool):
    """Web search using the Brave Search API.

    Enforces a 1-second minimum interval between requests.
    """

    ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
    COOLDOWN_SECONDS = 1.0

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._last_request_time: float = 0.0

    @property
    def name(self) -> str:
        return "brave_web_search"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Search the web using Brave Search. Returns titles, URLs, "
                    "and descriptions of the top results. Use this when you need "
                    "current information from the internet."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query string.",
                        },
                        "count": {
                            "type": "integer",
                            "description": "Number of results to return (1-20, default 5).",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    def _enforce_cooldown(self) -> None:
        """Sleep if needed to respect the rate limit."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.COOLDOWN_SECONDS:
            time.sleep(self.COOLDOWN_SECONDS - elapsed)

    def execute(self, **kwargs: Any) -> str:
        """Execute a Brave web search.

        Args:
            query: The search query.
            count: Number of results (default 5).
        """
        query = kwargs["query"]
        count = kwargs.get("count", 5)

        self._enforce_cooldown()

        response = httpx.get(
            self.ENDPOINT,
            params={"q": query, "count": count},
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": self._api_key,
            },
            timeout=10.0,
        )
        self._last_request_time = time.monotonic()

        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("web", {}).get("results", []):
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "description": item.get("description", ""),
                }
            )

        if not results:
            return json.dumps({"message": "No results found.", "results": []})

        return json.dumps({"results": results}, ensure_ascii=False)
