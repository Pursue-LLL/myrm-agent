"""A proposal built from text the skill's SKILL.md no longer holds is discarded; one built from the file goes to review."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import pytest
from myrm_agent_harness.agent.skills.evolution import SkillStore
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionProposal,
    EvolutionType,
    SkillLineage,
    SkillRecord,
)
from sqlalchemy import select

from app.database.connection import get_session
from app.database.models import ApprovalRecord
from app.services.agent.confidence_approval_flow import ConfidenceApprovalFlow
from app.services.skills.evolution_review.disk_content import skill_file_hash

_STORED = "---\nname: demo-skill\ndescription: As the store has it.\n---\n"
_ON_DISK = "---\nname: demo-skill\ndescription: As the user edited it.\nevolution-locked: true\n---\n"
_EVOLVED = "---\nname: demo-skill\ndescription: As evolved.\n---\n"


def _record(skill_path: Path | str) -> SkillRecord:
    return SkillRecord(
        skill_id="skill-1",
        name="demo-skill",
        description="Demo.",
        content=_STORED,
        path=str(skill_path),
        lineage=SkillLineage(evolution_type=EvolutionType.CAPTURED),
    )


def _proposal(original_content: str) -> EvolutionProposal:
    return EvolutionProposal(
        skill_id="skill-1",
        evolution_type=EvolutionType.FIX,
        original_content=original_content,
        proposed_content=_EVOLVED,
        diff="diff",
        score=0.5,
        reasoning="Repair the skill.",
        task_context="",
        created_at=None,
    )


@pytest.fixture
def skill_file(tmp_path: Path) -> Path:
    path = tmp_path / "demo-skill" / "SKILL.md"
    path.parent.mkdir()
    path.write_text(_ON_DISK, encoding="utf-8")
    return path


@pytest.fixture
async def store(tmp_path: Path, skill_file: Path) -> AsyncIterator[SkillStore]:
    """A store whose copy of the skill is the text before the user's edit, as the evolution store lets it fall behind."""
    skill_store = SkillStore(db_path=tmp_path / "skills.db")
    await skill_store.save_skill(_record(skill_file))
    with patch("app.core.skills.store.evolution_store.get_evolution_skill_store", return_value=skill_store):
        yield skill_store
    skill_store.close()


async def _evolution_approvals() -> list[ApprovalRecord]:
    async with get_session() as db:
        result = await db.execute(select(ApprovalRecord).where(ApprovalRecord.action_type == "evolution"))
        return list(result.scalars().all())


def _stored_content(store: SkillStore) -> str:
    skill = store.get_skill("skill-1")
    assert skill is not None
    return skill.content


@pytest.mark.asyncio
async def test_a_proposal_built_on_text_the_file_no_longer_has_is_discarded(store: SkillStore) -> None:
    result = await ConfidenceApprovalFlow().process_evolution(_proposal(_STORED))

    assert not result.approved
    assert not result.requires_manual_review
    assert await _evolution_approvals() == []
    assert _stored_content(store) == _STORED


@pytest.mark.asyncio
async def test_a_proposal_built_on_the_current_file_goes_to_review_against_it(store: SkillStore) -> None:
    await ConfidenceApprovalFlow().process_evolution(_proposal(_STORED))

    result = await ConfidenceApprovalFlow().process_evolution(_proposal(_ON_DISK))

    assert result.requires_manual_review
    (approval,) = await _evolution_approvals()
    assert isinstance(approval.payload, dict)
    assert approval.payload["original_content"] == _ON_DISK
    assert approval.payload["base_content_hash"] == skill_file_hash(Path(approval.payload["skill_path"]))


@pytest.mark.asyncio
async def test_a_proposal_for_a_skill_whose_file_is_gone_still_goes_to_review(store: SkillStore, skill_file: Path) -> None:
    skill_file.unlink()

    result = await ConfidenceApprovalFlow().process_evolution(_proposal(_STORED))

    assert result.requires_manual_review
    assert len(await _evolution_approvals()) == 1


@pytest.mark.asyncio
async def test_a_proposal_without_original_content_has_nothing_to_compare(store: SkillStore) -> None:
    result = await ConfidenceApprovalFlow().process_evolution(_proposal(""))

    assert result.requires_manual_review
    assert len(await _evolution_approvals()) == 1
