"""Feishu reaction vocabulary: names sent must be official ``emoji_type`` values; names read must be official spellings.

Feishu rejects an unknown ``emoji_type`` (error 231001) and its names are case-sensitive, so a
wrong spelling is silently dead on both the outbound and the inbound path.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from app.channels.providers.feishu import FeishuChannel
from app.channels.providers.feishu.api import FeishuClient
from app.channels.providers.feishu.reactions import FEISHU_EMOJI_TO_UNICODE, UNICODE_TO_FEISHU_EMOJI
from app.channels.routing.commands.commands import parse_approval_command
from app.channels.types import InboundMessage

# Subset of the official list (open.feishu.cn: message-reaction/emojis-introduce) the vocabulary may use.
OFFICIAL_EMOJI_TYPES = frozenset(
    {
        "DONE",
        "OK",
        "THUMBSUP",
        "HEART",
        "JIAYI",
        "Typing",
        "THINKING",
        "Hundred",
        "HEARTBROKEN",
        "DIZZY",
        "CrossMark",
        "ThumbsDown",
        "MUSCLE",
    }
)


def _channel() -> tuple[FeishuChannel, AsyncMock]:
    ch = FeishuChannel(app_id="test_app_id", app_secret="test_app_secret", encrypt_key="test_encrypt_key")
    mock = AsyncMock(spec=FeishuClient)
    mock.bot_open_id = "ou_bot"
    mock.is_configured = True
    mock._get_http.return_value = AsyncMock(spec=httpx.AsyncClient)
    mock.get_user.return_value = None
    ch._client = mock
    ch._user_resolver._api = mock
    return ch, mock


async def _react(ch: FeishuChannel, emoji_type: str) -> list[InboundMessage]:
    received: list[InboundMessage] = []

    async def handler(msg: InboundMessage) -> None:
        received.append(msg)

    ch.set_inbound_handler(handler)
    await ch.handle_webhook_event(
        {
            "header": {"event_type": "im.message.reaction_created_v1"},
            "event": {
                "message_id": "om_card",
                "reaction_type": {"emoji_type": emoji_type},
                "operator_type": {"operator_id": {"open_id": "ou_user1"}},
            },
        }
    )
    return received


class TestOutboundVocabulary:
    def test_every_name_sent_is_official(self) -> None:
        assert set(UNICODE_TO_FEISHU_EMOJI.values()) <= OFFICIAL_EMOJI_TYPES

    @pytest.mark.parametrize(
        ("glyph", "name"),
        [
            pytest.param("\U0001f440", "Typing", id="processing-eyes"),
            pytest.param("\u274c", "CrossMark", id="failure-cross"),
            pytest.param("\U0001f44e", "ThumbsDown", id="thumbs-down"),
            pytest.param("\u2705", "DONE", id="success-check"),
        ],
    )
    def test_default_status_glyphs_map_to_official_names(self, glyph: str, name: str) -> None:
        assert UNICODE_TO_FEISHU_EMOJI[glyph] == name

    @pytest.mark.asyncio
    async def test_processing_glyph_is_sent_under_its_official_name(self) -> None:
        ch, mock = _channel()
        mock.add_reaction.return_value = "rid"
        await ch.react_to_message("oc_chat", "om_msg", "\U0001f440")
        mock.add_reaction.assert_awaited_once_with("om_msg", "Typing")


class TestInboundVocabulary:
    @pytest.mark.parametrize(
        ("emoji_type", "decision"),
        [
            pytest.param("THUMBSUP", "allow_once", id="thumbsup"),
            pytest.param("MUSCLE", "allow_once", id="muscle"),
            pytest.param("ThumbsDown", "deny", id="thumbs-down"),
            pytest.param("CrossMark", "deny", id="cross-mark"),
        ],
    )
    @pytest.mark.asyncio
    async def test_official_names_reach_the_approval_parser(self, emoji_type: str, decision: str) -> None:
        ch, _ = _channel()
        received = await _react(ch, emoji_type)
        assert len(received) == 1
        assert received[0].metadata["target_message_id"] == "om_card"
        assert parse_approval_command(received[0].content) == decision

    @pytest.mark.parametrize("emoji_type", ["THUMBSDOWN", "NO", "INFINITY", "STAR", "EYES"])
    def test_names_feishu_never_sends_are_not_read(self, emoji_type: str) -> None:
        assert emoji_type not in FEISHU_EMOJI_TO_UNICODE
