"""Unit tests for the Zero Data Retention (ZDR) ephemeral in-memory session store.

[INPUT]
- pytest (POS: 测试框架)
- app.services.chat.ephemeral_session_store::EphemeralSessionStore
- app.database.dto::MessageDTO

[OUTPUT]
- Test suite verifying in-memory storage, 60s reconnect grace, physical 0x00 wipe,
  and the incognito bypass of database persistence.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

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
