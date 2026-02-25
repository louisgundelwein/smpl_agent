"""CalDAV connection registry with Postgres persistence."""

from datetime import datetime, timezone
from typing import Any

from src.db import Database


class CalendarConnectionStore:
    """Persistent CalDAV connection registry using Postgres.

    Stores CalDAV server connections (URL, credentials, provider type)
    so the agent can manage multiple calendar providers at runtime.
    """

    def __init__(self, db: Database) -> None:
        self._db = db
        self._init_schema()

    def _init_schema(self) -> None:
        """Create the connections table if it doesn't exist."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS connections (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        url TEXT NOT NULL,
                        username TEXT NOT NULL,
                        password TEXT NOT NULL,
                        provider TEXT NOT NULL DEFAULT 'caldav',
                        added_at TEXT NOT NULL
                    )
                """)
            conn.commit()
        finally:
            self._db.put_connection(conn)

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
            psycopg2.errors.UniqueViolation: If name already exists.
        """
        now = datetime.now(timezone.utc).isoformat()
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO connections (name, url, username, password, provider, added_at)
                       VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                    (name, url, username, password, provider, now),
                )
                row = cur.fetchone()
            conn.commit()
            return row["id"]
        except Exception:
            conn.rollback()
            raise
        finally:
            self._db.put_connection(conn)

    def list_all(self) -> list[dict[str, Any]]:
        """Return all registered connections (passwords redacted)."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, url, username, provider, added_at "
                    "FROM connections ORDER BY name"
                )
                rows = cur.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._db.put_connection(conn)

    def get(self, name: str) -> dict[str, Any] | None:
        """Get a connection by name (includes password for CalDAV auth).

        Returns None if not found.
        """
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, url, username, password, provider, added_at "
                    "FROM connections WHERE name = %s",
                    (name,),
                )
                row = cur.fetchone()
            return dict(row) if row else None
        finally:
            self._db.put_connection(conn)

    def remove(self, name: str) -> bool:
        """Remove a connection by name.

        Returns:
            True if a connection was removed, False if name not found.
        """
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM connections WHERE name = %s", (name,),
                )
                removed = cur.rowcount > 0
            conn.commit()
            return removed
        finally:
            self._db.put_connection(conn)

    def count(self) -> int:
        """Return the total number of registered connections."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS cnt FROM connections")
                row = cur.fetchone()
            return row["cnt"]
        finally:
            self._db.put_connection(conn)

    def close(self) -> None:
        """No-op — connection pool is managed by Database."""
