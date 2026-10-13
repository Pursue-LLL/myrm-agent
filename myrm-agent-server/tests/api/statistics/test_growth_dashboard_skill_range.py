"""The growth dashboard's range selector is the window of the skill trend panel, through the real HTTP route."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.statistics.growth_dashboard import WeeklySummary, _ActivitySnapshot
from app.api.statistics.skill_growth import SkillEvolutionSnapshot, SkillTrendPoint, SkillTrendSeries
from app.database.connection import get_db
from tests.support.minimal_app import build_minimal_app


@pytest.fixture
async def dashboard_client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[AsyncClient, AsyncMock]]:
    """The route with every panel but the skill trends stubbed; yields the client and the trends fetcher."""
    module = "app.api.statistics.growth_dashboard"
    trends = AsyncMock(return_value=[])
    for name, value in {
        "_fetch_memory_snapshot": ({}, 100, {}, 0),
        "_fetch_activity_data": _ActivitySnapshot(),
        "_fetch_weekly_summary": WeeklySummary(),
        "fetch_skill_evolution_data": SkillEvolutionSnapshot(),
        "_fetch_cost_summary": None,
        "fetch_skill_health": [],
        "_fetch_memory_citations_7d": 0,
    }.items():
        monkeypatch.setattr(f"{module}.{name}", AsyncMock(return_value=value))
    monkeypatch.setattr(f"{module}.fetch_skill_trends", trends)

    app = build_minimal_app(preset="statistics")
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, trends


@pytest.mark.asyncio
@pytest.mark.parametrize("days", [7, 30, 90])
async def test_selected_range_is_the_trend_window(dashboard_client: tuple[AsyncClient, AsyncMock], days: int) -> None:
    client, trends = dashboard_client

    response = await client.get(f"/api/v1/statistics/growth-dashboard?days={days}")

    assert response.status_code == 200
    trends.assert_awaited_once()
    assert trends.await_args.args[0] == days


@pytest.mark.asyncio
async def test_truncation_flag_reaches_the_client(dashboard_client: tuple[AsyncClient, AsyncMock]) -> None:
    client, trends = dashboard_client
    point = SkillTrendPoint(date="2026-10-12", success_rate=1.0, observed_count=3, call_count=3)
    trends.return_value = [SkillTrendSeries(skill_name="hourly-job", data_points=[point], truncated=True)]

    response = await client.get("/api/v1/statistics/growth-dashboard?days=30")

    (series,) = response.json()["data"]["skill_trends"]
    assert series["truncated"] is True
