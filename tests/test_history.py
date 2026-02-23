"""Tests for src.history."""

import json
import os

import pytest

from src.history import ConversationHistory


@pytest.fixture
def history_path(tmp_path):
    """Return a temporary file path for history."""
    return str(tmp_path / "test_history.json")


@pytest.fixture
def history(history_path):
    """ConversationHistory pointed at a temp file."""
    return ConversationHistory(history_path)


def test_save_and_load_round_trip(history):
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    history.save(messages)
    loaded = history.load()

    assert loaded == messages


def test_load_nonexistent_returns_none(history):
    assert history.load() is None


def test_clear_deletes_file(history, history_path):
    messages = [{"role": "system", "content": "sys"}]
    history.save(messages)
    assert os.path.exists(history_path)

    history.clear()

    assert not os.path.exists(history_path)


def test_clear_nonexistent_does_not_raise(history):
    history.clear()  # should not raise


def test_save_creates_parent_dirs(tmp_path):
    nested_path = str(tmp_path / "sub" / "dir" / "history.json")
    history = ConversationHistory(nested_path)
    messages = [{"role": "system", "content": "sys"}]

    history.save(messages)

    assert history.load() == messages


def test_load_corrupt_json_returns_none(history, history_path):
    with open(history_path, "w") as f:
        f.write("{truncated")

    assert history.load() is None


def test_load_invalid_structure_returns_none(history, history_path):
    with open(history_path, "w") as f:
        json.dump({"not": "a list"}, f)

    assert history.load() is None


def test_load_empty_list_returns_none(history, history_path):
    with open(history_path, "w") as f:
        json.dump([], f)

    assert history.load() is None


def test_load_missing_system_role_returns_none(history, history_path):
    with open(history_path, "w") as f:
        json.dump([{"role": "user", "content": "hi"}], f)

    assert history.load() is None


def test_save_overwrites_existing(history):
    messages1 = [{"role": "system", "content": "v1"}]
    messages2 = [
        {"role": "system", "content": "v2"},
        {"role": "user", "content": "hi"},
    ]

    history.save(messages1)
    history.save(messages2)

    assert history.load() == messages2


def test_compressed_messages_persist(history):
    """Context-compressed messages (containing summary) round-trip correctly."""
    messages = [
        {"role": "system", "content": "sys"},
        {
            "role": "system",
            "content": (
                "[Conversation Summary]\n"
                "- key facts here\n"
                "[End of Summary]"
            ),
        },
        {"role": "user", "content": "recent"},
        {"role": "assistant", "content": "reply"},
    ]

    history.save(messages)

    assert history.load() == messages
