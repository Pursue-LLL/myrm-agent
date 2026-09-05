"""全链路业务任务流 E2E 测试：搜索配额透明水库 + 浏览器算力水表 + 看门狗防护.

[INPUT]
- app.services.observability.runtime_meter_service.runtime_meter_service
- app.api.statistics.quota_runtime_router.router
- app.database.base.Base
- myrm_agent_harness.toolkits.browser.observability.BrowserObservability
- myrm_agent_harness.toolkits.browser.observability.RecordingConfig
- myrm_agent_harness.toolkits.browser.observability.BrowserRunTelemetry

[OUTPUT]
- Task flow E2E verifying in an isolated, ultra-fast in-memory database:
  1. Search query accumulation in SQLite ledger
  2. 429 quota exhaustion trigger and self-healing re-anchor
  3. Frontend REST reset & quota limit adjustment
  4. Browser compute runtime & network bandwidth telemetry recording
  5. 3-minute anti-runaway watchdog enforcement
"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.statistics.quota_runtime_router import router as quota_router
from app.database.connection import get_db, get_session
from app.database.models.runtime_quota_metric import Base
from app.services.observability.runtime_meter_service import runtime_meter_service
from myrm_agent_harness.toolkits.browser.observability import (
    BrowserObservability,
    BrowserRunTelemetry,
    RecordingConfig,
)
from myrm_agent_harness.toolkits.web_search.core.error_handling import (
    is_quota_or_rate_limit_error,
)


@pytest.mark.asyncio
async def test_e2e_search_quota_and_browser_compute_task_flow() -> None:
    """全链路 Task Flow E2E 验证：搜索配额熔断自愈 + 浏览器算力度量 + 看门狗防护."""
    # 创建独立隔离的内存 SQLite 引擎与会话工厂（零锁竞争、毫秒级执行）
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )

    test_app = FastAPI()
    test_app.include_router(quota_router, prefix="/api/statistics")

    async def _override_get_session():
        async with session_factory() as s:
            yield s

    test_app.dependency_overrides[get_session] = _override_get_session

    try:
        # Step 1: 真实模拟执行 5 次搜索任务调用
        async with session_factory() as session:
            await runtime_meter_service.reset_search_quota(session, provider="tavily")
            await runtime_meter_service.update_search_quota_limit(session, "tavily", 1000)

            for _ in range(5):
                await runtime_meter_service.record_search_usage(session, "tavily", count=1)

            # 检查配额水位
            quotas = await runtime_meter_service.get_search_quotas(session)
            tavily_q = next((q for q in quotas if q["provider"] == "tavily"), None)
            assert tavily_q is not None
            assert int(tavily_q["used_count"]) >= 5
            assert tavily_q["status"] in {"healthy", "warning"}
            assert tavily_q["is_metered"] is True

            # Step 2: 模拟发生真实 429 报错，Harness 状态机判定
            fake_429_exc = RuntimeError("HTTP 429: monthly_limit_reached for account")
            assert is_quota_or_rate_limit_error(fake_429_exc) is True

            # 同步至业务持久化表触发自愈归零
            await runtime_meter_service.record_search_usage(
                session, "tavily", count=1, quota_exceeded=True
            )
            quotas_after_depleted = await runtime_meter_service.get_search_quotas(session)
            tavily_depleted = next(
                (q for q in quotas_after_depleted if q["provider"] == "tavily"), None
            )
            assert tavily_depleted is not None
            assert tavily_depleted["is_depleted"] is True
            assert tavily_depleted["status"] == "depleted"

        # Step 3: 通过 FastAPI 路由真实模拟前端一键校准重置
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as ac:
            reset_resp = await ac.post(
                "/api/statistics/search-quotas/reset", json={"provider": "tavily"}
            )
            assert reset_resp.status_code == 200
            reset_body = reset_resp.json()
            assert reset_body["code"] == 0
            reset_payload = reset_body.get("data", {})
            assert reset_payload.get("reset_records_count", 0) >= 1

            # Step 4: 模拟前端修改配额上限为 2000
            limit_resp = await ac.put(
                "/api/statistics/search-quotas/limit",
                json={"provider": "tavily", "quota_limit": 2000},
            )
            assert limit_resp.status_code == 200
            limit_body = limit_resp.json()
            assert limit_body["code"] == 0
            limit_payload = limit_body.get("data", {})
            assert limit_payload.get("quota_limit") == 2000

        # Step 5: 验证重置后已复原为 healthy 且用量清零
        async with session_factory() as session:
            quotas_after_reset = await runtime_meter_service.get_search_quotas(session)
            tavily_restored = next(
                (q for q in quotas_after_reset if q["provider"] == "tavily"), None
            )
            assert tavily_restored is not None
            assert tavily_restored["is_depleted"] is False
            assert tavily_restored["status"] == "healthy"
            assert tavily_restored["used_count"] == 0

            # Step 6: 模拟浏览器运行全过程
            telemetry = BrowserRunTelemetry(
                start_time=time.time() - 300.0,
                active_compute_seconds=180.0,
                request_count=42,
                failed_request_count=0,
                total_bytes_transferred=20 * 1024 * 1024,  # 20 MB
            )
            telemetry.mark_closed()

            # 录入持久化账本
            await runtime_meter_service.record_browser_runtime(
                session=session,
                duration_seconds=telemetry.total_duration_seconds,
                active_compute_seconds=telemetry.active_compute_seconds,
                bytes_transferred=telemetry.total_bytes_transferred,
                request_count=telemetry.request_count,
                failed_request_count=telemetry.failed_request_count,
                session_id="task-flow-test-session-001",
            )

        # Step 7: 通过 REST API 查询浏览器算力消耗汇总
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as ac:
            browser_resp = await ac.get("/api/statistics/browser-runtime")
            assert browser_resp.status_code == 200
            raw_summary = browser_resp.json()
            assert raw_summary["code"] == 0
            summary = raw_summary.get("data", {})
            assert summary["session_count"] >= 1
            assert summary["active_compute_minutes"] >= 3.0
            assert summary["total_megabytes_transferred"] >= 20.0
            assert summary["estimated_compute_cost_usd"] > 0

        # Step 8: 验证 3 分钟死循环主动看门狗
        obs = BrowserObservability(recording_config=RecordingConfig())
        now = time.time()
        assert (
            obs.check_action_watchdog(now - 30.0, timeout_seconds=180.0) is False
        )
        assert (
            obs.check_action_watchdog(now - 200.0, timeout_seconds=180.0) is True
        )
    finally:
        test_app.dependency_overrides.clear()
        await test_engine.dispose()
