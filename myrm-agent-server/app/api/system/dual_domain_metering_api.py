"""
[INPUT]: Dual-domain metering records, session summary queries, and reconciliation requests.
[OUTPUT]: Pydantic schemas and REST endpoints for dual-domain metering and 3D penetrating cost attribution.
[POS]: myrm-agent/myrm-agent-server/app/api/system/dual_domain_metering_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.dual_domain_metering import (
    DomainMeteringRecord,
    MeteringDomain,
    ReconciliationStatement,
    SessionDualDomainSummary,
    ThreeDimensionalCost,
    get_default_dual_domain_ledger,
)

router = APIRouter(prefix="/dual-domain-metering", tags=["dual-domain-metering"])


# --- Schemas ---


class ThreeDimensionalCostModel(BaseModel):
    model_token_cost_usd: float = Field(default=0.0, ge=0.0)
    sandbox_compute_cost_usd: float = Field(default=0.0, ge=0.0)
    thirdparty_tool_cost_usd: float = Field(default=0.0, ge=0.0)
    total_cost_usd: float = Field(default=0.0, ge=0.0)


class RecordMeteringRequest(BaseModel):
    session_id: str = Field(..., description="Target session identifier")
    domain: str = Field(..., description="gateway_domain or sandbox_domain")
    operation_name: str = Field(..., description="Action/operation name")
    resource_units: float = Field(..., ge=0.0, description="Tokens, seconds or requests")
    cost_breakdown: ThreeDimensionalCostModel
    billable: bool = Field(default=True)
    policy_note: str = Field(default="")
    custom_record_id: Optional[str] = Field(default=None)


class DomainMeteringRecordModel(BaseModel):
    record_id: str
    session_id: str
    domain: str
    operation_name: str
    resource_units: float
    cost_breakdown: ThreeDimensionalCostModel
    billable: bool
    policy_note: str
    timestamp_ms: int


class SessionDualDomainSummaryModel(BaseModel):
    session_id: str
    gateway_token_cost_usd: float
    sandbox_compute_cost_usd: float
    thirdparty_tool_cost_usd: float
    total_cost_usd: float
    total_operations: int
    gateway_ops_count: int
    sandbox_ops_count: int
    gateway_cost_ratio: float
    sandbox_cost_ratio: float
    generated_at_ms: int


class ReconciliationStatementModel(BaseModel):
    statement_id: str
    session_id: str
    summary: SessionDualDomainSummaryModel
    records: List[DomainMeteringRecordModel]
    integrity_sha256: str
    generated_at_ms: int


# --- Helper Converters ---


def _to_record_model(r: DomainMeteringRecord) -> DomainMeteringRecordModel:
    return DomainMeteringRecordModel(
        record_id=r.record_id,
        session_id=r.session_id,
        domain=r.domain.value,
        operation_name=r.operation_name,
        resource_units=r.resource_units,
        cost_breakdown=ThreeDimensionalCostModel(
            model_token_cost_usd=r.cost_breakdown.model_token_cost_usd,
            sandbox_compute_cost_usd=r.cost_breakdown.sandbox_compute_cost_usd,
            thirdparty_tool_cost_usd=r.cost_breakdown.thirdparty_tool_cost_usd,
            total_cost_usd=r.cost_breakdown.total_cost_usd,
        ),
        billable=r.billable,
        policy_note=r.policy_note,
        timestamp_ms=r.timestamp_ms,
    )


def _to_summary_model(s: SessionDualDomainSummary) -> SessionDualDomainSummaryModel:
    return SessionDualDomainSummaryModel(
        session_id=s.session_id,
        gateway_token_cost_usd=s.gateway_token_cost_usd,
        sandbox_compute_cost_usd=s.sandbox_compute_cost_usd,
        thirdparty_tool_cost_usd=s.thirdparty_tool_cost_usd,
        total_cost_usd=s.total_cost_usd,
        total_operations=s.total_operations,
        gateway_ops_count=s.gateway_ops_count,
        sandbox_ops_count=s.sandbox_ops_count,
        gateway_cost_ratio=s.gateway_cost_ratio,
        sandbox_cost_ratio=s.sandbox_cost_ratio,
        generated_at_ms=s.generated_at_ms,
    )


def _to_statement_model(stmt: ReconciliationStatement) -> ReconciliationStatementModel:
    return ReconciliationStatementModel(
        statement_id=stmt.statement_id,
        session_id=stmt.session_id,
        summary=_to_summary_model(stmt.summary),
        records=[_to_record_model(r) for r in stmt.records],
        integrity_sha256=stmt.integrity_sha256,
        generated_at_ms=stmt.generated_at_ms,
    )


# --- Endpoints ---


@router.post("/record", response_model=DomainMeteringRecordModel)
async def record_metering_entry(req: RecordMeteringRequest) -> DomainMeteringRecordModel:
    """Record an itemized operation bounded by gateway or sandbox domain."""
    ledger = get_default_dual_domain_ledger()
    try:
        domain_enum = MeteringDomain(req.domain)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid domain: {req.domain}. Must be gateway_domain or sandbox_domain.",
        )

    cost_dto = ThreeDimensionalCost(
        model_token_cost_usd=req.cost_breakdown.model_token_cost_usd,
        sandbox_compute_cost_usd=req.cost_breakdown.sandbox_compute_cost_usd,
        thirdparty_tool_cost_usd=req.cost_breakdown.thirdparty_tool_cost_usd,
    )

    rec = ledger.record_metering(
        session_id=req.session_id,
        domain=domain_enum,
        operation_name=req.operation_name,
        resource_units=req.resource_units,
        cost_breakdown=cost_dto,
        billable=req.billable,
        policy_note=req.policy_note,
        custom_record_id=req.custom_record_id,
    )
    return _to_record_model(rec)


@router.get("/summary/{session_id}", response_model=SessionDualDomainSummaryModel)
async def get_session_summary(session_id: str) -> SessionDualDomainSummaryModel:
    """Get aggregated dual-domain and 3D cost summary for a session."""
    ledger = get_default_dual_domain_ledger()
    summary = ledger.get_session_summary(session_id)
    return _to_summary_model(summary)


@router.post("/statement/{session_id}", response_model=ReconciliationStatementModel)
async def generate_statement(session_id: str) -> ReconciliationStatementModel:
    """Generate and seal a cryptographically verifiable SHA-256 financial reconciliation statement."""
    ledger = get_default_dual_domain_ledger()
    stmt = ledger.generate_reconciliation_statement(session_id)
    return _to_statement_model(stmt)


@router.get("/statements", response_model=List[ReconciliationStatementModel])
async def list_statements(
    limit: int = Query(50, ge=1, le=200, description="Max statements to return"),
) -> List[ReconciliationStatementModel]:
    """List financial reconciliation statements, newest first."""
    ledger = get_default_dual_domain_ledger()
    statements = ledger.list_statements(limit=limit)
    return [_to_statement_model(s) for s in statements]


@router.post("/reset")
async def reset_ledger() -> Dict[str, bool]:
    """Reset all records and statements in the dual-domain ledger."""
    ledger = get_default_dual_domain_ledger()
    ledger.reset()
    return {"ok": True}
