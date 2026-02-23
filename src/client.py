"""TCP client that connects to a running AgentServer."""

import socket
import sys
import threading
from typing import Any

from src.formatting import format_message
from src.protocol import LineBuffer, decode, encode


class AgentClient:
    """CLI client for the agent daemon.

    Runs input in the main thread and receives messages
    in a background thread.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 7600) -> None:
        self._host = host
        self._port = port
        self._socket: socket.socket | None = None
        self._running = False

    def _display(self, msg: dict[str, Any]) -> None:
        """Format and print a server message."""
        msg_type = msg.get("type")

        # Error goes to stderr
        if msg_type == "error":
            print(f"\nError: {msg.get('content', '')}\n", file=sys.stderr)
            return

        # Pong is silent
        if msg_type == "pong":
            return

        line = format_message(msg)
        if line is not None:
            print(line)

    def _recv_loop(self) -> None:
        """Background thread: read messages from server."""
        buf = LineBuffer()
        try:
            while self._running and self._socket:
                try:
                    data = self._socket.recv(4096)
                except OSError:
                    break
                if not data:
                    break
                for line in buf.feed(data):
                    try:
                        msg = decode(line)
                    except Exception:
                        continue
                    self._display(msg)
        finally:
            if self._running:
                print("\nDisconnected from server.")
                self._running = False

    def repl(self) -> None:
        """Connect to the server and run an interactive REPL."""
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.connect((self._host, self._port))
        self._running = True

        recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        recv_thread.start()

        print(f"Connected to agent at {self._host}:{self._port}")
        print("Type 'quit' to detach, 'reset' to clear history.\n")

        try:
            while self._running:
                try:
                    user_input = input("You: ").strip()
                except (KeyboardInterrupt, EOFError):
                    break

                if not user_input:
                    continue
                if user_input.lower() in ("quit", "exit"):
                    break
                if user_input.lower() == "reset":
                    self._socket.sendall(encode({"type": "reset"}))
                    continue

                self._socket.sendall(encode({"type": "run", "content": user_input}))
        finally:
            self._running = False
            print("Detached.")
            try:
                self._socket.close()
            except OSError:
                pass
