"""Event types and emitter for agent lifecycle notifications."""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ToolStartEvent:
    """Emitted when a tool call begins."""

    tool_name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolEndEvent:
    """Emitted when a tool call completes successfully."""

    tool_name: str
    duration_ms: int


@dataclass(frozen=True)
class ToolErrorEvent:
    """Emitted when a tool call fails."""

    tool_name: str
    error: str
    duration_ms: int


@dataclass(frozen=True)
class LLMStartEvent:
    """Emitted when an LLM call begins."""

    round_number: int
    message_count: int
    estimated_tokens: int


@dataclass(frozen=True)
class LLMEndEvent:
    """Emitted when an LLM call completes."""

    round_number: int
    has_tool_calls: bool
    duration_ms: int


@dataclass(frozen=True)
class ContextCompressedEvent:
    """Emitted when context was compressed to save space."""

    original_tokens: int
    compressed_tokens: int
    messages_removed: int


@dataclass(frozen=True)
class SubagentSpawnedEvent:
    """Emitted when a subagent is created and its thread starts."""

    subagent_id: str
    task: str


@dataclass(frozen=True)
class SubagentStatusEvent:
    """Emitted when a subagent's status changes."""

    subagent_id: str
    task: str
    status: str  # "running", "completed", "failed", "cancelled"
    error: str | None = None


AgentEvent = (
    ToolStartEvent
    | ToolEndEvent
    | ToolErrorEvent
    | LLMStartEvent
    | LLMEndEvent
    | ContextCompressedEvent
    | SubagentSpawnedEvent
    | SubagentStatusEvent
)

EventCallback = Callable[[AgentEvent], None]


class EventEmitter:
    """Simple synchronous event emitter.

    If no listeners are registered, events are silently dropped.
    """

    def __init__(self) -> None:
        self._listeners: list[EventCallback] = []

    def on(self, callback: EventCallback) -> None:
        """Register a listener."""
        self._listeners.append(callback)

    def off(self, callback: EventCallback) -> None:
        """Remove a listener."""
        self._listeners.remove(callback)

    def emit(self, event: AgentEvent) -> None:
        """Dispatch event to all registered listeners."""
        for listener in self._listeners:
            listener(event)
