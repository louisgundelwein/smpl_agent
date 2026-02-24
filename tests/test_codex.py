"""Tests for src.tools.codex."""

import json
import os
import subprocess

import pytest

from src.tools.codex import CodexTool


@pytest.fixture
def tool():
    return CodexTool(timeout=300, max_output=50000)


def test_name(tool):
    assert tool.name == "codex"


def test_schema_structure(tool):
    schema = tool.schema
    assert schema["type"] == "function"
    func = schema["function"]
    assert func["name"] == "codex"
    props = func["parameters"]["properties"]
    assert "prompt" in props
    assert "cwd" in props
    assert func["parameters"]["required"] == ["prompt"]


def test_execute_success(tool, mocker):
    events = "\n".join([
        json.dumps({"type": "status", "content": "working..."}),
        json.dumps({"type": "message", "content": "Created main.py with hello world."}),
    ])
    mock_run = mocker.patch("subprocess.run", return_value=subprocess.CompletedProcess(
        args=[], returncode=0, stdout=events, stderr="",
    ))

    result = json.loads(tool.execute(prompt="Write hello world"))

    assert result["result"] == "Created main.py with hello world."
    # Verify prompt was passed via stdin
    assert mock_run.call_args.kwargs["input"] == "Write hello world"


def test_execute_with_cwd(tool, mocker):
    events = json.dumps({"type": "message", "content": "done"})
    mock_run = mocker.patch("subprocess.run", return_value=subprocess.CompletedProcess(
        args=[], returncode=0, stdout=events, stderr="",
    ))

    tool.execute(prompt="fix bugs", cwd="/home/user/project")

    assert mock_run.call_args.kwargs["cwd"] == "/home/user/project"


def test_execute_missing_prompt(tool):
    result = json.loads(tool.execute())
    assert "error" in result
    assert "prompt" in result["error"].lower()


def test_execute_timeout(tool, mocker):
    mocker.patch("subprocess.run", side_effect=subprocess.TimeoutExpired(
        cmd="codex", timeout=300,
    ))

    result = json.loads(tool.execute(prompt="long task"))

    assert "error" in result
    assert "timed out" in result["error"]
    assert "300" in result["error"]


def test_execute_not_found(tool, mocker):
    mocker.patch("subprocess.run", side_effect=FileNotFoundError())

    result = json.loads(tool.execute(prompt="write code"))

    assert "error" in result
    assert "not found" in result["error"].lower()
    assert "npm install" in result["error"]


def test_execute_fallback_no_message_event(tool, mocker):
    """When no structured message event is found, return raw stdout."""
    mocker.patch("subprocess.run", return_value=subprocess.CompletedProcess(
        args=[], returncode=0, stdout="Some raw text output", stderr="",
    ))

    result = json.loads(tool.execute(prompt="do something"))

    assert result["result"] == "Some raw text output"


def test_execute_stderr_fallback(tool, mocker):
    """When stdout is empty, fall back to stderr."""
    mocker.patch("subprocess.run", return_value=subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="Authentication required",
    ))

    result = json.loads(tool.execute(prompt="do something"))

    assert result["result"] == "Authentication required"


def test_execute_truncation(mocker):
    small_tool = CodexTool(timeout=300, max_output=2000)
    long_content = "A" * 5000
    events = json.dumps({"type": "message", "content": long_content})
    mocker.patch("subprocess.run", return_value=subprocess.CompletedProcess(
        args=[], returncode=0, stdout=events, stderr="",
    ))

    result = json.loads(small_tool.execute(prompt="generate"))

    assert len(result["result"]) <= 2000
    assert "TRUNCATED" in result["result"]


def test_command_structure(tool, mocker):
    """Verify the subprocess command uses codex exec --json -."""
    events = json.dumps({"type": "message", "content": "ok"})
    mock_run = mocker.patch("subprocess.run", return_value=subprocess.CompletedProcess(
        args=[], returncode=0, stdout=events, stderr="",
    ))

    tool.execute(prompt="test")

    cmd = mock_run.call_args[0][0]
    assert cmd == ["codex", "exec", "--json", "-"]


def test_exception_returns_error_json(tool, mocker):
    mocker.patch("subprocess.run", side_effect=OSError("something broke"))

    result = json.loads(tool.execute(prompt="test"))

    assert "error" in result
    assert "something broke" in result["error"]


def test_env_strips_openai_vars(tool, mocker):
    """Codex must not inherit OPENAI_BASE_URL or OPENAI_API_KEY from the agent."""
    mocker.patch.dict(os.environ, {
        "OPENAI_BASE_URL": "https://custom.example.com/v1",
        "OPENAI_API_KEY": "sk-secret",
        "HOME": "/home/test",
    })
    events = json.dumps({"type": "message", "content": "ok"})
    mock_run = mocker.patch("subprocess.run", return_value=subprocess.CompletedProcess(
        args=[], returncode=0, stdout=events, stderr="",
    ))

    tool.execute(prompt="test")

    env_passed = mock_run.call_args.kwargs["env"]
    assert "OPENAI_BASE_URL" not in env_passed
    assert "OPENAI_API_KEY" not in env_passed
    assert env_passed["HOME"] == "/home/test"
