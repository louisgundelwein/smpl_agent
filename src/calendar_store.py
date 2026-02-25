"""CalDAV connection registry with SQLite persistence."""

import sqlite3
from datetime import datetime, timezone
from typing import Any


class CalendarConnectionStore:
    """Persistent CalDAV connection registry using SQLite.

    Stores CalDAV server connections (URL, credentials, provider type)
    so the agent can manage multiple calendar providers at runtime.
    """

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        """Create the connections table if it doesn't exist."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                url TEXT NOT NULL,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'caldav',
                added_at TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def add(
        self,
        name: str,
        url: str,
        username: str,
        password: str,
        provider: str = "caldav",
    ) -> int:
        """Register a new CalDAV connection.

        Args:
            name: Short unique name (e.g. "work", "personal").
            url: CalDAV server URL.
            username: Authentication username.
            password: Authentication password or app-specific password.
            provider: Provider hint (caldav/google/icloud/nextcloud).

        Returns:
            The ID of the stored connection.

        Raises:
            sqlite3.IntegrityError: If name already exists.
        """
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            """INSERT INTO connections (name, url, username, password, provider, added_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, url, username, password, provider, now),
        )
        self._conn.commit()
        return cursor.lastrowid

    def list_all(self) -> list[dict[str, Any]]:
        """Return all registered connections (passwords redacted)."""
        rows = self._conn.execute(
            "SELECT id, name, url, username, provider, added_at "
            "FROM connections ORDER BY name"
        ).fetchall()
        return [dict(row) for row in rows]

    def get(self, name: str) -> dict[str, Any] | None:
        """Get a connection by name (includes password for CalDAV auth).

        Returns None if not found.
        """
        row = self._conn.execute(
            "SELECT id, name, url, username, password, provider, added_at "
            "FROM connections WHERE name = ?",
            (name,),
        ).fetchone()
        return dict(row) if row else None

    def remove(self, name: str) -> bool:
        """Remove a connection by name.

        Returns:
            True if a connection was removed, False if name not found.
        """
        cursor = self._conn.execute(
            "DELETE FROM connections WHERE name = ?", (name,),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def count(self) -> int:
        """Return the total number of registered connections."""
        row = self._conn.execute("SELECT COUNT(*) FROM connections").fetchone()
        return row[0]

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
