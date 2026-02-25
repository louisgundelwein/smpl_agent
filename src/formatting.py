"""Event formatting for terminal display."""

from typing import Any

from src.events import (
    AgentEvent,
    ContextCompressedEvent,
    LLMEndEvent,
    LLMStartEvent,
    SubagentSpawnedEvent,
    SubagentStatusEvent,
    ToolEndEvent,
    ToolErrorEvent,
    ToolStartEvent,
)


def format_event(event: AgentEvent) -> str | None:
    """Format an AgentEvent into a terminal-display string.

    Returns None if the event should not produce output.
    """
    if isinstance(event, LLMStartEvent):
        return (
            f"  [llm] round {event.round_number} "
            f"({event.message_count} messages, ~{event.estimated_tokens} tokens)"
        )
    elif isinstance(event, LLMEndEvent):
        action = "tool calls" if event.has_tool_calls else "response"
        return f"  [llm] done ({action}, {event.duration_ms}ms)"
    elif isinstance(event, ToolStartEvent):
        args_display = ", ".join(f"{k}={v!r}" for k, v in event.arguments.items())
        return f"  [tool] {event.tool_name}({args_display})"
    elif isinstance(event, ToolEndEvent):
        return f"  [tool] done ({event.duration_ms}ms)"
    elif isinstance(event, ToolErrorEvent):
        return f"  [tool] error: {event.error} ({event.duration_ms}ms)"
    elif isinstance(event, ContextCompressedEvent):
        return (
            f"  [context] compressed: {event.messages_removed} messages removed "
            f"(~{event.original_tokens} \u2192 ~{event.compressed_tokens} tokens)"
        )
    elif isinstance(event, SubagentSpawnedEvent):
        return f"  [subagent] spawned {event.subagent_id}: {event.task[:80]}"
    elif isinstance(event, SubagentStatusEvent):
        suffix = f" error: {event.error}" if event.error else ""
        return f"  [subagent] {event.subagent_id} \u2192 {event.status}{suffix}"
    return None


def format_message(msg: dict[str, Any]) -> str | None:
    """Format a protocol message dict into a terminal-display string.

    Used by the TCP client, which receives events as JSON dicts
    rather than as typed AgentEvent objects.

    Returns None if the message should not produce output.
    """
    msg_type = msg.get("type")

    if msg_type == "llm_start":
        return (
            f"  [llm] round {msg.get('round_number', '?')} "
            f"({msg.get('message_count', '?')} messages, "
            f"~{msg.get('estimated_tokens', '?')} tokens)"
        )
    elif msg_type == "llm_end":
        action = "tool calls" if msg.get("has_tool_calls") else "response"
        return f"  [llm] done ({action}, {msg.get('duration_ms', '?')}ms)"
    elif msg_type == "tool_start":
        args = msg.get("arguments", {})
        args_display = ", ".join(f"{k}={v!r}" for k, v in args.items())
        return f"  [tool] {msg.get('tool_name', '')}({args_display})"
    elif msg_type == "tool_end":
        return f"  [tool] done ({msg.get('duration_ms', '?')}ms)"
    elif msg_type == "tool_error":
        return f"  [tool] error: {msg.get('error', '')} ({msg.get('duration_ms', '?')}ms)"
    elif msg_type == "context_compressed":
        return (
            f"  [context] compressed: {msg.get('messages_removed', '?')} messages removed "
            f"(~{msg.get('original_tokens', '?')} \u2192 ~{msg.get('compressed_tokens', '?')} tokens)"
        )
    elif msg_type == "response":
        return f"\nAgent: {msg.get('content', '')}\n"
    elif msg_type == "reset_ack":
        return "Conversation reset.\n"
    elif msg_type == "busy":
        return f"\nBusy: {msg.get('content', '')}\n"
    elif msg_type == "subagent_spawned":
        return (
            f"  [subagent] spawned {msg.get('subagent_id', '?')}: "
            f"{msg.get('task', '')[:80]}"
        )
    elif msg_type == "subagent_status":
        suffix = f" error: {msg.get('error', '')}" if msg.get("error") else ""
        return (
            f"  [subagent] {msg.get('subagent_id', '?')} \u2192 "
            f"{msg.get('status', '?')}{suffix}"
        )

    return None
