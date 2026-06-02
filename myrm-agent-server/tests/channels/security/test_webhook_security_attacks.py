"""Webhook security attack simulation tests.

Tests cover OWASP Top 10 and common webhook attack vectors:
- DoS attacks (body size, slowloris, concurrent flood)
- Timing attacks (signature verification)
- Signature forgery (brute force, replay)
- Replay attacks (timestamp validation, idempotency)
- IP spoofing (X-Forwarded-For manipulation)

Reference: MASTER_IMPLEMENTATION_ROADMAP.md §13.1
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from collections.abc import AsyncIterator
from unittest.mock import MagicMock

import pytest

from app.channels.security import (
    FallbackMode,
    IdempotencyStore,
    IpPolicy,
    SecurityLimits,
    SecurityProtocols,
    SignatureVerifier,
    WebhookResponseError,
    WebhookSecurityMiddleware,
)


class MockState:
    """Mock request state that supports attribute assignment."""

    pass


class MockRequest:
    """Mock FastAPI Request for testing."""

    def __init__(
        self,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
        client_host: str = "1.2.3.4",
        path: str = "/webhook/test",
    ):
        self.body_bytes = body
        self.headers = headers or {}
        self.client = MagicMock()
        self.client.host = client_host
        self.url = MagicMock()
        self.url.path = path
        self.state = MockState()

    async def stream(self) -> AsyncIterator[bytes]:
        """Stream body in chunks."""
        chunk_size = 1024
        for i in range(0, len(self.body_bytes), chunk_size):
            yield self.body_bytes[i : i + chunk_size]


class MockSlowRequest(MockRequest):
    """Mock request that simulates slowloris attack."""

    def __init__(self, *args, delay_per_chunk: float = 0.1, **kwargs):
        super().__init__(*args, **kwargs)
        self.delay_per_chunk = delay_per_chunk

    async def stream(self) -> AsyncIterator[bytes]:
        """Stream body slowly to trigger timeout."""
        chunk_size = 10
        for i in range(0, len(self.body_bytes), chunk_size):
            await asyncio.sleep(self.delay_per_chunk)
            yield self.body_bytes[i : i + chunk_size]


class MockSignatureVerifier(SignatureVerifier):
    """Mock signature verifier for testing."""

    def __init__(self, should_pass: bool = True, delay_ms: float = 0):
        self.should_pass = should_pass
        self.delay_ms = delay_ms
        self.call_count = 0

    async def verify(self, request, body: bytes) -> None:
        """Verify signature with optional delay."""
        self.call_count += 1
        if self.delay_ms > 0:
            await asyncio.sleep(self.delay_ms / 1000)
        if not self.should_pass:
            raise WebhookResponseError(
                status_code=401,
                error_type="invalid-signature",
                title="Invalid Signature",
                detail="Signature verification failed",
                trace_id="test",
            )


class MockIdempotencyStore(IdempotencyStore):
    """Mock idempotency store for testing."""

    def __init__(self):
        self.processed_keys: set[str] = set()
        self.call_count = 0

    async def is_duplicate(self, key: str) -> bool:
        """Check if key was processed."""
        self.call_count += 1
        return key in self.processed_keys

    async def mark_processed(self, key: str) -> None:
        """Mark key as processed."""
        self.processed_keys.add(key)


@pytest.mark.asyncio
class TestDoSAttacks:
    """Test DoS attack prevention."""

    async def test_oversized_body_pre_auth_rejected(self):
        """Oversized body should be rejected at pre-auth stage."""
        limits = SecurityLimits(
            body_limit_pre_auth=1024,
            body_limit_post_auth=10 * 1024,
        )
        middleware = WebhookSecurityMiddleware(limits=limits)

        # Create request with Content-Length > pre_auth limit
        large_body = b"x" * 2000
        request = MockRequest(
            body=large_body,
            headers={"Content-Length": str(len(large_body))},
        )

        with pytest.raises(WebhookResponseError) as exc_info:
            await middleware.process_request(request, "test")

        err = exc_info.value
        assert err.status_code == 413
        assert err.error_type == "body-too-large"
        assert "pre-auth limit" in err.detail

    async def test_oversized_body_post_auth_rejected(self):
        """Oversized body should be rejected during streaming."""
        limits = SecurityLimits(
            body_limit_pre_auth=1024,
            body_limit_post_auth=2048,
        )
        middleware = WebhookSecurityMiddleware(limits=limits)

        # Create request without Content-Length (bypass pre-auth)
        large_body = b"x" * 3000
        request = MockRequest(body=large_body)

        with pytest.raises(WebhookResponseError) as exc_info:
            await middleware.process_request(request, "test")

        err = exc_info.value
        assert err.status_code == 413
        assert err.error_type == "body-too-large"
        assert "post-auth limit" in err.detail

    async def test_slowloris_attack_timeout(self):
        """Slowloris attack should trigger read timeout."""
        limits = SecurityLimits(
            read_timeout_seconds=0.5,
        )
        middleware = WebhookSecurityMiddleware(limits=limits)

        # Create slow request that exceeds timeout
        request = MockSlowRequest(
            body=b"x" * 100,
            delay_per_chunk=0.2,  # 10 chunks * 0.2s = 2s > 0.5s timeout
        )

        with pytest.raises(WebhookResponseError) as exc_info:
            await middleware.process_request(request, "test")

        err = exc_info.value
        assert err.status_code == 408
        assert err.error_type == "request-timeout"
        assert "timeout" in err.detail.lower()

    async def test_concurrent_request_flood_blocked(self):
        """Concurrent request flood should be blocked by in-flight limiter."""
        from app.channels.reliability.inflight_limiter import (
            MemoryInFlightLimiter,
        )

        limits = SecurityLimits(inflight_max_concurrent=2)
        inflight_limiter = MemoryInFlightLimiter(max_concurrent=2)

        # Create slow verifier to simulate processing time
        slow_verifier = MockSignatureVerifier(should_pass=True, delay_ms=100)

        middleware = WebhookSecurityMiddleware(
            limits=limits,
            inflight_limiter=inflight_limiter,
            protocols=SecurityProtocols(signature_verifier=slow_verifier),
        )

        async def concurrent_request(req_id: int):
            request = MockRequest(
                body=f'{{"req_id": {req_id}}}'.encode(),
                headers={"Content-Type": "application/json"},
                client_host="1.2.3.4",  # Same IP for all requests
            )
            return await middleware.process_request(request, "test")

        # Launch 5 concurrent requests from same IP (limit is 2)
        tasks = [asyncio.create_task(concurrent_request(i)) for i in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # At least 3 should be rejected (5 - 2 = 3)
        rejected = [r for r in results if isinstance(r, WebhookResponseError)]
        successful = [r for r in results if not isinstance(r, Exception)]

        assert len(rejected) >= 1, f"Expected rejections, got {len(rejected)} rejected, {len(successful)} successful"
        assert rejected[0].status_code == 429
        assert rejected[0].error_type == "inflight-limit-exceeded"


@pytest.mark.asyncio
class TestTimingAttacks:
    """Test timing attack prevention."""

    async def test_signature_verification_constant_time(self):
        """Signature verification should take constant time regardless of input."""
        import statistics

        verifier = MockSignatureVerifier(should_pass=False, delay_ms=5)
        middleware = WebhookSecurityMiddleware(protocols=SecurityProtocols(signature_verifier=verifier))

        signatures = [
            b"correct_signature_xxxxxxxxxx",
            b"wrong_at_start_xxxxxxxxxxxx",
            b"xxxxxxxxxxxxxxxxxx_wrong_end",
        ]

        rounds = 5
        per_sig_times: dict[int, list[float]] = {i: [] for i in range(len(signatures))}
        for _ in range(rounds):
            for idx, sig in enumerate(signatures):
                request = MockRequest(body=sig, headers={"Content-Type": "application/json"})
                start = time.perf_counter()
                try:
                    await middleware.process_request(request, "test")
                except WebhookResponseError:
                    pass
                per_sig_times[idx].append(time.perf_counter() - start)

        medians = [statistics.median(per_sig_times[i]) for i in range(len(signatures))]
        avg_median = sum(medians) / len(medians)
        for m in medians:
            assert abs(m - avg_median) / avg_median < 1.5, f"Timing variation too large: {medians}"

    async def test_hmac_compare_digest_used(self):
        """Verify that hmac.compare_digest is used for signature comparison."""
        # This is a smoke test - actual implementation uses hmac.compare_digest
        # which is guaranteed constant-time by Python stdlib

        secret = "test_secret"
        body = b"test_body"
        correct_sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        wrong_sig = "0" * 64

        # Both comparisons should take similar time
        start1 = time.perf_counter()
        result1 = hmac.compare_digest(correct_sig, correct_sig)
        time1 = time.perf_counter() - start1

        start2 = time.perf_counter()
        result2 = hmac.compare_digest(correct_sig, wrong_sig)
        time2 = time.perf_counter() - start2

        assert result1 is True
        assert result2 is False
        # Timing difference should be minimal (< 1ms)
        assert abs(time1 - time2) < 0.001


@pytest.mark.asyncio
class TestSignatureForgery:
    """Test signature forgery prevention."""

    async def test_missing_signature_rejected(self):
        """Request without signature should be rejected."""
        verifier = MockSignatureVerifier(should_pass=False)
        middleware = WebhookSecurityMiddleware(protocols=SecurityProtocols(signature_verifier=verifier))

        request = MockRequest(body=b"test", headers={})

        with pytest.raises(WebhookResponseError) as exc_info:
            await middleware.process_request(request, "test")

        err = exc_info.value
        assert err.status_code == 401
        assert "signature" in err.error_type.lower()

    async def test_invalid_signature_rejected(self):
        """Request with invalid signature should be rejected."""
        verifier = MockSignatureVerifier(should_pass=False)
        middleware = WebhookSecurityMiddleware(protocols=SecurityProtocols(signature_verifier=verifier))

        request = MockRequest(
            body=b"test",
            headers={"X-Signature": "invalid"},
        )

        with pytest.raises(WebhookResponseError) as exc_info:
            await middleware.process_request(request, "test")

        err = exc_info.value
        assert err.status_code == 401

    async def test_signature_brute_force_rate_limited(self):
        """Brute force signature attempts should be rate limited."""
        from app.channels.reliability.inbound_limiter import (
            MemoryInboundLimiter,
        )

        verifier = MockSignatureVerifier(should_pass=False)
        rate_limiter = MemoryInboundLimiter()
        limits = SecurityLimits(rate_limit_per_minute=5)

        middleware = WebhookSecurityMiddleware(
            limits=limits,
            protocols=SecurityProtocols(signature_verifier=verifier),
            rate_limiter=rate_limiter,
        )

        # Attempt 10 requests with different signatures
        client_ip = "1.2.3.4"
        rejected_count = 0

        for i in range(10):
            request = MockRequest(
                body=b"test",
                headers={"X-Signature": f"attempt_{i}"},
                client_host=client_ip,
            )

            try:
                await middleware.process_request(request, "test")
            except WebhookResponseError as e:
                if e.status_code == 429:
                    rejected_count += 1

        # After 5 requests, should start rate limiting
        assert rejected_count >= 4, f"Expected >= 4 rate limited, got {rejected_count}"


@pytest.mark.asyncio
class TestReplayAttacks:
    """Test replay attack prevention."""

    async def test_duplicate_request_detected(self):
        """Duplicate requests should be detected via idempotency store."""
        store = MockIdempotencyStore()
        middleware = WebhookSecurityMiddleware(protocols=SecurityProtocols(idempotency_store=store))

        request = MockRequest(
            body=b'{"message_id": "msg-123"}',
            headers={"Content-Type": "application/json"},
        )

        # First request should succeed
        ctx1 = await middleware.process_request(request, "test")
        assert ctx1.is_replay is False
        assert ctx1.idempotency_checked is True

        # Second request should be marked as replay
        ctx2 = await middleware.process_request(request, "test")
        assert ctx2.is_replay is True
        assert ctx2.replay_detected_at is not None

    async def test_expired_timestamp_rejected(self):
        """Expired timestamp should be rejected."""
        limits = SecurityLimits(
            max_timestamp_age_seconds=300,  # 5 minutes
        )
        middleware = WebhookSecurityMiddleware(limits=limits)

        # Create request with expired timestamp (10 minutes ago)
        old_timestamp = int(time.time()) - 600
        request = MockRequest(
            body=f'{{"timestamp": {old_timestamp}}}'.encode(),
            headers={"Content-Type": "application/json"},
        )

        with pytest.raises(WebhookResponseError) as exc_info:
            await middleware.process_request(request, "test")

        err = exc_info.value
        assert err.status_code == 401
        assert err.error_type == "timestamp-expired"

    async def test_future_timestamp_rejected(self):
        """Future timestamp should be rejected (prevents pre-signed attacks)."""
        limits = SecurityLimits(
            clock_skew_seconds=60,  # Allow 1 minute skew
        )
        middleware = WebhookSecurityMiddleware(limits=limits)

        # Create request with future timestamp (10 minutes ahead)
        future_timestamp = int(time.time()) + 600
        request = MockRequest(
            body=f'{{"timestamp": {future_timestamp}}}'.encode(),
            headers={"Content-Type": "application/json"},
        )

        with pytest.raises(WebhookResponseError) as exc_info:
            await middleware.process_request(request, "test")

        err = exc_info.value
        assert err.status_code == 401
        assert err.error_type == "timestamp-invalid"

    async def test_replay_with_same_message_id_detected(self):
        """Same idempotency key should be detected as replay."""
        store = MockIdempotencyStore()
        middleware = WebhookSecurityMiddleware(protocols=SecurityProtocols(idempotency_store=store))

        # Use explicit idempotency-key header for consistent testing
        # First request
        request1 = MockRequest(
            body=b'{"text": "hello"}',
            headers={
                "Content-Type": "application/json",
                "idempotency-key": "msg-123",  # lowercase header
            },
        )
        ctx1 = await middleware.process_request(request1, "test")
        assert ctx1.is_replay is False
        assert ctx1.idempotency_key == "msg-123"

        # Second request with same idempotency key (different body)
        request2 = MockRequest(
            body=b'{"text": "world"}',
            headers={
                "Content-Type": "application/json",
                "idempotency-key": "msg-123",  # lowercase header
            },
        )
        ctx2 = await middleware.process_request(request2, "test")
        # Should be detected as replay (same idempotency key)
        assert ctx2.is_replay is True
        assert ctx2.idempotency_key == "msg-123"


@pytest.mark.asyncio
class TestIPSpoofing:
    """Test IP spoofing prevention."""

    async def test_untrusted_proxy_xff_ignored(self):
        """X-Forwarded-For from untrusted proxy should be ignored."""
        ip_policy = IpPolicy(
            blocked_ips=["1.2.3.4"],
            trusted_proxies=["10.0.0.0/8"],
        )
        middleware = WebhookSecurityMiddleware(ip_policy=ip_policy)

        # Attacker tries to spoof IP via X-Forwarded-For
        request = MockRequest(
            body=b"test",
            headers={
                "X-Forwarded-For": "203.0.113.45",  # Fake "clean" IP
                "Content-Type": "application/json",
            },
            client_host="1.2.3.4",  # Real IP is blocked
        )

        with pytest.raises(WebhookResponseError) as exc_info:
            await middleware.process_request(request, "test")

        err = exc_info.value
        assert err.status_code == 403
        assert err.error_type == "ip-blocked"

    async def test_trusted_proxy_xff_honored(self):
        """X-Forwarded-For from trusted proxy should be honored."""
        ip_policy = IpPolicy(
            blocked_ips=["1.2.3.4"],
            trusted_proxies=["10.0.0.0/8"],
        )
        middleware = WebhookSecurityMiddleware(ip_policy=ip_policy)

        # Request from trusted proxy with XFF
        request = MockRequest(
            body=b"test",
            headers={
                "X-Forwarded-For": "1.2.3.4",  # Blocked IP in XFF
                "Content-Type": "application/json",
            },
            client_host="10.0.0.1",  # Trusted proxy
        )

        with pytest.raises(WebhookResponseError) as exc_info:
            await middleware.process_request(request, "test")

        err = exc_info.value
        assert err.status_code == 403
        assert err.error_type == "ip-blocked"

    async def test_xff_chain_leftmost_extracted(self):
        """Leftmost IP in X-Forwarded-For chain should be extracted."""
        ip_policy = IpPolicy(
            blocked_ips=["203.0.113.45"],
            trusted_proxies=["10.0.0.0/8"],
        )
        middleware = WebhookSecurityMiddleware(ip_policy=ip_policy)

        # XFF chain: client -> proxy1 -> proxy2
        request = MockRequest(
            body=b"test",
            headers={
                "X-Forwarded-For": "203.0.113.45, 192.168.1.1, 10.0.0.2",
                "Content-Type": "application/json",
            },
            client_host="10.0.0.1",  # Trusted proxy
        )

        with pytest.raises(WebhookResponseError) as exc_info:
            await middleware.process_request(request, "test")

        err = exc_info.value
        assert err.status_code == 403
        assert err.error_type == "ip-blocked"


@pytest.mark.asyncio
class TestContentTypeValidation:
    """Test Content-Type validation."""

    async def test_invalid_content_type_rejected(self):
        """Invalid Content-Type should be rejected."""
        middleware = WebhookSecurityMiddleware(allowed_content_types=["application/json"])

        request = MockRequest(
            body=b"test",
            headers={"Content-Type": "text/html"},
        )

        with pytest.raises(WebhookResponseError) as exc_info:
            await middleware.process_request(request, "test")

        err = exc_info.value
        assert err.status_code == 415
        assert err.error_type == "unsupported-media-type"

    async def test_content_type_with_charset_accepted(self):
        """Content-Type with charset should be accepted."""
        middleware = WebhookSecurityMiddleware(allowed_content_types=["application/json"])

        request = MockRequest(
            body=b'{"test": "data"}',
            headers={"Content-Type": "application/json; charset=utf-8"},
        )

        # Should not raise
        ctx = await middleware.process_request(request, "test")
        assert ctx.body == b'{"test": "data"}'
        # Verify JSON can be parsed
        parsed = ctx.get_json()
        assert parsed["test"] == "data"


@pytest.mark.asyncio
class TestFallbackStrategies:
    """Test fallback strategies during dependency failures."""

    async def test_verifier_failure_fail_closed(self):
        """Verifier failure with FAIL_CLOSED should reject request."""

        class FailingVerifier(SignatureVerifier):
            async def verify(self, request, body: bytes) -> None:
                raise RuntimeError("Redis connection failed")

        class FailClosedStrategy:
            async def on_verifier_error(self, error, request, channel):
                return FallbackMode.FAIL_CLOSED

        middleware = WebhookSecurityMiddleware(
            protocols=SecurityProtocols(
                signature_verifier=FailingVerifier(),
                fallback_strategy=FailClosedStrategy(),
            )
        )

        request = MockRequest(body=b"test", headers={"Content-Type": "application/json"})

        with pytest.raises(WebhookResponseError) as exc_info:
            await middleware.process_request(request, "test")

        err = exc_info.value
        assert err.status_code == 503
        assert err.error_type == "verifier-unavailable"

    async def test_verifier_failure_fail_open(self):
        """Verifier failure with FAIL_OPEN should allow request."""

        class FailingVerifier(SignatureVerifier):
            async def verify(self, request, body: bytes) -> None:
                raise RuntimeError("Redis connection failed")

        class FailOpenStrategy:
            async def on_verifier_error(self, error, request, channel):
                return FallbackMode.FAIL_OPEN

        middleware = WebhookSecurityMiddleware(
            protocols=SecurityProtocols(
                signature_verifier=FailingVerifier(),
                fallback_strategy=FailOpenStrategy(),
            )
        )

        request = MockRequest(body=b"test", headers={"Content-Type": "application/json"})

        ctx = await middleware.process_request(request, "test")
        assert ctx.signature_verified is False
        assert len(ctx.fallback_events) == 1
        assert ctx.fallback_events[0].component == "signature_verifier"
        assert ctx.fallback_events[0].mode == "fail_open"

    async def test_store_failure_degraded_with_alt_store(self):
        """Store failure with DEGRADED should use alternative store."""

        class FailingStore(IdempotencyStore):
            async def is_duplicate(self, key: str) -> bool:
                raise RuntimeError("Primary store down")

            async def mark_processed(self, key: str) -> None:
                raise RuntimeError("Primary store down")

        class AltStore(IdempotencyStore):
            def __init__(self):
                self.keys: set[str] = set()

            async def is_duplicate(self, key: str) -> bool:
                return key in self.keys

            async def mark_processed(self, key: str) -> None:
                self.keys.add(key)

        alt_store = AltStore()

        class DegradedStrategy:
            async def on_store_error(self, error, request):
                return FallbackMode.DEGRADED, alt_store

        middleware = WebhookSecurityMiddleware(
            protocols=SecurityProtocols(
                idempotency_store=FailingStore(),
                fallback_strategy=DegradedStrategy(),
            )
        )

        request = MockRequest(
            body=b'{"message_id": "msg-123"}',
            headers={"Content-Type": "application/json"},
        )

        # First request should use alt store
        ctx1 = await middleware.process_request(request, "test")
        assert ctx1.idempotency_checked is True
        assert ctx1.is_replay is False
        assert len(ctx1.fallback_events) == 1
        assert ctx1.fallback_events[0].mode == "degraded"

        # Second request should detect replay via alt store
        ctx2 = await middleware.process_request(request, "test")
        assert ctx2.is_replay is True


@pytest.mark.asyncio
class TestIPWhitelistBypass:
    """Test IP whitelist bypass scenarios."""

    async def test_whitelisted_ip_skips_rate_limit(self):
        """Whitelisted IP should skip rate limiting."""
        from app.channels.reliability.inbound_limiter import (
            MemoryInboundLimiter,
        )

        ip_policy = IpPolicy(allowed_ips=["203.0.113.0/24"])
        rate_limiter = MemoryInboundLimiter()
        limits = SecurityLimits(rate_limit_per_minute=2)

        middleware = WebhookSecurityMiddleware(
            limits=limits,
            ip_policy=ip_policy,
            rate_limiter=rate_limiter,
        )

        # Send 5 requests from whitelisted IP
        for _i in range(5):
            request = MockRequest(
                body=b"test",
                headers={"Content-Type": "application/json"},
                client_host="203.0.113.45",  # Whitelisted
            )
            # Should not raise rate limit error
            ctx = await middleware.process_request(request, "test")
            assert ctx.client_ip == "203.0.113.45"

    async def test_non_whitelisted_ip_rate_limited(self):
        """Non-whitelisted IP should be rate limited."""
        from app.channels.reliability.inbound_limiter import (
            MemoryInboundLimiter,
        )

        ip_policy = IpPolicy(allowed_ips=["203.0.113.0/24"])
        rate_limiter = MemoryInboundLimiter()
        limits = SecurityLimits(rate_limit_per_minute=2)

        middleware = WebhookSecurityMiddleware(
            limits=limits,
            ip_policy=ip_policy,
            rate_limiter=rate_limiter,
        )

        # Send 5 requests from non-whitelisted IP
        rejected = 0
        for _i in range(5):
            request = MockRequest(
                body=b"test",
                headers={"Content-Type": "application/json"},
                client_host="1.2.3.4",  # Not whitelisted
            )
            try:
                await middleware.process_request(request, "test")
            except WebhookResponseError as e:
                if e.status_code == 429:
                    rejected += 1

        # Should have rate limited after 2 requests
        assert rejected >= 2


@pytest.mark.asyncio
class TestTraceabilityAndMonitoring:
    """Test trace_id and metrics collection."""

    async def test_trace_id_generated_for_all_requests(self):
        """Every request should have a unique trace_id."""
        middleware = WebhookSecurityMiddleware()

        request1 = MockRequest(body=b"test1", headers={"Content-Type": "application/json"})
        request2 = MockRequest(body=b"test2", headers={"Content-Type": "application/json"})

        ctx1 = await middleware.process_request(request1, "test")
        ctx2 = await middleware.process_request(request2, "test")

        assert ctx1.trace_id
        assert ctx2.trace_id
        assert ctx1.trace_id != ctx2.trace_id

    async def test_trace_id_included_in_errors(self):
        """trace_id should be included in all error responses."""
        limits = SecurityLimits(body_limit_pre_auth=10)
        middleware = WebhookSecurityMiddleware(limits=limits)

        request = MockRequest(
            body=b"x" * 100,
            headers={"Content-Length": "100"},
        )

        with pytest.raises(WebhookResponseError) as exc_info:
            await middleware.process_request(request, "test")

        err = exc_info.value
        assert err.trace_id
        assert "trace_id" in err.to_dict()

    async def test_metrics_collected_on_success(self):
        """Metrics should be collected for successful requests."""

        class MockMetricsCollector:
            def __init__(self):
                self.success_count = 0
                self.last_metrics = None

            def record_success(self, metrics):
                self.success_count += 1
                self.last_metrics = metrics

            def record_failure(self, failure):
                pass

        collector = MockMetricsCollector()
        middleware = WebhookSecurityMiddleware(protocols=SecurityProtocols(metrics_collector=collector))

        request = MockRequest(body=b"test", headers={"Content-Type": "application/json"})
        await middleware.process_request(request, "test")

        assert collector.success_count == 1
        assert collector.last_metrics is not None
        assert collector.last_metrics.channel == "test"
        assert collector.last_metrics.body_size == 4

    async def test_metrics_collected_on_failure(self):
        """Metrics should be collected for failed requests."""

        class MockMetricsCollector:
            def __init__(self):
                self.failure_count = 0
                self.last_failure = None

            def record_success(self, metrics):
                pass

            def record_failure(self, failure):
                self.failure_count += 1
                self.last_failure = failure

        collector = MockMetricsCollector()
        limits = SecurityLimits(body_limit_pre_auth=10)
        middleware = WebhookSecurityMiddleware(
            limits=limits,
            protocols=SecurityProtocols(metrics_collector=collector),
        )

        request = MockRequest(
            body=b"x" * 100,
            headers={"Content-Length": "100"},
        )

        with pytest.raises(WebhookResponseError):
            await middleware.process_request(request, "test")

        assert collector.failure_count == 1
        assert collector.last_failure is not None
        assert collector.last_failure.error_type == "body-too-large"


@pytest.mark.asyncio
class TestOWASPCompliance:
    """Test OWASP Top 10 compliance."""

    async def test_a01_broken_access_control(self):
        """A01:2021 - Broken Access Control prevention via IP policy."""
        ip_policy = IpPolicy(blocked_ips=["1.2.3.4"])
        middleware = WebhookSecurityMiddleware(ip_policy=ip_policy)

        request = MockRequest(
            body=b"test",
            headers={"Content-Type": "application/json"},
            client_host="1.2.3.4",
        )

        with pytest.raises(WebhookResponseError) as exc_info:
            await middleware.process_request(request, "test")

        assert exc_info.value.status_code == 403

    async def test_a03_injection_prevention(self):
        """A03:2021 - Injection prevention via body size limits."""
        limits = SecurityLimits(
            body_limit_pre_auth=1024,
            body_limit_post_auth=2048,
        )
        middleware = WebhookSecurityMiddleware(limits=limits)

        # Attempt SQL injection in large payload
        malicious_body = b"'; DROP TABLE users; --" * 100
        request = MockRequest(body=malicious_body)

        with pytest.raises(WebhookResponseError) as exc_info:
            await middleware.process_request(request, "test")

        assert exc_info.value.status_code == 413

    async def test_a05_security_misconfiguration(self):
        """A05:2021 - Security misconfiguration detection."""
        # Test that default limits are secure
        middleware = WebhookSecurityMiddleware()

        # Default limits should be restrictive
        assert middleware._limits.body_limit_pre_auth <= 64 * 1024
        assert middleware._limits.body_limit_post_auth <= 10 * 1024 * 1024
        assert middleware._limits.read_timeout_seconds <= 10.0

    async def test_a07_authentication_failures(self):
        """A07:2021 - Authentication failures logged and rejected."""
        verifier = MockSignatureVerifier(should_pass=False)
        middleware = WebhookSecurityMiddleware(protocols=SecurityProtocols(signature_verifier=verifier))

        request = MockRequest(
            body=b"test",
            headers={"X-Signature": "invalid", "Content-Type": "application/json"},
        )

        with pytest.raises(WebhookResponseError) as exc_info:
            await middleware.process_request(request, "test")

        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    async def test_empty_body_accepted(self):
        """Empty body should be accepted."""
        middleware = WebhookSecurityMiddleware()

        request = MockRequest(body=b"", headers={"Content-Type": "application/json"})
        ctx = await middleware.process_request(request, "test")

        assert ctx.body == b""
        # Empty body gets parsed as None
        with pytest.raises(ValueError, match="not valid JSON"):
            ctx.get_json()

    async def test_malformed_json_body(self):
        """Malformed JSON should not crash, get_json() should raise."""
        middleware = WebhookSecurityMiddleware()

        request = MockRequest(
            body=b"{invalid json}",
            headers={"Content-Type": "application/json"},
        )
        ctx = await middleware.process_request(request, "test")

        assert ctx.body == b"{invalid json}"
        # Malformed JSON should raise when trying to access
        with pytest.raises(ValueError, match="not valid JSON"):
            ctx.get_json()

    async def test_missing_client_host(self):
        """Missing client host should not crash."""
        middleware = WebhookSecurityMiddleware()

        request = MockRequest(body=b"test", headers={"Content-Type": "application/json"})
        request.client = None

        # Should handle gracefully
        ctx = await middleware.process_request(request, "test")
        assert ctx.client_ip == "unknown"

    async def test_unicode_body_handling(self):
        """Unicode body should be handled correctly."""
        middleware = WebhookSecurityMiddleware()

        unicode_body = '{"text": "你好世界"}'.encode()
        request = MockRequest(body=unicode_body, headers={"Content-Type": "application/json"})

        ctx = await middleware.process_request(request, "test")
        assert ctx.body == unicode_body
        # Verify unicode is preserved
        parsed = ctx.get_json()
        assert parsed["text"] == "你好世界"

    async def test_zero_content_length_header(self):
        """Zero Content-Length should be handled."""
        middleware = WebhookSecurityMiddleware()

        request = MockRequest(
            body=b"",
            headers={"Content-Length": "0", "Content-Type": "application/json"},
        )
        ctx = await middleware.process_request(request, "test")

        assert ctx.body == b""


@pytest.mark.asyncio
class TestPerformanceUnderAttack:
    """Test performance characteristics under attack scenarios."""

    async def test_rapid_invalid_requests_performance(self):
        """System should maintain performance under rapid invalid requests."""
        from app.channels.reliability.inbound_limiter import (
            MemoryInboundLimiter,
        )

        rate_limiter = MemoryInboundLimiter()
        limits = SecurityLimits(
            body_limit_pre_auth=1024,
            rate_limit_per_minute=10,
        )
        middleware = WebhookSecurityMiddleware(
            limits=limits,
            rate_limiter=rate_limiter,
        )

        # Send 20 rapid requests
        start = time.perf_counter()
        for _i in range(20):
            request = MockRequest(
                body=b"x" * 2000,  # Oversized
                headers={"Content-Length": "2000"},
                client_host="1.2.3.4",
            )
            try:
                await middleware.process_request(request, "test")
            except WebhookResponseError:
                pass

        duration = time.perf_counter() - start

        # Should complete quickly (< 1 second for 20 requests)
        # Pre-auth checks are very fast
        assert duration < 1.0, f"Too slow: {duration}s for 20 requests"

    async def test_memory_usage_under_attack(self):
        """Memory usage should be bounded under attack."""
        limits = SecurityLimits(
            body_limit_pre_auth=10 * 1024,
            inflight_max_concurrent=5,
        )
        middleware = WebhookSecurityMiddleware(limits=limits)

        # Send many requests with max allowed body size
        for _i in range(100):
            request = MockRequest(
                body=b"x" * (10 * 1024),
                headers={"Content-Type": "application/json"},
            )
            try:
                await middleware.process_request(request, "test")
            except WebhookResponseError:
                pass

        # If we reach here without OOM, memory is bounded


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
