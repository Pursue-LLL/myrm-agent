"""
[INPUT]: Raw resource access recordings, timeline step payloads, and session IDs.
[OUTPUT]: REST API endpoints for lie-immune in-conversation audit theater and resource-level data access ledger.
[POS]: myrm-agent/myrm-agent-server/app/api/system/audit_theater_api.py
"""

from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.audit_theater import (
    DataAccessLedgerBuilder,
    ResourceAccessEntry,
    ResourceAccessKind,
    ResourceAccessMode,
    SessionDataAccessLedger,
    TimelineAuditEvent,
)

router = APIRouter(prefix="/audit-theater", tags=["audit-theater"])

_default_builder = DataAccessLedgerBuilder()


def get_default_ledger_builder() -> DataAccessLedgerBuilder:
    return _default_builder


# --- Request & Response Models ---


class RecordResourceAccessRequest(BaseModel):
    session_id: str = Field(..., description="Chat session ID")
    resource_id: str = Field(..., description="File path, memory query, MCP URI, or web domain")
    kind: str = Field(..., description="file | memory | connector_mcp | web_network")
    mode: str = Field(default="read", description="read | write | execute")
    scope_detail: str = Field(default="", description="Granular scope: e.g. 'lines 1-120'")
    size_bytes: int = Field(default=0, ge=0)
    line_count: int = Field(default=0, ge=0)
    success: bool = Field(default=True)


class RecordTimelineEventRequest(BaseModel):
    session_id: str = Field(...)
    step_name: str = Field(...)
    tool_name: str = Field(...)
    is_plan: bool = Field(default=False)
    status: str = Field(default="completed")
    duration_ms: int = Field(default=0, ge=0)
    inputs_summary: str = Field(default="")


# --- Endpoints ---


@router.post("/record-access")
def record_resource_access(req: RecordResourceAccessRequest) -> Dict[str, str]:
    """Record an authoritative low-level data access event directly from backend execution."""
    try:
        kind_enum = ResourceAccessKind(req.kind.lower())
    except ValueError:
        kind_enum = ResourceAccessKind.FILE

    try:
        mode_enum = ResourceAccessMode(req.mode.lower())
    except ValueError:
        mode_enum = ResourceAccessMode.READ

    builder = get_default_ledger_builder()
    entry = builder.record_resource_access(
        session_id=req.session_id,
        resource_id=req.resource_id,
        kind=kind_enum,
        mode=mode_enum,
        scope_detail=req.scope_detail,
        size_bytes=req.size_bytes,
        line_count=req.line_count,
        success=req.success,
    )
    return {"status": "recorded", "entry_id": entry.entry_id}


@router.post("/record-event")
def record_timeline_event(req: RecordTimelineEventRequest) -> Dict[str, str]:
    """Record an in-conversation audit event (executed action or declared forward plan)."""
    builder = get_default_ledger_builder()
    evt = builder.record_timeline_event(
        session_id=req.session_id,
        step_name=req.step_name,
        tool_name=req.tool_name,
        is_plan=req.is_plan,
        status=req.status,
        duration_ms=req.duration_ms,
        inputs_summary=req.inputs_summary,
    )
    return {"status": "recorded", "event_id": evt.event_id}


@router.get("/ledger/{session_id}")
def get_session_ledger(session_id: str) -> Dict[str, object]:
    """Retrieve full lie-immune data access ledger and timeline certified with SHA-256 digest."""
    builder = get_default_ledger_builder()
    ledger: SessionDataAccessLedger = builder.build_session_ledger(session_id)
    return ledger.model_dump()


@router.post("/reset")
def reset_audit_builder() -> Dict[str, str]:
    """Reset builder buffers for isolated test execution."""
    builder = get_default_ledger_builder()
    builder.reset()
    return {"status": "reset"}
