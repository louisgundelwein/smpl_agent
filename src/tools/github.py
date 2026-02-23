"""GitHub tool: interact with the GitHub REST API."""

import json
from typing import Any

import httpx

from src.tools.base import Tool


class GitHubTool(Tool):
    """Generic GitHub REST API wrapper.

    Allows the agent to call any GitHub API endpoint using a personal
    access token for authentication.
    """

    BASE_URL = "https://api.github.com"

    def __init__(
        self,
        token: str,
        max_output: int = 50_000,
    ) -> None:
        self._token = token
        self._max_output = max_output

    @property
    def name(self) -> str:
        return "github"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "github",
                "description": (
                    "Interact with the GitHub REST API. Use this to manage "
                    "repositories, issues, pull requests, files, and more. "
                    "Provide the HTTP method and API endpoint path."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {
                            "type": "string",
                            "enum": [
                                "GET",
                                "POST",
                                "PUT",
                                "PATCH",
                                "DELETE",
                            ],
                            "description": "HTTP method.",
                        },
                        "endpoint": {
                            "type": "string",
                            "description": (
                                "API endpoint path, e.g. "
                                "/repos/{owner}/{repo}/issues. "
                                "Will be appended to "
                                "https://api.github.com"
                            ),
                        },
                        "body": {
                            "type": "object",
                            "description": (
                                "Request body for POST/PUT/PATCH requests "
                                "(optional)."
                            ),
                        },
                        "params": {
                            "type": "object",
                            "description": (
                                "Query parameters (optional)."
                            ),
                        },
                    },
                    "required": ["method", "endpoint"],
                },
            },
        }

    def _truncate(self, text: str) -> str:
        """Truncate text if it exceeds max_output, keeping start and end."""
        if len(text) <= self._max_output:
            return text

        notice = f"\n\n--- TRUNCATED ({len(text)} chars total) ---\n\n"
        head_size = 1000
        tail_size = self._max_output - head_size - len(notice)

        if tail_size < 0:
            return text[: self._max_output]

        return text[:head_size] + notice + text[-tail_size:]

    def execute(self, **kwargs: Any) -> str:
        """Execute a GitHub API request."""
        method = kwargs.get("method")
        if not method:
            return json.dumps({"error": "Missing required parameter: method"})

        endpoint = kwargs.get("endpoint")
        if not endpoint:
            return json.dumps(
                {"error": "Missing required parameter: endpoint"}
            )

        url = self.BASE_URL + endpoint
        body = kwargs.get("body")
        params = kwargs.get("params")

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        try:
            response = httpx.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=body if body else None,
                timeout=30.0,
            )
            response.raise_for_status()

            # Some endpoints return 204 No Content
            if response.status_code == 204:
                return json.dumps({
                    "status_code": 204,
                    "body": None,
                })

            result_text = json.dumps(
                response.json(), ensure_ascii=False,
            )
            return json.dumps({
                "status_code": response.status_code,
                "body": self._truncate(result_text),
            }, ensure_ascii=False)

        except httpx.HTTPStatusError as exc:
            error_body = exc.response.text
            return json.dumps({
                "error": f"HTTP {exc.response.status_code}",
                "status_code": exc.response.status_code,
                "body": self._truncate(error_body),
            })
        except httpx.TimeoutException:
            return json.dumps({"error": "Request timed out"})
        except Exception as exc:
            return json.dumps({"error": str(exc)})
