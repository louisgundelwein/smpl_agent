"""Shared test fixtures."""

import pytest

from src.config import Config
from src.tools.base import Tool
from src.tools.registry import ToolRegistry


class DummyTool(Tool):
    """Minimal tool implementation for testing."""

    @property
    def name(self) -> str:
        return "dummy"

    @property
    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "dummy",
                "description": "A test tool",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "arg1": {"type": "string", "description": "Test argument"},
                    },
                    "required": ["arg1"],
                },
            },
        }

    def execute(self, **kwargs) -> str:
        return f"dummy result: {kwargs.get('arg1', '')}"


@pytest.fixture
def mock_config():
    """Config with fake API keys."""
    return Config(
        openai_api_key="test-openai-key",
        openai_model="gpt-4o",
        openai_base_url=None,
        brave_search_api_key="test-brave-key",
        agent_host="127.0.0.1",
        agent_port=0,
        telegram_bot_token=None,
        telegram_allowed_chat_ids=[],
        embedding_model="text-embedding-3-large",
        memory_db_path=":memory:",
        soul_path="SOUL.md",
        shell_command_timeout=30,
        shell_max_output=50000,
        context_max_tokens=100000,
        context_preserve_recent=10,
        codex_timeout=300,
        codex_max_output=50000,
        github_token="test-github-token",
        history_path="test_history.json",
    )


@pytest.fixture
def empty_registry():
    """A fresh empty ToolRegistry."""
    return ToolRegistry()


@pytest.fixture
def dummy_tool():
    """A minimal concrete Tool for testing."""
    return DummyTool()
