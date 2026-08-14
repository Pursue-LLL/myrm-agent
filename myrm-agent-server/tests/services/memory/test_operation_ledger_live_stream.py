"""Tests for memory operation ledger live SSE publish."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import patch

from myrm_agent_harness.toolkits.memory import MemoryOperationKind, MemoryOperationStatus

from app.database.models.memory import MemoryOperationEventModel
from app.services.event.app_event_bus import AppEventType, ServerEventBus
from app.services.memory.operation_ledger import (
    MemoryOperationLedgerService,
    _publish_memory_operation_event,
)


class _RecordingSession:
    """Test double recording the order of add/commit calls inside record_event."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def add(self, _row: object) -> None:
        self.calls.append("add")

    async def commit(self) -> None:
        self.calls.append("commit")


def test_publish_memory_operation_event_emits_timeline_payload() -> None:
    bus = ServerEventBus()
    queue = bus.subscribe()
    row = MemoryOperationEventModel(
        id="evt-1",
        kind="recall",
        status="success",
        occurred_at=datetime.now(UTC),
        memory_type="semantic",
        namespace="conversation:chat-123",
        source="memory_retrieval_trace",
        summary="Recalled 3 memories for routing",
        target_kind="chat",
        target_id="chat-123",
        correlation_id="msg-1",
        influence_refs_json=[],
        metadata_json={"chat_id": "chat-123", "step_phase": "rank"},
    )

    with patch("app.services.event.app_event_bus.get_event_bus", return_value=bus):
        _publish_memory_operation_event(row)

    event = queue.get_nowait()
    assert event.event_type == AppEventType.MEMORY_OPERATION
    assert event.data["id"] == "evt-1"
    assert event.data["kind"] == "recall"
    assert event.data["target_id"] == "chat-123"
    assert event.data["metadata"]["chat_id"] == "chat-123"
    assert event.data["description"] == "Recalled 3 memories for routing"


def test_publish_memory_operation_event_drops_nested_metadata_for_sse() -> None:
    """SSE payloads keep scalars only; nested diagnostic detail stays out of the wire format."""
    bus = ServerEventBus()
    queue = bus.subscribe()
    row = MemoryOperationEventModel(
        id="evt-nested",
        kind="health_check",
        status="success",
        occurred_at=datetime.now(UTC),
        source="memory_diagnostics",
        summary="Memory diagnostics completed",
        target_kind="health",
        target_id="diagnostic_run",
        metadata_json={
            "benchmark_recall_at_k": 0.9,
            "benchmark_categories": {"profile": "2/2"},
        },
    )

    with patch("app.services.event.app_event_bus.get_event_bus", return_value=bus):
        _publish_memory_operation_event(row)

    event = queue.get_nowait()
    assert event.data["metadata"]["benchmark_recall_at_k"] == 0.9
    assert "benchmark_categories" not in event.data["metadata"]


def test_record_event_publishes_only_after_commit_when_commit_requested() -> None:
    """commit=True 时 SSE publish 必须发生在 DB commit 之后，杜绝 ghost event。"""
    db = _RecordingSession()
    with patch(
        "app.services.memory.operation_ledger._publish_memory_operation_event",
        side_effect=lambda _row: db.calls.append("publish"),
    ):
        asyncio.run(
            MemoryOperationLedgerService(db).record_event(
                kind=MemoryOperationKind.RECALL,
                status=MemoryOperationStatus.SUCCESS,
                summary="recall during request",
                target_kind="chat",
                target_id="chat-1",
                commit=True,
            )
        )
    assert db.calls == ["add", "commit", "publish"]
