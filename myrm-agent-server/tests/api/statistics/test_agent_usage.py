"""Unit tests for agent_usage module — pure logic tests with mocked DB."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.statistics.agent_usage import get_usage_by_agent


def _make_totals_row(agent_id: str, tokens: int, usd: float, calls: int, sessions: int):
    return SimpleNamespace(agent_id=agent_id, tokens=tokens, usd=usd, calls=calls, sessions=sessions)


def _make_agent_row(id: str, name: str, avatar: str | None = None):
    return SimpleNamespace(id=id, name=name, avatar=avatar)


def _make_daily_row(agent_id: str, day: str, tokens: int, usd: float):
    return SimpleNamespace(agent_id=agent_id, day=day, tokens=tokens, usd=usd)


class TestGetUsageByAgent:
    """Test GET /usage/by-agent endpoint logic."""

    @pytest.mark.asyncio
    async def test_empty_data_returns_empty_agents(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        response = await get_usage_by_agent(days=7, db=mock_db)
        data = response.body
        import json
        parsed = json.loads(data)
        assert parsed["data"]["agents"] == []
        assert parsed["data"]["total_agents"] == 0

    @pytest.mark.asyncio
    async def test_single_agent_returns_correct_data(self):
        mock_db = AsyncMock()

        totals_result = MagicMock()
        totals_result.all.return_value = [
            _make_totals_row("agent-1", 1000, 0.05, 10, 5),
        ]

        agents_result = MagicMock()
        agents_result.all.return_value = [
            _make_agent_row("agent-1", "Research Assistant", "https://avatar.url/1.png"),
        ]

        daily_result = MagicMock()
        daily_result.all.return_value = [
            _make_daily_row("agent-1", "2026-06-03", 200, 0.01),
            _make_daily_row("agent-1", "2026-06-04", 300, 0.015),
        ]

        mock_db.execute.side_effect = [totals_result, agents_result, daily_result]

        response = await get_usage_by_agent(days=7, db=mock_db)
        import json
        parsed = json.loads(response.body)
        data = parsed["data"]

        assert data["total_agents"] == 1
        assert len(data["agents"]) == 1

        agent = data["agents"][0]
        assert agent["agentId"] == "agent-1"
        assert agent["name"] == "Research Assistant"
        assert agent["avatar"] == "https://avatar.url/1.png"
        assert agent["totalTokens"] == 1000
        assert agent["totalUsd"] == 0.05
        assert agent["totalCalls"] == 10
        assert agent["sessions"] == 5
        assert agent["percentTokens"] == 100.0
        assert agent["percentUsd"] == 100.0
        assert len(agent["sparkline"]) == 7

    @pytest.mark.asyncio
    async def test_multiple_agents_sorted_by_usd_desc(self):
        mock_db = AsyncMock()

        totals_result = MagicMock()
        totals_result.all.return_value = [
            _make_totals_row("agent-cheap", 500, 0.01, 5, 2),
            _make_totals_row("agent-expensive", 2000, 0.10, 20, 8),
        ]

        agents_result = MagicMock()
        agents_result.all.return_value = [
            _make_agent_row("agent-cheap", "Translator"),
            _make_agent_row("agent-expensive", "Researcher"),
        ]

        daily_result = MagicMock()
        daily_result.all.return_value = []

        mock_db.execute.side_effect = [totals_result, agents_result, daily_result]

        response = await get_usage_by_agent(days=7, db=mock_db)
        import json
        parsed = json.loads(response.body)
        agents = parsed["data"]["agents"]

        assert len(agents) == 2
        assert agents[0]["agentId"] == "agent-expensive"
        assert agents[1]["agentId"] == "agent-cheap"
        assert agents[0]["totalUsd"] > agents[1]["totalUsd"]

    @pytest.mark.asyncio
    async def test_percentage_calculation(self):
        mock_db = AsyncMock()

        totals_result = MagicMock()
        totals_result.all.return_value = [
            _make_totals_row("a1", 750, 0.075, 10, 3),
            _make_totals_row("a2", 250, 0.025, 5, 2),
        ]

        agents_result = MagicMock()
        agents_result.all.return_value = [
            _make_agent_row("a1", "Agent A"),
            _make_agent_row("a2", "Agent B"),
        ]

        daily_result = MagicMock()
        daily_result.all.return_value = []

        mock_db.execute.side_effect = [totals_result, agents_result, daily_result]

        response = await get_usage_by_agent(days=7, db=mock_db)
        import json
        parsed = json.loads(response.body)
        agents = parsed["data"]["agents"]

        assert agents[0]["percentTokens"] == 75.0
        assert agents[0]["percentUsd"] == 75.0
        assert agents[1]["percentTokens"] == 25.0
        assert agents[1]["percentUsd"] == 25.0

    @pytest.mark.asyncio
    async def test_deleted_agent_fallback(self):
        mock_db = AsyncMock()

        totals_result = MagicMock()
        totals_result.all.return_value = [
            _make_totals_row("deleted-id", 500, 0.02, 3, 1),
        ]

        agents_result = MagicMock()
        agents_result.all.return_value = []

        daily_result = MagicMock()
        daily_result.all.return_value = []

        mock_db.execute.side_effect = [totals_result, agents_result, daily_result]

        response = await get_usage_by_agent(days=7, db=mock_db)
        import json
        parsed = json.loads(response.body)
        agent = parsed["data"]["agents"][0]

        assert agent["name"] == "deleted-id"
        assert agent["avatar"] is None

    @pytest.mark.asyncio
    async def test_null_values_handled_safely(self):
        mock_db = AsyncMock()

        totals_result = MagicMock()
        totals_result.all.return_value = [
            _make_totals_row("a1", None, None, None, None),
        ]

        agents_result = MagicMock()
        agents_result.all.return_value = [
            _make_agent_row("a1", "Test Agent"),
        ]

        daily_result = MagicMock()
        daily_result.all.return_value = []

        mock_db.execute.side_effect = [totals_result, agents_result, daily_result]

        response = await get_usage_by_agent(days=7, db=mock_db)
        import json
        parsed = json.loads(response.body)
        agent = parsed["data"]["agents"][0]

        assert agent["totalTokens"] == 0
        assert agent["totalUsd"] == 0.0
        assert agent["totalCalls"] == 0
        assert agent["sessions"] == 0

    @pytest.mark.asyncio
    async def test_sparkline_has_correct_days_count(self):
        mock_db = AsyncMock()

        totals_result = MagicMock()
        totals_result.all.return_value = [
            _make_totals_row("a1", 1000, 0.05, 10, 5),
        ]

        agents_result = MagicMock()
        agents_result.all.return_value = [
            _make_agent_row("a1", "Agent"),
        ]

        daily_result = MagicMock()
        daily_result.all.return_value = []

        mock_db.execute.side_effect = [totals_result, agents_result, daily_result]

        response = await get_usage_by_agent(days=14, db=mock_db)
        import json
        parsed = json.loads(response.body)
        sparkline = parsed["data"]["agents"][0]["sparkline"]

        assert len(sparkline) == 14

    @pytest.mark.asyncio
    async def test_grand_totals_in_response(self):
        mock_db = AsyncMock()

        totals_result = MagicMock()
        totals_result.all.return_value = [
            _make_totals_row("a1", 600, 0.03, 6, 3),
            _make_totals_row("a2", 400, 0.02, 4, 2),
        ]

        agents_result = MagicMock()
        agents_result.all.return_value = [
            _make_agent_row("a1", "A"),
            _make_agent_row("a2", "B"),
        ]

        daily_result = MagicMock()
        daily_result.all.return_value = []

        mock_db.execute.side_effect = [totals_result, agents_result, daily_result]

        response = await get_usage_by_agent(days=7, db=mock_db)
        import json
        parsed = json.loads(response.body)
        data = parsed["data"]

        assert data["grand_total_tokens"] == 1000
        assert data["grand_total_usd"] == 0.05
