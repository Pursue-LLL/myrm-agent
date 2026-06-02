"""Webhook request context and validation result.

Post-validation request context and result objects, avoiding repeated parsing at the business layer.

[INPUT]

[OUTPUT]
- FallbackEvent: Fallback event details
- VerificationResult: Signature verification result (strongly-typed dataclass)
- IdempotencyResult: Idempotency check result (strongly-typed dataclass)
- WebhookContext: Request context (body + parsed data + metadata)

[POS]
Request context layer. Encapsulates validated request data and verification result objects.
Uses strongly-typed dataclasses for type safety. Supports distributed tracing (trace_id)
and degradation event tracking.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FallbackEvent:
    """Fallback event details.

    Records fallback decisions during dependency failures, for observability and troubleshooting.

    Example:
        >>> event = FallbackEvent(
        ...     component="signature_verifier",
        ...     mode="fail_open",
        ...     reason="Redis connection timeout",
        ...     timestamp=1710000000.123,
        ... )
    """

    component: str
    """Fallback component (signature_verifier, idempotency_store, etc.)."""

    mode: str
    """Fallback mode (fail_open, fail_closed, degraded)."""

    reason: str
    """Fallback reason (exception summary)."""

    timestamp: float
    """Fallback timestamp (Unix seconds, with fractional part)."""


@dataclass(frozen=True)
class VerificationResult:
    """Signature verification result (strongly-typed dataclass).

    Encapsulates the full signature verification result including status, performance metrics, and fallback events.

    Example:
        >>> result = VerificationResult(
        ...     verified=True,
        ...     duration_ms=45.8,
        ...     fallback_event=None,
        ... )
        >>> if result.verified:
        ...     print(f"Signature verified in {result.duration_ms}ms")
    """

    verified: bool
    """Whether signature was verified (True=verified, False=no verifier configured or verification failed)."""

    duration_ms: float | None
    """Signature verification duration (ms), None if no verifier configured."""

    fallback_event: FallbackEvent | None = None
    """Fallback event (only present when fallback occurred)."""


@dataclass(frozen=True)
class IdempotencyResult:
    """Idempotency check result (strongly-typed dataclass).

    Encapsulates the full idempotency check result including status, replay detection, performance metrics, and fallback events.

    Example:
        >>> # First request
        >>> result = IdempotencyResult(
        ...     checked=True,
        ...     duration_ms=12.3,
        ...     is_replay=False,
        ...     replay_detected_at=None,
        ... )

        >>> # Duplicate request
        >>> result = IdempotencyResult(
        ...     checked=True,
        ...     duration_ms=8.5,
        ...     is_replay=True,
        ...     replay_detected_at=1710000000.123,
        ... )
    """

    checked: bool
    """Whether idempotency check was executed (True=checked, False=no store configured)."""

    duration_ms: float | None
    """Idempotency check duration (ms), None if no store configured."""

    is_replay: bool
    """Whether this is a duplicate request (True=previously processed, False=first request)."""

    replay_detected_at: float | None = None
    """Replay detection timestamp (Unix seconds, with fractional part), only present when is_replay=True."""

    fallback_event: FallbackEvent | None = None
    """Fallback event (only present when fallback occurred)."""


@dataclass(frozen=True)
class WebhookContext:
    """Webhook request context.

    Complete context returned to the business layer after validation:
    - Raw body bytes
    - Parsed JSON data (cached)
    - Extracted metadata (timestamp, idempotency_key, etc.)
    - Validation process metrics
    - Fallback event tracking (fallback_events)
    - Distributed trace ID (trace_id)

    Properties:
    - frozen=True: immutable, thread-safe
    - Zero-copy: body is a raw bytes reference
    - Lazy parsing: parsed_data may be None (non-JSON requests)
    - Observability: trace_id links logs/metrics, fallback_events record fallback decisions
    """

    body: bytes
    """Raw request body (bytes)."""

    parsed_data: dict | None
    """Parsed JSON data (dict), None for non-JSON requests."""

    timestamp: int | None
    """Extracted timestamp (Unix seconds), None if not provided."""

    idempotency_key: str
    """Idempotency identifier (from header/body or body hash)."""

    client_ip: str
    """Client IP address."""

    verification_duration_ms: float
    """Total validation duration (ms)."""

    body_read_duration_ms: float
    """Body read duration (ms)."""

    signature_verified: bool
    """Whether signature verification was executed (True=verified, False=no verifier)."""

    idempotency_checked: bool
    """Whether idempotency check was executed (True=checked, False=no store configured)."""

    is_replay: bool = False
    """Whether this is a duplicate request (True=replay already processed, False=first request).

    Business layer can implement smart idempotency based on this field:
    - False: Process request normally
    - True: Return cached result (like Stripe) or return 200 directly
    """

    replay_detected_at: float | None = None
    """Replay detection timestamp (Unix seconds, fractional), only when is_replay=True.

    Usage:
    - Calculate time interval between duplicate requests (debug client retry strategy)
    - Monitor idempotency system response time
    """

    fallback_events: tuple[FallbackEvent, ...] = field(default_factory=tuple)
    """Fallback events tuple (records all dependency failure fallback details, immutable)."""

    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    """Distributed trace ID (for correlating logs/metrics/alerts)."""

    def get_json(self) -> dict:
        """Get parsed JSON data.

        Returns:
            Parsed dict

        Raises:
            ValueError: If parsed_data is None (non-JSON request)
        """
        if self.parsed_data is None:
            msg = "Request body is not valid JSON"
            raise ValueError(msg)
        return self.parsed_data
