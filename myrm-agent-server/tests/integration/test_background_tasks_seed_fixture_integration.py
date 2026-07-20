"""Integration: local-only shell fixture seeds live registry for Chrome E2E."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tests.integration.test_background_tasks_rest_api import _build_rest_app


@pytest.mark.integration
@pytest.mark.asyncio
async def test_seed_shell_fixture_failed_mode_exposes_exit_metadata() -> None:
    transport = ASGITransport(app=_build_rest_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        seed_resp = await client.post("/api/v1/background-tasks/test/seed-shell-fixture?mode=failed")
        assert seed_resp.status_code == 200
        seed = seed_resp.json()
        pid = int(seed["pid"])

        row_resp = await client.get(f"/api/v1/background-tasks/shell:{pid}")
        assert row_resp.status_code == 200
        row = row_resp.json()
        assert row["status"] == "failed"
        assert row["exit_code"] == 42
        assert row["error_category"] == "nonzero_exit"
