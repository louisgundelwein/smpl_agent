"""Tests for src.llm."""

from unittest.mock import MagicMock, patch


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
