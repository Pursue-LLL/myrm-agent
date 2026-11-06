"""[INPUT]
- app.core.utils.errors.* (POS: shared error primitives)

[OUTPUT]
- MyrmError, _classify_exception

[POS]
API error utilities: the MyrmError base class and the shared exception classifier.
"""

from __future__ import annotations

from app.schemas.responses import BusinessCode, ErrorDetail

from .constants import (
    _BUSINESS_CODE_TO_HTTP,
)


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
        status_code: int | None = None,
    ) -> None:
        resolved = message or code.name
        super().__init__(resolved)
        self.code = code
        self.message = resolved
        self.details = details
        self._status_code_override = status_code if status_code is not None else status_code_override

    @property
    def status_code(self) -> int:
        if self._status_code_override is not None:
            return self._status_code_override
        return _BUSINESS_CODE_TO_HTTP.get(self.code, 500)


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
