"""Repository registry with SQLite persistence."""

import sqlite3
from datetime import datetime, timezone
from typing import Any


class RepoStore:
    """Persistent repository registry using SQLite.

    Stores known repositories with their GitHub owner, name, URL,
    and metadata. Used by the agent to track which repos it manages.
    """

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        """Create the repos table if it doesn't exist."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS repos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        self._conn.commit()

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
            sqlite3.IntegrityError: If name already exists.
        """
        tags_str = ",".join(tags) if tags else ""
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            """INSERT INTO repos (name, owner, repo, url, default_branch, description, tags, added_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, owner, repo, url, default_branch, description, tags_str, now),
        )
        self._conn.commit()
        return cursor.lastrowid

    def list_all(self) -> list[dict[str, Any]]:
        """Return all registered repositories."""
        rows = self._conn.execute(
            "SELECT id, name, owner, repo, url, default_branch, description, tags, added_at "
            "FROM repos ORDER BY name"
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get(self, name: str) -> dict[str, Any] | None:
        """Get a repository by short name. Returns None if not found."""
        row = self._conn.execute(
            "SELECT id, name, owner, repo, url, default_branch, description, tags, added_at "
            "FROM repos WHERE name = ?",
            (name,),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def remove(self, name: str) -> bool:
        """Remove a repository by name.

        Returns:
            True if a repo was removed, False if name not found.
        """
        cursor = self._conn.execute("DELETE FROM repos WHERE name = ?", (name,))
        self._conn.commit()
        return cursor.rowcount > 0

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

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [name]
        cursor = self._conn.execute(
            f"UPDATE repos SET {set_clause} WHERE name = ?",
            values,
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def count(self) -> int:
        """Return the total number of registered repos."""
        row = self._conn.execute("SELECT COUNT(*) FROM repos").fetchone()
        return row[0]

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
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
