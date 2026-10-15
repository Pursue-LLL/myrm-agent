"""Auto skill materialization helpers.

Materializes safe new-skill drafts to disk and emits the skill-list refresh
event. Orchestration and policy decisions live in ``growth/lifecycle.py``.

[INPUT]
- myrm_agent_harness.agent.skills.evolution.core.types::EnvironmentFingerprint, EvolutionType, SkillLineage, SkillRecord (POS: Harness 技能演化核心类型)
- app.core.skills.creation.service::skill_creation_service (POS: Skill creation service)
- app.core.skills.utils::resolve_skill_description, yaml_scalar (POS: 技能描述回退与 frontmatter 标量转义)
- app.core.skills.store.evolution_store::get_evolution_skill_store (POS: core/skills/store 进化 SQLite 入口)
- app.services.skills.evolution_events::publish_skill_evolved_event (POS: 技能进化事件发布)

[OUTPUT]
- auto_extract_skill: 执行代码 AST 语法门禁，将已通过策略判断的新技能草稿落盘为真实技能
- render_skill_draft_markdown: 渲染新技能落盘的 SKILL.md 文本（安全预检与物化共用同一份）
- validate_python_code_blocks: 校验 Markdown 中 Python 代码块语法合法性
- SkillMaterializationResult: 物化结果 DTO

[POS]
技能物化辅助器：执行 Python 代码 AST 语法门禁，仅在语法合法且策略判定通过后把新技能草稿写入技能文件，并发布静默的 ``SKILL_EVOLVED`` 刷新事件（用户通知由 ``SKILL_GROWTH_UPDATED`` 承担）。补丁走人工审核，不经此处。
"""

import ast
import logging
import re
from dataclasses import dataclass

from myrm_agent_harness.agent.skills.evolution.core.types import (
    EnvironmentFingerprint,
    EvolutionType,
    SkillLineage,
    SkillRecord,
)

from app.core.skills.creation.service import skill_creation_service
from app.core.skills.utils import resolve_skill_description, yaml_scalar
from app.services.skills.evolution_events import publish_skill_evolved_event

logger = logging.getLogger(__name__)

_PYTHON_CODE_BLOCK_RE = re.compile(r"```(?:python|py)[^\n]*\n(.*?)\n```", re.DOTALL)


def validate_python_code_blocks(text: str) -> str | None:
    """Validate syntax of all python code blocks in markdown text.

    Returns an error description if any python code block fails ast.parse,
    otherwise None.
    """
    for i, match in enumerate(_PYTHON_CODE_BLOCK_RE.finditer(text), 1):
        code = match.group(1).strip()
        if not code:
            continue
        try:
            ast.parse(code)
        except SyntaxError as exc:
            return f"Python code block #{i} has syntax error: {exc}"
    return None


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
    description: str,
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
                description=description,
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
description: {yaml_scalar(description)}
category: custom
always: false
---

# {skill_name}

## Trigger Condition
{trigger_condition}

## Instructions
{skill_steps}
"""


def _draft_description(result: dict[str, object]) -> str:
    return resolve_skill_description(
        str(result.get("skill_description") or ""),
        str(result.get("trigger_condition") or ""),
        str(result.get("skill_name") or ""),
    )


def render_skill_draft_markdown(result: dict[str, object]) -> str:
    """Render the SKILL.md that materializing a ``skill_draft`` result writes to disk.

    The pre-materialization security scan reads this exact text, so what is scanned is what is saved.
    """
    return _build_skill_markdown(
        str(result.get("skill_name") or ""),
        _draft_description(result),
        str(result.get("trigger_condition") or ""),
        str(result.get("skill_steps") or ""),
    )


async def auto_extract_skill(
    result: dict[str, object],
    eval_cases: list[dict[str, object]] | None = None,
) -> SkillMaterializationResult:
    """Materialize a reviewed new-skill draft once policy allows it."""

    if not result.get("has_value"):
        return SkillMaterializationResult(success=False, error="has_value is false")

    result_type = str(result.get("type") or "")
    skill_name = str(result.get("skill_name") or "")

    if not skill_name:
        logger.warning("Auto-extractor: missing skill_name")
        return SkillMaterializationResult(success=False, error="missing skill_name")

    if result_type != "skill_draft":
        return SkillMaterializationResult(
            success=False,
            skill_name=skill_name,
            error=f"unsupported result_type: {result_type}",
        )

    description = _draft_description(result)
    skill_steps = str(result.get("skill_steps") or "")

    code_syntax_error = validate_python_code_blocks(skill_steps)
    if code_syntax_error:
        logger.warning("Auto-Extractor: Rejected skill draft '%s' due to syntax error: %s", skill_name, code_syntax_error)
        return SkillMaterializationResult(
            success=False,
            evolution_type="new",
            description=description,
            skill_name=skill_name,
            error=code_syntax_error,
        )

    content = render_skill_draft_markdown(result)
    save_result = await skill_creation_service.save_skill(
        name=skill_name,
        content=content,
        description=description,
    )
    if not save_result.success:
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

    await _persist_review_eval_cases(
        skill_name,
        description,
        content,
        str(skill_creation_service.base_path / skill_name / "SKILL.md"),
        eval_cases or [],
    )
    logger.info("Auto-Extractor: extracted new skill '%s'", skill_name)
    publish_skill_evolved_event(
        skill_name=skill_name,
        evolution_type="new",
        description=description,
        notify=False,
    )
    return SkillMaterializationResult(
        success=True,
        evolution_type="new",
        description=description,
        skill_name=skill_name,
    )
