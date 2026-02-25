"""Tests for src.memory using mocked Postgres/pgvector and mock embeddings."""

import json
from unittest.mock import MagicMock

import pytest

from src.memory import MemoryStore


def _make_store(dimensions=3):
    """Create a MemoryStore with a mock Database and mock embedder."""
    db = MagicMock()
    conn = MagicMock()
    cursor = MagicMock()

    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    db.get_connection.return_value = conn

    cursor.execute.return_value = None

    embedder = MagicMock()
    embedder.embed.return_value = [[1.0, 0.0, 0.0]]

    store = MemoryStore(db=db, embedding_client=embedder, dimensions=dimensions)
    return store, db, conn, cursor, embedder


def test_add_returns_id():
    store, db, conn, cursor, embedder = _make_store()
    embedder.embed.return_value = [[0.1, 0.2, 0.3]]
    cursor.fetchone.return_value = {"id": 1}
    mem_id = store.add("hello world")
    assert mem_id == 1
    conn.commit.assert_called()


def test_add_increments_ids():
    store, db, conn, cursor, embedder = _make_store()
    embedder.embed.return_value = [[0.1, 0.2, 0.3]]
    cursor.fetchone.side_effect = [{"id": 1}, {"id": 2}]
    id1 = store.add("first")
    id2 = store.add("second")
    assert id2 > id1


def test_add_with_tags():
    store, db, conn, cursor, embedder = _make_store()
    embedder.embed.return_value = [[0.1, 0.2, 0.3]]
    cursor.fetchone.return_value = {"id": 1}
    mem_id = store.add("tagged memory", tags=["project", "important"])
    assert mem_id == 1

    # Verify the tags were joined and passed to execute
    insert_call = [c for c in cursor.execute.call_args_list if "INSERT" in str(c)]
    assert len(insert_call) > 0


def test_count():
    store, db, conn, cursor, embedder = _make_store()
    cursor.fetchone.return_value = {"cnt": 2}
    assert store.count() == 2


def test_delete_existing():
    store, db, conn, cursor, embedder = _make_store()
    cursor.rowcount = 1
    assert store.delete(1) is True
    conn.commit.assert_called()


def test_delete_nonexistent():
    store, db, conn, cursor, embedder = _make_store()
    cursor.rowcount = 0
    assert store.delete(999) is False


def test_search_returns_results():
    store, db, conn, cursor, embedder = _make_store()
    embedder.embed.return_value = [[1.0, 0.0, 0.0]]

    cursor.fetchall.return_value = [
        {
            "id": 1, "content": "x-axis memory", "metadata": {},
            "created_at": "2025-01-01T00:00:00+00:00",
            "semantic_score": 1.0, "fts_bonus": 0.0,
        },
        {
            "id": 3, "content": "diagonal memory", "metadata": {},
            "created_at": "2025-01-01T00:00:00+00:00",
            "semantic_score": 0.707, "fts_bonus": 0.0,
        },
        {
            "id": 2, "content": "y-axis memory", "metadata": {},
            "created_at": "2025-01-01T00:00:00+00:00",
            "semantic_score": 0.0, "fts_bonus": 0.0,
        },
    ]

    results = store.search("find x things", top_k=3)

    assert len(results) == 3
    assert results[0]["content"] == "x-axis memory"
    assert results[0]["score"] == 1.0
    assert results[1]["content"] == "diagonal memory"
    assert results[2]["content"] == "y-axis memory"


def test_search_empty_store():
    store, db, conn, cursor, embedder = _make_store()
    embedder.embed.return_value = [[1.0, 0.0, 0.0]]
    cursor.fetchall.return_value = []
    results = store.search("anything")
    assert results == []


def test_search_top_k_passed_to_query():
    store, db, conn, cursor, embedder = _make_store()
    embedder.embed.return_value = [[0.1, 0.2, 0.3]]
    cursor.fetchall.return_value = [
        {
            "id": 1, "content": "mem1", "metadata": {},
            "created_at": "t", "semantic_score": 0.9, "fts_bonus": 0.0,
        },
        {
            "id": 2, "content": "mem2", "metadata": {},
            "created_at": "t", "semantic_score": 0.8, "fts_bonus": 0.0,
        },
    ]
    results = store.search("query", top_k=2)
    assert len(results) == 2

    # Verify top_k was passed to the SQL query
    search_call = [c for c in cursor.execute.call_args_list if "LIMIT" in str(c)]
    assert len(search_call) > 0


def test_search_result_structure():
    store, db, conn, cursor, embedder = _make_store()
    embedder.embed.return_value = [[1.0, 0.0, 0.0]]
    cursor.fetchall.return_value = [
        {
            "id": 1, "content": "test content",
            "metadata": {"tags": ["tag1", "tag2"]},
            "created_at": "2025-01-01T00:00:00+00:00",
            "semantic_score": 0.95, "fts_bonus": 0.1,
        },
    ]
    results = store.search("test")

    assert len(results) == 1
    result = results[0]
    assert result["id"] == 1
    assert result["content"] == "test content"
    assert result["tags"] == ["tag1", "tag2"]
    assert "created_at" in result
    assert result["score"] == 1.05
    assert isinstance(result["score"], float)


def test_search_tags_empty_when_none():
    store, db, conn, cursor, embedder = _make_store()
    embedder.embed.return_value = [[1.0, 0.0, 0.0]]
    cursor.fetchall.return_value = [
        {
            "id": 1, "content": "no tags", "metadata": {},
            "created_at": "t", "semantic_score": 1.0, "fts_bonus": 0.0,
        },
    ]
    results = store.search("no tags")
    assert results[0]["tags"] == []


def test_search_tags_empty_when_metadata_is_none():
    store, db, conn, cursor, embedder = _make_store()
    embedder.embed.return_value = [[1.0, 0.0, 0.0]]
    cursor.fetchall.return_value = [
        {
            "id": 1, "content": "null metadata", "metadata": None,
            "created_at": "t", "semantic_score": 1.0, "fts_bonus": 0.0,
        },
    ]
    results = store.search("null metadata")
    assert results[0]["tags"] == []
