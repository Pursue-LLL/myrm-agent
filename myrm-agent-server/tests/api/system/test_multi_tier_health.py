"""[INPUT]
- httpx, ASGITransport
- app.api.system.multi_tier_health_api::{router, record_trace_tree}
- app.core.infra.health.multi_tier_health::{MultiTierHealthChecker, TierLevel, HealthStatus}

[OUTPUT]
- Pytest test cases verifying multi-tier health verdicts, self-healing triggering, and causal trace lookup.

[POS]
tests/api/system/test_multi_tier_health.py — 分层健康检查与因果 Trace 查询 API 单元测试。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.system.multi_tier_health_api import record_trace_tree
from app.api.system.multi_tier_health_api import router as multi_tier_health_router
from app.core.infra.health.multi_tier_health import HealthStatus, MultiTierHealthChecker, TierLevel

test_app = FastAPI()
test_app.include_router(multi_tier_health_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_get_multi_tier_health_default_healthy(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.get("/api/v1/system/health/multi-tier")
    assert resp.status_code == 200
    data = resp.json()

    assert data["overall_status"] == "healthy"
    assert "所有组件与入口通道状态全绿" in data["summary"]
    probe_names = [p["name"] for p in data["probes"]]
    assert "database" in probe_names
    assert "webui_gateway" in probe_names


@pytest.mark.asyncio
async def test_multi_tier_health_checker_verdicts_and_self_healing() -> None:
    checker = MultiTierHealthChecker()

    # 1. 注册正常组件与正常入口
    async def ok_probe() -> tuple[HealthStatus, str]:
        return HealthStatus.HEALTHY, "OK"

    checker.register_probe("db", TierLevel.COMPONENT, ok_probe, is_core=True)
    checker.register_probe("web", TierLevel.INGRESS, ok_probe, is_core=True)

    report = await checker.check_all()
    assert report.overall_status == HealthStatus.HEALTHY

    # 2. 注入核心组件故障（无自愈）-> UNHEALTHY
    async def fail_probe() -> tuple[HealthStatus, str]:
        return HealthStatus.UNHEALTHY, "Connection lost"

    checker.register_probe("broken_core", TierLevel.COMPONENT, fail_probe, is_core=True)
    report2 = await checker.check_all()
    assert report2.overall_status == HealthStatus.UNHEALTHY
    assert "核心组件异常" in report2.summary

    # 3. 注册自愈函数 -> 触发自愈并降级为 DEGRADED
    async def heal_broken_core() -> bool:
        return True

    checker.register_recovery_fn("broken_core", heal_broken_core)
    report3 = await checker.check_all()
    assert report3.overall_status == HealthStatus.DEGRADED
    assert any("自愈函数已触发" in p.message for p in report3.probes if p.name == "broken_core")


@pytest.mark.asyncio
async def test_get_trace_tree_endpoint(async_client: httpx.AsyncClient) -> None:
    trace_id = "test-causal-trace-777"
    fake_tree = {
        "trace_id": trace_id,
        "root": {
            "name": "agent_execution",
            "kind": "input",
            "status": "ok",
            "duration_ms": 125.4,
            "children": [],
        },
    }

    record_trace_tree(trace_id, fake_tree)

    # 成功检索
    resp = await async_client.get(f"/api/v1/system/traces/{trace_id}")
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["trace_id"] == trace_id
    assert res_data["root"]["name"] == "agent_execution"

    # 查询不存在的 trace 返回 404
    not_found_resp = await async_client.get("/api/v1/system/traces/non-existent-999")
    assert not_found_resp.status_code == 404
