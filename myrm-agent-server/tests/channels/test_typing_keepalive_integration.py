"""Integration tests for typing keepalive — real ChannelCapabilities, no mock on critical path."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.routing.message_effects import MessageEffects
from app.channels.types import ChannelCapabilities


EXPECTED_KEEPALIVE: dict[str, float] = {
    "telegram": 4.0,
    "discord": 8.0,
    "whatsapp": 20.0,
    "signal": 4.0,
    "wechat_ilink": 5.0,
    "imessage": 55.0,
}

NO_TYPING_CHANNELS = ("dingtalk", "wecom", "feishu", "slack")


class TestRealChannelCapabilities:
    """Verify real channel classes expose correct typing capabilities."""

    def test_telegram_capabilities(self) -> None:
        from app.channels.providers.telegram.channel import TelegramChannel

        caps = TelegramChannel.capabilities
        assert caps.typing_indicator is True
        assert caps.typing_keepalive_interval == 4.0

    def test_discord_capabilities(self) -> None:
        from app.channels.providers.discord.channel import DiscordChannel

        caps = DiscordChannel.capabilities
        assert caps.typing_indicator is True
        assert caps.typing_keepalive_interval == 8.0

    def test_whatsapp_capabilities(self) -> None:
        from app.channels.providers.whatsapp.channel import WhatsAppChannel

        caps = WhatsAppChannel.capabilities
        assert caps.typing_indicator is True
        assert caps.typing_keepalive_interval == 20.0

    def test_signal_capabilities(self) -> None:
        from app.channels.providers.signal.channel import SignalChannel

        caps = SignalChannel.capabilities
        assert caps.typing_indicator is True
        assert caps.typing_keepalive_interval == 4.0

    def test_wechat_ilink_capabilities(self) -> None:
        from app.channels.providers.wechat.ilink_channel import WeChatILinkChannel

        caps = WeChatILinkChannel.capabilities
        assert caps.typing_indicator is True
        assert caps.typing_keepalive_interval == 5.0

    def test_imessage_capabilities(self) -> None:
        from app.channels.providers.imessage.channel import IMessageChannel

        caps = IMessageChannel.capabilities
        assert caps.typing_indicator is True
        assert caps.typing_keepalive_interval == 55.0

    def test_dingtalk_no_typing(self) -> None:
        from app.channels.providers.dingtalk.channel import DingTalkChannel

        assert DingTalkChannel.capabilities.typing_indicator is False

    def test_wecom_no_typing(self) -> None:
        from app.channels.providers.wecom.channel import WeComChannel

        assert WeComChannel.capabilities.typing_indicator is False

    def test_feishu_no_typing(self) -> None:
        from app.channels.providers.feishu.channel import FeishuChannel

        assert FeishuChannel.capabilities.typing_indicator is False

    def test_slack_no_typing(self) -> None:
        from app.channels.providers.slack.channel import SlackChannel

        assert SlackChannel.capabilities.typing_indicator is False


class TestKeepaliveIntegration:
    """End-to-end: real ChannelCapabilities → MessageEffects → asyncio task lifecycle."""

    @staticmethod
    def _build_fx_with_real_caps(
        interval: float,
    ) -> tuple[MessageEffects, MagicMock]:
        """Wire real ChannelCapabilities into MessageEffects via a minimal bus stub."""
        bus = MagicMock()
        ch = MagicMock()
        ch.capabilities = ChannelCapabilities(
            typing_indicator=True,
            typing_keepalive_interval=interval,
        )
        ch.start_typing = AsyncMock()
        ch.stop_typing = AsyncMock()
        bus.get_channel.return_value = ch
        return MessageEffects(bus), ch

    @pytest.mark.asyncio
    async def test_telegram_keepalive_lifecycle(self) -> None:
        fx, ch = self._build_fx_with_real_caps(4.0)
        fx.start_typing_keepalive("telegram", "chat-1")
        assert "telegram:chat-1" in fx._typing_keepalive_tasks
        task = fx._typing_keepalive_tasks["telegram:chat-1"]
        assert not task.done()
        await fx.stop_typing_keepalive("telegram", "chat-1")
        assert "telegram:chat-1" not in fx._typing_keepalive_tasks

    @pytest.mark.asyncio
    async def test_zero_interval_no_task(self) -> None:
        fx, _ = self._build_fx_with_real_caps(0.0)
        fx.start_typing_keepalive("dingtalk", "chat-1")
        assert len(fx._typing_keepalive_tasks) == 0

    @pytest.mark.asyncio
    async def test_keepalive_actually_calls_start_typing(self) -> None:
        """With tiny interval, verify start_typing is called periodically."""
        fx, ch = self._build_fx_with_real_caps(0.03)
        fx.start_typing_keepalive("test", "c1")
        await asyncio.sleep(0.12)
        assert ch.start_typing.call_count >= 2
        await fx.stop_typing_keepalive("test", "c1")
        final_count = ch.start_typing.call_count
        await asyncio.sleep(0.08)
        assert ch.start_typing.call_count == final_count

    @pytest.mark.asyncio
    async def test_error_resilience_in_keepalive(self) -> None:
        """Task survives exceptions from start_typing."""
        fx, ch = self._build_fx_with_real_caps(0.03)
        ch.start_typing = AsyncMock(side_effect=RuntimeError("network"))
        fx.start_typing_keepalive("test", "c1")
        await asyncio.sleep(0.1)
        task = fx._typing_keepalive_tasks.get("test:c1")
        assert task is not None and not task.done()
        await fx.stop_typing_keepalive("test", "c1")

    @pytest.mark.asyncio
    async def test_concurrent_channels_independent(self) -> None:
        """Multiple channels can run keepalive concurrently without interference."""
        fx_tg, ch_tg = self._build_fx_with_real_caps(0.03)
        bus = MagicMock()
        ch_dc = MagicMock()
        ch_dc.capabilities = ChannelCapabilities(
            typing_indicator=True, typing_keepalive_interval=0.05
        )
        ch_dc.start_typing = AsyncMock()
        ch_dc.stop_typing = AsyncMock()
        bus.get_channel.return_value = ch_dc
        fx_dc = MessageEffects(bus)

        fx_tg.start_typing_keepalive("telegram", "c1")
        fx_dc.start_typing_keepalive("discord", "c2")

        await asyncio.sleep(0.12)
        assert ch_tg.start_typing.call_count >= 2
        assert ch_dc.start_typing.call_count >= 1

        await fx_tg.stop_typing_keepalive("telegram", "c1")
        await fx_dc.stop_typing_keepalive("discord", "c2")

        assert len(fx_tg._typing_keepalive_tasks) == 0
        assert len(fx_dc._typing_keepalive_tasks) == 0

    @pytest.mark.asyncio
    async def test_negative_interval_noop(self) -> None:
        """Negative interval treated same as zero — no task created."""
        fx, _ = self._build_fx_with_real_caps(-1.0)
        fx.start_typing_keepalive("ch", "cid")
        assert len(fx._typing_keepalive_tasks) == 0

    @pytest.mark.asyncio
    async def test_restart_after_done_task(self) -> None:
        """When a previous task has finished, a new start should create a fresh task."""
        fx, ch = self._build_fx_with_real_caps(0.02)
        fx.start_typing_keepalive("ch", "cid")
        first_task = fx._typing_keepalive_tasks["ch:cid"]
        first_task.cancel()
        try:
            await first_task
        except asyncio.CancelledError:
            pass
        assert first_task.done()
        fx.start_typing_keepalive("ch", "cid")
        second_task = fx._typing_keepalive_tasks["ch:cid"]
        assert second_task is not first_task
        assert not second_task.done()
        await fx.stop_typing_keepalive("ch", "cid")

    @pytest.mark.asyncio
    async def test_full_router_flow_set_typing_plus_keepalive(self) -> None:
        """Simulate the exact router_execution call sequence."""
        fx, ch = self._build_fx_with_real_caps(0.03)
        await fx.set_typing("ch", "cid", composing=True)
        ch.start_typing.assert_called_once_with("cid")
        fx.start_typing_keepalive("ch", "cid")
        assert "ch:cid" in fx._typing_keepalive_tasks
        await asyncio.sleep(0.08)
        assert ch.start_typing.call_count >= 2
        await fx.stop_typing_keepalive("ch", "cid")
        await fx.set_typing("ch", "cid", composing=False)
        ch.stop_typing.assert_called_once_with("cid")
        assert "ch:cid" not in fx._typing_keepalive_tasks

    @pytest.mark.asyncio
    async def test_no_typing_channel_set_typing_is_noop(self) -> None:
        """For channels with typing_indicator=False, set_typing still calls BaseChannel no-op."""
        bus = MagicMock()
        ch = MagicMock()
        ch.capabilities = ChannelCapabilities(typing_indicator=False)
        ch.start_typing = AsyncMock()
        ch.stop_typing = AsyncMock()
        bus.get_channel.return_value = ch
        fx = MessageEffects(bus)
        await fx.set_typing("dingtalk", "cid", composing=True)
        ch.start_typing.assert_called_once_with("cid")
        fx.start_typing_keepalive("dingtalk", "cid")
        assert len(fx._typing_keepalive_tasks) == 0

    @pytest.mark.asyncio
    async def test_memory_cleanup_after_stop(self) -> None:
        """Verify no memory leaks — task dict is empty after stop."""
        fx, _ = self._build_fx_with_real_caps(0.03)
        for i in range(5):
            fx.start_typing_keepalive("ch", f"cid-{i}")
        assert len(fx._typing_keepalive_tasks) == 5
        for i in range(5):
            await fx.stop_typing_keepalive("ch", f"cid-{i}")
        assert len(fx._typing_keepalive_tasks) == 0

    @pytest.mark.asyncio
    async def test_stop_idempotent(self) -> None:
        """Calling stop twice should not raise."""
        fx, _ = self._build_fx_with_real_caps(0.03)
        fx.start_typing_keepalive("ch", "cid")
        await fx.stop_typing_keepalive("ch", "cid")
        await fx.stop_typing_keepalive("ch", "cid")

    @pytest.mark.asyncio
    async def test_typing_only_no_keepalive(self) -> None:
        """Channels with typing_indicator=True but interval=0 get single typing, no keepalive."""
        fx, ch = self._build_fx_with_real_caps(0.0)
        await fx.set_typing("msteams", "cid", composing=True)
        ch.start_typing.assert_called_once_with("cid")
        fx.start_typing_keepalive("msteams", "cid")
        assert len(fx._typing_keepalive_tasks) == 0
        count_after = ch.start_typing.call_count
        await asyncio.sleep(0.05)
        assert ch.start_typing.call_count == count_after


class TestRealChannelTypingOnlyNoKeepalive:
    """Channels with start_typing impl but no keepalive configured."""

    def test_matrix_typing_no_keepalive(self) -> None:
        from app.channels.providers.matrix.channel import MatrixChannel

        caps = MatrixChannel.capabilities
        assert caps.typing_indicator is True
        assert caps.typing_keepalive_interval == 0.0

    def test_msteams_typing_no_keepalive(self) -> None:
        from app.channels.providers.msteams.channel import MSTeamsChannel

        caps = MSTeamsChannel.capabilities
        assert caps.typing_indicator is True
        assert caps.typing_keepalive_interval == 0.0

    def test_qq_typing_no_keepalive(self) -> None:
        from app.channels.providers.qq.channel import QQChannel

        caps = QQChannel.capabilities
        assert caps.typing_indicator is True
        assert caps.typing_keepalive_interval == 0.0

    def test_line_typing_default_true_no_keepalive(self) -> None:
        from app.channels.providers.line.channel import LINEChannel

        caps = LINEChannel.capabilities
        assert caps.typing_indicator is True
        assert caps.typing_keepalive_interval == 0.0
