"""Codex tool: delegate coding tasks to OpenAI's Codex CLI."""

import json
import subprocess
from typing import Any

from src.tools.base import Tool


class CodexTool(Tool):
    """Delegate coding tasks to Codex CLI.

    Requires Codex CLI to be installed and authenticated:
        npm install -g @openai/codex
        codex login              # desktop (opens browser)
        codex login --device-code  # headless server (shows code to enter elsewhere)
    """

    def __init__(
        self,
        timeout: int = 300,
        max_output: int = 50_000,
    ) -> None:
        self._timeout = timeout
        self._max_output = max_output

    @property
    def name(self) -> str:
        return "codex"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "codex",
                "description": (
                    "Delegate a coding task to Codex. Use this for "
                    "complex coding tasks: writing, editing, refactoring, "
                    "or debugging code. Codex can autonomously read "
                    "files, write files, and run commands to complete the task."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": (
                                "The coding task or instruction for Codex."
                            ),
                        },
                        "cwd": {
                            "type": "string",
                            "description": (
                                "Working directory for Codex "
                                "(default: current directory)."
                            ),
                        },
                    },
                    "required": ["prompt"],
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
        """Execute a coding task via Codex CLI."""
        prompt = kwargs.get("prompt")
        if not prompt:
            return json.dumps({"error": "Missing required parameter: prompt"})

        cmd = ["codex", "exec", "--json", "-"]
        cwd = kwargs.get("cwd") or None

        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                cwd=cwd,
            )

            stdout = result.stdout.strip()

            # codex exec --json outputs one JSON event per line.
            # The last event with type "message" contains the final result.
            lines = stdout.split("\n") if stdout else []
            final_message = None
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    if event.get("type") == "message":
                        final_message = event
                        break
                except (json.JSONDecodeError, TypeError):
                    continue

            if final_message:
                return json.dumps({
                    "result": self._truncate(
                        final_message.get("content", "")
                    ),
                })

            # Fallback: return raw output if no structured message found
            return json.dumps({
                "result": self._truncate(stdout or result.stderr),
            })

        except FileNotFoundError:
            return json.dumps({
                "error": (
                    "codex CLI not found. "
                    "Install with: npm install -g @openai/codex"
                )
            })
        except subprocess.TimeoutExpired:
            return json.dumps({
                "error": f"Codex timed out after {self._timeout}s"
            })
        except Exception as exc:
            return json.dumps({"error": str(exc)})
