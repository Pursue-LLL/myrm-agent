from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from myrm_agent_harness.runtime.events import SkillFailureCandidate, SkillFailureEvent
from pytest import MonkeyPatch
from sqlalchemy import delete, select

from app.database.connection import get_session
from app.database.models import ApprovalRecord, Base, ExperienceLedgerEvent
from app.platform_utils import get_database_engine
from app.services.agent.evolution import skill_immune_service
from app.services.agent.evolution.skill_immune_service import handle_skill_failure_event
from app.services.skills.evolution_reviews import (
    EvolutionApplyError,
    EvolutionGrowthStatus,
    RuntimeFailureEvidence,
    approve_evolution_review_record,
    bump_runtime_failure_review_record,
    create_evolution_review_record,
    find_runtime_failure_review_record,
)

TEST_SKILL_PREFIX = "skill-immune-test-"


@pytest.fixture
async def created_record_ids() -> AsyncIterator[list[str]]:
    engine = get_database_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    record_ids: list[str] = []
    yield record_ids
    skill_immune_service._failure_locks.clear()
    async with get_session() as db:
        if record_ids:
            await db.execute(delete(ExperienceLedgerEvent).where(ExperienceLedgerEvent.entity_id.in_(record_ids)))
            await db.execute(delete(ApprovalRecord).where(ApprovalRecord.id.in_(record_ids)))
            await db.commit()


def _runtime_evidence(error_signature: str) -> RuntimeFailureEvidence:
    now = datetime.now(UTC).isoformat()
    return RuntimeFailureEvidence(
        tool_name="browser_interact_tool",
        error_signature=error_signature,
        tool_args_hash="abc123",
        skill_version="4",
        attribution_confidence=1.0,
        first_seen_at=now,
        last_seen_at=now,
        candidate_skill_names=["checkout_skill"],
    )


@pytest.mark.asyncio
async def test_runtime_failure_review_record_is_deduped_and_bumped(
    created_record_ids: list[str],
) -> None:
    skill_id = f"{TEST_SKILL_PREFIX}dedupe-{uuid4().hex}"
    error_signature = f"browser_interact:button missing:{uuid4().hex}"
    evidence = _runtime_evidence(error_signature)
    created = await create_evolution_review_record(
        agent_id="default",
        chat_id=None,
        proposal_skill_id=skill_id,
        skill_name="checkout_skill",
        skill_path="/skills/checkout/SKILL.md",
        evolution_type="fix",
        reason="Runtime skill failure detected",
        original_content="step one",
        evolved_content="step two",
        confidence=0.71,
        test_passed=True,
        task_context="runtime regression",
        runtime_failure=evidence,
    )
    created_record_ids.append(created.id)

    found = await find_runtime_failure_review_record(
        skill_id=skill_id,
        error_signature=evidence.error_signature,
        skill_version=evidence.skill_version,
    )
    assert found is not None
    assert found.id == created.id
    assert found.runtime_failure is not None
    assert found.runtime_failure.failure_count == 1

    bumped = await bump_runtime_failure_review_record(
        evolution_id=created.id,
        last_seen_at="2026-05-07T00:00:00+00:00",
    )
    assert bumped is not None
    assert bumped.runtime_failure is not None
    assert bumped.runtime_failure.failure_count == 2
    assert bumped.runtime_failure.last_seen_at == "2026-05-07T00:00:00+00:00"


@pytest.mark.asyncio
async def test_skill_failure_event_without_evolution_engine_creates_one_blocked_case(
    monkeypatch: MonkeyPatch,
    created_record_ids: list[str],
) -> None:
    skill_id = f"{TEST_SKILL_PREFIX}runtime-{uuid4().hex}"
    error_signature = f"browser_interact:button missing:{uuid4().hex}"
    monkeypatch.setattr(
        skill_immune_service,
        "get_global_evolution_integration",
        lambda: None,
    )
    event = SkillFailureEvent(
        tool_name="browser_interact_tool",
        tool_call_id="call-1",
        tool_args_hash="args-hash",
        error_message="Timeout: button missing",
        error_signature=error_signature,
        candidates=(
            SkillFailureCandidate(
                skill_id=skill_id,
                skill_name="checkout_skill",
                confidence=1.0,
                version="4",
                storage_path="/skills/checkout/SKILL.md",
            ),
        ),
        task_intent="complete checkout",
    )

    await handle_skill_failure_event(event)
    await handle_skill_failure_event(event)

    async with get_session() as db:
        rows = await db.execute(select(ApprovalRecord).where(ApprovalRecord.action_type == "evolution"))
        records = [
            item for item in rows.scalars().all() if isinstance(item.payload, dict) and item.payload.get("skill_id") == skill_id
        ]

    assert len(records) == 1
    created_record_ids.append(records[0].id)
    payload = records[0].payload
    assert isinstance(payload, dict)
    assert records[0].status == "REJECTED"
    assert payload["growth_status"] == EvolutionGrowthStatus.FAILED_SCAN.value
    assert payload["reason_code"] == "runtime:no_evolution_engine"
    assert payload["runtime_failure"]["failure_count"] == 2

    with pytest.raises(EvolutionApplyError, match="Blocked evolution cannot be approved"):
        await approve_evolution_review_record(records[0].id)
