"""Unit and integration tests for user local timezone bucketing in statistics endpoints.

[INPUT]
- app.api.statistics.timezone_helper::resolve_user_timezone, to_user_local_dt
- app.api.statistics.daily_journal::_parse_day
- app.api.statistics.router::router as statistics_router

[OUTPUT]
- Pytest test cases validating timezone resolution, boundary conversion, and endpoint responses

[POS]
- tests/api/statistics/test_statistics_timezone.py: Test suite for item 59 (Timezone-Aware Statistics)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.statistics.daily_journal import _parse_day
from app.api.statistics.router import router as statistics_router
from app.api.statistics.timezone_helper import resolve_user_timezone, to_user_local_dt

test_app = FastAPI()
test_app.include_router(statistics_router, prefix="/api/v1/statistics")


class TestTimezoneHelper:
    def test_resolve_user_timezone_none_or_empty(self) -> None:
        tz_info, tz_name = resolve_user_timezone(None, None)
        assert tz_info == UTC
        assert tz_name == "UTC"

        tz_info, tz_name = resolve_user_timezone("   ", "")
        assert tz_info == UTC
        assert tz_name == "UTC"

    def test_resolve_user_timezone_valid_query(self) -> None:
        tz_info, tz_name = resolve_user_timezone("Asia/Shanghai", None)
        assert tz_name == "Asia/Shanghai"
        assert isinstance(tz_info, ZoneInfo)
        assert tz_info.key == "Asia/Shanghai"

    def test_resolve_user_timezone_header_fallback(self) -> None:
        tz_info, tz_name = resolve_user_timezone(None, "America/New_York")
        assert tz_name == "America/New_York"
        assert isinstance(tz_info, ZoneInfo)
        assert tz_info.key == "America/New_York"

    def test_resolve_user_timezone_query_precedence_over_header(self) -> None:
        tz_info, tz_name = resolve_user_timezone("Europe/London", "Asia/Tokyo")
        assert tz_name == "Europe/London"
        assert tz_info.key == "Europe/London"

    def test_resolve_user_timezone_invalid_safe_fallback(self) -> None:
        tz_info, tz_name = resolve_user_timezone("Invalid/Non_Existent_TZ", None)
        assert tz_info == UTC
        assert tz_name == "UTC"


class TestDatetimeConversion:
    def test_to_user_local_dt_none(self) -> None:
        assert to_user_local_dt(None, UTC) is None

    def test_to_user_local_dt_naive_assumes_utc(self) -> None:
        # 16:30 naive UTC -> 00:30 next day in Asia/Shanghai
        shanghai = ZoneInfo("Asia/Shanghai")
        naive_utc = datetime(2026, 10, 12, 16, 30, 0)
        local_dt = to_user_local_dt(naive_utc, shanghai)
        assert local_dt is not None
        assert local_dt.year == 2026
        assert local_dt.month == 10
        assert local_dt.day == 13
        assert local_dt.hour == 0
        assert local_dt.minute == 30

    def test_parse_day_with_user_timezone(self) -> None:
        shanghai = ZoneInfo("Asia/Shanghai")
        day_start_utc, day_end_utc = _parse_day("2026-10-12", shanghai)
        # 2026-10-12 00:00 Shanghai is 2026-10-11 16:00 UTC
        assert day_start_utc == datetime(2026, 10, 11, 16, 0, 0, tzinfo=UTC)
        # 2026-10-13 00:00 Shanghai is 2026-10-12 16:00 UTC
        assert day_end_utc == datetime(2026, 10, 12, 16, 0, 0, tzinfo=UTC)
        assert (day_end_utc - day_start_utc) == timedelta(days=1)


@pytest.mark.asyncio
async def test_api_activity_endpoint_returns_timezone() -> None:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test with query timezone
        resp = await client.get("/api/v1/statistics/activity?timezone=Asia/Shanghai")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["timezone"] == "Asia/Shanghai"

        # Test with header timezone
        resp_hdr = await client.get(
            "/api/v1/statistics/activity",
            headers={"X-Timezone": "America/New_York"},
        )
        assert resp_hdr.status_code == 200
        data_hdr = resp_hdr.json()["data"]
        assert data_hdr["timezone"] == "America/New_York"

        # Test with default timezone
        resp_def = await client.get("/api/v1/statistics/activity")
        assert resp_def.status_code == 200
        data_def = resp_def.json()["data"]
        assert data_def["timezone"] == "UTC"


@pytest.mark.asyncio
async def test_api_daily_usage_endpoint_with_mocked_db() -> None:
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()

    # 16:30 UTC created_at message with token usage
    utc_time = datetime(2026, 10, 12, 16, 30, 0, tzinfo=UTC)
    extra_data = {
        "usage": {
            "total_tokens": 100,
            "prompt_tokens": 80,
            "completion_tokens": 20,
        }
    }
    mock_row = MagicMock()
    mock_row.extra_data = extra_data
    mock_row.created_at = utc_time

    mock_result = MagicMock()
    mock_result.all.return_value = [(extra_data, utc_time)]
    mock_db.execute.return_value = mock_result

    from app.database.connection import get_db

    test_app.dependency_overrides[get_db] = lambda: mock_db

    try:
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Query with Asia/Shanghai: 16:30 UTC belongs to 2026-10-13 locally!
            resp = await client.get("/api/v1/statistics/usage/daily?days=7&timezone=Asia/Shanghai")
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["timezone"] == "Asia/Shanghai"
            assert len(data["daily"]) == 1
            assert data["daily"][0]["date"] == "2026-10-13"

            # Query with UTC: belongs to 2026-10-12
            resp_utc = await client.get("/api/v1/statistics/usage/daily?days=7&timezone=UTC")
            assert resp_utc.status_code == 200
            data_utc = resp_utc.json()["data"]
            assert data_utc["timezone"] == "UTC"
            assert len(data_utc["daily"]) == 1
            assert data_utc["daily"][0]["date"] == "2026-10-12"
    finally:
        test_app.dependency_overrides.pop(get_db, None)
