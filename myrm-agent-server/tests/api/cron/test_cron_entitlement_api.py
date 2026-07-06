"""REST API tests for cron entitlement enforcement via EntitlementGuardedCronManager."""

from __future__ import annotations

from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.platform_utils.sandbox.entitlements.entitlement_guard import EntitlementGuardError


async def _raise_entitlement_blocked(*_args: object, **_kwargs: object) -> None:
    cause = EntitlementGuardError("Cron is not available on the current plan. Upgrade to Companion or above.")
    raise ValueError(str(cause)) from cause


@pytest.fixture
def app() -> Generator[FastAPI, None, None]:
    from app.api.cron.routes import helpers, router

    test_app = FastAPI()
    test_app.include_router(router, prefix="/cron")
    mock_mgr = MagicMock()
    mock_mgr.create_job = AsyncMock(side_effect=_raise_entitlement_blocked)
    mock_mgr.duplicate_job = AsyncMock(side_effect=_raise_entitlement_blocked)

    with patch.object(helpers, "_get_manager", return_value=mock_mgr):
        yield test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_create_job_returns_403_on_entitlement_failure(client: TestClient) -> None:
    resp = client.post(
        "/cron",
        json={
            "name": "blocked-job",
            "job_type": "agent",
            "schedule": {"kind": "interval", "interval_ms": 300_000},
            "prompt": "check",
        },
    )
    assert resp.status_code == 403
    assert "Upgrade" in resp.json()["detail"]


def test_duplicate_job_returns_403_on_entitlement_failure(client: TestClient) -> None:
    resp = client.post("/cron/job-123/duplicate")
    assert resp.status_code == 403
