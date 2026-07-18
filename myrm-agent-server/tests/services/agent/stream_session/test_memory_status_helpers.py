from __future__ import annotations

from app.services.agent.stream_session._memory_status_helpers import (
    build_memory_brief_status_payload,
    normalize_memory_injection,
)


def test_normalize_memory_injection_applied_with_source() -> None:
    payload = normalize_memory_injection({"state": "applied", "source": "snapshot"})
    assert payload == {"state": "applied", "source": "snapshot"}


def test_normalize_memory_injection_not_applied_with_reason() -> None:
    payload = normalize_memory_injection(
        {"state": "not_applied", "reason": "recall_mode_tools"}
    )
    assert payload == {"state": "not_applied", "reason": "recall_mode_tools"}


def test_normalize_memory_injection_rejects_unknown_state() -> None:
    assert normalize_memory_injection({"state": "unknown"}) is None


def test_build_memory_brief_status_payload_ready_with_injection() -> None:
    payload = build_memory_brief_status_payload(
        {"state": "ready"},
        {"state": "applied", "source": "fallback"},
    )
    assert payload == {
        "state": "ready",
        "injection": {"state": "applied", "source": "fallback"},
    }


def test_build_memory_brief_status_payload_skipped_with_reason() -> None:
    payload = build_memory_brief_status_payload(
        {"state": "skipped", "reason": "timeout"},
        {"state": "not_applied", "reason": "already_present"},
    )
    assert payload == {
        "state": "skipped",
        "reason": "timeout",
        "injection": {"state": "not_applied", "reason": "already_present"},
    }


def test_build_memory_brief_status_payload_drops_invalid_reason() -> None:
    payload = build_memory_brief_status_payload(
        {"state": "skipped", "reason": "invalid"},
        {"state": "not_applied", "reason": "bad_reason"},
    )
    assert payload == {
        "state": "skipped",
        "injection": {"state": "not_applied"},
    }


def test_build_memory_brief_status_payload_rejects_unknown_state() -> None:
    assert build_memory_brief_status_payload({"state": "bad"}, None) is None

