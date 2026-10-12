"""Unit tests for RedirectHopGuardService in server layer.

Verifies service orchestration, policy updates, hop evaluations,
and audit record operations.
"""

from __future__ import annotations

import pytest

from app.schemas.redirect_hop_guard import (
    HopEvaluationRequest,
    HopPolicyConfigRequest,
    HopSimulationRequest,
)
from app.services.security.redirect_hop_guard_service import RedirectHopGuardService


@pytest.fixture(autouse=True)
def clean_service_instance() -> None:
    RedirectHopGuardService.reset_instance()
    yield
    RedirectHopGuardService.reset_instance()


def test_evaluate_hop_cloud_metadata_and_private_ips() -> None:
    service = RedirectHopGuardService.get_instance()

    # Cloud IMDS
    req1 = HopEvaluationRequest(target_url="http://169.254.169.254/latest/meta-data/", resource_type="document")
    res1 = service.evaluate_hop(req1)
    assert res1.is_private is True
    assert res1.disposition == "ABORT_AND_RESET_DOCUMENT"
    assert "CLOUD_METADATA_IMDS" in res1.matched_rule

    # RFC 1918 Private IP
    req2 = HopEvaluationRequest(target_url="http://192.168.1.1/admin", resource_type="fetch")
    res2 = service.evaluate_hop(req2)
    assert res2.is_private is True
    assert res2.disposition == "ABORT_SUBRESOURCE"
    assert "PRIVATE_IPV4" in res2.matched_rule

    # Public safe target
    req3 = HopEvaluationRequest(target_url="https://api.github.com/repos", resource_type="document")
    res3 = service.evaluate_hop(req3)
    assert res3.is_private is False
    assert res3.disposition == "ALLOW"
    assert res3.matched_rule == "PUBLIC_TARGET"


def test_policy_get_and_update() -> None:
    service = RedirectHopGuardService.get_instance()

    default_policy = service.get_policy()
    assert default_policy.allow_private_networks is False
    assert default_policy.reset_to_about_blank is True

    update_req = HopPolicyConfigRequest(
        allow_private_networks=True,
        reset_to_about_blank=False,
        audit_history_max_size=200,
        custom_blocked_hostnames=["custom-metadata.internal"],
    )
    updated_policy = service.update_policy(update_req)
    assert updated_policy.allow_private_networks is True
    assert updated_policy.reset_to_about_blank is False
    assert updated_policy.audit_history_max_size == 200
    assert updated_policy.custom_blocked_hostnames == ["custom-metadata.internal"]

    # When private networks are allowed, evaluation allows internal hops
    res = service.evaluate_hop(HopEvaluationRequest(target_url="http://10.0.0.5/api"))
    assert res.is_private is False
    assert res.disposition == "ALLOW"


def test_simulate_violation_and_manage_history() -> None:
    service = RedirectHopGuardService.get_instance()

    sim_req = HopSimulationRequest(
        initial_url="https://example.com/login",
        hop_url="http://169.254.169.254/latest/meta-data/",
        resource_type="document",
    )
    recorded = service.simulate_violation(sim_req)
    assert recorded.initial_url == "https://example.com/login"
    assert recorded.hop_url == "http://169.254.169.254/latest/meta-data/"
    assert recorded.disposition == "ABORT_AND_RESET_DOCUMENT"

    violations = service.get_violations()
    assert violations.total == 1
    assert violations.violations[0].hop_url == recorded.hop_url

    service.clear_violations()
    assert service.get_violations().total == 0
