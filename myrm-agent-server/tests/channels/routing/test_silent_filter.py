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
