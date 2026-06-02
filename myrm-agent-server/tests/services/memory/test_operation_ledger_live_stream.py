"""Tests for memory operation ledger live SSE publish."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from app.database.models.memory import MemoryOperationEventModel
from app.services.event.app_event_bus import AppEventType, EventBus
from app.services.memory.operation_ledger import _publish_memory_operation_event


def test_publish_memory_operation_event_emits_timeline_payload() -> None:
    bus = EventBus()
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
