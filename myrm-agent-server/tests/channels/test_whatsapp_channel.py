"""WhatsAppChannel — pure-function helpers, bridge event dispatch, inbound, send, lifecycle."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.core.base import BaseChannel
from app.channels.providers.whatsapp.channel import WhatsAppChannel
from app.channels.providers.whatsapp.helpers import (
    _normalize_jid,
    _prefer_pn_jid,
    _strip_device_suffix,
    check_mentioned,
    is_self_chat,
    parse_message_key,
)
from app.channels.types import (
    ChannelStatus,
    MediaAttachment,
    MediaType,
    OutboundMessage,
)

from .channel_test_base import ChannelTestBase


def _make_channel() -> WhatsAppChannel:
    ch = WhatsAppChannel(auth_dir="/tmp/test_wa_auth")
    ch._self_jid = "8615546316576:5@s.whatsapp.net"
    ch._connected.set()
    ch._process = MagicMock()
    ch._process.stdin = MagicMock()
    ch._process.stdin.write = MagicMock()
    ch._process.stdin.drain = AsyncMock()
    ch._process.returncode = None
    return ch


# ------------------------------------------------------------------
# Contract compliance
# ------------------------------------------------------------------


class TestWhatsAppChannel(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return WhatsAppChannel(auth_dir="/tmp/test_wa_auth_base")


# ------------------------------------------------------------------
# Pure-function helpers
# ------------------------------------------------------------------


class TestWhatsAppHelpers:
    """Tests for module-level pure helper functions."""

    def test_strip_device_suffix_with_device(self) -> None:
        assert _strip_device_suffix("8615546316576:5@s.whatsapp.net") == "8615546316576@s.whatsapp.net"

    def test_strip_device_suffix_no_device(self) -> None:
        assert _strip_device_suffix("8615546316576@s.whatsapp.net") == "8615546316576@s.whatsapp.net"

    def test_strip_device_suffix_no_at(self) -> None:
        assert _strip_device_suffix("8615546316576") == "8615546316576"

    def test_normalize_jid_already_valid(self) -> None:
        assert _normalize_jid("8615546316576@s.whatsapp.net") == "8615546316576@s.whatsapp.net"

    def test_normalize_jid_with_device(self) -> None:
        assert _normalize_jid("8615546316576:3@s.whatsapp.net") == "8615546316576@s.whatsapp.net"

    def test_normalize_jid_phone_number(self) -> None:
        assert _normalize_jid("+86-155-4631-6576") == "8615546316576@s.whatsapp.net"

    def test_normalize_jid_group(self) -> None:
        assert _normalize_jid("120363123456789@g.us") == "120363123456789@g.us"

    def test_prefer_pn_jid_primary_is_pn(self) -> None:
        result = _prefer_pn_jid("8615546316576@s.whatsapp.net", None)
        assert result == "8615546316576@s.whatsapp.net"

    def test_prefer_pn_jid_primary_is_lid_alt_is_pn(self) -> None:
        result = _prefer_pn_jid("abc123@lid", "8615546316576@s.whatsapp.net")
        assert result == "8615546316576@s.whatsapp.net"

    def test_prefer_pn_jid_primary_is_lid_no_alt(self) -> None:
        result = _prefer_pn_jid("abc123@lid", None)
        assert result == "abc123@lid"

    def test_prefer_pn_jid_strips_device(self) -> None:
        result = _prefer_pn_jid("8615546316576:5@s.whatsapp.net", None)
        assert result == "8615546316576@s.whatsapp.net"


# ------------------------------------------------------------------
# Bridge event dispatch
# ------------------------------------------------------------------


class TestWhatsAppBridgeEvents:
    """Tests for _handle_bridge_event dispatching."""

    @pytest.mark.asyncio
    async def test_qr_event(self) -> None:
        ch = _make_channel()
        ch._connected.clear()
        await ch._handle_bridge_event(json.dumps({"type": "qr", "data": "QR_CODE_DATA"}))
        assert ch._qr_code == "QR_CODE_DATA"
        assert not ch._connected.is_set()

    @pytest.mark.asyncio
    async def test_connection_open(self) -> None:
        ch = _make_channel()
        ch._connected.clear()
        await ch._handle_bridge_event(
            json.dumps(
                {
                    "type": "connection",
                    "status": "open",
                    "selfJid": "123@s.whatsapp.net",
                }
            )
        )
        assert ch._connected.is_set()
        assert ch._self_jid == "123@s.whatsapp.net"
        assert ch._qr_code is None

    @pytest.mark.asyncio
    async def test_connection_logged_out(self) -> None:
        ch = _make_channel()
        await ch._handle_bridge_event(json.dumps({"type": "connection", "status": "logged_out"}))
        assert not ch._connected.is_set()
        assert ch._status == ChannelStatus.ERROR

    @pytest.mark.asyncio
    async def test_connection_close(self) -> None:
        ch = _make_channel()
        await ch._handle_bridge_event(json.dumps({"type": "connection", "status": "close", "reason": "timeout"}))
        assert not ch._connected.is_set()

    @pytest.mark.asyncio
    async def test_connection_reconnecting(self) -> None:
        ch = _make_channel()
        await ch._handle_bridge_event(json.dumps({"type": "connection", "status": "reconnecting"}))

    @pytest.mark.asyncio
    async def test_message_event_dispatches_inbound(self) -> None:
        ch = _make_channel()
        emitted: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]
        await ch._handle_bridge_event(
            json.dumps(
                {
                    "type": "message",
                    "text": "hello",
                    "from": "999@s.whatsapp.net",
                    "id": "msg_001",
                }
            )
        )
        assert len(emitted) == 1
        assert emitted[0].content == "hello"

    @pytest.mark.asyncio
    async def test_groups_event(self) -> None:
        ch = _make_channel()
        await ch._handle_bridge_event(
            json.dumps(
                {
                    "type": "groups",
                    "data": [
                        {"jid": "group1@g.us", "name": "Group One"},
                        {"jid": "group2@g.us", "name": "Group Two"},
                        {"jid": "invalid_jid", "name": "Not a group"},
                    ],
                }
            )
        )
        assert len(ch._groups_cache) == 2
        assert ch._groups_cache[0].name == "Group One"

    @pytest.mark.asyncio
    async def test_groups_event_resolves_future(self) -> None:
        ch = _make_channel()
        loop = asyncio.get_running_loop()
        ch._groups_future = loop.create_future()
        data = [{"jid": "g@g.us", "name": "G"}]
        await ch._handle_bridge_event(json.dumps({"type": "groups", "data": data}))
        assert ch._groups_future.done()
        assert ch._groups_future.result() == data

    @pytest.mark.asyncio
    async def test_sent_event(self) -> None:
        ch = _make_channel()
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, object]] = loop.create_future()
        ch._sent_futures["nonce123"] = fut
        await ch._handle_bridge_event(
            json.dumps(
                {
                    "type": "sent",
                    "nonce": "nonce123",
                    "key": {"id": "msg_key"},
                }
            )
        )
        assert fut.done()
        assert fut.result() == {"id": "msg_key"}

    @pytest.mark.asyncio
    async def test_lid_resolved_event(self) -> None:
        ch = _make_channel()
        await ch._handle_bridge_event(
            json.dumps(
                {
                    "type": "lid_resolved",
                    "lid": "abc@lid",
                    "pn": "123@s.whatsapp.net",
                }
            )
        )
        assert ch._lid_to_pn["abc@lid"] == "123@s.whatsapp.net"

    @pytest.mark.asyncio
    async def test_media_downloaded_event(self) -> None:
        ch = _make_channel()
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[str] = loop.create_future()
        ch._media_download_futures["msg_001"] = fut
        await ch._handle_bridge_event(
            json.dumps(
                {
                    "type": "media_downloaded",
                    "messageId": "msg_001",
                    "path": "/tmp/audio.ogg",
                    "size": 1024,
                }
            )
        )
        assert fut.done()
        assert fut.result() == "/tmp/audio.ogg"

    @pytest.mark.asyncio
    async def test_error_event(self) -> None:
        ch = _make_channel()
        await ch._handle_bridge_event(json.dumps({"type": "error", "message": "something broke"}))

    @pytest.mark.asyncio
    async def test_empty_event(self) -> None:
        ch = _make_channel()
        await ch._handle_bridge_event("")

    @pytest.mark.asyncio
    async def test_invalid_json(self) -> None:
        ch = _make_channel()
        await ch._handle_bridge_event("not json at all")

    @pytest.mark.asyncio
    async def test_edit_ok_event(self) -> None:
        ch = _make_channel()
        await ch._handle_bridge_event(json.dumps({"type": "edit_ok", "key": {"id": "k"}}))


# ------------------------------------------------------------------
# Inbound message handling
# ------------------------------------------------------------------


class TestWhatsAppInbound:
    """Tests for _handle_inbound — DM, group, self-chat, LID resolution."""

    @pytest.mark.asyncio
    async def test_inbound_dm(self) -> None:
        ch = _make_channel()
        emitted: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]
        event: dict[str, object] = {
            "type": "message",
            "text": "hi there",
            "from": "999@s.whatsapp.net",
            "id": "msg_001",
            "fromMe": False,
        }
        await ch._handle_inbound(event)
        assert len(emitted) == 1
        msg = emitted[0]
        assert msg.sender_id == "999@s.whatsapp.net"
        assert msg.is_group is False
        assert msg.mentioned is False

    @pytest.mark.asyncio
    async def test_inbound_group_with_mention(self) -> None:
        ch = _make_channel()
        emitted: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]
        event: dict[str, object] = {
            "type": "message",
            "text": "help me",
            "from": "group@g.us",
            "participant": "999@s.whatsapp.net",
            "isGroup": True,
            "mentionedJids": ["8615546316576@s.whatsapp.net"],
            "id": "msg_002",
        }
        await ch._handle_inbound(event)
        assert len(emitted) == 1
        assert emitted[0].is_group is True
        assert emitted[0].mentioned is True

    @pytest.mark.asyncio
    async def test_inbound_group_no_mention(self) -> None:
        ch = _make_channel()
        emitted: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]
        event: dict[str, object] = {
            "type": "message",
            "text": "random chat",
            "from": "group@g.us",
            "participant": "999@s.whatsapp.net",
            "isGroup": True,
            "mentionedJids": ["other@s.whatsapp.net"],
            "id": "msg_003",
        }
        await ch._handle_inbound(event)
        assert len(emitted) == 1
        assert emitted[0].mentioned is False

    @pytest.mark.asyncio
    async def test_inbound_self_chat(self) -> None:
        ch = _make_channel()
        emitted: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]
        event: dict[str, object] = {
            "type": "message",
            "text": "note to self",
            "from": "8615546316576@s.whatsapp.net",
            "fromMe": True,
            "id": "msg_004",
        }
        await ch._handle_inbound(event)
        assert len(emitted) == 1
        assert emitted[0].sender_id == "8615546316576@s.whatsapp.net"

    @pytest.mark.asyncio
    async def test_inbound_from_me_not_self_chat_ignored(self) -> None:
        ch = _make_channel()
        ch._emit_inbound = AsyncMock()  # type: ignore[assignment]
        event: dict[str, object] = {
            "type": "message",
            "text": "outbound echo",
            "from": "999@s.whatsapp.net",
            "fromMe": True,
            "id": "msg_005",
        }
        await ch._handle_inbound(event)
        ch._emit_inbound.assert_not_called()

    @pytest.mark.asyncio
    async def test_inbound_empty_text_no_audio(self) -> None:
        ch = _make_channel()
        ch._emit_inbound = AsyncMock()  # type: ignore[assignment]
        event: dict[str, object] = {
            "type": "message",
            "text": "",
            "from": "999@s.whatsapp.net",
            "id": "msg_006",
        }
        await ch._handle_inbound(event)
        ch._emit_inbound.assert_not_called()

    @pytest.mark.asyncio
    async def test_inbound_audio_message(self) -> None:
        ch = _make_channel()
        emitted: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]
        event: dict[str, object] = {
            "type": "message",
            "text": "",
            "from": "999@s.whatsapp.net",
            "audio": {"mimetype": "audio/ogg", "messageId": "audio_001", "ptt": True, "seconds": 5},
            "id": "msg_007",
        }
        await ch._handle_inbound(event)
        assert len(emitted) == 1
        assert len(emitted[0].media) == 1
        assert emitted[0].media[0].media_type.value == "audio"

    @pytest.mark.asyncio
    async def test_inbound_lid_resolution(self) -> None:
        ch = _make_channel()
        ch._lid_to_pn["abc@lid"] = "999@s.whatsapp.net"
        emitted: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]
        event: dict[str, object] = {
            "type": "message",
            "text": "from lid",
            "from": "abc@lid",
            "fromAlt": "999@s.whatsapp.net",
            "id": "msg_008",
        }
        await ch._handle_inbound(event)
        assert len(emitted) == 1
        assert emitted[0].sender_id == "999@s.whatsapp.net"
        assert emitted[0].chat_id == "999@s.whatsapp.net"


# ------------------------------------------------------------------
# Self-chat / LID detection
# ------------------------------------------------------------------


class TestWhatsAppSelfChat:
    """Tests for is_self_chat pure function."""

    _SELF_JID = "8615546316576@s.whatsapp.net"

    def test_self_chat_same_number(self) -> None:
        assert is_self_chat("8615546316576@s.whatsapp.net", self._SELF_JID, {}) is True

    def test_self_chat_different_number(self) -> None:
        assert is_self_chat("999@s.whatsapp.net", self._SELF_JID, {}) is False

    def test_self_chat_lid_resolved(self) -> None:
        lid_map = {"abc@lid": "8615546316576@s.whatsapp.net"}
        assert is_self_chat("abc@lid", self._SELF_JID, lid_map) is True

    def test_self_chat_lid_unresolved(self) -> None:
        assert is_self_chat("unknown@lid", self._SELF_JID, {}) is False

    def test_self_chat_no_self_jid(self) -> None:
        assert is_self_chat("8615546316576@s.whatsapp.net", None, {}) is False


# ------------------------------------------------------------------
# Mention detection
# ------------------------------------------------------------------


class TestWhatsAppMention:
    """Tests for check_mentioned pure function."""

    _SELF_JID = "8615546316576@s.whatsapp.net"

    def test_mentioned_exact_match(self) -> None:
        event: dict[str, object] = {"mentionedJids": ["8615546316576@s.whatsapp.net"]}
        assert check_mentioned(event, self._SELF_JID) is True

    def test_mentioned_with_device_suffix(self) -> None:
        event: dict[str, object] = {"mentionedJids": ["8615546316576:5@s.whatsapp.net"]}
        assert check_mentioned(event, self._SELF_JID) is True

    def test_not_mentioned(self) -> None:
        event: dict[str, object] = {"mentionedJids": ["other@s.whatsapp.net"]}
        assert check_mentioned(event, self._SELF_JID) is False

    def test_no_mentioned_jids(self) -> None:
        assert check_mentioned({}, self._SELF_JID) is False

    def test_no_self_jid(self) -> None:
        event: dict[str, object] = {"mentionedJids": ["8615546316576@s.whatsapp.net"]}
        assert check_mentioned(event, None) is False

    def test_reply_to_bot(self) -> None:
        event: dict[str, object] = {"replyToBot": True, "mentionedJids": []}
        assert check_mentioned(event, self._SELF_JID) is True

    def test_reply_to_bot_false(self) -> None:
        event: dict[str, object] = {"replyToBot": False, "mentionedJids": []}
        assert check_mentioned(event, self._SELF_JID) is False

    def test_reply_to_bot_absent(self) -> None:
        event: dict[str, object] = {"mentionedJids": []}
        assert check_mentioned(event, self._SELF_JID) is False

    def test_mentioned_via_lid_with_mapping(self) -> None:
        lid = "166589567639802@lid"
        event: dict[str, object] = {"mentionedJids": [lid]}
        lid_to_pn = {lid: "8615546316576@s.whatsapp.net"}
        assert check_mentioned(event, self._SELF_JID, lid_to_pn) is True

    def test_mentioned_via_lid_without_mapping(self) -> None:
        event: dict[str, object] = {"mentionedJids": ["166589567639802@lid"]}
        assert check_mentioned(event, self._SELF_JID) is False

    def test_mentioned_via_lid_wrong_mapping(self) -> None:
        lid = "166589567639802@lid"
        event: dict[str, object] = {"mentionedJids": [lid]}
        lid_to_pn = {lid: "8699999999999@s.whatsapp.net"}
        assert check_mentioned(event, self._SELF_JID, lid_to_pn) is False

    def test_mentioned_via_lid_empty_mapping(self) -> None:
        event: dict[str, object] = {"mentionedJids": ["166589567639802@lid"]}
        assert check_mentioned(event, self._SELF_JID, {}) is False


# ------------------------------------------------------------------
# Send / edit / delete
# ------------------------------------------------------------------


class TestWhatsAppSend:
    """Tests for send, send_placeholder, edit_message, delete_message."""

    @pytest.mark.asyncio
    async def test_send_text(self) -> None:
        ch = _make_channel()

        async def _resolve_sent(*_args: object, **_kwargs: object) -> None:
            await asyncio.sleep(0.01)
            for _nonce, fut in list(ch._sent_futures.items()):
                if not fut.done():
                    fut.set_result({"id": "key_123"})

        ch._process.stdin.write = MagicMock(side_effect=lambda _: asyncio.ensure_future(_resolve_sent()))

        msg = OutboundMessage(
            channel="whatsapp",
            recipient_id="999@s.whatsapp.net",
            content="Hello",
            user_id="U",
        )
        result = await ch.send(msg)
        assert result is not None
        key = json.loads(result)
        assert key["id"] == "key_123"

    @pytest.mark.asyncio
    async def test_send_not_connected(self) -> None:
        ch = _make_channel()
        ch._connected.clear()
        msg = OutboundMessage(
            channel="whatsapp",
            recipient_id="999@s.whatsapp.net",
            content="Hello",
            user_id="U",
        )
        with pytest.raises(RuntimeError, match="not connected"):
            await ch.send(msg)

    @pytest.mark.asyncio
    async def test_send_media(self) -> None:
        ch = _make_channel()
        msg = OutboundMessage(
            channel="whatsapp",
            recipient_id="999@s.whatsapp.net",
            content="",
            user_id="U",
            media=(MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/img.png", filename="img.png"),),
        )
        result = await ch.send(msg)
        assert result is None
        ch._process.stdin.write.assert_called()

    @pytest.mark.asyncio
    async def test_edit_message(self) -> None:
        ch = _make_channel()
        key = json.dumps({"id": "msg_key", "remoteJid": "999@s.whatsapp.net"})
        await ch.edit_message("999@s.whatsapp.net", key, "Updated text")
        ch._process.stdin.write.assert_called()

    @pytest.mark.asyncio
    async def test_edit_message_invalid_key(self) -> None:
        ch = _make_channel()
        await ch.edit_message("999@s.whatsapp.net", "not-json", "Updated text")

    @pytest.mark.asyncio
    async def test_delete_message(self) -> None:
        ch = _make_channel()
        key = json.dumps({"id": "msg_key"})
        await ch.delete_message(
            "999@s.whatsapp.net",
            key,
        )
        ch._process.stdin.write.assert_called()

    @pytest.mark.asyncio
    async def test_delete_message_invalid_key(self) -> None:
        ch = _make_channel()
        await ch.delete_message("999@s.whatsapp.net", "not-json")


# ------------------------------------------------------------------
# Typing / reactions / voice download
# ------------------------------------------------------------------


class TestWhatsAppActions:
    """Tests for start_typing, stop_typing, react_to_message, download_voice_message."""

    @pytest.mark.asyncio
    async def test_start_typing(self) -> None:
        ch = _make_channel()
        await ch.start_typing("999@s.whatsapp.net")
        ch._process.stdin.write.assert_called()

    @pytest.mark.asyncio
    async def test_stop_typing(self) -> None:
        ch = _make_channel()
        await ch.stop_typing("999@s.whatsapp.net")
        ch._process.stdin.write.assert_called()

    @pytest.mark.asyncio
    async def test_react_to_message(self) -> None:
        ch = _make_channel()
        await ch.react_to_message("999@s.whatsapp.net", "msg_001", "")
        ch._process.stdin.write.assert_called()

    @pytest.mark.asyncio
    async def test_react_not_connected(self) -> None:
        ch = _make_channel()
        ch._connected.clear()
        await ch.react_to_message("999@s.whatsapp.net", "msg_001", "")
        ch._process.stdin.write.assert_not_called()

    @pytest.mark.asyncio
    async def test_download_voice_message_not_connected(self) -> None:
        ch = _make_channel()
        ch._connected.clear()
        result = await ch.download_voice_message("msg_001")
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_lids_for_pns(self) -> None:
        ch = _make_channel()
        ch.resolve_lids_for_pns(["999@s.whatsapp.net"])
        ch._process.stdin.write.assert_called()

    @pytest.mark.asyncio
    async def test_resolve_lids_empty(self) -> None:
        ch = _make_channel()
        ch.resolve_lids_for_pns([])
        ch._process.stdin.write.assert_not_called()


# ------------------------------------------------------------------
# Health check
# ------------------------------------------------------------------


class TestWhatsAppHealthCheck:
    """Tests for health_check."""

    @pytest.mark.asyncio
    async def test_health_check_running(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        assert await ch.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_no_process(self) -> None:
        ch = _make_channel()
        ch._process = None
        assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_process_exited(self) -> None:
        ch = _make_channel()
        ch._process.returncode = 1
        assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_not_running_status(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.STOPPED
        assert await ch.health_check() is False


# ------------------------------------------------------------------
# Lifecycle
# ------------------------------------------------------------------


class TestWhatsAppLifecycle:
    """Tests for stop and _kill_process."""

    @pytest.mark.asyncio
    async def test_stop(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._process.wait = AsyncMock(return_value=0)
        await ch.stop()
        assert ch._status == ChannelStatus.STOPPED
        assert not ch._connected.is_set()

    @pytest.mark.asyncio
    async def test_stop_with_reader_task(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._process.wait = AsyncMock(return_value=0)

        async def _forever() -> None:
            await asyncio.sleep(999)

        ch._reader_task = asyncio.create_task(_forever())
        await ch.stop()
        assert ch._status == ChannelStatus.STOPPED

    @pytest.mark.asyncio
    async def test_stop_broken_pipe(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._process.stdin.write = MagicMock(side_effect=BrokenPipeError)
        ch._process.wait = AsyncMock(return_value=0)
        await ch.stop()
        assert ch._status == ChannelStatus.STOPPED

    @pytest.mark.asyncio
    async def test_properties(self) -> None:
        ch = _make_channel()
        ch._qr_code = "QR123"
        assert ch.qr_code == "QR123"
        assert ch.is_connected is True
        ch._connected.clear()
        assert ch.is_connected is False


# ------------------------------------------------------------------
# _write_cmd / _drain
# ------------------------------------------------------------------


class TestWhatsAppWriteCmd:
    """Tests for _write_cmd and _drain."""

    def test_write_cmd(self) -> None:
        ch = _make_channel()
        ch._write_cmd({"type": "test", "data": "value"})
        ch._process.stdin.write.assert_called_once()
        written = ch._process.stdin.write.call_args[0][0]
        parsed = json.loads(written.decode())
        assert parsed["type"] == "test"

    def test_write_cmd_no_process(self) -> None:
        ch = _make_channel()
        ch._process = None
        ch._write_cmd({"type": "test"})

    @pytest.mark.asyncio
    async def test_drain(self) -> None:
        ch = _make_channel()
        await ch._drain()
        ch._process.stdin.drain.assert_called_once()

    @pytest.mark.asyncio
    async def test_drain_broken_pipe(self) -> None:
        ch = _make_channel()
        ch._process.stdin.drain = AsyncMock(side_effect=BrokenPipeError)
        await ch._drain()

    @pytest.mark.asyncio
    async def test_drain_no_process(self) -> None:
        ch = _make_channel()
        ch._process = None
        await ch._drain()


# ------------------------------------------------------------------
# _parse_key
# ------------------------------------------------------------------


class TestWhatsAppParseKey:
    """Tests for parse_message_key pure function."""

    def test_parse_key_valid(self) -> None:
        assert parse_message_key(json.dumps({"id": "k1"})) == {"id": "k1"}

    def test_parse_key_invalid_json(self) -> None:
        assert parse_message_key("not-json") is None

    def test_parse_key_not_dict(self) -> None:
        assert parse_message_key(json.dumps([1, 2])) is None


# ------------------------------------------------------------------
# Start / spawn / node deps
# ------------------------------------------------------------------


class TestWhatsAppStart:
    """Tests for start() and related subprocess management."""

    @pytest.mark.asyncio
    async def test_start_success(self) -> None:
        ch = WhatsAppChannel(auth_dir="/tmp/test_wa_start")
        with (
            patch.object(ch, "_ensure_node_deps", new_callable=AsyncMock),
            patch.object(ch, "_spawn_bridge", new_callable=AsyncMock),
        ):
            await ch.start()
        assert ch._status == ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_failure(self) -> None:
        ch = WhatsAppChannel(auth_dir="/tmp/test_wa_start_fail")
        with patch.object(ch, "_ensure_node_deps", new_callable=AsyncMock, side_effect=RuntimeError("no node")):
            with pytest.raises(RuntimeError):
                await ch.start()
        assert ch._status == ChannelStatus.ERROR


# ------------------------------------------------------------------
# send_placeholder
# ------------------------------------------------------------------


class TestWhatsAppSendPlaceholder:
    """Tests for send_placeholder."""

    @pytest.mark.asyncio
    async def test_send_placeholder_success(self) -> None:
        ch = _make_channel()

        async def _resolve_sent() -> None:
            await asyncio.sleep(0.01)
            for _nonce, fut in list(ch._sent_futures.items()):
                if not fut.done():
                    fut.set_result({"id": "placeholder_key"})

        ch._process.stdin.write = MagicMock(side_effect=lambda _: asyncio.ensure_future(_resolve_sent()))
        result = await ch.send_placeholder("999@s.whatsapp.net", "Thinking...")
        assert result is not None
        key = json.loads(result)
        assert key["id"] == "placeholder_key"

    @pytest.mark.asyncio
    async def test_send_placeholder_not_connected(self) -> None:
        ch = _make_channel()
        ch._connected.clear()
        result = await ch.send_placeholder("999@s.whatsapp.net", "Thinking...")
        assert result is None

    @pytest.mark.asyncio
    async def test_send_placeholder_timeout(self) -> None:
        ch = _make_channel()
        with patch("asyncio.wait_for", side_effect=TimeoutError):
            result = await ch.send_placeholder("999@s.whatsapp.net", "Thinking...")
        assert result is None


# ------------------------------------------------------------------
# _send_media extended
# ------------------------------------------------------------------


class TestWhatsAppSendMedia:
    """Tests for _send_media with various attachment types."""

    def test_send_media_with_url(self) -> None:
        ch = _make_channel()
        attachment = MediaAttachment(
            media_type=MediaType.IMAGE,
            url="https://example.com/img.png",
            filename="img.png",
        )
        ch._send_media("999@s.whatsapp.net", attachment)
        written = ch._process.stdin.write.call_args[0][0]
        cmd = json.loads(written.decode())
        assert cmd["type"] == "send_media"
        assert cmd["url"] == "https://example.com/img.png"

    def test_send_media_with_path(self) -> None:
        ch = _make_channel()
        attachment = MediaAttachment(
            media_type=MediaType.DOCUMENT,
            path="/tmp/doc.pdf",
            filename="doc.pdf",
            mime_type="application/pdf",
        )
        ch._send_media("999@s.whatsapp.net", attachment)
        written = ch._process.stdin.write.call_args[0][0]
        cmd = json.loads(written.decode())
        assert cmd["path"] == "/tmp/doc.pdf"
        assert cmd["mimetype"] == "application/pdf"

    def test_send_media_with_caption(self) -> None:
        ch = _make_channel()
        attachment = MediaAttachment(
            media_type=MediaType.IMAGE,
            url="https://example.com/img.png",
            filename="img.png",
            caption="Look at this!",
        )
        ch._send_media("999@s.whatsapp.net", attachment)
        written = ch._process.stdin.write.call_args[0][0]
        cmd = json.loads(written.decode())
        assert cmd["caption"] == "Look at this!"


# ------------------------------------------------------------------
# download_voice_message
# ------------------------------------------------------------------


class TestWhatsAppDownloadVoice:
    """Tests for download_voice_message."""

    @pytest.mark.asyncio
    async def test_download_success(self) -> None:
        ch = _make_channel()

        async def _resolve_download() -> None:
            await asyncio.sleep(0.01)
            for _msg_id, fut in list(ch._media_download_futures.items()):
                if not fut.done():
                    fut.set_result("/tmp/audio.ogg")

        ch._process.stdin.write = MagicMock(side_effect=lambda _: asyncio.ensure_future(_resolve_download()))
        result = await ch.download_voice_message("msg_001")
        assert result is not None
        assert str(result) == "/tmp/audio.ogg"

    @pytest.mark.asyncio
    async def test_download_timeout(self) -> None:
        ch = _make_channel()
        with patch("asyncio.wait_for", side_effect=TimeoutError):
            result = await ch.download_voice_message("msg_001")
        assert result is None


# ------------------------------------------------------------------
# list_groups
# ------------------------------------------------------------------


class TestWhatsAppListGroups:
    """Tests for list_groups with cache."""

    @pytest.mark.asyncio
    async def test_list_groups_from_cache(self) -> None:
        import time as _time

        from app.channels.types import GroupInfo

        ch = _make_channel()
        ch._groups_cache = [GroupInfo(jid="g1@g.us", name="G1")]
        ch._groups_cache_time = _time.time()
        result = await ch.list_groups()
        assert len(result) == 1
        assert result[0].name == "G1"

    @pytest.mark.asyncio
    async def test_list_groups_not_connected(self) -> None:
        ch = _make_channel()
        ch._connected.clear()
        ch._groups_cache = []
        ch._groups_cache_time = 0.0
        result = await ch.list_groups(force_refresh=True)
        assert result == []

    @pytest.mark.asyncio
    async def test_list_groups_fetch_success(self) -> None:
        ch = _make_channel()
        ch._groups_cache = []
        ch._groups_cache_time = 0.0

        async def _resolve_groups() -> None:
            await asyncio.sleep(0.01)
            if ch._groups_future and not ch._groups_future.done():
                ch._groups_future.set_result([{"jid": "g2@g.us", "name": "G2"}])

        ch._process.stdin.write = MagicMock(side_effect=lambda _: asyncio.ensure_future(_resolve_groups()))
        result = await ch.list_groups(force_refresh=True)
        assert len(result) == 1
        assert result[0].name == "G2"

    @pytest.mark.asyncio
    async def test_list_groups_timeout(self) -> None:
        ch = _make_channel()
        ch._groups_cache = []
        ch._groups_cache_time = 0.0
        with patch("asyncio.wait_for", side_effect=TimeoutError):
            result = await ch.list_groups(force_refresh=True)
        assert result == []


# ------------------------------------------------------------------
# _kill_process
# ------------------------------------------------------------------


class TestWhatsAppKillProcess:
    """Tests for _kill_process."""

    @pytest.mark.asyncio
    async def test_kill_process_graceful(self) -> None:
        ch = _make_channel()
        proc = ch._process
        proc.terminate = MagicMock()
        proc.wait = AsyncMock(return_value=0)
        await ch._kill_process()
        proc.terminate.assert_called_once()
        assert ch._process is None

    @pytest.mark.asyncio
    async def test_kill_process_timeout_then_kill(self) -> None:
        ch = _make_channel()
        proc = ch._process
        proc.terminate = MagicMock()
        proc.kill = MagicMock()
        proc.wait = AsyncMock(return_value=0)
        with patch("asyncio.wait_for", side_effect=[TimeoutError, AsyncMock(return_value=0)()]):
            await ch._kill_process()
        proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_kill_process_already_exited(self) -> None:
        ch = _make_channel()
        ch._process.returncode = 0
        await ch._kill_process()
        assert ch._process is None

    @pytest.mark.asyncio
    async def test_kill_process_none(self) -> None:
        ch = _make_channel()
        ch._process = None
        await ch._kill_process()


# ------------------------------------------------------------------
# BridgeProcessMixin — subprocess management
# ------------------------------------------------------------------


class TestBridgeProcessMixin:
    """Tests for _ensure_node_deps, _spawn_bridge, _read_stderr, _read_stdout."""

    @pytest.mark.asyncio
    async def test_ensure_node_deps_already_installed(self) -> None:
        ch = _make_channel()
        with patch(
            "app.channels.providers.whatsapp.bridge._BRIDGE_DIR",
        ) as mock_dir:
            mock_dir.__truediv__ = lambda self, name: MagicMock(exists=MagicMock(return_value=True))
            await ch._ensure_node_deps()

    @pytest.mark.asyncio
    async def test_ensure_node_deps_no_node(self) -> None:
        ch = _make_channel()
        with (
            patch(
                "app.channels.providers.whatsapp.bridge._BRIDGE_DIR",
            ) as mock_dir,
            patch("shutil.which", return_value=None),
        ):
            mock_dir.__truediv__ = lambda self, name: MagicMock(exists=MagicMock(return_value=False))
            with pytest.raises(RuntimeError, match="Node.js not found"):
                await ch._ensure_node_deps()

    @pytest.mark.asyncio
    async def test_ensure_node_deps_no_npm(self) -> None:
        ch = _make_channel()
        with (
            patch(
                "app.channels.providers.whatsapp.bridge._BRIDGE_DIR",
            ) as mock_dir,
            patch("shutil.which", side_effect=lambda cmd: "/usr/bin/node" if cmd == "node" else None),
        ):
            mock_dir.__truediv__ = lambda self, name: MagicMock(exists=MagicMock(return_value=False))
            with pytest.raises(RuntimeError, match="npm not found"):
                await ch._ensure_node_deps()

    @pytest.mark.asyncio
    async def test_ensure_node_deps_npm_install_success(self) -> None:
        ch = _make_channel()
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with (
            patch(
                "app.channels.providers.whatsapp.bridge._BRIDGE_DIR",
            ) as mock_dir,
            patch("shutil.which", return_value="/usr/bin/fake"),
            patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc),
        ):
            mock_dir.__truediv__ = lambda self, name: MagicMock(exists=MagicMock(return_value=False))
            await ch._ensure_node_deps()

    @pytest.mark.asyncio
    async def test_ensure_node_deps_npm_install_failure(self) -> None:
        ch = _make_channel()
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error output"))
        mock_proc.returncode = 1

        with (
            patch(
                "app.channels.providers.whatsapp.bridge._BRIDGE_DIR",
            ) as mock_dir,
            patch("shutil.which", return_value="/usr/bin/fake"),
            patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc),
        ):
            mock_dir.__truediv__ = lambda self, name: MagicMock(exists=MagicMock(return_value=False))
            with pytest.raises(RuntimeError, match="npm install failed"):
                await ch._ensure_node_deps()

    @pytest.mark.asyncio
    async def test_spawn_bridge(self) -> None:
        ch = WhatsAppChannel(auth_dir="/tmp/test_wa_spawn")
        mock_proc = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stderr = MagicMock()
        mock_proc.stdin = MagicMock()

        with (
            patch("shutil.which", return_value="/usr/bin/node"),
            patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc),
            patch("asyncio.create_task") as mock_task,
        ):
            await ch._spawn_bridge()
        assert ch._process is mock_proc
        assert mock_task.call_count == 2

    @pytest.mark.asyncio
    async def test_read_stderr_logs_errors(self) -> None:
        ch = _make_channel()
        lines = [b"error line 1\n", b"error line 2\n", b""]
        ch._process.stderr = MagicMock()
        ch._process.stderr.readline = AsyncMock(side_effect=lines)

        await ch._read_stderr()

    @pytest.mark.asyncio
    async def test_read_stderr_no_process(self) -> None:
        ch = _make_channel()
        ch._process = None
        await ch._read_stderr()

    @pytest.mark.asyncio
    async def test_read_stderr_cancelled(self) -> None:
        ch = _make_channel()
        ch._process.stderr = MagicMock()
        ch._process.stderr.readline = AsyncMock(side_effect=asyncio.CancelledError)
        await ch._read_stderr()

    @pytest.mark.asyncio
    async def test_read_stdout_dispatches_events(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        event_data = json.dumps({"type": "qr", "data": "test_qr"})
        lines = [f"{event_data}\n".encode(), b""]
        ch._process.stdout = MagicMock()
        ch._process.stdout.readline = AsyncMock(side_effect=lines)
        ch._handle_bridge_event = AsyncMock()

        await ch._read_stdout()
        ch._handle_bridge_event.assert_called_once_with(event_data)

    @pytest.mark.asyncio
    async def test_read_stdout_no_process(self) -> None:
        ch = _make_channel()
        ch._process = None
        await ch._read_stdout()

    @pytest.mark.asyncio
    async def test_read_stdout_cancelled(self) -> None:
        ch = _make_channel()
        ch._process.stdout = MagicMock()
        ch._process.stdout.readline = AsyncMock(side_effect=asyncio.CancelledError)
        await ch._read_stdout()

    @pytest.mark.asyncio
    async def test_read_stdout_sets_error_on_unexpected_end(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._process.stdout = MagicMock()
        ch._process.stdout.readline = AsyncMock(return_value=b"")

        await ch._read_stdout()
        assert ch._status == ChannelStatus.ERROR
        assert not ch._connected.is_set()
