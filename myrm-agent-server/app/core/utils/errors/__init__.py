"""API error utilities.

[INPUT]
- fastapi / pydantic (POS: HTTP error primitives)

[OUTPUT]
- MyrmError, the HTTP error factories, the exception handlers and the LLM error normaliser.

[POS]
Aggregate exit of the error-utilities package; import path unchanged for 86 call sites.
"""

from __future__ import annotations

from .base import (
    MyrmError,
    _classify_exception,
)
from .handlers import (
    register_exception_handlers,
)
from .http import (
    StandardHTTPException,
    authentication_error,
    conflict_error,
    external_service_error,
    field_validation_error,
    internal_error,
    not_found_error,
    permission_error,
    rate_limit_error,
    service_unavailable_error,
    timeout_error,
    unauthorized_error,
    unprocessable_error,
    validation_error,
)
from .llm import (
    handle_llm_exception,
)
from .redaction import (
    fold_user_home_paths,
    format_error_message,
    log_and_format_error,
    redact_error_payload,
)

__all__ = [
    "_classify_exception",
    "MyrmError",
    "fold_user_home_paths",
    "redact_error_payload",
    "register_exception_handlers",
    "StandardHTTPException",
    "validation_error",
    "field_validation_error",
    "not_found_error",
    "authentication_error",
    "unauthorized_error",
    "permission_error",
    "conflict_error",
    "unprocessable_error",
    "internal_error",
    "service_unavailable_error",
    "timeout_error",
    "rate_limit_error",
    "external_service_error",
    "format_error_message",
    "log_and_format_error",
    "handle_llm_exception",
]
