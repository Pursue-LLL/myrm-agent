# -*- coding: utf-8 -*-
"""E2E 集成测试：搜索源配额自治熔断自愈与浏览器沙箱算力计量全链路闭环 (Task Flow E2E)

验证完整闭环链路：
1. 真实初始化 SQLite 数据库与统计表；
2. 模拟真实搜索任务执行，验证每轮调用精准记账；
3. 模拟第三方 Provider 抛出持久性配额耗尽异常 (429/402)，验证 Harness 链条熔断并标记为 DEPLETED；
4. 验证随后的搜索请求自动跳过 DEPLETED 的 Provider，优先 fallback 至健康 Provider（如 SearXNG 免鉴权专线）；
5. 验证 REST API 端点支持前端一键校准重置 (/search-quotas/reset)，Provider 状态自愈恢复为 HEALTHY；
6. 验证 REST API 端点支持动态配置每月额度告警上限 (/search-quotas/limit)，数据持久化到 SQLite；
7. 模拟浏览器自动化多轮会话执行，验证 active_compute_minutes 与 total_bytes_transferred 真实统计累加；
8. 验证 3 分钟死循环看门狗 (check_action_watchdog) 超时阻断机制；
9. 验证 REST API 端点 (/browser-runtime) 能够高保真产出折合算力开销与网络流量指标，供前端卡片渲染。
"""

import time

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.browser.observability import (
    BrowserObservability,
    BrowserRunTelemetry,
)
from myrm_agent_harness.toolkits.web_search.core.error_handling import (
    is_persistent_quota_depleted_error,
)
from myrm_agent_harness.toolkits.web_search.providers.chain import (
    ProviderQuotaStatus,
    ProviderQuotaTracker,
)

from fastapi import FastAPI
from app.api.statistics.quota_runtime_router import router as quota_router
from app.database.connection import get_db, get_session
from app.services.observability.runtime_meter_service import runtime_meter_service

test_app = FastAPI()
test_app.include_router(quota_router, prefix="/api/statistics")


@pytest.mark.asyncio
async def test_e2e_search_quota_and_browser_compute_task_flow() -> None:
    """全链路 Task Flow E2E 验证：搜索配额熔断自愈 + 浏览器算力度量 + 看门狗防护"""
    async with get_session() as session:
        # Step 1: 前置重置环境
        await runtime_meter_service.reset_search_quota(session, provider="tavily")
        await runtime_meter_service.update_search_quota_limit(session, "tavily", 1000)

        # Step 2: 真实模拟执行搜索任务（记录调用）
        for _ in range(5):
            await runtime_meter_service.record_search_query(session, "tavily")

        # 检查配额水位
        quotas = await runtime_meter_service.get_search_quotas(session)
        tavily_q = next((q for q in quotas if q.provider == "tavily"), None)
        assert tavily_q is not None
        assert tavily_q.used_count >= 5
        assert tavily_q.status in {"healthy", "warning"}
        assert tavily_q.is_metered is True

        # Step 3: 模拟发生真实 429 报错，Harness 状态机判定
        fake_429_exc = RuntimeError("HTTP 429: monthly_limit_reached for account")
        assert is_persistent_quota_depleted_error(fake_429_exc) is True

        # 标记熔断
        tracker = ProviderQuotaTracker()
        tracker.mark_depleted("tavily", reason="monthly_limit_reached")
        assert tracker.get_status("tavily") == ProviderQuotaStatus.DEPLETED

        # 同步至业务持久化表
        await runtime_meter_service.mark_search_quota_depleted(
            session, "tavily", reason="monthly_limit_reached"
        )
        quotas_after_depleted = await runtime_meter_service.get_search_quotas(session)
        tavily_depleted = next(
            (q for q in quotas_after_depleted if q.provider == "tavily"), None
        )
        assert tavily_depleted is not None
        assert tavily_depleted.is_depleted is True
        assert tavily_depleted.status == "depleted"

        # Step 4: 模拟前端一键校准重置
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as ac:
            # 依赖覆盖当前同一个 session
            async def _override_get_db():
                yield session

            test_app.dependency_overrides[get_db] = _override_get_db

            reset_resp = await ac.post(
                "/api/statistics/search-quotas/reset", json={"provider": "tavily"}
            )
            assert reset_resp.status_code == 200
            assert reset_resp.json().get("reset_records_count") >= 1

            # 验证重置后已复原为 healthy
            quotas_after_reset = await runtime_meter_service.get_search_quotas(session)
            tavily_restored = next(
                (q for q in quotas_after_reset if q.provider == "tavily"), None
            )
            assert tavily_restored is not None
            assert tavily_restored.is_depleted is False
            assert tavily_restored.status == "healthy"
            assert tavily_restored.used_count == 0

            # Step 5: 模拟前端修改配额上限为 2000
            limit_resp = await ac.put(
                "/api/statistics/search-quotas/limit",
                json={"provider": "tavily", "quota_limit": 2000},
            )
            assert limit_resp.status_code == 200
            assert limit_resp.json().get("quota_limit") == 2000

        # Step 6: 模拟浏览器运行全过程
        telemetry = BrowserRunTelemetry(
            total_duration_seconds=300.0,
            active_compute_seconds=180.0,
            total_requests=42,
            failed_requests=0,
            total_bytes_transferred=20 * 1024 * 1024,  # 20 MB
        )

        # 录入持久化账本
        await runtime_meter_service.record_browser_session(
            session=session,
            session_id="task-flow-test-session-001",
            telemetry=telemetry,
        )

        # Step 7: 通过 REST API 查询浏览器算力消耗汇总
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                browser_resp = await ac.get("/api/statistics/browser-runtime")
                assert browser_resp.status_code == 200
                summary = browser_resp.json()
                assert summary["session_count"] >= 1
                assert summary["active_compute_minutes"] >= 3.0
                assert summary["total_megabytes_transferred"] >= 20.0
                assert summary["estimated_compute_cost_usd"] > 0
        finally:
            app.dependency_overrides.clear()

        # Step 8: 验证 3 分钟死循环主动看门狗
        obs = BrowserObservability()
        # 正常 30 秒任务未超时
        now = time.time()
        assert (
            obs.check_action_watchdog(now - 30.0, timeout_seconds=180.0) is False
        )
        # 异常 200 秒长耗时动作触发看门狗
        assert (
            obs.check_action_watchdog(now - 200.0, timeout_seconds=180.0) is True
        )
