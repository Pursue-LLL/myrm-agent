"""Pre-reply idle compact SSE lifecycle for Web streams.

[INPUT]
- app.services.chat.stale_compact_gate::run_pre_reply_stale_compact_gate (POS: pre-reply idle gate)
- app.services.chat.compact_service::CompactReason, CompactResult (POS: closed decline reasons and compaction outcome)

[OUTPUT]
- run_pre_reply_compact_with_sse: active → compact → one closing phase (completed / ineffective / skipped / timeout / circuit_open / failed) as context_compaction progress-step SSE

[POS]
Web-only SSE wiring for idle pre-reply compaction. Reuses frontend context_compaction progress steps, which word each phase under ``progressSteps.context_compaction_<phase>`` in the frontend locales.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Literal, Protocol

from app.services.chat.compact_service import CompactReason, CompactResult

logger = logging.getLogger(__name__)

CompactionPhase = Literal["active", "completed", "ineffective", "skipped", "timeout", "circuit_open", "failed"]

# Only a compaction that broke is a warning; one that left the context as it was is calm.
_STATUS_BY_PHASE: Mapping[CompactionPhase, str] = {
    "active": "active",
    "completed": "success",
    "ineffective": "success",
    "skipped": "success",
    "timeout": "warning",
    "circuit_open": "warning",
    "failed": "warning",
}

# Only reasons known to be no failure are worded as such; every other reason, and any added later, reads as a failure.
_PHASE_BY_REASON: Mapping[str, CompactionPhase] = {
    CompactReason.CONCURRENT_COMPACTION: "skipped",
    CompactReason.NO_COMPACTABLE_MESSAGES: "skipped",
    CompactReason.TOO_FEW_MESSAGES: "skipped",
    CompactReason.ANTI_THRASH_ACTIVE: "skipped",
    CompactReason.SUMMARIZE_CIRCUIT_OPEN: "circuit_open",
    CompactReason.TIMEOUT: "timeout",
}


class _StreamBuffer(Protocol):
    async def append(self, sse_chunk: str) -> str: ...


def _closing_phase(result: CompactResult) -> CompactionPhase | None:
    """The phase a gate outcome closes the step on, or None when the gate never started a compaction."""
    if result.compacted:
        return "completed" if result.tokens_saved > 0 else "ineffective"
    if not result.attempted:
        return None
    return _PHASE_BY_REASON.get(result.reason or "", "failed")


def _chunk(message_id: str, phase: CompactionPhase, result: CompactResult | None = None) -> str:
    """The progress-step event of ``phase``; a completed phase carries what the compaction saved."""
    from app.schemas.streaming import SSEEnvelope

    payload: dict[str, object] = {
        "type": "status",
        "messageId": message_id,
        "step_key": "context_compaction",
        "status": _STATUS_BY_PHASE[phase],
        "data": {"phase": phase},
    }
    if phase == "completed" and result is not None:
        payload["tokens_saved"] = result.tokens_saved
        payload["snapshot_path"] = result.backup_path

    return SSEEnvelope.from_any(payload).to_sse_chunk()


async def run_pre_reply_compact_with_sse(
    buffer: _StreamBuffer,
    *,
    chat_id: str,
    message_id: str,
    agent_id: str | None,
    request_engine_params: dict[str, object] | None,
) -> None:
    """Run the stale compact gate and report it on the Web stream: active before it compacts, one closing phase after."""
    from app.services.chat.stale_compact_gate import run_pre_reply_stale_compact_gate

    async def on_before_compact() -> None:
        await buffer.append(_chunk(message_id, "active"))

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
        await buffer.append(_chunk(message_id, "failed"))
        return

    phase = _closing_phase(result)
    if phase is not None:
        await buffer.append(_chunk(message_id, phase, result))
