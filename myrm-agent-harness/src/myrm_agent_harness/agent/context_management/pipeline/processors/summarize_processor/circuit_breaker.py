"""Summarize 电路熔断：连续失败计数、错误分级冷却与半开探测。

[INPUT]
- myrm_agent_harness.observability.metrics.circuit_breaker_metrics::circuit_breaker_state (POS: 电路熔断指标)
- myrm_agent_harness.utils.logger_utils::get_agent_logger (POS: 统一日志器)

[OUTPUT]
- _get_failures / _set_failures / _is_circuit_open / _is_half_open_probe: 熔断状态读写与探测

[POS]
`summarize_processor/` 的熔断子系统；失败状态只保存在本模块。
"""

from __future__ import annotations

import time

from myrm_agent_harness.observability.metrics.circuit_breaker_metrics import (
    circuit_breaker_state,
)
from myrm_agent_harness.utils.logger_utils import get_agent_logger

logger = get_agent_logger(__name__)

MAX_CONSECUTIVE_SUMMARIZE_FAILURES = 3
_HALF_OPEN_PROBE_INTERVAL = 2

# Tiered cooldown periods by error type
_CIRCUIT_COOLDOWN_TRANSIENT = 60  # 1 minute for transient errors (timeout, rate limit)
_CIRCUIT_COOLDOWN_PERMANENT = 600  # 10 minutes for permanent errors (model not found, 503)
_CIRCUIT_COOLDOWN_AUTH = 1800  # 30 minutes for auth errors (invalid API key)

_summarize_failures: int = 0
_fallback_calls: int = 0
_circuit_open_time: float | None = None
_circuit_cooldown_seconds: int = _CIRCUIT_COOLDOWN_AUTH


def _get_failures() -> int:
    global _summarize_failures
    return _summarize_failures


def _classify_error_type(exc: Exception) -> str:
    """Classify error type for tiered circuit breaker cooldown.

    Returns:
        Error type: 'auth' | 'permanent' | 'transient'
    """
    exc_str = str(exc).lower()

    if any(
        kw in exc_str
        for kw in [
            "unauthorized",
            "forbidden",
            "invalid api key",
            "authentication failed",
        ]
    ):
        return "auth"

    if any(
        kw in exc_str
        for kw in [
            "model not found",
            "does not exist",
            "not available",
            "no available channel",
        ]
    ):
        return "permanent"

    status_code = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    if status_code in (404, 503):
        return "permanent"

    return "transient"


def _set_failures(n: int, error_type: str = "auth") -> None:
    """Set failure count and cooldown time based on error type."""
    global _summarize_failures, _circuit_open_time, _circuit_cooldown_seconds
    _summarize_failures = n

    if n >= MAX_CONSECUTIVE_SUMMARIZE_FAILURES:
        _circuit_open_time = time.time()

        if error_type == "auth":
            _circuit_cooldown_seconds = _CIRCUIT_COOLDOWN_AUTH
        elif error_type == "permanent":
            _circuit_cooldown_seconds = _CIRCUIT_COOLDOWN_PERMANENT
        else:  # transient
            _circuit_cooldown_seconds = _CIRCUIT_COOLDOWN_TRANSIENT

        logger.warning(
            "[Summarize] Circuit breaker opened, cooldown: %ds (type: %s)",
            _circuit_cooldown_seconds,
            error_type,
        )


def _record_fallback_call() -> None:
    global _fallback_calls
    _fallback_calls += 1


def _is_circuit_open() -> bool:
    """Check if circuit breaker is open (considering cooldown period)."""
    global _summarize_failures, _circuit_open_time, _fallback_calls, _circuit_cooldown_seconds
    failures = _get_failures()
    if failures < MAX_CONSECUTIVE_SUMMARIZE_FAILURES:
        return False

    open_time = _circuit_open_time
    if open_time is None:
        _circuit_open_time = time.time()
        return True

    elapsed = time.time() - open_time
    if elapsed > _circuit_cooldown_seconds:
        logger.info(
            "[Summarize] Circuit breaker cooldown completed (%ds) — attempting auto-recovery",
            _circuit_cooldown_seconds,
        )
        _set_failures(0)
        _fallback_calls = 0
        _circuit_open_time = None
        circuit_breaker_state.labels(component="summarize").set(0)  # CLOSED
        return False

    return True


def _is_half_open_probe() -> bool:
    """Allow one LLM attempt every N fallback calls to detect recovery."""
    global _fallback_calls
    calls = _fallback_calls
    return calls > 0 and calls % _HALF_OPEN_PROBE_INTERVAL == 0


def _cooldown_seconds() -> int:
    """Current cooldown applied when the circuit opens."""
    return _circuit_cooldown_seconds


def _reset_fallback_calls() -> None:
    """Reset the half-open probe counter after a successful call."""
    global _fallback_calls
    _fallback_calls = 0
