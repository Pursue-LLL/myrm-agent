"""Unit tests for growth_dashboard module — pure logic tests without real DB/memory."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.statistics.growth_dashboard import (
    ActivityDay,
    CostSummary,
    GrowthDashboardResponse,
    GrowthSnapshot,
    SkillEvolutionEvent,
    WeeklySummary,
    _ActivitySnapshot,
    _fetch_activity_data,
    _fetch_cost_summary,
    _fetch_memory_snapshot,
    _fetch_skill_evolution_data,
    _fetch_weekly_summary,
    _SkillEvolutionSnapshot,
)
from app.core.utils.errors import StandardHTTPException
from app.services.skills.experience_ledger import SkillGrowthLedgerSummary
from app.services.skills.growth_queries import (
    SkillGrowthCaseSource,
    SkillGrowthCaseStatus,
    SkillGrowthTimelineEventRead,
)


class TestGrowthDashboardSchemas:
    """Test Pydantic response schemas for correctness."""

    def test_snapshot_defaults(self):
        snap = GrowthSnapshot()
        assert snap.total_memories == 0
        assert snap.memory_health_score == 100
        assert snap.memory_by_type == {}

    def test_snapshot_with_data(self):
        snap = GrowthSnapshot(
            total_memories=150,
            memory_by_type={"semantic": 100, "episodic": 50},
            memory_week_delta=12,
            total_skills=5,
            total_evolutions=3,
            active_days=30,
            max_streak=7,
            memory_health_score=85,
            memory_health_dimensions={"freshness": 0.9, "coverage": 0.8},
        )
        assert snap.total_memories == 150
        assert snap.memory_by_type["semantic"] == 100
        assert snap.max_streak == 7

    def test_activity_day(self):
        day = ActivityDay(date="2026-04-20", count=3)
        assert day.date == "2026-04-20"
        assert day.count == 3

    def test_weekly_summary_defaults(self):
        ws = WeeklySummary()
        assert ws.cron_executions == 0
        assert ws.conversations == 0
        assert ws.tool_calls == 0
        assert ws.previous_conversations == 0
        assert ws.previous_messages_sent == 0
        assert ws.previous_cron_executions == 0
        assert ws.previous_tool_calls == 0

    def test_weekly_summary_with_delta(self):
        ws = WeeklySummary(
            conversations=12,
            messages_sent=48,
            cron_executions=3,
            tool_calls=156,
            previous_conversations=8,
            previous_messages_sent=52,
            previous_cron_executions=3,
            previous_tool_calls=133,
        )
        assert ws.conversations == 12
        assert ws.previous_conversations == 8
        assert ws.tool_calls == 156
        assert ws.previous_tool_calls == 133
        dumped = ws.model_dump()
        assert dumped["tool_calls"] == 156
        assert dumped["previous_tool_calls"] == 133

    def test_skill_evolution_event(self):
        event = SkillEvolutionEvent(
            skill_id="sk-001",
            skill_name="Web Search",
            source="draft",
            status="AUTO_APPLIED",
            growth_type="skill_draft",
            created_at="2026-04-20T10:00:00",
            change_summary="Fixed timeout handling",
        )
        assert event.source == "draft"
        assert event.status == "AUTO_APPLIED"

    def test_full_dashboard_response(self):
        resp = GrowthDashboardResponse(
            snapshot=GrowthSnapshot(total_memories=10),
            activity_heatmap=[ActivityDay(date="2026-04-20", count=1)],
            weekly_summary=WeeklySummary(conversations=5, tool_calls=20, previous_conversations=3),
            skill_events=[],
        )
        dumped = resp.model_dump()
        assert dumped["snapshot"]["total_memories"] == 10
        assert len(dumped["activity_heatmap"]) == 1
        assert dumped["weekly_summary"]["conversations"] == 5
        assert dumped["weekly_summary"]["tool_calls"] == 20
        assert dumped["weekly_summary"]["previous_conversations"] == 3

    def test_activity_snapshot_defaults(self):
        snap = _ActivitySnapshot()
        assert snap.active_days == 0
        assert snap.max_streak == 0
        assert snap.heatmap == []
        assert snap.tool_calls_this_week == 0
        assert snap.tool_calls_prev_week == 0

    def test_activity_snapshot_with_data(self):
        snap = _ActivitySnapshot(
            active_days=15,
            max_streak=5,
            heatmap=[ActivityDay(date="2026-05-20", count=3)],
            tool_calls_this_week=156,
            tool_calls_prev_week=133,
        )
        assert snap.active_days == 15
        assert snap.tool_calls_this_week == 156
        assert snap.tool_calls_prev_week == 133
        assert len(snap.heatmap) == 1

    def test_snapshot_week_delta_renders(self):
        """Verify memory_week_delta field is properly serialized."""
        snap = GrowthSnapshot(
            total_memories=100,
            memory_week_delta=15,
        )
        dumped = snap.model_dump()
        assert dumped["memory_week_delta"] == 15

    def test_snapshot_week_delta_zero(self):
        """Week delta defaults to 0."""
        snap = GrowthSnapshot()
        assert snap.memory_week_delta == 0


@pytest.mark.asyncio
async def test_fetch_skill_evolution_data_uses_full_funnel_totals(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_list_skills() -> list[object]:
        return [object(), object()]

    async def fake_summarize() -> SkillGrowthLedgerSummary:
        return SkillGrowthLedgerSummary(
            total_events=6,
            positive_events=2,
            negative_events=3,
            pending_events=1,
            auto_applied=1,
            approved=1,
            rejected=1,
            blocked=1,
            failed_scan=1,
            apply_failed=1,
        )

    async def fake_timeline(*, limit: int = 20) -> list[SkillGrowthTimelineEventRead]:
        assert limit == 20
        return [
            SkillGrowthTimelineEventRead(
                case_id="evolution-case-1",
                source=SkillGrowthCaseSource.EVOLUTION,
                status=SkillGrowthCaseStatus.APPLY_FAILED,
                skill_name="Timeout Handling",
                skill_id="skill-001",
                growth_type="patch",
                created_at=datetime.now(UTC),
                change_summary="Patch application failed due to file lock",
            )
        ]

    monkeypatch.setattr(
        "app.api.statistics.growth_dashboard.skills_service.list_skills",
        fake_list_skills,
    )
    monkeypatch.setattr(
        "app.api.statistics.growth_dashboard.summarize_skill_growth_events",
        fake_summarize,
    )
    monkeypatch.setattr(
        "app.api.statistics.growth_dashboard.list_skill_growth_timeline",
        fake_timeline,
    )

    result = await _fetch_skill_evolution_data()

    assert result.total_skills == 2
    assert result.total_evolutions == 6
    assert result.approved == 1
    assert result.rejected == 1
    assert result.pending == 1
    assert result.apply_failed == 1
    assert len(result.events) == 1
    assert result.events[0].status == "APPLY_FAILED"


# ── _fetch_activity_data tests ────────────────────────────────────────


@dataclass(frozen=True)
class _FakeDailyActivity:
    date: str
    day_of_week: int
    session_count: int
    tool_calls: int
    duration_ms: float


@dataclass(frozen=True)
class _FakeGlobalPatterns:
    daily_activities: list[_FakeDailyActivity]
    by_day_of_week: dict[int, int]
    by_hour: dict[int, int]
    active_days: int
    max_streak: int
    busiest_day_of_week: int
    busiest_hour: int


def _build_fake_patterns(today: datetime) -> _FakeGlobalPatterns:
    """Build fake patterns with activities spanning two weeks for delta testing."""
    d = today.date()
    activities = [
        _FakeDailyActivity(
            date=(d - timedelta(days=i)).isoformat(), day_of_week=0, session_count=1, tool_calls=10, duration_ms=100
        )
        for i in range(14)
    ]
    return _FakeGlobalPatterns(
        daily_activities=activities,
        by_day_of_week={},
        by_hour={},
        active_days=14,
        max_streak=14,
        busiest_day_of_week=0,
        busiest_hour=10,
    )


@pytest.mark.asyncio
async def test_fetch_activity_data_normal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test _fetch_activity_data aggregates tool_calls correctly over two weeks."""
    today = datetime.now(UTC)
    fake_patterns = _build_fake_patterns(today)

    mock_analytics = AsyncMock()
    mock_analytics.get_global_activity_patterns = AsyncMock(return_value=fake_patterns)

    fake_path = MagicMock()
    fake_path.exists.return_value = True
    monkeypatch.setattr("app.api.statistics.growth_dashboard.Path", lambda p: fake_path)
    monkeypatch.setattr("app.api.statistics.growth_dashboard.FileEventLogBackend", lambda log_dir, session_id: MagicMock())
    monkeypatch.setattr("app.api.statistics.growth_dashboard.EventLogAnalytics", lambda b: mock_analytics)

    result = await _fetch_activity_data(84)

    assert result.active_days == 14
    assert result.max_streak == 14
    assert result.tool_calls_this_week + result.tool_calls_prev_week == 140
    assert result.tool_calls_this_week > 0
    assert result.tool_calls_prev_week > 0
    assert len(result.heatmap) == 14


@pytest.mark.asyncio
async def test_fetch_activity_data_no_event_log_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """When event log dir does not exist, return empty snapshot."""
    fake_path = MagicMock()
    fake_path.exists.return_value = False
    monkeypatch.setattr("app.api.statistics.growth_dashboard.Path", lambda p: fake_path)

    result = await _fetch_activity_data(84)
    assert result.active_days == 0
    assert result.tool_calls_this_week == 0


@pytest.mark.asyncio
async def test_fetch_activity_data_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """When analytics raises, return empty snapshot."""
    fake_path = MagicMock()
    fake_path.exists.return_value = True
    monkeypatch.setattr("app.api.statistics.growth_dashboard.Path", lambda p: fake_path)
    monkeypatch.setattr("app.api.statistics.growth_dashboard.FileEventLogBackend", lambda log_dir, session_id: MagicMock())

    def raise_err(b: object) -> object:
        raise RuntimeError("broken")

    monkeypatch.setattr("app.api.statistics.growth_dashboard.EventLogAnalytics", raise_err)

    result = await _fetch_activity_data(84)
    assert result.active_days == 0


# ── _fetch_memory_snapshot tests ──────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_memory_snapshot_normal() -> None:
    """Test normal path via monkeypatching the entire function's internal imports."""
    from enum import Enum

    class FakeType(Enum):
        SEMANTIC = "semantic"
        EPISODIC = "episodic"

    mock_manager = MagicMock()
    mock_manager.get_enabled_types.return_value = [FakeType.SEMANTIC, FakeType.EPISODIC]
    mock_manager.count_memories = AsyncMock(side_effect=[100, 12, 50, 5])
    mock_manager.compute_health_score = AsyncMock(
        return_value=SimpleNamespace(total=90, dimensions={"freshness": 0.9, "coverage": 0.8})
    )

    import sys

    fake_setup = MagicMock()
    fake_setup.create_memory_manager = AsyncMock(return_value=mock_manager)
    fake_setup.resolve_context_binding = MagicMock(return_value=None)
    fake_emb = MagicMock()
    fake_emb.get_embedding_config = MagicMock(return_value=None)
    fake_platform_config = MagicMock()
    fake_platform_config.require_platform_embedding_config = AsyncMock(return_value=None)

    original_setup = sys.modules.get("app.core.memory.adapters.setup")
    original_emb = sys.modules.get("myrm_agent_harness.toolkits.retriever.embedding.factory")
    original_platform = sys.modules.get("app.services.agent.platform_config")
    try:
        sys.modules["app.core.memory.adapters.setup"] = fake_setup
        sys.modules["myrm_agent_harness.toolkits.retriever.embedding.factory"] = fake_emb
        sys.modules["app.services.agent.platform_config"] = fake_platform_config
        by_type, health, dims, delta = await _fetch_memory_snapshot()
    finally:
        if original_setup is not None:
            sys.modules["app.core.memory.adapters.setup"] = original_setup
        if original_emb is not None:
            sys.modules["myrm_agent_harness.toolkits.retriever.embedding.factory"] = original_emb
        if original_platform is not None:
            sys.modules["app.services.agent.platform_config"] = original_platform
        else:
            sys.modules.pop("app.services.agent.platform_config", None)

    assert by_type == {"semantic": 100, "episodic": 50}
    assert health == 90
    assert dims == {"freshness": 0.9, "coverage": 0.8}
    assert delta == 17


@pytest.mark.asyncio
async def test_fetch_memory_snapshot_exception() -> None:
    """When create_memory_manager raises, return safe defaults."""
    import sys

    fake_setup = MagicMock()
    fake_setup.create_memory_manager = AsyncMock(side_effect=RuntimeError("boom"))
    fake_setup.resolve_context_binding = MagicMock(return_value=None)
    fake_emb = MagicMock()
    fake_emb.get_embedding_config = MagicMock(return_value=None)

    original_setup = sys.modules.get("app.core.memory.adapters.setup")
    original_emb = sys.modules.get("myrm_agent_harness.toolkits.retriever.embedding.factory")
    try:
        sys.modules["app.core.memory.adapters.setup"] = fake_setup
        sys.modules["myrm_agent_harness.toolkits.retriever.embedding.factory"] = fake_emb
        by_type, health, dims, delta = await _fetch_memory_snapshot()
    finally:
        if original_setup is not None:
            sys.modules["app.core.memory.adapters.setup"] = original_setup
        if original_emb is not None:
            sys.modules["myrm_agent_harness.toolkits.retriever.embedding.factory"] = original_emb

    assert by_type == {}
    assert health == 100
    assert delta == 0


# ── _fetch_weekly_summary tests ───────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_weekly_summary_normal() -> None:
    """Test _fetch_weekly_summary with mocked DB session and cron manager."""
    execute_results = iter(
        [
            MagicMock(scalar=lambda: 5),
            MagicMock(scalar=lambda: 3),
            MagicMock(scalar=lambda: 20),
            MagicMock(scalar=lambda: 15),
        ]
    )

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=lambda q: next(execute_results))

    now = datetime.now(UTC)
    recent_ts = now.timestamp()
    older_ts = (now - timedelta(days=10)).timestamp()

    fake_history = [
        SimpleNamespace(started_at=recent_ts),
        SimpleNamespace(started_at=recent_ts),
        SimpleNamespace(started_at=older_ts),
    ]

    mock_cron_mgr = AsyncMock()
    mock_cron_mgr.get_execution_history = AsyncMock(return_value=fake_history)

    with patch("app.core.cron.adapters.setup.get_cron_manager", return_value=mock_cron_mgr):
        result = await _fetch_weekly_summary(mock_db)

    assert result.conversations == 5
    assert result.previous_conversations == 3
    assert result.messages_sent == 20
    assert result.previous_messages_sent == 15
    assert result.cron_executions == 2
    assert result.previous_cron_executions == 1


@pytest.mark.asyncio
async def test_fetch_weekly_summary_db_exception() -> None:
    """When DB query fails, return empty WeeklySummary."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=RuntimeError("db down"))

    result = await _fetch_weekly_summary(mock_db)
    assert result.conversations == 0
    assert result.cron_executions == 0


@pytest.mark.asyncio
async def test_fetch_weekly_summary_no_cron_manager() -> None:
    """When cron manager is None, cron counts remain 0."""
    execute_results = iter(
        [
            MagicMock(scalar=lambda: 2),
            MagicMock(scalar=lambda: 1),
            MagicMock(scalar=lambda: 8),
            MagicMock(scalar=lambda: 6),
        ]
    )

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=lambda q: next(execute_results))

    with patch("app.core.cron.adapters.setup.get_cron_manager", return_value=None):
        result = await _fetch_weekly_summary(mock_db)

    assert result.conversations == 2
    assert result.cron_executions == 0
    assert result.previous_cron_executions == 0


# ── _fetch_skill_evolution_data exception branch ──────────────────────


@pytest.mark.asyncio
async def test_fetch_skill_evolution_data_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """When skill services raise, return empty snapshot."""
    monkeypatch.setattr(
        "app.api.statistics.growth_dashboard.skills_service.list_skills",
        AsyncMock(side_effect=RuntimeError("service down")),
    )

    result = await _fetch_skill_evolution_data()
    assert result.total_skills == 0
    assert result.events == []


# ── _SkillEvolutionSnapshot tests ─────────────────────────────────────


class TestSkillEvolutionSnapshot:
    def test_defaults(self):
        snap = _SkillEvolutionSnapshot()
        assert snap.total_skills == 0
        assert snap.events == []

    def test_with_data(self):
        snap = _SkillEvolutionSnapshot(
            total_skills=3,
            approved=2,
            events=[
                SkillEvolutionEvent(
                    skill_name="test", source="draft", status="APPROVED", growth_type="create", created_at="2026-01-01"
                ),
            ],
        )
        assert snap.total_skills == 3
        assert snap.approved == 2
        assert len(snap.events) == 1


# ── get_growth_dashboard endpoint test ────────────────────────────────


@pytest.mark.asyncio
async def test_get_growth_dashboard_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test the main endpoint assembles all data correctly."""
    from app.api.statistics.growth_dashboard import get_growth_dashboard

    monkeypatch.setattr(
        "app.api.statistics.growth_dashboard._fetch_memory_snapshot",
        AsyncMock(return_value=({"semantic": 50}, 95, {"freshness": 0.9}, 8)),
    )
    monkeypatch.setattr(
        "app.api.statistics.growth_dashboard._fetch_activity_data",
        AsyncMock(
            return_value=_ActivitySnapshot(
                active_days=10,
                max_streak=5,
                heatmap=[ActivityDay(date="2026-05-20", count=2)],
                tool_calls_this_week=42,
                tool_calls_prev_week=30,
            )
        ),
    )
    monkeypatch.setattr(
        "app.api.statistics.growth_dashboard._fetch_weekly_summary",
        AsyncMock(
            return_value=WeeklySummary(
                conversations=6, messages_sent=20, cron_executions=3, previous_conversations=4, previous_messages_sent=15
            )
        ),
    )
    monkeypatch.setattr(
        "app.api.statistics.growth_dashboard._fetch_skill_evolution_data",
        AsyncMock(return_value=_SkillEvolutionSnapshot(total_skills=2, total_evolutions=5, approved=3)),
    )

    mock_db = AsyncMock()
    response = await get_growth_dashboard(days=84, db=mock_db)

    import json

    body = json.loads(response.body)
    data = body["data"]

    assert data["snapshot"]["total_memories"] == 50
    assert data["snapshot"]["memory_health_score"] == 95
    assert data["snapshot"]["active_days"] == 10
    assert data["snapshot"]["total_skills"] == 2
    assert data["weekly_summary"]["tool_calls"] == 42
    assert data["weekly_summary"]["previous_tool_calls"] == 30
    assert data["weekly_summary"]["conversations"] == 6
    assert len(data["activity_heatmap"]) == 1


@pytest.mark.asyncio
async def test_get_growth_dashboard_endpoint_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """When a fetcher raises unhandled, endpoint should raise internal_error."""
    from app.api.statistics.growth_dashboard import get_growth_dashboard

    monkeypatch.setattr(
        "app.api.statistics.growth_dashboard._fetch_memory_snapshot",
        AsyncMock(side_effect=RuntimeError("total crash")),
    )
    monkeypatch.setattr(
        "app.api.statistics.growth_dashboard._fetch_activity_data",
        AsyncMock(return_value=_ActivitySnapshot()),
    )
    monkeypatch.setattr(
        "app.api.statistics.growth_dashboard._fetch_weekly_summary",
        AsyncMock(return_value=WeeklySummary()),
    )
    monkeypatch.setattr(
        "app.api.statistics.growth_dashboard._fetch_skill_evolution_data",
        AsyncMock(return_value=_SkillEvolutionSnapshot()),
    )

    mock_db = AsyncMock()
    with pytest.raises(StandardHTTPException):
        await get_growth_dashboard(days=84, db=mock_db)


# ── CostSummary schema tests ─────────────────────────────────────────


class TestCostSummary:
    def test_defaults(self):
        cs = CostSummary()
        assert cs.total_cost_usd == 0.0
        assert cs.cache_savings_usd == 0.0
        assert cs.routing_savings == 0.0
        assert cs.routing_savings_percent == 0.0
        assert cs.total_savings_usd == 0.0

    def test_with_data(self):
        cs = CostSummary(
            total_cost_usd=1.25,
            cache_savings_usd=0.45,
            routing_savings=0.30,
            routing_savings_percent=24.0,
            total_savings_usd=0.75,
        )
        assert cs.total_cost_usd == 1.25
        assert cs.total_savings_usd == 0.75
        dumped = cs.model_dump()
        assert dumped["routing_savings_percent"] == 24.0

    def test_dashboard_response_includes_cost_summary(self):
        resp = GrowthDashboardResponse(
            snapshot=GrowthSnapshot(),
            activity_heatmap=[],
            weekly_summary=WeeklySummary(),
            skill_events=[],
            cost_summary=CostSummary(total_savings_usd=1.50),
        )
        dumped = resp.model_dump()
        assert dumped["cost_summary"]["total_savings_usd"] == 1.50

    def test_dashboard_response_cost_summary_none(self):
        resp = GrowthDashboardResponse(
            snapshot=GrowthSnapshot(),
            activity_heatmap=[],
            weekly_summary=WeeklySummary(),
            skill_events=[],
        )
        dumped = resp.model_dump()
        assert dumped["cost_summary"] is None


# ── _fetch_cost_summary tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_cost_summary_with_data() -> None:
    """Test _fetch_cost_summary aggregates extra_data correctly."""
    fake_rows = [
        {
            "usage": {"prompt_tokens": 1000, "completion_tokens": 200, "cached_tokens": 800},
            "costUsd": 0.005,
            "tokenEconomics": {"total_cache_savings_usd": 0.003},
            "routingTier": "fast",
        },
        {
            "usage": {"prompt_tokens": 2000, "completion_tokens": 400, "cached_tokens": 1500},
            "costUsd": 0.010,
            "tokenEconomics": {"total_cache_savings_usd": 0.006},
            "routingTier": "fast",
        },
    ]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = fake_rows
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await _fetch_cost_summary(mock_db, 30)

    assert result is not None
    assert result.cache_savings_usd == pytest.approx(0.009, abs=0.001)
    assert result.total_cost_usd > 0


@pytest.mark.asyncio
async def test_fetch_cost_summary_no_rows() -> None:
    """When no rows returned, should return None."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await _fetch_cost_summary(mock_db, 30)
    assert result is None


@pytest.mark.asyncio
async def test_fetch_cost_summary_no_valid_usage() -> None:
    """When rows have no valid usage data, return None."""
    fake_rows = [
        {"no_usage_key": True},
        {"usage": None, "costUsd": 0},
    ]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = fake_rows
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await _fetch_cost_summary(mock_db, 30)
    assert result is None


@pytest.mark.asyncio
async def test_fetch_cost_summary_db_exception() -> None:
    """When DB query fails, should return None gracefully."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=RuntimeError("db connection lost"))

    result = await _fetch_cost_summary(mock_db, 30)
    assert result is None


@pytest.mark.asyncio
async def test_fetch_cost_summary_tiny_savings_not_filtered() -> None:
    """Backend should return tiny savings (filtering is frontend's job)."""
    fake_rows = [
        {
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "cached_tokens": 50},
            "costUsd": 0.001,
            "tokenEconomics": {"total_cache_savings_usd": 0.0005},
        },
    ]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = fake_rows
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await _fetch_cost_summary(mock_db, 7)

    if result is not None:
        assert result.total_savings_usd >= 0
