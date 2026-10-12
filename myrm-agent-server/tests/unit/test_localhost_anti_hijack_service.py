"""Unit tests for LocalhostAntiHijackService."""

from __future__ import annotations

from myrm_agent_harness.core.security.localhost_anti_hijack import HostOriginPolicy

from app.services.security.localhost_anti_hijack_service import (
    LocalhostAntiHijackService,
    get_localhost_anti_hijack_service,
)


def test_service_initialization_and_singleton() -> None:
    """Test singleton and custom service instantiation."""
    service1 = get_localhost_anti_hijack_service()
    service2 = get_localhost_anti_hijack_service()
    assert service1 is service2

    custom_service = LocalhostAntiHijackService(
        cookie_name="custom_cookie",
        cookie_max_age=3600,
    )
    assert custom_service.token_manager is not None
    assert custom_service.origin_guard is not None


def test_service_token_lifecycle() -> None:
    """Test generating, exchanging, and validating tokens via service layer."""
    service = LocalhostAntiHijackService(cookie_name="test_sess")
    record = service.generate_setup_token(ttl_seconds=60, client_binding="tauri-app")

    assert record.token is not None
    assert record.is_consumed is False

    # Exchange with correct client binding
    success, msg, cookie_spec = service.exchange_token(
        token=record.token, client_binding="tauri-app"
    )
    assert success is True
    assert cookie_spec is not None
    assert cookie_spec.cookie_name == "test_sess"
    assert cookie_spec.httponly is True
    assert cookie_spec.samesite == "strict"

    # Validate active session
    assert service.validate_session(cookie_spec.session_id) is True

    # Revoke session
    assert service.revoke_session(cookie_spec.session_id) is True
    assert service.validate_session(cookie_spec.session_id) is False


def test_service_token_rejection_cases() -> None:
    """Test rejection on client mismatch or duplicate token usage."""
    service = LocalhostAntiHijackService()
    record = service.generate_setup_token(ttl_seconds=60, client_binding="expected-id")

    # Mismatch client binding
    success1, msg1, spec1 = service.exchange_token(
        token=record.token, client_binding="wrong-id"
    )
    assert success1 is False
    assert "mismatch" in msg1
    assert spec1 is None

    # Consume with valid client
    success2, msg2, spec2 = service.exchange_token(
        token=record.token, client_binding="expected-id"
    )
    assert success2 is True
    assert spec2 is not None

    # Duplicate consumption
    success3, msg3, spec3 = service.exchange_token(token=record.token)
    assert success3 is False
    assert "already been consumed" in msg3
    assert spec3 is None


def test_service_verify_request_guard() -> None:
    """Test service request verification against DNS rebinding and cross-origin attacks."""
    service = LocalhostAntiHijackService()

    # Legitimate local request
    res_ok = service.verify_request(
        host="localhost:8000",
        origin="http://localhost:5173",
        referer="http://localhost:5173/",
        client_ip="127.0.0.1",
    )
    assert res_ok.is_allowed is True
    assert res_ok.status == "allowed"

    # DNS rebinding Host spoofing
    res_rebinding = service.verify_request(
        host="malicious-rebinding-agent.io:8000",
        origin="http://localhost:8000",
        client_ip="127.0.0.1",
    )
    assert res_rebinding.is_allowed is False
    assert res_rebinding.status == "rejected_host"

    # Untrusted external Origin
    res_origin = service.verify_request(
        host="127.0.0.1:8000",
        origin="https://external-hacker.com",
        client_ip="127.0.0.1",
    )
    assert res_origin.is_allowed is False
    assert res_origin.status == "rejected_origin"


def test_service_get_policy() -> None:
    """Test getting active policy configuration."""
    custom_policy = HostOriginPolicy(
        allowed_hosts=("127.0.0.1", "custom.local"),
        allow_null_origin=False,
    )
    service = LocalhostAntiHijackService(policy=custom_policy)
    pol = service.get_policy()
    assert "custom.local" in pol.allowed_hosts
    assert pol.allow_null_origin is False
