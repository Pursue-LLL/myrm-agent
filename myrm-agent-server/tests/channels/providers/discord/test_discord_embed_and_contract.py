"""DiscordChannel contract compliance + Embed/View unit tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("discord")
import discord

from app.channels.core.base import BaseChannel
from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.discord.channel import (
    DiscordChannel,
)
from app.channels.providers.discord.config import DiscordChannelConfig
from app.channels.providers.discord.helpers import (
    build_discord_components,
    build_discord_embed,
)
from app.channels.types import (
    ActionButton,
    InboundMessage,
    OutboundMessage,
    SelectMenu,
    SelectOption,
    ToolStep,
)
from tests.channels.channel_test_base import ChannelTestBase


class TestDiscordChannelContract(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return DiscordChannel(
            config=DiscordChannelConfig(
                bot_token="test-discord-bot-token-for-unit-test",
            )
        )


def _make_msg(
    content: str = "Hello",
    reasoning: str | None = None,
    tool_steps: tuple[ToolStep, ...] = (),
    components: tuple[tuple[ActionButton | SelectMenu, ...], ...] = (),
    metadata: dict[str, object] | None = None,
) -> OutboundMessage:
    return OutboundMessage(
        channel="discord",
        recipient_id="123",
        content=content,
        reasoning=reasoning,
        user_id="u1",
        tool_steps=tool_steps,
        components=components,
        metadata=metadata,
    )


class TestBuildEmbed:
    """Unit tests for the _build_embed pure function."""

    def test_basic_embed(self) -> None:
        embed = build_discord_embed(_make_msg())
        assert embed is None

    def test_basic_embed_with_reasoning(self) -> None:
        embed = build_discord_embed(_make_msg(reasoning="Hello world"))
        assert embed is not None
        assert embed.fields[0].value == "```\nHello world\n```"
        assert embed.color is not None
        assert embed.color.value == discord.Color.blurple().value
        assert len(embed.fields) == 1

    def test_description_truncation(self) -> None:
        long_text = "x" * (4096 + 500)
        embed = build_discord_embed(_make_msg(reasoning=long_text))
        assert embed is not None
        assert len(embed.fields[0].value) == 4090 + 3 + 8  # 4090 + "..." + "```\n\n```"

    def test_tool_steps_as_fields(self) -> None:
        steps = (
            ToolStep(name="search", label="Web Search", detail="Found 5 results"),
            ToolStep(name="read", label="Read File", detail=None),
        )
        embed = build_discord_embed(_make_msg(tool_steps=steps))
        assert embed is not None
        assert len(embed.fields) == 1
        assert embed.fields[0].name == " Tool Execution"
        assert "**Web Search**: Found 5 results" in embed.fields[0].value
        assert "Read File" in embed.fields[0].value

    def test_tool_steps_max_25(self) -> None:
        steps = tuple(ToolStep(name=f"t{i}", label=f"Tool {i}") for i in range(30))
        embed = build_discord_embed(_make_msg(tool_steps=steps))
        assert embed is not None
        assert len(embed.fields) == 1

    def test_tool_step_detail_truncation(self) -> None:
        long_detail = "d" * (1024 + 100)
        steps = (ToolStep(name="t", label="T", detail=long_detail),)
        embed = build_discord_embed(_make_msg(tool_steps=steps))
        assert embed is not None
        assert len(embed.fields[0].value) <= 1024

    def test_no_sources_field(self) -> None:
        """Sources are handled by render pipeline, not by build_discord_embed."""
        metadata: dict[str, object] = {"sources": [{"url": "https://example.com", "title": "Example"}]}
        embed = build_discord_embed(_make_msg(metadata=metadata))
        assert embed is None

    def test_empty_content(self) -> None:
        embed = build_discord_embed(_make_msg(content=""))
        assert embed is None


class TestBuildView:
    """Unit tests for the _build_view pure function."""

    def test_no_components_returns_none(self) -> None:
        assert build_discord_components(_make_msg()) is None

    def test_button_creates_view(self) -> None:
        btn = ActionButton(label="Click", action_id="click")
        msg = _make_msg(components=((btn,),))
        view = build_discord_components(msg)
        assert view is not None
        assert len(view.children) == 1
        child = view.children[0]
        assert isinstance(child, discord.ui.Button)
        assert child.label == "Click"
        assert child.custom_id == "act:click:"

    def test_url_button_style(self) -> None:
        btn = ActionButton(label="Open", action_id="link", url="https://example.com")
        msg = _make_msg(components=((btn,),))
        view = build_discord_components(msg)
        assert view is not None
        child = view.children[0]
        assert isinstance(child, discord.ui.Button)
        assert child.style == discord.ButtonStyle.link
        assert child.url == "https://example.com"

    def test_select_menu(self) -> None:
        select = SelectMenu(
            action_id="pick",
            placeholder="Choose...",
            options=(
                SelectOption(label="A", value="a"),
                SelectOption(label="B", value="b", description="Option B"),
            ),
        )
        msg = _make_msg(components=((select,),))
        view = build_discord_components(msg)
        assert view is not None
        child = view.children[0]
        assert isinstance(child, discord.ui.Select)
        assert child.custom_id == "sel:pick"
        assert child.placeholder == "Choose..."
        assert len(child.options) == 2

    def test_mixed_components(self) -> None:
        btn = ActionButton(label="OK", action_id="act:ok")
        select = SelectMenu(
            action_id="sel:x",
            placeholder="Pick",
            options=(SelectOption(label="X", value="x"),),
        )
        msg = _make_msg(components=((btn,), (select,)))
        view = build_discord_components(msg)
        assert view is not None
        assert len(view.children) == 2


class TestDiscordEmbedRenderStyle:
    """Verify embed render style configuration."""

    @pytest.mark.skip(reason="DiscordChannel.edit_message override not implemented")
    def test_edit_placeholder_message_override(self) -> None:
        assert DiscordChannel.edit_message is not BaseChannel.edit_message


def _make_mock_channel() -> tuple[DiscordChannel, MagicMock]:
    """Create a DiscordChannel with a mocked discord.Client."""
    from app.channels.providers.discord.config import DiscordChannelConfig

    ch = DiscordChannel(config=DiscordChannelConfig(bot_token="test-token"))
    mock_client = MagicMock(spec=discord.Client)
    mock_client.is_ready.return_value = True
    mock_client.is_closed.return_value = False
    mock_client.guilds = []

    mock_user = MagicMock()
    mock_user.id = 999
    mock_user.name = "TestBot"
    mock_client.user = mock_user

    ch._client = mock_client
    return ch, mock_client


def _make_mock_messageable() -> MagicMock:
    """Create a mock Messageable channel."""
    mock_ch = MagicMock(spec=discord.TextChannel)
    mock_msg = MagicMock()
    mock_msg.id = 42
    mock_ch.send = AsyncMock(return_value=mock_msg)
    mock_ch.fetch_message = AsyncMock(return_value=mock_msg)
    mock_msg.edit = AsyncMock()
    mock_msg.delete = AsyncMock()
    mock_msg.add_reaction = AsyncMock()
    mock_ch.typing = AsyncMock()
    return mock_ch


@pytest.mark.skip(reason="Outbound send/edit covered in test_discord_channel.py")
class TestDiscordOutbound:
    """Tests for outbound message methods with mocked discord.Client."""

    @pytest.mark.asyncio
    async def test_send_basic_message(self) -> None:
        ch, client = _make_mock_channel()
        mock_ch = _make_mock_messageable()
        client.get_channel = MagicMock(return_value=mock_ch)

        msg = _make_msg(content="Hello")
        result = await ch.send(msg)
        assert result == "42"
        mock_ch.send.assert_called()

    @pytest.mark.asyncio
    async def test_send_returns_none_for_invalid_channel(self) -> None:
        ch, client = _make_mock_channel()
        client.get_channel = MagicMock(return_value=None)
        client.fetch_channel = AsyncMock(side_effect=Exception("not found"))

        msg = _make_msg(content="Hello")
        result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_placeholder(self) -> None:
        ch, client = _make_mock_channel()
        mock_ch = _make_mock_messageable()
        client.get_channel = MagicMock(return_value=mock_ch)

        result = await ch.send_placeholder("123", "Thinking...")
        assert result == "42"
        mock_ch.send.assert_called_once_with(content="Thinking...")

    @pytest.mark.asyncio
    async def test_edit_message(self) -> None:
        ch, client = _make_mock_channel()
        mock_ch = _make_mock_messageable()
        client.get_channel = MagicMock(return_value=mock_ch)

        await ch.edit_message("123", "42", "Updated text")
        mock_msg = mock_ch.fetch_message.return_value
        mock_msg.edit.assert_called_once_with(content="Updated text")

    @pytest.mark.asyncio
    async def test_edit_placeholder_message_uses_embed(self) -> None:
        ch, client = _make_mock_channel()
        mock_ch = _make_mock_messageable()
        client.get_channel = MagicMock(return_value=mock_ch)

        msg = _make_msg(content="Final answer with rich content", reasoning="thinking")
        await ch.edit_placeholder_message("123", "42", msg)

        mock_msg = mock_ch.fetch_message.return_value
        mock_msg.edit.assert_called_once()
        call_kwargs = mock_msg.edit.call_args
        assert call_kwargs.kwargs.get("content") is None or call_kwargs[1].get("content") is None
        embed_arg = call_kwargs.kwargs.get("embed") or call_kwargs[1].get("embed")
        assert isinstance(embed_arg, discord.Embed)

    @pytest.mark.asyncio
    async def test_edit_placeholder_message_graceful_failure(self) -> None:
        ch, client = _make_mock_channel()
        mock_ch = _make_mock_messageable()
        mock_ch.fetch_message = AsyncMock(side_effect=Exception("network error"))
        client.get_channel = MagicMock(return_value=mock_ch)

        msg = _make_msg(content="Final answer")
        await ch.edit_placeholder_message("123", "42", msg)

    @pytest.mark.asyncio
    async def test_delete_message(self) -> None:
        ch, client = _make_mock_channel()
        mock_ch = _make_mock_messageable()
        client.get_channel = MagicMock(return_value=mock_ch)

        await ch.delete_message("123", "42")
        mock_msg = mock_ch.fetch_message.return_value
        mock_msg.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_react_to_message(self) -> None:
        ch, client = _make_mock_channel()
        mock_ch = _make_mock_messageable()
        client.get_channel = MagicMock(return_value=mock_ch)

        await ch.react_to_message("123", "42", "")
        mock_msg = mock_ch.fetch_message.return_value
        mock_msg.add_reaction.assert_called_once_with("")

    @pytest.mark.asyncio
    async def test_react_empty_emoji_noop(self) -> None:
        ch, client = _make_mock_channel()
        await ch.react_to_message("123", "42", "")

    @pytest.mark.asyncio
    async def test_start_typing(self) -> None:
        ch, client = _make_mock_channel()
        mock_ch = _make_mock_messageable()
        client.get_channel = MagicMock(return_value=mock_ch)

        await ch.start_typing("123")
        mock_ch.typing.assert_called_once()


@pytest.mark.skip(reason="Inbound dispatch covered in test_discord_channel.py")
class TestDiscordInbound:
    """Tests for inbound message handling with mocked discord events."""

    @pytest.mark.asyncio
    async def test_on_message_emits_inbound(self) -> None:
        ch, client = _make_mock_channel()
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        mock_msg = MagicMock(spec=discord.Message)
        mock_msg.author = MagicMock()
        mock_msg.author.bot = False
        mock_msg.author.id = 123
        mock_msg.author.display_name = "TestUser"
        mock_msg.guild = None
        mock_msg.channel = MagicMock()
        mock_msg.channel.id = 456
        mock_msg.content = "Hello bot"
        mock_msg.attachments = []
        mock_msg.reference = None
        mock_msg.id = 789
        mock_msg.mentions = []

        await ch._on_message(mock_msg)
        assert len(received) == 1
        assert received[0].content == "Hello bot"
        assert received[0].sender_id == "123"
        assert received[0].sender_name == "TestUser"

    @pytest.mark.asyncio
    async def test_on_message_filters_bot_self(self) -> None:
        ch, client = _make_mock_channel()
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        mock_msg = MagicMock(spec=discord.Message)
        mock_msg.author = MagicMock()
        mock_msg.author.bot = True
        mock_msg.author.id = 999

        await ch._on_message(mock_msg)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_on_interaction_emits_inbound(self) -> None:
        ch, client = _make_mock_channel()
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.type = discord.InteractionType.component
        mock_interaction.data = {"custom_id": "act:approve", "component_type": 2}
        mock_interaction.user = MagicMock()
        mock_interaction.user.id = 123
        mock_interaction.user.display_name = "Approver"
        mock_interaction.guild_id = 456
        mock_interaction.channel_id = 789
        mock_interaction.channel = MagicMock()
        mock_interaction.channel.name = "general"
        mock_interaction.id = 101
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()

        await ch._on_interaction(mock_interaction)
        assert len(received) == 1
        assert received[0].content == "/action approve"
        assert received[0].sender_name == "Approver"

    @pytest.mark.asyncio
    async def test_on_interaction_ignores_non_component(self) -> None:
        ch, client = _make_mock_channel()
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.type = discord.InteractionType.application_command

        await ch._on_interaction(mock_interaction)
        assert len(received) == 0


@pytest.mark.skip(reason="Placeholder: not implemented")
class TestDiscordHelpers:
    """Tests for helper methods."""

    @pytest.mark.asyncio
    async def test_resolve_channel_cache_hit(self) -> None:
        pass

    @pytest.mark.asyncio
    async def test_resolve_channel_api_fallback(self) -> None:
        pass

    @pytest.mark.asyncio
    async def test_resolve_channel_not_found(self) -> None:
        pass

    def test_is_mentioned_direct(self) -> None:
        pass

    def test_is_mentioned_text_pattern(self) -> None:
        pass

    def test_strip_mention(self) -> None:
        pass

    def test_extract_attachments(self) -> None:
        pass


@pytest.mark.skip(reason="Placeholder: not implemented")
class TestDiscordLifecycle:
    """Tests for lifecycle methods."""

    @pytest.mark.asyncio
    async def test_start_creates_task(self) -> None:
        pass

    @pytest.mark.asyncio
    async def test_start_empty_token_noop(self) -> None:
        pass

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self) -> None:
        pass

    @pytest.mark.asyncio
    async def test_health_check_ready(self) -> None:
        pass

    @pytest.mark.asyncio
    async def test_health_check_not_ready(self) -> None:
        pass

    @pytest.mark.asyncio
    async def test_list_groups(self) -> None:
        pass


class TestDiscordSendMedia:
    """Tests for media attachment handling in send()."""

    @pytest.mark.asyncio
    async def test_send_with_media(self) -> None:
        """send() passes files from message.media to channel.send()."""
        import os
        import tempfile

        from app.channels.types.messages import MediaAttachment, MediaType

        ch, client = _make_mock_channel()
        mock_ch = _make_mock_messageable()
        mock_ch.type = discord.ChannelType.text
        client.get_channel = MagicMock(return_value=mock_ch)

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test content")
            tmp_path = f.name
        try:
            msg = OutboundMessage(
                channel="discord",
                recipient_id="123",
                content="Here is the file",
                user_id="u1",
                media=(MediaAttachment(media_type=MediaType.DOCUMENT, path=tmp_path, filename="test.txt"),),
            )
            result = await ch.send(msg)
            assert result == "42"
            call_kwargs = mock_ch.send.call_args
            assert "files" in call_kwargs.kwargs or (len(call_kwargs.args) > 1)
            files_arg = call_kwargs.kwargs.get("files", call_kwargs.args[1] if len(call_kwargs.args) > 1 else None)
            assert isinstance(files_arg, list)
            assert len(files_arg) == 1
            assert isinstance(files_arg[0], discord.File)
        finally:
            os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_send_without_media(self) -> None:
        """send() without media uses MISSING for files (no files sent)."""
        ch, client = _make_mock_channel()
        mock_ch = _make_mock_messageable()
        mock_ch.type = discord.ChannelType.text
        client.get_channel = MagicMock(return_value=mock_ch)

        msg = _make_msg(content="No media")
        result = await ch.send(msg)
        assert result == "42"
        call_kwargs = mock_ch.send.call_args
        files_arg = call_kwargs.kwargs.get("files", discord.utils.MISSING)
        assert files_arg is discord.utils.MISSING

    @pytest.mark.asyncio
    async def test_make_discord_file_from_path(self) -> None:
        """build_discord_media uploads a local path as discord.File."""
        import os
        import tempfile

        from app.channels.providers.discord.helpers import build_discord_media
        from app.channels.types.messages import MediaAttachment, MediaType

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"a,b,c")
            tmp_path = f.name
        try:
            media = build_discord_media((MediaAttachment(media_type=MediaType.DOCUMENT, path=tmp_path, filename="data.csv"),))
            assert len(media.files) == 1
            assert isinstance(media.files[0], discord.File)
            assert media.files[0].filename == "data.csv"
            assert (media.links, media.failed) == ([], [])
            media.files[0].close()
        finally:
            os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_url_only_attachment_becomes_a_link(self) -> None:
        """A URL-only attachment is not downloaded: it is posted as a link Discord unfurls."""
        from app.channels.providers.discord.helpers import build_discord_media
        from app.channels.types.messages import MediaAttachment, MediaType

        media = build_discord_media(
            (MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/img.png", filename="img.png"),)
        )
        assert (media.files, media.links, media.failed) == ([], ["https://example.com/img.png"], [])

    @pytest.mark.asyncio
    async def test_unreadable_path_is_reported_as_failed(self) -> None:
        """A missing file must not abort the whole message: it is listed as failed."""
        from app.channels.providers.discord.helpers import build_discord_media
        from app.channels.types.messages import MediaAttachment, MediaType

        media = build_discord_media(
            (MediaAttachment(media_type=MediaType.DOCUMENT, path="/nonexistent/file.txt", filename="file.txt"),)
        )
        assert (media.files, media.links, media.failed) == ([], [], ["file.txt"])

    @pytest.mark.asyncio
    async def test_attachment_without_a_source_is_reported_as_failed(self) -> None:
        from app.channels.providers.discord.helpers import build_discord_media
        from app.channels.types.messages import MediaAttachment, MediaType

        media = build_discord_media((MediaAttachment(media_type=MediaType.DOCUMENT, filename="orphan.txt"),))
        assert (media.files, media.links, media.failed) == ([], [], ["orphan.txt"])


class TestDiscordSendDelivery:
    """send() must raise instead of reporting a lost message as delivered."""

    @staticmethod
    def _channel_with(mock_ch: MagicMock) -> DiscordChannel:
        ch, client = _make_mock_channel()
        mock_ch.type = discord.ChannelType.text
        client.get_channel = MagicMock(return_value=mock_ch)
        return ch

    @staticmethod
    def _http_error(status: int) -> discord.HTTPException:
        response = MagicMock()
        response.status = status
        response.reason = "error"
        return discord.HTTPException(response, "boom")

    @pytest.mark.asyncio
    async def test_unreachable_channel_raises_a_retriable_error(self) -> None:
        ch, client = _make_mock_channel()
        client.get_channel = MagicMock(return_value=None)
        client.fetch_channel = AsyncMock(side_effect=RuntimeError("unknown channel"))

        with pytest.raises(ChannelSendError, match="not reachable") as excinfo:
            await ch.send(_make_msg())

        assert excinfo.value.retriable is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("status", "retriable"), [(403, False), (404, False), (429, True), (503, True)])
    async def test_http_errors_carry_their_retry_class(self, status: int, retriable: bool) -> None:
        mock_ch = _make_mock_messageable()
        mock_ch.send = AsyncMock(side_effect=self._http_error(status))

        with pytest.raises(ChannelSendError) as excinfo:
            await self._channel_with(mock_ch).send(_make_msg())

        assert (excinfo.value.status_code, excinfo.value.retriable) == (status, retriable)

    @pytest.mark.asyncio
    async def test_other_discord_errors_are_retriable(self) -> None:
        mock_ch = _make_mock_messageable()
        mock_ch.send = AsyncMock(side_effect=discord.ClientException("not connected"))

        with pytest.raises(ChannelSendError) as excinfo:
            await self._channel_with(mock_ch).send(_make_msg())

        assert excinfo.value.retriable is True

    @pytest.mark.asyncio
    async def test_url_only_attachment_is_delivered_as_a_link(self) -> None:
        from app.channels.types.messages import MediaAttachment, MediaType

        mock_ch = _make_mock_messageable()
        attachment = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/img.png")
        msg = OutboundMessage(channel="discord", recipient_id="123", content="Chart", user_id="u1", media=(attachment,))

        assert await self._channel_with(mock_ch).send(msg) == "42"

        assert mock_ch.send.call_args.kwargs["content"] == "Chart\nhttps://example.com/img.png"

    @pytest.mark.asyncio
    async def test_unreadable_file_is_reported_after_the_text_was_delivered(self) -> None:
        from app.channels.types.messages import MediaAttachment, MediaType

        mock_ch = _make_mock_messageable()
        attachment = MediaAttachment(media_type=MediaType.DOCUMENT, path="/nonexistent/file.txt", filename="file.txt")
        msg = OutboundMessage(channel="discord", recipient_id="123", content="Report", user_id="u1", media=(attachment,))

        with pytest.raises(ChannelSendError) as excinfo:
            await self._channel_with(mock_ch).send(msg)

        mock_ch.send.assert_called_once()
        assert excinfo.value.failed_attachments == ("file.txt",)
        assert (excinfo.value.accepted, excinfo.value.retriable) == (True, False)

    @pytest.mark.asyncio
    async def test_message_with_only_unreadable_files_sends_nothing_and_stays_retriable(self) -> None:
        from app.channels.types.messages import MediaAttachment, MediaType

        mock_ch = _make_mock_messageable()
        attachment = MediaAttachment(media_type=MediaType.DOCUMENT, path="/nonexistent/file.txt", filename="file.txt")
        msg = OutboundMessage(channel="discord", recipient_id="123", content="", user_id="u1", media=(attachment,))

        with pytest.raises(ChannelSendError) as excinfo:
            await self._channel_with(mock_ch).send(msg)

        mock_ch.send.assert_not_called()
        assert (excinfo.value.accepted, excinfo.value.retriable) == (False, True)

    @staticmethod
    def _forum_channel(create_thread: AsyncMock) -> DiscordChannel:
        mock_forum = MagicMock(spec=discord.ForumChannel)
        mock_forum.type = MagicMock(value=15)
        mock_forum.flags = discord.ChannelFlags(require_tag=False)
        mock_forum.create_thread = create_thread
        ch, _ = _make_mock_channel()
        ch._resolve_channel = AsyncMock(return_value=mock_forum)  # type: ignore[method-assign]
        return ch

    @pytest.mark.asyncio
    async def test_forum_thread_carries_the_files(self, tmp_path: Path) -> None:
        from app.channels.types.messages import MediaAttachment, MediaType

        report = tmp_path / "report.txt"
        report.write_text("data")
        thread = MagicMock(id=99, message=MagicMock(id=88), send=AsyncMock())
        create_thread = AsyncMock(return_value=thread)
        ch = self._forum_channel(create_thread)
        attachment = MediaAttachment(media_type=MediaType.DOCUMENT, path=str(report), filename="report.txt")
        msg = OutboundMessage(channel="discord", recipient_id="123", content="Weekly", user_id="u1", media=(attachment,))

        assert await ch.send(msg) == "88"

        files = create_thread.call_args.kwargs["files"]
        assert [f.filename for f in files] == ["report.txt"]
        for f in files:
            f.close()

    @pytest.mark.asyncio
    async def test_forum_placeholder_failure_stays_soft(self) -> None:
        ch = self._forum_channel(AsyncMock(side_effect=self._http_error(500)))

        assert await ch.send_placeholder("123", "thinking") is None


@pytest.mark.skip(reason="Placeholder: not implemented")
class TestDiscordInboundBranches:
    """Additional inbound tests for branch coverage."""

    @pytest.mark.asyncio
    async def test_on_message_guild_requires_mention(self) -> None:
        pass

    @pytest.mark.asyncio
    async def test_on_message_empty_content_ignored(self) -> None:
        pass

    @pytest.mark.asyncio
    async def test_on_message_thread_detection(self) -> None:
        pass

    @pytest.mark.asyncio
    async def test_on_interaction_select_values(self) -> None:
        pass

    @pytest.mark.asyncio
    async def test_on_ready_sets_bot_id(self) -> None:
        pass

    """Unit tests for derive_thread_name."""

    def test_first_line(self) -> None:
        pass

    def test_empty_lines_skipped(self) -> None:
        pass

    def test_truncation(self) -> None:
        pass

    def test_empty_string_fallback(self) -> None:
        pass

    def test_whitespace_only_fallback(self) -> None:
        pass


@pytest.mark.skip(reason="Forum send covered in test_discord_channel.py")
class TestDiscordForumSend:
    """Tests for Forum channel auto-thread-post in send()."""

    @pytest.mark.asyncio
    async def test_send_to_forum_creates_thread(self) -> None:
        pass

    @pytest.mark.asyncio
    async def test_send_to_forum_multi_chunk(self) -> None:
        pass

    @pytest.mark.asyncio
    async def test_send_to_forum_failure_returns_none(self) -> None:
        pass

    @pytest.mark.asyncio
    async def test_send_to_non_forum_guild_channel(self) -> None:
        """Non-forum GuildChannel should use normal send path."""
        ch, client = _make_mock_channel()
        mock_ch = _make_mock_messageable()
        mock_ch.type = discord.ChannelType.text
        client.get_channel = MagicMock(return_value=mock_ch)

        msg = _make_msg(content="Normal message")
        result = await ch.send(msg)
        assert result == "42"
        mock_ch.send.assert_called()


@pytest.mark.skip(reason="Placeholder: not implemented")
class TestDiscordCreateThread:
    """Tests for create_thread() method."""

    @pytest.mark.asyncio
    async def test_create_thread_on_message(self) -> None:
        pass

    @pytest.mark.asyncio
    async def test_create_thread_standalone(self) -> None:
        pass

    @pytest.mark.asyncio
    async def test_create_thread_in_forum(self) -> None:
        pass

    @pytest.mark.asyncio
    async def test_create_thread_unresolvable_channel(self) -> None:
        pass

    @pytest.mark.asyncio
    async def test_create_thread_unsupported_channel_type(self) -> None:
        pass

    @pytest.mark.asyncio
    async def test_create_thread_name_truncation(self) -> None:
        pass

    @pytest.mark.asyncio
    async def test_create_thread_failure_returns_none(self) -> None:
        pass
