"""Event formatting for terminal display."""

from typing import Any

from src.events import (
    AgentEvent,
    AutoMemoryStoredEvent,
    ContextCompressedEvent,
    ContinuationEvent,
    LLMEndEvent,
    LLMStartEvent,
    RunSummaryEvent,
    SubagentResultsCollectedEvent,
    SubagentSpawnedEvent,
    SubagentStatusEvent,
    SubagentWaitEvent,
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
        if event.has_tool_calls:
            action = f"{event.tool_call_count} tool call{'s' if event.tool_call_count != 1 else ''}"
        else:
            action = "response"
        line = f"  [llm] done ({action}, {event.duration_ms}ms)"
        if event.response_preview:
            preview = event.response_preview.replace("\n", " ")
            line += f' "{preview}"'
        return line
    elif isinstance(event, ToolStartEvent):
        args_display = ", ".join(f"{k}={v!r}" for k, v in event.arguments.items())
        if len(args_display) > 200:
            args_display = args_display[:200] + "..."
        return f"  [tool] {event.tool_name}({args_display})"
    elif isinstance(event, ToolEndEvent):
        line = f"  [tool] done ({event.duration_ms}ms)"
        if event.result_preview:
            preview = event.result_preview.replace("\n", " ")[:100]
            line += f" → {preview}"
        return line
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
    elif isinstance(event, SubagentWaitEvent):
        return f"  [subagent] waiting for {event.active_count} subagent(s) to finish..."
    elif isinstance(event, SubagentResultsCollectedEvent):
        return f"  [subagent] collected {event.count} result(s) ({event.duration_ms}ms)"
    elif isinstance(event, AutoMemoryStoredEvent):
        preview = event.content[:80].replace("\n", " ")
        return f"  [memory] auto-stored: {preview}..."
    elif isinstance(event, ContinuationEvent):
        return (
            f"  [continue] auto-continuing "
            f"({event.continuation_number}/{event.max_continuations})"
        )
    elif isinstance(event, RunSummaryEvent):
        return (
            f"  [agent] done in {event.total_rounds} round{'s' if event.total_rounds != 1 else ''} "
            f"({event.tool_calls_made} tool calls, "
            f"{event.continuations_used} continuations, "
            f"{event.total_duration_ms}ms)"
        )
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
        if msg.get("has_tool_calls"):
            count = msg.get("tool_call_count", 0)
            action = f"{count} tool call{'s' if count != 1 else ''}"
        else:
            action = "response"
        line = f"  [llm] done ({action}, {msg.get('duration_ms', '?')}ms)"
        preview = msg.get("response_preview")
        if preview:
            preview = preview.replace("\n", " ")
            line += f' "{preview}"'
        return line
    elif msg_type == "tool_start":
        args = msg.get("arguments", {})
        args_display = ", ".join(f"{k}={v!r}" for k, v in args.items())
        if len(args_display) > 200:
            args_display = args_display[:200] + "..."
        return f"  [tool] {msg.get('tool_name', '')}({args_display})"
    elif msg_type == "tool_end":
        line = f"  [tool] done ({msg.get('duration_ms', '?')}ms)"
        preview = msg.get("result_preview")
        if preview:
            preview = preview.replace("\n", " ")[:100]
            line += f" → {preview}"
        return line
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
    elif msg_type == "subagent_wait":
        return (
            f"  [subagent] waiting for {msg.get('active_count', '?')} "
            f"subagent(s) to finish..."
        )
    elif msg_type == "subagent_results_collected":
        return (
            f"  [subagent] collected {msg.get('count', '?')} result(s) "
            f"({msg.get('duration_ms', '?')}ms)"
        )
    elif msg_type == "auto_memory_stored":
        preview = msg.get("content", "")[:80].replace("\n", " ")
        return f"  [memory] auto-stored: {preview}..."
    elif msg_type == "continuation":
        return (
            f"  [continue] auto-continuing "
            f"({msg.get('continuation_number', '?')}/{msg.get('max_continuations', '?')})"
        )
    elif msg_type == "run_summary":
        rounds = msg.get("total_rounds", "?")
        return (
            f"  [agent] done in {rounds} round{'s' if rounds != 1 else ''} "
            f"({msg.get('tool_calls_made', '?')} tool calls, "
            f"{msg.get('continuations_used', '?')} continuations, "
            f"{msg.get('total_duration_ms', '?')}ms)"
        )

    return None
