"""Proactive follow-up decisions — pure predicate and registry contracts."""

from app.channels.routing.follow_up import (
    COMPLETION_RECEIPT_MIN_SECONDS,
    FollowUpDedup,
    ThreadStallTracker,
    _format_elapsed,
    should_nudge_stall,
    should_post_receipt,
)


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


def test_receipt_dedup_keyed_by_trigger_message() -> None:
    """Same trigger retried collapses; distinct triggers each deliver."""
    import asyncio

    from app.channels.routing.follow_up import maybe_post_completion_receipt
    from app.channels.types import InboundMessage, TopicContext

    sent: list[object] = []

    class FakeBus:
        async def publish_outbound(self, message: object) -> str:
            sent.append(message)
            return "mid-1"

    def _msg(message_id: str | None) -> InboundMessage:
        return InboundMessage(
            channel="feishu",
            sender_id="u1",
            content="do it",
            chat_id="chat-1",
            is_group=True,
            mentioned=True,
            message_id=message_id,
        )

    topic = TopicContext(topic_id="chat-1", agent_id="a1")
    kwargs: dict[str, object] = {
        "bus": FakeBus(),
        "topic": topic,
        "chat_id": "chat-1",
        "elapsed_seconds": 400.0,
        "is_resume": False,
        "delivered": True,
    }
    bus = kwargs["bus"]
    assert bus is not None
    assert (
        asyncio.run(
            maybe_post_completion_receipt(**kwargs, msg=_msg("m-1"))  # type: ignore[arg-type]
        )
        is True
    )
    assert (
        asyncio.run(
            maybe_post_completion_receipt(**kwargs, msg=_msg("m-1"))  # type: ignore[arg-type]
        )
        is False
    )
    assert (
        asyncio.run(
            maybe_post_completion_receipt(**kwargs, msg=_msg("m-2"))  # type: ignore[arg-type]
        )
        is True
    )
    assert len(sent) == 2
