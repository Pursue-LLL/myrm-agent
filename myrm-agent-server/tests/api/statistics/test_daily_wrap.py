"""Unit tests for daily_wrap module — pure logic + mock tests."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.statistics.daily_wrap import (
    _build_activity_prompt,
    _generate_wrap_via_llm,
)
from app.database.models.daily_wrap import DailyWrapCache


class TestBuildActivityPrompt:
    def test_empty_data(self):
        prompt = _build_activity_prompt("2026-06-20", [], [], [], [])
        assert "2026-06-20" in prompt
        assert "Sessions: 0" in prompt

    def test_sessions_included(self):
        sessions = [
            {"title": "Code Review", "action_mode": "chat", "total_tokens": 5000, "total_usd": 0.01},
            {"title": "Bug Fix", "action_mode": "agent", "total_tokens": 3000, "total_usd": 0.005},
        ]
        prompt = _build_activity_prompt("2026-06-20", sessions, [], [], [])
        assert "Sessions: 2" in prompt
        assert "Code Review" in prompt
        assert "Bug Fix" in prompt
        assert "8,000" in prompt

    def test_approvals_included(self):
        approvals = [
            {"action_type": "file_write", "status": "approved"},
        ]
        prompt = _build_activity_prompt("2026-06-20", [], approvals, [], [])
        assert "Approvals: 1" in prompt
        assert "file_write" in prompt

    def test_cron_runs_included(self):
        cron_runs = [
            {"job_id": "backup", "status": "completed"},
        ]
        prompt = _build_activity_prompt("2026-06-20", [], [], cron_runs, [])
        assert "Scheduled tasks: 1" in prompt
        assert "backup" in prompt

    def test_kanban_events_included(self):
        kanban = [
            {"task_id": "T-123", "kind": "completed"},
        ]
        prompt = _build_activity_prompt("2026-06-20", [], [], [], kanban)
        assert "Kanban events: 1" in prompt
        assert "T-123" in prompt

    def test_max_sessions_capped(self):
        sessions = [
            {"title": f"Session {i}", "action_mode": "chat", "total_tokens": 100, "total_usd": 0.001}
            for i in range(20)
        ]
        prompt = _build_activity_prompt("2026-06-20", sessions, [], [], [])
        assert "Session 14" in prompt
        assert "Session 15" not in prompt


class TestGenerateWrapViaLlm:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_lite_model(self):
        mock_configs = MagicMock()
        mock_configs.providers_dict = None

        with patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new_callable=AsyncMock,
            return_value=mock_configs,
        ):
            result = await _generate_wrap_via_llm("2026-06-20", [], [], [], [])
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_parsed_json_on_success(self):
        mock_configs = MagicMock()
        mock_configs.providers_dict = {"some": "config"}

        mock_lite_cfg = MagicMock()
        mock_lite_cfg.model = "gpt-4o-mini"
        mock_lite_cfg.base_url = None
        mock_lite_cfg.api_key = "test-key"

        llm_response = MagicMock()
        llm_response.content = json.dumps({
            "summary": "Productive day with 5 sessions focused on code review.",
            "keywords": ["code-review", "refactoring", "testing"],
            "suggestions": ["Follow up on PR #42", "Review test coverage"],
        })

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=llm_response)

        with (
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=mock_configs,
            ),
            patch(
                "app.core.channel_bridge.config_parsers.extract_lite_model_config",
                return_value=mock_lite_cfg,
            ),
            patch(
                "myrm_agent_harness.toolkits.llms.create_litellm_model",
                return_value=mock_llm,
            ),
        ):
            sessions = [{"title": "Review", "action_mode": "chat", "total_tokens": 5000, "total_usd": 0.01}]
            result = await _generate_wrap_via_llm("2026-06-20", sessions, [], [], [])

            assert result is not None
            assert result["summary"] == "Productive day with 5 sessions focused on code review."
            assert len(result["keywords"]) == 3
            assert len(result["suggestions"]) == 2

    @pytest.mark.asyncio
    async def test_handles_non_json_response_gracefully(self):
        mock_configs = MagicMock()
        mock_configs.providers_dict = {"some": "config"}

        mock_lite_cfg = MagicMock()
        mock_lite_cfg.model = "gpt-4o-mini"
        mock_lite_cfg.base_url = None
        mock_lite_cfg.api_key = "test-key"

        llm_response = MagicMock()
        llm_response.content = "This is just a plain text summary without JSON."

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=llm_response)

        with (
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=mock_configs,
            ),
            patch(
                "app.core.channel_bridge.config_parsers.extract_lite_model_config",
                return_value=mock_lite_cfg,
            ),
            patch(
                "myrm_agent_harness.toolkits.llms.create_litellm_model",
                return_value=mock_llm,
            ),
        ):
            result = await _generate_wrap_via_llm("2026-06-20", [], [], [], [])

            assert result is not None
            assert result["summary"] == "This is just a plain text summary without JSON."
            assert result["keywords"] == []
            assert result["suggestions"] == []

    @pytest.mark.asyncio
    async def test_handles_markdown_wrapped_json(self):
        mock_configs = MagicMock()
        mock_configs.providers_dict = {"some": "config"}

        mock_lite_cfg = MagicMock()
        mock_lite_cfg.model = "gpt-4o-mini"
        mock_lite_cfg.base_url = None
        mock_lite_cfg.api_key = "test-key"

        llm_response = MagicMock()
        llm_response.content = '```json\n{"summary": "Good day", "keywords": ["test"], "suggestions": []}\n```'

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=llm_response)

        with (
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=mock_configs,
            ),
            patch(
                "app.core.channel_bridge.config_parsers.extract_lite_model_config",
                return_value=mock_lite_cfg,
            ),
            patch(
                "myrm_agent_harness.toolkits.llms.create_litellm_model",
                return_value=mock_llm,
            ),
        ):
            result = await _generate_wrap_via_llm("2026-06-20", [], [], [], [])

            assert result is not None
            assert result["summary"] == "Good day"
            assert result["keywords"] == ["test"]


class TestDailyWrapCacheModel:
    def test_table_name(self):
        assert DailyWrapCache.__tablename__ == "daily_wrap_cache"

    def test_primary_key_is_date(self):
        pk_cols = [c.name for c in DailyWrapCache.__table__.primary_key.columns]
        assert pk_cols == ["date"]
