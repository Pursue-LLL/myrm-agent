"""[INPUT]
- app.core.utils.errors.* (POS: shared error primitives)
- myrm_agent_harness.toolkits.llms (POS: the failure classifier and the model transport's failure base class)

[OUTPUT]
- MyrmError, classify_model_failure, _classify_exception

[POS]
API error utilities: the MyrmError base class and the shared exception classifier.
"""

from __future__ import annotations

import httpx
from myrm_agent_harness.toolkits.llms.errors import FailoverReason, classify_failover_reason
from myrm_agent_harness.toolkits.llms.transport import LLMCallError

from app.schemas.responses import BusinessCode, ErrorDetail

from .constants import (
    _AI_FAILURE_MESSAGES,
    _BUSINESS_CODE_TO_HTTP,
    _DEFAULT_LLM_BUSINESS_CODE,
    _FAILOVER_REASON_TO_BUSINESS_CODE,
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


def classify_model_failure(exception: Exception) -> tuple[BusinessCode, FailoverReason]:
    """The business code and the failover reason of a failed model call, read by the harness failure classifier."""
    try:
        reason = classify_failover_reason(exception)
    except Exception:
        reason = FailoverReason.UNKNOWN
    return _FAILOVER_REASON_TO_BUSINESS_CODE.get(reason, _DEFAULT_LLM_BUSINESS_CODE), reason


def _classify_exception(exception: Exception) -> tuple[BusinessCode, str]:
    """Classify exception and return appropriate business code and message."""
    exception_type = type(exception).__name__
    exception_msg = str(exception)

    # Database errors
    if exception_type in ("OperationalError", "InterfaceError", "DatabaseError"):
        if "connect" in exception_msg.lower():
            return BusinessCode.DB_CONNECTION_ERROR, "Database connection failed"
        return BusinessCode.DB_QUERY_ERROR, "Database operation failed"

    if exception_type == "IntegrityError":
        return BusinessCode.DB_INTEGRITY_ERROR, "Data integrity error"

    if exception_type == "TimeoutError":
        return BusinessCode.DB_TIMEOUT_ERROR, "Database operation timeout"

    # Model-call errors, matched by type rather than class name: the transport raises its own failure classes (one
    # base), which carry the provider's status and body, and lets an httpx timeout through unwrapped. A bad key and an
    # overloaded provider are the same class, so a class name could not tell them apart.
    if isinstance(exception, LLMCallError):
        code, _ = classify_model_failure(exception)
        return code, _AI_FAILURE_MESSAGES[code]

    if isinstance(exception, httpx.TimeoutException):
        return BusinessCode.AI_TIMEOUT_ERROR, _AI_FAILURE_MESSAGES[BusinessCode.AI_TIMEOUT_ERROR]

    # Network/External service errors
    if exception_type in ("ConnectionError", "ConnectionRefusedError", "OSError"):
        return BusinessCode.EXTERNAL_SERVICE_ERROR, "External service connection failed"

    # Default: generic internal error
    return BusinessCode.INTERNAL_ERROR, "Internal server error"
