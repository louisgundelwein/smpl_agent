"""Tests for src.auto_recall."""

from unittest.mock import MagicMock

import pytest

from src.auto_recall import AutoRecall, _format_recall
from src.events import EventEmitter, MemoryRecallEvent


# --- Fixtures ---


@pytest.fixture
def mock_memory():
    """Mock MemoryStore."""
    store = MagicMock()
    store.count.return_value = 10  # Non-empty by default
    store.search.return_value = [
        {"id": 1, "content": "User prefers Python", "tags": [], "created_at": "2026-01-01", "score": 0.85},
        {"id": 2, "content": "User works on smpl_agent", "tags": [], "created_at": "2026-01-02", "score": 0.72},
        {"id": 3, "content": "Something irrelevant", "tags": [], "created_at": "2026-01-03", "score": 0.30},
    ]
    return store


@pytest.fixture
def recall(mock_memory):
    """AutoRecall with default settings."""
    return AutoRecall(memory=mock_memory, threshold=0.55, top_k=5)


# --- recall() tests ---


class TestRecall:
    def test_returns_none_when_no_memories(self, mock_memory):
        """Skip search entirely when memory store is empty."""
        mock_memory.count.return_value = 0
        ar = AutoRecall(memory=mock_memory)
        result = ar.recall("anything")
        assert result is None
        mock_memory.search.assert_not_called()

    def test_returns_none_below_threshold(self, mock_memory):
        """Return None when all results are below threshold."""
        mock_memory.search.return_value = [
            {"id": 1, "content": "Unrelated", "tags": [], "created_at": "2026-01-01", "score": 0.30},
        ]
        ar = AutoRecall(memory=mock_memory, threshold=0.55)
        result = ar.recall("some query")
        assert result is None

    def test_returns_formatted_context(self, recall, mock_memory):
        """Returns formatted string with relevant memories."""
        result = recall.recall("What language does the user prefer?")
        assert result is not None
        assert "[Memory context" in result
        assert "User prefers Python" in result
        assert "User works on smpl_agent" in result
        # Score 0.30 is below threshold 0.55 — should NOT appear
        assert "Something irrelevant" not in result

    def test_filters_by_threshold(self, mock_memory):
        """Only memories >= threshold are included."""
        mock_memory.search.return_value = [
            {"id": 1, "content": "High score", "tags": [], "created_at": "2026-01-01", "score": 0.90},
            {"id": 2, "content": "Medium score", "tags": [], "created_at": "2026-01-02", "score": 0.60},
            {"id": 3, "content": "Low score", "tags": [], "created_at": "2026-01-03", "score": 0.40},
        ]
        ar = AutoRecall(memory=mock_memory, threshold=0.55)
        result = ar.recall("test query")
        assert "High score" in result
        assert "Medium score" in result
        assert "Low score" not in result

    def test_emits_event(self, mock_memory):
        """MemoryRecallEvent is emitted when memories are recalled."""
        events = []
        emitter = EventEmitter()
        emitter.on(lambda e: events.append(e))
        ar = AutoRecall(memory=mock_memory, emitter=emitter, threshold=0.55)
        ar.recall("user preferences")

        recall_events = [e for e in events if isinstance(e, MemoryRecallEvent)]
        assert len(recall_events) == 1
        assert recall_events[0].count == 2  # score 0.85 and 0.72
        assert recall_events[0].top_score == 0.85

    def test_no_event_when_no_relevant_memories(self, mock_memory):
        """No event emitted when nothing is recalled."""
        mock_memory.search.return_value = [
            {"id": 1, "content": "Low", "tags": [], "created_at": "2026-01-01", "score": 0.20},
        ]
        events = []
        emitter = EventEmitter()
        emitter.on(lambda e: events.append(e))
        ar = AutoRecall(memory=mock_memory, emitter=emitter, threshold=0.55)
        ar.recall("test")
        assert len(events) == 0

    def test_handles_search_error(self, mock_memory):
        """Search errors return None instead of raising."""
        mock_memory.search.side_effect = RuntimeError("DB error")
        ar = AutoRecall(memory=mock_memory)
        result = ar.recall("test")
        assert result is None

    def test_respects_top_k(self, mock_memory):
        """top_k is passed through to memory.search()."""
        ar = AutoRecall(memory=mock_memory, top_k=3)
        ar.recall("test")
        mock_memory.search.assert_called_once_with(query="test", top_k=3)


# --- _format_recall() tests ---


class TestFormatRecall:
    def test_format_contains_scores(self):
        """Formatted output includes scores."""
        memories = [
            {"id": 1, "content": "Fact one", "score": 0.87},
            {"id": 2, "content": "Fact two", "score": 0.72},
        ]
        result = _format_recall(memories)
        assert "(score 0.87)" in result
        assert "(score 0.72)" in result

    def test_format_has_markers(self):
        """Formatted output has start and end markers."""
        memories = [{"id": 1, "content": "Test", "score": 0.80}]
        result = _format_recall(memories)
        assert "[Memory context" in result
        assert "[End memory context]" in result

    def test_multiline_content_flattened(self):
        """Newlines in memory content are replaced with spaces."""
        memories = [{"id": 1, "content": "Line one\nLine two", "score": 0.80}]
        result = _format_recall(memories)
        assert "Line one Line two" in result
        assert "\n\n" not in result.split("\n")[1]  # No double newlines in body
