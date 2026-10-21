"""Unit tests for VoiceReceiver."""

from __future__ import annotations

import struct
import time
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("discord")

from app.channels.providers.discord.voice.receiver import (
    _BYTES_PER_SECOND,
    _MIN_SPEECH_DURATION,
    _SILENCE_THRESHOLD,
    VoiceReceiver,
)


def _make_mock_vc(mode: str = "", dave_session: object | None = None) -> MagicMock:
    vc = MagicMock()
    conn = MagicMock()
    conn.secret_key = [0] * 32
    conn.ssrc = 999
    conn.hook = None
    conn.mode = mode
    conn.dave_session = dave_session
    vc._connection = conn
    vc.channel = MagicMock()
    vc.channel.members = []
    vc.user = MagicMock()
    vc.user.id = 1
    vc.mode = mode
    return vc


class TestVoiceReceiverInit:
    def test_init_defaults(self) -> None:
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        assert not r.running
        assert r._allowed_user_ids == set()
        assert not r._paused

    def test_init_with_allowed_users(self) -> None:
        vc = _make_mock_vc()
        r = VoiceReceiver(vc, allowed_user_ids={"100", "200"})
        assert r._allowed_user_ids == {"100", "200"}


class TestVoiceReceiverLifecycle:
    def test_start_sets_running(self) -> None:
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        r.start()
        assert r.running
        assert r._bot_ssrc == 999
        vc._connection.add_socket_listener.assert_called_once()

    def test_start_captures_mode(self) -> None:
        vc = _make_mock_vc(mode="aead_xchacha20_poly1305_rtpsize")
        r = VoiceReceiver(vc)
        r.start()
        assert r._mode == "aead_xchacha20_poly1305_rtpsize"

    def test_start_captures_dave_session(self) -> None:
        dave = MagicMock()
        vc = _make_mock_vc(dave_session=dave)
        r = VoiceReceiver(vc)
        r.start()
        assert r._dave_session is dave

    def test_start_no_dave(self) -> None:
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        r.start()
        assert r._dave_session is None

    def test_stop_clears_state(self) -> None:
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        r.start()
        r._buffers[123] = bytearray(b"\x00" * 100)
        r._ssrc_to_user[123] = 42
        r._decoders[123] = MagicMock()
        r.stop()
        assert not r.running
        assert len(r._buffers) == 0
        assert len(r._ssrc_to_user) == 0
        assert len(r._decoders) == 0

    def test_stop_handles_remove_listener_error(self) -> None:
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        r.start()
        vc._connection.remove_socket_listener.side_effect = RuntimeError("fail")
        r.stop()
        assert not r.running

    def test_pause_resume(self) -> None:
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        assert not r._paused
        r.pause()
        assert r._paused
        r.resume()
        assert not r._paused


class TestSpeakingHook:
    def test_speaking_hook_maps_ssrc(self) -> None:
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        r.start()

        conn = vc._connection
        hook = conn.hook
        assert hook is not None

        import asyncio

        msg = {"op": 5, "d": {"ssrc": 100, "user_id": 42}}
        asyncio.run(hook(MagicMock(), msg))
        assert r._ssrc_to_user[100] == 42

    def test_speaking_hook_ignores_non_op5(self) -> None:
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        r.start()

        hook = vc._connection.hook
        import asyncio

        msg = {"op": 3, "d": {"ssrc": 100, "user_id": 42}}
        asyncio.run(hook(MagicMock(), msg))
        assert 100 not in r._ssrc_to_user

    def test_speaking_hook_ws_set_error(self) -> None:
        vc = _make_mock_vc()
        ws = MagicMock()
        ws._hook = None

        class FailWs:
            @property
            def _hook(self) -> None:
                return None

            @_hook.setter
            def _hook(self, val: object) -> None:
                raise AttributeError("nope")

        vc._connection.ws = FailWs()
        r = VoiceReceiver(vc)
        r.start()
        assert r.running

    def test_map_ssrc_direct(self) -> None:
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        r._map_ssrc(200, 55)
        assert r._ssrc_to_user[200] == 55


class TestVoiceReceiverPacket:
    def test_ignores_short_packets(self) -> None:
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        r._running = True
        r._on_packet(b"\x00" * 10)
        assert len(r._buffers) == 0

    def test_ignores_non_rtp(self) -> None:
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        r._running = True
        r._on_packet(b"\x00" * 20)
        assert len(r._buffers) == 0

    def test_ignores_when_paused(self) -> None:
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        r._running = True
        r._paused = True
        r._on_packet(b"\x80\x78" + b"\x00" * 20)
        assert len(r._buffers) == 0

    def test_ignores_when_not_running(self) -> None:
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        r._running = False
        r._on_packet(b"\x80\x78" + b"\x00" * 20)
        assert len(r._buffers) == 0

    def test_ignores_bot_ssrc(self) -> None:
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        r._running = True
        r._bot_ssrc = 999
        header = struct.pack(">BBHII", 0x80, 0x78, 1, 100, 999)
        r._on_packet(header + b"\x00" * 20)
        assert len(r._buffers) == 0

    def test_secretbox_decrypt_path(self) -> None:
        """Test _on_packet with xsalsa20_poly1305_lite mode (SecretBox)."""
        vc = _make_mock_vc(mode="xsalsa20_poly1305_lite")
        r = VoiceReceiver(vc)
        r._running = True
        r._bot_ssrc = 999
        r._secret_key = b"\x00" * 32
        r._mode = "xsalsa20_poly1305_lite"

        ssrc = 100
        header = struct.pack(">BBHII", 0x80, 0x78, 1, 100, ssrc)
        fake_payload = b"\xab" * 20
        nonce_bytes = b"\x01\x00\x00\x00"
        packet = header + fake_payload + nonce_bytes

        mock_box = MagicMock()
        mock_box.decrypt.return_value = b"\x00" * 960

        mock_decoder = MagicMock()
        mock_decoder.decode.return_value = b"\x00" * 3840

        with (
            patch("nacl.secret.SecretBox", return_value=mock_box),
            patch("discord.opus.Decoder", return_value=mock_decoder),
        ):
            r._on_packet(packet)

        assert ssrc in r._buffers

    def test_aead_decrypt_path(self) -> None:
        """Test _on_packet with aead_xchacha20_poly1305_rtpsize mode."""
        vc = _make_mock_vc(mode="aead_xchacha20_poly1305_rtpsize")
        r = VoiceReceiver(vc)
        r._running = True
        r._bot_ssrc = 999
        r._secret_key = b"\x00" * 32
        r._mode = "aead_xchacha20_poly1305_rtpsize"

        ssrc = 200
        first_byte = 0x90
        header = struct.pack(">BBHII", first_byte, 0x78, 1, 100, ssrc)
        ext_header = struct.pack(">HH", 0xBEDE, 0)
        full_header = header + ext_header
        fake_payload = b"\xcd" * 20
        nonce_bytes = b"\x02\x00\x00\x00"
        packet = full_header + fake_payload + nonce_bytes

        mock_aead = MagicMock()
        mock_aead.decrypt.return_value = b"\x00" * 960

        mock_decoder = MagicMock()
        mock_decoder.decode.return_value = b"\x00" * 3840

        with (
            patch("nacl.secret.Aead", return_value=mock_aead),
            patch("discord.opus.Decoder", return_value=mock_decoder),
        ):
            r._on_packet(packet)

        assert ssrc in r._buffers

    def test_decrypt_failure_logs_first_5(self) -> None:
        """Decrypt failures should be silently counted."""
        vc = _make_mock_vc(mode="xsalsa20_poly1305_lite")
        r = VoiceReceiver(vc)
        r._running = True
        r._bot_ssrc = 999
        r._mode = "xsalsa20_poly1305_lite"
        r._secret_key = b"\x00" * 32

        ssrc = 100
        header = struct.pack(">BBHII", 0x80, 0x78, 1, 100, ssrc)
        packet = header + b"\xab" * 20 + b"\x01\x00\x00\x00"

        with patch("nacl.secret.SecretBox") as mock_sb:
            mock_sb.return_value.decrypt.side_effect = Exception("bad")
            for _ in range(7):
                r._on_packet(packet)

        assert r._packet_count == 7
        assert ssrc not in r._buffers

    def test_short_payload_after_header(self) -> None:
        """Packet with valid RTP header but payload too short."""
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        r._running = True
        r._bot_ssrc = 999
        ssrc = 100
        header = struct.pack(">BBHII", 0x80, 0x78, 1, 100, ssrc)
        packet = header + b"\x01\x02"
        r._on_packet(packet)
        assert ssrc not in r._buffers

    def test_opus_decode_error_handled(self) -> None:
        """Opus decode failure should not crash."""
        vc = _make_mock_vc(mode="xsalsa20_poly1305_lite")
        r = VoiceReceiver(vc)
        r._running = True
        r._bot_ssrc = 999
        r._mode = "xsalsa20_poly1305_lite"
        r._secret_key = b"\x00" * 32

        ssrc = 100
        header = struct.pack(">BBHII", 0x80, 0x78, 1, 100, ssrc)
        packet = header + b"\xab" * 20 + b"\x01\x00\x00\x00"

        mock_box = MagicMock()
        mock_box.decrypt.return_value = b"\x00" * 960

        mock_decoder = MagicMock()
        mock_decoder.decode.side_effect = Exception("opus fail")

        with (
            patch("nacl.secret.SecretBox", return_value=mock_box),
            patch("discord.opus.Decoder", return_value=mock_decoder),
        ):
            r._on_packet(packet)

        assert ssrc not in r._buffers

    def test_ext_data_stripped(self) -> None:
        """Extension data should be stripped from decrypted payload."""
        vc = _make_mock_vc(mode="aead_xchacha20_poly1305_rtpsize")
        r = VoiceReceiver(vc)
        r._running = True
        r._bot_ssrc = 999
        r._mode = "aead_xchacha20_poly1305_rtpsize"
        r._secret_key = b"\x00" * 32

        ssrc = 300
        first_byte = 0x90
        header = struct.pack(">BBHII", first_byte, 0x78, 1, 100, ssrc)
        ext_words = 2
        ext_header = struct.pack(">HH", 0xBEDE, ext_words)
        full_header = header + ext_header
        fake_payload = b"\xcd" * 20
        nonce_bytes = b"\x03\x00\x00\x00"
        packet = full_header + fake_payload + nonce_bytes

        ext_data = b"\xee" * (ext_words * 4)
        opus_data = b"\x00" * 960
        mock_aead = MagicMock()
        mock_aead.decrypt.return_value = ext_data + opus_data

        mock_decoder = MagicMock()
        mock_decoder.decode.return_value = b"\x00" * 3840

        with (
            patch("nacl.secret.Aead", return_value=mock_aead),
            patch("discord.opus.Decoder", return_value=mock_decoder),
        ):
            r._on_packet(packet)

        mock_decoder.decode.assert_called_once_with(opus_data)

    def test_padding_stripped(self) -> None:
        """Padding bytes should be removed from decrypted payload."""
        vc = _make_mock_vc(mode="xsalsa20_poly1305_lite")
        r = VoiceReceiver(vc)
        r._running = True
        r._bot_ssrc = 999
        r._mode = "xsalsa20_poly1305_lite"
        r._secret_key = b"\x00" * 32

        ssrc = 400
        first_byte = 0xA0
        header = struct.pack(">BBHII", first_byte, 0x78, 1, 100, ssrc)
        packet = header + b"\xab" * 20 + b"\x01\x00\x00\x00"

        opus_data = b"\x00" * 960
        pad_len = 3
        padded = opus_data + b"\x00" * (pad_len - 1) + bytes([pad_len])
        mock_box = MagicMock()
        mock_box.decrypt.return_value = padded

        mock_decoder = MagicMock()
        mock_decoder.decode.return_value = b"\x00" * 3840

        with (
            patch("nacl.secret.SecretBox", return_value=mock_box),
            patch("discord.opus.Decoder", return_value=mock_decoder),
        ):
            r._on_packet(packet)

        mock_decoder.decode.assert_called_once_with(opus_data)

    def test_padding_invalid_skips(self) -> None:
        """Invalid padding (pad_len > data length) should skip packet."""
        vc = _make_mock_vc(mode="xsalsa20_poly1305_lite")
        r = VoiceReceiver(vc)
        r._running = True
        r._bot_ssrc = 999
        r._mode = "xsalsa20_poly1305_lite"
        r._secret_key = b"\x00" * 32

        ssrc = 500
        first_byte = 0xA0
        header = struct.pack(">BBHII", first_byte, 0x78, 1, 100, ssrc)
        packet = header + b"\xab" * 20 + b"\x01\x00\x00\x00"

        mock_box = MagicMock()
        mock_box.decrypt.return_value = bytes([255])

        with patch("nacl.secret.SecretBox", return_value=mock_box):
            r._on_packet(packet)

        assert ssrc not in r._buffers

    def test_padding_zero_skips(self) -> None:
        """Padding byte of 0 should skip packet."""
        vc = _make_mock_vc(mode="xsalsa20_poly1305_lite")
        r = VoiceReceiver(vc)
        r._running = True
        r._bot_ssrc = 999
        r._mode = "xsalsa20_poly1305_lite"
        r._secret_key = b"\x00" * 32

        ssrc = 600
        first_byte = 0xA0
        header = struct.pack(">BBHII", first_byte, 0x78, 1, 100, ssrc)
        packet = header + b"\xab" * 20 + b"\x01\x00\x00\x00"

        mock_box = MagicMock()
        mock_box.decrypt.return_value = b"\x00" * 10 + bytes([0])

        with patch("nacl.secret.SecretBox", return_value=mock_box):
            r._on_packet(packet)

        assert ssrc not in r._buffers

    def test_empty_decrypted_with_padding_skips(self) -> None:
        """Empty decrypted data with padding flag should skip."""
        vc = _make_mock_vc(mode="xsalsa20_poly1305_lite")
        r = VoiceReceiver(vc)
        r._running = True
        r._bot_ssrc = 999
        r._mode = "xsalsa20_poly1305_lite"
        r._secret_key = b"\x00" * 32

        ssrc = 700
        first_byte = 0xA0
        header = struct.pack(">BBHII", first_byte, 0x78, 1, 100, ssrc)
        packet = header + b"\xab" * 20 + b"\x01\x00\x00\x00"

        mock_box = MagicMock()
        mock_box.decrypt.return_value = b""

        with patch("nacl.secret.SecretBox", return_value=mock_box):
            r._on_packet(packet)

        assert ssrc not in r._buffers

    def test_padding_strips_all_data(self) -> None:
        """Padding that strips all data should skip."""
        vc = _make_mock_vc(mode="xsalsa20_poly1305_lite")
        r = VoiceReceiver(vc)
        r._running = True
        r._bot_ssrc = 999
        r._mode = "xsalsa20_poly1305_lite"
        r._secret_key = b"\x00" * 32

        ssrc = 800
        first_byte = 0xA0
        header = struct.pack(">BBHII", first_byte, 0x78, 1, 100, ssrc)
        packet = header + b"\xab" * 20 + b"\x01\x00\x00\x00"

        mock_box = MagicMock()
        mock_box.decrypt.return_value = bytes([2, 2])

        with patch("nacl.secret.SecretBox", return_value=mock_box):
            r._on_packet(packet)

        assert ssrc not in r._buffers


class TestDAVEDecrypt:
    def test_dave_decrypt_success(self) -> None:
        vc = _make_mock_vc(mode="xsalsa20_poly1305_lite")
        r = VoiceReceiver(vc)
        r._running = True
        r._bot_ssrc = 999
        r._mode = "xsalsa20_poly1305_lite"
        r._secret_key = b"\x00" * 32

        ssrc = 100
        r._ssrc_to_user[ssrc] = 42
        r._dave_session = MagicMock()
        r._dave_session.decrypt.return_value = b"\x00" * 960

        header = struct.pack(">BBHII", 0x80, 0x78, 1, 100, ssrc)
        packet = header + b"\xab" * 20 + b"\x01\x00\x00\x00"

        mock_box = MagicMock()
        mock_box.decrypt.return_value = b"\x00" * 960

        mock_decoder = MagicMock()
        mock_decoder.decode.return_value = b"\x00" * 3840

        with (
            patch("nacl.secret.SecretBox", return_value=mock_box),
            patch("discord.opus.Decoder", return_value=mock_decoder),
        ):
            r._on_packet(packet)

        assert ssrc in r._buffers
        r._dave_session.decrypt.assert_called_once()

    def test_dave_decrypt_no_user_passthrough(self) -> None:
        """DAVE decrypt with unknown SSRC should pass through."""
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        dave = MagicMock()
        r._dave_session = dave

        result = r._dave_decrypt(999, b"\x00" * 100)
        assert result == b"\x00" * 100
        dave.decrypt.assert_not_called()

    def test_dave_decrypt_unencrypted_passthrough(self) -> None:
        """DAVE 'Unencrypted' exception should pass through payload."""
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        r._ssrc_to_user[100] = 42
        dave = MagicMock()
        dave.decrypt.side_effect = Exception("Unencrypted frame")
        r._dave_session = dave

        result = r._dave_decrypt(100, b"\xab" * 50)
        assert result == b"\xab" * 50

    def test_dave_decrypt_real_error_returns_none(self) -> None:
        """DAVE real decrypt error should return None."""
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        r._ssrc_to_user[100] = 42
        dave = MagicMock()
        dave.decrypt.side_effect = Exception("key expired")
        r._dave_session = dave

        result = r._dave_decrypt(100, b"\xab" * 50)
        assert result is None


class TestDecryptPayload:
    def test_aead_mode(self) -> None:
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        r._secret_key = b"\x00" * 32
        r._mode = "aead_xchacha20_poly1305_rtpsize"

        with patch("nacl.secret.Aead") as MockAead:
            mock_aead = MagicMock()
            mock_aead.decrypt.return_value = b"decrypted"
            MockAead.return_value = mock_aead

            result = r._decrypt_payload(b"encrypted", b"header", b"\x00" * 24)
            assert result == b"decrypted"
            MockAead.assert_called_once_with(b"\x00" * 32)

    def test_xchacha_mode(self) -> None:
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        r._secret_key = b"\x00" * 32
        r._mode = "xchacha_something"

        with patch("nacl.secret.Aead") as MockAead:
            mock_aead = MagicMock()
            mock_aead.decrypt.return_value = b"decrypted"
            MockAead.return_value = mock_aead

            result = r._decrypt_payload(b"encrypted", b"header", b"\x00" * 24)
            assert result == b"decrypted"

    def test_secretbox_mode(self) -> None:
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        r._secret_key = b"\x00" * 32
        r._mode = "xsalsa20_poly1305_lite"

        with patch("nacl.secret.SecretBox") as MockSB:
            mock_sb = MagicMock()
            mock_sb.decrypt.return_value = b"decrypted"
            MockSB.return_value = mock_sb

            result = r._decrypt_payload(b"encrypted", b"header", b"\x00" * 24)
            assert result == b"decrypted"
            MockSB.assert_called_once_with(b"\x00" * 32)


class TestSilenceDetection:
    def test_empty_buffers(self) -> None:
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        r._running = True
        assert r.check_silence() == []

    def test_detects_completed_utterance(self) -> None:
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        r._running = True

        ssrc = 100
        user_id = 42
        r._ssrc_to_user[ssrc] = user_id
        min_bytes = int(_MIN_SPEECH_DURATION * _BYTES_PER_SECOND) + 100
        r._buffers[ssrc] = bytearray(b"\x00" * min_bytes)
        r._last_packet_time[ssrc] = time.monotonic() - _SILENCE_THRESHOLD - 0.1

        completed = r.check_silence()
        assert len(completed) == 1
        uid, data = completed[0]
        assert uid == user_id
        assert len(data) == min_bytes

    def test_ignores_short_buffer(self) -> None:
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        r._running = True

        ssrc = 100
        r._ssrc_to_user[ssrc] = 42
        r._buffers[ssrc] = bytearray(b"\x00" * 100)
        r._last_packet_time[ssrc] = time.monotonic() - _SILENCE_THRESHOLD - 0.1

        completed = r.check_silence()
        assert len(completed) == 0

    def test_discards_stale_unmapped_buffer(self) -> None:
        vc = _make_mock_vc()
        r = VoiceReceiver(vc)
        r._running = True

        ssrc = 100
        r._buffers[ssrc] = bytearray(b"\x00" * 100)
        r._last_packet_time[ssrc] = time.monotonic() - _SILENCE_THRESHOLD * 2 - 1

        r.check_silence()
        assert ssrc not in r._buffers

    def test_infer_user_during_silence_check(self) -> None:
        """check_silence should call _infer_user_for_ssrc for unmapped SSRC."""
        vc = _make_mock_vc()
        member = MagicMock()
        member.id = 77
        member.bot = False
        vc.channel.members = [vc.user, member]

        r = VoiceReceiver(vc)
        r._running = True

        ssrc = 100
        min_bytes = int(_MIN_SPEECH_DURATION * _BYTES_PER_SECOND) + 100
        r._buffers[ssrc] = bytearray(b"\x00" * min_bytes)
        r._last_packet_time[ssrc] = time.monotonic() - _SILENCE_THRESHOLD - 0.1

        completed = r.check_silence()
        assert len(completed) == 1
        assert completed[0][0] == 77

    def test_no_user_no_output(self) -> None:
        """No mapped user and inference fails -> no output."""
        vc = _make_mock_vc()
        m1 = MagicMock()
        m1.id = 42
        m1.bot = False
        m2 = MagicMock()
        m2.id = 43
        m2.bot = False
        vc.channel.members = [vc.user, m1, m2]

        r = VoiceReceiver(vc)
        r._running = True

        ssrc = 100
        min_bytes = int(_MIN_SPEECH_DURATION * _BYTES_PER_SECOND) + 100
        r._buffers[ssrc] = bytearray(b"\x00" * min_bytes)
        r._last_packet_time[ssrc] = time.monotonic() - _SILENCE_THRESHOLD - 0.1

        completed = r.check_silence()
        assert len(completed) == 0
        assert ssrc in r._buffers


class TestSSRCInference:
    def test_infer_sole_user(self) -> None:
        vc = _make_mock_vc()
        member = MagicMock()
        member.id = 42
        member.bot = False
        vc.channel.members = [vc.user, member]

        r = VoiceReceiver(vc)
        r._running = True
        result = r._infer_user_for_ssrc(100)
        assert result == 42
        assert r._ssrc_to_user[100] == 42

    def test_no_candidates(self) -> None:
        vc = _make_mock_vc()
        vc.channel.members = [vc.user]

        r = VoiceReceiver(vc)
        r._running = True
        result = r._infer_user_for_ssrc(100)
        assert result == 0

    def test_multiple_candidates_no_infer(self) -> None:
        vc = _make_mock_vc()
        m1 = MagicMock()
        m1.id = 42
        m1.bot = False
        m2 = MagicMock()
        m2.id = 43
        m2.bot = False
        vc.channel.members = [vc.user, m1, m2]

        r = VoiceReceiver(vc)
        r._running = True
        result = r._infer_user_for_ssrc(100)
        assert result == 0

    def test_infer_no_channel(self) -> None:
        vc = _make_mock_vc()
        vc.channel = None

        r = VoiceReceiver(vc)
        r._running = True
        result = r._infer_user_for_ssrc(100)
        assert result == 0

    def test_infer_with_allowed_filter(self) -> None:
        vc = _make_mock_vc()
        m1 = MagicMock()
        m1.id = 42
        m1.bot = False
        m2 = MagicMock()
        m2.id = 43
        m2.bot = False
        vc.channel.members = [vc.user, m1, m2]

        r = VoiceReceiver(vc, allowed_user_ids={"42"})
        r._running = True
        result = r._infer_user_for_ssrc(100)
        assert result == 42

    def test_infer_exception_returns_zero(self) -> None:
        vc = _make_mock_vc()
        type(vc).channel = property(lambda self: (_ for _ in ()).throw(RuntimeError("nope")))

        r = VoiceReceiver(vc)
        r._running = True
        result = r._infer_user_for_ssrc(100)
        assert result == 0


class TestPcmToWavBytes:
    def test_pcm_to_wav_bytes_success(self) -> None:
        import io
        import wave

        pcm = b"\x00" * 3200
        result = VoiceReceiver.pcm_to_wav_bytes(pcm)

        assert isinstance(result, bytes)
        assert len(result) > len(pcm)

        with io.BytesIO(result) as wav_io:
            with wave.open(wav_io, "rb") as wav_file:
                assert wav_file.getnchannels() == 2
                assert wav_file.getsampwidth() == 2
                assert wav_file.getframerate() == 48000
                assert wav_file.readframes(wav_file.getnframes()) == pcm

    def test_pcm_to_wav_bytes_custom_params(self) -> None:
        import io
        import wave

        pcm = b"\x00" * 1600
        result = VoiceReceiver.pcm_to_wav_bytes(pcm, src_rate=16000, src_channels=1)

        with io.BytesIO(result) as wav_io:
            with wave.open(wav_io, "rb") as wav_file:
                assert wav_file.getnchannels() == 1
                assert wav_file.getframerate() == 16000
