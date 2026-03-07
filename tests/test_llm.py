"""Tests for src.llm."""

from unittest.mock import MagicMock, patch

from src.llm import LLMClient, _MAX_CONTENT_CHARS


# --- Sanitize tests ---


def test_sanitize_strips_unknown_fields():
    msgs = [
        {
            "role": "assistant",
            "content": "hi",
            "annotations": [],
            "refusal": None,
            "audio": None,
        }
    ]
    result = LLMClient._sanitize_messages(msgs)
    assert result == [{"role": "assistant", "content": "hi"}]


def test_sanitize_adds_missing_content():
    msgs = [
        {"role": "assistant", "tool_calls": [{"id": "1"}]},
        {"role": "assistant"},
    ]
    result = LLMClient._sanitize_messages(msgs)
    assert result[0]["content"] == ""
    assert result[0]["tool_calls"] == [{"id": "1"}]
    assert result[1]["content"] == ""


def test_sanitize_preserves_valid_messages():
    msgs = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello", "tool_calls": [{"id": "1"}]},
        {"role": "tool", "content": "result", "tool_call_id": "1", "name": "search"},
    ]
    result = LLMClient._sanitize_messages(msgs)
    assert result == msgs


def test_sanitize_adds_content_to_all_roles():
    """Every message gets content if missing, not just assistant."""
    msgs = [{"role": "user"}, {"role": "system"}]
    result = LLMClient._sanitize_messages(msgs)
    assert result[0]["content"] == ""
    assert result[1]["content"] == ""


def test_sanitize_truncates_oversized_content():
    """Messages with content exceeding _MAX_CONTENT_CHARS are truncated."""
    huge = "x" * (_MAX_CONTENT_CHARS + 10_000)
    msgs = [{"role": "tool", "content": huge, "tool_call_id": "1", "name": "shell"}]
    result = LLMClient._sanitize_messages(msgs)
    assert len(result[0]["content"]) < len(huge)
    assert "...[truncated]..." in result[0]["content"]


def test_sanitize_preserves_small_content():
    """Messages under the limit are not truncated."""
    small = "x" * 100
    msgs = [{"role": "user", "content": small}]
    result = LLMClient._sanitize_messages(msgs)
    assert result[0]["content"] == small


# --- Existing tests ---


def test_base_url_passed_to_client():
    with patch("src.llm.OpenAI") as MockOpenAI:
        from src.llm import LLMClient

        LLMClient(api_key="test-key", model="gpt-4o", base_url="https://proxy.example.com/v1")

        MockOpenAI.assert_called_once_with(api_key="test-key", base_url="https://proxy.example.com/v1")


def test_base_url_none_by_default():
    with patch("src.llm.OpenAI") as MockOpenAI:
        from src.llm import LLMClient

        LLMClient(api_key="test-key", model="gpt-4o")

        MockOpenAI.assert_called_once_with(api_key="test-key", base_url=None)


def test_chat_passes_messages_and_tools():
    with patch("src.llm.OpenAI") as MockOpenAI:
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        from src.llm import LLMClient

        llm = LLMClient(api_key="test-key", model="gpt-4o")

        tools = [{"type": "function", "function": {"name": "test"}}]
        messages = [{"role": "user", "content": "hello"}]

        llm.chat(messages=messages, tools=tools)

        mock_client.chat.completions.create.assert_called_once_with(
            model="gpt-4o",
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )


def test_chat_without_tools():
    with patch("src.llm.OpenAI") as MockOpenAI:
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        from src.llm import LLMClient

        llm = LLMClient(api_key="test-key", model="gpt-4o")

        messages = [{"role": "user", "content": "hello"}]
        llm.chat(messages=messages)

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert "tools" not in call_kwargs
        assert "tool_choice" not in call_kwargs


def test_model_property():
    with patch("src.llm.OpenAI"):
        from src.llm import LLMClient

        llm = LLMClient(api_key="test-key", model="gpt-4o-mini")
        assert llm.model == "gpt-4o-mini"
