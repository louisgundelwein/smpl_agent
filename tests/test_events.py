"""Tests for src.events."""

from src.events import (
    EventEmitter,
    LLMEndEvent,
    LLMStartEvent,
    ToolEndEvent,
    ToolErrorEvent,
    ToolStartEvent,
)


def test_emit_calls_listener():
    emitter = EventEmitter()
    received = []
    emitter.on(lambda e: received.append(e))

    event = ToolStartEvent(tool_name="search", arguments={"q": "test"})
    emitter.emit(event)

    assert received == [event]


def test_no_listeners_is_silent():
    emitter = EventEmitter()
    emitter.emit(ToolEndEvent(tool_name="search", duration_ms=0))  # should not raise


def test_off_removes_listener():
    emitter = EventEmitter()
    received = []
    cb = lambda e: received.append(e)
    emitter.on(cb)
    emitter.off(cb)

    emitter.emit(ToolEndEvent(tool_name="search", duration_ms=0))

    assert received == []


def test_multiple_listeners():
    emitter = EventEmitter()
    a, b = [], []
    emitter.on(lambda e: a.append(e))
    emitter.on(lambda e: b.append(e))

    event = ToolErrorEvent(tool_name="x", error="boom", duration_ms=50)
    emitter.emit(event)

    assert a == [event]
    assert b == [event]


def test_llm_start_event_fields():
    event = LLMStartEvent(round_number=1, message_count=5, estimated_tokens=1000)
    assert event.round_number == 1
    assert event.message_count == 5
    assert event.estimated_tokens == 1000


def test_llm_end_event_fields():
    event = LLMEndEvent(round_number=2, has_tool_calls=True, duration_ms=1500)
    assert event.round_number == 2
    assert event.has_tool_calls is True
    assert event.duration_ms == 1500


def test_tool_end_event_has_duration():
    event = ToolEndEvent(tool_name="shell", duration_ms=245)
    assert event.tool_name == "shell"
    assert event.duration_ms == 245


def test_tool_error_event_has_duration():
    event = ToolErrorEvent(tool_name="shell", error="timeout", duration_ms=30000)
    assert event.tool_name == "shell"
    assert event.error == "timeout"
    assert event.duration_ms == 30000
