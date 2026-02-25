"""TCP server that wraps the Agent and handles client connections."""

import json
import logging
import socket
import threading
from typing import Any

from src.agent import Agent
from src.events import (
    AgentEvent,
    ContextCompressedEvent,
    LLMEndEvent,
    LLMStartEvent,
    SubagentSpawnedEvent,
    SubagentStatusEvent,
    ToolEndEvent,
    ToolErrorEvent,
    ToolStartEvent,
)
from src.protocol import LineBuffer, decode, encode

logger = logging.getLogger(__name__)


def _event_to_message(event: AgentEvent) -> dict[str, Any]:
    """Convert an AgentEvent to a protocol message dict."""
    if isinstance(event, LLMStartEvent):
        return {
            "type": "llm_start",
            "round_number": event.round_number,
            "message_count": event.message_count,
            "estimated_tokens": event.estimated_tokens,
        }
    elif isinstance(event, LLMEndEvent):
        return {
            "type": "llm_end",
            "round_number": event.round_number,
            "has_tool_calls": event.has_tool_calls,
            "duration_ms": event.duration_ms,
        }
    elif isinstance(event, ToolStartEvent):
        return {
            "type": "tool_start",
            "tool_name": event.tool_name,
            "arguments": event.arguments,
        }
    elif isinstance(event, ToolEndEvent):
        return {
            "type": "tool_end",
            "tool_name": event.tool_name,
            "duration_ms": event.duration_ms,
        }
    elif isinstance(event, ToolErrorEvent):
        return {
            "type": "tool_error",
            "tool_name": event.tool_name,
            "error": event.error,
            "duration_ms": event.duration_ms,
        }
    elif isinstance(event, ContextCompressedEvent):
        return {
            "type": "context_compressed",
            "original_tokens": event.original_tokens,
            "compressed_tokens": event.compressed_tokens,
            "messages_removed": event.messages_removed,
        }
    elif isinstance(event, SubagentSpawnedEvent):
        return {
            "type": "subagent_spawned",
            "subagent_id": event.subagent_id,
            "task": event.task,
        }
    elif isinstance(event, SubagentStatusEvent):
        return {
            "type": "subagent_status",
            "subagent_id": event.subagent_id,
            "task": event.task,
            "status": event.status,
            "error": event.error,
        }
    # Defensive: log unknown event types instead of crashing
    logger.warning("Unknown event type: %s", type(event).__name__)
    return {"type": "unknown", "event_type": type(event).__name__}


class AgentServer:
    """TCP server managing a single Agent instance.

    Accepts one client at a time. The agent persists across
    client connections (detach/reattach preserves conversation).
    """

    def __init__(
        self,
        agent: Agent,
        host: str = "127.0.0.1",
        port: int = 7600,
        telegram_bot: Any = None,
        scheduler: Any = None,
    ) -> None:
        self._agent = agent
        self._host = host
        self._port = port
        self._telegram_bot = telegram_bot
        self._scheduler = scheduler
        self._server_socket: socket.socket | None = None
        self._running = False
        self._client_socket: socket.socket | None = None
        self._client_lock = threading.Lock()
        self._agent_lock = threading.Lock()

    @property
    def port(self) -> int:
        """Actual port (useful when started with port=0)."""
        if self._server_socket:
            return self._server_socket.getsockname()[1]
        return self._port

    @property
    def agent_lock(self) -> threading.Lock:
        """Lock for serializing agent.run() calls."""
        return self._agent_lock

    def _send_to_client(self, msg: dict[str, Any]) -> None:
        """Send a message to the connected client."""
        with self._client_lock:
            sock = self._client_socket
        if sock is None:
            return
        try:
            sock.sendall(encode(msg))
        except OSError:
            pass

    def _on_agent_event(self, event: AgentEvent) -> None:
        """Event callback: forward agent events to the connected client."""
        self._send_to_client(_event_to_message(event))

    def _handle_client(
        self, client_socket: socket.socket, addr: tuple[str, int]
    ) -> None:
        """Handle a single client connection."""
        logger.info("Client connected from %s:%d", addr[0], addr[1])
        buffer = LineBuffer()

        with self._client_lock:
            self._client_socket = client_socket

        try:
            while self._running:
                try:
                    data = client_socket.recv(4096)
                except OSError:
                    break
                if not data:
                    break

                for line in buffer.feed(data):
                    try:
                        msg = decode(line)
                    except (json.JSONDecodeError, ValueError) as exc:
                        self._send_to_client(
                            {"type": "error", "content": f"Bad message: {exc}"}
                        )
                        continue
                    self._dispatch(msg)
        finally:
            logger.info("Client disconnected from %s:%d", addr[0], addr[1])
            with self._client_lock:
                self._client_socket = None
            try:
                client_socket.close()
            except OSError:
                pass

    def _dispatch(self, msg: dict[str, Any]) -> None:
        """Route an incoming client message."""
        msg_type = msg.get("type")

        if msg_type == "ping":
            self._send_to_client({"type": "pong"})

        elif msg_type == "reset":
            self._agent.reset()
            self._send_to_client({"type": "reset_ack"})

        elif msg_type == "run":
            content = msg.get("content", "")
            if not content.strip():
                return

            if not self._agent_lock.acquire(blocking=False):
                self._send_to_client(
                    {"type": "busy", "content": "Agent is busy with another request."}
                )
                return

            try:
                response = self._agent.run(content)
                self._send_to_client({"type": "response", "content": response})
            except Exception as exc:
                self._send_to_client({"type": "error", "content": str(exc)})
            finally:
                self._agent_lock.release()

        else:
            self._send_to_client(
                {"type": "error", "content": f"Unknown message type: {msg_type}"}
            )

    def serve_forever(self) -> None:
        """Start listening and accept clients in a loop."""
        self._agent.emitter.on(self._on_agent_event)

        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._server_socket.bind((self._host, self._port))
        except OSError as exc:
            self._server_socket.close()
            raise RuntimeError(
                f"Cannot bind to {self._host}:{self._port}: {exc}. "
                f"Is another agent already running? Check with: lsof -i :{self._port}"
            ) from exc
        self._server_socket.listen(1)
        self._server_socket.settimeout(1.0)
        self._running = True

        actual_port = self._server_socket.getsockname()[1]
        print(f"Agent server listening on {self._host}:{actual_port}")

        # Start Telegram bot if configured
        if self._telegram_bot:
            telegram_thread = threading.Thread(
                target=self._telegram_bot.poll_loop,
                args=(self._agent, self._agent_lock),
                daemon=True,
            )
            telegram_thread.start()
            print("Telegram bot started.")

        # Start scheduler if configured
        if self._scheduler:
            scheduler_thread = threading.Thread(
                target=self._scheduler.poll_loop,
                args=(self._agent, self._agent_lock),
                daemon=True,
            )
            scheduler_thread.start()
            print("Scheduler started.")

        print("Press Ctrl+C to stop.")

        try:
            while self._running:
                try:
                    client_socket, addr = self._server_socket.accept()
                except socket.timeout:
                    continue

                with self._client_lock:
                    if self._client_socket is not None:
                        try:
                            client_socket.sendall(
                                encode(
                                    {
                                        "type": "busy",
                                        "content": "Another client is connected.",
                                    }
                                )
                            )
                            client_socket.close()
                        except OSError:
                            pass
                        continue

                thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, addr),
                    daemon=True,
                )
                thread.start()

        except KeyboardInterrupt:
            logger.info("Server shutting down.")
        finally:
            self._running = False
            self._agent.emitter.off(self._on_agent_event)
            if self._server_socket:
                self._server_socket.close()

    def shutdown(self) -> None:
        """Signal the server to stop."""
        self._running = False
