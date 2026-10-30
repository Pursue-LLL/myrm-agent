"""The receiver decrypts with the credentials the connection holds when a packet arrives, not with the ones it had at start.

discord.py replaces the transport key and mode at every session description (a server migration or any reconnect that
cannot resume), creates the DAVE session when the call upgrades to end-to-end encryption, and assigns the bot's SSRC at
every handshake. A receiver that read them once at ``start()`` keeps getting packets, since reconnecting leaves its
socket listener registered, and fails every one of them. Packets here are encrypted for real, so a stale key shows up as
a packet that does not open instead of as a mock that was never asked.
"""

from __future__ import annotations

import logging
import struct
from functools import partial
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("discord")
pytest.importorskip("davey")
import nacl.secret
from discord.utils import MISSING

from app.channels.providers.discord.voice.receiver import _UNDECRYPTABLE_STREAK_WARNING, VoiceReceiver
from tests.channels.providers.discord.voice.receiver_testkit import make_mock_vc

_RECEIVER_LOGGER = "app.channels.providers.discord.voice.receiver"
_KEY_A = bytes(range(32))
_KEY_B = bytes(range(32, 64))
_SECRETBOX_MODE = "xsalsa20_poly1305_lite"
_AEAD_MODE = "aead_xchacha20_poly1305_rtpsize"
_BOT_SSRC = 999
_OPUS_FRAME = b"\x01" * 120


_voice_client = partial(make_mock_vc, mode=_SECRETBOX_MODE, key=_KEY_A)


def _started(voice_client: MagicMock) -> VoiceReceiver:
    receiver = VoiceReceiver(voice_client)
    receiver.start()
    return receiver


def _packet(key: bytes, mode: str, *, ssrc: int) -> bytes:
    """One RTP packet whose Opus payload is encrypted for ``mode`` the way discord.py's voice server sends it."""
    header = struct.pack(">BBHII", 0x80, 0x78, 1, 100, ssrc)
    counter = b"\x01\x00\x00\x00"
    nonce = counter + b"\x00" * 20
    if "aead" in mode:
        sealed = nacl.secret.Aead(key).encrypt(_OPUS_FRAME, header, nonce).ciphertext
    else:
        sealed = nacl.secret.SecretBox(key).encrypt(_OPUS_FRAME, nonce).ciphertext
    return header + sealed + counter


def _feed(receiver: VoiceReceiver, packet: bytes) -> None:
    decoder = MagicMock()
    decoder.decode.return_value = b"\x00" * 3840
    with patch("discord.opus.Decoder", return_value=decoder):
        receiver._on_packet(packet)


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING and r.name == _RECEIVER_LOGGER]


def test_a_re_keyed_connection_is_decrypted_with_its_new_key() -> None:
    voice_client = _voice_client(key=_KEY_A)
    receiver = _started(voice_client)
    _feed(receiver, _packet(_KEY_A, _SECRETBOX_MODE, ssrc=200))
    assert 200 in receiver._buffers

    voice_client._connection.secret_key = list(_KEY_B)
    _feed(receiver, _packet(_KEY_B, _SECRETBOX_MODE, ssrc=201))
    _feed(receiver, _packet(_KEY_A, _SECRETBOX_MODE, ssrc=202))

    assert 201 in receiver._buffers
    assert 202 not in receiver._buffers


def test_a_renegotiated_mode_is_followed() -> None:
    voice_client = _voice_client(mode=_SECRETBOX_MODE)
    receiver = _started(voice_client)

    voice_client._connection.mode = _AEAD_MODE
    _feed(receiver, _packet(_KEY_A, _AEAD_MODE, ssrc=200))

    assert 200 in receiver._buffers


def test_the_bots_own_ssrc_is_the_one_of_the_current_handshake() -> None:
    voice_client = _voice_client()
    receiver = _started(voice_client)

    voice_client._connection.ssrc = 555
    _feed(receiver, _packet(_KEY_A, _SECRETBOX_MODE, ssrc=555))
    _feed(receiver, _packet(_KEY_A, _SECRETBOX_MODE, ssrc=_BOT_SSRC))

    assert 555 not in receiver._buffers
    assert _BOT_SSRC in receiver._buffers


def test_a_dave_session_created_after_start_is_applied() -> None:
    voice_client = _voice_client()
    receiver = _started(voice_client)
    receiver._map_ssrc(200, 42)

    dave_session = MagicMock()
    dave_session.decrypt.return_value = _OPUS_FRAME
    voice_client._connection.dave_session = dave_session
    _feed(receiver, _packet(_KEY_A, _SECRETBOX_MODE, ssrc=200))

    dave_session.decrypt.assert_called_once()
    assert dave_session.decrypt.call_args.args[0] == 42
    assert 200 in receiver._buffers


def test_a_connection_with_no_session_key_yet_is_listened_to_without_error() -> None:
    voice_client = _voice_client()
    voice_client._connection.secret_key = MISSING
    receiver = _started(voice_client)
    assert receiver.running

    _feed(receiver, _packet(_KEY_A, _SECRETBOX_MODE, ssrc=200))
    assert 200 not in receiver._buffers

    voice_client._connection.secret_key = list(_KEY_A)
    _feed(receiver, _packet(_KEY_A, _SECRETBOX_MODE, ssrc=200))
    assert 200 in receiver._buffers


def test_packets_that_arrive_before_the_session_key_are_not_counted_as_failures(
    caplog: pytest.LogCaptureFixture,
) -> None:
    voice_client = _voice_client()
    voice_client._connection.secret_key = MISSING
    receiver = _started(voice_client)

    with caplog.at_level(logging.WARNING, logger=_RECEIVER_LOGGER):
        for _ in range(_UNDECRYPTABLE_STREAK_WARNING * 2):
            _feed(receiver, _packet(_KEY_A, _SECRETBOX_MODE, ssrc=200))

    assert _warnings(caplog) == []


def test_a_run_of_undecryptable_packets_is_reported_once(caplog: pytest.LogCaptureFixture) -> None:
    receiver = _started(_voice_client(key=_KEY_A))
    stale = _packet(_KEY_B, _SECRETBOX_MODE, ssrc=200)

    with caplog.at_level(logging.WARNING, logger=_RECEIVER_LOGGER):
        for _ in range(_UNDECRYPTABLE_STREAK_WARNING - 1):
            _feed(receiver, stale)
        assert _warnings(caplog) == []
        _feed(receiver, stale)
        for _ in range(_UNDECRYPTABLE_STREAK_WARNING):
            _feed(receiver, stale)

    (warning,) = _warnings(caplog)
    assert "decrypt" in warning
    assert _SECRETBOX_MODE in warning


def test_a_run_is_reported_within_seconds_of_audio() -> None:
    """One speaker sends about 50 packets a second; the run has to surface long before the voice timeout."""
    assert _UNDECRYPTABLE_STREAK_WARNING <= 5 * 50


def test_a_packet_that_opens_ends_the_run(caplog: pytest.LogCaptureFixture) -> None:
    receiver = _started(_voice_client(key=_KEY_A))
    stale = _packet(_KEY_B, _SECRETBOX_MODE, ssrc=200)
    fresh = _packet(_KEY_A, _SECRETBOX_MODE, ssrc=200)

    with caplog.at_level(logging.WARNING, logger=_RECEIVER_LOGGER):
        for _ in range(_UNDECRYPTABLE_STREAK_WARNING - 1):
            _feed(receiver, stale)
        _feed(receiver, fresh)
        for _ in range(_UNDECRYPTABLE_STREAK_WARNING - 1):
            _feed(receiver, stale)

    assert _warnings(caplog) == []


def test_dave_layer_failures_count_toward_the_run(caplog: pytest.LogCaptureFixture) -> None:
    dave_session = MagicMock()
    dave_session.decrypt.side_effect = RuntimeError("epoch mismatch")
    receiver = _started(_voice_client(dave_session=dave_session))
    receiver._map_ssrc(200, 42)

    with caplog.at_level(logging.WARNING, logger=_RECEIVER_LOGGER):
        for _ in range(_UNDECRYPTABLE_STREAK_WARNING):
            _feed(receiver, _packet(_KEY_A, _SECRETBOX_MODE, ssrc=200))

    (warning,) = _warnings(caplog)
    assert "DAVE" in warning
