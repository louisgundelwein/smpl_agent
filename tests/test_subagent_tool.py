"""Tests for SubagentTool."""

import json
from unittest.mock import MagicMock

import pytest

from src.subagent import SubagentState, SubagentStatus
from src.tools.subagent import SubagentTool


@pytest.fixture
def mock_manager():
    return MagicMock()


@pytest.fixture
def tool(mock_manager):
    return SubagentTool(manager=mock_manager)


class TestSubagentTool:
    def test_name(self, tool):
        assert tool.name == "subagent"

    def test_schema_structure(self, tool):
        schema = tool.schema
        assert schema["type"] == "function"
        func = schema["function"]
        assert func["name"] == "subagent"
        params = func["parameters"]
        assert "action" in params["properties"]
        assert params["properties"]["action"]["enum"] == [
            "spawn",
            "status",
            "result",
            "cancel",
        ]
        assert "task" in params["properties"]
        assert "subagent_id" in params["properties"]
        assert params["required"] == ["action"]

    def test_spawn_success(self, tool, mock_manager):
        state = SubagentState(id="abc12345", task="do research")
        mock_manager.spawn.return_value = state
        mock_manager.active_count.return_value = 1
        result = json.loads(tool.execute(action="spawn", task="do research"))
        assert result["spawned"] is True
        assert result["subagent_id"] == "abc12345"
        assert result["task"] == "do research"
        assert result["active_count"] == 1
        mock_manager.spawn.assert_called_once_with("do research")

    def test_spawn_missing_task(self, tool):
        result = json.loads(tool.execute(action="spawn"))
        assert "error" in result
        assert "task is required" in result["error"]

    def test_spawn_max_concurrent_error(self, tool, mock_manager):
        mock_manager.spawn.side_effect = RuntimeError("Maximum concurrent subagents (10) reached")
        result = json.loads(tool.execute(action="spawn", task="test"))
        assert "error" in result
        assert "Maximum concurrent" in result["error"]

    def test_status_all(self, tool, mock_manager):
        mock_manager.get_status.return_value = [
            {"id": "a", "status": "running"},
            {"id": "b", "status": "completed"},
        ]
        result = json.loads(tool.execute(action="status"))
        assert len(result["subagents"]) == 2
        mock_manager.get_status.assert_called_once_with(None)

    def test_status_specific(self, tool, mock_manager):
        mock_manager.get_status.return_value = [{"id": "abc", "status": "running"}]
        result = json.loads(tool.execute(action="status", subagent_id="abc"))
        assert len(result["subagents"]) == 1
        mock_manager.get_status.assert_called_once_with("abc")

    def test_result_success(self, tool, mock_manager):
        mock_manager.get_result.return_value = {
            "id": "abc",
            "status": "completed",
            "result": "found 5 items",
        }
        result = json.loads(tool.execute(action="result", subagent_id="abc"))
        assert result["status"] == "completed"
        assert result["result"] == "found 5 items"

    def test_result_missing_id(self, tool):
        result = json.loads(tool.execute(action="result"))
        assert "error" in result
        assert "subagent_id is required" in result["error"]

    def test_cancel_success(self, tool, mock_manager):
        mock_manager.cancel.return_value = {"id": "abc", "cancelled": True}
        result = json.loads(tool.execute(action="cancel", subagent_id="abc"))
        assert result["cancelled"] is True

    def test_cancel_missing_id(self, tool):
        result = json.loads(tool.execute(action="cancel"))
        assert "error" in result
        assert "subagent_id is required" in result["error"]

    def test_unknown_action(self, tool):
        result = json.loads(tool.execute(action="frobnicate"))
        assert "error" in result
        assert "Unknown action" in result["error"]
