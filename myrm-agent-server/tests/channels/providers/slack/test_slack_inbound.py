"""SlackChannel inbound events, mention annotation, block-action timestamps and the thread tracker."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.channels.providers.slack import SlackChannel
from app.channels.types import (
    InboundMessage,
)
from tests.channels.providers.slack.support import make_channel


class TestSlackInbound:
    """Tests for handle_event, _handle_block_actions, _parse_message_event."""

    @pytest.mark.asyncio
    async def test_handle_event_url_verification(self) -> None:
        ch = make_channel()
        result = await ch.handle_event({"type": "url_verification", "challenge": "abc123"})
        assert result == {"challenge": "abc123"}

    @pytest.mark.asyncio
    async def test_handle_event_message(self) -> None:
        ch = make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[method-assign]
        event_data: dict[str, object] = {
            "type": "event_callback",
            "event": {
                "type": "message",
                "user": "U_USER",
                "text": "<@U_BOT> hello",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "1234.5678",
            },
        }
        result = await ch.handle_event(event_data)
        assert result is None
        assert len(emitted) == 1
        msg = emitted[0]
        assert msg.content == "hello"
        assert msg.sender_id == "U_USER"
        assert msg.mentioned is True

    @pytest.mark.asyncio
    async def test_handle_event_ignores_bot_message(self) -> None:
        ch = make_channel()
        ch._emit_inbound = AsyncMock()  # type: ignore[method-assign]
        event_data: dict[str, object] = {
            "type": "event_callback",
            "event": {
                "type": "message",
                "user": "U_BOT",
                "text": "bot reply",
                "channel": "C_CHAN",
                "ts": "1234.5678",
            },
        }
        await ch.handle_event(event_data)
        ch._emit_inbound.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_event_ignores_subtype(self) -> None:
        ch = make_channel()
        ch._emit_inbound = AsyncMock()  # type: ignore[method-assign]
        event_data: dict[str, object] = {
            "type": "event_callback",
            "event": {
                "type": "message",
                "subtype": "message_changed",
                "user": "U_USER",
                "text": "edited",
                "channel": "C_CHAN",
                "ts": "1234.5678",
            },
        }
        await ch.handle_event(event_data)
        ch._emit_inbound.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_event_block_actions(self) -> None:
        ch = make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[method-assign]
        payload: dict[str, object] = {
            "type": "block_actions",
            "user": {"id": "U_USER", "name": "testuser"},
            "channel": {"id": "C_CHAN"},
            "actions": [{"action_id": "approve", "type": "button"}],
            "message": {"ts": "1234.5678"},
            "trigger_id": "T_TRIGGER",
        }
        result = await ch.handle_event(payload)
        assert result is None
        assert len(emitted) == 1
        assert emitted[0].content == "approve"

    @pytest.mark.asyncio
    async def test_handle_event_invalid_event(self) -> None:
        ch = make_channel()
        result = await ch.handle_event({"type": "event_callback", "event": "not_a_dict"})
        assert result is None

    @pytest.mark.asyncio
    async def test_parse_message_event_with_thread(self) -> None:
        ch = make_channel()
        event: dict[str, object] = {
            "type": "message",
            "user": "U_USER",
            "text": "reply in thread",
            "channel": "C_CHAN",
            "channel_type": "im",
            "ts": "2222.0001",
            "thread_ts": "1111.0000",
        }
        msg = await ch._parse_message_event(event)
        assert msg is not None
        assert msg.thread_id == "1111.0000"
        assert msg.reply_to_id == "1111.0000"
        assert msg.is_group is False

    @pytest.mark.asyncio
    async def test_parse_message_event_with_media(self) -> None:
        ch = make_channel()
        event: dict[str, object] = {
            "type": "message",
            "user": "U_USER",
            "text": "",
            "channel": "C_CHAN",
            "channel_type": "channel",
            "ts": "3333.0001",
            "files": [{"mimetype": "image/jpeg", "name": "photo.jpg", "url_private": "https://files.slack.com/photo.jpg"}],
        }
        msg = await ch._parse_message_event(event)
        assert msg is not None
        assert len(msg.media) == 1
        assert msg.media[0].filename == "photo.jpg"

    @pytest.mark.asyncio
    async def test_parse_message_event_empty_text_no_media(self) -> None:
        ch = make_channel()
        event: dict[str, object] = {
            "type": "message",
            "user": "U_USER",
            "text": "  ",
            "channel": "C_CHAN",
            "ts": "4444.0001",
        }
        msg = await ch._parse_message_event(event)
        assert msg is None

    def test_verify_request(self) -> None:
        ch = SlackChannel(bot_token="xoxb-test", signing_secret="mysecret")
        with patch(
            "app.channels.providers.slack.inbound.verify_slack_signature",
            return_value=True,
        ):
            assert ch.verify_request(b"body", "123", "v0=sig") is True


class TestSlackMentionAnnotation:
    """Tests for _annotate_mentions."""

    @pytest.mark.asyncio
    async def test_annotate_mentions_no_mentions(self) -> None:
        ch = make_channel()
        result = await ch._annotate_mentions("hello world")
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_annotate_mentions_empty_text(self) -> None:
        ch = make_channel()
        result = await ch._annotate_mentions("")
        assert result == ""

    @pytest.mark.asyncio
    async def test_annotate_mentions_with_resolution(self) -> None:
        ch = make_channel()
        with patch.object(
            ch._user_resolver,
            "resolve_batch",
            new_callable=AsyncMock,
            return_value={"UABC": "Alice"},
        ):
            result = await ch._annotate_mentions("Hey <@UABC> check this")
        assert result == "Hey <@UABC> (Alice) check this"

    @pytest.mark.asyncio
    async def test_annotate_mentions_resolution_fails(self) -> None:
        ch = make_channel()
        with patch.object(
            ch._user_resolver,
            "resolve_batch",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await ch._annotate_mentions("Hey <@UABC> check this")
        assert result == "Hey <@UABC> check this"

    @pytest.mark.asyncio
    async def test_annotate_mentions_deduplicates(self) -> None:
        ch = make_channel()
        with patch.object(
            ch._user_resolver,
            "resolve_batch",
            new_callable=AsyncMock,
            return_value={"UABC": "Alice"},
        ) as mock_resolve:
            await ch._annotate_mentions("<@UABC> and <@UABC> again")
        args = mock_resolve.call_args[0][0]
        assert args == ["UABC"]

    @pytest.mark.asyncio
    async def test_annotate_mentions_limit(self) -> None:
        ch = make_channel()
        ch._mention_annotation_limit = 2
        many_mentions = " ".join(f"<@U{i:04d}>" for i in range(5))
        with patch.object(
            ch._user_resolver,
            "resolve_batch",
            new_callable=AsyncMock,
            return_value={},
        ) as mock_resolve:
            await ch._annotate_mentions(many_mentions)
        args = mock_resolve.call_args[0][0]
        assert len(args) == 2


class TestSlackBlockActionsTimestamp:
    """Tests for _handle_block_actions timestamp parsing."""

    @pytest.mark.asyncio
    async def test_block_action_uses_message_ts(self) -> None:
        ch = make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[method-assign]
        payload: dict[str, object] = {
            "type": "block_actions",
            "user": {"id": "U_USER", "name": "test"},
            "channel": {"id": "C_CHAN"},
            "actions": [{"action_id": "btn", "type": "button"}],
            "message": {"ts": "1700000000.000"},
            "trigger_id": "T_TRIG",
        }
        await ch.handle_event(payload)
        assert len(emitted) == 1
        assert emitted[0].sent_at == 1700000000.0

    @pytest.mark.asyncio
    async def test_block_action_invalid_ts(self) -> None:
        ch = make_channel()
        emitted: list[InboundMessage] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[method-assign]
        payload: dict[str, object] = {
            "type": "block_actions",
            "user": {"id": "U_USER", "name": "test"},
            "channel": {"id": "C_CHAN"},
            "actions": [{"action_id": "btn", "type": "button"}],
            "message": {"ts": "not_a_number"},
            "trigger_id": "T_TRIG",
        }
        await ch.handle_event(payload)
        assert len(emitted) == 1


class TestSlackThreadTracker:
    """Tests for ThreadTracker LRU cache and metrics."""

    def test_add_and_contains(self) -> None:
        from app.channels.providers.slack.thread_tracker import ThreadTracker

        tracker = ThreadTracker(max_size=3)
        tracker.add("t1")
        tracker.add("t2")
        assert tracker.contains("t1") is True
        assert tracker.contains("t3") is False

    def test_lru_eviction(self) -> None:
        from app.channels.providers.slack.thread_tracker import ThreadTracker

        tracker = ThreadTracker(max_size=2)
        tracker.add("t1")
        tracker.add("t2")
        tracker.add("t3")  # evicts t1
        assert tracker.contains("t1") is False
        assert tracker.contains("t2") is True
        assert tracker.contains("t3") is True

    def test_metrics_hit_rate(self) -> None:
        from app.channels.providers.slack.thread_tracker import ThreadTracker

        tracker = ThreadTracker()
        tracker.add("t1")
        tracker.contains("t1")  # hit
        tracker.contains("t2")  # miss
        assert tracker.metrics.hit_count == 1
        assert tracker.metrics.miss_count == 1
        assert tracker.metrics.get_hit_rate() == 0.5

    def test_metrics_zero_division(self) -> None:
        from app.channels.providers.slack.thread_tracker import ThreadTrackerMetrics

        metrics = ThreadTrackerMetrics()
        assert metrics.get_hit_rate() == 0.0

    def test_move_to_end_on_add(self) -> None:
        from app.channels.providers.slack.thread_tracker import ThreadTracker

        tracker = ThreadTracker(max_size=2)
        tracker.add("t1")
        tracker.add("t2")
        tracker.add("t1")  # move t1 to end
        tracker.add("t3")  # evicts t2 (oldest)
        assert tracker.contains("t1") is True
        assert tracker.contains("t2") is False
        assert tracker.contains("t3") is True
