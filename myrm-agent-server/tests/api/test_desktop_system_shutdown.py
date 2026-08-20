"""Integration test for Desktop graceful shutdown & drain API contracts."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tests.support.minimal_app import build_minimal_app


@pytest.mark.asyncio
async def test_desktop_shutdown_and_drain_api_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """Validate POST /api/v1/system/shutdown & drain contracts used by Desktop."""
    # Mock graceful_shutdown_task so test runner process is not terminated
    async def noop_shutdown_task() -> None:
        pass

    monkeypatch.setattr(
        "app.api.system.shutdown.graceful_shutdown_task", noop_shutdown_task
    )

    app = build_minimal_app(preset="system")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test/api/v1"
    ) as client:
        # 1. Test POST /api/v1/system/shutdown endpoint contract
        res = await client.post("/system/shutdown")
        assert res.status_code == 200
        data = res.json()
        assert data.get("status") == "shutting_down"
        assert "Graceful shutdown" in data.get("message", "")

        # 2. Test POST /api/v1/system/drain endpoint contract
        res_drain = await client.post("/system/drain")
        assert res_drain.status_code == 200
        drain_data = res_drain.json()
        assert drain_data.get("draining") is True

        # 3. Test DELETE /api/v1/system/drain endpoint contract
        res_cancel = await client.delete("/system/drain")
        assert res_cancel.status_code == 200
        cancel_data = res_cancel.json()
        assert cancel_data.get("draining") is False
