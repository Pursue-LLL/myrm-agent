"""[INPUT]
- app.services.approvals.registry::ApprovalRegistry (POS: 统一审批存储与查询)
- myrm_agent_harness.agent.security.batch_risk::classify_batch_approval_risk (POS: 批量风控分类引擎)

[OUTPUT]
- POST /approvals/batch-resolve: 批量审批决策路由（含双保险高危拦截）

[POS]
提供批量审批决策接口，与单审批路由解耦以满足单一职责和代码行数规范。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from myrm_agent_harness.agent.security.batch_risk import (
    BatchApprovalItem,
    classify_batch_approval_risk,
)
from pydantic import BaseModel

from app.database.models.approval import ApprovalRecord
from app.services.approvals.registry import ApprovalRegistry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["approvals-batch"])


class BatchResolveApprovalRequest(BaseModel):
    approval_ids: list[str]
    decision: str  # "approve" | "deny"
    confirm_high_risk: bool = False
    safe_only: bool = False


class BatchApprovalRecordItem(BaseModel):
    id: str
    action_type: str
    status: str
    severity: str
    reason: str | None


class BatchApprovalListResponse(BaseModel):
    approvals: list[BatchApprovalRecordItem]


@router.post("/batch-resolve", response_model=BatchApprovalListResponse)
async def batch_resolve_approvals(
    req: BatchResolveApprovalRequest,
) -> BatchApprovalListResponse:
    """Batch resolve multiple approvals and resume the agents with dual-insurance high-risk protection."""
    if not req.approval_ids:
        return BatchApprovalListResponse(approvals=[])

    normalized_decision = "approve" if req.decision == "approve" else "deny"

    # Pre-fetch records to evaluate batch risk
    pending_records: list[ApprovalRecord] = []
    for approval_id in req.approval_ids:
        record = await ApprovalRegistry.get_approval(approval_id)
        if record and record.status == "PENDING":
            pending_records.append(record)

    if not pending_records:
        return BatchApprovalListResponse(approvals=[])

    # Convert to BatchApprovalItem contract
    batch_items = [
        BatchApprovalItem(
            item_id=r.id,
            action_type=r.action_type,
            tool_name=(
                r.payload.get("tool_calls", [{}])[0].get("name", r.action_type)
                if isinstance(r.payload.get("tool_calls"), list) and r.payload.get("tool_calls")
                else r.action_type
            ),
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
        if risk_report.safe_count == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "NO_SAFE_ITEMS_TO_APPROVE",
                    "message": "All items in the batch are high-risk. Cannot resolve safe-only batch without explicit confirmation.",
                    "has_high_risk": True,
                    "high_risk_count": risk_report.high_risk_count,
                    "safe_count": 0,
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
                    "safe_item_ids": [],
                },
            )
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

            if record.action_type == "knowledge_patch":
                from app.api.approvals.knowledge_patch import handle_knowledge_patch_resolution

                await handle_knowledge_patch_resolution(record, normalized_decision)

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
                from app.services.agent.streaming_support.multiplexer import (
                    WorkspaceMultiplexer,
                )

                WorkspaceMultiplexer.get().publish_session_status(record.chat_id, "idle", "")
        except Exception as e:
            logger.error("Failed to batch resolve approval %s: %s", approval_id, e)

    return BatchApprovalListResponse(
        approvals=[
            BatchApprovalRecordItem(
                id=r.id,
                action_type=r.action_type,
                status=r.status,
                severity=r.severity,
                reason=r.reason,
            )
            for r in resolved_records
        ]
    )
