"""Tainted Egress Human-In-The-Loop Approval and Session Trust API.

[INPUT]
- pydantic::BaseModel, Field (POS: 声明请求与响应数据契约)
- fastapi::APIRouter, HTTPException, Query, status (POS: REST 路由定义与异常处理)
- threading::RLock (POS: 线程安全锁)
- time::time (POS: 时间戳计算)

[OUTPUT]
- TaintedEgressApprovalRequest: 放行审批请求模型
- TaintedEgressRejectRequest: 拒绝审批请求模型
- TaintedEgressDecisionResponse: 审批裁决响应模型
- PendingTaintedEgressItem: 待审批拦截项模型
- PendingTaintedEgressListResponse: 待审批列表响应
- TaintedEgressApprovalManager: 内存审批流与会话信任管理服务
- get_tainted_egress_manager: 单例获取器
- router: FastAPI 路由定义

[POS]
Server-level security approval API. Intercepts tainted socket egress events,
presenting clear modal approvals to the user and supporting session-level host trust
to eliminate alert fatigue while maintaining cryptographic and transport safety.
"""

from __future__ import annotations

import logging
import threading
import time

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TaintedEgressApprovalRequest(BaseModel):
    """Payload for approving an intercepted tainted outbound egress request."""

    request_id: str = Field(..., description="Unique intercepted request identifier")
    destination_host: str = Field(..., description="Target destination hostname or IP")
    session_id: str | None = Field(default=None, description="Optional agent session identifier")
    trust_session: bool = Field(
        default=False,
        description="Whether to trust this destination host for the remainder of this session",
    )


class TaintedEgressRejectRequest(BaseModel):
    """Payload for rejecting an intercepted tainted outbound egress request."""

    request_id: str = Field(..., description="Unique intercepted request identifier")
    session_id: str | None = Field(default=None, description="Optional agent session identifier")
    reason: str = Field(default="user_declined", description="Rejection rationale")


class TaintedEgressDecisionResponse(BaseModel):
    """Response payload detailing the outcome of the egress approval decision."""

    request_id: str
    approved: bool
    destination_host: str
    session_trusted: bool
    message: str


class PendingTaintedEgressItem(BaseModel):
    """A currently intercepted pending tainted egress transmission."""

    request_id: str
    session_id: str
    destination_host: str
    destination_port: int = 443
    sensitive_data_type: str = "credential"
    detected_pattern: str = ""
    timestamp: float = Field(default_factory=time.time)


class PendingTaintedEgressListResponse(BaseModel):
    """List of all currently pending egress interception events."""

    items: list[PendingTaintedEgressItem]
    total: int


class TaintedEgressApprovalManager:
    """Thread-safe manager for pending tainted egress events and session host trust."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._pending: dict[str, PendingTaintedEgressItem] = {}
        self._session_trusted_hosts: dict[str, set[str]] = {}

    def register_pending(self, item: PendingTaintedEgressItem) -> None:
        """Register a new intercepted transmission needing human authorization."""
        with self._lock:
            self._pending[item.request_id] = item
            logger.info(
                "Registered pending tainted egress interception: req_id=%s host=%s session=%s",
                item.request_id,
                item.destination_host,
                item.session_id,
            )

    def is_host_trusted_in_session(self, session_id: str, destination_host: str) -> bool:
        """Check whether a host is pre-authorized within a specific session scope."""
        if not session_id or not destination_host:
            return False
        with self._lock:
            trusted_hosts = self._session_trusted_hosts.get(session_id, set())
            clean_host = destination_host.lower().strip()
            return clean_host in trusted_hosts

    def approve(
        self,
        request_id: str,
        destination_host: str,
        session_id: str | None = None,
        trust_session: bool = False,
    ) -> TaintedEgressDecisionResponse:
        """Authorize an intercepted transmission, optionally recording session trust."""
        with self._lock:
            self._pending.pop(request_id, None)
            clean_host = destination_host.lower().strip()
            session_trusted = False

            if trust_session and session_id:
                if session_id not in self._session_trusted_hosts:
                    self._session_trusted_hosts[session_id] = set()
                self._session_trusted_hosts[session_id].add(clean_host)
                session_trusted = True
                logger.info(
                    "Granted session-level egress trust: session=%s host=%s",
                    session_id,
                    clean_host,
                )

            return TaintedEgressDecisionResponse(
                request_id=request_id,
                approved=True,
                destination_host=clean_host,
                session_trusted=session_trusted,
                message="Tainted egress approved by user",
            )

    def reject(
        self,
        request_id: str,
        session_id: str | None = None,
        reason: str = "user_declined",
    ) -> TaintedEgressDecisionResponse:
        """Deny an intercepted transmission and remove from pending queue."""
        with self._lock:
            pending_item = self._pending.pop(request_id, None)
            host = pending_item.destination_host if pending_item else "unknown"
            logger.warning(
                "Tainted egress denied by user: req_id=%s host=%s reason=%s session=%s",
                request_id,
                host,
                reason,
                session_id,
            )
            return TaintedEgressDecisionResponse(
                request_id=request_id,
                approved=False,
                destination_host=host,
                session_trusted=False,
                message=f"Tainted egress rejected: {reason}",
            )

    def list_pending(self, session_id: str | None = None) -> list[PendingTaintedEgressItem]:
        """List all pending intercepted items, optionally filtered by session."""
        with self._lock:
            if session_id:
                return [item for item in self._pending.values() if item.session_id == session_id]
            return list(self._pending.values())

    def clear_session_trust(self, session_id: str) -> None:
        """Clear all session-level trust grants when a session terminates."""
        with self._lock:
            self._session_trusted_hosts.pop(session_id, None)


_GLOBAL_TAINTED_EGRESS_MANAGER = TaintedEgressApprovalManager()


def get_tainted_egress_manager() -> TaintedEgressApprovalManager:
    """Obtain the process-wide tainted egress approval manager."""
    return _GLOBAL_TAINTED_EGRESS_MANAGER


router = APIRouter(prefix="/tainted-egress", tags=["security"])


@router.post("/approve", response_model=TaintedEgressDecisionResponse)
async def approve_tainted_egress(
    payload: TaintedEgressApprovalRequest,
) -> TaintedEgressDecisionResponse:
    """Approve an intercepted tainted egress connection, optionally enabling session trust."""
    manager = get_tainted_egress_manager()
    return manager.approve(
        request_id=payload.request_id,
        destination_host=payload.destination_host,
        session_id=payload.session_id,
        trust_session=payload.trust_session,
    )


@router.post("/reject", response_model=TaintedEgressDecisionResponse)
async def reject_tainted_egress(
    payload: TaintedEgressRejectRequest,
) -> TaintedEgressDecisionResponse:
    """Reject and block an intercepted tainted egress connection."""
    manager = get_tainted_egress_manager()
    return manager.reject(
        request_id=payload.request_id,
        session_id=payload.session_id,
        reason=payload.reason,
    )


@router.get("/pending", response_model=PendingTaintedEgressListResponse)
async def get_pending_tainted_egress(
    session_id: str | None = Query(default=None, description="Filter by session ID"),
) -> PendingTaintedEgressListResponse:
    """Retrieve all pending tainted egress requests awaiting human approval."""
    manager = get_tainted_egress_manager()
    items = manager.list_pending(session_id=session_id)
    return PendingTaintedEgressListResponse(items=items, total=len(items))


@router.delete("/trust/{session_id}")
async def clear_session_trust(session_id: str) -> dict[str, str]:
    """Revoke all trusted outbound hosts for a given session."""
    manager = get_tainted_egress_manager()
    manager.clear_session_trust(session_id)
    return {"status": "ok", "message": f"Trust cleared for session {session_id}"}
