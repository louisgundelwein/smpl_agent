"""Platform knowledge manager: static guides + dynamic learnings."""

import json
import logging
from pathlib import Path
from typing import Any

from src.db import Database
from src.marketing.base import BrowserTask

logger = logging.getLogger(__name__)


class PlatformKnowledge:
    """Combines static platform guides with dynamic learnings from the DB.

    Static guides are markdown files in a directory (one per platform).
    Dynamic learnings are key-value pairs stored in Postgres, accumulated
    as the agent interacts with platforms.
    """

    def __init__(self, knowledge_dir: Path, db: Database) -> None:
        self._knowledge_dir = knowledge_dir
        self._db = db
        self._init_schema()

    def _init_schema(self) -> None:
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS platform_learnings (
                        id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
                        platform TEXT NOT NULL,
                        key TEXT NOT NULL,
                        value TEXT NOT NULL,
                        confidence REAL DEFAULT 0.5,
                        learned_at TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE(platform, key)
                    )
                """)
            conn.commit()
        finally:
            self._db.put_connection(conn)

    def get_guide(self, platform: str) -> str:
        """Read the static markdown guide for a platform."""
        guide_path = self._knowledge_dir / f"{platform}.md"
        try:
            return guide_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def get_learnings(
        self,
        platform: str,
        keys: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch dynamic learnings from the DB."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                if keys:
                    placeholders = ",".join(["%s"] * len(keys))
                    cur.execute(
                        f"SELECT key, value, confidence FROM platform_learnings "
                        f"WHERE platform = %s AND key IN ({placeholders})",
                        [platform, *keys],
                    )
                else:
                    cur.execute(
                        "SELECT key, value, confidence FROM platform_learnings "
                        "WHERE platform = %s ORDER BY learned_at DESC",
                        (platform,),
                    )
                rows = cur.fetchall()
            return {row["key"]: {"value": row["value"], "confidence": row["confidence"]} for row in rows}
        finally:
            self._db.put_connection(conn)

    def record_learning(
        self,
        platform: str,
        key: str,
        value: str,
        confidence: float = 0.5,
    ) -> None:
        """Store or update a learning (upsert by platform+key)."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO platform_learnings (platform, key, value, confidence)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (platform, key)
                       DO UPDATE SET value = EXCLUDED.value,
                                     confidence = EXCLUDED.confidence,
                                     learned_at = NOW()""",
                    (platform, key, value, confidence),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._db.put_connection(conn)

    def enhance_task(
        self,
        platform: str,
        task: BrowserTask,
        context_keys: list[str] | None = None,
    ) -> BrowserTask:
        """Inject relevant knowledge into a browser task description."""
        parts = [task.task_description]

        # Add relevant learnings
        learnings = self.get_learnings(platform, keys=context_keys)
        if learnings:
            hints = []
            for key, info in learnings.items():
                if info["confidence"] >= 0.3:
                    hints.append(f"- {key}: {info['value']}")
            if hints:
                parts.append(
                    "\n\nPlatform knowledge (use these hints):\n"
                    + "\n".join(hints)
                )

        return BrowserTask(
            task_description="\n".join(parts),
            start_url=task.start_url,
        )
