"""SSE notification stream integration tests: the voice background task contract and non-JSON-native payloads.

Covers the real backend path that the frontend depends on for #3
VoiceBackgroundCompletionDuplexAnnounce:

  WebuiVoiceWorkNotifier publishes AppEventType.SYSTEM_NOTIFICATION
  (data.meta_data.kind == "voice_background_task_done") on the in-process
  ServerEventBus; the SSE generator serializes it as a data: JSON line.

The test drives the *real* `_sse_generator` async generator against the *real*
ServerEventBus (no mocks): the event is published before the generator starts,
PubSubBus replays its backlog to the new subscriber, and the generator emits
the exact SSE envelope the WebUI parses:
  type == "system_notification"
  data.meta_data.kind == "voice_background_task_done"
  data.meta_data.chat_id / task_id / status
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import UUID

import pytest
from myrm_agent_harness.infra.pubsub.event_bus import PubSubBus

from app.api.events.notifications import _sse_generator
from app.services.event.app_event_bus import AppEvent, AppEventType, ServerEventBus, get_event_bus


class _FakeRequest:
    """Minimal request shim — the generator only calls is_disconnected()."""

    async def is_disconnected(self) -> bool:
        return False


def _publish_voice_done(chat_id: str, task_id: str, status: str = "success") -> None:
    get_event_bus().publish(
        AppEvent(
            event_type=AppEventType.SYSTEM_NOTIFICATION,
            data={
                "title": "Background task finished",
                "message": "The web search completed.",
                "meta_data": {
                    "kind": "voice_background_task_done",
                    "chat_id": chat_id,
                    "task_id": task_id,
                    "status": status,
                },
            },
        )
    )


async def _read_event_payload(chat_id: str, task_id: str) -> dict[str, object]:
    """Publish, run the real generator, and return the matching SSE payload."""
    _publish_voice_done(chat_id, task_id)

    generator = _sse_generator(_FakeRequest())
    try:
        while True:
            line = await generator.__anext__()
            if not line.startswith("data:"):
                continue
            payload = json.loads(line[len("data:") :].strip())
            meta = (payload.get("data") or {}).get("meta_data") or {}
            if (
                payload.get("type") == AppEventType.SYSTEM_NOTIFICATION
                and meta.get("kind") == "voice_background_task_done"
                and meta.get("task_id") == task_id
            ):
                return payload
    finally:
        await generator.aclose()


@pytest.mark.asyncio
async def test_stream_emits_voice_background_task_done() -> None:
    payload = await _read_event_payload("chat_123", "task_456")

    assert payload["type"] == "system_notification"

    data = payload["data"]
    meta_data = data["meta_data"]
    assert meta_data["kind"] == "voice_background_task_done"
    assert meta_data["chat_id"] == "chat_123"
    assert meta_data["task_id"] == "task_456"
    assert meta_data["status"] == "success"
    assert data["title"]
    assert data["message"]


@pytest.mark.asyncio
async def test_stream_includes_timestamp() -> None:
    payload = await _read_event_payload("chat_789", "task_123")
    assert "timestamp" in payload
    assert payload["timestamp"]


@pytest.fixture
def isolated_bus(monkeypatch: pytest.MonkeyPatch) -> ServerEventBus:
    """A fresh bus, so events published here never enter the process-wide backlog."""
    bus: ServerEventBus = PubSubBus()
    monkeypatch.setattr("app.api.events.notifications.get_event_bus", lambda: bus)
    return bus


async def _next_data_line(generator: AsyncIterator[str]) -> str:
    """Return the next `data:` line, failing fast instead of waiting out a heartbeat."""
    while True:
        line = await asyncio.wait_for(generator.__anext__(), timeout=5)
        if line.startswith("data:"):
            return line


def _parse(line: str) -> dict[str, object]:
    return json.loads(line[len("data:") :].strip())


@pytest.mark.asyncio
async def test_plain_payload_is_serialized_as_plain_json(isolated_bus: ServerEventBus) -> None:
    event = AppEvent(event_type=AppEventType.SYSTEM_NOTIFICATION, data={"title": "已完成", "count": 2})
    isolated_bus.publish(event)

    generator = _sse_generator(_FakeRequest())
    try:
        line = await _next_data_line(generator)
    finally:
        await generator.aclose()

    envelope = {"type": event.event_type, "data": event.data, "timestamp": event.timestamp}
    assert line == f"data: {json.dumps(envelope, ensure_ascii=False)}\n\n"


@pytest.mark.asyncio
async def test_non_json_native_values_are_delivered_as_strings(isolated_bus: ServerEventBus) -> None:
    due_at = datetime(2026, 10, 15, 9, 30, tzinfo=timezone.utc)
    task_id = UUID(int=7)
    isolated_bus.publish(AppEvent(event_type=AppEventType.KANBAN_TASK_UPDATED, data={"due_at": due_at, "task_id": task_id}))

    generator = _sse_generator(_FakeRequest())
    try:
        payload = _parse(await _next_data_line(generator))
    finally:
        await generator.aclose()

    assert payload["type"] == "kanban_task_updated"
    assert payload["data"] == {"due_at": str(due_at), "task_id": str(task_id)}


@pytest.mark.asyncio
async def test_non_json_native_value_in_backlog_does_not_break_any_reconnect(isolated_bus: ServerEventBus) -> None:
    isolated_bus.publish(
        AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"due_at": datetime(2026, 10, 15, 9, 30, tzinfo=timezone.utc)},
        )
    )
    isolated_bus.publish(AppEvent(event_type=AppEventType.SYSTEM_NOTIFICATION, data={"title": "later"}))

    for _ in range(3):  # every iteration is a fresh subscriber replaying the same backlog
        generator = _sse_generator(_FakeRequest())
        try:
            types = [_parse(await _next_data_line(generator))["type"] for _ in range(2)]
        finally:
            await generator.aclose()
        assert types == ["kanban_task_updated", "system_notification"]
