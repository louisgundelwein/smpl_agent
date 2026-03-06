"""GitHub tool: interact with the GitHub REST API."""

import json
import re
import time
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

    def _parse_link_header(self, link_header: str) -> dict[str, str]:
        """Parse Link header (RFC 5988) to extract next/last/first/prev URLs."""
        links = {}
        if not link_header:
            return links
        for part in link_header.split(","):
            section = part.split(";")
            if len(section) == 2:
                url = section[0].strip()[1:-1]  # Remove < and >
                rel = section[1].split("=")[1].strip('"')
                links[rel] = url
        return links

    def _should_retry(self, status_code: int) -> bool:
        """Check if request should be retried."""
        return status_code == 429

    def _wait_before_retry(self, response: httpx.Response) -> None:
        """Wait before retrying based on Retry-After header or exponential backoff."""
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                wait_time = int(retry_after)
            except ValueError:
                wait_time = 2  # Default fallback
        else:
            wait_time = 2
        time.sleep(wait_time)

    def execute(self, **kwargs: Any) -> str:
        """Execute a GitHub API request with retry and pagination support."""
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

        # Exponential backoff retry loop (3 attempts, 1s initial delay)
        max_attempts = 3
        attempt = 0
        wait_time = 1

        while attempt < max_attempts:
            try:
                response = httpx.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=body if body else None,
                    timeout=30.0,
                )

                # Check for rate limit and retry if needed
                if self._should_retry(response.status_code):
                    if attempt < max_attempts - 1:
                        self._wait_before_retry(response)
                        attempt += 1
                        continue
                    else:
                        return json.dumps({
                            "error": "Rate limited (429)",
                            "status_code": 429,
                        })

                response.raise_for_status()

                # Some endpoints return 204 No Content
                if response.status_code == 204:
                    return json.dumps({
                        "status_code": 204,
                        "body": None,
                    })

                data = response.json()

                # Extract pagination info from Link header
                link_header = response.headers.get("Link", "")
                links = self._parse_link_header(link_header)
                pagination_info = {}
                if links:
                    pagination_info = {
                        "next": links.get("next"),
                        "last": links.get("last"),
                        "first": links.get("first"),
                        "prev": links.get("prev"),
                    }

                # Include rate limit info
                rate_limit_remaining = response.headers.get(
                    "X-RateLimit-Remaining"
                )

                result_text = json.dumps(data, ensure_ascii=False)
                truncated = self._truncate(result_text)
                # Avoid double-encoding: use parsed dict when not truncated
                body_out = data if truncated == result_text else truncated

                result = {
                    "status_code": response.status_code,
                    "body": body_out,
                }
                if pagination_info:
                    result["pagination"] = pagination_info
                if rate_limit_remaining:
                    result["rate_limit_remaining"] = int(
                        rate_limit_remaining
                    )

                return json.dumps(result, ensure_ascii=False)

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
