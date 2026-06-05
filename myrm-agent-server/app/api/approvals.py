"""
[INPUT]
- app.services.approvals.registry::ApprovalRegistry (POS: 统一的拦截审批注册与唤醒中枢)
- myrm_agent_harness.agent.types::Command (POS: LangGraph Resume 原语)

[OUTPUT]
- /api/v1/approvals: 审批接口

[POS]
提供统一的审批决策接口。处理挂起任务的 approve/deny，恢复底层 agent 执行。
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.services.approvals.registry import ApprovalRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/approvals", tags=["approvals"])


class ResolveApprovalRequest(BaseModel):
    decision: str  # "approve" | "deny"
    edited_payload: dict[str, Any] | None = None


class BatchResolveApprovalRequest(BaseModel):
    approval_ids: list[str]
    decision: str  # "approve" | "deny"


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

    record = await ApprovalRegistry.resolve_approval(
        approval_id=approval_id,
        decision=req.decision,
        edited_payload=req.edited_payload,
    )

    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")

    # If it's a LangGraph interrupt, we must resume the agent!
    if record.thread_id:
        from app.services.agent.manager import get_agent_manager

        agent_manager = get_agent_manager()
        agent = await agent_manager.get_agent_instance(record.agent_id)
        if not agent:
            logger.error(
                "Cannot resume thread_id=%s: agent=%s not found",
                record.thread_id,
                record.agent_id,
            )
        else:
            try:
                # Emit the command to the agent stream asynchronously.
                # Actually, the API shouldn't block waiting for the stream to finish.
                # In our Server architecture, streaming endpoints handle Agent.run().
                # We need to dispatch this to a background task or push it to the streaming session queue.
                logger.info(
                    "Resuming agent thread_id=%s with decision=%s",
                    record.thread_id,
                    req.decision,
                )

                # ... the actual run will be picked up by the chat service or background worker
                # In myrm_agent_harness, Command(resume=...) is passed to `agent.run()`.
                # We can fire an event to the chat stream.
                from app.services.event.app_event_bus import (
                    AppEvent,
                    AppEventType,
                    get_event_bus,
                )

                bus = get_event_bus()
                bus.publish(
                    AppEvent(
                        event_type=AppEventType.APPROVAL_RESOLVED,  # Signal to chat router to resume
                        data={
                            "action": "resume_agent",
                            "approval_id": record.id,
                            "thread_id": record.thread_id,
                            "chat_id": record.chat_id,
                            "agent_id": record.agent_id,
                            "decision": req.decision,
                            "edited_payload": req.edited_payload,
                        },
                    )
                )
            except Exception as e:
                logger.error("Failed to resume agent: %s", e)

    return ApprovalRecordResponse.from_orm(record)


@router.post("/batch-resolve")
async def batch_resolve_approvals(
    req: BatchResolveApprovalRequest,
) -> ApprovalListResponse:
    """Batch resolve multiple approvals and resume the agents."""
    resolved_records = []

    for approval_id in req.approval_ids:
        try:
            record = await ApprovalRegistry.resolve_approval(
                approval_id=approval_id,
                decision=req.decision,
            )
            if not record:
                continue

            resolved_records.append(record)

            if record.thread_id:
                from app.services.agent.manager import get_agent_manager

                agent_manager = get_agent_manager()
                agent = await agent_manager.get_agent_instance(record.agent_id)
                if not agent:
                    logger.error(
                        "Cannot resume thread_id=%s: agent=%s not found",
                        record.thread_id,
                        record.agent_id,
                    )
                else:
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
                                "decision": req.decision,
                                "edited_payload": None,
                            },
                        )
                    )
        except Exception as e:
            logger.error("Failed to batch resolve approval %s: %s", approval_id, e)

    return ApprovalListResponse(approvals=[ApprovalRecordResponse.from_orm(r) for r in resolved_records])
