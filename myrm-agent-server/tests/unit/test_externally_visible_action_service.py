"""Unit test suite for ExternallyVisibleActionService."""

from __future__ import annotations

import pytest

from app.schemas.externally_visible_action import (
    EvaluateActionRequest,
    RecordExternalActionAuditRequest,
)
from app.services.security.externally_visible_action_service import (
    ExternallyVisibleActionService,
)


@pytest.fixture
def service() -> ExternallyVisibleActionService:
    svc = ExternallyVisibleActionService()
    svc.clear_audit_records()
    return svc


def test_evaluate_action_third_party_builtin(service: ExternallyVisibleActionService) -> None:
    req = EvaluateActionRequest(tool_name="send_teammate_message_tool")
    res = service.evaluate_action(req)
    assert res.tool_name == "send_teammate_message_tool"
    assert res.is_third_party_visible is True
    assert res.requires_mandatory_human_review is True
    assert res.hide_allow_always is True
    assert res.visibility_scope == "THIRD_PARTY_VISIBLE"
    assert "send_teammate_message_tool" in res.rationale


def test_evaluate_action_heuristic_keyword(service: ExternallyVisibleActionService) -> None:
    req = EvaluateActionRequest(tool_name="send_email_dispatch_tool")
    res = service.evaluate_action(req)
    assert res.is_third_party_visible is True
    assert res.requires_mandatory_human_review is True
    assert res.hide_allow_always is True
    assert res.visibility_scope == "THIRD_PARTY_VISIBLE"


def test_evaluate_action_user_local(service: ExternallyVisibleActionService) -> None:
    req = EvaluateActionRequest(tool_name="ask_question_tool")
    res = service.evaluate_action(req)
    assert res.is_third_party_visible is False
    assert res.requires_mandatory_human_review is False
    assert res.hide_allow_always is False
    assert res.visibility_scope == "USER_LOCAL"


def test_evaluate_action_internal_only(service: ExternallyVisibleActionService) -> None:
    req = EvaluateActionRequest(tool_name="file_read_tool")
    res = service.evaluate_action(req)
    assert res.is_third_party_visible is False
    assert res.requires_mandatory_human_review is False
    assert res.hide_allow_always is False
    assert res.visibility_scope == "INTERNAL_ONLY"


def test_evaluate_action_custom_override(service: ExternallyVisibleActionService) -> None:
    req = EvaluateActionRequest(
        tool_name="custom_connector_sync",
        custom_is_third_party_visible=True,
    )
    res = service.evaluate_action(req)
    assert res.is_third_party_visible is True
    assert res.requires_mandatory_human_review is True
    assert res.hide_allow_always is True


def test_record_audit_and_query_trail(service: ExternallyVisibleActionService) -> None:
    req1 = RecordExternalActionAuditRequest(
        action_id="act-101",
        session_id="sess-alpha",
        agent_id="agent-01",
        tool_name="send_email_notification",
        recipient_or_destination="user@example.com",
        content_preview="Release status v1.0",
        is_approved=True,
        approved_by="secops-lead",
    )
    res1 = service.record_audit(req1)
    assert res1.action_id == "act-101"
    assert res1.is_approved is True
    assert res1.approved_by == "secops-lead"
    assert res1.timestamp > 0

    req2 = RecordExternalActionAuditRequest(
        action_id="act-102",
        session_id="sess-beta",
        agent_id="agent-02",
        tool_name="webhook_dispatch",
        recipient_or_destination="https://hooks.corp/notify",
        content_preview="Deployment alert",
        is_approved=False,
    )
    res2 = service.record_audit(req2)
    assert res2.action_id == "act-102"
    assert res2.is_approved is False

    trail_alpha = service.get_audit_trail(session_id="sess-alpha")
    assert trail_alpha.total == 1
    assert trail_alpha.records[0].action_id == "act-101"

    trail_all = service.get_audit_trail()
    assert trail_all.total == 2
