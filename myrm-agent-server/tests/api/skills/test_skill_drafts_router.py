"""Regression tests for skill drafts backed by ApprovalRecord."""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.api.skills.drafts import (
    ApproveDraftRequest,
    approve_skill_draft,
    get_skill_draft,
    get_unreviewed_draft_count,
    list_skill_drafts,
    reject_skill_draft,
)
from app.database.connection import get_session
from app.database.models import ApprovalRecord, ExperienceLedgerEvent
from app.services.skills.draft_notification import notify_skill_draft_created


@pytest.fixture(autouse=True)
async def cleanup_rows() -> None:
    from app.database.connection import get_session

    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()
    yield
    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.fixture
def mock_local_skills_dir(tmp_path: Path) -> Path:
    import app.api.skills.sync as sync_module
    import app.core.skills.models as models_module
    from app.core.skills.creation.service import skill_creation_service
    from app.core.skills.store.service import skills_service

    test_path = tmp_path / "skills"
    test_path.mkdir(parents=True, exist_ok=True)

    original_path = skill_creation_service.base_path
    original_default_paths = models_module.DEFAULT_LOCAL_SKILL_PATHS.copy()
    original_local_skills = skills_service._local_skills

    skill_creation_service.base_path = test_path
    sync_module.LOCAL_SKILLS_DIR = test_path
    models_module.DEFAULT_LOCAL_SKILL_PATHS.clear()
    models_module.DEFAULT_LOCAL_SKILL_PATHS.append(str(test_path))
    skills_service._local_skills = None

    yield test_path

    skill_creation_service.base_path = original_path
    sync_module.LOCAL_SKILLS_DIR = original_path
    models_module.DEFAULT_LOCAL_SKILL_PATHS.clear()
    models_module.DEFAULT_LOCAL_SKILL_PATHS.extend(original_default_paths)
    skills_service._local_skills = original_local_skills


@pytest.mark.asyncio
async def test_list_skill_drafts_reads_from_approval_records(
    mock_local_skills_dir: Path,
) -> None:
    user_id = f"router_drafts_{uuid4().hex}"
    skill_name = "router-patch-skill"
    skill_dir = mock_local_skills_dir / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: router-patch-skill\ndescription: Test\n---\n\n## Steps\n1. Do something\n",
        encoding="utf-8",
    )

    blocked_draft = await notify_skill_draft_created(
        {
            "has_value": True,
            "user_id": user_id,
            "type": "skill_draft",
            "skill_name": "blocked-growth",
            "content": "---\nname: blocked-growth\n---\n## Steps\nrm -rf /\n",
        }
    )
    pending_draft = await notify_skill_draft_created(
        {
            "has_value": True,
            "user_id": user_id,
            "type": "skill_patch",
            "skill_name": skill_name,
            "content": "<<<<<<< SEARCH\n1. Do something\n=======\n1. Do something better\n>>>>>>> REPLACE",
        }
    )

    drafts_response = await list_skill_drafts(status=None, limit=20, offset=0)
    details = await get_skill_draft(pending_draft.id)
    count = await get_unreviewed_draft_count()

    statuses = {draft.id: draft.status for draft in drafts_response.drafts}
    assert statuses[blocked_draft.id] == "FAILED_SCAN"
    assert statuses[pending_draft.id] == "PENDING_REVIEW"
    assert details.id == pending_draft.id
    assert details.status == "PENDING_REVIEW"
    assert count["unreviewed_count"] == 1

    async with get_session() as db:
        events = list(
            (
                await db.execute(
                    select(ExperienceLedgerEvent).where(ExperienceLedgerEvent.entity_id.in_([blocked_draft.id, pending_draft.id]))
                )
            )
            .scalars()
            .all()
        )
        for event in events:
            await db.delete(event)
        await db.delete(blocked_draft)
        await db.delete(pending_draft)
        await db.commit()


@pytest.mark.asyncio
async def test_approve_and_reject_skill_drafts_update_status_and_ledger(
    mock_local_skills_dir: Path,
) -> None:
    user_id = f"router_decision_{uuid4().hex}"
    approved_name = "manual-approved-skill"
    rejected_name = "manual-rejected-skill"

    approved_seed = await notify_skill_draft_created(
        {
            "has_value": True,
            "user_id": user_id,
            "type": "skill_draft",
            "skill_name": approved_name,
            "skill_description": "Manual approval flow",
            "trigger_condition": "When the user asks for the same manual workflow.",
            "skill_steps": "1. Inspect.\n2. Reuse.",
        }
    )
    rejected_seed = await notify_skill_draft_created(
        {
            "has_value": True,
            "user_id": user_id,
            "type": "skill_draft",
            "skill_name": rejected_name,
            "skill_description": "Reject this draft",
            "trigger_condition": "When the user asks to reject this.",
            "skill_steps": "1. Stop.",
        }
    )

    approve_result = await approve_skill_draft(
        approved_seed.id,
        ApproveDraftRequest(skill_name=approved_name),
    )
    reject_result = await reject_skill_draft(rejected_seed.id)

    assert approve_result["status"] == "APPROVED"
    assert approve_result["materialized"] is True
    assert reject_result["status"] == "REJECTED"

    skill_file = mock_local_skills_dir / approved_name / "SKILL.md"
    assert skill_file.exists()

    async with get_session() as db:
        approved_record = await db.get(type(approved_seed), approved_seed.id)
        rejected_record = await db.get(type(rejected_seed), rejected_seed.id)
        assert approved_record is not None
        assert rejected_record is not None
        assert approved_record.status == "APPROVED"
        assert approved_record.payload["growth_status"] == "APPROVED"
        assert rejected_record.status == "REJECTED"
        assert rejected_record.payload["growth_status"] == "REJECTED"

        events = list(
            (
                await db.execute(
                    select(ExperienceLedgerEvent).where(ExperienceLedgerEvent.entity_id.in_([approved_seed.id, rejected_seed.id]))
                )
            )
            .scalars()
            .all()
        )
        event_types_by_entity = {
            event.entity_id: {existing.event_type for existing in events if existing.entity_id == event.entity_id}
            for event in events
        }
        assert "skill_growth.approved" in event_types_by_entity[approved_seed.id]
        assert "skill_growth.rejected" in event_types_by_entity[rejected_seed.id]

        for event in events:
            await db.delete(event)
        await db.delete(approved_record)
        await db.delete(rejected_record)
        await db.commit()


@pytest.mark.asyncio
async def test_approve_binds_skill_to_agent(mock_local_skills_dir: Path) -> None:
    """Verify that approving a skill draft adds skill_id to Agent.skill_ids."""
    from app.database.models import Agent

    agent_id = f"test-agent-{uuid4().hex[:8]}"
    skill_name = "agent-bound-skill"

    async with get_session() as db:
        agent = Agent(id=agent_id, name="Test Agent", skill_ids=[], model_config={})
        db.add(agent)
        await db.commit()

    try:
        draft = await notify_skill_draft_created(
            {
                "has_value": True,
                "user_id": "test-user",
                "agent_id": agent_id,
                "type": "skill_draft",
                "skill_name": skill_name,
                "skill_description": "Test binding",
                "content": "---\nname: agent-bound-skill\ndescription: test\n---\n\n## Steps\n1. Do",
            }
        )

        result = await approve_skill_draft(
            draft.id,
            ApproveDraftRequest(skill_name=skill_name, scope_agent_id=agent_id),
        )

        assert result["status"] == "APPROVED"
        assert result["materialized"] is True
        assert result.get("skill_id") is not None

        async with get_session() as db:
            agent = await db.get(Agent, agent_id)
            assert agent is not None
            assert result["skill_id"] in agent.skill_ids
    finally:
        async with get_session() as db:
            from sqlalchemy import delete as sa_delete

            await db.execute(sa_delete(ExperienceLedgerEvent))
            await db.execute(sa_delete(ApprovalRecord))
            agent = await db.get(Agent, agent_id)
            if agent:
                await db.delete(agent)
            await db.commit()


@pytest.mark.asyncio
async def test_approve_binding_idempotent(mock_local_skills_dir: Path) -> None:
    """Verify that repeated approve does not duplicate skill_id in Agent.skill_ids."""
    from app.api.skills.drafts import _bind_skill_to_agent
    from app.database.models import Agent

    agent_id = f"test-agent-idempotent-{uuid4().hex[:8]}"

    async with get_session() as db:
        agent = Agent(id=agent_id, name="Idempotent Agent", skill_ids=["existing-skill"], model_config={})
        db.add(agent)
        await db.commit()

    try:
        await _bind_skill_to_agent("new-skill", agent_id)
        await _bind_skill_to_agent("new-skill", agent_id)

        async with get_session() as db:
            agent = await db.get(Agent, agent_id)
            assert agent is not None
            assert agent.skill_ids.count("new-skill") == 1
            assert "existing-skill" in agent.skill_ids
    finally:
        async with get_session() as db:
            agent = await db.get(Agent, agent_id)
            if agent:
                await db.delete(agent)
            await db.commit()


@pytest.mark.asyncio
async def test_bind_skill_to_nonexistent_agent() -> None:
    """Verify that binding to a non-existent agent does not raise."""
    from app.api.skills.drafts import _bind_skill_to_agent

    await _bind_skill_to_agent("some-skill", "nonexistent-agent-id")


@pytest.mark.asyncio
async def test_bind_skill_with_none_agent_id() -> None:
    """Verify that binding with None agent_id is a no-op."""
    from app.api.skills.drafts import _bind_skill_to_agent

    await _bind_skill_to_agent("some-skill", None)
