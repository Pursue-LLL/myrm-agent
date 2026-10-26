"""Reading side of the workspace text editor I/O: content, version, editable verdict, line-ending / BOM style."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.services.files import text_edit_io
from app.services.files.text_edit_io import (
    EDITABLE_MAX_BYTES,
    NotEditable,
    TextStyle,
    read_text_snapshot,
    text_style_of,
    version_of,
    write_text_if_version,
)

BOM = b"\xef\xbb\xbf"


def _file(tmp_path: Path, data: bytes, name: str = "note.txt") -> str:
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------------------
# Reading: content, version and the editable verdict
# --------------------------------------------------------------------------------------


def test_plain_file_is_editable_with_content_hash_version(tmp_path: Path) -> None:
    raw = "héllo\nworld\n".encode()
    snapshot = read_text_snapshot(_file(tmp_path, raw))

    assert snapshot.editable
    assert snapshot.content == "héllo\nworld\n"
    assert snapshot.version == _sha(raw) == version_of(raw)
    assert snapshot.size == len(raw)
    assert snapshot.style == TextStyle("lf", False)
    assert not snapshot.truncated


@pytest.mark.parametrize(
    ("raw", "style", "content"),
    [
        (b"a\r\nb\r\n", TextStyle("crlf", False), "a\nb\n"),
        (BOM + b"a\nb\n", TextStyle("lf", True), "a\nb\n"),
        (BOM + b"name,city\r\n\xe5\xbc\xa0,\xe5\x8c\x97\r\n", TextStyle("crlf", True), "name,city\n张,北\n"),
        (b"no newline at all", TextStyle("lf", False), "no newline at all"),
        (b"", TextStyle("lf", False), ""),
    ],
)
def test_line_endings_and_bom_are_reported_not_baked_into_content(
    tmp_path: Path, raw: bytes, style: TextStyle, content: str
) -> None:
    snapshot = read_text_snapshot(_file(tmp_path, raw))
    assert snapshot.editable
    assert (snapshot.style, snapshot.content) == (style, content)


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (b"MZ\x00\x01binary", "binary"),
        (b"\xd0\xd5\xc3\xfb,\xb3\xc7\xca\xd0\n", "not_utf8"),
        (b"a\r\nb\nc\r\n", "mixed_line_endings"),
        (b"old mac\rline\r", "mixed_line_endings"),
    ],
)
def test_files_the_editor_cannot_round_trip_are_read_only_but_still_viewable(tmp_path: Path, raw: bytes, reason: str) -> None:
    snapshot = read_text_snapshot(_file(tmp_path, raw))

    assert not snapshot.editable
    assert snapshot.readonly_reason == reason
    assert snapshot.version == _sha(raw)
    if reason != "binary":
        assert snapshot.content != ""


def test_oversized_file_is_a_read_only_prefix_and_is_not_hashed(tmp_path: Path) -> None:
    raw = b"x" * (EDITABLE_MAX_BYTES + 5000)
    snapshot = read_text_snapshot(_file(tmp_path, raw))

    assert snapshot.readonly_reason == "too_large"
    assert snapshot.truncated
    assert snapshot.version == ""
    assert snapshot.size == len(raw)
    assert len(snapshot.content) == EDITABLE_MAX_BYTES


class _ReadSpy:
    """File handle wrapper recording how many bytes each ``read`` asked for."""

    sizes: list[int | None] = []

    def __init__(self, path: str, mode: str) -> None:
        self._handle = open(path, mode)  # noqa: SIM115 - closed by __exit__

    def read(self, size: int | None = -1) -> bytes:
        self.sizes.append(size)
        return self._handle.read(size)

    def fileno(self) -> int:
        return self._handle.fileno()

    def __enter__(self) -> _ReadSpy:
        return self

    def __exit__(self, *_exc: object) -> None:
        self._handle.close()


def _spy_on_reads(monkeypatch: pytest.MonkeyPatch) -> list[int | None]:
    _ReadSpy.sizes = []
    monkeypatch.setattr(text_edit_io, "open", _ReadSpy, raising=False)
    return _ReadSpy.sizes


def test_an_oversized_file_is_never_read_beyond_the_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _file(tmp_path, b"x" * (EDITABLE_MAX_BYTES * 4))
    sizes = _spy_on_reads(monkeypatch)

    read_text_snapshot(path)
    with pytest.raises(NotEditable):
        write_text_if_version(path, "x", "0" * 64)

    assert sizes == [EDITABLE_MAX_BYTES + 1, EDITABLE_MAX_BYTES + 1]


def test_binary_wins_over_too_large(tmp_path: Path) -> None:
    raw = b"\x00" + b"x" * (EDITABLE_MAX_BYTES + 10)
    assert read_text_snapshot(_file(tmp_path, raw)).readonly_reason == "binary"


def test_preview_cut_inside_a_multibyte_character_shows_no_replacement_character(tmp_path: Path) -> None:
    raw = b"a" * (EDITABLE_MAX_BYTES - 1) + "é".encode() + b"tail"
    snapshot = read_text_snapshot(_file(tmp_path, raw))

    assert snapshot.truncated
    assert "\ufffd" not in snapshot.content


def test_text_style_of_falls_back_to_lf_for_unreadable_or_read_only_files(tmp_path: Path) -> None:
    assert text_style_of(_file(tmp_path, BOM + b"a\r\n")) == TextStyle("crlf", True)
    assert text_style_of(_file(tmp_path, b"\x00bin", "b.bin")) == TextStyle()
    assert text_style_of(str(tmp_path / "missing.txt")) == TextStyle()
