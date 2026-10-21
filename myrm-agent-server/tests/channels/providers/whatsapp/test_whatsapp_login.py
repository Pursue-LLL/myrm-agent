"""WhatsAppLoginMixin — QR pairing stream built from real bridge events and the real AsyncLoginProtocol types."""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest

from app.channels.protocols.async_login import LoginEvent, LoginMethod, LoginStatus
from app.channels.providers.whatsapp.channel import WhatsAppChannel
from app.channels.types import ChannelStatus

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_OPEN = json.dumps({"type": "connection", "status": "open", "selfJid": "123@s.whatsapp.net"})


def _qr(text: str) -> str:
    return json.dumps({"type": "qr", "data": text})


def _channel(tmp_path: Path) -> WhatsAppChannel:
    return WhatsAppChannel(auth_dir=str(tmp_path))


async def _next(stream: AsyncGenerator[LoginEvent, None]) -> LoginEvent:
    return await asyncio.wait_for(anext(stream), timeout=5.0)


def _assert_png(event: LoginEvent) -> bytes:
    assert event.state.qr_code_base64 is not None
    png = base64.b64decode(event.state.qr_code_base64)
    assert png.startswith(_PNG_MAGIC)
    return png


def _assert_unsubscribed(ch: WhatsAppChannel) -> None:
    assert not ch._listeners.get("qr_code")
    assert not ch._listeners.get("connection_change")


class TestWhatsAppLoginStream:
    async def test_rejects_methods_other_than_qr(self, tmp_path: Path) -> None:
        ch = _channel(tmp_path)

        with pytest.raises(ValueError, match="QR_CODE"):
            await _next(ch.start_login(LoginMethod.OAUTH2))

    async def test_connected_channel_reports_success_and_unsubscribes(self, tmp_path: Path) -> None:
        ch = _channel(tmp_path)
        ch._connected.set()
        stream = ch.start_login(method=LoginMethod.QR_CODE, timeout=300.0, callback_url=None)

        event = await _next(stream)

        assert event.state.status is LoginStatus.SUCCESS
        assert event.state.method is LoginMethod.QR_CODE
        assert event.state.progress_percent == 100
        assert event.channel_name == "whatsapp"
        with pytest.raises(StopAsyncIteration):
            await _next(stream)
        _assert_unsubscribed(ch)

    async def test_streams_every_rotated_qr_then_success(self, tmp_path: Path) -> None:
        ch = _channel(tmp_path)
        stream = ch.start_login(LoginMethod.QR_CODE)

        first = await _next(stream)
        assert first.state.status is LoginStatus.GENERATING
        assert first.state.qr_code_base64 is None

        await ch._handle_bridge_event(_qr("2@first-pairing-payload"))
        qr_one = await _next(stream)
        assert qr_one.state.status is LoginStatus.WAITING_USER_ACTION
        png_one = _assert_png(qr_one)

        await ch._handle_bridge_event(_qr("2@rotated-pairing-payload"))
        qr_two = await _next(stream)
        assert qr_two.state.status is LoginStatus.WAITING_USER_ACTION
        assert _assert_png(qr_two) != png_one

        await ch._handle_bridge_event(_OPEN)
        done = await _next(stream)
        assert done.state.status is LoginStatus.SUCCESS
        with pytest.raises(StopAsyncIteration):
            await _next(stream)
        _assert_unsubscribed(ch)

    async def test_qr_already_known_is_the_first_event(self, tmp_path: Path) -> None:
        ch = _channel(tmp_path)
        ch._qr_code = "2@already-generated-payload"
        stream = ch.start_login(LoginMethod.QR_CODE)

        event = await _next(stream)

        assert event.state.status is LoginStatus.WAITING_USER_ACTION
        _assert_png(event)
        await stream.aclose()

    async def test_event_without_qr_text_is_ignored(self, tmp_path: Path) -> None:
        ch = _channel(tmp_path)
        stream = ch.start_login(LoginMethod.QR_CODE)
        await _next(stream)

        ch.emit("qr_code", {"qr": None})
        await ch._handle_bridge_event(_qr("2@valid-pairing-payload"))
        event = await _next(stream)

        assert event.state.status is LoginStatus.WAITING_USER_ACTION
        _assert_png(event)
        await stream.aclose()

    async def test_times_out_when_nothing_happens(self, tmp_path: Path) -> None:
        ch = _channel(tmp_path)
        stream = ch.start_login(LoginMethod.QR_CODE, timeout=0.05)

        assert (await _next(stream)).state.status is LoginStatus.GENERATING
        timeout_event = await _next(stream)

        assert timeout_event.state.status is LoginStatus.TIMEOUT
        assert timeout_event.state.error_message
        with pytest.raises(StopAsyncIteration):
            await _next(stream)
        _assert_unsubscribed(ch)

    async def test_failed_when_the_connection_drops_while_channel_is_in_error(self, tmp_path: Path) -> None:
        ch = _channel(tmp_path)
        stream = ch.start_login(LoginMethod.QR_CODE)
        await _next(stream)

        ch._connected.set()
        ch._status = ChannelStatus.ERROR
        ch._set_connected(False)
        event = await _next(stream)

        assert event.state.status is LoginStatus.FAILED
        assert event.state.error_message
        with pytest.raises(StopAsyncIteration):
            await _next(stream)
        _assert_unsubscribed(ch)

    async def test_closing_the_stream_early_unsubscribes(self, tmp_path: Path) -> None:
        ch = _channel(tmp_path)
        stream = ch.start_login(LoginMethod.QR_CODE)
        await _next(stream)
        assert ch._listeners["qr_code"]

        await stream.aclose()

        _assert_unsubscribed(ch)
