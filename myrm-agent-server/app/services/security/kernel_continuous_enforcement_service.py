"""Service layer for Kernel Continuous Enforcement, Formal Policy Prover,
and Revocation Residue Suite.

[INPUT]
- app.schemas.kernel_continuous_enforcement::(NetworkPolicyRuleSchema, RuntimeHopCheckRequestSchema,
  RuntimeHopCheckResponseSchema, PolicyProposalSubmitRequestSchema, ProverValidationResponseSchema,
  ProposalDetailResponseSchema, RevocationAuditRequestSchema, RevocationResidueReportResponseSchema)
- myrm_agent_harness.core.security.kernel_continuous_enforcement::(KernelContinuousEnforcementFacade,
  NetworkPolicyRule, PolicyChangeProposal, ProtocolKind, RuntimeHopCheckRequest)
- stdlib datetime, threading

[OUTPUT]
- KernelContinuousEnforcementService: singleton service orchestrating continuous 3D enforcement,
  formal prover gates, and residue audits

[POS]
Service layer bridging REST API endpoints to harness KernelContinuousEnforcementFacade.
Strictly avoids Any types; enforced under 400 lines limit.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

from myrm_agent_harness.core.security.kernel_continuous_enforcement import (
    KernelContinuousEnforcementFacade,
    NetworkPolicyRule,
    PolicyChangeProposal,
    ProtocolKind,
    RuntimeHopCheckRequest,
)

from app.schemas.kernel_continuous_enforcement import (
    NetworkPolicyRuleSchema,
    PolicyProposalSubmitRequestSchema,
    ProposalDetailResponseSchema,
    ProverValidationResponseSchema,
    RevocationAuditRequestSchema,
    RevocationResidueReportResponseSchema,
    RuntimeHopCheckRequestSchema,
    RuntimeHopCheckResponseSchema,
)


def _to_protocol_kind(val: str) -> ProtocolKind:
    try:
        return ProtocolKind(val.lower())
    except ValueError:
        return ProtocolKind.REST


def _to_rule_domain(schema: NetworkPolicyRuleSchema) -> NetworkPolicyRule:
    return NetworkPolicyRule(
        rule_id=schema.rule_id,
        allowed_binaries=tuple(schema.allowed_binaries),
        endpoint_host=schema.endpoint_host,
        endpoint_port=schema.endpoint_port,
        path_glob=schema.path_glob,
        protocol=_to_protocol_kind(schema.protocol),
        allow_upgrade_header=schema.allow_upgrade_header,
        provider_binding=schema.provider_binding,
    )


def _to_rule_schema(domain: NetworkPolicyRule) -> NetworkPolicyRuleSchema:
    return NetworkPolicyRuleSchema(
        rule_id=domain.rule_id,
        allowed_binaries=list(domain.allowed_binaries),
        endpoint_host=domain.endpoint_host,
        endpoint_port=domain.endpoint_port,
        path_glob=domain.path_glob,
        protocol=domain.protocol.value,
        allow_upgrade_header=domain.allow_upgrade_header,
        provider_binding=domain.provider_binding,
    )


class KernelContinuousEnforcementService:
    """Singleton service orchestrating 3D runtime enforcement, prover, and audits."""

    _instance: KernelContinuousEnforcementService | None = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        self._facade: KernelContinuousEnforcementFacade = KernelContinuousEnforcementFacade()

    @classmethod
    def get_instance(cls) -> KernelContinuousEnforcementService:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        with cls._lock:
            cls._instance = None

    def evaluate_egress(self, request: RuntimeHopCheckRequestSchema) -> RuntimeHopCheckResponseSchema:
        """Evaluate executing binary egress against active 3D policies."""
        hop_req = RuntimeHopCheckRequest(
            binary_name=request.binary_name,
            host=request.host,
            port=request.port,
            path=request.path,
            protocol=_to_protocol_kind(request.protocol),
            has_upgrade_header=request.has_upgrade_header,
        )
        res = self._facade.evaluate_egress(hop_req)
        return RuntimeHopCheckResponseSchema(
            decision=res.decision.value,
            rule_id=res.rule_id,
            reason=res.reason,
            violates_protocol_upgrade=res.violates_protocol_upgrade,
        )

    def get_active_rules(self) -> list[NetworkPolicyRuleSchema]:
        """List all active 3D network policy rules."""
        return [_to_rule_schema(r) for r in self._facade.enforcer.get_rules()]

    def add_rule(self, rule: NetworkPolicyRuleSchema) -> None:
        """Add an active 3D network policy rule."""
        self._facade.enforcer.add_rule(_to_rule_domain(rule))

    def submit_proposal(self, request: PolicyProposalSubmitRequestSchema) -> ProverValidationResponseSchema:
        """Submit agent proposal and execute formal verification."""
        timestamp = datetime.now(UTC).isoformat()
        domain_rules = tuple(_to_rule_domain(r) for r in request.proposed_rules)
        proposal = PolicyChangeProposal(
            proposal_id=request.proposal_id,
            agent_id=request.agent_id,
            proposed_rules=domain_rules,
            justification=request.justification,
            timestamp_iso=timestamp,
        )
        proof = self._facade.submit_proposal(proposal)
        return ProverValidationResponseSchema(
            proposal_id=proof.proposal_id,
            is_safe=proof.is_safe,
            risk_score=proof.risk_score,
            flagged_risks=list(proof.flagged_risks),
            formal_proof_summary=proof.formal_proof_summary,
            requires_human_approval=proof.requires_human_approval,
        )

    def approve_proposal(self, proposal_id: str) -> bool:
        """Approve and hot-load proposed rules into the enforcer."""
        return self._facade.approve_proposal(proposal_id)

    def reject_proposal(self, proposal_id: str) -> bool:
        """Reject a proposed policy."""
        return self._facade.reject_proposal(proposal_id)

    def list_proposals(self) -> list[ProposalDetailResponseSchema]:
        """List all proposals with proof outcomes and status."""
        entries = self._facade.get_proposals()
        result: list[ProposalDetailResponseSchema] = []
        for prop, proof, status_str in entries:
            result.append(
                ProposalDetailResponseSchema(
                    proposal_id=prop.proposal_id,
                    agent_id=prop.agent_id,
                    status=status_str,
                    proposed_rules=[_to_rule_schema(r) for r in prop.proposed_rules],
                    proof=ProverValidationResponseSchema(
                        proposal_id=proof.proposal_id,
                        is_safe=proof.is_safe,
                        risk_score=proof.risk_score,
                        flagged_risks=list(proof.flagged_risks),
                        formal_proof_summary=proof.formal_proof_summary,
                        requires_human_approval=proof.requires_human_approval,
                    ),
                )
            )
        return result

    def audit_revocation(self, request: RevocationAuditRequestSchema) -> RevocationResidueReportResponseSchema:
        """Audit post-revocation environment for surviving artifacts."""
        report = self._facade.audit_revocation(
            run_id=request.run_id,
            active_pids=request.active_pids,
            open_sockets=request.open_sockets,
            temp_files=request.temp_files,
            cached_tokens=request.cached_tokens,
        )
        return RevocationResidueReportResponseSchema(
            run_id=report.run_id,
            timestamp_iso=report.timestamp_iso,
            lingering_pids=list(report.lingering_pids),
            lingering_sockets=list(report.lingering_sockets),
            lingering_tmp_files=list(report.lingering_tmp_files),
            lingering_cached_tokens=list(report.lingering_cached_tokens),
            is_fully_clean=report.is_fully_clean,
        )

    def list_residue_reports(self) -> list[RevocationResidueReportResponseSchema]:
        """List historical revocation residue reports."""
        reports = self._facade.get_residue_reports()
        return [
            RevocationResidueReportResponseSchema(
                run_id=r.run_id,
                timestamp_iso=r.timestamp_iso,
                lingering_pids=list(r.lingering_pids),
                lingering_sockets=list(r.lingering_sockets),
                lingering_tmp_files=list(r.lingering_tmp_files),
                lingering_cached_tokens=list(r.lingering_cached_tokens),
                is_fully_clean=r.is_fully_clean,
            )
            for r in reports
        ]
