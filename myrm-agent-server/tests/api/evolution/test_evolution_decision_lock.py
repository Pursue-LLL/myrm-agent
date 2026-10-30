"""Writes to one evolution proposal run one at a time: a rejection or a count bump cannot land inside an apply in flight."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Coroutine
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from app.database.connection import get_session
from app.database.models import ApprovalRecord, ExperienceLedgerEvent
from app.services.skills.evolution_review import disk as review_disk
from app.services.skills.evolution_review import queries as review_queries
from app.services.skills.evolution_review.decision_lock import serialized_per_evolution
from app.services.skills.evolution_review.persistence import persist_approval_payload
from app.services.skills.evolution_review.types import EvolutionApprovalPayload
from app.services.skills.evolution_reviews import (
    EvolutionApplyError,
    EvolutionReviewRecord,
    RuntimeFailureEvidence,
    approve_evolution_review_record,
    bump_runtime_failure_review_record,
    create_evolution_review_record,
    reject_evolution_review_record,
    revise_evolution_review_record,
    rollback_evolution_review_record,
)
from app.services.skills.experience_ledger import ExperienceEventType

_EVOLVED_SKILL_MD = "---\nname: locked-skill\ndescription: Fixes the skill.\n---\n\n# Locked skill\n"
_WAIT_FOR_ENTRY_SECONDS = 5
_WAIT_FOR_BLOCKED_SECONDS = 0.3

_real_apply = review_disk.apply_to_disk_and_store


class _ApplyGate:
    """Holds the apply open so a test can act while a decision is in flight."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.running = 0
        self.peak = 0

    async def __call__(self, payload: EvolutionApprovalPayload, agent_id: str | None = None) -> None:
        self.running += 1
        self.peak = max(self.peak, self.running)
        self.entered.set()
        try:
            await self.release.wait()
            await _real_apply(payload, agent_id)
        finally:
            self.running -= 1


@pytest.fixture
async def apply_gate(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_ApplyGate]:
    gate = _ApplyGate()
    monkeypatch.setattr(review_disk, "apply_to_disk_and_store", gate)
    yield gate
    gate.release.set()


async def _create_record(tmp_path: Path, runtime_failure: RuntimeFailureEvidence | None = None) -> EvolutionReviewRecord:
    return await create_evolution_review_record(
        agent_id="test-agent",
        chat_id=None,
        proposal_skill_id="locked_skill_123",
        skill_name="locked-skill",
        skill_path=str(tmp_path / "locked-skill" / "SKILL.md"),
        evolution_type="fix",
        reason="Two decisions arrive for one proposal",
        original_content="# Locked skill\n",
        evolved_content=_EVOLVED_SKILL_MD,
        confidence=0.9,
        test_passed=True,
        task_context="decision lock regression",
        runtime_failure=runtime_failure,
    )


async def _settle(*tasks: asyncio.Task[object]) -> None:
    await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_a_rejection_waits_for_the_apply_in_flight_and_then_finds_it_applied(
    apply_gate: _ApplyGate, tmp_path: Path
) -> None:
    record = await _create_record(tmp_path)
    approving = asyncio.create_task(approve_evolution_review_record(record.id))
    rejecting: asyncio.Task[object] | None = None
    try:
        await asyncio.wait_for(apply_gate.entered.wait(), _WAIT_FOR_ENTRY_SECONDS)

        rejecting = asyncio.create_task(reject_evolution_review_record(record.id))
        decided, _ = await asyncio.wait({rejecting}, timeout=_WAIT_FOR_BLOCKED_SECONDS)
        assert not decided, "a rejection must wait for the apply that is in flight"

        apply_gate.release.set()
        await approving
        with pytest.raises(EvolutionApplyError, match="not been applied"):
            await rejecting
    finally:
        apply_gate.release.set()
        await _settle(*(task for task in (approving, rejecting) if task is not None))

    async with get_session() as db:
        approval_record = await db.get(ApprovalRecord, record.id)
        rejected_events = (
            (
                await db.execute(
                    select(ExperienceLedgerEvent).where(
                        ExperienceLedgerEvent.entity_id == record.id,
                        ExperienceLedgerEvent.event_type == ExperienceEventType.EVOLUTION_REJECTED.value,
                    )
                )
            )
            .scalars()
            .all()
        )
    assert approval_record is not None
    assert approval_record.status == "APPROVED"
    assert isinstance(approval_record.payload, dict)
    assert approval_record.payload["apply_status"] == "APPLIED"
    assert rejected_events == []


@pytest.mark.asyncio
async def test_two_decisions_on_one_record_never_apply_at_once(apply_gate: _ApplyGate, tmp_path: Path) -> None:
    record = await _create_record(tmp_path)
    first = asyncio.create_task(approve_evolution_review_record(record.id))
    second: asyncio.Task[object] | None = None
    try:
        await asyncio.wait_for(apply_gate.entered.wait(), _WAIT_FOR_ENTRY_SECONDS)

        second = asyncio.create_task(approve_evolution_review_record(record.id))
        await asyncio.wait({second}, timeout=_WAIT_FOR_BLOCKED_SECONDS)

        apply_gate.release.set()
        await asyncio.gather(first, second)
    finally:
        apply_gate.release.set()
        await _settle(*(task for task in (first, second) if task is not None))

    assert apply_gate.peak == 1


def _runtime_failure() -> RuntimeFailureEvidence:
    now = datetime.now(UTC).isoformat()
    return RuntimeFailureEvidence(
        tool_name="browser_interact_tool",
        error_signature="button missing",
        attribution_confidence=1.0,
        first_seen_at=now,
        last_seen_at=now,
    )


@pytest.mark.asyncio
async def test_a_failure_count_bump_waits_for_an_apply_and_does_not_overwrite_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    record = await _create_record(tmp_path, _runtime_failure())
    persisting, release = asyncio.Event(), asyncio.Event()

    async def paused_persist(evolution_id: str, *, payload: EvolutionApprovalPayload | None = None) -> ApprovalRecord:
        persisting.set()
        await release.wait()
        return await persist_approval_payload(evolution_id, payload=payload)

    monkeypatch.setattr(review_queries, "persist_approval_payload", paused_persist)
    bumping = asyncio.create_task(bump_runtime_failure_review_record(record.id, last_seen_at=datetime.now(UTC).isoformat()))
    approving: asyncio.Task[object] | None = None
    try:
        await asyncio.wait_for(persisting.wait(), _WAIT_FOR_ENTRY_SECONDS)

        approving = asyncio.create_task(approve_evolution_review_record(record.id))
        decided, _ = await asyncio.wait({approving}, timeout=_WAIT_FOR_BLOCKED_SECONDS)
        assert not decided, "an apply must wait for the count bump whose write is open"

        release.set()
        await asyncio.gather(bumping, approving)
    finally:
        release.set()
        await _settle(*(task for task in (bumping, approving) if task is not None))

    async with get_session() as db:
        approval_record = await db.get(ApprovalRecord, record.id)
    assert approval_record is not None
    assert approval_record.status == "APPROVED"
    assert isinstance(approval_record.payload, dict)
    assert approval_record.payload["apply_status"] == "APPLIED"
    runtime_failure = approval_record.payload["runtime_failure"]
    assert isinstance(runtime_failure, dict)
    assert runtime_failure["failure_count"] == 2
    await rollback_evolution_review_record(record.id)


@serialized_per_evolution
async def _hold_decision(evolution_id: str, release: asyncio.Event) -> None:
    await release.wait()


_PAYLOAD_WRITERS: dict[str, Callable[[str], Coroutine[None, None, object]]] = {
    "approve": approve_evolution_review_record,
    "reject": reject_evolution_review_record,
    "revise": lambda evolution_id: revise_evolution_review_record(evolution_id, evolved_content=_EVOLVED_SKILL_MD),
    "rollback": rollback_evolution_review_record,
    "bump": lambda evolution_id: bump_runtime_failure_review_record(evolution_id, last_seen_at="2026-05-07T00:00:00+00:00"),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("writer", sorted(_PAYLOAD_WRITERS))
async def test_every_payload_writer_waits_for_the_one_in_flight_on_its_proposal(writer: str) -> None:
    release = asyncio.Event()
    holding = asyncio.create_task(_hold_decision("evolution-held", release))
    waiting: asyncio.Task[object] | None = None
    other: asyncio.Task[object] | None = None
    try:
        await asyncio.sleep(0)
        waiting = asyncio.create_task(_PAYLOAD_WRITERS[writer]("evolution-held"))
        other = asyncio.create_task(_PAYLOAD_WRITERS[writer]("evolution-other"))

        done, _ = await asyncio.wait({waiting, other}, timeout=_WAIT_FOR_BLOCKED_SECONDS)
        assert other in done, "a write on another proposal must not wait"
        assert waiting not in done, f"{writer} must wait for the write in flight on the same proposal"
    finally:
        release.set()
        await _settle(*(task for task in (holding, waiting, other) if task is not None))
