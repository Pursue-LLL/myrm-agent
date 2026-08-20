"""Unit tests for learning_timeline module — memory & skill unified chronological stream."""

from __future__ import annotations

from datetime import UTC, datetime

from app.api.statistics.learning_timeline import (
    LearningTimelineItem,
    LearningTimelineResponse,
    TimelineMemoryUpdateRequest,
    TimelineNodeKind,
)


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
