"""Unit tests for Web ask_question 900s clarification timeout scheduling (B-package)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler
from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

from app.ai_agents import GeneralAgentParams
from app.core.types import ModelConfig
from app.services.agent.streaming_support.sse_helpers import (
    CLARIFICATION_NO_ANSWER_RESUME_VALUE,
    CLARIFICATION_TIMEOUT_SECONDS,
    extract_clarification_required,
    schedule_clarification_timeout,
)


@pytest.fixture(autouse=True)
def _reset_scheduler_singleton() -> None:
    ApprovalTimeoutScheduler._instance = None


def _minimal_params(chat_id: str = "chat-clarify-scheduler") -> GeneralAgentParams:
    return GeneralAgentParams(
        query="hello",
        model_cfg=ModelConfig(
            provider="openai",
            model="gpt-4o-mini",
            api_key="test-key",
        ),
        search_service_cfg=SearchServiceConfig(search_service="tavily"),
        chat_id=chat_id,
        message_id="msg-clarify-scheduler",
    )


def test_schedule_clarification_timeout_registers_900s_empty_dict_override() -> None:
    params = _minimal_params()
    mock_scheduler = MagicMock()
    with patch(
        "app.services.agent.streaming_support.sse_helpers.ApprovalTimeoutScheduler.get",
        return_value=mock_scheduler,
    ):
        schedule_clarification_timeout("chat-clarify-scheduler", params)

    mock_scheduler.schedule.assert_called_once()
    kwargs = mock_scheduler.schedule.call_args.kwargs
    assert kwargs["key"] == "chat-clarify-scheduler"
    assert kwargs["timeout_seconds"] == CLARIFICATION_TIMEOUT_SECONDS
    assert kwargs["timeout_seconds"] == 900.0
    assert kwargs["behavior"] == "deny"
    assert kwargs["resume_value_override"] == CLARIFICATION_NO_ANSWER_RESUME_VALUE
    assert kwargs["resume_value_override"] == {}
    assert callable(kwargs["resume_callback"])


def test_schedule_clarification_timeout_accepts_custom_timeout() -> None:
    params = _minimal_params()
    mock_scheduler = MagicMock()
    with patch(
        "app.services.agent.streaming_support.sse_helpers.ApprovalTimeoutScheduler.get",
        return_value=mock_scheduler,
    ):
        schedule_clarification_timeout("chat-clarify-scheduler", params, timeout_seconds=42.0)

    assert mock_scheduler.schedule.call_args.kwargs["timeout_seconds"] == 42.0


def test_extract_clarification_required_detects_sse_event() -> None:
    chunk = 'data: {"type":"clarification_required","data":{"form":{}}}\n\n'
    assert extract_clarification_required(chunk) is True


def test_extract_clarification_required_rejects_unrelated_events() -> None:
    chunk = 'data: {"type":"message","data":""}\n\n'
    assert extract_clarification_required(chunk) is False
