"""[INPUT]
- (stdlib only)

[OUTPUT]
- logger and the shared error-code / home-path constants

[POS]
Shared constants of the API error utilities.
"""

from __future__ import annotations

import logging
import re

from myrm_agent_harness.toolkits.llms.errors import FailoverReason

from app.schemas.responses import BusinessCode

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


_HOME_DIR_UNIX_RE = re.compile(r"(?<!https:)(?<!http:)(^|[\s\"'(\[:])(?:/Users/|/home/)[^/\s\"')\]:]+(/?)")


_HOME_DIR_ROOT_RE = re.compile(r"(?<!https:)(?<!http:)(^|[\s\"'(\[:])/root(/|(?=[\s\"')\]:]|$))")


_HOME_DIR_WIN_RE = re.compile(r"(^|[\s\"'(\[:])[A-Za-z]:\\Users\\[^\\/\s\"')\]:]+(\\?)")


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
    FailoverReason.TLS_CERTIFICATE: "tls_certificate",
}
