"""Auto skill materialization helpers.

Materializes safe growth outcomes to disk and emits user-facing evolution
events. Orchestration and policy decisions live in ``growth/lifecycle.py``.

[INPUT]
- myrm_agent_harness.agent.skills.evolution.core.types::EnvironmentFingerprint, EvolutionType, SkillLineage, SkillRecord (POS: Harness 技能演化核心类型)
- myrm_agent_harness.agent.skills.evolution.pipeline.patch::PatchType, apply_skill_patch (POS: Harness 技能补丁应用)
- app.core.skills.creation.service::skill_creation_service (POS: Skill creation service)
- app.core.skills.store.evolution_store::get_evolution_skill_store (POS: core/skills/store 进化 SQLite 入口)
- app.services.skills.evolution_events::publish_skill_evolved_event (POS: 技能进化事件发布)

[OUTPUT]
- auto_extract_or_patch_skill: 将已通过策略判断的成长结果落盘为真实技能或补丁
- SkillMaterializationResult: 物化结果 DTO

[POS]
技能物化辅助器：仅在策略判定通过后把成长结果写入技能文件（新建或补丁），并发布 ``SKILL_EVOLVED`` 事件。
"""

import logging
from dataclasses import dataclass

from myrm_agent_harness.agent.skills.evolution.core.types import (
    EnvironmentFingerprint,
    EvolutionType,
    SkillLineage,
    SkillRecord,
)
from myrm_agent_harness.agent.skills.evolution.pipeline.patch import (
    PatchType,
    apply_skill_patch,
)

from app.core.skills.creation.service import skill_creation_service
from app.services.skills.evolution_events import publish_skill_evolved_event

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SkillMaterializationResult:
    """Outcome of materializing a reviewed skill growth result."""

    success: bool
    evolution_type: str | None = None
    description: str = ""
    skill_name: str | None = None
    error: str | None = None


async def _persist_review_eval_cases(
    skill_name: str,
    content: str,
    skill_path: str,
    eval_cases: list[dict[str, object]],
) -> None:
    """Best-effort write of review-generated eval_cases into the evolution SkillStore.

    Populates the regression gate consumed by ``filter_variants_by_regression`` so
    future FIX/OPTIMIZE proposals are guarded by the freshly materialized cases.
    """
    if not eval_cases:
        return
    try:
        from app.core.skills.store.evolution_store import get_evolution_skill_store

        store = get_evolution_skill_store()
        record = store.get_skill_by_name_version(skill_name)
        if record is None:
            record = SkillRecord(
                skill_id=skill_name,
                name=skill_name,
                description="Auto-extracted skill",
                content=content,
                path=skill_path,
                lineage=SkillLineage(
                    evolution_type=EvolutionType.CAPTURED,
                    version=1,
                    created_by="review_callback",
                ),
                is_active=True,
                environment=EnvironmentFingerprint(),
            )
        record.eval_cases = eval_cases
        await store.save_skill(record)
    except Exception as exc:
        logger.warning("Failed to persist eval_cases for skill '%s': %s", skill_name, exc)


def _build_skill_markdown(
    skill_name: str,
    description: str,
    trigger_condition: str,
    skill_steps: str,
) -> str:
    return f"""---
name: {skill_name}
description: {description}
category: custom
always: false
---

# {skill_name}

## Trigger Condition
{trigger_condition}

## Instructions
{skill_steps}
"""


async def auto_extract_or_patch_skill(
    result: dict[str, object],
    eval_cases: list[dict[str, object]] | None = None,
) -> SkillMaterializationResult:
    """Materialize a reviewed skill growth result when policy allows it."""

    if not result.get("has_value"):
        return SkillMaterializationResult(success=False, error="has_value is false")

    result_type = str(result.get("type") or "")
    skill_name = str(result.get("skill_name") or "")

    if not skill_name:
        logger.warning("Auto-extractor: missing skill_name")
        return SkillMaterializationResult(success=False, error="missing skill_name")

    if result_type == "skill_draft":
        description = str(result.get("skill_description") or "Auto-extracted skill")
        trigger_condition = str(result.get("trigger_condition") or "")
        skill_steps = str(result.get("skill_steps") or "")

        content = _build_skill_markdown(skill_name, description, trigger_condition, skill_steps)
        save_result = await skill_creation_service.save_skill(
            name=skill_name,
            content=content,
            description=description,
        )
        if save_result.success:
            await _persist_review_eval_cases(
                skill_name,
                content,
                str(skill_creation_service.base_path / skill_name / "SKILL.md"),
                eval_cases or [],
            )
            logger.warning("🚀 Auto-Extractor: Successfully extracted NEW skill '%s'", skill_name)
            publish_skill_evolved_event(
                skill_name=skill_name,
                evolution_type="new",
                description=description,
            )
            return SkillMaterializationResult(
                success=True,
                evolution_type="new",
                description=description,
                skill_name=skill_name,
            )
        else:
            logger.error(
                "Auto-Extractor failed to save new skill '%s': %s",
                skill_name,
                save_result.error,
            )
            return SkillMaterializationResult(
                success=False,
                evolution_type="new",
                description=description,
                skill_name=skill_name,
                error=save_result.error,
            )

    elif result_type == "skill_patch":
        patch_content = str(result.get("patch_content") or "")
        if not patch_content:
            logger.warning("Auto-extractor: patch_content missing for skill %s", skill_name)
            return SkillMaterializationResult(
                success=False,
                evolution_type="patch",
                skill_name=skill_name,
                error="patch_content missing",
            )

        skill_dir = skill_creation_service.base_path / skill_name
        skill_file = skill_dir / "SKILL.md"

        if not skill_file.exists():
            logger.warning(
                "Auto-Extractor: Cannot patch skill '%s' because it does not exist locally.",
                skill_name,
            )
            return SkillMaterializationResult(
                success=False,
                evolution_type="patch",
                skill_name=skill_name,
                error="target skill not found locally",
            )

        original_content = skill_file.read_text(encoding="utf-8")

        patch_result = apply_skill_patch(
            original_content=original_content,
            llm_output=patch_content,
            patch_type=PatchType.DIFF,
        )

        if patch_result.success and patch_result.content:
            save_result = await skill_creation_service.save_skill(
                name=skill_name,
                content=patch_result.content,
                description="Auto-patched skill",
            )
            if save_result.success:
                await _persist_review_eval_cases(
                    skill_name,
                    patch_result.content,
                    str(skill_file),
                    eval_cases or [],
                )
                logger.warning(
                    "🛠️ Auto-Extractor: Successfully applied PATCH to skill '%s'",
                    skill_name,
                )
                publish_skill_evolved_event(
                    skill_name=skill_name,
                    evolution_type="patch",
                    description="Applied optimization patch",
                )
                return SkillMaterializationResult(
                    success=True,
                    evolution_type="patch",
                    description="Applied optimization patch",
                    skill_name=skill_name,
                )
            else:
                logger.error(
                    "Auto-Extractor failed to save patched skill '%s': %s",
                    skill_name,
                    save_result.error,
                )
                return SkillMaterializationResult(
                    success=False,
                    evolution_type="patch",
                    description="Applied optimization patch",
                    skill_name=skill_name,
                    error=save_result.error,
                )
        else:
            logger.error(
                "Auto-Extractor failed to apply patch to skill '%s': %s",
                skill_name,
                patch_result.error_message,
            )
            return SkillMaterializationResult(
                success=False,
                evolution_type="patch",
                description="Applied optimization patch",
                skill_name=skill_name,
                error=patch_result.error_message,
            )

    else:
        return SkillMaterializationResult(
            success=False,
            skill_name=skill_name,
            error=f"unsupported result_type: {result_type}",
        )
