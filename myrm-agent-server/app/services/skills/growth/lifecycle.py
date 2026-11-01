"""Skill growth lifecycle orchestration.

[INPUT]
- app.core.skills.config_version::bump_skill_config_version (POS: Skill config version bumper)
- app.core.skills.store.local_lookup::approval_writes_into (POS: Blocking file system lookups in the primary local skills directory; tells whether approving a draft under its name writes into the directory of the skill it names)
- app.core.skills.store.service::skills_service (POS: Skill store service; finds the existing local skill a review result names, by directory name or by a name it is known by)
- app.platform_utils.deployment_capabilities::get_deployment_capabilities (POS: 部署能力语义注册表。启动时一次性计算并缓存当前部署环境支持的语义能力位。)
- ..auto_extractor::auto_extract_skill, render_skill_draft_markdown (POS: 技能物化辅助器)
- ..draft_notification (POS: 技能成长记录持久化)
- ..scan_risk_policy::assess_scan_risk (POS: 后台学习的高危新增复核策略)

[OUTPUT]
- process_skill_review_result(): Unified entry point for processing Harness review results.

[POS]
Skill growth lifecycle orchestration. Unifies Harness review outputs into a single
business-layer lifecycle: safe new skills may auto-apply, risky changes become
reviewable growth cases, and locked skills are recorded as blocked.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import cast

from app.core.skills.config_version import bump_skill_config_version
from app.core.skills.store.local_lookup import approval_writes_into
from app.core.skills.store.service import skills_service
from app.platform_utils.deployment_capabilities import get_deployment_capabilities

from ..auto_extractor import auto_extract_skill, render_skill_draft_markdown
from ..draft_notification import (
    REASON_APPLY_FAILED,
    REASON_EVOLUTION_LOCKED,
    REASON_RISK_PREFIX,
    REASON_SCAN_FAILED,
    evaluate_growth_scan,
    notify_skill_draft_created,
    persist_skill_draft_record,
)
from ..scan_risk_policy import assess_scan_risk

logger = logging.getLogger(__name__)


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
    if not skill_name:
        logger.warning("Skill growth lifecycle skipped: missing skill_name")
        return None

    # The reviewer names a skill by the name the agent runtime lists it under; the pipeline from here on keeps,
    # previews and applies a patch by the directory of the skill it patches. A new skill draft keeps its name unless
    # approving it writes into that directory: it is then recorded under the directory's own spelling, because the
    # skill is enabled and bound by the page id of that spelling, not of the one the approval wrote under.
    skill_dir = await skills_service.find_local_skill_dir(skill_name)
    existing_skill = await skills_service.get_local_skill(skill_dir) if skill_dir is not None else None
    if skill_dir is not None and (result_type == "skill_patch" or approval_writes_into(skill_dir, skill_name)):
        skill_name = skill_dir.name
        result = {**result, "skill_name": skill_name}
    is_locked = existing_skill is not None and existing_skill.evolution_locked

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
