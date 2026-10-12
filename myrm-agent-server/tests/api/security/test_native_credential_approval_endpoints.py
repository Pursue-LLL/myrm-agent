"""Integration tests for Native Credential Approvals API endpoints.

[INPUT]
- HTTP requests to /api/v1/security/native-credential-approvals/* endpoints.

[OUTPUT]
- Verified JSON responses matching CredentialAsk and audit schemas (QM #1502).

[POS]
- Server integration test layer for native credential approvals and contextual message linking.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.native_credential_approval_router import (
    router as native_credential_approval_router,
)
from app.services.security.native_credential_approval_service import (
    NativeCredentialApprovalService,
    get_native_credential_approval_service,
)


@pytest.fixture(scope="function")
def isolated_service() -> NativeCredentialApprovalService:
    """Fixture providing isolated in-memory service instance."""
    return NativeCredentialApprovalService()


@pytest.fixture(scope="function")
def client(isolated_service: NativeCredentialApprovalService) -> TestClient:
    """Fixture providing test client mounting native_credential_approval_router."""
    test_app = FastAPI(title="Native Credential Approval Test App")
    test_app.dependency_overrides[get_native_credential_approval_service] = (
        lambda: isolated_service
    )
    test_app.include_router(
        native_credential_approval_router, prefix="/api/v1/security"
    )
    return TestClient(test_app, raise_server_exceptions=False)


def test_create_and_get_ask_endpoint(client: TestClient) -> None:
    payload = {
        "credential_id": "cred-gitlab-pat",
        "service_name": "GitLab",
        "account_label": "enterprise-deployer",
        "requester_id": "ci-agent",
        "owner_id": "devops-engineer-01",
        "purpose": "Trigger deployment pipeline",
        "session_id": "sess-ci-101",
        "message_id": "msg-step-5",
        "sequence_number": 9,
    }
    resp = client.post(
        "/api/v1/security/native-credential-approvals/asks",
        json=payload,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["ask_id"].startswith("ask-")
    assert data["status"] == "pending"
    assert data["deep_link"]["deep_link_url"] == "/chat/sess-ci-101?seq=9&msg=msg-step-5"

    ask_id = data["ask_id"]
    get_resp = client.get(f"/api/v1/security/native-credential-approvals/asks/{ask_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["ask_id"] == ask_id

    missing_resp = client.get(
        "/api/v1/security/native-credential-approvals/asks/nonexistent-ask-id"
    )
    assert missing_resp.status_code == 404


def test_decide_ask_endpoint_success_and_audits(client: TestClient) -> None:
    create_payload = {
        "credential_id": "cred-db-master",
        "service_name": "Postgres",
        "account_label": "master-write",
        "requester_id": "migration-agent",
        "owner_id": "dba-lead",
        "purpose": "Apply database schema patch",
        "session_id": "sess-db-patch",
        "message_id": "msg-apply-1",
        "sequence_number": 3,
    }
    create_resp = client.post(
        "/api/v1/security/native-credential-approvals/asks",
        json=create_payload,
    )
    assert create_resp.status_code == 201
    ask_id = create_resp.json()["ask_id"]

    decide_payload = {
        "decider_id": "dba-lead",
        "decision": "standing",
        "note": "Granted for migration session",
    }
    decide_resp = client.post(
        f"/api/v1/security/native-credential-approvals/asks/{ask_id}/decide",
        json=decide_payload,
    )
    assert decide_resp.status_code == 200
    decide_data = decide_resp.json()
    assert decide_data["ask"]["status"] == "approved"
    assert decide_data["ask"]["decision_mode"] == "standing"
    assert decide_data["audit_record"]["actor_id"] == "dba-lead"

    audits_resp = client.get(
        "/api/v1/security/native-credential-approvals/audits"
    )
    assert audits_resp.status_code == 200
    audits_data = audits_resp.json()
    assert len(audits_data) == 1
    assert audits_data[0]["ask_id"] == ask_id


def test_decide_ask_endpoint_unauthorized(client: TestClient) -> None:
    create_payload = {
        "credential_id": "cred-prod-key",
        "service_name": "OpenAI",
        "account_label": "prod-tier-5",
        "requester_id": "chat-agent",
        "owner_id": "secops-director",
        "purpose": "Query GPT-4o",
        "session_id": "sess-gpt",
        "message_id": "msg-prompt",
        "sequence_number": 1,
    }
    create_resp = client.post(
        "/api/v1/security/native-credential-approvals/asks",
        json=create_payload,
    )
    assert create_resp.status_code == 201
    ask_id = create_resp.json()["ask_id"]

    decide_payload = {
        "decider_id": "malicious-actor",
        "decision": "once",
        "note": "Unauthorized approval attempt",
    }
    decide_resp = client.post(
        f"/api/v1/security/native-credential-approvals/asks/{ask_id}/decide",
        json=decide_payload,
    )
    assert decide_resp.status_code == 403
    assert "Only the credential owner can decide" in decide_resp.json()["detail"]


def test_list_pending_asks_endpoint(client: TestClient) -> None:
    for i in range(2):
        client.post(
            "/api/v1/security/native-credential-approvals/asks",
            json={
                "credential_id": f"cred-{i}",
                "service_name": "Service",
                "account_label": f"acc-{i}",
                "requester_id": f"agent-{i}",
                "owner_id": f"owner-{i}",
                "purpose": f"purpose-{i}",
                "session_id": f"sess-{i}",
                "message_id": f"msg-{i}",
                "sequence_number": i,
            },
        )

    resp_all = client.get(
        "/api/v1/security/native-credential-approvals/asks/pending"
    )
    assert resp_all.status_code == 200
    assert resp_all.json()["total_count"] == 2

    resp_filtered = client.get(
        "/api/v1/security/native-credential-approvals/asks/pending?owner_id=owner-0"
    )
    assert resp_filtered.status_code == 200
    assert resp_filtered.json()["total_count"] == 1
    assert resp_filtered.json()["pending_asks"][0]["owner_id"] == "owner-0"
