"""Tests for src.context."""

import json
from unittest.mock import MagicMock

import pytest

from src.context import ContextManager


@pytest.fixture
def mock_llm():
    """Mock LLMClient that returns a summary string."""
    llm = MagicMock()
    msg = MagicMock()
    msg.content = "- User asked about X\n- Assistant found Y via tool"
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message = msg
    llm.chat.return_value = resp
    return llm


@pytest.fixture
def cm(mock_llm):
    """ContextManager with low thresholds for testing."""
    return ContextManager(llm=mock_llm, max_tokens=100, preserve_recent=3)


def _make_messages(system="sys", user_contents=None):
    """Helper to build a message list."""
    msgs = [{"role": "system", "content": system}]
    for content in (user_contents or []):
        msgs.append({"role": "user", "content": content})
        msgs.append({"role": "assistant", "content": f"reply to {content}"})
    return msgs


def test_estimate_tokens_basic(cm):
    messages = [
        {"role": "system", "content": "A" * 400},  # 100 tokens
        {"role": "user", "content": "B" * 200},     # 50 tokens
    ]
    assert cm.estimate_tokens(messages) == 150


def test_estimate_tokens_with_tool_calls(cm):
    tool_calls = [{"function": {"name": "shell", "arguments": "{}"}}]
    messages = [
        {"role": "assistant", "content": "", "tool_calls": tool_calls},
    ]
    expected_chars = len(json.dumps(tool_calls))
    assert cm.estimate_tokens(messages) == expected_chars // 4


def test_no_compression_under_limit(cm):
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    result = cm.maybe_compress(messages)
    assert result is messages  # exact same object


def test_compression_triggers_over_limit(cm, mock_llm):
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "A" * 500},      # old, big
        {"role": "assistant", "content": "B" * 500},  # old, big
        {"role": "user", "content": "recent1"},
        {"role": "assistant", "content": "recent2"},
        {"role": "user", "content": "recent3"},
    ]
    result = cm.maybe_compress(messages)

    assert len(result) < len(messages)
    assert result[0]["content"] == "sys"
    assert "[Conversation Summary]" in result[1]["content"]
    mock_llm.chat.assert_called_once()


def test_system_prompt_preserved(cm):
    system = {"role": "system", "content": "Original system prompt"}
    messages = [
        system,
        {"role": "user", "content": "X" * 500},
        {"role": "assistant", "content": "Y" * 500},
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": "c"},
    ]
    result = cm.maybe_compress(messages)

    assert result[0] is system


def test_recent_messages_preserved(cm):
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "Z" * 500},
        {"role": "assistant", "content": "W" * 500},
        {"role": "user", "content": "recent1"},
        {"role": "assistant", "content": "recent2"},
        {"role": "user", "content": "recent3"},
    ]
    result = cm.maybe_compress(messages)

    # Last 3 messages (preserve_recent=3) must be at the end
    assert result[-1]["content"] == "recent3"
    assert result[-2]["content"] == "recent2"
    assert result[-3]["content"] == "recent1"


def test_tool_call_pairs_not_split(mock_llm):
    # preserve_recent=2 so the cut falls inside a tool-call block
    cm = ContextManager(llm=mock_llm, max_tokens=50, preserve_recent=2)
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "X" * 400},
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "shell", "arguments": '{"command":"ls"}'}}
        ]},
        {"role": "tool", "tool_call_id": "1", "name": "shell", "content": "file1\nfile2"},
        {"role": "assistant", "content": "result"},
        {"role": "user", "content": "recent1"},
        {"role": "assistant", "content": "recent2"},
    ]
    result = cm.maybe_compress(messages)

    # The tool_call + tool response block must not be split
    for i, msg in enumerate(result):
        if msg.get("tool_calls"):
            # Next message must be the tool response
            assert result[i + 1].get("role") == "tool"


def test_summary_message_format(cm, mock_llm):
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "Q" * 500},
        {"role": "assistant", "content": "A" * 500},
        {"role": "user", "content": "r1"},
        {"role": "assistant", "content": "r2"},
        {"role": "user", "content": "r3"},
    ]
    result = cm.maybe_compress(messages)
    summary = result[1]

    assert summary["role"] == "system"
    assert "[Conversation Summary]" in summary["content"]
    assert "[End of Summary" in summary["content"]
    assert "User asked about X" in summary["content"]


def test_summarizer_truncates_long_tool_output(cm, mock_llm):
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "run this"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "shell", "arguments": '{"command":"big"}'}}
        ]},
        {"role": "tool", "tool_call_id": "1", "name": "shell",
         "content": "X" * 50000},
        {"role": "assistant", "content": "done"},
        {"role": "user", "content": "r1"},
        {"role": "assistant", "content": "r2"},
        {"role": "user", "content": "r3"},
    ]
    cm.maybe_compress(messages)

    # Check the text sent to the summarizer LLM
    call_args = mock_llm.chat.call_args
    summarizer_messages = call_args[1].get("messages") or call_args[0][0]
    user_content = summarizer_messages[1]["content"]
    # The 50k tool output should be truncated in the summary input
    assert len(user_content) < 50000
    assert "truncated" in user_content.lower()


def test_empty_compressible_zone(mock_llm):
    cm = ContextManager(llm=mock_llm, max_tokens=10, preserve_recent=10)
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "X" * 500},
        {"role": "assistant", "content": "Y" * 500},
    ]
    # Only 2 messages after system, preserve_recent=10 → nothing to compress
    result = cm.maybe_compress(messages)
    assert result is messages
    mock_llm.chat.assert_not_called()


def test_multiple_compressions(mock_llm):
    cm = ContextManager(llm=mock_llm, max_tokens=100, preserve_recent=3)

    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "A" * 500},
        {"role": "assistant", "content": "B" * 500},
        {"role": "user", "content": "r1"},
        {"role": "assistant", "content": "r2"},
        {"role": "user", "content": "r3"},
    ]

    # First compression
    result1 = cm.maybe_compress(messages)
    assert "[Conversation Summary]" in result1[1]["content"]

    # Add more big messages
    result1.append({"role": "user", "content": "C" * 500})
    result1.append({"role": "assistant", "content": "D" * 500})
    result1.append({"role": "user", "content": "new_recent"})

    # Second compression — should handle existing summary correctly
    result2 = cm.maybe_compress(result1)
    assert result2[0]["content"] == "sys"
    assert "[Conversation Summary]" in result2[1]["content"]
    assert result2[-1]["content"] == "new_recent"


def test_llm_error_graceful_fallback(cm, mock_llm):
    mock_llm.chat.side_effect = RuntimeError("API down")

    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "A" * 500},
        {"role": "assistant", "content": "B" * 500},
        {"role": "user", "content": "r1"},
        {"role": "assistant", "content": "r2"},
        {"role": "user", "content": "r3"},
    ]
    result = cm.maybe_compress(messages)

    # Should return original messages unchanged on error
    assert result is messages
