"""Webhook security middleware for inbound request validation.

Unified security middleware providing out-of-the-box webhook inbound protection.
Supports protocol injection for platform-specific logic (signature verification, idempotency store, metrics, fallback).

[INPUT]
- fastapi::Request (POS: Out-of-the-box FastAPI implementation. Users can directly use these classes without implementing RouteRegistrar Protocol themselves.)
- security.protocols::SignatureVerifier, (POS: Protocols for Skill Optimization Subsystem)
- security.context::WebhookContext (POS: Provides ArtifactContext, ArtifactContextManager, get_artifact_context.)
- security.errors::WebhookResponseError (POS: Storage quota related errors.)

[OUTPUT]
- WebhookSecurityMiddleware: Unified security middleware
- process_request(): Process inbound request, return WebhookContext

[POS]
Webhook security middleware layer. Unified inbound security verification (body limits,
timeouts, signatures, timestamps, idempotency). Defends against DoS, Slowloris, replay attacks,
and message forgery. Supports graceful degradation on dependency failures.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING

from fastapi import Request

from .context import FallbackEvent, IdempotencyResult, VerificationResult, WebhookContext
from .errors import WebhookResponseError
from .ip_utils import extract_real_ip, is_ip_allowed, is_ip_blocked
from .protocols import (
    FallbackMode,
    IpPolicy,
    SecurityLimits,
    SecurityProtocols,
    WebhookFailure,
    WebhookMetrics,
)

if TYPE_CHECKING:
    from ..reliability.inbound_limiter import InboundRateLimiter
    from ..reliability.inflight_limiter import InFlightLimiter

logger = logging.getLogger(__name__)


class WebhookSecurityMiddleware:
    """Webhook inbound security middleware (production-grade).

    Features:
    - IP blacklist/whitelist (fast block/skip)
    - Real IP extraction (trusted_proxies validation)
    - Rate limiting + in-flight limiter (anti-DoS/concurrency attacks)
    - Content-Type validation + two-stage body limits
    - Signature verification + timestamp validation + idempotency check
    - Fallback strategy (auto-decisions on dependency failures)
    - Fine-grained monitoring (per-stage timing + fallback event tracking)
    """

    def __init__(
        self,
        limits: SecurityLimits | None = None,
        ip_policy: IpPolicy | None = None,
        protocols: SecurityProtocols | None = None,
        rate_limiter: InboundRateLimiter | None = None,
        inflight_limiter: InFlightLimiter | None = None,
        allowed_content_types: Sequence[str] | None = None,
    ) -> None:
        """Initialize middleware (3 config objects + 2 limiter dependencies).

        Args:
            limits: Security rate-limit configuration (7-parameter group)
            ip_policy: IP policy configuration (blacklist/whitelist + trusted proxies)
            protocols: Security protocol configuration (4 Protocol instances)
            rate_limiter: Inbound rate limiter (anti-frequency attacks)
            inflight_limiter: Concurrency limiter (anti-concurrent attacks)
            allowed_content_types: Allowed Content-Type list
        """
        self._limits = limits or SecurityLimits()
        self._ip_policy = ip_policy or IpPolicy()
        self._protocols = protocols or SecurityProtocols()
        self._rate_limiter = rate_limiter
        self._inflight_limiter = inflight_limiter
        self._allowed_content_types = (
            list(allowed_content_types)
            if allowed_content_types
            else ["application/json", "application/x-www-form-urlencoded"]
        )

    async def process_request(
        self,
        request: Request,
        channel_name: str,
    ) -> WebhookContext:
        """Process an inbound webhook request and return a full context.

        Pipeline (ordered by cost):
        1. Extract real IP (validate trusted_proxies)
        2. IP blacklist check (block known attack IPs immediately)
        3. IP whitelist check (trusted IPs skip rate limiting)
        4. Rate limiting (anti-sustained attacks, configurable)
        5. In-flight limiter (anti-concurrency storms, context-manager auto-release)
        6. Content-Type validation (reject illegal requests)
        7. Pre-auth body check (Content-Length < 64KB)
        8. Post-auth body read (streaming, 1MB limit)
        9. Signature verification (with fallback strategy)
        10. Timestamp validation (reject future timestamps, configurable expiry window)
        11. Idempotency check (with fallback strategy)
        12. Return WebhookContext (with trace_id + fallback_events)

        Returns:
            WebhookContext: Contains body, parsed JSON, metadata, metrics, fallback events
        """
        start_time = time.time()
        trace_id = str(uuid.uuid4())
        request.state._webhook_trace_id = trace_id
        request_path = str(request.url.path)
        real_ip = "unknown"

        try:
            # 1. Extract real IP
            real_ip = extract_real_ip(request, self._ip_policy.trusted_proxies)
            logger.debug(
                f"[{trace_id}] Extracted real IP: {real_ip}",
                extra={"trace_id": trace_id, "real_ip": real_ip},
            )

            # 2. IP blacklist check (minimal cost, fast blocking)
            if self._ip_policy.blocked_ips and is_ip_blocked(real_ip, self._ip_policy.blocked_ips):
                logger.warning(
                    f"[{trace_id}] Blocked IP rejected",
                    extra={"trace_id": trace_id, "real_ip": real_ip},
                )
                raise WebhookResponseError(
                    status_code=403,
                    error_type="ip-blocked",
                    title="IP Address Blocked",
                    detail="Your IP address is blocked",
                    trace_id=trace_id,
                )

            # 3. IP whitelist check (trusted IPs skip rate limiting)
            is_whitelisted = self._ip_policy.allowed_ips and is_ip_allowed(real_ip, self._ip_policy.allowed_ips)

            # 4. Rate limiting (whitelisted IPs skip)
            if not is_whitelisted and self._rate_limiter:
                if not await self._rate_limiter.check_limit(
                    identifier=real_ip,
                    endpoint=request_path,
                    limit_per_minute=self._limits.rate_limit_per_minute,
                ):
                    logger.warning(
                        f"[{trace_id}] Rate limit exceeded",
                        extra={"trace_id": trace_id, "real_ip": real_ip},
                    )
                    # Rate limiting: retry_after=60s (frequency limit, wait for window reset)
                    raise WebhookResponseError(
                        status_code=429,
                        error_type="rate-limit-exceeded",
                        title="Too Many Requests",
                        detail=f"Rate limit exceeded ({self._limits.rate_limit_per_minute} req/min)",
                        trace_id=trace_id,
                        retry_after=60,
                    )

            # 5. In-flight limiter (context manager ensures release)
            if self._inflight_limiter:
                async with self._inflight_limiter.acquire(real_ip) as acquired:
                    if not acquired:
                        logger.warning(
                            f"[{trace_id}] In-flight limit exceeded",
                            extra={
                                "trace_id": trace_id,
                                "real_ip": real_ip,
                                "max_concurrent": self._limits.inflight_max_concurrent,
                            },
                        )
                        # In-flight limiter: retry_after=2s (concurrency limit, slots release quickly)
                        raise WebhookResponseError(
                            status_code=429,
                            error_type="inflight-limit-exceeded",
                            title="Too Many Concurrent Requests",
                            detail=f"Concurrent request limit exceeded (max {self._limits.inflight_max_concurrent})",
                            trace_id=trace_id,
                            retry_after=2,
                        )

                    # Process request under in-flight lock protection
                    return await self._process_request_locked(
                        request,
                        channel_name,
                        real_ip,
                        trace_id,
                        start_time,
                    )
            else:
                # No in-flight limiter configured, process directly
                return await self._process_request_locked(
                    request,
                    channel_name,
                    real_ip,
                    trace_id,
                    start_time,
                )

        except WebhookResponseError as e:
            if self._protocols.metrics_collector:
                content_length = request.headers.get("Content-Length")
                body_size = int(content_length) if content_length and content_length.isdigit() else None
                self._protocols.metrics_collector.record_failure(
                    WebhookFailure(
                        channel=channel_name,
                        error_type=e.error_type,
                        client_ip=real_ip,
                        body_size=body_size,
                        request_path=request_path,
                        details={"status_code": e.status_code, "trace_id": trace_id},
                    )
                )
            raise

    async def _process_request_locked(
        self,
        request: Request,
        channel_name: str,
        real_ip: str,
        trace_id: str,
        start_time: float,
    ) -> WebhookContext:
        """Core request processing logic (under in-flight lock).

        Executed within the in-flight limiter context manager, ensuring counter release.
        """
        fallback_events: list[FallbackEvent] = []
        signature_verified = False
        idempotency_checked = False
        signature_duration_ms: float | None = None
        idempotency_duration_ms: float | None = None
        request_path = str(request.url.path)

        # 6. Content-Type validation
        content_type = request.headers.get("Content-Type", "").split(";")[0].strip()
        if content_type and content_type not in self._allowed_content_types:
            logger.warning(
                f"[{trace_id}] Invalid Content-Type",
                extra={
                    "trace_id": trace_id,
                    "content_type": content_type,
                    "allowed": self._allowed_content_types,
                },
            )
            raise WebhookResponseError(
                status_code=415,
                error_type="unsupported-media-type",
                title="Unsupported Content-Type",
                detail=f"Content-Type must be one of: {', '.join(self._allowed_content_types)}",
                trace_id=trace_id,
            )

        # 7-8. Two-stage body read
        body_read_start = time.time()
        body_bytes = await self._read_two_stage_body(request, trace_id)
        body_read_duration_ms = (time.time() - body_read_start) * 1000

        # 9. Signature verification (with fallback)
        verification_result = await self._verify_signature(request, body_bytes, channel_name, trace_id)
        if verification_result.fallback_event:
            fallback_events.append(verification_result.fallback_event)
        signature_verified = verification_result.verified
        signature_duration_ms = verification_result.duration_ms

        # 10. Timestamp validation
        timestamp = self._extract_timestamp(request, body_bytes)
        if timestamp is not None:
            self._validate_timestamp(timestamp, trace_id)

        # 11. Idempotency check (with fallback)
        idempotency_key = self._extract_idempotency_key(request, body_bytes)
        idempotency_result = await self._check_idempotency(request, idempotency_key, trace_id)
        if idempotency_result.fallback_event:
            fallback_events.append(idempotency_result.fallback_event)
        idempotency_checked = idempotency_result.checked
        idempotency_duration_ms = idempotency_result.duration_ms
        is_replay = idempotency_result.is_replay
        replay_detected_at = idempotency_result.replay_detected_at

        # 12. Build context
        verification_duration_ms = (time.time() - start_time) * 1000
        parsed_data = self._get_parsed_body(request, body_bytes)

        context = WebhookContext(
            body=body_bytes,
            parsed_data=parsed_data,
            timestamp=timestamp,
            idempotency_key=idempotency_key,
            client_ip=real_ip,
            verification_duration_ms=verification_duration_ms,
            body_read_duration_ms=body_read_duration_ms,
            signature_verified=signature_verified,
            idempotency_checked=idempotency_checked,
            is_replay=is_replay,
            replay_detected_at=replay_detected_at,
            fallback_events=tuple(fallback_events),
            trace_id=trace_id,
        )

        # 13. Record metrics (per-stage timing and traffic analysis)
        if self._protocols.metrics_collector:
            total_duration = time.time() - start_time
            self._protocols.metrics_collector.record_success(
                WebhookMetrics(
                    channel=channel_name,
                    body_size=len(body_bytes),
                    total_duration_seconds=total_duration,
                    body_read_ms=body_read_duration_ms,
                    client_ip=real_ip,
                    request_path=request_path,
                    signature_verify_ms=signature_duration_ms,
                    idempotency_check_ms=idempotency_duration_ms,
                )
            )

        return context

    async def _verify_signature(
        self,
        request: Request,
        body: bytes,
        channel: str,
        trace_id: str,
    ) -> VerificationResult:
        """Execute signature verification (with fallback strategy).

        Returns:
            VerificationResult: Strongly-typed result (verified, duration_ms, fallback_event)
        """
        if not self._protocols.signature_verifier:
            return VerificationResult(verified=False, duration_ms=None)

        start = time.time()
        try:
            await self._protocols.signature_verifier.verify(request, body)
            return VerificationResult(verified=True, duration_ms=(time.time() - start) * 1000)
        except WebhookResponseError:
            raise
        except Exception as e:
            if not self._protocols.fallback_strategy:
                raise

            mode = await self._protocols.fallback_strategy.on_verifier_error(e, request, channel)
            if mode == FallbackMode.FAIL_CLOSED:
                logger.error(
                    "Signature verifier failed, fallback=FAIL_CLOSED",
                    extra={"channel": channel, "error": str(e)},
                )
                raise WebhookResponseError(
                    status_code=503,
                    error_type="verifier-unavailable",
                    title="Signature Verifier Unavailable",
                    detail="Signature verification service is temporarily unavailable",
                    trace_id=trace_id,
                ) from e

            # Fallback event encapsulated in result
            fallback_event = FallbackEvent(
                component="signature_verifier",
                mode=mode.value,
                reason=str(e)[:200],
                timestamp=time.time(),
            )

            logger.warning(
                f"Signature verifier failed, fallback={mode.value}",
                extra={"channel": channel, "error": str(e), "mode": mode.value},
            )
            return VerificationResult(verified=False, duration_ms=None, fallback_event=fallback_event)

    async def _check_idempotency(
        self,
        request: Request,
        key: str,
        trace_id: str,
    ) -> IdempotencyResult:
        """Execute idempotency check (with fallback strategy).

        Returns:
            IdempotencyResult: Strongly-typed result (checked, duration_ms, is_replay, etc.)
        """
        if not self._protocols.idempotency_store:
            return IdempotencyResult(checked=False, duration_ms=None, is_replay=False)

        start = time.time()
        try:
            if await self._protocols.idempotency_store.is_duplicate(key):
                # Duplicate request: return is_replay=True for business-layer decision
                # Business-layer options: cached result / 200 OK / 409 Conflict
                replay_time = time.time()
                duration_ms = (replay_time - start) * 1000
                logger.info(
                    "Duplicate request detected",
                    extra={"idempotency_key": key, "duration_ms": duration_ms},
                )
                return IdempotencyResult(
                    checked=True,
                    duration_ms=duration_ms,
                    is_replay=True,
                    replay_detected_at=replay_time,
                )

            await self._protocols.idempotency_store.mark_processed(key)
            return IdempotencyResult(
                checked=True,
                duration_ms=(time.time() - start) * 1000,
                is_replay=False,
            )
        except WebhookResponseError:
            raise
        except Exception as e:
            if not self._protocols.fallback_strategy:
                raise

            mode, alt_store = await self._protocols.fallback_strategy.on_store_error(e, request)
            if mode == FallbackMode.FAIL_CLOSED:
                logger.error(
                    "Idempotency store failed, fallback=FAIL_CLOSED",
                    extra={"error": str(e)},
                )
                raise WebhookResponseError(
                    status_code=503,
                    error_type="store-unavailable",
                    title="Idempotency Store Unavailable",
                    detail="Idempotency check service is temporarily unavailable",
                    trace_id=trace_id,
                ) from e

            # Fallback event encapsulated in result
            fallback_event = FallbackEvent(
                component="idempotency_store",
                mode=mode.value,
                reason=str(e)[:200],
                timestamp=time.time(),
            )

            if mode == FallbackMode.DEGRADED and alt_store:
                logger.warning(
                    "Idempotency store failed, using fallback store",
                    extra={"error": str(e)},
                )
                is_dup = await alt_store.is_duplicate(key)
                if is_dup:
                    replay_time = time.time()
                    return IdempotencyResult(
                        checked=True,
                        duration_ms=(replay_time - start) * 1000,
                        is_replay=True,
                        replay_detected_at=replay_time,
                        fallback_event=fallback_event,
                    )
                else:
                    await alt_store.mark_processed(key)
                    return IdempotencyResult(
                        checked=True,
                        duration_ms=(time.time() - start) * 1000,
                        is_replay=False,
                        fallback_event=fallback_event,
                    )

            logger.warning(
                f"Idempotency store failed, fallback={mode.value}",
                extra={"error": str(e), "mode": mode.value},
            )
            return IdempotencyResult(
                checked=False,
                duration_ms=None,
                is_replay=False,
                fallback_event=fallback_event,
            )

    async def _read_two_stage_body(self, request: Request, trace_id: str) -> bytes:
        """Two-stage body read (pre-auth Content-Length check + post-auth streaming read).

        Stage 1 (Pre-Auth): Check Content-Length < 64KB (reject oversized requests, lowest cost)
        Stage 2 (Post-Auth): Stream-read body, 1MB limit (prevent malicious payloads)
        """
        # Stage 1: Pre-auth Content-Length check
        content_length = request.headers.get("Content-Length")
        if content_length:
            try:
                length = int(content_length)
                if length > self._limits.body_limit_pre_auth:
                    logger.warning(
                        "Pre-auth body size check failed",
                        extra={
                            "content_length": length,
                            "pre_auth_limit": self._limits.body_limit_pre_auth,
                        },
                    )
                    raise WebhookResponseError(
                        status_code=413,
                        error_type="body-too-large",
                        title="Request Body Too Large",
                        detail=(
                            f"Content-Length {length} exceeds pre-auth limit"
                            f" of {self._limits.body_limit_pre_auth} bytes"
                        ),
                        trace_id=trace_id,
                    )
            except ValueError:
                pass  # Invalid Content-Length, continue reading and check in post-auth stage

        # Stage 2: Post-auth streaming read (1MB limit)
        return await self._read_limited_body(request, trace_id)

    async def _read_limited_body(self, request: Request, trace_id: str) -> bytes:
        """Stream-read request body (with size and timeout limits)."""
        start_time = time.time()
        buffer = bytearray()

        try:
            async with asyncio.timeout(self._limits.read_timeout_seconds):
                async for chunk in request.stream():
                    buffer.extend(chunk)

                    if len(buffer) > self._limits.body_limit_post_auth:
                        logger.warning(
                            "Post-auth body size limit exceeded",
                            extra={
                                "client_ip": request.client.host if request.client else "unknown",
                                "body_size": len(buffer),
                                "post_auth_limit": self._limits.body_limit_post_auth,
                                "duration_ms": int((time.time() - start_time) * 1000),
                            },
                        )
                        raise WebhookResponseError(
                            status_code=413,
                            error_type="body-too-large",
                            title="Request Body Too Large",
                            detail=f"Request body exceeds post-auth limit of {self._limits.body_limit_post_auth} bytes",
                            trace_id=trace_id,
                        )

        except TimeoutError as e:
            logger.warning(
                "Webhook body read timeout",
                extra={
                    "client_ip": request.client.host if request.client else "unknown",
                    "body_size": len(buffer),
                    "timeout_seconds": self._limits.read_timeout_seconds,
                    "duration_ms": int((time.time() - start_time) * 1000),
                },
            )
            raise WebhookResponseError(
                status_code=408,
                error_type="request-timeout",
                title="Request Timeout",
                detail=f"Request body read timeout after {self._limits.read_timeout_seconds} seconds",
                trace_id=trace_id,
            ) from e

        duration_ms = int((time.time() - start_time) * 1000)
        logger.debug(
            f"Webhook body read complete: {len(buffer)} bytes in {duration_ms}ms",
            extra={"body_size": len(buffer), "duration_ms": duration_ms},
        )

        return bytes(buffer)

    def _validate_timestamp(self, timestamp: int, trace_id: str) -> None:
        """Validate request timestamp to prevent replay attacks.

        Rejects future timestamps (prevents pre-generated signature attacks).
        Rejects expired timestamps (configurable max_age, default 300s).
        Allows clock skew (configurable max_clock_skew, default 60s).
        """
        current_time = int(time.time())

        # Reject future timestamps (allow minor clock skew)
        if timestamp > current_time + self._limits.clock_skew_seconds:
            logger.warning(
                "Webhook timestamp from future rejected",
                extra={
                    "timestamp": timestamp,
                    "current_time": current_time,
                    "diff_seconds": timestamp - current_time,
                    "max_clock_skew": self._limits.clock_skew_seconds,
                    "trace_id": trace_id,
                },
            )
            raise WebhookResponseError(
                status_code=401,
                error_type="timestamp-invalid",
                title="Invalid Timestamp",
                detail=f"Request timestamp is in the future (max clock skew: {self._limits.clock_skew_seconds}s)",
                trace_id=trace_id,
            )

        # Reject expired timestamps (configurable window)
        if current_time - timestamp > self._limits.max_timestamp_age_seconds:
            logger.warning(
                "Webhook timestamp expired",
                extra={
                    "timestamp": timestamp,
                    "current_time": current_time,
                    "diff_seconds": current_time - timestamp,
                    "max_age": self._limits.max_timestamp_age_seconds,
                    "trace_id": trace_id,
                },
            )
            raise WebhookResponseError(
                status_code=401,
                error_type="timestamp-expired",
                title="Request Too Old",
                detail=f"Request timestamp expired (max age: {self._limits.max_timestamp_age_seconds}s)",
                trace_id=trace_id,
            )

        logger.debug(
            "Webhook timestamp validated",
            extra={
                "timestamp": timestamp,
                "current_time": current_time,
                "diff_seconds": current_time - timestamp,
            },
        )

    def _get_parsed_body(self, request: Request, body: bytes) -> dict | None:
        """Parse body as JSON and cache on request.state (avoid repeated parsing)."""
        if not hasattr(request.state, "_webhook_parsed_body"):
            try:
                request.state._webhook_parsed_body = json.loads(body)
            except json.JSONDecodeError:
                request.state._webhook_parsed_body = None
        return request.state._webhook_parsed_body  # type: ignore[return-value]

    def _extract_timestamp(self, request: Request, body: bytes) -> int | None:
        """Extract request timestamp (platform-adaptive, using cached parsed_data)."""
        if ts_header := request.headers.get("x-timestamp"):
            try:
                return int(ts_header)
            except (ValueError, TypeError):
                pass

        data = self._get_parsed_body(request, body)
        if data and isinstance(data, dict):
            if ts := data.get("timestamp"):
                return int(ts) if isinstance(ts, (int, str)) else None
            if ts := data.get("ts"):
                return int(ts) if isinstance(ts, (int, str)) else None

        return None

    def _extract_idempotency_key(self, request: Request, body: bytes) -> str:
        """Extract idempotency identifier (using cached parsed_data)."""
        if key := request.headers.get("idempotency-key"):
            return key

        data = self._get_parsed_body(request, body)
        if data and isinstance(data, dict):
            if msg_id := data.get("message_id"):
                return f"msg:{msg_id}"
            if event_id := data.get("event_id"):
                return f"event:{event_id}"
            if update_id := data.get("update_id"):
                return f"update:{update_id}"

        return f"hash:{hashlib.sha256(body).hexdigest()[:16]}"
