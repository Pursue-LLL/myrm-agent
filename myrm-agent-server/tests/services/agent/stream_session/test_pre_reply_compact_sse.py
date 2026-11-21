"""How a pre-reply compaction reads in the Web progress step.

The step opens as "compressing" and must always close on a phase that tells the truth: a compaction that did nothing
harmful is calm, only one that broke is a warning, and nothing is shown when the gate never started one.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.stream_session.pre_reply_compact_sse import run_pre_reply_compact_with_sse
from app.services.chat.compact_service import CompactReason, CompactResult

_GATE = "app.services.chat.stale_compact_gate.run_pre_reply_stale_compact_gate"

# What each way a compaction can decline reads as: (phase, status). Spelled out here, not derived from the module under
# test, so that a reason added without a decision about how it reads fails below.
_READS_AS: dict[CompactReason, tuple[str, str]] = {
    CompactReason.CONCURRENT_COMPACTION: ("skipped", "success"),
    CompactReason.NO_COMPACTABLE_MESSAGES: ("skipped", "success"),
    CompactReason.TOO_FEW_MESSAGES: ("skipped", "success"),
    CompactReason.ANTI_THRASH_ACTIVE: ("skipped", "success"),
    CompactReason.SUMMARIZE_CIRCUIT_OPEN: ("circuit_open", "warning"),
    CompactReason.TIMEOUT: ("timeout", "warning"),
    CompactReason.CHAT_NOT_FOUND: ("failed", "warning"),
    CompactReason.PERSIST_FAILED: ("failed", "warning"),
}


async def _run(gate_result: CompactResult, *, announces_active: bool = True) -> AsyncMock:
    """Run the SSE lifecycle against a gate that returns ``gate_result``; returns the buffer it wrote to."""
    buffer = AsyncMock()

    async def _gate(*_args: object, **kwargs: object) -> CompactResult:
        on_active = kwargs.get("on_before_compact")
        if announces_active and on_active is not None:
            await on_active()
        return gate_result

    with patch(_GATE, AsyncMock(side_effect=_gate)):
        await run_pre_reply_compact_with_sse(
            buffer,
            chat_id="chat-1",
            message_id="msg-1",
            agent_id="agent-1",
            request_engine_params={"idle_compact_after_seconds": 1800},
        )
    return buffer


def _events(buffer: AsyncMock) -> list[dict[str, object]]:
    return [json.loads(call.args[0].removeprefix("data: ")) for call in buffer.append.await_args_list]


def _phases(buffer: AsyncMock) -> list[tuple[str, str]]:
    """The (phase, status) of every compaction event the buffer received, in order."""
    return [(event["data"]["phase"], event["status"]) for event in _events(buffer)]


def test_every_decline_reason_has_a_decision_about_how_it_reads() -> None:
    assert set(_READS_AS) == set(CompactReason)


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", list(CompactReason), ids=lambda reason: reason.value)
async def test_a_declined_compaction_closes_the_step_on_the_phase_its_reason_reads_as(reason: CompactReason) -> None:
    buffer = await _run(CompactResult(compacted=False, reason=reason, attempted=True))

    assert _phases(buffer) == [("active", "active"), _READS_AS[reason]]


@pytest.mark.asyncio
async def test_a_compaction_that_saved_tokens_completes_the_step_with_the_savings() -> None:
    buffer = await _run(CompactResult(compacted=True, tokens_saved=900, backup_path="/tmp/backup.jsonl", attempted=True))

    assert _phases(buffer) == [("active", "active"), ("completed", "success")]
    completed = _events(buffer)[1]
    assert completed["tokens_saved"] == 900
    assert completed["snapshot_path"] == "/tmp/backup.jsonl"


@pytest.mark.asyncio
async def test_a_compaction_that_saved_nothing_is_not_reported_as_a_failure() -> None:
    buffer = await _run(CompactResult(compacted=True, tokens_saved=0, backup_path="/tmp/backup.jsonl", attempted=True))

    assert _phases(buffer) == [("active", "active"), ("ineffective", "success")]
    ineffective = _events(buffer)[1]
    assert "tokens_saved" not in ineffective
    assert "snapshot_path" not in ineffective


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["a-reason-nobody-classified", None], ids=["unknown-reason", "no-reason"])
async def test_a_decline_nobody_classified_reads_as_a_failure(reason: str | None) -> None:
    buffer = await _run(CompactResult(compacted=False, reason=reason, attempted=True))

    assert _phases(buffer) == [("active", "active"), ("failed", "warning")]


@pytest.mark.asyncio
async def test_a_gate_that_raises_closes_the_step_as_a_failure() -> None:
    buffer = AsyncMock()

    with patch(_GATE, AsyncMock(side_effect=RuntimeError("db unavailable"))):
        await run_pre_reply_compact_with_sse(
            buffer,
            chat_id="chat-1",
            message_id="msg-1",
            agent_id="agent-1",
            request_engine_params={"idle_compact_after_seconds": 1800},
        )

    assert _phases(buffer) == [("failed", "warning")]


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["idle_compact_disabled", "context_below_floor (900 <= 12800)"])
async def test_a_gate_that_never_started_a_compaction_shows_nothing(reason: str) -> None:
    buffer = await _run(CompactResult(compacted=False, reason=reason), announces_active=False)

    buffer.append.assert_not_called()


@pytest.mark.asyncio
async def test_every_event_belongs_to_the_context_compaction_step_of_its_message() -> None:
    buffer = await _run(CompactResult(compacted=False, reason=CompactReason.TIMEOUT, attempted=True))

    assert [(event["type"], event["step_key"], event["messageId"]) for event in _events(buffer)] == [
        ("status", "context_compaction", "msg-1"),
        ("status", "context_compaction", "msg-1"),
    ]
