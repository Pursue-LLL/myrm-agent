"""Tests for IRC channel implementation."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.core.base import BaseChannel
from app.channels.providers.irc import (
    IRCChannel,
    _sanitize_outbound,
    _strip_irc_control_chars,
)
from app.channels.types import (
    ChannelStatus,
    IssueKind,
    IssueSeverity,
    OutboundMessage,
)

from .channel_test_base import ChannelTestBase


class TestIRCChannelContract(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return IRCChannel(server="irc.test.com", nick="testbot", channels=("#test",))


class TestStripControlChars:
    def test_removes_bold(self) -> None:
        assert _strip_irc_control_chars("\x02bold\x02") == "bold"

    def test_removes_color_codes(self) -> None:
        assert _strip_irc_control_chars("\x034red text\x03") == "red text"

    def test_removes_color_with_bg(self) -> None:
        assert _strip_irc_control_chars("\x034,12colored\x03") == "colored"

    def test_removes_italic(self) -> None:
        assert _strip_irc_control_chars("\x1ditalic\x1d") == "italic"

    def test_removes_underline(self) -> None:
        assert _strip_irc_control_chars("\x1funderline\x1f") == "underline"

    def test_removes_reverse(self) -> None:
        assert _strip_irc_control_chars("\x16reverse\x16") == "reverse"

    def test_removes_strikethrough(self) -> None:
        assert _strip_irc_control_chars("\x1estrikethrough\x1e") == "strikethrough"

    def test_removes_reset(self) -> None:
        assert _strip_irc_control_chars("text\x0f") == "text"

    def test_plain_text_unchanged(self) -> None:
        assert _strip_irc_control_chars("hello world") == "hello world"

    def test_mixed_controls(self) -> None:
        assert _strip_irc_control_chars("\x02\x034hi\x03\x02") == "hi"


class TestSanitizeOutbound:
    def test_removes_cr(self) -> None:
        assert _sanitize_outbound("hello\rworld") == "helloworld"

    def test_removes_newline(self) -> None:
        assert _sanitize_outbound("line1\nline2") == "line1 line2"

    def test_removes_crlf(self) -> None:
        assert _sanitize_outbound("cmd\r\nQUIT") == "cmd QUIT"

    def test_strips_control_chars(self) -> None:
        assert _sanitize_outbound("\x02bold\x02") == "bold"

    def test_strips_whitespace(self) -> None:
        assert _sanitize_outbound("  hello  ") == "hello"

    def test_empty_returns_empty(self) -> None:
        assert _sanitize_outbound("  \x02  ") == ""


class TestIRCChannelInit:
    def test_default_values(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot")
        assert ch._server == "irc.example.com"
        assert ch._nick == "bot"
        assert ch._port == 6667
        assert ch._use_ssl is False
        assert ch._password == ""
        assert ch._nickserv_password == ""
        assert len(ch._channels) == 0

    def test_custom_values(self) -> None:
        ch = IRCChannel(
            server="irc.example.com",
            nick="bot",
            port=6697,
            use_ssl=True,
            password="pass",
            nickserv_password="nspass",
            channels=["#test"],
        )
        assert ch._port == 6697
        assert ch._use_ssl is True
        assert ch._password == "pass"
        assert ch._nickserv_password == "nspass"
        assert "#test" in ch._channels


class TestIRCCollectIssues:
    def test_no_issues_when_configured(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot")
        issues = ch.collect_issues()
        assert len(issues) == 0

    def test_missing_server(self) -> None:
        ch = IRCChannel(server="", nick="bot")
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert issues[0].kind == IssueKind.CONFIG
        assert issues[0].severity == IssueSeverity.ERROR
        assert "server" in issues[0].message

    def test_missing_nick(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="")
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert "nick" in issues[0].message

    def test_missing_both(self) -> None:
        ch = IRCChannel(server="", nick="")
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert "server" in issues[0].message
        assert "nick" in issues[0].message

    def test_error_status(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot")
        ch._status = ChannelStatus.ERROR
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert issues[0].kind == IssueKind.RUNTIME


class TestIRCHealthCheck:
    @pytest.mark.asyncio
    async def test_health_running(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot")
        ch._writer = MagicMock()
        ch._writer.is_closing.return_value = False
        assert await ch.health_check() is True

    @pytest.mark.asyncio
    async def test_health_no_writer(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot")
        assert await ch.health_check() is False


class TestIRCSend:
    @pytest.mark.asyncio
    async def test_send_no_writer(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot")
        msg = MagicMock(spec=OutboundMessage)
        msg.recipient_id = "#test"
        msg.content = "hello"
        result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_with_writer(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot")
        ch._writer = MagicMock()

        msg = MagicMock(spec=OutboundMessage)
        msg.recipient_id = "#test"
        msg.content = "hello world"

        with (
            patch(
                "app.channels.providers.irc.render",
                return_value=["hello world"],
            ),
            patch.object(ch, "_send_raw", new_callable=AsyncMock) as mock_raw,
        ):
            await ch.send(msg)

        mock_raw.assert_called_once_with("PRIVMSG #test :hello world")


class TestIRCStart:
    @pytest.mark.asyncio
    async def test_start_no_server(self) -> None:
        ch = IRCChannel(server="", nick="bot")
        await ch.start()
        assert ch._status != ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_no_nick(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="")
        await ch.start()
        assert ch._status != ChannelStatus.RUNNING


class TestIRCStop:
    @pytest.mark.asyncio
    async def test_stop(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot")
        ch._status = ChannelStatus.RUNNING
        await ch.stop()
        assert ch._status == ChannelStatus.STOPPED


class TestIRCSendRaw:
    @pytest.mark.asyncio
    async def test_send_raw(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot")
        writer = MagicMock()
        writer.is_closing.return_value = False
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        ch._writer = writer

        await ch._send_raw("NICK testbot")
        writer.write.assert_called_once_with(b"NICK testbot\r\n")
        writer.drain.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_raw_no_writer(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot")
        await ch._send_raw("NICK testbot")

    @pytest.mark.asyncio
    async def test_send_raw_closing(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot")
        writer = MagicMock()
        writer.is_closing.return_value = True
        ch._writer = writer
        await ch._send_raw("NICK testbot")
        writer.write.assert_not_called()


class TestIRCQuitAndDisconnect:
    @pytest.mark.asyncio
    async def test_quit_and_disconnect(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot")
        writer = MagicMock()
        writer.is_closing.return_value = False
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        ch._writer = writer

        await ch._quit_and_disconnect()
        writer.write.assert_called_with(b"QUIT :shutdown\r\n")
        assert ch._writer is None

    @pytest.mark.asyncio
    async def test_quit_no_writer(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot")
        await ch._quit_and_disconnect()

    @pytest.mark.asyncio
    async def test_disconnect_exception(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot")
        writer = MagicMock()
        writer.close = MagicMock(side_effect=OSError("broken"))
        writer.wait_closed = AsyncMock()
        ch._writer = writer
        await ch._disconnect()
        assert ch._writer is None


class TestIRCStartSuccess:
    @pytest.mark.asyncio
    async def test_start_sets_running(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot")

        async def fake_connect() -> None:
            await asyncio.sleep(100)

        with patch.object(ch, "_connect_once", side_effect=fake_connect):
            await ch.start()

        assert ch._status == ChannelStatus.RUNNING
        assert ch._bot_id == "bot"
        assert ch._recv_task is not None
        ch._recv_task.cancel()
        try:
            await ch._recv_task
        except (asyncio.CancelledError, Exception):
            pass


class TestIRCReadLoop:
    @pytest.mark.asyncio
    async def test_ping_pong(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot")
        ch._status = ChannelStatus.RUNNING

        reader = AsyncMock()
        reader.readline = AsyncMock(side_effect=[b"PING :server1\r\n", b""])
        ch._reader = reader

        with patch.object(ch, "_send_raw", new_callable=AsyncMock) as mock_raw:
            await ch._read_loop()
        mock_raw.assert_called_once_with("PONG :server1")

    @pytest.mark.asyncio
    async def test_welcome_001_join_channels(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot", channels=["#test", "#dev"])
        ch._status = ChannelStatus.RUNNING

        reader = AsyncMock()
        reader.readline = AsyncMock(side_effect=[b":server 001 bot :Welcome\r\n", b""])
        ch._reader = reader

        with patch.object(ch, "_send_raw", new_callable=AsyncMock) as mock_raw:
            await ch._read_loop()
        calls = [c[0][0] for c in mock_raw.call_args_list]
        assert "JOIN #test" in calls
        assert "JOIN #dev" in calls

    @pytest.mark.asyncio
    async def test_nickserv_on_001(self) -> None:
        ch = IRCChannel(
            server="irc.example.com",
            nick="bot",
            nickserv_password="secret",
        )
        ch._status = ChannelStatus.RUNNING

        reader = AsyncMock()
        reader.readline = AsyncMock(side_effect=[b":server 001 bot :Welcome\r\n", b""])
        ch._reader = reader

        with patch.object(ch, "_send_raw", new_callable=AsyncMock) as mock_raw:
            await ch._read_loop()
        calls = [c[0][0] for c in mock_raw.call_args_list]
        assert "PRIVMSG NickServ :IDENTIFY bot secret" in calls

    @pytest.mark.asyncio
    async def test_nick_collision_433(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot")
        ch._status = ChannelStatus.RUNNING

        reader = AsyncMock()
        reader.readline = AsyncMock(side_effect=[b":server 433 * bot :Nickname in use\r\n", b""])
        ch._reader = reader

        with patch.object(ch, "_send_raw", new_callable=AsyncMock) as mock_raw:
            await ch._read_loop()
        assert ch._nick == "bot_"
        assert ch._bot_id == "bot_"
        calls = [c[0][0] for c in mock_raw.call_args_list]
        assert "NICK bot_" in calls

    @pytest.mark.asyncio
    async def test_privmsg_inbound(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot")
        ch._status = ChannelStatus.RUNNING

        reader = AsyncMock()
        reader.readline = AsyncMock(
            side_effect=[
                b":user!user@host PRIVMSG #test :hello world\r\n",
                b"",
            ]
        )
        ch._reader = reader

        with patch.object(ch, "_emit_inbound", new_callable=AsyncMock) as mock_emit:
            await ch._read_loop()
        mock_emit.assert_called_once()
        msg = mock_emit.call_args[0][0]
        assert msg.content == "hello world"
        assert msg.sender_id == "user"

    @pytest.mark.asyncio
    async def test_privmsg_self_filter(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot")
        ch._status = ChannelStatus.RUNNING

        reader = AsyncMock()
        reader.readline = AsyncMock(
            side_effect=[
                b":bot!bot@host PRIVMSG #test :self msg\r\n",
                b"",
            ]
        )
        ch._reader = reader

        with patch.object(ch, "_emit_inbound", new_callable=AsyncMock) as mock_emit:
            await ch._read_loop()
        mock_emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_privmsg_dm(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot")
        ch._status = ChannelStatus.RUNNING

        reader = AsyncMock()
        reader.readline = AsyncMock(
            side_effect=[
                b":user!user@host PRIVMSG bot :dm hello\r\n",
                b"",
            ]
        )
        ch._reader = reader

        with patch.object(ch, "_emit_inbound", new_callable=AsyncMock) as mock_emit:
            await ch._read_loop()
        mock_emit.assert_called_once()
        msg = mock_emit.call_args[0][0]
        assert msg.is_group is False
        assert msg.chat_id == "user"

    @pytest.mark.asyncio
    async def test_control_chars_stripped(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot")
        ch._status = ChannelStatus.RUNNING

        reader = AsyncMock()
        reader.readline = AsyncMock(
            side_effect=[
                b":user!user@host PRIVMSG #test :\x02bold\x02 text\r\n",
                b"",
            ]
        )
        ch._reader = reader

        with patch.object(ch, "_emit_inbound", new_callable=AsyncMock) as mock_emit:
            await ch._read_loop()
        msg = mock_emit.call_args[0][0]
        assert msg.content == "bold text"


class TestIRCConnectOnce:
    @pytest.mark.asyncio
    async def test_connect_once_plain(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot")
        ch._status = ChannelStatus.RUNNING

        mock_reader = AsyncMock()
        mock_reader.readline = AsyncMock(return_value=b"")
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = False
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()

        with patch(
            "asyncio.open_connection",
            new_callable=AsyncMock,
            return_value=(mock_reader, mock_writer),
        ):
            await ch._connect_once()

        calls_data = [c[0][0] for c in mock_writer.write.call_args_list]
        assert b"NICK bot\r\n" in calls_data
        assert b"USER bot 0 * :bot\r\n" in calls_data

    @pytest.mark.asyncio
    async def test_connect_once_with_password(self) -> None:
        ch = IRCChannel(server="irc.example.com", nick="bot", password="pw")
        ch._status = ChannelStatus.RUNNING

        mock_reader = AsyncMock()
        mock_reader.readline = AsyncMock(return_value=b"")
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = False
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()

        with patch(
            "asyncio.open_connection",
            new_callable=AsyncMock,
            return_value=(mock_reader, mock_writer),
        ):
            await ch._connect_once()

        calls_data = [c[0][0] for c in mock_writer.write.call_args_list]
        assert b"PASS pw\r\n" in calls_data
