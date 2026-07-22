"""Unit tests for Web clarification timeout scheduling and sse_helpers HITL paths."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler

from app.services.agent.streaming_support.sse_helpers import (
    CLARIFICATION_NO_ANSWER_RESUME_VALUE,
    CLARIFICATION_TIMEOUT_SECONDS,
    error_sse,
    extract_approval_intercepted,
    extract_approval_timeout,
    extract_clarification_required,
    schedule_approval_timeout,
    schedule_clarification_timeout,
)


@pytest.fixture(autouse=True)
def _reset_scheduler() -> None:
    ApprovalTimeoutScheduler._instance = None


def test_extract_clarification_required_true() -> None:
    event = {
        "type": "clarification_required",
        "data": {"type": "ask_question", "form": {"questions": []}},
    }
    chunk = f"data: {json.dumps(event)}\n\n"
    assert extract_clarification_required(chunk) is True


def test_extract_clarification_required_false_for_other_events() -> None:
    chunk = 'data: {"type":"message","data":"hello"}\n\n'
    assert extract_clarification_required(chunk) is False


def test_extract_clarification_required_false_for_malformed_json() -> None:
    assert extract_clarification_required("data: {broken}\n\n") is False


def test_extract_clarification_required_false_without_sse_prefix() -> None:
    assert extract_clarification_required('{"type":"clarification_required"}\n\n') is False


def test_error_sse_includes_message_id_when_provided() -> None:
    chunk = error_sse("boom", "msg-42")
    assert "msg-42" in chunk
    assert "boom" in chunk


def test_error_sse_generates_message_id_when_missing() -> None:
    chunk = error_sse("boom", None)
    assert "messageId" in chunk
    assert "boom" in chunk


def test_extract_approval_intercepted_parses_event() -> None:
    event = {
        "type": "approval_intercepted",
        "data": {"decision": "approve"},
    }
    chunk = f"data: {json.dumps(event)}\n\n"
    parsed = extract_approval_intercepted(chunk)
    assert parsed is not None
    assert parsed.decision == "approve"


def test_extract_approval_intercepted_returns_none_for_invalid_payload() -> None:
    assert extract_approval_intercepted("not sse") is None


def test_extract_approval_intercepted_returns_none_for_wrong_event_type() -> None:
    chunk = 'data: {"type":"message","data":{"decision":"approve"}}\n\n'
    assert extract_approval_intercepted(chunk) is None


def test_extract_approval_intercepted_returns_none_for_non_dict_data() -> None:
    chunk = 'data: {"type":"approval_intercepted","data":"bad"}\n\n'
    assert extract_approval_intercepted(chunk) is None


def test_extract_approval_intercepted_returns_none_for_malformed_json() -> None:
    assert extract_approval_intercepted("data: approval_intercepted {broken}\n\n") is None


def test_extract_approval_timeout_returns_none_for_wrong_event_type() -> None:
    chunk = 'data: {"type":"message","data":{}}\n\n'
    assert extract_approval_timeout(chunk) is None


def test_extract_approval_timeout_returns_none_for_non_dict_data() -> None:
    chunk = 'data: {"type":"tool_approval_request","data":"bad"}\n\n'
    assert extract_approval_timeout(chunk) is None


def test_extract_approval_timeout_returns_none_for_non_dict_extensions() -> None:
    chunk = 'data: {"type":"tool_approval_request","data":{"extensions":"bad"}}\n\n'
    assert extract_approval_timeout(chunk) is None


def test_extract_approval_timeout_returns_none_for_non_dict_timeout() -> None:
    chunk = 'data: {"type":"tool_approval_request","data":{"extensions":{"timeout":"bad"}}}\n\n'
    assert extract_approval_timeout(chunk) is None


def test_extract_approval_timeout_returns_none_for_malformed_json() -> None:
    assert extract_approval_timeout("data: tool_approval_request {broken}\n\n") is None


def test_extract_clarification_required_false_for_wrong_event_type() -> None:
    chunk = 'data: {"type":"message","clarification_required":true}\n\n'
    assert extract_clarification_required(chunk) is False


def test_extract_approval_timeout_parses_extensions() -> None:
    event = {
        "type": "tool_approval_request",
        "data": {
            "extensions": {"timeout": {"seconds": 120, "behavior": "allow"}},
        },
    }
    chunk = f"data: {json.dumps(event)}\n\n"
    parsed = extract_approval_timeout(chunk)
    assert parsed == {"seconds": 120, "behavior": "allow"}


def test_extract_approval_timeout_defaults_when_missing() -> None:
    event = {"type": "tool_approval_request", "data": {}}
    chunk = f"data: {json.dumps(event)}\n\n"
    parsed = extract_approval_timeout(chunk)
    assert parsed == {"seconds": 300, "behavior": "deny"}


def test_extract_approval_timeout_returns_none_for_invalid_payload() -> None:
    assert extract_approval_timeout("not sse") is None


@pytest.mark.asyncio
async def test_schedule_clarification_timeout_registers_empty_resume_override() -> None:
    captured: dict[str, object] = {}

    def fake_schedule(
        key: str,
        timeout_seconds: float,
        behavior: str,
        resume_callback: object,
        *,
        resume_value_override: dict[str, object] | None = None,
    ) -> None:
        captured["key"] = key
        captured["timeout_seconds"] = timeout_seconds
        captured["override"] = resume_value_override
        captured["callback"] = resume_callback

    with patch.object(ApprovalTimeoutScheduler.get(), "schedule", side_effect=fake_schedule):
        schedule_clarification_timeout("chat-1", MagicMock(), timeout_seconds=12.0)

    assert captured["key"] == "chat-1"
    assert captured["timeout_seconds"] == 12.0
    assert captured["override"] == CLARIFICATION_NO_ANSWER_RESUME_VALUE
    assert callable(captured["callback"])


async def _invoke_captured_callback(captured: dict[str, object]) -> None:
    callback = captured["callback"]
    assert callable(callback)
    await callback({})  # type: ignore[misc]


@pytest.mark.asyncio
async def test_clarification_resume_callback_persists_and_logs_completion() -> None:
    captured: dict[str, object] = {}
    params = MagicMock()
    params.model_copy.return_value = params

    async def fake_stream(*_args: object, **_kwargs: object) -> AsyncIterator[dict[str, object]]:
        yield {"type": "message", "data": "continued"}

    def fake_schedule(
        key: str,
        timeout_seconds: float,
        behavior: str,
        resume_callback: object,
        *,
        resume_value_override: dict[str, object] | None = None,
    ) -> None:
        captured["callback"] = resume_callback
        captured["override"] = resume_value_override

    collector = MagicMock()
    collector.has_content = True
    collector.content = "continued"
    collector.extra_data = {"k": "v"}
    collector.feed_sse = MagicMock()

    with (
        patch.object(ApprovalTimeoutScheduler.get(), "schedule", side_effect=fake_schedule),
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            side_effect=fake_stream,
        ),
        patch(
            "app.services.agent.streaming_support.sse_helpers.StreamContentCollector",
            return_value=collector,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            new_callable=AsyncMock,
        ) as mock_persist,
    ):
        schedule_clarification_timeout("chat-2", params)
        await _invoke_captured_callback(captured)

    mock_persist.assert_awaited_once_with("chat-2", "continued", extra_data={"k": "v"})


@pytest.mark.asyncio
async def test_clarification_resume_callback_reschedules_nested_clarify() -> None:
    captured: dict[str, object] = {}
    params = MagicMock()
    params.model_copy.return_value = params
    clarify_event = {
        "type": "clarification_required",
        "data": {"type": "ask_question", "form": {"questions": []}},
    }

    async def fake_stream(*_args: object, **_kwargs: object) -> AsyncIterator[dict[str, object]]:
        yield clarify_event

    def fake_schedule(
        key: str,
        timeout_seconds: float,
        behavior: str,
        resume_callback: object,
        *,
        resume_value_override: dict[str, object] | None = None,
    ) -> None:
        captured["callback"] = resume_callback

    collector = MagicMock()
    collector.has_content = False
    collector.feed_sse = MagicMock()

    with (
        patch.object(ApprovalTimeoutScheduler.get(), "schedule", side_effect=fake_schedule),
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            side_effect=fake_stream,
        ),
        patch(
            "app.services.agent.streaming_support.sse_helpers.StreamContentCollector",
            return_value=collector,
        ),
        patch(
            "app.services.agent.streaming_support.sse_helpers.schedule_clarification_timeout"
        ) as mock_reschedule,
    ):
        schedule_clarification_timeout("chat-3", params, timeout_seconds=99.0)
        await _invoke_captured_callback(captured)

    mock_reschedule.assert_called_once_with("chat-3", params, timeout_seconds=99.0)


@pytest.mark.asyncio
async def test_clarification_resume_callback_schedules_nested_approval() -> None:
    captured: dict[str, object] = {}
    params = MagicMock()
    params.model_copy.return_value = params
    approval_event = {
        "type": "tool_approval_request",
        "data": {"extensions": {"timeout": {"seconds": 60, "behavior": "deny"}}},
    }

    async def fake_stream(*_args: object, **_kwargs: object) -> AsyncIterator[dict[str, object]]:
        yield approval_event

    def fake_schedule(
        key: str,
        timeout_seconds: float,
        behavior: str,
        resume_callback: object,
        *,
        resume_value_override: dict[str, object] | None = None,
    ) -> None:
        captured["callback"] = resume_callback

    collector = MagicMock()
    collector.has_content = False
    collector.feed_sse = MagicMock()

    with (
        patch.object(ApprovalTimeoutScheduler.get(), "schedule", side_effect=fake_schedule),
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            side_effect=fake_stream,
        ),
        patch(
            "app.services.agent.streaming_support.sse_helpers.StreamContentCollector",
            return_value=collector,
        ),
        patch(
            "app.services.agent.streaming_support.sse_helpers.schedule_approval_timeout"
        ) as mock_approval_schedule,
    ):
        schedule_clarification_timeout("chat-4", params)
        await _invoke_captured_callback(captured)

    mock_approval_schedule.assert_called_once()
    assert mock_approval_schedule.call_args.args[0] == "chat-4"


@pytest.mark.asyncio
async def test_schedule_approval_timeout_registers_callback() -> None:
    captured: dict[str, object] = {}
    params = MagicMock()
    params.model_copy.return_value = params

    def fake_schedule(
        key: str,
        timeout_seconds: float,
        behavior: str,
        resume_callback: object,
        *,
        resume_value_override: dict[str, object] | None = None,
    ) -> None:
        captured["key"] = key
        captured["timeout_seconds"] = timeout_seconds
        captured["behavior"] = behavior
        captured["callback"] = resume_callback
        captured["override"] = resume_value_override

    with patch.object(ApprovalTimeoutScheduler.get(), "schedule", side_effect=fake_schedule):
        schedule_approval_timeout(
            "chat-5",
            {"seconds": "45", "behavior": "allow"},
            params,
        )

    assert captured["key"] == "chat-5"
    assert captured["timeout_seconds"] == 45.0
    assert captured["behavior"] == "allow"
    assert captured["override"] is None
    assert callable(captured["callback"])


@pytest.mark.asyncio
async def test_approval_resume_callback_persists_and_reschedules() -> None:
    captured: dict[str, object] = {}
    params = MagicMock()
    params.model_copy.return_value = params
    approval_event = {
        "type": "tool_approval_request",
        "data": {"extensions": {"timeout": {"seconds": 30, "behavior": "deny"}}},
    }

    async def fake_stream(*_args: object, **_kwargs: object) -> AsyncIterator[dict[str, object]]:
        yield approval_event

    def fake_schedule(
        key: str,
        timeout_seconds: float,
        behavior: str,
        resume_callback: object,
        *,
        resume_value_override: dict[str, object] | None = None,
    ) -> None:
        captured["callback"] = resume_callback

    collector = MagicMock()
    collector.has_content = True
    collector.content = "approved flow"
    collector.extra_data = None
    collector.feed_sse = MagicMock()

    with (
        patch.object(ApprovalTimeoutScheduler.get(), "schedule", side_effect=fake_schedule),
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            side_effect=fake_stream,
        ),
        patch(
            "app.services.agent.streaming_support.sse_helpers.StreamContentCollector",
            return_value=collector,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            new_callable=AsyncMock,
        ) as mock_persist,
        patch(
            "app.services.agent.streaming_support.sse_helpers.schedule_approval_timeout"
        ) as mock_reschedule,
    ):
        schedule_approval_timeout("chat-6", {"seconds": 30, "behavior": "deny"}, params)
        await _invoke_captured_callback(captured)

    mock_persist.assert_awaited_once()
    mock_reschedule.assert_called_once()


@pytest.mark.asyncio
async def test_approval_resume_callback_logs_completion_without_nested_timeout() -> None:
    captured: dict[str, object] = {}
    params = MagicMock()
    params.model_copy.return_value = params

    async def fake_stream(*_args: object, **_kwargs: object) -> AsyncIterator[dict[str, object]]:
        yield {"type": "message", "data": "done"}
        return
        yield  # pragma: no cover

    def fake_schedule(
        key: str,
        timeout_seconds: float,
        behavior: str,
        resume_callback: object,
        *,
        resume_value_override: dict[str, object] | None = None,
    ) -> None:
        captured["callback"] = resume_callback

    collector = MagicMock()
    collector.has_content = False
    collector.feed_sse = MagicMock()

    with (
        patch.object(ApprovalTimeoutScheduler.get(), "schedule", side_effect=fake_schedule),
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            side_effect=fake_stream,
        ),
        patch(
            "app.services.agent.streaming_support.sse_helpers.StreamContentCollector",
            return_value=collector,
        ),
        patch(
            "app.services.agent.streaming_support.sse_helpers.schedule_approval_timeout"
        ) as mock_reschedule,
    ):
        schedule_approval_timeout("chat-7", {"seconds": 30, "behavior": "deny"}, params)
        await _invoke_captured_callback(captured)

    mock_reschedule.assert_not_called()


def test_schedule_approval_timeout_falls_back_for_invalid_seconds_type() -> None:
    captured: dict[str, object] = {}

    def fake_schedule(
        key: str,
        timeout_seconds: float,
        behavior: str,
        resume_callback: object,
        *,
        resume_value_override: dict[str, object] | None = None,
    ) -> None:
        captured["timeout_seconds"] = timeout_seconds

    with patch.object(ApprovalTimeoutScheduler.get(), "schedule", side_effect=fake_schedule):
        schedule_approval_timeout("chat-8", {"seconds": object(), "behavior": "deny"}, MagicMock())

    assert captured["timeout_seconds"] == 300.0


def test_clarification_timeout_default_is_900_seconds() -> None:
    assert CLARIFICATION_TIMEOUT_SECONDS == 900.0
