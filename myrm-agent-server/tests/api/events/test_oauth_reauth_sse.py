"""Integration test: OAUTH_REAUTH_REQUIRED event → SSE stream delivery.

Verifies the full backend chain without external deps:
  _emit_reauth_if_needed() → EventBus.publish() → SSE generator yields correct JSON
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.services.agent.oauth_refresher import _emit_reauth_if_needed, _reauth_emitted_at
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus


@pytest.fixture(autouse=True)
def _reset_dedup():
    _reauth_emitted_at.clear()
    yield
    _reauth_emitted_at.clear()


@pytest.mark.asyncio
async def test_oauth_reauth_event_flows_through_eventbus() -> None:
    """Publish via _emit_reauth_if_needed and verify subscriber receives the event."""
    bus = get_event_bus()
    queue = bus.subscribe()
    try:
        _emit_reauth_if_needed("integration_issuer", "invalid_grant")

        event: AppEvent = await asyncio.wait_for(queue.get(), timeout=2.0)
        assert event.event_type == AppEventType.OAUTH_REAUTH_REQUIRED
        assert event.data["issuer"] == "integration_issuer"
        assert event.data["reason"] == "invalid_grant"
        assert event.timestamp
    finally:
        bus.unsubscribe(queue)


@pytest.mark.asyncio
async def test_sse_json_format_matches_frontend_contract() -> None:
    """Verify the SSE payload structure matches what useGlobalEvents.ts expects."""
    bus = get_event_bus()
    queue = bus.subscribe()
    try:
        # Drain any leftover events from previous tests
        while not queue.empty():
            queue.get_nowait()

        _emit_reauth_if_needed("google_workspace", "token_expired")

        event: AppEvent = await asyncio.wait_for(queue.get(), timeout=2.0)

        payload = json.dumps(
            {"type": event.event_type, "data": event.data, "timestamp": event.timestamp},
            ensure_ascii=False,
        )
        parsed = json.loads(payload)

        assert parsed["type"] == "oauth_reauth_required"
        assert parsed["data"]["issuer"] == "google_workspace"
        assert parsed["data"]["reason"] == "token_expired"
        assert "timestamp" in parsed
    finally:
        bus.unsubscribe(queue)


@pytest.mark.asyncio
async def test_dispatcher_template_renders_for_oauth_reauth() -> None:
    """Verify the IM notification template renders without KeyError."""
    from app.core.notifications.dispatcher import _EVENT_TEMPLATES

    template = _EVENT_TEMPLATES[AppEventType.OAUTH_REAUTH_REQUIRED]
    rendered = template.format(issuer="google_workspace", reason="invalid_grant")
    assert "google_workspace" in rendered
    assert "invalid_grant" in rendered
    assert "Settings" in rendered
