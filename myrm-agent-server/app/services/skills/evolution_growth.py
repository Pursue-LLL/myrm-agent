"""Evolution proposal adaptation for the unified skill-growth domain.

[INPUT]
- myrm_agent_harness.agent.skills.evolution.core.types::EvolutionProposal, EvolutionType (POS: Harness 技能演化提案类型)
- myrm_agent_harness.agent.skills.evolution.db.store::SkillStore (POS: Harness 技能存储访问)

[OUTPUT]
- build_skill_growth_result: 将 Harness EvolutionProposal 归一化为 server skill-growth payload

[POS]
Skill Growth 适配层。负责把 Harness 层的演化提案转换为 server 统一技能成长生命周期可消费的结果载荷，
统一写入 ApprovalRecord 作为唯一事实源。
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionProposal,
    EvolutionType,
)
from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore

from app.config.settings import settings

_DEFAULT_AGENT_ID = "skill_evolution_monitor"


def _skills_db_path() -> Path:
    return Path(settings.database.state_dir) / "skills.db"


def _resolve_skill_identity(proposal: EvolutionProposal) -> tuple[str, str]:
    if proposal.evolution_type == EvolutionType.CAPTURED:
        return proposal.skill_id, ""

    store = SkillStore(db_path=_skills_db_path())
    try:
        skill_record = store.get_skill(proposal.skill_id)
    finally:
        store.close()

    if skill_record is None:
        return proposal.skill_id, ""
    return skill_record.name or proposal.skill_id, skill_record.path or ""


def _build_reason(proposal: EvolutionProposal) -> str:
    reason = proposal.reasoning.strip()
    if proposal.task_context.strip():
        return (
            f"{reason}\n\n[Task Context]: {proposal.task_context.strip()}"
            if reason
            else proposal.task_context.strip()
        )
    return reason


def _build_trigger_condition(proposal: EvolutionProposal) -> str:
    if proposal.task_context.strip():
        return proposal.task_context.strip()
    return proposal.reasoning.strip()


def build_skill_growth_result(
    proposal: EvolutionProposal,
    *,
    auto_apply: bool,
    agent_id: str = _DEFAULT_AGENT_ID,
    chat_id: str | None = None,
) -> dict[str, object]:
    """Convert a Harness evolution proposal into the unified skill-growth payload."""
    skill_name, skill_path = _resolve_skill_identity(proposal)
    reason = _build_reason(proposal)
    test_passed = proposal.score > 0.5

    base_payload: dict[str, object] = {
        "has_value": True,
        "agent_id": agent_id,
        "chat_id": chat_id,
        "skill_id": proposal.skill_id,
        "skill_name": skill_name,
        "skill_path": skill_path,
        "skill_description": reason,
        "original_content": proposal.original_content,
        "proposed_content": proposal.proposed_content,
        "confidence": proposal.score,
        "test_passed": test_passed,
        "growth_source": "evolution_engine",
        "evolution_type": proposal.evolution_type.value,
        "auto_apply": auto_apply,
        "trajectory": proposal.trajectory,
    }

    if proposal.edit_summary:
        base_payload["edit_summary"] = proposal.edit_summary

    if proposal.evolution_type == EvolutionType.CAPTURED:
        base_payload.update(
            {
                "type": "skill_draft",
                "trigger_condition": _build_trigger_condition(proposal),
                "skill_steps": proposal.proposed_content,
                "content": proposal.proposed_content,
            }
        )
        return base_payload

    if proposal.evolution_type == EvolutionType.OPTIMIZE_DESCRIPTION:
        base_payload.update(
            {
                "type": "description_update",
                "proposed_description": proposal.proposed_content,
            }
        )
        return base_payload

    base_payload.update(
        {
            "type": "skill_patch",
            "patch_content": proposal.proposed_content,
            "proposal_diff": proposal.diff,
            "content": proposal.proposed_content,
        }
    )
    return base_payload
