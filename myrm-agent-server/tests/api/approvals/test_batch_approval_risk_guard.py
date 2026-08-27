"""Unit and integration tests for /approvals/batch-resolve security guard."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.approvals.router import router as approvals_router
from app.database.models.approval import ApprovalRecord
from app.services.approvals.registry import ApprovalRegistry


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(approvals_router)
    with TestClient(app) as c:
        yield c


def test_batch_resolve_safe_items_succeeds(client: TestClient):
    rec1 = ApprovalRecord(
        id="appr-safe-1",
        agent_id="agent1",
        action_type="file_read",
        status="PENDING",
        severity="info",
        reason="Reading config file",
        payload={"tool_name": "read_file"},
    )
    rec2 = ApprovalRecord(
        id="appr-safe-2",
        agent_id="agent1",
        action_type="web_search",
        status="PENDING",
        severity="low",
        reason="Search docs",
        payload={"tool_name": "search"},
    )

    with patch.object(
        ApprovalRegistry,
        "get_approval",
        new=AsyncMock(side_effect=lambda approval_id: rec1 if approval_id == "appr-safe-1" else rec2),
    ), patch.object(
        ApprovalRegistry,
        "resolve_approval",
        new=AsyncMock(side_effect=lambda approval_id, decision, edited_payload=None: rec1 if approval_id == "appr-safe-1" else rec2),
    ):
        response = client.post(
            "/approvals/batch-resolve",
            json={"approval_ids": ["appr-safe-1", "appr-safe-2"], "decision": "approve"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["approvals"]) == 2


def test_batch_resolve_high_risk_blocked_with_409(client):
    rec_safe = ApprovalRecord(
        id="appr-safe-1",
        agent_id="agent1",
        action_type="file_read",
        status="PENDING",
        severity="info",
        reason="Reading config file",
        payload={"tool_name": "read_file"},
    )
    rec_high = ApprovalRecord(
        id="appr-high-1",
        agent_id="agent1",
        action_type="system_reboot",
        status="PENDING",
        severity="critical",
        reason="Reboot host",
        payload={"tool_name": "reboot"},
    )

    with patch.object(
        ApprovalRegistry,
        "get_approval",
        new=AsyncMock(side_effect=lambda approval_id: rec_safe if approval_id == "appr-safe-1" else rec_high),
    ):
        response = client.post(
            "/approvals/batch-resolve",
            json={"approval_ids": ["appr-safe-1", "appr-high-1"], "decision": "approve"},
        )
        assert response.status_code == 409
        data = response.json()
        assert data["detail"]["error"] == "BATCH_HIGH_RISK_CONFIRMATION_REQUIRED"
        assert data["detail"]["high_risk_count"] == 1
        assert data["detail"]["safe_count"] == 1
        assert len(data["detail"]["high_risk_items"]) == 1
        assert data["detail"]["high_risk_items"][0]["item_id"] == "appr-high-1"


def test_batch_resolve_high_risk_with_explicit_confirm(client):
    rec_high = ApprovalRecord(
        id="appr-high-1",
        agent_id="agent1",
        action_type="delete_file",
        status="PENDING",
        severity="high",
        reason="Delete temp dir",
        payload={"tool_name": "rm"},
    )

    with patch.object(
        ApprovalRegistry,
        "get_approval",
        new=AsyncMock(return_value=rec_high),
    ), patch.object(
        ApprovalRegistry,
        "resolve_approval",
        new=AsyncMock(return_value=rec_high),
    ):
        response = client.post(
            "/approvals/batch-resolve",
            json={
                "approval_ids": ["appr-high-1"],
                "decision": "approve",
                "confirm_high_risk": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["approvals"]) == 1


def test_batch_resolve_safe_only_mode(client):
    rec_safe = ApprovalRecord(
        id="appr-safe-1",
        agent_id="agent1",
        action_type="file_read",
        status="PENDING",
        severity="info",
        reason="Reading config file",
        payload={"tool_name": "read_file"},
    )
    rec_high = ApprovalRecord(
        id="appr-high-1",
        agent_id="agent1",
        action_type="delete_file",
        status="PENDING",
        severity="high",
        reason="Delete temp dir",
        payload={"tool_name": "rm"},
    )

    with patch.object(
        ApprovalRegistry,
        "get_approval",
        new=AsyncMock(side_effect=lambda approval_id: rec_safe if approval_id == "appr-safe-1" else rec_high),
    ), patch.object(
        ApprovalRegistry,
        "resolve_approval",
        new=AsyncMock(return_value=rec_safe),
    ):
        response = client.post(
            "/approvals/batch-resolve",
            json={
                "approval_ids": ["appr-safe-1", "appr-high-1"],
                "decision": "approve",
                "safe_only": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["approvals"]) == 1
