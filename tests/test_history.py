"""Tests for src.history (Postgres-backed ConversationHistory)."""

import json
from unittest.mock import MagicMock

import pytest

from src.history import ConversationHistory


@pytest.fixture
def cursor():
    return MagicMock()


@pytest.fixture
def conn(cursor):
    c = MagicMock()
    c.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    c.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return c


@pytest.fixture
def db(conn):
    d = MagicMock()
    d.get_connection.return_value = conn
    return d


@pytest.fixture
def history(db):
    return ConversationHistory(db=db, session_id="test-session")


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------

def test_save_executes_upsert(history, cursor, conn):
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "hi"},
    ]
    history.save(messages)

    cursor.execute.assert_called_once()
    call_args = cursor.execute.call_args
    sql = call_args[0][0]
    params = call_args[0][1]

    assert "INSERT INTO conversations" in sql
    assert "ON CONFLICT" in sql
    assert params[0] == "test-session"
    assert json.loads(params[1]) == messages
    conn.commit.assert_called_once()


def test_save_releases_connection(history, db, conn):
    history.save([{"role": "system", "content": "sys"}])
    db.put_connection.assert_called_once_with(conn)


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------

def test_load_returns_messages_when_row_exists(history, cursor):
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
    ]
    # psycopg2 RealDictCursor returns JSONB as Python object
    cursor.fetchone.return_value = {"messages": messages}

    result = history.load()

    assert result == messages


def test_load_returns_none_when_no_row(history, cursor):
    cursor.fetchone.return_value = None

    assert history.load() is None


def test_load_returns_none_when_empty_list(history, cursor):
    cursor.fetchone.return_value = {"messages": []}

    assert history.load() is None


def test_load_returns_none_when_first_message_not_system(history, cursor):
    cursor.fetchone.return_value = {
        "messages": [{"role": "user", "content": "hi"}]
    }

    assert history.load() is None


def test_load_releases_connection(history, db, conn, cursor):
    cursor.fetchone.return_value = None
    history.load()
    db.put_connection.assert_called_once_with(conn)


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------

def test_clear_executes_delete(history, cursor, conn):
    history.clear()

    cursor.execute.assert_called_once()
    call_args = cursor.execute.call_args
    sql = call_args[0][0]
    params = call_args[0][1]

    assert "DELETE FROM conversations" in sql
    assert params[0] == "test-session"
    conn.commit.assert_called_once()


def test_clear_releases_connection(history, db, conn):
    history.clear()
    db.put_connection.assert_called_once_with(conn)


# ---------------------------------------------------------------------------
# session_id isolation
# ---------------------------------------------------------------------------

def test_different_session_ids_use_correct_id(db, cursor, conn):
    db.get_connection.return_value = conn

    h1 = ConversationHistory(db=db, session_id="session-a")
    h1.save([{"role": "system", "content": "a"}])
    params = cursor.execute.call_args[0][1]
    assert params[0] == "session-a"


def test_default_session_id_is_default(db, cursor, conn):
    db.get_connection.return_value = conn
    h = ConversationHistory(db=db)
    h.save([{"role": "system", "content": "x"}])
    params = cursor.execute.call_args[0][1]
    assert params[0] == "default"
