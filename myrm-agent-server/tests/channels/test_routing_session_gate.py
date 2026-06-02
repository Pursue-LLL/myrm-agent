"""SessionGate tests — debounce, merge, concurrency, pending queue."""

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
    ContextEntry,
    InboundMessage,
    MediaAttachment,
    MediaType,
)


def _msg(
    content: str = "hi",
    *,
    channel: str = "test",
    sender_id: str = "user1",
    chat_id: str = "",
    is_group: bool = False,
    mentioned: bool = False,
    thread_id: str | None = None,
    media: tuple[MediaAttachment, ...] = (),
    metadata: dict[str, object] | None = None,
    message_id: str = "",
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        content=content,
        chat_id=chat_id,
        is_group=is_group,
        mentioned=mentioned,
        thread_id=thread_id,
        media=media,
        metadata=metadata or {},
        message_id=message_id,
    )


class TestGateKey:
    def test_dm_key(self) -> None:
        msg = _msg(sender_id="u1", is_group=False)
        key = gate_key(msg)
        assert "test" in key
        assert "u1" in key

    def test_group_key_uses_chat_id(self) -> None:
        msg = _msg(sender_id="u1", chat_id="grp-1", is_group=True)
        key = gate_key(msg)
        assert "grp-1" in key

    def test_missing_peer_uses_unknown(self) -> None:
        msg = _msg(sender_id="", chat_id="", is_group=False)
        key = gate_key(msg)
        assert "unknown" in key


class TestMergeMessages:
    def test_single_message_passthrough(self) -> None:
        m = _msg("hello")
        result = merge_messages((m,))
        assert result is m

    def test_two_messages_merged(self) -> None:
        m1 = _msg("hello", message_id="1", metadata={"a": 1})
        m2 = _msg("world", message_id="2", metadata={"b": 2})
        result = merge_messages((m1, m2))
        assert result.content == "hello\nworld"
        assert result.message_id == "2"
        assert result.metadata == {"b": 2}

    def test_empty_content_skipped(self) -> None:
        m1 = _msg("hello")
        m2 = _msg("   ")
        m3 = _msg("world")
        result = merge_messages((m1, m2, m3))
        assert result.content == "hello\nworld"

    def test_media_concatenated(self) -> None:
        att1 = MediaAttachment(media_type=MediaType.IMAGE, url="a.png")
        att2 = MediaAttachment(media_type=MediaType.DOCUMENT, url="b.pdf")
        m1 = _msg("a", media=(att1,))
        m2 = _msg("b", media=(att2,))
        result = merge_messages((m1, m2))
        assert len(result.media) == 2

    def test_context_concatenated(self) -> None:
        c1 = ContextEntry(sender_id="s1", content="c1", timestamp=1.0)
        c2 = ContextEntry(sender_id="s2", content="c2", timestamp=2.0)
        m1 = InboundMessage(channel="t", sender_id="u", content="a", context_messages=(c1,))
        m2 = InboundMessage(channel="t", sender_id="u", content="b", context_messages=(c2,))
        result = merge_messages((m1, m2))
        assert len(result.context_messages) == 2

    def test_thread_id_first_non_none(self) -> None:
        m1 = _msg("a", thread_id=None)
        m2 = _msg("b", thread_id="t-1")
        m3 = _msg("c", thread_id="t-2")
        result = merge_messages((m1, m2, m3))
        assert result.thread_id == "t-1"

    def test_mentioned_any_true(self) -> None:
        m1 = _msg("a", mentioned=False)
        m2 = _msg("b", mentioned=True)
        result = merge_messages((m1, m2))
        assert result.mentioned is True


class TestSessionGateDebounce:
    @pytest.mark.asyncio
    async def test_immediate_fire_when_debounce_zero(self) -> None:
        received: list[InboundMessage] = []

        async def on_ready(msg: InboundMessage) -> None:
            received.append(msg)

        gate = SessionGate(SessionGateConfig(debounce_window_ms=0), on_ready=on_ready)
        gate.submit(_msg("hello"))
        await asyncio.sleep(0.05)
        assert len(received) == 1
        assert received[0].content == "hello"

    @pytest.mark.asyncio
    async def test_debounce_merges_rapid_messages(self) -> None:
        received: list[InboundMessage] = []

        async def on_ready(msg: InboundMessage) -> None:
            received.append(msg)

        gate = SessionGate(SessionGateConfig(debounce_window_ms=50), on_ready=on_ready)
        gate.submit(_msg("a", message_id="1"))
        gate.submit(_msg("b", message_id="2"))
        gate.submit(_msg("c", message_id="3"))

        await asyncio.sleep(0.2)
        assert len(received) == 1
        assert "a" in received[0].content
        assert "c" in received[0].content

    @pytest.mark.asyncio
    async def test_pending_queue_when_active(self) -> None:
        call_count = 0
        received: list[InboundMessage] = []

        async def on_ready(msg: InboundMessage) -> None:
            nonlocal call_count
            call_count += 1
            received.append(msg)
            if call_count == 1:
                await asyncio.sleep(0.1)

        gate = SessionGate(SessionGateConfig(debounce_window_ms=0), on_ready=on_ready)
        gate.submit(_msg("first"))
        await asyncio.sleep(0.02)
        gate.submit(_msg("second"))
        await asyncio.sleep(0.3)
        assert len(received) == 2

    @pytest.mark.asyncio
    async def test_pending_queue_overflow(self) -> None:
        received: list[InboundMessage] = []

        async def on_ready(msg: InboundMessage) -> None:
            received.append(msg)
            await asyncio.sleep(0.5)

        gate = SessionGate(
            SessionGateConfig(debounce_window_ms=0, max_pending_per_session=2),
            on_ready=on_ready,
        )
        gate.submit(_msg("first"))
        await asyncio.sleep(0.02)
        gate.submit(_msg("p1"))
        gate.submit(_msg("p2"))
        gate.submit(_msg("p3-dropped"))
        await asyncio.sleep(0.8)
        assert len(received) == 2

    @pytest.mark.asyncio
    async def test_on_task_complete_drains_pending(self) -> None:
        received: list[InboundMessage] = []
        hold = asyncio.Event()

        async def on_ready(msg: InboundMessage) -> None:
            received.append(msg)
            if len(received) == 1:
                await hold.wait()

        gate = SessionGate(SessionGateConfig(debounce_window_ms=0), on_ready=on_ready)
        m1 = _msg("first")
        gate.submit(m1)
        await asyncio.sleep(0.02)
        gate.submit(_msg("pending"))
        hold.set()
        await asyncio.sleep(0.2)
        assert len(received) >= 2

    @pytest.mark.asyncio
    async def test_clear_cancels_timers(self) -> None:
        received: list[InboundMessage] = []

        async def on_ready(msg: InboundMessage) -> None:
            received.append(msg)

        gate = SessionGate(SessionGateConfig(debounce_window_ms=200), on_ready=on_ready)
        gate.submit(_msg("hello"))
        gate.clear()
        await asyncio.sleep(0.4)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_callback_error_handled(self) -> None:
        async def on_ready(msg: InboundMessage) -> None:
            raise RuntimeError("callback error")

        gate = SessionGate(SessionGateConfig(debounce_window_ms=0), on_ready=on_ready)
        gate.submit(_msg("hello"))
        await asyncio.sleep(0.1)
