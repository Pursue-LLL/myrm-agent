"""Unit tests for VoicePlayer."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("discord")

from app.channels.providers.discord.voice.player import (
    VoicePlayer,
)


class TestVoicePlayerInit:
    def test_defaults(self) -> None:
        vc = MagicMock()
        p = VoicePlayer(vc)
        assert not p.is_playing
        assert p._receiver is None

    def test_with_receiver(self) -> None:
        vc = MagicMock()
        receiver = MagicMock()
        p = VoicePlayer(vc, receiver)
        assert p._receiver is receiver


class TestVoicePlayerPlay:
    @pytest.mark.asyncio
    async def test_play_nonexistent_file(self, tmp_path: Path) -> None:
        vc = MagicMock()
        p = VoicePlayer(vc)
        result = await p.play(tmp_path / "nonexistent.mp3")
        assert result is False

    @pytest.mark.asyncio
    async def test_play_not_connected(self, tmp_path: Path) -> None:
        vc = MagicMock()
        vc.is_connected.return_value = False
        p = VoicePlayer(vc)

        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"\x00" * 100)

        result = await p.play(audio)
        assert result is False

    @pytest.mark.asyncio
    async def test_play_pauses_receiver(self, tmp_path: Path) -> None:
        vc = MagicMock()
        vc.is_connected.return_value = True
        vc.is_playing.return_value = False
        receiver = MagicMock()

        def mock_play(source, after=None):
            if after:
                after(None)

        vc.play = mock_play

        p = VoicePlayer(vc, receiver)
        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"\x00" * 100)

        with patch("discord.FFmpegPCMAudio"):
            await p.play(audio)

        receiver.pause.assert_called_once()
        receiver.resume.assert_called()

    @pytest.mark.asyncio
    async def test_play_stops_current(self, tmp_path: Path) -> None:
        vc = MagicMock()
        vc.is_connected.return_value = True
        vc.is_playing.return_value = True

        def mock_play(source, after=None):
            if after:
                after(None)

        vc.play = mock_play
        p = VoicePlayer(vc)

        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"\x00" * 100)

        with patch("discord.FFmpegPCMAudio"):
            await p.play(audio)

        vc.stop.assert_called()

    @pytest.mark.asyncio
    async def test_play_with_error_callback(self, tmp_path: Path) -> None:
        vc = MagicMock()
        vc.is_connected.return_value = True
        vc.is_playing.return_value = False
        receiver = MagicMock()

        def mock_play(source, after=None):
            if after:
                after(Exception("codec error"))

        vc.play = mock_play
        p = VoicePlayer(vc, receiver)

        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"\x00" * 100)

        with patch("discord.FFmpegPCMAudio"):
            result = await p.play(audio)

        assert result is True
        receiver.resume.assert_called()

    @pytest.mark.asyncio
    async def test_play_timeout(self, tmp_path: Path) -> None:
        vc = MagicMock()
        vc.is_connected.return_value = True
        vc.is_playing.return_value = False
        receiver = MagicMock()

        vc.play = MagicMock()

        p = VoicePlayer(vc, receiver)
        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"\x00" * 100)

        with (
            patch("discord.FFmpegPCMAudio"),
            patch(
                "app.channels.providers.discord.voice.player._PLAYBACK_TIMEOUT",
                0.01,
            ),
        ):
            result = await p.play(audio)

        assert result is False
        vc.stop.assert_called()
        receiver.resume.assert_called()
        assert not p.is_playing

    @pytest.mark.asyncio
    async def test_play_exception(self, tmp_path: Path) -> None:
        vc = MagicMock()
        vc.is_connected.return_value = True
        vc.is_playing.return_value = False
        receiver = MagicMock()

        p = VoicePlayer(vc, receiver)
        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"\x00" * 100)

        with patch("discord.FFmpegPCMAudio", side_effect=RuntimeError("no ffmpeg")):
            result = await p.play(audio)

        assert result is False
        assert not p.is_playing
        receiver.resume.assert_called()

    @pytest.mark.asyncio
    async def test_play_no_receiver_timeout(self, tmp_path: Path) -> None:
        vc = MagicMock()
        vc.is_connected.return_value = True
        vc.is_playing.return_value = False

        vc.play = MagicMock()

        p = VoicePlayer(vc)
        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"\x00" * 100)

        with (
            patch("discord.FFmpegPCMAudio"),
            patch(
                "app.channels.providers.discord.voice.player._PLAYBACK_TIMEOUT",
                0.01,
            ),
        ):
            result = await p.play(audio)

        assert result is False

    @pytest.mark.asyncio
    async def test_play_no_receiver_exception(self, tmp_path: Path) -> None:
        vc = MagicMock()
        vc.is_connected.return_value = True
        vc.is_playing.return_value = False

        p = VoicePlayer(vc)
        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"\x00" * 100)

        with patch("discord.FFmpegPCMAudio", side_effect=RuntimeError("fail")):
            result = await p.play(audio)

        assert result is False

    @pytest.mark.asyncio
    async def test_stop(self) -> None:
        vc = MagicMock()
        vc.is_playing.return_value = True
        receiver = MagicMock()
        p = VoicePlayer(vc, receiver)
        p._playing = True

        p.stop()
        vc.stop.assert_called_once()
        assert not p.is_playing
        receiver.resume.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_not_playing(self) -> None:
        vc = MagicMock()
        vc.is_playing.return_value = False
        p = VoicePlayer(vc)
        p._playing = True

        p.stop()
        vc.stop.assert_not_called()
        assert not p.is_playing

    @pytest.mark.asyncio
    async def test_stop_no_receiver(self) -> None:
        vc = MagicMock()
        vc.is_playing.return_value = True
        p = VoicePlayer(vc)
        p._playing = True

        p.stop()
        vc.stop.assert_called_once()
        assert not p.is_playing
