"""Integration: local-only shell fixture seeds live registry for Chrome E2E."""

from __future__ import annotations

import asyncio

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
        int(seed["pid"])
        job_id = str(seed["job_id"])

        row_resp = await client.get(f"/api/v1/background-tasks/shell:{job_id}")
        assert row_resp.status_code == 200
        row = row_resp.json()
        assert row["status"] == "failed"
        assert row["exit_code"] == 42
        assert row["error_category"] == "nonzero_exit"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_seed_shell_fixture_running_mode_exposes_live_row() -> None:
    transport = ASGITransport(app=_build_rest_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        seed_resp = await client.post("/api/v1/background-tasks/test/seed-shell-fixture?mode=running")
        assert seed_resp.status_code == 200
        seed = seed_resp.json()
        job_id = str(seed["job_id"])

        row: dict[str, object] = {}
        for _ in range(20):
            row_resp = await client.get(f"/api/v1/background-tasks/shell:{job_id}")
            assert row_resp.status_code == 200
            row = row_resp.json()
            status = str(row.get("status") or "")
            if status == "running":
                break
            await asyncio.sleep(0.1)

        assert row["status"] == "running"
        assert row.get("pid") is not None
