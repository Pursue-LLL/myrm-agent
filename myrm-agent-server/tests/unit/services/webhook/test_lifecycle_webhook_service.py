"""Unit tests for lifecycle outbound webhook service and models.

[POS] Tests HMAC signature generation, event dispatch, and API routes.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.event.app_event_bus import AppEvent, AppEventType
from app.services.webhook.lifecycle_webhook_service import (
    LifecycleOutboundWebhookService,
    OutboundWebhookTarget,
)


def test_build_payload_bytes_and_signature():
    """Verify JSON structure and HMAC signature matching."""
    svc = LifecycleOutboundWebhookService()
    event_name = "session_completed"
    data = {"session_id": "test-123", "tokens_used": 100}
    delivery_id = "deliv-456"

    payload_bytes = svc._build_payload_bytes(event_name, data, delivery_id)
    payload = json.loads(payload_bytes.decode("utf-8"))

    assert payload["hook_event_name"] == "session_completed"
    assert payload["delivery_id"] == "deliv-456"
    assert payload["data"]["session_id"] == "test-123"

    target = OutboundWebhookTarget(
        id="target-1",
        name="Test Target",
        url="https://example.com/webhook",
        secret="whsec_mysecret",
        events=["session_completed"],
        agent_id=None,
        is_active=True,
        timeout_seconds=10,
    )

    item = svc._build_delivery_item(target, event_name, payload_bytes, delivery_id)
    assert item["headers"]["X-Myrm-Event"] == "session_completed"
    assert item["headers"]["X-Myrm-Delivery"] == "deliv-456"

    expected_sig = "sha256=" + hmac.new(b"whsec_mysecret", payload_bytes, hashlib.sha256).hexdigest()
    assert item["headers"]["X-Myrm-Signature-256"] == expected_sig


@pytest.mark.asyncio
async def test_ping_webhook_ssrf_block():
    """Verify SSRF validation blocks dangerous private network ranges in ping probe."""
    svc = LifecycleOutboundWebhookService()
    # 169.254.169.254 is cloud metadata IP, should be rejected by validate_webhook_url
    res = await svc.ping_webhook(url="http://169.254.169.254/latest/meta-data/")
    assert not res.success
    assert res.error is not None
    assert "SSRF blocked" in res.error


@pytest.mark.asyncio
async def test_on_app_event_enqueues_matching_webhook_target():
    """AppEvent publish must enqueue outbound delivery for subscribed active targets."""
    svc = LifecycleOutboundWebhookService()
    svc._running = True

    mock_model = MagicMock()
    mock_model.id = "wh-dispatch-1"
    mock_model.name = "Dispatch Test"
    mock_model.url = "https://example.com/hook"
    mock_model.secret = "whsec_test"
    mock_model.events_json = ["session_completed"]
    mock_model.agent_id = None
    mock_model.is_active = True
    mock_model.timeout_seconds = 10

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_model]
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    @asynccontextmanager
    async def fake_get_session():
        yield mock_session

    with patch(
        "app.services.webhook.lifecycle_webhook_service.get_session",
        fake_get_session,
    ):
        svc._on_app_event(
            AppEvent(
                event_type=AppEventType.SESSION_COMPLETED,
                data={"chat_id": "chat-dispatch", "phase": "completed"},
            )
        )
        await asyncio.sleep(0.05)

    assert svc._queue.qsize() == 1
    item = svc._queue.get_nowait()
    assert item["url"] == "https://example.com/hook"
    assert item["headers"]["X-Myrm-Event"] == "session_completed"
