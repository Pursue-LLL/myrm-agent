"""
[INPUT]: Enterprise credit transactions, actor identities, data scopes, and quota configurations.
[OUTPUT]: EnterpriseCockpitResponse, audit trails, and REST endpoints for enterprise credit and risk ops.
[POS]: myrm-agent/myrm-agent-server/app/api/system/enterprise_credit_cockpit_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.enterprise_credit_cockpit import (
    CreditPoolAllocation,
    CreditRiskAuditRecord,
    EnterpriseCockpitSnapshot,
    PolicyVerdict,
    RiskBehaviorType,
    RiskLevel,
    get_default_credit_risk_ledger,
)

router = APIRouter(prefix="/enterprise-credit", tags=["enterprise-credit"])


# --- Pydantic Request & Response Schemas ---

class ConfigureQuotaRequest(BaseModel):
    total_quota: float = Field(..., ge=1.0, description="Total enterprise credit quota")
    warning_threshold_pct: float = Field(default=80.0, ge=1.0, le=100.0, description="Soft warning threshold percentage")


class RecordTransactionRequest(BaseModel):
    actor_id: str = Field(..., description="Employee, user, or agent identifier")
    product_surface: str = Field(..., description="Surface: webui, desktop, cloud_sandbox, mobile")
    interaction_summary: str = Field(..., description="Redacted summary of interaction")
    data_object_scope: str = Field(..., description="Target data domain or object scope")
    credit_consumed: float = Field(..., ge=0.0, description="Credit points burned")
    risk_level: str = Field(default="NONE", description="NONE, LOW, MEDIUM, HIGH, CRITICAL")
    risk_behavior: str = Field(default="NONE", description="Categorized risk behavior")
    policy_verdict: str = Field(default="ALLOW", description="ALLOW, AUDIT, BLOCKED")


class CreditRiskAuditRecordModel(BaseModel):
    record_id: str
    actor_id: str
    product_surface: str
    interaction_summary: str
    data_object_scope: str
    credit_consumed: float
    risk_level: str
    risk_behavior: str
    policy_verdict: str
    timestamp_ms: int


class CreditPoolAllocationModel(BaseModel):
    surface_name: str
    credit_spent: float
    request_count: int


class EnterpriseCockpitResponse(BaseModel):
    total_credit_quota: float
    total_credit_spent: float
    available_credit: float
    utilization_pct: float
    is_quota_breached: bool
    warning_threshold_pct: float
    total_audit_records: int
    risk_event_count: int
    blocked_count: int
    allocations_by_surface: List[CreditPoolAllocationModel]
    recent_audit_records: List[CreditRiskAuditRecordModel]


class AuditTrailQueryResponse(BaseModel):
    records: List[CreditRiskAuditRecordModel]
    total_matched: int


# --- Helper Converters ---

def _to_record_model(record: CreditRiskAuditRecord) -> CreditRiskAuditRecordModel:
    return CreditRiskAuditRecordModel(
        record_id=record.record_id,
        actor_id=record.actor_id,
        product_surface=record.product_surface,
        interaction_summary=record.interaction_summary,
        data_object_scope=record.data_object_scope,
        credit_consumed=record.credit_consumed,
        risk_level=record.risk_level.value,
        risk_behavior=record.risk_behavior.value,
        policy_verdict=record.policy_verdict.value,
        timestamp_ms=record.timestamp_ms,
    )


def _to_allocation_model(alloc: CreditPoolAllocation) -> CreditPoolAllocationModel:
    return CreditPoolAllocationModel(
        surface_name=alloc.surface_name,
        credit_spent=alloc.credit_spent,
        request_count=alloc.request_count,
    )


def _to_cockpit_response(snapshot: EnterpriseCockpitSnapshot) -> EnterpriseCockpitResponse:
    return EnterpriseCockpitResponse(
        total_credit_quota=snapshot.total_credit_quota,
        total_credit_spent=snapshot.total_credit_spent,
        available_credit=snapshot.available_credit,
        utilization_pct=snapshot.utilization_pct,
        is_quota_breached=snapshot.is_quota_breached,
        warning_threshold_pct=snapshot.warning_threshold_pct,
        total_audit_records=snapshot.total_audit_records,
        risk_event_count=snapshot.risk_event_count,
        blocked_count=snapshot.blocked_count,
        allocations_by_surface=[_to_allocation_model(a) for a in snapshot.allocations_by_surface],
        recent_audit_records=[_to_record_model(r) for r in snapshot.recent_audit_records],
    )


# --- Endpoints ---

@router.get("/cockpit", response_model=EnterpriseCockpitResponse)
async def get_cockpit() -> EnterpriseCockpitResponse:
    """Retrieve full cockpit status of enterprise credit quota and risk ops."""
    ledger = get_default_credit_risk_ledger()
    snapshot = ledger.get_cockpit_snapshot()
    return _to_cockpit_response(snapshot)


@router.post("/record", response_model=CreditRiskAuditRecordModel)
async def record_transaction(req: RecordTransactionRequest) -> CreditRiskAuditRecordModel:
    """Record a credit transaction linked with actor identity, data scope, and risk evaluation."""
    ledger = get_default_credit_risk_ledger()
    record = ledger.record_transaction(
        actor_id=req.actor_id,
        product_surface=req.product_surface,
        interaction_summary=req.interaction_summary,
        data_object_scope=req.data_object_scope,
        credit_consumed=req.credit_consumed,
        risk_level=req.risk_level,
        risk_behavior=req.risk_behavior,
        policy_verdict=req.policy_verdict,
    )
    return _to_record_model(record)


@router.post("/configure-quota")
async def configure_quota(req: ConfigureQuotaRequest) -> Dict[str, bool]:
    """Configure enterprise-level credit quota and soft warning threshold."""
    ledger = get_default_credit_risk_ledger()
    ledger.configure_quota(
        total_quota=req.total_quota,
        warning_threshold_pct=req.warning_threshold_pct,
    )
    return {"ok": True}


@router.get("/audit-trail", response_model=AuditTrailQueryResponse)
async def get_audit_trail(
    actor_id: Optional[str] = Query(default=None, description="Filter by actor identifier"),
    risk_level: Optional[str] = Query(default=None, description="Filter by risk level"),
    surface: Optional[str] = Query(default=None, description="Filter by surface"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum records to return"),
) -> AuditTrailQueryResponse:
    """Query unified audit trail with multi-dimensional filtering."""
    ledger = get_default_credit_risk_ledger()
    records = ledger.filter_audit_records(
        actor_id=actor_id,
        risk_level=risk_level,
        surface=surface,
        limit=limit,
    )
    return AuditTrailQueryResponse(
        records=[_to_record_model(r) for r in records],
        total_matched=len(records),
    )


@router.post("/reset")
async def reset_ledger() -> Dict[str, bool]:
    """Reset credit counters and audit history (for test and maintenance)."""
    ledger = get_default_credit_risk_ledger()
    ledger.reset()
    return {"ok": True}
