"""Tests for src.scheduler — scheduled task store and polling loop."""

import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

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


@pytest.fixture
def store():
    """SchedulerStore backed by in-memory SQLite."""
    return SchedulerStore(db_path=":memory:")


def _add_sample(store, name="daily-check", cron="0 9 * * *"):
    return store.add(
        name=name,
        prompt="Check open PRs",
        cron_expression=cron,
        deliver_to="memory",
    )


class TestSchedulerStoreAdd:
    def test_returns_id(self, store):
        task_id = _add_sample(store)
        assert task_id == 1

    def test_increments_ids(self, store):
        id1 = _add_sample(store, "task1")
        id2 = _add_sample(store, "task2")
        assert id2 > id1

    def test_duplicate_name_raises(self, store):
        _add_sample(store)
        with pytest.raises(Exception):
            _add_sample(store)

    def test_computes_next_run(self, store):
        _add_sample(store)
        task = store.get("daily-check")
        assert task["next_run_at"] is not None

    def test_with_telegram(self, store):
        store.add(
            name="tg-task",
            prompt="Send report",
            cron_expression="0 9 * * *",
            deliver_to="telegram",
            telegram_chat_id=12345,
        )
        task = store.get("tg-task")
        assert task["deliver_to"] == "telegram"
        assert task["telegram_chat_id"] == 12345


class TestSchedulerStoreListAll:
    def test_empty(self, store):
        assert store.list_all() == []

    def test_returns_all(self, store):
        _add_sample(store, "task1")
        _add_sample(store, "task2")
        assert len(store.list_all()) == 2


class TestSchedulerStoreGetDue:
    def test_returns_due_tasks(self, store):
        _add_sample(store)
        # Set next_run_at to the past
        store._conn.execute(
            "UPDATE schedules SET next_run_at = ?",
            (datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat(),),
        )
        store._conn.commit()

        due = store.get_due()
        assert len(due) == 1

    def test_skips_disabled(self, store):
        _add_sample(store)
        store._conn.execute(
            "UPDATE schedules SET next_run_at = ?, enabled = 0",
            (datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat(),),
        )
        store._conn.commit()

        assert store.get_due() == []

    def test_skips_future(self, store):
        _add_sample(store)
        # next_run_at is in the future by default
        due = store.get_due(now=datetime(2020, 1, 1, tzinfo=timezone.utc))
        assert due == []


class TestSchedulerStoreMarkRun:
    def test_updates_timestamps(self, store):
        task_id = _add_sample(store)
        now = datetime(2025, 6, 15, 9, 0, 0, tzinfo=timezone.utc)

        store.mark_run(task_id, now=now)

        task = store.get("daily-check")
        assert task["last_run_at"] == now.isoformat()
        # next_run_at should be after now
        next_run = datetime.fromisoformat(task["next_run_at"])
        assert next_run > now


class TestSchedulerStoreDelete:
    def test_deletes_existing(self, store):
        _add_sample(store)
        assert store.delete("daily-check") is True
        assert store.get("daily-check") is None

    def test_returns_false_for_missing(self, store):
        assert store.delete("nonexistent") is False


class TestSchedulerStoreToggle:
    def test_disable(self, store):
        _add_sample(store)
        assert store.toggle("daily-check", enabled=False) is True
        task = store.get("daily-check")
        assert task["enabled"] == 0

    def test_enable(self, store):
        _add_sample(store)
        store.toggle("daily-check", enabled=False)
        store.toggle("daily-check", enabled=True)
        task = store.get("daily-check")
        assert task["enabled"] == 1

    def test_returns_false_for_missing(self, store):
        assert store.toggle("nonexistent", enabled=False) is False


class TestSchedulerStoreUpsert:
    def test_inserts_new(self, store):
        task_id = store.upsert("new-task", "Do something", "0 9 * * *")
        assert task_id == 1

    def test_skips_existing(self, store):
        id1 = store.upsert("my-task", "Do something", "0 9 * * *")
        id2 = store.upsert("my-task", "Different prompt", "0 10 * * *")
        assert id1 == id2
        assert store.count() == 1


class TestSchedulerStoreCount:
    def test_empty(self, store):
        assert store.count() == 0

    def test_after_add(self, store):
        _add_sample(store)
        assert store.count() == 1


# --- Scheduler polling loop ---


class TestSchedulerRunTask:
    def test_runs_agent_and_marks_done(self, store):
        task_id = _add_sample(store)
        # Force task to be due
        store._conn.execute(
            "UPDATE schedules SET next_run_at = ?",
            (datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat(),),
        )
        store._conn.commit()

        mock_agent = MagicMock()
        mock_agent.run.return_value = "PR summary: 3 open PRs"
        lock = threading.Lock()

        scheduler = Scheduler(store=store, poll_interval=1)
        task = store.get_due()[0]
        scheduler._run_task(task, mock_agent, lock)

        mock_agent.run.assert_called_once()
        prompt_arg = mock_agent.run.call_args[0][0]
        assert "daily-check" in prompt_arg
        assert "Check open PRs" in prompt_arg

        # Task should be marked as run
        updated = store.get("daily-check")
        assert updated["last_run_at"] is not None

    def test_delivers_to_telegram(self, store):
        store.add(
            name="tg-task",
            prompt="Report",
            cron_expression="0 9 * * *",
            deliver_to="telegram",
            telegram_chat_id=42,
        )
        store._conn.execute(
            "UPDATE schedules SET next_run_at = ?",
            (datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat(),),
        )
        store._conn.commit()

        mock_agent = MagicMock()
        mock_agent.run.return_value = "Daily report content"
        mock_send = MagicMock()
        lock = threading.Lock()

        scheduler = Scheduler(store=store, telegram_send=mock_send)
        task = store.get_due()[0]
        scheduler._run_task(task, mock_agent, lock)

        mock_send.assert_called_once()
        call_args = mock_send.call_args[0]
        assert call_args[0] == 42  # chat_id
        assert "Daily report content" in call_args[1]

    def test_handles_agent_error(self, store):
        task_id = _add_sample(store)
        store._conn.execute(
            "UPDATE schedules SET next_run_at = ?",
            (datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat(),),
        )
        store._conn.commit()

        mock_agent = MagicMock()
        mock_agent.run.side_effect = RuntimeError("LLM down")
        lock = threading.Lock()

        scheduler = Scheduler(store=store)
        task = store.get_due()[0]
        # Should not raise
        scheduler._run_task(task, mock_agent, lock)

        # Task should still be marked as run
        updated = store.get("daily-check")
        assert updated["last_run_at"] is not None
