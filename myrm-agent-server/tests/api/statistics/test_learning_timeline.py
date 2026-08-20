"""Unit tests for learning_timeline module — memory & skill unified chronological stream."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api.statistics.learning_timeline import (
    LearningTimelineItem,
    LearningTimelineResponse,
    TimelineMemoryUpdateRequest,
    TimelineNodeKind,
    archive_timeline_skill_item,
    delete_timeline_memory_item,
    get_learning_timeline,
    update_timeline_memory_item,
)
from app.services.skills.growth.audit_queries import SkillGrowthTimelineEventRead
from app.services.skills.growth.case_types import SkillGrowthCaseSource, SkillGrowthCaseStatus


class TestLearningTimelineSchemas:
    """Test Pydantic schemas for learning timeline."""

    def test_item_schema(self):
        item = LearningTimelineItem(
            id="mem-1",
            kind=TimelineNodeKind.FACT_MEMORY,
            title="User prefers Python 3.13",
            content="Always use Python 3.13 and uv package manager",
            created_at=datetime.now(UTC).isoformat(),
            agent_id="agent-coder",
            confidence=0.95,
            importance=8.0,
            is_user_edited=True,
            status="active",
            metadata={"source": "user_correction"},
        )
        assert item.id == "mem-1"
        assert item.kind == TimelineNodeKind.FACT_MEMORY
        assert item.importance == 8.0
        assert item.is_user_edited is True

    def test_response_schema(self):
        resp = LearningTimelineResponse(
            items=[],
            total_count=0,
            has_more=False,
            next_cursor=None,
        )
        assert resp.total_count == 0
        assert resp.has_more is False

    def test_update_request_schema(self):
        req = TimelineMemoryUpdateRequest(
            content="Updated rule",
            importance=0.9,
            reasoning="Manual override by user",
        )
        assert req.content == "Updated rule"
        assert req.importance == 0.9
        assert req.reasoning == "Manual override by user"


@pytest.mark.asyncio
class TestLearningTimelineEndpoints:
    """Test API endpoint handler functions with mocked dependencies."""

    async def test_get_learning_timeline_success(self):
        mock_manager = AsyncMock()
        mock_mem = SimpleNamespace(
            id="mem-123",
            content="Use pytest-safe script",
            created_at=datetime.now(UTC),
            importance=0.8,
            confidence=0.95,
            is_user_locked=True,
            scope=SimpleNamespace(agent_id="agent-1"),
            tags=["dev", "test"],
            status="active",
            source_chat_id="chat-1",
            preference_type=None,
        )
        mock_manager.list_memories.return_value = [mock_mem]

        mock_growth_evt = SkillGrowthTimelineEventRead(
            case_id="case-1",
            skill_name="code-reviewer",
            growth_type="evolve",
            status=SkillGrowthCaseStatus.APPROVED,
            source=SkillGrowthCaseSource.EVOLUTION,
            created_at=datetime.now(UTC),
            change_summary="Improved lint error detection",
            skill_id="skill-1",
        )

        with patch(
            "app.api.statistics.learning_timeline.list_skill_growth_timeline",
            new_callable=AsyncMock,
        ) as mock_growth:
            mock_growth.return_value = [mock_growth_evt]

            resp = await get_learning_timeline(
                days=30,
                agent_id=None,
                kind_filter=None,
                limit=10,
                cursor=None,
                manager=mock_manager,
            )
            assert resp.status_code == 200

    async def test_update_timeline_memory_item_success(self):
        mock_manager = AsyncMock()
        mock_mem = SimpleNamespace(
            id="mem-1",
            content="Updated rule",
            importance=0.9,
            reasoning="Context",
            tags=["python"],
            is_user_locked=True,
            status="active",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_manager.update_memory.return_value = mock_mem

        with patch(
            "app.api.statistics.learning_timeline._record_memory_event",
            new_callable=AsyncMock,
        ):
            req = TimelineMemoryUpdateRequest(
                content="Updated rule",
                importance=0.9,
                reasoning="Context",
            )
            resp = await update_timeline_memory_item(
                memory_type="semantic",
                memory_id="mem-1",
                body=req,
                manager=mock_manager,
            )
            assert resp.status_code == 200

    async def test_delete_timeline_memory_item_success(self):
        mock_manager = AsyncMock()
        mock_manager.delete_memory.return_value = True

        with patch(
            "app.api.statistics.learning_timeline._record_memory_event",
            new_callable=AsyncMock,
        ):
            resp = await delete_timeline_memory_item(
                memory_id="mem-1",
                memory_type="semantic",
                manager=mock_manager,
            )
            assert resp.status_code == 200

    async def test_archive_timeline_skill_item_success(self):
        mock_skill = SimpleNamespace(
            id="skill-1",
            name="test-skill",
            is_active=False,
        )
        with patch(
            "app.api.statistics.learning_timeline.skills_service.update_skill",
            new_callable=AsyncMock,
        ) as mock_update:
            mock_update.return_value = mock_skill
            resp = await archive_timeline_skill_item(
                skill_id="skill-1",
                active=False,
            )
            assert resp.status_code == 200
