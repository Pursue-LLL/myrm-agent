"""[INPUT]
- app.core.utils.errors.* (POS: shared error primitives)

[OUTPUT]
- StandardHTTPException, validation_error, field_validation_error, not_found_error, authentication_error, unauthorized_error, permission_error, conflict_error, unprocessable_error, internal_error, service_unavailable_error, timeout_error, rate_limit_error, external_service_error

[POS]
API error utilities: StandardHTTPException and the HTTP error response factories.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from app.schemas.responses import BusinessCode, ErrorDetail, create_error_response

from .base import _classify_exception
from .constants import (
    logger,
)
from .redaction import redact_error_payload


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
        safe_message = str(redact_error_payload(message))
        error_response = create_error_response(code=business_code, message=safe_message, details=details, trace_id=trace_id)
        super().__init__(status_code=status_code, detail=error_response.model_dump(mode="json"))


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


def not_found_error(
    resource: str = "Resource",
    *,
    details: list[ErrorDetail] | None = None,
    trace_id: str | None = None,
) -> StandardHTTPException:
    """Create resource not found error 404"""
    return StandardHTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        business_code=BusinessCode.RESOURCE_NOT_FOUND,
        message=f"{resource} not found",
        details=details,
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


def conflict_error(
    message: str = "Resource conflict",
    *,
    details: list[ErrorDetail] | None = None,
    trace_id: str | None = None,
) -> StandardHTTPException:
    """Create conflict error 409"""
    return StandardHTTPException(
        status_code=status.HTTP_409_CONFLICT,
        business_code=BusinessCode.RESOURCE_CONFLICT,
        message=message,
        details=details,
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
