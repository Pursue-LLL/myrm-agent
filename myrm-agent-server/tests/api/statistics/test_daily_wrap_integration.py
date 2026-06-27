"""Integration tests for /statistics/daily-wrap endpoints.

Tests the full HTTP request-response cycle using a minimal FastAPI app
with real routing and real database caching. The data fetchers are mocked
at the boundary to supply controlled activity data, while all other paths
(routing, JSON parsing, DB cache read/write, response formatting) are real.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from tests.support.minimal_app import build_minimal_app


@pytest.fixture()
def app():
    return build_minimal_app(preset="statistics")


@pytest.fixture()
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _patch_fetchers(sessions=None, approvals=None, cron_runs=None, kanban_events=None):
    """Patch data fetchers to return controlled data."""
    return (
        patch("app.api.statistics.daily_wrap._fetch_sessions", new_callable=AsyncMock, return_value=sessions or []),
        patch("app.api.statistics.daily_wrap._fetch_approvals", new_callable=AsyncMock, return_value=approvals or []),
        patch("app.api.statistics.daily_wrap._fetch_cron_runs", new_callable=AsyncMock, return_value=cron_runs or []),
        patch("app.api.statistics.daily_wrap._fetch_kanban_events", new_callable=AsyncMock, return_value=kanban_events or []),
    )


def _patch_llm_success(summary: str = "Good day", keywords: list[str] | None = None, suggestions: list[str] | None = None):
    """Patch LLM pipeline to return valid JSON response."""
    kw = keywords or ["test"]
    sg = suggestions or ["keep it up"]

    mock_configs = MagicMock()
    mock_configs.providers_dict = {"mock": "provider"}

    mock_lite_cfg = MagicMock()
    mock_lite_cfg.model = "gpt-4o-mini"
    mock_lite_cfg.base_url = None
    mock_lite_cfg.api_key = "sk-test"

    llm_response = MagicMock()
    llm_response.content = json.dumps({"summary": summary, "keywords": kw, "suggestions": sg})

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=llm_response)

    return (
        patch("app.core.channel_bridge.config_loader.load_user_configs", new_callable=AsyncMock, return_value=mock_configs),
        patch("app.core.channel_bridge.config_parsers.extract_lite_model_config", return_value=mock_lite_cfg),
        patch("myrm_agent_harness.toolkits.llms.create_litellm_model", return_value=mock_llm),
    )


def _patch_llm_not_configured():
    """Patch to simulate LITE_MODEL not configured."""
    mock_configs = MagicMock()
    mock_configs.providers_dict = None
    return patch("app.core.channel_bridge.config_loader.load_user_configs", new_callable=AsyncMock, return_value=mock_configs)


SAMPLE_SESSIONS = [
    {"title": "Code Review", "action_mode": "chat", "total_tokens": 5000, "total_usd": 0.01},
    {"title": "Bug Fix", "action_mode": "agent", "total_tokens": 3000, "total_usd": 0.005},
]

SAMPLE_APPROVALS = [{"action_type": "file_write", "status": "approved"}]


class TestDailyWrapGetEndpoint:
    """GET /api/v1/statistics/daily-wrap"""

    @pytest.mark.asyncio
    async def test_no_activity_returns_null_summary(self, client: AsyncClient):
        """Empty activity data should return reason='no_activity'."""
        fetchers = _patch_fetchers()
        with fetchers[0], fetchers[1], fetchers[2], fetchers[3]:
            resp = await client.get("/api/v1/statistics/daily-wrap", params={"date": "2026-06-27"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["date"] == "2026-06-27"
        assert data["summary"] is None
        assert data["reason"] == "no_activity"

    @pytest.mark.asyncio
    async def test_lite_model_not_configured(self, client: AsyncClient):
        """Activity exists but no LITE_MODEL returns reason='lite_model_not_configured'."""
        fetchers = _patch_fetchers(sessions=SAMPLE_SESSIONS)
        with fetchers[0], fetchers[1], fetchers[2], fetchers[3], _patch_llm_not_configured():
            resp = await client.get("/api/v1/statistics/daily-wrap", params={"date": "2026-06-27"})

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["reason"] == "lite_model_not_configured"
        assert data["summary"] is None

    @pytest.mark.asyncio
    async def test_full_generation_flow(self, client: AsyncClient):
        """Full flow: fetches activity → LLM generates → returns summary."""
        fetchers = _patch_fetchers(sessions=SAMPLE_SESSIONS, approvals=SAMPLE_APPROVALS)
        llm = _patch_llm_success(summary="Productive day", keywords=["review", "bugfix"], suggestions=["merge PRs"])

        with fetchers[0], fetchers[1], fetchers[2], fetchers[3], llm[0], llm[1], llm[2]:
            resp = await client.get("/api/v1/statistics/daily-wrap", params={"date": "2026-06-20"})

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["summary"] == "Productive day"
        assert data["keywords"] == ["review", "bugfix"]
        assert data["suggestions"] == ["merge PRs"]
        assert data["cached"] is False
        assert data["generated_at"] is not None

    @pytest.mark.asyncio
    async def test_cached_response_on_second_call(self, client: AsyncClient):
        """Second GET should return cached result without calling LLM."""
        fetchers = _patch_fetchers(sessions=SAMPLE_SESSIONS)
        llm = _patch_llm_success(summary="Cached day")

        with fetchers[0], fetchers[1], fetchers[2], fetchers[3], llm[0], llm[1], llm[2]:
            await client.get("/api/v1/statistics/daily-wrap", params={"date": "2026-06-19"})

        resp2 = await client.get("/api/v1/statistics/daily-wrap", params={"date": "2026-06-19"})
        assert resp2.status_code == 200
        data2 = resp2.json()["data"]
        assert data2["cached"] is True
        assert data2["summary"] == "Cached day"

    @pytest.mark.asyncio
    async def test_missing_date_param_returns_error(self, client: AsyncClient):
        """Missing required 'date' param should return 422."""
        resp = await client.get("/api/v1/statistics/daily-wrap")
        assert resp.status_code == 422


class TestDailyWrapRegenerateEndpoint:
    """POST /api/v1/statistics/daily-wrap/regenerate"""

    @pytest.mark.asyncio
    async def test_regenerate_overwrites_cache(self, client: AsyncClient):
        """Regenerate produces fresh data and updates cache."""
        fetchers = _patch_fetchers(sessions=SAMPLE_SESSIONS)
        llm1 = _patch_llm_success(summary="Version 1")

        with fetchers[0], fetchers[1], fetchers[2], fetchers[3], llm1[0], llm1[1], llm1[2]:
            resp1 = await client.get("/api/v1/statistics/daily-wrap", params={"date": "2026-06-18"})
        assert resp1.json()["data"]["summary"] == "Version 1"

        fetchers2 = _patch_fetchers(sessions=SAMPLE_SESSIONS)
        llm2 = _patch_llm_success(summary="Version 2 Regenerated")

        with fetchers2[0], fetchers2[1], fetchers2[2], fetchers2[3], llm2[0], llm2[1], llm2[2]:
            resp2 = await client.post("/api/v1/statistics/daily-wrap/regenerate", params={"date": "2026-06-18"})

        assert resp2.status_code == 200
        assert resp2.json()["data"]["summary"] == "Version 2 Regenerated"

        resp3 = await client.get("/api/v1/statistics/daily-wrap", params={"date": "2026-06-18"})
        assert resp3.json()["data"]["cached"] is True
        assert resp3.json()["data"]["summary"] == "Version 2 Regenerated"

    @pytest.mark.asyncio
    async def test_regenerate_no_activity(self, client: AsyncClient):
        """Regenerate with no activity returns reason='no_activity'."""
        fetchers = _patch_fetchers()
        with fetchers[0], fetchers[1], fetchers[2], fetchers[3]:
            resp = await client.post("/api/v1/statistics/daily-wrap/regenerate", params={"date": "2020-01-01"})

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["reason"] == "no_activity"

    @pytest.mark.asyncio
    async def test_regenerate_missing_date_returns_error(self, client: AsyncClient):
        """Missing required 'date' param should return 422."""
        resp = await client.post("/api/v1/statistics/daily-wrap/regenerate")
        assert resp.status_code == 422


class TestDailyWrapEdgeCases:
    """Edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_only_approvals_triggers_generation(self, client: AsyncClient):
        """Activity with only approvals (no sessions) should still generate."""
        fetchers = _patch_fetchers(approvals=SAMPLE_APPROVALS)
        llm = _patch_llm_success(summary="Approvals only day")

        with fetchers[0], fetchers[1], fetchers[2], fetchers[3], llm[0], llm[1], llm[2]:
            resp = await client.get("/api/v1/statistics/daily-wrap", params={"date": "2026-06-15"})

        assert resp.status_code == 200
        assert resp.json()["data"]["summary"] == "Approvals only day"

    @pytest.mark.asyncio
    async def test_only_cron_runs_triggers_generation(self, client: AsyncClient):
        """Activity with only cron runs should still trigger LLM."""
        cron = [{"job_id": "backup-daily", "status": "completed"}]
        fetchers = _patch_fetchers(cron_runs=cron)
        llm = _patch_llm_success(summary="Cron only day")

        with fetchers[0], fetchers[1], fetchers[2], fetchers[3], llm[0], llm[1], llm[2]:
            resp = await client.get("/api/v1/statistics/daily-wrap", params={"date": "2026-06-14"})

        assert resp.status_code == 200
        assert resp.json()["data"]["summary"] == "Cron only day"

    @pytest.mark.asyncio
    async def test_only_kanban_events_triggers_generation(self, client: AsyncClient):
        """Activity with only kanban events should still trigger LLM."""
        kanban = [{"task_id": "T-999", "kind": "completed"}]
        fetchers = _patch_fetchers(kanban_events=kanban)
        llm = _patch_llm_success(summary="Kanban only day")

        with fetchers[0], fetchers[1], fetchers[2], fetchers[3], llm[0], llm[1], llm[2]:
            resp = await client.get("/api/v1/statistics/daily-wrap", params={"date": "2026-06-13"})

        assert resp.status_code == 200
        assert resp.json()["data"]["summary"] == "Kanban only day"

    @pytest.mark.asyncio
    async def test_llm_exception_returns_500(self, client: AsyncClient):
        """LLM call raising exception should return a 500 error response."""
        fetchers = _patch_fetchers(sessions=SAMPLE_SESSIONS)

        mock_configs = MagicMock()
        mock_configs.providers_dict = {"mock": "provider"}
        mock_lite_cfg = MagicMock()
        mock_lite_cfg.model = "gpt-4o-mini"
        mock_lite_cfg.base_url = None
        mock_lite_cfg.api_key = "sk-test"

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        with (
            fetchers[0], fetchers[1], fetchers[2], fetchers[3],
            patch("app.core.channel_bridge.config_loader.load_user_configs", new_callable=AsyncMock, return_value=mock_configs),
            patch("app.core.channel_bridge.config_parsers.extract_lite_model_config", return_value=mock_lite_cfg),
            patch("myrm_agent_harness.toolkits.llms.create_litellm_model", return_value=mock_llm),
        ):
            resp = await client.get("/api/v1/statistics/daily-wrap", params={"date": "2026-06-12"})

        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_llm_non_json_response_graceful_degradation(self, client: AsyncClient):
        """LLM returning plain text (not JSON) should degrade gracefully."""
        fetchers = _patch_fetchers(sessions=SAMPLE_SESSIONS)

        mock_configs = MagicMock()
        mock_configs.providers_dict = {"mock": "provider"}
        mock_lite_cfg = MagicMock()
        mock_lite_cfg.model = "gpt-4o-mini"
        mock_lite_cfg.base_url = None
        mock_lite_cfg.api_key = "sk-test"

        llm_response = MagicMock()
        llm_response.content = "Today was productive. Reviewed 3 PRs and fixed 2 bugs."

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=llm_response)

        with (
            fetchers[0], fetchers[1], fetchers[2], fetchers[3],
            patch("app.core.channel_bridge.config_loader.load_user_configs", new_callable=AsyncMock, return_value=mock_configs),
            patch("app.core.channel_bridge.config_parsers.extract_lite_model_config", return_value=mock_lite_cfg),
            patch("myrm_agent_harness.toolkits.llms.create_litellm_model", return_value=mock_llm),
        ):
            resp = await client.get("/api/v1/statistics/daily-wrap", params={"date": "2026-06-11"})

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["summary"] == "Today was productive. Reviewed 3 PRs and fixed 2 bugs."
        assert data["keywords"] == []
        assert data["suggestions"] == []

    @pytest.mark.asyncio
    async def test_cache_isolation_between_dates(self, client: AsyncClient):
        """Different dates have independent caches."""
        fetchers1 = _patch_fetchers(sessions=SAMPLE_SESSIONS)
        llm1 = _patch_llm_success(summary="Day A summary")
        with fetchers1[0], fetchers1[1], fetchers1[2], fetchers1[3], llm1[0], llm1[1], llm1[2]:
            await client.get("/api/v1/statistics/daily-wrap", params={"date": "2026-06-01"})

        fetchers2 = _patch_fetchers(sessions=SAMPLE_SESSIONS)
        llm2 = _patch_llm_success(summary="Day B summary")
        with fetchers2[0], fetchers2[1], fetchers2[2], fetchers2[3], llm2[0], llm2[1], llm2[2]:
            await client.get("/api/v1/statistics/daily-wrap", params={"date": "2026-06-02"})

        resp_a = await client.get("/api/v1/statistics/daily-wrap", params={"date": "2026-06-01"})
        resp_b = await client.get("/api/v1/statistics/daily-wrap", params={"date": "2026-06-02"})

        assert resp_a.json()["data"]["summary"] == "Day A summary"
        assert resp_b.json()["data"]["summary"] == "Day B summary"

    @pytest.mark.asyncio
    async def test_future_date_no_activity(self, client: AsyncClient):
        """Future date should return no_activity (no data exists yet)."""
        fetchers = _patch_fetchers()
        with fetchers[0], fetchers[1], fetchers[2], fetchers[3]:
            resp = await client.get("/api/v1/statistics/daily-wrap", params={"date": "2030-12-31"})

        assert resp.status_code == 200
        assert resp.json()["data"]["reason"] == "no_activity"

    @pytest.mark.asyncio
    async def test_response_structure_completeness(self, client: AsyncClient):
        """Verify all expected fields are present in successful response."""
        fetchers = _patch_fetchers(sessions=SAMPLE_SESSIONS)
        llm = _patch_llm_success()
        with fetchers[0], fetchers[1], fetchers[2], fetchers[3], llm[0], llm[1], llm[2]:
            resp = await client.get("/api/v1/statistics/daily-wrap", params={"date": "2026-06-10"})

        data = resp.json()["data"]
        required_fields = {"date", "summary", "keywords", "suggestions", "generated_at", "cached"}
        assert required_fields.issubset(set(data.keys()))
        assert isinstance(data["keywords"], list)
        assert isinstance(data["suggestions"], list)
