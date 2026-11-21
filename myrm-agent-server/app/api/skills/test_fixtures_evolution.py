"""Local-only HTTP fixture for the evolution proposal review Chrome E2E.

[INPUT]
- app.services.skills.evolution_reviews::create_evolution_review_record (POS: 以 ApprovalRecord 为唯一事实源的 evolution 审核生命周期服务)
- app.services.skills.evolution_review.disk::get_skill_store (POS: Evolution 审核的 apply / rollback 所读写的进化 SkillStore)
- app.api.skills.test_fixtures::GrowthDirName (POS: Dev-only skills fixture router for Chrome E2E (prebuilt catalog, skill-manage and upstream-update seeds, growth drafts); gated by is_local_mode())
- app.core.skills.models::LOCAL_SKILLS_DIR (POS: Skill system data models)
- app.core.skills.providers.local::compute_local_skill_id (POS: 本地技能扫描服务)
- app.config.deploy_mode::is_local_mode (POS: 部署模式与运行方式)
- myrm_agent_harness.agent.skills.evolution::EvolutionType (POS: Skill Evolution System - Framework Layer.)
- myrm_agent_harness.agent.skills.evolution.core.types::(EnvironmentFingerprint, SkillLineage, SkillRecord) (POS: Data types for skill evolution system.)
- myrm_agent_harness.agent.skills.market.sanitizer::SKILL_MD_FILE (POS: 技能文件过滤与校验)

[OUTPUT]
- seed_evolution_proposal: local/test route that records a pending evolution proposal for a skill directory the test
  created with seed_growth_skill; the proposal appends one step carrying the test's marker and is created by the
  production path, so the review card, its approve and reject actions and the apply are the real ones. The proposal
  belongs to the agent the request names, and a skill given an owner is stored as that agent's own, which makes the
  apply for any other agent a Copy-on-Write fork

[POS]
Dev-only fixture for the evolution proposal review Chrome E2E; gated by is_local_mode().
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.agent.skills.evolution import EvolutionType
from myrm_agent_harness.agent.skills.evolution.core.types import EnvironmentFingerprint, SkillLineage, SkillRecord
from myrm_agent_harness.agent.skills.market.sanitizer import SKILL_MD_FILE
from pydantic import BaseModel, Field

from app.api.skills.test_fixtures import GrowthDirName
from app.config.deploy_mode import is_local_mode
from app.core.skills.models import LOCAL_SKILLS_DIR
from app.core.skills.providers.local import compute_local_skill_id
from app.services.skills.evolution_review.disk import get_skill_store
from app.services.skills.evolution_reviews import create_evolution_review_record

router = APIRouter()


class SeedEvolutionProposalRequest(BaseModel):
    dir_name: GrowthDirName
    marker: str = Field(min_length=1, max_length=120)
    agent_id: str = Field(default="default", min_length=1, max_length=64)
    owner_agent_id: str | None = Field(default=None, min_length=1, max_length=64)


def _skill_owned_by(owner_agent_id: str, skill_id: str, name: str, content: str, skill_md: Path) -> SkillRecord:
    """The store row of a skill that belongs to one agent: another agent's approval copies it instead of editing it."""
    return SkillRecord(
        skill_id=skill_id,
        name=name,
        description="Build the weekly report.",
        content=content,
        path=str(skill_md),
        lineage=SkillLineage(evolution_type=EvolutionType.CAPTURED, parent_id=None),
        environment=EnvironmentFingerprint(custom_tags={"scope_agent_id": owner_agent_id}),
    )


@router.post("/test/seed-evolution-proposal", include_in_schema=False)
async def seed_evolution_proposal(body: SeedEvolutionProposalRequest) -> dict[str, str]:
    """Local E2E: a pending proposal that appends one step carrying ``marker`` to a skill from ``seed_growth_skill``.

    Only the engine that would have written the evolved content is replaced: the base hash, the approval record and
    the ledger event come from the production creation path. The skill is named after its directory, which is how
    the proposal addresses it.
    """
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    directory = LOCAL_SKILLS_DIR / body.dir_name
    skill_md = directory / SKILL_MD_FILE
    try:
        original = await asyncio.to_thread(skill_md.read_text, encoding="utf-8")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Skill not found: {body.dir_name}") from exc

    skill_id = compute_local_skill_id(directory)
    if body.owner_agent_id:
        await get_skill_store().save_skill(_skill_owned_by(body.owner_agent_id, skill_id, body.dir_name, original, skill_md))
    record = await create_evolution_review_record(
        agent_id=body.agent_id,
        chat_id=None,
        proposal_skill_id=skill_id,
        skill_name=body.dir_name,
        skill_path=str(skill_md),
        evolution_type=EvolutionType.FIX.value,
        reason=f"E2E proposal: add a step with marker {body.marker}",
        original_content=original,
        evolved_content=f"{original.rstrip()}\n2. {body.marker}\n",
        confidence=0.9,
        test_passed=True,
        task_context=None,
    )
    return {"evolution_id": record.id, "skill_id": skill_id}
