"""Tests for src.auto_memory."""

import time
from unittest.mock import MagicMock

import pytest

from src.auto_memory import AutoMemory, MIN_MESSAGES_FOR_SUMMARY
from src.events import AutoMemoryStoredEvent, EventEmitter


# --- Helpers ---


def _make_llm_response(content: str) -> MagicMock:
    """Create a mock LLM response with given content."""
    msg = MagicMock()
    msg.content = content
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message = msg
    return resp


def _build_messages(n_user_turns: int) -> list[dict]:
    """Build a message list with system + n user/assistant pairs."""
    msgs = [{"role": "system", "content": "You are helpful."}]
    for i in range(n_user_turns):
        msgs.append({"role": "user", "content": f"Question {i}"})
        msgs.append({"role": "assistant", "content": f"Answer {i}"})
    return msgs


# --- Fixtures ---


@pytest.fixture
def mock_llm():
    """Mock LLMClient for auto-memory."""
    llm = MagicMock()
    llm.chat.return_value = _make_llm_response(
        "User prefers Python for scripting tasks."
    )
    return llm


@pytest.fixture
def mock_memory():
    """Mock MemoryStore."""
    store = MagicMock()
    store.add.return_value = 1
    store.search.return_value = []  # No duplicates by default
    return store


@pytest.fixture
def auto_mem(mock_llm, mock_memory):
    """AutoMemory with mocked dependencies."""
    return AutoMemory(
        llm=mock_llm,
        memory=mock_memory,
        extract_interval=3,
    )


# --- on_conversation_end tests ---


class TestConversationEnd:
    def test_skips_short_conversations(self, auto_mem, mock_llm, mock_memory):
        """Conversations with fewer than MIN_MESSAGES_FOR_SUMMARY are skipped."""
        messages = _build_messages(1)  # system + 2 = 3 total, only 2 non-system
        auto_mem.on_conversation_end(messages)
        mock_llm.chat.assert_not_called()
        mock_memory.add.assert_not_called()

    def test_summarizes_long_conversation(self, auto_mem, mock_llm, mock_memory):
        """Conversations >= MIN_MESSAGES_FOR_SUMMARY get summarized and stored."""
        messages = _build_messages(3)  # system + 6 = 7 messages, 6 non-system
        auto_mem.on_conversation_end(messages)
        mock_llm.chat.assert_called_once()
        mock_memory.add.assert_called_once()
        call_kwargs = mock_memory.add.call_args
        assert "auto" in call_kwargs.kwargs["tags"]
        assert "summary" in call_kwargs.kwargs["tags"]

    def test_emits_event_on_store(self, mock_llm, mock_memory):
        """AutoMemoryStoredEvent is emitted when a summary is stored."""
        events = []
        emitter = EventEmitter()
        emitter.on(lambda e: events.append(e))
        am = AutoMemory(llm=mock_llm, memory=mock_memory, emitter=emitter)
        am.on_conversation_end(_build_messages(3))
        stored = [e for e in events if isinstance(e, AutoMemoryStoredEvent)]
        assert len(stored) == 1
        assert stored[0].source == "conversation_end"

    def test_handles_llm_error_gracefully(self, auto_mem, mock_llm, mock_memory):
        """LLM errors don't propagate; no memory is stored."""
        mock_llm.chat.side_effect = RuntimeError("API down")
        auto_mem.on_conversation_end(_build_messages(3))  # Should not raise
        mock_memory.add.assert_not_called()

    def test_handles_empty_summary_gracefully(self, auto_mem, mock_llm, mock_memory):
        """Empty LLM response doesn't store anything."""
        mock_llm.chat.return_value = _make_llm_response("")
        auto_mem.on_conversation_end(_build_messages(3))
        mock_memory.add.assert_not_called()

    def test_resets_turn_counter(self, auto_mem):
        """Turn counter resets after conversation end."""
        auto_mem._turn_count = 5
        auto_mem.on_conversation_end(_build_messages(3))
        assert auto_mem._turn_count == 0

    def test_boundary_message_count(self, auto_mem, mock_llm, mock_memory):
        """Exactly MIN_MESSAGES_FOR_SUMMARY non-system messages triggers summary."""
        # MIN_MESSAGES_FOR_SUMMARY = 4, so 2 turns = 4 non-system messages
        messages = _build_messages(2)
        auto_mem.on_conversation_end(messages)
        mock_llm.chat.assert_called_once()


# --- on_turn_end tests ---


class TestTurnEnd:
    def test_no_extraction_before_interval(self, auto_mem, mock_llm):
        """No extraction on turns 1 and 2 when interval=3."""
        messages = _build_messages(1)
        auto_mem.on_turn_end(messages)  # turn 1
        auto_mem.on_turn_end(messages)  # turn 2
        mock_llm.chat.assert_not_called()

    def test_extraction_on_interval(self, auto_mem, mock_llm, mock_memory):
        """Extraction triggers on turn 3 (interval=3)."""
        messages = _build_messages(3)
        auto_mem.on_turn_end(messages)  # turn 1
        auto_mem.on_turn_end(messages)  # turn 2
        auto_mem.on_turn_end(messages)  # turn 3 -> triggers

        # Give the background thread time to run
        time.sleep(0.2)

        mock_llm.chat.assert_called_once()

    def test_skips_when_previous_extraction_running(self, mock_llm, mock_memory):
        """If a background thread is still running, skip new extraction."""

        def slow_chat(**kwargs):
            time.sleep(0.5)
            return _make_llm_response("NONE")

        mock_llm.chat.side_effect = slow_chat

        am = AutoMemory(llm=mock_llm, memory=mock_memory, extract_interval=1)
        messages = _build_messages(2)
        am.on_turn_end(messages)  # turn 1 -> triggers, starts slow thread
        am.on_turn_end(messages)  # turn 2 -> should skip (thread alive)
        time.sleep(0.6)
        assert mock_llm.chat.call_count == 1  # Only one call

    def test_extraction_runs_in_background(self, auto_mem, mock_llm):
        """on_turn_end returns immediately (doesn't block)."""
        messages = _build_messages(3)
        auto_mem.on_turn_end(messages)  # turn 1
        auto_mem.on_turn_end(messages)  # turn 2

        t0 = time.monotonic()
        auto_mem.on_turn_end(messages)  # turn 3 -> triggers
        elapsed = time.monotonic() - t0
        assert elapsed < 0.05  # Should return near-instantly

    def test_extraction_stores_facts(self, mock_llm, mock_memory):
        """Extracted facts are stored as individual memories."""
        mock_llm.chat.return_value = _make_llm_response(
            "User prefers dark mode.\nUser works at Acme Corp."
        )
        am = AutoMemory(llm=mock_llm, memory=mock_memory, extract_interval=1)
        am.on_turn_end(_build_messages(2))
        time.sleep(0.2)
        assert mock_memory.add.call_count == 2

    def test_extraction_emits_events(self, mock_llm, mock_memory):
        """AutoMemoryStoredEvent emitted for each stored fact."""
        mock_llm.chat.return_value = _make_llm_response("User likes cats.")
        events = []
        emitter = EventEmitter()
        emitter.on(lambda e: events.append(e))
        am = AutoMemory(
            llm=mock_llm, memory=mock_memory, emitter=emitter, extract_interval=1
        )
        am.on_turn_end(_build_messages(2))
        time.sleep(0.2)
        stored = [e for e in events if isinstance(e, AutoMemoryStoredEvent)]
        assert len(stored) == 1
        assert stored[0].source == "turn_extraction"


# --- NONE response handling ---


class TestNoneResponse:
    def test_no_storage_on_none_response(self, mock_llm, mock_memory):
        """When LLM responds with NONE, nothing is stored."""
        mock_llm.chat.return_value = _make_llm_response("NONE")
        am = AutoMemory(llm=mock_llm, memory=mock_memory, extract_interval=1)
        am.on_turn_end(_build_messages(2))
        time.sleep(0.2)
        mock_memory.add.assert_not_called()

    def test_no_storage_on_empty_response(self, mock_llm, mock_memory):
        """Empty extraction response stores nothing."""
        mock_llm.chat.return_value = _make_llm_response("")
        am = AutoMemory(llm=mock_llm, memory=mock_memory, extract_interval=1)
        am.on_turn_end(_build_messages(2))
        time.sleep(0.2)
        mock_memory.add.assert_not_called()


# --- Duplicate detection tests ---


class TestDuplicateDetection:
    def test_skips_duplicate_memory(self, auto_mem, mock_memory):
        """Near-duplicate memories are not stored."""
        mock_memory.search.return_value = [
            {"id": 1, "content": "User prefers Python.", "score": 0.95}
        ]
        result = auto_mem._store_if_not_duplicate(
            "User prefers Python for scripting.", ["auto"]
        )
        assert result is None
        mock_memory.add.assert_not_called()

    def test_stores_non_duplicate(self, auto_mem, mock_memory):
        """Genuinely new facts are stored."""
        mock_memory.search.return_value = [
            {"id": 1, "content": "Something unrelated", "score": 0.4}
        ]
        result = auto_mem._store_if_not_duplicate("User works at Acme Corp.", ["auto"])
        assert result is not None
        mock_memory.add.assert_called_once()

    def test_stores_when_memory_empty(self, auto_mem, mock_memory):
        """Stores when no existing memories at all."""
        mock_memory.search.return_value = []
        result = auto_mem._store_if_not_duplicate("Brand new fact.", ["auto"])
        mock_memory.add.assert_called_once()

    def test_stores_on_search_error(self, auto_mem, mock_memory):
        """If dedup search fails, store anyway."""
        mock_memory.search.side_effect = RuntimeError("DB error")
        result = auto_mem._store_if_not_duplicate("Some fact.", ["auto"])
        mock_memory.add.assert_called_once()


# --- Shutdown tests ---


class TestShutdown:
    def test_shutdown_signals_thread(self, auto_mem):
        """shutdown() sets the event and doesn't raise."""
        auto_mem.shutdown()
        assert auto_mem._shutdown_event.is_set()

    def test_shutdown_with_no_thread(self, auto_mem):
        """shutdown() works when no thread was ever started."""
        auto_mem.shutdown()  # Should not raise


# --- Message formatting ---


class TestFormatMessages:
    def test_skips_system_messages(self):
        """System messages are excluded from formatted output."""
        from src.auto_memory import _format_messages_for_llm

        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        result = _format_messages_for_llm(messages)
        assert "system" not in result.lower()
        assert "User: Hello" in result

    def test_formats_tool_calls(self):
        """Tool call messages are formatted with tool names."""
        from src.auto_memory import _format_messages_for_llm

        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "memory", "arguments": "{}"}}
                ],
            },
            {"role": "tool", "name": "memory", "content": '{"stored": true}'},
        ]
        result = _format_messages_for_llm(messages)
        assert "memory" in result

    def test_truncates_long_tool_output(self):
        """Tool output > 2000 chars is truncated."""
        from src.auto_memory import _format_messages_for_llm

        messages = [
            {"role": "tool", "name": "shell", "content": "x" * 3000},
        ]
        result = _format_messages_for_llm(messages)
        assert "...[truncated]..." in result
