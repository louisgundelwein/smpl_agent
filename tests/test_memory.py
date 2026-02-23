"""Tests for src.memory using in-memory SQLite and mock embeddings."""

import pytest
from unittest.mock import MagicMock

from src.memory import MemoryStore


@pytest.fixture
def mock_embedder():
    """Mock EmbeddingClient that returns deterministic vectors."""
    client = MagicMock()
    client.embed.return_value = [[1.0, 0.0, 0.0]]
    return client


@pytest.fixture
def store(mock_embedder):
    """MemoryStore backed by in-memory SQLite."""
    return MemoryStore(db_path=":memory:", embedding_client=mock_embedder)


def test_add_returns_id(store, mock_embedder):
    mock_embedder.embed.return_value = [[0.1, 0.2, 0.3]]
    mem_id = store.add("hello world")
    assert mem_id == 1


def test_add_increments_ids(store, mock_embedder):
    mock_embedder.embed.return_value = [[0.1, 0.2, 0.3]]
    id1 = store.add("first")
    id2 = store.add("second")
    assert id2 > id1


def test_add_with_tags(store, mock_embedder):
    mock_embedder.embed.return_value = [[0.1, 0.2, 0.3]]
    mem_id = store.add("tagged memory", tags=["project", "important"])
    assert mem_id == 1


def test_count(store, mock_embedder):
    mock_embedder.embed.return_value = [[0.1, 0.2, 0.3]]
    assert store.count() == 0
    store.add("first")
    assert store.count() == 1
    store.add("second")
    assert store.count() == 2


def test_delete_existing(store, mock_embedder):
    mock_embedder.embed.return_value = [[0.1, 0.2, 0.3]]
    mem_id = store.add("to delete")
    assert store.delete(mem_id) is True
    assert store.count() == 0


def test_delete_nonexistent(store):
    assert store.delete(999) is False


def test_search_returns_sorted_by_similarity(store, mock_embedder):
    # Store three memories with distinct direction vectors
    mock_embedder.embed.side_effect = [
        [[1.0, 0.0, 0.0]],  # memory 1: x-axis
        [[0.0, 1.0, 0.0]],  # memory 2: y-axis
        [[0.7, 0.7, 0.0]],  # memory 3: diagonal
    ]
    store.add("x-axis memory")
    store.add("y-axis memory")
    store.add("diagonal memory")

    # Search with query vector along x-axis
    mock_embedder.embed.side_effect = None
    mock_embedder.embed.return_value = [[1.0, 0.0, 0.0]]
    results = store.search("find x things", top_k=3)

    assert len(results) == 3
    # x-axis memory should rank first (cosine sim = 1.0)
    assert results[0]["content"] == "x-axis memory"
    # diagonal should rank second (cosine sim ~= 0.707)
    assert results[1]["content"] == "diagonal memory"
    # y-axis should rank last (cosine sim = 0.0)
    assert results[2]["content"] == "y-axis memory"


def test_search_empty_store(store, mock_embedder):
    mock_embedder.embed.return_value = [[1.0, 0.0, 0.0]]
    results = store.search("anything")
    assert results == []


def test_search_top_k_limits_results(store, mock_embedder):
    mock_embedder.embed.return_value = [[0.1, 0.2, 0.3]]
    for i in range(5):
        store.add(f"memory {i}")

    mock_embedder.embed.return_value = [[0.1, 0.2, 0.3]]
    results = store.search("query", top_k=2)
    assert len(results) == 2


def test_search_result_structure(store, mock_embedder):
    mock_embedder.embed.return_value = [[1.0, 0.0, 0.0]]
    store.add("test content", tags=["tag1", "tag2"])

    mock_embedder.embed.return_value = [[1.0, 0.0, 0.0]]
    results = store.search("test")

    assert len(results) == 1
    result = results[0]
    assert "id" in result
    assert result["content"] == "test content"
    assert result["tags"] == ["tag1", "tag2"]
    assert "created_at" in result
    assert "score" in result
    assert isinstance(result["score"], float)


def test_search_tags_empty_when_none(store, mock_embedder):
    mock_embedder.embed.return_value = [[1.0, 0.0, 0.0]]
    store.add("no tags")

    mock_embedder.embed.return_value = [[1.0, 0.0, 0.0]]
    results = store.search("no tags")

    assert results[0]["tags"] == []
