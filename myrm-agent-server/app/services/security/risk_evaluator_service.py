"""Service orchestrating Independent Risk Evaluator Agent, OS Security Guard, and Structured Risk Audit Ledger.

[INPUT]
- EvaluateProposalRequest, OsCommandScanRequest
- Harness IndependentRiskEvaluatorAgent, OsSecurityGuard, StructuredRiskAuditLedger

[OUTPUT]
- RiskEvaluatorService: enterprise security service handling proposal assessments and OS security scans.

[POS]
Server service layer. Enforces independent multi-agent risk checks before dispatching sensitive actions.
"""

from __future__ import annotations

import logging
import uuid

from myrm_agent_harness.core.security.risk_evaluator import (
    ActionProposal,
    IndependentRiskEvaluatorAgent,
    OsOperatorScanResult,
    OsSecurityGuard,
    ProposalActionType,
    RiskEvaluationReport,
    RiskEvaluationTier,
    StructuredRiskAuditLedger,
)

from app.schemas.risk_evaluator import (
    ActionProposalDto,
    EvaluateProposalRequest,
    EvaluateProposalResponse,
    OsCommandScanRequest,
    OsCommandScanResponse,
    OsOperatorScanResultDto,
    RiskAuditEntryDto,
    RiskAuditLedgerResponse,
    RiskEvaluationReportDto,
)

logger = logging.getLogger(__name__)


def _proposal_dto_to_domain(dto: ActionProposalDto) -> ActionProposal:
    """Map proposal DTO to Harness domain dataclass."""
    try:
        action_type = ProposalActionType(dto.action_type)
    except ValueError:
        action_type = ProposalActionType.SYSTEM_OPERATION

    return ActionProposal(
        proposal_id=dto.proposal_id,
        action_type=action_type,
        title=dto.title,
        description=dto.description,
        estimated_cost=dto.estimated_cost,
        blast_radius_scope=dto.blast_radius_scope,
        rollback_supported=dto.rollback_supported,
        raw_command_or_payload=dto.raw_command_or_payload,
        target_resources=tuple(dto.target_resources),
    )


def _os_scan_to_dto(domain: OsOperatorScanResult) -> OsOperatorScanResultDto:
    """Map OS scan domain dataclass to DTO."""
    return OsOperatorScanResultDto(
        safe=domain.safe,
        command_signature=domain.command_signature,
        detected_vulnerabilities=list(domain.detected_vulnerabilities),
        blocked_patterns=list(domain.blocked_patterns),
        scanned_at=domain.scanned_at,
    )


def _report_to_dto(domain: RiskEvaluationReport) -> RiskEvaluationReportDto:
    """Map risk evaluation report domain model to DTO."""
    os_scan_dto = _os_scan_to_dto(domain.os_scan_result) if domain.os_scan_result else None
    return RiskEvaluationReportDto(
        evaluation_id=domain.evaluation_id,
        proposal_id=domain.proposal_id,
        tier=str(domain.tier),
        risk_score=domain.risk_score,
        approved=domain.approved,
        blast_radius_score=domain.blast_radius_score,
        rollback_feasible=domain.rollback_feasible,
        violations=list(domain.violations),
        recommendations=list(domain.recommendations),
        os_scan_result=os_scan_dto,
        evaluated_at=domain.evaluated_at,
    )


class RiskEvaluatorService:
    """Singleton service managing independent risk evaluation and OS command verification."""

    def __init__(
        self,
        agent: IndependentRiskEvaluatorAgent | None = None,
        ledger: StructuredRiskAuditLedger | None = None,
    ) -> None:
        self._agent = agent or IndependentRiskEvaluatorAgent(max_cost_limit=100.0)
        self._ledger = ledger or StructuredRiskAuditLedger(capacity=2000)

    @property
    def agent(self) -> IndependentRiskEvaluatorAgent:
        """Underlying risk evaluation agent."""
        return self._agent

    @property
    def ledger(self) -> StructuredRiskAuditLedger:
        """Underlying audit ledger."""
        return self._ledger

    def evaluate_proposal(self, request: EvaluateProposalRequest) -> EvaluateProposalResponse:
        """Independently evaluate action proposal against risk metrics and record audit entry."""
        domain_prop = _proposal_dto_to_domain(request.proposal)
        report = self._agent.evaluate_proposal(domain_prop)

        # Record into audit ledger
        outcome = "approved" if report.approved else "blocked"
        entry_id = f"aud_{uuid.uuid4().hex[:10]}"
        self._ledger.record_entry(
            entry_id=entry_id,
            proposal=domain_prop,
            report=report,
            outcome=outcome,
        )

        verdict_str = (
            "APPROVED"
            if report.approved and report.tier == RiskEvaluationTier.PASS_SAFE
            else "ELEVATED_WARNING"
            if report.approved
            else "BLOCKED"
        )

        return EvaluateProposalResponse(
            report=_report_to_dto(report),
            verdict=verdict_str,
        )

    def scan_os_command(self, request: OsCommandScanRequest) -> OsCommandScanResponse:
        """Scan terminal command or dynamic script payload against OS security threat models."""
        result = OsSecurityGuard.scan_command(request.command)
        return OsCommandScanResponse(scan_result=_os_scan_to_dto(result))

    def get_audit_ledger(
        self,
        tier: str | None = None,
        limit: int = 100,
    ) -> RiskAuditLedgerResponse:
        """Fetch audit records from ledger, with optional risk tier filter."""
        parsed_tier: RiskEvaluationTier | None = None
        if tier:
            try:
                parsed_tier = RiskEvaluationTier(tier)
            except ValueError:
                parsed_tier = None

        entries = self._ledger.list_entries(tier=parsed_tier, limit=limit)
        dto_list: list[RiskAuditEntryDto] = []
        for e in entries:
            dto_list.append(
                RiskAuditEntryDto(
                    entry_id=e.entry_id,
                    proposal_id=e.proposal.proposal_id,
                    title=e.proposal.title,
                    tier=str(e.report.tier),
                    risk_score=e.report.risk_score,
                    outcome=e.outcome,
                    recorded_at=e.recorded_at,
                )
            )
        return RiskAuditLedgerResponse(entries=dto_list, count=len(dto_list))


# Default global singleton service
default_risk_evaluator_service = RiskEvaluatorService()
