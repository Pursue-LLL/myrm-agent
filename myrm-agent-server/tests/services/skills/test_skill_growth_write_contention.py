"""Skill-growth units that read a row and write it back must not lose the write to a writer that commits in between.

Under the deferred-read transaction policy another writer committing between a unit's read and its write aborts the unit
with SQLITE_BUSY_SNAPSHOT, which ``busy_timeout`` does not cover, and most callers here can only log that: a rolled-back
draft stays approved with nothing behind it, an approved skill is never bound to its agent, a fork leaves the agent bound
to the skill it was forked from, a growth record loses the time it was resolved, and an approved evolution fails to apply
because its version cannot be activated. The tests run the real transaction policy on a file database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EnvironmentFingerprint,
    EvolutionType,
    SkillLineage,
    SkillRecord,
)

from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage
from app.api.skills.drafts import _bind_skill_to_agent, _rollback_draft_status
from app.database.models import Agent, ApprovalRecord, Base
from app.services.approvals.registry import ApprovalRegistry
from app.services.skills.draft_notification import persist_skill_draft_record
from app.services.skills.evolution_review.disk_content import apply_content_update
from app.services.skills.evolution_review.persistence import persist_approval_payload
from app.services.skills.evolution_review.types import EVOLUTION_ACTION_TYPE, EvolutionApprovalPayload
from tests.support.policy_sqlite import PolicyDb, policy_database, run_while_another_writer_commits

_RESOLVED_AT = datetime(2031, 1, 1, tzinfo=UTC)
_SKILL_MD = "---\nname: demo-skill\ndescription: The skill after the evolution.\n---\n\n# Demo\n"


@pytest_asyncio.fixture
async def policy_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[PolicyDb]:
    async with policy_database(tmp_path / "growth.db", monkeypatch) as db:
        yield db


async def _seed(policy_db: PolicyDb, row: Agent | ApprovalRecord) -> None:
    async with policy_db.factory() as db:
        db.add(row)
        await db.commit()


async def _stored[Row: Base](policy_db: PolicyDb, model: type[Row], row_id: str) -> Row:
    async with policy_db.factory() as db:
        row = await db.get(model, row_id)
    assert row is not None
    return row


@pytest.mark.asyncio
async def test_evolution_settlement_keeps_its_write_when_another_writer_commits_first(policy_db: PolicyDb) -> None:
    await _seed(
        policy_db,
        ApprovalRecord(id="evolution-1", agent_id="agent-1", action_type=EVOLUTION_ACTION_TYPE, status="PENDING", payload={}),
    )

    await run_while_another_writer_commits(
        policy_db, lambda: persist_approval_payload("evolution-1", approval_status="APPROVED", resolved_at=_RESOLVED_AT)
    )

    settled = await _stored(policy_db, ApprovalRecord, "evolution-1")
    assert settled.status == "APPROVED"
    assert settled.resolved_at is not None


@pytest.mark.asyncio
async def test_draft_rollback_keeps_its_write_when_another_writer_commits_first(policy_db: PolicyDb) -> None:
    await _seed(
        policy_db,
        ApprovalRecord(
            id="draft-1",
            agent_id="agent-1",
            action_type="skill_draft",
            status="APPROVED",
            payload={"growth_status": "APPROVED"},
            resolved_at=_RESOLVED_AT,
        ),
    )

    await run_while_another_writer_commits(policy_db, lambda: _rollback_draft_status("draft-1"))

    draft = await _stored(policy_db, ApprovalRecord, "draft-1")
    assert (draft.status, draft.payload["growth_status"], draft.resolved_at) == ("PENDING", "PENDING_REVIEW", None)


@pytest.mark.asyncio
async def test_skill_binding_keeps_its_write_when_another_writer_commits_first(policy_db: PolicyDb) -> None:
    await _seed(policy_db, Agent(id="agent-1", name="Agent", skill_ids=["existing-skill"], model_config={}))

    await run_while_another_writer_commits(policy_db, lambda: _bind_skill_to_agent("new-skill", "agent-1"))

    assert (await _stored(policy_db, Agent, "agent-1")).skill_ids == ["existing-skill", "new-skill"]


@pytest.mark.asyncio
async def test_growth_record_keeps_its_resolution_time_when_another_writer_commits_first(
    policy_db: PolicyDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = ApprovalRecord(id="growth-1", agent_id="agent-1", action_type="skill_draft", status="APPROVED", payload={})
    await _seed(policy_db, created)
    # The record's own creating write would be the unit's first transaction; this test is about the stamp that follows it.
    monkeypatch.setattr(ApprovalRegistry, "create_approval", AsyncMock(return_value=created))

    await run_while_another_writer_commits(
        policy_db,
        lambda: persist_skill_draft_record(
            {"type": "skill_draft", "skill_name": "growth-skill", "verification_proof": {}},
            status="AUTO_APPLIED",
            reviewed_at=_RESOLVED_AT,
        ),
    )

    assert (await _stored(policy_db, ApprovalRecord, "growth-1")).resolved_at is not None


@pytest.mark.asyncio
async def test_fork_rebinding_keeps_its_write_when_another_writer_commits_first(policy_db: PolicyDb, tmp_path: Path) -> None:
    skill_file = tmp_path / "demo-skill" / "SKILL.md"
    skill_file.parent.mkdir()
    skill_file.write_text(_SKILL_MD, encoding="utf-8")
    await _seed(policy_db, Agent(id="forking-agent", name="Agent", skill_ids=["skill-1"], model_config={}))
    payload = EvolutionApprovalPayload(
        skill_id="skill-1",
        skill_name="demo-skill",
        skill_path=str(skill_file),
        evolution_type="fix",
        reason="fork",
        original_content=_SKILL_MD,
        evolved_content=_SKILL_MD,
        confidence=0.9,
    )
    # The skill belongs to another agent, so applying for the forking agent forks it.
    store = MagicMock()
    store.get_skill.return_value = SkillRecord(
        skill_id="skill-1",
        name="demo-skill",
        description="Owned by another agent",
        content=_SKILL_MD,
        path="",
        lineage=SkillLineage(evolution_type=EvolutionType.FIX),
        environment=EnvironmentFingerprint(custom_tags={"scope_agent_id": "owner-agent"}),
    )
    store.save_skill = AsyncMock()

    with patch("app.services.skills.write_orchestrator.persist_skill_md_snapshot", new=AsyncMock()):
        await run_while_another_writer_commits(policy_db, lambda: apply_content_update(payload, store, agent_id="forking-agent"))

    # A fork gives the payload a new id; without one the binding assertion below holds with no write at all.
    assert payload.skill_id != "skill-1"
    assert (await _stored(policy_db, Agent, "forking-agent")).skill_ids == [payload.skill_id]


@pytest.mark.asyncio
async def test_version_activation_keeps_its_write_when_another_writer_commits_first(policy_db: PolicyDb) -> None:
    storage = SQLAlchemyStorage(session_factory=policy_db.factory)
    await storage.save_skill_version("skill-1", 1, "first", created_by="test")
    await storage.save_skill_version("skill-1", 2, "second", created_by="test")
    await storage.activate_version("skill-1", 1)

    await run_while_another_writer_commits(policy_db, lambda: storage.activate_version("skill-1", 2))

    active = await storage.get_active_version("skill-1")
    assert active is not None
    assert active.version == 2
