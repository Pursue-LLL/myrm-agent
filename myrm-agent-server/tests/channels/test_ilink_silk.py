"""Tests for ilink_silk module (SILK audio conversion)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.channels.providers._ilink.silk import silk_to_wav


class TestSilkToWav:
    def test_success(self, tmp_path: Path) -> None:
        silk_path = tmp_path / "voice.silk"
        silk_path.write_bytes(b"silk data")
        wav_path = tmp_path / "voice.wav"

        mock_pilk = MagicMock()

        def fake_convert(src: str, dst: str, rate: int) -> None:
            Path(dst).write_bytes(b"wav data")

        mock_pilk.silk_to_wav = fake_convert

        with patch.dict("sys.modules", {"pilk": mock_pilk}):
            result = silk_to_wav(silk_path, wav_path)

        assert result is True
        assert wav_path.exists()

    def test_pilk_not_installed(self, tmp_path: Path) -> None:
        silk_path = tmp_path / "voice.silk"
        silk_path.write_bytes(b"silk data")
        wav_path = tmp_path / "voice.wav"

        with (
            patch.dict("sys.modules", {"pilk": None}),
            patch(
                "app.channels.providers._ilink.silk.silk_to_wav",
            ) as mock_fn,
        ):
            mock_fn.return_value = False
            result = mock_fn(silk_path, wav_path)

        assert result is False

    def test_conversion_failure(self, tmp_path: Path) -> None:
        silk_path = tmp_path / "voice.silk"
        silk_path.write_bytes(b"silk data")
        wav_path = tmp_path / "voice.wav"

        mock_pilk = MagicMock()
        mock_pilk.silk_to_wav.side_effect = RuntimeError("decode error")

        with patch.dict("sys.modules", {"pilk": mock_pilk}):
            result = silk_to_wav(silk_path, wav_path)

        assert result is False

    def test_custom_sample_rate(self, tmp_path: Path) -> None:
        silk_path = tmp_path / "voice.silk"
        silk_path.write_bytes(b"silk data")
        wav_path = tmp_path / "voice.wav"

        mock_pilk = MagicMock()

        def fake_convert(src: str, dst: str, rate: int) -> None:
            assert rate == 16000
            Path(dst).write_bytes(b"wav data")

        mock_pilk.silk_to_wav = fake_convert

        with patch.dict("sys.modules", {"pilk": mock_pilk}):
            result = silk_to_wav(silk_path, wav_path, sample_rate=16000)

        assert result is True
