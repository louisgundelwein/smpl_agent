"""Tests for src.tools.memory."""

import json

import pytest
from unittest.mock import MagicMock

from src.tools.memory import MemoryTool


@pytest.fixture
def mock_store():
    return MagicMock()


@pytest.fixture
def tool(mock_store):
    return MemoryTool(memory_store=mock_store)


def test_name(tool):
    assert tool.name == "memory"


def test_schema_structure(tool):
    schema = tool.schema
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "memory"
    props = schema["function"]["parameters"]["properties"]
    assert "action" in props
    assert "content" in props
    assert "tags" in props
    assert "memory_id" in props
    assert "top_k" in props
    assert "action" in schema["function"]["parameters"]["required"]


def test_store_action(tool, mock_store):
    mock_store.add.return_value = 42
    mock_store.count.return_value = 10

    result = json.loads(tool.execute(action="store", content="remember this"))

    assert result["stored"] is True
    assert result["memory_id"] == 42
    assert result["total_memories"] == 10
    mock_store.add.assert_called_once_with(content="remember this", tags=None)


def test_store_action_with_tags(tool, mock_store):
    mock_store.add.return_value = 1
    mock_store.count.return_value = 1

    result = json.loads(
        tool.execute(action="store", content="tagged", tags=["a", "b"])
    )

    assert result["stored"] is True
    mock_store.add.assert_called_once_with(content="tagged", tags=["a", "b"])


def test_store_action_missing_content(tool):
    result = json.loads(tool.execute(action="store"))
    assert "error" in result


def test_search_action(tool, mock_store):
    mock_store.search.return_value = [
        {"id": 1, "content": "found it", "tags": [], "score": 0.95}
    ]

    result = json.loads(tool.execute(action="search", content="find something"))

    assert result["count"] == 1
    assert result["results"][0]["content"] == "found it"
    mock_store.search.assert_called_once_with(query="find something", top_k=5)


def test_search_action_custom_top_k(tool, mock_store):
    mock_store.search.return_value = []

    tool.execute(action="search", content="query", top_k=10)

    mock_store.search.assert_called_once_with(query="query", top_k=10)


def test_search_action_missing_content(tool):
    result = json.loads(tool.execute(action="search"))
    assert "error" in result


def test_delete_action(tool, mock_store):
    mock_store.delete.return_value = True

    result = json.loads(tool.execute(action="delete", memory_id=5))

    assert result["deleted"] is True
    assert result["memory_id"] == 5
    mock_store.delete.assert_called_once_with(memory_id=5)


def test_delete_action_missing_id(tool):
    result = json.loads(tool.execute(action="delete"))
    assert "error" in result


def test_unknown_action(tool):
    result = json.loads(tool.execute(action="purge"))
    assert "error" in result
    assert "Unknown action" in result["error"]


def test_exception_returns_error_json(tool, mock_store):
    mock_store.add.side_effect = RuntimeError("db locked")

    result = json.loads(tool.execute(action="store", content="test"))
    assert "error" in result
    assert "db locked" in result["error"]


# --- cleanup action tests ---


def test_schema_includes_cleanup():
    """Schema includes cleanup in action enum and threshold property."""
    tool = MemoryTool(memory_store=MagicMock())
    schema = tool.schema
    props = schema["function"]["parameters"]["properties"]
    assert "cleanup" in props["action"]["enum"]
    assert "threshold" in props


def test_cleanup_action_without_auto_memory(mock_store):
    """Cleanup returns error when auto_memory is not configured."""
    tool = MemoryTool(memory_store=mock_store, auto_memory=None)
    result = json.loads(tool.execute(action="cleanup"))
    assert "error" in result
    assert "auto_memory" in result["error"]


def test_cleanup_action_success():
    """Cleanup delegates to auto_memory.cleanup_duplicates()."""
    mock_store = MagicMock()
    mock_auto_memory = MagicMock()
    mock_auto_memory.cleanup_duplicates.return_value = [
        {
            "merged_id": 10,
            "deleted_ids": [1, 2],
            "content": "User prefers Python for scripting tasks.",
        }
    ]
    tool = MemoryTool(memory_store=mock_store, auto_memory=mock_auto_memory)

    result = json.loads(tool.execute(action="cleanup"))
    assert result["groups_merged"] == 1
    assert result["total_deleted"] == 2
    assert len(result["merges"]) == 1
    mock_auto_memory.cleanup_duplicates.assert_called_once_with(threshold=0.90)


def test_cleanup_action_custom_threshold():
    """Cleanup passes custom threshold to auto_memory."""
    mock_store = MagicMock()
    mock_auto_memory = MagicMock()
    mock_auto_memory.cleanup_duplicates.return_value = []
    tool = MemoryTool(memory_store=mock_store, auto_memory=mock_auto_memory)

    tool.execute(action="cleanup", threshold=0.85)
    mock_auto_memory.cleanup_duplicates.assert_called_once_with(threshold=0.85)
