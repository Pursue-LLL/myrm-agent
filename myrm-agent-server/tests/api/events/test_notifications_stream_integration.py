"""SSE notification stream integration tests for the voice background task contract.

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

import json

import pytest

from app.api.events.notifications import _sse_generator
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus


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
            payload = json.loads(line[len("data:"):].strip())
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
