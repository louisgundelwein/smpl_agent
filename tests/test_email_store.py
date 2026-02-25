"""Tests for src.email_store — Email account persistence (Postgres, cursor-mocked)."""

from unittest.mock import MagicMock

import pytest

from src.email_store import EmailAccountStore


def _make_store():
    """Create an EmailAccountStore with a mock Database."""
    db = MagicMock()
    conn = MagicMock()
    cursor = MagicMock()

    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    db.get_connection.return_value = conn

    cursor.execute.return_value = None
    store = EmailAccountStore(db=db)
    return store, db, conn, cursor


def _sample_row(
    id=1, name="work", email_address="alice@example.com", password="app-secret",
    imap_host="imap.example.com", imap_port=993, smtp_host="smtp.example.com",
    smtp_port=587, provider="generic", added_at="2025-01-01T00:00:00+00:00",
):
    return {
        "id": id, "name": name, "email_address": email_address,
        "password": password, "imap_host": imap_host, "imap_port": imap_port,
        "smtp_host": smtp_host, "smtp_port": smtp_port, "provider": provider,
        "added_at": added_at,
    }


def test_add_and_get():
    store, db, conn, cursor = _make_store()
    cursor.fetchone.return_value = {"id": 1}
    rid = store.add(
        name="work", email_address="alice@example.com", password="app-secret",
        imap_host="imap.example.com", smtp_host="smtp.example.com",
    )
    assert rid == 1
    conn.commit.assert_called()

    cursor.fetchone.return_value = _sample_row()
    acct = store.get("work")
    assert acct["name"] == "work"
    assert acct["email_address"] == "alice@example.com"
    assert acct["password"] == "app-secret"
    assert acct["imap_port"] == 993
    assert acct["smtp_port"] == 587


def test_add_duplicate_name_raises():
    store, db, conn, cursor = _make_store()
    import psycopg2.errors
    cursor.execute.side_effect = psycopg2.errors.UniqueViolation("duplicate")
    with pytest.raises(psycopg2.errors.UniqueViolation):
        store.add(name="dup", email_address="a@b", password="p",
                  imap_host="i", smtp_host="s")


def test_list_all_redacts_password():
    store, db, conn, cursor = _make_store()
    cursor.fetchall.return_value = [
        {"id": 1, "name": "a", "email_address": "a@a", "imap_host": "i1",
         "imap_port": 993, "smtp_host": "s1", "smtp_port": 587,
         "provider": "generic", "added_at": "t"},
        {"id": 2, "name": "b", "email_address": "b@b", "imap_host": "i2",
         "imap_port": 993, "smtp_host": "s2", "smtp_port": 587,
         "provider": "generic", "added_at": "t"},
    ]
    accts = store.list_all()
    assert len(accts) == 2
    for a in accts:
        assert "password" not in a
    assert accts[0]["name"] == "a"
    assert accts[1]["name"] == "b"


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


def test_default_provider_and_ports():
    store, db, conn, cursor = _make_store()
    cursor.fetchone.return_value = {"id": 1}
    store.add(name="plain", email_address="x@x", password="p",
              imap_host="i", smtp_host="s")
    cursor.fetchone.return_value = _sample_row(name="plain")
    acct = store.get("plain")
    assert acct["provider"] == "generic"
    assert acct["imap_port"] == 993
    assert acct["smtp_port"] == 587


def test_custom_ports():
    store, db, conn, cursor = _make_store()
    cursor.fetchone.return_value = {"id": 1}
    store.add(name="custom", email_address="x@x", password="p",
              imap_host="i", smtp_host="s", imap_port=143, smtp_port=465)
    cursor.fetchone.return_value = _sample_row(name="custom", imap_port=143, smtp_port=465)
    acct = store.get("custom")
    assert acct["imap_port"] == 143
    assert acct["smtp_port"] == 465
