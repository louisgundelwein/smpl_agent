"""Tests for src.repos — repository registry store (Postgres, cursor-mocked)."""

from unittest.mock import MagicMock, patch

import pytest

from src.repos import RepoStore


def _make_store():
    """Create a RepoStore with a mock Database."""
    db = MagicMock()
    conn = MagicMock()
    cursor = MagicMock()

    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    db.get_connection.return_value = conn

    # Schema init: no-op
    cursor.execute.return_value = None

    store = RepoStore(db=db)
    return store, db, conn, cursor


def _sample_row(
    id=1, name="smpl_agent", owner="louisgundelwein", repo="smpl_agent",
    url="https://github.com/louisgundelwein/smpl_agent.git",
    default_branch="main", description="Test repo", tags="python,agent",
    added_at="2025-01-01T00:00:00+00:00",
):
    return {
        "id": id, "name": name, "owner": owner, "repo": repo,
        "url": url, "default_branch": default_branch,
        "description": description, "tags": tags, "added_at": added_at,
    }


class TestAdd:
    def test_returns_id(self):
        store, db, conn, cursor = _make_store()
        cursor.fetchone.return_value = {"id": 1}
        repo_id = store.add(
            name="smpl_agent", owner="louisgundelwein", repo="smpl_agent",
            url="https://github.com/louisgundelwein/smpl_agent.git",
            tags=["python", "agent"],
        )
        assert repo_id == 1
        conn.commit.assert_called()

    def test_duplicate_name_raises(self):
        store, db, conn, cursor = _make_store()
        import psycopg2.errors
        cursor.execute.side_effect = psycopg2.errors.UniqueViolation("duplicate")
        with pytest.raises(psycopg2.errors.UniqueViolation):
            store.add(name="dup", owner="o", repo="r", url="https://x")

    def test_default_values(self):
        store, db, conn, cursor = _make_store()
        # add
        cursor.fetchone.return_value = {"id": 1}
        store.add(name="minimal", owner="owner", repo="repo", url="https://example.com")

        # get
        cursor.fetchone.return_value = _sample_row(
            name="minimal", description="", tags="", owner="owner", repo="repo",
            url="https://example.com",
        )
        repo = store.get("minimal")
        assert repo["default_branch"] == "main"
        assert repo["description"] == ""
        assert repo["tags"] == []


class TestListAll:
    def test_empty(self):
        store, db, conn, cursor = _make_store()
        cursor.fetchall.return_value = []
        assert store.list_all() == []

    def test_returns_all_sorted_by_name(self):
        store, db, conn, cursor = _make_store()
        cursor.fetchall.return_value = [
            _sample_row(id=2, name="alpha"),
            _sample_row(id=1, name="zeta"),
        ]
        repos = store.list_all()
        assert len(repos) == 2
        assert repos[0]["name"] == "alpha"
        assert repos[1]["name"] == "zeta"

    def test_tags_parsed(self):
        store, db, conn, cursor = _make_store()
        cursor.fetchall.return_value = [_sample_row()]
        repos = store.list_all()
        assert repos[0]["tags"] == ["python", "agent"]


class TestGet:
    def test_found(self):
        store, db, conn, cursor = _make_store()
        cursor.fetchone.return_value = _sample_row()
        repo = store.get("smpl_agent")
        assert repo is not None
        assert repo["owner"] == "louisgundelwein"

    def test_not_found(self):
        store, db, conn, cursor = _make_store()
        cursor.fetchone.return_value = None
        assert store.get("nonexistent") is None


class TestRemove:
    def test_removes_existing(self):
        store, db, conn, cursor = _make_store()
        cursor.rowcount = 1
        assert store.remove("smpl_agent") is True
        conn.commit.assert_called()

    def test_returns_false_for_missing(self):
        store, db, conn, cursor = _make_store()
        cursor.rowcount = 0
        assert store.remove("nonexistent") is False


class TestUpdate:
    def test_updates_description(self):
        store, db, conn, cursor = _make_store()
        cursor.rowcount = 1
        assert store.update("smpl_agent", description="Updated desc") is True
        conn.commit.assert_called()

    def test_ignores_unknown_fields(self):
        store, db, conn, cursor = _make_store()
        assert store.update("smpl_agent", unknown_field="value") is False

    def test_returns_false_for_missing(self):
        store, db, conn, cursor = _make_store()
        cursor.rowcount = 0
        assert store.update("nonexistent", description="x") is False


class TestCount:
    def test_returns_count(self):
        store, db, conn, cursor = _make_store()
        cursor.fetchone.return_value = {"cnt": 3}
        assert store.count() == 3
