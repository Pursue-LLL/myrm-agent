"""Unit tests for NativeCredentialApprovalService.

[INPUT]
- CreateCredentialAskRequest, DecideCredentialAskRequest DTOs.

[OUTPUT]
- Verified behavior of NativeCredentialApprovalService layer.

[POS]
- Server unit test layer for QM #1502 native credential approval and session message linking.
"""

from __future__ import annotations

import pytest

from app.schemas.native_credential_approval import (
    CreateCredentialAskRequest,
    DecideCredentialAskRequest,
)
from app.services.security.native_credential_approval_service import (
    NativeCredentialApprovalService,
)


def test_service_create_and_get_ask() -> None:
    service = NativeCredentialApprovalService()
    req = CreateCredentialAskRequest(
        credential_id="cred-github",
        service_name="GitHub",
        account_label="org-admin",
        requester_id="pr-agent",
        owner_id="security-lead",
        purpose="Fetch pull request review comments",
        session_id="session-456",
        message_id="msg-101",
        sequence_number=12,
    )
    ask_dto = service.create_ask(req)

    assert ask_dto.ask_id.startswith("ask-")
    assert ask_dto.status == "pending"
    assert ask_dto.owner_id == "security-lead"
    assert ask_dto.message_ref.session_id == "session-456"
    assert ask_dto.message_ref.sequence_number == 12
    assert ask_dto.deep_link.deep_link_url == "/chat/session-456?seq=12&msg=msg-101"

    retrieved = service.get_ask(ask_dto.ask_id)
    assert retrieved is not None
    assert retrieved.ask_id == ask_dto.ask_id


def test_service_decide_ask_modes_and_audits() -> None:
    service = NativeCredentialApprovalService()
    req = CreateCredentialAskRequest(
        credential_id="cred-aws-s3",
        service_name="AWS",
        account_label="backup-bucket",
        requester_id="backup-agent",
        owner_id="ops-admin",
        purpose="Download snapshot file",
        session_id="sess-backup",
        message_id="msg-01",
        sequence_number=5,
    )
    ask_dto = service.create_ask(req)

    decide_req = DecideCredentialAskRequest(
        decider_id="ops-admin",
        decision="once",
        note="Approved for single backup download turn",
    )
    response = service.decide_ask(ask_dto.ask_id, decide_req)

    assert response.ask.status == "approved"
    assert response.ask.decision_mode == "once"
    assert response.ask.decided_by == "ops-admin"
    assert response.audit_record.actor_id == "ops-admin"
    assert response.audit_record.decision == "once"
    assert response.audit_record.sequence_number == 5

    audits = service.list_audit_records()
    assert len(audits) == 1
    assert audits[0].ask_id == ask_dto.ask_id


def test_service_unauthorized_decider_rejected() -> None:
    service = NativeCredentialApprovalService()
    req = CreateCredentialAskRequest(
        credential_id="cred-slack-token",
        service_name="Slack",
        account_label="bot-user",
        requester_id="notify-agent",
        owner_id="comms-admin",
        purpose="Post status update",
        session_id="sess-chat",
        message_id="msg-09",
        sequence_number=1,
    )
    ask_dto = service.create_ask(req)

    decide_req = DecideCredentialAskRequest(
        decider_id="unauthorized-intruder",
        decision="standing",
    )

    with pytest.raises(PermissionError, match="Only the credential owner can decide"):
        service.decide_ask(ask_dto.ask_id, decide_req)


def test_service_list_pending_asks() -> None:
    service = NativeCredentialApprovalService()
    req1 = CreateCredentialAskRequest(
        credential_id="c1",
        service_name="S1",
        account_label="A1",
        requester_id="r1",
        owner_id="user-a",
        purpose="p1",
        session_id="sess-1",
        message_id="m1",
        sequence_number=1,
    )
    req2 = CreateCredentialAskRequest(
        credential_id="c2",
        service_name="S2",
        account_label="A2",
        requester_id="r2",
        owner_id="user-b",
        purpose="p2",
        session_id="sess-2",
        message_id="m2",
        sequence_number=2,
    )
    service.create_ask(req1)
    service.create_ask(req2)

    all_pending = service.list_pending_asks()
    assert all_pending.total_count == 2

    user_a_pending = service.list_pending_asks(owner_id="user-a")
    assert user_a_pending.total_count == 1
    assert user_a_pending.pending_asks[0].owner_id == "user-a"
