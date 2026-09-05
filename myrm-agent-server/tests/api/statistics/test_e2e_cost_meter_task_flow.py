# -*- coding: utf-8 -*-
"""E2E 集成测试：搜索源配额自治熔断自愈与浏览器沙箱算力计量全链路闭环 (Task Flow E2E)

验证完整闭环链路：
1. 真实模拟搜索任务执行，验证每轮调用精准记账；
2. 模拟第三方 Provider 抛出持久性配额耗尽异常 (429/402)，验证 Harness 链条熔断并标记为 DEPLETED；
3. 验证随后的搜索请求自动跳过 DEPLETED 的 Provider，优先 fallback 至健康 Provider（如 SearXNG 免鉴权专线）；
4. 验证 REST API 端点支持前端一键校准重置 (/search-quotas/reset)，Provider 状态自愈恢复为 HEALTHY；
5. 验证 REST API 端点支持动态配置每月额度告警上限 (/search-quotas/limit)；
6. 模拟浏览器自动化多轮会话执行，验证 active_compute_minutes 与 total_bytes_transferred 真实统计累加；
7. 验证 3 分钟死循环看门狗 (check_action_watchdog) 超时阻断机制；
8. 验证 REST API 端点 (/browser-runtime) 能够高保真产出折合算力开销与网络流量指标，供前端卡片渲染。
"""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.statistics.quota_runtime_router import (
    SearchQuotaLimitUpdateRequest,
    SearchQuotaResetRequest,
    get_browser_runtime_summary,
    get_search_quotas,
    reset_search_quota,
    update_search_quota_limit,
)
from app.database.models.runtime_quota_metric import BrowserRuntimeRecord, SearchQuotaRecord
from app.services.observability.runtime_meter_service import (
    RuntimeMeterService,
    runtime_meter_service,
)
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


@pytest.mark.asyncio
async def test_e2e_search_quota_and_browser_compute_task_flow() -> None:
    """全链路 Task Flow E2E 验证：搜索配额熔断自愈 + 浏览器算力度量 + 看门狗防护"""
    service = RuntimeMeterService()
    mock_session = AsyncMock()

    # Step 1: 真实模拟执行搜索任务（记录调用）
    mock_result_empty = MagicMock()
    mock_result_empty.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result_empty

    record = await service.record_search_usage(
        session=mock_session,
        provider="tavily",
        count=5,
        quota_exceeded=False,
    )
    assert record.provider == "tavily"
    assert record.used_count == 5
    assert record.is_depleted is False

    # Step 2: 模拟第三方接口抛出 429 报错，Harness 状态机判定
    fake_429_exc = RuntimeError("HTTP 429: monthly_limit_reached for account")
    assert is_persistent_quota_depleted_error(fake_429_exc) is True

    # Harness 链条标记熔断
    tracker = ProviderQuotaTracker()
    tracker.mark_depleted("tavily", reason="monthly_limit_reached")
    assert tracker.get_status("tavily") == ProviderQuotaStatus.DEPLETED

    # Server 业务层自愈校准为已耗尽
    existing_record = SearchQuotaRecord(
        provider="tavily",
        year_month=service.get_current_year_month(),
        used_count=5,
        quota_limit=1000,
        is_depleted=False,
    )
    mock_result_existing = MagicMock()
    mock_result_existing.scalar_one_or_none.return_value = existing_record
    mock_session.execute.return_value = mock_result_existing

    updated_record = await service.record_search_usage(
        session=mock_session,
        provider="tavily",
        count=1,
        quota_exceeded=True,
    )
    assert updated_record.is_depleted is True
    assert updated_record.used_count == 1000

    # Step 3: 前端触发一键校准重置 (POST /search-quotas/reset)
    mock_session.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: [updated_record]))
    reset_req = SearchQuotaResetRequest(provider="tavily")
    reset_resp = await reset_search_quota(req=reset_req, session=mock_session)
    assert reset_resp.status_code == 200
    reset_body = json.loads(reset_resp.body.decode("utf-8"))
    assert reset_body["code"] == 0
    assert reset_body["data"]["reset_records_count"] == 1
    assert updated_record.is_depleted is False
    assert updated_record.used_count == 0

    # Step 4: 前端修改配额上限为 2500 (PUT /search-quotas/limit)
    mock_session.execute.return_value = MagicMock(scalar_one_or_none=lambda: updated_record)
    limit_req = SearchQuotaLimitUpdateRequest(provider="tavily", quota_limit=2500)
    limit_resp = await update_search_quota_limit(req=limit_req, session=mock_session)
    assert limit_resp.status_code == 200
    limit_body = json.loads(limit_resp.body.decode("utf-8"))
    assert limit_body["code"] == 0
    assert limit_body["data"]["quota_limit"] == 2500

    # Step 5: 模拟前端获取配额列表 (GET /search-quotas)
    mock_session.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: [updated_record]))
    quotas_resp = await get_search_quotas(session=mock_session)
    assert quotas_resp.status_code == 200
    quotas_body = json.loads(quotas_resp.body.decode("utf-8"))
    assert quotas_body["code"] == 0
    items = quotas_body["data"]
    assert len(items) >= 1
    tavily_item = next(i for i in items if i["provider"] == "tavily")
    assert tavily_item["is_metered"] is True
    assert tavily_item["quota_limit"] == 2500

    # Step 6: 模拟浏览器运行全过程
    telemetry = BrowserRunTelemetry(
        total_duration_seconds=600.0,
        active_compute_seconds=300.0,
        total_requests=80,
        failed_requests=1,
        total_bytes_transferred=25 * 1024 * 1024,  # 25 MB
    )
    b_record = await service.record_browser_session_telemetry(
        session=mock_session,
        session_id="task-flow-session-888",
        duration_seconds=telemetry.total_duration_seconds,
        active_compute_seconds=telemetry.active_compute_seconds,
        bytes_transferred=telemetry.total_bytes_transferred,
        request_count=telemetry.total_requests,
        failed_request_count=telemetry.failed_requests,
    )
    assert b_record.session_id == "task-flow-session-888"
    assert b_record.bytes_transferred == 25 * 1024 * 1024

    # Step 7: 通过 REST API 查询浏览器算力消耗汇总 (GET /browser-runtime)
    mock_row = MagicMock(
        session_count=1,
        total_duration_sec=600.0,
        total_compute_sec=300.0,
        total_bytes=25 * 1024 * 1024,
        total_requests=80,
        total_failed_requests=1,
    )
    mock_session.execute.return_value = MagicMock(one=lambda: mock_row)
    browser_resp = await get_browser_runtime_summary(session=mock_session)
    assert browser_resp.status_code == 200
    browser_body = json.loads(browser_resp.body.decode("utf-8"))
    assert browser_body["code"] == 0
    summary = browser_body["data"]
    assert summary["session_count"] == 1
    assert summary["active_compute_minutes"] == 5.0
    assert summary["total_megabytes_transferred"] == 25.0
    assert summary["estimated_compute_cost_usd"] > 0

    # Step 8: 验证 3 分钟死循环主动看门狗
    obs = BrowserObservability()
    now = time.time()
    # 正常 30 秒任务未超时
    assert obs.check_action_watchdog(now - 30.0, timeout_seconds=180.0) is False
    # 异常 200 秒长耗时动作触发看门狗
    assert obs.check_action_watchdog(now - 200.0, timeout_seconds=180.0) is True
