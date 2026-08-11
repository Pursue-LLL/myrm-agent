"""Regression tests for skill drafts backed by ApprovalRecord."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
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
from app.services.approvals.registry import ApprovalRegistry
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


@pytest.mark.asyncio
async def test_approve_skill_patch_applies_diff(mock_local_skills_dir: Path) -> None:
    """Approve a skill_patch draft; the SEARCH/REPLACE diff is applied to the file."""
    skill_name = "patch-target-skill"
    skill_dir = mock_local_skills_dir / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: patch-target-skill\ndescription: Base\n---\n\n## Steps\n1. Old behavior\n",
        encoding="utf-8",
    )

    draft = await notify_skill_draft_created(
        {
            "has_value": True,
            "type": "skill_patch",
            "skill_name": skill_name,
            "content": "<<<<<<< SEARCH\n1. Old behavior\n=======\n1. New behavior\n>>>>>>> REPLACE",
        }
    )
    assert draft is not None

    result = await approve_skill_draft(
        draft.id,
        ApproveDraftRequest(skill_name=skill_name),
    )

    assert result["status"] == "APPROVED"
    assert result["materialized"] is True
    assert result["materialized_type"] == "skill_patch"
    updated = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "1. New behavior" in updated

    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.mark.asyncio
async def test_approve_skill_patch_missing_target_rolls_back(mock_local_skills_dir: Path) -> None:
    """Approve a patch whose target skill is missing => rollback to PENDING_REVIEW."""
    draft = await notify_skill_draft_created(
        {
            "has_value": True,
            "type": "skill_patch",
            "skill_name": "no-such-target",
            "content": "<<<<<<< SEARCH\nx\n=======\ny\n>>>>>>> REPLACE",
        }
    )
    assert draft is not None

    result = await approve_skill_draft(
        draft.id,
        ApproveDraftRequest(skill_name="no-such-target"),
    )

    assert result["materialized"] is False
    async with get_session() as db:
        record = await db.get(ApprovalRecord, draft.id)
        assert record is not None
        assert record.status == "PENDING"
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.mark.asyncio
async def test_approve_draft_missing_returns_404() -> None:
    from fastapi import HTTPException

    from app.api.skills.drafts import approve_skill_draft

    with pytest.raises(HTTPException) as exc:
        await approve_skill_draft("nonexistent-draft", ApproveDraftRequest(skill_name="x"))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_approve_non_pending_review_rejected(mock_local_skills_dir: Path) -> None:
    """Approve a draft already marked APPROVED => 400 Cannot approve."""
    from fastapi import HTTPException

    from app.api.skills.drafts import approve_skill_draft

    draft = await notify_skill_draft_created(
        {
            "has_value": True,
            "type": "skill_draft",
            "skill_name": "already-approved",
            "content": "---\nname: already-approved\ndescription: x\n---\n\n## Steps\n1. Do",
        }
    )
    assert draft is not None
    await approve_skill_draft(draft.id, ApproveDraftRequest(skill_name="already-approved"))
    assert (mock_local_skills_dir / "already-approved" / "SKILL.md").exists()

    with pytest.raises(HTTPException) as exc:
        await approve_skill_draft(draft.id, ApproveDraftRequest(skill_name="already-approved"))
    assert exc.value.status_code == 400

    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.mark.asyncio
async def test_approve_unknown_draft_type_not_a_growth_draft(mock_local_skills_dir: Path) -> None:
    """Drafts whose action_type is not a growth draft are not approvable (404)."""
    from fastapi import HTTPException

    from app.api.skills.drafts import approve_skill_draft

    draft = await notify_skill_draft_created(
        {
            "has_value": True,
            "type": "mystery_type",
            "skill_name": "mystery",
            "content": "some content",
        }
    )
    assert draft is not None

    with pytest.raises(HTTPException) as exc:
        await approve_skill_draft(draft.id, ApproveDraftRequest(skill_name="mystery"))
    assert exc.value.status_code == 404

    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.mark.asyncio
async def test_reject_missing_draft_returns_404() -> None:
    from fastapi import HTTPException

    from app.api.skills.drafts import reject_skill_draft

    with pytest.raises(HTTPException) as exc:
        await reject_skill_draft("nonexistent-draft")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_approve_skill_patch_without_skilfile(mock_local_skills_dir: Path) -> None:
    """Patch target dir exists but has no SKILL.md => materialization fails cleanly."""
    skill_name = "patch-no-md"
    skill_dir = mock_local_skills_dir / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    # No SKILL.md written on purpose.

    draft = await notify_skill_draft_created(
        {
            "has_value": True,
            "type": "skill_patch",
            "skill_name": skill_name,
            "content": "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE",
        }
    )
    assert draft is not None

    result = await approve_skill_draft(draft.id, ApproveDraftRequest(skill_name=skill_name))
    assert result["materialized"] is False
    assert "not found" in (result.get("error") or "")

    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.mark.asyncio
async def test_approve_draft_with_markdown_fence(mock_local_skills_dir: Path) -> None:
    """Draft content wrapped in ```markdown fences is stripped before save."""
    draft = await notify_skill_draft_created(
        {
            "has_value": True,
            "type": "skill_draft",
            "skill_name": "fenced-skill",
            "content": "```markdown\n---\nname: fenced-skill\ndescription: fenced\n---\n\n## Steps\n1. Do\n```",
        }
    )
    assert draft is not None

    result = await approve_skill_draft(draft.id, ApproveDraftRequest(skill_name="fenced-skill"))
    assert result["materialized"] is True
    saved = (mock_local_skills_dir / "fenced-skill" / "SKILL.md").read_text(encoding="utf-8")
    assert saved.startswith("---")
    assert "```" not in saved

    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.mark.asyncio
async def test_materialize_semantic_memory_failure() -> None:
    """Semantic memory materialization failure returns a clean error dict."""
    from app.api.skills.drafts import _materialize_semantic_memory

    class _Draft:
        id = "memory-draft"
        content = "remember this fact"

    with patch(
        "app.services.agent.platform_config.require_platform_embedding_config",
        side_effect=RuntimeError("no embedding backend"),
    ):
        result = await _materialize_semantic_memory(_Draft())  # type: ignore[arg-type]

    assert result["materialized"] is False
    assert "Semantic memory materialization failed" in (result.get("error") or "")


@pytest.mark.asyncio
async def test_approve_non_pending_review_raises_400(mock_local_skills_dir: Path) -> None:
    """Approve of a draft that is not in PENDING_REVIEW is rejected with 400."""
    from fastapi import HTTPException

    record = await ApprovalRegistry.create_approval(
        agent_id="guard-agent",
        action_type="skill_draft",
        payload={"skill_name": "already-approved", "content": "# x"},
        reason="already resolved",
        status="APPROVED",
    )

    with pytest.raises(HTTPException) as exc_info:
        await approve_skill_draft(
            record.id,
            ApproveDraftRequest(skill_name="already-approved"),
        )
    assert exc_info.value.status_code == 400
    assert "Cannot approve" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_approve_unknown_draft_raises_404() -> None:
    """Approve of a non-existent draft raises 404."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await approve_skill_draft(
            "no-such-draft-id",
            ApproveDraftRequest(skill_name="x"),
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_approve_semantic_memory_draft(mock_local_skills_dir: Path) -> None:
    """Approve a semantic_memory draft; memory materialization is mocked."""
    from unittest.mock import patch as mock_patch

    draft = await notify_skill_draft_created(
        {
            "has_value": True,
            "type": "semantic_memory",
            "skill_name": "memory-draft",
            "content": "The user prefers concise replies.",
            "skill_description": "Memory about user preference",
        }
    )
    assert draft is not None

    fake_manager = AsyncMock()
    fake_manager.add_knowledge = AsyncMock(return_value=SimpleNamespace(id="mem-123"))

    fake_embed_cfg = SimpleNamespace(
        provider="openai",
        api_key="test-key",
        model="text-embedding-3-small",
    )

    with (
        mock_patch(
            "app.services.agent.platform_config.require_platform_embedding_config",
            new=AsyncMock(return_value=fake_embed_cfg),
        ),
        mock_patch(
            "app.core.memory.adapters.setup.create_memory_manager",
            new=AsyncMock(return_value=fake_manager),
        ),
        mock_patch(
            "app.core.memory.adapters.setup.resolve_context_binding",
            return_value=SimpleNamespace(namespace="test"),
        ),
    ):
        result = await approve_skill_draft(
            draft.id,
            ApproveDraftRequest(skill_name="memory-draft"),
        )

    assert result["status"] == "APPROVED"
    assert result["materialized"] is True
    assert result["materialized_type"] == "memory"
    assert result["memory_id"] == "mem-123"
    fake_manager.add_knowledge.assert_awaited_once()

    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.mark.asyncio
async def test_reject_unknown_draft_raises_404() -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await reject_skill_draft("no-such-draft")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_reject_non_pending_review_raises_400() -> None:
    from fastapi import HTTPException

    record = await ApprovalRegistry.create_approval(
        agent_id="reject-guard-agent",
        action_type="skill_draft",
        payload={"skill_name": "already-rejected", "content": "# x"},
        reason="already resolved",
        status="REJECTED",
    )

    with pytest.raises(HTTPException) as exc_info:
        await reject_skill_draft(record.id)
    assert exc_info.value.status_code == 400
    assert "Cannot reject" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_reject_writes_negative_exemplar_memory(mock_local_skills_dir: Path) -> None:
    """Rejecting a draft adds a negative exemplar memory (mocked)."""
    from unittest.mock import patch as mock_patch

    draft = await notify_skill_draft_created(
        {
            "has_value": True,
            "type": "skill_draft",
            "skill_name": "neg-memory-skill",
            "content": "---\nname: neg-memory-skill\n---\n## Steps\n1. x",
        }
    )
    assert draft is not None

    fake_manager = AsyncMock()
    fake_manager.add_knowledge = AsyncMock(return_value=SimpleNamespace(id="neg-1"))

    with (
        mock_patch(
            "app.services.agent.platform_config.require_platform_embedding_config",
            new=AsyncMock(return_value=SimpleNamespace(provider="openai", api_key="k")),
        ),
        mock_patch(
            "app.core.memory.adapters.setup.create_memory_manager",
            new=AsyncMock(return_value=fake_manager),
        ),
        mock_patch(
            "app.core.memory.adapters.setup.resolve_context_binding",
            return_value=SimpleNamespace(namespace="test"),
        ),
    ):
        result = await reject_skill_draft(draft.id)

    assert result["status"] == "REJECTED"
    fake_manager.add_knowledge.assert_awaited_once()
    assert fake_manager.add_knowledge.await_args.kwargs["tags"] == [
        "rejected-skill-proposal",
        "negative-exemplar",
    ]

    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.mark.asyncio
async def test_get_unknown_draft_raises_404() -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await get_skill_draft("no-such-draft")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_approve_with_eval_cases_persists_to_store(mock_local_skills_dir: Path) -> None:
    """Approving a draft with eval_cases writes them into the evolution SkillStore."""
    from unittest.mock import patch as mock_patch

    eval_cases = [{"input": "do x", "expected": "x"}]
    draft = await notify_skill_draft_created(
        {
            "has_value": True,
            "type": "skill_draft",
            "skill_name": "eval-cases-skill",
            "content": "---\nname: eval-cases-skill\ndescription: Eval cases skill\n---\n## Steps\n1. x",
            "eval_cases": eval_cases,
        }
    )
    assert draft is not None

    fake_store = AsyncMock()
    fake_store.get_skill_by_name_version = MagicMock(return_value=None)
    fake_store.save_skill = AsyncMock()

    with mock_patch(
        "app.core.skills.store.evolution_store.get_evolution_skill_store",
        return_value=fake_store,
    ):
        result = await approve_skill_draft(
            draft.id,
            ApproveDraftRequest(skill_name="eval-cases-skill"),
        )

    assert result["status"] == "APPROVED"
    fake_store.save_skill.assert_awaited_once()
    saved = fake_store.save_skill.await_args.args[0]
    assert saved.eval_cases == eval_cases

    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.mark.asyncio
async def test_approve_eval_cases_store_failure_is_swallowed(mock_local_skills_dir: Path) -> None:
    """A failing SkillStore write does not abort the approval."""
    from unittest.mock import patch as mock_patch

    draft = await notify_skill_draft_created(
        {
            "has_value": True,
            "type": "skill_draft",
            "skill_name": "eval-fail-skill",
            "content": "---\nname: eval-fail-skill\ndescription: Eval fail skill\n---\n## Steps\n1. x",
            "eval_cases": [{"input": "a", "expected": "b"}],
        }
    )
    assert draft is not None

    fake_store = AsyncMock()
    fake_store.get_skill_by_name_version = MagicMock(return_value=None)
    fake_store.save_skill = AsyncMock(side_effect=RuntimeError("store down"))

    with mock_patch(
        "app.core.skills.store.evolution_store.get_evolution_skill_store",
        return_value=fake_store,
    ):
        result = await approve_skill_draft(
            draft.id,
            ApproveDraftRequest(skill_name="eval-fail-skill"),
        )

    assert result["status"] == "APPROVED"  # failure is logged, not propagated

    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.mark.asyncio
async def test_approve_content_in_code_fence_strips_fences(mock_local_skills_dir: Path) -> None:
    """Materialization strips surrounding markdown code fences from content."""
    draft = await notify_skill_draft_created(
        {
            "has_value": True,
            "type": "skill_draft",
            "skill_name": "fenced-skill",
            "content": "```markdown\n---\nname: fenced-skill\ndescription: Fenced\n---\n## Steps\n1. x\n```",
        }
    )
    assert draft is not None

    result = await approve_skill_draft(
        draft.id,
        ApproveDraftRequest(skill_name="fenced-skill"),
    )

    assert result["status"] == "APPROVED"
    assert result["materialized"] is True
    assert result["materialized_type"] == "skill"
    # The written SKILL.md must not contain the outer code fence.
    saved_dir = Path(str(result["saved_path"]))
    written = (saved_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "```markdown" not in written
    assert "1. x" in written

    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.mark.asyncio
async def test_approve_content_without_frontmatter_injects_header(mock_local_skills_dir: Path) -> None:
    """Content without YAML frontmatter gets a synthetic header injected."""
    draft = await notify_skill_draft_created(
        {
            "has_value": True,
            "type": "skill_draft",
            "skill_name": "no-frontmatter-skill",
            "content": "Just plain steps.\n1. do it",
            "skill_description": "Plain skill",
        }
    )
    assert draft is not None

    result = await approve_skill_draft(
        draft.id,
        ApproveDraftRequest(skill_name="no-frontmatter-skill"),
    )

    assert result["status"] == "APPROVED"
    assert result["materialized"] is True
    saved_dir = Path(str(result["saved_path"]))
    written = (saved_dir / "SKILL.md").read_text(encoding="utf-8")
    assert written.startswith("---\nname: no-frontmatter-skill")
    assert "1. do it" in written

    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.mark.asyncio
async def test_approve_draft_without_content_uses_template(mock_local_skills_dir: Path) -> None:
    """A draft with no content falls back to the form-based template builder."""
    draft = await notify_skill_draft_created(
        {
            "has_value": True,
            "type": "skill_draft",
            "skill_name": "template-skill",
            "content": "",
            "skill_description": "Template-based",
            "trigger_condition": "when asked",
            "skill_steps": "1. run",
        }
    )
    assert draft is not None

    result = await approve_skill_draft(
        draft.id,
        ApproveDraftRequest(skill_name="template-skill"),
    )

    assert result["status"] == "APPROVED"
    assert result["materialized"] is True
    saved_dir = Path(str(result["saved_path"]))
    written = (saved_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "## When to Use" in written
    assert "## Steps" in written

    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.mark.asyncio
async def test_approve_draft_without_name_not_materialized() -> None:
    """A draft without a name reports materialized=False."""
    record = await ApprovalRegistry.create_approval(
        agent_id="no-name-agent",
        action_type="skill_draft",
        payload={
            "skill_name": "",
            "content": "---\nname: x\n---\n## Steps\n1. x",
            "growth_status": "PENDING_REVIEW",
        },
        reason="test",
        status="PENDING",
    )
    record.payload = dict(record.payload) | {"skill_name": ""}
    async with get_session() as db:
        await db.commit()

    result = await approve_skill_draft(
        record.id,
        ApproveDraftRequest(skill_name=""),
    )

    assert result["materialized"] is False

    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.mark.asyncio
async def test_approve_save_skill_failure_rolls_back(mock_local_skills_dir: Path) -> None:
    """When the local skill write fails, the draft rolls back to PENDING_REVIEW."""
    from unittest.mock import patch as mock_patch

    draft = await notify_skill_draft_created(
        {
            "has_value": True,
            "type": "skill_draft",
            "skill_name": "save-fail-skill",
            "content": "---\nname: save-fail-skill\ndescription: x\n---\n## Steps\n1. x",
        }
    )
    assert draft is not None

    fake_result = SimpleNamespace(
        success=False,
        error="disk full",
        skill_id=None,
        skill_name=None,
        saved_path=None,
    )
    fake_service = AsyncMock()
    fake_service.save_skill = AsyncMock(return_value=fake_result)

    with mock_patch(
        "app.core.skills.creation.service.skill_creation_service",
        fake_service,
    ):
        result = await approve_skill_draft(
            draft.id,
            ApproveDraftRequest(skill_name="save-fail-skill"),
        )

    assert result["materialized"] is False
    assert result["error"] == "disk full"

    async with get_session() as db:
        record = await db.get(ApprovalRecord, draft.id)
        assert record is not None
        assert record.status == "PENDING"
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.mark.asyncio
async def test_approve_patch_without_name_not_materialized() -> None:
    """A skill_patch draft without a name reports materialized=False."""
    record = await ApprovalRegistry.create_approval(
        agent_id="no-name-patch-agent",
        action_type="skill_patch",
        payload={
            "skill_name": "",
            "content": "<<<<<<< SEARCH\na\n=======\nb\n>>>>>>> REPLACE",
            "growth_status": "PENDING_REVIEW",
        },
        reason="test",
        status="PENDING",
    )
    record.payload = dict(record.payload) | {"skill_name": ""}
    async with get_session() as db:
        await db.commit()

    result = await approve_skill_draft(
        record.id,
        ApproveDraftRequest(skill_name=""),
    )

    assert result["materialized"] is False
    assert "no name" in str(result.get("error", ""))

    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.mark.asyncio
async def test_approve_patch_full_markdown_fallback(mock_local_skills_dir: Path) -> None:
    """A patch whose content is full markdown (no diff) replaces the whole file."""
    skill_name = "full-md-target"
    skill_dir = mock_local_skills_dir / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: full-md-target\ndescription: Base\n---\n\n## Steps\n1. Old\n",
        encoding="utf-8",
    )

    draft = await notify_skill_draft_created(
        {
            "has_value": True,
            "type": "skill_patch",
            "skill_name": skill_name,
            "content": "---\nname: full-md-target\ndescription: Replaced\n---\n\n## Steps\n1. Brand new\n",
        }
    )
    assert draft is not None

    result = await approve_skill_draft(
        draft.id,
        ApproveDraftRequest(skill_name=skill_name),
    )

    assert result["status"] == "APPROVED"
    assert result["materialized"] is True
    updated = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "1. Brand new" in updated
    assert "1. Old" not in updated

    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.mark.asyncio
async def test_approve_patch_mismatched_search_rolls_back(mock_local_skills_dir: Path) -> None:
    """A SEARCH block that does not match the target rolls back to PENDING_REVIEW."""
    skill_name = "mismatch-target"
    skill_dir = mock_local_skills_dir / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: mismatch-target\ndescription: Base\n---\n\n## Steps\n1. Actual content\n",
        encoding="utf-8",
    )

    draft = await notify_skill_draft_created(
        {
            "has_value": True,
            "type": "skill_patch",
            "skill_name": skill_name,
            "content": "<<<<<<< SEARCH\n1. This text does not exist\n=======\n1. Replacement\n>>>>>>> REPLACE",
        }
    )
    assert draft is not None

    result = await approve_skill_draft(
        draft.id,
        ApproveDraftRequest(skill_name=skill_name),
    )

    assert result["materialized"] is False
    assert "not found" in str(result.get("error", ""))
    async with get_session() as db:
        record = await db.get(ApprovalRecord, draft.id)
        assert record is not None
        assert record.status == "PENDING"
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.mark.asyncio
async def test_approve_semantic_memory_without_content_not_materialized() -> None:
    """A semantic_memory draft with no content reports materialized=False."""
    record = await ApprovalRegistry.create_approval(
        agent_id="empty-mem-agent",
        action_type="semantic_memory",
        payload={
            "skill_name": "empty-memory",
            "content": "",
            "growth_status": "PENDING_REVIEW",
        },
        reason="test",
        status="PENDING",
    )
    record.payload = dict(record.payload) | {"content": ""}
    async with get_session() as db:
        await db.commit()

    result = await approve_skill_draft(
        record.id,
        ApproveDraftRequest(skill_name="empty-memory"),
    )

    assert result["materialized"] is False
    assert "no content" in str(result.get("error", ""))

    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()
