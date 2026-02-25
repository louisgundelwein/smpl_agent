"""Subagent manager for concurrent task execution."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

from src.events import EventEmitter, SubagentSpawnedEvent, SubagentStatusEvent

if TYPE_CHECKING:
    from src.agent import Agent

logger = logging.getLogger(__name__)


class SubagentStatus(Enum):
    """Lifecycle states for a subagent."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SubagentState:
    """Mutable state tracking a single subagent."""

    id: str
    task: str
    status: SubagentStatus = SubagentStatus.PENDING
    result: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.monotonic)
    started_at: float | None = None
    completed_at: float | None = None
    thread: threading.Thread | None = field(default=None, repr=False)
    cancel_flag: threading.Event = field(
        default_factory=threading.Event, repr=False
    )

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable snapshot (no thread/event refs)."""
        elapsed = None
        if self.started_at:
            end = self.completed_at or time.monotonic()
            elapsed = round(end - self.started_at, 1)
        return {
            "id": self.id,
            "task": self.task,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "elapsed_seconds": elapsed,
        }


class SubagentManager:
    """Manages subagent lifecycle, concurrency, and result collection.

    Thread-safe: all mutable state access is guarded by a lock.
    The manager receives an agent_factory callable that creates a fresh
    Agent for each subagent, keeping the manager decoupled from config.
    """

    def __init__(
        self,
        agent_factory: Callable[[str], Agent],
        emitter: EventEmitter | None = None,
        max_concurrent: int = 10,
    ) -> None:
        self._agent_factory = agent_factory
        self._emitter = emitter or EventEmitter()
        self._max_concurrent = max_concurrent
        self._lock = threading.Lock()
        self._subagents: dict[str, SubagentState] = {}

    def spawn(self, task: str) -> SubagentState:
        """Create a new subagent and start it in a background thread.

        Raises RuntimeError if max concurrent subagents reached.
        """
        with self._lock:
            active = sum(
                1
                for s in self._subagents.values()
                if s.status in (SubagentStatus.PENDING, SubagentStatus.RUNNING)
            )
            if active >= self._max_concurrent:
                raise RuntimeError(
                    f"Maximum concurrent subagents ({self._max_concurrent}) reached"
                )

            subagent_id = uuid.uuid4().hex[:8]
            state = SubagentState(id=subagent_id, task=task)
            self._subagents[subagent_id] = state

        thread = threading.Thread(
            target=self._run_subagent,
            args=(state,),
            name=f"subagent-{subagent_id}",
            daemon=True,
        )
        state.thread = thread
        thread.start()

        self._emitter.emit(
            SubagentSpawnedEvent(subagent_id=subagent_id, task=task)
        )

        return state

    def get_status(self, subagent_id: str | None = None) -> list[dict[str, Any]]:
        """Return status of all subagents, or a specific one."""
        with self._lock:
            if subagent_id:
                state = self._subagents.get(subagent_id)
                if not state:
                    return [{"error": f"Unknown subagent: {subagent_id}"}]
                return [state.to_dict()]
            return [s.to_dict() for s in self._subagents.values()]

    def get_result(self, subagent_id: str) -> dict[str, Any]:
        """Return the result of a completed subagent."""
        with self._lock:
            state = self._subagents.get(subagent_id)
        if not state:
            return {"error": f"Unknown subagent: {subagent_id}"}
        if state.status == SubagentStatus.COMPLETED:
            return {"id": state.id, "status": "completed", "result": state.result}
        elif state.status == SubagentStatus.FAILED:
            return {"id": state.id, "status": "failed", "error": state.error}
        else:
            return {
                "id": state.id,
                "status": state.status.value,
                "message": "Subagent has not finished yet",
            }

    def cancel(self, subagent_id: str) -> dict[str, Any]:
        """Cancel a running subagent (best-effort)."""
        with self._lock:
            state = self._subagents.get(subagent_id)
        if not state:
            return {"error": f"Unknown subagent: {subagent_id}"}
        if state.status not in (SubagentStatus.PENDING, SubagentStatus.RUNNING):
            return {
                "id": state.id,
                "status": state.status.value,
                "message": "Cannot cancel — already finished",
            }
        state.cancel_flag.set()
        state.status = SubagentStatus.CANCELLED
        state.completed_at = time.monotonic()
        self._emitter.emit(
            SubagentStatusEvent(
                subagent_id=state.id,
                task=state.task,
                status="cancelled",
            )
        )
        return {"id": state.id, "cancelled": True}

    def active_count(self) -> int:
        """Number of subagents that are pending or running."""
        with self._lock:
            return sum(
                1
                for s in self._subagents.values()
                if s.status in (SubagentStatus.PENDING, SubagentStatus.RUNNING)
            )

    def shutdown(self) -> None:
        """Cancel all running subagents."""
        with self._lock:
            ids = [
                s.id
                for s in self._subagents.values()
                if s.status in (SubagentStatus.PENDING, SubagentStatus.RUNNING)
            ]
        for sid in ids:
            self.cancel(sid)

    def wait_all(self, timeout: float | None = None) -> list[dict[str, Any]]:
        """Block until all pending/running subagents complete.

        Returns a list of result dicts for subagents that were waited on.
        Thread-safe: snapshots active threads under lock, then joins
        without holding the lock so subagent threads can update state.
        """
        with self._lock:
            active = [
                s
                for s in self._subagents.values()
                if s.status in (SubagentStatus.PENDING, SubagentStatus.RUNNING)
            ]

        for state in active:
            if state.thread is not None:
                state.thread.join(timeout=timeout)
                if state.thread.is_alive():
                    state.status = SubagentStatus.FAILED
                    state.error = "Timed out waiting for completion"
                    state.completed_at = time.monotonic()

        return [s.to_dict() for s in active]

    def _run_subagent(self, state: SubagentState) -> None:
        """Thread target: run the subagent's agent loop."""
        state.status = SubagentStatus.RUNNING
        state.started_at = time.monotonic()

        self._emitter.emit(
            SubagentStatusEvent(
                subagent_id=state.id,
                task=state.task,
                status="running",
            )
        )

        try:
            if state.cancel_flag.is_set():
                state.status = SubagentStatus.CANCELLED
                state.completed_at = time.monotonic()
                self._emitter.emit(
                    SubagentStatusEvent(
                        subagent_id=state.id,
                        task=state.task,
                        status="cancelled",
                    )
                )
                return

            agent = self._agent_factory(state.task)
            result = agent.run(state.task)

            # Check cancel after run (result discarded if cancelled)
            if state.cancel_flag.is_set():
                state.status = SubagentStatus.CANCELLED
                state.completed_at = time.monotonic()
                return

            state.result = result
            state.status = SubagentStatus.COMPLETED
            state.completed_at = time.monotonic()

            self._emitter.emit(
                SubagentStatusEvent(
                    subagent_id=state.id,
                    task=state.task,
                    status="completed",
                )
            )

        except Exception as exc:
            logger.exception("Subagent %s failed", state.id)
            state.error = str(exc)
            state.status = SubagentStatus.FAILED
            state.completed_at = time.monotonic()

            self._emitter.emit(
                SubagentStatusEvent(
                    subagent_id=state.id,
                    task=state.task,
                    status="failed",
                    error=str(exc),
                )
            )
