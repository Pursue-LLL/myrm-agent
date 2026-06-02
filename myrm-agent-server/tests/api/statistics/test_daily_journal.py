"""Unit tests for daily_journal module — pure logic + mock DB tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.statistics.daily_journal import (
    _build_source_breakdown,
    _build_timeline,
    _parse_day,
)
from app.core.utils.errors import StandardHTTPException


class TestParseDay:
    def test_valid_date(self):
        start, end = _parse_day("2026-05-20")
        assert start == datetime(2026, 5, 20, tzinfo=UTC)
        assert end == datetime(2026, 5, 21, tzinfo=UTC)
        assert (end - start) == timedelta(days=1)

    def test_invalid_format_raises(self):
        with pytest.raises(StandardHTTPException):
            _parse_day("20-05-2026")

    def test_invalid_date_raises(self):
        with pytest.raises(StandardHTTPException):
            _parse_day("not-a-date")

    def test_leap_year(self):
        start, end = _parse_day("2024-02-29")
        assert start.day == 29
        assert end.day == 1
        assert end.month == 3


class TestBuildTimeline:
    def test_empty_inputs(self):
        result = _build_timeline([], [], [], [])
        assert result == []

    def test_sessions_only(self):
        sessions = [
            {"started_at": "2026-05-20T10:00:00", "chat_id": "c1", "title": "Test", "action_mode": "chat", "total_tokens": 100},
        ]
        result = _build_timeline(sessions, [], [], [])
        assert len(result) == 1
        assert result[0]["type"] == "session"
        assert result[0]["title"] == "Test"

    def test_mixed_types_sorted_by_time(self):
        sessions = [{"started_at": "2026-05-20T14:00:00", "chat_id": "c1", "title": "Late session", "action_mode": "chat", "total_tokens": 0}]
        approvals = [{"created_at": "2026-05-20T09:00:00", "id": "a1", "action_type": "bash", "status": "approved", "severity": "high"}]
        cron_runs = [{"started_at": "2026-05-20T12:00:00", "id": "cr1", "job_id": "heartbeat", "status": "success", "duration_ms": 500}]
        kanban_events = [{"created_at": "2026-05-20T11:00:00", "id": 1, "task_id": "t1", "kind": "created"}]

        result = _build_timeline(sessions, approvals, cron_runs, kanban_events)
        assert len(result) == 4
        types_in_order = [r["type"] for r in result]
        assert types_in_order == ["approval", "kanban", "cron_run", "session"]

    def test_null_time_sorted_to_end(self):
        """FIX 2 verification: events without time go to end of timeline."""
        sessions = [{"started_at": "2026-05-20T08:00:00", "chat_id": "c1", "title": "Morning", "action_mode": "chat", "total_tokens": 0}]
        kanban_events = [{"created_at": None, "id": 1, "task_id": "t1", "kind": "created"}]

        result = _build_timeline(sessions, [], [], kanban_events)
        assert len(result) == 2
        assert result[0]["type"] == "session"
        assert result[1]["type"] == "kanban"
        assert result[1]["time"] is None

    def test_multiple_null_times_at_end(self):
        sessions = [{"started_at": "2026-05-20T10:00:00", "chat_id": "c1", "title": "S1", "action_mode": "chat", "total_tokens": 0}]
        approvals = [{"created_at": None, "id": "a1", "action_type": "bash", "status": "pending", "severity": "low"}]
        kanban_events = [{"created_at": None, "id": 1, "task_id": "t1", "kind": "created"}]

        result = _build_timeline(sessions, approvals, [], kanban_events)
        assert len(result) == 3
        assert result[0]["type"] == "session"
        assert result[1]["time"] is None
        assert result[2]["time"] is None


class TestBuildSourceBreakdown:
    def test_empty_sessions(self):
        assert _build_source_breakdown([]) == {}

    def test_single_source(self):
        sessions = [{"source": "web"}, {"source": "web"}]
        result = _build_source_breakdown(sessions)
        assert result == {"web": 2}

    def test_multiple_sources(self):
        sessions = [{"source": "web"}, {"source": "api"}, {"source": "web"}, {"source": "wechat"}]
        result = _build_source_breakdown(sessions)
        assert result == {"web": 2, "api": 1, "wechat": 1}

    def test_none_source_becomes_unknown(self):
        sessions = [{"source": None}]
        result = _build_source_breakdown(sessions)
        assert result == {"unknown": 1}

    def test_missing_source_key(self):
        sessions = [{}]
        result = _build_source_breakdown(sessions)
        assert result == {"unknown": 1}


class TestFetchToolCallCountDynamicDays:
    """FIX 1 verification: days_ago is computed dynamically."""

    @pytest.mark.asyncio
    async def test_recent_date_uses_minimum_2(self):
        from app.api.statistics.daily_journal import _fetch_tool_call_count

        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

        mock_activity = MagicMock()
        mock_activity.date = today.strftime("%Y-%m-%d")
        mock_activity.tool_calls = 42

        mock_patterns = MagicMock()
        mock_patterns.daily_activities = [mock_activity]

        mock_analytics = AsyncMock()
        mock_analytics.get_global_activity_patterns = AsyncMock(return_value=mock_patterns)

        mock_backend_cls = MagicMock()

        with (
            patch("app.api.statistics.daily_journal.settings") as mock_settings,
            patch("app.api.statistics.daily_journal.Path") as mock_path,
            patch.dict("sys.modules", {
                "myrm_agent_harness.agent.event_log": MagicMock(EventLogAnalytics=MagicMock(return_value=mock_analytics)),
                "myrm_agent_harness.agent.event_log.backends.file_backend": MagicMock(FileEventLogBackend=mock_backend_cls),
            }),
        ):
            mock_settings.database.event_log_dir = "/tmp/test"
            mock_path.return_value.exists.return_value = True

            result = await _fetch_tool_call_count(today, today + timedelta(days=1))

            assert result == 42
            call_args = mock_analytics.get_global_activity_patterns.call_args
            assert call_args.kwargs["time_range_days"] >= 2

    @pytest.mark.asyncio
    async def test_old_date_uses_large_days_ago(self):
        from app.api.statistics.daily_journal import _fetch_tool_call_count

        old_date = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=30)

        mock_activity = MagicMock()
        mock_activity.date = old_date.strftime("%Y-%m-%d")
        mock_activity.tool_calls = 99

        mock_patterns = MagicMock()
        mock_patterns.daily_activities = [mock_activity]

        mock_analytics = AsyncMock()
        mock_analytics.get_global_activity_patterns = AsyncMock(return_value=mock_patterns)

        mock_backend_cls = MagicMock()

        with (
            patch("app.api.statistics.daily_journal.settings") as mock_settings,
            patch("app.api.statistics.daily_journal.Path") as mock_path,
            patch.dict("sys.modules", {
                "myrm_agent_harness.agent.event_log": MagicMock(EventLogAnalytics=MagicMock(return_value=mock_analytics)),
                "myrm_agent_harness.agent.event_log.backends.file_backend": MagicMock(FileEventLogBackend=mock_backend_cls),
            }),
        ):
            mock_settings.database.event_log_dir = "/tmp/test"
            mock_path.return_value.exists.return_value = True

            result = await _fetch_tool_call_count(old_date, old_date + timedelta(days=1))

            assert result == 99
            call_args = mock_analytics.get_global_activity_patterns.call_args
            assert call_args.kwargs["time_range_days"] >= 31

    @pytest.mark.asyncio
    async def test_missing_event_log_dir_returns_zero(self):
        from app.api.statistics.daily_journal import _fetch_tool_call_count

        today = datetime.now(UTC)

        with (
            patch("app.api.statistics.daily_journal.settings") as mock_settings,
            patch("app.api.statistics.daily_journal.Path") as mock_path,
        ):
            mock_settings.database.event_log_dir = "/nonexistent"
            mock_path.return_value.exists.return_value = False

            result = await _fetch_tool_call_count(today, today + timedelta(days=1))
            assert result == 0

    @pytest.mark.asyncio
    async def test_exception_returns_zero(self):
        from app.api.statistics.daily_journal import _fetch_tool_call_count

        today = datetime.now(UTC)

        with (
            patch("app.api.statistics.daily_journal.settings") as mock_settings,
            patch("app.api.statistics.daily_journal.Path") as mock_path,
            patch.dict("sys.modules", {
                "myrm_agent_harness.agent.event_log": MagicMock(EventLogAnalytics=MagicMock(side_effect=RuntimeError("boom"))),
                "myrm_agent_harness.agent.event_log.backends.file_backend": MagicMock(FileEventLogBackend=MagicMock()),
            }),
        ):
            mock_settings.database.event_log_dir = "/tmp/test"
            mock_path.return_value.exists.return_value = True

            result = await _fetch_tool_call_count(today, today + timedelta(days=1))
            assert result == 0

    @pytest.mark.asyncio
    async def test_date_not_in_activities_returns_zero(self):
        from app.api.statistics.daily_journal import _fetch_tool_call_count

        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

        mock_activity = MagicMock()
        mock_activity.date = "1999-01-01"
        mock_activity.tool_calls = 42

        mock_patterns = MagicMock()
        mock_patterns.daily_activities = [mock_activity]

        mock_analytics = AsyncMock()
        mock_analytics.get_global_activity_patterns = AsyncMock(return_value=mock_patterns)

        mock_backend_cls = MagicMock()

        with (
            patch("app.api.statistics.daily_journal.settings") as mock_settings,
            patch("app.api.statistics.daily_journal.Path") as mock_path,
            patch.dict("sys.modules", {
                "myrm_agent_harness.agent.event_log": MagicMock(EventLogAnalytics=MagicMock(return_value=mock_analytics)),
                "myrm_agent_harness.agent.event_log.backends.file_backend": MagicMock(FileEventLogBackend=mock_backend_cls),
            }),
        ):
            mock_settings.database.event_log_dir = "/tmp/test"
            mock_path.return_value.exists.return_value = True

            result = await _fetch_tool_call_count(today, today + timedelta(days=1))
            assert result == 0


class TestGetDailyJournalEndpoint:
    """Integration tests for the main endpoint using mock DB."""

    @pytest.mark.asyncio
    async def test_valid_date_returns_success(self):
        from app.api.statistics.daily_journal import get_daily_journal

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.api.statistics.daily_journal._fetch_tool_call_count", new_callable=AsyncMock, return_value=0):
            response = await get_daily_journal(date="2026-05-20", agent_id=None, db=mock_db)

        import json

        body = json.loads(response.body)
        assert body["code"] == 0
        data = body["data"]
        assert data["date"] == "2026-05-20"
        assert data["overview"]["total_sessions"] == 0
        assert data["overview"]["total_tokens"] == 0
        assert data["overview"]["total_cost_usd"] == 0
        assert data["timeline"] == []

    @pytest.mark.asyncio
    async def test_invalid_date_raises(self):
        from app.api.statistics.daily_journal import get_daily_journal

        mock_db = AsyncMock()

        with pytest.raises(StandardHTTPException):
            await get_daily_journal(date="not-valid", agent_id=None, db=mock_db)

    @pytest.mark.asyncio
    async def test_with_sessions_aggregates_tokens(self):
        from app.api.statistics.daily_journal import get_daily_journal

        chat_row = (
            "chat-1", "Test Chat", "chat", "web", None,
            datetime(2026, 5, 20, 10, 0, 0, tzinfo=UTC),
            500, 0.01, 3,
        )

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.all.return_value = [chat_row]
            elif call_count == 2:
                result.all.return_value = [("chat-1", 5)]
            else:
                result.all.return_value = []
            return result

        mock_db = AsyncMock()
        mock_db.execute = mock_execute

        with patch("app.api.statistics.daily_journal._fetch_tool_call_count", new_callable=AsyncMock, return_value=10):
            response = await get_daily_journal(date="2026-05-20", agent_id=None, db=mock_db)

        import json

        body = json.loads(response.body)
        data = body["data"]
        assert data["overview"]["total_sessions"] == 1
        assert data["overview"]["total_tokens"] == 500
        assert data["overview"]["total_tool_calls"] == 10
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["title"] == "Test Chat"
        assert data["sessions"][0]["message_count"] == 5
        assert len(data["timeline"]) == 1
        assert data["timeline"][0]["type"] == "session"

    @pytest.mark.asyncio
    async def test_source_breakdown_computed(self):
        from app.api.statistics.daily_journal import get_daily_journal

        rows = [
            ("c1", "Chat 1", "chat", "web", None, datetime(2026, 5, 20, 10, tzinfo=UTC), 100, 0.01, 1),
            ("c2", "Chat 2", "chat", "api", None, datetime(2026, 5, 20, 11, tzinfo=UTC), 200, 0.02, 2),
            ("c3", "Chat 3", "chat", "web", None, datetime(2026, 5, 20, 12, tzinfo=UTC), 300, 0.03, 3),
        ]

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.all.return_value = rows
            elif call_count == 2:
                result.all.return_value = []
            else:
                result.all.return_value = []
            return result

        mock_db = AsyncMock()
        mock_db.execute = mock_execute

        with patch("app.api.statistics.daily_journal._fetch_tool_call_count", new_callable=AsyncMock, return_value=0):
            response = await get_daily_journal(date="2026-05-20", agent_id=None, db=mock_db)

        import json

        body = json.loads(response.body)
        data = body["data"]
        assert data["overview"]["sessions_by_source"]["web"] == 2
        assert data["overview"]["sessions_by_source"]["api"] == 1
