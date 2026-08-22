"""Unit tests for lifecycle outbound webhook service and models.

[POS] Tests HMAC signature generation, event dispatch, and API routes.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import pytest
from unittest.mock import MagicMock, patch

from app.api.webhook.schemas import LifecycleWebhookCreate, LifecycleWebhookUpdate, WebhookPingRequest
from app.database.models.lifecycle_webhook import LifecycleWebhookModel
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
