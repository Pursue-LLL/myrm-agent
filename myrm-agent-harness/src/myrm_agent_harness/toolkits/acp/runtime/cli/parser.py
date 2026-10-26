"""Event builders shared by the CLI output formats.

Each function turns one decoded NDJSON object (or part of it) of a CLI agent into a RuntimeEvent: tool calls and
results, usage, errors, thinking and the Codex ``item.*`` events. ``TurnParser`` composes them into the parser of
a whole turn; formats that nest several events in one line (Claude content blocks) are split there.

[INPUT]
- toolkits.acp.types::AcpError, AcpErrorCode, RuntimeEvent (POS: ACP runtime type definitions layer. Provides all ACP-related core abstractions and data structures, serving as the foundation for the entire ACP module.)

[OUTPUT]
- parse_json_line: Parse a JSON line, returning None for non-dict values.
- parse_tool_use / parse_tool_result: tool call and result events with a one-line summary / bounded output
- parse_usage / parse_thinking: usage and reasoning events
- error_message / parse_turn_failed: the text of an ``error`` line, and the error event of Codex's ``turn.failed``
- unwrap_codex_envelope / parse_codex_item_event: the Codex legacy envelope and ``item.*`` events
- extract_text_from_event: text of a flat or nested assistant/text event
- tool_summary: one short line telling what a tool call works on

[POS]
Shared event builders of the CLI runtime's output parsing.
"""

from __future__ import annotations

import json
import re

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


# One tool result can be a whole file; consumers only show a short excerpt of it.
_MAX_TOOL_OUTPUT_CHARS = 2000
_MAX_SUMMARY_CHARS = 80
_SUMMARY_KEYS = ("file_path", "path", "command", "pattern", "query", "url", "description")


def tool_summary(tool_input: object) -> str:
    """One short line telling what a tool call works on (a path, a command, a query); empty when nothing fits."""
    if not isinstance(tool_input, dict):
        return ""
    for key in _SUMMARY_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            first_line = value.strip().splitlines()[0].strip()
            if len(first_line) > _MAX_SUMMARY_CHARS:
                return first_line[: _MAX_SUMMARY_CHARS - 1] + "…"
            return first_line
    return ""


def _result_text(content: object) -> str:
    """The text of a tool result: a plain string or a list of content blocks; anything else has none."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block["text"] for block in content if isinstance(block, dict) and isinstance(block.get("text"), str)
        )
    return ""


def parse_tool_use(data: dict[str, object], session_id: str) -> RuntimeEvent:
    tool_input = data.get("input", {})
    return create_event(
        RuntimeEventType.TOOL_START,
        session_id,
        tool_name=data.get("name", "unknown"),
        tool_input=tool_input,
        tool_call_id=data.get("id", ""),
        summary=tool_summary(tool_input),
    )


def parse_tool_result(data: dict[str, object], session_id: str) -> RuntimeEvent:
    return create_event(
        RuntimeEventType.TOOL_RESULT,
        session_id,
        tool_call_id=data.get("tool_use_id", ""),
        output=_result_text(data.get("content", ""))[:_MAX_TOOL_OUTPUT_CHARS],
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


def error_message(data: dict[str, object], default: str) -> str:
    """The text of an ``error`` / ``turn.failed`` line: its ``error`` object or string, else its own ``message``.

    Claude and generic CLIs nest the text under ``error``; Codex puts it at the top level of the line.
    """
    error = data.get("error")
    if isinstance(error, dict) and error:
        text = error.get("message") or str(error)
    else:
        text = error or data.get("message")
    return str(text) if text else default


# Codex words an HTTP failure of its model API as "unexpected status <code> <reason>: <body>". Only 401 is a
# login problem: 403 is also what a blocked region or an organization policy answers.
_CODEX_UNAUTHORIZED = re.compile(r"\bunexpected status 401\b")


def parse_turn_failed(data: dict[str, object], session_id: str) -> RuntimeEvent:
    """The error event of Codex's ``turn.failed`` — the CLI's verdict that the turn did not finish."""
    message = error_message(data, "Turn failed")
    code = AcpErrorCode.AUTH_FAILED if _CODEX_UNAUTHORIZED.search(message) else AcpErrorCode.UNKNOWN
    return create_event(RuntimeEventType.ERROR, session_id, error=AcpError(code=code, message=message))


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
    - ``error`` → STATUS_UPDATE (``warning``): a note about one item, not a failed turn
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
            tool_input = {"command": item.get("command", "")}
            return create_event(
                RuntimeEventType.TOOL_START,
                session_id,
                tool_name="command_execution",
                tool_input=tool_input,
                tool_call_id=item_id,
                summary=tool_summary(tool_input),
            )
        return create_event(
            RuntimeEventType.TOOL_RESULT,
            session_id,
            tool_call_id=item_id,
            output=str(item.get("aggregated_output", ""))[:_MAX_TOOL_OUTPUT_CHARS],
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
