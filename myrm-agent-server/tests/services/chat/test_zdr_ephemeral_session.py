"""Unit tests for Zero Data Retention (ZDR) ephemeral in-memory session store & attestation.

[INPUT]
- pytest (POS: 测试框架)
- app.services.chat.ephemeral_session_store::EphemeralSessionStore
- app.core.security.zdr_attestation::generate_zdr_attestation
- app.database.dto::MessageDTO

[OUTPUT]
- Test suite verifying in-memory storage, 60s reconnect grace, physical 0x00 wipe,
  and cryptographic attestation signing.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from app.core.security.zdr_attestation import generate_zdr_attestation
from app.database.dto import MessageDTO
from app.services.chat.chat_message import _ChatMessageMixin
from app.services.chat.ephemeral_session_store import EphemeralSessionStore


@pytest.fixture(autouse=True)
def _reset_ephemeral_store() -> None:
    """Ensure clean singleton state before each test."""
    EphemeralSessionStore.reset_instance_for_testing()


@pytest.mark.asyncio
async def test_ephemeral_session_store_lifecycle() -> None:
    """Verify appending, retrieving, and physical wiping in RAM."""
    store = EphemeralSessionStore.get_instance()
    chat_id = "test-zdr-session-123"

    assert await store.has_session(chat_id) is False

    msg1 = MessageDTO(
        id="m1",
        chat_id=chat_id,
        role="user",
        content="Confidential acquisition term sheet",
        sent_at=datetime.now(timezone.utc),
        sent_timezone="UTC",
        created_at=datetime.now(timezone.utc),
    )
    await store.append_message(chat_id, msg1)

    assert await store.has_session(chat_id) is True
    messages = await store.get_messages(chat_id)
    assert len(messages) == 1
    assert messages[0].content == "Confidential acquisition term sheet"

    # Audit summary
    summary = await store.get_audit_summary(chat_id)
    assert summary is not None
    assert summary["chat_id"] == chat_id
    assert summary["message_count"] == 1
    assert summary["is_zero_retention"] is True

    # Physical wipe
    wiped = await store.wipe(chat_id)
    assert wiped is True
    assert await store.has_session(chat_id) is False
    assert await store.get_messages(chat_id) == []


@pytest.mark.asyncio
async def test_graceful_reconnect_window() -> None:
    """Verify 60s transient disconnect tolerance."""
    store = EphemeralSessionStore.get_instance()
    chat_id = "test-reconnect-session"

    msg = MessageDTO(
        id="m1",
        chat_id=chat_id,
        role="user",
        content="Hello secret",
        sent_at=datetime.now(timezone.utc),
        sent_timezone="UTC",
        created_at=datetime.now(timezone.utc),
    )
    await store.append_message(chat_id, msg)

    # Disconnect
    await store.mark_disconnected(chat_id)
    # Immediately after disconnect, it should NOT be expired
    assert await store.is_reconnect_window_expired(chat_id, timeout_seconds=10.0) is False

    # Simulate reconnect within window
    reconnected = await store.mark_reconnected(chat_id)
    assert reconnected is True

    # Artificially set an old disconnect timestamp to test expiration
    store._disconnect_timestamps[chat_id] = time.time() - 70.0
    assert await store.is_reconnect_window_expired(chat_id, timeout_seconds=60.0) is True


def test_cryptographic_attestation_signing() -> None:
    """Verify HMAC-SHA256 signature and markdown report generation."""
    attestation = generate_zdr_attestation(
        chat_id="chat-ciso-audit-999",
        message_count=12,
        total_chars=8500,
    )

    assert attestation.chat_id == "chat-ciso-audit-999"
    assert attestation.message_count == 12
    assert attestation.total_characters_processed == 8500
    assert attestation.zero_disk_storage_verified is True
    assert attestation.vendor_zdr_headers_injected is True
    assert len(attestation.signature) == 64  # SHA256 hex digest length
    assert attestation.attestation_id.startswith("zdr-attest-")

    md_report = attestation.to_markdown_report()
    assert "# Myrm Zero Data Retention (ZDR) Compliance Attestation" in md_report
    assert "chat-ciso-audit-999" in md_report
    assert "VERIFIED (100% RAM-Only)" in md_report


@pytest.mark.asyncio
async def test_chat_message_mixin_bypasses_db_for_incognito() -> None:
    """Verify append_message stores in EphemeralSessionStore when is_incognito=True."""
    store = EphemeralSessionStore.get_instance()
    chat_id = "incognito-chat-bypass-test"

    msg = await _ChatMessageMixin.append_message(
        chat_id=chat_id,
        role="user",
        content="Secret query",
        sent_at=datetime.now(timezone.utc),
        sent_timezone="UTC",
        is_incognito=True,
    )

    assert msg.content == "Secret query"
    assert await store.has_session(chat_id) is True
    msgs_in_mem = await store.get_messages(chat_id)
    assert len(msgs_in_mem) == 1
    assert msgs_in_mem[0].content == "Secret query"

    # Fetch through getter
    retrieved = await _ChatMessageMixin.get_all_messages(chat_id)
    assert len(retrieved) == 1
    assert retrieved[0].id == msg.id


def test_zdr_rest_api_endpoints() -> None:
    """Verify REST API endpoints: /status, /attestation, /reconnect, /wipe."""
    from fastapi.testclient import TestClient

    from tests.support.minimal_app import build_minimal_app

    app = build_minimal_app(preset="chats")

    with TestClient(app) as client:
        non_existent = "non-existent-zdr"
        # 1. Status for non-existent session
        res = client.get(f"/api/v1/chats/{non_existent}/zdr/status")
        assert res.status_code == 200
        assert res.json()["data"]["is_active_ephemeral"] is False

        # 2. Append message directly to simulate incognito session
        store = EphemeralSessionStore.get_instance()
        chat_id = "api-test-chat-zdr"
        import asyncio

        msg = MessageDTO(
            id="m_api",
            chat_id=chat_id,
            role="user",
            content="Top secret message",
            sent_at=datetime.now(timezone.utc),
            sent_timezone="UTC",
            created_at=datetime.now(timezone.utc),
        )
        asyncio.run(store.append_message(chat_id, msg))

        # 3. Status for active session
        res = client.get(f"/api/v1/chats/{chat_id}/zdr/status")
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["is_active_ephemeral"] is True
        assert data["zero_disk_retention"] is True
        assert data["message_count"] == 1

        # 4. Attestation
        res = client.get(f"/api/v1/chats/{chat_id}/zdr/attestation")
        assert res.status_code == 200
        attest_data = res.json()["data"]
        assert attest_data["chat_id"] == chat_id
        assert attest_data["zero_disk_storage_verified"] is True
        assert len(attest_data["signature"]) == 64

        # 5. Reconnect
        res = client.post(f"/api/v1/chats/{chat_id}/zdr/reconnect")
        assert res.status_code == 200
        assert res.json()["data"]["reconnected"] is True

        # 6. Wipe
        res = client.post(f"/api/v1/chats/{chat_id}/zdr/wipe")
        assert res.status_code == 200
        assert res.json()["data"]["wiped"] is True

        # 7. Status after wipe
        res = client.get(f"/api/v1/chats/{chat_id}/zdr/status")
        assert res.status_code == 200
        assert res.json()["data"]["is_active_ephemeral"] is False

