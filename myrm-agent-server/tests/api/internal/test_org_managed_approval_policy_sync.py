"""Unit tests for CP org managed approval policy sync endpoint."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.api.security import ManagedApprovalPolicy, get_process_managed_approval_policy

from app.api.internal.org_managed_approval_policy_sync import (
    router as org_managed_approval_policy_sync_router,
)


@pytest.fixture
def map_sync_app() -> FastAPI:
    app = FastAPI()
    app.include_router(org_managed_approval_policy_sync_router)
    return app


@pytest.fixture(autouse=True)
def reset_process_map() -> None:
    from myrm_agent_harness.api.security import configure_process_managed_approval_policy

    configure_process_managed_approval_policy(ManagedApprovalPolicy.empty())
    yield
    configure_process_managed_approval_policy(ManagedApprovalPolicy.empty())


@pytest.mark.asyncio
async def test_sync_applies_process_map(map_sync_app: FastAPI) -> None:
    transport = ASGITransport(app=map_sync_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/org-managed-approval-policy-sync",
            json={
                "ignoreAllowlistForModels": ["claude-opus*"],
                "forceAutoReviewForModels": ["gpt-*"],
                "disableYolo": True,
                "disableAllowAlways": False,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "synced"
    assert data["active"] is True

    policy = get_process_managed_approval_policy()
    assert policy.should_ignore_allowlist("claude-opus-4") is True
    assert policy.should_force_auto_review("gpt-4o") is True
    assert policy.disable_yolo is True


@pytest.mark.asyncio
async def test_sync_empty_clears_to_inactive(map_sync_app: FastAPI) -> None:
    transport = ASGITransport(app=map_sync_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/org-managed-approval-policy-sync",
            json={
                "ignoreAllowlistForModels": [],
                "forceAutoReviewForModels": [],
                "disableYolo": False,
                "disableAllowAlways": False,
            },
        )

    assert resp.status_code == 200
    assert resp.json()["active"] is False
    assert get_process_managed_approval_policy() == ManagedApprovalPolicy.empty()


@pytest.mark.asyncio
async def test_sync_rejects_invalid_token(map_sync_app: FastAPI) -> None:
    with patch.dict("os.environ", {"CONTROL_PLANE_TELEMETRY_TOKEN": "secret123"}):
        transport = ASGITransport(app=map_sync_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/org-managed-approval-policy-sync",
                json={
                    "ignoreAllowlistForModels": [],
                    "forceAutoReviewForModels": [],
                    "disableYolo": False,
                    "disableAllowAlways": False,
                },
                headers={"X-Telemetry-Token": "wrong"},
            )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_sync_publishes_managed_policy_updated_event(map_sync_app: FastAPI) -> None:
    from app.services.event.app_event_bus import AppEventType

    with patch("app.api.internal.org_managed_approval_policy_sync.get_event_bus") as mock_bus:
        transport = ASGITransport(app=map_sync_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/org-managed-approval-policy-sync",
                json={
                    "ignoreAllowlistForModels": [],
                    "forceAutoReviewForModels": ["gpt-*"],
                    "disableYolo": True,
                    "disableAllowAlways": False,
                },
            )

        assert resp.status_code == 200
        mock_bus.return_value.publish.assert_called_once()
        event = mock_bus.return_value.publish.call_args.args[0]
        assert event.event_type == AppEventType.MANAGED_POLICY_UPDATED
        assert event.data["active"] is True
        assert isinstance(event.data["revision"], int)
        assert event.data["revision"] >= 1
