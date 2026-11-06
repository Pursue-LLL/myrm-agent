"""[INPUT]
- app.core.utils.errors.* (POS: shared error primitives)

[OUTPUT]
- handle_llm_exception

[POS]
API error utilities: LLM exception normalisation.
"""

from __future__ import annotations

from typing import NoReturn

from myrm_agent_harness.toolkits.llms.errors import FailoverReason

from .base import MyrmError
from .constants import (
    _DEFAULT_LLM_BUSINESS_CODE,
    _FAILOVER_REASON_TO_BUSINESS_CODE,
    _FAILOVER_REASON_TO_DETAILED_REASON,
    logger,
)
from .redaction import format_error_message


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
