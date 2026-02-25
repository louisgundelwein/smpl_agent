"""Conversation history persistence via Postgres."""

import json
from datetime import datetime, timezone
from typing import Any

from src.db import Database


class ConversationHistory:
    """Save and load conversation messages to/from Postgres.

    Each conversation is identified by a session_id (default: "default").
    Messages are stored as JSONB in the conversations table.
    """

    def __init__(self, db: Database, session_id: str = "default") -> None:
        self._db = db
        self._session_id = session_id

    def save(self, messages: list[dict[str, Any]]) -> None:
        """Upsert the full message list into the conversations table."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO conversations (session_id, messages, updated_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (session_id) DO UPDATE SET
                        messages   = EXCLUDED.messages,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (self._session_id, json.dumps(messages), now),
                )
            conn.commit()
        finally:
            self._db.put_connection(conn)

    def load(self) -> list[dict[str, Any]] | None:
        """Load messages from Postgres.

        Returns None if no conversation exists or the data is invalid.
        """
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT messages FROM conversations WHERE session_id = %s",
                    (self._session_id,),
                )
                row = cur.fetchone()
        finally:
            self._db.put_connection(conn)

        if row is None:
            return None

        # psycopg2 with RealDictCursor returns JSONB columns as Python objects
        data = row["messages"]
        if not isinstance(data, list) or not data:
            return None
        if not isinstance(data[0], dict) or data[0].get("role") != "system":
            return None
        return data

    def clear(self) -> None:
        """Delete this conversation from Postgres."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM conversations WHERE session_id = %s",
                    (self._session_id,),
                )
            conn.commit()
        finally:
            self._db.put_connection(conn)
