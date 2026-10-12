"""
Unit tests for BrowserHumanHandoffService.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest

from app.schemas.browser_human_handoff import (
    AcquireBrowserLeaseRequest,
    InspectPageSafetyRequest,
    ReleaseBrowserLeaseRequest,
    ResolveHandoffRequest,
)
from app.services.security.browser_human_handoff_service import (
    BrowserHumanHandoffService,
)


def test_service_inspect_page_safety_captcha() -> None:
    service = BrowserHumanHandoffService()

    # 1. Cloudflare turnstile inspection
    req = InspectPageSafetyRequest(
        html_or_dom="<html><body><div id='cf-turnstile'>Security Check</div></body></html>",
        url="https://app.example.com/login",
    )
    res = service.inspect_page_safety(req)
    assert res.interception.is_handoff_required is True
    assert res.interception.trigger_type == "CAPTCHA_CHALLENGE"
    assert res.health.is_corrupted_zero_content is False

    # 2. List pending
    pending = service.list_pending_handoffs()
    assert len(pending) == 1
    assert pending[0].interception_id == res.interception.interception_id

    # 3. Resolve handoff
    resolve_res = service.resolve_handoff(
        ResolveHandoffRequest(interception_id=res.interception.interception_id)
    )
    assert resolve_res.is_resolved is True
    assert resolve_res.is_handoff_required is False
    assert len(service.list_pending_handoffs()) == 0


def test_service_inspect_page_safety_whiteout() -> None:
    service = BrowserHumanHandoffService()

    req = InspectPageSafetyRequest(
        html_or_dom="<html><body>     </body></html>",
        url="https://portal.example.com",
    )
    res = service.inspect_page_safety(req)
    assert res.interception.is_handoff_required is True
    assert res.interception.trigger_type == "ZERO_CONTENT_CORRUPTION"
    assert res.health.is_corrupted_zero_content is True


def test_service_lease_lifecycle() -> None:
    service = BrowserHumanHandoffService()

    # 1. Acquire lease
    acq_req = AcquireBrowserLeaseRequest(
        profile_name="personal-chrome",
        consumer_id="claude-runner-1",
        ttl_seconds=120.0,
    )
    lease = service.acquire_lease(acq_req)
    assert lease.status == "LEASED"
    assert lease.consumer_id == "claude-runner-1"

    # 2. Query active lease
    active = service.get_active_lease("personal-chrome")
    assert active is not None
    assert active.lease_id == lease.lease_id

    # 3. Collision raises RuntimeError
    with pytest.raises(RuntimeError):
        service.acquire_lease(
            AcquireBrowserLeaseRequest(
                profile_name="personal-chrome",
                consumer_id="cursor-runner-2",
            )
        )

    # 4. Release lease
    rel = service.release_lease(ReleaseBrowserLeaseRequest(lease_id=lease.lease_id))
    assert rel.status == "RELEASED"
    assert service.get_active_lease("personal-chrome") is None

    # 5. Check metrics
    metrics = service.get_metrics()
    assert metrics.browser_leases_granted_total == 1
    assert metrics.browser_leases_released_total == 1
