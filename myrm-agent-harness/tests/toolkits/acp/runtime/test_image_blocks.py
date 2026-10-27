"""Image files become base64 blocks: the format comes from the first bytes, and no file is trusted by its name."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.acp.runtime.image_blocks import ImageBlock, load_image_blocks

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 8
_GIF87 = b"GIF87a" + b"\x00" * 8
_GIF89 = b"GIF89a" + b"\x00" * 8
_WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 "
_WAV = b"RIFF\x24\x00\x00\x00WAVEfmt "
_LOGGER = "myrm_agent_harness.toolkits.acp.runtime.image_blocks"


class TestFormats:
    @pytest.mark.parametrize(
        ("data", "media_type"),
        [
            (_PNG, "image/png"),
            (_JPEG, "image/jpeg"),
            (_GIF87, "image/gif"),
            (_GIF89, "image/gif"),
            (_WEBP, "image/webp"),
        ],
    )
    def test_the_formats_the_claude_api_takes_are_told_by_their_first_bytes(
        self, tmp_path: Path, data: bytes, media_type: str
    ) -> None:
        path = tmp_path / "image.bin"
        path.write_bytes(data)

        assert [block.media_type for block in load_image_blocks([str(path)])] == [media_type]

    @pytest.mark.parametrize(
        "data",
        [
            _WAV,
            b"%PDF-1.7\n%\xe2\xe3\xcf\xd3",
            b"<svg xmlns=",
            b"BM" + b"\x00" * 10,
            b"BM25 results are in",
            b"GIF90a" + b"\x00" * 8,
            b"\xff\xd8\xff",
            b"",
            b"\x89PNG",
            b"RIFF",
        ],
        ids=[
            "wav",
            "pdf",
            "svg",
            "bmp",
            "text-that-starts-with-bm",
            "gif-90a",
            "three-byte-jpeg",
            "empty",
            "short-png",
            "short-riff",
        ],
    )
    def test_anything_else_is_not_an_image(self, tmp_path: Path, data: bytes) -> None:
        path = tmp_path / "other.png"
        path.write_bytes(data)

        assert load_image_blocks([str(path)]) == []


class TestLoadImageBlocks:
    def test_the_blocks_keep_the_order_of_the_paths_and_carry_the_file_bytes(self, tmp_path: Path) -> None:
        first = tmp_path / "Application Support" / "张 三.png"
        first.parent.mkdir()
        first.write_bytes(_PNG + b"first")
        second = tmp_path / "b.jpg"
        second.write_bytes(_JPEG + b"second")

        blocks = load_image_blocks([str(first), str(second)])

        assert [block.media_type for block in blocks] == ["image/png", "image/jpeg"]
        assert [base64.b64decode(block.data) for block in blocks] == [_PNG + b"first", _JPEG + b"second"]

    def test_an_image_far_above_the_size_a_cli_file_mention_gives_up_on_arrives_whole(self, tmp_path: Path) -> None:
        body = _PNG + bytes(range(256)) * 20_000  # about 5 MB
        path = tmp_path / "big.png"
        path.write_bytes(body)

        (block,) = load_image_blocks([str(path)])

        assert base64.b64decode(block.data) == body

    def test_the_type_comes_from_the_content_not_from_the_file_name(self, tmp_path: Path) -> None:
        path = tmp_path / "photo.png"
        path.write_bytes(_JPEG)

        assert load_image_blocks([str(path)]) == [ImageBlock("image/jpeg", base64.b64encode(_JPEG).decode())]

    def test_a_file_that_is_not_an_image_is_left_out_and_logged_without_its_path(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        text = tmp_path / "secret-user" / "notes.png"
        text.parent.mkdir()
        text.write_text("not an image")
        good = tmp_path / "ok.gif"
        good.write_bytes(_GIF89)

        with caplog.at_level("WARNING", logger=_LOGGER):
            blocks = load_image_blocks([str(text), str(good)])

        assert [block.media_type for block in blocks] == ["image/gif"]
        assert [record.getMessage() for record in caplog.records] == ["image_skipped reason=unknown_format"]

    def test_a_missing_or_unreadable_path_is_left_out_and_logged_without_its_path(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level("WARNING", logger=_LOGGER):
            blocks = load_image_blocks([str(tmp_path / "secret-user" / "gone.png"), str(tmp_path)])

        assert blocks == []
        assert [record.getMessage() for record in caplog.records] == [
            "image_skipped reason=unreadable error=FileNotFoundError",
            "image_skipped reason=unreadable error=IsADirectoryError",
        ]
        assert "secret-user" not in caplog.text

    def test_no_paths_make_no_blocks(self) -> None:
        assert load_image_blocks([]) == []
