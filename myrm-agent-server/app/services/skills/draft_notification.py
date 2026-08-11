"""Skill growth record persistence service.

Persists reviewed skill growth cases into ``ApprovalRecord`` rows, mirrors the
final lifecycle status into the experience ledger, and publishes front-end
refresh events.

[INPUT]
- myrm_agent_harness.backends.skills.scanning::ScanResult, ScanSeverity, scan_skill_content (POS: 技能内容安全扫描)
- app.database.connection::get_session (POS: 数据库连接管理)
- app.services.approvals.registry::ApprovalRegistry (POS: 统一的拦截审批注册与唤醒中枢)
- app.services.skills.experience_ledger::record_skill_growth_event (POS: 学习资产事件账本)
- app.core.skills.creation.service::skill_creation_service (POS: Skill creation service)
- app.core.skills.providers.local::compute_local_skill_id (POS: Local skill ID computation)
- app.core.skills.store.service::skills_service (POS: Skill store service)
- myrm_agent_harness.utils.fuzzy_match::fuzzy_replace (POS: 通用模糊匹配模块)
- app.services.event.app_event_bus::AppEvent, AppEventType, get_event_bus (POS: 业务层 SSE 事件总线)

[OUTPUT]
- publish_skill_growth_event: SKILL_GROWTH_UPDATED 前端刷新事件单一出口
- notify_skill_draft_created: Harness 审核输出 → 可审核草稿
- persist_skill_draft_record: ApprovalRecord 落库 + 去重抑制 + ledger 镜像 + 前端事件
- evaluate_growth_scan / build_scannable_growth_content: 落库前安全预检

[POS]
技能成长记录持久化：成长 case 落库、安全预检、去重抑制与前端刷新事件发布。
"""

import logging
from datetime import datetime

from myrm_agent_harness.backends.skills.scanning import (
    ScanResult,
    ScanSeverity,
    scan_skill_content,
)

from app.database.connection import get_session
from app.database.models.approval import ApprovalRecord
from app.services.approvals.registry import ApprovalRegistry
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus
from app.services.skills.experience_ledger import record_skill_growth_event

logger = logging.getLogger(__name__)

MAX_SKILL_CONTENT_CHARS = 65_536
MAX_PENDING_PROPOSALS = 50


def _resolve_growth_status(record_status: str, payload: dict[str, object]) -> str:
    payload_status = payload.get("growth_status")
    if isinstance(payload_status, str) and payload_status:
        return payload_status
    if record_status == "APPROVED":
        return "APPROVED"
    if record_status == "REJECTED":
        return "REJECTED"
    return "PENDING_REVIEW"


def _append_scan_failure(description: str, scan_result: ScanResult) -> str:
    findings_texts = [
        f"- [{f.severity.name}] {f.threat_type}: {f.description}"
        for f in scan_result.findings
    ]
    base = description.strip()
    suffix = "\n".join(findings_texts)
    if base:
        return f"{base}\n\n**PRE-FLIGHT SECURITY SCAN FAILED:**\n{suffix}"
    return f"**PRE-FLIGHT SECURITY SCAN FAILED:**\n{suffix}"


def _publish_sse_event(
    event_type: AppEventType, data: dict[str, object]
) -> None:
    """Publish an SSE event through the shared bus, logging failures."""
    try:
        bus = get_event_bus()
        bus.publish(AppEvent(event_type=event_type, data=data))
    except Exception as e:
        logger.error("Failed to publish SSE event %s: %s", event_type, e)


def publish_skill_growth_event(
    *,
    case_id: str,
    draft_type: str,
    status: str,
    name: str,
) -> None:
    """Publish the single-source SKILL_GROWTH_UPDATED refresh event."""
    _publish_sse_event(
        AppEventType.SKILL_GROWTH_UPDATED,
        {
            "case_id": case_id,
            "draft_type": draft_type,
            "status": status,
            "name": name,
        },
    )


def _publish_new_skill_draft_event(*, draft_id: str, draft_type: str, name: str) -> None:
    """Publish the NEW_SKILL_DRAFT event for a pending review draft."""
    _publish_sse_event(
        AppEventType.NEW_SKILL_DRAFT,
        {
            "draft_id": draft_id,
            "draft_type": draft_type,
            "name": name,
        },
    )


async def build_scannable_growth_content(result: dict[str, object]) -> str:
    """Resolve the effective skill content used for security scanning."""
    draft_type = str(result.get("type") or "")
    if draft_type == "skill_draft":
        return str(result.get("content") or result.get("skill_steps") or "")
    if draft_type != "skill_patch":
        return str(result.get("content") or "")

    import re

    from myrm_agent_harness.utils.fuzzy_match import fuzzy_replace

    from app.core.skills.creation.service import skill_creation_service
    from app.core.skills.providers.local import compute_local_skill_id
    from app.core.skills.store.service import skills_service

    skill_name = str(result.get("skill_name") or "")
    if not skill_name:
        return str(result.get("patch_content") or result.get("content") or "")

    skill_dir = skill_creation_service.base_path / skill_name
    skill_id = compute_local_skill_id(skill_dir)
    skill_content_bytes = await skills_service.get_skill_file(skill_id, "SKILL.md")
    patch_content = str(result.get("patch_content") or result.get("content") or "")
    if not skill_content_bytes:
        return patch_content

    original_content = (
        skill_content_bytes.decode("utf-8")
        if isinstance(skill_content_bytes, bytes)
        else skill_content_bytes
    )
    pattern = r"<<<<<<<\s*SEARCH\n(.*?)\n=======\n(.*?)\n>>>>>>>\s*REPLACE"
    blocks = re.findall(pattern, patch_content, flags=re.DOTALL)

    new_content = original_content
    if blocks:
        for search, replace in blocks:
            replace_result = fuzzy_replace(
                new_content, search, replace, replace_all=False
            )
            if replace_result.success:
                new_content = replace_result.content
        return new_content

    if patch_content.startswith("---"):
        return patch_content
    return patch_content


async def evaluate_growth_scan(
    result: dict[str, object],
    *,
    skill_name: str,
    description: str,
) -> tuple[str, str]:
    """Return (status, description) after pre-flight security scan."""
    content_to_scan = await build_scannable_growth_content(result)
    if not content_to_scan:
        return "PENDING_REVIEW", description

    try:
        scan_result = scan_skill_content(skill_name, content_to_scan)
    except Exception as exc:
        logger.error("Skill draft pre-flight scan failed: %s", exc)
        return "PENDING_REVIEW", description

    if (
        not scan_result.is_clean
        and scan_result.max_severity
        and scan_result.max_severity >= ScanSeverity.CRITICAL
    ):
        logger.warning(
            "Skill draft '%s' failed pre-flight security scan. Marking as FAILED_SCAN.",
            skill_name,
        )
        return "FAILED_SCAN", _append_scan_failure(description, scan_result)
    return "PENDING_REVIEW", description


async def persist_skill_draft_record(
    result: dict[str, object],
    *,
    status: str,
    description: str | None = None,
    reviewed_at: datetime | None = None,
    dedupe_statuses: tuple[str, ...] = ("PENDING_REVIEW",),
) -> ApprovalRecord | None:
    """Persist a skill growth case using ApprovalRegistry."""
    agent_id = str(result.get("agent_id") or "default")
    chat_id = result.get("chat_id")
    draft_type = str(result.get("type") or "unknown")
    raw_content = result.get("content") or ""
    draft_name = str(result.get("skill_name") or str(raw_content)[:80] or "")
    final_description = (
        description
        if description is not None
        else str(result.get("skill_description") or "")
    )

    if isinstance(raw_content, str) and len(raw_content) > MAX_SKILL_CONTENT_CHARS:
        logger.warning(
            "Skill draft content too large (%d chars, max %d): %s",
            len(raw_content),
            MAX_SKILL_CONTENT_CHARS,
            draft_name,
        )
        return None

    if draft_name and status in dedupe_statuses:
        pending_records = await ApprovalRegistry.list_pending_growth(
            limit=MAX_PENDING_PROPOSALS + 1
        )
        is_dup = False
        for rec in pending_records:
            existing_status = _resolve_growth_status(rec.status, rec.payload)
            if (
                rec.action_type == draft_type
                and rec.payload.get("skill_name") == draft_name
                and existing_status in dedupe_statuses
            ):
                is_dup = True
                break
        if is_dup:
            logger.info(
                "Duplicate skill growth suppressed: name=%s type=%s status=%s",
                draft_name,
                draft_type,
                status,
            )
            for rec in pending_records:
                if (
                    rec.action_type == draft_type
                    and rec.payload.get("skill_name") == draft_name
                ):
                    return rec
            return None

        if len(pending_records) >= MAX_PENDING_PROPOSALS:
            logger.warning(
                "Pending proposal limit reached (%d/%d). Rejecting new draft: %s",
                len(pending_records),
                MAX_PENDING_PROPOSALS,
                draft_name,
            )
            return None

    # Determine severity based on status
    severity = "critical" if status == "FAILED_SCAN" else "info"

    # Persist via ApprovalRegistry
    eval_cases = result.get("eval_cases")
    payload = {
        "skill_name": draft_name,
        "description": final_description,
        "trigger_condition": result.get("trigger_condition"),
        "skill_steps": result.get("skill_steps"),
        "patch_content": result.get("patch_content"),
        "content": result.get("content"),
        "growth_status": status,
        "eval_cases": eval_cases if isinstance(eval_cases, list) else None,
    }

    approval_status = "PENDING"
    if status in {"AUTO_APPLIED", "APPROVED"}:
        approval_status = "APPROVED"
    elif status == "REJECTED":
        approval_status = "REJECTED"
    elif status == "BLOCKED_LOCKED":
        approval_status = "PENDING"
        severity = "warning"

    record = await ApprovalRegistry.create_approval(
        agent_id=agent_id,
        action_type=draft_type,
        payload=payload,
        reason=final_description,
        severity=severity,
        chat_id=str(chat_id) if chat_id else None,
        status=approval_status,
    )

    if record and reviewed_at is not None and approval_status != "PENDING":
        async with get_session() as db:
            persisted = await db.get(type(record), record.id)
            if persisted is not None:
                persisted.resolved_at = reviewed_at
                await db.commit()
                await db.refresh(persisted)
                record = persisted

    if record is not None:
        await record_skill_growth_event(
            entity_id=record.id,
            draft_type=draft_type,
            status=status,
            skill_name=draft_name or None,
            summary=final_description or draft_name or draft_type,
            detail={
                "approval_status": approval_status,
                "severity": severity,
            },
        )

    publish_skill_growth_event(
        case_id=record.id if record else "",
        draft_type=draft_type,
        status=status,
        name=draft_name,
    )
    if record is not None and status == "PENDING_REVIEW":
        _publish_new_skill_draft_event(
            draft_id=record.id, draft_type=draft_type, name=draft_name
        )

    return record


async def notify_skill_draft_created(result: dict[str, object]) -> ApprovalRecord | None:
    """Persist a reviewable skill draft from Harness review output."""
    if not result.get("has_value"):
        return None

    draft_name = str(
        result.get("skill_name") or str(result.get("content") or "")[:80] or ""
    )
    description = str(result.get("skill_description") or "")
    status = "PENDING_REVIEW"

    if str(result.get("type") or "") in ("skill_draft", "skill_patch") and draft_name:
        status, description = await evaluate_growth_scan(
            result, skill_name=draft_name, description=description
        )

    return await persist_skill_draft_record(
        result,
        status=status,
        description=description,
        dedupe_statuses=("PENDING_REVIEW", "FAILED_SCAN", "BLOCKED_LOCKED"),
    )
