"""Unit and integration tests for runtime search quota and browser compute telemetry."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.statistics.quota_runtime_router import (
    BrowserRuntimeRecordRequest,
    SearchQuotaLimitUpdateRequest,
    SearchQuotaRecordRequest,
    SearchQuotaResetRequest,
    get_browser_runtime_summary,
    get_runtime_cost_gauge,
    get_search_quotas,
    record_browser_runtime,
    record_search_quota,
    reset_search_quota,
    update_search_quota_limit,
)
from app.database.models.runtime_quota_metric import SearchQuotaRecord
from app.services.observability.runtime_meter_service import (
    RuntimeMeterService,
)


class TestRuntimeMeterService:
    """Test RuntimeMeterService in-memory logic and DB interactions."""

    @pytest.mark.asyncio
    async def test_record_search_usage_normal_and_self_healing(self) -> None:
        service = RuntimeMeterService()
        mock_session = AsyncMock()

        # 1. First search: no existing record -> create record
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
        assert record.quota_limit == 1000

        # 2. 429 received: triggers self-healing recalibration
        existing_record = SearchQuotaRecord(
            provider="tavily",
            year_month=service.get_current_year_month(),
            used_count=400,
            quota_limit=1000,
            is_depleted=False,
        )
        mock_result_existing = MagicMock()
        mock_result_existing.scalar_one_or_none.return_value = existing_record
        mock_session.execute.return_value = mock_result_existing

        updated = await service.record_search_usage(
            session=mock_session,
            provider="tavily",
            count=1,
            quota_exceeded=True,
        )

        assert updated.is_depleted is True
        assert updated.used_count == 1000  # Automatically calibrated to limit
        assert updated.last_depleted_at is not None

    @pytest.mark.asyncio
    async def test_get_search_quotas_classification(self) -> None:
        service = RuntimeMeterService()
        mock_session = AsyncMock()

        mock_record_tavily = SearchQuotaRecord(
            provider="tavily",
            year_month=service.get_current_year_month(),
            used_count=850,
            quota_limit=1000,
            is_depleted=False,
        )
        mock_record_brave = SearchQuotaRecord(
            provider="brave",
            year_month=service.get_current_year_month(),
            used_count=2000,
            quota_limit=2000,
            is_depleted=True,
        )

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_record_tavily, mock_record_brave]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        quotas = await service.get_search_quotas(mock_session)
        assert len(quotas) >= 2

        tavily_entry = next(q for q in quotas if q["provider"] == "tavily")
        assert tavily_entry["used_count"] == 850
        assert tavily_entry["status"] == "warning"  # 85% >= 80%

        brave_entry = next(q for q in quotas if q["provider"] == "brave")
        assert brave_entry["status"] == "depleted"

    @pytest.mark.asyncio
    async def test_browser_runtime_recording_and_summary(self) -> None:
        service = RuntimeMeterService()
        mock_session = AsyncMock()

        row = MagicMock()
        row.session_count = 3
        row.total_duration_sec = 600.0  # 10 minutes
        row.total_compute_sec = 300.0   # 5 minutes
        row.total_bytes = 10 * 1024 * 1024  # 10 MB
        row.total_requests = 45
        row.total_failed_requests = 2

        mock_result = MagicMock()
        mock_result.one.return_value = row
        mock_session.execute.return_value = mock_result

        summary = await service.get_browser_runtime_summary(mock_session)
        assert summary["session_count"] == 3
        assert summary["total_duration_minutes"] == 10.0
        assert summary["active_compute_minutes"] == 5.0
        assert summary["total_megabytes_transferred"] == 10.0
        assert summary["total_requests"] == 45
        assert summary["total_failed_requests"] == 2
        assert summary["estimated_compute_cost_usd"] == round(5.0 * 0.001, 4)

    @pytest.mark.asyncio
    async def test_runtime_burn_rate_gauge_calculation(self) -> None:
        service = RuntimeMeterService()
        mock_session = AsyncMock()

        # Mock search quotas
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_res_search = MagicMock()
        mock_res_search.scalars.return_value = mock_scalars

        # Mock browser summary
        row = MagicMock()
        row.session_count = 2
        row.total_duration_sec = 120.0
        row.total_compute_sec = 60.0
        row.total_bytes = 2048
        row.total_requests = 10
        row.total_failed_requests = 0
        mock_res_browser = MagicMock()
        mock_res_browser.one.return_value = row

        mock_session.execute.side_effect = [mock_res_search, mock_res_browser]

        gauge = await service.get_runtime_burn_rate_gauge(mock_session)
        assert gauge["overall_search_health"] == "healthy"
        assert gauge["is_burn_rate_alert"] is False
        assert "burn_rate_message" in gauge


class TestQuotaRuntimeRouterEndpoints:
    """Test API endpoint handlers."""

    @pytest.mark.asyncio
    async def test_get_search_quotas_endpoint(self) -> None:
        mock_session = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        response = await get_search_quotas(session=mock_session)
        assert response.status_code == 200
        data = json.loads(response.body)
        assert data["code"] == 0
        assert isinstance(data["data"], list)

    @pytest.mark.asyncio
    async def test_record_search_quota_endpoint(self) -> None:
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        req = SearchQuotaRecordRequest(provider="tavily", count=2, quota_exceeded=False)
        response = await record_search_quota(req=req, session=mock_session)
        assert response.status_code == 200
        data = json.loads(response.body)
        assert data["code"] == 0
        assert data["data"]["provider"] == "tavily"
        assert data["data"]["used_count"] == 2

    @pytest.mark.asyncio
    async def test_get_browser_runtime_summary_endpoint(self) -> None:
        mock_session = AsyncMock()
        row = MagicMock()
        row.session_count = 1
        row.total_duration_sec = 60.0
        row.total_compute_sec = 30.0
        row.total_bytes = 1048576
        row.total_requests = 5
        row.total_failed_requests = 0

        mock_result = MagicMock()
        mock_result.one.return_value = row
        mock_session.execute.return_value = mock_result

        response = await get_browser_runtime_summary(session=mock_session)
        assert response.status_code == 200
        data = json.loads(response.body)
        assert data["code"] == 0
        assert data["data"]["session_count"] == 1
        assert data["data"]["total_megabytes_transferred"] == 1.0

    @pytest.mark.asyncio
    async def test_record_browser_runtime_endpoint(self) -> None:
        mock_session = AsyncMock()
        req = BrowserRuntimeRecordRequest(
            session_id="test-session-123",
            duration_seconds=12.5,
            active_compute_seconds=8.0,
            bytes_transferred=2048,
            request_count=4,
            failed_request_count=0,
        )
        response = await record_browser_runtime(req=req, session=mock_session)
        assert response.status_code == 200
        data = json.loads(response.body)
        assert data["code"] == 0
        assert "year_month" in data["data"]

    @pytest.mark.asyncio
    async def test_get_runtime_cost_gauge_endpoint(self) -> None:
        mock_session = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_res_search = MagicMock()
        mock_res_search.scalars.return_value = mock_scalars

        row = MagicMock()
        row.session_count = 0
        row.total_duration_sec = 0.0
        row.total_compute_sec = 0.0
        row.total_bytes = 0
        row.total_requests = 0
        row.total_failed_requests = 0
        mock_res_browser = MagicMock()
        mock_res_browser.one.return_value = row

        mock_session.execute.side_effect = [mock_res_search, mock_res_browser]

        response = await get_runtime_cost_gauge(session=mock_session)
        assert response.status_code == 200
        data = json.loads(response.body)
        assert data["code"] == 0
        assert "overall_search_health" in data["data"]
        assert "burn_rate_message" in data["data"]

    @pytest.mark.asyncio
    async def test_reset_and_update_limit_endpoints(self) -> None:
        mock_session = AsyncMock()

        # Test reset
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_res = MagicMock()
        mock_res.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_res

        reset_req = SearchQuotaResetRequest(provider="brave")
        resp_reset = await reset_search_quota(req=reset_req, session=mock_session)
        assert resp_reset.status_code == 200
        data_reset = json.loads(resp_reset.body)
        assert data_reset["code"] == 0
        assert data_reset["data"]["provider"] == "brave"

        # Test update limit with fresh mock session
        mock_session_update = AsyncMock()
        mock_res_empty = MagicMock()
        mock_res_empty.scalar_one_or_none.return_value = None
        mock_session_update.execute.return_value = mock_res_empty

        limit_req = SearchQuotaLimitUpdateRequest(provider="brave", quota_limit=5000)
        resp_limit = await update_search_quota_limit(req=limit_req, session=mock_session_update)
        assert resp_limit.status_code == 200
        data_limit = json.loads(resp_limit.body)
        assert data_limit["code"] == 0
        assert data_limit["data"]["quota_limit"] == 5000

    @pytest.mark.asyncio
    async def test_full_task_flow_e2e_closed_loop(self) -> None:
        """全链路真实业务闭环 Task Flow E2E:
        1. 验证搜索调用记账与配额正常扣减；
        2. 触发持久性 429 报错时自愈重锚定为 DEPLETED；
        3. 前端触发重置校准，自愈复位状态为 HEALTHY；
        4. 前端修改配额告警阈值；
        5. 浏览器会话时长、请求数、原生带宽度量累加与费用折算；
        6. 3 分钟死循环看门狗超时阻断校验。
        """
        import time

        from myrm_agent_harness.toolkits.browser.observability import (
            BrowserObservability,
            BrowserRunTelemetry,
            RecordingConfig,
        )
        from myrm_agent_harness.toolkits.web_search.core.error_handling import (
            is_persistent_quota_depleted_error,
        )
        from myrm_agent_harness.toolkits.web_search.providers.chain import (
            ProviderQuotaStatus,
            ProviderQuotaTracker,
        )

        service = RuntimeMeterService()
        mock_session = AsyncMock()

        # Step 1: 正常记录搜索
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

        # Step 2: 模拟 429 配额耗尽
        fake_429 = RuntimeError("HTTP 429: monthly_limit_reached for account")
        assert is_persistent_quota_depleted_error(fake_429) is True

        tracker = ProviderQuotaTracker()
        tracker.mark_depleted("tavily", reason="monthly_limit_reached")
        status, reason = tracker.get_status("tavily")
        assert status == ProviderQuotaStatus.DEPLETED
        assert reason == "monthly_limit_reached"

        # Server 标记为耗尽
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

        # Step 3: 前端一键重置
        mock_session.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: [updated_record]))
        reset_req = SearchQuotaResetRequest(provider="tavily")
        reset_resp = await reset_search_quota(req=reset_req, session=mock_session)
        assert reset_resp.status_code == 200
        reset_data = json.loads(reset_resp.body)
        assert reset_data["code"] == 0
        assert updated_record.is_depleted is False
        assert updated_record.used_count == 0

        # Step 4: 前端调整上限
        mock_session.execute.return_value = MagicMock(scalar_one_or_none=lambda: updated_record)
        limit_req = SearchQuotaLimitUpdateRequest(provider="tavily", quota_limit=2500)
        limit_resp = await update_search_quota_limit(req=limit_req, session=mock_session)
        assert limit_resp.status_code == 200
        limit_data = json.loads(limit_resp.body)
        assert limit_data["code"] == 0
        assert limit_data["data"]["quota_limit"] == 2500

        # Step 5: 前端查询配额
        mock_session.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: [updated_record]))
        quotas_resp = await get_search_quotas(session=mock_session)
        assert quotas_resp.status_code == 200
        quotas_data = json.loads(quotas_resp.body)
        tavily_item = next(i for i in quotas_data["data"] if i["provider"] == "tavily")
        assert tavily_item["is_metered"] is True
        assert tavily_item["quota_limit"] == 2500

        # Step 6: 浏览器度量与看门狗
        telemetry = BrowserRunTelemetry(
            start_time=time.time() - 600.0,
            active_compute_seconds=300.0,
            request_count=80,
            failed_request_count=1,
            total_bytes_transferred=25 * 1024 * 1024,
        )
        assert telemetry.active_compute_seconds == 300.0
        assert telemetry.total_bytes_transferred == 25 * 1024 * 1024

        obs = BrowserObservability(recording_config=RecordingConfig())
        mono_now = time.monotonic()
        assert obs.check_action_watchdog(mono_now - 30.0, timeout_seconds=180.0) is True
        assert obs.check_action_watchdog(mono_now - 200.0, timeout_seconds=180.0) is False
        assert obs.telemetry.watchdog_tripped_count == 1
