"""Unit tests for MuseSentinelIsolationService."""

from __future__ import annotations

import pytest

from app.schemas.muse_sentinel_isolation import (
    IssueSingleUseTokenRequest,
    RedeemSingleUseTokenRequest,
    RegisterVmRequest,
    ReviewOutboundTrafficRequest,
)
from app.services.security.muse_sentinel_isolation_service import (
    MuseSentinelIsolationService,
)
from tests.support.fake_secrets import stripe_live_key


@pytest.fixture
def service() -> MuseSentinelIsolationService:
    """Create a fresh MuseSentinelIsolationService instance."""
    return MuseSentinelIsolationService()


def test_service_register_and_get_vm(service: MuseSentinelIsolationService) -> None:
    """Verify registering, retrieving, and listing secure VM profiles."""
    reg_req = RegisterVmRequest(
        user_id="user_dev_01",
        isolation_tier="dedicated_secure_vm",
    )
    profile = service.register_vm(reg_req)
    assert profile.user_id == "user_dev_01"
    assert profile.isolation_tier == "dedicated_secure_vm"
    assert profile.credential_sealed is True

    # Retrieve by vm_id and user_id
    by_vm = service.get_vm(profile.vm_id)
    assert by_vm is not None
    assert by_vm.vm_id == profile.vm_id

    by_user = service.get_user_vm("user_dev_01")
    assert by_user is not None
    assert by_user.user_id == "user_dev_01"

    # List
    vms = service.list_vms()
    assert len(vms) >= 1


def test_service_review_outbound_blocked_and_allowed(
    service: MuseSentinelIsolationService,
) -> None:
    """Verify Sentinel screening blocks leaks and allows clean traffic."""
    # 1. Leak: Stripe Live Key
    req_leak = ReviewOutboundTrafficRequest(
        request_id="trace_01",
        destination_url="https://external.api/v1/charge",
        method="POST",
        headers={"Authorization": f"Bearer {stripe_live_key('abcdef1234567890abcdef1234')}"},
        body_preview="",
        source_vm_id="vm_01",
    )
    res_leak = service.review_outbound(req_leak)
    assert res_leak.verdict == "block"
    assert res_leak.risk_score == 1.0
    assert "stripe_live_key" in (res_leak.matched_rule or "")

    # 2. Clean traffic
    req_clean = ReviewOutboundTrafficRequest(
        request_id="trace_02",
        destination_url="https://api.github.com/zen",
        method="GET",
        headers={"Accept": "application/json"},
        body_preview="",
        source_vm_id="vm_01",
    )
    res_clean = service.review_outbound(req_clean)
    assert res_clean.verdict == "allow"
    assert res_clean.risk_score == 0.0


def test_service_issue_and_redeem_single_use_token(
    service: MuseSentinelIsolationService,
) -> None:
    """Verify single-use credential issuance, authorization, and replay prevention."""
    # 1. Issue virtual payment card
    issue_req = IssueSingleUseTokenRequest(
        token_type="virtual_payment_card",
        max_amount=80.0,
        currency="USD",
        bound_recipient="stripe_link_merchant",
        ttl_seconds=300,
    )
    token = service.issue_single_use_token(issue_req)
    assert token.is_consumed is False
    assert token.max_amount == 80.0
    assert token.virtual_token.startswith("link_vtok_")

    # 2. Redeem #1 (Valid)
    redeem_req1 = RedeemSingleUseTokenRequest(
        virtual_token=token.virtual_token,
        amount=60.0,
        currency="USD",
        recipient="stripe_link_merchant",
    )
    res1 = service.redeem_single_use_token(redeem_req1)
    assert res1.success is True
    assert res1.token_id == token.token_id

    # 3. Redeem #2 (Replay blocked)
    redeem_req2 = RedeemSingleUseTokenRequest(
        virtual_token=token.virtual_token,
        amount=10.0,
        currency="USD",
        recipient="stripe_link_merchant",
    )
    res2 = service.redeem_single_use_token(redeem_req2)
    assert res2.success is False
    assert "already been consumed" in res2.reason
