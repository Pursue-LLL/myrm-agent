"""Tests for internal background shell status endpoint."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.internal.background_shell_status import router as background_shell_status_router


@pytest.fixture
def status_app() -> FastAPI:
    app = FastAPI()
    app.include_router(background_shell_status_router)
    return app


@pytest.mark.asyncio
async def test_background_shell_status_requires_token(status_app: FastAPI) -> None:
    transport = ASGITransport(app=status_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/internal/background-shell/status")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_background_shell_status_returns_running_count(status_app: FastAPI) -> None:
    transport = ASGITransport(app=status_app)
    with (
        patch.dict(os.environ, {"CONTROL_PLANE_TELEMETRY_TOKEN": "test-token"}),
        patch(
            "myrm_agent_harness.api.hooks.count_running_background_shell_jobs",
            return_value=2,
        ),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/internal/background-shell/status",
                headers={"X-Telemetry-Token": "test-token"},
            )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["running_count"] == 2
    assert payload["registry_ephemeral"] is True
