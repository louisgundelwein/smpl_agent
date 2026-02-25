"""Email account registry with SQLite persistence."""

import sqlite3
from datetime import datetime, timezone
from typing import Any


class EmailAccountStore:
    """Persistent email account registry using SQLite.

    Stores IMAP/SMTP connection details (host, port, credentials)
    so the agent can manage multiple email accounts at runtime.
    """

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        """Create the accounts table if it doesn't exist."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                email_address TEXT NOT NULL,
                password TEXT NOT NULL,
                imap_host TEXT NOT NULL,
                imap_port INTEGER NOT NULL DEFAULT 993,
                smtp_host TEXT NOT NULL,
                smtp_port INTEGER NOT NULL DEFAULT 587,
                provider TEXT NOT NULL DEFAULT 'generic',
                added_at TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def add(
        self,
        name: str,
        email_address: str,
        password: str,
        imap_host: str,
        smtp_host: str,
        imap_port: int = 993,
        smtp_port: int = 587,
        provider: str = "generic",
    ) -> int:
        """Register a new email account.

        Args:
            name: Short unique name (e.g. "work", "personal").
            email_address: Full email address.
            password: Password or app-specific password.
            imap_host: IMAP server hostname.
            smtp_host: SMTP server hostname.
            imap_port: IMAP port (default: 993 for SSL/TLS).
            smtp_port: SMTP port (default: 587 for STARTTLS).
            provider: Provider hint (gmail/outlook/generic).

        Returns:
            The ID of the stored account.

        Raises:
            sqlite3.IntegrityError: If name already exists.
        """
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            """INSERT INTO accounts
               (name, email_address, password, imap_host, imap_port,
                smtp_host, smtp_port, provider, added_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, email_address, password, imap_host, imap_port,
             smtp_host, smtp_port, provider, now),
        )
        self._conn.commit()
        return cursor.lastrowid

    def list_all(self) -> list[dict[str, Any]]:
        """Return all registered accounts (passwords redacted)."""
        rows = self._conn.execute(
            "SELECT id, name, email_address, imap_host, imap_port, "
            "smtp_host, smtp_port, provider, added_at "
            "FROM accounts ORDER BY name"
        ).fetchall()
        return [dict(row) for row in rows]

    def get(self, name: str) -> dict[str, Any] | None:
        """Get an account by name (includes password for auth).

        Returns None if not found.
        """
        row = self._conn.execute(
            "SELECT id, name, email_address, password, imap_host, imap_port, "
            "smtp_host, smtp_port, provider, added_at "
            "FROM accounts WHERE name = ?",
            (name,),
        ).fetchone()
        return dict(row) if row else None

    def remove(self, name: str) -> bool:
        """Remove an account by name.

        Returns:
            True if an account was removed, False if name not found.
        """
        cursor = self._conn.execute(
            "DELETE FROM accounts WHERE name = ?", (name,),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def count(self) -> int:
        """Return the total number of registered accounts."""
        row = self._conn.execute("SELECT COUNT(*) FROM accounts").fetchone()
        return row[0]

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
