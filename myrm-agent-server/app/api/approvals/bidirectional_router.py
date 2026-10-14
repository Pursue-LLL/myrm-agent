"""[INPUT]
StructuredApprovalDecision, StructuredApprovalRequest, ApprovalAck from app.services.approvals.bidirectional.protocol_types
[OUTPUT]
FastAPI router for bidirectional structured approvals, diff review, and client decision ACK.
[POS]
app/api/approvals/bidirectional_router.py
"""

from typing import Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.services.approvals.bidirectional.protocol_types import (
    ApprovalAck,
    StructuredApprovalDecision,
    StructuredApprovalRequest,
)
from app.services.approvals.bidirectional.bidirectional_approval_service import (
    BidirectionalApprovalService,
)

router = APIRouter(prefix="/bidirectional", tags=["bidirectional-approvals"])

_approval_service = BidirectionalApprovalService()


class CreateFileDiffApprovalPayload(BaseModel):
    session_id: str = Field(description="Active session ID")
    file_path: str = Field(description="Target file path")
    new_content: str = Field(description="New file content")
    old_content: Optional[str] = Field(default=None, description="Previous file content if any")
    summary: Optional[str] = Field(default=None, description="Action summary")
    timeout_seconds: Optional[float] = Field(default=300.0, description="Expiration TTL")


class CreateCommandApprovalPayload(BaseModel):
    session_id: str = Field(description="Active session ID")
    command: str = Field(description="Command string to execute")
    cwd: str = Field(description="Working directory")
    summary: Optional[str] = Field(default=None, description="Action summary")
    timeout_seconds: Optional[float] = Field(default=300.0, description="Expiration TTL")


@router.post("/file-diff-request", response_model=StructuredApprovalRequest)
def create_file_diff_request(
    payload: CreateFileDiffApprovalPayload,
) -> StructuredApprovalRequest:
    """Create a structured approval request for file modification with computed diff."""
    return _approval_service.create_file_write_approval(
        session_id=payload.session_id,
        file_path=payload.file_path,
        new_content=payload.new_content,
        old_content=payload.old_content,
        summary=payload.summary,
        timeout_seconds=payload.timeout_seconds,
    )


@router.post("/command-request", response_model=StructuredApprovalRequest)
def create_command_request(
    payload: CreateCommandApprovalPayload,
) -> StructuredApprovalRequest:
    """Create a structured approval request for shell command with risk radar analysis."""
    return _approval_service.create_command_approval(
        session_id=payload.session_id,
        command=payload.command,
        cwd=payload.cwd,
        summary=payload.summary,
        timeout_seconds=payload.timeout_seconds,
    )


@router.post("/decide", response_model=ApprovalAck)
def submit_approval_decision(
    decision: StructuredApprovalDecision,
) -> ApprovalAck:
    """Submit client decision (allow, reject, remember_session) and retrieve server ACK."""
    return _approval_service.record_decision(decision)


@router.get("/pending", response_model=list[StructuredApprovalRequest])
def list_pending_approvals(
    session_id: Optional[str] = Query(None, description="Optional session filter"),
) -> list[StructuredApprovalRequest]:
    """Retrieve all pending structured approvals awaiting client review."""
    return _approval_service.list_pending_requests(session_id=session_id)
