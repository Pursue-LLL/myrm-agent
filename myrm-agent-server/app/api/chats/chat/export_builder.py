"""Chat export payload aggregation and sanitization builders.

[INPUT]
- chat_id: str, db: AsyncSession, redact_secrets: bool
- myrm_agent_harness.agent.event_log.backends.file_backend::FileEventLogBackend
- myrm_agent_harness.agent.event_log.trace_builder::build_trace
- myrm_agent_harness.agent.event_log.trace_types::ToolCallRecord
- myrm_agent_harness.core.security.redact.engine::redact_sensitive_text
- app.database.models.agent::Agent
- app.database.models.chat::Message

[OUTPUT]
- build_tool_summary: aggregate tool call statistics from harness event log
- build_tool_call_details: extract tool call records with argument sanitization
- build_agent_info: fetch agent identity metadata
- redact_export_payload: sanitize secrets across exported chat structures

[POS]
api/chats/chat export helper. Keeps messages.py under the 400-line budget and
encapsulates tool-call aggregation and payload redaction logic.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Final

from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.trace_builder import build_trace
from myrm_agent_harness.agent.event_log.trace_types import ToolCallRecord
from myrm_agent_harness.core.security.redact.engine import redact_sensitive_text
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.database.models.agent import Agent
from app.database.models.chat import Message

_SENSITIVE_KEY_PATTERN_PARTS: Final[tuple[str, ...]] = (
    "key",
    "secret",
    "token",
    "password",
    "credential",
    "auth",
)
_ARG_SUMMARY_MAX_LEN: Final[int] = 200


def redact_export_payload(payload: dict[str, object]) -> dict[str, object]:
    """Sanitize secrets across all exported chat structures."""
    chat_meta = payload.get("chat")
    if isinstance(chat_meta, dict) and isinstance(chat_meta.get("title"), str):
        chat_meta["title"] = redact_sensitive_text(chat_meta["title"])

    for msg in payload.get("messages") or []:
        if isinstance(msg, dict):
            if isinstance(msg.get("content"), str):
                msg["content"] = redact_sensitive_text(msg["content"])
            meta = msg.get("metadata")
            if isinstance(meta, dict) and isinstance(meta.get("reasoning_content"), str):
                meta["reasoning_content"] = redact_sensitive_text(meta["reasoning_content"])

    for tool_call in payload.get("toolCallDetails") or []:
        if isinstance(tool_call, dict) and isinstance(tool_call.get("argsSummary"), str):
            tool_call["argsSummary"] = redact_sensitive_text(tool_call["argsSummary"])

    agent_info = payload.get("agentInfo")
    if isinstance(agent_info, dict) and isinstance(agent_info.get("description"), str):
        agent_info["description"] = redact_sensitive_text(agent_info["description"])

    return payload


async def load_tool_calls(chat_id: str) -> list[ToolCallRecord]:
    """Read a chat's real tool calls from the harness event log (agent-event SSOT)."""
    log_dir = Path(settings.database.event_log_dir)
    if not (log_dir / f"{chat_id}.jsonl").exists():
        return []
    backend = FileEventLogBackend(log_dir=log_dir, session_id=chat_id)
    trace = await build_trace(backend, chat_id)
    return list(trace.tool_calls)


async def build_tool_summary(chat_id: str, db: AsyncSession) -> dict[str, object] | None:
    """Aggregate tool call statistics from the harness event log.

    Returns None when no tool activity exists for this chat.
    """
    tool_calls = await load_tool_calls(chat_id)
    if not tool_calls:
        return None

    tool_buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "totalMs": 0})
    total_calls = 0
    total_ms = 0
    for call in tool_calls:
        bucket = tool_buckets[call.tool_name]
        bucket["count"] += 1
        bucket["totalMs"] += int(call.duration_ms or 0)
        total_calls += 1
        total_ms += int(call.duration_ms or 0)

    tools_used = sorted(
        [{"name": name, "count": b["count"], "totalMs": b["totalMs"]} for name, b in tool_buckets.items()],
        key=lambda x: x["count"],
        reverse=True,
    )

    return {
        "totalToolCalls": total_calls,
        "totalDurationMs": total_ms,
        "toolsUsed": tools_used,
    }


async def build_agent_info(agent_id: str | None, db: AsyncSession) -> dict[str, str | None] | None:
    """Fetch Agent identity for export (name, model, description)."""
    if not agent_id:
        return None

    agent = (await db.execute(select(Agent).where(Agent.id == agent_id))).scalar_one_or_none()
    if not agent:
        return None

    model_name: str | None = None
    if agent.model_selection and isinstance(agent.model_selection, dict):
        model_name = agent.model_selection.get("model")

    return {
        "name": agent.name,
        "model": model_name,
        "description": agent.description or None,
    }


def sanitize_args_summary(payload: dict[str, object]) -> str:
    """Extract a truncated, sanitized summary of tool call arguments.

    Accepts the raw tool input (event-log ``input_data``) directly, or a payload
    that wraps arguments under ``arguments``/``args``/``input``.
    """
    args: object = payload
    if isinstance(payload, dict):
        for key in ("arguments", "args", "input"):
            if payload.get(key):
                args = payload[key]
                break
    if not args:
        return ""
    if isinstance(args, str):
        text = args
    else:
        parts: list[str] = []
        items = args.items() if isinstance(args, dict) else []
        for k, v in items:
            k_lower = str(k).lower()
            if any(pat in k_lower for pat in _SENSITIVE_KEY_PATTERN_PARTS):
                parts.append(f"{k}=***")
            else:
                val_str = str(v) if not isinstance(v, str) else v
                if len(val_str) > 80:
                    val_str = val_str[:77] + "..."
                parts.append(f"{k}={val_str}")
        text = ", ".join(parts)

    if len(text) > _ARG_SUMMARY_MAX_LEN:
        return text[: _ARG_SUMMARY_MAX_LEN - 3] + "..."
    return text


async def build_tool_call_details(chat_id: str, db: AsyncSession) -> list[dict[str, object]] | None:
    """Fetch per-tool-call details from the harness event log.

    ``turnIndex`` maps each call to the assistant message that produced it:
    by the event's ``message_id`` when present, otherwise by the first
    assistant message sent at or after the call's start time.
    """
    tool_calls = await load_tool_calls(chat_id)
    if not tool_calls:
        return None

    assistant_rows = (
        await db.execute(
            select(Message.id, Message.sent_at)
            .where(Message.chat_id == chat_id, Message.role == "assistant")
            .order_by(Message.sent_at)
        )
    ).all()
    by_message_id = {str(row.id): index for index, row in enumerate(assistant_rows)}
    message_windows = [(row.sent_at.timestamp(), index) for index, row in enumerate(assistant_rows)]

    details: list[dict[str, object]] = []
    for call in tool_calls:
        turn_index = by_message_id.get(str(call.message_id)) if call.message_id else None
        if turn_index is None:
            turn_index = _assistant_turn_index_at(call.start_time, message_windows)
        details.append({
            "turnIndex": turn_index,
            "name": call.tool_name,
            "argsSummary": sanitize_args_summary(call.input_data),
            "durationMs": int(call.duration_ms) if call.duration_ms is not None else None,
            "success": call.success,
        })
    return details


def _assistant_turn_index_at(start_time: float, windows: list[tuple[float, int]]) -> int:
    """Index of the first assistant message sent at/after ``start_time`` (last if none)."""
    for sent_at, index in windows:
        if start_time <= sent_at:
            return index
    return windows[-1][1] if windows else 0
