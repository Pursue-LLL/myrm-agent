"""Shared memory status helpers for stream session paths.

[INPUT]
- raw `memory_brief_status` object from stream extra_context
- raw runtime injection telemetry from harness context vars

[OUTPUT]
- build_memory_brief_status_payload: normalized payload for SSE/persistence

[POS]
Single-source shape validation for `memory_brief_status` assembly, reused by
both streaming emission and finalize persistence to avoid logic drift.
"""

from __future__ import annotations

from typing import Literal

MemoryBriefState = Literal["ready", "skipped"]
MemoryBriefReason = Literal["timeout", "error"]
MemoryInjectionState = Literal["applied", "not_applied"]
MemoryInjectionSource = Literal["snapshot", "fallback"]
MemoryInjectionReason = Literal[
    "missing_context",
    "not_injected",
    "recall_mode_tools",
    "load_error",
    "static_error",
    "invalid_static_payload",
    "empty_context",
    "already_present",
]

_BRIEF_REASONS: set[MemoryBriefReason] = {"timeout", "error"}
_INJECTION_SOURCES: set[MemoryInjectionSource] = {"snapshot", "fallback"}
_INJECTION_REASONS: set[MemoryInjectionReason] = {
    "missing_context",
    "not_injected",
    "recall_mode_tools",
    "load_error",
    "static_error",
    "invalid_static_payload",
    "empty_context",
    "already_present",
}


def normalize_memory_injection(raw: object) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None

    state = raw.get("state")
    if state == "applied":
        payload: dict[str, str] = {"state": "applied"}
        source = raw.get("source")
        if source in _INJECTION_SOURCES:
            payload["source"] = source
        return payload

    if state == "not_applied":
        payload = {"state": "not_applied"}
        reason = raw.get("reason")
        if reason in _INJECTION_REASONS:
            payload["reason"] = reason
        return payload

    return None


def build_memory_brief_status_payload(
    raw_status: object,
    raw_injection: object,
) -> dict[str, object] | None:
    if not isinstance(raw_status, dict):
        return None

    state = raw_status.get("state")
    payload: dict[str, object]
    if state == "ready":
        payload = {"state": "ready"}
    elif state == "skipped":
        payload = {"state": "skipped"}
        reason = raw_status.get("reason")
        if reason in _BRIEF_REASONS:
            payload["reason"] = reason
    else:
        return None

    injection = normalize_memory_injection(raw_injection)
    if injection is not None:
        payload["injection"] = injection
    return payload

