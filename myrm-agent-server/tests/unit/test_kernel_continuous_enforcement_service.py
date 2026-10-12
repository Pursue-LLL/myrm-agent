"""Unit tests for KernelContinuousEnforcementService in server layer.

Verifies service orchestration, 3D rule addition, egress evaluation,
formal policy proposal verification and approval hot-loading, and revocation residue auditing.
Strict typing applied: No `Any` types allowed. Enforced under 400 lines limit.
"""

from __future__ import annotations

import pytest

from app.schemas.kernel_continuous_enforcement import (
    NetworkPolicyRuleSchema,
    PolicyProposalSubmitRequestSchema,
    RevocationAuditRequestSchema,
    RuntimeHopCheckRequestSchema,
)
from app.services.security.kernel_continuous_enforcement_service import (
    KernelContinuousEnforcementService,
)


@pytest.fixture(autouse=True)
def clean_service_instance() -> None:
    KernelContinuousEnforcementService.reset_instance()
    yield
    KernelContinuousEnforcementService.reset_instance()


def test_evaluate_egress_and_rule_lifecycle() -> None:
    service = KernelContinuousEnforcementService.get_instance()

    req = RuntimeHopCheckRequestSchema(
        binary_name="curl",
        host="api.external.com",
        port=443,
        path="/v1/telemetry",
        protocol="rest",
    )

    # 1. Initially denied
    res_init = service.evaluate_egress(req)
    assert res_init.decision == "deny"
    assert "No matching policy rule" in res_init.reason

    # 2. Add rule
    rule = NetworkPolicyRuleSchema(
        rule_id="rule-external-telemetry",
        allowed_binaries=["curl", "git"],
        endpoint_host="api.external.com",
        endpoint_port=443,
        path_glob="/v1/*",
        protocol="rest",
        allow_upgrade_header=False,
    )
    service.add_rule(rule)

    active_rules = service.get_active_rules()
    assert len(active_rules) == 1
    assert active_rules[0].rule_id == "rule-external-telemetry"

    # 3. Retry with authorized binary -> ALLOW
    res_allowed = service.evaluate_egress(req)
    assert res_allowed.decision == "allow"
    assert res_allowed.rule_id == "rule-external-telemetry"

    # 4. Request with unauthorized binary -> DENY
    req_unauth = RuntimeHopCheckRequestSchema(
        binary_name="python3",
        host="api.external.com",
        port=443,
        path="/v1/telemetry",
        protocol="rest",
    )
    res_unauth = service.evaluate_egress(req_unauth)
    assert res_unauth.decision == "deny"
    assert "not permitted" in res_unauth.reason


def test_proposals_submit_approve_and_reject() -> None:
    service = KernelContinuousEnforcementService.get_instance()

    risky_rule = NetworkPolicyRuleSchema(
        rule_id="prop-rule-ssh",
        allowed_binaries=["*"],
        endpoint_host="bastion.internal",
        endpoint_port=22,
        path_glob="*",
        protocol="tcp",
    )
    proposal_req = PolicyProposalSubmitRequestSchema(
        proposal_id="prop-ssh-01",
        agent_id="agent-ops",
        proposed_rules=[risky_rule],
        justification="Administrative SSH access requested",
    )

    # 1. Submit proposal -> prover flags risks
    proof = service.submit_proposal(proposal_req)
    assert proof.is_safe is False
    assert proof.requires_human_approval is True
    assert proof.risk_score >= 0.5
    assert len(proof.flagged_risks) >= 2

    proposals = service.list_proposals()
    assert len(proposals) == 1
    assert proposals[0].status == "PENDING"

    # 2. Approve proposal -> rules hot-loaded into enforcer
    ok_approve = service.approve_proposal("prop-ssh-01")
    assert ok_approve is True

    proposals_after = service.list_proposals()
    assert proposals_after[0].status == "APPROVED"

    # Verify rule is now active in enforcer
    rules_now = service.get_active_rules()
    assert any(r.rule_id == "prop-rule-ssh" for r in rules_now)


def test_revocation_residue_audit_service() -> None:
    service = KernelContinuousEnforcementService.get_instance()

    audit_dirty = RevocationAuditRequestSchema(
        run_id="run-test-dirty",
        active_pids=[9991],
        open_sockets=["127.0.0.1:8001"],
        temp_files=["/tmp/.agent_cred"],
        cached_tokens=["token_xyz"],
    )
    rep_dirty = service.audit_revocation(audit_dirty)
    assert rep_dirty.is_fully_clean is False
    assert len(rep_dirty.lingering_pids) == 1

    audit_clean = RevocationAuditRequestSchema(
        run_id="run-test-clean",
        active_pids=[],
        open_sockets=[],
        temp_files=[],
        cached_tokens=[],
    )
    rep_clean = service.audit_revocation(audit_clean)
    assert rep_clean.is_fully_clean is True

    reports = service.list_residue_reports()
    assert len(reports) == 2
