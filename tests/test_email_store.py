"""Tests for src.email_store — Email account persistence."""

import sqlite3

import pytest

from src.email_store import EmailAccountStore


@pytest.fixture()
def store():
    s = EmailAccountStore(db_path=":memory:")
    yield s
    s.close()


def test_add_and_get(store):
    rid = store.add(
        name="work",
        email_address="alice@example.com",
        password="app-secret",
        imap_host="imap.example.com",
        smtp_host="smtp.example.com",
        provider="generic",
    )
    assert isinstance(rid, int)

    acct = store.get("work")
    assert acct is not None
    assert acct["name"] == "work"
    assert acct["email_address"] == "alice@example.com"
    assert acct["password"] == "app-secret"
    assert acct["imap_host"] == "imap.example.com"
    assert acct["imap_port"] == 993
    assert acct["smtp_host"] == "smtp.example.com"
    assert acct["smtp_port"] == 587
    assert acct["provider"] == "generic"
    assert acct["added_at"]


def test_add_duplicate_name_raises(store):
    store.add(name="dup", email_address="a@b", password="p",
              imap_host="i", smtp_host="s")
    with pytest.raises(sqlite3.IntegrityError):
        store.add(name="dup", email_address="c@d", password="p2",
                  imap_host="i2", smtp_host="s2")


def test_list_all_redacts_password(store):
    store.add(name="a", email_address="a@a", password="secret1",
              imap_host="i1", smtp_host="s1")
    store.add(name="b", email_address="b@b", password="secret2",
              imap_host="i2", smtp_host="s2")

    accts = store.list_all()
    assert len(accts) == 2
    for a in accts:
        assert "password" not in a
    assert accts[0]["name"] == "a"
    assert accts[1]["name"] == "b"


def test_get_nonexistent_returns_none(store):
    assert store.get("nope") is None


def test_remove(store):
    store.add(name="tmp", email_address="t@t", password="p",
              imap_host="i", smtp_host="s")
    assert store.count() == 1

    removed = store.remove("tmp")
    assert removed is True
    assert store.count() == 0
    assert store.get("tmp") is None


def test_remove_nonexistent(store):
    assert store.remove("ghost") is False


def test_count(store):
    assert store.count() == 0
    store.add(name="one", email_address="1@1", password="p",
              imap_host="i", smtp_host="s")
    assert store.count() == 1
    store.add(name="two", email_address="2@2", password="p",
              imap_host="i", smtp_host="s")
    assert store.count() == 2


def test_default_provider_and_ports(store):
    store.add(name="plain", email_address="x@x", password="p",
              imap_host="i", smtp_host="s")
    acct = store.get("plain")
    assert acct["provider"] == "generic"
    assert acct["imap_port"] == 993
    assert acct["smtp_port"] == 587


def test_custom_ports(store):
    store.add(name="custom", email_address="x@x", password="p",
              imap_host="i", smtp_host="s",
              imap_port=143, smtp_port=465)
    acct = store.get("custom")
    assert acct["imap_port"] == 143
    assert acct["smtp_port"] == 465
