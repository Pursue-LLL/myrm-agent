"""Tests for cron default delivery resolution in tool_setup."""

from __future__ import annotations

from myrm_agent_harness.toolkits.cron.types import DeliveryConfig

from app.ai_agents.general_agent.tool_setup import ToolSetupMixin


class _DeliveryProbe(ToolSetupMixin):
    def __init__(self, *, channel_name: str, chat_id: str | None = None) -> None:
        self.channel_name = channel_name
        self.chat_id = chat_id
        self.memory_conversation_id = chat_id


def test_web_chat_default_delivery_is_none() -> None:
    probe = _DeliveryProbe(channel_name="web_chat", chat_id="chat-1")
    assert probe._resolve_cron_default_delivery() is None


def test_telegram_with_recipient_uses_channel_delivery() -> None:
    probe = _DeliveryProbe(channel_name="telegram", chat_id="tg-user-42")
    delivery = probe._resolve_cron_default_delivery()
    assert delivery == DeliveryConfig(channel="telegram", target="tg-user-42")
