"""Tests for src.tools.shell."""

import json
import subprocess

import pytest

from src.tools.shell import ShellTool


@pytest.fixture
def tool():
    return ShellTool(command_timeout=5, max_output=200)


def test_name(tool):
    assert tool.name == "shell"


def test_schema_structure(tool):
    schema = tool.schema
    assert schema["type"] == "function"
    func = schema["function"]
    assert func["name"] == "shell"
    props = func["parameters"]["properties"]
    assert "command" in props
    assert "timeout" in props
    assert "cwd" in props
    assert func["parameters"]["required"] == ["command"]


def test_execute_success(tool, mocker):
    mock_run = mocker.patch("src.tools.shell.subprocess.run")
    mock_run.return_value = mocker.MagicMock(
        returncode=0, stdout="hello\n", stderr=""
    )

    result = json.loads(tool.execute(command="echo hello"))

    assert result["exit_code"] == 0
    assert result["stdout"] == "hello\n"
    assert result["stderr"] == ""


def test_execute_with_stderr(tool, mocker):
    mock_run = mocker.patch("src.tools.shell.subprocess.run")
    mock_run.return_value = mocker.MagicMock(
        returncode=1, stdout="", stderr="not found\n"
    )

    result = json.loads(tool.execute(command="bad_command"))

    assert result["exit_code"] == 1
    assert result["stderr"] == "not found\n"


def test_execute_missing_command(tool):
    result = json.loads(tool.execute())

    assert "error" in result
    assert "command" in result["error"].lower()


def test_execute_timeout(tool, mocker):
    mock_run = mocker.patch("src.tools.shell.subprocess.run")
    mock_run.side_effect = subprocess.TimeoutExpired(
        cmd="sleep 100", timeout=5, output="partial", stderr=""
    )

    result = json.loads(tool.execute(command="sleep 100"))

    assert "timed out" in result["error"]
    assert "5s" in result["error"]


def test_execute_custom_timeout_and_cwd(tool, mocker):
    mock_run = mocker.patch("src.tools.shell.subprocess.run")
    mock_run.return_value = mocker.MagicMock(
        returncode=0, stdout="ok", stderr=""
    )

    tool.execute(command="ls", timeout=60, cwd="/tmp")

    mock_run.assert_called_once_with(
        "ls",
        shell=True,
        capture_output=True,
        text=True,
        timeout=60,
        cwd="/tmp",
    )


def test_execute_oserror(tool, mocker):
    mock_run = mocker.patch("src.tools.shell.subprocess.run")
    mock_run.side_effect = OSError("No such file or directory")

    result = json.loads(tool.execute(command="nonexistent"))

    assert "error" in result
    assert "No such file or directory" in result["error"]


def test_truncation():
    tool = ShellTool(command_timeout=5, max_output=2000)

    long_text = "A" * 5000
    truncated = tool._truncate(long_text)

    assert len(truncated) <= 2000
    assert "TRUNCATED" in truncated
    assert "5000 chars total" in truncated
    # Starts with the head (first 1000 chars preserved)
    assert truncated.startswith("A" * 1000)


def test_no_truncation_when_short(tool):
    short_text = "hello"
    assert tool._truncate(short_text) == "hello"


def test_exception_returns_error_json(tool, mocker):
    mock_run = mocker.patch("src.tools.shell.subprocess.run")
    mock_run.side_effect = RuntimeError("unexpected failure")

    result = json.loads(tool.execute(command="anything"))

    assert result["error"] == "unexpected failure"
