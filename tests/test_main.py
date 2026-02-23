"""Tests for src.main helper functions."""

import os

import pytest

from src.agent import SYSTEM_PROMPT
from src.main import _build_system_context, _load_system_prompt


def test_load_system_prompt_reads_existing_file(tmp_path):
    soul = tmp_path / "SOUL.md"
    soul.write_text("You are a pirate.", encoding="utf-8")

    result = _load_system_prompt(str(soul))

    assert result == "You are a pirate."


def test_load_system_prompt_strips_whitespace(tmp_path):
    soul = tmp_path / "SOUL.md"
    soul.write_text("  \n  Hello soul.  \n  ", encoding="utf-8")

    result = _load_system_prompt(str(soul))

    assert result == "Hello soul."


def test_load_system_prompt_falls_back_when_file_missing():
    result = _load_system_prompt("/nonexistent/path/SOUL.md")

    assert result == SYSTEM_PROMPT


def test_load_system_prompt_falls_back_when_file_empty(tmp_path):
    soul = tmp_path / "SOUL.md"
    soul.write_text("   \n   ", encoding="utf-8")

    result = _load_system_prompt(str(soul))

    assert result == SYSTEM_PROMPT


def test_build_system_context_contains_required_fields():
    result = _build_system_context()
    assert "OS:" in result
    assert "Shell:" in result
    assert "Working directory:" in result
    assert "Home directory:" in result


def test_build_system_context_starts_with_section_header():
    result = _build_system_context()
    assert result.startswith("\n\n## Environment\n\n")


def test_build_system_context_cwd_matches_os():
    result = _build_system_context()
    assert os.getcwd() in result


def test_build_system_context_darwin_shows_macos(mocker):
    mocker.patch("src.main.platform.system", return_value="Darwin")
    mocker.patch("src.main.platform.release", return_value="23.1.0")
    mocker.patch.dict(os.environ, {"SHELL": "/bin/zsh"})

    result = _build_system_context()
    assert "macOS 23.1.0" in result
    assert "Darwin" not in result


def test_print_event_formats_and_prints(capsys):
    from src.events import ToolStartEvent
    from src.main import _print_event

    event = ToolStartEvent(tool_name="shell", arguments={"command": "ls"})
    _print_event(event)
    out = capsys.readouterr().out
    assert "[tool] shell" in out
    assert "command='ls'" in out
