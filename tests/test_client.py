"""Tests for src.client display formatting."""

import pytest

from src.client import AgentClient


@pytest.fixture
def client():
    return AgentClient(host="127.0.0.1", port=0)


def test_display_response(client, capsys):
    client._display({"type": "response", "content": "Hello!"})
    out = capsys.readouterr().out
    assert "Agent: Hello!" in out


def test_display_tool_start(client, capsys):
    client._display({
        "type": "tool_start",
        "tool_name": "brave_web_search",
        "arguments": {"query": "python"},
    })
    out = capsys.readouterr().out
    assert "[tool] brave_web_search" in out
    assert "query='python'" in out


def test_display_tool_end(client, capsys):
    client._display({"type": "tool_end", "tool_name": "brave_web_search", "duration_ms": 245})
    out = capsys.readouterr().out
    assert "[tool] done" in out
    assert "245ms" in out


def test_display_tool_error(client, capsys):
    client._display({
        "type": "tool_error",
        "tool_name": "brave_web_search",
        "error": "timeout",
        "duration_ms": 30000,
    })
    out = capsys.readouterr().out
    assert "[tool] error: timeout" in out
    assert "30000ms" in out


def test_display_error(client, capsys):
    client._display({"type": "error", "content": "Bad message"})
    err = capsys.readouterr().err
    assert "Error: Bad message" in err


def test_display_reset_ack(client, capsys):
    client._display({"type": "reset_ack"})
    out = capsys.readouterr().out
    assert "Conversation reset" in out


def test_display_busy(client, capsys):
    client._display({"type": "busy", "content": "Agent is busy"})
    out = capsys.readouterr().out
    assert "Busy: Agent is busy" in out


def test_display_pong_silent(client, capsys):
    client._display({"type": "pong"})
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_display_llm_start(client, capsys):
    client._display({
        "type": "llm_start",
        "round_number": 1,
        "message_count": 3,
        "estimated_tokens": 500,
    })
    out = capsys.readouterr().out
    assert "[llm] round 1" in out
    assert "3 messages" in out
    assert "~500 tokens" in out


def test_display_llm_end(client, capsys):
    client._display({
        "type": "llm_end",
        "round_number": 1,
        "has_tool_calls": True,
        "duration_ms": 1843,
    })
    out = capsys.readouterr().out
    assert "[llm] done" in out
    assert "tool calls" in out
    assert "1843ms" in out


def test_display_context_compressed(client, capsys):
    client._display({
        "type": "context_compressed",
        "original_tokens": 95000,
        "compressed_tokens": 12000,
        "messages_removed": 24,
    })
    out = capsys.readouterr().out
    assert "[context] compressed" in out
    assert "24 messages removed" in out
