"""Security protocols for webhook validation.

Framework layer defines protocols; business layer provides implementations.
Supports signature verification, idempotency checks, metrics collection, and fallback strategies.

[INPUT]

[OUTPUT]
Data classes (Metrics):
- WebhookMetrics: Encapsulates successful request metrics
- WebhookFailure: Encapsulates failed request details

Data classes (Config):
- SecurityLimits: Security rate-limit configuration (7 limit params grouped)
- IpPolicy: IP policy configuration (allow/deny lists + trusted proxies)
- SecurityProtocols: Security protocol configuration (4 Protocol instances grouped)

Protocols:
- SignatureVerifier: Signature verification protocol
- IdempotencyStore: Idempotency storage protocol
- MetricsCollector: Security metrics collection protocol (object parameters)
- FallbackStrategy: Fallback strategy protocol

Enums:
- FallbackMode: Fallback mode enum

[POS]
Security protocol layer. Defines standard webhook security verification interfaces,
allowing flexible business-layer implementations (memory/Redis/custom).
Uses strongly-typed dataclasses with __post_init__ validation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from fastapi import Request


@dataclass(frozen=True)
class WebhookMetrics:
    """Successful webhook request metrics (single-object encapsulation, 8 fields).

    Encapsulates all monitoring metrics for successful requests, used by MetricsCollector.

    Example:
        >>> metrics = WebhookMetrics(
        ...     channel="telegram",
        ...     body_size=1024,
        ...     total_duration_seconds=0.123,
        ...     body_read_ms=15.2,
        ...     client_ip="203.0.113.45",
        ...     request_path="/webhook/telegram",
        ...     signature_verify_ms=45.8,
        ...     idempotency_check_ms=12.3,
        ... )
        >>> collector.record_success(metrics)
    """

    channel: str
    """Platform name (telegram/feishu/wecom, etc.)"""

    body_size: int
    """Request body size in bytes"""

    total_duration_seconds: float
    """Total verification duration (seconds)"""

    body_read_ms: float
    """Body read duration (milliseconds)"""

    client_ip: str
    """Client real IP (for traffic pattern analysis)"""

    request_path: str
    """Request path (e.g., /webhook/telegram, for hotspot analysis)"""

    signature_verify_ms: float | None = None
    """Signature verification duration (ms), None when verifier not configured"""

    idempotency_check_ms: float | None = None
    """Idempotency check duration (ms), None when store not configured"""


@dataclass(frozen=True)
class WebhookFailure:
    """Failed webhook request details (single-object encapsulation, 6 fields).

    Encapsulates all monitoring metrics for failed requests, supporting attack pattern analysis.

    Example:
        >>> failure = WebhookFailure(
        ...     channel="telegram",
        ...     error_type="signature-invalid",
        ...     client_ip="1.2.3.4",
        ...     body_size=1024,
        ...     request_path="/webhook/telegram",
        ...     details={"status_code": 401, "trace_id": "abc"},
        ... )
        >>> collector.record_failure(failure)
    """

    channel: str
    """Platform name"""

    error_type: str
    """Error type (body-too-large/timeout/signature-invalid, etc.)"""

    client_ip: str
    """Client real IP (for attack pattern analysis)"""

    body_size: int | None
    """Request body size (bytes), None when unknown"""

    request_path: str
    """Request path (e.g., /webhook/telegram)"""

    details: dict | None = None
    """Additional details (e.g., status_code, trace_id, etc.)"""


class FallbackMode(Enum):
    """Fallback mode enum."""

    FAIL_CLOSED = "fail_closed"  # Reject request (security first)
    FAIL_OPEN = "fail_open"  # Allow through (availability first)
    DEGRADED = "degraded"  # Degraded mode (e.g., use backup verification)


class SignatureVerifier(Protocol):
    """Signature verifier protocol.

    Business layer implements platform-specific signature algorithms:
    - Telegram: HMAC-SHA256 secret token
    - Feishu: verification_token comparison
    - WeCom: SHA1 signature
    - Teams: JWT validation (Microsoft public key)
    - GoogleChat: Bearer token validation
    """

    async def verify(self, request: Request, body: bytes) -> None:
        """Verify request signature.

        Args:
            request: FastAPI Request object (contains headers)
            body: Raw body bytes (for signature computation)

        Raises:
            WebhookResponseError: Raised when signature verification fails (401/403)
        """
        ...


class IdempotencyStore(Protocol):
    """Idempotency storage protocol.

    Prevents duplicate processing of the same request (5-10 minute window).

    Business layer implements storage backends:
    - Standalone: MemoryIdempotencyStore (LRU Cache)
    - Distributed: RedisIdempotencyStore (two-tier cache)
    - Custom: PostgreSQL/DynamoDB, etc.
    """

    async def is_duplicate(self, key: str) -> bool:
        """Check whether a request has already been processed.

        Args:
            key: Idempotency identifier (Idempotency-Key header, message_id, or body hash)

        Returns:
            True for duplicate request, False for first-time request
        """
        ...

    async def mark_processed(self, key: str, ttl_seconds: int = 600) -> None:
        """Mark a request as processed.

        Args:
            key: Idempotency identifier
            ttl_seconds: Storage TTL (default 600 seconds = 10 minutes)
        """
        ...


class MetricsCollector(Protocol):
    """Security metrics collector protocol (with fine-grained performance metrics).

    Collects webhook security metrics for monitoring and alerting, supporting per-stage timing.

    Business layer implements monitoring backends:
    - PrometheusMetricsCollector (Prometheus Histogram)
    - DatadogMetricsCollector (Datadog Distribution)
    - NoOpMetricsCollector (testing / no-monitoring scenarios)

    Fine-grained metric use cases:
    - body_read_ms: Pinpoint network/IO bottlenecks
    - signature_verify_ms: Pinpoint external API call latency (e.g., Microsoft public key verification)
    - idempotency_check_ms: Pinpoint Redis/database query latency
    - Supports P50/P95/P99 latency analysis and alerting
    """

    def record_success(self, metrics: WebhookMetrics) -> None:
        """Record a successful request (single-object parameter, type-safe).

        Args:
            metrics: Complete successful request metrics (timing, traffic, performance data)

        Example:
            >>> metrics = WebhookMetrics(
            ...     channel="telegram",
            ...     body_size=1024,
            ...     total_duration_seconds=0.123,
            ...     body_read_ms=15.2,
            ...     client_ip="203.0.113.45",
            ...     request_path="/webhook/telegram",
            ...     signature_verify_ms=45.8,
            ...     idempotency_check_ms=12.3,
            ... )
            >>> collector.record_success(metrics)
        """
        ...

    def record_failure(self, failure: WebhookFailure) -> None:
        """Record a failed request (single-object parameter, type-safe).

        Args:
            failure: Complete failed request details (error type, IP, path, etc.)

        Example:
            >>> failure = WebhookFailure(
            ...     channel="telegram",
            ...     error_type="signature-invalid",
            ...     client_ip="1.2.3.4",
            ...     body_size=1024,
            ...     request_path="/webhook/telegram",
            ...     details={"status_code": 401, "trace_id": "abc"},
            ... )
            >>> collector.record_failure(failure)
        """
        ...


class FallbackStrategy(Protocol):
    """Fallback strategy protocol.

    Determines degradation behavior when dependent services fail:
    - Signature verifier failure (external API timeout, key errors, etc.)
    - Idempotency store failure (Redis down, etc.)

    Typical strategies:
    - Production: fail-open for internal network, fail-closed for public internet
    - Testing: fail-open everywhere
    - Hybrid: decide based on error type (allow on timeout, reject on key error)
    """

    async def on_verifier_error(
        self,
        error: Exception,
        request: Request,
        channel: str,
    ) -> FallbackMode:
        """Fallback strategy when signature verifier fails.

        Args:
            error: Exception thrown by the verifier (not WebhookResponseError)
            request: Current request object
            channel: Platform name (telegram/teams/feishu, etc.)

        Returns:
            FallbackMode.FAIL_CLOSED: Reject request (default, security first)
            FallbackMode.FAIL_OPEN: Allow through (availability first)
            FallbackMode.DEGRADED: Degraded verification (e.g., skip JWT, check IP only)
        """
        ...

    async def on_store_error(
        self,
        error: Exception,
        request: Request,
    ) -> tuple[FallbackMode, IdempotencyStore | None]:
        """Fallback strategy when idempotency store fails.

        Args:
            error: Exception thrown by the store
            request: Current request object

        Returns:
            (FallbackMode, fallback_store):
            - (DEGRADED, MemoryStore): Degrade to in-memory storage
            - (FAIL_OPEN, None): Skip idempotency check
            - (FAIL_CLOSED, None): Reject request
        """
        ...


# ========== Configuration Objects ==========


@dataclass(frozen=True)
class SecurityLimits:
    """Security rate-limit configuration (single-object encapsulation, 7 rate-limit params).

    Example:
        >>> limits = SecurityLimits(
        ...     body_limit_pre_auth=65_536,
        ...     body_limit_post_auth=10_485_760,
        ...     read_timeout_seconds=10.0,
        ...     max_timestamp_age_seconds=300,
        ...     clock_skew_seconds=60,
        ...     rate_limit_per_minute=60,
        ...     inflight_max_concurrent=8,
        ... )
    """

    body_limit_pre_auth: int = 64 * 1024
    """Pre-auth body limit (bytes), default 64KB"""

    body_limit_post_auth: int = 10 * 1024 * 1024
    """Post-auth body limit (bytes), default 10MB"""

    read_timeout_seconds: float = 10.0
    """Body read timeout (seconds), prevents Slowloris attacks"""

    max_timestamp_age_seconds: int = 300
    """Maximum timestamp age (seconds), prevents replay attacks, default 5 minutes"""

    clock_skew_seconds: int = 60
    """Allowed clock skew (seconds), prevents false rejection of valid requests, default 60s"""

    rate_limit_per_minute: int = 60
    """Per-IP requests per minute limit, default 60"""

    inflight_max_concurrent: int = 8
    """Per-IP concurrent request limit, default 8"""

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.body_limit_pre_auth <= 0:
            msg = "body_limit_pre_auth must be positive"
            raise ValueError(msg)
        if self.body_limit_post_auth < self.body_limit_pre_auth:
            msg = "body_limit_post_auth must >= body_limit_pre_auth"
            raise ValueError(msg)
        if self.read_timeout_seconds <= 0:
            msg = "read_timeout_seconds must be positive"
            raise ValueError(msg)
        if self.max_timestamp_age_seconds <= 0:
            msg = "max_timestamp_age_seconds must be positive"
            raise ValueError(msg)
        if self.clock_skew_seconds < 0:
            msg = "clock_skew_seconds must be non-negative"
            raise ValueError(msg)
        if self.rate_limit_per_minute <= 0:
            msg = "rate_limit_per_minute must be positive"
            raise ValueError(msg)
        if self.inflight_max_concurrent <= 0:
            msg = "inflight_max_concurrent must be positive"
            raise ValueError(msg)


@dataclass(frozen=True)
class IpPolicy:
    """IP policy configuration (single-object encapsulation, 3 IP param groups).

    Supports CIDR-format deny/allow lists and trusted proxy lists.

    Example:
        >>> policy = IpPolicy(
        ...     blocked_ips=["1.2.3.4", "10.0.0.0/8"],
        ...     allowed_ips=["203.0.113.0/24"],
        ...     trusted_proxies=["192.168.1.1", "10.0.0.1"],
        ... )
    """

    blocked_ips: Sequence[str] = field(default_factory=list)
    """IP deny list (supports CIDR), matched IPs are immediately rejected"""

    allowed_ips: Sequence[str] = field(default_factory=list)
    """IP allow list (supports CIDR), matched IPs bypass Rate/InFlight limits"""

    trusted_proxies: Sequence[str] = field(default_factory=list)
    """Trusted proxy IP list (for X-Forwarded-For parsing)"""

    def __post_init__(self) -> None:
        """Validate all IP/CIDR formats (fail-fast)."""
        import ipaddress

        for ip_str in self.blocked_ips:
            try:
                ipaddress.ip_network(ip_str, strict=False)
            except ValueError as e:
                msg = f"Invalid blocked_ip '{ip_str}': {e}"
                raise ValueError(msg) from e

        for ip_str in self.allowed_ips:
            try:
                ipaddress.ip_network(ip_str, strict=False)
            except ValueError as e:
                msg = f"Invalid allowed_ip '{ip_str}': {e}"
                raise ValueError(msg) from e

        for ip_str in self.trusted_proxies:
            try:
                ipaddress.ip_network(ip_str, strict=False)
            except ValueError as e:
                msg = f"Invalid trusted_proxy '{ip_str}': {e}"
                raise ValueError(msg) from e


@dataclass(frozen=True)
class SecurityProtocols:
    """Security protocol configuration (single-object encapsulation, 4 Protocol instances).

    Example:
        >>> protocols = SecurityProtocols(
        ...     signature_verifier=MyVerifier(),
        ...     idempotency_store=RedisStore(),
        ...     metrics_collector=PrometheusCollector(),
        ...     fallback_strategy=DefaultFallback(),
        ... )
    """

    signature_verifier: SignatureVerifier | None = None
    """Signature verifier (None skips signature verification)"""

    idempotency_store: IdempotencyStore | None = None
    """Idempotency store (None skips idempotency check)"""

    metrics_collector: MetricsCollector | None = None
    """Metrics collector (None skips metrics recording)"""

    fallback_strategy: FallbackStrategy | None = None
    """Fallback strategy (None uses default FAIL_CLOSED)"""
