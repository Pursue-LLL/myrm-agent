"""Tests for ChannelSkillCommandHandler — verifies [use skill_id] rewriting."""

from __future__ import annotations

import pytest

from app.channels.types.messages import InboundMessage
from app.core.channel_bridge.skill_command_handler import ChannelSkillCommandHandler


def _make_msg(content: str = "/daily-report") -> InboundMessage:
    return InboundMessage(channel="test", sender_id="u1", content=content)


@pytest.fixture
def handler() -> ChannelSkillCommandHandler:
    return ChannelSkillCommandHandler()


class TestChannelSkillCommandHandler:
    @pytest.mark.asyncio
    async def test_rewrite_with_args(self, handler: ChannelSkillCommandHandler) -> None:
        result = await handler(_make_msg(), "daily_report_skill", "generate today's report")
        assert result is not None
        assert result.content == "[use daily_report_skill] generate today's report"

    @pytest.mark.asyncio
    async def test_rewrite_without_args(self, handler: ChannelSkillCommandHandler) -> None:
        result = await handler(_make_msg(), "deploy_skill", "")
        assert result is not None
        assert result.content == "[use deploy_skill]"

    @pytest.mark.asyncio
    async def test_empty_skill_id_returns_none(self, handler: ChannelSkillCommandHandler) -> None:
        result = await handler(_make_msg(), "", "some args")
        assert result is None

    @pytest.mark.asyncio
    async def test_preserves_original_fields(self, handler: ChannelSkillCommandHandler) -> None:
        msg = InboundMessage(
            channel="telegram",
            sender_id="user123",
            content="/deploy",
            chat_id="chat456",
        )
        result = await handler(msg, "deploy_skill", "staging")
        assert result is not None
        assert result.channel == "telegram"
        assert result.sender_id == "user123"
        assert result.chat_id == "chat456"
        assert result.content == "[use deploy_skill] staging"

    @pytest.mark.asyncio
    async def test_whitespace_only_args(self, handler: ChannelSkillCommandHandler) -> None:
        result = await handler(_make_msg(), "test_skill", "   ")
        assert result is not None
        assert result.content == "[use test_skill]"

    @pytest.mark.asyncio
    async def test_hyphenated_skill_id(self, handler: ChannelSkillCommandHandler) -> None:
        result = await handler(_make_msg(), "my-great-skill", "do stuff")
        assert result is not None
        assert result.content == "[use my-great-skill] do stuff"
