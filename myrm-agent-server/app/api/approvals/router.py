"""[INPUT]
- app.services.approvals.registry::ApprovalRegistry (POS: 统一的拦截审批注册与唤醒中枢)
- app.services.approvals.docket_service::DocketService (POS: 法律案卷包归档服务)
- myrm_agent_harness.agent.types::Command (POS: LangGraph Resume 原语)
- myrm_agent_harness.agent.security.jit_gate::JITDualVerificationGate (POS: 执行期防掉包与现势策略双重动态断言网关)
- myrm_agent_harness.api.security::rollback_workspace_snapshot (POS: 快照回滚底层核心)

[OUTPUT]
- /api/v1/approvals: 审批决策接口、法律案卷导出接口与快照回滚接口

[POS]
提供统一的审批决策接口。处理挂起任务的 approve/deny，在恢复底层 agent 执行瞬间前置执行 JIT 物理资产防篡改校验，并固化法律审计案卷。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status
from myrm_agent_harness.agent.file_snapshot.restore_inbox import push_restore_notification
from myrm_agent_harness.agent.security.jit_gate import (
    AssetContentFingerprint,
    AssetTamperedDuringApprovalError,
    AssetType,
    JITDualVerificationGate,
    PolicyTightenedAtJITError,
)
from myrm_agent_harness.api.security import rollback_workspace_snapshot
from pydantic import BaseModel

from app.api.approvals.batch import router as batch_router
from app.api.approvals.credentials import router as credentials_router
from app.api.approvals.test_routes import router as test_routes_router
from app.database.models.approval import ApprovalRecord
from app.services.approvals.audit_ledger import get_audit_ledger
from app.services.approvals.docket_service import DocketService
from app.services.approvals.registry import ApprovalRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/approvals", tags=["approvals"])
router.include_router(credentials_router)
router.include_router(test_routes_router)
router.include_router(batch_router)


async def _handle_knowledge_patch_resolution(record: ApprovalRecord, decision: str) -> None:
    """Delegate approved knowledge patch resolution to knowledge_patch module."""
    from app.api.approvals.knowledge_patch import handle_knowledge_patch_resolution

    await handle_knowledge_patch_resolution(record, decision)


class AllowAlwaysValue(BaseModel):
    tool: bool | None = None
    args: bool | None = None
    pattern: bool | None = None
    duration: str | None = None
    ttl_seconds: int | float | None = None


class ResolveApprovalRequest(BaseModel):
    decision: str  # "approve" | "deny" | "reject" (frontend alias)
    edited_payload: dict[str, object] | None = None
    comment: str | None = None
    allow_always: bool | str | AllowAlwaysValue | None = None
    ttl_seconds: int | float | None = None
    ephemeral_credential_handles: list[str] | None = None


class ApprovalRecordResponse(BaseModel):
    id: str
    action_type: str
    reason: str | None
    severity: str
    payload: dict[str, object]
    status: str
    created_at: str
    chat_id: str | None
    expires_at: str | None

    @classmethod
    def from_orm(cls, record: ApprovalRecord) -> ApprovalRecordResponse:
        return cls(
            id=record.id,
            action_type=record.action_type,
            reason=record.reason,
            severity=record.severity,
            payload=record.payload or {},
            status=record.status,
            created_at=record.created_at.isoformat() if record.created_at else "",
            chat_id=record.chat_id,
            expires_at=record.expires_at.isoformat() if record.expires_at else None,
        )


class ApprovalListResponse(BaseModel):
    approvals: list[ApprovalRecordResponse]


class ActiveGrantResponse(BaseModel):
    permission: str
    tool_name: str | None = None
    tool_args_hash: str | None = None
    command_pattern: str | None = None
    agent_id: str | None = None
    created_at: float
    expires_at: float | None = None


class ActiveGrantListResponse(BaseModel):
    grants: list[ActiveGrantResponse]


class RevokeGrantRequest(BaseModel):
    permission: str
    tool_name: str | None = None
    tool_args_hash: str | None = None
    command_pattern: str | None = None
    agent_id: str | None = None


class RollbackSnapshotRequest(BaseModel):
    workspace_path: str | None = None


@router.get("/grants", response_model=ActiveGrantListResponse)
async def list_active_grants(
    user_id: str = Query("sandbox", description="User identifier"),
) -> ActiveGrantListResponse:
    """List currently active time-bound and permanent permission grants."""
    from myrm_agent_harness.agent.security.approval_flow import get_allowlist

    allowlist = get_allowlist()
    entries = await allowlist.list_active_grants(user_id)
    return ActiveGrantListResponse(
        grants=[
            ActiveGrantResponse(
                permission=e.permission,
                tool_name=e.tool_name,
                tool_args_hash=e.tool_args_hash,
                command_pattern=e.command_pattern,
                agent_id=e.agent_id,
                created_at=e.created_at,
                expires_at=e.expires_at,
            )
            for e in entries
        ]
    )


@router.post("/grants/revoke")
async def revoke_active_grant(
    req: RevokeGrantRequest,
    user_id: str = Query("sandbox", description="User identifier"),
) -> dict[str, str]:
    """Revoke an active permission grant."""
    from myrm_agent_harness.agent.security.approval_flow import get_allowlist

    allowlist = get_allowlist()
    await allowlist.remove(
        user_id=user_id,
        permission=req.permission,
        tool_name=req.tool_name,
        tool_args_hash=req.tool_args_hash,
        command_pattern=req.command_pattern,
        agent_id=req.agent_id,
    )
    return {"status": "ok", "message": "Grant revoked"}


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
    """Resolve an approval and resume the agent (if applicable), enforcing JIT dual assertions."""
    normalized_decision = "approve" if req.decision == "approve" else "deny"

    # Fetch pending record to assert physical integrity before committing state transition
    existing_record = await ApprovalRegistry.get_approval(approval_id)
    if not existing_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")

    # JIT Dual Verification Gate Assertion: Prevent TOCTOU asset tampering before approval resolution
    if normalized_decision == "approve" and isinstance(existing_record.payload, dict):
        fingerprint_data = existing_record.payload.get("content_fingerprint")
        if isinstance(fingerprint_data, dict):
            try:
                fingerprint = AssetContentFingerprint.from_dict(fingerprint_data)
                target_path = Path(fingerprint.asset_identifier) if fingerprint.asset_type == AssetType.FILE else None
                JITDualVerificationGate.assert_jit_dual_verification(
                    fingerprint=fingerprint,
                    target_path=target_path,
                    is_policy_allowed=True,
                )
            except AssetTamperedDuringApprovalError as exc:
                logger.warning(
                    "[JIT_GATE] TOCTOU asset tampering detected for approval %s: %s",
                    approval_id,
                    exc,
                )
                await ApprovalRegistry.resolve_approval(
                    approval_id=approval_id,
                    decision="deny",
                    edited_payload={"tampered_error": str(exc)},
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": "ASSET_TAMPERED_DURING_APPROVAL",
                        "message": str(exc),
                        "asset_identifier": exc.asset_identifier,
                        "expected_sha256": exc.expected_sha256,
                        "current_sha256": exc.current_sha256,
                    },
                ) from exc
            except PolicyTightenedAtJITError as exc:
                logger.warning(
                    "[JIT_GATE] Policy tightened assertion failed for approval %s: %s",
                    approval_id,
                    exc,
                )
                await ApprovalRegistry.resolve_approval(
                    approval_id=approval_id,
                    decision="deny",
                    edited_payload={"policy_error": str(exc)},
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": "POLICY_TIGHTENED_AT_JIT",
                        "message": str(exc),
                        "action_identifier": exc.action_identifier,
                    },
                ) from exc

    record = await ApprovalRegistry.resolve_approval(
        approval_id=approval_id,
        decision=normalized_decision,
        edited_payload=req.edited_payload,
    )

    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")

    # If approved, seal immutable legal audit docket for non-repudiation compliance
    if normalized_decision == "approve":
        try:
            await DocketService.create_docket_for_approval(record)
        except Exception as exc:
            logger.warning("[APPROVAL_ROUTER] Failed to seal legal audit docket for %s: %s", approval_id, exc)

    if normalized_decision == "deny" and req.ephemeral_credential_handles:
        try:
            from myrm_agent_harness.api import get_ephemeral_credential_store

            store = get_ephemeral_credential_store()
            session_id = record.chat_id or "default"
            wiped = store.wipe_handles(session_id, req.ephemeral_credential_handles)
            logger.info(
                "[APPROVAL_ROUTER] Wiped %d ephemeral credential handles upon denial for approval %s (session %s)",
                wiped,
                approval_id,
                session_id,
            )
        except Exception as e:
            logger.warning("[APPROVAL_ROUTER] Failed to wipe handles on denial: %s", e)

    if record.action_type == "outbound_draft":
        # Resolving it already sent or released the held reply, and no agent run waits on it.
        return ApprovalRecordResponse.from_orm(record)

    if record.action_type == "knowledge_patch":
        await _handle_knowledge_patch_resolution(record, normalized_decision)
        return ApprovalRecordResponse.from_orm(record)

    if record.action_type == "mcp_elicitation":
        from app.services.agent.backends.mcp_elicitation_handler import resolve_pending_elicitation

        resolved = resolve_pending_elicitation(approval_id, normalized_decision)
        if not resolved:
            logger.warning(
                "MCP elicitation %s not found in pending map (may have timed out)",
                approval_id,
            )
        return ApprovalRecordResponse.from_orm(record)

    # If it's a LangGraph interrupt, resume the agent
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

            payload = record.payload or {}
            review_configs = payload.get("reviewConfigs", [])
            is_destructive = payload.get("irreversibleDestructive") is True or (
                isinstance(review_configs, list)
                and any(isinstance(cfg, dict) and cfg.get("irreversibleDestructive") is True for cfg in review_configs)
            )
            effective_allow_always = None if is_destructive else req.allow_always
            if is_destructive and req.allow_always:
                logger.warning(
                    "[APPROVAL_ROUTER] Suppressed allow_always for irreversible destructive approval %s",
                    record.id,
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
                        "allow_always": effective_allow_always,
                        "ttl_seconds": req.ttl_seconds,
                        "edited_payload": req.edited_payload,
                        "ephemeral_credential_handles": req.ephemeral_credential_handles,
                    },
                )
            )
        except Exception as e:
            logger.error("Failed to resume agent: %s", e)

    if record.chat_id:
        from app.services.agent.streaming_support.multiplexer import (
            WorkspaceMultiplexer,
        )

        WorkspaceMultiplexer.get().publish_session_status(record.chat_id, "idle", "")

    return ApprovalRecordResponse.from_orm(record)


@router.post("/{approval_id}/rollback")
async def rollback_approval_snapshot(
    approval_id: str,
    req: RollbackSnapshotRequest | None = None,
) -> dict[str, object]:
    """Rollback the workspace state to the pre-destructive snapshot captured for this approval."""
    record = await ApprovalRegistry.get_approval(approval_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")

    if record.created_at:
        now = datetime.now(timezone.utc)
        record_time = record.created_at
        if record_time.tzinfo is None:
            record_time = record_time.replace(tzinfo=timezone.utc)
        elapsed_seconds = (now - record_time).total_seconds()
        if elapsed_seconds > 600.0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Rollback window has expired ({elapsed_seconds:.0f}s elapsed, maximum allowed is 600s)",
            )

    payload = record.payload or {}
    snapshot_id = payload.get("snapshotId") or payload.get("snapshot_id")
    if not snapshot_id:
        review_configs = payload.get("reviewConfigs", [])
        if isinstance(review_configs, list):
            for cfg in review_configs:
                if isinstance(cfg, dict) and cfg.get("snapshotId"):
                    snapshot_id = cfg["snapshotId"]
                    break

    if not snapshot_id or not isinstance(snapshot_id, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No workspace snapshot ID associated with this approval",
        )

    wpath = Path(req.workspace_path).resolve() if (req and req.workspace_path) else Path.cwd()
    success = rollback_workspace_snapshot(wpath, snapshot_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rollback workspace snapshot",
        )

    # 1. Inform Agent via restore_inbox to align context and prevent hallucinations
    try:
        push_restore_notification(snapshot_id=snapshot_id, files_restored=1)
    except Exception as exc:
        logger.warning("Failed to push restore notification to restore_inbox: %s", exc)

    # 2. Record tamper-evident audit receipt in the legal ledger
    receipt_id: str | None = None
    try:
        ledger = get_audit_ledger()
        receipt = await ledger.record_action(
            action_type="WORKSPACE_PHYSICAL_ROLLBACK",
            action_command=f"rollback_snapshot:{snapshot_id}",
            target_assets=[str(wpath)],
            operator_id=record.agent_id or "user",
            snapshot_ref=snapshot_id,
            metadata={"approval_id": approval_id},
        )
        receipt_id = receipt.receipt_id
    except Exception as exc:
        logger.warning("Failed to record audit receipt for rollback %s: %s", approval_id, exc)

    return {
        "ok": True,
        "approval_id": approval_id,
        "snapshot_id": snapshot_id,
        "receipt_id": receipt_id,
        "message": "Workspace successfully rolled back to pre-destructive state",
    }
