"""Scheduled task engine with SQLite persistence and polling loop."""

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from croniter import croniter

logger = logging.getLogger(__name__)


def _parse_simple_interval(expression: str) -> str | None:
    """Convert simple interval strings to cron expressions.

    Supports: 'every 30m', 'every 6h', 'every 1d'.
    Returns None if not a simple interval.
    """
    expression = expression.strip().lower()
    if not expression.startswith("every "):
        return None

    part = expression[6:].strip()
    if part.endswith("m"):
        try:
            minutes = int(part[:-1])
            return f"*/{minutes} * * * *"
        except ValueError:
            return None
    elif part.endswith("h"):
        try:
            hours = int(part[:-1])
            return f"0 */{hours} * * *"
        except ValueError:
            return None
    elif part.endswith("d"):
        try:
            days = int(part[:-1])
            return f"0 0 */{days} * *"
        except ValueError:
            return None
    return None


def compute_next_run(cron_expression: str, after: datetime | None = None) -> datetime:
    """Compute the next run time for a cron expression.

    Args:
        cron_expression: Standard 5-field cron or simple interval (e.g. 'every 6h').
        after: Reference time (default: now UTC).

    Returns:
        Next run time as a timezone-aware UTC datetime.
    """
    if after is None:
        after = datetime.now(timezone.utc)

    parsed = _parse_simple_interval(cron_expression)
    cron_str = parsed if parsed else cron_expression

    cron = croniter(cron_str, after)
    next_dt = cron.get_next(datetime)

    if next_dt.tzinfo is None:
        next_dt = next_dt.replace(tzinfo=timezone.utc)
    return next_dt


class SchedulerStore:
    """Persistent scheduled task storage using SQLite.

    Manages creation, listing, and lifecycle of scheduled tasks.
    Thread-safe via WAL mode.
    """

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        """Create the schedules table if it doesn't exist."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                prompt TEXT NOT NULL,
                cron_expression TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                deliver_to TEXT NOT NULL DEFAULT 'memory',
                telegram_chat_id INTEGER,
                last_run_at TEXT,
                next_run_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def add(
        self,
        name: str,
        prompt: str,
        cron_expression: str,
        deliver_to: str = "memory",
        telegram_chat_id: int | None = None,
    ) -> int:
        """Add a new scheduled task.

        Args:
            name: Unique task name.
            prompt: The instruction to run on schedule.
            cron_expression: Cron expression or simple interval.
            deliver_to: Where to deliver results ('memory', 'telegram', 'both').
            telegram_chat_id: Telegram chat ID for delivery.

        Returns:
            The ID of the stored task.
        """
        now = datetime.now(timezone.utc)
        next_run = compute_next_run(cron_expression, after=now)

        cursor = self._conn.execute(
            """INSERT INTO schedules
               (name, prompt, cron_expression, deliver_to, telegram_chat_id, next_run_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                name,
                prompt,
                cron_expression,
                deliver_to,
                telegram_chat_id,
                next_run.isoformat(),
                now.isoformat(),
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def upsert(
        self,
        name: str,
        prompt: str,
        cron_expression: str,
        deliver_to: str = "memory",
        telegram_chat_id: int | None = None,
    ) -> int:
        """Insert a task or skip if name already exists. Returns ID."""
        existing = self.get(name)
        if existing:
            return existing["id"]
        return self.add(name, prompt, cron_expression, deliver_to, telegram_chat_id)

    def list_all(self) -> list[dict[str, Any]]:
        """Return all scheduled tasks."""
        rows = self._conn.execute(
            "SELECT * FROM schedules ORDER BY name"
        ).fetchall()
        return [dict(row) for row in rows]

    def get(self, name: str) -> dict[str, Any] | None:
        """Get a task by name. Returns None if not found."""
        row = self._conn.execute(
            "SELECT * FROM schedules WHERE name = ?", (name,)
        ).fetchone()
        return dict(row) if row else None

    def get_due(self, now: datetime | None = None) -> list[dict[str, Any]]:
        """Return enabled tasks whose next_run_at is in the past."""
        if now is None:
            now = datetime.now(timezone.utc)
        rows = self._conn.execute(
            "SELECT * FROM schedules WHERE enabled = 1 AND next_run_at <= ?",
            (now.isoformat(),),
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_run(self, task_id: int, now: datetime | None = None) -> None:
        """Update last_run_at and compute the next next_run_at."""
        if now is None:
            now = datetime.now(timezone.utc)

        row = self._conn.execute(
            "SELECT cron_expression FROM schedules WHERE id = ?", (task_id,)
        ).fetchone()
        if not row:
            return

        next_run = compute_next_run(row["cron_expression"], after=now)
        self._conn.execute(
            "UPDATE schedules SET last_run_at = ?, next_run_at = ? WHERE id = ?",
            (now.isoformat(), next_run.isoformat(), task_id),
        )
        self._conn.commit()

    def delete(self, name: str) -> bool:
        """Delete a task by name."""
        cursor = self._conn.execute(
            "DELETE FROM schedules WHERE name = ?", (name,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def toggle(self, name: str, enabled: bool) -> bool:
        """Enable or disable a task."""
        cursor = self._conn.execute(
            "UPDATE schedules SET enabled = ? WHERE name = ?",
            (1 if enabled else 0, name),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def count(self) -> int:
        """Return the total number of scheduled tasks."""
        row = self._conn.execute("SELECT COUNT(*) FROM schedules").fetchone()
        return row[0]

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()


class Scheduler:
    """Polling loop that runs scheduled tasks using the agent.

    Started as a daemon thread alongside the Telegram bot.
    Uses the same agent_lock for serialization.
    """

    def __init__(
        self,
        store: SchedulerStore,
        telegram_send: Callable[[int, str], None] | None = None,
        poll_interval: int = 30,
    ) -> None:
        self._store = store
        self._telegram_send = telegram_send
        self._poll_interval = poll_interval

    def poll_loop(self, agent: Any, agent_lock: threading.Lock) -> None:
        """Daemon thread loop. Checks for due tasks every poll_interval seconds.

        Same signature as TelegramBot.poll_loop() for consistency.
        """
        logger.info("Scheduler started (poll every %ds)", self._poll_interval)

        while True:
            try:
                time.sleep(self._poll_interval)
                due_tasks = self._store.get_due()

                for task in due_tasks:
                    self._run_task(task, agent, agent_lock)

            except Exception:
                logger.exception("Scheduler error")
                time.sleep(self._poll_interval)

    def _run_task(
        self, task: dict, agent: Any, agent_lock: threading.Lock
    ) -> None:
        """Execute a single scheduled task."""
        task_name = task["name"]
        prompt = task["prompt"]

        logger.info("[scheduler] running task: %s", task_name)

        agent_lock.acquire()
        try:
            result = agent.run(
                f"[Scheduled task '{task_name}']: {prompt}\n\n"
                "Store the result in memory with tag 'scheduled-task'."
            )
        except Exception as exc:
            logger.error("[scheduler] task '%s' failed: %s", task_name, exc)
            result = f"Error: {exc}"
        finally:
            agent_lock.release()

        self._store.mark_run(task["id"])
        self._deliver_result(task, result)
        logger.info("[scheduler] task '%s' completed", task_name)

    def _deliver_result(self, task: dict, result: str) -> None:
        """Route result to Telegram based on task config."""
        deliver_to = task.get("deliver_to", "memory")
        chat_id = task.get("telegram_chat_id")

        if deliver_to in ("telegram", "both") and self._telegram_send and chat_id:
            try:
                header = f"📋 Scheduled task '{task['name']}':\n\n"
                self._telegram_send(chat_id, header + result)
            except Exception:
                logger.exception(
                    "Failed to send scheduled result to Telegram chat %s", chat_id
                )
