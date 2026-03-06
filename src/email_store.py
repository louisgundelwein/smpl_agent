"""Email account registry with Postgres persistence."""

from datetime import datetime, timezone
from typing import Any

from src.db import Database
from src.encryption import EncryptionManager


class EmailAccountStore:
    """Persistent email account registry using Postgres.

    Stores IMAP/SMTP connection details (host, port, credentials)
    so the agent can manage multiple email accounts at runtime.
    """

    def __init__(self, db: Database, encryption_key_path: str = "encryption.key") -> None:
        self._db = db
        self._encryption = EncryptionManager(encryption_key_path)
        self._init_schema()

    def _init_schema(self) -> None:
        """Create the accounts table if it doesn't exist."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS accounts (
                        id SERIAL PRIMARY KEY,
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
            conn.commit()
        finally:
            self._db.put_connection(conn)

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
            psycopg2.errors.UniqueViolation: If name already exists.
        """
        now = datetime.now(timezone.utc).isoformat()
        encrypted_password = self._encryption.encrypt(password)
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO accounts
                       (name, email_address, password, imap_host, imap_port,
                        smtp_host, smtp_port, provider, added_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (name, email_address, encrypted_password, imap_host, imap_port,
                     smtp_host, smtp_port, provider, now),
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
        """Return all registered accounts (passwords redacted)."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, email_address, imap_host, imap_port, "
                    "smtp_host, smtp_port, provider, added_at "
                    "FROM accounts ORDER BY name"
                )
                rows = cur.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._db.put_connection(conn)

    def get(self, name: str) -> dict[str, Any] | None:
        """Get an account by name (includes password for auth).

        Returns None if not found. Decrypts password on retrieval and handles migration
        of plaintext passwords to encrypted storage.
        """
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, email_address, password, imap_host, imap_port, "
                    "smtp_host, smtp_port, provider, added_at "
                    "FROM accounts WHERE name = %s",
                    (name,),
                )
                row = cur.fetchone()
            if not row:
                return None

            result = dict(row)
            password = result.get("password", "")

            # Handle plaintext password migration: encrypt it on first access
            if password and not self._encryption.is_encrypted(password):
                encrypted_password = self._encryption.encrypt(password)
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE accounts SET password = %s WHERE name = %s",
                        (encrypted_password, name),
                    )
                conn.commit()
                result["password"] = password
            else:
                # Decrypt the password
                try:
                    result["password"] = self._encryption.decrypt(password)
                except Exception:
                    result["password"] = ""
            return result
        finally:
            self._db.put_connection(conn)

    def remove(self, name: str) -> bool:
        """Remove an account by name.

        Returns:
            True if an account was removed, False if name not found.
        """
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM accounts WHERE name = %s", (name,),
                )
                removed = cur.rowcount > 0
            conn.commit()
            return removed
        finally:
            self._db.put_connection(conn)

    def count(self) -> int:
        """Return the total number of registered accounts."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS cnt FROM accounts")
                row = cur.fetchone()
            return row["cnt"]
        finally:
            self._db.put_connection(conn)

    def close(self) -> None:
        """No-op — connection pool is managed by Database."""
