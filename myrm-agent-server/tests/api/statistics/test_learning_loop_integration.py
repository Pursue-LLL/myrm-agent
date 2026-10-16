"""Unit and integration tests for /statistics/learning-loop/status endpoint."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import create_autospec, patch

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.agent.event_log.types import DailyActivity, GlobalActivityPatterns
from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryType

from app.api.statistics.learning_loop import (
    LearningLoopFiveRingStatusResponse,
    Ring1ReflectionStatus,
    Ring2DistillationStatus,
    Ring3AdvancementStatus,
    Ring4ConsolidationStatus,
    Ring5ProfilingStatus,
)
from app.config.settings import settings
from app.services.memory.command_center.command_center_memory_scan import ALL_MEMORY_TYPES
from app.services.memory.manager_deps import get_crud_memory_manager
from tests.support.minimal_app import build_minimal_app


class TestLearningLoopSchemas:
    """Validate Pydantic models for learning loop status."""

    def test_schema_defaults(self):
        resp = LearningLoopFiveRingStatusResponse(
            ring1_reflection=Ring1ReflectionStatus(),
            ring2_distillation=Ring2DistillationStatus(),
            ring3_advancement=Ring3AdvancementStatus(),
            ring4_consolidation=Ring4ConsolidationStatus(),
            ring5_profiling=Ring5ProfilingStatus(),
        )
        assert resp.overall_loop_health_score == 100
        assert resp.overall_status == "optimal"
        assert resp.ring1_reflection.is_active is True
        assert resp.ring2_distillation.total_active_skills == 0
        assert resp.ring3_advancement.regressions_blocked == 0
        assert resp.ring4_consolidation.memory_health_score == 100
        assert resp.ring5_profiling.cross_session_recall_ready is True


@pytest.fixture()
def app():
    return build_minimal_app(preset="statistics")


@pytest.fixture()
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


STATUS_URL = "/api/v1/statistics/learning-loop/status?days=30"
MEMORIES_PER_TYPE = 2


def _activity_patterns(*session_counts: int) -> GlobalActivityPatterns:
    return GlobalActivityPatterns(
        daily_activities=[
            DailyActivity(
                date=f"2026-08-{20 + index}",
                day_of_week=index,
                session_count=count,
                tool_calls=count * 3,
                duration_ms=1000.0,
            )
            for index, count in enumerate(session_counts)
        ],
        by_day_of_week={},
        by_hour={},
        active_days=len(session_counts),
        max_streak=len(session_counts),
        busiest_day_of_week=0,
        busiest_hour=0,
    )


@pytest.fixture()
def event_log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An existing event-log directory registered as the server's canonical one."""
    monkeypatch.setattr(settings.database, "event_log_dir", str(tmp_path))
    return tmp_path


@pytest.fixture()
def memory_manager(app):
    """Signature-enforcing manager double: a drifted ``MemoryManager`` call fails the test."""
    manager = create_autospec(MemoryManager, instance=True)
    manager.count_memories.return_value = MEMORIES_PER_TYPE
    app.dependency_overrides[get_crud_memory_manager] = lambda: manager
    return manager


@pytest.fixture()
def skill_sources():
    """Autospec'd skill catalog and growth timeline, so call-signature drift fails the test."""
    with (
        patch(
            "app.api.statistics.learning_loop.skills_service.list_skills",
            autospec=True,
            return_value=[SimpleNamespace(id="skill-1", name="deploy_app")],
        ) as list_skills,
        patch(
            "app.api.statistics.learning_loop.list_skill_growth_timeline",
            autospec=True,
            return_value=[
                SimpleNamespace(status="approved", created_at="2026-08-20T10:00:00Z"),
                SimpleNamespace(status="pending", created_at="2026-08-20T11:00:00Z"),
            ],
        ),
    ):
        yield list_skills


@pytest.mark.asyncio
class TestLearningLoopIntegration:
    """Full HTTP routing integration tests for learning loop status."""

    async def test_status_aggregates_every_ring_from_its_source(self, client, event_log_dir, memory_manager, skill_sources):
        with patch(
            "app.api.statistics.learning_loop.EventLogAnalytics.get_global_activity_patterns",
            autospec=True,
            return_value=_activity_patterns(2, 3),
        ) as patterns:
            resp = await client.get(STATUS_URL)

        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        payload = data["data"]

        patterns.assert_awaited_once()
        assert patterns.await_args.kwargs == {"time_range_days": 30}
        assert payload["ring1_reflection"]["total_traces_analyzed"] == 5
        assert payload["ring1_reflection"]["status"] == "active"
        assert payload["ring2_distillation"]["total_active_skills"] == 1
        assert payload["ring2_distillation"]["proposals_approved"] == 1
        assert payload["ring2_distillation"]["proposals_pending"] == 1
        assert payload["ring4_consolidation"]["total_memories"] == MEMORIES_PER_TYPE * len(ALL_MEMORY_TYPES)
        assert payload["ring4_consolidation"]["status"] == "active"
        assert "ring3_advancement" in payload
        assert "ring5_profiling" in payload
        assert payload["overall_loop_health_score"] == 100
        assert payload["overall_status"] == "optimal"

    async def test_missing_event_log_dir_reports_ring1_ready(self, client, tmp_path, monkeypatch, memory_manager, skill_sources):
        monkeypatch.setattr(settings.database, "event_log_dir", str(tmp_path / "absent"))

        resp = await client.get(STATUS_URL)

        assert resp.status_code == 200
        ring1 = resp.json()["data"]["ring1_reflection"]
        assert ring1["total_traces_analyzed"] == 0
        assert ring1["status"] == "ready"

    async def test_failing_memory_type_is_skipped_without_hiding_the_others(
        self, client, event_log_dir, memory_manager, skill_sources
    ):
        failing_type = ALL_MEMORY_TYPES[0]

        def count(memory_type: MemoryType, **_: object) -> int:
            if memory_type is failing_type:
                raise RuntimeError("store unavailable")
            return MEMORIES_PER_TYPE

        memory_manager.count_memories.side_effect = count

        resp = await client.get(STATUS_URL)

        assert resp.status_code == 200
        ring4 = resp.json()["data"]["ring4_consolidation"]
        assert ring4["total_memories"] == MEMORIES_PER_TYPE * (len(ALL_MEMORY_TYPES) - 1)
        assert ring4["status"] == "active"
