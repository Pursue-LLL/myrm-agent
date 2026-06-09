"""Tests for the E-Stop security API endpoint."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def _reset_estop():
    """Ensure estop is inactive before/after each test."""
    from myrm_agent_harness.agent.security.guards.estop import get_estop_guard

    guard = get_estop_guard()
    guard.resume(resumed_by="test_setup")
    yield
    guard.resume(resumed_by="test_teardown")


@pytest.mark.asyncio
class TestEstopAPI:
    async def test_get_status_inactive(self, _reset_estop, _bypass_auth):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/security/estop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["level"] == "none"

    async def test_activate_tool_freeze(self, _reset_estop, _bypass_auth):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/security/estop",
                json={"action": "activate", "level": "tool_freeze", "reason": "test freeze"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["level"] == "tool_freeze"
        assert data["activated_by"] == "webui_user"
        assert data["reason"] == "test freeze"

    async def test_activate_and_resume(self, _reset_estop, _bypass_auth):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            await ac.post(
                "/api/v1/security/estop",
                json={"action": "activate", "level": "tool_freeze", "reason": "temp"},
            )
            resp = await ac.post("/api/v1/security/estop", json={"action": "resume"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["level"] == "none"

    async def test_activate_kill_all(self, _reset_estop, _bypass_auth):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/security/estop",
                json={"action": "activate", "level": "kill_all", "reason": "critical"},
            )
        assert resp.status_code == 200
        assert resp.json()["level"] == "kill_all"
