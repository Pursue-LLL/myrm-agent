"""Auto skill materialization helpers.

Materializes safe growth outcomes to disk and emits user-facing evolution
events. Orchestration and policy decisions live in ``growth_lifecycle.py``.
"""

import logging
from dataclasses import dataclass

from myrm_agent_harness.agent.skills.evolution.pipeline.patch import PatchType, apply_skill_patch

from app.core.skills.creation.service import skill_creation_service
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SkillMaterializationResult:
    """Outcome of materializing a reviewed skill growth result."""

    success: bool
    evolution_type: str | None = None
    description: str = ""
    skill_name: str | None = None
    error: str | None = None


def _publish_evolution_event(skill_name: str, evolution_type: str, description: str) -> None:
    try:
        bus = get_event_bus()
        bus.publish(
            AppEvent(
                event_type=AppEventType.SKILL_EVOLVED,
                data={"skill_name": skill_name, "evolution_type": evolution_type, "description": description[:200]},
            )
        )
        logger.info("Skill evolved notification published: %s", skill_name)
    except Exception as e:
        logger.error("Failed to publish skill evolution event: %s", e)


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


async def auto_extract_or_patch_skill(result: dict[str, object]) -> SkillMaterializationResult:
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
            logger.warning("🚀 Auto-Extractor: Successfully extracted NEW skill '%s'", skill_name)
            _publish_evolution_event(skill_name, "new", description)
            return SkillMaterializationResult(
                success=True,
                evolution_type="new",
                description=description,
                skill_name=skill_name,
            )
        else:
            logger.error("Auto-Extractor failed to save new skill '%s': %s", skill_name, save_result.error)
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
            logger.warning("Auto-Extractor: Cannot patch skill '%s' because it does not exist locally.", skill_name)
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
                logger.warning("🛠️ Auto-Extractor: Successfully applied PATCH to skill '%s'", skill_name)
                _publish_evolution_event(skill_name, "patch", "Applied optimization patch")
                return SkillMaterializationResult(
                    success=True,
                    evolution_type="patch",
                    description="Applied optimization patch",
                    skill_name=skill_name,
                )
            else:
                logger.error("Auto-Extractor failed to save patched skill '%s': %s", skill_name, save_result.error)
                return SkillMaterializationResult(
                    success=False,
                    evolution_type="patch",
                    description="Applied optimization patch",
                    skill_name=skill_name,
                    error=save_result.error,
                )
        else:
            logger.error("Auto-Extractor failed to apply patch to skill '%s': %s", skill_name, patch_result.error_message)
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
