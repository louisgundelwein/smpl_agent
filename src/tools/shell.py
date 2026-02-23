"""Shell tool: execute arbitrary commands on the local machine."""

import json
import subprocess
from typing import Any

from src.tools.base import Tool


class ShellTool(Tool):
    """Execute shell commands on the local system."""

    def __init__(
        self,
        command_timeout: int = 30,
        max_output: int = 50_000,
    ) -> None:
        self._command_timeout = command_timeout
        self._max_output = max_output

    @property
    def name(self) -> str:
        return "shell"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "shell",
                "description": (
                    "Execute a shell command on the local machine. "
                    "Use commands appropriate for the OS described in the system prompt. "
                    "Use this for anything: running scripts, reading/writing "
                    "files, installing packages, inspecting the system, etc."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The shell command to execute.",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": (
                                "Timeout in seconds (default: "
                                f"{30})."
                            ),
                        },
                        "cwd": {
                            "type": "string",
                            "description": (
                                "Working directory for the command "
                                "(default: current directory)."
                            ),
                        },
                    },
                    "required": ["command"],
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
        """Execute a shell command and return the result as JSON."""
        command = kwargs.get("command")
        if not command:
            return json.dumps({"error": "Missing required parameter: command"})

        timeout = kwargs.get("timeout", self._command_timeout)
        cwd = kwargs.get("cwd") or None

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )
            return json.dumps({
                "exit_code": result.returncode,
                "stdout": self._truncate(result.stdout),
                "stderr": self._truncate(result.stderr),
            })
        except subprocess.TimeoutExpired as exc:
            return json.dumps({
                "error": f"Command timed out after {timeout}s",
                "stdout": self._truncate(exc.stdout or ""),
                "stderr": self._truncate(exc.stderr or ""),
            })
        except Exception as exc:
            return json.dumps({"error": str(exc)})
