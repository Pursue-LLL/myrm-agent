"""Feishu API exception hierarchy.

Platform-specific errors for the Feishu/Lark OpenAPI.

Hierarchy::

    FeishuAPIError
    ├── FeishuSendError      — API call failed
    │   └── FeishuRateLimitError  — rate limit hit
    └── FeishuAuthError      — credentials invalid

[INPUT]
- (none)

[OUTPUT]
- FeishuAPIError: Base exception for all Feishu API errors.
- FeishuSendError: API call failed. May be retriable depending on status code.
- FeishuRateLimitError: Platform rate limit hit. Always retriable with specific delay.
- FeishuAuthError: Credentials invalid or expired. Never retry.

[POS]
Feishu-specific API error hierarchy. When used inside a channel provider,
the provider is responsible for catching these and converting to the
appropriate ChannelError subclass.
"""

from __future__ import annotations


class FeishuAPIError(Exception):
    """Base exception for all Feishu API errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class FeishuSendError(FeishuAPIError):
    """API call failed. May be retriable depending on status code."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 0,
        retriable: bool = True,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retriable = retriable


class FeishuRateLimitError(FeishuSendError):
    """Platform rate limit hit. Always retriable with specific delay."""

    def __init__(
        self,
        message: str,
        *,
        retry_after: float = 1.0,
        status_code: int = 429,
    ) -> None:
        super().__init__(message, status_code=status_code, retriable=True)
        self.retry_after = retry_after


class FeishuAuthError(FeishuAPIError):
    """Credentials invalid or expired. Never retry."""
