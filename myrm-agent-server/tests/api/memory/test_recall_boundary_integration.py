"""Unit and integration tests for Review-First Memory Recall Boundary endpoint.

[INPUT]
app.schemas.memory.command_center::MemoryRecallBoundaryData
app.api.memory.operations.command_center::get_memory_recall_boundary

[OUTPUT]
test_recall_boundary_schema_contracts, test_recall_boundary_api_endpoint

[POS]
Tests for the Review-First Memory Recall Boundary and Candidate/Approved partition snapshot API.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock

from app.main import app
from app.schemas.memory.command_center import (
    MemoryRecallBoundaryData,
    MemoryRecallScopeBoundary,
    MemoryFourPartitionSummary,
    MemoryCandidateRecord,
    MemoryApprovedRecord,
)


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
            working_memory_count=4,
            operating_instructions_count=1,
            retrievable_evidence_count=10,
            identity_chars=400,
            working_memory_chars=1200,
            operating_instructions_chars=300,
            retrievable_evidence_chars=2500,
        ),
        candidate_records=[
            MemoryCandidateRecord(
                id="cand-1",
                memory_type="semantic",
                content_preview="User prefers dark mode",
                confidence=0.88,
                source="extraction",
                created_at="2026-08-20T12:00:00Z",
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
                char_count=22,
                is_pinned=True,
            )
        ],
        budget_chars_used=4400,
        budget_chars_total=6000,
        budget_overflow_risk="safe",
        total_candidates=1,
        total_approved=17,
    )

    assert boundary.agent_id == "test-agent"
    assert boundary.budget_overflow_risk == "safe"
    assert len(boundary.read_scopes) == 2
    assert boundary.partitions.identity_count == 2
    assert len(boundary.candidate_records) == 1
    assert len(boundary.approved_records) == 1
    assert boundary.approved_records[0].is_pinned is True


@pytest.mark.asyncio
async def test_get_memory_recall_boundary_api() -> None:
    """Verify GET /api/v1/memory/command-center/recall-boundary endpoint returns 200."""
    from app.api.dependencies import get_db_session
    from app.api.memory.utils import get_crud_memory_manager

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    mock_db.execute.return_value.scalars.return_value = scalars_mock

    mock_manager = MagicMock()
    mock_manager.memory_policy = None
    mock_manager.namespaces = ["global", "agent:default"]
    mock_manager.list_memories = AsyncMock(return_value=[])

    app.dependency_overrides[get_db_session] = lambda: mock_db
    app.dependency_overrides[get_crud_memory_manager] = lambda: mock_manager

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/memory/command-center/recall-boundary?agent_id=ag-1&task_id=task-1")
            assert response.status_code == 200
            data = response.json()
            assert "read_scopes" in data
            assert "partitions" in data
            assert "budget_chars_total" in data
            assert data["budget_chars_total"] == 6000
            assert data["budget_overflow_risk"] in ("safe", "approaching_limit", "overflow")
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_crud_memory_manager, None)
