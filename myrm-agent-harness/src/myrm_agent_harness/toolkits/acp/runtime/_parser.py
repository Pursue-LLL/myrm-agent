"""Shared NDJSON event parsers for CLI runtimes.

Provides common parsing logic for tool_use, tool_result, usage, and error
events. Each runtime delegates to these shared parsers for identical event
types and handles its own text/assistant format differences.

[INPUT]
- toolkits.acp.types::AcpError, AcpErrorCode, RuntimeEvent (POS: ACP runtime type definitions layer. Provides all ACP-related core abstractions and data structures, serving as the foundation for the entire ACP module.)

[OUTPUT]
- parse_json_line: Parse a JSON line, returning None for non-dict values.
- parse_tool_use: Parse a thinking/reasoning event. Returns None if no cont...
- parse_tool_result: function — parse_tool_result
- parse_usage: function — parse_usage
- parse_error: function — parse_error
- parse_ndjson_line: Parse one NDJSON line of a CLI agent (Claude, Codex, plain text) into a RuntimeEvent.

[POS]
Shared NDJSON event parsers for CLI and SDK runtimes.
"""

from __future__ import annotations

import json

from myrm_agent_harness.toolkits.acp.types import (
    AcpError,
    AcpErrorCode,
    RuntimeEvent,
    RuntimeEventType,
    create_event,
)


def parse_json_line(line: str) -> dict[str, object] | None:
    """Parse a JSON line, returning None for non-dict values.

    Non-JSON lines are returned as None; the caller should handle them
    as raw text.
    """
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def parse_tool_use(data: dict[str, object], session_id: str) -> RuntimeEvent:
    return create_event(
        RuntimeEventType.TOOL_START,
        session_id,
        tool_name=data.get("name", "unknown"),
        tool_input=data.get("input", {}),
        tool_call_id=data.get("id", ""),
    )


def parse_tool_result(data: dict[str, object], session_id: str) -> RuntimeEvent:
    return create_event(
        RuntimeEventType.TOOL_RESULT,
        session_id,
        tool_call_id=data.get("tool_use_id", ""),
        output=str(data.get("content", "")),
        is_error=data.get("is_error", False),
    )


def parse_usage(data: dict[str, object], session_id: str) -> RuntimeEvent:
    cache_read = data.get("cache_read_input_tokens") or data.get("cached_input_tokens") or 0
    return create_event(
        RuntimeEventType.USAGE_UPDATE,
        session_id,
        input_tokens=data.get("input_tokens", 0),
        output_tokens=data.get("output_tokens", 0),
        cache_read=cache_read,
        cache_write=data.get("cache_creation_input_tokens", 0),
    )


def parse_error(data: dict[str, object], session_id: str) -> RuntimeEvent:
    error_msg = data.get("error", {})
    if isinstance(error_msg, dict):
        msg = error_msg.get("message", str(error_msg))
    elif error_msg:
        msg = str(error_msg)
    else:
        msg = str(data.get("message", "Unknown error"))
    return create_event(
        RuntimeEventType.ERROR,
        session_id,
        error=AcpError(code=AcpErrorCode.UNKNOWN, message=msg),
    )


def parse_thinking(data: dict[str, object], session_id: str) -> RuntimeEvent | None:
    """Parse a thinking/reasoning event. Returns None if no content."""
    content = data.get("thinking", data.get("text", ""))
    if isinstance(content, str) and content:
        return create_event(RuntimeEventType.REASONING_DELTA, session_id, content=content)
    return None


def unwrap_codex_envelope(data: dict[str, object]) -> dict[str, object]:
    """Unwrap Codex CLI ``{"id": "0", "msg": {...}}`` envelope.

    Codex ``exec --json`` wraps events in an envelope with ``id`` and ``msg``
    fields. This extracts the inner ``msg`` dict so downstream parsing sees
    the same flat structure as Claude CLI events.
    """
    msg = data.get("msg")
    if isinstance(msg, dict) and "type" in msg:
        return msg
    return data


def parse_codex_item_event(data: dict[str, object], session_id: str) -> RuntimeEvent | None:
    """Parse Codex ``item.started`` / ``item.completed`` events.

    Maps Codex item types to RuntimeEvent types:
    - ``agent_message`` → TEXT_DELTA
    - ``reasoning`` → REASONING_DELTA
    - ``command_execution`` → TOOL_START (started) / TOOL_RESULT (completed)
    - ``file_change`` → TOOL_RESULT
    - ``error`` → ERROR
    """
    item = data.get("item")
    if not isinstance(item, dict):
        return None

    item_type = item.get("type", "")
    event_type = data.get("type", "")

    if item_type == "agent_message":
        text = item.get("text", "")
        if isinstance(text, str) and text:
            return create_event(RuntimeEventType.TEXT_DELTA, session_id, content=text)
        return None

    if item_type == "reasoning":
        text = item.get("text", "")
        if isinstance(text, str) and text:
            return create_event(RuntimeEventType.REASONING_DELTA, session_id, content=text)
        return None

    if item_type == "command_execution":
        item_id = str(item.get("id", ""))
        if event_type == "item.started":
            return create_event(
                RuntimeEventType.TOOL_START,
                session_id,
                tool_name="command_execution",
                tool_input={"command": item.get("command", "")},
                tool_call_id=item_id,
            )
        return create_event(
            RuntimeEventType.TOOL_RESULT,
            session_id,
            tool_call_id=item_id,
            output=str(item.get("aggregated_output", "")),
            is_error=item.get("status") == "failed",
        )

    if item_type == "file_change" and event_type == "item.completed":
        changes = item.get("changes", [])
        summary = (
            ", ".join(f"{c.get('kind', '?')} {c.get('path', '?')}" for c in changes if isinstance(c, dict))
            if isinstance(changes, list)
            else str(changes)
        )
        return create_event(
            RuntimeEventType.TOOL_RESULT,
            session_id,
            tool_call_id=str(item.get("id", "")),
            output=summary,
            is_error=item.get("status") == "failed",
        )

    if item_type == "error":
        msg = item.get("message", "Unknown item error")
        return create_event(
            RuntimeEventType.STATUS_UPDATE,
            session_id,
            status="warning",
            message=str(msg),
            is_error=False,
        )

    return None


def extract_text_from_event(data: dict[str, object]) -> str | None:
    """Extract text content from an assistant/text event.

    Handles both flat content (string) and nested Claude CLI format
    (message.content[{type: "text", text: "..."}]).
    """
    content = data.get("content", "")
    if not content:
        message = data.get("message")
        if isinstance(message, dict):
            content = message.get("content", "")

    if isinstance(content, str) and content:
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if isinstance(text, str) and text:
                    parts.append(text)
        return "".join(parts) if parts else None

    return None


def parse_ndjson_line(line: str, session_id: str) -> RuntimeEvent | None:
    """Parse a single NDJSON line into a RuntimeEvent.

    Handles three formats:
    - Claude CLI stream-json (``type: "assistant"`` / ``"tool_use"`` etc.)
    - Codex CLI legacy (``{"id","msg":{...}}`` envelope, deprecated)
    - Codex CLI new format (``item.started`` / ``item.completed`` /
      ``turn.completed`` / ``turn.failed``)
    """
    data = parse_json_line(line)
    if data is None:
        from myrm_agent_harness.utils.text_utils import strip_ansi

        cleaned = strip_ansi(line).rstrip("\r\n")
        return create_event(RuntimeEventType.TEXT_DELTA, session_id, content=cleaned + "\n") if cleaned else None

    data = unwrap_codex_envelope(data)
    event_type = data.get("type", "")

    # --- Codex new format: item.* events ---
    if event_type in ("item.started", "item.updated", "item.completed"):
        return parse_codex_item_event(data, session_id)

    if event_type == "turn.completed":
        usage = data.get("usage")
        if isinstance(usage, dict):
            return parse_usage(usage, session_id)
        return None

    if event_type == "turn.failed":
        error_obj = data.get("error")
        msg = error_obj.get("message", "Turn failed") if isinstance(error_obj, dict) else "Turn failed"
        return create_event(
            RuntimeEventType.ERROR,
            session_id,
            error=AcpError(code=AcpErrorCode.UNKNOWN, message=str(msg)),
        )

    # --- Claude CLI / generic format ---
    if event_type in ("assistant", "text"):
        text = extract_text_from_event(data)
        if text:
            return create_event(RuntimeEventType.TEXT_DELTA, session_id, content=text)
        return None

    if event_type == "agent_message":
        message = data.get("message")
        if isinstance(message, str) and message:
            return create_event(RuntimeEventType.TEXT_DELTA, session_id, content=message)
        return None

    if event_type == "thinking":
        return parse_thinking(data, session_id)

    if event_type == "tool_use":
        return parse_tool_use(data, session_id)

    if event_type == "tool_result":
        return parse_tool_result(data, session_id)

    if event_type in ("usage", "token_count"):
        info = data.get("info")
        if isinstance(info, dict):
            return parse_usage(info, session_id)
        return parse_usage(data, session_id)

    if event_type == "result":
        usage = data.get("usage")
        if isinstance(usage, dict):
            return parse_usage(usage, session_id)
        return None

    if event_type in ("error", "stream_error"):
        return parse_error(data, session_id)

    return None
