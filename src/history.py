"""Conversation history persistence via JSON file."""

import json
import os
import tempfile
from typing import Any


class ConversationHistory:
    """Save and load conversation messages to/from a JSON file.

    Uses atomic writes (write-to-temp-then-replace) to prevent
    corruption from crashes or interrupts.
    """

    def __init__(self, file_path: str) -> None:
        self._path = file_path

    def save(self, messages: list[dict[str, Any]]) -> None:
        """Atomically write messages to disk as JSON.

        Creates parent directories if they don't exist.
        """
        dir_name = os.path.dirname(self._path) or "."
        os.makedirs(dir_name, exist_ok=True)
        data = json.dumps(messages, ensure_ascii=False, indent=2)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(tmp_path, self._path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def load(self) -> list[dict[str, Any]] | None:
        """Load messages from disk.

        Returns None if the file doesn't exist or is corrupt.
        """
        if not os.path.exists(self._path):
            return None
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(data, list) or not data:
            return None
        if not isinstance(data[0], dict) or data[0].get("role") != "system":
            return None
        return self._sanitize(data)

    def _sanitize(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove None values from messages.

        Some providers (e.g. Gemini) reject messages with ``content: null``.
        This strips those keys so persisted history stays compatible.
        """
        return [
            {k: v for k, v in msg.items() if v is not None}
            for msg in messages
        ]

    def clear(self) -> None:
        """Delete the history file if it exists."""
        try:
            os.unlink(self._path)
        except FileNotFoundError:
            pass
