"""Tests for src.calendar_store — CalDAV connection persistence (Postgres, cursor-mocked)."""

from unittest.mock import MagicMock

import pytest

from src.calendar_store import CalendarConnectionStore


def _make_store():
    """Create a CalendarConnectionStore with a mock Database."""
    db = MagicMock()
    conn = MagicMock()
    cursor = MagicMock()

    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    db.get_connection.return_value = conn

    cursor.execute.return_value = None
    store = CalendarConnectionStore(db=db)
    return store, db, conn, cursor


def _sample_row(
    id=1, name="work", url="https://cal.example.com/dav/",
    username="alice", password="secret", provider="nextcloud",
    added_at="2025-01-01T00:00:00+00:00",
):
    return {
        "id": id, "name": name, "url": url, "username": username,
        "password": password, "provider": provider, "added_at": added_at,
    }


def test_add_and_get():
    store, db, conn, cursor = _make_store()
    cursor.fetchone.return_value = {"id": 1}
    rid = store.add(
        name="work", url="https://cal.example.com/dav/",
        username="alice", password="secret", provider="nextcloud",
    )
    assert rid == 1
    conn.commit.assert_called()

    cursor.fetchone.return_value = _sample_row()
    result = store.get("work")
    assert result["name"] == "work"
    assert result["password"] == "secret"
    assert result["provider"] == "nextcloud"


def test_add_duplicate_name_raises():
    store, db, conn, cursor = _make_store()
    import psycopg2.errors
    cursor.execute.side_effect = psycopg2.errors.UniqueViolation("duplicate")
    with pytest.raises(psycopg2.errors.UniqueViolation):
        store.add(name="dup", url="https://a", username="u", password="p")


def test_list_all_redacts_password():
    store, db, conn, cursor = _make_store()
    cursor.fetchall.return_value = [
        {"id": 1, "name": "a", "url": "https://a", "username": "u1", "provider": "caldav", "added_at": "t"},
        {"id": 2, "name": "b", "url": "https://b", "username": "u2", "provider": "caldav", "added_at": "t"},
    ]
    conns = store.list_all()
    assert len(conns) == 2
    for c in conns:
        assert "password" not in c
    assert conns[0]["name"] == "a"
    assert conns[1]["name"] == "b"


def test_get_nonexistent_returns_none():
    store, db, conn, cursor = _make_store()
    cursor.fetchone.return_value = None
    assert store.get("nope") is None


def test_remove():
    store, db, conn, cursor = _make_store()
    cursor.rowcount = 1
    assert store.remove("tmp") is True
    conn.commit.assert_called()


def test_remove_nonexistent():
    store, db, conn, cursor = _make_store()
    cursor.rowcount = 0
    assert store.remove("ghost") is False


def test_count():
    store, db, conn, cursor = _make_store()
    cursor.fetchone.return_value = {"cnt": 2}
    assert store.count() == 2


def test_default_provider():
    store, db, conn, cursor = _make_store()
    cursor.fetchone.return_value = {"id": 1}
    store.add(name="plain", url="https://x", username="u", password="p")

    cursor.fetchone.return_value = _sample_row(name="plain", provider="caldav")
    result = store.get("plain")
    assert result["provider"] == "caldav"
