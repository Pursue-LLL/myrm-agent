"""Integration and unit tests for Tiered Risk HITL Approval & Dry-Run REST endpoints.

[INPUT]
- httpx, ASGITransport
- app.api.approvals.tiered_risk::router

[OUTPUT]
- Pytest test cases verifying three-tier risk evaluation, token lifecycle, and dry-run preview.

[POS]
Test suite for Item 29 server layer.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.approvals.tiered_risk import router as tiered_risk_router

# Build minimal test app isolated from heavy global optional dependencies
test_app = FastAPI()
test_app.include_router(tiered_risk_router, prefix="/api/v1/approvals")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_evaluate_tiered_risk_read_fast_pass(async_client: httpx.AsyncClient) -> None:
    """Read operations should be classified as READ and bypass confirmation."""
    payload = {
        "tool_name": "read_file",
        "tool_input": {"path": "/workspace/README.md"},
        "session_id": "test-session-1",
    }
    resp = await async_client.post("/api/v1/approvals/tiered-risk/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "READ"
    assert data["need_confirmation"] is False
    assert data["confirmation_token"] is None
    assert data["suggested_action"] == "pass"


@pytest.mark.asyncio
async def test_evaluate_tiered_risk_write_summary(async_client: httpx.AsyncClient) -> None:
    """Standard write operations should be classified as WRITE with dry-run support."""
    payload = {
        "tool_name": "write_to_file",
        "tool_input": {"TargetFile": "/workspace/new_doc.txt", "CodeContent": "Hello world"},
    }
    resp = await async_client.post("/api/v1/approvals/tiered-risk/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "WRITE"
    assert data["need_confirmation"] is False
    assert data["supports_dry_run"] is True
    assert data["confirmation_token"] is None
    assert "target_entity" in data


@pytest.mark.asyncio
async def test_evaluate_and_confirm_high_risk_workflow(async_client: httpx.AsyncClient) -> None:
    """High-risk operations must issue a one-time token and require explicit confirmation."""
    eval_payload = {
        "tool_name": "delete_database",
        "tool_input": {"table": "users", "force": True},
    }
    eval_resp = await async_client.post("/api/v1/approvals/tiered-risk/evaluate", json=eval_payload)
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    assert eval_data["tier"] == "HIGH_RISK"
    assert eval_data["need_confirmation"] is True
    assert eval_data["suggested_action"] == "NEED_CONFIRMATION"

    token = eval_data["confirmation_token"]
    assert token is not None
    assert token.startswith("tok_")

    # 1. Confirm with human approval and modified input
    confirm_payload = {
        "confirmation_token": token,
        "approved": True,
        "modified_input": {"table": "users_backup", "force": False},
        "reason": "Operator sanitized table target",
    }
    confirm_resp = await async_client.post("/api/v1/approvals/tiered-risk/confirm", json=confirm_payload)
    assert confirm_resp.status_code == 200
    confirm_data = confirm_resp.json()
    assert confirm_data["decision"] == "APPROVED"
    assert confirm_data["status"] == "PROCEED"
    assert confirm_data["tool_name"] == "delete_database"
    assert confirm_data["effective_input"]["table"] == "users_backup"

    # 2. Replay attack should fail (token already consumed)
    replay_resp = await async_client.post("/api/v1/approvals/tiered-risk/confirm", json=confirm_payload)
    assert replay_resp.status_code in (404, 409)


@pytest.mark.asyncio
async def test_confirm_high_risk_rejection(async_client: httpx.AsyncClient) -> None:
    """Human rejection should result in ABORTED status."""
    eval_payload = {
        "tool_name": "run_command",
        "tool_input": {"CommandLine": "rm -rf /"},
    }
    eval_resp = await async_client.post("/api/v1/approvals/tiered-risk/evaluate", json=eval_payload)
    assert eval_resp.status_code == 200
    token = eval_resp.json()["confirmation_token"]
    assert token is not None

    reject_payload = {
        "confirmation_token": token,
        "approved": False,
        "reason": "Dangerous recursive deletion blocked",
    }
    reject_resp = await async_client.post("/api/v1/approvals/tiered-risk/confirm", json=reject_payload)
    assert reject_resp.status_code == 200
    reject_data = reject_resp.json()
    assert reject_data["decision"] == "REJECTED"
    assert reject_data["status"] == "ABORTED"
    assert reject_data["reason"] == "Dangerous recursive deletion blocked"


@pytest.mark.asyncio
async def test_simulate_dry_run_endpoint(async_client: httpx.AsyncClient) -> None:
    """Dry-run endpoint returns simulated execution impact."""
    dry_run_payload = {
        "tool_name": "update_user_profile",
        "tool_input": {"target": "user_42", "tier": "gold"},
    }
    resp = await async_client.post("/api/v1/approvals/tiered-risk/dry-run", json=dry_run_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["simulated"] is True
    assert data["tool_name"] == "update_user_profile"
    assert data["affected_target"] == "user_42"
    assert len(data["predicted_changes"]) >= 1
