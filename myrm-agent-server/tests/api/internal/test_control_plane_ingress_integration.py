"""Integration tests for Control Plane Ingress endpoints with Origin and Token Guard.

[INPUT]
- app.api.channels.channel_ingress::router
- app.api.internal.agent_interrupt::router
- app.core.security.auth.control_plane_guard::verify_control_plane_token

[OUTPUT]
- Integration verification of unmocked endpoint authorization flow.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.api.channels.channel_ingress import router as channel_router
from app.api.internal.agent_interrupt import router as interrupt_router
from app.config.settings import settings
from tests.support.minimal_app import build_minimal_app


@pytest.fixture
def cp_ingress_app():
    from fastapi import FastAPI

    app = FastAPI(title="CP Ingress Test App")
    app.include_router(channel_router)
    app.include_router(interrupt_router)
    return app


@pytest.mark.asyncio
async def test_channel_ingress_token_gate_unauthorized(
    cp_ingress_app, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings.control_plane, "telemetry_token", SecretStr("secret-cp-token"))
    monkeypatch.setattr(settings, "cors_origins", ["http://localhost:3000"])

    async with AsyncClient(
        transport=ASGITransport(app=cp_ingress_app),
        base_url="http://testserver",
    ) as client:
        # 1. No token -> 401 Unauthorized
        resp_no_token = await client.post(
            "/api/channel/message",
            json={"message_id": "m1", "content": "hi", "channel_type": "feishu", "channel_user_id": "u1"},
        )
        assert resp_no_token.status_code == 401

        # 2. Wrong token -> 401 Unauthorized
        resp_wrong_token = await client.post(
            "/api/channel/message",
            headers={"X-Control-Plane-Token": "bad-token"},
            json={"message_id": "m1", "content": "hi", "channel_type": "feishu", "channel_user_id": "u1"},
        )
        assert resp_wrong_token.status_code == 401

        # 3. Malicious Origin -> 403 Forbidden
        resp_bad_origin = await client.post(
            "/api/channel/message",
            headers={
                "X-Control-Plane-Token": "secret-cp-token",
                "Origin": "http://malicious-site.com",
            },
            json={"message_id": "m1", "content": "hi", "channel_type": "feishu", "channel_user_id": "u1"},
        )
        assert resp_bad_origin.status_code == 403


@pytest.mark.asyncio
async def test_agent_interrupt_token_gate_success(
    cp_ingress_app, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings.control_plane, "telemetry_token", SecretStr("secret-cp-token"))
    monkeypatch.setattr(settings, "cors_origins", ["http://localhost:3000"])

    async with AsyncClient(
        transport=ASGITransport(app=cp_ingress_app),
        base_url="http://testserver",
    ) as client:
        # Valid token via X-Telemetry-Token
        resp = await client.post(
            "/api/agent/interrupt",
            headers={"X-Telemetry-Token": "secret-cp-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
