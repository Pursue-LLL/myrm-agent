"""Export helpers for chat messages endpoint.

[INPUT]
app.database.models.agent::Agent
myrm_agent_harness.agent.event_log.backends.file_backend::FileEventLogBackend
myrm_agent_harness.agent.event_log.trace_builder::build_trace
myrm_agent_harness.api::redact_nested, redact_field_text (POS: shared walker and field-aware credential masking of the redaction domain)
sqlalchemy.ext.asyncio::AsyncSession

[OUTPUT]
Export helper functions and sanitizers for chat messages export.

[POS]
app.api.chats.chat.export_helpers: Supporting logic for chat export, tool summaries, and redaction.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Final, cast

from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.trace_builder import build_trace
from myrm_agent_harness.agent.event_log.trace_types import ToolCallRecord
from myrm_agent_harness.api import redact_field_text, redact_nested
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.database.models.agent import Agent
from app.database.models.chat import Message

_ARG_SUMMARY_MAX_LEN: Final[int] = 200


def redact_export_payload(payload: dict[str, object]) -> dict[str, object]:
    """Mask credentials in every string and key of an export payload, by the name of the field that holds it.

    A container nested deeper than the walker's limit is replaced by a marker, never exported as it is.
    """
    return cast("dict[str, object]", redact_nested(payload, redact_field_text, mask_keys=True))


async def load_tool_calls(chat_id: str) -> list[ToolCallRecord]:
    """Read a chat's real tool calls from the harness event log (agent-event SSOT)."""
    log_dir = Path(settings.database.event_log_dir)
    if not (log_dir / f"{chat_id}.jsonl").exists():
        return []
    backend = FileEventLogBackend(log_dir=log_dir, session_id=chat_id)
    trace = await build_trace(backend, chat_id)
    return list(trace.tool_calls)


async def build_tool_summary(chat_id: str, db: AsyncSession) -> dict[str, object] | None:
    """Aggregate tool call statistics from the harness event log."""
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

    model = agent.model_selection.get("model") if isinstance(agent.model_selection, dict) else None
    model_name = model if isinstance(model, str) else None

    return {
        "name": agent.name,
        "model": model_name,
        "description": agent.description or None,
    }


def build_args_summary(payload: dict) -> str:
    """Extract a truncated summary of tool call arguments.

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
            val_str = str(v) if not isinstance(v, str) else v
            if len(val_str) > 80:
                val_str = val_str[:77] + "..."
            parts.append(f"{k}={val_str}")
        text = ", ".join(parts)

    if len(text) > _ARG_SUMMARY_MAX_LEN:
        return text[: _ARG_SUMMARY_MAX_LEN - 3] + "..."
    return text


def assistant_turn_index_at(start_time: float, windows: list[tuple[float, int]]) -> int:
    """Index of the first assistant message sent at/after ``start_time`` (last if none)."""
    for sent_at, index in windows:
        if start_time <= sent_at:
            return index
    return windows[-1][1] if windows else 0


def _args_of(call: ToolCallRecord, *, redact_secrets: bool) -> dict[str, object]:
    """Tool input of ``call``; credentials are masked while the fields still have names, before the flat summary."""
    if not redact_secrets:
        return call.input_data
    return cast("dict[str, object]", redact_nested(call.input_data, redact_field_text))


async def build_tool_call_details(chat_id: str, db: AsyncSession, *, redact_secrets: bool) -> list[dict[str, object]] | None:
    """Fetch per-tool-call details from the harness event log."""
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
            turn_index = assistant_turn_index_at(call.start_time, message_windows)
        details.append(
            {
                "turnIndex": turn_index,
                "name": call.tool_name,
                "argsSummary": build_args_summary(_args_of(call, redact_secrets=redact_secrets)),
                "durationMs": int(call.duration_ms) if call.duration_ms is not None else None,
                "success": call.success,
            }
        )
    return details
