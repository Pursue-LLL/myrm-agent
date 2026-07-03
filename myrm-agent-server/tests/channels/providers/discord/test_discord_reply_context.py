"""Unit tests for Discord reply context parsing and mention resolution.

Covers _parse_reply_context() and _resolve_mentioned() with discord.py
API mocking via reference.resolved.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

pytest.importorskip("discord")
import discord

from app.channels.providers.discord.channel import DiscordChannel
from app.channels.providers.discord.config import DiscordChannelConfig


@pytest.fixture
def channel() -> DiscordChannel:
    cfg = DiscordChannelConfig(bot_token="test", enable_gateway=True, allowed_users=["1"])
    ch = DiscordChannel(cfg)
    client = MagicMock()
    bot_user = MagicMock(spec=discord.User)
    bot_user.id = 42
    client.user = bot_user
    ch._client = client
    return ch


def _make_resolved_message(
    *,
    msg_id: int = 100,
    content: str = "original text",
    embeds: list[discord.Embed] | None = None,
    attachments: list[discord.Attachment] | None = None,
    author_id: int = 200,
    author_name: str = "Alice",
    created_at: datetime | None = None,
) -> MagicMock:
    msg = MagicMock(spec=discord.Message)
    msg.id = msg_id
    msg.content = content
    msg.embeds = embeds or []
    msg.attachments = attachments or []
    msg.author = MagicMock(spec=discord.Member)
    msg.author.id = author_id
    msg.author.display_name = author_name
    msg.created_at = created_at or datetime(2025, 1, 1, tzinfo=timezone.utc)
    return msg


def _make_message_with_ref(
    ref_message_id: int,
    resolved: discord.Message | MagicMock | None,
    *,
    guild: MagicMock | None = MagicMock(),
    mentions: list | None = None,
) -> MagicMock:
    ref = MagicMock(spec=discord.MessageReference)
    ref.message_id = ref_message_id

    ref.resolved = resolved

    msg = MagicMock(spec=discord.Message)
    msg.reference = ref
    msg.guild = guild
    msg.mentions = mentions or []
    return msg


# ── _parse_reply_context ──


class TestParseReplyContext:
    def test_normal_reply_extracts_full_context(self, channel: DiscordChannel) -> None:
        resolved = _make_resolved_message(content="Hello world", author_name="Bob")
        msg = _make_message_with_ref(100, resolved)

        ctx, reply_to_id = channel._parse_reply_context(msg)

        assert reply_to_id == "100"
        assert ctx is not None
        assert ctx.content == "Hello world"
        assert ctx.sender_name == "Bob"
        assert ctx.sender_id == "200"
        assert ctx.message_id == "100"
        assert ctx.timestamp is not None

    def test_deleted_message_returns_id_only(self, channel: DiscordChannel) -> None:
        deleted = MagicMock(spec=discord.message.DeletedReferencedMessage)
        msg = _make_message_with_ref(999, deleted)

        ctx, reply_to_id = channel._parse_reply_context(msg)

        assert reply_to_id == "999"
        assert ctx is not None
        assert ctx.message_id == "999"
        assert ctx.content == ""
        assert ctx.media == ()

    def test_no_reference_returns_none(self, channel: DiscordChannel) -> None:
        msg = MagicMock(spec=discord.Message)
        msg.reference = None

        ctx, reply_to_id = channel._parse_reply_context(msg)

        assert ctx is None
        assert reply_to_id is None

    def test_resolved_none_returns_id_only(self, channel: DiscordChannel) -> None:
        msg = _make_message_with_ref(555, None)

        ctx, reply_to_id = channel._parse_reply_context(msg)

        assert reply_to_id == "555"
        assert ctx is not None
        assert ctx.content == ""

    def test_embed_content_extracted(self, channel: DiscordChannel) -> None:
        embed = MagicMock(spec=discord.Embed)
        embed.description = "Embed description"
        embed.title = "Embed title"
        resolved = _make_resolved_message(content="", embeds=[embed])
        msg = _make_message_with_ref(100, resolved)

        ctx, _ = channel._parse_reply_context(msg)

        assert ctx is not None
        assert "Embed description" in ctx.content

    def test_embed_fallback_to_title(self, channel: DiscordChannel) -> None:
        embed = MagicMock(spec=discord.Embed)
        embed.description = None
        embed.title = "Only Title"
        resolved = _make_resolved_message(content="", embeds=[embed])
        msg = _make_message_with_ref(100, resolved)

        ctx, _ = channel._parse_reply_context(msg)

        assert ctx is not None
        assert "Only Title" in ctx.content

    def test_content_plus_embed_merged(self, channel: DiscordChannel) -> None:
        embed = MagicMock(spec=discord.Embed)
        embed.description = "extra info"
        embed.title = None
        resolved = _make_resolved_message(content="main text", embeds=[embed])
        msg = _make_message_with_ref(100, resolved)

        ctx, _ = channel._parse_reply_context(msg)

        assert ctx is not None
        assert "main text" in ctx.content
        assert "extra info" in ctx.content

    def test_attachment_creates_media(self, channel: DiscordChannel) -> None:
        att = MagicMock(spec=discord.Attachment)
        att.content_type = "image/png"
        att.url = "https://cdn.example.com/img.png"
        att.filename = "img.png"
        att.width = 100
        att.height = 100
        resolved = _make_resolved_message(attachments=[att])
        msg = _make_message_with_ref(100, resolved)

        ctx, _ = channel._parse_reply_context(msg)

        assert ctx is not None
        assert len(ctx.media) == 1


# ── _resolve_mentioned ──


class TestResolveMentioned:
    def test_dm_always_false(self, channel: DiscordChannel) -> None:
        msg = MagicMock(spec=discord.Message)
        assert channel._resolve_mentioned(msg, is_group=False, reply_to_id=None) is False

    def test_group_explicit_mention(self, channel: DiscordChannel) -> None:
        bot_user = channel._client.user
        msg = MagicMock(spec=discord.Message)
        msg.mentions = [bot_user]
        assert channel._resolve_mentioned(msg, is_group=True, reply_to_id=None) is True

    def test_group_no_mention(self, channel: DiscordChannel) -> None:
        msg = MagicMock(spec=discord.Message)
        msg.mentions = []
        msg.reference = None
        assert channel._resolve_mentioned(msg, is_group=True, reply_to_id=None) is False

    def test_group_reply_to_bot_implicit_mention(self, channel: DiscordChannel) -> None:
        bot_user = channel._client.user
        resolved = _make_resolved_message(author_id=bot_user.id)
        msg = _make_message_with_ref(100, resolved, mentions=[])
        assert channel._resolve_mentioned(msg, is_group=True, reply_to_id="100") is True

    def test_group_reply_to_other_user_no_mention(self, channel: DiscordChannel) -> None:
        resolved = _make_resolved_message(author_id=9999)
        msg = _make_message_with_ref(100, resolved, mentions=[])
        assert channel._resolve_mentioned(msg, is_group=True, reply_to_id="100") is False

    def test_group_reply_to_deleted_no_mention(self, channel: DiscordChannel) -> None:
        deleted = MagicMock(spec=discord.message.DeletedReferencedMessage)
        msg = _make_message_with_ref(100, deleted, mentions=[])
        assert channel._resolve_mentioned(msg, is_group=True, reply_to_id="100") is False
