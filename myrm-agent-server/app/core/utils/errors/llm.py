"""[INPUT]
- app.core.utils.errors.* (POS: shared error primitives)

[OUTPUT]
- handle_llm_exception

[POS]
API error utilities: LLM exception normalisation.
"""

from __future__ import annotations

from typing import NoReturn

from .base import MyrmError, classify_model_failure
from .constants import _FAILOVER_REASON_TO_DETAILED_REASON, logger
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
    logger.warning(format_error_message(exception, context))

    code, reason = classify_model_failure(exception)
    detailed_reason = _FAILOVER_REASON_TO_DETAILED_REASON.get(reason, "unknown_error")

    error_message = f"{context} failed: {exception} [reason: {detailed_reason}]"
    raise MyrmError(code=code, message=error_message)
