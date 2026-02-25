"""Tests for src.scheduler — scheduled task store and polling loop (Postgres, cursor-mocked)."""

import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call

import pytest

from src.scheduler import Scheduler, SchedulerStore, _parse_simple_interval, compute_next_run


# --- Simple interval parsing ---


class TestParseSimpleInterval:
    def test_every_30m(self):
        assert _parse_simple_interval("every 30m") == "*/30 * * * *"

    def test_every_6h(self):
        assert _parse_simple_interval("every 6h") == "0 */6 * * *"

    def test_every_1d(self):
        assert _parse_simple_interval("every 1d") == "0 0 */1 * *"

    def test_not_interval(self):
        assert _parse_simple_interval("0 9 * * *") is None

    def test_invalid_number(self):
        assert _parse_simple_interval("every abcm") is None

    def test_case_insensitive(self):
        assert _parse_simple_interval("Every 5H") == "0 */5 * * *"


class TestComputeNextRun:
    def test_cron_daily_at_9(self):
        ref = datetime(2025, 6, 15, 8, 0, 0, tzinfo=timezone.utc)
        next_run = compute_next_run("0 9 * * *", after=ref)
        assert next_run.hour == 9
        assert next_run.day == 15

    def test_cron_past_today_goes_tomorrow(self):
        ref = datetime(2025, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        next_run = compute_next_run("0 9 * * *", after=ref)
        assert next_run.day == 16

    def test_simple_interval(self):
        ref = datetime(2025, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        next_run = compute_next_run("every 6h", after=ref)
        assert next_run > ref

    def test_result_is_utc(self):
        next_run = compute_next_run("0 9 * * *")
        assert next_run.tzinfo is not None


# --- SchedulerStore ---


def _make_store():
    """Create a SchedulerStore with a mock Database."""
    db = MagicMock()
    conn = MagicMock()
    cursor = MagicMock()

    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    db.get_connection.return_value = conn

    cursor.execute.return_value = None
    store = SchedulerStore(db=db)
    return store, db, conn, cursor


def _sample_task(
    id=1, name="daily-check", prompt="Check open PRs",
    cron_expression="0 9 * * *", enabled=True, deliver_to="memory",
    telegram_chat_id=None, last_run_at=None,
    next_run_at="2025-06-16T09:00:00+00:00",
    created_at="2025-06-15T08:00:00+00:00",
):
    return {
        "id": id, "name": name, "prompt": prompt,
        "cron_expression": cron_expression, "enabled": enabled,
        "deliver_to": deliver_to, "telegram_chat_id": telegram_chat_id,
        "last_run_at": last_run_at, "next_run_at": next_run_at,
        "created_at": created_at,
    }


class TestSchedulerStoreAdd:
    def test_returns_id(self):
        store, db, conn, cursor = _make_store()
        cursor.fetchone.return_value = {"id": 1}
        task_id = store.add(name="daily-check", prompt="Check open PRs", cron_expression="0 9 * * *")
        assert task_id == 1
        conn.commit.assert_called()

    def test_duplicate_name_raises(self):
        store, db, conn, cursor = _make_store()
        import psycopg2.errors
        cursor.execute.side_effect = psycopg2.errors.UniqueViolation("duplicate")
        with pytest.raises(psycopg2.errors.UniqueViolation):
            store.add(name="daily-check", prompt="Check open PRs", cron_expression="0 9 * * *")

    def test_with_telegram(self):
        store, db, conn, cursor = _make_store()
        cursor.fetchone.return_value = {"id": 1}
        store.add(
            name="tg-task", prompt="Send report",
            cron_expression="0 9 * * *", deliver_to="telegram",
            telegram_chat_id=12345,
        )
        cursor.fetchone.return_value = _sample_task(
            name="tg-task", deliver_to="telegram", telegram_chat_id=12345,
        )
        task = store.get("tg-task")
        assert task["deliver_to"] == "telegram"
        assert task["telegram_chat_id"] == 12345


class TestSchedulerStoreListAll:
    def test_empty(self):
        store, db, conn, cursor = _make_store()
        cursor.fetchall.return_value = []
        assert store.list_all() == []

    def test_returns_all(self):
        store, db, conn, cursor = _make_store()
        cursor.fetchall.return_value = [_sample_task(id=1, name="task1"), _sample_task(id=2, name="task2")]
        assert len(store.list_all()) == 2


class TestSchedulerStoreGetDue:
    def test_returns_due_tasks(self):
        store, db, conn, cursor = _make_store()
        cursor.fetchall.return_value = [_sample_task(next_run_at="2020-01-01T00:00:00+00:00")]
        due = store.get_due()
        assert len(due) == 1

    def test_skips_disabled(self):
        store, db, conn, cursor = _make_store()
        cursor.fetchall.return_value = []
        assert store.get_due() == []


class TestSchedulerStoreMarkRun:
    def test_updates_timestamps(self):
        store, db, conn, cursor = _make_store()
        now = datetime(2025, 6, 15, 9, 0, 0, tzinfo=timezone.utc)
        cursor.fetchone.return_value = {"cron_expression": "0 9 * * *"}
        store.mark_run(1, now=now)
        conn.commit.assert_called()

    def test_nonexistent_task_noop(self):
        store, db, conn, cursor = _make_store()
        cursor.fetchone.return_value = None
        store.mark_run(999)


class TestSchedulerStoreDelete:
    def test_deletes_existing(self):
        store, db, conn, cursor = _make_store()
        cursor.rowcount = 1
        assert store.delete("daily-check") is True

    def test_returns_false_for_missing(self):
        store, db, conn, cursor = _make_store()
        cursor.rowcount = 0
        assert store.delete("nonexistent") is False


class TestSchedulerStoreToggle:
    def test_disable(self):
        store, db, conn, cursor = _make_store()
        cursor.rowcount = 1
        assert store.toggle("daily-check", enabled=False) is True
        conn.commit.assert_called()

    def test_returns_false_for_missing(self):
        store, db, conn, cursor = _make_store()
        cursor.rowcount = 0
        assert store.toggle("nonexistent", enabled=False) is False


class TestSchedulerStoreUpsert:
    def test_inserts_new(self):
        store, db, conn, cursor = _make_store()
        # get returns None (not found) → insert
        cursor.fetchone.side_effect = [None, {"id": 1}]
        task_id = store.upsert("new-task", "Do something", "0 9 * * *")
        assert task_id == 1

    def test_skips_existing(self):
        store, db, conn, cursor = _make_store()
        cursor.fetchone.return_value = _sample_task(id=5, name="my-task")
        task_id = store.upsert("my-task", "Different prompt", "0 10 * * *")
        assert task_id == 5


class TestSchedulerStoreCount:
    def test_returns_count(self):
        store, db, conn, cursor = _make_store()
        cursor.fetchone.return_value = {"cnt": 3}
        assert store.count() == 3


# --- Scheduler polling loop ---


class TestSchedulerRunTask:
    def test_runs_agent_and_marks_done(self):
        store, db, conn, cursor = _make_store()
        mock_agent = MagicMock()
        mock_agent.run.return_value = "PR summary: 3 open PRs"
        lock = threading.Lock()

        # mark_run needs a cron_expression row
        cursor.fetchone.return_value = {"cron_expression": "0 9 * * *"}

        scheduler = Scheduler(store=store, poll_interval=1)
        task = _sample_task()
        scheduler._run_task(task, mock_agent, lock)

        mock_agent.run.assert_called_once()
        prompt_arg = mock_agent.run.call_args[0][0]
        assert "daily-check" in prompt_arg
        assert "Check open PRs" in prompt_arg
        conn.commit.assert_called()

    def test_delivers_to_telegram(self):
        store, db, conn, cursor = _make_store()
        mock_agent = MagicMock()
        mock_agent.run.return_value = "Daily report content"
        mock_send = MagicMock()
        lock = threading.Lock()

        cursor.fetchone.return_value = {"cron_expression": "0 9 * * *"}

        scheduler = Scheduler(store=store, telegram_send=mock_send)
        task = _sample_task(name="tg-task", deliver_to="telegram", telegram_chat_id=42)
        scheduler._run_task(task, mock_agent, lock)

        mock_send.assert_called_once()
        call_args = mock_send.call_args[0]
        assert call_args[0] == 42
        assert "Daily report content" in call_args[1]

    def test_handles_agent_error(self):
        store, db, conn, cursor = _make_store()
        mock_agent = MagicMock()
        mock_agent.run.side_effect = RuntimeError("LLM down")
        lock = threading.Lock()

        cursor.fetchone.return_value = {"cron_expression": "0 9 * * *"}

        scheduler = Scheduler(store=store)
        task = _sample_task()
        # Should not raise
        scheduler._run_task(task, mock_agent, lock)
        conn.commit.assert_called()
