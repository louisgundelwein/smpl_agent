"""Repository registry with Postgres persistence."""

from datetime import datetime, timezone
from typing import Any

from src.db import Database


class RepoStore:
    """Persistent repository registry using Postgres.

    Stores known repositories with their GitHub owner, name, URL,
    and metadata. Used by the agent to track which repos it manages.
    """

    def __init__(self, db: Database) -> None:
        self._db = db
        self._init_schema()

    def _init_schema(self) -> None:
        """Create the repos table if it doesn't exist."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS repos (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        owner TEXT NOT NULL,
                        repo TEXT NOT NULL,
                        url TEXT NOT NULL,
                        default_branch TEXT NOT NULL DEFAULT 'main',
                        description TEXT NOT NULL DEFAULT '',
                        tags TEXT NOT NULL DEFAULT '',
                        added_at TEXT NOT NULL
                    )
                """)
            conn.commit()
        finally:
            self._db.put_connection(conn)

    def add(
        self,
        name: str,
        owner: str,
        repo: str,
        url: str,
        default_branch: str = "main",
        description: str = "",
        tags: list[str] | None = None,
    ) -> int:
        """Register a new repository.

        Args:
            name: Short unique name (e.g. "smpl_agent").
            owner: GitHub owner/org.
            repo: GitHub repo name.
            url: Full clone URL.
            default_branch: Default branch name.
            description: Short description.
            tags: Optional categorization tags.

        Returns:
            The ID of the stored repo.

        Raises:
            psycopg2.errors.UniqueViolation: If name already exists.
        """
        tags_str = ",".join(tags) if tags else ""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO repos (name, owner, repo, url, default_branch, description, tags, added_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (name, owner, repo, url, default_branch, description, tags_str, now),
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
        """Return all registered repositories."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, owner, repo, url, default_branch, description, tags, added_at "
                    "FROM repos ORDER BY name"
                )
                rows = cur.fetchall()
            return [self._row_to_dict(row) for row in rows]
        finally:
            self._db.put_connection(conn)

    def get(self, name: str) -> dict[str, Any] | None:
        """Get a repository by short name. Returns None if not found."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, owner, repo, url, default_branch, description, tags, added_at "
                    "FROM repos WHERE name = %s",
                    (name,),
                )
                row = cur.fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            self._db.put_connection(conn)

    def remove(self, name: str) -> bool:
        """Remove a repository by name.

        Returns:
            True if a repo was removed, False if name not found.
        """
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM repos WHERE name = %s", (name,))
                removed = cur.rowcount > 0
            conn.commit()
            return removed
        finally:
            self._db.put_connection(conn)

    def update(self, name: str, **fields: Any) -> bool:
        """Update repo fields (description, default_branch, tags).

        Returns:
            True if a repo was updated, False if name not found.
        """
        allowed = {"description", "default_branch", "tags"}
        updates = {}
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "tags" and isinstance(value, list):
                value = ",".join(value)
            updates[key] = value

        if not updates:
            return False

        set_clause = ", ".join(f"{k} = %s" for k in updates)
        values = list(updates.values()) + [name]
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE repos SET {set_clause} WHERE name = %s",
                    values,
                )
                updated = cur.rowcount > 0
            conn.commit()
            return updated
        finally:
            self._db.put_connection(conn)

    def count(self) -> int:
        """Return the total number of registered repos."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS cnt FROM repos")
                row = cur.fetchone()
            return row["cnt"]
        finally:
            self._db.put_connection(conn)

    def close(self) -> None:
        """No-op — connection pool is managed by Database."""

    @staticmethod
    def _row_to_dict(row: dict) -> dict[str, Any]:
        """Convert a database row to a dict with parsed tags."""
        return {
            "id": row["id"],
            "name": row["name"],
            "owner": row["owner"],
            "repo": row["repo"],
            "url": row["url"],
            "default_branch": row["default_branch"],
            "description": row["description"],
            "tags": [t for t in row["tags"].split(",") if t],
            "added_at": row["added_at"],
        }
