"""Tests for ChannelSkillCommandHandler — verifies [use skill_id(s)] rewriting.

Covers single-skill, multi-skill bundle, instruction injection, and edge cases.
"""

from __future__ import annotations

import pytest

from app.channels.types.messages import InboundMessage
from app.core.channel_bridge.skill_command_handler import ChannelSkillCommandHandler


def _make_msg(content: str = "/daily-report") -> InboundMessage:
    return InboundMessage(channel="test", sender_id="u1", content=content)


@pytest.fixture
def handler() -> ChannelSkillCommandHandler:
    return ChannelSkillCommandHandler()


class TestSingleSkillRewrite:
    @pytest.mark.asyncio
    async def test_rewrite_with_args(self, handler: ChannelSkillCommandHandler) -> None:
        result = await handler(
            _make_msg(), skill_ids=("daily_report_skill",), user_args="generate today's report"
        )
        assert result is not None
        assert result.content == "[use daily_report_skill] generate today's report"

    @pytest.mark.asyncio
    async def test_rewrite_without_args(self, handler: ChannelSkillCommandHandler) -> None:
        result = await handler(_make_msg(), skill_ids=("deploy_skill",), user_args="")
        assert result is not None
        assert result.content == "[use deploy_skill]"

    @pytest.mark.asyncio
    async def test_whitespace_only_args(self, handler: ChannelSkillCommandHandler) -> None:
        result = await handler(_make_msg(), skill_ids=("test_skill",), user_args="   ")
        assert result is not None
        assert result.content == "[use test_skill]"

    @pytest.mark.asyncio
    async def test_hyphenated_skill_id(self, handler: ChannelSkillCommandHandler) -> None:
        result = await handler(
            _make_msg(), skill_ids=("my-great-skill",), user_args="do stuff"
        )
        assert result is not None
        assert result.content == "[use my-great-skill] do stuff"

    @pytest.mark.asyncio
    async def test_preserves_original_fields(self, handler: ChannelSkillCommandHandler) -> None:
        msg = InboundMessage(
            channel="telegram",
            sender_id="user123",
            content="/deploy",
            chat_id="chat456",
        )
        result = await handler(msg, skill_ids=("deploy_skill",), user_args="staging")
        assert result is not None
        assert result.channel == "telegram"
        assert result.sender_id == "user123"
        assert result.chat_id == "chat456"
        assert result.content == "[use deploy_skill] staging"


class TestEmptySkillIds:
    @pytest.mark.asyncio
    async def test_empty_tuple_returns_none(self, handler: ChannelSkillCommandHandler) -> None:
        result = await handler(_make_msg(), skill_ids=(), user_args="some args")
        assert result is None


class TestMultiSkillBundle:
    @pytest.mark.asyncio
    async def test_two_skills(self, handler: ChannelSkillCommandHandler) -> None:
        result = await handler(
            _make_msg(), skill_ids=("skill_a", "skill_b"), user_args="run both"
        )
        assert result is not None
        assert result.content == "[use skill_a,skill_b] run both"

    @pytest.mark.asyncio
    async def test_three_skills_no_args(self, handler: ChannelSkillCommandHandler) -> None:
        result = await handler(
            _make_msg(), skill_ids=("a", "b", "c"), user_args=""
        )
        assert result is not None
        assert result.content == "[use a,b,c]"


class TestInstructionInjection:
    @pytest.mark.asyncio
    async def test_instruction_with_single_skill(self, handler: ChannelSkillCommandHandler) -> None:
        result = await handler(
            _make_msg(),
            skill_ids=("skill_a",),
            user_args="do it",
            instruction="be concise",
        )
        assert result is not None
        assert result.content == "[use skill_a] [instruction: be concise] do it"

    @pytest.mark.asyncio
    async def test_instruction_with_bundle(self, handler: ChannelSkillCommandHandler) -> None:
        result = await handler(
            _make_msg(),
            skill_ids=("skill_a", "skill_b"),
            user_args="run",
            instruction="output JSON",
        )
        assert result is not None
        assert result.content == "[use skill_a,skill_b] [instruction: output JSON] run"

    @pytest.mark.asyncio
    async def test_instruction_without_args(self, handler: ChannelSkillCommandHandler) -> None:
        result = await handler(
            _make_msg(),
            skill_ids=("skill_a",),
            user_args="",
            instruction="be brief",
        )
        assert result is not None
        assert result.content == "[use skill_a] [instruction: be brief]"

    @pytest.mark.asyncio
    async def test_empty_instruction_omitted(self, handler: ChannelSkillCommandHandler) -> None:
        result = await handler(
            _make_msg(),
            skill_ids=("skill_a",),
            user_args="args",
            instruction="",
        )
        assert result is not None
        assert "[instruction:" not in result.content
        assert result.content == "[use skill_a] args"
