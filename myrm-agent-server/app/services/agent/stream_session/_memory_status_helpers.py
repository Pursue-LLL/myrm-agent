"""Shared memory status helpers for stream session paths.

[INPUT]
- raw `memory_brief_status` object from stream extra_context
- raw runtime injection telemetry from harness context vars (validated against
  `myrm_agent_harness.api.hooks` public injection contract)

[OUTPUT]
- get_memory_brief_status_contract: normalized brief enum contract for frontend parity checks
- build_memory_brief_status_payload: normalized payload for SSE/persistence (`skipped` includes source)

[POS]
Single-source shape validation for `memory_brief_status` assembly, reused by
both streaming emission and finalize persistence to avoid logic drift.
"""

from __future__ import annotations

import logging
from typing import Literal

from myrm_agent_harness.api.hooks import get_memory_runtime_injection_contract

MemoryBriefState = Literal["ready", "skipped"]
MemoryBriefReason = Literal["timeout", "error"]
MemoryBriefSource = Literal["preflight", "runtime_fallback"]

MEMORY_BRIEF_STATES: tuple[MemoryBriefState, ...] = ("ready", "skipped")
MEMORY_BRIEF_REASONS: tuple[MemoryBriefReason, ...] = ("timeout", "error")
MEMORY_BRIEF_SOURCES: tuple[MemoryBriefSource, ...] = ("preflight", "runtime_fallback")
_BRIEF_REASONS: set[MemoryBriefReason] = set(MEMORY_BRIEF_REASONS)
_BRIEF_SOURCES: set[MemoryBriefSource] = set(MEMORY_BRIEF_SOURCES)
_INJECTION_CONTRACT = get_memory_runtime_injection_contract()
_INJECTION_STATES: frozenset[str] = frozenset(_INJECTION_CONTRACT.get("states", ()))
_INJECTION_SOURCES: frozenset[str] = frozenset(_INJECTION_CONTRACT.get("sources", ()))
_INJECTION_REASONS: frozenset[str] = frozenset(_INJECTION_CONTRACT.get("reasons", ()))

logger = logging.getLogger(__name__)

try:
    from prometheus_client import Counter
except Exception:  # pragma: no cover - exporter is optional in some runtimes
    Counter = None  # type: ignore[assignment]

_METRIC_NONE = "none"
_METRIC_UNKNOWN = "unknown"
_VALID_PHASES: frozenset[str] = frozenset({"stream", "persist"})
_warned_unknown_values: set[str] = set()

if Counter is not None:
    _MEMORY_STATUS_EVENTS = Counter(
        "myrm_memory_brief_status_events_total",
        "Memory brief status events emitted by stream and persistence paths.",
        labelnames=(
            "phase",
            "brief_state",
            "brief_reason",
            "brief_source",
            "injection_state",
            "injection_source",
            "injection_reason",
        ),
    )
    _MEMORY_NOT_APPLIED = Counter(
        "myrm_memory_brief_injection_not_applied_total",
        "Memory brief not_applied injection events by reason/source.",
        labelnames=("phase", "brief_source", "reason"),
    )
    _MEMORY_STATUS_UNKNOWN = Counter(
        "myrm_memory_brief_status_unknown_total",
        "Unknown memory brief/injection enum values observed at runtime.",
        labelnames=("field", "kind"),
    )
else:  # pragma: no cover - exercised only when prometheus dependency is absent
    _MEMORY_STATUS_EVENTS = None
    _MEMORY_NOT_APPLIED = None
    _MEMORY_STATUS_UNKNOWN = None


def _record_unknown(field: str, kind: str, raw_value: object) -> None:
    if _MEMORY_STATUS_UNKNOWN is not None:
        _MEMORY_STATUS_UNKNOWN.labels(field=field, kind=kind).inc()
    key = f"{field}:{kind}:{raw_value!r}"
    if key in _warned_unknown_values:
        return
    if len(_warned_unknown_values) >= 256:
        return
    _warned_unknown_values.add(key)
    logger.warning("Unknown memory status value detected: %s=%r (%s)", field, raw_value, kind)


def get_memory_brief_status_contract() -> dict[str, tuple[str, ...]]:
    """Expose normalized brief status enums for frontend parity tests."""
    return {
        "states": MEMORY_BRIEF_STATES,
        "reasons": MEMORY_BRIEF_REASONS,
        "sources": MEMORY_BRIEF_SOURCES,
    }


def normalize_memory_injection(raw: object) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None

    state = raw.get("state")
    if state == "applied" and "applied" in _INJECTION_STATES:
        payload: dict[str, str] = {"state": "applied"}
        source = raw.get("source")
        if source in _INJECTION_SOURCES:
            payload["source"] = source
        elif source is not None:
            _record_unknown("injection_source", "unrecognized_source", source)
        return payload

    if state == "not_applied" and "not_applied" in _INJECTION_STATES:
        payload = {"state": "not_applied"}
        reason = raw.get("reason")
        if reason in _INJECTION_REASONS:
            payload["reason"] = reason
        elif reason is not None:
            _record_unknown("injection_reason", "unrecognized_reason", reason)
        return payload

    if state is not None:
        _record_unknown("injection_state", "unrecognized_state", state)
    return None


def build_memory_brief_status_payload(
    raw_status: object,
    raw_injection: object,
) -> dict[str, object] | None:
    injection = normalize_memory_injection(raw_injection)
    if not isinstance(raw_status, dict):
        # Resume paths may not have preflight status, but runtime injection
        # telemetry can still explain what happened in this turn.
        if injection is None:
            return None
        return {"state": "skipped", "source": "runtime_fallback", "injection": injection}

    state = raw_status.get("state")
    payload: dict[str, object]
    if state == "ready" and "ready" in MEMORY_BRIEF_STATES:
        payload = {"state": "ready"}
    elif state == "skipped" and "skipped" in MEMORY_BRIEF_STATES:
        payload = {"state": "skipped", "source": "preflight"}
        reason = raw_status.get("reason")
        if reason in _BRIEF_REASONS:
            payload["reason"] = reason
        elif reason is not None:
            _record_unknown("brief_reason", "unrecognized_reason", reason)
    else:
        if state is not None:
            _record_unknown("brief_state", "unrecognized_state", state)
        if injection is None:
            return None
        return {"state": "skipped", "source": "runtime_fallback", "injection": injection}

    if injection is not None:
        payload["injection"] = injection
    return payload


def observe_memory_brief_status_payload(*, phase: str, payload: dict[str, object]) -> None:
    """Emit normalized per-turn observability metrics for memory status payloads."""
    if _MEMORY_STATUS_EVENTS is None:
        return
    if phase not in _VALID_PHASES:
        _record_unknown("phase", "unrecognized_phase", phase)
        return

    brief_state = payload.get("state")
    brief_reason = payload.get("reason")
    brief_source = payload.get("source")
    injection = payload.get("injection")

    brief_source_label = _METRIC_NONE
    if isinstance(brief_source, str) and brief_source:
        if brief_source in _BRIEF_SOURCES:
            brief_source_label = brief_source
        else:
            brief_source_label = _METRIC_UNKNOWN
            _record_unknown("brief_source", "unrecognized_source", brief_source)

    injection_state: str = _METRIC_NONE
    injection_source: str = _METRIC_NONE
    injection_reason: str = _METRIC_NONE
    if isinstance(injection, dict):
        raw_injection_state = injection.get("state")
        if isinstance(raw_injection_state, str) and raw_injection_state:
            injection_state = raw_injection_state
        raw_injection_source = injection.get("source")
        if isinstance(raw_injection_source, str) and raw_injection_source:
            injection_source = raw_injection_source
        raw_injection_reason = injection.get("reason")
        if isinstance(raw_injection_reason, str) and raw_injection_reason:
            injection_reason = raw_injection_reason

    _MEMORY_STATUS_EVENTS.labels(
        phase=phase,
        brief_state=brief_state if isinstance(brief_state, str) and brief_state else _METRIC_NONE,
        brief_reason=brief_reason if isinstance(brief_reason, str) and brief_reason else _METRIC_NONE,
        brief_source=brief_source_label,
        injection_state=injection_state,
        injection_source=injection_source,
        injection_reason=injection_reason,
    ).inc()
    if _MEMORY_NOT_APPLIED is not None and injection_state == "not_applied":
        _MEMORY_NOT_APPLIED.labels(
            phase=phase,
            brief_source=brief_source_label,
            reason=injection_reason if injection_reason != _METRIC_NONE else _METRIC_UNKNOWN,
        ).inc()

