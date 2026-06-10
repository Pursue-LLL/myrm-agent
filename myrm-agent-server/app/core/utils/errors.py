"""核心错误处理模块

提供 MyrmError 统一业务异常、全局 exception handler、HTTP 异常快捷函数。
所有业务代码应抛出 MyrmError 而非裸 HTTPException，全局 handler 负责转换。
"""

from __future__ import annotations

import logging
import traceback
from typing import NoReturn

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from myrm_agent_harness.toolkits.llms.errors import FailoverReason

from app.database.standard_responses import (
    BusinessCode,
    ErrorDetail,
    create_error_response,
)

logger = logging.getLogger(__name__)

_BUSINESS_CODE_TO_HTTP: dict[BusinessCode, int] = {
    BusinessCode.VALIDATION_ERROR: 400,
    BusinessCode.AUTHENTICATION_FAILED: 401,
    BusinessCode.PERMISSION_DENIED: 403,
    BusinessCode.RESOURCE_NOT_FOUND: 404,
    BusinessCode.RESOURCE_CONFLICT: 409,
    BusinessCode.RATE_LIMIT_ERROR: 429,
    BusinessCode.INTERNAL_ERROR: 500,
    BusinessCode.SERVICE_UNAVAILABLE: 503,
    BusinessCode.TIMEOUT_ERROR: 408,
    BusinessCode.DB_CONNECTION_ERROR: 503,
    BusinessCode.DB_QUERY_ERROR: 500,
    BusinessCode.DB_INTEGRITY_ERROR: 500,
    BusinessCode.DB_TIMEOUT_ERROR: 504,
    BusinessCode.DB_STORAGE_BUSY: 503,
    BusinessCode.EXTERNAL_SERVICE_ERROR: 502,
    BusinessCode.SEARCH_SERVICE_ERROR: 502,
    BusinessCode.FILE_SERVICE_ERROR: 502,
    BusinessCode.AI_MODEL_ERROR: 502,
    BusinessCode.AI_RATE_LIMIT_ERROR: 429,
    BusinessCode.AI_AUTH_ERROR: 401,
    BusinessCode.AI_TIMEOUT_ERROR: 504,
}

# ============================================================================
# MyrmError — single business exception type
# ============================================================================


class MyrmError(Exception):
    """Structured business exception with BusinessCode.

    Raise this instead of HTTPException in business code.  The global handler
    registered by ``register_exception_handlers`` converts it into a JSON
    response automatically.

    Args:
        code: BusinessCode enum member
        message: Human-readable error message
        details: Optional field-level error details
        status_code_override: Override the default HTTP status derived from *code*
    """

    def __init__(
        self,
        code: BusinessCode,
        message: str | None = None,
        *,
        details: list[ErrorDetail] | None = None,
        status_code_override: int | None = None,
    ) -> None:
        resolved = message or code.name
        super().__init__(resolved)
        self.code = code
        self.message = resolved
        self.details = details
        self._status_code_override = status_code_override

    @property
    def status_code(self) -> int:
        if self._status_code_override is not None:
            return self._status_code_override
        return _BUSINESS_CODE_TO_HTTP.get(self.code, 500)


def register_exception_handlers(app: FastAPI) -> None:
    """Register global handlers that convert MyrmError into JSON responses.

    Must be called once during app startup.

    In debug mode (DEBUG=true), error responses include full stack traces
    for faster troubleshooting. In production, only structured error info is returned.
    """
    from app.config.env import is_debug_mode

    @app.exception_handler(MyrmError)
    async def _handle_myrm_error(
        request: Request,
        exc: MyrmError,
    ) -> JSONResponse:
        path = request.url.path
        if exc.status_code >= 500:
            logger.error("[%s] MyrmError %s: %s", path, exc.code.name, exc.message)
        else:
            logger.warning("[%s] MyrmError %s: %s", path, exc.code.name, exc.message)

        body = create_error_response(
            code=exc.code,
            message=exc.message,
            details=exc.details,
        ).model_dump(mode="json")

        # In debug mode, append full traceback
        if is_debug_mode():
            body["traceback"] = traceback.format_exception(type(exc), exc, exc.__traceback__)

        return JSONResponse(
            status_code=exc.status_code,
            content=body,
        )

    @app.exception_handler(AttributeError)
    async def _handle_attribute_error(request: Request, exc: AttributeError) -> JSONResponse:
        """Handle AttributeError (e.g., 'str' object has no attribute 'id')."""
        path = request.url.path
        logger.error(
            "[AttributeError] %s: %s\nTraceback:\n%s",
            path,
            exc,
            traceback.format_exc(),
        )

        body = create_error_response(
            code=BusinessCode.INTERNAL_ERROR,
            message="Data type mismatch detected. Please contact support.",
        ).model_dump(mode="json")

        if is_debug_mode():
            body["traceback"] = traceback.format_exception(type(exc), exc, exc.__traceback__)
            body["exception_type"] = "AttributeError"

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=body,
        )

    @app.exception_handler(TypeError)
    async def _handle_type_error(request: Request, exc: TypeError) -> JSONResponse:
        """Handle TypeError (e.g., None is not subscriptable)."""
        path = request.url.path
        logger.error(
            "[TypeError] %s: %s\nTraceback:\n%s",
            path,
            exc,
            traceback.format_exc(),
        )

        body = create_error_response(
            code=BusinessCode.INTERNAL_ERROR,
            message="Type error detected. Please contact support.",
        ).model_dump(mode="json")

        if is_debug_mode():
            body["traceback"] = traceback.format_exception(type(exc), exc, exc.__traceback__)
            body["exception_type"] = "TypeError"

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=body,
        )

    logger.info("✅ Global error handlers registered (MyrmError + AttributeError + TypeError)")


# ============================================================================
# 标准HTTP异常类（向后兼容，新代码应使用 MyrmError）
# ============================================================================


class StandardHTTPException(HTTPException):
    """标准HTTP异常，包含结构化的错误响应"""

    def __init__(
        self,
        status_code: int,
        business_code: BusinessCode,
        message: str,
        details: list[ErrorDetail] | None = None,
        trace_id: str | None = None,
    ):
        error_response = create_error_response(code=business_code, message=message, details=details, trace_id=trace_id)
        super().__init__(status_code=status_code, detail=error_response.model_dump(mode="json"))


# ============================================================================
# HTTP异常快捷函数
# ============================================================================


def validation_error(
    message: str = "Invalid request parameters",
    details: list[ErrorDetail] | None = None,
    trace_id: str | None = None,
) -> StandardHTTPException:
    """Create parameter validation error 400"""
    return StandardHTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        business_code=BusinessCode.VALIDATION_ERROR,
        message=message,
        details=details,
        trace_id=trace_id,
    )


def field_validation_error(field_errors: dict[str, object]) -> StandardHTTPException:
    """Create field validation error"""
    details = [ErrorDetail(field=str(field), issue=str(issue)) for field, issue in field_errors.items()]
    return validation_error(message="Request parameter validation failed", details=details)


def not_found_error(resource: str = "Resource", trace_id: str | None = None) -> StandardHTTPException:
    """Create resource not found error 404"""
    return StandardHTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        business_code=BusinessCode.RESOURCE_NOT_FOUND,
        message=f"{resource} not found",
        trace_id=trace_id,
    )


def authentication_error(message: str = "Authentication failed", trace_id: str | None = None) -> StandardHTTPException:
    """Create authentication error 401"""
    return StandardHTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        business_code=BusinessCode.AUTHENTICATION_FAILED,
        message=message,
        trace_id=trace_id,
    )


def unauthorized_error(message: str = "Unauthorized", trace_id: str | None = None) -> StandardHTTPException:
    """Create unauthorized error 401 (alias for authentication_error)"""
    return StandardHTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        business_code=BusinessCode.AUTHENTICATION_FAILED,
        message=message,
        trace_id=trace_id,
    )


def permission_error(message: str = "Permission denied", trace_id: str | None = None) -> StandardHTTPException:
    """Create permission error 403"""
    return StandardHTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        business_code=BusinessCode.PERMISSION_DENIED,
        message=message,
        trace_id=trace_id,
    )


def conflict_error(message: str = "Resource conflict", trace_id: str | None = None) -> StandardHTTPException:
    """Create conflict error 409"""
    return StandardHTTPException(
        status_code=status.HTTP_409_CONFLICT,
        business_code=BusinessCode.RESOURCE_CONFLICT,
        message=message,
        trace_id=trace_id,
    )


def unprocessable_error(
    message: str = "Request cannot be processed",
    details: list[ErrorDetail] | None = None,
    trace_id: str | None = None,
) -> StandardHTTPException:
    """Create unprocessable error 422"""
    return StandardHTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        business_code=BusinessCode.VALIDATION_ERROR,
        message=message,
        details=details,
        trace_id=trace_id,
    )


def _classify_exception(exception: Exception) -> tuple[BusinessCode, str]:
    """Classify exception and return appropriate business code and message."""
    exception_type = type(exception).__name__
    exception_msg = str(exception)

    # Database errors
    if exception_type in ("OperationalError", "InterfaceError", "DatabaseError"):
        if "connect" in exception_msg.lower() or "connection" in exception_msg.lower():
            return BusinessCode.DB_CONNECTION_ERROR, "Database connection failed"
        return BusinessCode.DB_QUERY_ERROR, "Database operation failed"

    if exception_type == "IntegrityError":
        return BusinessCode.DB_INTEGRITY_ERROR, "Data integrity error"

    if exception_type in ("TimeoutError", "asyncio.TimeoutError"):
        return BusinessCode.DB_TIMEOUT_ERROR, "Database operation timeout"

    # AI/LLM errors
    if exception_type in ("AuthenticationError", "APIKeyError"):
        return BusinessCode.AI_AUTH_ERROR, "AI service authentication failed"

    if exception_type == "RateLimitError":
        return BusinessCode.AI_RATE_LIMIT_ERROR, "AI service rate limited"

    if exception_type in ("Timeout", "ReadTimeout", "ConnectTimeout"):
        return BusinessCode.AI_TIMEOUT_ERROR, "AI service timeout"

    if exception_type in ("APIError", "APIConnectionError", "ServiceUnavailableError"):
        return BusinessCode.AI_MODEL_ERROR, "AI model call failed"

    # Network/External service errors
    if exception_type in ("ConnectionError", "ConnectionRefusedError", "OSError"):
        return BusinessCode.EXTERNAL_SERVICE_ERROR, "External service connection failed"

    # Default: generic internal error
    return BusinessCode.INTERNAL_ERROR, "Internal server error"


def internal_error(
    message: str = "Internal server error",
    operation: str | None = None,
    trace_id: str | None = None,
    exception: Exception | None = None,
) -> StandardHTTPException:
    """Create internal server error 500

    Args:
        message: Error message (only used if no exception provided)
        operation: Operation name (e.g., "Get chat list")
        trace_id: Trace ID for debugging
        exception: Original exception - used to classify error and log details
    """
    business_code = BusinessCode.INTERNAL_ERROR
    user_message = message

    if exception:
        # Classify exception and get appropriate code/message
        business_code, user_message = _classify_exception(exception)

        # Add operation context to user message
        if operation:
            user_message = f"{operation} failed: {user_message}"

        # Log detailed error info (not exposed to frontend)
        exception_detail = f"{type(exception).__name__}: {str(exception)}"
        logger.warning(f"[{business_code}] {operation or 'Operation'} - {exception_detail}")
    elif operation:
        user_message = f"{operation} failed"

    return StandardHTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        business_code=business_code,
        message=user_message,
        trace_id=trace_id,
    )


def service_unavailable_error(
    message: str = "Service temporarily unavailable", trace_id: str | None = None
) -> StandardHTTPException:
    """Create service unavailable error 503"""
    return StandardHTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        business_code=BusinessCode.SERVICE_UNAVAILABLE,
        message=message,
        trace_id=trace_id,
    )


def timeout_error(
    message: str = "Request timeout", operation: str | None = None, trace_id: str | None = None
) -> StandardHTTPException:
    """Create timeout error 408"""
    if operation:
        message = f"{operation} timeout"

    return StandardHTTPException(
        status_code=status.HTTP_408_REQUEST_TIMEOUT,
        business_code=BusinessCode.TIMEOUT_ERROR,
        message=message,
        trace_id=trace_id,
    )


def rate_limit_error(
    operation: str = "Request", message: str | None = None, trace_id: str | None = None
) -> StandardHTTPException:
    """Create rate limit error 429"""
    if not message:
        message = f"{operation} rate limit exceeded"

    return StandardHTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        business_code=BusinessCode.RATE_LIMIT_ERROR,
        message=message,
        trace_id=trace_id,
    )


def external_service_error(service: str, message: str | None = None, trace_id: str | None = None) -> StandardHTTPException:
    """Create external service error 502"""
    if not message:
        message = f"{service} service error"

    return StandardHTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        business_code=BusinessCode.EXTERNAL_SERVICE_ERROR,
        message=message,
        trace_id=trace_id,
    )


# ============================================================================
# 错误格式化工具
# ============================================================================


def format_error_message(exception: Exception, context: str = "", include_traceback: bool = False) -> str:
    """格式化异常信息

    Args:
        exception: 异常对象
        context: 错误上下文描述
        include_traceback: 是否包含堆栈跟踪信息

    Returns:
        格式化后的错误信息字符串
    """
    error_type = type(exception).__name__
    error_msg = str(exception)

    # 如果异常的str()返回空字符串，使用repr()获取更多信息
    if not error_msg or error_msg.strip() == "":
        error_msg = repr(exception)

    # 如果仍然为空，提供默认错误信息
    if not error_msg or error_msg.strip() == "":
        error_msg = f"{error_type} occurred"

    if context:
        formatted_error = f"{context} - {error_type}: {error_msg}"
    else:
        formatted_error = f"{error_type}: {error_msg}"

    if include_traceback:
        tb = traceback.format_exc()
        formatted_error += f"\nStack trace:\n{tb}"

    return formatted_error


def log_and_format_error(
    exception: Exception,
    context: str = "",
    include_traceback: bool = False,
) -> str:
    """记录日志并格式化异常信息

    Args:
        exception: 异常对象
        context: 错误上下文描述
        include_traceback: 是否包含堆栈跟踪信息

    Returns:
        格式化后的错误信息字符串
    """
    formatted_error = format_error_message(exception, context, include_traceback)
    logger.warning(formatted_error)

    return formatted_error


# ============================================================================
# LLM相关错误处理
# ============================================================================

_FAILOVER_REASON_TO_BUSINESS_CODE: dict[FailoverReason, BusinessCode] = {
    FailoverReason.RATE_LIMIT: BusinessCode.AI_RATE_LIMIT_ERROR,
    FailoverReason.LONG_CONTEXT_TIER: BusinessCode.AI_RATE_LIMIT_ERROR,
    FailoverReason.AUTH_PERMANENT: BusinessCode.AI_AUTH_ERROR,
    FailoverReason.SESSION_EXPIRED: BusinessCode.AI_AUTH_ERROR,
    FailoverReason.TIMEOUT: BusinessCode.AI_TIMEOUT_ERROR,
    FailoverReason.BILLING: BusinessCode.AI_RATE_LIMIT_ERROR,
    # All other model/format/capacity errors → AI_MODEL_ERROR
}

_DEFAULT_LLM_BUSINESS_CODE = BusinessCode.AI_MODEL_ERROR

_FAILOVER_REASON_TO_DETAILED_REASON: dict[FailoverReason, str] = {
    FailoverReason.RATE_LIMIT: "rate_limit_exceeded",
    FailoverReason.LONG_CONTEXT_TIER: "long_context_tier",
    FailoverReason.AUTH_PERMANENT: "authentication_failed",
    FailoverReason.SESSION_EXPIRED: "session_expired",
    FailoverReason.TIMEOUT: "request_timeout",
    FailoverReason.BILLING: "insufficient_quota",
    FailoverReason.OVERLOADED: "model_overloaded",
    FailoverReason.CONTEXT_OVERFLOW: "context_overflow",
    FailoverReason.SAFETY_BLOCK: "safety_block",
    FailoverReason.FORMAT_ERROR: "format_error",
    FailoverReason.RESPONSE_FORMAT_ERROR: "response_format_error",
    FailoverReason.MODEL_NOT_FOUND: "model_not_found",
    FailoverReason.THINKING_SIGNATURE: "thinking_signature",
    FailoverReason.IMAGE_TOO_LARGE: "image_too_large",
    FailoverReason.MEDIA_REJECTED: "media_rejected",
    FailoverReason.PROVIDER_POLICY_BLOCKED: "provider_policy_blocked",
}


def handle_llm_exception(exception: Exception, context: str = "Model call") -> NoReturn:
    """Classify LLM exception and raise a structured MyrmError with detailed error info.

    Uses the harness-layer ``classify_failover_reason`` for deep error analysis
    (regex patterns, status codes, nested error extraction) instead of naive
    exception-type matching.

    Args:
        exception: Caught LLM-related exception
        context: Error context description

    Raises:
        MyrmError: Structured business error with detailed classification
    """
    from myrm_agent_harness.toolkits.llms.errors import classify_failover_reason

    logger.warning(format_error_message(exception, context))

    try:
        reason = classify_failover_reason(exception)
    except Exception:
        reason = FailoverReason.UNKNOWN

    code = _FAILOVER_REASON_TO_BUSINESS_CODE.get(reason, _DEFAULT_LLM_BUSINESS_CODE)
    detailed_reason = _FAILOVER_REASON_TO_DETAILED_REASON.get(reason, "unknown_error")

    error_message = f"{context} failed: {exception} [reason: {detailed_reason}]"
    raise MyrmError(code=code, message=error_message)
