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
from app.api.internal.background_shell_status import router as bg_shell_router
from app.api.internal.skills_killswitch import router as killswitch_router
from app.config.settings import settings


@pytest.fixture
def cp_ingress_app():
    from fastapi import FastAPI

    app = FastAPI(title="CP Ingress Test App")
    app.include_router(channel_router, prefix="/api")
    app.include_router(interrupt_router, prefix="/api")
    app.include_router(bg_shell_router)
    app.include_router(killswitch_router)
    return app


@pytest.mark.asyncio
async def test_channel_ingress_token_gate_unauthorized(cp_ingress_app, monkeypatch: pytest.MonkeyPatch) -> None:
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
async def test_agent_interrupt_token_gate_success(cp_ingress_app, monkeypatch: pytest.MonkeyPatch) -> None:
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
        assert "interrupted" in data


@pytest.mark.asyncio
async def test_background_shell_status_token_gate(cp_ingress_app, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.control_plane, "telemetry_token", SecretStr("secret-cp-token"))
    monkeypatch.setattr(settings, "cors_origins", ["http://localhost:3000"])

    async with AsyncClient(
        transport=ASGITransport(app=cp_ingress_app),
        base_url="http://testserver",
    ) as client:
        # 1. No token -> 401
        resp_no_token = await client.get("/api/internal/background-shell/status")
        assert resp_no_token.status_code == 401

        # 2. Valid token -> 200
        resp_valid = await client.get(
            "/api/internal/background-shell/status",
            headers={"X-Control-Plane-Token": "secret-cp-token"},
        )
        assert resp_valid.status_code == 200
        data = resp_valid.json()
        assert "running_count" in data


@pytest.mark.asyncio
async def test_killswitch_origin_and_token_gate(cp_ingress_app, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.control_plane, "telemetry_token", SecretStr("secret-cp-token"))
    monkeypatch.setattr(settings, "cors_origins", ["http://localhost:3000"])

    async with AsyncClient(
        transport=ASGITransport(app=cp_ingress_app),
        base_url="http://testserver",
    ) as client:
        # 1. Invalid origin -> 403
        resp_bad_origin = await client.post(
            "/api/internal/skills/killswitch",
            headers={
                "X-Control-Plane-Token": "secret-cp-token",
                "Origin": "http://evil-origin.com",
            },
            json={"skill_id": "bash", "action": "disable"},
        )
        assert resp_bad_origin.status_code == 403

        # 2. Allowed origin with token
        resp_allowed = await client.post(
            "/api/internal/skills/killswitch",
            headers={
                "X-Control-Plane-Token": "secret-cp-token",
                "Origin": "http://localhost:3000",
            },
            json={"skill_id": "test_skill", "action": "disable"},
        )
        assert resp_allowed.status_code == 200
        data = resp_allowed.json()
        assert data["status"] == "disabled"
        assert data["skill_id"] == "test_skill"
