"""Skill growth lifecycle orchestration.

[INPUT]
- app.api.skills.config_version::bump_skill_config_version (POS: Skill config version bumper)
- app.core.skills.creation.service::skill_creation_service (POS: Skill creation service)
- app.core.skills.providers.local::compute_local_skill_id (POS: Local skill ID computation)
- app.core.skills.store.service::skills_service (POS: Skill store service)
- app.services.skills.auto_extractor::auto_extract_or_patch_skill (POS: Skill materialization helper)
- app.services.skills.draft_notification (POS: Skill draft persistence and notification)
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
from app.services.skills.auto_extractor import auto_extract_or_patch_skill
from app.services.skills.draft_notification import (
    evaluate_growth_scan,
    notify_skill_draft_created,
    persist_skill_draft_record,
)

if TYPE_CHECKING:
    from myrm_agent_harness.backends.skills.similarity import SkillSimilarityChecker

logger = logging.getLogger(__name__)

_similarity_checker: SkillSimilarityChecker | None = None

SIMILARITY_THRESHOLD = 0.75


def set_similarity_checker(checker: SkillSimilarityChecker | None) -> None:
    """Inject an optional SkillSimilarityChecker at startup (called from agent factory)."""
    global _similarity_checker  # noqa: PLW0603
    _similarity_checker = checker


async def _check_semantic_duplicate(skill_name: str, description: str) -> str | None:
    """Return a human-readable warning if a semantically similar skill already exists, else None."""
    if _similarity_checker is None:
        return None
    try:
        similar = await _similarity_checker.find_similar(
            skill_name, description, top_k=3, threshold=SIMILARITY_THRESHOLD
        )
        if not similar:
            return None
        names = ", ".join(f"'{s.name}' ({s.similarity_score:.0%})" for s in similar)
        return f"Semantically similar skill(s) detected: {names}. Downgraded to manual review to prevent skill entropy."
    except Exception as e:
        logger.warning("Semantic dedup check failed (non-blocking): %s", e)
        return None


async def _get_existing_local_skill(skill_name: str) -> object | None:
    skill_dir = skill_creation_service.base_path / skill_name
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None

    skill_id = compute_local_skill_id(skill_dir)
    return await skills_service.get_skill(skill_id)


def _locked_description(skill_name: str, base_description: str) -> str:
    message = (
        f'Skill "{skill_name}" is locked against automatic evolution. Review the proposed change manually before applying it.'
    )
    if base_description.strip():
        return f"{base_description.strip()}\n\n{message}"
    return message


def _materialization_failure_description(base_description: str, error: str | None) -> str:
    failure = f"Auto-apply failed and has been downgraded to manual review: {error or 'unknown error'}"
    if base_description.strip():
        return f"{base_description.strip()}\n\n{failure}"
    return failure


async def process_skill_review_result(result: dict[str, object]) -> object | None:
    """Process a Harness review result into the unified skill growth lifecycle."""
    if not result.get("has_value"):
        return None

    result_type = str(result.get("type") or "")
    if result_type not in {"skill_draft", "skill_patch", "semantic_memory"}:
        return None

    if result_type == "semantic_memory":
        return cast(object | None, await notify_skill_draft_created(result))

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
                description=_locked_description(skill_name, description),
                dedupe_statuses=("BLOCKED_LOCKED",),
            ),
        )

    if result_type == "skill_patch":
        return cast(object | None, await notify_skill_draft_created(result))

    # For new skill captures, only auto-apply when the target does not already exist
    # and the pre-flight security scan is clean.
    if existing_skill is not None:
        return cast(object | None, await notify_skill_draft_created(result))

    dedup_warning = await _check_semantic_duplicate(skill_name, description)
    if dedup_warning:
        logger.info("Skill draft '%s' flagged by semantic dedup: %s", skill_name, dedup_warning)
        desc_with_warning = f"{description}\n\n⚠️ {dedup_warning}" if description.strip() else dedup_warning
        return cast(
            object | None,
            await persist_skill_draft_record(
                result,
                status="PENDING_REVIEW",
                description=desc_with_warning,
                dedupe_statuses=("PENDING_REVIEW",),
            ),
        )

    scan_status, scan_description = await evaluate_growth_scan(
        result,
        skill_name=skill_name,
        description=description,
    )
    if scan_status != "PENDING_REVIEW":
        return cast(
            object | None,
            await persist_skill_draft_record(
                result,
                status=scan_status,
                description=scan_description,
                dedupe_statuses=("FAILED_SCAN",),
            ),
        )

    materialized = await auto_extract_or_patch_skill(result)
    if not materialized.success:
        return cast(
            object | None,
            await persist_skill_draft_record(
                result,
                status="PENDING_REVIEW",
                description=_materialization_failure_description(scan_description, materialized.error),
                dedupe_statuses=("PENDING_REVIEW",),
            ),
        )

    bump_skill_config_version()
    return cast(
        object | None,
        await persist_skill_draft_record(
            result,
            status="AUTO_APPLIED",
            description=materialized.description or scan_description,
            reviewed_at=datetime.now(timezone.utc),
            dedupe_statuses=(),
        ),
    )
