"""Tests for MessageBus and downgrade_components."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.bus import (
    MessageBus,
    downgrade_components,
)
from app.channels.types import (
    ActionButton,
    ChannelCapabilities,
    InboundMessage,
    OutboundMessage,
    QuickReply,
    SelectMenu,
    SelectOption,
)


class FakeChannel(BaseChannel):
    name = "fake"
    capabilities = ChannelCapabilities(
        buttons=True,
        quick_replies=True,
        select_menus=True,
    )

    def __init__(self, *, name: str = "fake", caps: ChannelCapabilities | None = None) -> None:
        super().__init__()
        if name != "fake":
            type(self).name = name  # type: ignore[assignment]
        if caps:
            type(self).capabilities = caps  # type: ignore[assignment]
        self.sent: list[OutboundMessage] = []

    async def send(self, msg: OutboundMessage) -> str | None:
        self.sent.append(msg)
        return "msg_id_1"


def _make_out(
    channel: str = "fake",
    content: str = "hello",
    components: tuple[tuple[ActionButton | SelectMenu, ...], ...] = (),
    quick_replies: tuple[QuickReply, ...] = (),
) -> OutboundMessage:
    return OutboundMessage(
        channel=channel,
        recipient_id="user1",
        content=content,
        user_id="test_user",
        components=components,
        quick_replies=quick_replies,
    )


class TestDowngradeComponents:
    def test_no_components_returns_same(self) -> None:
        ch = FakeChannel()
        msg = _make_out()
        result = downgrade_components(msg, ch)
        assert result is msg

    def test_buttons_kept_when_supported(self) -> None:
        ch = FakeChannel(caps=ChannelCapabilities(buttons=True))
        btn = ActionButton(label="OK", action_id="test:ok")
        msg = _make_out(components=((btn,),))
        result = downgrade_components(msg, ch)
        assert result is msg

    def test_buttons_downgraded_when_unsupported(self) -> None:
        ch = FakeChannel(caps=ChannelCapabilities(buttons=False))
        btn = ActionButton(label="OK", action_id="test:ok")
        msg = _make_out(content="Choose:", components=((btn,),))
        result = downgrade_components(msg, ch)
        assert len(result.components) == 0
        assert "OK" in result.content

    def test_select_menu_downgraded_independently(self) -> None:
        ch = FakeChannel(caps=ChannelCapabilities(buttons=True, select_menus=False))
        btn = ActionButton(label="OK", action_id="test:ok")
        sel = SelectMenu(
            action_id="test:sel",
            placeholder="Pick",
            options=(SelectOption(label="A", value="a"),),
        )
        msg = _make_out(components=((btn,), (sel,)))
        result = downgrade_components(msg, ch)
        assert len(result.components) == 1  # button row kept
        assert "A" in result.content or "Pick" in result.content

    def test_required_quick_replies_downgraded_when_unsupported(self) -> None:
        ch = FakeChannel(caps=ChannelCapabilities(quick_replies=False))
        qr = QuickReply(label="Yes", text="yes", required=True)
        msg = _make_out(quick_replies=(qr,))
        result = downgrade_components(msg, ch)
        assert len(result.quick_replies) == 0
        assert "Yes" in result.content

    def test_non_required_quick_replies_dropped_when_unsupported(self) -> None:
        ch = FakeChannel(caps=ChannelCapabilities(quick_replies=False))
        qr = QuickReply(label="Search", text="search")
        msg = _make_out(quick_replies=(qr,))
        result = downgrade_components(msg, ch)
        assert len(result.quick_replies) == 0
        assert "Search" not in result.content

    def test_mixed_quick_replies_only_required_downgraded(self) -> None:
        ch = FakeChannel(caps=ChannelCapabilities(quick_replies=False))
        suggestion = QuickReply(label="Search", text="search")
        action = QuickReply(label="Approve", text="/approve", required=True)
        msg = _make_out(quick_replies=(suggestion, action))
        result = downgrade_components(msg, ch)
        assert len(result.quick_replies) == 0
        assert "Approve" in result.content
        assert "Search" not in result.content

    def test_fallback_uses_english_by_default(self) -> None:
        """Test that fallback defaults to English for framework compliance."""
        ch = FakeChannel(caps=ChannelCapabilities(quick_replies=False))
        qr = QuickReply(label="Yes", text="yes", required=True)
        msg = _make_out(quick_replies=(qr,))
        result = downgrade_components(msg, ch)
        assert "Reply with a number" in result.content

    def test_fallback_uses_chinese_when_specified(self) -> None:
        """Test that fallback uses Chinese when explicitly requested."""
        ch = FakeChannel(caps=ChannelCapabilities(quick_replies=False))
        qr = QuickReply(label="Yes", text="yes", required=True)
        msg = OutboundMessage(
            channel="fake",
            recipient_id="user1",
            content="Do you agree?",
            user_id="test_user",
            quick_replies=(qr,),
            metadata={"locale": "zh"},
        )
        result = downgrade_components(msg, ch)
        assert "回复数字选择" in result.content
        assert "Reply with a number" not in result.content

    def test_downgrade_logs_info_message(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that downgrade events are logged at INFO level."""
        import logging

        caplog.set_level(logging.INFO)
        ch = FakeChannel(caps=ChannelCapabilities(buttons=False, quick_replies=False))
        button = ActionButton(label="Approve", action_id="approve")
        qr = QuickReply(label="Yes", text="yes", required=True)
        msg = OutboundMessage(
            channel="fake",
            recipient_id="user1",
            content="Choose:",
            user_id="test_user",
            components=((button,),),
            quick_replies=(qr,),
        )

        downgrade_components(msg, ch)

        # Verify log was emitted
        assert len(caplog.records) == 1
        log_record = caplog.records[0]
        assert log_record.levelname == "INFO"
        assert "Downgrading components/media for channel 'fake'" in log_record.message
        assert "buttons" in log_record.message
        assert "quick_replies(1)" in log_record.message

    def test_url_button_downgrade_shows_link(self) -> None:
        """Test that URL buttons show the URL in fallback text."""
        ch = FakeChannel(caps=ChannelCapabilities(buttons=False))
        url_button = ActionButton(label="View Details", action_id="view", url="https://example.com/details")
        msg = _make_out(components=((url_button,),))
        result = downgrade_components(msg, ch)
        assert "View Details → https://example.com/details" in result.content
        assert "/view" not in result.content  # Should NOT show action_id for URL buttons

    def test_select_menu_without_placeholder_uses_default(self) -> None:
        """Test that SelectMenu without placeholder uses localized default text."""
        ch = FakeChannel(caps=ChannelCapabilities(select_menus=False))
        menu = SelectMenu(
            action_id="test:sel",
            placeholder="",  # Empty placeholder
            options=(
                SelectOption(label="Option A", value="a"),
                SelectOption(label="Option B", value="b"),
            ),
        )

        # English default
        msg_en = _make_out(components=((menu,),))
        result_en = downgrade_components(msg_en, ch)
        assert "Options:" in result_en.content or "• Options:" in result_en.content

        # Chinese
        msg_zh = OutboundMessage(
            channel="fake",
            recipient_id="user1",
            content="选择:",
            user_id="test_user",
            components=((menu,),),
            metadata={"locale": "zh"},
        )
        result_zh = downgrade_components(msg_zh, ch)
        assert "选项:" in result_zh.content or "• 选项:" in result_zh.content

    def test_media_downgraded_when_unsupported(self) -> None:
        import dataclasses

        from app.channels.types import MediaAttachment, MediaType

        ch = FakeChannel(caps=ChannelCapabilities(media=False))
        media1 = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/img.png")
        media2 = MediaAttachment(media_type=MediaType.VIDEO, path="/local/video.mp4")
        msg = _make_out(content="Look at this:")
        msg = dataclasses.replace(msg, media=(media1, media2))
        result = downgrade_components(msg, ch)
        assert len(result.media) == 0
        assert "[Image: https://example.com/img.png]" in result.content
        assert "[Video attachment omitted (unsupported channel)]" in result.content

    def test_media_kept_when_supported(self) -> None:
        import dataclasses

        from app.channels.types import MediaAttachment, MediaType

        ch = FakeChannel(caps=ChannelCapabilities(media=True))
        media1 = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/img.png")
        msg = _make_out(content="Look at this:")
        msg = dataclasses.replace(msg, media=(media1,))
        result = downgrade_components(msg, ch)
        assert len(result.media) == 1
        assert "[Image: https://example.com/img.png]" not in result.content

    def test_mixed_components_and_media_downgraded_correctly(self) -> None:
        import dataclasses

        from app.channels.types import MediaAttachment, MediaType

        # Channel supports buttons but NOT media
        ch = FakeChannel(caps=ChannelCapabilities(buttons=True, media=False))
        btn = ActionButton(label="OK", action_id="test:ok")
        media1 = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/img.png")

        msg = _make_out(content="Choose:", components=((btn,),))
        msg = dataclasses.replace(msg, media=(media1,))

        result = downgrade_components(msg, ch)

        # Buttons should be kept
        assert len(result.components) == 1
        assert result.components[0][0].label == "OK"

        # Media should be stripped and appended to text
        assert len(result.media) == 0
        assert "[Image: https://example.com/img.png]" in result.content

    def test_empty_media_list_ignored(self) -> None:
        import dataclasses

        ch = FakeChannel(caps=ChannelCapabilities(media=False))
        msg = _make_out(content="Hello")
        msg = dataclasses.replace(msg, media=())
        result = downgrade_components(msg, ch)
        assert result is msg
        assert result.content == "Hello"


class TestMessageBusRegister:
    def test_register_and_get_channel(self) -> None:
        bus = MessageBus()
        ch = FakeChannel()
        bus.register_channel(ch)
        assert bus.get_channel("fake") is ch
        assert "fake" in bus.registered_channels

    def test_register_replaces_existing(self) -> None:
        bus = MessageBus()
        ch1 = FakeChannel()
        ch2 = FakeChannel()
        bus.register_channel(ch1)
        bus.register_channel(ch2)
        assert bus.get_channel("fake") is ch2

    def test_get_unknown_returns_none(self) -> None:
        bus = MessageBus()
        assert bus.get_channel("nonexistent") is None


class TestMessageBusSendTracked:
    @pytest.mark.asyncio
    async def test_send_tracked_returns_message_id(self) -> None:
        bus = MessageBus()
        ch = FakeChannel()
        bus.register_channel(ch)
        msg = _make_out()
        result = await bus.send_tracked(msg)
        assert result == "msg_id_1"
        assert len(ch.sent) == 1

    @pytest.mark.asyncio
    async def test_send_tracked_records_activity(self) -> None:
        bus = MessageBus()
        ch = FakeChannel()
        bus.register_channel(ch)
        assert ch.activity.last_outbound_at is None
        await bus.send_tracked(_make_out())
        assert ch.activity.last_outbound_at is not None

    @pytest.mark.asyncio
    async def test_send_tracked_unknown_channel_returns_none(self) -> None:
        bus = MessageBus()
        msg = _make_out(channel="unknown")
        result = await bus.send_tracked(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_tracked_downgrades_components(self) -> None:
        bus = MessageBus()
        ch = FakeChannel(caps=ChannelCapabilities(buttons=False))
        bus.register_channel(ch)
        btn = ActionButton(label="Click", action_id="test:click")
        msg = _make_out(content="Do:", components=((btn,),))
        await bus.send_tracked(msg)
        assert len(ch.sent) == 1
        assert len(ch.sent[0].components) == 0
        assert "Click" in ch.sent[0].content


class TestMessageBusEditMessage:
    @pytest.mark.asyncio
    async def test_edit_returns_true_on_success(self) -> None:
        bus = MessageBus()
        ch = FakeChannel()
        bus.register_channel(ch)
        result = await bus.edit_channel_message("fake", "chat1", "msg1", "new content")
        assert result is True

    @pytest.mark.asyncio
    async def test_edit_returns_false_for_unknown_channel(self) -> None:
        bus = MessageBus()
        result = await bus.edit_channel_message("unknown", "chat1", "msg1", "content")
        assert result is False


class TestMessageBusInbound:
    @pytest.mark.asyncio
    async def test_inbound_handler_routes_to_queue(self) -> None:
        bus = MessageBus()
        ch = FakeChannel()
        bus.register_channel(ch)

        msg = InboundMessage(
            channel="fake",
            sender_id="u1",
            content="hi",
            chat_id="c1",
        )
        await bus._handle_inbound(msg)
        result = await asyncio.wait_for(bus.consume_inbound(), timeout=1.0)
        assert result.content == "hi"


class TestMessageBusLifecycle:
    @pytest.mark.asyncio
    async def test_start_and_stop(self) -> None:
        bus = MessageBus()
        await bus.start()
        assert bus._running is True
        assert bus._dispatch_task is not None
        await bus.stop()
        assert bus._running is False
        assert bus._dispatch_task is None

    @pytest.mark.asyncio
    async def test_start_idempotent(self) -> None:
        bus = MessageBus()
        await bus.start()
        task1 = bus._dispatch_task
        await bus.start()
        assert bus._dispatch_task is task1
        await bus.stop()

    @pytest.mark.asyncio
    async def test_dispatch_loop_sends_message(self) -> None:
        bus = MessageBus()
        ch = FakeChannel()
        bus.register_channel(ch)
        await bus.start()
        try:
            await bus.publish_outbound(_make_out())
            await asyncio.sleep(0.1)
            assert len(ch.sent) == 1
        finally:
            await bus.stop()


class TestMessageBusEdgeCases:
    @pytest.mark.asyncio
    async def test_outbound_queue_full_drops_message(self) -> None:
        bus = MessageBus(max_queue_size=1)
        bus._ensure_queues()
        bus._outbound.put_nowait(_make_out())
        await bus.publish_outbound(_make_out(content="overflow"))
        assert bus._outbound.qsize() == 1

    @pytest.mark.asyncio
    async def test_inbound_queue_full_drops_message(self) -> None:
        bus = MessageBus(max_queue_size=1)
        bus._ensure_queues()
        msg = InboundMessage(channel="fake", sender_id="u1", content="hi", chat_id="c1")
        bus._inbound.put_nowait(msg)
        await bus._handle_inbound(msg)
        assert bus._inbound.qsize() == 1

    @pytest.mark.asyncio
    async def test_send_tracked_disabled_channel_returns_none(self) -> None:
        from app.channels.types import ChannelStatus

        bus = MessageBus()
        ch = FakeChannel()
        bus.register_channel(ch)
        ch._status = ChannelStatus.DISABLED
        result = await bus.send_tracked(_make_out())
        assert result is None

    @pytest.mark.asyncio
    async def test_send_tracked_send_failure_returns_none(self) -> None:
        class FailSendChannel(FakeChannel):
            async def send(self, msg: OutboundMessage) -> str | None:
                raise RuntimeError("send failed")

        bus = MessageBus()
        ch = FailSendChannel()
        bus.register_channel(ch)
        result = await bus.send_tracked(_make_out())
        assert result is None

    @pytest.mark.asyncio
    async def test_send_tracked_failure_invokes_permanent_failure_callback(self, tmp_path) -> None:
        class FailSendChannel(FakeChannel):
            async def send(self, msg: OutboundMessage) -> str | None:
                raise RuntimeError("send failed")

        callback = AsyncMock()
        dlq_dir = tmp_path / "dlq"
        dlq_dir.mkdir()
        bus = MessageBus(dlq_dir=dlq_dir, on_permanent_failure=callback)
        bus.register_channel(FailSendChannel())
        await bus.start()
        try:
            result = await bus.send_tracked(_make_out())
            assert result is None
            callback.assert_awaited_once()
            assert callback.await_args.args[1] == "send failed"
            dlq_messages = await bus.get_dlq_messages()
            assert len(dlq_messages) == 1
            assert dlq_messages[0].channel == "fake"
            assert bus._dlq is not None
            await bus._dlq._process_failed_messages()
            callback.assert_awaited_once()
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_send_tracked_failure_skips_duplicate_callback_with_ledger(self, tmp_path) -> None:
        class FailSendChannel(FakeChannel):
            async def send(self, msg: OutboundMessage) -> str | None:
                raise RuntimeError("send failed")

        callback = AsyncMock()
        dlq_dir = tmp_path / "dlq"
        dlq_dir.mkdir()
        ledger_path = tmp_path / "ledger.db"
        from app.channels.reliability.delivery_notify_ledger import SqliteDeliveryNotifyLedger

        ledger = SqliteDeliveryNotifyLedger(ledger_path)
        bus = MessageBus(
            dlq_dir=dlq_dir,
            on_permanent_failure=callback,
            notification_ledger=ledger,
        )
        bus.register_channel(FailSendChannel())
        await bus.start()
        try:
            await bus.send_tracked(_make_out())
            callback.assert_awaited_once()
            callback.reset_mock()

            await bus._dlq._process_failed_messages()
            callback.assert_not_awaited()

            bus2 = MessageBus(
                dlq_dir=dlq_dir,
                on_permanent_failure=callback,
                notification_ledger=SqliteDeliveryNotifyLedger(ledger_path),
            )
            bus2.register_channel(FailSendChannel())
            await bus2.start()
            try:
                await bus2._dlq._process_failed_messages()
                callback.assert_not_awaited()
            finally:
                await bus2.stop()
        finally:
            await bus.stop()
            ledger.close()

    @pytest.mark.asyncio
    async def test_send_tracked_failure_presync_notified_merged_on_start(self, tmp_path) -> None:
        class FailSendChannel(FakeChannel):
            async def send(self, msg: OutboundMessage) -> str | None:
                raise RuntimeError("send failed")

        callback = AsyncMock()
        dlq_dir = tmp_path / "dlq"
        dlq_dir.mkdir()
        bus = MessageBus(dlq_dir=dlq_dir, on_permanent_failure=callback)
        bus.register_channel(FailSendChannel())
        await bus.send_tracked(_make_out())
        assert len(bus._presync_notified_delivery_ids) == 1
        await bus.start()
        try:
            assert bus._presync_notified_delivery_ids == set()
            assert bus._dlq is not None
            await bus._dlq._process_failed_messages()
            callback.assert_awaited_once()
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_record_outbound_failure_callback_without_dlq_dir(self) -> None:
        callback = AsyncMock()
        bus = MessageBus(on_permanent_failure=callback)
        await bus._record_outbound_failure(_make_out(), "send failed", retries_exhausted=True)
        callback.assert_awaited_once()
        assert callback.await_args.args[1] == "send failed"

    @pytest.mark.asyncio
    async def test_record_outbound_failure_callback_exception_does_not_raise(self, tmp_path) -> None:
        async def failing_callback(_delivery: object, _error: str) -> None:
            raise RuntimeError("callback failed")

        dlq_dir = tmp_path / "dlq"
        dlq_dir.mkdir()
        bus = MessageBus(dlq_dir=dlq_dir, on_permanent_failure=failing_callback)
        await bus._record_outbound_failure(_make_out(), "send failed", retries_exhausted=True)

    @pytest.mark.asyncio
    async def test_edit_message_exception_returns_false(self) -> None:
        class FailEditChannel(FakeChannel):
            async def edit_message(self, chat_id: str, message_id: str, content: str) -> None:
                raise RuntimeError("edit failed")

        bus = MessageBus()
        ch = FailEditChannel()
        bus.register_channel(ch)
        result = await bus.edit_channel_message("fake", "c1", "m1", "new")
        assert result is False

    @pytest.mark.asyncio
    async def test_dispatch_to_unknown_channel_drops(self) -> None:
        bus = MessageBus()
        ch = FakeChannel()
        bus.register_channel(ch)
        await bus.start()
        try:
            await bus.publish_outbound(_make_out(channel="nonexistent"))
            await asyncio.sleep(0.15)
            assert len(ch.sent) == 0
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_dispatch_send_failure_records_error(self) -> None:
        class FailDispatchChannel(FakeChannel):
            async def send(self, msg: OutboundMessage) -> str | None:
                raise RuntimeError("dispatch fail")

        bus = MessageBus()
        ch = FailDispatchChannel()
        bus.register_channel(ch)
        await bus.start()
        try:
            await bus.publish_outbound(_make_out())
            await asyncio.sleep(0.5)
            assert ch.activity.total_errors > 0
        finally:
            await bus.stop()

    def test_unregister_channel(self) -> None:
        bus = MessageBus()
        ch = FakeChannel()
        bus.register_channel(ch)
        assert bus.get_channel("fake") is ch
        removed = bus.unregister_channel("fake")
        assert removed is ch
        assert bus.get_channel("fake") is None

    def test_unregister_unknown_returns_none(self) -> None:
        bus = MessageBus()
        removed = bus.unregister_channel("nonexistent")
        assert removed is None


class TestOutboundRiskGate:
    """Tests for _apply_outbound_risk_gate in bus.py."""

    def test_passthrough_when_no_rules(self) -> None:
        from unittest.mock import patch

        from app.channels.core.bus import _apply_outbound_risk_gate

        msg = _make_out(content="secret phone 13812345678")
        with patch("app.services.risk.detection.get_detection_service") as mock_svc:
            mock_svc.return_value.rule_count = 0
            result = _apply_outbound_risk_gate(msg)
        assert result is msg

    def test_passthrough_when_empty_content(self) -> None:
        from app.channels.core.bus import _apply_outbound_risk_gate

        msg = _make_out(content="")
        result = _apply_outbound_risk_gate(msg)
        assert result is msg

    def test_blocks_matching_content(self) -> None:
        from unittest.mock import patch

        from app.channels.core.bus import _apply_outbound_risk_gate
        from app.services.risk.detection import DetectionResult, RiskMatch

        msg = _make_out(content="My phone is 13812345678")
        match = RiskMatch(
            rule_id="r1",
            display_name="CN Mobile",
            severity="high",
            action="block",
            category="pii",
            match_summary="13812345678",
        )
        blocked_result = DetectionResult(blocked=True, matches=(match,))

        with patch("app.services.risk.detection.get_detection_service") as mock_svc:
            mock_svc.return_value.rule_count = 5
            mock_svc.return_value.detect.return_value = blocked_result
            result = _apply_outbound_risk_gate(msg)

        assert result is not msg
        assert "13812345678" not in result.content
        assert result.channel == msg.channel
        assert result.recipient_id == msg.recipient_id

    def test_passthrough_when_no_match(self) -> None:
        from unittest.mock import patch

        from app.channels.core.bus import _apply_outbound_risk_gate
        from app.services.risk.detection import DetectionResult

        msg = _make_out(content="Safe message without sensitive data")
        no_match = DetectionResult(blocked=False, matches=())

        with patch("app.services.risk.detection.get_detection_service") as mock_svc:
            mock_svc.return_value.rule_count = 5
            mock_svc.return_value.detect.return_value = no_match
            result = _apply_outbound_risk_gate(msg)

        assert result is msg

    @pytest.mark.asyncio
    async def test_dispatch_loop_applies_risk_gate(self) -> None:
        """Integration: blocked message is replaced before reaching channel.send()."""
        from unittest.mock import patch

        from app.services.risk.detection import DetectionResult, RiskMatch

        match = RiskMatch(
            rule_id="r1",
            display_name="DB Credential",
            severity="critical",
            action="block",
            category="credential",
            match_summary="postgres://admin:***",
        )
        blocked_result = DetectionResult(blocked=True, matches=(match,))

        bus = MessageBus()
        ch = FakeChannel()
        bus.register_channel(ch)
        await bus.start()

        try:
            with patch("app.services.risk.detection.get_detection_service") as mock_svc:
                mock_svc.return_value.rule_count = 5
                mock_svc.return_value.detect.return_value = blocked_result
                await bus.publish_outbound(
                    _make_out(content="postgres://admin:secret@db.internal:5432/prod")
                )
                await asyncio.sleep(0.2)

            assert len(ch.sent) == 1
            assert "postgres://" not in ch.sent[0].content
            assert "secret" not in ch.sent[0].content
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_send_tracked_applies_risk_gate(self) -> None:
        """send_tracked also applies outbound risk gate."""
        from unittest.mock import patch

        from app.services.risk.detection import DetectionResult, RiskMatch

        match = RiskMatch(
            rule_id="r2",
            display_name="API Key",
            severity="critical",
            action="block",
            category="credential",
            match_summary="sk-abc***",
        )
        blocked_result = DetectionResult(blocked=True, matches=(match,))

        bus = MessageBus()
        ch = FakeChannel()
        bus.register_channel(ch)

        with patch("app.services.risk.detection.get_detection_service") as mock_svc:
            mock_svc.return_value.rule_count = 3
            mock_svc.return_value.detect.return_value = blocked_result
            msg_id = await bus.send_tracked(
                _make_out(content="Your API key is sk-abc123def456")
            )

        assert msg_id is not None
        assert len(ch.sent) == 1
        assert "sk-abc123def456" not in ch.sent[0].content
