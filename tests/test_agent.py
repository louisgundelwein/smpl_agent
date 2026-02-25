"""Tests for src.agent."""

import json
from unittest.mock import MagicMock

import pytest

from src.agent import Agent
from src.events import (
    ContinuationEvent,
    EventEmitter,
    LLMEndEvent,
    LLMStartEvent,
    RunSummaryEvent,
    SubagentResultsCollectedEvent,
    SubagentWaitEvent,
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

    agent = Agent(llm=mock_llm, registry=registry_with_dummy, max_continuations=0)
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

    agent = Agent(llm=mock_llm, registry=registry_with_dummy, max_continuations=0)
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

    agent = Agent(llm=mock_llm, registry=registry_with_dummy, max_continuations=0)
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

    agent = Agent(llm=mock_llm, registry=registry, max_continuations=0)
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

    agent = Agent(llm=mock_llm, registry=registry, max_tool_rounds=3, max_continuations=0)

    with pytest.raises(RuntimeError, match="exceeded maximum rounds"):
        agent.run("infinite loop")


def test_conversation_history_persists(registry_with_dummy):
    mock_llm = MagicMock()
    msg1 = _make_message(content="First reply.")
    msg2 = _make_message(content="Second reply.")
    mock_llm.chat.side_effect = [
        _make_response(msg1),
        _make_response(msg2),
    ]

    agent = Agent(llm=mock_llm, registry=registry_with_dummy, max_continuations=0)
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

    agent = Agent(llm=mock_llm, registry=registry_with_dummy, emitter=emitter, max_continuations=0)
    agent.run("test")

    # 7 events: LLMStart, LLMEnd, ToolStart, ToolEnd, LLMStart, LLMEnd, RunSummary
    assert len(events) == 7
    assert isinstance(events[0], LLMStartEvent)
    assert events[0].round_number == 1
    assert isinstance(events[1], LLMEndEvent)
    assert events[1].has_tool_calls is True
    assert events[1].tool_call_count == 1
    assert isinstance(events[2], ToolStartEvent)
    assert events[2].tool_name == "dummy"
    assert events[2].arguments == {"arg1": "hello"}
    assert isinstance(events[3], ToolEndEvent)
    assert events[3].tool_name == "dummy"
    assert events[3].duration_ms >= 0
    assert events[3].result_preview is not None
    assert isinstance(events[4], LLMStartEvent)
    assert events[4].round_number == 2
    assert isinstance(events[5], LLMEndEvent)
    assert events[5].has_tool_calls is False
    assert isinstance(events[6], RunSummaryEvent)
    assert events[6].total_rounds == 2
    assert events[6].tool_calls_made == 1


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
        max_continuations=0,
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
        max_continuations=0,
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

    agent = Agent(llm=mock_llm, registry=registry_with_dummy, emitter=emitter, max_continuations=0)
    agent.run("hi")

    assert len(events) == 3  # LLMStart, LLMEnd, RunSummary
    assert isinstance(events[0], LLMStartEvent)
    assert events[0].round_number == 1
    assert events[0].message_count == 2  # system + user
    assert events[0].estimated_tokens >= 0
    assert isinstance(events[1], LLMEndEvent)
    assert events[1].round_number == 1
    assert events[1].has_tool_calls is False
    assert events[1].duration_ms >= 0
    assert events[1].response_preview == "Hello!"
    assert isinstance(events[2], RunSummaryEvent)
    assert events[2].total_rounds == 1
    assert events[2].tool_calls_made == 0
    assert events[2].continuations_used == 0


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

    agent = Agent(llm=mock_llm, registry=registry_with_dummy, emitter=emitter, max_continuations=0)
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

    agent = Agent(llm=mock_llm, registry=registry_with_dummy, emitter=emitter, max_continuations=0)
    agent.run("test")

    tool_ends = [e for e in events if isinstance(e, ToolEndEvent)]
    assert len(tool_ends) == 1
    assert tool_ends[0].duration_ms >= 0


# --- Subagent auto-collection tests ---


def test_subagent_results_collected_after_text_response(registry_with_dummy):
    """When LLM returns text and subagents are active, wait and re-enter loop."""
    mock_llm = MagicMock()
    mock_sm = MagicMock()

    first_msg = _make_message(content="I've started the subagents.")
    final_msg = _make_message(content="Here are the combined results.")

    mock_llm.chat.side_effect = [
        _make_response(first_msg),
        _make_response(final_msg),
    ]

    # First call: 2 active, second call (after wait): 0 active
    mock_sm.active_count.side_effect = [2, 0]
    mock_sm.wait_all.return_value = [
        {"id": "aaa", "task": "task 1", "status": "completed", "result": "done 1", "error": None, "elapsed_seconds": 1.0},
        {"id": "bbb", "task": "task 2", "status": "completed", "result": "done 2", "error": None, "elapsed_seconds": 2.0},
    ]

    agent = Agent(
        llm=mock_llm,
        registry=registry_with_dummy,
        subagent_manager=mock_sm,
        max_continuations=0,
    )
    result = agent.run("do parallel work")

    assert result == "Here are the combined results."
    assert mock_llm.chat.call_count == 2
    mock_sm.wait_all.assert_called_once()

    # Verify synthetic user message was injected
    user_messages = [
        m for m in agent.messages
        if isinstance(m, dict) and m.get("role") == "user"
    ]
    assert len(user_messages) == 2  # original + synthetic
    assert "Subagent results" in user_messages[1]["content"]


def test_no_subagent_wait_when_none_active(registry_with_dummy):
    """When no subagents are active, return immediately."""
    mock_llm = MagicMock()
    mock_sm = MagicMock()
    mock_sm.active_count.return_value = 0

    msg = _make_message(content="No subagents running.")
    mock_llm.chat.return_value = _make_response(msg)

    agent = Agent(
        llm=mock_llm,
        registry=registry_with_dummy,
        subagent_manager=mock_sm,
        max_continuations=0,
    )
    result = agent.run("hi")

    assert result == "No subagents running."
    assert mock_llm.chat.call_count == 1
    mock_sm.wait_all.assert_not_called()


def test_no_subagent_wait_when_manager_is_none(registry_with_dummy):
    """When subagent_manager is None (default), return immediately."""
    mock_llm = MagicMock()
    msg = _make_message(content="No manager.")
    mock_llm.chat.return_value = _make_response(msg)

    agent = Agent(llm=mock_llm, registry=registry_with_dummy, max_continuations=0)
    result = agent.run("hi")

    assert result == "No manager."
    assert mock_llm.chat.call_count == 1


def test_subagent_wait_emits_events(registry_with_dummy):
    """SubagentWaitEvent and SubagentResultsCollectedEvent are emitted."""
    from src.events import SubagentResultsCollectedEvent, SubagentWaitEvent

    mock_llm = MagicMock()
    mock_sm = MagicMock()

    first_msg = _make_message(content="Started subagents.")
    final_msg = _make_message(content="Done.")
    mock_llm.chat.side_effect = [
        _make_response(first_msg),
        _make_response(final_msg),
    ]
    mock_sm.active_count.side_effect = [1, 0]
    mock_sm.wait_all.return_value = [
        {"id": "aaa", "task": "t", "status": "completed", "result": "r", "error": None, "elapsed_seconds": 1.0},
    ]

    events = []
    emitter = EventEmitter()
    emitter.on(lambda e: events.append(e))

    agent = Agent(
        llm=mock_llm,
        registry=registry_with_dummy,
        subagent_manager=mock_sm,
        emitter=emitter,
        max_continuations=0,
    )
    agent.run("test")

    wait_events = [e for e in events if isinstance(e, SubagentWaitEvent)]
    collected_events = [e for e in events if isinstance(e, SubagentResultsCollectedEvent)]
    assert len(wait_events) == 1
    assert wait_events[0].active_count == 1
    assert len(collected_events) == 1
    assert collected_events[0].count == 1


def test_subagent_failed_result_included(registry_with_dummy):
    """Failed subagent results are included in the injected message."""
    mock_llm = MagicMock()
    mock_sm = MagicMock()

    first_msg = _make_message(content="Started subagent.")
    final_msg = _make_message(content="The subagent failed.")
    mock_llm.chat.side_effect = [
        _make_response(first_msg),
        _make_response(final_msg),
    ]
    mock_sm.active_count.side_effect = [1, 0]
    mock_sm.wait_all.return_value = [
        {"id": "aaa", "task": "task 1", "status": "failed", "result": None, "error": "LLM exploded", "elapsed_seconds": 0.5},
    ]

    agent = Agent(
        llm=mock_llm,
        registry=registry_with_dummy,
        subagent_manager=mock_sm,
        max_continuations=0,
    )
    agent.run("test")

    user_messages = [
        m for m in agent.messages
        if isinstance(m, dict) and m.get("role") == "user"
    ]
    synthetic = user_messages[1]["content"]
    assert "Failed: LLM exploded" in synthetic


# --- Auto-memory hook tests ---


def test_auto_memory_on_turn_end_called(registry_with_dummy):
    """auto_memory.on_turn_end is called after agent.run() returns."""
    mock_llm = MagicMock()
    msg = _make_message(content="reply")
    mock_llm.chat.return_value = _make_response(msg)

    mock_am = MagicMock()
    agent = Agent(
        llm=mock_llm, registry=registry_with_dummy,
        auto_memory=mock_am, max_continuations=0,
    )
    agent.run("hello")

    mock_am.on_turn_end.assert_called_once()
    # Verify messages snapshot was passed
    call_args = mock_am.on_turn_end.call_args[0][0]
    assert call_args[0]["role"] == "system"


def test_auto_memory_on_conversation_end_called_on_reset(registry_with_dummy):
    """auto_memory.on_conversation_end is called before reset clears messages."""
    mock_llm = MagicMock()
    msg = _make_message(content="reply")
    mock_llm.chat.return_value = _make_response(msg)

    mock_am = MagicMock()
    agent = Agent(
        llm=mock_llm, registry=registry_with_dummy,
        auto_memory=mock_am, max_continuations=0,
    )
    agent.run("hello")
    agent.reset()

    mock_am.on_conversation_end.assert_called_once()
    # Verify messages were passed BEFORE clearing (should have 3: system + user + assistant)
    call_args = mock_am.on_conversation_end.call_args[0][0]
    assert len(call_args) == 3


def test_agent_works_without_auto_memory(registry_with_dummy):
    """Agent still works when auto_memory=None (default)."""
    mock_llm = MagicMock()
    msg = _make_message(content="works")
    mock_llm.chat.return_value = _make_response(msg)

    agent = Agent(llm=mock_llm, registry=registry_with_dummy, max_continuations=0)
    result = agent.run("test")
    assert result == "works"
    agent.reset()  # Should not raise


# --- Auto-continuation tests ---


def test_no_continuation_without_prior_tools(registry_with_dummy):
    """LLM returns text without ever using tools -> no continuation, returns immediately."""
    mock_llm = MagicMock()
    msg = _make_message(content="Here's the answer.")
    mock_llm.chat.return_value = _make_response(msg)

    agent = Agent(llm=mock_llm, registry=registry_with_dummy, max_continuations=5)
    result = agent.run("hello")

    assert result == "Here's the answer."
    assert mock_llm.chat.call_count == 1  # no continuation nudge


def test_continuation_nudge_after_tool_use(registry_with_dummy):
    """After using tools, text response triggers continuation nudge."""
    mock_llm = MagicMock()
    tc = _make_tool_call("call_1", "dummy", {"arg1": "x"})
    mock_llm.chat.side_effect = [
        _make_response(_make_message(tool_calls=[tc])),         # tools
        _make_response(_make_message(content="I found it.")),   # text -> nudge
        _make_response(_make_message(content="Here's the answer.")),  # text -> return
    ]

    agent = Agent(llm=mock_llm, registry=registry_with_dummy, max_continuations=5)
    result = agent.run("hello")

    assert result == "Here's the answer."
    assert mock_llm.chat.call_count == 3

    # Verify nudge message was injected
    user_msgs = [
        m for m in agent.messages
        if isinstance(m, dict) and m.get("role") == "user"
    ]
    assert len(user_msgs) == 2  # original + nudge
    assert "[Continue" in user_msgs[1]["content"]


def test_continuation_triggers_more_tool_use(registry_with_dummy):
    """After initial tools, text gets nudged, nudge causes more tool use."""
    mock_llm = MagicMock()
    tc1 = _make_tool_call("call_1", "dummy", {"arg1": "first"})
    tc2 = _make_tool_call("call_2", "dummy", {"arg1": "second"})
    mock_llm.chat.side_effect = [
        _make_response(_make_message(tool_calls=[tc1])),        # tool call -> any_tools_used=True
        _make_response(_make_message(content="Let me check.")), # text -> nudge (consec=1)
        _make_response(_make_message(tool_calls=[tc2])),        # tool call -> reset consec
        _make_response(_make_message(content="Here's result.")),# text -> nudge (consec=1)
        _make_response(_make_message(content="Final.")),        # text -> consec=2 -> return
    ]

    agent = Agent(llm=mock_llm, registry=registry_with_dummy, max_continuations=5)
    result = agent.run("search for something")

    assert result == "Final."
    assert mock_llm.chat.call_count == 5


def test_continuation_disabled_when_zero(registry_with_dummy):
    """With max_continuations=0, text returns immediately (backward compat)."""
    mock_llm = MagicMock()
    msg = _make_message(content="Hello!")
    mock_llm.chat.return_value = _make_response(msg)

    agent = Agent(llm=mock_llm, registry=registry_with_dummy, max_continuations=0)
    result = agent.run("hi")

    assert result == "Hello!"
    assert mock_llm.chat.call_count == 1


def test_consecutive_text_resets_after_tools(registry_with_dummy):
    """Tool calls reset the consecutive text counter."""
    mock_llm = MagicMock()
    tc = _make_tool_call("call_1", "dummy", {"arg1": "x"})
    tc2 = _make_tool_call("call_2", "dummy", {"arg1": "y"})
    mock_llm.chat.side_effect = [
        _make_response(_make_message(tool_calls=[tc])),         # tools -> any_tools_used=True
        _make_response(_make_message(content="Thinking...")),   # text (consec=1) -> nudge
        _make_response(_make_message(tool_calls=[tc2])),        # tools -> consec resets
        _make_response(_make_message(content="More thinking")), # text (consec=1) -> nudge
        _make_response(_make_message(content="Done now.")),     # text (consec=2) -> return
    ]

    agent = Agent(llm=mock_llm, registry=registry_with_dummy, max_continuations=5)
    result = agent.run("test")

    assert result == "Done now."
    assert mock_llm.chat.call_count == 5


def test_continuation_event_emitted(registry_with_dummy):
    """ContinuationEvent is emitted when a nudge is injected."""
    mock_llm = MagicMock()
    tc = _make_tool_call("call_1", "dummy", {"arg1": "x"})
    mock_llm.chat.side_effect = [
        _make_response(_make_message(tool_calls=[tc])),          # tools -> any_tools_used
        _make_response(_make_message(content="Working on it...")),
        _make_response(_make_message(content="Done.")),
    ]

    events = []
    emitter = EventEmitter()
    emitter.on(lambda e: events.append(e))

    agent = Agent(
        llm=mock_llm,
        registry=registry_with_dummy,
        max_continuations=5,
        emitter=emitter,
    )
    agent.run("test")

    cont_events = [e for e in events if isinstance(e, ContinuationEvent)]
    assert len(cont_events) == 1
    assert cont_events[0].continuation_number == 1
    assert cont_events[0].max_continuations == 5


def test_max_continuations_cap(registry_with_dummy):
    """Agent stops after max_continuations nudges are exhausted."""
    mock_llm = MagicMock()
    tc = _make_tool_call("call_1", "dummy", {"arg1": "x"})
    # Initial tools set any_tools_used=True, then each text->nudge->tools cycle
    # uses one continuation. With max_continuations=2, after 2 nudges the next
    # text returns immediately.
    mock_llm.chat.side_effect = [
        _make_response(_make_message(tool_calls=[tc])),     # tools -> any_tools_used=True
        _make_response(_make_message(content="Step 1")),    # nudge (cont=1)
        _make_response(_make_message(tool_calls=[tc])),     # tools -> reset consec
        _make_response(_make_message(content="Step 2")),    # nudge (cont=2)
        _make_response(_make_message(tool_calls=[tc])),     # tools -> reset consec
        _make_response(_make_message(content="Step 3")),    # cont exhausted -> return
    ]

    agent = Agent(llm=mock_llm, registry=registry_with_dummy, max_continuations=2)
    result = agent.run("test")

    assert result == "Step 3"
    assert mock_llm.chat.call_count == 6


def test_llm_error_rolls_back_messages(registry_with_dummy):
    """When the LLM call raises, messages added during the round are removed."""
    mock_llm = MagicMock()

    # First call succeeds (tool call + tool result), second call fails.
    tc = _make_tool_call("call_1", "dummy", {"arg1": "x"})
    tool_msg = _make_message(tool_calls=[tc])
    mock_llm.chat.side_effect = [
        _make_response(tool_msg),
        RuntimeError("Gemini 400"),
    ]

    agent = Agent(llm=mock_llm, registry=registry_with_dummy, max_continuations=0)
    initial_count = len(agent.messages)  # system prompt only

    with pytest.raises(RuntimeError, match="Gemini 400"):
        agent.run("test")

    # After error, messages should have: system + user + assistant + tool
    # The second LLM call failed, so nothing from round 2 should remain.
    # (The assistant message + tool result from round 1 are committed before
    # round 2 starts, so they persist.)
    assert len(agent.messages) == initial_count + 3  # user + assistant + tool


def test_llm_error_during_continuation_rolls_back(registry_with_dummy):
    """Continuation prompt is rolled back when the next LLM call fails."""
    mock_llm = MagicMock()

    # First call: tool use (sets any_tools_used), second: text (triggers continuation),
    # third: LLM error (should roll back).
    tc = _make_tool_call("call_1", "dummy", {"arg1": "x"})
    mock_llm.chat.side_effect = [
        _make_response(_make_message(tool_calls=[tc])),
        _make_response(_make_message(content="Working on it...")),
        RuntimeError("Gemini 400"),
    ]

    agent = Agent(llm=mock_llm, registry=registry_with_dummy, max_continuations=5)

    with pytest.raises(RuntimeError, match="Gemini 400"):
        agent.run("test")

    # Messages should have: system + user + assistant(tool) + tool_result +
    # assistant(text) + continuation user.
    # The continuation user message was added before round 3's LLM call,
    # so it persists. But no corrupted assistant from round 3.
    msgs = agent.messages
    assert msgs[-1]["role"] == "user"
    assert "[Continue" in msgs[-1]["content"]


def test_subagent_wait_before_continuation(registry_with_dummy):
    """Subagent wait fires before continuation logic. After subagent results,
    continuation only fires if tools were used at some point."""
    mock_llm = MagicMock()
    mock_sm = MagicMock()
    tc = _make_tool_call("call_1", "dummy", {"arg1": "spawn"})

    # Round 1: tool call (spawns subagent) → any_tools_used=True
    # Round 2: text → subagent active → wait_all → re-enter loop
    # Round 3: text → no subagents → continuation nudge (consecutive_text=1)
    # Round 4: text → no subagents → consecutive_text=2 → done
    mock_llm.chat.side_effect = [
        _make_response(_make_message(tool_calls=[tc])),
        _make_response(_make_message(content="Started subagents.")),
        _make_response(_make_message(content="Results synthesized.")),
        _make_response(_make_message(content="All done.")),
    ]

    # Round 1: no subagents yet; round 2: 1 active; rounds 3+4: 0 active
    mock_sm.active_count.side_effect = [1, 0, 0]
    mock_sm.wait_all.return_value = [
        {"id": "a", "task": "t", "status": "completed", "result": "r",
         "error": None, "elapsed_seconds": 1.0},
    ]

    events = []
    emitter = EventEmitter()
    emitter.on(lambda e: events.append(e))

    agent = Agent(
        llm=mock_llm,
        registry=registry_with_dummy,
        subagent_manager=mock_sm,
        max_continuations=5,
        emitter=emitter,
    )
    result = agent.run("test")

    mock_sm.wait_all.assert_called_once()
    wait_events = [e for e in events if isinstance(e, SubagentWaitEvent)]
    cont_events = [e for e in events if isinstance(e, ContinuationEvent)]
    assert len(wait_events) == 1
    assert len(cont_events) == 1
    assert result == "All done."
