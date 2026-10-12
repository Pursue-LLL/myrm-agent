"""Unit tests for HitlDenialEventsService in myrm-agent-server."""

from __future__ import annotations

import pytest

from app.schemas.hitl_denial_events import (
    ConfirmResultDto,
    ProcessHitlDecisionsRequest,
    ToolUseBlockDto,
)
from app.services.security.hitl_denial_events_service import HitlDenialEventsService


@pytest.fixture
def service() -> HitlDenialEventsService:
    return HitlDenialEventsService()


def test_service_process_decisions_custom_reason(
    service: HitlDenialEventsService,
) -> None:
    request = ProcessHitlDecisionsRequest(
        session_id="test_sess_01",
        step_id="step_1",
        tool_calls=[
            ToolUseBlockDto(
                id="call_1",
                name="disk_format",
                arguments={"target": "/dev/sda"},
            ),
            ToolUseBlockDto(
                id="call_2",
                name="read_file",
                arguments={"path": "/app/config.json"},
            ),
        ],
        decisions=[
            ConfirmResultDto(
                tool_call_id="call_1",
                tool_name="disk_format",
                confirmed=False,
                reason="Destructive disk formatting is forbidden.",
            ),
            ConfirmResultDto(
                tool_call_id="call_2",
                tool_name="read_file",
                confirmed=True,
            ),
        ],
    )

    response = service.process_decisions(request)

    assert response.session_id == "test_sess_01"
    assert response.total_calls == 2
    assert response.confirmed_count == 1
    assert response.denied_count == 1
    assert response.all_denied is False
    assert response.can_resume is True
    assert response.all_tools_denied_event is None

    assert len(response.tool_result_events) == 2
    assert response.tool_result_events[0].state == "DENIED"
    assert (
        response.tool_result_events[0].output_text
        == "Destructive disk formatting is forbidden."
    )
    assert response.tool_result_events[1].state == "ALLOWED"


def test_service_all_denied_halt(service: HitlDenialEventsService) -> None:
    request = ProcessHitlDecisionsRequest(
        session_id="test_sess_02",
        step_id="step_2",
        tool_calls=[
            ToolUseBlockDto(
                id="call_1",
                name="delete_table",
                arguments={"table": "users"},
            ),
        ],
        decisions=[
            ConfirmResultDto(
                tool_call_id="call_1",
                tool_name="delete_table",
                confirmed=False,
                reason="User data cannot be dropped.",
            ),
        ],
        policy="HALT",
    )

    response = service.process_decisions(request)

    assert response.all_denied is True
    assert response.can_resume is False
    assert response.terminal_reason == "ALL_TOOLS_DENIED"
    assert response.all_tools_denied_event is not None
    assert response.all_tools_denied_event.should_stop is True
    assert response.all_tools_denied_event.policy_applied == "HALT"


def test_service_policies_config(service: HitlDenialEventsService) -> None:
    config = service.get_policies_config()
    assert "HALT" in config.available_policies
    assert "RESUME_WITH_FEEDBACK" in config.available_policies
    assert config.default_policy == "HALT"
    assert "bash_exec" in config.strict_halt_tools
