"""Tests for src.tools.browser."""

import asyncio
import json

import pytest

from src.tools.browser import BrowserTool


@pytest.fixture
def tool(tmp_path):
    return BrowserTool(
        openai_api_key="test-key",
        openai_model="gpt-4o",
        recording_dir=str(tmp_path / "recordings"),
        timeout=60,
    )


def test_name(tool):
    assert tool.name == "browser"


def test_schema_structure(tool):
    schema = tool.schema
    assert schema["type"] == "function"
    func = schema["function"]
    assert func["name"] == "browser"
    assert "task" in func["parameters"]["properties"]
    assert "url" in func["parameters"]["properties"]
    assert func["parameters"]["required"] == ["task"]


def test_missing_task(tool):
    result = json.loads(tool.execute())
    assert "error" in result
    assert "task" in result["error"].lower()


def test_import_error(tool, mocker):
    mocker.patch(
        "src.tools.browser.asyncio.run",
        side_effect=ImportError("No module named 'browser_use'"),
    )
    result = json.loads(tool.execute(task="test"))
    assert "error" in result
    assert "not installed" in result["error"]


def test_timeout_error(tool, mocker):
    mocker.patch(
        "src.tools.browser.asyncio.run",
        side_effect=asyncio.TimeoutError(),
    )
    result = json.loads(tool.execute(task="test"))
    assert "error" in result
    assert "timed out" in result["error"]


def test_generic_error(tool, mocker):
    mocker.patch(
        "src.tools.browser.asyncio.run",
        side_effect=RuntimeError("something broke"),
    )
    result = json.loads(tool.execute(task="test"))
    assert "error" in result
    assert "something broke" in result["error"]


def test_successful_execution(tool, mocker):
    mocker.patch(
        "src.tools.browser.asyncio.run",
        return_value={
            "result": "Task completed",
            "session_id": "abc123",
            "recording_path": "/tmp/rec.webm",
        },
    )
    result = json.loads(tool.execute(task="go to example.com"))
    assert result["result"] == "Task completed"
    assert result["session_id"] == "abc123"
    assert result["recording_path"] == "/tmp/rec.webm"


def test_find_recording_in_directory(tmp_path):
    rec_dir = tmp_path / "session_abc"
    rec_dir.mkdir()
    video = rec_dir / "video.webm"
    video.write_bytes(b"fake video")

    found = BrowserTool._find_recording(str(rec_dir))
    assert found == video


def test_find_recording_direct_file(tmp_path):
    video = tmp_path / "recording.webm"
    video.write_bytes(b"fake video")

    found = BrowserTool._find_recording(str(video))
    assert found == video


def test_find_recording_missing(tmp_path):
    found = BrowserTool._find_recording(str(tmp_path / "nonexistent"))
    assert found is None


def test_find_recording_empty_dir(tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    found = BrowserTool._find_recording(str(empty_dir))
    assert found is None


def test_recording_dir_created(tmp_path):
    rec_dir = tmp_path / "new_recordings"
    assert not rec_dir.exists()
    BrowserTool(
        openai_api_key="key",
        openai_model="model",
        recording_dir=str(rec_dir),
    )
    assert rec_dir.exists()
