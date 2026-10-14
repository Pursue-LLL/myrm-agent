"""Skill growth lifecycle orchestration.

[INPUT]
- app.core.skills.config_version::bump_skill_config_version (POS: Skill config version bumper)
- app.core.skills.creation.service::skill_creation_service (POS: Skill creation service)
- app.core.skills.providers.local::compute_local_skill_id (POS: Local skill ID computation)
- app.core.skills.store.service::skills_service (POS: Skill store service)
- app.platform_utils.deployment_capabilities::get_deployment_capabilities (POS: 部署能力语义注册表。启动时一次性计算并缓存当前部署环境支持的语义能力位。)
- ..auto_extractor::auto_extract_skill, render_skill_draft_markdown (POS: 技能物化辅助器)
- ..draft_notification (POS: 技能成长记录持久化)
- ..scan_risk_policy::assess_scan_risk (POS: 后台学习的高危新增复核策略)
- myrm_agent_harness.backends.skills.similarity::SkillSimilarityChecker (POS: Skill similarity checking protocol)

[OUTPUT]
- process_skill_review_result(): Unified entry point for processing Harness review results.
- set_similarity_checker(): Inject optional SkillSimilarityChecker at startup.

[POS]
Skill growth lifecycle orchestration. Unifies Harness review outputs into a single
business-layer lifecycle: safe new skills may auto-apply, risky changes become
reviewable growth cases, and locked skills are recorded as blocked.
Includes semantic deduplication to prevent skill entropy.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, cast

from app.core.skills.config_version import bump_skill_config_version
from app.core.skills.creation.service import skill_creation_service
from app.core.skills.providers.local import compute_local_skill_id
from app.core.skills.store.service import skills_service
from app.platform_utils.deployment_capabilities import get_deployment_capabilities

from ..auto_extractor import auto_extract_skill, render_skill_draft_markdown
from ..draft_notification import (
    REASON_APPLY_FAILED,
    REASON_EVOLUTION_LOCKED,
    REASON_RISK_PREFIX,
    REASON_SCAN_FAILED,
    REASON_SIMILAR_PREFIX,
    evaluate_growth_scan,
    notify_skill_draft_created,
    persist_skill_draft_record,
)
from ..scan_risk_policy import assess_scan_risk

if TYPE_CHECKING:
    from myrm_agent_harness.backends.skills.similarity import SkillSimilarityChecker

logger = logging.getLogger(__name__)

_similarity_checker: SkillSimilarityChecker | None = None

SIMILARITY_THRESHOLD = 0.75


def set_similarity_checker(checker: SkillSimilarityChecker | None) -> None:
    """Inject an optional SkillSimilarityChecker at startup (called from agent factory)."""
    global _similarity_checker  # noqa: PLW0603
    _similarity_checker = checker


async def _find_similar_skill_names(skill_name: str, description: str) -> list[str]:
    """Names of existing skills semantically close to the draft; empty when none or the check is unavailable."""
    if _similarity_checker is None:
        return []
    try:
        similar = await _similarity_checker.find_similar(skill_name, description, top_k=3, threshold=SIMILARITY_THRESHOLD)
    except Exception as e:
        logger.warning("Semantic dedup check failed (non-blocking): %s", e)
        return []
    return [match.name for match in similar]


async def _get_existing_local_skill(skill_name: str) -> object | None:
    skill_dir = skill_creation_service.base_path / skill_name
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None

    skill_id = compute_local_skill_id(skill_dir)
    return await skills_service.get_skill(skill_id)


async def process_skill_review_result(result: dict[str, object]) -> object | None:
    """Process a Harness review result into the unified skill growth lifecycle."""
    if not result.get("has_value"):
        return None

    result_type = str(result.get("type") or "")
    if result_type not in {"skill_draft", "skill_patch", "semantic_memory"}:
        return None

    if result_type == "semantic_memory":
        return cast(object | None, await notify_skill_draft_created(result))

    # Local skill writes are disabled when allows_local_skills is False (e.g. remote
    # webui or disabled persistent volume). Fail closed: skip skill drafts/patches
    # entirely, while semantic-memory drafts stay available (they do not touch
    # the local skill store).
    if not get_deployment_capabilities().allows_local_skills:
        logger.info(
            "Skill growth materialization skipped: local skills disabled in current deployment mode (%s)",
            result_type,
        )
        return None

    skill_name = str(result.get("skill_name") or "")
    description = str(result.get("skill_description") or "")
    if not skill_name:
        logger.warning("Skill growth lifecycle skipped: missing skill_name")
        return None

    existing_skill = await _get_existing_local_skill(skill_name)
    is_locked = bool(existing_skill and getattr(existing_skill, "evolution_locked", False))

    if is_locked:
        return cast(
            object | None,
            await persist_skill_draft_record(
                result,
                status="BLOCKED_LOCKED",
                dedupe_statuses=("BLOCKED_LOCKED",),
                reason_code=REASON_EVOLUTION_LOCKED,
            ),
        )

    if result_type == "skill_patch":
        return cast(object | None, await notify_skill_draft_created(result))

    # For new skill captures, only auto-apply when the target does not already exist
    # and the pre-flight security scan is clean.
    if existing_skill is not None:
        return cast(object | None, await notify_skill_draft_created(result))

    similar_names = await _find_similar_skill_names(skill_name, description)
    if similar_names:
        logger.info("Skill draft '%s' flagged by semantic dedup: %s", skill_name, similar_names)
        return cast(
            object | None,
            await persist_skill_draft_record(
                result,
                status="PENDING_REVIEW",
                dedupe_statuses=("PENDING_REVIEW",),
                reason_code=REASON_SIMILAR_PREFIX + ",".join(similar_names),
            ),
        )

    scan_status, scan_summary = await evaluate_growth_scan(result, skill_name=skill_name)
    if scan_status != "PENDING_REVIEW":
        return cast(
            object | None,
            await persist_skill_draft_record(
                result,
                status=scan_status,
                dedupe_statuses=("FAILED_SCAN",),
                reason_code=REASON_SCAN_FAILED,
                security_scan_summary=scan_summary,
            ),
        )

    # CRITICAL is a hard stop above; HIGH-level behavior (outbound uploads, privilege changes,
    # persistence) is allowed in a skill but must be seen by the user before it runs unattended.
    risk = await assess_scan_risk(skill_name, render_skill_draft_markdown(result))
    if risk.requires_review:
        logger.info("Skill draft '%s' held for review by the scan risk policy: %s", skill_name, risk.signals)
        return cast(
            object | None,
            await persist_skill_draft_record(
                result,
                status="PENDING_REVIEW",
                dedupe_statuses=("PENDING_REVIEW",),
                reason_code=REASON_RISK_PREFIX + ",".join(risk.signals),
                security_scan_summary=risk.scan_summary,
            ),
        )

    eval_cases = result.get("eval_cases")
    materialized = await auto_extract_skill(
        result,
        eval_cases=eval_cases if isinstance(eval_cases, list) else None,
    )
    if not materialized.success:
        return cast(
            object | None,
            await persist_skill_draft_record(
                result,
                status="PENDING_REVIEW",
                dedupe_statuses=("PENDING_REVIEW",),
                reason_code=REASON_APPLY_FAILED,
                apply_error=materialized.error or "unknown error",
            ),
        )

    bump_skill_config_version()
    return cast(
        object | None,
        await persist_skill_draft_record(
            result,
            status="AUTO_APPLIED",
            description=materialized.description,
            reviewed_at=datetime.now(timezone.utc),
            dedupe_statuses=(),
        ),
    )
