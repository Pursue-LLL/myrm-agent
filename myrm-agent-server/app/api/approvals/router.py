"""
[INPUT]
- app.services.approvals.registry::ApprovalRegistry (POS: 统一的拦截审批注册与唤醒中枢)
- myrm_agent_harness.agent.types::Command (POS: LangGraph Resume 原语)

[OUTPUT]
- /api/v1/approvals: 审批接口（resolve 支持 comment、allow_always 透传）

[POS]
提供统一的审批决策接口。处理挂起任务的 approve/deny，恢复底层 agent 执行。
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.database.models.approval import ApprovalRecord
from app.services.approvals.registry import ApprovalRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/approvals", tags=["approvals"])


async def _handle_outbound_draft_resolution(record: ApprovalRecord, decision: str) -> None:
    """Send or discard a held outbound draft message based on the approval decision."""
    if decision == "approve":
        from app.services.approvals.registry import send_outbound_draft_payload

        await send_outbound_draft_payload(record.payload or {}, record.agent_id, record.id)
    else:
        logger.info("Outbound draft %s rejected, message discarded", record.id)


class AllowAlwaysValue(BaseModel):
    tool: bool | None = None
    args: bool | None = None


class ResolveApprovalRequest(BaseModel):
    decision: str  # "approve" | "deny" | "reject" (frontend alias)
    edited_payload: dict[str, Any] | None = None
    comment: str | None = None
    allow_always: bool | AllowAlwaysValue | None = None


class BatchResolveApprovalRequest(BaseModel):
    approval_ids: list[str]
    decision: str  # "approve" | "deny"
    confirm_high_risk: bool = False
    safe_only: bool = False


class ApprovalRecordResponse(BaseModel):
    id: str
    action_type: str
    reason: str | None
    severity: str
    payload: dict[str, Any]
    status: str
    created_at: str
    chat_id: str | None
    expires_at: str | None

    @classmethod
    def from_orm(cls, record: Any) -> "ApprovalRecordResponse":
        return cls(
            id=record.id,
            action_type=record.action_type,
            reason=record.reason,
            severity=record.severity,
            payload=record.payload,
            status=record.status,
            created_at=record.created_at.isoformat() if record.created_at else "",
            chat_id=record.chat_id,
            expires_at=record.expires_at.isoformat() if record.expires_at else None,
        )


class ApprovalListResponse(BaseModel):
    approvals: list[ApprovalRecordResponse]


@router.get("", response_model=ApprovalListResponse)
async def list_pending_approvals(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ApprovalListResponse:
    records = await ApprovalRegistry.list_pending(limit=limit, offset=offset)
    return ApprovalListResponse(approvals=[ApprovalRecordResponse.from_orm(r) for r in records])


@router.post("/{approval_id}/resolve")
async def resolve_approval(
    approval_id: str,
    req: ResolveApprovalRequest,
) -> ApprovalRecordResponse:
    """Resolve an approval and resume the agent (if applicable)."""

    normalized_decision = "approve" if req.decision == "approve" else "deny"

    record = await ApprovalRegistry.resolve_approval(
        approval_id=approval_id,
        decision=normalized_decision,
        edited_payload=req.edited_payload,
    )

    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")

    if record.action_type == "outbound_draft":
        await _handle_outbound_draft_resolution(record, normalized_decision)
        return ApprovalRecordResponse.from_orm(record)

    if record.action_type == "mcp_elicitation":
        from app.services.agent.backends.mcp_elicitation_handler import (
            resolve_pending_elicitation,
        )

        resolved = resolve_pending_elicitation(approval_id, normalized_decision)
        if not resolved:
            logger.warning("MCP elicitation %s not found in pending map (may have timed out)", approval_id)
        return ApprovalRecordResponse.from_orm(record)

    # If it's a LangGraph interrupt, we must resume the agent!
    if record.thread_id:
        try:
            logger.info(
                "Resuming agent thread_id=%s with decision=%s",
                record.thread_id,
                req.decision,
            )

            from app.services.event.app_event_bus import (
                AppEvent,
                AppEventType,
                get_event_bus,
            )

            bus = get_event_bus()
            bus.publish(
                AppEvent(
                    event_type=AppEventType.APPROVAL_RESOLVED,
                    data={
                        "action": "resume_agent",
                        "approval_id": record.id,
                        "thread_id": record.thread_id,
                        "chat_id": record.chat_id,
                        "agent_id": record.agent_id,
                        "decision": normalized_decision,
                        "comment": req.comment,
                        "allow_always": req.allow_always,
                        "edited_payload": req.edited_payload,
                    },
                )
            )
        except Exception as e:
            logger.error("Failed to resume agent: %s", e)

    if record.chat_id:
        from app.services.agent.streaming_support.multiplexer import WorkspaceMultiplexer

        WorkspaceMultiplexer.get().publish_session_status(record.chat_id, "idle", "")

    return ApprovalRecordResponse.from_orm(record)


@router.post("/batch-resolve")
async def batch_resolve_approvals(
    req: BatchResolveApprovalRequest,
) -> ApprovalListResponse:
    """Batch resolve multiple approvals and resume the agents with dual-insurance high-risk protection."""
    from myrm_agent_harness.agent.security.batch_risk import (
        BatchApprovalItem,
        classify_batch_approval_risk,
    )

    if not req.approval_ids:
        return ApprovalListResponse(approvals=[])

    normalized_decision = "approve" if req.decision == "approve" else "deny"

    # Pre-fetch records to evaluate batch risk
    pending_records: list[ApprovalRecord] = []
    for approval_id in req.approval_ids:
        record = await ApprovalRegistry.get_approval(approval_id)
        if record and record.status == "PENDING":
            pending_records.append(record)

    if not pending_records:
        return ApprovalListResponse(approvals=[])

    # Convert to BatchApprovalItem contract
    batch_items = [
        BatchApprovalItem(
            item_id=r.id,
            action_type=r.action_type,
            tool_name=(r.payload.get("tool_calls", [{}])[0].get("name", r.action_type) if isinstance(r.payload.get("tool_calls"), list) and r.payload.get("tool_calls") else r.action_type),
            severity=r.severity,
            reason=r.reason,
            payload=r.payload or {},
        )
        for r in pending_records
    ]

    risk_report = classify_batch_approval_risk(batch_items)

    # If approving and batch contains high risk actions, enforce dual insurance
    if normalized_decision == "approve" and risk_report.has_high_risk:
        if not req.confirm_high_risk and not req.safe_only:
            # Block batch approval and return 409 Conflict with structured risk detail
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "BATCH_HIGH_RISK_CONFIRMATION_REQUIRED",
                    "message": "Batch contains high-risk actions. Explicit confirmation or safe-only resolution is required.",
                    "has_high_risk": True,
                    "high_risk_count": risk_report.high_risk_count,
                    "safe_count": risk_report.safe_count,
                    "high_risk_items": [
                        {
                            "item_id": item.item_id,
                            "action_type": item.action_type,
                            "tool_name": item.tool_name,
                            "risk_level": item.risk_level.value,
                            "risk_reason": item.risk_reason,
                        }
                        for item in risk_report.high_risk_items
                    ],
                    "safe_item_ids": list(risk_report.safe_item_ids),
                },
            )

    # Determine which target approval IDs to resolve
    if normalized_decision == "approve" and req.safe_only:
        target_ids = list(risk_report.safe_item_ids)
    else:
        target_ids = req.approval_ids

    resolved_records = []

    for approval_id in target_ids:
        try:
            record = await ApprovalRegistry.resolve_approval(
                approval_id=approval_id,
                decision=normalized_decision,
            )
            if not record:
                continue

            resolved_records.append(record)

            if record.thread_id:
                try:
                    from app.services.event.app_event_bus import (
                        AppEvent,
                        AppEventType,
                        get_event_bus,
                    )

                    bus = get_event_bus()
                    bus.publish(
                        AppEvent(
                            event_type=AppEventType.APPROVAL_RESOLVED,
                            data={
                                "action": "resume_agent",
                                "approval_id": record.id,
                                "thread_id": record.thread_id,
                                "chat_id": record.chat_id,
                                "agent_id": record.agent_id,
                                "decision": normalized_decision,
                                "edited_payload": None,
                            },
                        )
                    )
                except Exception as e:
                    logger.error("Failed to resume agent for %s: %s", record.id, e)

            if record.chat_id:
                from app.services.agent.streaming_support.multiplexer import WorkspaceMultiplexer

                WorkspaceMultiplexer.get().publish_session_status(record.chat_id, "idle", "")
        except Exception as e:
            logger.error("Failed to batch resolve approval %s: %s", approval_id, e)

    return ApprovalListResponse(approvals=[ApprovalRecordResponse.from_orm(r) for r in resolved_records])


@router.post("/test/seed-mock", include_in_schema=False)
async def seed_test_mock_push_approval() -> dict[str, str]:
    """Local dev/test only: seed a chat + inline pending approval for push deeplink E2E."""
    from uuid import uuid4

    from app.config.deploy_mode import is_local_mode
    from app.database.dto import ChatCreate
    from app.services.chat.chat_service import ChatService

    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    chat_id = f"e2epush{uuid4().hex[:8]}"
    await ChatService.create_or_update_chat(
        ChatCreate(chat_id=chat_id, title="Push deeplink E2E", messages=[]),
    )
    record = await ApprovalRegistry.create_approval(
        agent_id="e2e-push-deeplink",
        action_type="delete_file",
        payload={"path": "/tmp/e2e-push-deeplink"},
        reason="Chrome E2E push approval deeplink",
        chat_id=chat_id,
        thread_id=f"e2e-thread-{uuid4().hex[:8]}",
    )
    push_url = f"/{chat_id}?approval={record.id}"
    return {
        "chat_id": chat_id,
        "approval_id": record.id,
        "push_url": push_url,
        "ui_url": push_url,
    }
