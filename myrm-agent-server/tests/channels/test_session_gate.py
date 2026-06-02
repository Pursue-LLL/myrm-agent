"""Tests for SessionGate debounce and concurrency control.

Validates that rapid-fire messages are merged, active-session messages
are held in pending, and edge cases (single message, debounce=0) work.
"""

from __future__ import annotations

import asyncio

import pytest

from app.channels.routing.session_gate import (
    SessionGate,
    SessionGateConfig,
    gate_key,
    merge_messages,
)
from app.channels.types import (
    InboundMessage,
    MediaAttachment,
    MediaType,
)


def _msg(
    content: str = "hello",
    *,
    channel: str = "telegram",
    sender_id: str = "user1",
    chat_id: str | None = None,
    is_group: bool = False,
    media: tuple[MediaAttachment, ...] = (),
    thread_id: str | None = None,
    mentioned: bool = False,
    message_id: str | None = None,
) -> InboundMessage:
    metadata: dict[str, object] = {}
    if message_id:
        metadata["message_id"] = message_id
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        content=content,
        chat_id=chat_id,
        is_group=is_group,
        media=media,
        thread_id=thread_id,
        mentioned=mentioned,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# gate_key
# ---------------------------------------------------------------------------


class TestGateKey:
    def test_dm_uses_sender_id(self) -> None:
        msg = _msg(sender_id="alice")
        assert gate_key(msg) == "telegram:alice"

    def test_group_uses_chat_id(self) -> None:
        msg = _msg(chat_id="group1", is_group=True)
        assert gate_key(msg) == "telegram:group1"

    def test_empty_ids_fallback(self) -> None:
        msg = _msg(sender_id="", chat_id=None)
        assert gate_key(msg) == "telegram:unknown"


# ---------------------------------------------------------------------------
# merge_messages
# ---------------------------------------------------------------------------


class TestMergeMessages:
    def test_single_message_unchanged(self) -> None:
        msg = _msg("hi")
        merged = merge_messages((msg,))
        assert merged is msg

    def test_content_newline_joined(self) -> None:
        m1 = _msg("hello")
        m2 = _msg("world")
        merged = merge_messages((m1, m2))
        assert merged.content == "hello\nworld"

    def test_empty_content_skipped(self) -> None:
        m1 = _msg("")
        m2 = _msg("real content")
        m3 = _msg("  ")
        merged = merge_messages((m1, m2, m3))
        assert merged.content == "real content"

    def test_media_concatenated(self) -> None:
        img = MediaAttachment(media_type=MediaType.IMAGE, url="http://img1.png")
        doc = MediaAttachment(media_type=MediaType.DOCUMENT, url="http://doc.pdf")
        m1 = _msg("look", media=(img,))
        m2 = _msg("also", media=(doc,))
        merged = merge_messages((m1, m2))
        assert len(merged.media) == 2
        assert merged.media[0].url == "http://img1.png"
        assert merged.media[1].url == "http://doc.pdf"

    def test_metadata_from_last(self) -> None:
        m1 = _msg("a", message_id="m1")
        m2 = _msg("b", message_id="m2")
        merged = merge_messages((m1, m2))
        assert merged.metadata.get("message_id") == "m2"

    def test_thread_id_from_first_non_none(self) -> None:
        m1 = _msg("a")
        m2 = _msg("b", thread_id="topic42")
        merged = merge_messages((m1, m2))
        assert merged.thread_id == "topic42"

    def test_mentioned_propagated(self) -> None:
        m1 = _msg("a")
        m2 = _msg("b", mentioned=True)
        merged = merge_messages((m1, m2))
        assert merged.mentioned is True

    def test_channel_and_sender_from_first(self) -> None:
        m1 = _msg("a", channel="whatsapp", sender_id="alice")
        m2 = _msg("b", channel="whatsapp", sender_id="alice")
        merged = merge_messages((m1, m2))
        assert merged.channel == "whatsapp"
        assert merged.sender_id == "alice"


# ---------------------------------------------------------------------------
# SessionGate
# ---------------------------------------------------------------------------


class TestSessionGate:
    @pytest.mark.asyncio
    async def test_single_message_fires_after_debounce(self) -> None:
        received: list[InboundMessage] = []

        async def on_ready(msg: InboundMessage) -> None:
            received.append(msg)

        gate = SessionGate(SessionGateConfig(debounce_window_ms=50), on_ready=on_ready)
        gate.submit(_msg("hello"))
        assert len(received) == 0
        await asyncio.sleep(0.1)
        assert len(received) == 1
        assert received[0].content == "hello"

    @pytest.mark.asyncio
    async def test_rapid_fire_merged(self) -> None:
        received: list[InboundMessage] = []

        async def on_ready(msg: InboundMessage) -> None:
            received.append(msg)

        gate = SessionGate(SessionGateConfig(debounce_window_ms=100), on_ready=on_ready)
        gate.submit(_msg("one"))
        await asyncio.sleep(0.02)
        gate.submit(_msg("two"))
        await asyncio.sleep(0.02)
        gate.submit(_msg("three"))

        await asyncio.sleep(0.2)
        assert len(received) == 1
        assert received[0].content == "one\ntwo\nthree"

    @pytest.mark.asyncio
    async def test_zero_debounce_fires_immediately(self) -> None:
        received: list[InboundMessage] = []

        async def on_ready(msg: InboundMessage) -> None:
            received.append(msg)

        gate = SessionGate(SessionGateConfig(debounce_window_ms=0), on_ready=on_ready)
        gate.submit(_msg("instant1"))
        gate.submit(_msg("instant2"))
        await asyncio.sleep(0.05)
        assert len(received) == 2

    @pytest.mark.asyncio
    async def test_pending_during_active_task(self) -> None:
        received: list[InboundMessage] = []
        proceed = asyncio.Event()

        async def on_ready(msg: InboundMessage) -> None:
            received.append(msg)
            if len(received) == 1:
                await proceed.wait()

        gate = SessionGate(SessionGateConfig(debounce_window_ms=30), on_ready=on_ready)
        gate.submit(_msg("first"))
        await asyncio.sleep(0.1)
        assert len(received) == 1

        gate.submit(_msg("pending1"))
        gate.submit(_msg("pending2"))
        await asyncio.sleep(0.1)
        assert len(received) == 1

        proceed.set()
        await asyncio.sleep(0.15)
        assert len(received) == 2
        assert received[1].content == "pending1\npending2"

    @pytest.mark.asyncio
    async def test_different_sessions_independent(self) -> None:
        received: list[InboundMessage] = []

        async def on_ready(msg: InboundMessage) -> None:
            received.append(msg)

        gate = SessionGate(SessionGateConfig(debounce_window_ms=50), on_ready=on_ready)
        gate.submit(_msg("from alice", sender_id="alice"))
        gate.submit(_msg("from bob", sender_id="bob"))
        await asyncio.sleep(0.15)
        assert len(received) == 2
        contents = {r.content for r in received}
        assert contents == {"from alice", "from bob"}

    @pytest.mark.asyncio
    async def test_pending_queue_limit(self) -> None:
        received: list[InboundMessage] = []
        proceed = asyncio.Event()

        async def on_ready(msg: InboundMessage) -> None:
            received.append(msg)
            if len(received) == 1:
                await proceed.wait()

        gate = SessionGate(
            SessionGateConfig(debounce_window_ms=30, max_pending_per_session=2),
            on_ready=on_ready,
        )
        gate.submit(_msg("first"))
        await asyncio.sleep(0.1)

        gate.submit(_msg("p1"))
        gate.submit(_msg("p2"))
        gate.submit(_msg("p3 dropped"))
        await asyncio.sleep(0.05)

        proceed.set()
        await asyncio.sleep(0.15)
        assert len(received) == 2
        assert received[1].content == "p1\np2"

    @pytest.mark.asyncio
    async def test_pending_count_empty(self) -> None:
        async def on_ready(msg: InboundMessage) -> None:
            pass

        gate = SessionGate(SessionGateConfig(debounce_window_ms=50), on_ready=on_ready)
        assert gate.pending_count("telegram:unknown") == 0

    @pytest.mark.asyncio
    async def test_pending_count_with_queued_messages(self) -> None:
        received: list[InboundMessage] = []
        proceed = asyncio.Event()

        async def on_ready(msg: InboundMessage) -> None:
            received.append(msg)
            if len(received) == 1:
                await proceed.wait()

        gate = SessionGate(SessionGateConfig(debounce_window_ms=30), on_ready=on_ready)
        gate.submit(_msg("first"))
        await asyncio.sleep(0.1)
        assert len(received) == 1

        gate.submit(_msg("queued1"))
        gate.submit(_msg("queued2"))
        await asyncio.sleep(0.05)
        assert gate.pending_count("telegram:user1") == 2

        proceed.set()
        await asyncio.sleep(0.15)
        assert gate.pending_count("telegram:user1") == 0

    @pytest.mark.asyncio
    async def test_clear_cancels_timers(self) -> None:
        received: list[InboundMessage] = []

        async def on_ready(msg: InboundMessage) -> None:
            received.append(msg)

        gate = SessionGate(SessionGateConfig(debounce_window_ms=100), on_ready=on_ready)
        gate.submit(_msg("hello"))
        gate.clear()
        await asyncio.sleep(0.2)
        assert len(received) == 0
