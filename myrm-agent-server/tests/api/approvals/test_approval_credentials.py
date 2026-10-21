"""Unit tests for staging ephemeral credentials in tool approval subsystem."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.api import get_ephemeral_credential_store

from app.services.approvals.registry import ApprovalRegistry


@pytest.mark.asyncio
async def test_stage_credentials_not_found(client) -> None:
    resp = client.post(
        "/api/v1/approvals/non_existent_approval_id/credentials",
        json={"credentials": [{"key": "DB_PASS", "secret": "abc"}]},
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_stage_credentials_blocked_key(client) -> None:
    record = await ApprovalRegistry.create_approval(
        agent_id="agent-cred-test",
        action_type="tool_approval",
        payload={"action": "run_shell"},
        chat_id="chat-cred-1",
        thread_id="thread-cred-1",
    )

    resp = client.post(
        f"/api/v1/approvals/{record.id}/credentials",
        json={"credentials": [{"key": "LD_PRELOAD", "secret": "/evil.so"}]},
    )
    assert resp.status_code == 400
    assert "blocked" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_stage_credentials_success_and_resolve(client) -> None:
    record = await ApprovalRegistry.create_approval(
        agent_id="agent-cred-test",
        action_type="tool_approval",
        payload={"action": "run_shell"},
        chat_id="chat-cred-2",
        thread_id="thread-cred-2",
    )

    resp = client.post(
        f"/api/v1/approvals/{record.id}/credentials",
        json={
            "credentials": [
                {
                    "key": "MYSQL_ROOT_PASSWORD",
                    "secret": "ProductionSuperSecret999!",
                    "ttl_seconds": 45.0,
                    "single_use": True,
                }
            ]
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["approval_id"] == record.id
    assert data["session_id"] == "chat-cred-2"
    assert len(data["staged"]) == 1
    handle = data["staged"][0]["handle_id"]
    assert handle.startswith("cred_ephemeral_")
    assert data["staged"][0]["key"] == "MYSQL_ROOT_PASSWORD"

    # Verify secret is stored in-memory in EphemeralCredentialStore
    store = get_ephemeral_credential_store()
    summary = store.peek_summary("chat-cred-2", handle)
    assert summary is not None
    assert summary.key == "MYSQL_ROOT_PASSWORD"
    assert not summary.is_consumed

    # Now resolve the approval passing the handle
    bus = MagicMock()
    with patch("app.services.event.app_event_bus.get_event_bus", return_value=bus):
        resolve_resp = client.post(
            f"/api/v1/approvals/{record.id}/resolve",
            json={
                "decision": "approve",
                "ephemeral_credential_handles": [handle],
            },
        )
        assert resolve_resp.status_code == 200

    # Verify bus published event contains the handle
    bus.publish.assert_called_once()
    event = bus.publish.call_args.args[0]
    assert event.data["ephemeral_credential_handles"] == [handle]


@pytest.mark.asyncio
async def test_deny_approval_wipes_ephemeral_credentials(client) -> None:
    record = await ApprovalRegistry.create_approval(
        agent_id="agent-deny-test",
        action_type="shell_execution",
        reason="Run database query",
        severity="high",
        payload={"command": "psql -h localhost"},
        chat_id="session_deny_test",
        thread_id="thread_deny_test",
    )

    stage_resp = client.post(
        f"/api/v1/approvals/{record.id}/credentials",
        json={
            "credentials": [
                {
                    "key": "PGPASSWORD",
                    "secret": "my_pass_123",
                    "ttl_seconds": 60.0,
                    "single_use": True,
                }
            ]
        },
    )
    assert stage_resp.status_code == 201
    handle = stage_resp.json()["staged"][0]["handle_id"]

    store = get_ephemeral_credential_store()
    assert len(store.list_summaries("session_deny_test")) == 1

    # Deny the approval passing the handle
    resolve_resp = client.post(
        f"/api/v1/approvals/{record.id}/resolve",
        json={
            "decision": "deny",
            "ephemeral_credential_handles": [handle],
        },
    )
    assert resolve_resp.status_code == 200

    # Credential must be immediately wiped from store
    assert store.list_summaries("session_deny_test") == []

