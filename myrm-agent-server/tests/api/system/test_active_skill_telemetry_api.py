"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.active_skill_telemetry_api::router

[OUTPUT]:
- Pytest verification for active skill span telemetry REST endpoints and per-skill P95 latency aggregations.

[POS]:
tests/api/system/test_active_skill_telemetry_api.py — 活跃技能 Span 遥测透传 REST API 单元测试。
"""

from collections.abc import AsyncGenerator
from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.active_skill_telemetry_api import router as telemetry_router

test_app = FastAPI()
test_app.include_router(telemetry_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_active_skill_telemetry_api_lifecycle(async_client: httpx.AsyncClient) -> None:
    # 1. Reset telemetry state
    reset_resp = await async_client.post("/api/v1/system/active-skill-telemetry/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json() == {"status": "reset_completed"}

    # 2. Record span with active skill git_master
    r1 = await async_client.post(
        "/api/v1/system/active-skill-telemetry/record-span",
        json={
            "name": "tool.git_commit",
            "duration_ms": 45.0,
            "active_skill": "git_master",
            "status": "ok",
            "attributes": {"git.branch": "main"},
        },
    )
    assert r1.status_code == 200
    span1 = r1.json()
    assert span1["active_skill"] == "git_master"
    assert span1["attributes"]["myrm.skill.active"] == "git_master"
    assert span1["attributes"]["omnigent.skill.active"] == "git_master"
    assert span1["attributes"]["git.branch"] == "main"

    # 3. Record span with active skill data_analysis (error status)
    r2 = await async_client.post(
        "/api/v1/system/active-skill-telemetry/record-span",
        json={
            "name": "tool.sql_query",
            "duration_ms": 120.0,
            "active_skill": "data_analysis",
            "status": "error",
        },
    )
    assert r2.status_code == 200
    span2 = r2.json()
    assert span2["active_skill"] == "data_analysis"
    assert span2["status"] == "error"

    # 4. Record unattributed baseline span
    r3 = await async_client.post(
        "/api/v1/system/active-skill-telemetry/record-span",
        json={
            "name": "system.heartbeat",
            "duration_ms": 5.0,
            "status": "ok",
        },
    )
    assert r3.status_code == 200
    span3 = r3.json()
    assert span3["active_skill"] is None

    # 5. Retrieve telemetry report
    report_resp = await async_client.get("/api/v1/system/active-skill-telemetry/report")
    assert report_resp.status_code == 200
    report_data = report_resp.json()
    assert report_data["total_spans_recorded"] == 3
    assert report_data["skills_count"] == 2
    assert report_data["unattributed_spans_count"] == 1
    assert len(report_data["skill_aggregations"]) == 2

    git_agg = next(a for a in report_data["skill_aggregations"] if a["skill_name"] == "git_master")
    assert git_agg["total_spans"] == 1
    assert git_agg["error_spans"] == 0
    assert git_agg["error_rate"] == 0.0
    assert git_agg["avg_duration_ms"] == 45.0

    analysis_agg = next(a for a in report_data["skill_aggregations"] if a["skill_name"] == "data_analysis")
    assert analysis_agg["total_spans"] == 1
    assert analysis_agg["error_spans"] == 1
    assert analysis_agg["error_rate"] == 1.0
    assert analysis_agg["avg_duration_ms"] == 120.0

    # 6. Retrieve spans filtered by active skill
    filtered_spans_resp = await async_client.get(
        "/api/v1/system/active-skill-telemetry/spans",
        params={"skill_name": "git_master"},
    )
    assert filtered_spans_resp.status_code == 200
    spans_git = filtered_spans_resp.json()
    assert len(spans_git) == 1
    assert spans_git[0]["name"] == "tool.git_commit"
