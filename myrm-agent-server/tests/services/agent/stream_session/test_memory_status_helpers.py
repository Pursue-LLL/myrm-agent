from __future__ import annotations

import app.services.agent.stream_session._memory_status_helpers as memory_status_helpers
from app.services.agent.stream_session._memory_status_helpers import (
    build_memory_brief_status_payload,
    get_memory_brief_status_contract,
    normalize_memory_injection,
    observe_memory_brief_status_payload,
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
        "source": "preflight",
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
        "source": "preflight",
        "injection": {"state": "not_applied"},
    }


def test_build_memory_brief_status_payload_rejects_unknown_state() -> None:
    assert build_memory_brief_status_payload({"state": "bad"}, None) is None


def test_build_memory_brief_status_payload_falls_back_when_state_unknown_but_injection_exists() -> None:
    payload = build_memory_brief_status_payload(
        {"state": "bad"},
        {"state": "not_applied", "reason": "missing_context"},
    )
    assert payload == {
        "state": "skipped",
        "source": "runtime_fallback",
        "injection": {"state": "not_applied", "reason": "missing_context"},
    }


def test_build_memory_brief_status_payload_falls_back_to_skipped_when_status_missing() -> None:
    payload = build_memory_brief_status_payload(
        None,
        {"state": "not_applied", "reason": "missing_context"},
    )
    assert payload == {
        "state": "skipped",
        "source": "runtime_fallback",
        "injection": {"state": "not_applied", "reason": "missing_context"},
    }


def test_build_memory_brief_status_payload_falls_back_when_status_missing_and_applied() -> None:
    payload = build_memory_brief_status_payload(
        None,
        {"state": "applied", "source": "fallback"},
    )
    assert payload == {
        "state": "skipped",
        "source": "runtime_fallback",
        "injection": {"state": "applied", "source": "fallback"},
    }


def test_memory_brief_status_contract_includes_source_enum() -> None:
    assert get_memory_brief_status_contract()["sources"] == (
        "preflight",
        "runtime_fallback",
    )


class _DummyCounter:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def labels(self, **labels: str) -> _DummyCounter:
        self.calls.append(labels)
        return self

    def inc(self) -> None:
        return None


def test_observe_memory_brief_status_payload_emits_metric_labels(monkeypatch) -> None:
    metric_counter = _DummyCounter()
    not_applied_counter = _DummyCounter()
    monkeypatch.setattr(memory_status_helpers, "_MEMORY_STATUS_EVENTS", metric_counter)
    monkeypatch.setattr(memory_status_helpers, "_MEMORY_NOT_APPLIED", not_applied_counter)

    observe_memory_brief_status_payload(
        phase="stream",
        payload={
            "state": "skipped",
            "source": "preflight",
            "reason": "timeout",
            "injection": {"state": "not_applied", "reason": "missing_context"},
        },
    )

    assert metric_counter.calls == [
        {
            "phase": "stream",
            "brief_state": "skipped",
            "brief_reason": "timeout",
            "brief_source": "preflight",
            "injection_state": "not_applied",
            "injection_source": "none",
            "injection_reason": "missing_context",
        }
    ]
    assert not_applied_counter.calls == [
        {
            "phase": "stream",
            "brief_source": "preflight",
            "reason": "missing_context",
        }
    ]


def test_observe_memory_brief_status_payload_records_unknown_phase(monkeypatch) -> None:
    metric_counter = _DummyCounter()
    unknown_counter = _DummyCounter()
    monkeypatch.setattr(memory_status_helpers, "_MEMORY_STATUS_EVENTS", metric_counter)
    monkeypatch.setattr(memory_status_helpers, "_MEMORY_STATUS_UNKNOWN", unknown_counter)
    monkeypatch.setattr(memory_status_helpers, "_warned_unknown_values", set())

    observe_memory_brief_status_payload(phase="bad_phase", payload={"state": "ready"})

    assert metric_counter.calls == []
    assert unknown_counter.calls == [{"field": "phase", "kind": "unrecognized_phase"}]


def test_normalize_memory_injection_records_unknown_reason(monkeypatch) -> None:
    unknown_counter = _DummyCounter()
    monkeypatch.setattr(memory_status_helpers, "_MEMORY_STATUS_UNKNOWN", unknown_counter)
    monkeypatch.setattr(memory_status_helpers, "_warned_unknown_values", set())

    payload = normalize_memory_injection({"state": "not_applied", "reason": "unsupported_reason"})

    assert payload == {"state": "not_applied"}
    assert unknown_counter.calls == [{"field": "injection_reason", "kind": "unrecognized_reason"}]

