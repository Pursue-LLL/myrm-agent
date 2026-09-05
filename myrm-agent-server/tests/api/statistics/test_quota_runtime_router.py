"""Unit and integration tests for runtime search quota and browser compute telemetry."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.statistics.quota_runtime_router import (
    BrowserRuntimeRecordRequest,
    SearchQuotaRecordRequest,
    get_browser_runtime_summary,
    get_search_quotas,
    record_browser_runtime,
    record_search_quota,
)
from app.database.models.runtime_quota_metric import BrowserRuntimeRecord, SearchQuotaRecord
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
        data = json.loads(response.body)
        assert data["code"] == 200
        assert isinstance(data["data"], list)

    @pytest.mark.asyncio
    async def test_record_search_quota_endpoint(self) -> None:
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        req = SearchQuotaRecordRequest(provider="tavily", count=2, quota_exceeded=False)
        response = await record_search_quota(req=req, session=mock_session)
        data = json.loads(response.body)
        assert data["code"] == 200
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
        data = json.loads(response.body)
        assert data["code"] == 200
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
        data = json.loads(response.body)
        assert data["code"] == 200
        assert "year_month" in data["data"]
