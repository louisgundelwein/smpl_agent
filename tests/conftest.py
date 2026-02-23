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
    )


@pytest.fixture
def empty_registry():
    """A fresh empty ToolRegistry."""
    return ToolRegistry()


@pytest.fixture
def dummy_tool():
    """A minimal concrete Tool for testing."""
    return DummyTool()
