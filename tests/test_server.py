"""Tests for src.server using real loopback sockets."""

import json
import socket
import threading
import time

import pytest

from src.agent import Agent
from src.events import (
    ContextCompressedEvent,
    EventEmitter,
    ToolEndEvent,
    ToolStartEvent,
)
from src.protocol import LineBuffer, decode, encode
from src.server import AgentServer
from src.tools.base import Tool
from src.tools.registry import ToolRegistry


class EchoTool(Tool):
    """Tool that returns its input — for triggering tool events."""

    @property
    def name(self) -> str:
        return "echo"

    @property
    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "echo",
                "description": "Echo",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            },
        }

    def execute(self, **kwargs) -> str:
        return kwargs.get("text", "")


class FakeLLM:
    """Fake LLM that returns canned responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self._call_index = 0

    def chat(self, messages, tools=None):
        resp = self._responses[self._call_index]
        self._call_index = min(self._call_index + 1, len(self._responses) - 1)
        return resp


def _make_chat_response(content, tool_calls=None):
    """Build a minimal fake ChatCompletion-like object."""

    class _Function:
        def __init__(self, name, arguments):
            self.name = name
            self.arguments = arguments

    class _ToolCall:
        def __init__(self, tc_id, function):
            self.id = tc_id
            self.function = function

    class _Message:
        def __init__(self, content, tool_calls):
            self.content = content
            self.tool_calls = tool_calls

        def model_dump(self):
            d = {"role": "assistant", "content": self.content}
            if self.tool_calls:
                d["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in self.tool_calls
                ]
            return d

    class _Choice:
        def __init__(self, message):
            self.message = message

    class _Response:
        def __init__(self, choices):
            self.choices = choices

    tcs = None
    if tool_calls:
        tcs = [
            _ToolCall(tc["id"], _Function(tc["name"], json.dumps(tc["args"])))
            for tc in tool_calls
        ]

    msg = _Message(content, tcs)
    return _Response([_Choice(msg)])


def _text_response(text):
    return _make_chat_response(text)


def _tool_then_text(tool_name, tool_args, tool_id, final_text):
    """Two-step: first response triggers a tool call, second returns text."""
    return [
        _make_chat_response(
            None,
            tool_calls=[{"id": tool_id, "name": tool_name, "args": tool_args}],
        ),
        _make_chat_response(final_text),
    ]


def _start_server(agent, port=0, telegram_bot=None):
    """Create and start a server in a daemon thread; returns (server, port)."""
    server = AgentServer(agent, host="127.0.0.1", port=port, telegram_bot=telegram_bot)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    # Wait for the server to bind
    for _ in range(50):
        if server._server_socket and server._running:
            break
        time.sleep(0.05)
    return server


def _connect(port):
    """Open a TCP connection to the server and return the socket."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", port))
    sock.settimeout(5.0)
    return sock


def _send(sock, msg):
    sock.sendall(encode(msg))


def _recv_all(sock, timeout=2.0):
    """Receive all messages until timeout or connection closes."""
    buf = LineBuffer()
    messages = []
    sock.settimeout(timeout)
    try:
        while True:
            data = sock.recv(4096)
            if not data:
                break
            for line in buf.feed(data):
                messages.append(decode(line))
    except socket.timeout:
        pass
    return messages


def _recv_one(sock, timeout=5.0):
    """Receive exactly one message."""
    buf = LineBuffer()
    sock.settimeout(timeout)
    while True:
        data = sock.recv(4096)
        if not data:
            raise ConnectionError("Socket closed before message received")
        for line in buf.feed(data):
            return decode(line)


# --- Tests ---


def test_ping_pong():
    llm = FakeLLM([_text_response("hi")])
    registry = ToolRegistry()
    agent = Agent(llm=llm, registry=registry)
    server = _start_server(agent)

    sock = _connect(server.port)
    try:
        _send(sock, {"type": "ping"})
        msg = _recv_one(sock)
        assert msg == {"type": "pong"}
    finally:
        sock.close()
        server.shutdown()


def test_run_and_response():
    llm = FakeLLM([_text_response("Hello back!")])
    registry = ToolRegistry()
    agent = Agent(llm=llm, registry=registry)
    server = _start_server(agent)

    sock = _connect(server.port)
    try:
        _send(sock, {"type": "run", "content": "Hello"})
        messages = _recv_all(sock, timeout=3.0)
        response = next(m for m in messages if m["type"] == "response")
        assert response["content"] == "Hello back!"
    finally:
        sock.close()
        server.shutdown()


def test_tool_events_forwarded():
    responses = _tool_then_text("echo", {"text": "hi"}, "call_1", "Done!")
    llm = FakeLLM(responses)
    registry = ToolRegistry()
    registry.register(EchoTool())
    agent = Agent(llm=llm, registry=registry)
    server = _start_server(agent)

    sock = _connect(server.port)
    try:
        _send(sock, {"type": "run", "content": "echo something"})
        messages = _recv_all(sock, timeout=3.0)

        types = [m["type"] for m in messages]
        assert "llm_start" in types
        assert "llm_end" in types
        assert "tool_start" in types
        assert "tool_end" in types
        assert "response" in types

        tool_start = next(m for m in messages if m["type"] == "tool_start")
        assert tool_start["tool_name"] == "echo"
        assert tool_start["arguments"] == {"text": "hi"}

        tool_end = next(m for m in messages if m["type"] == "tool_end")
        assert "duration_ms" in tool_end

        llm_start = next(m for m in messages if m["type"] == "llm_start")
        assert llm_start["round_number"] == 1
        assert "message_count" in llm_start
        assert "estimated_tokens" in llm_start
    finally:
        sock.close()
        server.shutdown()


def test_reset():
    llm = FakeLLM([_text_response("first"), _text_response("second")])
    registry = ToolRegistry()
    agent = Agent(llm=llm, registry=registry)
    server = _start_server(agent)

    sock = _connect(server.port)
    try:
        _send(sock, {"type": "run", "content": "hi"})
        # Consume all messages from the run (llm_start, llm_end, response)
        messages = _recv_all(sock, timeout=2.0)
        assert any(m["type"] == "response" for m in messages)

        assert len(agent.messages) > 1  # system + user + assistant

        _send(sock, {"type": "reset"})
        msg = _recv_one(sock)
        assert msg == {"type": "reset_ack"}
        assert len(agent.messages) == 1  # only system prompt
    finally:
        sock.close()
        server.shutdown()


def test_client_disconnect_preserves_agent():
    llm = FakeLLM([_text_response("first"), _text_response("second")])
    registry = ToolRegistry()
    agent = Agent(llm=llm, registry=registry)
    server = _start_server(agent)

    # First connection — send a message
    sock1 = _connect(server.port)
    _send(sock1, {"type": "run", "content": "hello"})
    _recv_all(sock1, timeout=2.0)  # consume all messages
    sock1.close()
    time.sleep(0.3)  # let server detect disconnect

    # Conversation should still have the exchange
    assert len(agent.messages) >= 3  # system + user + assistant

    # Second connection — agent still works
    sock2 = _connect(server.port)
    try:
        _send(sock2, {"type": "run", "content": "follow up"})
        messages = _recv_all(sock2, timeout=3.0)
        assert any(m["type"] == "response" for m in messages)
    finally:
        sock2.close()
        server.shutdown()


def test_second_client_gets_busy():
    llm = FakeLLM([_text_response("hi")])
    registry = ToolRegistry()
    agent = Agent(llm=llm, registry=registry)
    server = _start_server(agent)

    sock1 = _connect(server.port)
    time.sleep(0.3)  # let server register client

    sock2 = _connect(server.port)
    try:
        msg = _recv_one(sock2, timeout=3.0)
        assert msg["type"] == "busy"
    finally:
        sock1.close()
        sock2.close()
        server.shutdown()


def test_unknown_message_type():
    llm = FakeLLM([_text_response("hi")])
    registry = ToolRegistry()
    agent = Agent(llm=llm, registry=registry)
    server = _start_server(agent)

    sock = _connect(server.port)
    try:
        _send(sock, {"type": "unknown_type"})
        msg = _recv_one(sock)
        assert msg["type"] == "error"
        assert "Unknown message type" in msg["content"]
    finally:
        sock.close()
        server.shutdown()


def test_empty_run_ignored():
    llm = FakeLLM([_text_response("hi")])
    registry = ToolRegistry()
    agent = Agent(llm=llm, registry=registry)
    server = _start_server(agent)

    sock = _connect(server.port)
    try:
        _send(sock, {"type": "run", "content": "   "})
        # Should not get a response — send a ping to verify server is still alive
        _send(sock, {"type": "ping"})
        msg = _recv_one(sock)
        assert msg == {"type": "pong"}
    finally:
        sock.close()
        server.shutdown()


def test_context_compressed_event_forwarded():
    """ContextCompressedEvent should be forwarded instead of crashing."""
    from src.server import _event_to_message

    event = ContextCompressedEvent(
        original_tokens=95000,
        compressed_tokens=12000,
        messages_removed=24,
    )
    msg = _event_to_message(event)

    assert msg["type"] == "context_compressed"
    assert msg["original_tokens"] == 95000
    assert msg["compressed_tokens"] == 12000
    assert msg["messages_removed"] == 24


def test_unknown_event_does_not_crash():
    """Unknown event types should not crash the server."""
    from dataclasses import dataclass

    from src.server import _event_to_message

    @dataclass(frozen=True)
    class FutureEvent:
        data: str

    msg = _event_to_message(FutureEvent(data="test"))

    assert msg["type"] == "unknown"
    assert msg["event_type"] == "FutureEvent"
