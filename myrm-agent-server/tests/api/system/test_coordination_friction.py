"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.coordination_friction_api::router

[OUTPUT]:
- Pytest test cases verifying coordination friction scoreboard, intervention recording, and template supervision decay curve APIs.

[POS]:
tests/api/system/test_coordination_friction.py — 人机协调摩擦度量与监督衰减曲线 API 单元测试。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.coordination_friction_api import router as coordination_friction_router

test_app = FastAPI()
test_app.include_router(coordination_friction_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_get_coordination_scoreboard_seeded(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.get("/api/v1/system/coordination-friction/scoreboard")
    assert resp.status_code == 200
    data = resp.json()

    assert data["template_type"] == "global"
    assert data["total_runs"] >= 5
    assert data["average_friction_rate"] > 0
    assert data["total_coordination_hours_saved"] >= 0
    assert len(data["decay_curve"]) >= 2
    assert "broadcast_prep" in data["active_templates"]
    assert "channel_deal" in data["active_templates"]


@pytest.mark.asyncio
async def test_record_task_intervention(async_client: httpx.AsyncClient) -> None:
    payload = {
        "task_id": "task-refactor-101",
        "template_type": "code_refactor",
        "execution_sequence": 1,
        "total_substeps": 20,
        "intervention_count": 4,
        "rework_count": 1,
        "human_attention_minutes": 15.0,
        "intervention_type": "STEER_CORRECTION",
    }
    resp = await async_client.post(
        "/api/v1/system/coordination-friction/record-intervention",
        json=payload,
    )
    assert resp.status_code == 201
    data = resp.json()

    assert data["task_id"] == "task-refactor-101"
    assert data["template_type"] == "code_refactor"
    assert data["friction_rate"] == 2.0  # (4 / 20) * 10
    assert data["rework_count"] == 1
    assert data["human_attention_minutes"] == 15.0


@pytest.mark.asyncio
async def test_get_template_decay_curve(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.get(
        "/api/v1/system/coordination-friction/decay-curve/broadcast_prep"
    )
    assert resp.status_code == 200
    points = resp.json()

    assert len(points) >= 3
    # Check that sequence is ordered: 1, 2, 3
    assert points[0]["sequence_number"] == 1
    assert points[1]["sequence_number"] == 2
    assert points[2]["sequence_number"] == 3
    # Decay: rate should decrease over time
    assert points[0]["intervention_rate_pct"] > points[-1]["intervention_rate_pct"]
