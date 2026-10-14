"""[INPUT]
httpx, ASGITransport, app.api.approvals.bidirectional_router::router
[OUTPUT]
Pytest integration tests verifying bidirectional approval protocol, diff generation, and client decision ACK.
[POS]
tests/api/approvals/test_bidirectional_approval_api.py
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.approvals.bidirectional_router import router as bidirectional_router

test_app = FastAPI()
test_app.include_router(bidirectional_router, prefix="/api/v1/approvals")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_create_file_diff_approval(async_client: httpx.AsyncClient) -> None:
    payload = {
        "session_id": "test-session-diff",
        "file_path": "src/utils.py",
        "old_content": "def add(a, b):\n    return a + b\n",
        "new_content": "def add(a, b):\n    # add validation\n    return a + b\n",
        "summary": "Add comment to utils.py",
    }

    response = await async_client.post(
        "/api/v1/approvals/bidirectional/file-diff-request", json=payload
    )
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "test-session-diff"
    assert data["kind"] == "file_write"
    assert data["sequence_id"] >= 1
    assert data["file_diff"] is not None
    assert data["file_diff"]["added_lines"] == 1
    assert data["file_diff"]["removed_lines"] == 0
    assert "+    # add validation" in data["file_diff"]["unified_diff"]
    assert "allow" in data["allowed_decisions"]


@pytest.mark.asyncio
async def test_create_command_risk_approval(async_client: httpx.AsyncClient) -> None:
    # Critical risk command test
    critical_payload = {
        "session_id": "test-session-cmd",
        "command": "rm -rf / --no-preserve-root",
        "cwd": "/workspace",
        "summary": "Destructive deletion",
    }
    resp = await async_client.post(
        "/api/v1/approvals/bidirectional/command-request", json=critical_payload
    )
    assert resp.status_code == 200
    critical_data = resp.json()
    assert critical_data["kind"] == "command_exec"
    assert critical_data["command_risk"]["risk_severity"] == "critical"
    assert len(critical_data["command_risk"]["risk_reasons"]) > 0

    # Low risk command test
    safe_payload = {
        "session_id": "test-session-cmd",
        "command": "echo 'build success'",
        "cwd": "/workspace",
    }
    safe_resp = await async_client.post(
        "/api/v1/approvals/bidirectional/command-request", json=safe_payload
    )
    assert safe_resp.status_code == 200
    safe_data = safe_resp.json()
    assert safe_data["command_risk"]["risk_severity"] == "low"


@pytest.mark.asyncio
async def test_decision_ack_and_pending_lifecycle(async_client: httpx.AsyncClient) -> None:
    # 1. Create a request
    create_payload = {
        "session_id": "session-lifecycle",
        "file_path": "docs/README.md",
        "old_content": "# Intro\n",
        "new_content": "# Intro\nUpdated docs.\n",
    }
    create_resp = await async_client.post(
        "/api/v1/approvals/bidirectional/file-diff-request", json=create_payload
    )
    assert create_resp.status_code == 200
    approval_id = create_resp.json()["approval_id"]
    seq_id = create_resp.json()["sequence_id"]

    # 2. Check in pending list
    pending_resp = await async_client.get(
        "/api/v1/approvals/bidirectional/pending",
        params={"session_id": "session-lifecycle"},
    )
    assert pending_resp.status_code == 200
    pending_list = pending_resp.json()
    assert any(item["approval_id"] == approval_id for item in pending_list)

    # 3. Submit decision
    decision_payload = {
        "approval_id": approval_id,
        "decision": "allow",
        "decided_by": "lead-architect",
        "client_type": "desktop",
        "reason": "Verified code changes safe",
        "decided_at": 1760000000.0,
    }
    decision_resp = await async_client.post(
        "/api/v1/approvals/bidirectional/decide", json=decision_payload
    )
    assert decision_resp.status_code == 200
    ack = decision_resp.json()
    assert ack["approval_id"] == approval_id
    assert ack["sequence_id"] == seq_id
    assert ack["acknowledged"] is True
    assert ack["status"] == "resolved_allow"

    # 4. Check removed from pending list
    pending_resp2 = await async_client.get(
        "/api/v1/approvals/bidirectional/pending",
        params={"session_id": "session-lifecycle"},
    )
    assert pending_resp2.status_code == 200
    assert not any(item["approval_id"] == approval_id for item in pending_resp2.json())

    # 5. Duplicate decision returns acknowledged=False
    dup_resp = await async_client.post(
        "/api/v1/approvals/bidirectional/decide", json=decision_payload
    )
    assert dup_resp.status_code == 200
    dup_ack = dup_resp.json()
    assert dup_ack["acknowledged"] is False
