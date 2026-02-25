"""Conversation history persistence via Postgres.

Conversations are stored in two tables:
- conversations: one row per session (id, timestamps)
- messages: one row per message, FK to conversations with ON DELETE CASCADE
"""

import json
from typing import Any

from psycopg2.extras import execute_values

from src.db import Database


class ConversationHistory:
    """Save and load conversation messages to/from Postgres.

    Each conversation is identified by a session_id (default: "default").
    Messages are stored as individual rows in the messages table.
    """

    def __init__(self, db: Database, session_id: str = "default") -> None:
        self._db = db
        self._session_id = session_id
        self._init_schema()

    def _init_schema(self) -> None:
        """Create tables and indexes if they don't exist."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS conversations (
                        id TEXT PRIMARY KEY,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id SERIAL PRIMARY KEY,
                        conversation_id TEXT NOT NULL
                            REFERENCES conversations(id) ON DELETE CASCADE,
                        role TEXT NOT NULL,
                        content TEXT,
                        tool_calls JSONB,
                        tool_call_id TEXT,
                        name TEXT,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS messages_conversation_id_idx
                        ON messages(conversation_id)
                """)
            conn.commit()
        finally:
            self._db.put_connection(conn)

    def save(self, messages: list[dict[str, Any]]) -> None:
        """Save the full message list (upsert conversation, replace messages)."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO conversations (id) VALUES (%s)
                       ON CONFLICT (id) DO UPDATE SET updated_at = NOW()""",
                    (self._session_id,),
                )
                cur.execute(
                    "DELETE FROM messages WHERE conversation_id = %s",
                    (self._session_id,),
                )
                rows = [
                    (
                        self._session_id,
                        m.get("role"),
                        m.get("content"),
                        json.dumps(m["tool_calls"]) if "tool_calls" in m else None,
                        m.get("tool_call_id"),
                        m.get("name"),
                    )
                    for m in messages
                ]
                execute_values(
                    cur,
                    """INSERT INTO messages
                        (conversation_id, role, content, tool_calls, tool_call_id, name)
                       VALUES %s""",
                    rows,
                )
            conn.commit()
        finally:
            self._db.put_connection(conn)

    def load(self) -> list[dict[str, Any]] | None:
        """Load messages from the messages table.

        Returns None if no conversation exists or the data is invalid.
        None-valued fields are excluded from messages so providers
        that reject null content (e.g. Gemini) work correctly.
        """
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT role, content, tool_calls, tool_call_id, name
                       FROM messages
                       WHERE conversation_id = %s
                       ORDER BY id""",
                    (self._session_id,),
                )
                rows = cur.fetchall()
        finally:
            self._db.put_connection(conn)

        if not rows:
            return None

        messages = []
        for row in rows:
            msg: dict[str, Any] = {"role": row["role"]}
            if row["content"] is not None:
                msg["content"] = row["content"]
            if row["tool_calls"] is not None:
                msg["tool_calls"] = row["tool_calls"]
            if row["tool_call_id"] is not None:
                msg["tool_call_id"] = row["tool_call_id"]
            if row["name"] is not None:
                msg["name"] = row["name"]
            messages.append(msg)

        if not messages or messages[0].get("role") != "system":
            return None
        return messages

    def clear(self) -> None:
        """Delete this conversation (CASCADE removes messages)."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM conversations WHERE id = %s",
                    (self._session_id,),
                )
            conn.commit()
        finally:
            self._db.put_connection(conn)
