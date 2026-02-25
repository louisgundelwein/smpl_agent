"""Tests for src.calendar_store — CalDAV connection persistence."""

import sqlite3

import pytest

from src.calendar_store import CalendarConnectionStore


@pytest.fixture()
def store():
    s = CalendarConnectionStore(db_path=":memory:")
    yield s
    s.close()


def test_add_and_get(store):
    rid = store.add(
        name="work",
        url="https://cal.example.com/dav/",
        username="alice",
        password="secret",
        provider="nextcloud",
    )
    assert isinstance(rid, int)

    conn = store.get("work")
    assert conn is not None
    assert conn["name"] == "work"
    assert conn["url"] == "https://cal.example.com/dav/"
    assert conn["username"] == "alice"
    assert conn["password"] == "secret"
    assert conn["provider"] == "nextcloud"
    assert conn["added_at"]  # non-empty ISO timestamp


def test_add_duplicate_name_raises(store):
    store.add(name="dup", url="https://a", username="u", password="p")
    with pytest.raises(sqlite3.IntegrityError):
        store.add(name="dup", url="https://b", username="u2", password="p2")


def test_list_all_redacts_password(store):
    store.add(name="a", url="https://a", username="u1", password="secret1")
    store.add(name="b", url="https://b", username="u2", password="secret2")

    conns = store.list_all()
    assert len(conns) == 2
    # list_all should NOT include password
    for c in conns:
        assert "password" not in c
    assert conns[0]["name"] == "a"
    assert conns[1]["name"] == "b"


def test_get_nonexistent_returns_none(store):
    assert store.get("nope") is None


def test_remove(store):
    store.add(name="tmp", url="https://x", username="u", password="p")
    assert store.count() == 1

    removed = store.remove("tmp")
    assert removed is True
    assert store.count() == 0
    assert store.get("tmp") is None


def test_remove_nonexistent(store):
    assert store.remove("ghost") is False


def test_count(store):
    assert store.count() == 0
    store.add(name="one", url="https://1", username="u", password="p")
    assert store.count() == 1
    store.add(name="two", url="https://2", username="u", password="p")
    assert store.count() == 2


def test_default_provider(store):
    store.add(name="plain", url="https://x", username="u", password="p")
    conn = store.get("plain")
    assert conn["provider"] == "caldav"
