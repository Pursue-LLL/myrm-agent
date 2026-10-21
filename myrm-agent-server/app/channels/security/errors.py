"""Standardized webhook error responses.

遵循RFC 7807 Problem Details规范，provides机器可Parse ErrorFormat。

[INPUT]
( no Externaldepends on)

[OUTPUT]
- WebhookResponseError: RFC 7807standard化ErrorResponse
- SecurityViolation: Security违规Exception

[POS]
Webhook error response layer. Provides RFC 7807 standardized error format,
supporting machine-parsable and human-readable output without leaking sensitive data.
"""

from __future__ import annotations

import time


class WebhookResponseError(Exception):
    """RFC 7807 Problem Detailsstandard化ErrorResponse（封装trace_id）

    特性：
    - 机器可Parse（type/status/detailField）
    - 人类可读（titleField）
    - 脱敏Process（ not ContainsInternalPath、敏感时间戳 etc.）
    - 国际化友好（ErrorTypeindependent于Error消息）
    - 强制追踪（trace_id in 构造时注入， avoid 遗漏）

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
        """构造ErrorResponse

        Args:
            status_code: HTTPState码
            error_type: ErrorType标识（如body-too-large）
            title: ErrorHeading（人类可读）
            detail: Error详情（Concreteoriginal因）
            trace_id: 分布式追踪ID（required， ensure 可追踪）
            retry_after: Retry延迟秒数（Support429/503 etc.State码）
        """
        self.status_code = status_code
        self.error_type = error_type
        self.title = title
        self.detail = detail
        self.trace_id = trace_id
        self.retry_after = retry_after
        super().__init__(detail)

    def to_dict(self) -> dict[str, object]:
        """Convert is RFC 7807 Problem DetailsFormat

        Returns:
            RFC 7807standardFormat ErrorResponseDict（含trace_id）
        """
        result: dict[str, object] = {
            "type": f"https://docs.example.com/errors/webhook/{self.error_type}",
            "title": self.title,
            "status": self.status_code,
            "detail": self.detail,
            "timestamp": time.time(),
            "trace_id": self.trace_id,
        }

        # RFC 6585/7231: Supportretry_after（429 Rate Limit, 503 Service Unavailable etc.）
        if self.retry_after is not None:
            result["retry_after"] = self.retry_after

        return result


class SecurityViolationError(WebhookResponseError):
    """Security违规Exception（SignatureValidateFailure、重放攻击 etc.）"""

    def __init__(
        self,
        detail: str,
        trace_id: str,
        error_type: str = "security-violation",
    ) -> None:
        """构造Security违规Exception

        Args:
            detail: Error详情（如"Invalid signature"）
            trace_id: 分布式追踪ID
            error_type: ErrorType标识（Defaultsecurity-violation）
        """
        super().__init__(
            status_code=401,
            error_type=error_type,
            title="Security Violation",
            detail=detail,
            trace_id=trace_id,
        )
