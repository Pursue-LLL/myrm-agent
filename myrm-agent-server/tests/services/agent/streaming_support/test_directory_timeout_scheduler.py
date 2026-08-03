"""Unit tests for request_directory 900s timeout scheduling."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler
from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

from app.ai_agents import GeneralAgentParams
from app.core.types import ModelConfig
from app.services.agent.streaming_support.sse_helpers import (
    DIRECTORY_DENY_RESUME_VALUE,
    DIRECTORY_TIMEOUT_SECONDS,
    extract_directory_request_required,
    schedule_directory_timeout,
)


@pytest.fixture(autouse=True)
def _reset_scheduler_singleton() -> None:
    ApprovalTimeoutScheduler._instance = None


def _minimal_params(chat_id: str = "chat-directory-scheduler") -> GeneralAgentParams:
    return GeneralAgentParams(
        query="hello",
        model_cfg=ModelConfig(
            provider="openai",
            model="gpt-4o-mini",
            api_key="test-key",
        ),
        search_service_cfg=SearchServiceConfig(search_service="tavily"),
        chat_id=chat_id,
        message_id="msg-directory-scheduler",
    )


def test_schedule_directory_timeout_registers_900s_deny_grant() -> None:
    params = _minimal_params()
    mock_scheduler = MagicMock()
    with patch(
        "app.services.agent.streaming_support.sse_helpers.ApprovalTimeoutScheduler.get",
        return_value=mock_scheduler,
    ):
        schedule_directory_timeout("chat-directory-scheduler", params)

    mock_scheduler.schedule.assert_called_once()
    kwargs = mock_scheduler.schedule.call_args.kwargs
    assert kwargs["key"] == "chat-directory-scheduler"
    assert kwargs["timeout_seconds"] == DIRECTORY_TIMEOUT_SECONDS
    assert kwargs["timeout_seconds"] == 900.0
    assert kwargs["behavior"] == "deny"
    assert kwargs["resume_value_override"] == DIRECTORY_DENY_RESUME_VALUE
    assert kwargs["resume_value_override"] == {"granted": False}
    assert callable(kwargs["resume_callback"])


def test_extract_directory_request_required_detects_sse_event() -> None:
    chunk = 'data: {"type":"directory_request_required","data":{"request":{}}}\n\n'
    assert extract_directory_request_required(chunk) is True


def test_extract_directory_request_required_rejects_unrelated_events() -> None:
    chunk = 'data: {"type":"message","data":""}\n\n'
    assert extract_directory_request_required(chunk) is False
