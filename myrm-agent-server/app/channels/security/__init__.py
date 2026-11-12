"""Webhook security protocols and middleware.

[INPUT]
(No external dependencies, pure protocol definitions)

[OUTPUT]
Protocols:
- SignatureVerifier: signature verification protocol
- IdempotencyStore: idempotency storage protocol
- MetricsCollector: security metrics collection protocol (takes metric objects as parameters)
- FallbackStrategy: degradation strategy protocol
- FallbackMode: degradation mode enum

Result data classes:
- VerificationResult: signature verification result (strongly typed)
- IdempotencyResult: idempotency check result (strongly typed)

Metrics data classes:
- WebhookMetrics: metrics of a successful request
- WebhookFailure: details of a failed request

Config data classes:
- SecurityLimits: security and rate-limit settings (7-parameter group)
- IpPolicy: IP policy (blacklist, whitelist and trusted proxies)
- SecurityProtocols: protocol settings (group of 4 protocol instances)

Context data classes:
- FallbackEvent: degradation event record
- WebhookContext: request context after validation

Exceptions:
- WebhookResponseError: standardized error response (RFC 7807/6585/7231, trace_id + retry_after)
- SecurityViolationError: security violation exception

Middleware:
- WebhookSecurityMiddleware: unified security middleware (takes 3 config objects)

Utility functions:
- extract_real_ip: extracts the real client IP
- is_ip_blocked: IP blacklist check
- is_ip_allowed: IP whitelist check
- validate_host: Host header validation

[POS]
Webhook security layer. Defines inbound security protocols (signature verification,
idempotency, metrics, degradation). Provides out-of-the-box security middleware.
Business layer injects platform-specific logic via protocols.
"""

from .context import FallbackEvent, IdempotencyResult, VerificationResult, WebhookContext
from .errors import SecurityViolationError, WebhookResponseError
from .ip_utils import extract_real_ip, is_ip_allowed, is_ip_blocked, validate_host
from .protocols import (
    FallbackMode,
    FallbackStrategy,
    IdempotencyStore,
    IpPolicy,
    MetricsCollector,
    SecurityLimits,
    SecurityProtocols,
    SignatureVerifier,
    WebhookFailure,
    WebhookMetrics,
)
from .webhook_middleware import WebhookSecurityMiddleware

__all__ = [
    # Protocols
    "SignatureVerifier",
    "IdempotencyStore",
    "MetricsCollector",
    "FallbackStrategy",
    "FallbackMode",
    # Result data classes
    "VerificationResult",
    "IdempotencyResult",
    # Metrics data classes
    "WebhookMetrics",
    "WebhookFailure",
    # Config data classes
    "SecurityLimits",
    "IpPolicy",
    "SecurityProtocols",
    # Context data classes
    "FallbackEvent",
    "WebhookContext",
    # Exceptions
    "WebhookResponseError",
    "SecurityViolationError",
    # Middleware
    "WebhookSecurityMiddleware",
    # Utility functions
    "extract_real_ip",
    "is_ip_blocked",
    "is_ip_allowed",
    "validate_host",
]
