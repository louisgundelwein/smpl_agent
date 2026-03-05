"""Shared test fixtures."""

from unittest.mock import MagicMock

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
        embedding_dimensions=1024,
        database_url="postgresql://test:test@localhost:5432/test",
        soul_path="SOUL.md",
        shell_command_timeout=30,
        shell_max_output=50000,
        context_max_tokens=100000,
        context_preserve_recent=10,
        codex_timeout=300,
        codex_max_output=50000,
        github_token="test-github-token",
        whisper_model="openai/whisper-large-v3-turbo",
        max_tool_rounds=25,
        max_continuations=20,
        daemon_pid_path="test_agent.pid",
        daemon_log_path="test_agent.log",
        scheduler_poll_interval=30,
        scheduler_tasks="",
        max_subagents=10,
        subagent_tool_rounds=15,
        auto_memory=True,
        auto_memory_extract_interval=3,
        auto_recall_threshold=0.55,
        auto_recall_top_k=5,
        browser_use_enabled=False,
        browser_use_timeout=300,
        browser_use_recording_dir="test_browser_recordings",
        temp_file_ttl_hours=72,
        marketing_enabled=False,
    )


@pytest.fixture
def mock_db():
    """Mock Database that returns mock connections with RealDictCursor-like behavior."""
    db = MagicMock()
    conn = MagicMock()
    cursor = MagicMock()

    # Make cursor work as context manager
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    db.get_connection.return_value = conn
    db._mock_conn = conn
    db._mock_cursor = cursor

    return db


@pytest.fixture
def empty_registry():
    """A fresh empty ToolRegistry."""
    return ToolRegistry()


@pytest.fixture
def dummy_tool():
    """A minimal concrete Tool for testing."""
    return DummyTool()
