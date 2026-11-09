"""Unit and integration tests for Review-First Memory Recall Boundary endpoint.

[INPUT]
app.schemas.memory.command_center::MemoryRecallBoundaryData
app.api.memory.operations.command_center::get_memory_recall_boundary

[OUTPUT]
test_recall_boundary_schema_contracts, test_an_approved_record_may_have_no_importance_score, test_get_memory_recall_boundary_api

[POS]
Tests for the Review-First Memory Recall Boundary and Candidate/Approved partition snapshot API.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.memory import MemoryType

from app.schemas.memory.command_center import (
    MemoryApprovedRecord,
    MemoryCandidateRecord,
    MemoryFourPartitionSummary,
    MemoryRecallBoundaryData,
    MemoryRecallScopeBoundary,
)
from tests.support.minimal_app import build_minimal_app


def test_recall_boundary_schema_contracts() -> None:
    """Verify MemoryRecallBoundaryData Pydantic validation and field defaults."""
    boundary = MemoryRecallBoundaryData(
        agent_id="test-agent",
        task_id="test-task",
        read_scopes=[
            MemoryRecallScopeBoundary(
                level="global",
                label="Global Shared",
                is_active=True,
                namespace_pattern="global",
                description="System-wide knowledge",
            ),
            MemoryRecallScopeBoundary(
                level="task",
                label="Task Isolated",
                is_active=True,
                namespace_pattern="task:test-task",
                description="Task ephemeral memory",
            ),
        ],
        write_policy="inherit",
        partitions=MemoryFourPartitionSummary(
            identity_count=2,
            session_memory_count=4,
            operating_instructions_count=1,
            retrievable_evidence_count=10,
        ),
        candidate_records=[
            MemoryCandidateRecord(
                id="cand-1",
                memory_type="semantic",
                content_preview="User prefers dark mode",
                confidence=0.88,
                source="extraction",
                created_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
                status="pending",
            )
        ],
        approved_records=[
            MemoryApprovedRecord(
                id="appr-1",
                memory_type="procedural",
                content_preview="Always avoid alert()",
                namespace="global",
                partition="operating_instructions",
                importance=0.95,
                access_count=12,
                is_pinned=True,
            )
        ],
        total_candidates=1,
        total_approved=17,
    )

    assert boundary.agent_id == "test-agent"
    assert len(boundary.read_scopes) == 2
    assert boundary.partitions.identity_count == 2
    assert len(boundary.candidate_records) == 1
    assert len(boundary.approved_records) == 1
    assert boundary.approved_records[0].is_pinned is True


def test_an_approved_record_may_have_no_importance_score() -> None:
    """A memory type without an importance score (a procedural rule) reports none instead of a made-up value."""
    record = MemoryApprovedRecord(
        id="appr-2",
        memory_type="procedural",
        content_preview="Ask before changing the schema",
        namespace="global",
        partition="operating_instructions",
        access_count=0,
    )

    assert record.importance is None


@pytest.mark.asyncio
async def test_get_memory_recall_boundary_api() -> None:
    """Verify GET /api/v1/memory/command-center/recall-boundary endpoint returns 200."""
    from app.api.dependencies import get_db_session
    from app.api.memory.utils import get_crud_memory_manager

    mock_exec_result = MagicMock()
    mock_exec_result.scalars.return_value.all.return_value = []
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_exec_result)

    mock_manager = MagicMock()
    mock_manager.memory_policy = None
    mock_manager.namespaces = ["global", "agent:default"]
    mock_manager.list_memories = AsyncMock(return_value=[])
    mock_manager.list_pending = AsyncMock(return_value=[])
    mock_manager.count_memories = AsyncMock(side_effect=lambda memory_type: 3 if memory_type == MemoryType.SEMANTIC else 0)

    test_app = build_minimal_app(preset="memory")
    test_app.dependency_overrides[get_db_session] = lambda: mock_db
    test_app.dependency_overrides[get_crud_memory_manager] = lambda: mock_manager

    try:
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/memory/command-center/recall-boundary?agent_id=ag-1&task_id=task-1")
            assert response.status_code == 200
            data = response.json()
            assert "read_scopes" in data
            assert data["partitions"] == {
                "identity_count": 0,
                "session_memory_count": 0,
                "operating_instructions_count": 0,
                "retrievable_evidence_count": 3,
            }
            assert data["total_approved"] == 3
            assert not [name for name in data if name.startswith("budget")]
    finally:
        test_app.dependency_overrides.pop(get_db_session, None)
        test_app.dependency_overrides.pop(get_crud_memory_manager, None)
