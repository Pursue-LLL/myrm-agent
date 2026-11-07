"""[INPUT]
- （无跨模块依赖）

[OUTPUT]
- _SSE_DATA_PREFIX / _MAX_REASONING_CHARS / _PERSISTED_STATUS_STEP_KEYS
- _FAILOVER_REASON_TO_STEP_KEY / _INTERRUPT_REPLAY_TYPES

[POS]
handlers / state / core 共用的限制与事件映射。
"""

from __future__ import annotations

_SSE_DATA_PREFIX = "data: "
_MAX_REASONING_CHARS = 24_000
_PERSISTED_STATUS_STEP_KEYS = frozenset({"archive_restore_blocked", "archive_restore_result"})
_FAILOVER_REASON_TO_STEP_KEY: dict[str, str] = {
    "rate_limit": "model_failover_rate_limit",
    "overloaded": "model_failover_overloaded",
    "timeout": "model_failover_timeout",
    "billing": "model_failover_billing",
    "context_overflow": "model_failover_context_overflow",
    "response_format": "model_failover_response_format_error",
    "format": "model_failover_response_format_error",
    "model_not_found": "model_failover_model_not_found",
    "auth_permanent": "model_failover_auth",
    "session_expired": "model_failover_auth",
    "safety_block": "safety_fallback_active",
}
_INTERRUPT_REPLAY_TYPES: frozenset[str] = frozenset(
    {
        "tool_approval_request",
        "approval_required",
        "clarification_required",
    }
)
