"""Tests for Matrix channel implementation (mautrix SDK)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.core.base import BaseChannel
from app.channels.providers.matrix import MatrixChannel
from app.channels.providers.matrix.channel import _MAUTRIX_AVAILABLE
from app.channels.providers.matrix.media import (
    send_media,
)
from app.channels.types import (
    ChannelStatus,
    IssueKind,
    IssueSeverity,
    MediaAttachment,
    MediaType,
    OutboundMessage,
)

from .channel_test_base import ChannelTestBase

_requires_mautrix = pytest.mark.skipif(not _MAUTRIX_AVAILABLE, reason="mautrix not installed")


class TestMatrixChannelContract(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return MatrixChannel(homeserver="https://matrix.test.com", access_token="test_token")


class TestMatrixInit:
    def test_defaults(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        assert ch._homeserver == "https://matrix.example.com"
        assert ch._access_token == "tok"
        assert ch._user_id == ""
        assert ch._encryption is False
        assert ch._proxy == ""
        assert ch._client is None

    def test_trailing_slash_stripped(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com/", access_token="tok")
        assert ch._homeserver == "https://matrix.example.com"

    def test_encryption_flag(self) -> None:
        ch = MatrixChannel(
            homeserver="https://matrix.example.com",
            access_token="tok",
            encryption="true",
        )
        assert ch._encryption is True

    def test_password_auth_config(self) -> None:
        ch = MatrixChannel(
            homeserver="https://matrix.example.com",
            user_id="@bot:example.com",
            password="secret",
        )
        assert ch._password == "secret"
        assert ch._user_id == "@bot:example.com"
        assert ch._access_token == ""

    def test_proxy_config(self) -> None:
        ch = MatrixChannel(
            homeserver="https://matrix.example.com",
            access_token="tok",
            proxy="http://proxy:8080",
        )
        assert ch._proxy == "http://proxy:8080"


class TestMatrixCollectIssues:
    def test_no_issues(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        with patch("app.channels.providers.matrix.channel._MAUTRIX_AVAILABLE", True):
            issues = ch.collect_issues()
        assert len(issues) == 0

    def test_missing_homeserver(self) -> None:
        ch = MatrixChannel(homeserver="", access_token="tok")
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert issues[0].kind == IssueKind.CONFIG
        assert "homeserver" in issues[0].message

    def test_missing_credentials(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="")
        with patch("app.channels.providers.matrix.channel._MAUTRIX_AVAILABLE", True):
            issues = ch.collect_issues()
        assert len(issues) == 1
        assert "access_token" in issues[0].message or "password" in issues[0].message

    def test_error_status(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        ch._status = ChannelStatus.ERROR
        issues = ch.collect_issues()
        assert any(i.kind == IssueKind.AUTH for i in issues)

    def test_encryption_without_deps(self) -> None:
        ch = MatrixChannel(
            homeserver="https://matrix.example.com",
            access_token="tok",
            encryption="true",
        )
        with patch(
            "app.channels.providers.matrix.channel._MAUTRIX_AVAILABLE", True,
        ), patch(
            "app.channels.providers.matrix.crypto.check_e2ee_deps",
            return_value=False,
        ):
            issues = ch.collect_issues()
        dep_issues = [i for i in issues if i.kind == IssueKind.DEPENDENCY]
        assert len(dep_issues) == 1
        assert "E2EE" in dep_issues[0].message

    def test_encryption_without_device_id(self) -> None:
        ch = MatrixChannel(
            homeserver="https://matrix.example.com",
            access_token="tok",
            encryption="true",
        )
        with patch(
            "app.channels.providers.matrix.crypto.check_e2ee_deps",
            return_value=True,
        ):
            issues = ch.collect_issues()
        config_warnings = [
            i for i in issues if i.kind == IssueKind.CONFIG and i.severity == IssueSeverity.WARNING
        ]
        assert len(config_warnings) == 1
        assert "device_id" in config_warnings[0].message

    def test_mautrix_not_installed(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        with patch(
            "app.channels.providers.matrix.channel._MAUTRIX_AVAILABLE",
            False,
        ):
            issues = ch.collect_issues()
        dep_issues = [i for i in issues if i.kind == IssueKind.DEPENDENCY]
        assert len(dep_issues) == 1
        assert "mautrix" in dep_issues[0].message
        assert dep_issues[0].fix == "uv sync --extra matrix"


class TestMatrixHealthCheck:
    @pytest.mark.asyncio
    async def test_health_idle_status(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_health_no_client(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        ch._status = ChannelStatus.RUNNING
        assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_health_success(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        ch._status = ChannelStatus.RUNNING
        mock_client = AsyncMock()
        mock_client.whoami = AsyncMock(return_value=MagicMock())
        ch._client = mock_client
        assert await ch.health_check() is True

    @pytest.mark.asyncio
    async def test_health_whoami_fails(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        ch._status = ChannelStatus.RUNNING
        mock_client = AsyncMock()
        mock_client.whoami = AsyncMock(side_effect=Exception("connection refused"))
        ch._client = mock_client
        assert await ch.health_check() is False


class TestMatrixStart:
    @pytest.mark.asyncio
    async def test_start_no_config(self) -> None:
        ch = MatrixChannel(homeserver="", access_token="")
        await ch.start()
        assert ch._status != ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_no_credentials(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="")
        await ch.start()
        assert ch._status != ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_mautrix_not_available(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        with patch(
            "app.channels.providers.matrix.channel._MAUTRIX_AVAILABLE",
            False,
        ):
            await ch.start()
        assert ch._status == ChannelStatus.ERROR


class TestMatrixStop:
    @pytest.mark.asyncio
    async def test_stop_no_task(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        ch._status = ChannelStatus.RUNNING
        ch._sync_task = None
        ch._client = None
        await ch.stop()
        assert ch._status == ChannelStatus.STOPPED

    @pytest.mark.asyncio
    async def test_stop_with_task(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        ch._status = ChannelStatus.RUNNING

        async def _dummy() -> None:
            await asyncio.sleep(100)

        task = asyncio.create_task(_dummy())
        ch._sync_task = task
        ch._client = None

        await ch.stop()
        assert ch._status == ChannelStatus.STOPPED
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_stop_cleans_up_client(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        ch._status = ChannelStatus.RUNNING
        ch._sync_task = None

        mock_session = AsyncMock()
        mock_client = MagicMock()
        mock_client.api.session = mock_session
        ch._client = mock_client

        with patch(
            "app.channels.providers.matrix.crypto.cleanup_e2ee",
            new_callable=AsyncMock,
        ):
            await ch.stop()

        assert ch._client is None
        mock_session.close.assert_called_once()


@_requires_mautrix
class TestMatrixSend:
    @pytest.mark.asyncio
    async def test_send_not_running(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        msg = MagicMock(spec=OutboundMessage)
        msg.recipient_id = "!room:example.com"
        msg.content = "hello"
        msg.media = ()
        msg.reply_to_id = ""
        result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_text_success(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        ch._status = ChannelStatus.RUNNING
        mock_client = AsyncMock()
        mock_client.send_message_event = AsyncMock(return_value="$ev1")
        mock_client.get_joined_members = AsyncMock(return_value={})
        ch._client = mock_client

        msg = MagicMock(spec=OutboundMessage)
        msg.recipient_id = "!room:example.com"
        msg.content = "hello"
        msg.media = ()
        msg.reply_to_id = None
        msg.channel = "matrix"
        msg.user_id = "@user:example.com"
        msg.metadata = None

        result = await ch.send(msg)
        assert result == "$ev1"

    @pytest.mark.asyncio
    async def test_send_text_failure(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        ch._status = ChannelStatus.RUNNING
        mock_client = AsyncMock()
        mock_client.send_message_event = AsyncMock(side_effect=Exception("forbidden"))
        mock_client.get_joined_members = AsyncMock(return_value={})
        ch._client = mock_client

        msg = MagicMock(spec=OutboundMessage)
        msg.recipient_id = "!room:example.com"
        msg.content = "hello"
        msg.media = ()
        msg.reply_to_id = None
        msg.channel = "matrix"
        msg.user_id = "@user:example.com"
        msg.metadata = None

        result = await ch.send(msg)
        assert result is None


@_requires_mautrix
class TestMatrixEditDelete:
    @pytest.mark.asyncio
    async def test_edit_message(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        mock_client = AsyncMock()
        mock_client.send_message_event = AsyncMock(return_value="$ev2")
        ch._client = mock_client

        await ch.edit_message("!room:example.com", "$ev1", "updated")
        mock_client.send_message_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_edit_no_client(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        await ch.edit_message("!room:example.com", "$ev1", "updated")

    @pytest.mark.asyncio
    async def test_delete_message(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        mock_client = AsyncMock()
        mock_client.redact = AsyncMock()
        ch._client = mock_client

        await ch.delete_message("!room:example.com", "$ev1")
        mock_client.redact.assert_called_once()

    @pytest.mark.asyncio
    async def test_react_to_message(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        mock_client = AsyncMock()
        mock_client.send_message_event = AsyncMock(return_value="$ev_react")
        ch._client = mock_client

        await ch.react_to_message("!room:example.com", "$ev1", "+1")
        mock_client.send_message_event.assert_called_once()


@_requires_mautrix
class TestMatrixTyping:
    @pytest.mark.asyncio
    async def test_start_typing(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        mock_client = AsyncMock()
        mock_client.set_typing = AsyncMock()
        ch._client = mock_client

        await ch.start_typing("!room:example.com")
        mock_client.set_typing.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_typing(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        mock_client = AsyncMock()
        mock_client.set_typing = AsyncMock()
        ch._client = mock_client

        await ch.stop_typing("!room:example.com")
        mock_client.set_typing.assert_called_once()

    @pytest.mark.asyncio
    async def test_typing_no_client(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        await ch.start_typing("!room:example.com")
        await ch.stop_typing("!room:example.com")


@_requires_mautrix
class TestMatrixOnRoomMessage:
    """Tests for _on_room_message event handler.

    Uses DM rooms (is_group=False) to bypass SELECTIVE_POLICY mention check.
    """

    @pytest.mark.asyncio
    async def test_text_message_dm(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        ch._user_id = "@bot:example.com"
        ch._bot_id = "@bot:example.com"
        ch._status = ChannelStatus.RUNNING
        ch._dm_rooms = {"!dm:example.com": True}

        handler = AsyncMock()
        ch.set_inbound_handler(handler)

        event = MagicMock()
        event.room_id = "!dm:example.com"
        event.sender = "@user:example.com"
        event.event_id = "$ev100"
        content = MagicMock()
        content.msgtype = "m.text"
        content.body = "hello"
        content.url = None
        content.file = None
        content.relates_to = None
        event.content = content

        await ch._on_room_message(event)
        handler.assert_called_once()
        inbound = handler.call_args[0][0]
        assert inbound.content == "hello"
        assert inbound.sender_id == "@user:example.com"
        assert inbound.is_group is False

    @pytest.mark.asyncio
    async def test_group_message_with_mention(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        ch._user_id = "@bot:example.com"
        ch._bot_id = "@bot:example.com"
        ch._status = ChannelStatus.RUNNING

        handler = AsyncMock()
        ch.set_inbound_handler(handler)

        event = MagicMock()
        event.room_id = "!room:example.com"
        event.sender = "@user:example.com"
        event.event_id = "$ev100m"
        content = MagicMock()
        content.msgtype = "m.text"
        content.body = "@bot:example.com hello"
        content.url = None
        content.file = None
        content.relates_to = None
        event.content = content

        await ch._on_room_message(event)
        handler.assert_called_once()
        inbound = handler.call_args[0][0]
        assert inbound.mentioned is True
        assert inbound.is_group is True

    @pytest.mark.asyncio
    async def test_self_message_filtered(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        ch._user_id = "@bot:example.com"

        handler = AsyncMock()
        ch.set_inbound_handler(handler)

        event = MagicMock()
        event.room_id = "!room:example.com"
        event.sender = "@bot:example.com"
        event.event_id = "$ev101"
        event.content = MagicMock()

        await ch._on_room_message(event)
        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_dm_detection(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        ch._user_id = "@bot:example.com"
        ch._bot_id = "@bot:example.com"
        ch._status = ChannelStatus.RUNNING
        ch._dm_rooms = {"!dm_room:example.com": True}

        handler = AsyncMock()
        ch.set_inbound_handler(handler)

        event = MagicMock()
        event.room_id = "!dm_room:example.com"
        event.sender = "@user:example.com"
        event.event_id = "$ev102"
        content = MagicMock()
        content.msgtype = "m.text"
        content.body = "hello dm"
        content.url = None
        content.file = None
        content.relates_to = None
        event.content = content

        await ch._on_room_message(event)
        handler.assert_called_once()
        inbound = handler.call_args[0][0]
        assert inbound.is_group is False

    @pytest.mark.asyncio
    async def test_image_message_dm(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        ch._user_id = "@bot:example.com"
        ch._bot_id = "@bot:example.com"
        ch._status = ChannelStatus.RUNNING
        ch._dm_rooms = {"!dm:example.com": True}

        handler = AsyncMock()
        ch.set_inbound_handler(handler)

        event = MagicMock()
        event.room_id = "!dm:example.com"
        event.sender = "@user:example.com"
        event.event_id = "$ev103"
        content = MagicMock()
        content.msgtype = "m.image"
        content.body = "photo.jpg"
        content.url = "mxc://example.com/img"
        content.file = None
        content.relates_to = None
        event.content = content

        await ch._on_room_message(event)
        handler.assert_called_once()
        inbound = handler.call_args[0][0]
        assert len(inbound.media) == 1
        assert inbound.media[0].media_type == MediaType.IMAGE


@_requires_mautrix
class TestMatrixSendMedia:
    @pytest.mark.asyncio
    async def test_send_media_mxc_url(self) -> None:
        mock_client = AsyncMock()
        mock_client.send_message_event = AsyncMock(return_value="$media_ev")

        att = MediaAttachment(
            url="mxc://example.com/img",
            media_type=MediaType.IMAGE,
            filename="pic.jpg",
        )
        result = await send_media(mock_client, "!room:example.com", att, False)
        assert result == "$media_ev"

    @pytest.mark.asyncio
    async def test_send_media_no_url_no_path(self) -> None:
        mock_client = AsyncMock()
        att = MediaAttachment(media_type=MediaType.IMAGE)
        result = await send_media(mock_client, "!room:example.com", att, False)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_media_no_client(self) -> None:
        att = MediaAttachment(
            url="mxc://example.com/img",
            media_type=MediaType.IMAGE,
        )
        result = await send_media(None, "!room:example.com", att, False)
        assert result is None


class TestMatrixCredentialSpec:
    def test_credential_spec_config_key(self) -> None:
        assert MatrixChannel.credential_spec is not None
        assert MatrixChannel.credential_spec.config_key == "matrixCredentials"

    def test_credential_spec_fields(self) -> None:
        assert MatrixChannel.credential_spec is not None
        field_names = {name for name, _ in MatrixChannel.credential_spec.fields}
        assert "homeserver" in field_names
        assert "access_token" in field_names
        assert "user_id" in field_names
        assert "password" in field_names
        assert "device_id" in field_names
        assert "encryption" in field_names
        assert "proxy" in field_names


class TestMatrixCapabilities:
    def test_capabilities(self) -> None:
        assert MatrixChannel.capabilities.text is True
        assert MatrixChannel.capabilities.markdown is True
        assert MatrixChannel.capabilities.media is True
        assert MatrixChannel.capabilities.threads is True
        assert MatrixChannel.capabilities.edit is True
        assert MatrixChannel.capabilities.delete is True
        assert MatrixChannel.capabilities.reactions is True


@_requires_mautrix
class TestRefreshDmCache:
    """Tests for refresh_dm_cache in-place mutation behavior."""

    @pytest.mark.asyncio
    async def test_dm_cache_mutates_in_place(self) -> None:
        from mautrix.client import Client

        from app.channels.providers.matrix.auth import (
            refresh_dm_cache,
        )

        mock_client = MagicMock(spec=Client)
        dm_data = {
            "@user:example.com": ["!dm_room:example.com"],
        }
        mock_client.get_account_data = AsyncMock(return_value=dm_data)

        joined = {"!dm_room:example.com", "!group_room:example.com"}
        dm_rooms: dict[str, bool] = {}
        await refresh_dm_cache(mock_client, joined, dm_rooms)

        assert dm_rooms.get("!dm_room:example.com") is True
        assert dm_rooms.get("!group_room:example.com") is False
        assert len(dm_rooms) == 2

    @pytest.mark.asyncio
    async def test_dm_cache_clears_old_entries(self) -> None:
        from mautrix.client import Client

        from app.channels.providers.matrix.auth import (
            refresh_dm_cache,
        )

        mock_client = MagicMock(spec=Client)
        mock_client.get_account_data = AsyncMock(return_value={})

        dm_rooms = {"!old_room:example.com": True}
        await refresh_dm_cache(mock_client, {"!new_room:example.com"}, dm_rooms)

        assert "!old_room:example.com" not in dm_rooms
        assert dm_rooms.get("!new_room:example.com") is False


@_requires_mautrix
class TestAutoJoinDmRefresh:
    """Tests that _auto_join refreshes DM cache after joining."""

    @pytest.mark.asyncio
    async def test_auto_join_refreshes_dm_cache(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        ch._user_id = "@bot:example.com"

        mock_client = AsyncMock()
        ch._client = mock_client

        with patch(
            "app.channels.providers.matrix.channel.auto_join",
            new_callable=AsyncMock,
        ), patch(
            "app.channels.providers.matrix.channel.refresh_dm_cache",
            new_callable=AsyncMock,
        ) as mock_refresh:
            await ch._auto_join(mock_client, "!new_room:example.com")

            assert "!new_room:example.com" in ch._joined_rooms
            mock_refresh.assert_called_once_with(
                mock_client, ch._joined_rooms, ch._dm_rooms,
            )


@_requires_mautrix
class TestMembersCacheTtl:
    """Tests for _room_members_cache TTL behavior."""

    @pytest.mark.asyncio
    async def test_cache_hit_within_ttl(self) -> None:
        import time

        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        mock_client = AsyncMock()
        ch._client = mock_client

        ch._room_members_cache["!room:example.com"] = {"Alice": "@alice:example.com"}
        ch._room_members_ts["!room:example.com"] = time.monotonic()

        result = await ch._get_room_members("!room:example.com")
        assert result == {"Alice": "@alice:example.com"}
        mock_client.get_joined_members.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_expired(self) -> None:
        import time

        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        mock_client = AsyncMock()
        mock_client.get_joined_members = AsyncMock(return_value={
            "@bob:example.com": MagicMock(displayname="Bob", display_name="Bob"),
        })
        ch._client = mock_client

        ch._room_members_cache["!room:example.com"] = {"Alice": "@alice:example.com"}
        ch._room_members_ts["!room:example.com"] = time.monotonic() - 400.0

        result = await ch._get_room_members("!room:example.com")
        assert "Bob" in result
        mock_client.get_joined_members.assert_called_once()
