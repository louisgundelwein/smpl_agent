"""Tests for src.formatting."""

from dataclasses import dataclass

from src.events import (
    ContextCompressedEvent,
    LLMEndEvent,
    LLMStartEvent,
    RunSummaryEvent,
    ToolEndEvent,
    ToolErrorEvent,
    ToolStartEvent,
)
from src.formatting import format_event, format_message


# --- format_event tests ---


def test_format_llm_start_event():
    event = LLMStartEvent(round_number=1, message_count=5, estimated_tokens=1200)
    result = format_event(event)
    assert "[llm] round 1" in result
    assert "5 messages" in result
    assert "~1200 tokens" in result


def test_format_llm_end_event_with_tool_calls():
    event = LLMEndEvent(round_number=1, has_tool_calls=True, duration_ms=1843, tool_call_count=3)
    result = format_event(event)
    assert "[llm] done" in result
    assert "3 tool calls" in result
    assert "1843ms" in result


def test_format_llm_end_event_single_tool_call():
    event = LLMEndEvent(round_number=1, has_tool_calls=True, duration_ms=500, tool_call_count=1)
    result = format_event(event)
    assert "1 tool call," in result


def test_format_llm_end_event_with_response():
    event = LLMEndEvent(round_number=2, has_tool_calls=False, duration_ms=2105)
    result = format_event(event)
    assert "[llm] done" in result
    assert "response" in result
    assert "2105ms" in result


def test_format_llm_end_event_with_response_preview():
    event = LLMEndEvent(
        round_number=1, has_tool_calls=False, duration_ms=800,
        response_preview="I'll help you with that task",
    )
    result = format_event(event)
    assert "response" in result
    assert '"I\'ll help you with that task"' in result


def test_format_tool_start_event():
    event = ToolStartEvent(tool_name="brave_web_search", arguments={"query": "python"})
    result = format_event(event)
    assert "[tool] brave_web_search" in result
    assert "query='python'" in result


def test_format_tool_end_event():
    event = ToolEndEvent(tool_name="shell", duration_ms=245)
    result = format_event(event)
    assert "[tool] done" in result
    assert "245ms" in result


def test_format_tool_end_event_with_result_preview():
    event = ToolEndEvent(tool_name="shell", duration_ms=100, result_preview='{"results": [1, 2, 3]}')
    result = format_event(event)
    assert "100ms" in result
    assert '→ {"results": [1, 2, 3]}' in result


def test_format_tool_error_event():
    event = ToolErrorEvent(tool_name="shell", error="timeout", duration_ms=30000)
    result = format_event(event)
    assert "[tool] error: timeout" in result
    assert "30000ms" in result


def test_format_context_compressed_event():
    event = ContextCompressedEvent(
        original_tokens=95000, compressed_tokens=12000, messages_removed=24
    )
    result = format_event(event)
    assert "[context] compressed" in result
    assert "24 messages removed" in result
    assert "~95000" in result
    assert "~12000" in result


def test_format_run_summary_event():
    event = RunSummaryEvent(total_rounds=3, tool_calls_made=5, continuations_used=1, total_duration_ms=4200)
    result = format_event(event)
    assert "[agent] done in 3 rounds" in result
    assert "5 tool calls" in result
    assert "1 continuations" in result
    assert "4200ms" in result


def test_format_run_summary_event_single_round():
    event = RunSummaryEvent(total_rounds=1, tool_calls_made=0, continuations_used=0, total_duration_ms=300)
    result = format_event(event)
    assert "1 round " in result


def test_format_unknown_event_returns_none():
    @dataclass(frozen=True)
    class UnknownEvent:
        data: str

    result = format_event(UnknownEvent(data="test"))
    assert result is None


# --- format_message tests ---


def test_format_message_llm_start():
    msg = {
        "type": "llm_start",
        "round_number": 1,
        "message_count": 3,
        "estimated_tokens": 500,
    }
    result = format_message(msg)
    assert "[llm] round 1" in result
    assert "3 messages" in result
    assert "~500 tokens" in result


def test_format_message_llm_end():
    msg = {
        "type": "llm_end",
        "round_number": 1,
        "has_tool_calls": False,
        "duration_ms": 2000,
    }
    result = format_message(msg)
    assert "[llm] done" in result
    assert "response" in result
    assert "2000ms" in result


def test_format_message_tool_start():
    msg = {
        "type": "tool_start",
        "tool_name": "brave_web_search",
        "arguments": {"query": "python"},
    }
    result = format_message(msg)
    assert "[tool] brave_web_search" in result
    assert "query='python'" in result


def test_format_message_tool_end():
    msg = {"type": "tool_end", "tool_name": "shell", "duration_ms": 120}
    result = format_message(msg)
    assert "[tool] done" in result
    assert "120ms" in result


def test_format_message_tool_error():
    msg = {
        "type": "tool_error",
        "tool_name": "shell",
        "error": "timeout",
        "duration_ms": 30000,
    }
    result = format_message(msg)
    assert "[tool] error: timeout" in result
    assert "30000ms" in result


def test_format_message_context_compressed():
    msg = {
        "type": "context_compressed",
        "original_tokens": 95000,
        "compressed_tokens": 12000,
        "messages_removed": 24,
    }
    result = format_message(msg)
    assert "[context] compressed" in result
    assert "24 messages removed" in result
    assert "~95000" in result
    assert "~12000" in result


def test_format_message_response():
    msg = {"type": "response", "content": "Hello there!"}
    result = format_message(msg)
    assert "Agent: Hello there!" in result


def test_format_message_reset_ack():
    msg = {"type": "reset_ack"}
    result = format_message(msg)
    assert "Conversation reset" in result


def test_format_message_busy():
    msg = {"type": "busy", "content": "Agent is busy"}
    result = format_message(msg)
    assert "Busy: Agent is busy" in result


def test_format_message_unknown_returns_none():
    msg = {"type": "some_unknown_type"}
    result = format_message(msg)
    assert result is None


# --- Subagent wait/results events ---


def test_format_subagent_wait_event():
    from src.events import SubagentWaitEvent

    event = SubagentWaitEvent(active_count=3)
    result = format_event(event)
    assert "[subagent] waiting for 3 subagent(s)" in result


def test_format_subagent_results_collected_event():
    from src.events import SubagentResultsCollectedEvent

    event = SubagentResultsCollectedEvent(count=2, duration_ms=5400)
    result = format_event(event)
    assert "[subagent] collected 2 result(s)" in result
    assert "5400ms" in result


def test_format_message_subagent_wait():
    msg = {"type": "subagent_wait", "active_count": 2}
    result = format_message(msg)
    assert "[subagent] waiting for 2 subagent(s)" in result


def test_format_message_subagent_results_collected():
    msg = {"type": "subagent_results_collected", "count": 3, "duration_ms": 1200}
    result = format_message(msg)
    assert "[subagent] collected 3 result(s)" in result
    assert "1200ms" in result


def test_format_message_llm_end_with_tool_count():
    msg = {
        "type": "llm_end",
        "round_number": 1,
        "has_tool_calls": True,
        "duration_ms": 500,
        "tool_call_count": 2,
    }
    result = format_message(msg)
    assert "2 tool calls" in result


def test_format_message_llm_end_with_response_preview():
    msg = {
        "type": "llm_end",
        "round_number": 1,
        "has_tool_calls": False,
        "duration_ms": 500,
        "response_preview": "I'll help you with that",
    }
    result = format_message(msg)
    assert '"I\'ll help you with that"' in result


def test_format_message_tool_end_with_result_preview():
    msg = {
        "type": "tool_end",
        "tool_name": "shell",
        "duration_ms": 100,
        "result_preview": '{"ok": true}',
    }
    result = format_message(msg)
    assert '→ {"ok": true}' in result


def test_format_message_run_summary():
    msg = {
        "type": "run_summary",
        "total_rounds": 3,
        "tool_calls_made": 5,
        "continuations_used": 0,
        "total_duration_ms": 4200,
    }
    result = format_message(msg)
    assert "[agent] done in 3 rounds" in result
    assert "5 tool calls" in result
    assert "0 continuations" in result
    assert "4200ms" in result
