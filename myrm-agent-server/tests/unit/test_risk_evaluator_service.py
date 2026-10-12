"""Unit tests for RiskEvaluatorService.

[POS]
Server unit tests verifying orchestration of independent proposal risk evaluation,
OS-level shell command scanning, and structured audit ledger persistence.
"""

from __future__ import annotations

from app.schemas.risk_evaluator import (
    ActionProposalDto,
    EvaluateProposalRequest,
    OsCommandScanRequest,
)
from app.services.security.risk_evaluator_service import RiskEvaluatorService


def test_risk_evaluator_service_proposals() -> None:
    service = RiskEvaluatorService()

    # 1. Safe proposal
    safe_prop = ActionProposalDto(
        proposal_id="prop_01",
        action_type="system_operation",
        title="Check system logs",
        description="Inspect stdout logs of worker container",
        estimated_cost=0.0,
        blast_radius_scope="local",
        rollback_supported=True,
    )
    res_safe = service.evaluate_proposal(EvaluateProposalRequest(proposal=safe_prop))
    assert res_safe.verdict == "APPROVED"
    assert res_safe.report.approved is True
    assert res_safe.report.tier == "pass_safe"

    # 2. Blocked proposal: financial overbudget + global blast radius
    danger_prop = ActionProposalDto(
        proposal_id="prop_02",
        action_type="financial_transaction",
        title="Unauthorized crypto trade",
        description="Execute 100 ETH market buy",
        estimated_cost=250000.0,
        blast_radius_scope="global",
        rollback_supported=False,
    )
    res_danger = service.evaluate_proposal(EvaluateProposalRequest(proposal=danger_prop))
    assert res_danger.verdict == "BLOCKED"
    assert res_danger.report.approved is False
    assert res_danger.report.tier == "block_critical"
    assert len(res_danger.report.violations) >= 2

    # 3. Check audit ledger has both records
    ledger = service.get_audit_ledger()
    assert ledger.count == 2
    assert ledger.entries[0].proposal_id == "prop_02"
    assert ledger.entries[0].outcome == "blocked"
    assert ledger.entries[1].proposal_id == "prop_01"
    assert ledger.entries[1].outcome == "approved"


def test_risk_evaluator_service_os_command_scanning() -> None:
    service = RiskEvaluatorService()

    # 1. Safe command
    safe_scan = service.scan_os_command(OsCommandScanRequest(command="ls -la /workspace"))
    assert safe_scan.scan_result.safe is True
    assert safe_scan.scan_result.command_signature == "ls"
    assert len(safe_scan.scan_result.detected_vulnerabilities) == 0

    # 2. Destructive command
    danger_scan = service.scan_os_command(OsCommandScanRequest(command="rm -rf /"))
    assert danger_scan.scan_result.safe is False
    assert len(danger_scan.scan_result.detected_vulnerabilities) >= 1
