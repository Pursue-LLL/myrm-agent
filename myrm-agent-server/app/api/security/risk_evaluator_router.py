"""API endpoints for Independent Risk Evaluator Agent and OS Security Scanner.

[INPUT]
- EvaluateProposalRequest, OsCommandScanRequest
- Query parameters: tier, limit

[OUTPUT]
- EvaluateProposalResponse, OsCommandScanResponse, RiskAuditLedgerResponse

[POS]
Server API layer. Exposes REST endpoints for pre-execution risk gates and OS command security scanning.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas.risk_evaluator import (
    EvaluateProposalRequest,
    EvaluateProposalResponse,
    OsCommandScanRequest,
    OsCommandScanResponse,
    RiskAuditLedgerResponse,
)
from app.services.security.risk_evaluator_service import default_risk_evaluator_service

router = APIRouter(prefix="/risk-evaluator", tags=["risk-evaluator"])


@router.post("/evaluate", response_model=EvaluateProposalResponse)
async def evaluate_action_proposal(
    request: EvaluateProposalRequest,
) -> EvaluateProposalResponse:
    """Submit an action proposal to the independent risk agent for multi-dimensional assessment."""
    return default_risk_evaluator_service.evaluate_proposal(request)


@router.post("/scan-os-command", response_model=OsCommandScanResponse)
async def scan_os_command(
    request: OsCommandScanRequest,
) -> OsCommandScanResponse:
    """Scan shell commands or dynamic scripts against ECC-style OS threat models."""
    return default_risk_evaluator_service.scan_os_command(request)


@router.get("/audit-ledger", response_model=RiskAuditLedgerResponse)
async def get_risk_audit_ledger(
    tier: str | None = Query(default=None, description="Filter by risk tier (pass_safe, warn_elevated, block_critical)"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max audit entries to retrieve"),
) -> RiskAuditLedgerResponse:
    """Query structured risk audit ledger records."""
    return default_risk_evaluator_service.get_audit_ledger(tier=tier, limit=limit)
