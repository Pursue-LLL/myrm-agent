"""Core security module tests - 80%+ coverage target.

Tests cover:
- IpPolicy CIDR validation
- fallback_events immutability
- retry_after multi-status-code support
- SecurityLimits validation
- WebhookContext data integrity
- RFC 7807/6585/7231 compliance
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.channels.security import (
    FallbackEvent,
    FallbackMode,
    IdempotencyResult,
    IpPolicy,
    SecurityLimits,
    SecurityProtocols,
    VerificationResult,
    WebhookContext,
    WebhookFailure,
    WebhookMetrics,
    WebhookResponseError,
)


class TestIpPolicyCIDRValidation:
    """Test IpPolicy CIDR format validation (P0 feature)."""

    def test_valid_ips_pass(self) -> None:
        """Valid IP addresses and CIDR blocks should pass."""
        policy = IpPolicy(
            blocked_ips=["1.2.3.4", "10.0.0.0/8", "192.168.0.0/16"],
            allowed_ips=["203.0.113.0/24"],
            trusted_proxies=["172.16.0.0/12", "10.0.0.1"],
        )
        assert len(policy.blocked_ips) == 3
        assert len(policy.allowed_ips) == 1
        assert len(policy.trusted_proxies) == 2

    def test_empty_config_passes(self) -> None:
        """Empty IP policy should pass validation."""
        policy = IpPolicy()
        assert len(policy.blocked_ips) == 0
        assert len(policy.allowed_ips) == 0
        assert len(policy.trusted_proxies) == 0

    def test_invalid_blocked_ip_raises(self) -> None:
        """Invalid IP in blocked_ips should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid blocked_ip"):
            IpPolicy(blocked_ips=["not-an-ip"])

    def test_invalid_allowed_ip_raises(self) -> None:
        """Invalid IP in allowed_ips should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid allowed_ip"):
            IpPolicy(allowed_ips=["999.999.999.999"])

    def test_invalid_trusted_proxy_raises(self) -> None:
        """Invalid IP in trusted_proxies should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid trusted_proxy"):
            IpPolicy(trusted_proxies=["invalid-proxy"])

    def test_invalid_cidr_raises(self) -> None:
        """Invalid CIDR notation should raise ValueError."""
        with pytest.raises(ValueError):
            IpPolicy(blocked_ips=["10.0.0.256/24"])

    def test_ipv6_support(self) -> None:
        """IPv6 addresses should be supported."""
        policy = IpPolicy(
            blocked_ips=["2001:db8::/32"],
            allowed_ips=["::1"],
        )
        assert len(policy.blocked_ips) == 1
        assert len(policy.allowed_ips) == 1


class TestFallbackEventsImmutability:
    """Test fallback_events tuple immutability (P0 feature)."""

    def test_fallback_events_is_tuple(self) -> None:
        """fallback_events should be a tuple, not a list."""
        event = FallbackEvent("test", "fail_open", "reason", 123.0)
        ctx = WebhookContext(
            body=b"test",
            parsed_data=None,
            timestamp=None,
            idempotency_key="k",
            client_ip="1.2.3.4",
            verification_duration_ms=1.0,
            body_read_duration_ms=1.0,
            signature_verified=False,
            idempotency_checked=False,
            fallback_events=tuple([event]),
        )
        assert isinstance(ctx.fallback_events, tuple)

    def test_fallback_events_immutable(self) -> None:
        """tuple should prevent item assignment."""
        event = FallbackEvent("test", "fail_open", "reason", 123.0)
        ctx = WebhookContext(
            body=b"test",
            parsed_data=None,
            timestamp=None,
            idempotency_key="k",
            client_ip="1.2.3.4",
            verification_duration_ms=1.0,
            body_read_duration_ms=1.0,
            signature_verified=False,
            idempotency_checked=False,
            fallback_events=tuple([event]),
        )
        with pytest.raises(TypeError):
            ctx.fallback_events[0] = event  # type: ignore

    def test_webhook_context_frozen(self) -> None:
        """WebhookContext should be frozen (immutable)."""
        ctx = WebhookContext(
            body=b"test",
            parsed_data=None,
            timestamp=None,
            idempotency_key="k",
            client_ip="1.2.3.4",
            verification_duration_ms=1.0,
            body_read_duration_ms=1.0,
            signature_verified=False,
            idempotency_checked=False,
        )
        with pytest.raises(FrozenInstanceError):
            ctx.fallback_events = tuple()  # type: ignore

    def test_empty_fallback_events_default(self) -> None:
        """Default fallback_events should be empty tuple."""
        ctx = WebhookContext(
            body=b"test",
            parsed_data=None,
            timestamp=None,
            idempotency_key="k",
            client_ip="1.2.3.4",
            verification_duration_ms=1.0,
            body_read_duration_ms=1.0,
            signature_verified=False,
            idempotency_checked=False,
        )
        assert ctx.fallback_events == tuple()
        assert len(ctx.fallback_events) == 0

    def test_multiple_fallback_events(self) -> None:
        """Multiple fallback events should be preserved in order."""
        events = [
            FallbackEvent("verifier", "fail_open", "timeout", 100.0),
            FallbackEvent("store", "degraded", "redis down", 101.0),
        ]
        ctx = WebhookContext(
            body=b"test",
            parsed_data=None,
            timestamp=None,
            idempotency_key="k",
            client_ip="1.2.3.4",
            verification_duration_ms=1.0,
            body_read_duration_ms=1.0,
            signature_verified=False,
            idempotency_checked=False,
            fallback_events=tuple(events),
        )
        assert len(ctx.fallback_events) == 2
        assert ctx.fallback_events[0].component == "verifier"
        assert ctx.fallback_events[1].component == "store"


class TestRetryAfterMultiStatusCode:
    """Test retry_after support for multiple HTTP status codes (P1 feature)."""

    def test_429_with_retry_after(self) -> None:
        """429 status should include retry_after."""
        err = WebhookResponseError(
            status_code=429,
            error_type="rate-limit",
            title="Rate Limited",
            detail="Too many requests",
            trace_id="test-429",
            retry_after=60,
        )
        result = err.to_dict()
        assert "retry_after" in result
        assert result["retry_after"] == 60

    def test_503_with_retry_after(self) -> None:
        """503 status should support retry_after (RFC 7231)."""
        err = WebhookResponseError(
            status_code=503,
            error_type="maintenance",
            title="Service Unavailable",
            detail="Scheduled maintenance",
            trace_id="test-503",
            retry_after=300,
        )
        result = err.to_dict()
        assert "retry_after" in result
        assert result["retry_after"] == 300

    def test_504_with_retry_after(self) -> None:
        """504 Gateway Timeout should support retry_after."""
        err = WebhookResponseError(
            status_code=504,
            error_type="gateway-timeout",
            title="Gateway Timeout",
            detail="Upstream timeout",
            trace_id="test-504",
            retry_after=30,
        )
        result = err.to_dict()
        assert "retry_after" in result
        assert result["retry_after"] == 30

    def test_retry_after_none_not_included(self) -> None:
        """retry_after=None should not be included in response."""
        err = WebhookResponseError(
            status_code=429,
            error_type="rate-limit",
            title="Rate Limited",
            detail="Too many requests",
            trace_id="test-none",
            retry_after=None,
        )
        result = err.to_dict()
        assert "retry_after" not in result

    def test_401_without_retry_after(self) -> None:
        """4xx errors without retry_after should not include the field."""
        err = WebhookResponseError(
            status_code=401,
            error_type="unauthorized",
            title="Unauthorized",
            detail="Invalid signature",
            trace_id="test-401",
        )
        result = err.to_dict()
        assert "retry_after" not in result


class TestSecurityLimitsValidation:
    """Test SecurityLimits configuration validation."""

    def test_valid_limits_pass(self) -> None:
        """Valid security limits should pass validation."""
        limits = SecurityLimits(
            body_limit_pre_auth=64 * 1024,
            body_limit_post_auth=10 * 1024 * 1024,
            read_timeout_seconds=10.0,
            max_timestamp_age_seconds=300,
            clock_skew_seconds=60,
            rate_limit_per_minute=60,
            inflight_max_concurrent=8,
        )
        assert limits.body_limit_pre_auth == 64 * 1024
        assert limits.inflight_max_concurrent == 8

    def test_negative_body_limit_raises(self) -> None:
        """Negative body limit should raise ValueError."""
        with pytest.raises(ValueError, match="body_limit_pre_auth"):
            SecurityLimits(body_limit_pre_auth=-1)

    def test_negative_timeout_raises(self) -> None:
        """Negative timeout should raise ValueError."""
        with pytest.raises(ValueError, match="read_timeout_seconds"):
            SecurityLimits(read_timeout_seconds=-1.0)

    def test_negative_rate_limit_raises(self) -> None:
        """Negative rate limit should raise ValueError."""
        with pytest.raises(ValueError, match="rate_limit_per_minute"):
            SecurityLimits(rate_limit_per_minute=-1)

    def test_pre_auth_exceeds_post_auth_raises(self) -> None:
        """Pre-auth limit > post-auth limit should raise ValueError."""
        with pytest.raises(ValueError, match="must >= body_limit_pre_auth"):
            SecurityLimits(
                body_limit_pre_auth=10 * 1024 * 1024,
                body_limit_post_auth=1 * 1024 * 1024,
            )


class TestWebhookContextDataIntegrity:
    """Test WebhookContext data completeness."""

    def test_minimal_context_creation(self) -> None:
        """Minimal WebhookContext with required fields."""
        ctx = WebhookContext(
            body=b"test",
            parsed_data=None,
            timestamp=None,
            idempotency_key="k",
            client_ip="1.2.3.4",
            verification_duration_ms=1.0,
            body_read_duration_ms=1.0,
            signature_verified=False,
            idempotency_checked=False,
        )
        assert ctx.body == b"test"
        assert ctx.client_ip == "1.2.3.4"
        assert ctx.trace_id  # Auto-generated

    def test_full_context_creation(self) -> None:
        """Full WebhookContext with all fields."""
        ctx = WebhookContext(
            body=b'{"test": "data"}',
            parsed_data={"test": "data"},
            timestamp=1234567890,
            idempotency_key="key-123",
            client_ip="203.0.113.45",
            verification_duration_ms=123.4,
            body_read_duration_ms=56.7,
            signature_verified=True,
            idempotency_checked=True,
            is_replay=True,
            replay_detected_at=1234567891.0,
            fallback_events=tuple(),
            trace_id="custom-trace-id",
        )
        assert ctx.timestamp == 1234567890
        assert ctx.is_replay is True
        assert ctx.trace_id == "custom-trace-id"

    def test_get_json_with_data(self) -> None:
        """get_json() should return parsed_data when available."""
        ctx = WebhookContext(
            body=b'{"key": "value"}',
            parsed_data={"key": "value"},
            timestamp=None,
            idempotency_key="k",
            client_ip="1.2.3.4",
            verification_duration_ms=1.0,
            body_read_duration_ms=1.0,
            signature_verified=False,
            idempotency_checked=False,
        )
        assert ctx.get_json() == {"key": "value"}

    def test_get_json_without_data_raises(self) -> None:
        """get_json() should raise ValueError when parsed_data is None."""
        ctx = WebhookContext(
            body=b"not json",
            parsed_data=None,
            timestamp=None,
            idempotency_key="k",
            client_ip="1.2.3.4",
            verification_duration_ms=1.0,
            body_read_duration_ms=1.0,
            signature_verified=False,
            idempotency_checked=False,
        )
        with pytest.raises(ValueError, match="not valid JSON"):
            ctx.get_json()


class TestRFC7807Compliance:
    """Test RFC 7807 Problem Details compliance."""

    def test_error_response_structure(self) -> None:
        """Error response should contain all RFC 7807 fields."""
        err = WebhookResponseError(
            status_code=400,
            error_type="invalid-request",
            title="Invalid Request",
            detail="Missing required header",
            trace_id="trace-123",
        )
        result = err.to_dict()

        # RFC 7807 required fields
        assert "type" in result
        assert "title" in result
        assert "status" in result
        assert "detail" in result

        # Additional fields
        assert "timestamp" in result
        assert "trace_id" in result

    def test_trace_id_always_included(self) -> None:
        """trace_id should always be included in error response."""
        err = WebhookResponseError(
            status_code=500,
            error_type="internal-error",
            title="Internal Error",
            detail="Something went wrong",
            trace_id="mandatory-trace",
        )
        result = err.to_dict()
        assert result["trace_id"] == "mandatory-trace"


class TestDataClassImmutability:
    """Test immutability of all frozen dataclasses."""

    def test_verification_result_frozen(self) -> None:
        """VerificationResult should be immutable."""
        result = VerificationResult(verified=True, duration_ms=10.0)
        with pytest.raises(FrozenInstanceError):
            result.verified = False  # type: ignore

    def test_idempotency_result_frozen(self) -> None:
        """IdempotencyResult should be immutable."""
        result = IdempotencyResult(
            checked=True,
            duration_ms=5.0,
            is_replay=False,
        )
        with pytest.raises(FrozenInstanceError):
            result.is_replay = True  # type: ignore

    def test_webhook_metrics_frozen(self) -> None:
        """WebhookMetrics should be immutable."""
        metrics = WebhookMetrics(
            channel="test",
            body_size=100,
            total_duration_seconds=0.1,
            body_read_ms=10.0,
            client_ip="1.2.3.4",
            request_path="/webhook",
        )
        with pytest.raises(FrozenInstanceError):
            metrics.body_size = 200  # type: ignore

    def test_webhook_failure_frozen(self) -> None:
        """WebhookFailure should be immutable."""
        failure = WebhookFailure(
            channel="test",
            error_type="rate-limit",
            client_ip="1.2.3.4",
            body_size=100,
            request_path="/webhook",
        )
        with pytest.raises(FrozenInstanceError):
            failure.error_type = "other"  # type: ignore


class TestSecurityProtocolsConfiguration:
    """Test SecurityProtocols configuration object."""

    def test_empty_protocols(self) -> None:
        """SecurityProtocols with all None values should be valid."""
        protocols = SecurityProtocols()
        assert protocols.signature_verifier is None
        assert protocols.idempotency_store is None
        assert protocols.metrics_collector is None
        assert protocols.fallback_strategy is None

    def test_protocols_frozen(self) -> None:
        """SecurityProtocols should be immutable."""
        protocols = SecurityProtocols()
        with pytest.raises(FrozenInstanceError):
            protocols.signature_verifier = None  # type: ignore


class TestFallbackMode:
    """Test FallbackMode enum."""

    def test_fallback_modes_exist(self) -> None:
        """All fallback modes should be accessible."""
        assert FallbackMode.FAIL_CLOSED
        assert FallbackMode.FAIL_OPEN
        assert FallbackMode.DEGRADED

    def test_fallback_mode_values(self) -> None:
        """Fallback modes should have expected values."""
        assert FallbackMode.FAIL_CLOSED.value == "fail_closed"
        assert FallbackMode.FAIL_OPEN.value == "fail_open"
        assert FallbackMode.DEGRADED.value == "degraded"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
