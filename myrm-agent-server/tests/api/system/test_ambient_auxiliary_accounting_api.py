"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.ambient_auxiliary_accounting_api::router

[OUTPUT]:
- Pytest verification for ambient auxiliary usage accounting and task dimension attribution REST endpoints.

[POS]:
tests/api/system/test_ambient_auxiliary_accounting_api.py — 环境感知式用量记账与任务归因 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.ambient_auxiliary_accounting_api import router as ambient_router

test_app = FastAPI()
test_app.include_router(ambient_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_ambient_auxiliary_accounting_api_flow(async_client: httpx.AsyncClient) -> None:
    # 1. Reset all records
    reset_resp = await async_client.post("/api/v1/system/ambient-auxiliary/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json() == {"ok": True}

    # 2. Check initial clean report
    init_rep = await async_client.get("/api/v1/system/ambient-auxiliary/report")
    assert init_rep.status_code == 200
    rep_data = init_rep.json()
    assert rep_data["total_invocations"] == 0
    assert rep_data["total_cost_usd"] == 0.0
    assert rep_data["prompt_cache_purity_preserved"] is True

    # 3. Record main dialogue invocation
    r1_resp = await async_client.post(
        "/api/v1/system/ambient-auxiliary/record",
        json={
            "session_id": "sess_api_01",
            "input_tokens": 1200,
            "output_tokens": 300,
            "duration_ms": 500.0,
            "cost_usd": 0.015,
            "task_type": "main_dialogue",
            "model": "gpt-4o",
        },
    )
    assert r1_resp.status_code == 200
    r1 = r1_resp.json()
    assert r1["task_type"] == "main_dialogue"
    assert r1["total_tokens"] == 1500
    assert r1["effective_task_name"] == "main_dialogue"

    # 4. Record auxiliary invocation: context compression
    r2_resp = await async_client.post(
        "/api/v1/system/ambient-auxiliary/record",
        json={
            "session_id": "sess_api_01",
            "input_tokens": 800,
            "output_tokens": 100,
            "duration_ms": 250.0,
            "cost_usd": 0.005,
            "task_type": "context_compression",
            "model": "gpt-4o-mini",
        },
    )
    assert r2_resp.status_code == 200
    r2 = r2_resp.json()
    assert r2["task_type"] == "context_compression"

    # 5. Check aggregate report
    rep_after = await async_client.get("/api/v1/system/ambient-auxiliary/report?session_id=sess_api_01")
    assert rep_after.status_code == 200
    data = rep_after.json()
    assert data["total_invocations"] == 2
    assert abs(data["total_cost_usd"] - 0.020) < 1e-4
    assert abs(data["core_dialogue_cost_usd"] - 0.015) < 1e-4
    assert abs(data["auxiliary_cost_usd"] - 0.005) < 1e-4
    # Aux share = 0.005 / 0.020 = 25.0%
    assert abs(data["auxiliary_cost_share_pct"] - 25.0) < 0.1
    assert len(data["task_summaries"]) == 2

    # 6. Retrieve recent snapshots
    snaps_resp = await async_client.get("/api/v1/system/ambient-auxiliary/recent-snapshots?session_id=sess_api_01")
    assert snaps_resp.status_code == 200
    snaps = snaps_resp.json()
    assert len(snaps) == 2

    # 7. Reset session-specific telemetry
    reset_sess = await async_client.post(
        "/api/v1/system/ambient-auxiliary/reset",
        json={"session_id": "sess_api_01"},
    )
    assert reset_sess.status_code == 200

    snaps_cleared = await async_client.get("/api/v1/system/ambient-auxiliary/recent-snapshots?session_id=sess_api_01")
    assert snaps_cleared.status_code == 200
    assert len(snaps_cleared.json()) == 0
