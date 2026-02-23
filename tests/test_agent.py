"""Tests for src.agent."""

import json
from unittest.mock import MagicMock

import pytest

from src.agent import Agent
from src.events import (
    EventEmitter,
    LLMEndEvent,
    LLMStartEvent,
    ToolEndEvent,
    ToolStartEvent,
)
from src.tools.registry import ToolRegistry
from tests.conftest import DummyTool


def _make_message(content=None, tool_calls=None):
    """Create a mock message object."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    msg.model_dump.return_value = {
        "role": "assistant",
        "content": content,
        "tool_calls": (
            [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]
            if tool_calls
            else None
        ),
    }
    return msg


def _make_tool_call(call_id, name, arguments):
    """Create a mock tool call object."""
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    return tc


def _make_response(message):
    """Create a mock ChatCompletion response."""
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message = message
    return resp


@pytest.fixture
def registry_with_dummy():
    registry = ToolRegistry()
    registry.register(DummyTool())
    return registry


def test_simple_text_response(registry_with_dummy):
    mock_llm = MagicMock()
    msg = _make_message(content="Hello there!")
    mock_llm.chat.return_value = _make_response(msg)

    agent = Agent(llm=mock_llm, registry=registry_with_dummy)
    result = agent.run("hi")

    assert result == "Hello there!"
    assert mock_llm.chat.call_count == 1


def test_single_tool_call_cycle(registry_with_dummy):
    mock_llm = MagicMock()

    tool_call = _make_tool_call("call_1", "dummy", {"arg1": "hello"})
    tool_msg = _make_message(tool_calls=[tool_call])
    final_msg = _make_message(content="Here is your answer.")

    mock_llm.chat.side_effect = [
        _make_response(tool_msg),
        _make_response(final_msg),
    ]

    agent = Agent(llm=mock_llm, registry=registry_with_dummy)
    result = agent.run("test")

    assert result == "Here is your answer."
    assert mock_llm.chat.call_count == 2


def test_multiple_tool_calls_in_one_response(registry_with_dummy):
    mock_llm = MagicMock()

    tc1 = _make_tool_call("call_1", "dummy", {"arg1": "first"})
    tc2 = _make_tool_call("call_2", "dummy", {"arg1": "second"})
    tool_msg = _make_message(tool_calls=[tc1, tc2])
    final_msg = _make_message(content="Both done.")

    mock_llm.chat.side_effect = [
        _make_response(tool_msg),
        _make_response(final_msg),
    ]

    agent = Agent(llm=mock_llm, registry=registry_with_dummy)
    result = agent.run("do two things")

    assert result == "Both done."

    # Check both tool results were added to messages
    tool_messages = [m for m in agent.messages if isinstance(m, dict) and m.get("role") == "tool"]
    assert len(tool_messages) == 2


def test_tool_execution_error_sent_to_llm():
    mock_llm = MagicMock()
    registry = ToolRegistry()

    # Register a tool that raises
    error_tool = MagicMock()
    error_tool.name = "failing"
    error_tool.schema = {"type": "function", "function": {"name": "failing"}}
    error_tool.execute.side_effect = RuntimeError("boom")
    registry._tools["failing"] = error_tool

    tc = _make_tool_call("call_1", "failing", {})
    tool_msg = _make_message(tool_calls=[tc])
    final_msg = _make_message(content="Sorry, that failed.")

    mock_llm.chat.side_effect = [
        _make_response(tool_msg),
        _make_response(final_msg),
    ]

    agent = Agent(llm=mock_llm, registry=registry)
    result = agent.run("break it")

    assert result == "Sorry, that failed."

    # Check error was passed back
    tool_messages = [m for m in agent.messages if isinstance(m, dict) and m.get("role") == "tool"]
    assert len(tool_messages) == 1
    error_content = json.loads(tool_messages[0]["content"])
    assert "error" in error_content


def test_max_rounds_exceeded():
    mock_llm = MagicMock()
    registry = ToolRegistry()
    registry.register(DummyTool())

    tc = _make_tool_call("call_1", "dummy", {"arg1": "loop"})
    tool_msg = _make_message(tool_calls=[tc])

    # Always return tool calls, never a final text response
    mock_llm.chat.return_value = _make_response(tool_msg)

    agent = Agent(llm=mock_llm, registry=registry, max_tool_rounds=3)

    with pytest.raises(RuntimeError, match="exceeded maximum tool rounds"):
        agent.run("infinite loop")


def test_conversation_history_persists(registry_with_dummy):
    mock_llm = MagicMock()
    msg1 = _make_message(content="First reply.")
    msg2 = _make_message(content="Second reply.")
    mock_llm.chat.side_effect = [
        _make_response(msg1),
        _make_response(msg2),
    ]

    agent = Agent(llm=mock_llm, registry=registry_with_dummy)
    agent.run("first")
    agent.run("second")

    # Should have: system + user1 + assistant1 + user2 + assistant2
    assert len(agent.messages) == 5
    assert agent.messages[0]["role"] == "system"


def test_reset_clears_history(registry_with_dummy):
    mock_llm = MagicMock()
    msg = _make_message(content="reply")
    mock_llm.chat.return_value = _make_response(msg)

    agent = Agent(llm=mock_llm, registry=registry_with_dummy)
    agent.run("hello")
    agent.reset()

    assert len(agent.messages) == 1
    assert agent.messages[0]["role"] == "system"


def test_events_emitted_during_tool_call(registry_with_dummy):
    mock_llm = MagicMock()

    tc = _make_tool_call("call_1", "dummy", {"arg1": "hello"})
    tool_msg = _make_message(tool_calls=[tc])
    final_msg = _make_message(content="Done.")
    mock_llm.chat.side_effect = [
        _make_response(tool_msg),
        _make_response(final_msg),
    ]

    events = []
    emitter = EventEmitter()
    emitter.on(lambda e: events.append(e))

    agent = Agent(llm=mock_llm, registry=registry_with_dummy, emitter=emitter)
    agent.run("test")

    # 6 events: LLMStart, LLMEnd, ToolStart, ToolEnd, LLMStart, LLMEnd
    assert len(events) == 6
    assert isinstance(events[0], LLMStartEvent)
    assert events[0].round_number == 1
    assert isinstance(events[1], LLMEndEvent)
    assert events[1].has_tool_calls is True
    assert isinstance(events[2], ToolStartEvent)
    assert events[2].tool_name == "dummy"
    assert events[2].arguments == {"arg1": "hello"}
    assert isinstance(events[3], ToolEndEvent)
    assert events[3].tool_name == "dummy"
    assert events[3].duration_ms >= 0
    assert isinstance(events[4], LLMStartEvent)
    assert events[4].round_number == 2
    assert isinstance(events[5], LLMEndEvent)
    assert events[5].has_tool_calls is False


def test_context_manager_called_before_llm(registry_with_dummy):
    mock_llm = MagicMock()
    msg = _make_message(content="reply")
    mock_llm.chat.return_value = _make_response(msg)

    # Capture snapshot of messages at call time (list is mutable)
    captured = []
    def capture_and_passthrough(msgs):
        captured.append(list(msgs))  # shallow copy at call time
        return msgs

    mock_cm = MagicMock()
    mock_cm.maybe_compress.side_effect = capture_and_passthrough
    mock_cm.estimate_tokens.return_value = 100

    agent = Agent(
        llm=mock_llm,
        registry=registry_with_dummy,
        context_manager=mock_cm,
    )
    agent.run("hi")

    mock_cm.maybe_compress.assert_called_once()
    # Verify it was called with system + user message
    assert captured[0][0]["role"] == "system"
    assert captured[0][-1]["content"] == "hi"


def test_agent_works_without_context_manager(registry_with_dummy):
    mock_llm = MagicMock()
    msg = _make_message(content="no context manager")
    mock_llm.chat.return_value = _make_response(msg)

    # context_manager defaults to None — should work fine
    agent = Agent(llm=mock_llm, registry=registry_with_dummy)
    result = agent.run("test")

    assert result == "no context manager"


def test_history_loaded_on_init(registry_with_dummy):
    """Agent loads persisted messages on construction."""
    mock_llm = MagicMock()
    mock_history = MagicMock()
    mock_history.load.return_value = [
        {"role": "system", "content": "old prompt"},
        {"role": "user", "content": "previous question"},
        {"role": "assistant", "content": "previous answer"},
    ]

    agent = Agent(
        llm=mock_llm,
        registry=registry_with_dummy,
        system_prompt="new prompt",
        history=mock_history,
    )

    # System prompt should be replaced with current one
    assert agent.messages[0]["content"] == "new prompt"
    # But conversation should be preserved
    assert len(agent.messages) == 3
    assert agent.messages[1]["content"] == "previous question"


def test_history_saved_after_run(registry_with_dummy):
    """Agent saves messages to history after each run()."""
    mock_llm = MagicMock()
    msg = _make_message(content="reply")
    mock_llm.chat.return_value = _make_response(msg)

    mock_history = MagicMock()
    mock_history.load.return_value = None

    agent = Agent(
        llm=mock_llm,
        registry=registry_with_dummy,
        history=mock_history,
    )
    agent.run("hello")

    mock_history.save.assert_called_once()
    saved_messages = mock_history.save.call_args[0][0]
    assert len(saved_messages) == 3  # system + user + assistant


def test_history_cleared_on_reset(registry_with_dummy):
    """Agent clears history file on reset()."""
    mock_llm = MagicMock()
    mock_history = MagicMock()
    mock_history.load.return_value = None

    agent = Agent(
        llm=mock_llm,
        registry=registry_with_dummy,
        history=mock_history,
    )
    agent.reset()

    mock_history.clear.assert_called_once()


def test_agent_works_without_history(registry_with_dummy):
    """Agent still works when history=None (backward compatible)."""
    mock_llm = MagicMock()
    msg = _make_message(content="works")
    mock_llm.chat.return_value = _make_response(msg)

    agent = Agent(llm=mock_llm, registry=registry_with_dummy)
    result = agent.run("test")

    assert result == "works"


def test_history_not_saved_on_max_rounds_error(registry_with_dummy):
    """History is not saved when max_tool_rounds is exceeded."""
    mock_llm = MagicMock()

    tc = _make_tool_call("call_1", "dummy", {"arg1": "loop"})
    tool_msg = _make_message(tool_calls=[tc])
    mock_llm.chat.return_value = _make_response(tool_msg)

    mock_history = MagicMock()
    mock_history.load.return_value = None

    agent = Agent(
        llm=mock_llm,
        registry=registry_with_dummy,
        max_tool_rounds=2,
        history=mock_history,
    )

    with pytest.raises(RuntimeError):
        agent.run("infinite loop")

    mock_history.save.assert_not_called()


def test_llm_events_emitted_on_simple_response(registry_with_dummy):
    """A simple text response emits LLMStart + LLMEnd."""
    mock_llm = MagicMock()
    msg = _make_message(content="Hello!")
    mock_llm.chat.return_value = _make_response(msg)

    events = []
    emitter = EventEmitter()
    emitter.on(lambda e: events.append(e))

    agent = Agent(llm=mock_llm, registry=registry_with_dummy, emitter=emitter)
    agent.run("hi")

    assert len(events) == 2
    assert isinstance(events[0], LLMStartEvent)
    assert events[0].round_number == 1
    assert events[0].message_count == 2  # system + user
    assert events[0].estimated_tokens >= 0
    assert isinstance(events[1], LLMEndEvent)
    assert events[1].round_number == 1
    assert events[1].has_tool_calls is False
    assert events[1].duration_ms >= 0


def test_llm_events_round_numbers_increment(registry_with_dummy):
    """Round numbers increment across tool-calling iterations."""
    mock_llm = MagicMock()

    tc = _make_tool_call("call_1", "dummy", {"arg1": "x"})
    tool_msg = _make_message(tool_calls=[tc])
    final_msg = _make_message(content="Done.")
    mock_llm.chat.side_effect = [
        _make_response(tool_msg),
        _make_response(final_msg),
    ]

    events = []
    emitter = EventEmitter()
    emitter.on(lambda e: events.append(e))

    agent = Agent(llm=mock_llm, registry=registry_with_dummy, emitter=emitter)
    agent.run("test")

    llm_starts = [e for e in events if isinstance(e, LLMStartEvent)]
    assert len(llm_starts) == 2
    assert llm_starts[0].round_number == 1
    assert llm_starts[1].round_number == 2


def test_tool_end_has_duration_ms(registry_with_dummy):
    """ToolEndEvent includes a non-negative duration."""
    mock_llm = MagicMock()

    tc = _make_tool_call("call_1", "dummy", {"arg1": "test"})
    tool_msg = _make_message(tool_calls=[tc])
    final_msg = _make_message(content="Done.")
    mock_llm.chat.side_effect = [
        _make_response(tool_msg),
        _make_response(final_msg),
    ]

    events = []
    emitter = EventEmitter()
    emitter.on(lambda e: events.append(e))

    agent = Agent(llm=mock_llm, registry=registry_with_dummy, emitter=emitter)
    agent.run("test")

    tool_ends = [e for e in events if isinstance(e, ToolEndEvent)]
    assert len(tool_ends) == 1
    assert tool_ends[0].duration_ms >= 0
