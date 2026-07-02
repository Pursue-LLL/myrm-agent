"""Unit tests for outbound [SILENT] content filtering in router_execution."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.channels.routing.router_constants import _is_silent_content


class TestIsSilentContent:
    """Pure function tests for _is_silent_content."""

    @pytest.mark.parametrize(
        "text",
        [
            "[SILENT]",
            "  [SILENT]  ",
            "\n[SILENT]\n",
            "```\n[SILENT]\n```",
            "```text\n[SILENT]\n```",
            "[SILENT]\n[SILENT]",
            "[SILENT]\n\n[SILENT]",
            "\t[SILENT]\t",
        ],
    )
    def test_silent_variants(self, text: str) -> None:
        assert _is_silent_content(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            None,
            "",
            "   ",
            "Hello world",
            "[SILENT] nothing to report",
            "The token [SILENT] appears in text",
            "SILENT",
            "[silent]",
            "[SILENT] \n extra content",
            "[SILENT].",
            "> [SILENT]",
            "```\n[SILENT]\n```\nExtra after fence",
        ],
    )
    def test_non_silent_variants(self, text: str) -> None:
        assert _is_silent_content(text) is False


class TestDeliverAgentResultSilentFilter:
    """Integration test: _deliver_agent_result suppresses silent output."""

    def _make_mixin(self) -> tuple:
        from app.channels.routing.router_execution import RouterExecutionMixin

        fx = AsyncMock()
        bus = AsyncMock()
        mixin = RouterExecutionMixin()
        mixin._fx = fx  # type: ignore[attr-defined]
        mixin._bus = bus  # type: ignore[attr-defined]
        mixin._voice = None  # type: ignore[attr-defined]
        return mixin, fx, bus

    @pytest.mark.asyncio
    async def test_silent_result_with_placeholder_cleans_up(self) -> None:
        from app.channels.types import InboundMessage, OutboundMessage

        mixin, fx, bus = self._make_mixin()

        result = OutboundMessage(
            channel="telegram",
            recipient_id="chat1",
            content="[SILENT]",
            user_id="u1",
        )

        deferred = AsyncMock()
        deferred.resolve_for_delivery = AsyncMock(return_value="ph_123")

        msg = InboundMessage(
            channel="telegram",
            sender_id="u1",
            content="@bot hello",
            message_id="m1",
        )

        await mixin._deliver_agent_result(
            result=result,
            deferred=deferred,
            msg=msg,
            chat_id="chat1",
            last_progress_at=0.0,
            inbound_had_voice=False,
        )

        fx.cleanup_placeholder.assert_called_once_with(
            "telegram", "chat1", "ph_123", "\u200b"
        )
        bus.publish_outbound.assert_not_called()
        fx.edit_placeholder.assert_not_called()

    @pytest.mark.asyncio
    async def test_silent_result_without_placeholder_returns_silently(self) -> None:
        from app.channels.types import InboundMessage, OutboundMessage

        mixin, fx, bus = self._make_mixin()

        result = OutboundMessage(
            channel="telegram",
            recipient_id="chat1",
            content="  [SILENT]  ",
            user_id="u1",
        )

        deferred = AsyncMock()
        deferred.resolve_for_delivery = AsyncMock(return_value=None)

        msg = InboundMessage(
            channel="telegram",
            sender_id="u1",
            content="@bot hello",
            message_id="m1",
        )

        await mixin._deliver_agent_result(
            result=result,
            deferred=deferred,
            msg=msg,
            chat_id="chat1",
            last_progress_at=0.0,
            inbound_had_voice=False,
        )

        fx.cleanup_placeholder.assert_not_called()
        bus.publish_outbound.assert_not_called()
        fx.edit_placeholder.assert_not_called()

    @pytest.mark.asyncio
    async def test_normal_result_passes_through(self) -> None:
        from app.channels.types import InboundMessage, OutboundMessage

        mixin, fx, bus = self._make_mixin()

        result = OutboundMessage(
            channel="telegram",
            recipient_id="chat1",
            content="Here is your answer.",
            user_id="u1",
        )

        deferred = AsyncMock()
        deferred.resolve_for_delivery = AsyncMock(return_value=None)

        msg = InboundMessage(
            channel="telegram",
            sender_id="u1",
            content="@bot hello",
            message_id="m1",
        )

        await mixin._deliver_agent_result(
            result=result,
            deferred=deferred,
            msg=msg,
            chat_id="chat1",
            last_progress_at=0.0,
            inbound_had_voice=False,
        )

        bus.publish_outbound.assert_called_once()

    @pytest.mark.asyncio
    async def test_markdown_fence_silent_suppressed_at_deliver_level(self) -> None:
        """Markdown-wrapped [SILENT] is filtered at the routing delivery layer."""
        from app.channels.types import InboundMessage, OutboundMessage

        mixin, fx, bus = self._make_mixin()

        result = OutboundMessage(
            channel="feishu",
            recipient_id="group-42",
            content="```\n[SILENT]\n```",
            user_id="u2",
        )

        deferred = AsyncMock()
        deferred.resolve_for_delivery = AsyncMock(return_value="ph_md")

        msg = InboundMessage(
            channel="feishu",
            sender_id="u2",
            content="@bot 定期报告",
            message_id="m2",
            is_group=True,
        )

        await mixin._deliver_agent_result(
            result=result,
            deferred=deferred,
            msg=msg,
            chat_id="group-42",
            last_progress_at=0.0,
            inbound_had_voice=False,
        )

        fx.cleanup_placeholder.assert_called_once_with(
            "feishu", "group-42", "ph_md", "\u200b"
        )
        bus.publish_outbound.assert_not_called()

    @pytest.mark.asyncio
    async def test_silent_with_voice_flag_skips_tts(self) -> None:
        """Even when inbound had voice, silent output must not trigger TTS."""
        from app.channels.types import InboundMessage, OutboundMessage

        mixin, fx, bus = self._make_mixin()
        mixin._voice = AsyncMock()  # type: ignore[attr-defined]

        result = OutboundMessage(
            channel="telegram",
            recipient_id="chat3",
            content="[SILENT]",
            user_id="u3",
        )

        deferred = AsyncMock()
        deferred.resolve_for_delivery = AsyncMock(return_value=None)

        msg = InboundMessage(
            channel="telegram",
            sender_id="u3",
            content="@bot status",
            message_id="m3",
        )

        await mixin._deliver_agent_result(
            result=result,
            deferred=deferred,
            msg=msg,
            chat_id="chat3",
            last_progress_at=0.0,
            inbound_had_voice=True,
        )

        bus.publish_outbound.assert_not_called()
        fx.edit_placeholder.assert_not_called()

    @pytest.mark.asyncio
    async def test_normal_result_with_placeholder_edits_message(self) -> None:
        """Non-silent result with placeholder goes through edit_placeholder path."""
        from app.channels.types import InboundMessage, OutboundMessage

        mixin, fx, bus = self._make_mixin()

        result = OutboundMessage(
            channel="discord",
            recipient_id="ch-5",
            content="Task completed successfully.",
            user_id="u5",
        )

        deferred = AsyncMock()
        deferred.resolve_for_delivery = AsyncMock(return_value="ph_edit")

        msg = InboundMessage(
            channel="discord",
            sender_id="u5",
            content="!run task",
            message_id="m5",
        )

        await mixin._deliver_agent_result(
            result=result,
            deferred=deferred,
            msg=msg,
            chat_id="ch-5",
            last_progress_at=0.0,
            inbound_had_voice=False,
        )

        fx.edit_placeholder.assert_called_once()
        bus.publish_outbound.assert_not_called()
