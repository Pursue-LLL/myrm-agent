"""Materialization of approved skill growth drafts.

Turns an approved draft into its durable form: a new local SKILL.md, a patched SKILL.md, or a semantic
memory entry. The approve route in ``drafts.py`` owns status transitions and events; this module owns
what gets written.

[INPUT]
- app.api.skills.draft_record::SkillDraftRecord (POS: 技能草稿记录视图)
- app.core.skills.creation.service::skill_creation_service (POS: 技能创作服务)
- app.core.skills.config_version::bump_skill_config_version (POS: skill 配置版本自增)
- app.core.skills.utils::resolve_skill_description, yaml_scalar (POS: 技能描述回退与 frontmatter 标量转义)
- app.core.skills.curator.service::describe_skill_lifecycle,set_skill_archived (POS: 技能归档/恢复的单一写入口)
- app.database.connection::get_session (POS: 数据库连接管理)

[OUTPUT]
- materialize_skill_draft / materialize_skill_patch / materialize_semantic_memory: 落地结果字典（materialized 标志 + 技能/记忆标识或错误）

[POS]
技能草稿落地：新技能写盘（已归档的同名技能一并恢复）、补丁 SEARCH/REPLACE 应用、语义记忆写入，以及批准后评测用例的持久化。
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from app.core.skills.config_version import bump_skill_config_version
from app.core.skills.curator.service import describe_skill_lifecycle, set_skill_archived
from app.core.skills.utils import resolve_skill_description, yaml_scalar
from app.database.connection import get_session
from app.database.models import ApprovalRecord

if TYPE_CHECKING:
    from app.api.skills.draft_record import SkillDraftRecord

logger = logging.getLogger(__name__)


async def _persist_approved_draft_eval_cases(
    draft: SkillDraftRecord,
    skill_name: str,
    description: str,
    content: str,
) -> None:
    """Best-effort write of an approved draft's eval_cases into the evolution SkillStore."""
    try:
        from myrm_agent_harness.agent.skills.evolution.core.types import (
            EnvironmentFingerprint,
            EvolutionType,
            SkillLineage,
            SkillRecord,
        )

        from app.core.skills.creation.service import skill_creation_service
        from app.core.skills.store.evolution_store import get_evolution_skill_store

        raw_eval_cases = None
        async with get_session() as db:
            record = await db.get(ApprovalRecord, draft.id)
            if record is not None and isinstance(record.payload, dict):
                raw_eval_cases = record.payload.get("eval_cases")

        eval_cases = raw_eval_cases if isinstance(raw_eval_cases, list) else []
        if not eval_cases:
            return

        store = get_evolution_skill_store()
        existing = store.get_skill_by_name_version(skill_name)
        if existing is None:
            skill_path = str(skill_creation_service.base_path / skill_name / "SKILL.md")
            existing = SkillRecord(
                skill_id=skill_name,
                name=skill_name,
                description=description,
                content=content,
                path=skill_path,
                lineage=SkillLineage(
                    evolution_type=EvolutionType.CAPTURED,
                    version=1,
                    created_by="draft_approval",
                ),
                is_active=True,
                environment=EnvironmentFingerprint(),
            )
        existing.eval_cases = eval_cases
        await store.save_skill(existing)
    except Exception as exc:
        logger.warning("Failed to persist approved draft eval_cases for %s: %s", skill_name, exc)


def _restore_if_archived(skill_name: str) -> None:
    """Approving a draft is the user's decision to run the skill, so an archived one comes back."""
    lifecycle = describe_skill_lifecycle(skill_name)
    if lifecycle is not None and lifecycle[0]:
        set_skill_archived(skill_name, archived=False)


async def materialize_skill_draft(
    draft: SkillDraftRecord,
    override_name: str | None,
) -> dict[str, str | bool | None]:
    """Write an approved skill draft to disk as a local SKILL.md and auto-enable."""
    from app.core.skills.creation.service import skill_creation_service

    raw_name = override_name or draft.name
    if not raw_name:
        logger.warning("Skill draft %s has no name, skipping materialization", draft.id)
        return {"materialized": False, "error": "Skill draft has no name"}

    skill_name = _slugify_skill_name(raw_name)
    description = resolve_skill_description(draft.description, draft.trigger_condition, skill_name)

    if draft.content and draft.content.strip():
        content = draft.content.strip()
        # Remove any surrounding markdown code blocks (e.g., ```markdown ... ```)
        if content.startswith("```markdown"):
            content = content[11:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        # Sniff for YAML frontmatter
        if not content.startswith("---"):
            skill_md = f"{_frontmatter(skill_name, description)}\n{content}"
        else:
            skill_md = content
    else:
        # Fallback to dummy template for form-based simple drafts
        skill_md = _build_skill_md(skill_name, description, draft.trigger_condition, draft.skill_steps)

    save_result = await skill_creation_service.save_skill(
        name=skill_name,
        content=skill_md,
        description=description,
    )

    if save_result.success:
        _restore_if_archived(skill_name)
        bump_skill_config_version()
        await _persist_approved_draft_eval_cases(draft, skill_name, description, skill_md)
        logger.info("Skill draft materialized: %s -> %s", draft.id, save_result.skill_id)
        return {
            "materialized": True,
            "materialized_type": "skill",
            "skill_id": save_result.skill_id,
            "skill_name": save_result.skill_name,
            "saved_path": save_result.saved_path,
        }

    logger.warning("Skill draft materialization failed: %s - %s", draft.id, save_result.error)
    return {"materialized": False, "error": save_result.error}


async def materialize_skill_patch(
    draft: SkillDraftRecord,
) -> dict[str, str | bool | None]:
    """Apply an approved skill patch to an existing skill."""
    from app.core.skills.creation.service import skill_creation_service
    from app.core.skills.store.service import skills_service

    skill_name = draft.name
    if not skill_name:
        return {"materialized": False, "error": "Skill patch has no name"}

    # patch target is a local skill
    from app.core.skills.providers.local import compute_local_skill_id

    skill_id = compute_local_skill_id(skill_creation_service.base_path / skill_name)
    skill = await skills_service.get_skill(skill_id)
    if not skill:
        logger.warning("Skill patch target not found: %s", skill_id)
        return {"materialized": False, "error": f"Target skill not found: {skill_id}"}

    skill_content_bytes = await skills_service.get_skill_file(skill_id, "SKILL.md")
    if not skill_content_bytes:
        return {"materialized": False, "error": "Could not read original SKILL.md"}

    original_content = skill_content_bytes.decode("utf-8") if isinstance(skill_content_bytes, bytes) else skill_content_bytes

    patch_content = draft.content or ""

    from myrm_agent_harness.utils.fuzzy_match import fuzzy_replace

    pattern = r"<<<<<<<\s*SEARCH\n(.*?)\n=======\n(.*?)\n>>>>>>>\s*REPLACE"
    blocks = re.findall(pattern, patch_content, flags=re.DOTALL)

    new_content = original_content
    if not blocks:
        # Fallback: maybe the LLM just returned the full new markdown instead of a diff?
        if patch_content.startswith("---"):
            new_content = patch_content
        else:
            return {
                "materialized": False,
                "error": "No valid SEARCH/REPLACE blocks found in patch",
            }
    else:
        for search, replace in blocks:
            replace_result = fuzzy_replace(new_content, search, replace, replace_all=False)
            if replace_result.success:
                new_content = replace_result.content
            else:
                logger.warning("Fuzzy replace failed for block: %s", search[:50])
                return {
                    "materialized": False,
                    "error": f"SEARCH block not found or ambiguous: {search[:50]}...",
                }

    save_result = await skill_creation_service.save_skill(
        name=skill_name,
        content=new_content,
        description=skill.description or "",
    )

    if save_result.success:
        bump_skill_config_version()
        await _persist_approved_draft_eval_cases(draft, skill_name, skill.description or skill_name, new_content)
        logger.info("Skill patch materialized: %s -> %s", draft.id, save_result.skill_id)
        return {
            "materialized": True,
            "materialized_type": "skill_patch",
            "skill_id": save_result.skill_id,
            "skill_name": save_result.skill_name,
            "saved_path": save_result.saved_path,
        }

    return {"materialized": False, "error": save_result.error}


async def materialize_semantic_memory(
    draft: SkillDraftRecord,
) -> dict[str, str | bool | None]:
    """Write an approved semantic memory draft into the memory store."""
    content = draft.content or ""
    if not content:
        return {"materialized": False, "error": "Draft has no content"}

    try:
        from app.core.memory.adapters.setup import (
            create_memory_manager,
            resolve_context_binding,
        )
        from app.services.agent.platform_config import require_platform_embedding_config

        embedding_cfg = await require_platform_embedding_config()

        manager = await create_memory_manager(
            resolve_context_binding(
                namespaces=None,
                agent_id=None,
                channel_id=None,
                conversation_id=None,
                task_id=None,
            ),
            embedding_config=embedding_cfg,
            approval_required=False,
        )
        memory = await manager.add_knowledge(content, importance=0.6, tags=["auto-review"])
        logger.info("Semantic memory materialized from draft %s: id=%s", draft.id, memory.id)
        return {
            "materialized": True,
            "materialized_type": "memory",
            "memory_id": str(memory.id),
        }
    except Exception as e:
        logger.error(
            "Failed to materialize semantic memory from draft %s: %s",
            draft.id,
            e,
            exc_info=True,
        )
        return {
            "materialized": False,
            "error": "Semantic memory materialization failed",
        }


def _slugify_skill_name(raw: str) -> str:
    """Convert a human-readable skill name to a valid slug (a-zA-Z0-9_-)."""
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw.strip())
    slug = slug.strip("-")
    return slug[:64] or "auto-skill"


def _frontmatter(name: str, description: str) -> str:
    return f"---\nname: {name}\ndescription: {yaml_scalar(description)}\n---\n"


def _build_skill_md(
    name: str,
    description: str,
    trigger_condition: str | None,
    skill_steps: str | None,
) -> str:
    """Build a minimal SKILL.md with YAML frontmatter from draft fields."""
    parts = [_frontmatter(name, description)]
    if trigger_condition:
        parts.append(f"## When to Use\n{trigger_condition}\n")
    if skill_steps:
        parts.append(f"## Steps\n{skill_steps}\n")
    return "\n".join(parts)
