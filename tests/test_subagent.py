"""Tests for SubagentManager and SubagentState."""

import threading
from unittest.mock import MagicMock

import pytest

from src.events import EventEmitter, SubagentSpawnedEvent, SubagentStatusEvent
from src.subagent import SubagentManager, SubagentState, SubagentStatus


# ---------------------------------------------------------------------------
# SubagentState
# ---------------------------------------------------------------------------


class TestSubagentState:
    def test_to_dict_pending(self):
        state = SubagentState(id="abc12345", task="do something")
        d = state.to_dict()
        assert d["id"] == "abc12345"
        assert d["task"] == "do something"
        assert d["status"] == "pending"
        assert d["result"] is None
        assert d["error"] is None
        assert d["elapsed_seconds"] is None

    def test_to_dict_completed_with_elapsed(self):
        state = SubagentState(id="abc12345", task="do something")
        state.started_at = 100.0
        state.completed_at = 103.5
        state.status = SubagentStatus.COMPLETED
        state.result = "done"
        d = state.to_dict()
        assert d["status"] == "completed"
        assert d["result"] == "done"
        assert d["elapsed_seconds"] == 3.5

    def test_to_dict_excludes_thread_and_cancel_flag(self):
        state = SubagentState(id="abc12345", task="do something")
        d = state.to_dict()
        assert "thread" not in d
        assert "cancel_flag" not in d


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def emitter():
    return EventEmitter()


@pytest.fixture
def collected_events(emitter):
    events = []
    emitter.on(events.append)
    return events


@pytest.fixture
def manager(emitter):
    """Manager with a mock factory that returns instantly."""
    def factory(task):
        mock_agent = MagicMock()
        mock_agent.run.return_value = f"Result for: {task}"
        return mock_agent

    return SubagentManager(
        agent_factory=factory,
        emitter=emitter,
        max_concurrent=3,
    )


@pytest.fixture
def slow_manager(emitter):
    """Manager where subagents block until released."""
    gate = threading.Event()

    def factory(task):
        mock_agent = MagicMock()

        def slow_run(prompt):
            gate.wait(timeout=5.0)
            return f"Result for: {prompt}"

        mock_agent.run.side_effect = slow_run
        return mock_agent

    mgr = SubagentManager(
        agent_factory=factory,
        emitter=emitter,
        max_concurrent=2,
    )
    mgr._gate = gate  # Expose for test control
    return mgr


# ---------------------------------------------------------------------------
# SubagentManager
# ---------------------------------------------------------------------------


class TestSubagentManager:
    def test_spawn_creates_state_and_starts_thread(self, manager):
        state = manager.spawn("test task")
        assert len(state.id) == 8
        assert state.task == "test task"
        assert state.thread is not None
        # Wait for thread to complete
        state.thread.join(timeout=2.0)
        assert state.status == SubagentStatus.COMPLETED

    def test_spawn_respects_max_concurrent(self, slow_manager):
        slow_manager.spawn("task 1")
        slow_manager.spawn("task 2")
        with pytest.raises(RuntimeError, match="Maximum concurrent subagents"):
            slow_manager.spawn("task 3")
        # Release the gate so threads can finish
        slow_manager._gate.set()

    def test_spawn_emits_spawned_event(self, manager, collected_events):
        state = manager.spawn("test task")
        state.thread.join(timeout=2.0)
        spawned = [e for e in collected_events if isinstance(e, SubagentSpawnedEvent)]
        assert len(spawned) >= 1
        assert spawned[0].subagent_id == state.id
        assert spawned[0].task == "test task"

    def test_completed_subagent_stores_result(self, manager):
        state = manager.spawn("test task")
        state.thread.join(timeout=2.0)
        assert state.status == SubagentStatus.COMPLETED
        assert state.result == "Result for: test task"

    def test_failed_subagent_stores_error(self, emitter):
        def factory(task):
            mock_agent = MagicMock()
            mock_agent.run.side_effect = RuntimeError("LLM exploded")
            return mock_agent

        mgr = SubagentManager(
            agent_factory=factory, emitter=emitter, max_concurrent=3
        )
        state = mgr.spawn("fail task")
        state.thread.join(timeout=2.0)
        assert state.status == SubagentStatus.FAILED
        assert "LLM exploded" in state.error

    def test_status_returns_all(self, manager):
        s1 = manager.spawn("task 1")
        s2 = manager.spawn("task 2")
        s1.thread.join(timeout=2.0)
        s2.thread.join(timeout=2.0)
        statuses = manager.get_status()
        assert len(statuses) == 2
        ids = {s["id"] for s in statuses}
        assert s1.id in ids
        assert s2.id in ids

    def test_status_returns_specific(self, manager):
        state = manager.spawn("task 1")
        state.thread.join(timeout=2.0)
        statuses = manager.get_status(state.id)
        assert len(statuses) == 1
        assert statuses[0]["id"] == state.id

    def test_status_unknown_id(self, manager):
        statuses = manager.get_status("nonexistent")
        assert len(statuses) == 1
        assert "error" in statuses[0]

    def test_result_completed(self, manager):
        state = manager.spawn("task 1")
        state.thread.join(timeout=2.0)
        result = manager.get_result(state.id)
        assert result["status"] == "completed"
        assert result["result"] == "Result for: task 1"

    def test_result_not_finished(self, slow_manager):
        state = slow_manager.spawn("slow task")
        result = slow_manager.get_result(state.id)
        assert "not finished" in result.get("message", "")
        slow_manager._gate.set()
        state.thread.join(timeout=2.0)

    def test_result_unknown_id(self, manager):
        result = manager.get_result("nonexistent")
        assert "error" in result

    def test_cancel_sets_status(self, slow_manager, collected_events):
        state = slow_manager.spawn("slow task")
        result = slow_manager.cancel(state.id)
        assert result["cancelled"] is True
        assert state.status == SubagentStatus.CANCELLED
        cancel_events = [
            e
            for e in collected_events
            if isinstance(e, SubagentStatusEvent) and e.status == "cancelled"
        ]
        assert len(cancel_events) >= 1
        # Release the gate so the thread can finish
        slow_manager._gate.set()
        state.thread.join(timeout=2.0)

    def test_cancel_already_completed(self, manager):
        state = manager.spawn("task")
        state.thread.join(timeout=2.0)
        result = manager.cancel(state.id)
        assert "already finished" in result.get("message", "")

    def test_cancel_unknown_id(self, manager):
        result = manager.cancel("nonexistent")
        assert "error" in result

    def test_status_event_emitted_on_completion(self, manager, collected_events):
        state = manager.spawn("task")
        state.thread.join(timeout=2.0)
        completed = [
            e
            for e in collected_events
            if isinstance(e, SubagentStatusEvent) and e.status == "completed"
        ]
        assert len(completed) == 1
        assert completed[0].subagent_id == state.id

    def test_status_event_emitted_on_failure(self, emitter, collected_events):
        def factory(task):
            mock_agent = MagicMock()
            mock_agent.run.side_effect = ValueError("bad")
            return mock_agent

        mgr = SubagentManager(
            agent_factory=factory, emitter=emitter, max_concurrent=3
        )
        state = mgr.spawn("fail")
        state.thread.join(timeout=2.0)
        failed = [
            e
            for e in collected_events
            if isinstance(e, SubagentStatusEvent) and e.status == "failed"
        ]
        assert len(failed) == 1
        assert "bad" in failed[0].error

    def test_active_count(self, slow_manager):
        slow_manager.spawn("task 1")
        slow_manager.spawn("task 2")
        assert slow_manager.active_count() == 2
        slow_manager._gate.set()

    def test_shutdown_cancels_all(self, slow_manager):
        s1 = slow_manager.spawn("task 1")
        s2 = slow_manager.spawn("task 2")
        slow_manager.shutdown()
        assert s1.status == SubagentStatus.CANCELLED
        assert s2.status == SubagentStatus.CANCELLED
        slow_manager._gate.set()
        s1.thread.join(timeout=2.0)
        s2.thread.join(timeout=2.0)
