from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.skills.evolution.core.engine import SkillEvolutionEngine
from myrm_agent_harness.agent.skills.evolution.core.types import SkillRecord
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
    assert payload["test_passed"] is None
    assert payload["runtime_failure"]["failure_count"] == 2

    with pytest.raises(EvolutionApplyError, match="Blocked evolution cannot be approved"):
        await approve_evolution_review_record(records[0].id)


def _failure_event(skill_id: str, *, session_key: str | None) -> SkillFailureEvent:
    return SkillFailureEvent(
        tool_name="bash",
        tool_call_id="call-1",
        error_message="deploy failed: step two exploded",
        error_signature=f"bash:deploy failed:{uuid4().hex}",
        candidates=(
            SkillFailureCandidate(
                skill_id=skill_id,
                skill_name="deploy_skill",
                confidence=1.0,
                version="2",
                storage_path="/skills/deploy/SKILL.md",
            ),
        ),
        session_id=session_key,
    )


async def _blocked_case_ids(skill_id: str) -> list[str]:
    async with get_session() as db:
        rows = await db.execute(select(ApprovalRecord).where(ApprovalRecord.action_type == "evolution"))
        return [
            item.id
            for item in rows.scalars().all()
            if isinstance(item.payload, dict) and item.payload.get("skill_id") == skill_id
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("session_key", "log_session_id"),
    [
        ("chat_c-1a2b", "c-1a2b"),
        ("chat_chat_x", "chat_x"),
        ("kanban:task-7", "kanban:task-7"),
        (None, None),
        ("", None),
        ("chat_../secrets", None),
        ("chat_a/b", None),
    ],
)
async def test_a_runtime_repair_reads_the_event_log_named_by_the_chat_of_the_failure(
    monkeypatch: MonkeyPatch,
    created_record_ids: list[str],
    session_key: str | None,
    log_session_id: str | None,
) -> None:
    fix_skill = AsyncMock(return_value=None)
    evolution = SimpleNamespace(
        engine=SimpleNamespace(fix_skill=fix_skill),
        store=SimpleNamespace(get_skill=lambda _skill_id: None),
        screener=None,
    )
    monkeypatch.setattr(skill_immune_service, "get_global_evolution_integration", lambda: evolution)
    skill_id = f"{TEST_SKILL_PREFIX}log-{uuid4().hex}"

    await handle_skill_failure_event(_failure_event(skill_id, session_key=session_key))
    created_record_ids.extend(await _blocked_case_ids(skill_id))

    assert fix_skill.await_args is not None
    assert fix_skill.await_args.kwargs["session_id"] == log_session_id


def _write_log_stored_before_redaction(log_dir: Path, chat_id: str, *, credential: str) -> None:
    """A chat's event log as an older version wrote it: the credential of the failed call is in the clear."""
    sid = f"chat_{chat_id}"
    records = [
        {"seq": 1, "ts": 1000.0, "type": "session_start", "sid": sid, "data": {}},
        {"seq": 2, "ts": 1001.0, "type": "tool_start", "sid": sid, "data": {"tool_name": "bash", "tool_call_id": "call-1"}},
        {
            "seq": 3,
            "ts": 1002.0,
            "type": "tool_failure",
            "sid": sid,
            "data": {"tool_name": "bash", "tool_call_id": "call-1", "error": f"deploy failed: 401 for key {credential}"},
        },
    ]
    (log_dir / f"{chat_id}.jsonl").write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


async def _repair_prompt_trajectory(
    monkeypatch: MonkeyPatch,
    created_record_ids: list[str],
    log_dir: Path,
    *,
    failing_chat_id: str,
) -> str:
    """Run a real runtime repair over a real engine and return the trajectory its variant prompt was built from."""
    skill_id = f"{TEST_SKILL_PREFIX}repair-{uuid4().hex}"
    skill = SkillRecord(
        skill_id=skill_id,
        name="deploy_skill",
        description="Deploys the service",
        content="step one",
        path="/skills/deploy/SKILL.md",
        lineage=None,
    )
    store = MagicMock()
    store.get_skill.return_value = skill
    store.get_evolution_constraints.return_value = []
    engine = SkillEvolutionEngine(
        store=store,
        llm=MagicMock(),
        event_log_backend=FileEventLogBackend(log_dir=log_dir, session_id="default"),
    )
    trajectories: list[str] = []

    async def no_variants(**kwargs: str) -> list[str]:
        trajectories.append(kwargs["trajectory"])
        return []

    monkeypatch.setattr(engine._variant_generator, "generate_variants", no_variants)
    evolution = SimpleNamespace(engine=engine, store=store, screener=None)
    monkeypatch.setattr(skill_immune_service, "get_global_evolution_integration", lambda: evolution)

    await handle_skill_failure_event(_failure_event(skill_id, session_key=f"chat_{failing_chat_id}"))
    created_record_ids.extend(await _blocked_case_ids(skill_id))

    (trajectory,) = trajectories
    return trajectory


@pytest.mark.asyncio
async def test_the_repair_prompt_holds_the_failed_run_of_the_chat_and_no_credential_an_older_log_stored(
    monkeypatch: MonkeyPatch,
    created_record_ids: list[str],
    tmp_path: Path,
) -> None:
    chat_id = f"c-{uuid4().hex}"
    credential = "Zq8Xv2Lm9Tp4Rk7Ws1Yb5Nc3Hd6Jf0GaQw"
    _write_log_stored_before_redaction(tmp_path, chat_id, credential=credential)

    trajectory = await _repair_prompt_trajectory(monkeypatch, created_record_ids, tmp_path, failing_chat_id=chat_id)

    assert "- **bash**: 1 calls, success rate 0.0%, 1 failures" in trajectory
    assert "deploy failed: 401 for key" in trajectory
    assert credential not in trajectory
    assert "step one" not in trajectory  # the generator and the judge receive the skill on its own
    assert len(trajectory) <= 1500 * 4


@pytest.mark.asyncio
async def test_a_failure_whose_chat_left_no_log_keeps_the_error_text_as_the_repair_prompt_trajectory(
    monkeypatch: MonkeyPatch,
    created_record_ids: list[str],
    tmp_path: Path,
) -> None:
    trajectory = await _repair_prompt_trajectory(monkeypatch, created_record_ids, tmp_path, failing_chat_id=f"c-{uuid4().hex}")

    assert trajectory.startswith("Trajectory extraction not available. Error: ")
    assert "deploy failed: step two exploded" in trajectory
