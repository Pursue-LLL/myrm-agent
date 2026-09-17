"""Proactive follow-up decisions — pure predicate and registry contracts."""

from app.channels.routing.follow_up import (
    COMPLETION_RECEIPT_MIN_SECONDS,
    FollowUpDedup,
    ThreadStallTracker,
    _format_elapsed,
    should_nudge_stall,
    should_post_receipt,
)
from app.channels.types import InboundMessage


def test_should_post_receipt_long_group_turn() -> None:
    assert (
        should_post_receipt(
            is_group=True,
            receipts_enabled=True,
            identity_revoked=False,
            turn_seconds=COMPLETION_RECEIPT_MIN_SECONDS + 1,
            is_resume=False,
            result_sent=True,
        )
        is True
    )


def test_should_post_receipt_gates() -> None:
    base = dict(
        is_group=True,
        receipts_enabled=True,
        identity_revoked=False,
        turn_seconds=9999.0,
        is_resume=False,
        result_sent=True,
    )
    assert should_post_receipt(**{**base, "is_group": False}) is False
    assert should_post_receipt(**{**base, "receipts_enabled": False}) is False
    assert should_post_receipt(**{**base, "identity_revoked": True}) is False
    assert should_post_receipt(**{**base, "result_sent": False}) is False
    assert (
        should_post_receipt(**{**base, "turn_seconds": 1.0, "is_resume": True}) is True
    )
    assert should_post_receipt(**{**base, "turn_seconds": 1.0}) is False


def test_should_nudge_stall_requires_pending_and_cooldown() -> None:
    base = dict(
        stall_enabled=True,
        identity_revoked=False,
        muted=False,
        silent_seconds=49 * 3600.0,
        has_pending=True,
        cooldown_ok=True,
    )
    assert should_nudge_stall(**base) is True
    assert should_nudge_stall(**{**base, "stall_enabled": False}) is False
    assert should_nudge_stall(**{**base, "identity_revoked": True}) is False
    assert should_nudge_stall(**{**base, "muted": True}) is False
    assert should_nudge_stall(**{**base, "has_pending": False}) is False
    assert should_nudge_stall(**{**base, "cooldown_ok": False}) is False
    assert should_nudge_stall(**{**base, "silent_seconds": 60.0}) is False


def test_dedup_collapses_retries_then_expires() -> None:
    dedup = FollowUpDedup(ttl_seconds=60.0, max_size=10)
    assert dedup.seen("k") is False
    dedup.mark("k")
    assert dedup.seen("k") is True


def test_stall_tracker_touch_and_stalled() -> None:
    from app.channels.routing.follow_up import TrackedThread

    tracker = ThreadStallTracker(max_size=10)
    tracker.touch(
        TrackedThread(
            channel="feishu",
            chat_id="chat-1",
            thread_id=None,
            requester_id="u1",
            requester_name=None,
            locale="en",
        )
    )
    assert tracker.stalled(stall_after_seconds=10**9) == []
    assert len(tracker.stalled(stall_after_seconds=-1)) == 1
    key = ThreadStallTracker.thread_key("feishu", "chat-1", None)
    tracker.refresh(key)
    assert tracker.stalled(stall_after_seconds=10**9) == []
    tracker.drop(key)
    assert tracker.stalled(stall_after_seconds=-1) == []


def test_muted_thread_never_nudged() -> None:
    from app.channels.routing.follow_up import TrackedThread

    tracker = ThreadStallTracker(max_size=10)
    slot = TrackedThread(
        channel="feishu",
        chat_id="chat-9",
        thread_id=None,
        requester_id="u9",
        requester_name=None,
        locale="en",
    )
    key = ThreadStallTracker.thread_key("feishu", "chat-9", None)
    tracker.touch(slot)
    tracker.mute(key)
    assert tracker.is_muted(key) is True
    # Later inbound traffic must not resurrect it.
    tracker.touch(slot)
    assert tracker.stalled(stall_after_seconds=-1) == []
    # Unbind clears the mute.
    tracker.drop(key)
    assert tracker.is_muted(key) is False
    tracker.touch(slot)
    assert len(tracker.stalled(stall_after_seconds=-1)) == 1


def test_format_elapsed_units() -> None:
    assert _format_elapsed(45) == "45s"
    assert _format_elapsed(125) == "2m05s"
    assert "h" in _format_elapsed(3700)


class _FakeBus:
    def __init__(self) -> None:
        self.sent: list[object] = []

    async def publish_outbound(self, message: object) -> str:
        self.sent.append(message)
        return "mid-1"


def _group_msg(message_id: str | None, chat_id: str = "chat-1") -> InboundMessage:
    return InboundMessage(
        channel="feishu",
        sender_id="u1",
        content="do it",
        chat_id=chat_id,
        is_group=True,
        mentioned=True,
        message_id=message_id,
    )


async def test_receipt_short_turn_silent() -> None:
    from app.channels.routing.follow_up import maybe_post_completion_receipt
    from app.channels.types import TopicContext

    bus = _FakeBus()
    topic = TopicContext(topic_id="chat-1", agent_id="a1")
    assert (
        await maybe_post_completion_receipt(
            bus=bus,
            topic=topic,
            msg=_group_msg("m-1"),
            chat_id="chat-1",
            elapsed_seconds=5.0,
            is_resume=False,
            delivered=True,
        )
        is False
    )
    assert bus.sent == []


async def test_receipt_long_turn_posts_once_per_trigger() -> None:
    from app.channels.routing.follow_up import maybe_post_completion_receipt
    from app.channels.types import TopicContext

    bus = _FakeBus()
    # Unique ids: the dedup registry is process-wide, tests must not collide.
    topic = TopicContext(topic_id="chat-dedup", agent_id="a1")
    base = dict(bus=bus, topic=topic, chat_id="chat-dedup")
    assert (
        await maybe_post_completion_receipt(
            **base,  # type: ignore[arg-type]
            msg=_group_msg("m-1", chat_id="chat-dedup"),
            elapsed_seconds=400.0,
            is_resume=False,
            delivered=True,
        )
        is True
    )
    assert (
        await maybe_post_completion_receipt(
            **base,  # type: ignore[arg-type]
            msg=_group_msg("m-1", chat_id="chat-dedup"),
            elapsed_seconds=401.0,
            is_resume=False,
            delivered=True,
        )
        is False
    )
    assert (
        await maybe_post_completion_receipt(
            **base,  # type: ignore[arg-type]
            msg=_group_msg("m-2", chat_id="chat-dedup"),
            elapsed_seconds=402.0,
            is_resume=False,
            delivered=True,
        )
        is True
    )
    assert len(bus.sent) == 2


async def test_receipt_gates_draft_revoked_disabled() -> None:
    from app.channels.routing.follow_up import maybe_post_completion_receipt
    from app.channels.types import ReplyMode, TopicContext

    bus = _FakeBus()
    base = dict(chat_id="chat-1", elapsed_seconds=9999.0, is_resume=True, delivered=True)
    draft = TopicContext(topic_id="chat-1", agent_id="a1", reply_mode=ReplyMode.DRAFT_REVIEW)
    assert await maybe_post_completion_receipt(bus=bus, topic=draft, msg=_group_msg("m-1"), **base) is False  # type: ignore[arg-type]
    revoked = TopicContext(topic_id="chat-1", agent_id="a1", identity_revoked=True)
    assert await maybe_post_completion_receipt(bus=bus, topic=revoked, msg=_group_msg("m-1"), **base) is False  # type: ignore[arg-type]
    off = TopicContext(topic_id="chat-1", agent_id="a1", completion_receipts=False)
    assert await maybe_post_completion_receipt(bus=bus, topic=off, msg=_group_msg("m-1"), **base) is False  # type: ignore[arg-type]
    assert bus.sent == []


def test_activity_helpers_never_raise() -> None:
    from app.channels.routing.follow_up import drop_tracked_thread, mute_tracked_thread, note_group_activity

    note_group_activity("feishu", "chat-1", None, "u1", None, "en")
    mute_tracked_thread("feishu", "chat-1", None)
    drop_tracked_thread("feishu", "chat-1", None)


async def test_scan_empty_tracker_sends_nothing() -> None:
    from app.channels.routing.follow_up import get_stall_tracker, scan_stalled_threads

    bus = _FakeBus()
    get_stall_tracker()._slots.clear()

    async def resolve(channel: str, chat_id: str, thread_id: str | None) -> None:
        return None

    assert await scan_stalled_threads(bus=bus, resolve_topic=resolve) == 0
    assert bus.sent == []
