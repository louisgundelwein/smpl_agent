"""Tests for src.agent."""

import json
from unittest.mock import MagicMock

import pytest

from src.agent import Agent
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
