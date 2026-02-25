"""JSON-lines protocol for client-server communication."""

import json
from typing import Any


def encode(msg: dict[str, Any]) -> bytes:
    """Encode a message dict to JSON-line bytes (with trailing newline)."""
    return (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")


def decode(line: bytes) -> dict[str, Any]:
    """Decode a single JSON-line bytes to a message dict.

    Raises:
        json.JSONDecodeError: If the line is not valid JSON.
        ValueError: If the decoded value is not a dict.
    """
    text = line.decode("utf-8").strip()
    if not text:
        raise ValueError("Empty line")
    obj = json.loads(text)
    if not isinstance(obj, dict):
        raise ValueError(f"Expected JSON object, got {type(obj).__name__}")
    if "type" not in obj:
        raise ValueError("Message missing required 'type' field")
    return obj


class LineBuffer:
    """Accumulates bytes and yields complete newline-terminated lines.

    Handles the case where a TCP recv() returns a partial line,
    multiple lines, or a mix.
    """

    def __init__(self) -> None:
        self._buffer = b""

    def feed(self, data: bytes) -> list[bytes]:
        """Feed raw bytes and return any complete lines."""
        self._buffer += data
        lines = []
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            if line:
                lines.append(line)
        return lines
