"""Stored template-file format: capacity ceilings, encoding round trip, safe materialization."""

from __future__ import annotations

import base64
from pathlib import Path

from myrm_agent_harness.agent.plugins.rules import MAX_TEMPLATE_FILE_BYTES, MAX_TOTAL_TEMPLATE_BYTES

from app.services.plugins.template_workspace import (
    OVERSIZED_FILE,
    TOTAL_SIZE_EXCEEDED,
    decode_template_files,
    encode_template_files,
    materialize_template_workspace_files,
)


class TestEncode:
    def test_text_stays_text_and_binary_is_base64(self) -> None:
        encoded = encode_template_files({"notes.md": b"hello", "logo.png": b"\x89PNG\x00\xff"})

        assert encoded.files["notes.md"] == "hello"
        assert encoded.files["logo.png"] == "base64:" + base64.b64encode(b"\x89PNG\x00\xff").decode()
        assert encoded.skipped == ()

    def test_oversized_file_is_skipped_not_truncated(self) -> None:
        encoded = encode_template_files({"big.txt": b"x" * (MAX_TEMPLATE_FILE_BYTES + 1), "ok.txt": b"ok"})

        assert encoded.files == {"ok.txt": "ok"}
        assert encoded.skipped == (("big.txt", OVERSIZED_FILE),)

    def test_total_ceiling_skips_the_overflowing_file_but_later_small_files_still_fit(self) -> None:
        files: dict[str, bytes] = {}
        remaining = MAX_TOTAL_TEMPLATE_BYTES - 100  # leave 100 bytes of headroom
        index = 0
        while remaining > 0:
            size = min(MAX_TEMPLATE_FILE_BYTES, remaining)
            files[f"part{index}.txt"] = b"a" * size
            remaining -= size
            index += 1
        files["over.txt"] = b"b" * 200
        files["tiny.txt"] = b"c" * 50

        encoded = encode_template_files(files)

        assert encoded.skipped == (("over.txt", TOTAL_SIZE_EXCEEDED),)
        assert "tiny.txt" in encoded.files

    def test_decode_is_the_inverse_of_encode(self) -> None:
        original = {"a/b.txt": b"text", "bin.dat": b"\x00\x01\xfe\xff", "unicode.md": "héllo".encode()}

        assert decode_template_files(encode_template_files(original).files) == original

    def test_decode_drops_malformed_entries(self) -> None:
        stored = {"ok.txt": "fine", "bad.bin": "base64:***", "": "empty-name", "num": 5}

        assert decode_template_files(stored) == {"ok.txt": b"fine"}


class TestMaterialize:
    def test_writes_text_and_binary_files(self, tmp_path: Path) -> None:
        stored = encode_template_files({"docs/readme.md": b"hi", "img.bin": b"\x00\xff"}).files

        written = materialize_template_workspace_files(dict(stored), tmp_path)

        assert sorted(written) == ["docs/readme.md", "img.bin"]
        assert (tmp_path / "docs" / "readme.md").read_bytes() == b"hi"
        assert (tmp_path / "img.bin").read_bytes() == b"\x00\xff"

    def test_never_overwrites_existing_files(self, tmp_path: Path) -> None:
        (tmp_path / "keep.txt").write_text("mine")

        written = materialize_template_workspace_files({"keep.txt": "template"}, tmp_path)

        assert written == []
        assert (tmp_path / "keep.txt").read_text() == "mine"

    def test_blocks_path_traversal(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()

        written = materialize_template_workspace_files({"../escape.txt": "x", "a/../../escape2.txt": "y"}, workspace)

        assert written == []
        assert not (tmp_path / "escape.txt").exists() and not (tmp_path / "escape2.txt").exists()

    def test_absolute_paths_stay_inside_the_workspace(self, tmp_path: Path) -> None:
        written = materialize_template_workspace_files({"/etc/passwd-copy": "x", "C:\\temp\\f.txt": "y"}, tmp_path)

        assert "etc/passwd-copy" in written
        assert (tmp_path / "etc" / "passwd-copy").read_text() == "x"

    def test_invalid_base64_and_non_dict_input_are_ignored(self, tmp_path: Path) -> None:
        assert materialize_template_workspace_files({"bad.bin": "base64:***"}, tmp_path) == []
        assert materialize_template_workspace_files(None, tmp_path) == []
        assert materialize_template_workspace_files({}, tmp_path) == []
