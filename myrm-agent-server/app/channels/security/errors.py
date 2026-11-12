"""Standardized webhook error responses.

Follows the RFC 7807 Problem Details specification and provides a machine-parsable error format.

[INPUT]
(no external dependencies)

[OUTPUT]
- WebhookResponseError: Standardized RFC 7807 error response
- SecurityViolationError: Security violation exception

[POS]
Webhook error response layer. Provides RFC 7807 standardized error format,
supporting machine-parsable and human-readable output without leaking sensitive data.
"""

from __future__ import annotations

import time


class WebhookResponseError(Exception):
    """Standardized RFC 7807 Problem Details error response (wraps trace_id)

    Features:
    - Machine-parsable (type/status/detail fields)
    - Human-readable (title field)
    - Sanitized (no internal paths, sensitive timestamps, etc.)
    - i18n-friendly (the error type is independent of the error message)
    - Mandatory tracing (trace_id is injected at construction so it cannot be forgotten)

    Example:
        {
            "type": "https://docs.example.com/errors/webhook/body-too-large",
            "title": "Request Body Too Large",
            "status": 413,
            "detail": "Request body exceeds the maximum allowed size of 10000 bytes",
            "timestamp": 1234567890.123,
            "trace_id": "abc123..."
        }
    """

    def __init__(
        self,
        status_code: int,
        error_type: str,
        title: str,
        detail: str,
        trace_id: str,
        retry_after: int | None = None,
    ) -> None:
        """Build the error response

        Args:
            status_code: HTTP status code
            error_type: Error type identifier (e.g. body-too-large)
            title: Error title (human-readable)
            detail: Error detail (the concrete cause)
            trace_id: Distributed trace ID (required, keeps the error traceable)
            retry_after: Retry delay in seconds (supports status codes such as 429/503)
        """
        self.status_code = status_code
        self.error_type = error_type
        self.title = title
        self.detail = detail
        self.trace_id = trace_id
        self.retry_after = retry_after
        super().__init__(detail)

    def to_dict(self) -> dict[str, object]:
        """Convert to the RFC 7807 Problem Details format

        Returns:
            Error response dict in RFC 7807 format (including trace_id)
        """
        result: dict[str, object] = {
            "type": f"https://docs.example.com/errors/webhook/{self.error_type}",
            "title": self.title,
            "status": self.status_code,
            "detail": self.detail,
            "timestamp": time.time(),
            "trace_id": self.trace_id,
        }

        # RFC 6585/7231: support retry_after (429 Rate Limit, 503 Service Unavailable, etc.)
        if self.retry_after is not None:
            result["retry_after"] = self.retry_after

        return result


class SecurityViolationError(WebhookResponseError):
    """Security violation exception (signature validation failure, replay attack, etc.)"""

    def __init__(
        self,
        detail: str,
        trace_id: str,
        error_type: str = "security-violation",
    ) -> None:
        """Build the security violation exception

        Args:
            detail: Error detail (e.g. "Invalid signature")
            trace_id: Distributed trace ID
            error_type: Error type identifier (defaults to security-violation)
        """
        super().__init__(
            status_code=401,
            error_type=error_type,
            title="Security Violation",
            detail=detail,
            trace_id=trace_id,
        )
