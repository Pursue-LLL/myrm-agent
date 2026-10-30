"""VoiceReceiver lifecycle, speaking hook, silence detection, SSRC inference and PCM-to-WAV conversion."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

pytest.importorskip("discord")

from app.channels.providers.discord.voice.receiver import (
    _BYTES_PER_SECOND,
    _MIN_SPEECH_DURATION,
    _SILENCE_THRESHOLD,
    VoiceReceiver,
)
from tests.channels.providers.discord.voice.receiver_testkit import make_mock_vc


class TestVoiceReceiverInit:
    def test_init_defaults(self) -> None:
        vc = make_mock_vc()
        r = VoiceReceiver(vc)
        assert not r.running
        assert r._allowed_user_ids == set()
        assert not r._paused

    def test_init_with_allowed_users(self) -> None:
        vc = make_mock_vc()
        r = VoiceReceiver(vc, allowed_user_ids={"100", "200"})
        assert r._allowed_user_ids == {"100", "200"}


class TestVoiceReceiverLifecycle:
    def test_start_sets_running(self) -> None:
        vc = make_mock_vc()
        r = VoiceReceiver(vc)
        r.start()
        assert r.running
        vc._connection.add_socket_listener.assert_called_once()

    def test_stop_clears_state(self) -> None:
        vc = make_mock_vc()
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
        vc = make_mock_vc()
        r = VoiceReceiver(vc)
        r.start()
        vc._connection.remove_socket_listener.side_effect = RuntimeError("fail")
        r.stop()
        assert not r.running

    def test_pause_resume(self) -> None:
        vc = make_mock_vc()
        r = VoiceReceiver(vc)
        assert not r._paused
        r.pause()
        assert r._paused
        r.resume()
        assert not r._paused


class TestSpeakingHook:
    def test_speaking_hook_maps_ssrc(self) -> None:
        vc = make_mock_vc()
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
        vc = make_mock_vc()
        r = VoiceReceiver(vc)
        r.start()

        hook = vc._connection.hook
        import asyncio

        msg = {"op": 3, "d": {"ssrc": 100, "user_id": 42}}
        asyncio.run(hook(MagicMock(), msg))
        assert 100 not in r._ssrc_to_user

    def test_speaking_hook_ws_set_error(self) -> None:
        vc = make_mock_vc()
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
        vc = make_mock_vc()
        r = VoiceReceiver(vc)
        r._map_ssrc(200, 55)
        assert r._ssrc_to_user[200] == 55


class TestSilenceDetection:
    def test_empty_buffers(self) -> None:
        vc = make_mock_vc()
        r = VoiceReceiver(vc)
        r._running = True
        assert r.check_silence() == []

    def test_detects_completed_utterance(self) -> None:
        vc = make_mock_vc()
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
        vc = make_mock_vc()
        r = VoiceReceiver(vc)
        r._running = True

        ssrc = 100
        r._ssrc_to_user[ssrc] = 42
        r._buffers[ssrc] = bytearray(b"\x00" * 100)
        r._last_packet_time[ssrc] = time.monotonic() - _SILENCE_THRESHOLD - 0.1

        completed = r.check_silence()
        assert len(completed) == 0

    def test_discards_stale_unmapped_buffer(self) -> None:
        vc = make_mock_vc()
        r = VoiceReceiver(vc)
        r._running = True

        ssrc = 100
        r._buffers[ssrc] = bytearray(b"\x00" * 100)
        r._last_packet_time[ssrc] = time.monotonic() - _SILENCE_THRESHOLD * 2 - 1

        r.check_silence()
        assert ssrc not in r._buffers

    def test_infer_user_during_silence_check(self) -> None:
        """check_silence should call _infer_user_for_ssrc for unmapped SSRC."""
        vc = make_mock_vc()
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
        vc = make_mock_vc()
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
        vc = make_mock_vc()
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
        vc = make_mock_vc()
        vc.channel.members = [vc.user]

        r = VoiceReceiver(vc)
        r._running = True
        result = r._infer_user_for_ssrc(100)
        assert result == 0

    def test_multiple_candidates_no_infer(self) -> None:
        vc = make_mock_vc()
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
        vc = make_mock_vc()
        vc.channel = None

        r = VoiceReceiver(vc)
        r._running = True
        result = r._infer_user_for_ssrc(100)
        assert result == 0

    def test_infer_with_allowed_filter(self) -> None:
        vc = make_mock_vc()
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
        vc = make_mock_vc()
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
