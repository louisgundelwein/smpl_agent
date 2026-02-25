"""Tests for src.history (Postgres-backed ConversationHistory)."""

from unittest.mock import MagicMock, patch, call

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
# _init_schema
# ---------------------------------------------------------------------------

def test_init_schema_creates_tables(history, cursor, conn):
    """_init_schema is called during __init__ and creates tables + index."""
    sqls = [c[0][0] for c in cursor.execute.call_args_list]
    assert any("CREATE TABLE IF NOT EXISTS conversations" in s for s in sqls)
    assert any("CREATE TABLE IF NOT EXISTS messages" in s for s in sqls)
    assert any("CREATE INDEX IF NOT EXISTS messages_conversation_id_idx" in s for s in sqls)
    conn.commit.assert_called()


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------

@patch("src.history.execute_values")
def test_save_upserts_conversation_and_inserts_messages(mock_ev, history, cursor, conn):
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "hi"},
    ]
    cursor.execute.reset_mock()
    conn.commit.reset_mock()

    history.save(messages)

    execute_calls = cursor.execute.call_args_list
    # First call: upsert conversation
    assert "INSERT INTO conversations" in execute_calls[0][0][0]
    assert "ON CONFLICT" in execute_calls[0][0][0]
    assert execute_calls[0][0][1] == ("test-session",)
    # Second call: delete old messages
    assert "DELETE FROM messages" in execute_calls[1][0][0]
    assert execute_calls[1][0][1] == ("test-session",)
    # Third: execute_values batch insert
    mock_ev.assert_called_once()
    ev_args = mock_ev.call_args
    assert "INSERT INTO messages" in ev_args[0][1]
    rows = ev_args[0][2]
    assert len(rows) == 2
    assert rows[0][0] == "test-session"  # conversation_id
    assert rows[0][1] == "system"  # role
    assert rows[0][2] == "You are helpful."  # content
    conn.commit.assert_called_once()


@patch("src.history.execute_values")
def test_save_handles_tool_calls(mock_ev, history, cursor, conn):
    messages = [
        {"role": "system", "content": "sys"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "tc1", "function": {"name": "search", "arguments": "{}"}}],
        },
        {"role": "tool", "content": "result", "tool_call_id": "tc1", "name": "search"},
    ]
    cursor.execute.reset_mock()

    history.save(messages)

    rows = mock_ev.call_args[0][2]
    assert len(rows) == 3
    # assistant message with tool_calls
    assert rows[1][1] == "assistant"  # role
    assert rows[1][2] is None  # content
    assert '"search"' in rows[1][3]  # tool_calls JSON string
    # tool result message
    assert rows[2][1] == "tool"  # role
    assert rows[2][4] == "tc1"  # tool_call_id
    assert rows[2][5] == "search"  # name


@patch("src.history.execute_values")
def test_save_releases_connection(mock_ev, history, db, conn):
    history.save([{"role": "system", "content": "sys"}])
    db.put_connection.assert_called_with(conn)


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------

def test_load_returns_messages(history, cursor):
    cursor.fetchall.return_value = [
        {"role": "system", "content": "sys", "tool_calls": None, "tool_call_id": None, "name": None},
        {"role": "user", "content": "hello", "tool_calls": None, "tool_call_id": None, "name": None},
    ]

    result = history.load()

    assert result == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
    ]


def test_load_reconstructs_tool_calls(history, cursor):
    cursor.fetchall.return_value = [
        {"role": "system", "content": "sys", "tool_calls": None, "tool_call_id": None, "name": None},
        {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "tc1", "function": {"name": "search"}}],
            "tool_call_id": None, "name": None,
        },
        {
            "role": "tool", "content": "result",
            "tool_calls": None, "tool_call_id": "tc1", "name": "search",
        },
    ]

    result = history.load()

    assert len(result) == 3
    assert result[1] == {
        "role": "assistant",
        "tool_calls": [{"id": "tc1", "function": {"name": "search"}}],
    }
    assert result[2] == {
        "role": "tool", "content": "result",
        "tool_call_id": "tc1", "name": "search",
    }


def test_load_returns_none_when_no_messages(history, cursor):
    cursor.fetchall.return_value = []
    assert history.load() is None


def test_load_returns_none_when_first_message_not_system(history, cursor):
    cursor.fetchall.return_value = [
        {"role": "user", "content": "hi", "tool_calls": None, "tool_call_id": None, "name": None},
    ]
    assert history.load() is None


def test_load_releases_connection(history, db, conn, cursor):
    cursor.fetchall.return_value = []
    history.load()
    db.put_connection.assert_called_with(conn)


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------

def test_clear_deletes_conversation(history, cursor, conn):
    cursor.execute.reset_mock()
    conn.commit.reset_mock()

    history.clear()

    call_args = cursor.execute.call_args
    sql = call_args[0][0]
    params = call_args[0][1]

    assert "DELETE FROM conversations" in sql
    assert params[0] == "test-session"
    conn.commit.assert_called_once()


def test_clear_releases_connection(history, db, conn):
    history.clear()
    db.put_connection.assert_called_with(conn)


# ---------------------------------------------------------------------------
# session_id isolation
# ---------------------------------------------------------------------------

@patch("src.history.execute_values")
def test_different_session_ids_use_correct_id(mock_ev, db, cursor, conn):
    h1 = ConversationHistory(db=db, session_id="session-a")
    cursor.execute.reset_mock()
    h1.save([{"role": "system", "content": "a"}])
    upsert_params = cursor.execute.call_args_list[0][0][1]
    assert upsert_params == ("session-a",)


@patch("src.history.execute_values")
def test_default_session_id_is_default(mock_ev, db, cursor, conn):
    h = ConversationHistory(db=db)
    cursor.execute.reset_mock()
    h.save([{"role": "system", "content": "x"}])
    upsert_params = cursor.execute.call_args_list[0][0][1]
    assert upsert_params == ("default",)
