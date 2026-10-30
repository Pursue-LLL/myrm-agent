"""VoiceReceiver packet path: RTP framing, transport decryption, extension and padding stripping, DAVE, Opus decode."""

from __future__ import annotations

import struct
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("discord")

from app.channels.providers.discord.voice.receiver import VoiceReceiver, _Credentials
from tests.channels.providers.discord.voice.receiver_testkit import make_mock_vc


class TestVoiceReceiverPacket:
    def test_ignores_short_packets(self) -> None:
        vc = make_mock_vc()
        r = VoiceReceiver(vc)
        r._running = True
        r._on_packet(b"\x00" * 10)
        assert len(r._buffers) == 0

    def test_ignores_non_rtp(self) -> None:
        vc = make_mock_vc()
        r = VoiceReceiver(vc)
        r._running = True
        r._on_packet(b"\x00" * 20)
        assert len(r._buffers) == 0

    def test_ignores_when_paused(self) -> None:
        vc = make_mock_vc()
        r = VoiceReceiver(vc)
        r._running = True
        r._paused = True
        r._on_packet(b"\x80\x78" + b"\x00" * 20)
        assert len(r._buffers) == 0

    def test_ignores_when_not_running(self) -> None:
        vc = make_mock_vc()
        r = VoiceReceiver(vc)
        r._running = False
        r._on_packet(b"\x80\x78" + b"\x00" * 20)
        assert len(r._buffers) == 0

    def test_ignores_bot_ssrc(self) -> None:
        vc = make_mock_vc()
        r = VoiceReceiver(vc)
        r._running = True
        header = struct.pack(">BBHII", 0x80, 0x78, 1, 100, 999)
        r._on_packet(header + b"\x00" * 20)
        assert len(r._buffers) == 0

    def test_secretbox_decrypt_path(self) -> None:
        """Test _on_packet with xsalsa20_poly1305_lite mode (SecretBox)."""
        vc = make_mock_vc(mode="xsalsa20_poly1305_lite")
        r = VoiceReceiver(vc)
        r._running = True

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
        vc = make_mock_vc(mode="aead_xchacha20_poly1305_rtpsize")
        r = VoiceReceiver(vc)
        r._running = True

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

    def test_undecryptable_packets_are_dropped(self) -> None:
        """A packet that fails to decrypt is dropped without raising."""
        vc = make_mock_vc(mode="xsalsa20_poly1305_lite")
        r = VoiceReceiver(vc)
        r._running = True

        ssrc = 100
        header = struct.pack(">BBHII", 0x80, 0x78, 1, 100, ssrc)
        packet = header + b"\xab" * 20 + b"\x01\x00\x00\x00"

        with patch("nacl.secret.SecretBox") as mock_sb:
            mock_sb.return_value.decrypt.side_effect = Exception("bad")
            for _ in range(7):
                r._on_packet(packet)

        assert ssrc not in r._buffers

    def test_short_payload_after_header(self) -> None:
        """Packet with valid RTP header but payload too short."""
        vc = make_mock_vc()
        r = VoiceReceiver(vc)
        r._running = True
        ssrc = 100
        header = struct.pack(">BBHII", 0x80, 0x78, 1, 100, ssrc)
        packet = header + b"\x01\x02"
        r._on_packet(packet)
        assert ssrc not in r._buffers

    def test_opus_decode_error_handled(self) -> None:
        """Opus decode failure should not crash."""
        vc = make_mock_vc(mode="xsalsa20_poly1305_lite")
        r = VoiceReceiver(vc)
        r._running = True

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
        vc = make_mock_vc(mode="aead_xchacha20_poly1305_rtpsize")
        r = VoiceReceiver(vc)
        r._running = True

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

        mock_decoder.decode.assert_called_once_with(opus_data, fec=False)

    def test_padding_stripped(self) -> None:
        """Padding bytes should be removed from decrypted payload."""
        vc = make_mock_vc(mode="xsalsa20_poly1305_lite")
        r = VoiceReceiver(vc)
        r._running = True

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

        mock_decoder.decode.assert_called_once_with(opus_data, fec=False)

    def test_padding_invalid_skips(self) -> None:
        """Invalid padding (pad_len > data length) should skip packet."""
        vc = make_mock_vc(mode="xsalsa20_poly1305_lite")
        r = VoiceReceiver(vc)
        r._running = True

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
        vc = make_mock_vc(mode="xsalsa20_poly1305_lite")
        r = VoiceReceiver(vc)
        r._running = True

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
        vc = make_mock_vc(mode="xsalsa20_poly1305_lite")
        r = VoiceReceiver(vc)
        r._running = True

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
        vc = make_mock_vc(mode="xsalsa20_poly1305_lite")
        r = VoiceReceiver(vc)
        r._running = True

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
        dave = MagicMock()
        dave.decrypt.return_value = b"\x00" * 960
        vc = make_mock_vc(mode="xsalsa20_poly1305_lite", dave_session=dave)
        r = VoiceReceiver(vc)
        r._running = True

        ssrc = 100
        r._ssrc_to_user[ssrc] = 42

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
        dave.decrypt.assert_called_once()

    def test_dave_decrypt_no_user_passthrough(self) -> None:
        """DAVE decrypt with unknown SSRC should pass through."""
        vc = make_mock_vc()
        r = VoiceReceiver(vc)
        dave = MagicMock()

        result = r._dave_decrypt(dave, 999, b"\x00" * 100)
        assert result == b"\x00" * 100
        dave.decrypt.assert_not_called()

    def test_dave_decrypt_unencrypted_passthrough(self) -> None:
        """DAVE 'Unencrypted' exception should pass through payload."""
        vc = make_mock_vc()
        r = VoiceReceiver(vc)
        r._ssrc_to_user[100] = 42
        dave = MagicMock()
        dave.decrypt.side_effect = Exception("Unencrypted frame")

        result = r._dave_decrypt(dave, 100, b"\xab" * 50)
        assert result == b"\xab" * 50

    def test_dave_decrypt_real_error_propagates(self) -> None:
        """A real DAVE decrypt error reaches the caller, which counts it."""
        vc = make_mock_vc()
        r = VoiceReceiver(vc)
        r._ssrc_to_user[100] = 42
        dave = MagicMock()
        dave.decrypt.side_effect = RuntimeError("key expired")

        with pytest.raises(RuntimeError, match="key expired"):
            r._dave_decrypt(dave, 100, b"\xab" * 50)


class TestDecryptPayload:
    def test_aead_mode(self) -> None:
        vc = make_mock_vc()
        r = VoiceReceiver(vc)
        credentials = _Credentials(b"\x00" * 32, "aead_xchacha20_poly1305_rtpsize", 999, None)

        with patch("nacl.secret.Aead") as MockAead:
            mock_aead = MagicMock()
            mock_aead.decrypt.return_value = b"decrypted"
            MockAead.return_value = mock_aead

            result = r._decrypt_payload(credentials, b"encrypted", b"header", b"\x00" * 24)
            assert result == b"decrypted"
            MockAead.assert_called_once_with(b"\x00" * 32)

    def test_xchacha_mode(self) -> None:
        vc = make_mock_vc()
        r = VoiceReceiver(vc)
        credentials = _Credentials(b"\x00" * 32, "xchacha_something", 999, None)

        with patch("nacl.secret.Aead") as MockAead:
            mock_aead = MagicMock()
            mock_aead.decrypt.return_value = b"decrypted"
            MockAead.return_value = mock_aead

            result = r._decrypt_payload(credentials, b"encrypted", b"header", b"\x00" * 24)
            assert result == b"decrypted"

    def test_secretbox_mode(self) -> None:
        vc = make_mock_vc()
        r = VoiceReceiver(vc)
        credentials = _Credentials(b"\x00" * 32, "xsalsa20_poly1305_lite", 999, None)

        with patch("nacl.secret.SecretBox") as MockSB:
            mock_sb = MagicMock()
            mock_sb.decrypt.return_value = b"decrypted"
            MockSB.return_value = mock_sb

            result = r._decrypt_payload(credentials, b"encrypted", b"header", b"\x00" * 24)
            assert result == b"decrypted"
            MockSB.assert_called_once_with(b"\x00" * 32)
