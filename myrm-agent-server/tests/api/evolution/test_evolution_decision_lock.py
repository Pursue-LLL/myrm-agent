"""Decisions on one evolution proposal run one at a time: a rejection cannot land inside an apply in flight."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import pytest
from sqlalchemy import select

from app.database.connection import get_session
from app.database.models import ApprovalRecord, ExperienceLedgerEvent
from app.services.skills.evolution_review import disk as review_disk
from app.services.skills.evolution_review.decision_lock import serialized_per_evolution
from app.services.skills.evolution_review.types import EvolutionApprovalPayload
from app.services.skills.evolution_reviews import (
    EvolutionApplyError,
    EvolutionReviewRecord,
    approve_evolution_review_record,
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


async def _create_record(tmp_path: Path) -> EvolutionReviewRecord:
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


@serialized_per_evolution
async def _hold_decision(evolution_id: str, release: asyncio.Event) -> None:
    await release.wait()


_DECISIONS: dict[str, Callable[[str], Awaitable[object]]] = {
    "approve": approve_evolution_review_record,
    "reject": reject_evolution_review_record,
    "revise": lambda evolution_id: revise_evolution_review_record(evolution_id, evolved_content=_EVOLVED_SKILL_MD),
    "rollback": rollback_evolution_review_record,
}


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", sorted(_DECISIONS))
async def test_every_decision_waits_for_the_one_in_flight_on_its_proposal(decision: str) -> None:
    release = asyncio.Event()
    holding = asyncio.create_task(_hold_decision("evolution-held", release))
    waiting: asyncio.Task[object] | None = None
    other: asyncio.Task[object] | None = None
    try:
        await asyncio.sleep(0)
        waiting = asyncio.create_task(_DECISIONS[decision]("evolution-held"))
        other = asyncio.create_task(_DECISIONS[decision]("evolution-other"))

        done, _ = await asyncio.wait({waiting, other}, timeout=_WAIT_FOR_BLOCKED_SECONDS)
        assert other in done, "a decision on another proposal must not wait"
        assert waiting not in done, f"{decision} must wait for the decision in flight on the same proposal"
    finally:
        release.set()
        await _settle(*(task for task in (holding, waiting, other) if task is not None))
