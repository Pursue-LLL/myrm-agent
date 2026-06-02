"""AgentRouter locale enrichment and localized slash-command reply tests."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.routing.command_defs import CommandAction
from app.channels.routing.router import AgentRouter
from app.channels.types import InboundMessage


def _make_bus(channel: MagicMock | None = None) -> MagicMock:
    bus = MagicMock()
    bus.publish_outbound = AsyncMock()
    bus.get_channel = MagicMock(return_value=channel)
    return bus


def _make_router(
    *,
    bus: MagicMock | None = None,
    locale_provider: object | None = None,
) -> AgentRouter:
    bus = bus or _make_bus()
    return AgentRouter(
        bus=bus,
        pairing_store=MagicMock(),
        agent_executor=MagicMock(),
        locale_provider=locale_provider,
    )


class _FixedLocaleProvider:
    def __init__(self, locale: str) -> None:
        self._locale = locale

    async def resolve_locale(self, msg: InboundMessage) -> str:
        del msg
        return self._locale


@pytest.mark.asyncio
async def test_enrich_message_locale_from_provider() -> None:
    router = _make_router(locale_provider=_FixedLocaleProvider("zh-CN"))
    msg = InboundMessage(channel="telegram", sender_id="u1", content="/help")
    enriched = await router._enrich_message_locale(msg)
    assert enriched.metadata["locale"] == "zh-CN"


@pytest.mark.asyncio
async def test_enrich_message_locale_preserves_existing() -> None:
    router = _make_router(locale_provider=_FixedLocaleProvider("zh-CN"))
    msg = InboundMessage(
        channel="telegram",
        sender_id="u1",
        content="/help",
        metadata={"locale": "en"},
    )
    enriched = await router._enrich_message_locale(msg)
    assert enriched.metadata["locale"] == "en"


@pytest.mark.asyncio
async def test_enrich_message_locale_user_overrides_platform_on_neutral_channel() -> None:
    ch = MagicMock()
    ch.extract_sender_locale = MagicMock(return_value="zh-CN")
    bus = _make_bus(ch)
    router = _make_router(bus=bus, locale_provider=_FixedLocaleProvider("en"))
    msg = InboundMessage(channel="telegram", sender_id="u1", content="/help")
    enriched = await router._enrich_message_locale(msg)
    assert enriched.metadata["platform_locale"] == "zh-CN"
    # platform_locale wins over user_locale per resolve_locale priority
    assert enriched.metadata["locale"] == "zh-CN"


@pytest.mark.asyncio
async def test_enrich_message_locale_feishu_defaults_zh_without_user_pref() -> None:
    bus = _make_bus(None)
    router = _make_router(bus=bus, locale_provider=None)
    msg = InboundMessage(channel="feishu", sender_id="u1", content="/help")
    enriched = await router._enrich_message_locale(msg)
    assert enriched.metadata["locale"] == "zh-CN"


@pytest.mark.asyncio
async def test_enrich_message_locale_user_pref_overrides_feishu_default() -> None:
    bus = _make_bus(None)
    router = _make_router(bus=bus, locale_provider=_FixedLocaleProvider("en"))
    msg = InboundMessage(channel="feishu", sender_id="u1", content="/help")
    enriched = await router._enrich_message_locale(msg)
    assert enriched.metadata["locale"] == "en"


@pytest.mark.asyncio
async def test_help_command_reply_is_localized_zh() -> None:
    bus = _make_bus()
    router = _make_router(bus=bus)
    msg = InboundMessage(
        channel="telegram",
        sender_id="u1",
        content="/help",
        metadata={"locale": "zh-CN"},
    )
    await router._handle_help_command(msg)
    bus.publish_outbound.assert_called_once()
    content = bus.publish_outbound.call_args[0][0].content
    assert "可用命令" in content


@pytest.mark.asyncio
async def test_status_command_reply_is_localized_zh() -> None:
    bus = _make_bus()
    router = _make_router(bus=bus)
    msg = InboundMessage(
        channel="telegram",
        sender_id="u1",
        content="/status",
        metadata={"locale": "zh-CN"},
    )
    await router._handle_status_command(msg)
    bus.publish_outbound.assert_called_once()
    content = bus.publish_outbound.call_args[0][0].content
    assert "会话状态" in content or "状态" in content


@pytest.mark.asyncio
async def test_dispatch_help_action() -> None:
    bus = _make_bus()
    router = _make_router(bus=bus)
    msg = InboundMessage(
        channel="telegram",
        sender_id="u1",
        content="/help",
        metadata={"locale": "en"},
    )
    handled = await router._dispatch_system_command(msg, CommandAction.HELP, "")
    assert handled is True
    await asyncio.sleep(0.05)
    bus.publish_outbound.assert_called()
