"""
Unit tests for Strict Target Scope Authorization & Egress Boundary Service.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from app.schemas.target_scope_boundary import (
    SetContractRequest,
    VerifyTargetRequest,
)
from app.services.security.target_scope_boundary_service import (
    TargetScopeBoundaryService,
)


def _sample_contract_request() -> SetContractRequest:
    return SetContractRequest(
        contract_id="contract-sec-2026",
        engagement_name="Penetration Audit Internal Services",
        authorized_domains=["*.audit.myrm.internal", "audit-target.local"],
        authorized_cidrs=["10.20.0.0/16", "172.28.10.0/24"],
        prohibited_targets=["billing.audit.myrm.internal", "10.20.99.1"],
        signed_by="security_lead_ciso",
        signature_hash="sha256_valid_audit_sig_abc",
        is_active=True,
    )


def test_service_set_and_get_contract() -> None:
    service = TargetScopeBoundaryService()
    req = _sample_contract_request()

    resp = service.set_contract(req)
    assert resp.contract_id == "contract-sec-2026"
    assert resp.is_active

    active = service.get_active_contract()
    assert active is not None
    assert active.engagement_name == "Penetration Audit Internal Services"

    service.clear_contract()
    assert service.get_active_contract() is None


def test_service_verify_target_scope_outcomes() -> None:
    service = TargetScopeBoundaryService()
    service.set_contract(_sample_contract_request())

    # 1. In scope domain
    res1 = service.verify_target(VerifyTargetRequest(target_host="api.audit.myrm.internal"))
    assert res1.is_allowed
    assert res1.verdict == "IN_SCOPE_ALLOWED"

    # 2. In scope domain with matching authorized resolved IP
    res2 = service.verify_target(
        VerifyTargetRequest(target_host="api.audit.myrm.internal", resolved_ip="10.20.1.15")
    )
    assert res2.is_allowed
    assert res2.verdict == "IN_SCOPE_ALLOWED"

    # 3. Domain matches, but resolved IP is outside authorized CIDRs (unauthorized IP / CNAME evasion)
    res3 = service.verify_target(
        VerifyTargetRequest(target_host="api.audit.myrm.internal", resolved_ip="1.1.1.1")
    )
    assert not res3.is_allowed
    assert res3.verdict == "UNAUTHORIZED_IP_BLOCKED"

    # 4. Prohibited sub-target
    res4 = service.verify_target(VerifyTargetRequest(target_host="billing.audit.myrm.internal"))
    assert not res4.is_allowed
    assert res4.verdict == "OUT_OF_SCOPE_BLOCKED"

    # 5. Cloud provider metadata attempt
    res5 = service.verify_target(VerifyTargetRequest(target_host="169.254.169.254"))
    assert not res5.is_allowed
    assert res5.verdict == "CLOUD_METADATA_PROHIBITED"


def test_service_kill_switch_lifecycle_and_metrics() -> None:
    service = TargetScopeBoundaryService()
    service.set_contract(_sample_contract_request())

    # Initially disengaged
    status_init = service.get_kill_switch_status()
    assert not status_init.is_kill_switch_active

    # Activate
    act_resp = service.activate_kill_switch()
    assert act_resp.is_kill_switch_active

    # When active, in-scope targets are immediately severed
    res_killed = service.verify_target(VerifyTargetRequest(target_host="api.audit.myrm.internal"))
    assert not res_killed.is_allowed
    assert res_killed.verdict == "EMERGENCY_KILL_SWITCH_ACTIVE"

    # Reset
    reset_resp = service.reset_kill_switch()
    assert not reset_resp.is_kill_switch_active

    # Restored
    res_restored = service.verify_target(VerifyTargetRequest(target_host="api.audit.myrm.internal"))
    assert res_restored.is_allowed
    assert res_restored.verdict == "IN_SCOPE_ALLOWED"

    # Metrics
    metrics = service.get_metrics()
    assert metrics.scope_checks_total == 2
    assert metrics.in_scope_allowed_total == 1
    assert metrics.out_of_scope_blocked_total == 1
    assert metrics.kill_switch_activations_total == 1
