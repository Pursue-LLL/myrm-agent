"""Pre-reply idle compact SSE lifecycle for Web streams.

[INPUT]
- app.services.chat.stale_compact_gate::run_pre_reply_stale_compact_gate (POS: pre-reply idle gate)
- app.services.chat.compact_service::CompactResult (POS: compaction outcome)

[OUTPUT]
- run_pre_reply_compact_with_sse: active → compact → completed/failure SSE envelopes
- append_pre_reply_compact_sse: emit SSE from an existing CompactResult

[POS]
Web-only SSE wiring for idle pre-reply compaction. Reuses frontend context_compaction progress steps.
"""

from __future__ import annotations

import logging
from typing import Protocol

from app.services.chat.compact_service import CompactResult

logger = logging.getLogger(__name__)


class _StreamBuffer(Protocol):
    async def append(self, sse_chunk: str) -> str: ...


def _resolve_failure_phase(reason: str | None) -> str:
    if not reason:
        return "failed"
    lowered = reason.lower()
    if "timeout" in lowered:
        return "timeout"
    if "circuit" in lowered:
        return "circuit_open"
    return "failed"


def build_context_compaction_sse_chunk(
    message_id: str,
    *,
    phase: str,
    result: CompactResult | None = None,
) -> str:
    from app.schemas.streaming import SSEEnvelope

    status = "active"
    if phase == "completed":
        status = "success"
    elif phase in ("timeout", "circuit_open", "failed"):
        status = "warning"

    payload: dict[str, object] = {
        "type": "status",
        "messageId": message_id,
        "step_key": "context_compaction",
        "status": status,
        "data": {"phase": phase},
    }
    if result is not None and result.compacted and result.tokens_saved > 0:
        payload["tokens_saved"] = result.tokens_saved
        payload["snapshot_path"] = result.backup_path

    return SSEEnvelope.from_any(payload).to_sse_chunk()


async def append_pre_reply_compact_sse(
    buffer: _StreamBuffer,
    message_id: str,
    result: CompactResult | None,
) -> None:
    """Append completed/failure compaction SSE when appropriate."""
    if result is None:
        return
    if result.compacted and result.tokens_saved > 0:
        await buffer.append(
            build_context_compaction_sse_chunk(
                message_id, phase="completed", result=result
            )
        )
        return
    if result.attempted:
        phase = _resolve_failure_phase(result.reason)
        await buffer.append(
            build_context_compaction_sse_chunk(message_id, phase=phase, result=result)
        )


async def run_pre_reply_compact_with_sse(
    buffer: _StreamBuffer,
    *,
    chat_id: str,
    message_id: str,
    agent_id: str | None,
    request_engine_params: dict[str, object] | None,
) -> CompactResult | None:
    """Run stale compact gate with Web SSE active/completed/failure lifecycle."""
    from app.services.chat.stale_compact_gate import run_pre_reply_stale_compact_gate

    async def on_before_compact() -> None:
        await buffer.append(
            build_context_compaction_sse_chunk(message_id, phase="active")
        )

    try:
        result = await run_pre_reply_stale_compact_gate(
            chat_id,
            agent_id=agent_id,
            request_engine_params=request_engine_params,
            on_before_compact=on_before_compact,
        )
    except Exception as exc:
        logger.warning(
            "Pre-reply stale compact gate failed for chat %s: %s",
            chat_id,
            exc,
        )
        failure = CompactResult(
            compacted=False,
            reason=f"gate_failed: {exc}",
            attempted=True,
        )
        await append_pre_reply_compact_sse(buffer, message_id, failure)
        return failure

    await append_pre_reply_compact_sse(buffer, message_id, result)
    return result
