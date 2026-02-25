"""Tests for src.tools.scheduler — scheduler tool."""

import json

import pytest

from src.scheduler import SchedulerStore
from src.tools.scheduler import SchedulerTool


@pytest.fixture
def store():
    """Fake SchedulerStore backed by an in-memory dict (no DB required)."""
    from datetime import datetime, timezone
    from unittest.mock import MagicMock
    from src.scheduler import compute_next_run
    s = MagicMock(spec=SchedulerStore)
    _data = {}
    _seq = iter(range(1, 10_000))

    def _add(name, prompt, cron_expression, deliver_to="memory", telegram_chat_id=None):
        if name in _data:
            import psycopg2.errors
            raise psycopg2.errors.UniqueViolation("duplicate key")
        task_id = next(_seq)
        now = datetime.now(timezone.utc)
        _data[name] = dict(
            id=task_id, name=name, prompt=prompt, cron_expression=cron_expression,
            enabled=True, deliver_to=deliver_to, telegram_chat_id=telegram_chat_id,
            last_run_at=None,
            next_run_at=compute_next_run(cron_expression, after=now).isoformat(),
            created_at=now.isoformat(),
        )
        return task_id

    def _upsert(name, **kwargs):
        if name in _data:
            _data[name].update(kwargs)
        else:
            _add(name, **kwargs)

    def _toggle(name, enabled):
        if name not in _data:
            return False
        _data[name]["enabled"] = enabled
        return True

    s.add.side_effect = _add
    s.upsert.side_effect = _upsert
    s.list_all.side_effect = lambda: list(_data.values())
    s.get.side_effect = lambda name: _data.get(name)
    s.delete.side_effect = lambda name: bool(_data.pop(name, None))
    s.toggle.side_effect = _toggle
    s.count.side_effect = lambda: len(_data)
    return s


@pytest.fixture
def tool(store):
    return SchedulerTool(store=store)


def test_name(tool):
    assert tool.name == "scheduler"


def test_schema_structure(tool):
    schema = tool.schema
    assert schema["type"] == "function"
    func = schema["function"]
    assert func["name"] == "scheduler"
    props = func["parameters"]["properties"]
    assert "action" in props
    assert "name" in props
    assert "prompt" in props
    assert "schedule" in props
    assert "deliver_to" in props
    assert func["parameters"]["required"] == ["action"]


class TestCreateAction:
    def test_success(self, tool, store):
        result = json.loads(tool.execute(
            action="create",
            name="daily-check",
            prompt="Check open PRs",
            schedule="0 9 * * *",
        ))
        assert result["created"] is True
        assert result["task_id"] == 1
        assert result["next_run_at"] is not None
        assert result["total_tasks"] == 1

    def test_with_telegram(self, tool, store):
        result = json.loads(tool.execute(
            action="create",
            name="tg-report",
            prompt="Send daily report",
            schedule="0 9 * * *",
            deliver_to="telegram",
            telegram_chat_id=12345,
        ))
        assert result["created"] is True
        task = store.get("tg-report")
        assert task["deliver_to"] == "telegram"
        assert task["telegram_chat_id"] == 12345

    def test_with_simple_interval(self, tool, store):
        result = json.loads(tool.execute(
            action="create",
            name="frequent-check",
            prompt="Check status",
            schedule="every 6h",
        ))
        assert result["created"] is True
        assert result["next_run_at"] is not None

    def test_missing_fields(self, tool):
        result = json.loads(tool.execute(action="create", name="test"))
        assert "error" in result

    def test_missing_name(self, tool):
        result = json.loads(tool.execute(
            action="create", prompt="Do stuff", schedule="0 9 * * *"
        ))
        assert "error" in result

    def test_duplicate_name(self, tool):
        tool.execute(
            action="create", name="t", prompt="p", schedule="0 9 * * *"
        )
        result = json.loads(tool.execute(
            action="create", name="t", prompt="p2", schedule="0 10 * * *"
        ))
        assert "error" in result


class TestListAction:
    def test_empty(self, tool):
        result = json.loads(tool.execute(action="list"))
        assert result["tasks"] == []
        assert result["count"] == 0

    def test_with_tasks(self, tool):
        tool.execute(
            action="create", name="t1", prompt="p1", schedule="0 9 * * *"
        )
        tool.execute(
            action="create", name="t2", prompt="p2", schedule="0 10 * * *"
        )
        result = json.loads(tool.execute(action="list"))
        assert result["count"] == 2


class TestDeleteAction:
    def test_success(self, tool):
        tool.execute(
            action="create", name="t", prompt="p", schedule="0 9 * * *"
        )
        result = json.loads(tool.execute(action="delete", name="t"))
        assert result["deleted"] is True

    def test_missing_name(self, tool):
        result = json.loads(tool.execute(action="delete"))
        assert "error" in result

    def test_not_found(self, tool):
        result = json.loads(tool.execute(action="delete", name="nope"))
        assert result["deleted"] is False


class TestEnableAction:
    def test_enable(self, tool, store):
        tool.execute(
            action="create", name="t", prompt="p", schedule="0 9 * * *"
        )
        tool.execute(action="disable", name="t")
        result = json.loads(tool.execute(action="enable", name="t"))
        assert result["toggled"] is True
        assert result["enabled"] is True
        task = store.get("t")
        assert task["enabled"] == 1

    def test_missing_name(self, tool):
        result = json.loads(tool.execute(action="enable"))
        assert "error" in result


class TestDisableAction:
    def test_disable(self, tool, store):
        tool.execute(
            action="create", name="t", prompt="p", schedule="0 9 * * *"
        )
        result = json.loads(tool.execute(action="disable", name="t"))
        assert result["toggled"] is True
        assert result["enabled"] is False
        task = store.get("t")
        assert task["enabled"] == 0

    def test_missing_name(self, tool):
        result = json.loads(tool.execute(action="disable"))
        assert "error" in result

    def test_not_found(self, tool):
        result = json.loads(tool.execute(action="disable", name="nope"))
        assert result["toggled"] is False


class TestUnknownAction:
    def test_returns_error(self, tool):
        result = json.loads(tool.execute(action="frobnicate"))
        assert "error" in result
