from __future__ import annotations

import asyncio
from typing import cast
from unittest.mock import MagicMock

import pytest

import app.services.agent.stream_session.turn_capability_terminal as turn_capability_terminal
from app.services.agent.params.models import AgentRequest, TurnCapabilityTelemetryRequest
from app.services.agent.stream_session.stream_session_types import AgentStreamSession


def _build_request_with_terminal_context() -> AgentRequest:
    return AgentRequest(
        message_id="msg-1",
        chat_id="chat-1",
        turn_capability_telemetry=TurnCapabilityTelemetryRequest(
            source="direct",
            effective_skill_count=2,
            effective_mcp_count=1,
        ),
    )


def test_has_turn_capability_terminal_context_requires_structured_payload() -> None:
    with_context = _build_request_with_terminal_context()
    without_context = AgentRequest(message_id="msg-2", chat_id="chat-2")

    assert turn_capability_terminal.has_turn_capability_terminal_context(with_context)
    assert not turn_capability_terminal.has_turn_capability_terminal_context(without_context)


def test_classify_turn_capability_failure_reason_maps_core_cases() -> None:
    assert turn_capability_terminal.classify_turn_capability_failure_reason(RuntimeError("network timeout")) == "network_error"
    assert (
        turn_capability_terminal.classify_turn_capability_failure_reason(ValueError("archive restore invalid arg"))
        == "archive_restore_invalid"
    )
    assert turn_capability_terminal.classify_turn_capability_failure_reason(RuntimeError("HTTP status 503")) == "server_error"
    assert turn_capability_terminal.classify_turn_capability_failure_reason(asyncio.CancelledError()) == "abort"


@pytest.mark.asyncio
async def test_record_turn_capability_send_completed_serializes_effective_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _build_request_with_terminal_context()
    captured: dict[str, object] = {}

    async def _fake_write(**kwargs: object) -> bool:
        captured.update(kwargs)
        return True

    monkeypatch.setattr(
        turn_capability_terminal,
        "_write_turn_capability_event",
        _fake_write,
    )

    recorded = await turn_capability_terminal.record_turn_capability_send_completed(request)

    assert recorded
    assert captured == {
        "source": "direct",
        "event_type": "send_completed",
        "context_key": "chat:chat-1",
        "effective_skill_count": 2,
        "effective_mcp_count": 1,
    }


@pytest.mark.asyncio
async def test_record_turn_capability_send_failed_writes_enum_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _build_request_with_terminal_context()
    captured: dict[str, object] = {}

    async def _fake_write(**kwargs: object) -> bool:
        captured.update(kwargs)
        return True

    monkeypatch.setattr(
        turn_capability_terminal,
        "_write_turn_capability_event",
        _fake_write,
    )

    recorded = await turn_capability_terminal.record_turn_capability_send_failed(
        request,
        "unknown_error",
    )

    assert recorded
    assert captured == {
        "source": "direct",
        "event_type": "send_failed",
        "context_key": "chat:chat-1",
        "failure_reason": "unknown_error",
    }


def _session_for(request: AgentRequest, *, recorded: bool = False) -> AgentStreamSession:
    session = cast(AgentStreamSession, MagicMock(spec=AgentStreamSession))
    session.request = request
    session.turn_capability_terminal_recorded = recorded
    return session


def _capture_event_writes(monkeypatch: pytest.MonkeyPatch, *, succeed: bool = True) -> list[dict[str, object]]:
    writes: list[dict[str, object]] = []

    async def _fake_write(**kwargs: object) -> bool:
        writes.append(kwargs)
        return succeed

    monkeypatch.setattr(turn_capability_terminal, "_write_turn_capability_event", _fake_write)
    return writes


@pytest.mark.asyncio
async def test_completed_once_records_the_turn_and_marks_the_session(monkeypatch: pytest.MonkeyPatch) -> None:
    writes = _capture_event_writes(monkeypatch)
    session = _session_for(_build_request_with_terminal_context())

    await turn_capability_terminal.record_turn_capability_completed_once(session)

    assert [write["event_type"] for write in writes] == ["send_completed"]
    assert session.turn_capability_terminal_recorded is True


@pytest.mark.asyncio
async def test_a_turn_records_its_terminal_state_only_once(monkeypatch: pytest.MonkeyPatch) -> None:
    writes = _capture_event_writes(monkeypatch)
    session = _session_for(_build_request_with_terminal_context(), recorded=True)

    await turn_capability_terminal.record_turn_capability_completed_once(session)
    await turn_capability_terminal.record_turn_capability_failed_once(session, "abort")

    assert writes == []


@pytest.mark.asyncio
async def test_once_helpers_skip_a_request_without_capability_telemetry(monkeypatch: pytest.MonkeyPatch) -> None:
    writes = _capture_event_writes(monkeypatch)
    session = _session_for(AgentRequest(message_id="msg-2", chat_id="chat-2"))

    await turn_capability_terminal.record_turn_capability_completed_once(session)
    await turn_capability_terminal.record_turn_capability_failed_once(session, "abort")

    assert writes == []
    assert session.turn_capability_terminal_recorded is False


@pytest.mark.asyncio
async def test_a_failed_write_leaves_the_session_open_for_a_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    _capture_event_writes(monkeypatch, succeed=False)
    session = _session_for(_build_request_with_terminal_context())

    await turn_capability_terminal.record_turn_capability_failed_once(session, "abort")

    assert session.turn_capability_terminal_recorded is False
