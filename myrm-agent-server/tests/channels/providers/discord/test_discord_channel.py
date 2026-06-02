from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from app.channels.providers.discord.channel import (
    DiscordChannel,
)
from app.channels.providers.discord.config import (
    DiscordChannelConfig,
)
from app.channels.types import ChannelStatus, OutboundMessage
from app.channels.types.messages import MediaType


@pytest.fixture
def config():
    return DiscordChannelConfig(
        bot_token="test_token",
        enable_gateway=True,
        allowed_users=["123"],
        allowed_guilds=["456"],
    )


@pytest.fixture
def channel(config):
    return DiscordChannel(config)


@pytest.mark.asyncio
async def test_start_with_gateway(channel):
    with patch("discord.Client") as mock_client_cls:
        mock_client_instance = mock_client_cls.return_value
        mock_client_instance.start = AsyncMock()

        await channel.start()

        assert channel.status == ChannelStatus.IDLE
        mock_client_cls.assert_called_once()
        # The task is created, we can't easily assert on it without awaiting it,
        # but we know it should have called start
        assert channel._gateway_task is not None


@pytest.mark.asyncio
async def test_start_without_gateway():
    config = DiscordChannelConfig(bot_token="test_token", enable_gateway=False)
    channel = DiscordChannel(config)

    await channel.start()

    assert channel.status == ChannelStatus.RUNNING
    assert channel._client is None
    assert channel._gateway_task is None


@pytest.mark.asyncio
async def test_stop(channel):
    channel._client = MagicMock()
    channel._client.is_closed.return_value = False
    channel._client.close = AsyncMock()
    channel._gateway_task = MagicMock()
    channel._gateway_task.cancel = MagicMock()

    await channel.stop()

    assert channel.status == ChannelStatus.STOPPED
    channel._client.close.assert_called_once()
    channel._gateway_task.cancel.assert_called_once()


@pytest.mark.asyncio
async def test_on_message_dispatches(channel):
    """_on_message should dispatch non-bot messages via _emit_inbound."""
    mock_message = MagicMock()
    mock_message.author.bot = False
    mock_message.author.id = 123
    mock_message.author.display_name = "test_user"
    mock_message.guild = None
    mock_message.channel.id = 789
    mock_message.id = 101
    mock_message.content = "hello"
    mock_message.attachments = []
    mock_message.reference = None
    mock_message.mentions = []

    received = []

    async def handler(msg):
        received.append(msg)

    channel.set_inbound_handler(handler)

    await channel._on_message(mock_message)

    assert len(received) == 1
    assert received[0].content == "hello"
    assert received[0].sender_id == "123"


@pytest.mark.asyncio
async def test_on_message_ignores_bot(channel):
    """_on_message should skip bot messages."""
    mock_message = MagicMock()
    mock_message.author.bot = True
    mock_message.author.id = 999

    received = []

    async def handler(msg):
        received.append(msg)

    channel.set_inbound_handler(handler)

    await channel._on_message(mock_message)

    assert len(received) == 0


# ── Media extraction tests ──


def _make_attachment(
    *,
    content_type: str,
    filename: str,
    width=None,
    height=None,
    url="https://cdn.discord.com/file"
):
    att = MagicMock()
    att.content_type = content_type
    att.filename = filename
    att.width = width
    att.height = height
    att.url = url
    return att


@pytest.mark.asyncio
async def test_on_message_with_image_attachment(channel):
    """Image attachments should be extracted as MediaType.IMAGE."""
    mock_message = MagicMock()
    mock_message.author.bot = False
    mock_message.author.id = 123
    mock_message.author.display_name = "user"
    mock_message.guild = None
    mock_message.channel.id = 789
    mock_message.id = 102
    mock_message.content = "check this image"
    mock_message.attachments = [
        _make_attachment(
            content_type="image/png", filename="screenshot.png", width=800, height=600
        ),
    ]

    received = []

    async def handler(msg):
        received.append(msg)

    channel.set_inbound_handler(handler)
    await channel._on_message(mock_message)

    assert len(received) == 1
    inbound = received[0]
    assert inbound.content == "check this image"
    assert len(inbound.media) == 1
    assert inbound.media[0].media_type == MediaType.IMAGE
    assert inbound.media[0].filename == "screenshot.png"
    assert inbound.media[0].url == "https://cdn.discord.com/file"


@pytest.mark.asyncio
async def test_on_message_with_document_attachment(channel):
    """Non-image/video/audio files should be MediaType.DOCUMENT."""
    mock_message = MagicMock()
    mock_message.author.bot = False
    mock_message.author.id = 123
    mock_message.author.display_name = "user"
    mock_message.guild = None
    mock_message.channel.id = 789
    mock_message.id = 103
    mock_message.content = ""
    mock_message.attachments = [
        _make_attachment(content_type="application/pdf", filename="report.pdf"),
    ]

    received = []

    async def handler(msg):
        received.append(msg)

    channel.set_inbound_handler(handler)
    await channel._on_message(mock_message)

    assert len(received) == 1
    inbound = received[0]
    assert inbound.media[0].media_type == MediaType.DOCUMENT
    assert inbound.media[0].filename == "report.pdf"
    assert inbound.media[0].mime_type == "application/pdf"


@pytest.mark.asyncio
async def test_on_message_with_multiple_attachments(channel):
    """Multiple attachments of different types should all be extracted."""
    mock_message = MagicMock()
    mock_message.author.bot = False
    mock_message.author.id = 123
    mock_message.author.display_name = "user"
    mock_message.guild = None
    mock_message.channel.id = 789
    mock_message.id = 104
    mock_message.content = "mixed media"
    mock_message.attachments = [
        _make_attachment(
            content_type="image/jpeg", filename="photo.jpg", width=1920, height=1080
        ),
        _make_attachment(content_type="video/mp4", filename="clip.mp4"),
        _make_attachment(content_type="audio/ogg", filename="voice.ogg"),
        _make_attachment(content_type="text/plain", filename="notes.txt"),
    ]

    received = []

    async def handler(msg):
        received.append(msg)

    channel.set_inbound_handler(handler)
    await channel._on_message(mock_message)

    assert len(received) == 1
    inbound = received[0]
    assert len(inbound.media) == 4
    assert inbound.media[0].media_type == MediaType.IMAGE
    assert inbound.media[1].media_type == MediaType.VIDEO
    assert inbound.media[2].media_type == MediaType.AUDIO
    assert inbound.media[3].media_type == MediaType.DOCUMENT


@pytest.mark.asyncio
async def test_on_message_no_attachments(channel):
    """Messages without attachments should have empty media tuple."""
    mock_message = MagicMock()
    mock_message.author.bot = False
    mock_message.author.id = 123
    mock_message.author.display_name = "user"
    mock_message.guild = None
    mock_message.channel.id = 789
    mock_message.id = 105
    mock_message.content = "just text"
    mock_message.attachments = []

    received = []

    async def handler(msg):
        received.append(msg)

    channel.set_inbound_handler(handler)
    await channel._on_message(mock_message)

    assert len(received) == 1
    assert received[0].media == ()


@pytest.mark.asyncio
async def test_on_message_image_by_dimensions_fallback(channel):
    """Images detected by width/height even without standard content_type."""
    mock_message = MagicMock()
    mock_message.author.bot = False
    mock_message.author.id = 123
    mock_message.author.display_name = "user"
    mock_message.guild = None
    mock_message.channel.id = 789
    mock_message.id = 106
    mock_message.content = ""
    mock_message.attachments = [
        _make_attachment(
            content_type="", filename="unknown.bin", width=640, height=480
        ),
    ]

    received = []

    async def handler(msg):
        received.append(msg)

    channel.set_inbound_handler(handler)
    await channel._on_message(mock_message)

    assert len(received) == 1
    assert received[0].media[0].media_type == MediaType.IMAGE


# ── Forum channel tests ──


class TestIsForumChannel:
    def test_none_returns_false(self):
        assert DiscordChannel._is_forum_channel(None) is False

    def test_regular_channel_returns_false(self):
        ch = MagicMock(spec=discord.TextChannel)
        ch.type = MagicMock()
        ch.type.value = 0
        assert DiscordChannel._is_forum_channel(ch) is False

    def test_forum_channel_by_isinstance(self):
        ch = MagicMock(spec=discord.ForumChannel)
        assert DiscordChannel._is_forum_channel(ch) is True

    def test_forum_channel_by_type_value(self):
        ch = MagicMock()
        del ch.spec  # Not a ForumChannel instance
        ch.type = MagicMock()
        ch.type.value = 15
        assert DiscordChannel._is_forum_channel(ch) is True

    def test_no_type_attribute(self):
        ch = MagicMock(spec=[])
        assert DiscordChannel._is_forum_channel(ch) is False


class TestDeriveThreadName:
    def test_single_line(self):
        assert DiscordChannel._derive_thread_name("Hello world") == "Hello world"

    def test_multi_line(self):
        assert DiscordChannel._derive_thread_name("First\nSecond") == "First"

    def test_strips_markdown_heading(self):
        assert DiscordChannel._derive_thread_name("## My Title") == "My Title"

    def test_empty_content(self):
        assert DiscordChannel._derive_thread_name("") == "New Post"

    def test_whitespace_only(self):
        assert DiscordChannel._derive_thread_name("   \n  ") == "New Post"

    def test_hash_only(self):
        assert DiscordChannel._derive_thread_name("###") == "New Post"

    def test_skips_empty_leading_lines(self):
        assert (
            DiscordChannel._derive_thread_name("\n\nActual Title\nBody")
            == "Actual Title"
        )

    def test_skips_blank_leading_with_markdown(self):
        assert (
            DiscordChannel._derive_thread_name("\n# Report Title\nContent")
            == "Report Title"
        )

    def test_truncates_to_100(self):
        long = "A" * 200
        assert len(DiscordChannel._derive_thread_name(long)) == 100


def _setup_resolve(channel, mock_channel):
    """Patch _resolve_channel to directly return the mock, bypassing isinstance checks."""
    channel._resolve_channel = AsyncMock(return_value=mock_channel)


def _make_forum_mock(
    *, requires_tag: bool = False, available_tags: list[MagicMock] | None = None
):
    mock_forum = MagicMock(spec=discord.ForumChannel)
    mock_forum.type = MagicMock()
    mock_forum.type.value = 15
    mock_forum.requires_tag = requires_tag
    mock_forum.available_tags = available_tags or []
    return mock_forum


@pytest.mark.asyncio
async def test_send_to_forum_channel(channel):
    """send() should auto-create a forum thread when target is a Forum channel."""
    mock_forum = _make_forum_mock()

    mock_thread = MagicMock()
    mock_thread.id = 99999
    starter_msg = MagicMock()
    starter_msg.id = 88888
    mock_thread.message = starter_msg
    mock_thread.send = AsyncMock()
    mock_forum.create_thread = AsyncMock(return_value=mock_thread)

    _setup_resolve(channel, mock_forum)

    msg = OutboundMessage(
        channel="discord",
        recipient_id="12345",
        content="Daily report\nSome content here",
        user_id="u1",
    )
    result = await channel.send(msg)

    mock_forum.create_thread.assert_called_once()
    call_kwargs = mock_forum.create_thread.call_args
    assert call_kwargs.kwargs["name"] == "Daily report"
    assert call_kwargs.kwargs["content"] == "Daily report\nSome content here"
    assert result == "88888"


@pytest.mark.asyncio
async def test_send_to_forum_with_require_tag(channel):
    """When Forum requires tags, the first available tag is applied."""
    mock_tag = MagicMock()
    mock_tag.id = 777
    mock_forum = _make_forum_mock(requires_tag=True, available_tags=[mock_tag])

    mock_thread = MagicMock()
    mock_thread.id = 99999
    mock_thread.message = MagicMock(id=88888)
    mock_thread.send = AsyncMock()
    mock_forum.create_thread = AsyncMock(return_value=mock_thread)

    _setup_resolve(channel, mock_forum)

    msg = OutboundMessage(
        channel="discord",
        recipient_id="12345",
        content="Tagged post",
        user_id="u1",
    )
    result = await channel.send(msg)

    call_kwargs = mock_forum.create_thread.call_args.kwargs
    assert call_kwargs["applied_tags"] == [mock_tag]
    assert result == "88888"


@pytest.mark.asyncio
async def test_send_to_regular_channel(channel):
    """send() should behave normally for non-Forum channels."""
    mock_ch = MagicMock(spec=discord.TextChannel)
    mock_ch.type = MagicMock()
    mock_ch.type.value = 0
    sent_msg = MagicMock()
    sent_msg.id = 55555
    mock_ch.send = AsyncMock(return_value=sent_msg)

    _setup_resolve(channel, mock_ch)

    msg = OutboundMessage(
        channel="discord",
        recipient_id="12345",
        content="Regular message",
        user_id="u1",
    )
    result = await channel.send(msg)

    mock_ch.send.assert_called_once_with(content="Regular message")
    assert result == "55555"


@pytest.mark.asyncio
async def test_send_placeholder_to_forum(channel):
    """send_placeholder() should create forum thread when target is Forum."""
    mock_forum = _make_forum_mock()

    mock_thread = MagicMock()
    mock_thread.id = 99999
    mock_thread.message = MagicMock(id=77777)
    mock_thread.send = AsyncMock()
    mock_forum.create_thread = AsyncMock(return_value=mock_thread)

    _setup_resolve(channel, mock_forum)

    result = await channel.send_placeholder("12345", "Thinking...")

    mock_forum.create_thread.assert_called_once()
    assert result == "77777"


@pytest.mark.asyncio
async def test_forum_thread_creation_failure(channel):
    """_create_forum_thread returns None on API failure."""
    mock_forum = _make_forum_mock()
    mock_forum.id = 12345
    mock_forum.create_thread = AsyncMock(side_effect=Exception("Permission denied"))

    _setup_resolve(channel, mock_forum)

    msg = OutboundMessage(
        channel="discord",
        recipient_id="12345",
        content="Should fail",
        user_id="u1",
    )
    result = await channel.send(msg)
    assert result is None


@pytest.mark.asyncio
async def test_on_message_forum_thread_inherits_topic(channel):
    """Forum thread messages should have channel_topic from parent Forum."""
    mock_message = MagicMock()
    mock_message.author.bot = False
    mock_message.author.id = 123
    mock_message.author.display_name = "user"
    mock_message.guild = None
    mock_message.channel = MagicMock(spec=discord.Thread)
    mock_message.channel.id = 789
    mock_message.channel.topic = None
    parent = MagicMock()
    parent.topic = "Q&A Forum — keep answers concise"
    mock_message.channel.parent = parent
    mock_message.id = 107
    mock_message.content = "question"
    mock_message.attachments = []

    received = []

    async def handler(msg):
        received.append(msg)

    channel.set_inbound_handler(handler)
    await channel._on_message(mock_message)

    assert len(received) == 1
    assert received[0].metadata["channel_topic"] == "Q&A Forum — keep answers concise"


@pytest.mark.asyncio
async def test_on_message_regular_channel_no_topic(channel):
    """Regular text channel without topic should have None channel_topic."""
    mock_message = MagicMock()
    mock_message.author.bot = False
    mock_message.author.id = 123
    mock_message.author.display_name = "user"
    mock_message.guild = None
    mock_message.channel = MagicMock(spec=discord.TextChannel)
    mock_message.channel.id = 789
    mock_message.channel.topic = None
    mock_message.id = 108
    mock_message.content = "hello"
    mock_message.attachments = []

    received = []

    async def handler(msg):
        received.append(msg)

    channel.set_inbound_handler(handler)
    await channel._on_message(mock_message)

    assert len(received) == 1
    assert received[0].metadata["channel_topic"] is None


@pytest.mark.asyncio
async def test_on_interaction_forum_thread_topic(channel):
    """Interaction in a Forum thread should inherit parent topic in metadata."""
    mock_interaction = MagicMock()
    mock_interaction.type = discord.InteractionType.component
    mock_interaction.response = MagicMock()
    mock_interaction.response.defer = AsyncMock()
    mock_interaction.user.id = 123
    mock_interaction.user.display_name = "user"
    mock_interaction.channel_id = 789
    mock_interaction.guild_id = 456
    mock_interaction.id = 111
    mock_interaction.data = {"custom_id": "act:approve"}

    mock_interaction.channel = MagicMock(spec=discord.Thread)
    mock_interaction.channel.topic = None
    parent = MagicMock()
    parent.topic = "Support Forum — please be specific"
    mock_interaction.channel.parent = parent

    received = []

    async def handler(msg):
        received.append(msg)

    channel.set_inbound_handler(handler)
    await channel._on_interaction(mock_interaction)

    assert len(received) == 1
    assert received[0].metadata["channel_topic"] == "Support Forum — please be specific"
    assert received[0].content == "/action approve"


# ── Outbound edit/delete/react tests ──


@pytest.mark.asyncio
async def test_edit_message(channel):
    mock_ch = MagicMock()
    mock_msg = MagicMock()
    mock_ch.fetch_message = AsyncMock(return_value=mock_msg)
    mock_msg.edit = AsyncMock()
    channel._resolve_channel = AsyncMock(return_value=mock_ch)

    await channel.edit_message("123", "456", "updated text")

    mock_msg.edit.assert_called_once_with(content="updated text")


@pytest.mark.asyncio
async def test_edit_message_channel_not_found(channel):
    channel._resolve_channel = AsyncMock(return_value=None)
    await channel.edit_message("123", "456", "text")


@pytest.mark.asyncio
async def test_edit_placeholder_message(channel):
    mock_ch = MagicMock()
    mock_target = MagicMock()
    mock_ch.fetch_message = AsyncMock(return_value=mock_target)
    mock_target.edit = AsyncMock()
    channel._resolve_channel = AsyncMock(return_value=mock_ch)

    msg = OutboundMessage(
        channel="discord",
        recipient_id="123",
        content="final answer",
        user_id="u1",
        reasoning="because reasons",
    )
    await channel.edit_placeholder_message("123", "456", msg)

    mock_target.edit.assert_called_once()
    call_kwargs = mock_target.edit.call_args.kwargs
    assert call_kwargs["embed"].description == "final answer"


@pytest.mark.asyncio
async def test_delete_message(channel):
    mock_ch = MagicMock()
    mock_msg = MagicMock()
    mock_ch.fetch_message = AsyncMock(return_value=mock_msg)
    mock_msg.delete = AsyncMock()
    channel._resolve_channel = AsyncMock(return_value=mock_ch)

    await channel.delete_message("123", "456")

    mock_msg.delete.assert_called_once()


@pytest.mark.asyncio
async def test_react_to_message(channel):
    mock_ch = MagicMock()
    mock_msg = MagicMock()
    mock_ch.fetch_message = AsyncMock(return_value=mock_msg)
    mock_msg.add_reaction = AsyncMock()
    channel._resolve_channel = AsyncMock(return_value=mock_ch)

    await channel.react_to_message("123", "456", "👍")

    mock_msg.add_reaction.assert_called_once_with("👍")


@pytest.mark.asyncio
async def test_react_to_message_empty_emoji(channel):
    """Empty emoji should no-op without calling resolve_channel."""
    channel._resolve_channel = AsyncMock()
    await channel.react_to_message("123", "456", "")
    channel._resolve_channel.assert_not_called()


@pytest.mark.asyncio
async def test_start_typing(channel):
    mock_ch = MagicMock()
    mock_ch.typing = AsyncMock()
    channel._resolve_channel = AsyncMock(return_value=mock_ch)

    await channel.start_typing("123")

    mock_ch.typing.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_channel_cache_hit(channel):
    """_resolve_channel should return channel from client cache."""
    mock_ch = MagicMock(spec=discord.TextChannel)
    channel._client = MagicMock()
    channel._client.get_channel = MagicMock(return_value=mock_ch)

    result = await channel._resolve_channel("12345")

    assert result == mock_ch
    channel._client.get_channel.assert_called_once_with(12345)


@pytest.mark.asyncio
async def test_resolve_channel_no_client(channel):
    """_resolve_channel should return None when client is not set."""
    channel._client = None
    result = await channel._resolve_channel("12345")
    assert result is None


@pytest.mark.asyncio
async def test_resolve_channel_api_fallback(channel):
    """_resolve_channel should fall back to fetch_channel when get_channel returns None."""
    mock_ch = MagicMock(spec=discord.TextChannel)
    channel._client = MagicMock()
    channel._client.get_channel = MagicMock(return_value=None)
    channel._client.fetch_channel = AsyncMock(return_value=mock_ch)

    result = await channel._resolve_channel("12345")

    assert result == mock_ch
    channel._client.fetch_channel.assert_called_once_with(12345)


@pytest.mark.asyncio
async def test_discord_fetch_history(channel):
    """Test fetch_history on DiscordChannel with mock async iterator."""
    channel._bot_id = "bot-id"
    mock_channel = MagicMock(spec=discord.TextChannel)
    mock_channel.id = 12345
    mock_channel.topic = "test topic"

    # Configure mock author
    mock_author = MagicMock()
    mock_author.id = "user-abc"
    mock_author.display_name = "Alice"
    mock_author.bot = False

    # Configure mock messages
    msg1 = MagicMock(spec=discord.Message)
    msg1.id = 111
    msg1.author = mock_author
    msg1.content = "Hello there"
    msg1.created_at = MagicMock()
    msg1.created_at.timestamp.return_value = 1779340000.0
    msg1.attachments = []
    msg1.embeds = []
    msg1.guild = None

    # This is a bot message that should be skipped
    mock_bot_author = MagicMock()
    mock_bot_author.id = "bot-id"
    mock_bot_author.bot = True
    msg2 = MagicMock(spec=discord.Message)
    msg2.id = 222
    msg2.author = mock_bot_author
    msg2.content = "I am a bot"
    msg2.created_at = MagicMock()
    msg2.created_at.timestamp.return_value = 1779340010.0
    msg2.attachments = []
    msg2.embeds = []
    msg2.guild = None

    class MockAsyncIterator:
        def __init__(self, items):
            self.items = items
            self.index = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.index >= len(self.items):
                raise StopAsyncIteration
            item = self.items[self.index]
            self.index += 1
            return item

    mock_channel.history.return_value = MockAsyncIterator([msg1, msg2])

    with patch.object(
        channel, "_resolve_channel", AsyncMock(return_value=mock_channel)
    ):
        res = await channel.fetch_history("12345", limit=5)

        # msg2 should be filtered out because it is a bot message
        assert len(res) == 1
        assert res[0].content == "Hello there"
        assert res[0].sender_id == "user-abc"
        assert res[0].sender_name == "Alice"
        assert res[0].sent_at == 1779340000.0


class TestParseAllowedChannels:
    def test_valid_entries(self) -> None:
        result = DiscordChannelConfig._parse_allowed_channels(
            ["111:222", "333:444"]
        )
        assert result == [("111", "222"), ("333", "444")]

    def test_entries_with_whitespace(self) -> None:
        result = DiscordChannelConfig._parse_allowed_channels(
            [" 111 : 222 ", "333:444"]
        )
        assert result == [("111", "222"), ("333", "444")]

    def test_invalid_entries_skipped(self) -> None:
        result = DiscordChannelConfig._parse_allowed_channels(
            ["111", "222:333:444", ":555", "666:", "777:888"]
        )
        assert result == [("777", "888")]

    def test_none_returns_empty(self) -> None:
        result = DiscordChannelConfig._parse_allowed_channels(None)
        assert result == []

    def test_empty_list_returns_empty(self) -> None:
        result = DiscordChannelConfig._parse_allowed_channels([])
        assert result == []


class TestDiscordConfigVoiceFields:
    def test_voice_follow_users(self) -> None:
        cfg = DiscordChannelConfig(
            bot_token="token",
            voice_follow_users=["100", "200"],
        )
        assert cfg.voice_follow_users == ["100", "200"]

    def test_voice_follow_users_default(self) -> None:
        cfg = DiscordChannelConfig(bot_token="token")
        assert cfg.voice_follow_users == []

    def test_voice_allowed_channels_parsed(self) -> None:
        cfg = DiscordChannelConfig(
            bot_token="token",
            voice_allowed_channels=["111:222", "333:444"],
        )
        assert cfg.voice_allowed_channels == [("111", "222"), ("333", "444")]

    def test_voice_allowed_channels_default(self) -> None:
        cfg = DiscordChannelConfig(bot_token="token")
        assert cfg.voice_allowed_channels == []


class TestCredentialSpecFields:
    def test_credential_spec_includes_voice_follow_fields(self) -> None:
        spec = DiscordChannel.credential_spec
        field_keys = {name for name, _ in spec.fields}
        assert "voice_follow_users" in field_keys
        assert "voice_allowed_channels" in field_keys
